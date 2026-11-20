
import streamlit as st
import subprocess
import tempfile
import shutil
import zipfile
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import gdown
import yt_dlp

st.set_page_config(
    page_title="CLIPSHORT AI",
    page_icon="🎬",
    layout="wide"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;800&display=swap');
html,body,[class*="css"] {font-family:'DM Sans',sans-serif;}
.stApp {
 background:linear-gradient(135deg,#080d19,#15162e);
 color:#ffffff;
}
[data-testid="stSidebar"] {
 background:#0c1424;
 border-right:1px solid #293653;
}
.block-container {max-width:1400px;padding-top:2rem;}
.hero {
 background:linear-gradient(120deg,#182944,#30204d);
 border:1px solid #39466a;
 border-radius:20px;
 padding:25px;
 margin-bottom:25px;
}
.hero h1 {font-size:38px;font-weight:800;margin:0;}
.hero p {color:#b5c3df;}
div.stButton>button,div.stDownloadButton>button {
 background:linear-gradient(90deg,#6255e8,#984fe8);
 color:white;border:0;border-radius:10px;
 font-weight:700;min-height:45px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
<h1>🎬 CLIPSHORT AI</h1>
<p>AI Video Clipping Studio · Captions · Music · Shorts</p>
</div>
""", unsafe_allow_html=True)


def run(args):
    p = subprocess.run(
        args, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True
    )
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])
    return p.stdout.strip()


def drive_id(url):
    p = urlparse(url)
    match = re.search(r"/file/d/([^/]+)", p.path)
    if match:
        return match.group(1)
    values = parse_qs(p.query)
    if values.get("id"):
        return values["id"][0]
    raise ValueError("Invalid Google Drive sharing link")


def download_drive(url, folder):
    file_id = drive_id(url)
    target = folder / "drive_video"
    result = gdown.download(
        id=file_id,
        output=str(target),
        quiet=False
    )
    if not result or not Path(result).exists():
        raise RuntimeError(
            "Google Drive download failed. "
            "Set sharing to Anyone with the link."
        )
    return Path(result)


def download_youtube(url, folder):
    options = {
        "format": "best[height<=720]/best",
        "outtmpl": str(folder / "youtube.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    files = list(folder.glob("youtube.*"))
    if not files:
        raise RuntimeError(
            "YouTube blocked the download. "
            "Try another permitted video or Google Drive."
        )
    return files[0]


def duration(path):
    return float(run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]))


def has_audio(path):
    p = subprocess.run([
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0", str(path)
    ], capture_output=True, text=True)
    return bool(p.stdout.strip())


@st.cache_resource
def get_whisper(model_name):
    from faster_whisper import WhisperModel
    return WhisperModel(
        model_name, device="cpu", compute_type="int8"
    )


def transcribe(path, model_name, language):
    model = get_whisper(model_name)
    options = {"vad_filter": True, "beam_size": 2}
    if language != "Auto":
        options["language"] = language.lower()

    segments, _ = model.transcribe(str(path), **options)
    return [
        {
            "start": float(s.start),
            "end": float(s.end),
            "text": s.text.strip()
        }
        for s in segments if s.text.strip()
    ]


def select_clips(segments, total, length, count):
    if total <= length:
        return [0.0]

    step = max(3, min(length / 4, 8))
    candidates = []
    t = 0.0

    while t + length <= total:
        end = t + length
        score = sum(
            max(0, min(s["end"], end) - max(s["start"], t))
            for s in segments
        )
        candidates.append((score, t))
        t += step

    candidates.sort(reverse=True)
    chosen = []

    for score, start in candidates:
        if all(abs(start - old) >= length * 0.7 for old in chosen):
            chosen.append(start)
        if len(chosen) >= count:
            break

    return sorted(chosen or [0.0])


def ass_time(value):
    h = int(value // 3600)
    m = int((value % 3600) // 60)
    s = value % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_color(value):
    value = value.lstrip("#")
    r, g, b = value[:2], value[2:4], value[4:6]
    return f"&H00{b}{g}{r}&".upper()


def make_subtitles(path, segments, start, end, cfg):
    alignment = {"Bottom": 2, "Middle": 5, "Top": 8}[cfg["position"]]
    bold = -1 if cfg["bold"] else 0
    border = 3 if cfg["box"] else 1
    outline = 0 if cfg["box"] else cfg["outline"]

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{cfg['font']},{cfg['size']},{ass_color(cfg['color'])},&H000000FF&,{ass_color(cfg['outline_color'])},{ass_color(cfg['box_color'])},{bold},0,0,0,100,100,0,0,{border},{outline},{cfg['shadow']},{alignment},60,60,90,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]

    for seg in segments:
        a = max(start, seg["start"])
        b = min(end, seg["end"])
        if b <= a:
            continue

        caption = seg["text"].replace("{", r"\{").replace("}", r"\}")
        if cfg["uppercase"]:
            caption = caption.upper()

        lines.append(
            f"Dialogue: 0,{ass_time(a-start)},{ass_time(b-start)},Default,,0,0,0,,{caption}"
        )

    path.write_text("\n".join(lines), encoding="utf-8")


def render_clip(source, output, start, length, segments, cfg, music):
    filters = [
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920",
        "setsar=1",
        "fps=30"
    ]

    subtitle_file = output.with_suffix(".ass")

    if cfg["subtitles"]:
        make_subtitles(
            subtitle_file, segments, start,
            start + length, cfg
        )
        ass_path = str(subtitle_file).replace("\\", "/").replace(":", r"\:")
        filters.append(f"ass='{ass_path}'")

    args = [
        "ffmpeg", "-y", "-ss", str(start),
        "-i", str(source)
    ]

    if music:
        args += ["-stream_loop", "-1", "-i", str(music)]

    args += [
        "-t", str(length),
        "-vf", ",".join(filters),
        "-c:v", "libx264",
        "-preset", cfg["preset"],
        "-crf", str(cfg["crf"]),
        "-pix_fmt", "yuv420p"
    ]

    audio = has_audio(source)

    if music and audio:
        args += [
            "-filter_complex",
            f"[0:a]volume={cfg['source_volume']}[a0];"
            f"[1:a]volume={cfg['music_volume']}[a1];"
            "[a0][a1]amix=inputs=2:duration=first[aout]",
            "-map", "0:v:0", "-map", "[aout]",
            "-c:a", "aac"
        ]
    elif music:
        args += [
            "-map", "0:v:0", "-map", "1:a:0",
            "-af", f"volume={cfg['music_volume']}",
            "-c:a", "aac"
        ]
    elif audio:
        args += [
            "-af", f"volume={cfg['source_volume']}",
            "-c:a", "aac"
        ]
    else:
        args += ["-an"]

    args += ["-movflags", "+faststart", str(output)]
    run(args)


# SIDEBAR SETTINGS
with st.sidebar:
    st.header("⚙️ Editing settings")

    clip_count = st.slider("Maximum clips", 1, 30, 5)
    clip_length = st.slider("Clip length (seconds)", 10, 90, 30)

    st.divider()
    st.subheader("Caption settings")

    subtitles = st.toggle("Automatic subtitles", True)
    font = st.selectbox(
        "Font",
        ["Arial", "DejaVu Sans", "Liberation Sans",
         "Montserrat", "Roboto", "Poppins", "Impact", "Georgia"]
    )
    font_size = st.slider("Font size", 18, 80, 48)
    text_color = st.color_picker("Text colour", "#FFFFFF")
    outline_color = st.color_picker("Outline colour", "#000000")
    outline = st.slider("Outline thickness", 0, 8, 3)
    position = st.selectbox("Caption position", ["Bottom", "Middle", "Top"])
    bold = st.toggle("Bold captions", True)
    uppercase = st.toggle("Uppercase captions", False)
    box = st.toggle("Caption background", False)
    box_color = st.color_picker("Background colour", "#151515")
    shadow = st.slider("Caption shadow", 0, 5, 2)

    st.divider()
    st.subheader("Audio settings")
    source_volume = st.slider("Original audio", 0.0, 2.0, 1.0)
    music_volume = st.slider("Music volume", 0.0, 2.0, 0.25)

    st.divider()
    quality = st.selectbox("Export quality", ["Fast", "Balanced", "High"])
    model_name = st.selectbox("Whisper model", ["tiny", "base", "small"])
    language = st.selectbox(
        "Subtitle language",
        ["Auto", "English", "Hindi", "Telugu", "Tamil", "Kannada", "Malayalam"]
    )

cfg = {
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
    "preset": {"Fast": "ultrafast", "Balanced": "veryfast", "High": "fast"}[quality],
    "crf": {"Fast": 27, "Balanced": 23, "High": 19}[quality]
}

# MAIN SCREEN
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
        video_url = st.text_input("Google Drive link")
        st.caption("Set file sharing to Anyone with the link · Viewer.")

    elif source_type == "Upload video":
        video_upload = st.file_uploader(
            "Upload video",
            type=["mp4", "mov", "mkv", "webm", "avi", "m4v"]
        )

    else:
        video_url = st.text_input("YouTube video URL")

with music_col:
    st.subheader("🎵 Background music")
    music_upload = st.file_uploader(
        "Upload music (optional)",
        type=["mp3", "wav", "m4a", "aac", "ogg", "flac"]
    )
    st.caption("Use music that you have permission to use.")

st.subheader("🚀 Generate your clips")

if st.button("GENERATE CLIPS", type="primary", use_container_width=True):

    if source_type == "Upload video" and video_upload is None:
        st.error("Upload a video first.")
        st.stop()

    if source_type != "Upload video" and not video_url.startswith(("http://", "https://")):
        st.error("Enter a valid link.")
        st.stop()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        st.error("FFmpeg is missing. Check packages.txt.")
        st.stop()

    work = Path(tempfile.mkdtemp(prefix="clipshort_"))

    try:
        with st.status("Processing video...", expanded=True) as status:

            if source_type == "Google Drive":
                st.write("Downloading Google Drive video to server disk...")
                source = download_drive(video_url, work)

            elif source_type == "YouTube":
                st.write("Downloading YouTube video...")
                source = download_youtube(video_url, work)

            else:
                source = work / ("source" + Path(video_upload.name).suffix)
                with source.open("wb") as f:
                    shutil.copyfileobj(video_upload, f, 8 * 1024 * 1024)

            music = None
            if music_upload:
                music = work / ("music" + Path(music_upload.name).suffix)
                with music.open("wb") as f:
                    shutil.copyfileobj(music_upload, f)

            total = duration(source)
            if total <= 0:
                raise RuntimeError("Invalid video duration.")

            st.write(f"Video duration: {total/60:.1f} minutes")

            if subtitles:
                st.write("Generating automatic subtitles...")
                segments = transcribe(source, model_name, language)
            else:
                segments = []

            starts = select_clips(
                segments, total,
                min(clip_length, total),
                clip_count
            )

            output_dir = work / "clips"
            output_dir.mkdir()

            progress = st.progress(0)

            for i, start in enumerate(starts, 1):
                length = min(clip_length, total - start)
                if length <= 0:
                    continue

                st.write(f"Creating clip {i}/{len(starts)}")

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
                raise RuntimeError("No clips were created.")

            zip_path = work / "CLIPSHORT_AI.zip"

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                for clip in clips:
                    z.write(clip, clip.name)

            zip_data = zip_path.read_bytes()

            status.update(
                label="Video processing complete!",
                state="complete"
            )

        st.success(f"{len(clips)} clips created!")

        st.download_button(
            "⬇️ DOWNLOAD ALL CLIPS",
            zip_data,
            file_name="CLIPSHORT_AI.zip",
            mime="application/zip",
            use_container_width=True
        )

        st.subheader("Clip previews")
        columns = st.columns(min(3, len(clips)))

        for i, clip in enumerate(clips):
            with columns[i % len(columns)]:
                st.caption(clip.name)
                st.video(str(clip))

    except Exception as error:
        st.error(f"Processing error: {error}")
        st.info(
            "Try a smaller video or Whisper tiny. "
            "Check Drive sharing permissions and free-server limits."
        )

    finally:
        # Keep temporary files available for preview during this session.
        pass

st.divider()
st.caption("CLIPSHORT AI · Streamlit edition")
