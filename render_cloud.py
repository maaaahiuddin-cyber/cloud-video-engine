import os
import re
import sys
import glob
import json
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
        "kokoro-onnx", "soundfile", "numpy", "fonttools", "edge-tts", "gTTS"
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

row_id = str(payload.get("row_id", "1")).strip()
title = str(payload.get("title", "Dépaysement")).strip()
niche = str(payload.get("niche", "soul searching")).strip()
overlay_text = str(payload.get(
    "overlay_text",
    "There's a word in French… Dépaysement. It's the dizzy feeling of being somewhere unfamiliar, far from everything that tells you who you are."
)).strip()
search_keyword = str(payload.get("search_keyword", "lone traveler")).strip()
fallback_keyword = str(payload.get("fallback_keyword", "rain")).strip()
drive_video_url = str(payload.get("drive_video_url", "")).strip()
caption = str(payload.get(
    "caption",
    "Dépaysement | French\nThe dizzy feeling of being far from everything familiar. #wordsoftheworld #reels"
)).strip()

PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "").strip().strip('"').strip("'")
FREESOUND_API_KEY = os.environ.get("FREESOUND_API_KEY", "").strip().strip('"').strip("'")

PRIMARY_MAKE_WEBHOOK = "https://hook.us2.make.com/ga5opcigaf8fw3keq4zh5x5uy2r6gs24"
raw_webhook = os.environ.get("MAKE_WEBHOOK_URL", "").strip().strip('"').strip("'")
if raw_webhook.startswith("MAKE_WEBHOOK_URL="):
    raw_webhook = raw_webhook.split("MAKE_WEBHOOK_URL=", 1)[1].strip().strip('"').strip("'")
MAKE_WEBHOOK_URL = raw_webhook if raw_webhook.startswith("http") else PRIMARY_MAKE_WEBHOOK

VO_START_DELAY = 0.6          # Fast-Hook: Voiceover starts at 0.6 seconds (600ms)
EXTRA_TAIL_SECONDS = 4.0      # Extra 4.0 seconds of calm ASMR + Piano after voiceover finishes
AUDIO_FADE_DURATION = 1.50    # Smooth 1.50s audio fade-out so piano & rain end softly
VIDEO_FADE_DURATION = 0.35    # 0.35s micro-dissolve for seamless infinite-looping (+1.15s reading time)

# Strict filter to reject CGI, 3D renders, cartoons, AI, and abstract loops on Pixabay fallback
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

# 1. Smooth Acoustic Phonetic Map for Kokoro-82M Voiceover (unbroken single-breath reading)
SMOOTH_SPOKEN_MAP = {
    # French (17)
    "Dépaysement": "daypaizmahn",
    "Retrouvailles": "ruhtroovigh",
    "Sillage": "seeyahzh",
    "L'esprit de l'escalier": "lespree duh leskahlyay",
    "Coup de foudre": "koo duh foodruh",
    "Lâcher prise": "lahshay preez",
    "Tu me manques": "too muh mahnk",
    "Épanouissement": "aypahnweesmahn",
    "Douceur de vivre": "doosur duh veevruh",
    "Chagrin": "shahgran",
    "Ennui": "ahnwee",
    "Apaisement": "ahpaizmahn",
    "Tendresse": "tahndress",
    "Souvenir": "soovuhneer",
    "Âme sœur": "ahm sur",
    "Éphémère": "ayfehmair",
    "Au revoir": "oh ruhvwar",

    # Spanish (17)
    "Sobremesa": "sohbreh mehsah",
    "Duende": "dwenday",
    "Querencia": "kehrenseeah",
    "Anhelo": "ahnehloh",
    "Desvelo": "desvehloh",
    "Ojalá": "oh hahlah",
    "Madrugada": "mahdroogahdah",
    "Alma gemela": "ahlmah hehmehlah",
    "Corazonada": "kohrahsohnahdah",
    "Desahogo": "desah ohgoh",
    "Aguante": "ahgwahntay",
    "Amanecer": "ahmahnehser",
    "Echar de menos": "ehchar day mehnohs",
    "Ilusión": "eeloosyohn",
    "Despedida": "despehdeedah",
    "Soledad": "sohlehdahd",
    "Empezar de cero": "empehsar day sehroh",

    # Italian (17 + inline words)
    "Dolce far niente": "dohlchay far nyentay",
    "Sprezzatura": "spretsahtoorah",
    "Ti voglio bene": "tee vohlyoh behnay",
    "Struggimento": "stroodjeementoh",
    "Meraviglia": "mehrahveelyah",
    "Rimpianto": "reempyahntoh",
    "Cogli l'attimo": "kohlyee lahteemoh",
    "Pazienza": "pahtsyentsah",
    "Rinascita": "reenahsheetah",
    "Smarrimento": "zmahreementoh",
    "Insieme": "eensyehmay",
    "Fidarsi": "feedarsee",
    "Coraggio": "kohrahdjoh",
    "cuore": "kwohray",
    "Disgelo": "deezjehloh",
    "Speranza": "spehrahntsah",
    "Incanto": "eenkahntoh",
    "Ritrovarsi": "reetrohvarsee",

    # Japanese (17)
    "木漏れ日": "komorebi",
    "一期一会": "icheego icheeay",
    "侘び寂び": "wahbee sahbee",
    "物の哀れ": "mohno no ahwahray",
    "生き甲斐": "eekeegigh",
    "懐かしい": "nahtsookahshee",
    "七転び八起き": "nahnah kohrobee yah ohkee",
    "切ない": "setsoonigh",
    "面影": "ohmohkahgay",
    "以心伝心": "eesheen densheen",
    "初心": "shohsheen",
    "儚い": "hahkahnigh",
    "余韻": "yoheen",
    "絆": "keezoonah",
    "見守る": "meemahmohroo",
    "遠回り": "tohmahwahree",
    "有り難う": "ahreegahtoh",

    # Portuguese (16 + inline words)
    "Saudade": "sowdahjee",
    "Cafuné": "kahfooneh",
    "Desabafar": "dehzahbahfar",
    "Aconchego": "ahkohnshaygoh",
    "Companheiro": "kohmpahnyayroh",
    "com pão": "kohm pown",
    "Amor próprio": "ahmor prohpreeoh",
    "Desenrascanço": "dezenrahskahnsoh",
    "Mágoa": "mahgwah",
    "Desassossego": "dehzahsohsaygoh",
    "Sossego": "sohsaygoh",
    "Dengo": "dengoh",
    "Fôlego": "fohlehgoh",
    "Gratidão": "grahcheedown",
    "Perdoar": "perdohar",
    "Adeus": "ahdayoos",
    "a Deus": "ah dayoos",
    "Lembrança": "lembrahnsah",
    "lembranças": "lembrahnsahs",

    # Hindi (16)
    "इंतज़ार": "intehzaar",
    "बिछोह": "beechoh",
    "सुकून": "sookoon",
    "तलाश": "tuhlaash",
    "हौसला": "hawslah",
    "अपनापन": "upnahpun",
    "सब्र": "subruh",
    "ठहराव": "tehraav",
    "फ़िक्र": "fikruh",
    "अधूरा": "uhdhoorah",
    "संजोना": "sunjohnah",
    "मरहम": "murhum",
    "निभाना": "nibhaanah",
    "कशिश": "kushish",
    "तन्हाई": "tunhaaee",
    "उम्मीद": "oomeed"
}

# 2. Clean Hyphenated Pronunciation Guide for On-Screen Editorial Subtitle
DISPLAY_PRONUNCIATION_MAP = {
    # French (17)
    "Dépaysement": "day-paiz-mahn",
    "Retrouvailles": "ruh-troo-vigh",
    "Sillage": "see-yahzh",
    "L'esprit de l'escalier": "les-pree duh les-kal-yay",
    "Coup de foudre": "koo duh food-ruh",
    "Lâcher prise": "lah-shay preez",
    "Tu me manques": "too muh mahnk",
    "Épanouissement": "ay-pah-nwees-mahn",
    "Douceur de vivre": "doo-sur duh vee-vruh",
    "Chagrin": "shah-gran",
    "Ennui": "ahn-wee",
    "Apaisement": "ah-paiz-mahn",
    "Tendresse": "tahn-dress",
    "Souvenir": "soo-vuh-neer",
    "Âme sœur": "ahm sur",
    "Éphémère": "ay-feh-mair",
    "Au revoir": "oh ruh-vwar",

    # Spanish (17)
    "Sobremesa": "soh-breh-meh-sah",
    "Duende": "dwen-day",
    "Querencia": "keh-ren-see-ah",
    "Anhelo": "ah-neh-loh",
    "Desvelo": "des-veh-loh",
    "Ojalá": "oh-hah-lah",
    "Madrugada": "mah-droo-gah-dah",
    "Alma gemela": "ahl-mah heh-meh-lah",
    "Corazonada": "koh-rah-soh-nah-dah",
    "Desahogo": "des-ah-oh-goh",
    "Aguante": "ah-gwan-tay",
    "Amanecer": "ah-mah-neh-ser",
    "Echar de menos": "eh-char day meh-nohs",
    "Ilusión": "ee-loo-syohn",
    "Despedida": "des-peh-dee-dah",
    "Soledad": "soh-leh-dahd",
    "Empezar de cero": "em-peh-sar day seh-roh",

    # Italian (17)
    "Dolce far niente": "dohl-chay far nyen-tay",
    "Sprezzatura": "spret-sah-too-rah",
    "Ti voglio bene": "tee vohl-yoh beh-nay",
    "Struggimento": "strood-jee-men-toh",
    "Meraviglia": "meh-rah-veel-yah",
    "Rimpianto": "reem-pyahn-toh",
    "Cogli l'attimo": "kohl-yee laht-tee-moh",
    "Pazienza": "pah-tsyen-tsah",
    "Rinascita": "ree-nah-shee-tah",
    "Smarrimento": "zmar-ree-men-toh",
    "Insieme": "een-syeh-may",
    "Fidarsi": "fee-dar-see",
    "Coraggio": "koh-rahd-joh",
    "Disgelo": "deez-jeh-loh",
    "Speranza": "speh-rahn-tsah",
    "Incanto": "een-kahn-toh",
    "Ritrovarsi": "ree-troh-var-see",

    # Japanese (17)
    "木漏れ日": "komorebi",
    "一期一会": "ichigo ichie",
    "侘び寂び": "wabi-sabi",
    "物の哀れ": "mono no aware",
    "生き甲斐": "ikigai",
    "懐かしい": "natsukashii",
    "七転び八起き": "nana korobi ya oki",
    "切ない": "setsunai",
    "面影": "omokage",
    "以心伝心": "ishin denshin",
    "初心": "shoshin",
    "儚い": "hakanai",
    "余韻": "yoin",
    "絆": "kizuna",
    "見守る": "mimamoru",
    "遠回り": "toomawari",
    "有り難う": "arigatou",

    # Portuguese (16)
    "Saudade": "sow-dah-jee",
    "Cafuné": "kah-foo-neh",
    "Desabafar": "deh-zah-bah-far",
    "Aconchego": "ah-kohn-shay-goh",
    "Companheiro": "kohm-pah-nyay-roh",
    "Amor próprio": "ah-mor proh-pree-oh",
    "Desenrascanço": "deh-zen-rah-skahn-soh",
    "Mágoa": "mah-gwah",
    "Desassossego": "deh-zah-soh-say-goh",
    "Sossego": "soh-say-goh",
    "Dengo": "den-goh",
    "Fôlego": "foh-leh-goh",
    "Gratidão": "grah-chee-down",
    "Perdoar": "per-doh-ar",
    "Adeus": "ah-day-oos",
    "Lembrança": "lem-brahn-sah",

    # Hindi (16)
    "इंतज़ार": "intezaar",
    "बिछोह": "bichoh",
    "सुकून": "sukoon",
    "तलाश": "talaash",
    "हौसला": "hausla",
    "अपनापन": "apnapan",
    "सब्र": "sabr",
    "ठहराव": "thehrav",
    "फ़िक्र": "fikr",
    "अधूरा": "adhoora",
    "संजोना": "sanjona",
    "मरहम": "murhum",
    "निभाना": "nibhana",
    "कशिश": "kashish",
    "तन्हाई": "tanhai",
    "उम्मीद": "ummeed"
}


def ensure_assets():
    """Downloads Kokoro-82M ONNX models, Poetic Serif Font, and builds Merged Hindi+Latin Serif Font."""
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
            "https://raw.githubusercontent.com/google/fonts/main/ofl/cormorantgaramond/CormorantGaramond%5Bwght%5D.ttf"
        ]
        for f_url in font_urls:
            try:
                r = requests.get(f_url, timeout=25)
                if r.status_code == 200 and len(r.content) > 40_000:
                    with open(font_path, "wb") as f:
                        f.write(r.content)
                    print(f"Downloaded poetic serif font successfully from {f_url}")
                    break
            except Exception as e:
                print(f"Font attempt skipped: {e}")

    if not os.path.exists("MergedHindiSerif.ttf"):
        try:
            from fontTools.merge import Merger
            latin_base = "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf"
            dev_base = "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Regular.ttf"
            if os.path.exists(latin_base) and os.path.exists(dev_base):
                merger = Merger()
                merged = merger.merge([latin_base, dev_base])
                merged.save("MergedHindiSerif.ttf")
                print("Created MergedHindiSerif.ttf (Latin + Devanagari) successfully.")
        except Exception as e:
            print(f"Merged Hindi font build skipped: {e}")


def get_font_for_text(line_text):
    """Selects the right serif font per line for Latin, Japanese Kanji/Kana, or Hindi Devanagari."""
    if re.search(r'[\u3040-\u30ff\u4e00-\u9fff]', line_text):
        cjk_candidates = [
            "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"
        ]
        for p in cjk_candidates:
            if os.path.exists(p):
                return p

    if re.search(r'[\u0900-\u097f]', line_text):
        if os.path.exists("MergedHindiSerif.ttf"):
            return "MergedHindiSerif.ttf"
        dev_path = "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Regular.ttf"
        if os.path.exists(dev_path):
            return dev_path

    latin_candidates = [
        "PoetrySerif.ttf",
        "/usr/share/fonts/truetype/ebgaramond/EBGaramond12-Regular.ttf",
        "/usr/share/fonts/opentype/ebgaramond/EBGaramond12-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    ]
    for p in latin_candidates:
        if os.path.exists(p) and os.path.getsize(p) > 20_000:
            return p
    return "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"


def build_editorial_subtitle(title_str, overlay_str, caption_str):
    """Builds the editorial '[ Language  •  pronunciation ]' sub-header shown directly below the Yellow Title."""
    lang_label = ""
    first_line = caption_str.splitlines()[0] if caption_str else ""
    if "|" in first_line:
        lang_label = first_line.split("|")[-1].strip()

    if not lang_label:
        for l_name in ["French", "Spanish", "Italian", "Japanese", "Portuguese", "Hindi"]:
            if l_name.lower() in f"{overlay_str} {caption_str}".lower():
                lang_label = l_name
                break

    clean_t = (title_str or "").strip()
    pron = DISPLAY_PRONUNCIATION_MAP.get(clean_t, "")
    if not pron:
        m = re.search(r'\(([^)]+)\)', first_line)
        if m:
            pron = m.group(1).strip()

    if lang_label and pron:
        return f"[ {lang_label}  •  {pron} ]"
    elif lang_label:
        return f"[ {lang_label} ]"
    return ""


def prepare_poetic_lines(title_text, body_text, caption_text, sentence_start_times=None):
    """
    Formats:
      1) Yellow Title (#FFD700, fontsize=58) locked at 100% opacity on Frame 0 (t=0.00s) for IG/FB Grid Cover
      2) Editorial Sub-Header '[ Language • Pronunciation ]' (#E6C687, fontsize=32) locked at 100% opacity on Frame 0 (t=0.00s)
      3) Overlay_Text stanzas (#f5f5f3, fontsize=45) fade in line-by-line synced to each spoken sentence (starting at t=0.60s)
    """
    items = []
    current_y = 0
    file_idx = 0

    clean_title = (title_text or "").strip()
    if clean_title:
        title_wrapped = textwrap.wrap(clean_title, width=22) or [clean_title]
        title_line_height = 70

        for t_line in title_wrapped:
            fname = f"quote_line_{file_idx}.txt"
            with open(fname, "w", encoding="utf-8", newline="\n") as f:
                f.write(t_line)
            items.append({
                "fname": fname,
                "rel_y": current_y,
                "fontsize": 58,
                "fontcolor": "#FFD700",
                "fontfile": get_font_for_text(t_line),
                "start_t": 0.00,
                "instant_header": True
            })
            current_y += title_line_height
            file_idx += 1

        subtitle_str = build_editorial_subtitle(title_text, body_text, caption_text)
        if subtitle_str:
            fname = f"quote_line_{file_idx}.txt"
            with open(fname, "w", encoding="utf-8", newline="\n") as f:
                f.write(subtitle_str)
            items.append({
                "fname": fname,
                "rel_y": current_y + 4,
                "fontsize": 32,
                "fontcolor": "#E6C687",
                "fontfile": get_font_for_text(subtitle_str),
                "start_t": 0.00,
                "instant_header": True
            })
            current_y += 44 + 42
            file_idx += 1
        else:
            current_y += 50

    cleaned = (body_text or "").replace("\r\n", "\n").replace("\u2028", "\n").replace("\u2029", "\n").strip()
    if not cleaned:
        cleaned = "Peace comes from within.\nDo not seek it without."

    raw_lines = [l.strip() for l in cleaned.split("\n") if l.strip()]
    if len(raw_lines) == 1 and ". " in cleaned:
        stanzas = [s.strip() for s in re.split(r'(?<=[.!?])\s+', cleaned) if s.strip()]
    else:
        stanzas = [s.strip() for s in re.split(r'\n\s*\n', cleaned) if s.strip()]

    line_height = 58
    stanza_gap = 34

    for s_idx, stanza in enumerate(stanzas):
        if sentence_start_times and s_idx < len(sentence_start_times):
            stanza_base_t = sentence_start_times[s_idx]
        elif sentence_start_times:
            stanza_base_t = sentence_start_times[-1] + ((s_idx - len(sentence_start_times) + 1) * 3.0)
        else:
            stanza_base_t = VO_START_DELAY + (s_idx * 3.2)

        line_in_stanza = 0
        for raw_line in stanza.split("\n"):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            wrapped = textwrap.wrap(raw_line, width=30)
            for w_line in wrapped:
                fname = f"quote_line_{file_idx}.txt"
                with open(fname, "w", encoding="utf-8", newline="\n") as f:
                    f.write(w_line)
                items.append({
                    "fname": fname,
                    "rel_y": current_y,
                    "fontsize": 45,
                    "fontcolor": "#f5f5f3",
                    "fontfile": get_font_for_text(w_line),
                    "start_t": round(stanza_base_t + (line_in_stanza * 0.28), 2),
                    "instant_header": False
                })
                current_y += line_height
                file_idx += 1
                line_in_stanza += 1

        if s_idx < len(stanzas) - 1:
            current_y += stanza_gap

    total_height = max(current_y - line_height, 60)
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


def prepare_spoken_script(title_str, overlay_str, caption_str):
    """Replaces foreign words in the spoken voiceover script ONLY while keeping visual text intact."""
    spoken = overlay_str.replace("…", ", ").replace("...", ", ")

    for word, phonetic in sorted(SMOOTH_SPOKEN_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if word in spoken:
            spoken = spoken.replace(word, phonetic)

    clean_title = (title_str or "").strip()
    if clean_title and clean_title in spoken and clean_title not in SMOOTH_SPOKEN_MAP:
        first_line = caption_str.splitlines()[0] if caption_str else ""
        m = re.search(r'\(([^)]+)\)', first_line)
        if m:
            spoken = spoken.replace(clean_title, m.group(1).strip())

    return re.sub(r'\s{2,}', ' ', spoken).strip()


def generate_kokoro_asmr_voiceover(title_word, text, caption_text):
    """
    Generates the 55% af_nicole + 45% af_heart voiceover AND returns the exact
    video timestamp (in seconds) where each sentence begins speaking.
    """
    spoken_text = prepare_spoken_script(title_word, text, caption_text)
    chunks = re.split(r'(?<=[.!?])\s+|\n+', spoken_text.replace("\r", ""))
    phrases = [c.strip() for c in chunks if c.strip()]
    if not phrases:
        phrases = ["Peace comes from within."]

    sentence_start_times = []
    raw_gen = False
    try:
        kokoro = Kokoro("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")
        try:
            v1 = kokoro.get_voice_style("af_nicole")
            v2 = kokoro.get_voice_style("af_heart")
            target_voice = (v1 * 0.55) + (v2 * 0.45)
            print("Using custom 55% af_nicole + 45% af_heart blended ASMR voice vector.")
        except Exception:
            target_voice = "af_nicole"

        audio_segments = []
        sample_rate = 24000
        cumulative_samples = 0
        total_phrases = len(phrases)

        for i, phrase in enumerate(phrases):
            is_final_sentence = (i == total_phrases - 1 and total_phrases > 1)
            phrase_speed = 0.79 if is_final_sentence else 0.83

            sent_start_sec = round(VO_START_DELAY + (cumulative_samples / float(sample_rate)), 2)
            sentence_start_times.append(sent_start_sec)
            print(f"Synthesizing sentence {i+1}/{total_phrases} (starts at {sent_start_sec:.2f}s, speed={phrase_speed}x): {phrase}")

            samples, sample_rate = kokoro.create(
                phrase,
                voice=target_voice,
                speed=phrase_speed,
                lang="en-us"
            )
            audio_segments.append(samples)
            cumulative_samples += len(samples)

            if i < total_phrases - 1:
                next_is_final = (i + 1 == total_phrases - 1)
                pause_sec = 1.45 if next_is_final else 1.10
                pause_samples = np.zeros(int(sample_rate * pause_sec), dtype=np.float32)
                audio_segments.append(pause_samples)
                cumulative_samples += len(pause_samples)

        reverb_tail_pad = np.zeros(int(sample_rate * 0.80), dtype=np.float32)
        audio_segments.append(reverb_tail_pad)

        full_audio = np.concatenate(audio_segments)
        sf.write("voice_raw.wav", full_audio, sample_rate)

        if os.path.exists("voice_raw.wav") and os.path.getsize("voice_raw.wav") > 1000:
            print("Generated blended Kokoro-82M ASMR voiceover successfully!")
            raw_gen = True
    except Exception as e:
        print(f"Kokoro-82M error ({e}), falling back to Edge-TTS...")

    if not raw_gen:
        try:
            import edge_tts
            import asyncio
            communicate = edge_tts.Communicate(spoken_text, voice="en-GB-RyanNeural", rate="-12%", pitch="-2Hz")
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
                    "aecho=0.88:0.90:95|190:0.12|0.07,"
                    "adelay=0|12,"
                    "afade=t=in:st=0:d=0.15,"
                    "volume=2.1"
                ),
                "-ar", "44100", "-ac", "2", "voice.mp3"
            ], check=True)
        except Exception as e:
            print(f"Mastering fallback: {e}")
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


def detect_niche_keyword():
    niche_lower = niche.lower().strip()
    if niche_lower in NICHE_AUDIO_MAP:
        return niche_lower
    combined = f"{niche} {search_keyword} {fallback_keyword}".lower()
    for key in NICHE_AUDIO_MAP:
        if key in combined:
            return key
    return "rain"


def is_real_camera_footage(hit):
    """Enforces real camera footage on Pixabay fallback by filtering out CGI, 3D, animation, and AI tags."""
    hit_type = str(hit.get("type", "")).lower()
    if "animation" in hit_type or "illustration" in hit_type:
        return False

    tags_str = str(hit.get("tags", "")).lower()
    tag_tokens = {t.strip() for t in tags_str.split(",") if t.strip()}
    for banned in BANNED_VISUAL_TAGS:
        if banned in tag_tokens or re.search(rf'\b{re.escape(banned)}\b', tags_str):
            return False
    return True


def strip_original_audio(input_path, output_path="raw_video.mp4"):
    """
    Removes 100% of the video's original sound (-an) so ONLY the script's
    Kokoro-82M voiceover, piano.mp3, and 3D binaural ASMR audio play.
    """
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
    print(f"Stripped original audio (-an) cleanly from video: {os.path.basename(input_path)}")


def download_from_google_drive(url, dest_path="drive_raw.mp4"):
    """Downloads a shared Google Drive file, handling large-file confirmation tokens if returned."""
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


def download_visual_background(target_duration):
    """
    Downloads your Google Drive background video first, strips its original sound (-an),
    and falls back to real Pixabay camera footage (or a silent dark canvas) if needed.
    """
    if drive_video_url and drive_video_url.startswith("http"):
        try:
            print(f"Downloading Google Drive background video: {drive_video_url}")
            if download_from_google_drive(drive_video_url, "drive_raw.mp4"):
                strip_original_audio("drive_raw.mp4", "raw_video.mp4")
                return
        except Exception as e_drv:
            print(f"Google Drive download failed ({e_drv}), falling back to real camera footage...")

    if PIXABAY_API_KEY:
        try:
            real_footage_queries = [
                urllib.parse.quote(search_keyword),
                urllib.parse.quote(fallback_keyword),
                "calm+nature+rain",
                "rain+drops+window",
                "ocean+waves+beach",
                "forest+trees+wind",
                "river+stream+water",
                "sunset+clouds+sky"
            ]

            for orientation_param in ["&orientation=vertical", ""]:
                for q in real_footage_queries:
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
                        random.shuffle(real_hits)
                        for chosen in real_hits[:5]:
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
                                    print(f"Downloaded verified REAL camera footage from Pixabay (query='{q}').")
                                    return
        except Exception as e:
            print(f"Pixabay real footage search warning: {e}")

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=#0d1b2a:s=1080x1920:r=30:d={target_duration:.2f}",
        "-vf", "noise=alls=8:allf=t+u",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-an", "raw_video.mp4"
    ], check=True)


def fetch_asmr_audio(matched_key, target_duration):
    if FREESOUND_API_KEY:
        try:
            q_str = NICHE_AUDIO_MAP.get(matched_key, f"{search_keyword} ambient")
            query = urllib.parse.quote(q_str)
            url = (
                f"https://freesound.org/apiv2/search/text/"
                f"?query={query}&filter=duration:[15 TO 180]&fields=id,name,previews"
                f"&page_size=8&token={FREESOUND_API_KEY}"
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
    """Automatically detects your uploaded custom piano.mp3 before falling back to Freesound."""
    for filename in ["piano.mp3", "bgm.mp3", "audio/piano.mp3", "audio/default.mp3"]:
        if os.path.exists(filename) and os.path.getsize(filename) > 10_000:
            print(f"Using custom uploaded track: {filename}")
            return filename

    excluded = {"asmr.mp3", "voice.mp3", "voice_raw.mp3", "cloud_piano.mp3", "synth_piano.mp3", "pause_gap.mp3"}
    custom_candidates = []
    for pattern in ["*.mp3", "music/*.mp3", "audio/*.mp3"]:
        for f in glob.glob(pattern):
            if os.path.basename(f) not in excluded and os.path.getsize(f) > 10_000:
                custom_candidates.append(f)
    if custom_candidates:
        chosen_custom = random.choice(custom_candidates)
        print(f"Using custom uploaded music track: {chosen_custom}")
        return chosen_custom

    if FREESOUND_API_KEY:
        try:
            query = urllib.parse.quote("soft relaxing piano calm ambient instrumental")
            url = (
                f"https://freesound.org/apiv2/search/text/"
                f"?query={query}&filter=duration:[20 TO 240]&fields=id,name,previews"
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
            print(f"Freesound Piano fallback triggered: {e}")

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
            "lowpass=f=650,aecho=0.8:0.88:120|240:0.4|0.3,volume=0.18"
        ),
        "synth_piano.mp3"
    ], check=True)
    return "synth_piano.mp3"


def render_ffmpeg(piano_file, vo_duration, total_duration, sentence_start_times):
    raw_vid_duration = get_duration("raw_video.mp4")
    if raw_vid_duration < total_duration and raw_vid_duration > 0.5:
        pts_multiplier = (total_duration + 0.5) / raw_vid_duration
        print(f"Video is {raw_vid_duration:.2f}s (< {total_duration:.2f}s). Stretching speed (setpts={pts_multiplier:.4f}*PTS).")
    else:
        pts_multiplier = 1.0

    piano_dur = get_duration(piano_file)
    max_offset = max(0.0, piano_dur - total_duration - 2.0)
    piano_start = random.uniform(0.0, max_offset) if max_offset > 4.0 else 0.0

    line_items, total_height = prepare_poetic_lines(title, overlay_text, caption, sentence_start_times)

    audio_fade_start = max(total_duration - AUDIO_FADE_DURATION, total_duration - 2.0)
    video_fade_start = max(total_duration - VIDEO_FADE_DURATION, 1.0)
    text_fade_start = max(video_fade_start - 0.30, 4.0)
    text_fade_end = text_fade_start + 0.35

    base_y = int((1920 - total_height) / 2 - 70)
    bar_y = max(base_y - 6, 120)
    bar_h = total_height + 56

    drawtext_filters = []
    for item in line_items:
        start_t = item["start_t"]
        if item.get("instant_header", False):
            line_alpha = (
                f"if(lt(t,{text_fade_start:.2f}),1,"
                f"if(lt(t,{text_fade_end:.2f}),({text_fade_end:.2f}-t)/0.35,0))"
            )
        else:
            fade_in_end = start_t + 0.70
            line_alpha = (
                f"if(lt(t,{start_t:.2f}),0,"
                f"if(lt(t,{fade_in_end:.2f}),(t-{start_t:.2f})/0.70,"
                f"if(lt(t,{text_fade_start:.2f}),1,"
                f"if(lt(t,{text_fade_end:.2f}),({text_fade_end:.2f}-t)/0.35,0))))"
            )
        y_pos = base_y + item["rel_y"]
        drawtext_filters.append(
            f"drawtext=fontfile={item['fontfile']}:"
            f"textfile={item['fname']}:"
            f"fontcolor={item['fontcolor']}:"
            f"fontsize={item['fontsize']}:"
            f"x=76:"
            f"y={y_pos}:"
            f"shadowcolor=black@0.85:shadowx=2:shadowy=3:"
            f"enable='gte(t,{start_t:.2f})':"
            f"alpha='{line_alpha}'"
        )

    drawtext_filters_str = ",".join(drawtext_filters)
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
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,setsar=1,fps=30,"
        f"eq=brightness=-0.05:contrast=1.08:saturation=0.82,"
        f"colorbalance=rs=-0.02:bs=0.03:rh=0.03:gh=0.01:bh=-0.02,"
        f"noise=alls=4:allf=t+u,"
        f"vignette=PI/4,"
        f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.46:t=fill,"
        f"drawbox=x=50:y={bar_y}:w=3:h={bar_h}:color=#FFD700@0.65:t=fill:enable='between(t,0.00,{text_fade_end:.2f})',"
        f"{drawtext_filters_str},"
        f"fade=t=out:st={video_fade_start:.2f}:d={VIDEO_FADE_DURATION}[v]"
    )

    a_filter = (
        f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,"
        f"lowpass=f=3000,volume='{piano_vol_expr}':eval=frame[piano];"
        f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo,"
        f"apulsator=mode=sine:hz=0.08:amount=0.25,"
        f"volume='{asmr_vol_expr}':eval=frame[asmr];"
        f"[3:a]aformat=sample_rates=44100:channel_layouts=stereo,"
        f"adelay={adelay_ms}|{adelay_ms},apad=whole_dur={total_duration:.2f}[voice];"
        f"[piano][asmr][voice]amix=inputs=3:duration=first:dropout_transition=0:normalize=0,"
        f"afade=t=in:st=0:d=0.6,"
        f"afade=t=out:st={audio_fade_start:.2f}:d={AUDIO_FADE_DURATION}[a]"
    )

    filter_complex = f"{v_filter};{a_filter}"
    subprocess.run([
        "ffmpeg", "-y",
        "-i", "raw_video.mp4",
        "-ss", f"{piano_start:.2f}", "-stream_loop", "-1", "-i", piano_file,
        "-stream_loop", "-1", "-i", "asmr.mp3",
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
    """Confirms the MP4 link is publicly downloadable over HTTPS before sending to Make.com."""
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
    """Uses GITHUB_TOKEN to host final_output.mp4 directly on GitHub Releases CDN."""
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
            print(f"GitHub Release creation warning: {r_create.status_code} {r_create.text}")
            return ""
        release_data = r_create.json()

    release_id = release_data.get("id")
    asset_name = f"video_row_{row_id}_{random.randint(1000, 9999)}.mp4"

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
            print(f"Uploaded to GitHub Releases CDN successfully: {dl_url}")
            return dl_url
    else:
        print(f"GitHub Release asset upload warning: {r_up.status_code} {r_up.text}")
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
                print(f"Uploaded to Cloudinary successfully: {video_url}")
                return video_url
        except Exception as e:
            print(f"Cloudinary upload skipped ({e}). Trying GitHub Release CDN...")

    try:
        gh_url = upload_to_github_release("final_output.mp4")
        if gh_url:
            return gh_url
    except Exception as e_gh:
        print(f"GitHub Release upload skipped: {e_gh}")

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
                    print(f"Uploaded to tmpfiles.org (HTTPS) successfully: {direct_url}")
                    return direct_url
    except Exception as e_tmp:
        print(f"tmpfiles backup failed: {e_tmp}")

    try:
        with open("final_output.mp4", "rb") as f:
            r = requests.post(
                "https://0x0.st",
                files={"file": ("final_output.mp4", f, "video/mp4")},
                headers={"User-Agent": "CloudVideoRenderer/1.0"},
                timeout=60
            )
        if r.status_code == 200 and r.text.strip().startswith("https://"):
            url = r.text.strip()
            if verify_url_accessible(url):
                print(f"Uploaded to 0x0.st successfully: {url}")
                return url
    except Exception as e_0x0:
        print(f"0x0.st backup failed: {e_0x0}")

    try:
        with open("final_output.mp4", "rb") as f:
            r = requests.post(
                "https://litterbox.catbox.moe/resources/internals/api.php",
                data={"reqtype": "fileupload", "time": "72h"},
                files={"fileToUpload": ("final_output.mp4", f, "video/mp4")},
                timeout=60
            )
        if r.status_code == 200 and r.text.strip().startswith("https://"):
            url = r.text.strip()
            print(f"Uploaded to Litterbox successfully: {url}")
            return url
    except Exception as e_lit:
        print(f"Litterbox backup failed: {e_lit}")

    return ""


def main():
    ensure_assets()

    # Step 1: Generate Voiceover FIRST and capture exact start timestamp of each sentence
    sentence_start_times = generate_kokoro_asmr_voiceover(title, overlay_text, caption)
    vo_duration = get_duration("voice.mp3")

    # Step 2: Calculate Dynamic Total Video Duration = 0.6s fast-hook intro + full voiceover + 4.0s extra tail
    total_duration = max(12.0, round(VO_START_DELAY + vo_duration + EXTRA_TAIL_SECONDS, 2))
    print(f"Voiceover length: {vo_duration:.2f}s -> Dynamic Total Video Duration set to: {total_duration:.2f}s (0.6s intro + 4.0s tail)")

    # Step 3: Fetch Google Drive background video (strips original sound -an) & script audio tracks
    matched_niche = detect_niche_keyword()
    download_visual_background(total_duration)
    fetch_asmr_audio(matched_niche, total_duration)
    piano_file = fetch_relaxing_piano(total_duration)

    # Step 4: Render final video with 0.35s loop micro-dissolve & 3D binaural ASMR drift
    render_ffmpeg(piano_file, vo_duration, total_duration, sentence_start_times)
    video_url = upload_video_with_fallback()
    print(f"Final Hosted Video URL: {video_url}")

    if not video_url or not video_url.startswith("http"):
        raise RuntimeError("Video upload failed across all hosts; no valid video_url to send to Make.com!")

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
        resp = requests.post(
            wh_url,
            json=webhook_payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        print(f"Sent webhook to {wh_url} -> Status: {resp.status_code} | Response: {resp.text}")


if __name__ == "__main__":
    main()
