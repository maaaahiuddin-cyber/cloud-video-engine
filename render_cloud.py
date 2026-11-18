import os
import re
import sys
import glob
import time
import json
import random
import shutil
import hashlib
import urllib.parse
import textwrap
import requests
import subprocess

# ==============================================================================
# 0. DEPENDENCY BOOTSTRAP & CLOUDINARY SANITIZATION
# ==============================================================================
try:
    import soundfile as sf
    import numpy as np
    from kokoro_onnx import Kokoro
except ImportError:
    subprocess.run([
        sys.executable, "-m", "pip", "install",
        "kokoro-onnx", "soundfile", "numpy", "fonttools", "edge-tts", "gTTS"
    ], check=True)
    import soundfile as sf
    import numpy as np
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
# 1. CENTRALIZED CONFIGURATION — MODE 1 (TOKEN-LOCKED FLUX SEED, DEFAULT)
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

    # Mode 1 Default: Video-Wide Token-Locked Flux Seed
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

    # Compact Character Anchors (Keeps character consistent while avoiding URL length truncation)
    BOY_ANCHOR = (
        "1990s retro anime young man with messy dark brown wavy hair and cream linen shirt over navy t-shirt, waist-up shot"
    )
    GIRL_ANCHOR = (
        "1990s retro anime young woman with wavy chestnut hair, soft bangs, terracotta sundress and cream cardigan, waist-up shot"
    )
    COUPLE_ANCHOR = (
        "1990s retro anime romantic couple, young man in cream shirt and young woman in terracotta dress together, waist-up shot"
    )

    RETRO_ANIME_STYLE = (
        "vintage 90s anime cel-shaded romance illustration, studio ghibli makoto shinkai style, "
        "burnt terracotta orange and deep midnight blue palette, warm film grain, vertical 9:16, no text"
    )

    SCENE_ENVIRONMENTS_POOL = [
        "on a vintage European rooftop under a glowing full moon and dark navy night sky",
        "on a coastal balcony overlooking the bay at sunset under a crescent moon",
        "along a rain-washed cobblestone street under a warm glowing streetlamp at night",
        "by an open vintage wooden window overlooking dark rippling ocean waves at sunset",
        "in a quiet dark meadow at night surrounded by glowing golden fireflies and warm lanterns",
        "on a stone bridge over a calm moonlit canal with floating paper lanterns",
        "inside a vintage night train carriage with blurred glowing town lights outside the glass",
        "on a wooden seaside pier stretching into a twilight sea under orange and indigo clouds",
        "along a quiet park path at dusk surrounded by swirling red autumn leaves",
        "in a cozy vintage room lit by a flickering candle flame beside a rain-streaked windowpane",
        "on a quiet grassy hillside under a galaxy of stars overlooking a sleeping coastal village",
        "inside a warm vintage bookstore corner at night with amber lamp light and rain outside",
        "along a calm misty shoreline at dawn with golden water reflections",
        "on an outdoor cafe terrace at twilight with warm string lights and evening sky"
    ]

    WALLHAVEN_QUERIES = [
        "makoto shinkai",
        "anime night sky",
        "anime sunset",
        "anime rain",
        "anime stars",
        "anime city night",
        "anime clouds",
        "studio ghibli"
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
            seg_dur = len(samples) / float(sample_rate)
            pad_dur = Config.CLAUSE_PAUSE_SEC if idx < len(clauses) - 1 else 0.45

            scene_start = round(current_sec, 3)
            scene_end = round(current_sec + seg_dur + pad_dur, 3)
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
# 4. ZERO-BLACK-SCREEN MULTI-SCENE IMAGE FETCHER & CAMERA MOTION ENGINE
# ==============================================================================
def select_video_wide_character(overlay_text, niche, row_id_str):
    """
    Mode 1 Cast Lock: Selects ONE character cast (Boy, Girl, or Couple) for the ENTIRE video
    from 0.00s to the end so the protagonist never switches mid-video.
    """
    n_low = niche.lower().strip()
    text_low = overlay_text.lower()
    row_num = int(re.sub(r'\D', '', row_id_str) or "1")

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


def fetch_fallback_anime_art(out_path, scene_idx, used_urls, used_hashes):
    """
    3-Stage Real Anime Art Fallback (Wallhaven Broad Search -> Nekos.best -> Waifu.pics)
    so if Pollinations rate-limits a cloud IP, a real high-res anime illustration is still downloaded.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    # Stage A: Wallhaven Anime Category (without strict 9x16 filter; FFmpeg crops 1080x1920 cleanly)
    for q_offset in range(2):
        q_str = Config.WALLHAVEN_QUERIES[(scene_idx + q_offset * 3) % len(Config.WALLHAVEN_QUERIES)]
        try:
            url = (
                f"https://wallhaven.cc/api/v1/search?q={urllib.parse.quote(q_str)}"
                f"&categories=010&purity=100&sorting=favorites&page={scene_idx + 1}"
            )
            r = requests.get(url, timeout=20, headers=headers)
            hits = r.json().get("data", []) if r.status_code == 200 else []
            random.shuffle(hits)
            for hit in hits:
                img_url = hit.get("path", "")
                if img_url and img_url not in used_urls:
                    img_resp = requests.get(img_url, timeout=30, headers=headers)
                    if img_resp.status_code == 200 and len(img_resp.content) > 20_000:
                        h_val = hashlib.sha256(img_resp.content).hexdigest()
                        if h_val not in used_hashes:
                            with open(out_path, "wb") as f:
                                f.write(img_resp.content)
                            used_urls.add(img_url)
                            used_hashes.add(h_val)
                            print(f"Scene {scene_idx+1}: Downloaded Wallhaven anime art ('{q_str}').")
                            return True
        except Exception as e:
            print(f"Wallhaven attempt skipped: {e}")

    # Stage B: Nekos.best & Waifu.pics High-Res Anime Illustration APIs (zero rate limit, no API key)
    backup_apis = [
        "https://nekos.best/api/v2/waifu",
        "https://api.waifu.pics/sfw/waifu"
    ]
    for api_url in backup_apis:
        try:
            r = requests.get(api_url, timeout=15, headers=headers)
            if r.status_code == 200:
                data = r.json()
                img_url = data.get("url") or (data.get("results", [{}])[0].get("url", ""))
                if img_url and img_url not in used_urls:
                    img_resp = requests.get(img_url, timeout=25, headers=headers)
                    if img_resp.status_code == 200 and len(img_resp.content) > 15_000:
                        with open(out_path, "wb") as f:
                            f.write(img_resp.content)
                        used_urls.add(img_url)
                        print(f"Scene {scene_idx+1}: Downloaded backup anime illustration from {api_url}.")
                        return True
        except Exception as e:
            print(f"Backup anime API skipped: {e}")

    return False


def build_scene_motion_filter(dur, scene_idx, flip_variant=False):
    """
    Unified 30fps scale+crop camera motion across all 4 modes (eliminates zoompan
    frame/timebase glitches that caused black frames on Scene 2+).
    """
    mode = scene_idx % 4
    flip_prefix = "hflip," if flip_variant else ""

    if mode == 0:
        # 1. Slow diagonal drift: left-to-right + gentle upward tilt
        x_expr = f"20+90*(t/{dur:.3f})"
        y_expr = f"160-90*(t/{dur:.3f})"
        motion_vf = (
            f"{flip_prefix}scale=1210:2150:force_original_aspect_ratio=increase,"
            f"crop=1080:1920:x='{x_expr}':y='{y_expr}'"
        )
    elif mode == 1:
        # 2. Deep vertical crane rise + gentle horizontal pan (replaces zoompan)
        x_expr = f"40+60*(t/{dur:.3f})"
        y_expr = f"240-170*(t/{dur:.3f})"
        motion_vf = (
            f"{flip_prefix}scale=1260:2240:force_original_aspect_ratio=increase,"
            f"crop=1080:1920:x='{x_expr}':y='{y_expr}'"
        )
    elif mode == 2:
        # 3. Slow reverse pan: right-to-left + downward drift
        x_expr = f"110-90*(t/{dur:.3f})"
        y_expr = f"70+90*(t/{dur:.3f})"
        motion_vf = (
            f"{flip_prefix}scale=1210:2150:force_original_aspect_ratio=increase,"
            f"crop=1080:1920:x='{x_expr}':y='{y_expr}'"
        )
    else:
        # 4. Floating handheld camera breathing (sine/cosine wave drift)
        x_expr = "65+45*sin(2*PI*t*0.28)"
        y_expr = "115+55*cos(2*PI*t*0.22)"
        motion_vf = (
            f"{flip_prefix}scale=1210:2150:force_original_aspect_ratio=increase,"
            f"crop=1080:1920:x='{x_expr}':y='{y_expr}'"
        )

    return (
        f"{motion_vf},setsar=1,fps=30,"
        f"eq=brightness='0.025*sin(2*PI*t*0.55)':contrast=1.04:eval=frame"
    )


def generate_retro_anime_scenes(scene_timings):
    """
    Guarantees a visible, animated background image in EVERY single scene (1 through 7):
      - Paces Pollinations requests with a 3.5s delay and model rotation (flux -> turbo) to prevent HTTP 429 after Scene 1
      - Uses a 3-stage real anime art fallback if Pollinations ever times out
      - Never renders a black canvas: if offline, transforms a previous scene image with a new crop & angle
    """
    num_scenes = len(scene_timings)
    scene_video_files = []
    used_wallhaven_urls = set()
    used_image_hashes = set()
    valid_downloaded_images = []

    char_label, locked_char_anchor = select_video_wide_character(
        Config.OVERLAY_TEXT, Config.NICHE, Config.ROW_ID
    )
    video_character_seed = 50000 + (int(re.sub(r'\D', '', Config.ROW_ID) or "1") * 997)
    print(f"Mode 1 Video-Wide Character Lock: {char_label} (Seed={video_character_seed})")

    custom_scene_keywords = [k.strip() for k in Config.SEARCH_KEYWORD.split("|") if k.strip()]
    shuffled_envs = list(Config.SCENE_ENVIRONMENTS_POOL)
    random.Random(video_character_seed).shuffle(shuffled_envs)

    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    models_to_try = ["flux", "turbo", "flux"]

    for idx, (s_start, s_end, clause_text) in enumerate(scene_timings):
        dur = (s_end - s_start) + (Config.OUTRO_TAIL_DURATION if idx == num_scenes - 1 else 0.0)
        raw_scene_kw = custom_scene_keywords[idx] if idx < len(custom_scene_keywords) else custom_scene_keywords[-1]
        bg_only = raw_scene_kw.split("in scene:")[-1].strip() if "in scene
