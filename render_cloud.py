import os
import re
import sys
import time
import glob
import json
import random
import hashlib
import urllib.parse
import textwrap
import subprocess
import requests

# ==============================================================================
# 0. DEPENDENCY BOOTSTRAP & CLOUDINARY SANITIZATION
# ==============================================================================
try:
    import soundfile as sf
    import numpy as np
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter
    from kokoro_onnx import Kokoro
except ImportError:
    subprocess.run([
        sys.executable, "-m", "pip", "install",
        "kokoro-onnx", "soundfile", "numpy", "pillow", "fonttools", "edge-tts", "gTTS"
    ], check=True)
    import soundfile as sf
    import numpy as np
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter
    from kokoro_onnx import Kokoro

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


# ==============================================================================
# 1. CENTRALIZED CONFIGURATION — 8K REALISTIC 35MM PHOTOGRAPHY (MODE 1)
# ==============================================================================
class Config:
    _raw_payload = os.environ.get("PAYLOAD_JSON", "{}")
    try:
        PAYLOAD = json.loads(_raw_payload) if _raw_payload else {}
    except Exception:
        PAYLOAD = {}

    ROW_ID = str(PAYLOAD.get("row_id", "1")).strip()
    TITLE = str(PAYLOAD.get("title", "I'm Lucky Because I Found You")).strip()
    NICHE = str(PAYLOAD.get("niche", "love")).strip()
    OVERLAY_TEXT = str(PAYLOAD.get(
        "overlay_text",
        "I'm lucky because I found you / "
        "because I get to know the real you / "
        "I can't imagine a world / "
        "where you're just someone I used to know / "
        "let's never become strangers / "
        "it would be a shame not to know you / "
        "it would be a shame not to love you"
    )).strip()
    SEARCH_KEYWORD = str(PAYLOAD.get(
        "search_keyword",
        "rooftop moonlight embrace | coastal balcony sunset tea | dark ocean water reflection | "
        "starlight pathway | red autumn petals night | fireflies meadow lantern | ocean window sunset"
    )).strip()
    CAPTION = str(PAYLOAD.get(
        "caption",
        "let's never become strangers #poetry #romance #lovequotes #reels"
    )).strip()

    # Mode 1 Default: Video-Wide Token-Locked Seed (Same character cast from start to end)
    USE_PIXEL_LOCKED_CUTOUT = False

    OUTRO_TAIL_DURATION = 2.00
    FADE_OUT_DURATION = 1.20
    CLAUSE_PAUSE_SEC = 0.72
    VOICE_SPEED = 0.84

    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
    GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "maaaahiuddin-cyber/cloud-video-engine").strip()
    FREESOUND_API_KEY = os.environ.get("FREESOUND_API_KEY", "").strip().strip('"').strip("'")
    PRIMARY_MAKE_WEBHOOK = "https://hook.us2.make.com/ga5opcigaf8fw3keq4zh5x5uy2r6gs24"

    _raw_wh = os.environ.get("MAKE_WEBHOOK_URL", "").strip().strip('"').strip("'")
    if _raw_wh.startswith("MAKE_WEBHOOK_URL="):
        _raw_wh = _raw_wh.split("MAKE_WEBHOOK_URL=", 1)[1].strip().strip('"').strip("'")
    MAKE_WEBHOOK_URL = _raw_wh if _raw_wh.startswith("http") else PRIMARY_MAKE_WEBHOOK

    BOY_ANCHOR = (
        "real candid photograph of the same 23-year-old young man with natural wavy dark hair, "
        "authentic skin texture, calm expressive eyes, wearing a relaxed cream linen shirt over a dark navy tee"
    )
    GIRL_ANCHOR = (
        "real candid photograph of the same 22-year-old young woman with natural wavy chestnut hair, "
        "authentic skin texture, warm expressive eyes, wearing a terracotta dress and soft cream cardigan"
    )
    COUPLE_ANCHOR = (
        "real candid photograph of the same young couple together, 23-year-old man in cream linen shirt "
        "and 22-year-old woman in terracotta dress, natural body language and authentic expressions"
    )

    REALISTIC_CINEMA_STYLE = (
        "8k realistic photography, 35mm motion picture still, shot on 85mm f/1.4 lens, "
        "natural skin pores and fabric weave, soft highlights, rich natural shadows, "
        "authentic reflections and volumetric depth, natural color grading, vertical 9:16, no text, no watermark"
    )

    SCENE_ENVIRONMENTS_POOL = [
        "on a rooftop terrace under a glowing full moon and starry night sky with soft city bokeh",
        "on a coastal balcony overlooking a bay at golden sunset with warm tea under a crescent moon",
        "along a rain-washed cobblestone street reflecting warm glowing amber streetlamps at night",
        "by an open wooden window overlooking ocean waves at golden sunset with natural rim light",
        "in a quiet twilight meadow with warm glass lanterns and soft evening atmosphere",
        "on a stone bridge over a calm moonlit canal with warm glowing reflections",
        "inside a night train carriage with warm cabin lighting and glowing town lights outside",
        "on a wooden seaside pier stretching into a twilight sea under orange and blue clouds",
        "along a tree-lined park path at golden dusk with falling autumn leaves and natural light",
        "in a cozy wooden room lit by warm candlelight beside a rain-streaked window",
        "on a grassy hillside under a starry night sky overlooking a coastal village",
        "inside a warm bookstore corner at night with warm lamp light and rain outside",
        "along a calm beach shoreline at golden sunrise with natural water reflections",
        "on an outdoor cafe terrace at twilight with warm string lights and evening sky"
    ]


# ==============================================================================
# 2. ASSET & FONT MANAGER
# ==============================================================================
def ensure_assets():
    """Downloads Kokoro-82M ONNX models and Crimson Text Italic font."""
    model_path = "kokoro-v1.0.int8.onnx"
    voices_path = "voices-v1.0.bin"
    italic_font_path = "PoetryItalic.ttf"

    if not os.path.exists(model_path) or os.path.getsize(model_path) < 10_000_000:
        print("Downloading Kokoro-82M int8 model...")
        r = requests.get(
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx",
            timeout=120
        )
        r.raise_for_status()
        with open(model_path, "wb") as f:
            f.write(r.content)

    if not os.path.exists(voices_path) or os.path.getsize(voices_path) < 1_000_000:
        print("Downloading Kokoro-82M voices pack...")
        r = requests.get(
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
            timeout=60
        )
        r.raise_for_status()
        with open(voices_path, "wb") as f:
            f.write(r.content)

    if not os.path.exists(italic_font_path) or os.path.getsize(italic_font_path) < 30_000:
        italic_urls = [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/crimsontext/CrimsonText-Italic.ttf",
            "https://raw.githubusercontent.com/google/fonts/main/ofl/ebgaramond/EBGaramond-Italic%5Bwght%5D.ttf",
            "https://raw.githubusercontent.com/google/fonts/main/ofl/crimsontext/CrimsonText-Regular.ttf"
        ]
        for url in italic_urls:
            try:
                r = requests.get(url, timeout=25)
                if r.status_code == 200 and len(r.content) > 30_000:
                    with open(italic_font_path, "wb") as f:
                        f.write(r.content)
                    print(f"Downloaded italic poetic font from {url}")
                    break
            except Exception as e:
                print(f"Italic font download skipped: {e}")


def get_italic_font_path():
    """Returns the best available italic serif font path."""
    candidates = [
        "PoetryItalic.ttf",
        "PoetrySerif.ttf",
        "/usr/share/fonts/truetype/ebgaramond/EBGaramond12-Italic.ttf",
        "/usr/share/fonts/truetype/ebgaramond/EBGaramond12-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    ]
    for p in candidates:
        if os.path.exists(p) and os.path.getsize(p) > 20_000:
            return p
    return "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"


# ==============================================================================
# 3. VOICEOVER & TIMING ENGINE
# ==============================================================================
def split_into_poetic_clauses(text):
    """Splits Overlay_Text into 5-8 short poetic scene lines."""
    cleaned = text.replace("\r\n", "\n").strip()
    if "/" in cleaned:
        raw_parts = [p.strip() for p in cleaned.split("/") if p.strip()]
    elif "\n" in cleaned:
        raw_parts = [p.strip() for p in cleaned.split("\n") if p.strip()]
    else:
        raw_parts = [p.strip() for p in re.split(r'(?<=[.!?…,:;])\s+', cleaned) if p.strip()]

    clauses = []
    for part in raw_parts:
        words = part.split()
        if len(words) > 11:
            mid = len(words) // 2
            clauses.append(" ".join(words[:mid]))
            clauses.append(" ".join(words[mid:]))
        else:
            clauses.append(part)

    return clauses if clauses else ["I'm lucky because I found you"]


def generate_deep_male_poetic_voiceover(clauses):
    """
    Synthesizes the deep male spoken-word voice (65% am_michael + 20% bm_fable + 15% af_nicole)
    and returns exact (start_sec, end_sec, clause_text) tuples for every scene.
    """
    scene_timings = []
    sample_rate = 24000

    try:
        kokoro = Kokoro("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")
        try:
            v_michael = kokoro.get_voice_style("am_michael")
            v_fable = kokoro.get_voice_style("bm_fable")
            v_nicole = kokoro.get_voice_style("af_nicole")
            male_poetic_vec = (v_michael * 0.65) + (v_fable * 0.20) + (v_nicole * 0.15)
            print("Using 65% am_michael + 20% bm_fable + 15% af_nicole deep male spoken-word vector.")
        except Exception:
            male_poetic_vec = "am_michael"

        audio_segments = []
        current_sec = 0.0

        for idx, clause in enumerate(clauses):
            spoken_clause = clause.strip()
            if spoken_clause and spoken_clause[-1] not in ".!?,":
                spoken_clause += "," if idx < len(clauses) - 1 else "."

            samples, sample_rate = kokoro.create(
                spoken_clause,
                voice=male_poetic_vec,
                speed=Config.VOICE_SPEED,
                lang="en-us"
            )
            seg_dur = max(len(samples) / float(sample_rate), 0.5)
            pad_dur = Config.CLAUSE_PAUSE_SEC if idx < len(clauses) - 1 else 0.45

            scene_start = round(current_sec, 3)
            scene_end = round(max(current_sec + seg_dur + pad_dur, scene_start + 0.5), 3)
            scene_timings.append((scene_start, scene_end, clause))
            print(f"Scene {idx+1}: {scene_start:.2f}s -> {scene_end:.2f}s | '{clause}'")

            audio_segments.append(samples)
            audio_segments.append(np.zeros(int(sample_rate * pad_dur), dtype=np.float32))
            current_sec = scene_end

        audio_segments.append(np.zeros(int(sample_rate * (Config.OUTRO_TAIL_DURATION + 0.5)), dtype=np.float32))
        full_audio = np.concatenate(audio_segments)
        sf.write("voice_raw.wav", full_audio, sample_rate)

        subprocess.run([
            "ffmpeg", "-y", "-i", "voice_raw.wav",
            "-af", (
                "aformat=sample_rates=44100:channel_layouts=stereo,"
                "highpass=f=55,"
                "equalizer=f=115:width_type=o:w=1.4:g=3.8,"
                "equalizer=f=240:width_type=o:w=1.5:g=1.5,"
                "equalizer=f=5800:width_type=o:w=1.5:g=-4.5,"
                "lowpass=f=7800,"
                "aecho=0.88:0.90:85|170:0.14|0.08,"
                "adelay=0|10,"
                "volume=2.2"
            ),
            "-ar", "44100", "-ac", "2", "voice.mp3"
        ], check=True)
        return scene_timings

    except Exception as e:
        print(f"Kokoro male voice error ({e}), using fallback...")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=18.0", "voice.mp3"
        ], check=True)
        dur_per_clause = 2.8
        for idx, clause in enumerate(clauses):
            scene_timings.append((round(idx * dur_per_clause, 2), round((idx + 1) * dur_per_clause, 2), clause))
        return scene_timings


# ==============================================================================
# 4. 8K REALISTIC PHOTOGRAPHY SCENE & LANCZOS MOTION ENGINE
# ==============================================================================
def select_video_wide_character(overlay_text, niche, row_id_str):
    """Locks ONE realistic character cast (Boy, Girl, or Couple) for the entire video."""
    n_low = niche.lower().strip()
    text_low = overlay_text.lower()
    digits = re.sub(r'\D', '', row_id_str)
    row_num = int(digits) if digits else 1

    if n_low in ("love", "soulmates") or any(
        w in text_low for w in ["found you", "love you", "strangers", "together", "we ", "us ", "beside you", "your hand"]
    ):
        return "2 Characters (Same Couple Start-to-End)", Config.COUPLE_ANCHOR
    elif n_low == "healing" or any(w in text_low for w in ["she ", "her ", "bloom", "softness"]):
        return "1 Character (Same Girl Start-to-End)", Config.GIRL_ANCHOR
    elif n_low in ("solitude", "nostalgia", "longing"):
        if row_num % 3 == 0:
            return "1 Character (Same Girl Start-to-End)", Config.GIRL_ANCHOR
        return "1 Character (Same Boy Start-to-End)", Config.BOY_ANCHOR
    return "2 Characters (Same Couple Start-to-End)", Config.COUPLE_ANCHOR


def is_valid_non_black_image(img_path):
    """Confirms the image file is readable, high-detail, and NOT a black/blank frame."""
    try:
        if not os.path.exists(img_path) or os.path.getsize(img_path) < 12_000:
            return False
        with Image.open(img_path) as im:
            im.verify()
        with Image.open(img_path) as im:
            rgb = im.convert("RGB")
            arr = np.asarray(rgb, dtype=np.float32)
            mean_val = float(arr.mean())
            std_val = float(arr.std())
            return mean_val > 12.0 and std_val > 8.0
    except Exception:
        return False


def enhance_image_ultra_hd(img_path):
    """
    Pre-masters every scene image to 1240x2200 using Lanczos resampling,
    UnsharpMask micro-detail sharpening, and natural optical contrast/color balance.
    """
    with Image.open(img_path) as im:
        rgb = im.convert("RGB")
        rgb = ImageOps.fit(rgb, (1240, 2200), method=Image.Resampling.LANCZOS)
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.5, percent=125, threshold=2))
        rgb = ImageEnhance.Color(rgb).enhance(1.10)
        rgb = ImageEnhance.Contrast(rgb).enhance(1.06)
        rgb.save(img_path, format="JPEG", quality=98, subsampling=0)


def fetch_realistic_hd_fallbacks(out_path, scene_kw, scene_idx, used_urls):
    """High-resolution photography fallbacks via Wallhaven when Pollinations is busy."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    wh_queries = [
        f"https://wallhaven.cc/api/v1/search?q={urllib.parse.quote(scene_kw)}&categories=100&purity=100&ratios=9x16,10x16&sorting=favorites",
        "https://wallhaven.cc/api/v1/search?q=night+city+lights&categories=100&purity=100&ratios=9x16,10x16&sorting=favorites",
        "https://wallhaven.cc/api/v1/search?q=sunset+ocean+sky&categories=100&purity=100&ratios=9x16,10x16&sorting=favorites",
        "https://wallhaven.cc/api/v1/search?q=cinematic+night&categories=110&purity=100&ratios=9x16,10x16&sorting=favorites"
    ]
    for wh_url in wh_queries:
        try:
            r = requests.get(wh_url, timeout=20, headers=headers)
            hits = r.json().get("data", []) if r.status_code == 200 else []
            if hits:
                random.shuffle(hits)
                for hit in hits[:8]:
                    img_url = hit.get("path", "")
                    if img_url and img_url not in used_urls:
                        img_data = requests.get(img_url, timeout=30, headers=headers).content
                        with open(out_path, "wb") as f:
                            f.write(img_data)
                        if is_valid_non_black_image(out_path):
                            enhance_image_ultra_hd(out_path)
                            used_urls.add(img_url)
                            print(f"Scene {scene_idx+1}: Downloaded 4K realistic background from Wallhaven.")
                            return True
        except Exception as e:
            print(f"Wallhaven 4K fallback skipped: {e}")
    return False


def create_distinct_variation_from_existing(source_img_path, target_img_path, scene_idx):
    """Creates a differently framed variation if external image networks time out."""
    with Image.open(source_img_path) as im:
        rgb = im.convert("RGB")
        if scene_idx % 2 == 1:
            rgb = ImageOps.mirror(rgb)
        w, h = rgb.size
        crop_margin_x = int(w * 0.05)
        crop_margin_y = int(h * 0.05)
        rgb = rgb.crop((crop_margin_x, crop_margin_y, w - crop_margin_x, h - crop_margin_y))
        rgb = ImageOps.fit(rgb, (1240, 2200), method=Image.Resampling.LANCZOS)
        rgb = ImageEnhance.Color(rgb).enhance(1.06)
        rgb.save(target_img_path, format="JPEG", quality=98, subsampling=0)


def build_scene_motion_filter(dur, scene_idx):
    """
    Uses integer frame counter 'n' on our pre-mastered 1240x2200 Lanczos canvas
    with subtle optical unsharpness and natural contrast/color balance.
    """
    total_frames = max(int(dur * 30), 30)
    mode = scene_idx % 4

    if mode == 0:
        x_expr = f"20+120*(n/{total_frames})"
        y_expr = f"220-160*(n/{total_frames})"
    elif mode == 1:
        x_expr = f"60+60*(n/{total_frames})"
        y_expr = f"240-180*(n/{total_frames})"
    elif mode == 2:
        x_expr = f"140-120*(n/{total_frames})"
        y_expr = f"40+160*(n/{total_frames})"
    else:
        x_expr = "80+55*sin(n*0.06)"
        y_expr = "140+75*cos(n*0.05)"

    return (
        f"scale=1240:2200:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop=1080:1920:x='{x_expr}':y='{y_expr}',"
        f"setsar=1,fps=30,"
        f"unsharp=5:5:0.75:3:3:0.35,"
        f"eq=brightness=0.01:contrast=1.06:saturation=1.08"
    )


def generate_realistic_8k_scenes(scene_timings):
    """Generates and animates 7 realistic 8K 35mm photography scenes with Mode 1 character lock."""
    num_scenes = len(scene_timings)
    scene_video_files = []
    verified_scene_images = []
    used_fallback_urls = set()
    used_image_hashes = set()

    char_label, locked_char_anchor = select_video_wide_character(
        Config.OVERLAY_TEXT, Config.NICHE, Config.ROW_ID
    )
    digits = re.sub(r'\D', '', Config.ROW_ID)
    row_num = int(digits) if digits else 1
    video_character_seed = 50000 + (row_num * 997)
    print(f"Mode 1 8K Realistic Character Lock: {char_label} (Base Seed={video_character_seed})")

    custom_scene_keywords = [k.strip() for k in Config.SEARCH_KEYWORD.split("|") if k.strip()]
    shuffled_envs = list(Config.SCENE_ENVIRONMENTS_POOL)
    random.Random(video_character_seed).shuffle(shuffled_envs)

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for idx, (s_start, s_end, clause_text) in enumerate(scene_timings):
        dur = max((s_end - s_start) + (Config.OUTRO_TAIL_DURATION if idx == num_scenes - 1 else 0.0), 0.5)
        distinct_env = shuffled_envs[idx % len(shuffled_envs)]

        if idx < len(custom_scene_keywords):
            raw_scene_kw = custom_scene_keywords[idx]
            bg_only = raw_scene_kw.split("in scene:")[-1].strip() if "in scene:" in raw_scene_kw else raw_scene_kw
        else:
            bg_only = distinct_env

        prompt_text = (
            f"{locked_char_anchor}, scene {idx+1} setting: {bg_only}, {distinct_env}, {Config.REALISTIC_CINEMA_STYLE}"
        )
        full_prompt = urllib.parse.quote(prompt_text)

        img_path = f"scene_img_{idx}.jpg"
        vid_path = f"scene_clip_{idx}.mp4"
        downloaded = False

        if idx > 0:
            time.sleep(2.0)

        for attempt in range(3):
            try:
                scene_seed = video_character_seed + (idx * 17) + (attempt * 101)
                url = (
                    f"https://image.pollinations.ai/prompt/{full_prompt}"
                    f"?width=1080&height=1920&seed={scene_seed}&model=flux&nologo=true&enhance=true"
                )
                r = requests.get(url, timeout=50, headers=headers)
                if r.status_code == 200 and len(r.content) > 15_000:
                    img_hash = hashlib.sha256(r.content).hexdigest()
                    if img_hash not in used_image_hashes:
                        with open(img_path, "wb") as f:
                            f.write(r.content)
                        if is_valid_non_black_image(img_path):
                            enhance_image_ultra_hd(img_path)
                            used_image_hashes.add(img_hash)
                            downloaded = True
                            print(f"Scene {idx+1}/{num_scenes} ({dur:.2f}s) -> [8K Realistic] '{bg_only}'")
                            break
                time.sleep(1.5)
            except Exception as e:
                print(f"Scene {idx+1} Flux 8K attempt {attempt+1} skipped: {e}")
                time.sleep(1.5)

        if not downloaded:
            downloaded = fetch_realistic_hd_fallbacks(img_path, bg_only, idx, used_fallback_urls)

        if not downloaded and verified_scene_images:
            create_distinct_variation_from_existing(verified_scene_images[-1], img_path, idx)
            downloaded = is_valid_non_black_image(img_path)

        if downloaded:
            verified_scene_images.append(img_path)
            vf_chain = build_scene_motion_filter(dur, idx)
            subprocess.run([
                "ffmpeg", "-y",
                "-framerate", "30", "-loop", "1", "-i", img_path,
                "-vf", vf_chain,
                "-t", f"{dur:.3f}",
                "-r", "30",
                "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p",
                "-video_track_timescale", "15360",
                vid_path
            ], check=True)
        else:
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", f"color=c=#1e293b:s=1080x1920:r=30:d={dur:.3f}",
                "-r", "30",
                "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p",
                "-video_track_timescale", "15360",
                vid_path
            ], check=True)

        scene_video_files.append(vid_path)

    with open("concat_scenes.txt", "w", encoding="utf-8") as f:
        for vf in scene_video_files:
            f.write(f"file '{vf}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat_scenes.txt",
        "-r", "30", "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p",
        "raw_video.mp4"
    ], check=True)


# ==============================================================================
# 5. AUDIO & MASTER VIDEO COMPOSITOR
# ==============================================================================
def fetch_ambient_pad_music(target_duration):
    """Detects uploaded piano.mp3 / bgm.mp3 or synthesizes a warm ambient chord pad."""
    for filename in ["piano.mp3", "bgm.mp3", "audio/piano.mp3", "audio/default.mp3"]:
        if os.path.exists(filename) and os.path.getsize(filename) > 10_000:
            return filename

    excluded = {"asmr.mp3", "voice.mp3", "voice_raw.mp3", "cloud_piano.mp3", "synth_piano.mp3"}
    for pattern in ["*.mp3", "music/*.mp3", "audio/*.mp3"]:
        for f in glob.glob(pattern):
            if os.path.basename(f) not in excluded and os.path.getsize(f) > 10_000:
                return f

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=220.00:duration={target_duration:.2f}",
        "-f", "lavfi", "-i", f"sine=frequency=277.18:duration={target_duration:.2f}",
        "-f", "lavfi", "-i", f"sine=frequency=329.63:duration={target_duration:.2f}",
        "-f", "lavfi", "-i", f"sine=frequency=440.00:duration={target_duration:.2f}",
        "-filter_complex", (
            "[0:a]tremolo=f=0.18:d=0.4[a0];"
            "[1:a]tremolo=f=0.22:d=0.4[a1];"
            "[2:a]tremolo=f=0.15:d=0.4[a2];"
            "[3:a]tremolo=f=0.12:d=0.5[a3];"
            "[a0][a1][a2][a3]amix=inputs=4:duration=first,"
            "lowpass=f=520,aecho=0.85:0.90:160|320:0.45|0.35,extrastereo=m=1.8,volume=0.22"
        ),
        "synth_piano.mp3"
    ], check=True)
    return "synth_piano.mp3"


def render_poetic_video(piano_file, scene_timings):
    """Composites 8K realistic scenes, crisp italic subtitles, and mastered audio."""
    italic_font = get_italic_font_path()
    vo_end = scene_timings[-1][1]
    total_duration = round(vo_end + Config.OUTRO_TAIL_DURATION, 2)
    fade_start = max(total_duration - Config.FADE_OUT_DURATION, 1.0)

    drawtext_filters = []
    file_idx = 0

    for s_idx, (s_start, s_end, clause_text) in enumerate(scene_timings):
        safe_start = round(s_start, 2)
        safe_end = round(max(s_end, safe_start + 0.5), 2)
        wrapped_lines = textwrap.wrap(clause_text.strip(), width=32) or [clause_text.strip()]
        line_spacing = 56
        block_h = len(wrapped_lines) * line_spacing

        for l_idx, w_line in enumerate(wrapped_lines):
            fname = f"scene_text_{file_idx}.txt"
            with open(fname, "w", encoding="utf-8", newline="\n") as f:
                f.write(w_line)

            rel_offset = int((l_idx * line_spacing) - (block_h / 2))
            y_expr = f"(h/2)+({rel_offset})"

            drawtext_filters.append(
                f"drawtext=fontfile={italic_font}:"
                f"textfile={fname}:"
                f"fontcolor=#ffffff:"
                f"fontsize=46:"
                f"borderw=2:bordercolor=black@0.55:"
                f"x=(w-text_w)/2:"
                f"y={y_expr}:"
                f"shadowcolor=black@0.90:shadowx=2:shadowy=3:"
                f"enable='between(t,{safe_start:.2f},{safe_end:.2f})'"
            )
            file_idx += 1

    drawtext_str = ",".join(drawtext_filters)

    v_filter = (
        f"[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop=1080:1920,setsar=1,"
        f"{drawtext_str},"
        f"fade=t=out:st={fade_start:.2f}:d={Config.FADE_OUT_DURATION}[v]"
    )

    swell_end = round(vo_end + 1.0, 2)
    pad_vol_expr = (
        f"if(lt(t,{vo_end:.2f}),0.24,"
        f"if(lt(t,{swell_end:.2f}),0.24+0.16*(t-{vo_end:.2f}),0.40))"
    )

    a_filter = (
        f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,"
        f"lowpass=f=1800,aecho=0.85:0.88:120|240:0.30|0.20,"
        f"volume='{pad_vol_expr}':eval=frame[pad];"
        f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo,"
        f"apad=whole_dur={total_duration:.2f}[voice];"
        f"[pad][voice]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        f"afade=t=in:st=0:d=0.4,"
        f"afade=t=out:st={fade_start:.2f}:d={Config.FADE_OUT_DURATION}[a]"
    )

    subprocess.run([
        "ffmpeg", "-y",
        "-i", "raw_video.mp4",
        "-stream_loop", "-1", "-i", piano_file,
        "-i", "voice.mp3",
        "-filter_complex", f"{v_filter};{a_filter}",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{total_duration:.2f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "final_output.mp4"
    ], check=True)


# ==============================================================================
# 6. CLOUD UPLOADER & MAKE.COM WEBHOOK DISPATCHER
# ==============================================================================
def verify_url_accessible(url):
    if not url or not url.startswith("https://"):
        return False
    try:
        r = requests.get(url, stream=True, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        ok = r.status_code in (200, 206)
        r.close()
        return ok
    except Exception:
        return False


def upload_to_github_release(filepath):
    if not Config.GITHUB_TOKEN:
        return ""

    headers = {
        "Authorization": f"Bearer {Config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    tag_name = "rendered-videos"
    api_base = f"https://api.github.com/repos/{Config.GITHUB_REPO}"

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
    asset_name = f"video_row_{Config.ROW_ID}_{random.randint(1000, 9999)}.mp4"
    upload_url = f"https://uploads.github.com/repos/{Config.GITHUB_REPO}/releases/{release_id}/assets?name={asset_name}"
    upload_headers = {
        "Authorization": f"Bearer {Config.GITHUB_TOKEN}",
        "Content-Type": "video/mp4",
        "Accept": "application/vnd.github+json"
    }
    with open(filepath, "rb") as f:
        r_up = requests.post(upload_url, headers=upload_headers, data=f, timeout=120)

    if r_up.status_code in (200, 201):
        dl_url = r_up.json().get("browser_download_url", "")
        if verify_url_accessible(dl_url):
            print(f"Uploaded to GitHub Releases CDN successfully: {dl_url}")
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
            print(f"Cloudinary skipped ({e}). Trying GitHub Release CDN...")

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
    except Exception:
        pass

    return ""


def send_make_webhook(video_url):
    if not video_url or not video_url.startswith("http"):
        raise RuntimeError("Video upload failed across all hosts; no valid video_url to send to Make.com!")

    webhook_payload = {
        "row_id": Config.ROW_ID,
        "title": Config.TITLE,
        "video_url": video_url,
        "caption": Config.CAPTION
    }

    target_webhooks = [Config.PRIMARY_MAKE_WEBHOOK]
    if Config.MAKE_WEBHOOK_URL.startswith("http") and Config.MAKE_WEBHOOK_URL != Config.PRIMARY_MAKE_WEBHOOK:
        target_webhooks.append(Config.MAKE_WEBHOOK_URL)

    for wh_url in target_webhooks:
        resp = requests.post(
            wh_url,
            json=webhook_payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        print(f"Sent webhook to {wh_url} -> Status: {resp.status_code} | Response: {resp.text}")


# ==============================================================================
# 7. MAIN PIPELINE ENTRYPOINT
# ==============================================================================
def main():
    ensure_assets()

    clauses = split_into_poetic_clauses(Config.OVERLAY_TEXT)
    scene_timings = generate_deep_male_poetic_voiceover(clauses)
    total_duration = round(scene_timings[-1][1] + Config.OUTRO_TAIL_DURATION, 2)
    print(f"Generated {len(scene_timings)} poetic scenes -> Total Video Duration: {total_duration:.2f}s")

    generate_realistic_8k_scenes(scene_timings)
    piano_file = fetch_ambient_pad_music(total_duration)

    render_poetic_video(piano_file, scene_timings)
    video_url = upload_video_with_fallback()
    print(f"Final Hosted Video URL: {video_url}")

    send_make_webhook(video_url)


if __name__ == "__main__":
    main()
