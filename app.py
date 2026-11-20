import streamlit as st
import subprocess
import tempfile
import shutil
import zipfile
import re
import os
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import gdown
import yt_dlp

# --------------------------------------------------
# APP CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="CLIPSHORT AI",
    page_icon="🎬",
    layout="wide"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;800&display=swap');

html,body,[class*="css"] {
    font-family:'DM Sans',sans-serif;
}

.stApp {
    background:linear-gradient(135deg,#080d19,#15162e);
    color:white;
}

[data-testid="stSidebar"] {
    background:#0c1424;
    border-right:1px solid #293653;
}

.block-container {
    max-width:1400px;
    padding-top:2rem;
}

.hero {
    background:linear-gradient(120deg,#182944,#30204d);
    border:1px solid #39466a;
    border-radius:20px;
    padding:25px;
    margin-bottom:25px;
}

.hero h1 {
    font-size:38px;
    font-weight:800;
    margin:0;
}

.hero p {
    color:#b5c3df;
}

div.stButton>button,
div.stDownloadButton>button {
    background:linear-gradient(90deg,#6255e8,#984fe8);
    color:white;
    border:0;
    border-radius:10px;
    font-weight:700;
    min-height:45px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
<h1>🎬 CLIPSHORT AI</h1>
<p>AI Video Clipping Studio · Captions · Music · YouTube Shorts</p>
</div>
""", unsafe_allow_html=True)


# --------------------------------------------------
# SYSTEM COMMAND
# --------------------------------------------------

def run_command(args):
    process = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if process.returncode != 0:
        raise RuntimeError(process.stderr[-2500:])

    return process.stdout.strip()


def check_ffmpeg():
    return (
        shutil.which("ffmpeg") is not None
        and shutil.which("ffprobe") is not None
    )


def get_duration(path):
    result = run_command([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ])

    return float(result)


def has_audio(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            str(path)
        ],
        capture_output=True,
        text=True
    )

    return bool(result.stdout.strip())


# --------------------------------------------------
# GOOGLE DRIVE
# --------------------------------------------------

def get_drive_id(url):
    parsed = urlparse(url.strip())

    match = re.search(
        r"/file/d/([A-Za-z0-9_-]+)",
        parsed.path
    )

    if match:
        return match.group(1)

    values = parse_qs(parsed.query)

    if values.get("id"):
        return values["id"][0]

    raise ValueError("Invalid Google Drive file link.")


def download_drive(url, folder):
    file_id = get_drive_id(url)

    target = folder / "drive_video"

    result = gdown.download(
        id=file_id,
        output=str(target),
        quiet=False
    )

    if not result or not Path(result).exists():
        raise RuntimeError(
            "Google Drive download failed. "
            "Set sharing to Anyone with the link - Viewer."
        )

    if Path(result).stat().st_size == 0:
        raise RuntimeError("Downloaded file is empty.")

    return Path(result)


# --------------------------------------------------
# YOUTUBE
# --------------------------------------------------

def download_youtube(url, folder):
    options = {
        "format": "best[height<=720]/best",
        "outtmpl": str(folder / "youtube.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 2
    }

    with yt_dlp.YoutubeDL(options) as downloader:
        downloader.download([url])

    files = list(folder.glob("youtube.*"))

    if not files:
        raise RuntimeError(
            "YouTube blocked the download. "
            "Try Google Drive or a permitted public video."
        )

    return files[0]


# --------------------------------------------------
# WHISPER COMPATIBILITY FIX
# --------------------------------------------------

@st.cache_resource
def get_whisper(model_name):

    import av

    # Compatibility wrapper for metadata_errors.
    # Older Faster-Whisper versions may pass this
    # argument to PyAV versions that no longer accept it.

    original_open = av.open

    def compatible_open(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return original_open(*args, **kwargs)

    av.open = compatible_open

    from faster_whisper import WhisperModel

    return WhisperModel(
        model_name,
        device="cpu",
        compute_type="int8"
    )


# --------------------------------------------------
# AUTOMATIC SUBTITLES
# --------------------------------------------------

def transcribe_video(path, model_name, language):

    model = get_whisper(model_name)

    options = {
        "beam_size": 2,
        "vad_filter": True
    }

    if language != "Auto":
        options["language"] = language.lower()

    segments, info = model.transcribe(
        str(path),
        **options
    )

    return [
        {
            "start": float(segment.start),
            "end": float(segment.end),
            "text": segment.text.strip()
        }
        for segment in segments
        if segment.text.strip()
    ]


# --------------------------------------------------
# CLIP SELECTION
# --------------------------------------------------

def choose_clips(segments, total, clip_length, count):

    if total <= clip_length:
        return [0.0]

    step = max(3, min(clip_length / 4, 8))
    candidates = []

    start = 0.0

    while start + clip_length <= total:

        end = start + clip_length

        score = sum(
            max(
                0,
                min(segment["end"], end)
                - max(segment["start"], start)
            )
            for segment in segments
        )

        candidates.append((score, start))

        start += step

    candidates.sort(reverse=True)

    selected = []

    for score, start in candidates:

        if all(
            abs(start - previous) >= clip_length * 0.7
            for previous in selected
        ):
            selected.append(start)

        if len(selected) >= count:
            break

    return sorted(selected or [0.0])


# --------------------------------------------------
# SUBTITLE FILE
# --------------------------------------------------

def ass_time(value):

    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = value % 60

    return f"{hours}:{minutes:02d}:{seconds:05.2f}"


def ass_color(value):

    value = value.lstrip("#")

    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        value = "FFFFFF"

    red = value[0:2]
    green = value[2:4]
    blue = value[4:6]

    return f"&H00{blue}{green}{red}&".upper()


def create_subtitles(
    subtitle_file,
    segments,
    clip_start,
    clip_end,
    settings
):

    alignment = {
        "Bottom": 2,
        "Middle": 5,
        "Top": 8
    }[settings["position"]]

    bold = -1 if settings["bold"] else 0

    border = 3 if settings["box"] else 1

    outline = 0 if settings["box"] else settings["outline"]

    font = settings["font"].replace(",", " ")

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font},{settings['size']},{ass_color(settings['color'])},&H000000FF&,{ass_color(settings['outline_color'])},{ass_color(settings['box_color'])},{bold},0,0,0,100,100,0,0,{border},{outline},{settings['shadow']},{alignment},60,60,90,1",
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
            .replace("{", r"\{")
            .replace("}", r"\}")
            .replace("\n", " ")
        )

        if settings["uppercase"]:
            caption = caption.upper()

        lines.append(
            f"Dialogue: 0,{ass_time(start-clip_start)},"
            f"{ass_time(end-clip_start)},Default,,0,0,0,,{caption}"
        )

    subtitle_file.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )


# --------------------------------------------------
# VIDEO RENDERING
# --------------------------------------------------

def render_clip(
    source,
    output,
    start,
    length,
    segments,
    settings,
    music
):

    filters = [
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920",
        "setsar=1",
        "fps=30"
    ]

    subtitle_file = output.with_suffix(".ass")

    if settings["subtitles"]:

        create_subtitles(
            subtitle_file,
            segments,
            start,
            start + length,
            settings
        )

        ass_path = (
            str(subtitle_file)
            .replace("\\", "/")
            .replace(":", r"\:")
        )

        filters.append(f"ass='{ass_path}'")

    args = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-i", str(source)
    ]

    if music:
        args += [
            "-stream_loop", "-1",
            "-i", str(music)
        ]

    args += [
        "-t", str(length),
        "-vf", ",".join(filters),
        "-c:v", "libx264",
        "-preset", settings["preset"],
        "-crf", str(settings["crf"]),
        "-pix_fmt", "yuv420p"
    ]

    audio = has_audio(source)

    if music and audio:

        args += [
            "-filter_complex",
            (
                f"[0:a]volume={settings['source_volume']}[a0];"
                f"[1:a]volume={settings['music_volume']}[a1];"
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
            "-af", f"volume={settings['music_volume']}",
            "-c:a", "aac"
        ]

    elif audio:

        args += [
            "-af", f"volume={settings['source_volume']}",
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


# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------

with st.sidebar:

    st.header("⚙️ Editing settings")

    clip_count = st.slider(
        "Maximum clips",
        1, 30, 5
    )

    clip_length = st.slider(
        "Clip length (seconds)",
        10, 90, 30
    )

    st.divider()

    st.subheader("Caption settings")

    subtitles = st.toggle(
        "Automatic subtitles",
        True
    )

    font = st.selectbox(
        "Font",
        [
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
        "Font size", 18, 80, 48
    )

    text_color = st.color_picker(
        "Text colour", "#FFFFFF"
    )

    outline_color = st.color_picker(
        "Outline colour", "#000000"
    )

    outline = st.slider(
        "Outline thickness", 0, 8, 3
    )

    position = st.selectbox(
        "Caption position",
        ["Bottom", "Middle", "Top"]
    )

    bold = st.toggle("Bold captions", True)

    uppercase = st.toggle(
        "Uppercase captions", False
    )

    box = st.toggle(
        "Caption background", False
    )

    box_color = st.color_picker(
        "Background colour", "#151515"
    )

    shadow = st.slider(
        "Caption shadow", 0, 5, 2
    )

    st.divider()

    st.subheader("Audio settings")

    source_volume = st.slider(
        "Original audio", 0.0, 2.0, 1.0
    )

    music_volume = st.slider(
        "Music volume", 0.0, 2.0, 0.25
    )

    st.divider()

    quality = st.selectbox(
        "Export quality",
        ["Fast", "Balanced", "High"]
    )

    model_name = st.selectbox(
        "Whisper model",
        ["tiny", "base", "small"]
    )

    language = st.selectbox(
        "Subtitle language",
        [
            "Auto",
            "English",
            "Hindi",
            "Telugu",
            "Tamil",
            "Kannada",
            "Malayalam"
        ]
    )


settings = {
    "subtitles": subtitles,
    "font": font,
    "size": font_size,
    "color": text_color,
    "outline_color": outline_color,
    "outline": outline,
    "position": position,
    "bold": bold,
    "uppercase": uppercase,
    "box": box,
    "box_color": box_color,
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


# --------------------------------------------------
# MAIN VIDEO SOURCE
# --------------------------------------------------

video_col, music_col = st.columns([1.3, 1])

with video_col:

    st.subheader("📁 Video source")

    source_type = st.radio(
        "Select source",
        ["Google Drive", "Upload video", "YouTube"],
        horizontal=True
    )

    video_upload = None
    video_url = ""

    if source_type == "Google Drive":

        video_url = st.text_input(
            "Google Drive link",
            placeholder="Paste Drive sharing link"
        )

        st.caption(
            "Sharing must be Anyone with the link - Viewer."
        )

    elif source_type == "Upload video":

        video_upload = st.file_uploader(
            "Upload video",
            type=[
                "mp4", "mov", "mkv",
                "webm", "avi", "m4v"
            ]
        )

    else:

        video_url = st.text_input(
            "YouTube video URL"
        )

        st.caption(
            "YouTube may block cloud-server downloads."
        )


with music_col:

    st.subheader("🎵 Background music")

    music_upload = st.file_uploader(
        "Upload music (optional)",
        type=[
            "mp3", "wav", "m4a",
            "aac", "ogg", "flac"
        ]
    )

    st.caption(
        "Use music that you have permission to use."
    )


# --------------------------------------------------
# GENERATE
# --------------------------------------------------

st.subheader("🚀 Generate your clips")

if st.button(
    "GENERATE CLIPS",
    type="primary",
    use_container_width=True
):

    if source_type == "Upload video" and video_upload is None:
        st.error("Upload a video first.")
        st.stop()

    if source_type != "Upload video" and not video_url.startswith(("http://", "https://")):
        st.error("Enter a valid video link.")
        st.stop()

    if not check_ffmpeg():
        st.error("FFmpeg or FFprobe is missing.")
        st.stop()

    work = Path(
        tempfile.mkdtemp(prefix="clipshort_")
    )

    try:

        with st.status(
            "Processing video...",
            expanded=True
        ) as status:

            # DOWNLOAD SOURCE

            if source_type == "Google Drive":

                st.write(
                    "Downloading Google Drive video to server disk..."
                )

                source = download_drive(
                    video_url, work
                )

            elif source_type == "YouTube":

                st.write(
                    "Downloading YouTube video..."
                )

                source = download_youtube(
                    video_url, work
                )

            else:

                source = work / (
                    "source" +
                    Path(video_upload.name).suffix
                )

                with source.open("wb") as file:
                    shutil.copyfileobj(
                        video_upload,
                        file,
                        8 * 1024 * 1024
                    )

            # MUSIC

            music = None

            if music_upload:

                music = work / (
                    "music" +
                    Path(music_upload.name).suffix
                )

                with music.open("wb") as file:
                    shutil.copyfileobj(
                        music_upload,
                        file
                    )

            # DURATION

            total = get_duration(source)

            if total <= 0:
                raise RuntimeError(
                    "Invalid video duration."
                )

            st.write(
                f"Video duration: {total/60:.1f} minutes"
            )

            # SUBTITLES

            if subtitles:

                st.write(
                    "Generating automatic subtitles..."
                )

                segments = transcribe_video(
                    source,
                    model_name,
                    language
                )

            else:

                segments = []

            # SELECT CLIPS

            starts = choose_clips(
                segments,
                total,
                min(clip_length, total),
                clip_count
            )

            output_dir = work / "clips"
            output_dir.mkdir()

            progress = st.progress(0)

            # RENDER CLIPS

            for index, start in enumerate(
                starts, 1
            ):

                length = min(
                    clip_length,
                    total - start
                )

                if length <= 0:
                    continue

                st.write(
                    f"Creating clip {index}/{len(starts)}"
                )

                render_clip(
                    source,
                    output_dir / f"clip_{index:02d}.mp4",
                    start,
                    length,
                    segments,
                    settings,
                    music
                )

                progress.progress(
                    index / len(starts)
                )

            # ZIP

            clips = sorted(
                output_dir.glob("*.mp4")
            )

            if not clips:
                raise RuntimeError(
                    "No clips were created."
                )

            zip_path = work / "CLIPSHORT_AI.zip"

            with zipfile.ZipFile(
                zip_path,
                "w",
                zipfile.ZIP_DEFLATED
            ) as archive:

                for clip in clips:
                    archive.write(
                        clip,
                        clip.name
                    )

            zip_data = zip_path.read_bytes()

            status.update(
                label="Processing complete!",
                state="complete"
            )

        st.success(
            f"{len(clips)} clips created!"
        )

        st.download_button(
            "⬇️ DOWNLOA
