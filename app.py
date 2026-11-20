import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import streamlit as st
import subprocess
import tempfile
import shutil
import re
import gc
import wave
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

st.set_page_config(page_title="CLIPSHORT AI", page_icon="🎬", layout="wide")
st.markdown("<h1>🎬 CLIPSHORT AI</h1><p>YouTube Only + Cobalt Server | Unlimited Highlights | Trim + Effects | No Subtitles</p>", unsafe_allow_html=True)

if "preview_done" not in st.session_state:
    st.session_state.preview_done = False
if "preview_bytes" not in st.session_state:
    st.session_state.preview_bytes = None

def run_cmd(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[-1500:])
    return r.stdout.strip()

def check_ffmpeg():
    return shutil.which("ffmpeg") is not None

def get_duration(path):
    v = run_cmd(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(v)

def has_audio(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return bool(r.stdout.strip())

# ===== COBALT SERVER - YOUTUBE DOWNLOAD FIX FOR STREAMLIT =====
# Streamlit blocks yt-dlp directly. Cobalt is a separate server that downloads YouTube for us.
# Flow: Streamlit -> Cobalt Server -> YouTube -> Returns Direct MP4 Link -> Streamlit Downloads It
COBALT_SERVERS = [
    "https://api.cobalt.tools/api/json",
    "https://cobalt.canine.tools/api/json",
    "https://cobalt.themarcus.top/api/json",
]

def download_via_cobalt(youtube_url, folder):
    import requests
    last_error = ""
    for cobalt_url in COBALT_SERVERS:
        try:
            # Step 1: Ask Cobalt for direct download link
            payload = {
                "url": youtube_url,
                "vCodec": "h264",
                "vQuality": "720",
                "aFormat": "mp3",
                "isAudioOnly": False,
                "filenameStyle": "basic",
                "duplicate": "never"
            }
            headers = {"Accept": "application/json", "Content-Type": "application/json"}
            r = requests.post(cobalt_url, json=payload, headers=headers, timeout=60)
            if r.status_code != 200:
                last_error = f"Cobalt {cobalt_url} returned {r.status_code}"
                continue
            data = r.json()
            # Cobalt can return: status=redirect / tunnel / picker
            download_url = data.get("url")
            if not download_url:
                # Picker = multiple files, take first video
                picker = data.get("picker", [])
                if picker:
                    download_url = picker[0].get("url")
            if not download_url:
                last_error = f"Cobalt no URL: {str(data)[:300]}"
                continue
            # Step 2: Download the MP4 from Cobalt's direct link
            target = folder / "cobalt_video.mp4"
            dl = requests.get(download_url, stream=True, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
            with open(target, "wb") as f:
                for chunk in dl.iter_content(chunk_size=1024 * 1024 * 2):
                    if chunk:
                        f.write(chunk)
            if target.exists() and target.stat().st_size > 10000:
                return target
            last_error = "Cobalt file empty"
        except Exception as e:
            last_error = str(e)[:400]
            continue
    raise RuntimeError("Cobalt failed: " + last_error)

def download_youtube_yt_dlp(url, folder):
    # Fallback 2: yt-dlp direct (works on local PC, sometimes blocked on Streamlit)
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp not installed")
    attempts = [
        "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]/best",
        "best[height<=720][ext=mp4]/best[height<=720]/best",
        "best",
    ]
    last_error = ""
    for fmt in attempts:
        try:
            for old in folder.glob("youtube_video.*"):
                try:
                    old.unlink()
                except Exception:
                    pass
            opts = {
                "format": fmt,
                "merge_output_format": "mp4",
                "outtmpl": str(folder / "youtube_video.%(ext)s"),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "retries": 3,
                "socket_timeout": 30,
                "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            files = [f for f in folder.glob("youtube_video.*") if f.suffix.lower() in [".mp4", ".webm", ".mkv", ".mov", ".m4v"]]
            if files and files[0].stat().st_size > 10000:
                return files[0]
        except Exception as e:
            last_error = str(e)[-400:]
            continue
    raise RuntimeError("yt-dlp failed: " + last_error)

def download_youtube(url, folder):
    url = url.strip()
    # Priority 1: Cobalt (Best for Streamlit)
    try:
        return download_via_cobalt(url, folder)
    except Exception as cobalt_err:
        # Priority 2: yt-dlp fallback
        try:
            return download_youtube_yt_dlp(url, folder)
        except Exception as ytdlp_err:
            raise RuntimeError(f"Cobalt failed: {str(cobalt_err)[:300]} | yt-dlp failed: {str(ytdlp_err)[:300]} | Try another video or try again in 1 min.")

def get_drive_id(url):
    p = urlparse(url.strip())
    m = re.search(r"/file/d/([A-Za-z0-9_-]+)", p.path)
    if m:
        return m.group(1)
    q = parse_qs(p.query)
    if q.get("id"):
        return q["id"][0]
    raise ValueError("Invalid Drive link")

def download_drive(url, folder):
    import requests
    fid = get_drive_id(url)
    target = folder / "drive_video.mp4"
    dl_url = "https://drive.google.com/uc?export=download&id=" + fid + "&confirm=t"
    s = requests.Session()
    r = s.get(dl_url, stream=True, timeout=120)
    with open(target, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024 * 2):
            if chunk:
                f.write(chunk)
    if not target.exists() or target.stat().st_size < 10000:
        raise RuntimeError("Drive failed. Set Anyone with link to Viewer")
    return target

# ===== UNLIMITED HIGHLIGHTS - NO 10 MIN LIMIT =====
# Works for 1 min, 10 min, 1 hour, 3 hours - NO LIMIT
# Uses chunk reading so long videos do not crash RAM
def get_highlight_scores(video_path, total):
    try:
        import numpy as np
        audio_path = Path(str(video_path) + "_audio.wav")
        subprocess.run(["ffmpeg", "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio_path)], capture_output=True)
        if not audio_path.exists() or audio_path.stat().st_size < 1000:
            return None
        # Total seconds - UNLIMITED, no cap
        total_sec = int(total)
        scores = [0.0] * total_sec
        with wave.open(str(audio_path), "rb") as wf:
            rate = wf.getframerate()
            # Read in 10-sec chunks to save RAM for long videos
            chunk_frames = rate * 10
            sec_index = 0
            while True:
                data = wf.readframes(chunk_frames)
                if not data:
                    break
                audio = np.frombuffer(data, dtype=np.int16).astype(float) / 32768.0
                # Split 10-sec chunk into 1-sec scores
                for s in range(10):
                    start = s * rate
                    end = min((s + 1) * rate, len(audio))
                    if end <= start:
                        break
                    if sec_index >= total_sec:
                        break
                    chunk = audio[start:end]
                    rms = float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) > 0 else 0.0
                    peak = float(np.max(np.abs(chunk))) if len(chunk) > 0 else 0.0
                    scores[sec_index] = rms * 0.7 + peak * 0.3
                    sec_index += 1
                if sec_index >= total_sec:
                    break
        # Smooth - avoid single spike
        smoothed = []
        for i in range(len(scores)):
            vals = scores[max(0, i - 1):min(len(scores), i + 2)]
            smoothed.append(sum(vals) / len(vals) if vals else 0.0)
        try:
            audio_path.unlink()
        except Exception:
            pass
        return smoothed
    except Exception as e:
        print("Highlight failed", e)
        return None

def choose_highlight_starts(scores, total, length, count, trim_start, trim_end):
    if scores is None:
        return None
    # UNLIMITED: scan full trim range, any length
    cands = []
    start = trim_start
    step = 2.0
    while start + length <= trim_end:
        end = start + length
        s_idx = int(start)
        e_idx = int(min(end, len(scores)))
        score = sum(scores[s_idx:e_idx]) if e_idx > s_idx else 0
        if s_idx < len(scores) and e_idx > s_idx:
            peak = max(scores[s_idx:e_idx])
            score += peak * 2.0
        cands.append((score, start))
        start += step
    cands.sort(key=lambda x: x[0], reverse=True)
    sel = []
    for _, s in cands:
        ok = True
        for p in sel:
            if abs(s - p) < length * 0.65:
                ok = False
        if ok:
            sel.append(s)
        if len(sel) >= count:
            break
    if not sel:
        sel = [trim_start]
    return sorted(sel)

def choose_normal_starts(total, length, count, trim_start, trim_end):
    avail = trim_end - trim_start
    if avail <= length:
        return [trim_start]
    # Try NON-OVERLAPPING first - no duplicate clips
    # Example: 90 sec video, 30 sec clips -> max 3 non-overlapping clips
    max_non_overlap = int(avail // length)
    if count <= max_non_overlap:
        # Evenly spread non-overlapping: 0, 30, 60 for 90 sec
        starts = []
        # Spread to cover full video, not just start
        if count == 1:
            starts = [trim_start + (avail - length) / 2]
        else:
            gap = (avail - (count * length)) / (count - 1) if count > 1 else 0
            pos = trim_start
            for i in range(count):
                starts.append(pos)
                pos += length + gap
        return starts
    # If user asks for MORE clips than non-overlap allows, use evenly spaced overlapping
    if count == 1:
        return [trim_start + avail / 2 - length / 2]
    step = (avail - length) / (count - 1) if count > 1 else 0
    starts = []
    for i in range(count):
        starts.append(trim_start + i * step)
    return starts

RATIOS = {"9:16 - Shorts / Reels": (1080, 1920), "16:9 - YouTube": (1920, 1080), "1:1 - Instagram Post": (1080, 1080), "4:5 - Instagram Portrait": (1080, 1350)}
RESOLUTIONS = {"480p - Fast": 480, "720p - HD": 720, "1080p - Full HD": 1080}

def get_output_size(ratio_label, res_label):
    base_w, base_h = RATIOS[ratio_label]
    target = RESOLUTIONS[res_label]
    if base_w <= base_h:
        w = target
        h = int(base_h * (target / base_w))
    else:
        h = target
        w = int(base_w * (target / base_h))
    w = w - (w % 2)
    h = h - (h % 2)
    return w, h

def build_effect_filter(cfg, length):
    filters = []
    eff = cfg["effect"]
    bright = cfg["brightness"]
    cont = cfg["contrast"]
    sat = cfg["saturation"]
    if eff == "Cinematic - Dark + Warm":
        bright -= 0.05
        cont += 0.15
        sat -= 0.10
        filters.append("curves=r='0/0 0.5/0.45 1/1':g='0/0 0.5/0.5 1/1':b='0/0 0.5/0.55 1/0.95'")
    elif eff == "Vivid - Color Pop":
        bright += 0.05
        cont += 0.20
        sat += 0.40
    elif eff == "Black & White":
        sat = 0.0
        cont += 0.10
    elif eff == "Vintage - Old Film":
        bright += 0.05
        cont -= 0.05
        sat -= 0.20
        filters.append("noise=alls=6:allf=t")
    elif eff == "Warm - Golden":
        filters.append("colorbalance=rs=0.15:gs=0.05:bs=-0.15")
    elif eff == "Cool - Blue":
        filters.append("colorbalance=rs=-0.10:gs=0.0:bs=0.15")
    filters.append(f"eq=brightness={bright:.2f}:contrast={cont:.2f}:saturation={sat:.2f}")
    if cfg["sharpen"] > 0:
        filters.append(f"unsharp=5:5:{cfg['sharpen']:.1f}:5:5:0.0")
    if cfg["blur"] > 0:
        filters.append(f"gblur=sigma={cfg['blur']:.1f}")
    if cfg["fade_in"]:
        filters.append("fade=t=in:st=0:d=0.8")
    if cfg["fade_out"]:
        filters.append(f"fade=t=out:st={max(0, length-0.8):.1f}:d=0.8")
    return filters

def render_clip(source, output, start, length, cfg, music):
    out_w = cfg["out_w"]
    out_h = cfg["out_h"]
    args = ["ffmpeg", "-y", "-threads", "1", "-ss", str(start), "-i", str(source)]
    if music:
        args += ["-stream_loop", "-1", "-i", str(music)]
    filters = []
    filters.append("scale=" + str(out_w) + ":" + str(out_h) + ":force_original_aspect_ratio=increase")
    filters.append("crop=" + str(out_w) + ":" + str(out_h))
    filters.append("setsar=1")
    if cfg["speed"] != 1.0:
        filters.append(f"setpts={1.0/cfg['speed']:.3f}*PTS")
    filters += build_effect_filter(cfg, length)
    filters.append("fps=30")
    args += ["-t", str(length), "-vf", ",".join(filters), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-threads", "1", "-pix_fmt", "yuv420p"]
    src_audio = has_audio(source)
    atempo = f"atempo={cfg['speed']:.2f}," if cfg["speed"] != 1.0 else ""
    if music and src_audio:
        args += ["-filter_complex", "[0:a]" + atempo + "volume=" + str(cfg["source_volume"]) + "[a0];[1:a]volume=" + str(cfg["music_volume"]) + "[a1];[a0][a1]amix=inputs=2:duration=first[aout]", "-map", "0:v:0", "-map", "[aout]", "-c:a", "aac"]
    elif music:
        args += ["-map", "0:v:0", "-map", "1:a:0", "-af", "volume=" + str(cfg["music_volume"]), "-c:a", "aac"]
    elif src_audio:
        args += ["-af", atempo + "volume=" + str(cfg["source_volume"]), "-c:a", "aac"]
    else:
        args += ["-an"]
    args += ["-movflags", "+faststart", str(output)]
    run_cmd(args)
    gc.collect()

def get_source(work, source_type, video_url, video_upload):
    if source_type == "Google Drive":
        return download_drive(video_url, work)
    elif source_type == "YouTube":
        return download_youtube(video_url, work)
    else:
        suffix = Path(video_upload.name).suffix.lower()
        if suffix not in [".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"]:
            suffix = ".mp4"
        source = work / ("uploaded_video" + suffix)
        with source.open("wb") as f:
            shutil.copyfileobj(video_upload, f, length=8 * 1024 * 1024)
        return source

def get_music(work, music_upload):
    if music_upload is None:
        return None
    suffix = Path(music_upload.name).suffix.lower()
    if suffix not in [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"]:
        suffix = ".mp3"
    music = work / ("background_music" + suffix)
    with music.open("wb") as f:
        shutil.copyfileobj(music_upload, f, length=1024 * 1024)
    return music

# ===== UI - ENGLISH ONLY =====
st.subheader("📁 Video Source - YouTube Only + Drive + Upload")
source_type = st.radio("Choose source", ["YouTube", "Google Drive", "Upload video"], horizontal=True)
video_url = ""
video_upload = None
if source_type == "YouTube":
    video_url = st.text_input("YouTube URL", placeholder="Paste YouTube link - https://www.youtube.com/watch?v=...")
    st.caption("Powered by Cobalt Server - Works on Streamlit! If one Cobalt server fails, it auto tries next server.")
elif source_type == "Google Drive":
    video_url = st.text_input("Google Drive sharing link", placeholder="Paste Drive link")
    st.caption("Drive: Anyone with the link -> Viewer")
else:
    video_upload = st.file_uploader("Upload video", type=["mp4", "mov", "mkv", "webm", "avi", "m4v"])

st.subheader("🎵 Background Music")
music_upload = st.file_uploader("Upload music (optional)", type=["mp3", "wav", "m4a", "aac", "ogg", "flac"])

st.subheader("🎯 Clipping Mode")
clip_mode = st.radio("How do you want to clip?", ["🔥 Highlight Moments - Best Parts Only (UNLIMITED Length)", "📐 Normal Clipping - Evenly Spaced Clips"], index=0)
if "Highlight" in clip_mode:
    st.info("🔥 UNLIMITED Highlights: No 10 min limit! 10 min, 30 min, 1 hour, 3 hours - any length works. App listens to loudness (laughs, cheers, beats) and picks BEST moments.")
else:
    st.info("📐 Normal Mode: Non-overlapping clips. Example: 90 sec video + 30 sec clips = 3 clips at 0:00, 0:30, 1:00 - No duplicates!")

c1, c2 = st.columns(2)
with c1:
    clip_count = st.slider("Maximum clips", 1, 30, 3)
    clip_length = st.slider("Clip duration (seconds)", 5, 60, 30)
with c2:
    quality = st.selectbox("Video quality", ["Fast - Low CPU", "Balanced", "High"], index=0)
    source_volume = st.slider("Original audio volume", 0.0, 2.0, 1.5)
    music_volume = st.slider("Background music volume", 0.0, 2.0, 0.25)

if clip_count > 10:
    st.warning(f"You selected {clip_count} clips. It will take more time. For daily use, 3-5 clips is best.")

st.subheader("✂️ Trim Settings")
use_trim = st.toggle("Enable Trim - Use only a part of video", value=False)
trim_start = 0.0
trim_end = 999999.0
if use_trim:
    cT1, cT2 = st.columns(2)
    with cT1:
        trim_start = st.number_input("Start Time (seconds) - Where to start?", min_value=0.0, value=0.0, step=1.0)
        st.caption("Example: 120 = Start from 2:00")
    with cT2:
        trim_end = st.number_input("End Time (seconds) - Where to end?", min_value=1.0, value=600.0, step=1.0)
        st.caption("Example: 1800 = End at 30:00 - No limit, enter any value!")
    st.info(f"Trim: Using only {trim_start:.0f}s to {trim_end:.0f}s - Rest will be ignored!")
    if trim_end <= trim_start:
        st.error("End Time must be greater than Start Time!")
else:
    st.caption("Trim OFF - Full video will be used - Unlimited length!")

st.subheader("🎨 Video Effects")
effect = st.selectbox("Video Effect / Filter", ["None - Original", "Cinematic - Dark + Warm", "Vivid - Color Pop", "Black & White", "Vintage - Old Film", "Warm - Golden", "Cool - Blue"])
e1, e2, e3 = st.columns(3)
with e1:
    brightness = st.slider("Brightness", -0.3, 0.3, 0.0, step=0.01)
    speed = st.selectbox("Speed", [0.5, 0.75, 1.0, 1.25, 1.5, 2.0], index=2)
with e2:
    contrast = st.slider("Contrast", 0.5, 2.0, 1.0, step=0.05)
    sharpen = st.slider("Sharpen", 0.0, 3.0, 0.0, step=0.5)
with e3:
    saturation = st.slider("Saturation / Color", 0.0, 2.5, 1.0, step=0.05)
    blur = st.slider("Blur (0 = No Blur)", 0.0, 3.0, 0.0, step=0.5)
f1, f2 = st.columns(2)
with f1:
    fade_in = st.toggle("Fade In - Start from black", value=False)
with f2:
    fade_out = st.toggle("Fade Out - End to black", value=False)
st.caption(f"Effect: {effect} | Speed: {speed}x | Brightness: {brightness} | Contrast: {contrast} | Saturation: {saturation}")

st.markdown("### 📐 Ratio & Resolution")
r1, r2 = st.columns(2)
with r1:
    ratio_label = st.selectbox("Aspect Ratio", list(RATIOS.keys()), index=0)
with r2:
    res_label = st.selectbox("Resolution", list(RESOLUTIONS.keys()), index=1)
out_w, out_h = get_output_size(ratio_label, res_label)
st.info("Selected: " + ratio_label + " | " + res_label + " | " + str(out_w) + "x" + str(out_h))

cfg = {"source_volume": source_volume, "music_volume": music_volume, "preset": {"Fast - Low CPU": "ultrafast", "Balanced": "veryfast", "High": "fast"}[quality], "crf": {"Fast - Low CPU": 28, "Balanced": 23, "High": 19}[quality], "out_w": out_w, "out_h": out_h, "ratio": ratio_label, "resolution": res_label, "effect": effect, "brightness": brightness, "contrast": contrast, "saturation": saturation, "sharpen": sharpen, "blur": blur, "speed": float(speed), "fade_in": fade_in, "fade_out": fade_out}

st.subheader("👀 Step 1: Preview (Mandatory)")
st.warning("First check Preview - Then Generate button will unlock")
if st.button("GENERATE PREVIEW - 5 Sec Sample", use_container_width=True, key="btn_preview"):
    if source_type == "Upload video" and video_upload is None:
        st.error("Please upload a video first")
        st.stop()
    if source_type != "Upload video" and not video_url.strip().startswith(("https://", "http://")):
        st.error("Please enter a valid video link")
        st.stop()
    if not check_ffmpeg():
        st.error("FFmpeg missing")
        st.stop()
    work = Path(tempfile.mkdtemp(prefix="preview_"))
    try:
        st.write("Making Preview... Please wait - Cobalt downloading...")
        source = get_source(work, source_type, video_url, video_upload)
        music = get_music(work, music_upload)
        p_start = trim_start if use_trim else 0.0
        preview_out = work / "preview.mp4"
        render_clip(source, preview_out, p_start, 5, cfg, music)
        with open(preview_out, "rb") as f:
            st.session_state.preview_bytes = f.read()
        st.success("Preview Ready - Check Trim + Effect!")
        st.video(st.session_state.preview_bytes)
        st.session_state.preview_done = True
    except Exception as e:
        st.error("Preview Error: " + str(e))
        st.session_state.preview_done = False

if st.session_state.preview_bytes is not None:
    st.video(st.session_state.preview_bytes)
if st.session_state.preview_done:
    st.success("Preview Approved - Now you can Generate!")
else:
    st.warning("Generate Locked - Watch Preview First")

st.subheader("🚀 Step 2: Generate Your Clips")
generate_disabled = not st.session_state.preview_done
if st.button("GENERATE CLIPS", type="primary", use_container_width=True, disabled=generate_disabled, key="btn_generate"):
    work = Path(tempfile.mkdtemp(prefix="clipshort_"))
    try:
        st.write("Processing your video via Cobalt...")
        source = get_source(work, source_type, video_url, video_upload)
        music = get_music(work, music_upload)
        total = get_duration(source)
        st.write("Video length: " + str(round(total, 1)) + " sec (" + str(round(total / 60, 1)) + " min) - UNLIMITED Supported!")
        t_start = trim_start if use_trim else 0.0
        t_end = min(trim_end, total) if use_trim else total
        if t_end <= t_start:
            st.error("Trim End must be greater than Trim Start!")
            st.stop()
        st.write(f"Trim: {t_start:.0f}s to {t_end:.0f}s | Mode: {clip_mode} | Effect: {effect} | Speed: {speed}x")
        if "Highlight" in clip_mode:
            st.write("Analyzing audio for highlight moments... (Loud parts = Best parts) - Unlimited length, please wait...")
            scores = get_highlight_scores(source, total)
            if scores is None:
                st.warning("No audio found - Falling back to Normal Clipping")
                starts = choose_normal_starts(total, clip_length, clip_count, t_start, t_end)
            else:
                starts = choose_highlight_starts(scores, total, clip_length, clip_count, t_start, t_end)
                st.write(f"Found {len(starts)} highlight moments from {round(total/60,1)} min video!")
                for idx, s in enumerate(starts):
                    st.write(f"Highlight {idx+1}: Starts at {int(s//60)}:{int(s%60):02d} - Duration {clip_length}s")
        else:
            starts = choose_normal_starts(total, clip_length, clip_count, t_start, t_end)
            st.write(f"Normal Mode: {len(starts)} clips - No overlap!")
            for idx, s in enumerate(starts):
                st.write(f"Clip {idx+1}: Starts at {int(s//60)}:{int(s%60):02d}")
        st.write("Making " + str(len(starts)) + " clips...")
        outs = []
        for i, s in enumerate(starts):
            out = work / ("clip_" + str(i + 1) + ".mp4")
            st.write("Rendering clip " + str(i + 1) + " / " + str(len(starts)) + f" - Start: {int(s//60)}:{int(s%60):02d} - Length: {clip_length}s")
            render_clip(source, out, s, clip_length, cfg, music)
            if out.exists():
                outs.append(out)
        st.success("Done - " + str(len(outs)) + " Clips Ready!")
        for i, o in enumerate(outs):
            st.subheader("Clip " + str(i + 1) + " - " + str(out_w) + "x" + str(out_h) + " - " + effect)
            st.video(str(o))
            with open(o, "rb") as f:
                st.download_button("Download Clip " + str(i + 1), data=f.read(), file_name="clip_" + str(i + 1) + "_" + str(out_w) + "x" + str(out_h) + ".mp4", mime="video/mp4", key="dl_" + str(i))
    except Exception as e:
        st.error("Error: " + str(e))
