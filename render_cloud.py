# 2. Load payload from Google Sheets (10-property client_payload + branding_json)
raw_payload = os.environ.get("PAYLOAD_JSON", "{}")
try:
    payload = json.loads(raw_payload) if raw_payload else {}
except Exception:
    payload = {}

branding_raw = payload.get("branding_json", "{}")
try:
    branding = json.loads(branding_raw) if isinstance(branding_raw, str) and branding_raw else (branding_raw if isinstance(branding_raw, dict) else {})
except Exception:
    branding = {}

row_id = str(payload.get("row_id", "2")).strip()
title = str(payload.get("title", "The Quiet Bench")).strip()
niche = str(payload.get("niche", "love")).strip()
visual_mode = str(payload.get("visual_mode", "illustration")).strip().lower()
overlay_text = str(payload.get(
    "overlay_text",
    "We sat beneath the old oak tree\nTwo quiet souls in autumn rain\nNo heavy words were left to say\nJust shared umbrellas in the dark\nYour shoulder brushed against my coat\nAnd suddenly the cold was gone\nHome is a person, not a place"
)).strip()
line_visual_prompts_raw = str(payload.get("line_visual_prompts", "")).strip()
style_prefix = str(payload.get(
    "style_prefix",
    "vintage gouache painting, risograph grain, 1970s travel poster palette, deep teal and burnt orange, warm lantern halation glow, wide empty center space for text, painterly brushwork, no text, no watermark"
)).strip()
search_keyword = str(payload.get("search_keyword", "gentle rain window piano ambient")).strip()
fallback_keyword = str(branding.get("fallback_keyword", payload.get("fallback_keyword", "rain"))).strip()
watermark_handle = str(branding.get("watermark_handle", payload.get("watermark_handle", "@wordsoftheworld"))).strip()
end_card_credit = str(branding.get("end_card_credit", payload.get("end_card_credit", "Written & Voiced by Words of the World"))).strip()
caption = str(payload.get(
    "caption",
    "Home is a person, not a place.\n\n#poetryreels #quietlove #wordsoftheworld #reels"
)).strip()

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

try:
    import soundfile as sf
    import numpy as np
    from PIL import Image, ImageFilter
    from kokoro_onnx import Kokoro
except ImportError:
    subprocess.run([
        sys.executable, "-m", "pip", "install",
        "kokoro-onnx", "soundfile", "numpy", "pillow", "fonttools", "edge-tts", "gTTS"
    ], check=True)
    import soundfile as sf
    import numpy as np
    from PIL import Image, ImageFilter
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

# 2. Load payload from Google Sheets
raw_payload = os.environ.get("PAYLOAD_JSON", "{}")
try:
    payload = json.loads(raw_payload) if raw_payload else {}
except Exception:
    payload = {}

row_id = str(payload.get("row_id", "2")).strip()
title = str(payload.get("title", "The Quiet Bench")).strip()
niche = str(payload.get("niche", "love")).strip()
visual_mode = str(payload.get("visual_mode", "illustration")).strip().lower()
overlay_text = str(payload.get(
    "overlay_text",
    "We sat beneath the old oak tree\nTwo quiet souls in autumn rain\nNo heavy words were left to say\nJust shared umbrellas in the dark\nYour shoulder brushed against my coat\nAnd suddenly the cold was gone\nHome is a person, not a place"
)).strip()
line_visual_prompts_raw = str(payload.get("line_visual_prompts", "")).strip()
style_prefix = str(payload.get(
    "style_prefix",
    "vintage gouache painting, risograph grain, 1970s travel poster palette, deep teal and burnt orange, warm lantern halation glow, wide empty center space for text, painterly brushwork, no text, no watermark"
)).strip()
search_keyword = str(payload.get("search_keyword", "gentle rain window piano ambient")).strip()
fallback_keyword = str(payload.get("fallback_keyword", "rain")).strip()
watermark_handle = str(payload.get("watermark_handle", "@wordsoftheworld")).strip()
end_card_credit = str(payload.get("end_card_credit", "Written & Voiced by Words of the World")).strip()
caption = str(payload.get(
    "caption",
    "Home is a person, not a place.\n\n#poetryreels #quietlove #wordsoftheworld #reels"
)).strip()

CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "").strip().strip('"').strip("'")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "").strip().strip('"').strip("'")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "").strip().strip('"').strip("'")
FREESOUND_API_KEY = os.environ.get("FREESOUND_API_KEY", "").strip().strip('"').strip("'")

PRIMARY_MAKE_WEBHOOK = "https://hook.us2.make.com/ga5opcigaf8fw3keq4zh5x5uy2r6gs24"
raw_webhook = os.environ.get("MAKE_WEBHOOK_URL", "").strip().strip('"').strip("'")
if raw_webhook.startswith("MAKE_WEBHOOK_URL="):
    raw_webhook = raw_webhook.split("MAKE_WEBHOOK_URL=", 1)[1].strip().strip('"').strip("'")
MAKE_WEBHOOK_URL = raw_webhook if raw_webhook.startswith("http") else PRIMARY_MAKE_WEBHOOK

VO_START_DELAY = 0.6
END_CARD_SECONDS = 2.5
EXTRA_TAIL_SECONDS = 2.0
AUDIO_FADE_DURATION = 1.50
VIDEO_FADE_DURATION = 0.35
OUTPUT_W = 1080
OUTPUT_H = 1920
FPS = 30

BANNED_VISUAL_TAGS = {
    "animation", "animated", "cartoon", "anime", "3d", "cgi", "render",
    "illustration", "drawing", "sketch", "painting", "art", "abstract",
    "fractal", "vj", "neon", "cyberpunk", "sci-fi", "fantasy", "ai",
    "generated", "digital", "graphic", "motion graphics", "particles",
    "matrix", "tunnel", "kaleidoscope", "geometry", "game", "virtual"
}

NICHE_AUDIO_MAP = {
    "rain": "gentle rain falling window ambient asmr",
    "ocean": "calm ocean waves beach water ambient",
    "water": "gentle stream river flowing water nature",
    "forest": "forest wind birds leaves nature ambient",
    "fire": "cozy fireplace crackling wood fire asmr",
    "night": "night crickets calm wind ambient",
    "snow": "soft winter wind snow ambient",
    "soul searching": "gentle night wind rain window ambient asmr",
    "relationship": "cozy fireplace warm rain ambient asmr",
    "healing": "gentle stream forest birds nature ambient",
    "gratitude": "morning forest birds gentle breeze ambient",
    "longing": "gentle rain falling window dark night ambient",
    "motivation": "calm ocean waves wind nature ambient",
    "love": "soft fireplace crackling gentle rain ambient",
    "self-love": "gentle rain leaves forest breeze ambient",
    "hope": "morning birds gentle water stream ambient",
    "nostalgia": "vinyl crackle gentle rain window ambient",
    "solitude": "quiet night wind crickets calm ambient"
}


def ensure_assets():
    model_path = "kokoro-v1.0.int8.onnx"
    voices_path = "voices-v1.0.bin"

    if not os.path.exists(model_path) or os.path.getsize(model_path) < 10_000_000:
        r = requests.get(
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx",
            timeout=120
        )
        with open(model_path, "wb") as f:
            f.write(r.content)

    if not os.path.exists(voices_path) or os.path.getsize(voices_path) < 1_000_000:
        r = requests.get(
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
            timeout=60
        )
        with open(voices_path, "wb") as f:
            f.write(r.content)

    for fname, url in [
        ("PoetrySerif.ttf", "https://raw.githubusercontent.com/google/fonts/main/ofl/crimsontext/CrimsonText-Regular.ttf"),
        ("HandwrittenFont.ttf", "https://raw.githubusercontent.com/google/fonts/main/ofl/caveat/Caveat%5Bwght%5D.ttf")
    ]:
        if not os.path.exists(fname) or os.path.getsize(fname) < 20_000:
            try:
                r = requests.get(url, timeout=25)
                if r.status_code == 200 and len(r.content) > 20_000:
                    with open(fname, "wb") as f:
                        f.write(r.content)
            except Exception as e:
                print(f"Font download skipped ({fname}): {e}")


def get_body_font():
    for p in [
        "HandwrittenFont.ttf",
        "PoetrySerif.ttf",
        "/usr/share/fonts/truetype/ebgaramond/EBGaramond12-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    ]:
        if os.path.exists(p) and os.path.getsize(p) > 15_000:
            return p
    return "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"


def get_title_font():
    for p in [
        "PoetrySerif.ttf",
        "/usr/share/fonts/truetype/ebgaramond/EBGaramond12-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    ]:
        if os.path.exists(p) and os.path.getsize(p) > 15_000:
            return p
    return "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"


def get_script_lines():
    raw_lines = [l.strip() for l in overlay_text.replace("\r\n", "\n").split("\n") if l.strip()]
    if len(raw_lines) == 1 and ". " in overlay_text:
        raw_lines = [s.strip() for s in re.split(r'(?<=[.!?])\s+', overlay_text) if s.strip()]
    return raw_lines or ["Peace comes from within."]


def get_line_visual_prompts(num_lines):
    parsed = []
    if line_visual_prompts_raw:
        for line in line_visual_prompts_raw.replace("\r\n", "\n").split("\n"):
            cleaned = re.sub(r'^\s*\d+[\).\-\:]\s*', '', line).strip()
            if cleaned:
                parsed.append(cleaned)

    while len(parsed) < num_lines:
        base_idx = len(parsed) % max(len(parsed), 1) if parsed else 0
        fallback_p = parsed[base_idx] if parsed else f"{search_keyword}, warm atmospheric scene"
        parsed.append(fallback_p)

    return parsed[:num_lines]


def get_duration(filename):
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", filename
        ], text=True).strip()
        return float(out)
    except Exception:
        return 10.0


def generate_kokoro_asmr_voiceover(lines):
    """Generates blended 55% af_nicole + 45% af_heart voiceover and returns per-line start timestamps."""
    line_start_times = []
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
        total_lines = len(lines)

        for i, line in enumerate(lines):
            is_final = (i == total_lines - 1 and total_lines > 1)
            speed = 0.79 if is_final else 0.83
            start_sec = round(VO_START_DELAY + (cumulative_samples / float(sample_rate)), 2)
            line_start_times.append(start_sec)

            # Add trailing period if missing for natural cadence
            spoken_line = line if line[-1] in ".!?," else line + "."
            samples, sample_rate = kokoro.create(spoken_line, voice=target_voice, speed=speed, lang="en-us")
            audio_segments.append(samples)
            cumulative_samples += len(samples)

            if i < total_lines - 1:
                pause_sec = 1.45 if (i + 1 == total_lines - 1) else 0.85
                pause_samples = np.zeros(int(sample_rate * pause_sec), dtype=np.float32)
                audio_segments.append(pause_samples)
                cumulative_samples += len(pause_samples)

        audio_segments.append(np.zeros(int(sample_rate * 0.80), dtype=np.float32))
        sf.write("voice_raw.wav", np.concatenate(audio_segments), sample_rate)
        raw_gen = os.path.exists("voice_raw.wav") and os.path.getsize("voice_raw.wav") > 1000
    except Exception as e:
        print(f"Kokoro-82M error ({e}), falling back to Edge-TTS...")

    if not raw_gen:
        try:
            import edge_tts
            import asyncio
            joined = " ".join(lines)
            communicate = edge_tts.Communicate(joined, voice="en-GB-RyanNeural", rate="-12%", pitch="-2Hz")
            asyncio.run(communicate.save("voice_raw.wav"))
            raw_gen = True
        except Exception as e2:
            print(f"Edge-TTS fallback failed: {e2}")

    if raw_gen:
        subprocess.run([
            "ffmpeg", "-y", "-i", "voice_raw.wav",
            "-af", (
                "aformat=sample_rates=44100:channel_layouts=stereo,"
                "highpass=f=65,equalizer=f=130:width_type=o:w=1.5:g=3.0,"
                "equalizer=f=6200:width_type=o:w=1.5:g=-4.0,lowpass=f=8000,"
                "aecho=0.88:0.90:95|190:0.12|0.07,adelay=0|12,afade=t=in:st=0:d=0.15,volume=2.1"
            ),
            "-ar", "44100", "-ac", "2", "voice.mp3"
        ], check=True)
    else:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=12.0", "voice.mp3"
        ], check=True)

    if not line_start_times:
        vo_dur = get_duration("voice.mp3")
        step = vo_dur / max(len(lines), 1)
        line_start_times = [round(VO_START_DELAY + i * step, 2) for i in range(len(lines))]

    return line_start_times


def generate_scene_image_cloudflare(full_prompt, seed, out_path):
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        return False
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json"
    }
    body = {
        "prompt": full_prompt,
        "width": 768,
        "height": 1344,
        "num_steps": 4,
        "seed": seed
    }
    resp = requests.post(url, headers=headers, json=body, timeout=60)
    if resp.status_code == 200:
        content_type = resp.headers.get("Content-Type", "")
        if "image" in content_type:
            with open(out_path, "wb") as f:
                f.write(resp.content)
            return True
        data = resp.json()
        b64_img = data.get("result", {}).get("image")
        if b64_img:
            import base64
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(b64_img))
            return True
    print(f"Cloudflare Workers AI warning ({resp.status_code}): {resp.text[:200]}")
    return False


def generate_scene_image_pollinations(full_prompt, seed, out_path):
    encoded = urllib.parse.quote(full_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=1344&seed={seed}&nologo=true"
    resp = requests.get(url, timeout=45)
    if resp.status_code == 200 and len(resp.content) > 10_000:
        with open(out_path, "wb") as f:
            f.write(resp.content)
        return True
    return False


def is_valid_image(path):
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            w, h = im.size
            arr = np.asarray(im.convert("RGB"), dtype=np.float32)
            mean_val = float(arr.mean())
            return w >= 256 and h >= 256 and mean_val > 5.0
    except Exception:
        return False


def add_drifting_particles_clip(still_path, clip_dur, out_mp4, seed):
    """Creates a smooth Ken Burns clip with subtle drifting warm dust/firefly particles using Pillow + FFmpeg."""
    base_img = Image.open(still_path).convert("RGB").resize((OUTPUT_W, OUTPUT_H), Image.Resampling.LANCZOS)
    frames_dir = f"particles_{seed}"
    os.makedirs(frames_dir, exist_ok=True)

    rng = random.Random(seed)
    num_particles = 28
    particles = [
        {
            "x0": rng.uniform(60, OUTPUT_W - 60),
            "y0": rng.uniform(140, OUTPUT_H - 140),
            "amp_x": rng.uniform(10, 26),
            "amp_y": rng.uniform(12, 32),
            "freq": rng.uniform(0.35, 0.75),
            "phase": rng.uniform(0, 6.28),
            "r": rng.uniform(2.2, 4.8)
        }
        for _ in range(num_particles)
    ]

    num_frames = max(int(round(clip_dur * FPS)), 15)
    # Sample at 15fps overlay or 30fps directly for short clips
    for f_idx in range(num_frames):
        t = f_idx / float(FPS)
        progress = f_idx / float(max(num_frames - 1, 1))
        # Gentle eased zoom from 1.00 to 1.06
        ease = 0.5 - 0.5 * math.cos(math.pi * progress)
        zoom = 1.00 + (0.06 * ease)
        crop_w = int(OUTPUT_W / zoom)
        crop_h = int(OUTPUT_H / zoom)
        left = max(0, min(OUTPUT_W - crop_w, (OUTPUT_W - crop_w) // 2))
        top = max(0, min(OUTPUT_H - crop_h, (OUTPUT_H - crop_h) // 2))

        frame = base_img.crop((left, top, left + crop_w, top + crop_h)).resize((OUTPUT_W, OUTPUT_H), Image.Resampling.BILINEAR)
        # Subtle warm glow dots using numpy mask
        arr = np.asarray(frame, dtype=np.float32)
        yy, xx = np.mgrid[0:OUTPUT_H:8, 0:OUTPUT_W:8]
        glow_acc = np.zeros_like(yy, dtype=np.float32)
        for p in particles:
            px = (p["x0"] + p["amp_x"] * math.sin(2 * math.pi * p["freq"] * t + p["phase"])) / 8.0
            py = (p["y0"] + p["amp_y"] * math.cos(2 * math.pi * p["freq"] * t + p["phase"])) / 8.0
            dist2 = (xx - px) ** 2 + (yy - py) ** 2
            radius2 = max((p["r"] / 4.0) ** 2, 0.8)
            pulse = 0.65 + 0.35 * math.sin(3.0 * t + p["phase"])
            glow_acc += pulse * np.exp(-dist2 / (2.0 * radius2))

        glow_full = np.asarray(
            Image.fromarray(np.clip(glow_acc * 255, 0, 255).astype(np.uint8)).resize((OUTPUT_W, OUTPUT_H), Image.Resampling.BILINEAR),
            dtype=np.float32
        ) / 255.0
        arr[:, :, 0] = np.clip(arr[:, :, 0] + glow_full * 95.0, 0, 255)
        arr[:, :, 1] = np.clip(arr[:, :, 1] + glow_full * 68.0, 0, 255)
        arr[:, :, 2] = np.clip(arr[:, :, 2] + glow_full * 24.0, 0, 255)

        Image.fromarray(arr.astype(np.uint8)).save(os.path.join(frames_dir, f"f_{f_idx:04d}.jpg"), quality=86)

    subprocess.run([
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", os.path.join(frames_dir, "f_%04d.jpg"),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-pix_fmt", "yuv420p",
        out_mp4
    ], check=True)


def build_illustrated_background_video(line_prompts, line_start_times, total_duration):
    """Generates 1 painted illustration per script line and stitches them with smooth cross-dissolves."""
    base_seed = random.randint(100000, 999999)
    num_scenes = len(line_prompts)
    scene_durations = []

    for i in range(num_scenes):
        if i < num_scenes - 1:
            dur = max(1.6, line_start_times[i + 1] - line_start_times[i])
        else:
            dur = max(2.2, total_duration - line_start_times[i])
        scene_durations.append(round(dur, 2))

    clip_files = []
    for idx, (s_prompt, s_dur) in enumerate(zip(line_prompts, scene_durations)):
        still_path = f"scene_{idx}.png"
        full_prompt = f"{style_prefix}, {s_prompt}"
        ok = False
        for attempt in range(2):
            seed = base_seed + idx * 10 + attempt
            if generate_scene_image_cloudflare(full_prompt, seed, still_path) and is_valid_image(still_path):
                ok = True
                break
            if generate_scene_image_pollinations(full_prompt, seed, still_path) and is_valid_image(still_path):
                ok = True
                break

        if not ok:
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", f"color=c=#13222b:s={OUTPUT_W}x{OUTPUT_H}:r={FPS}:d={s_dur:.2f}",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                f"scene_clip_{idx}.mp4"
            ], check=True)
            clip_files.append(f"scene_clip_{idx}.mp4")
        else:
            clip_mp4 = f"scene_clip_{idx}.mp4"
            add_drifting_particles_clip(still_path, s_dur + 0.4, clip_mp4, base_seed + idx)
            clip_files.append(clip_mp4)

    if len(clip_files) == 1:
        subprocess.run(["cp", clip_files[0], "raw_video.mp4"], check=True)
        return

    # Concatenate scene clips cleanly and trim/pad to total_duration
    concat_list = "scenes_concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for cf in clip_files:
            f.write(f"file '{os.path.abspath(cf)}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
        "-t", f"{total_duration:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
        "raw_video.mp4"
    ], check=True)


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


def download_real_footage_background(target_duration):
    if PIXABAY_API_KEY:
        queries = [
            urllib.parse.quote(search_keyword),
            urllib.parse.quote(fallback_keyword),
            "calm+nature+rain",
            "ocean+waves+beach",
            "forest+trees+wind"
        ]
        for orientation_param in ["&orientation=vertical", ""]:
            for q in queries:
                if not q:
                    continue
                url = (
                    f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}"
                    f"&q={q}&video_type=film{orientation_param}&per_page=20&safesearch=true"
                )
                r = requests.get(url, timeout=20)
                raw_hits = r.json().get("hits", []) if r.status_code == 200 else []
                real_hits = [h for h in raw_hits if is_real_camera_footage(h)]
                if real_hits:
                    chosen = random.choice(real_hits)
                    vids = chosen.get("videos", {})
                    v_url = vids.get("large", {}).get("url") or vids.get("medium", {}).get("url") or vids.get("small", {}).get("url")
                    if v_url:
                        vid_data = requests.get(v_url, timeout=60).content
                        if len(vid_data) > 50_000:
                            with open("raw_video.mp4", "wb") as f:
                                f.write(vid_data)
                            return

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=#0d1b2a:s={OUTPUT_W}x{OUTPUT_H}:r={FPS}:d={target_duration:.2f}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "raw_video.mp4"
    ], check=True)


def fetch_asmr_audio(target_duration):
    niche_l = niche.lower().strip()
    q_str = NICHE_AUDIO_MAP.get(niche_l, search_keyword or "gentle rain window ambient asmr")
    if FREESOUND_API_KEY:
        try:
            query = urllib.parse.quote(q_str)
            url = f"https://freesound.org/apiv2/search/text/?query={query}&filter=duration:[15 TO 180]&fields=id,name,previews&page_size=8&token={FREESOUND_API_KEY}"
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                results = r.json().get("results", [])
                if results:
                    mp3_url = random.choice(results).get("previews", {}).get("preview-hq-mp3")
                    if mp3_url:
                        audio_data = requests.get(mp3_url, timeout=20).content
                        if len(audio_data) > 5000:
                            with open("asmr.mp3", "wb") as f:
                                f.write(audio_data)
                            return
        except Exception as e:
            print(f"Freesound ASMR fallback triggered: {e}")

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anoisesrc=d={target_duration:.2f}:c=pink:r=44100:a=0.10",
        "-af", "bandpass=f=900:width_type=h:w=700,tremolo=f=0.4:d=0.35,extrastereo=m=2.0",
        "asmr.mp3"
    ], check=True)


def fetch_relaxing_piano(target_duration):
    for filename in ["piano.mp3", "bgm.mp3", "audio/piano.mp3", "audio/default.mp3"]:
        if os.path.exists(filename) and os.path.getsize(filename) > 10_000:
            return filename

    excluded = {"asmr.mp3", "voice.mp3", "voice_raw.mp3", "cloud_piano.mp3", "synth_piano.mp3", "pause_gap.mp3"}
    for pattern in ["*.mp3", "music/*.mp3", "audio/*.mp3"]:
        for f in glob.glob(pattern):
            if os.path.basename(f) not in excluded and os.path.getsize(f) > 10_000:
                return f

    if FREESOUND_API_KEY:
        try:
            query = urllib.parse.quote("soft relaxing piano calm ambient instrumental")
            url = f"https://freesound.org/apiv2/search/text/?query={query}&filter=duration:[20 TO 240]&fields=id,name,previews&page_size=10&token={FREESOUND_API_KEY}"
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                results = r.json().get("results", [])
                if results:
                    mp3_url = random.choice(results).get("previews", {}).get("preview-hq-mp3")
                    if mp3_url:
                        audio_data = requests.get(mp3_url, timeout=20).content
                        if len(audio_data) > 5000:
                            with open("cloud_piano.mp3", "wb") as f:
                                f.write(audio_data)
                            return "cloud_piano.mp3"
        except Exception as e:
            print(f"Freesound Piano fallback triggered: {e}")

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=261.63:duration={target_duration:.2f}",
        "-f", "lavfi", "-i", f"sine=frequency=329.63:duration={target_duration:.2f}",
        "-f", "lavfi", "-i", f"sine=frequency=392.00:duration={target_duration:.2f}",
        "-f", "lavfi", "-i", f"sine=frequency=493.88:duration={target_duration:.2f}",
        "-filter_complex", (
            "[0:a]tremolo=f=0.25:d=0.6[a0];[1:a]tremolo=f=0.33:d=0.6[a1];"
            "[2:a]tremolo=f=0.20:d=0.6[a2];[3:a]tremolo=f=0.15:d=0.7[a3];"
            "[a0][a1][a2][a3]amix=inputs=4:duration=first,lowpass=f=650,volume=0.18"
        ),
        "synth_piano.mp3"
    ], check=True)
    return "synth_piano.mp3"


def render_ffmpeg(piano_file, lines, line_start_times, vo_duration, total_duration):
    raw_vid_duration = get_duration("raw_video.mp4")
    pts_multiplier = ((total_duration + 0.5) / raw_vid_duration) if (raw_vid_duration < total_duration and raw_vid_duration > 0.5) else 1.0

    piano_dur = get_duration(piano_file)
    max_offset = max(0.0, piano_dur - total_duration - 2.0)
    piano_start = random.uniform(0.0, max_offset) if max_offset > 4.0 else 0.0

    title_font = get_title_font()
    body_font = get_body_font()

    # Write Title file
    with open("title_txt.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write(title)

    # Write Watermark & End Card files
    with open("watermark_txt.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write(watermark_handle)

    credit_wrapped = "\n".join(textwrap.wrap(end_card_credit, width=32)) or end_card_credit
    with open("endcard_txt.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write(credit_wrapped)

    end_card_start = max(total_duration - END_CARD_SECONDS, 4.0)
    audio_fade_start = max(total_duration - AUDIO_FADE_DURATION, total_duration - 2.0)
    video_fade_start = max(total_duration - VIDEO_FADE_DURATION, 1.0)

    filters = []
    # Title visible from Frame 0 until end_card_start
    filters.append(
        f"drawtext=fontfile={title_font}:textfile=title_txt.txt:"
        f"fontcolor=#FFD700:fontsize=56:x=76:y=360:"
        f"shadowcolor=black@0.85:shadowx=2:shadowy=3:"
        f"enable='lt(t,{end_card_start:.2f})'"
    )

    # One line of poem at a time synced to its Kokoro timestamp
    for idx, line in enumerate(lines):
        wrapped_line = "\n".join(textwrap.wrap(line, width=28)) or line
        l_file = f"line_{idx}.txt"
        with open(l_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(wrapped_line)

        l_start = line_start_times[idx] if idx < len(line_start_times) else (VO_START_DELAY + idx * 2.5)
        l_end = (line_start_times[idx + 1] - 0.05) if (idx + 1 < len(line_start_times)) else (end_card_start - 0.1)
        l_end = max(l_end, l_start + 0.8)

        filters.append(
            f"drawtext=fontfile={body_font}:textfile={l_file}:"
            f"fontcolor=#FFFFFF:fontsize=54:x=76:y=860:"
            f"shadowcolor=black@0.90:shadowx=2:shadowy=3:"
            f"enable='between(t,{l_start:.2f},{l_end:.2f})'"
        )

    # Subtle watermark below body text
    if watermark_handle:
        filters.append(
            f"drawtext=fontfile={body_font}:textfile=watermark_txt.txt:"
            f"fontcolor=#E6C687@0.75:fontsize=30:x=76:y=1020:"
            f"shadowcolor=black@0.75:shadowx=1:shadowy=2:"
            f"enable='between(t,0.60,{end_card_start:.2f})'"
        )

    # End Card Credit on final ~2.5s
    if end_card_credit:
        filters.append(
            f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.68:t=fill:enable='gte(t,{end_card_start:.2f})',"
            f"drawtext=fontfile={body_font}:textfile=endcard_txt.txt:"
            f"fontcolor=#F8FAFC:fontsize=46:x=(w-text_w)/2:y=(h-text_h)/2:"
            f"shadowcolor=black@0.90:shadowx=2:shadowy=3:"
            f"enable='gte(t,{end_card_start:.2f})'"
        )

    drawtext_str = ",".join(filters)
    vo_start = VO_START_DELAY
    vo_end = VO_START_DELAY + vo_duration
    adelay_ms = int(VO_START_DELAY * 1000)

    duck_ramp = 0.45
    swell_ramp = 1.20
    duck_start = max(0.0, round(vo_start - duck_ramp, 2))
    swell_end = round(vo_end + swell_ramp, 2)

    piano_vol_expr = (
        f"if(lt(t,{duck_start:.2f}),0.35,"
        f"if(lt(t,{vo_start:.2f}),0.35-0.19*((t-{duck_start:.2f})/{duck_ramp:.2f}),"
        f"if(lt(t,{vo_end:.2f}),0.16,"
        f"if(lt(t,{swell_end:.2f}),0.16+0.19*((t-{vo_end:.2f})/{swell_ramp:.2f}),0.35))))"
    )
    asmr_vol_expr = (
        f"if(lt(t,{duck_start:.2f}),0.42,"
        f"if(lt(t,{vo_start:.2f}),0.42-0.22*((t-{duck_start:.2f})/{duck_ramp:.2f}),"
        f"if(lt(t,{vo_end:.2f}),0.20,"
        f"if(lt(t,{swell_end:.2f}),0.20+0.22*((t-{vo_end:.2f})/{swell_ramp:.2f}),0.42))))"
    )

    v_filter = (
        f"[0:v]setpts={pts_multiplier:.4f}*PTS,"
        f"scale={OUTPUT_W}:{OUTPUT_H}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_W}:{OUTPUT_H},setsar=1,fps={FPS},"
        f"eq=brightness=-0.04:contrast=1.08:saturation=0.92,"
        f"noise=alls=4:allf=t+u,vignette=PI/4,"
        f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.28:t=fill,"
        f"{drawtext_str},"
        f"fade=t=out:st={video_fade_start:.2f}:d={VIDEO_FADE_DURATION}[v]"
    )

    a_filter = (
        f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,lowpass=f=3000,volume='{piano_vol_expr}':eval=frame[piano];"
        f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo,apulsator=mode=sine:hz=0.08:amount=0.25,volume='{asmr_vol_expr}':eval=frame[asmr];"
        f"[3:a]aformat=sample_rates=44100:channel_layouts=stereo,adelay={adelay_ms}|{adelay_ms},apad=whole_dur={total_duration:.2f}[voice];"
        f"[piano][asmr][voice]amix=inputs=3:duration=first:dropout_transition=0:normalize=0,"
        f"afade=t=in:st=0:d=0.6,afade=t=out:st={audio_fade_start:.2f}:d={AUDIO_FADE_DURATION}[a]"
    )

    subprocess.run([
        "ffmpeg", "-y",
        "-i", "raw_video.mp4",
        "-ss", f"{piano_start:.2f}", "-stream_loop", "-1", "-i", piano_file,
        "-stream_loop", "-1", "-i", "asmr.mp3",
        "-i", "voice.mp3",
        "-filter_complex", f"{v_filter};{a_filter}",
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
    except Exception:
        return False


def upload_to_github_release(filepath):
    gh_token = os.environ.get("GITHUB_TOKEN", "").strip()
    gh_repo = os.environ.get("GITHUB_REPOSITORY", "maaaaaaaahiuddin-code/cloud-video-engine").strip()
    if not gh_token:
        return ""
    headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"}
    tag_name = "rendered-videos"
    api_base = f"https://api.github.com/repos/{gh_repo}"

    r = requests.get(f"{api_base}/releases/tags/{tag_name}", headers=headers, timeout=20)
    if r.status_code == 200:
        release_data = r.json()
    else:
        r_create = requests.post(
            f"{api_base}/releases",
            headers=headers,
            json={"tag_name": tag_name, "name": "Automated Cloud Videos", "draft": False, "prerelease": False},
            timeout=20
        )
        if r_create.status_code not in (200, 201):
            return ""
        release_data = r_create.json()

    release_id = release_data.get("id")
    asset_name = f"video_row_{row_id}_{random.randint(1000, 9999)}.mp4"
    upload_url = f"https://uploads.github.com/repos/{gh_repo}/releases/{release_id}/assets?name={asset_name}"
    with open(filepath, "rb") as f:
        r_up = requests.post(
            upload_url,
            headers={"Authorization": f"Bearer {gh_token}", "Content-Type": "video/mp4", "Accept": "application/vnd.github+json"},
            data=f,
            timeout=120
        )
    if r_up.status_code in (200, 201):
        dl_url = r_up.json().get("browser_download_url", "")
        if verify_url_accessible(dl_url):
            return dl_url
    return ""


def upload_video_with_fallback():
    if os.environ.get("CLOUDINARY_URL", "").startswith("cloudinary://"):
        try:
            res = cloudinary.uploader.upload("final_output.mp4", resource_type="video", folder="auto_relaxing_videos", timeout=120)
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
            r = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": ("final_output.mp4", f, "video/mp4")}, timeout=60)
        if r.status_code == 200:
            raw_url = r.json().get("data", {}).get("url", "")
            if raw_url:
                direct_url = raw_url.replace("http://", "https://", 1).replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)
                if verify_url_accessible(direct_url):
                    return direct_url
    except Exception as e:
        print(f"tmpfiles failed: {e}")

    return ""


def main():
    ensure_assets()
    lines = get_script_lines()
    line_prompts = get_line_visual_prompts(len(lines))

    line_start_times = generate_kokoro_asmr_voiceover(lines)
    vo_duration = get_duration("voice.mp3")
    total_duration = max(14.0, round(VO_START_DELAY + vo_duration + END_CARD_SECONDS + EXTRA_TAIL_SECONDS, 2))

    if visual_mode == "footage":
        download_real_footage_background(total_duration)
    else:
        build_illustrated_background_video(line_prompts, line_start_times, total_duration)

    fetch_asmr_audio(total_duration)
    piano_file = fetch_relaxing_piano(total_duration)
    render_ffmpeg(piano_file, lines, line_start_times, vo_duration, total_duration)

    video_url = upload_video_with_fallback()
    if not video_url or not video_url.startswith("http"):
        raise RuntimeError("Video upload failed across all hosts!")

    webhook_payload = {
        "row_id": row_id,
        "title": title,
        "video_url": video_url,
        "caption": caption
    }

    target_webhooks = [PRIMARY_MAKE_WEBHOOK]
    if MAKE_WEBHOOK_URL.startswith("http") and MAKE_WEBHOOK_URL != PRIMARY_MAKE_WEBHOOK:
        target_webhooks.append(MAKE_WEBHOOK_URL)

    for wh_url in target_webhooks:
        resp = requests.post(wh_url, json=webhook_payload, headers={"Content-Type": "application/json"}, timeout=30)
        print(f"Sent webhook to {wh_url} -> Status: {resp.status_code}")


if __name__ == "__main__":
    main()
