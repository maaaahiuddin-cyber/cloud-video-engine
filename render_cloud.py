def strip_original_audio(input_path, output_path="raw_video.mp4"):
    """Removes 100% of the video's original sound (-an) so only script voiceover, piano, and ASMR play."""
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
    print(f"Stripped original audio (-an) cleanly from custom video: {os.path.basename(input_path)}")


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
    """Uses drive_video_url from Google Drive first, strips original audio (-an), and falls back to real camera footage."""
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
                "forest+trees+wind"
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
            print(f"Pixabay real footage search warning: {e}")

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=#0d1b2a:s=1080x1920:r=30:d={target_duration:.2f}",
        "-vf", "noise=alls=8:allf=t+u",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-an", "raw_video.mp4"
    ], check=True)
