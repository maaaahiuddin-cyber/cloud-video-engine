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
    SEARCH_KEYWORD = str(PAYLOAD.get("search_keyword", "")).strip()
    CAPTION = str(PAYLOAD.get(
        "caption",
        "let's never become strangers #poetry #romance #lovequotes #reels"
    )).strip()

    USE_PIXEL_LOCKED_CUTOUT = False

    OUTRO_TAIL_DURATION = 2.00
    FADE_OUT_DURATION = 1.20
    CLAUSE_PAUSE_SEC = 0.65
    VOICE_SPEED = 0.90

    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
    GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "maaaahiuddin-cyber/cloud-video-engine").strip()
    FREESOUND_API_KEY = os.environ.get("FREESOUND_API_KEY", "").strip().strip('"').strip("'")
    PRIMARY_MAKE_WEBHOOK = "[https://hook.us2.make.com/ga5opcigaf8fw3keq4zh5x5uy2r6gs24](https://hook.us2.make.com/ga5opcigaf8fw3keq4zh5x5uy2r6gs24)"

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
            "[https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx](https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx)",
            timeout=120
        )
        r.raise_for_status()
        with open(model_path, "wb") as f:
            f.write(r.content)

    if not os.path.exists(voices_path) or os.path.getsize(voices_path) < 1_000_000:
        print("Downloading Kokoro-82M voices pack...")
        r = requests.get(
            "[https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin](https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin)",
            timeout=60
        )
        r.raise_for_status()
        with open(voices_path, "wb") as f:
            f.write(r.content)

    if not os.path.exists(italic_font_path) or os.path.getsize(italic_font_path) < 30_000:
        italic_urls = [
            "[https://raw.githubusercontent.com/google/fonts/main/ofl/crimsontext/CrimsonText-Italic.ttf](https://raw.githubusercontent.com/google/fonts/main/ofl/crimsontext/CrimsonText-Italic.ttf)",
            "[https://raw.githubusercontent.com/google/fonts/main/ofl/ebgaramond/EBGaramond-Italic%5Bwght%5D.ttf](https://raw.githubusercontent.com/google/fonts/main/ofl/ebgaramond/EBGaramond-Italic%5Bwght%5D.ttf)",
            "[https://raw.githubusercontent.com/google/fonts/main/ofl/crimsontext/CrimsonText-Regular.ttf](https://raw.githubusercontent.com/google/fonts/main/ofl/crimsontext/CrimsonText-Regular.ttf)"
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
        print(f"Scene {idx+1}: {scene_start:.2f}s -> {scene_end:.2f}s | '{clause}'")

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


def build_meaningful_scene_prompt(clause_text, sheet_kw, niche, scene_idx, char_anchor):
    """Builds a scene description directly tied to what the spoken overlay line means."""
    c_low = clause_text.lower()
    concept_cues = []

    if any(k in c_low for k in ["rain", "storm", "wet", "umbrella"]):
        concept_cues.append("standing under gentle evening rain with warm streetlights reflecting on wet ground")
    if any(k in c_low for k in ["window", "glass", "outside", "night sky", "moon", "star"]):
        concept_cues.append("looking out a window into a twilight evening sky with soft glowing lights")
    if any(k in c_low for k in ["tea", "coffee", "cup", "warm", "home", "kitchen", "table"]):
        concept_cues.append("in a warm cozy room with a steaming cup and soft golden lamp light")
    if any(k in c_low for k in ["walk", "path", "street", "road", "away", "strangers", "left"]):
        concept_cues.append("walking slowly along a quiet tree-lined street at golden dusk")
    if any(k in c_low for k in ["hand", "hold", "touch", "shoulder", "arms", "close", "found you", "love you"]):
        concept_cues.append("sharing a quiet, heartfelt moment close together in soft golden-hour light")
    if any(k in c_low for w in ["memory", "memories", "time", "used to", "past", "ago", "years", "childhood"]):
        concept_cues.append("in a quiet nostalgic evening setting with warm sunset light and soft shadows")
    if any(k in c_low for k in ["breath", "quiet", "peace", "still", "sleep", "rest", "alone", "dark"]):
        concept_cues.append("in a calm, peaceful dusk setting with soft natural light and quiet atmosphere")

    if not concept_cues:
        concept_cues.append("in a calm, meaningful outdoor setting at golden dusk with natural light")

    meaning_part = "; ".join(concept_cues[:2])
    setting_str = f"{sheet_kw.strip()}, {meaning_part}" if sheet_kw.strip() else meaning_part

    return (
        f"{char_anchor}, depicting the meaning of '{clause_text.strip()}', "
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


def enhance
