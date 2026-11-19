import os
import re
import sys
import time
import glob
import json
import random
import hashlib
import asyncio
import urllib.parse
import textwrap
import subprocess
import requests

# ==============================================================================
# 0. DEPENDENCY BOOTSTRAP & CLOUDINARY SANITIZATION
# ==============================================================================
try:
    import cv2
    import soundfile as sf
    import numpy as np
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter
    from kokoro_onnx import Kokoro
except ImportError:
    subprocess.run([
        sys.executable, "-m", "pip", "install",
        "opencv-python-headless", "kokoro-onnx", "soundfile", "numpy", "pillow", "fonttools", "edge-tts", "gTTS"
    ], check=True)
    import cv2
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
# 1. CENTRALIZED CONFIGURATION — NATURAL VOICE + MEANINGFUL 8K SCENES + FX
# ==============================================================================
class Config:
    _raw_payload = os.environ.get("PAYLOAD_JSON", "{}")
    try:
        PAYLOAD = json.loads(_raw_payload) if _raw_payload else {}
    except Exception:
        PAYLOAD = {}

    ROW_ID = str(PAYLOAD.get("row_id", "1")).strip()
    TITLE = str(PAYLOAD.get("title", "Ordinary Evenings")).strip()
    NICHE = str(PAYLOAD.get("niche", "love")).strip()
    OVERLAY_TEXT = str(PAYLOAD.get(
        "overlay_text",
        "I don't want a love made for movies / "
        "I want the quiet evenings with you / "
        "two cups of tea on a small balcony / "
        "talking until the streetlights flicker on / "
        "watching the moon climb over the rooftops / "
        "knowing tomorrow I get to wake up / "
        "and choose you all over again"
    )).strip()
    SEARCH_KEYWORD = str(PAYLOAD.get(
        "search_keyword",
        "vintage cinema rain | warm kitchen light | two teacups balcony sunset | cobblestone streetlamps dusk | full moon over rooftops | sunrise bedroom curtains | walking beach"
    )).strip()
    FALLBACK_KEYWORD = str(PAYLOAD.get("fallback_keyword", "cozy window sunset")).strip()
    CAPTION = str(PAYLOAD.get(
        "caption",
        "Ordinary Evenings — I don't want a love made for movies... and choose you all over again. #lovequotes #romance #poetrycommunity #deepquotes #reels"
    )).strip()

    USE_PIXEL_LOCKED_CUTOUT = False

    OUTRO_TAIL_DURATION = 2.00
    FADE_OUT_DURATION = 1.20
    CLAUSE_PAUSE_SEC = 0.65
    VOICE_SPEED = 0.90

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
        "authentic skin texture, calm expressive eyes, wearing a cream linen shirt over a dark navy tee"
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
        "natural lighting, crisp focus, authentic depth of field, vertical 9:16, no text, no watermark"
    )


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
# 3. NATURAL HUMAN VOICEOVER & TIMING ENGINE
# ==============================================================================
def split_into_poetic_clauses(text):
    """Splits Overlay_Text into short poetic scene lines."""
    cleaned = text.replace(chr(13) + chr(10), chr(10)).strip()
    if "/" in cleaned:
        raw_parts = [p.strip() for p in cleaned.split("/") if p.strip()]
    elif chr(10) in cleaned:
        raw_parts = [p.strip() for p in cleaned.split(chr(10)) if p.strip()]
    else:
        raw_parts = [p.strip() for p in re.split(r"(?<=[.!?…,;:])\\s+", cleaned) if p.strip()]

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


async def _synthesize_edge_tts_clause(text, out_wav, voice="en-US-ChristopherNeural", rate="-6%"):
    import edge_tts
    tmp_mp3 = out_wav + ".tmp.mp3"
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(tmp_mp3)
    subprocess.run([
        "ffmpeg", "-y", "-i", tmp_mp3, "-ar", "24000", "-ac", "1", out_wav
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(tmp_mp3):
        os.remove(tmp_mp3)


def generate_natural_human_voiceover(clauses):
    """
    Generates natural, human-sounding narration using clean Kokoro-82M speech
    (without heavy room echo or artificial pitch shifts) with Edge-TTS fallback.
    """
    scene_timings = []
    sample_rate = 24000
    kokoro = None

    try:
        kokoro = Kokoro("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")
        print("Loaded Kokoro-82M voice synthesizer.")
    except Exception as e:
        print(f"Kokoro load note ({e}), will use Edge-TTS if needed.")

    audio_segments = []
    current_sec = 0.0

    for idx, clause in enumerate(clauses):
        spoken_clause = clause.strip()
        if spoken_clause and spoken_clause[-1] not in ".!?,":
            spoken_clause += "," if idx < len(clauses) - 1 else "."

        clause_wav = f"clause_{idx}.wav"
        synthesized = False

        if kokoro is not None:
            try:
                try:
                    v_m = kokoro.get_voice_style("am_michael")
                    v_f = kokoro.get_voice_style("bm_fable")
                    natural_vec = (v_m * 0.75) + (v_f * 0.25)
                except Exception:
                    natural_vec = "am_michael"

                samples, sample_rate = kokoro.create(
                    spoken_clause,
                    voice=natural_vec,
                    speed=Config.VOICE_SPEED,
                    lang="en-us"
                )
                sf.write(clause_wav, samples, sample_rate)
                synthesized = True
            except Exception as e:
                print(f"Kokoro clause {idx+1} fallback to Edge-TTS: {e}")

        if not synthesized:
            try:
                asyncio.run(_synthesize_edge_tts_clause(spoken_clause, clause_wav, voice="en-US-ChristopherNeural", rate="-6%"))
                samples, sample_rate = sf.read(clause_wav, dtype="float32")
                synthesized = True
            except Exception as e:
                print(f"Edge-TTS clause {idx+1} skipped: {e}")
                samples = np.zeros(int(sample_rate * 2.2), dtype=np.float32)

        seg_dur = max(len(samples) / float(sample_rate), 0.5)
        pad_dur = Config.CLAUSE_PAUSE_SEC if idx < len(clauses) - 1 else 0.45

        scene_start = round(current_sec, 3)
        scene_end = round(max(current_sec + seg_dur + pad_dur, scene_start + 0.5), 3)
        scene_timings.append((scene_start, scene_end, clause))
        print(f"Scene {idx+1}: {scene_start:.2f}s -> {scene_end:.2f}s | {clause}")

        audio_segments.append(samples.astype(np.float32))
        audio_segments.append(np.zeros(int(sample_rate * pad_dur), dtype=np.float32))
        current_sec = scene_end

    audio_segments.append(np.zeros(int(sample_rate * (Config.OUTRO_TAIL_DURATION + 0.5)), dtype=np.float32))
    full_audio = np.concatenate(audio_segments)
    sf.write("voice_raw.wav", full_audio, sample_rate)

    subprocess.run([
        "ffmpeg", "-y", "-i", "voice_raw.wav",
        "-af", (
            "aformat=sample_rates=44100:channel_layouts=stereo,"
            "highpass=f=65,"
            "equalizer=f=130:width_type=o:w=1.5:g=2.0,"
            "equalizer=f=5200:width_type=o:w=1.5:g=-2.5,"
            "lowpass=f=11500,"
            "volume=1.8"
        ),
        "-ar", "44100", "-ac", "2", "voice.mp3"
    ], check=True)
    return scene_timings


# ==============================================================================
# 4. MEANINGFUL OVERLAY-MATCHED SCENES & OPENCV PARTICLE/FOG ENGINE
# ==============================================================================
def select_video_wide_character(overlay_text, niche, row_id_str):
    """Locks ONE realistic character cast (Boy, Girl, or Couple) for the entire video."""
    n_low = niche.lower().strip()
    text_low = overlay_text.lower()
    digits = re.sub(r"\\D", "", row_id_str)
    row_num = int(digits) if digits else 1

    if n_low in ("love", "soulmates") or any(
        w in text_low for w in ["found you", "love you", "strangers", "together", "we ", "us ", "beside you", "your hand", "wake up", "choose you"]
    ):
        return "2 Characters (Same Couple Start-to-End)", Config.COUPLE_ANCHOR
    elif n_low == "healing" or any(w in text_low for w in ["she ", "her ", "bloom", "softness"]):
        return "1 Character (Same Girl Start-to-End)", Config.GIRL_ANCHOR
    elif n_low in ("solitude", "nostalgia", "longing"):
        if row_num % 3 == 0:
            return "1 Character (Same Girl Start-to-End)", Config.GIRL_ANCHOR
        return "1 Character (Same Boy Start-to-End)", Config.BOY_ANCHOR
    return "2 Characters (Same Couple Start-to-End)", Config.COUPLE_ANCHOR


def build_meaningful_scene_prompt(clause_text, sheet_kw, niche, scene_idx, char_anchor):
    """Builds a scene description directly tied to what the spoken overlay line means."""
    c_low = clause_text.lower()
    concept_cues = []

    if any(k in c_low for k in ["rain", "storm", "wet", "umbrella"]):
        concept_cues.append("standing under gentle evening rain with warm streetlights reflecting on wet ground")
    if any(k in c_low for k in ["window", "glass", "outside", "night sky", "moon", "star", "rooftops", "sunrise", "curtains"]):
        concept_cues.append("looking out toward a twilight or sunrise sky with soft glowing lights")
    if any(k in c_low for k in ["tea", "coffee", "cup", "warm", "home", "kitchen", "table", "balcony", "evening", "evenings"]):
        concept_cues.append("in a warm cozy evening setting with soft golden lamp light")
    if any(k in c_low for k in ["walk", "path", "street", "road", "away", "strangers", "left", "beach"]):
        concept_cues.append("walking slowly along a quiet scenic path at golden dusk")
    if any(k in c_low for k in ["hand", "hold", "touch", "shoulder", "arms", "close", "found you", "love you", "choose you", "wake up"]):
        concept_cues.append("sharing a quiet, heartfelt moment close together in soft golden-hour light")
    if any(k in c_low for k in ["memory", "memories", "time", "used to", "past", "ago", "years", "childhood"]):
        concept_cues.append("in a quiet nostalgic evening setting with warm sunset light and soft shadows")
    if any(k in c_low for k in ["breath", "quiet", "peace", "still", "sleep", "rest", "alone", "dark"]):
        concept_cues.append("in a calm, peaceful dusk setting with soft natural light and quiet atmosphere")

    if not concept_cues:
        concept_cues.append("in a calm, meaningful outdoor setting at golden dusk with natural light")

    meaning_part = "; ".join(concept_cues[:2])
    setting_str = f"{sheet_kw.strip()}, {meaning_part}" if sheet_kw.strip() else meaning_part

    return (
        f"{char_anchor}, depicting the meaning of {clause_text.strip()}, "
        f"setting: {setting_str}, {Config.REALISTIC_CINEMA_STYLE}"
    )


def choose_particle_mode(clause_text, niche, scene_idx):
    """Selects particle style (petals, snow, fireflies, or dust) matched to the scene mood."""
    c_low = f"{clause_text} {niche}".lower()
    if any(w in c_low for w in ["winter", "snow", "cold", "freeze", "december"]):
        return "snow"
    if any(w in c_low for w in ["autumn", "fall", "petal", "flower", "bloom", "spring", "love"]):
        return "petals" if (scene_idx % 2 == 0) else "fireflies"
    if any(w in c_low for w in ["night", "moon", "star", "midnight", "firefly", "dark", "dream"]):
        return "fireflies"
    return "dust"


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
            return float(arr.mean()) > 12.0 and float(arr.std()) > 8.0
    except Exception:
        return False


def enhance_image_ultra_hd(img_path):
    """Pre-masters every scene image to 1080x1920 with Lanczos + UnsharpMask + natural clarity."""
    with Image.open(img_path) as im:
        rgb = im.convert("RGB")
        rgb = ImageOps.fit(rgb, (1080, 1920), method=Image.Resampling.LANCZOS)
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.4, percent=120, threshold=2))
        rgb = ImageEnhance.Color(rgb).enhance(1.08)
        rgb = ImageEnhance.Contrast(rgb).enhance(1.05)
        rgb.save(img_path, format="JPEG", quality=96, subsampling=0)


def render_opencv_particle_fog_clip(img_path, vid_path, dur, scene_idx, particle_mode="fireflies"):
    """
    Renders a 30fps 1080x1920 scene clip using OpenCV & NumPy with:
      - 35-55 soft glowing particles (fireflies, dust, petals, or snow) with slow sine-wave drift
      - ~3% gentle light flicker / glow pulse
      - Soft animated fog/mist noise layer
    """
    base = cv2.imread(img_path)
    if base is None:
        base = np.full((1920, 1080, 3), 36, dtype=np.uint8)
    base = cv2.resize(base, (1080, 1920), interpolation=cv2.INTER_LANCZOS4).astype(np.float32)

    fps = 30
    total_frames = max(int(round(dur * fps)), 30)
    rng = np.random.default_rng(seed=7000 + scene_idx * 131)

    count = int(rng.integers(35, 56))
    bx = rng.uniform(0.0, 1080.0, size=count)
    by = rng.uniform(0.0, 1920.0, size=count)
    radii = rng.uniform(3.5, 9.0, size=count)
    phases = rng.uniform(0.0, 2.0 * np.pi, size=count)
    freq_x = rng.uniform(0.35, 0.95, size=count)
    freq_y = rng.uniform(0.30, 0.85, size=count)
    amp_x = rng.uniform(10.0, 24.0, size=count)
    amp_y = rng.uniform(10.0, 22.0, size=count)
    vel_x = rng.uniform(-10.0, 10.0, size=count)
    vel_y = rng.uniform(-14.0, 10.0, size=count)

    if particle_mode == "petals":
        color_bgr = np.array([135.0, 145.0, 240.0], dtype=np.float32)
    elif particle_mode == "snow":
        color_bgr = np.array([245.0, 248.0, 255.0], dtype=np.float32)
    elif particle_mode == "dust":
        color_bgr = np.array([195.0, 225.0, 250.0], dtype=np.float32)
    else:
        color_bgr = np.array([130.0, 235.0, 255.0], dtype=np.float32)

    fog_seed_map = rng.normal(0.0, 1.0, size=(240, 135)).astype(np.float32)
    fog_blur = cv2.GaussianBlur(fog_seed_map, (23, 23), 0)
    fog_up = cv2.resize(fog_blur, (1080, 1920), interpolation=cv2.INTER_LINEAR)
    fog_norm = (fog_up - fog_up.min()) / (fog_up.max() - fog_up.min() + 1e-6)

    tmp_avi = vid_path + ".raw.avi"
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(tmp_avi, fourcc, fps, (1080, 1920))

    for f_idx in range(total_frames):
        t = f_idx / float(fps)

        zoom = 1.0 + 0.03 * (f_idx / float(total_frames))
        shift_x = 14.0 * np.sin(0.4 * t + scene_idx)
        shift_y = -14.0 * np.cos(0.35 * t + scene_idx)
        mat = cv2.getRotationMatrix2D((540.0, 960.0), 0.0, zoom)
        mat[0, 2] += shift_x
        mat[1, 2] += shift_y
        frame = cv2.warpAffine(base, mat, (1080, 1920), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)

        glow_pulse = 1.0 + 0.03 * np.sin(2.0 * np.pi * 0.6 * t + scene_idx)
        frame = frame * glow_pulse

        ox = int((22.0 * np.sin(0.25 * t)) % 1080)
        oy = int((14.0 * t) % 1920)
        fog_frame = np.roll(np.roll(fog_norm, oy, axis=0), ox, axis=1)
        fog_alpha = 0.045 + 0.015 * np.sin(1.1 * t)
        frame = frame + (fog_frame[:, :, None] * 255.0 * fog_alpha)

        p_canvas = np.zeros((1920, 1080, 3), dtype=np.float32)
        for i in range(count):
            x_cur = (bx[i] + vel_x[i] * t + amp_x[i] * np.sin(freq_x[i] * t + phases[i])) % 1080.0
            y_cur = (by[i] + vel_y[i] * t + amp_y[i] * np.cos(freq_y[i] * t + phases[i])) % 1920.0
            twinkle = 0.45 + 0.55 * (0.5 + 0.5 * np.sin(2.0 * t + phases[i] * 2.0))
            cv2.circle(
                p_canvas,
                (int(round(x_cur)), int(round(y_cur))),
                max(2, int(round(radii[i]))),
                (color_bgr * twinkle).tolist(),
                -1,
                lineType=cv2.LINE_AA
            )

        p_glow = cv2.GaussianBlur(p_canvas, (0, 0), sigmaX=4.5, sigmaY=4.5)
        out_frame = np.clip(frame + p_glow * 0.75, 0, 255).astype(np.uint8)
        writer.write(out_frame)

    writer.release()

    subprocess.run([
        "ffmpeg", "-y", "-i", tmp_avi,
        "-r", "30",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-video_track_timescale", "15360",
        vid_path
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(tmp_avi):
        os.remove(tmp_avi)


def fetch_realistic_hd_fallbacks(out_path, scene_kw, scene_idx, used_urls):
    """High-resolution photography fallback via Wallhaven."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    wh_queries = [
        f"https://wallhaven.cc/api/v1/search?q={urllib.parse.quote(scene_kw)}&categories=100&purity=100&ratios=9x16,10x16&sorting=favorites",
        "https://wallhaven.cc/api/v1/search?q=night+city+lights&categories=100&purity=100&ratios=9x16,10x16&sorting=favorites",
        "https://wallhaven.cc/api/v1/search?q=sunset+ocean+sky&categories=100&purity=100&ratios=9x16,10x16&sorting=favorites"
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
                            return True
        except Exception as e:
            print(f"Wallhaven fallback skipped: {e}")
    return False


def create_distinct_variation_from_existing(source_img_path, target_img_path, scene_idx):
    """Creates a distinct variation if external image networks time out."""
    with Image.open(source_img_path) as im:
        rgb = im.convert("RGB")
        if scene_idx % 2 == 1:
            rgb = ImageOps.mirror(rgb)
        w, h = rgb.size
        crop_margin_x = int(w * 0.05)
        crop_margin_y = int(h * 0.05)
        rgb = rgb.crop((crop_margin_x, crop_margin_y, w - crop_margin_x, h - crop_margin_y))
        rgb = ImageOps.fit(rgb, (1080, 1920), method=Image.Resampling.LANCZOS)
        rgb = ImageEnhance.Color(rgb).enhance(1.06)
        rgb.save(target_img_path, format="JPEG", quality=96, subsampling=0)


def generate_meaningful_8k_scenes(scene_timings):
    """
    Generates 8K realistic scenes matched to each spoken overlay clause,
    locks the character cast from start to end, and adds OpenCV/NumPy particles + fog + glow pulse.
    """
    num_scenes = len(scene_timings)
    scene_video_files = []
    verified_scene_images = []
    used_fallback_urls = set()
    used_image_hashes = set()

    char_label, locked_char_anchor = select_video_wide_character(
        Config.OVERLAY_TEXT, Config.NICHE, Config.ROW_ID
    )
    digits = re.sub(r"\\D", "", Config.ROW_ID)
    row_num = int(digits) if digits else 1
    video_character_seed = 50000 + (row_num * 997)
    print(f"Character Lock: {char_label} (Seed={video_character_seed})")

    custom_scene_keywords = [k.strip() for k in Config.SEARCH_KEYWORD.split("|") if k.strip()]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for idx, (s_start, s_end, clause_text) in enumerate(scene_timings):
        dur = max((s_end - s_start) + (Config.OUTRO_TAIL_DURATION if idx == num_scenes - 1 else 0.0), 0.5)
        sheet_kw = custom_scene_keywords[idx] if idx < len(custom_scene_keywords) else Config.FALLBACK_KEYWORD

        prompt_text = build_meaningful_scene_prompt(
            clause_text, sheet_kw, Config.NICHE.lower(), idx, locked_char_anchor
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
                            print(f"Scene {idx+1}/{num_scenes} ({dur:.2f}s) matched to overlay: {clause_text}")
                            break
                time.sleep(1.5)
            except Exception as e:
                print(f"Scene {idx+1} attempt {attempt+1} skipped: {e}")
                time.sleep(1.5)

        if not downloaded:
            downloaded = fetch_realistic_hd_fallbacks(img_path, sheet_kw or clause_text, idx, used_fallback_urls)

        if not downloaded and verified_scene_images:
            create_distinct_variation_from_existing(verified_scene_images[-1], img_path, idx)
            downloaded = is_valid_non_black_image(img_path)

        if downloaded:
            verified_scene_images.append(img_path)

        p_mode = choose_particle_mode(clause_text, Config.NICHE, idx)
        render_opencv_particle_fog_clip(img_path, vid_path, dur, idx, particle_mode=p_mode)
        scene_video_files.append(vid_path)

    with open("concat_scenes.txt", "w", encoding="utf-8") as f:
        for vf in scene_video_files:
            f.write(f"file {repr(vf)}" + chr(10))

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat_scenes.txt",
        "-r", "30", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "raw_video.mp4"
    ], check=True)


# ==============================================================================
# 5. AUDIO & MASTER VIDEO COMPOSITOR
# ==============================================================================
def fetch_ambient_pad_music(target_duration):
    """Detects uploaded piano.mp3 / bgm.mp3 or synthesizes a soft ambient bed."""
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
            "lowpass=f=520,aecho=0.85:0.90:160|320:0.45|0.35,extrastereo=m=1.8,volume=0.18"
        ),
        "synth_piano.mp3"
    ], check=True)
    return "synth_piano.mp3"


def render_poetic_video(piano_file, scene_timings):
    """Composites animated particle/fog scenes, crisp italic subtitles, and natural audio."""
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
            with open(fname, "w", encoding="utf-8", newline=chr(10)) as f:
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
                f"enable=between(t\\,{safe_start:.2f}\\,{safe_end:.2f})"
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
        f"if(lt(t,{vo_end:.2f}),0.20,"
        f"if(lt(t,{swell_end:.2f}),0.20+0.14*(t-{vo_end:.2f}),0.34))"
    )

    a_filter = (
        f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,"
        f"lowpass=f=1800,aecho=0.85:0.88:120|240:0.30|0.20,"
        f"volume={repr(pad_vol_expr)}:eval=frame[pad];"
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
    scene_timings = generate_natural_human_voiceover(clauses)
    total_duration = round(scene_timings[-1][1] + Config.OUTRO_TAIL_DURATION, 2)
    print(f"Generated {len(scene_timings)} scenes -> Total Video Duration: {total_duration:.2f}s")

    generate_meaningful_8k_scenes(scene_timings)
    piano_file = fetch_ambient_pad_music(total_duration)

    render_poetic_video(piano_file, scene_timings)
    video_url = upload_video_with_fallback()
    print(f"Final Hosted Video URL: {video_url}")

    send_make_webhook(video_url)


if __name__ == "__main__":
    main()
