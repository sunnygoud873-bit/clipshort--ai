
import streamlit as st
import subprocess
import tempfile
import shutil
import zipfile
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# =====================================================
# CLIPSHORT AI - COMPLETE SINGLE FILE APPLICATION
# =====================================================

st.set_page_config(
    page_title="CLIPSHORT AI",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================
# PROFESSIONAL UI THEME
# =====================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
}

.stApp {
    background: #0b1120;
    color: #f1f5f9;
}

[data-testid="stSidebar"] {
    background: #111827;
    border-right: 1px solid #26354c;
    min-width: 310px;
}

[data-testid="stSidebar"] * {
    color: #f1f5f9;
    font-family: 'Inter', sans-serif !important;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #a5b4fc !important;
    font-weight: 700;
}

.block-container {
    max-width: 1350px;
    padding-top: 2rem;
}

.hero {
    padding: 32px;
    border-radius: 20px;
    background: linear-gradient(125deg,#172554,#312e81,#581c87);
    border: 1px solid #4338ca;
    margin-bottom: 25px;
}

.hero h1 {
    font-size: 40px;
    font-weight: 800;
    letter-spacing: -1.5px;
    color: #ffffff;
    margin: 0;
}

.hero p {
    color: #c7d2fe;
    font-size: 15px;
    margin-bottom: 0;
}

div.stButton > button,
div.stDownloadButton > button {
    background: linear-gradient(100deg,#6366f1,#9333ea);
    color: white;
    border: none;
    border-radius: 12px;
    min-height: 48px;
    font-weight: 700;
}

div.stButton > button:hover,
div.stDownloadButton > button:hover {
    border: 1px solid #c4b5fd;
    color: white;
}

[data-testid="stMetric"] {
    background: #172033;
    border: 1px solid #334155;
    border-radius: 14px;
    padding: 16px;
}

[data-testid="stFileUploader"] {
    background: #151f33;
    border: 1px dashed #64748b;
    border-radius: 14px;
    padding: 10px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
<h1>🎬 CLIPSHORT AI</h1>
<p>AI Video Clipping Studio · Automatic Subtitles · Music · Shorts</p>
</div>
""", unsafe_allow_html=True)


# =====================================================
# SYSTEM UTILITIES
# =====================================================

def run_command(args):
    result = subprocess.run(
        args,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            (result.stderr or result.stdout)[-3000:]
        )
    return result.stdout.strip()


def check_ffmpeg():
    return (
        shutil.which("ffmpeg") is not None
        and shutil.which("ffprobe") is not None
    )


def get_duration(path):
    value = run_command([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ])
    return float(value)


def has_audio(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0", str(path)
        ],
        capture_output=True,
        text=True
    )
    return bool(result.stdout.strip())


# =====================================================
# GOOGLE DRIVE
# =====================================================

def get_drive_id(url):
    parsed = urlparse(url.strip())

    match = re.search(
        r"/file/d/([A-Za-z0-9_-]+)",
        parsed.path
    )

    if match:
        return match.group(1)

    query = parse_qs(parsed.query)

    if query.get("id"):
        return query["id"][0]

    raise ValueError("Invalid Google Drive sharing link.")


def download_drive(url, folder):
    import gdown

    file_id = get_drive_id(url)
    target = folder / "drive_video"

    result = gdown.download(
        id=file_id,
        output=str(target),
        quiet=False
    )

    if not result:
        raise RuntimeError(
            "Google Drive download failed. "
            "Set sharing to Anyone with the link - Viewer."
        )

    path = Path(result)

    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError("Google Drive file is empty or unavailable.")

    return path


# =====================================================
# YOUTUBE
# =====================================================

def download_youtube(url, folder):
    import yt_dlp

    options = {
        "format": "best[height<=720][ext=mp4]/best[height<=720]/best",
        "outtmpl": str(folder / "youtube_video.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 2
    }

    with yt_dlp.YoutubeDL(options) as downloader:
        downloader.download([url])

    files = list(folder.glob("youtube_video.*"))

    if not files:
        raise RuntimeError(
            "YouTube download failed. The platform may block "
            "cloud downloads. Try uploading your video instead."
        )

    return files[0]


# =====================================================
# WHISPER MODEL
# =====================================================

@st.cache_resource
def load_whisper(model_name):
    from faster_whisper import WhisperModel

    return WhisperModel(
        model_name,
        device="cpu",
        compute_type="int8"
    )


# =====================================================
# INDIAN LANGUAGE SUBTITLES
# =====================================================

LANGUAGE_CODES = {
    "Hindi": "hi",
    "Telugu": "te",
    "Tamil": "ta",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Bengali": "bn",
    "Marathi": "mr",
    "Gujarati": "gu",
    "Punjabi": "pa",
    "Urdu": "ur"
}


def transcribe_video(path, model_name, language):
    model = load_whisper(model_name)

    options = {
        "vad_filter": True,
        "beam_size": 5,
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "no_speech_threshold": 0.6,
        "compression_ratio_threshold": 2.4,
        "log_prob_threshold": -1.0,
        "task": "transcribe"
    }

    if language == "English (Translate)":
        options["task"] = "translate"

    elif language == "Auto Detect":
        options["task"] = "transcribe"

    else:
        options["language"] = LANGUAGE_CODES[language]

    if language == "Telugu":
        options["initial_prompt"] = (
            "తెలుగు భాషలో మాట్లాడిన మాటలను "
            "సహజమైన తెలుగు లిపిలో రాయండి. "
            "తెలుగు పదాలను ఇంగ్లీష్ అక్షరాలతో రాయకండి. "
            "విన్న మాటలనే రాయండి."
        )

    segments, info = model.transcribe(
        str(path),
        **options
    )

    results = []

    for segment in segments:
        caption = segment.text.strip()

        if not caption:
            continue

        if segment.no_speech_prob > 0.85:
            continue

        results.append({
            "start": float(segment.start),
            "end": float(segment.end),
            "text": caption
        })

    return results


# =====================================================
# CLIP SELECTION
# =====================================================

def choose_clip_starts(segments, total, length, count):
    if total <= length:
        return [0.0]

    step = max(2.0, min(length / 5, 6.0))
    candidates = []
    start = 0.0

    while start + length <= total:
        end = start + length

        score = sum(
            max(
                0.0,
                min(segment["end"], end)
                - max(segment["start"], start)
            )
            for segment in segments
        )

        candidates.append((score, start))
        start += step

    candidates.sort(
        key=lambda item: item[0],
        reverse=True
    )

    selected = []

    for score, start in candidates:
        if all(
            abs(start - previous) >= length * 0.65
            for previous in selected
        ):
            selected.append(start)

        if len(selected) >= count:
            break

    return sorted(selected or [0.0])


# =====================================================
# SUBTITLE FORMATTING
# =====================================================

def ass_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining = seconds % 60

    return (
        f"{hours}:"
        f"{minutes:02d}:"
        f"{remaining:05.2f}"
    )


def ass_color(value):
    value = value.lstrip("#")

    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        value = "FFFFFF"

    red = value[0:2]
    green = value[2:4]
    blue = value[4:6]

    return f"&H00{blue}{green}{red}&".upper()


def write_subtitles(
    subtitle_file,
    segments,
    clip_start,
    clip_end,
    cfg
):
    alignment = {
        "Bottom": 2,
        "Middle": 5,
        "Top": 8
    }[cfg["position"]]

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
        (
            f"Style: Default,{font},{cfg['font_size']},"
            f"{ass_color(cfg['text_color'])},"
            f"&H000000FF&,"
            f"{ass_color(cfg['outline_color'])},"
            f"{ass_color(cfg['background_color'])},"
            f"{bold},0,0,0,100,100,0,0,"
            f"{border_style},{outline},{cfg['shadow']},"
            f"{alignment},60,60,90,1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]

    for segment in segments:
        start = max(segment["start"], clip_start)
        end = min(segment["end"], clip_end)

        if end <= start:
            continue

        caption = (
            segment["text"]
            .replace("\\", r"\\")
            .replace("{", r"\{")
            .replace("}", r"\}")
            .replace("\n", " ")
        )

        if cfg["uppercase"]:
            caption = caption.upper()

        rows.append(
            f"Dialogue: 0,{ass_time(start-clip_start)},"
            f"{ass_time(end-clip_start)},Default,,0,0,0,,{caption}"
        )

    subtitle_file.write_text(
        "\n".join(rows),
        encoding="utf-8"
    )


def subtitle_filter_path(path):
    value = str(path.resolve()).replace("\\", "/")

    return (
        value.replace(":", r"\:")
        .replace("'", r"\'")
        .replace(",", r"\,")
    )


# =====================================================
# VIDEO RENDERING
# =====================================================

def render_clip(
    source,
    output,
    start,
    length,
    segments,
    cfg,
    music
):
    args = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(source)
    ]

    if music:
        args += [
            "-stream_loop", "-1",
            "-i", str(music)
        ]

    filters = [
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920",
        "setsar=1",
        "fps=30"
    ]

    subtitle_file = output.with_suffix(".ass")

    if cfg["subtitles"] and segments:
        write_subtitles(
            subtitle_file,
            segments,
            start,
            start + length,
            cfg
        )

        filters.append(
            "ass='" + subtitle_filter_path(subtitle_file) + "'"
        )

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
            (
                f"[0:a]volume={cfg['source_volume']}[a0];"
                f"[1:a]volume={cfg['music_volume']}[a1];"
                "[a0][a1]amix=inputs=2:duration=first[aout]"
            ),
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

    args += [
        "-movflags", "+faststart",
        str(output)
    ]

    run_command(args)

    if subtitle_file.exists():
        subtitle_file.unlink()


# =====================================================
# SIDEBAR SETTINGS
# =====================================================

with st.sidebar:
    st.title("⚙️ EDIT STUDIO")

    st.header("🎬 Clip Settings")

    clip_count = st.slider(
        "Maximum clips",
        1, 30, 5
    )

    clip_length = st.slider(
        "Clip duration (seconds)",
        10, 90, 30
    )

    st.divider()
    st.header("💬 Subtitle Settings")

    subtitles = st.toggle(
        "Automatic subtitles",
        value=True
    )

    language = st.selectbox(
        "Subtitle language",
        [
            "English (Translate)",
            "Auto Detect",
            "Hindi",
            "Telugu",
            "Tamil",
            "Kannada",
            "Malayalam",
            "Bengali",
            "Marathi",
            "Gujarati",
            "Punjabi",
            "Urdu"
        ],
        index=0
    )

    st.divider()
    st.header("🔤 Font Settings")

    font = st.selectbox(
        "Font family",
        [
            "Noto Sans",
            "Arial",
            "DejaVu Sans",
            "Liberation Sans",
            "Montserrat",
            "Roboto",
            "Poppins",
            "Impact",
            "Georgia"
        ]
    )

    font_size = st.slider(
        "Font size",
        18, 80, 48
    )

    bold = st.toggle("Bold font", True)
    uppercase = st.toggle("Uppercase text", False)

    st.divider()
    st.header("🎨 Caption Appearance")

    text_color = st.color_picker(
        "Text colour", "#FFFFFF"
    )

    outline_color = st.color_picker(
        "Outline colour", "#000000"
    )

    outline = st.slider(
        "Outline thickness", 0, 10, 3
    )

    position = st.selectbox(
        "Caption position",
        ["Bottom", "Middle", "Top"]
    )

    background = st.toggle(
        "Caption background", False
    )

    background_color = st.color_picker(
        "Caption background colour", "#151515"
    )

    shadow = st.slider(
        "Caption shadow", 0, 5, 2
    )

    st.divider()
    st.header("🎵 Audio Settings")

    source_volume = st.slider(
        "Original audio volume",
        0.0, 2.0, 1.0
    )

    music_volume = st.slider(
        "Background music volume",
        0.0, 2.0, 0.25
    )

    st.divider()
    st.header("⚡ Export Settings")

    quality = st.selectbox(
        "Video quality",
        ["Fast", "Balanced", "High"],
        index=1
    )

    model_name = st.selectbox(
        "Subtitle AI model",
        ["small", "base", "tiny", "medium"],
        index=0
    )


# =====================================================
# CONFIGURATION
# =====================================================

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
    "preset": {
        "Fast": "ultrafast",
        "Balanced": "veryfast",
        "High": "fast"
    }[quality],
    "crf": {
        "Fast": 27,
        "Balanced": 23,
        "High": 19
    }[quality]
}


# =====================================================
# VIDEO SOURCE
# =====================================================

video_col, music_col = st.columns([1.25, 1])

with video_col:
    st.subheader("📁 Video Source")

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

        st.caption(
            "Google Drive: Anyone with the link → Viewer."
        )

    elif source_type == "Upload video":
        video_upload = st.file_uploader(
            "Upload video",
            type=["mp4", "mov", "mkv", "webm", "avi", "m4v"]
        )

    else:
        video_url = st.text_input(
            "YouTube URL",
            placeholder="Paste YouTube video link"
        )


with music_col:
    st.subheader("🎵 Background Music")

    music_upload = st.file_uploader(
        "Upload music (optional)",
        type=["mp3", "wav", "m4a", "aac", "ogg", "flac"]
    )

    st.caption("Use music you have permission to use.")


# =====================================================
# GENERATE CLIPS
# =====================================================

st.subheader("🚀 Generate Your Clips")

if st.button(
    "GENERATE CLIPS",
    type="primary",
    use_container_width=True
):

    if source_type == "Upload video" and video_upload is None:
        st.error("Please upload a video.")
        st.stop()

    if source_type != "Upload video":
        if not video_url.strip().startswith(("https://", "http://")):
            st.error("Please enter a valid video link.")
            st.stop()

    if not check_ffmpeg():
        st.error("FFmpeg or FFprobe is missing. Check packages.txt.")
        st.stop()

    work = Path(
        tempfile.mkdtemp(prefix="clipshort_")
    )

    try:
        with st.status(
            "Processing your video...",
            expanded=True
        ) as status:

            # DOWNLOAD SOURCE

            if source_type == "Google Drive":
                st.write("Downloading Google Drive video...")
                source = download_drive(video_url, work)

            elif source_type == "YouTube":
                st.write("Downloading YouTube video...")
                source = download_youtube(video_url, work)

            else:
                source = work / (
                    "uploaded_video"
                    + Path(video_upload.name).suffix.lower()
                )

                with source.open("wb") as file:
                    shutil.copyfileobj(
                        video_upload,
                        file,
                        length=8 * 1024 * 1024
                    )

            # MUSIC

            music = None

            if music_upload is not None:
                music = work / (
                    "background_music"
                    + Path(music_upload.name).suffix.lower()
                )

                with music.open("wb") as file:
                    shutil.copyfileobj(
                        music_upload,
                        file,
                        length=1024 * 1024
                    )

            # DURATION

            total = get_duration(source)

            if total <= 0:
                raise RuntimeError("Could not detect video duration.")

            st.write(
                f"Video duration: {total / 60:.1f} minutes"
            )

            # SUBTITLES

            if subtitles:
                st.write(
                    f"Generating subtitles in {language}..."
                )

                segments = transcribe_video(
                    source,
                    model_name,
                    language
                )
            else:
                segments = []

            # CLIP SELECTION

            starts = choose_clip_starts(
                segments,
                total,
                min(float(clip_length), total),
                clip_count
            )

            output_dir = work / "clips"
            output_dir.mkdir()

            progress = st.progress(0)

            # RENDER

            for index, start in enumerate(starts, 1):
                length = min(
                    float(clip_length),
                    total - start
                )

                if length <= 0:
                    continue

                st.write(
                    f"Rendering clip {index} of {len(starts)}..."
                )

                render_clip(
                    source,
                    output_dir / f"clip_{index:02d}.mp4",
                    start,
                    length,
                    segments,
                    cfg,
                    music
                )

                progress.progress(index / len(starts))

            # ZIP DOWNLOAD

            clips = sorted(
                output_dir.glob("*.mp4")
            )

            if not clips:
                raise RuntimeError("No clips were generated.")

            zip_path = work / "CLIPSHORT_AI.zip"

            with zipfile.ZipFile(
                zip_path,
                "w",
                zipfile.ZIP_DEFLATED
            ) as archive:

                for clip in clips:
                    archive.write(
                        clip,
                        arcname=clip.name
                    )

            zip_data = zip_path.read_bytes()

            status.update(
                label="Processing completed!",
                state="complete"
            )

        st.success(
            f"Successfully generated {len(clips)} clips!"
        )

        st.download_button(
            "⬇️ DOWNLOAD ALL CLIPS",
            data=zip_data,
            file_name="CLIPSHORT_AI.zip",
            mime="application/zip",
            use_container_width=True
        )

        st.subheader("🎥 Clip Previews")

        columns = st.columns(
            min(3, len(clips))
        )

        for index, clip in enumerate(clips):
            with columns[index % len(columns)]:
                st.caption(clip.name)
                st.video(str(clip))

    except Exception as error:
        st.error(f"Processing error: {error}")

        st.info(
            "Check video permissions, FFmpeg, server storage "
            "and available memory. Try a shorter video or "
            "the tiny subtitle model if processing is too slow."
        )

    finally:
        # Keep files available for previews in this session.
        pass


# =====================================================
# FOOTER
# =====================================================

st.divider()

st.caption(
    "CLIPSHORT AI · Professional Video Editing Studio"
)
