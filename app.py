
import streamlit as st
import subprocess
import tempfile
import shutil
import zipfile
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

st.set_page_config(page_title="CLIPSHORT AI", page_icon="🎬", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;800&display=swap');
html, body, [class*="css"] {font-family: 'DM Sans', sans-serif;}
.stApp {background:#0b1020;color:#f5f7ff;}
[data-testid="stSidebar"] {background:#111a2e;border-right:1px solid #263451;}
.block-container {max-width:1250px;padding-top:2rem;}
.hero {padding:26px;border-radius:18px;background:linear-gradient(120deg,#172b49,#34204d);border:1px solid #35476a;margin-bottom:22px;}
.hero h1 {font-size:36px;font-weight:800;margin:0;}
.hero p {color:#c4cde0;margin-bottom:0;}
div.stButton>button, div.stDownloadButton>button {border:0;border-radius:10px;background:linear-gradient(90deg,#6255e8,#984fe8);color:white;font-weight:700;min-height:44px;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="hero"><h1>🎬 CLIPSHORT AI</h1><p>Video clips • Automatic subtitles • Music • Shorts</p></div>', unsafe_allow_html=True)


def command(args):
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout)[-3000:])
    return p.stdout.strip()


def ffmpeg_ready():
    return shutil.which("ffmpeg") and shutil.which("ffprobe")


def video_duration(path):
    return float(command([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ]))


def has_audio(path):
    p = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)
    ], capture_output=True, text=True)
    return bool(p.stdout.strip())


# GOOGLE DRIVE

def drive_file_id(url):
    parsed = urlparse(url.strip())
    m = re.search(r"/file/d/([A-Za-z0-9_-]+)", parsed.path)
    if m:
        return m.group(1)
    q = parse_qs(parsed.query)
    if q.get("id"):
        return q["id"][0]
    raise ValueError("Invalid Google Drive file link.")


def download_drive(url, folder):
    import gdown
    file_id = drive_file_id(url)
    target = folder / "drive_source"
    result = gdown.download(id=file_id, output=str(target), quiet=False)
    if not result or not Path(result).is_file() or Path(result).stat().st_size == 0:
        raise RuntimeError("Google Drive download failed. Set sharing to Anyone with the link (Viewer).")
    return Path(result)


# YOUTUBE

def download_youtube(url, folder):
    import yt_dlp
    opts = {
        "format": "best[height<=720][ext=mp4]/best[height<=720]/best",
        "outtmpl": str(folder / "youtube_source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 2
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    found = [p for p in folder.glob("youtube_source.*") if p.is_file()]
    if not found:
        raise RuntimeError("YouTube did not provide a downloadable video. Try a permitted video or upload a file.")
    return found[0]


# WHISPER / PYAV COMPATIBILITY

@st.cache_resource
def load_whisper(model_name):
    import av

    original_open = av.open

    def compatible_open(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return original_open(*args, **kwargs)

    av.open = compatible_open

    from faster_whisper import WhisperModel
    return WhisperModel(model_name, device="cpu", compute_type="int8")


# AUTOMATIC SUBTITLES

def transcribe(path, model_name, language):
    model = load_whisper(model_name)
    opts = {"vad_filter": True, "beam_size": 2}
    if language != "Auto":
        opts["language"] = language.lower()

    segments, _ = model.transcribe(str(path), **opts)

    return [
        {"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
        for s in segments if s.text.strip()
    ]


# CLIP SELECTION

def choose_clip_starts(segments, total, length, count):
    if total <= length:
        return [0.0]

    step = max(2.0, min(length / 5, 6.0))
    ranked = []
    t = 0.0

    while t + length <= total:
        end = t + length
        score = sum(
            max(0.0, min(s["end"], end) - max(s["start"], t))
            for s in segments
        )
        ranked.append((score, t))
        t += step

    ranked.sort(key=lambda x: x[0], reverse=True)
    selected = []

    for _, start in ranked:
        if all(abs(start - old) >= length * 0.65 for old in selected):
            selected.append(start)
        if len(selected) >= count:
            break

    return sorted(selected or [0.0])


# CAPTION FILE

def ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_color(hex_color):
    value = hex_color.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        value = "FFFFFF"
    r, g, b = value[0:2], value[2:4], value[4:6]
    return f"&H00{b}{g}{r}&".upper()


def write_ass(path, segments, clip_start, clip_end, cfg):
    alignment = {"Bottom": 2, "Middle": 5, "Top": 8}[cfg["position"]]
    bold = -1 if cfg["bold"] else 0
    border_style = 3 if cfg["background"] else 1
    outline = 0 if cfg["background"] else cfg["outline"]
    font = cfg["font"].replace(",", " ")

    rows = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font},{cfg['font_size']},{ass_color(cfg['text_color'])},&H000000FF&,{ass_color(cfg['outline_color'])},{ass_color(cfg['background_color'])},{bold},0,0,0,100,100,0,0,{border_style},{outline},{cfg['shadow']},{alignment},60,60,90,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]

    for seg in segments:
        a = max(seg["start"], clip_start)
        b = min(seg["end"], clip_end)
        if b <= a:
            continue

        text = seg["text"].replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", " ")
        if cfg["uppercase"]:
            text = text.upper()

        rows.append(
            f"Dialogue: 0,{ass_time(a-clip_start)},{ass_time(b-clip_start)},Default,,0,0,0,,{text}"
        )

    path.write_text("\n".join(rows), encoding="utf-8")


def ffmpeg_filter_path(path):
    value = str(path.resolve()).replace("\\", "/")
    value = value.replace(":", r"\:").replace("'", r"\'").replace(",", r"\,")
    return value


# VIDEO RENDERING

def render_clip(source, output, start, length, segments, cfg, music):
    args = ["ffmpeg", "-y", "-ss", str(start), "-i", str(source)]

    if music:
        args += ["-stream_loop", "-1", "-i", str(music)]

    filters = [
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920",
        "setsar=1",
        "fps=30"
    ]

    ass_file = output.with_suffix(".ass")

    if cfg["subtitles"]:
        write_ass(ass_file, segments, start, start + length, cfg)
        filters.append("ass='" + ffmpeg_filter_path(ass_file) + "'")

    args += [
        "-t", str(length),
        "-vf", ",".join(filters),
        "-c:v", "libx264",
        "-preset", cfg["preset"],
        "-crf", str(cfg["crf"]),
        "-pix_fmt", "yuv420p"
    ]

    source_audio = has_audio(source)

    if music and source_audio:
        args += [
            "-filter_complex",
            f"[0:a]volume={cfg['source_volume']}[a0];[1:a]volume={cfg['music_volume']}[a1];[a0][a1]amix=inputs=2:duration=first[aout]",
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:a", "aac"
        ]
    elif music:
        args += [
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-af", f"volume={cfg['music_volume']}",
            "-c:a", "aac"
        ]
    elif source_audio:
        args += [
            "-af", f"volume={cfg['source_volume']}",
            "-c:a", "aac"
        ]
    else:
        args += ["-an"]

    args += ["-movflags", "+faststart", str(output)]
    command(args)

    if ass_file.exists():
        ass_file.unlink()


# SIDEBAR SETTINGS

with st.sidebar:
    st.header("⚙️ Edit settings")

    clip_count = st.slider("Maximum clips", 1, 30, 5)
    clip_length = st.slider("Clip length (seconds)", 10, 90, 30)

    st.divider()
    st.subheader("Captions")

    subtitles = st.toggle("Automatic subtitles", True)
    font = st.selectbox("Font", [
        "Arial", "DejaVu Sans", "Liberation Sans",
        "Montserrat", "Roboto", "Poppins", "Impact", "Georgia"
    ])
    font_size = st.slider("Font size", 18, 80, 48)
    text_color = st.color_picker("Text colour", "#FFFFFF")
    outline_color = st.color_picker("Outline colour", "#000000")
    outline = st.slider("Outline thickness", 0, 8, 3)
    position = st.selectbox("Caption position", ["Bottom", "Middle", "Top"])
    bold = st.toggle("Bold", True)
    uppercase = st.toggle("Uppercase", False)
    background = st.toggle("Caption background", False)
    background_color = st.color_picker("Caption background colour", "#151515")
    shadow = st.slider("Shadow", 0, 5, 2)

    st.divider()
    st.subheader("Audio")

    source_volume = st.slider("Original audio volume", 0.0, 2.0, 1.0)
    music_volume = st.slider("Music volume", 0.0, 2.0, 0.25)

    st.divider()

    quality = st.selectbox("Export quality", ["Fast", "Balanced", "High"], index=1)
    model_name = st.selectbox("Subtitle model", ["tiny", "base", "small"], index=0)
    language = st.selectbox("Subtitle language", [
        "Auto", "English", "Hindi", "Telugu",
        "Tamil", "Kannada", "Malayalam"
    ])


cfg = {
    "subtitles": subtitles,
    "font": font,
    "font_size": font_size,
    "text_color": text_color,
    "outline_color": outline_color,
    "outline": outline,
    "position": position,
    "bold": bold,
    "uppercase": uppercase,
    "background": background,
    "background_color": background_color,
    "shadow": shadow,
    "source_volume": source_volume,
    "music_volume": music_volume,
    "preset": {"Fast": "ultrafast", "Balanced": "veryfast", "High": "fast"}[quality],
    "crf": {"Fast": 27, "Balanced": 23, "High": 19}[quality]
}


# VIDEO INPUT

video_col, music_col = st.columns([1.25, 1])

with video_col:
    st.subheader("📁 Video source")

    source_type = st.radio(
        "Choose source",
        ["Google Drive", "Upload video", "YouTube"],
        horizontal=True
    )

    video_url = ""
    video_upload = None

    if source_type == "Google Drive":
        video_url = st.text_input(
            "Google Drive sharing link",
            placeholder="Paste your Drive link"
        )
        st.caption("Drive sharing: Anyone with the link → Viewer.")

    elif source_type == "Upload video":
        video_upload = st.file_uploader(
            "Upload video",
            type=["mp4", "mov", "mkv", "webm", "avi", "m4v"]
        )

    else:
        video_url = st.text_input(
            "YouTube video URL",
            placeholder="https://www.youtube.com/watch?v=..."
        )


with music_col:
    st.subheader("🎵 Background music")

    music_upload = st.file_uploader(
        "Upload music (optional)",
        type=["mp3", "wav", "m4a", "aac", "ogg", "flac"]
    )

    st.caption("Only use music you have permission to use.")


# GENERATE CLIPS

st.subheader("🚀 Generate clips")

if st.button("GENERATE CLIPS", type="primary", use_container_width=True):

    if source_type == "Upload video" and video_upload is None:
        st.error("Please upload a video.")
        st.stop()

    if source_type != "Upload video" and not video_url.strip().startswith(("https://", "http://")):
        st.error("Please enter a valid video link.")
        st.stop()

    if not ffmpeg_ready():
        st.error("FFmpeg/FFprobe is missing. Check packages.txt.")
        st.stop()

    work = Path(tempfile.mkdtemp(prefix="clipshort_"))

    try:
        with st.status("Preparing your video...", expanded=True) as status:

            if source_type == "Google Drive":
                st.write("Downloading from Google Drive...")
                source = download_drive(video_url, work)

            elif source_type == "YouTube":
                st.write("Downloading from YouTube...")
                source = download_youtube(video_url, work)

            else:
                source = work / ("uploaded_video" + Path(video_upload.name).suffix.lower())
                with source.open("wb") as f:
                    shutil.copyfileobj(video_upload, f, length=8 * 1024 * 1024)

            music = None

            if music_upload is not None:
                music = work / ("background_music" + Path(music_upload.name).suffix.lower())
                with music.open("wb") as f:
                    shutil.copyfileobj(music_upload, f, length=1024 * 1024)

            total = video_duration(source)

            if total <= 0:
                raise RuntimeError("Could not read video duration.")

            st.write(f"Video duration: {total/60:.1f} minutes")

            if subtitles:
                st.write("Generating automatic subtitles...")
                segments = transcribe(source, model_name, language)
            else:
                segments = []

            starts = choose_clip_starts(
                segments, total, min(clip_length, total), clip_count
            )

            output_dir = work / "clips"
            output_dir.mkdir()

            progress = st.progress(0)

            for i, start in enumerate(starts, 1):
                length = min(float(clip_length), total - start)

                if length <= 0:
                    continue

                st.write(f"Rendering clip {i} of {len(starts)}...")

                render_clip(
                    source,
                    output_dir / f"clip_{i:02d}.mp4",
                    start,
                    length,
                    segments,
                    cfg,
                    music
                )

                progress.progress(i / len(starts))

            clips = sorted(output_dir.glob("*.mp4"))

            if not clips:
                raise RuntimeError("No clips were generated.")

            zip_path = work / "CLIPSHORT_AI_clips.zip"

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for clip in clips:
                    archive.write(clip, arcname=clip.name)

            zip_bytes = zip_path.read_bytes()

            status.update(
                label="Clips generated successfully",
                state="complete"
            )

        st.success(f"Created {len(clips)} clip(s).")

        st.download_button(
            "⬇️ DOWNLOAD ALL CLIPS",
            data=zip_bytes,
            file_name="CLIPSHORT_AI_clips.zip",
            mime="application/zip",
            use_container_width=True
        )

        st.subheader("Preview")

        cols = st.columns(min(3, len(clips)))

        for i, clip in enumerate(clips):
            with cols[i % len(cols)]:
                st.caption(clip.name)
                st.video(str(clip))

    except Exception as exc:
        st.error(f"Processing error: {exc}")
        st.info(
            "Try a shorter video and Whisper tiny. "
            "Check Drive permissions. Streamlit free hosting has "
            "limited CPU, RAM, disk and execution time."
        )

    finally:
        # Keep output files available for previews in this session.
        pass


st.divider()
st.caption("CLIPSHORT AI • Streamlit")
