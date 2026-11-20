def apply_emotional_phrasing(phrase, idx, total):
    """Adds subtle hidden punctuation for natural emotional rise-and-fall without changing on-screen text."""
    p = phrase.strip()
    if not p:
        return p
    if p[-1] in ".!?…":
        return p
    if idx == total - 1:
        return p + "..."      # Soft lingering exhale on the final line
    if idx % 2 == 0:
        return p + ","        # Gentle anticipation on lead-in lines
    return p + "."            # Warm emotional settle on resolving lines


def generate_kokoro_asmr_voiceover(text):
    """
    Generates a natural, emotional close-mic English whisper using Kokoro-82M
    (78% af_nicole breathy whisper + 22% af_heart emotional warmth) with dynamic pacing
    and a high-air ASMR mastering chain.
    """
    clean_spoken = re.sub(r'\s{2,}', ' ', (text or "").replace("…", ", ").replace("...", ", ")).strip()
    chunks = re.split(r'(?<=[.!?])\s+|\n+', clean_spoken.replace("\r", ""))
    phrases = [c.strip() for c in chunks if c.strip()]
    if not phrases:
        phrases = ["Back leg stretched out so neat."]

    line_windows = []
    raw_gen = False
    try:
        kokoro = Kokoro("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")
        try:
            v_whisper = kokoro.get_voice_style("af_nicole")
            v_emotion = kokoro.get_voice_style("af_heart")
            # Breathy whisper body + slightly warmer emotional closing line
            whisper_body_vec = (v_whisper * 0.78) + (v_emotion * 0.22)
            whisper_final_vec = (v_whisper * 0.70) + (v_emotion * 0.30)
            print("Using Emotional Whisper blend: 78% af_nicole + 22% af_heart (70/30 on closing line).")
        except Exception:
            whisper_body_vec = "af_nicole"
            whisper_final_vec = "af_nicole"

        audio_segments = []
        sample_rate = 24000
        cumulative_samples = 0
        total_phrases = len(phrases)

        for i, phrase in enumerate(phrases):
            is_first = (i == 0)
            is_final = (i == total_phrases - 1 and total_phrases > 1)

            # Natural human speed arc: soft intro -> gentle flow -> tender slow finish
            if is_final:
                phrase_speed = 0.74
                active_voice = whisper_final_vec
            elif is_first:
                phrase_speed = 0.80
                active_voice = whisper_body_vec
            else:
                phrase_speed = 0.82 if (i % 2 == 1) else 0.79
                active_voice = whisper_body_vec

            voiced_phrase = apply_emotional_phrasing(phrase, i, total_phrases)
            sent_start_sec = round(VO_START_DELAY + (cumulative_samples / float(sample_rate)), 2)

            samples, sample_rate = kokoro.create(
                voiced_phrase,
                voice=active_voice,
                speed=phrase_speed,
                lang="en-us"
            )

            # Apply a 20ms soft fade-in/out on each phrase to prevent hard vocal cuts
            samples = samples.astype(np.float32)
            fade_len = min(int(sample_rate * 0.02), len(samples) // 4)
            if fade_len > 1:
                samples[:fade_len] *= np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
                samples[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)

            audio_segments.append(samples)
            cumulative_samples += len(samples)
            sent_end_sec = round(VO_START_DELAY + (cumulative_samples / float(sample_rate)), 2)
            line_windows.append((sent_start_sec, sent_end_sec))
            print(f"Line {i+1} whisper window: {sent_start_sec:.2f}s -> {sent_end_sec:.2f}s (speed={phrase_speed}x) | '{voiced_phrase}'")

            if i < total_phrases - 1:
                # Longer breath pause before the final emotional line
                pause_sec = 1.35 if (i + 1 == total_phrases - 1) else (0.95 if i % 2 == 1 else 0.70)
                pause_samples = np.zeros(int(sample_rate * pause_sec), dtype=np.float32)
                audio_segments.append(pause_samples)
                cumulative_samples += len(pause_samples)

        # Short trailing pad so intimate room reflections decay cleanly
        audio_segments.append(np.zeros(int(sample_rate * 0.45), dtype=np.float32))

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
            communicate = edge_tts.Communicate(clean_spoken, voice="en-US-AriaNeural", rate="-14%", pitch="-3Hz")
            asyncio.run(communicate.save("voice_raw.wav"))
            raw_gen = True
        except Exception as e2:
            print(f"Fallback TTS failed: {e2}")

    if raw_gen:
        try:
            # Close-Mic Emotional Whisper Mastering Chain:
            # - 180Hz proximity warmth + 480Hz boxy-resonance cut (removes normal "talking" tone)
            # - 6.5kHz narrow de-esser + 10.5kHz breathy air boost (preserves delicate whisper texture)
            # - Gentle compression brings up quiet emotional breath tails
            # - 10ms binaural Haas delay + subtle room air + brickwall limiter (zero clipping)
            subprocess.run([
                "ffmpeg", "-y", "-i", "voice_raw.wav",
                "-af", (
                    "aformat=sample_rates=44100:channel_layouts=stereo,"
                    "highpass=f=80,"
                    "equalizer=f=180:width_type=o:w=1.2:g=2.5,"
                    "equalizer=f=480:width_type=o:w=1.0:g=-2.5,"
                    "equalizer=f=6500:width_type=o:w=0.6:g=-3.5,"
                    "equalizer=f=10500:width_type=o:w=1.2:g=3.0,"
                    "lowpass=f=13500,"
                    "acompressor=threshold=0.10:ratio=2.8:attack=15:release=180:makeup=1.5,"
                    "aecho=0.90:0.90:55|110:0.08|0.04,"
                    "adelay=0|10,"
                    "volume=1.5,"
                    "alimiter=limit=0.92,"
                    "afade=t=in:st=0:d=0.15"
                ),
                "-ar", "44100", "-ac", "2", "voice.mp3"
            ], check=True)
        except Exception as e_m:
            print(f"Whisper mastering fallback ({e_m}): using clean stereo boost.")
            subprocess.run([
                "ffmpeg", "-y", "-i", "voice_raw.wav",
                "-af", "volume=1.8", "-ar", "44100", "-ac", "2", "voice.mp3"
            ], check=True)
    else:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=10.0", "voice.mp3"
        ], check=True)

    if not line_windows:
        vo_dur = get_duration("voice.mp3")
        total_chars = max(sum(len(p) for p in phrases), 1)
        elapsed = 0.0
        for p in phrases:
            dur_p = (len(p) / total_chars) * vo_dur
            line_windows.append((round(VO_START_DELAY + elapsed, 2), round(VO_START_DELAY + elapsed + dur_p, 2)))
            elapsed += dur_p

    return line_windows
