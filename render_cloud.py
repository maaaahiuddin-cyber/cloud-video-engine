import os
import re
import sys
import glob
import json
import math
import random
import urllib.parse
import textwrap
import requests
import subprocess

# Auto-install required packages if missing in workflow YAML
try:
    import soundfile as sf
    import numpy as np
    from kokoro_onnx import Kokoro
except ImportError:
    subprocess.run([
        sys.executable, "-m", "pip", "install",
        "kokoro-onnx", "soundfile", "numpy", "edge-tts", "gTTS"
    ], check=True)
    import soundfile as sf
    import numpy as np
    from kokoro_onnx import Kokoro

# 1. Auto-sanitize CLOUDINARY_URL BEFORE importing cloudinary
raw_cloud = os.environ.get("CLOUDINARY_URL", "").strip().strip('"').strip("'")
if raw_cloud.startswith("CLOUDINARY_URL="):
    raw_cloud = raw_cloud.split("CLOUDINARY_URL=", 1)[1].strip().strip('"').strip("'")
os.environ["CLOUDINARY_URL"] = raw_cloud

import cloudinary
import cloudinary.uploader

try:
    if raw_cloud.startswith("cloudinary://") and "@" in raw_cloud:
        creds, cloud_name = raw_cloud.replace("cloudinary://", "", 1).split("@", 1)
        api_key, api_secret = creds.split(":", 1)
        cloudinary.config(
            cloud_name=cloud_name.strip(),
            api_key=api_key.strip(),
            api_secret=api_secret.strip(),
            secure=True
        )
except Exception as e:
    print(f"Cloudinary URL parse warning: {e}")

# 2. Load payload sent from Google Sheets
raw_payload = os.environ.get("PAYLOAD_JSON", "{}")
try:
    payload = json.loads(raw_payload) if raw_payload else {}
except Exception:
    payload = {}

BEARDED_DRAGON_SCRIPTS = [
    (
        "Back leg stretched out so neat\n"
        "Resting on warm sunny feet\n"
        "Zero worries in the whole wide room\n"
        "Pure comfort in the afternoon\n"
        "A little dinosaur full of grace\n"
        "Stealing hearts in every place"
    ),
    (
        "Warm heat lamp glowing bright\n"
        "Tiny dragon basking in the light\n"
        "One slow blink and a judging side-eye\n"
        "Living the royal reptile life\n"
        "No rent, no rush, just warm rocks\n"
        "My scaly little best friend"
    ),
    (
        "Slow head tilt when I walk by\n"
        "Deep dark eyes that never lie\n"
        "Listening closely to every sound\n"
        "The sweetest companion I ever found\n"
        "Curious heart in a spiky coat\n"
        "Taking in every word I spoke"
    ),
    (
        "Sunbeam warming up the floor\n"
        "Nothing else could matter more\n"
        "A quiet pause in a busy day\n"
        "Watching my little dragon stay\n"
        "Gentle company, soft and slow\n"
        "The sweetest calm I'll ever know"
    ),
    (
        "Lights dim low as evening falls\n"
        "Soft shadows dance across the walls\n"
        "Curled up snug in a cozy spot\n"
        "The gentlest little soul I've got\n"
        "Drift into a peaceful dream\n"
        "Brighter than a golden beam"
    ),
]

row_id = str(payload.get("row_id", "1")).strip()
niche = str(payload.get("niche", "bearded dragon")).strip() or "bearded dragon"
raw_overlay_input = str(payload.get("overlay_text", "")).strip()
if raw_overlay_input:
    overlay_text = raw_overlay_input
else:
    try:
        overlay_text = BEARDED_DRAGON_SCRIPTS[(max(1, int(row_id)) - 1) % len(BEARDED_DRAGON_SCRIPTS)]
    except Exception:
        overlay_text = BEARDED_DRAGON_SCRIPTS[0]

search_keyword = str(payload.get("search_keyword", "bearded dragon")).strip() or "bearded dragon"
fallback_keyword = str(payload.get("fallback_keyword", "reptile")).strip() or "reptile"
drive_video_url = str(payload.get("drive_video_url", "")).strip()
caption = str(payload.get(
    "caption",
    "Quiet basking moments with a bearded dragon.\n\nTag a fellow beardie lover.\n\n#beardeddragon #beardie #reptilelover #petreels"
)).strip()

PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "").strip().strip('"').strip("'")
FREESOUND_API_KEY = os.environ.get("FREESOUND_API_KEY", "").strip().strip('"').strip("'")

PRIMARY_MAKE_WEBHOOK = "https://hook.us2.make.com/ga5opcigaf8fw3keq4zh5x5uy2r6gs24"
raw_webhook = os.environ.get("MAKE_WEBHOOK_URL", "").strip().strip('"').strip("'")
if raw_webhook.startswith("MAKE_WEBHOOK_URL="):
    raw_webhook = raw_webhook.split("MAKE_WEBHOOK_URL=", 1)[1].strip().strip('"').strip("'")
MAKE_WEBHOOK_URL = raw_webhook if raw_webhook.startswith("http") else PRIMARY_MAKE_WEBHOOK

VO_START_DELAY = 0.6          # Voiceover starts at 0.6 seconds
EXTRA_TAIL_SECONDS = 2.0      # Tail when video is shorter than voiceover
AUDIO_FADE_DURATION = 1.50    # Smooth 1.50s audio fade-out at the end
MIN_VIDEO_DURATION = 12.0     # Minimum reel length in seconds

BANNED_VISUAL_TAGS = {
    "animation", "animated", "cartoon", "anime", "3d", "cgi", "render",
    "illustration", "drawing", "sketch", "painting", "art", "abstract",
    "fractal", "vj", "neon", "cyberpunk", "sci-fi", "fantasy", "ai",
    "generated", "digital", "graphic", "motion graphics", "particles",
    "matrix", "tunnel", "kaleidoscope", "geometry", "game", "virtual"
}


def ensure_assets():
    """Downloads Kokoro-82M ONNX models and serif font."""
    model_path = "kokoro-v1.0.int8.onnx"
    voices_path = "voices-v1.0.bin"
    font_path = "PoetrySerif.ttf"

    if not os.path.exists(model_path) or os.path.getsize(model_path) < 10_000_000:
        print("Downloading Kokoro-82M int8 model...")
        r = requests.get(
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx",
            timeout=120
        )
        with open(model_path, "wb") as f:
            f.write(r.content)

    if not os.path.exists(voices_path) or os.path.getsize(voices_path) < 1_000_000:
        print("Downloading Kokoro-82M voices pack...")
        r = requests.get(
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
            timeout=60
        )
        with open(voices_path, "wb") as f:
            f.write(r.content)

    if not os.path.exists(font_path) or os.path.getsize(font_path) < 40_000:
        font_urls = [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/crimsontext/CrimsonText-Regular.ttf",
            "https://raw.githubusercontent.com/google/fonts/main/ofl/lora/Lora%5Bwght%5D.ttf",
        ]
        for f_url in font_urls:
            try:
                r = requests.get(f_url, timeout=25)
                if r.status_code == 200 and len(r.content) > 40_000:
                    with open(font_path, "wb") as f:
                        f.write(r.content)
                    break
            except Exception as e:
                print(f"Font attempt skipped: {e}")


def get_quote_font_path():
    for p in [
        "PoetrySerif.ttf",
        "/usr/share/fonts/truetype/ebgaramond/EBGaramond12-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    ]:
        if os.path.exists(p) and os.path.getsize(p) > 20_000:
            return p
    return "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"


def prepare_overlay_lines(body_text, sentence_start_times=None):
    """
    Prepares ONLY the English overlay text lines (no title, no watermark, no end text)
    for center-bottom placement.
    """
    cleaned = (body_text or "").replace("\r\n", "\n").replace("\u2028", "\n").replace("\u2029", "\n").strip()
    if not cleaned:
        cleaned = BEARDED_DRAGON_SCRIPTS[0]

    raw_lines = [l.strip() for l in cleaned.split("\n") if l.strip()]
    if len(raw_lines) == 1 and ". " in cleaned:
        lines_source = [s.strip() for s in re.split(r'(?<=[.!?])\s+', cleaned) if s.strip()]
    else:
        lines_source = raw_lines

    items = []
    current_y = 0
    line_height = 56
    file_idx = 0

    for idx, src_line in enumerate(lines_source):
        if sentence_start_times and idx < len(sentence_start_times):
            base_t = sentence_start_times[idx]
        else:
            base_t = round(VO_START_DELAY + (idx * 1.9), 2)

        wrapped = textwrap.wrap(src_line, width=32) or [src_line]
        for w_idx, w_line in enumerate(wrapped):
            fname = f"overlay_line_{file_idx}.txt"
            with open(fname, "w", encoding="utf-8", newline="\n") as f:
                f.write(w_line)
            items.append({
                "fname": fname,
                "rel_y": current_y,
                "fontsize": 44,
                "fontcolor": "#FFFFFF",
                "start_t": round(base_t + (w_idx * 0.18), 2)
            })
            current_y += line_height
            file_idx += 1

    total_height = max(current_y, line_height)
    return items, total_height


def get_duration(filename):
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", filename
        ], text=True).strip()
        return float(out)
    except Exception:
        return 10.0


def generate_kokoro_asmr_voiceover(text):
    """Generates pure English Kokoro-82M voiceover directly from Overlay_Text."""
    clean_spoken = re.sub(r'\s{2,}', ' ', (text or "").replace("…", ", ").replace("...", ", ")).strip()
    chunks = re.split(r'(?<=[.!?])\s+|\n+', clean_spoken.replace("\r", ""))
    phrases = [c.strip() for c in chunks if c.strip()]
    if not phrases:
        phrases = ["Back leg stretched out so neat."]

    sentence_start_times = []
    raw_gen = False
    try:
        kokoro = Kokoro("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")
        try:
            v1 = kokoro.get_voice_style("af_nicole")
            v2 = kokoro.get_voice_style("af_heart")
            target_voice = (v1 * 0.55) + (v2 * 0.45)
        except Exception:
            target_voice = "af_nicole"

        audio_segments = []
        sample_rate = 24000
        cumulative_samples = 0
        total_phrases = len(phrases)

        for i, phrase in enumerate(phrases):
            is_final = (i == total_phrases - 1 and total_phrases > 1)
            phrase_speed = 0.80 if is_final else 0.84

            sent_start_sec = round(VO_START_DELAY + (cumulative_samples / float(sample_rate)), 2)
            sentence_start_times.append(sent_start_sec)

            samples, sample_rate = kokoro.create(
                phrase,
                voice=target_voice,
                speed=phrase_speed,
                lang="en-us"
            )
            audio_segments.append(samples)
            cumulative_samples += len(samples)

            if i < total_phrases - 1:
                pause_sec = 1.25 if (i + 1 == total_phrases - 1) else 0.85
                pause_samples = np.zeros(int(sample_rate * pause_sec), dtype=np.float32)
                audio_segments.append(pause_samples)
                cumulative_samples += len(pause_samples)

        full_audio = np.concatenate(audio_segments)
        sf.write("voice_raw.wav", full_audio, sample_rate)
        if os.path.exists("voice_raw.wav") and os.path.getsize("voice_raw.wav") > 1000:
            raw_gen = True
    except Exception as e:
        print(f"Kokoro-82M error ({e}), falling back to Edge-TTS...")

    if not raw_gen:
        try:
            import edge_tts
            import asyncio
            communicate = edge_tts.Communicate(clean_spoken, voice="en-GB-RyanNeural", rate="-10%", pitch="-2Hz")
            asyncio.run(communicate.save("voice_raw.wav"))
            raw_gen = True
        except Exception as e2:
            print(f"Fallback TTS failed: {e2}")

    if raw_gen:
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", "voice_raw.wav",
                "-af", (
                    "aformat=sample_rates=44100:channel_layouts=stereo,"
                    "highpass=f=65,"
                    "equalizer=f=130:width_type=o:w=1.5:g=3.0,"
                    "equalizer=f=6200:width_type=o:w=1.5:g=-4.0,"
                    "lowpass=f=8000,"
                    "adelay=0|12,"
                    "afade=t=in:st=0:d=0.12,"
                    "volume=2.1"
                ),
                "-ar", "44100", "-ac", "2", "voice.mp3"
            ], check=True)
        except Exception:
            subprocess.run([
                "ffmpeg", "-y", "-i", "voice_raw.wav",
                "-af", "volume=2.0", "-ar", "44100", "-ac", "2", "voice.mp3"
            ], check=True)
    else:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=10.0", "voice.mp3"
        ], check=True)

    if not sentence_start_times:
        vo_dur = get_duration("voice.mp3")
        total_chars = max(sum(len(p) for p in phrases), 1)
        elapsed = 0.0
        for p in phrases:
            sentence_start_times.append(round(VO_START_DELAY + elapsed, 2))
            elapsed += (len(p) / total_chars) * vo_dur

    return sentence_start_times


def strip_original_audio(input_path, output_path="raw_video.mp4"):
    """Removes 100% of the original sound (-an) from the background video."""
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-c:v", "copy", "-an", output_path
        ], check=True)
    except Exception:
        subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-pix_fmt", "yuv420p", "-an", output_path
        ], check=True)
    print(f"Stripped original sound (-an) from video: {os.path.basename(input_path)}")


def download_from_google_drive(url, dest_path="drive_raw.mp4"):
    """Downloads a shared Google Drive video file, handling large-file confirmation tokens."""
    match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    file_id = match.group(1) if match else ""
    session = requests.Session()
    resp = session.get(url, stream=True, timeout=60)

    content_type = resp.headers.get("Content-Type", "").lower()
    if "text/html" in content_type and file_id:
        html_text = resp.text
        resp.close()
        confirm_match = re.search(r'confirm=([0-9A-Za-z_-]+)', html_text)
        confirm_token = confirm_match.group(1) if confirm_match else "t"
        confirm_url = f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={file_id}"
        resp = session.get(confirm_url, stream=True, timeout=120)

    if resp.status_code == 200:
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        resp.close()
        return os.path.exists(dest_path) and os.path.getsize(dest_path) > 50_000
    resp.close()
    return False


def is_real_camera_footage(hit):
    hit_type = str(hit.get("type", "")).lower()
    if "animation" in hit_type or "illustration" in hit_type:
        return False
    tags_str = str(hit.get("tags", "")).lower()
    tag_tokens = {t.strip() for t in tags_str.split(",") if t.strip()}
    for banned in BANNED_VISUAL_TAGS:
        if banned in tag_tokens or re.search(rf'\b{re.escape(banned)}\b', tags_str):
            return False
    return True


def download_visual_background(target_duration):
    """Downloads Google Drive video first, strips original audio (-an), and falls back to Pixabay real footage."""
    if drive_video_url and drive_video_url.startswith("http"):
        try:
            print(f"Downloading Google Drive video: {drive_video_url}")
            if download_from_google_drive(drive_video_url, "drive_raw.mp4"):
                strip_original_audio("drive_raw.mp4", "raw_video.mp4")
                return
        except Exception as e_drv:
            print(f"Google Drive download failed ({e_drv}), trying fallback...")

    video_exts = (".mp4", ".mov", ".mkv", ".webm")
    for folder in ["videos", "backgrounds", "clips"]:
        if os.path.isdir(folder):
            found = [
                os.path.join(folder, f) for f in sorted(os.listdir(folder))
                if f.lower().endswith(video_exts) and os.path.getsize(os.path.join(folder, f)) > 50_000
            ]
            if found:
                idx = (max(1, int(row_id)) - 1) % len(found)
                strip_original_audio(found[idx], "raw_video.mp4")
                return

    if PIXABAY_API_KEY:
        try:
            queries = [
                urllib.parse.quote(search_keyword),
                urllib.parse.quote(fallback_keyword),
                "bearded+dragon",
                "lizard+reptile",
                "calm+nature+sunlight"
            ]
            for orientation_param in ["&orientation=vertical", ""]:
                for q in queries:
                    if not q:
                        continue
                    url = (
                        f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}"
                        f"&q={q}&video_type=film{orientation_param}&per_page=25&safesearch=true"
                    )
                    r = requests.get(url, timeout=20)
                    raw_hits = r.json().get("hits", []) if r.status_code == 200 else []
                    real_hits = [h for h in raw_hits if is_real_camera_footage(h)]
                    if real_hits:
                        chosen = random.choice(real_hits[:5])
                        vids = chosen.get("videos", {})
                        v_url = (
                            vids.get("large", {}).get("url")
                            or vids.get("medium", {}).get("url")
                            or vids.get("small", {}).get("url")
                        )
                        if v_url:
                            vid_data = requests.get(v_url, timeout=60).content
                            if len(vid_data) > 50_000:
                                with open("pixabay_raw.mp4", "wb") as f:
                                    f.write(vid_data)
                                strip_original_audio("pixabay_raw.mp4", "raw_video.mp4")
                                return
        except Exception as e:
            print(f"Pixabay search warning: {e}")

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=#141414:s=1080x1920:r=30:d={target_duration:.2f}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-an", "raw_video.mp4"
    ], check=True)


def fetch_relaxing_piano(target_duration):
    """Loads custom piano.mp3 first, then Freesound soft relaxing piano, then gentle synth piano."""
    for filename in ["piano.mp3", "bgm.mp3", "audio/piano.mp3", "audio/default.mp3"]:
        if os.path.exists(filename) and os.path.getsize(filename) > 10_000:
            print(f"Using relaxing piano track: {filename}")
            return filename

    excluded = {"voice.mp3", "voice_raw.mp3", "cloud_piano.mp3", "synth_piano.mp3", "asmr.mp3"}
    custom_candidates = []
    for pattern in ["*.mp3", "music/*.mp3", "audio/*.mp3"]:
        for f in glob.glob(pattern):
            if os.path.basename(f) not in excluded and os.path.getsize(f) > 10_000:
                custom_candidates.append(f)
    if custom_candidates:
        return random.choice(custom_candidates)

    if FREESOUND_API_KEY:
        try:
            query = urllib.parse.quote("soft relaxing piano calm ambient instrumental")
            url = (
                f"https://freesound.org/apiv2/search/text/"
                f"?query={query}&filter=duration:[20 TO 300]&fields=id,name,previews"
                f"&page_size=10&token={FREESOUND_API_KEY}"
            )
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                results = r.json().get("results", [])
                if results:
                    chosen = random.choice(results)
                    mp3_url = chosen.get("previews", {}).get("preview-hq-mp3")
                    if mp3_url:
                        audio_data = requests.get(mp3_url, timeout=20).content
                        if len(audio_data) > 5000:
                            with open("cloud_piano.mp3", "wb") as f:
                                f.write(audio_data)
                            return "cloud_piano.mp3"
        except Exception as e:
            print(f"Freesound piano fallback triggered: {e}")

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=261.63:duration={target_duration:.2f}",
        "-f", "lavfi", "-i", f"sine=frequency=329.63:duration={target_duration:.2f}",
        "-f", "lavfi", "-i", f"sine=frequency=392.00:duration={target_duration:.2f}",
        "-f", "lavfi", "-i", f"sine=frequency=493.88:duration={target_duration:.2f}",
        "-filter_complex", (
            "[0:a]tremolo=f=0.25:d=0.6[a0];"
            "[1:a]tremolo=f=0.33:d=0.6[a1];"
            "[2:a]tremolo=f=0.20:d=0.6[a2];"
            "[3:a]tremolo=f=0.15:d=0.7[a3];"
            "[a0][a1][a2][a3]amix=inputs=4:duration=first,"
            "lowpass=f=650,aecho=0.8:0.88:120|240:0.4|0.3,volume=0.22"
        ),
        "synth_piano.mp3"
    ], check=True)
    return "synth_piano.mp3"


def build_background_video_graph(raw_vid_dur, total_dur):
    """
    - Video shorter than voiceover -> plays forward, then 2nd time in reverse.
    - Video longer than voiceover -> continues playing to end with relaxing piano music.
    - Zero dark overlay, vignette, grain, or color effects applied to background video.
    """
    base_prep = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30"
    if raw_vid_dur < total_dur and raw_vid_dur > 0.2:
        pairs = max(1, math.ceil(total_dur / (2.0 * raw_vid_dur)))
        total_splits = pairs * 2
        split_labels = "".join(f"[s{i}]" for i in range(total_splits))
        chain_parts = []
        concat_inputs = ""
        for p in range(pairs):
            f_in = f"[s{2*p}]"
            r_in = f"[s{2*p+1}]"
            f_out = f"[fwd{p}]"
            r_out = f"[rev{p}]"
            chain_parts.append(f"{f_in}setpts=PTS-STARTPTS{f_out}")
            chain_parts.append(f"{r_in}reverse,setpts=PTS-STARTPTS{r_out}")
            concat_inputs += f"{f_out}{r_out}"
        return f"[0:v]{base_prep},split={total_splits}{split_labels};" + ";".join(chain_parts) + f";{concat_inputs}concat=n={total_splits}:v=1:a=0[vbg]"
    return f"[0:v]{base_prep},setpts=PTS-STARTPTS[vbg]"


def render_ffmpeg(piano_file, vo_duration, total_duration, sentence_start_times):
    raw_vid_duration = get_duration("raw_video.mp4")
    piano_dur = get_duration(piano_file)
    max_offset = max(0.0, piano_dur - total_duration - 2.0)
    piano_start = random.uniform(0.0, max_offset) if max_offset > 4.0 else 0.0

    line_items, total_height = prepare_overlay_lines(overlay_text, sentence_start_times)
    quote_font = get_quote_font_path()

    # Center-bottom positioning on 1080x1920 frame
    bottom_margin = 230
    base_y = max(120, 1920 - bottom_margin - total_height)

    audio_fade_start = max(total_duration - AUDIO_FADE_DURATION, total_duration - 2.0)
    text_fade_start = max(total_duration - 0.65, VO_START_DELAY + 2.0)
    text_fade_end = round(text_fade_start + 0.35, 2)

    drawtext_filters = []
    for item in line_items:
        start_t = item["start_t"]
        fade_in_end = round(start_t + 0.45, 2)
        line_alpha = (
            f"if(lt(t,{start_t:.2f}),0,"
            f"if(lt(t,{fade_in_end:.2f}),(t-{start_t:.2f})/0.45,"
            f"if(lt(t,{text_fade_start:.2f}),1,"
            f"if(lt(t,{text_fade_end:.2f}),({text_fade_end:.2f}-t)/0.35,0))))"
        )
        y_pos = base_y + item["rel_y"]
        drawtext_filters.append(
            f"drawtext=fontfile={quote_font}:"
            f"textfile={item['fname']}:"
            f"fontcolor={item['fontcolor']}:"
            f"fontsize={item['fontsize']}:"
            f"x=(w-text_w)/2:"
            f"y={y_pos}:"
            f"shadowcolor=black@0.90:shadowx=3:shadowy=4:"
            f"enable='gte(t,{start_t:.2f})':"
            f"alpha='{line_alpha}'"
        )

    drawtext_filters_str = ",".join(drawtext_filters)
    bg_graph = build_background_video_graph(raw_vid_duration, total_duration)

    v_filter = f"{bg_graph},{drawtext_filters_str}[v]"

    vo_start = VO_START_DELAY
    vo_end = VO_START_DELAY + vo_duration
    adelay_ms = int(VO_START_DELAY * 1000)

    piano_vol_expr = f"if(between(t,{vo_start:.2f},{vo_end:.2f}),0.20,0.38)"

    a_filter = (
        f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,"
        f"lowpass=f=3200,volume='{piano_vol_expr}':eval=frame[piano];"
        f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo,"
        f"adelay={adelay_ms}|{adelay_ms},apad=whole_dur={total_duration:.2f}[voice];"
        f"[piano][voice]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        f"afade=t=in:st=0:d=0.4,"
        f"afade=t=out:st={audio_fade_start:.2f}:d={AUDIO_FADE_DURATION}[a]"
    )

    filter_complex = f"{v_filter};{a_filter}"
    subprocess.run([
        "ffmpeg", "-y",
        "-i", "raw_video.mp4",
        "-ss", f"{piano_start:.2f}", "-stream_loop", "-1", "-i", piano_file,
        "-i", "voice.mp3",
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-t", f"{total_duration:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "final_output.mp4"
    ], check=True)


def verify_url_accessible(url):
    if not url or not url.startswith("https://"):
        return False
    try:
        r = requests.get(url, stream=True, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        ok = r.status_code in (200, 206)
        r.close()
        return ok
    except Exception as e:
        print(f"URL verification failed for {url}: {e}")
        return False


def upload_to_github_release(filepath):
    gh_token = os.environ.get("GITHUB_TOKEN", "").strip()
    gh_repo = os.environ.get("GITHUB_REPOSITORY", "maaaaaaaahiuddin-code/cloud-video-engine").strip()
    if not gh_token:
        return ""

    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json"
    }
    tag_name = "rendered-videos"
    api_base = f"https://api.github.com/repos/{gh_repo}"

    r = requests.get(f"{api_base}/releases/tags/{tag_name}", headers=headers, timeout=20)
    if r.status_code == 200:
        release_data = r.json()
    else:
        r_create = requests.post(
            f"{api_base}/releases",
            headers=headers,
            json={
                "tag_name": tag_name,
                "name": "Automated Cloud Videos",
                "body": "Hosted MP4 assets for Make.com social publishing.",
                "draft": False,
                "prerelease": False
            },
            timeout=20
        )
        if r_create.status_code not in (200, 201):
            return ""
        release_data = r_create.json()

    release_id = release_data.get("id")
    asset_name = f"beardie_row_{row_id}_{random.randint(1000, 9999)}.mp4"
    upload_url = f"https://uploads.github.com/repos/{gh_repo}/releases/{release_id}/assets?name={asset_name}"
    upload_headers = {
        "Authorization": f"Bearer {gh_token}",
        "Content-Type": "video/mp4",
        "Accept": "application/vnd.github+json"
    }
    with open(filepath, "rb") as f:
        r_up = requests.post(upload_url, headers=upload_headers, data=f, timeout=120)

    if r_up.status_code in (200, 201):
        dl_url = r_up.json().get("browser_download_url", "")
        if verify_url_accessible(dl_url):
            return dl_url
    return ""


def upload_video_with_fallback():
    if os.environ.get("CLOUDINARY_URL", "").startswith("cloudinary://"):
        try:
            res = cloudinary.uploader.upload(
                "final_output.mp4",
                resource_type="video",
                folder="auto_relaxing_videos",
                timeout=120
            )
            video_url = res.get("secure_url", "")
            if verify_url_accessible(video_url):
                return video_url
        except Exception as e:
            print(f"Cloudinary upload skipped ({e}).")

    gh_url = upload_to_github_release("final_output.mp4")
    if gh_url:
        return gh_url

    try:
        with open("final_output.mp4", "rb") as f:
            r = requests.post(
                "https://tmpfiles.org/api/v1/upload",
                files={"file": ("final_output.mp4", f, "video/mp4")},
                timeout=60
            )
        if r.status_code == 200:
            raw_url = r.json().get("data", {}).get("url", "")
            if raw_url:
                direct_url = raw_url.replace("http://", "https://", 1).replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)
                if verify_url_accessible(direct_url):
                    return direct_url
    except Exception as e_tmp:
        print(f"tmpfiles backup failed: {e_tmp}")

    return ""


def main():
    ensure_assets()

    # Step 1: Generate English voiceover first so we know its exact duration
    sentence_start_times = generate_kokoro_asmr_voiceover(overlay_text)
    vo_duration = get_duration("voice.mp3")
    vo_end = round(VO_START_DELAY + vo_duration, 2)

    # Step 2: Fetch background video (original sound removed) to compare video vs voiceover duration
    download_visual_background(max(MIN_VIDEO_DURATION, vo_end + EXTRA_TAIL_SECONDS))
    raw_vid_duration = get_duration("raw_video.mp4")

    if raw_vid_duration > vo_end:
        total_duration = max(MIN_VIDEO_DURATION, round(raw_vid_duration, 2))
        print(f"Video ({raw_vid_duration:.2f}s) > Voiceover end ({vo_end:.2f}s): continuing video to {total_duration:.2f}s with relaxing piano.")
    else:
        total_duration = max(MIN_VIDEO_DURATION, round(vo_end + EXTRA_TAIL_SECONDS, 2))
        print(f"Video ({raw_vid_duration:.2f}s) < Voiceover end ({vo_end:.2f}s): playing 2nd time in reverse up to {total_duration:.2f}s.")

    piano_file = fetch_relaxing_piano(total_duration)

    # Step 3: Render final video (center-bottom shadowed overlay text, no title/watermark/end text, no video effects)
    render_ffmpeg(piano_file, vo_duration, total_duration, sentence_start_times)
    video_url = upload_video_with_fallback()
    print(f"Final Hosted Video URL: {video_url}")

    if not video_url or not video_url.startswith("http"):
        raise RuntimeError("Video upload failed across all hosts; no valid video_url to send to Make.com!")

    webhook_payload = {
        "row_id": row_id,
        "title": f"Bearded Dragon #{row_id}",
        "video_url": video_url,
        "caption": caption
    }

    target_webhooks = [PRIMARY_MAKE_WEBHOOK]
    if MAKE_WEBHOOK_URL.startswith("http") and MAKE_WEBHOOK_URL != PRIMARY_MAKE_WEBHOOK:
        target_webhooks.append(MAKE_WEBHOOK_URL)

    for wh_url in target_webhooks:
        resp = requests.post(
            wh_url,
            json=webhook_payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        print(f"Sent webhook to {wh_url} -> Status: {resp.status_code} | Response: {resp.text}")


if __name__ == "__main__":
    main()
