import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import streamlit as st

APP_DIR = Path("clipshort_work")
APP_DIR.mkdir(exist_ok=True)
INPUT_PATH = APP_DIR / "source_video"
OUTPUT_DIR = APP_DIR / "clips"
OUTPUT_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="ClipShort AI", page_icon="✂️", layout="wide")

st.markdown("""
<style>
.stApp {background:#08080d;color:#f8fafc}
h1,h2,h3 {color:#fff}
div[data-testid="stButton"] button[kind="primary"] {background:#7c3aed;border:0}
.small-muted {color:#a1a1aa}
</style>
""", unsafe_allow_html=True)

def run_cmd(cmd, timeout=None):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

def ffmpeg_path():
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

FFMPEG = ffmpeg_path()
FFPROBE = shutil.which("ffprobe")

def probe_duration(path):
    if FFPROBE:
        r = run_cmd([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
        if r.returncode == 0:
            try:
                return float(r.stdout.strip())
            except ValueError:
                pass
    r = run_cmd([FFMPEG, "-i", str(path)], timeout=60)
    match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr)
    if match:
        h, m, s = match.groups()
        return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0

def safe_name(value):
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")
    return value[:50] or "clip"

def download_youtube(url, destination, cookies_browser=None):
    # Downloads only public/authorized videos that yt-dlp can access.
    cmd = ["yt-dlp", "--no-playlist", "--newline", "--retries", "5",
           "--fragment-retries", "5", "--extractor-retries", "3",
           "--socket-timeout", "30", "-f", "bv*+ba/b",
           "--merge-output-format", "mp4", "-o", str(destination), url]
    if cookies_browser:
        cmd[1:1] = ["--cookies-from-browser", cookies_browser]
    return run_cmd(cmd, timeout=60 * 60 * 8)

def extract_audio(video_path, wav_path):
    cmd = [FFMPEG, "-y", "-i", str(video_path), "-vn", "-ac", "1",
           "-ar", "16000", "-c:a", "pcm_s16le", str(wav_path)]
    return run_cmd(cmd, timeout=60 * 60 * 4)

def transcribe(wav_path, model_name, device):
    from faster_whisper import WhisperModel
    compute = "float16" if device == "cuda" else "int8"
    model = WhisperModel(model_name, device=device, compute_type=compute)
    segments, info = model.transcribe(str(wav_path), vad_filter=True,
                                      word_timestamps=False, beam_size=5)
    rows = []
    for seg in segments:
        text = (seg.text or "").strip()
        if text:
            rows.append({"start": float(seg.start), "end": float(seg.end), "text": text})
    return rows, info

def candidate_windows(segments, duration, clip_len, prompt):
    # Generate overlapping transcript-backed candidate windows.
    step = max(5, clip_len // 3)
    starts = list(range(0, max(1, int(duration - clip_len) + 1), step))
    if not starts:
        starts = [0]
    last = max(0, duration - clip_len)
    if starts[-1] != int(last):
        starts.append(int(last))
    prompt_words = set(re.findall(r"[a-zA-Z]{3,}", prompt.lower()))
    candidates = []
    for start in starts:
        end = min(duration, start + clip_len)
        parts = [s for s in segments if s["end"] > start and s["start"] < end]
        transcript = " ".join(s["text"] for s in parts).strip()
        if len(transcript.split()) < 8:
            continue
        words = re.findall(r"[a-zA-Z']+", transcript.lower())
        if not words:
            continue
        hooks = ["why", "how", "secret", "never", "best", "worst", "mistake",
                 "important", "amazing", "because", "but", "however", "finally",
                 "truth", "learn", "problem", "solution", "number one"]
        hook_score = sum(1 for w in hooks if w in transcript.lower())
        question_score = transcript.count("?")
        exclaim_score = transcript.count("!")
        unique_ratio = len(set(words)) / max(1, len(words))
        prompt_score = sum(1 for w in words if w in prompt_words)
        # A lightweight fallback score; not a prediction of actual virality.
        score = (min(len(words), 110) / 110) * 35 + hook_score * 3 + \
                question_score * 2 + exclaim_score + unique_ratio * 12 + prompt_score * 4
        candidates.append({"start": float(start), "end": float(end),
                           "transcript": transcript, "local_score": score})
    candidates.sort(key=lambda x: x["local_score"], reverse=True)
    return candidates[:40]

def ai_rank(candidates, number, prompt):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or not candidates:
        return candidates[:number], "Local transcript scoring"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        compact = [{"id": i, "start": round(c["start"], 1),
                    "end": round(c["end"], 1), "transcript": c["transcript"][:1200]}
                   for i, c in enumerate(candidates)]
        instructions = (
            "You are an expert short-form video editor. Select distinct, self-contained "
            "moments with a strong hook, useful insight, emotion, story payoff, or clear "
            "entertainment value. Avoid intros, dead air, repeated ideas and incomplete "
            "sentences. Do not claim to predict virality. Return only valid JSON in the "
            "shape {\"selected_ids\":[integer,...],\"titles\":[string,...]}."
        )
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
            instructions=instructions,
            input=f"Editing goal: {prompt or 'Find the strongest engaging moments.'}\n"
                  f"Choose up to {number} candidates, prioritizing distinct moments.\n"
                  f"Candidates: {json.dumps(compact, ensure_ascii=False)}",
            text={"format": {"type": "json_object"}},
            store=False
        )
        data = json.loads(response.output_text)
        chosen = []
        for idx in data.get("selected_ids", []):
            if isinstance(idx, int) and 0 <= idx < len(candidates):
                item = dict(candidates[idx])
                pos = len(chosen)
                titles = data.get("titles", [])
                item["title"] = titles[pos] if pos < len(titles) else f"Highlight {pos+1}"
                chosen.append(item)
            if len(chosen) >= number:
                break
        if chosen:
            return chosen, "OpenAI AI selection + local Whisper"
    except Exception as exc:
        st.warning(f"AI API selection unavailable; using local ranking. Details: {exc}")
    return candidates[:number], "Local transcript scoring (fallback)"

def srt_timestamp(seconds):
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def write_srt(segments, clip_start, clip_end, path):
    lines = []
    index = 1
    for seg in segments:
        start = max(seg["start"], clip_start)
        end = min(seg["end"], clip_end)
        if end <= start:
            continue
        lines += [str(index),
                  f"{srt_timestamp(start-clip_start)} --> {srt_timestamp(end-clip_start)}",
                  seg["text"].replace("-->", "—"), ""]
        index += 1
    Path(path).write_text("\n".join(lines), encoding="utf-8")

def render_clip(video, out, start, end, segments, burn_subtitles=True):
    duration = max(0.1, end - start)
    filters = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920:(iw-1080)/2:(ih-1920)/2"
    )
    srt_path = out.with_suffix(".srt")
    if burn_subtitles:
        write_srt(segments, start, end, srt_path)
        # Escape path for FFmpeg subtitles filter.
        escaped = str(srt_path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        filters += f",subtitles='{escaped}':force_style='FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=110'"
    cmd = [FFMPEG, "-y", "-ss", str(start), "-i", str(video), "-t", str(duration),
           "-vf", filters, "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
           str(out)]
    result = run_cmd(cmd, timeout=60 * 60 * 2)
    return result

st.title("✂️ ClipShort AI")
st.caption("Turn long videos into captioned vertical Shorts with AI-assisted highlight selection.")

if not FFMPEG:
    st.error("FFmpeg was not found. Install FFmpeg and add it to PATH, then restart the app.")
    st.stop()

with st.sidebar:
    st.header("AI settings")
    whisper_model = st.selectbox("Whisper model", ["base", "small", "medium"], index=1,
                                 help="Small is a practical balance. Medium is slower and more accurate.")
    device = st.selectbox("Compute device", ["cpu", "cuda"], index=0,
                          help="Choose CUDA only if your PC has a compatible NVIDIA GPU.")
    st.caption("First run downloads the Whisper model. This can take time and disk space.")
    st.divider()
    st.caption("Optional AI selection")
    api_key_input = st.text_input("OpenAI API key (optional)", type="password")
    if api_key_input:
        os.environ["OPENAI_API_KEY"] = api_key_input
    model_name = st.text_input("API model", value=os.getenv("OPENAI_MODEL", "gpt-5.5"))
    if model_name.strip():
        os.environ["OPENAI_MODEL"] = model_name.strip()

source_mode = st.radio("Video source", ["Upload video", "YouTube link"], horizontal=True)
video_path = None

if source_mode == "Upload video":
    uploaded = st.file_uploader("Upload a video (up to 4 GB configured)", type=["mp4", "mov", "mkv", "webm"])
    if uploaded is not None:
        size_gb = uploaded.size / (1024 ** 3)
        st.info(f"Selected file: {uploaded.name} · {size_gb:.2f} GB")
        if uploaded.size > 4 * 1024**3:
            st.error("File exceeds the 4 GB limit.")
        else:
            if st.button("Save uploaded video", type="primary"):
                with st.spinner("Saving upload to disk..."):
                    with open(INPUT_PATH, "wb") as f:
                        shutil.copyfileobj(uploaded, f, length=8 * 1024 * 1024)
                st.session_state["video_path"] = str(INPUT_PATH)
                st.success("Video saved.")
    video_path = st.session_state.get("video_path")

else:
    yt_url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...")
    cookies = st.selectbox("Browser cookies (optional)", ["None", "chrome", "firefox", "edge", "brave"])
    st.caption("Only download videos you own or are authorized to use. Cookies must exist on the machine running this app.")
    if st.button("Import YouTube video", type="primary", disabled=not yt_url.strip()):
        with st.spinner("yt-dlp is importing the video..."):
            result = download_youtube(yt_url.strip(), INPUT_PATH, None if cookies == "None" else cookies)
        if INPUT_PATH.exists() and INPUT_PATH.stat().st_size > 1000:
            st.session_state["video_path"] = str(INPUT_PATH)
            st.success("Video imported.")
        else:
            st.error("YouTube import failed. The server may not be able to access this video.")
            st.code((result.stderr or result.stdout)[-3000:])

if video_path and Path(video_path).exists():
    video_path = Path(video_path)
    duration = probe_duration(video_path)
    st.video(str(video_path))
    st.write(f"Video duration: **{duration/60:.1f} minutes** · File size: **{video_path.stat().st_size/(1024**3):.2f} GB**")
    c1, c2, c3 = st.columns(3)
    with c1:
        clip_count = st.selectbox("Number of clips", [3, 5, 10], index=1)
    with c2:
        clip_len = st.selectbox("Target clip length", [15, 30, 45, 60], index=1)
    with c3:
        burn = st.checkbox("Burn subtitles into video", value=True)
    prompt = st.text_input("Highlight direction (optional)",
                           placeholder="e.g. funny moments, key lessons, strong opinions, gaming wins")
    if st.button("🚀 Generate AI Shorts", type="primary", use_container_width=True):
        if duration < 8:
            st.error("Video is too short to create useful clips.")
            st.stop()
        if duration <= clip_len:
            st.warning("The source is shorter than the selected clip length. Clips will use the available duration.")
        for old in OUTPUT_DIR.glob("*"):
            if old.is_file():
                old.unlink()
        wav = APP_DIR / "audio_16k.wav"
        progress = st.progress(0)
        status = st.empty()
        try:
            status.write("1/4 · Extracting audio...")
            audio_result = extract_audio(video_path, wav)
            if audio_result.returncode != 0 or not wav.exists():
                raise RuntimeError(audio_result.stderr[-2000:])
            progress.progress(20)

            status.write("2/4 · Whisper is transcribing the video...")
            segments, info = transcribe(wav, whisper_model, device)
            if not segments:
                raise RuntimeError("No speech was detected. Try a video with clear speech.")
            progress.progress(50)

            status.write("3/4 · AI is selecting the strongest moments...")
            actual_len = min(float(clip_len), duration)
            candidates = candidate_windows(segments, duration, actual_len, prompt)
            if not candidates:
                # Fallback to evenly spaced windows if transcription produced too little text.
                starts = [max(0, (duration-actual_len)*i/max(1, clip_count-1)) for i in range(clip_count)]
                candidates = [{"start": s, "end": min(duration, s+actual_len),
                               "transcript": "", "local_score": 0} for s in starts]
            selected, method = ai_rank(candidates, clip_count, prompt)
            progress.progress(65)

            status.write("4/4 · Rendering vertical clips and subtitles...")
            results = []
            for i, item in enumerate(selected, start=1):
                start = max(0.0, float(item["start"]))
                end = min(duration, float(item["end"]))
                out = OUTPUT_DIR / f"clip_{i:02}.mp4"
                r = render_clip(video_path, out, start, end, segments, burn)
                if r.returncode == 0 and out.exists() and out.stat().st_size > 1000:
                    results.append((out, item, start, end))
                else:
                    st.warning(f"Clip {i} failed: {(r.stderr or '')[-1000:]}")
                progress.progress(65 + int(35*i/max(1, len(selected))))
            status.success(f"Finished: {len(results)} clips · Selection: {method}")
            st.session_state["clip_results"] = [(str(p), x, a, b) for p, x, a, b in results]
        except Exception as exc:
            st.error(f"Processing failed: {exc}")
            st.info("Check that FFmpeg is installed, the selected Whisper model can download, and enough free disk space is available.")

    results = st.session_state.get("clip_results", [])
    if results:
        st.subheader("Your generated Shorts")
        for i, (path, item, start, end) in enumerate(results, start=1):
            path = Path(path)
            if not path.exists():
                continue
            st.markdown(f"**Clip {i}: {item.get('title', 'AI highlight')}** · {start:.1f}s–{end:.1f}s")
            if item.get("transcript"):
                st.caption(item["transcript"][:350])
            st.video(str(path))
            st.download_button(f"⬇️ Download Clip {i}", data=path.read_bytes(),
                               file_name=path.name, mime="video/mp4", key=f"download_{i}")
        zip_path = APP_DIR / "clipshort_shorts.zip"
        import zipfile
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path, *_ in results:
                if Path(path).exists():
                    zf.write(path, arcname=Path(path).name)
        st.download_button("⬇️ Download all clips (ZIP)", data=zip_path.read_bytes(),
                           file_name="clipshort_shorts.zip", mime="application/zip")
else:
    st.info("Upload a video or import a YouTube link to begin.")
