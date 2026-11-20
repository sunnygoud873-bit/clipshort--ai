import os
import re
import shutil
import tempfile
import subprocess
import zipfile
import logging

from pathlib import Path
from urllib.parse import urlparse

import gdown
import yt_dlp

from flask import Flask, request, render_template, send_file, jsonify
from werkzeug.utils import secure_filename
from faster_whisper import WhisperModel


# ==================================================
# CLIPSHORT AI CONFIGURATION
# ==================================================

app = Flask(__name__, template_folder=".")
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path("/tmp/clipshort_jobs")
BASE_DIR.mkdir(parents=True, exist_ok=True)

MODEL_NAME = os.getenv("WHISPER_MODEL", "tiny")

COOKIES_FILE = os.getenv(
    "YOUTUBE_COOKIES_FILE",
    "/etc/secrets/youtube_cookies.txt"
)

whisper_model = None

VIDEO_EXT = {
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"
}

AUDIO_EXT = {
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"
}

FONTS = {
    "Arial", "DejaVu Sans", "Liberation Sans",
    "Montserrat", "Roboto", "Poppins", "Impact", "Georgia"
}


# ==================================================
# SYSTEM FUNCTIONS
# ==================================================

def run_command(command):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            (result.stderr or result.stdout or "Command failed")[-3000:]
        )

    return result.stdout.strip()


def get_model():
    global whisper_model

    if whisper_model is None:
        whisper_model = WhisperModel(
            MODEL_NAME,
            device="cpu",
            compute_type="int8"
        )

    return whisper_model


def get_duration(video):
    value = run_command([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video)
    ])

    return float(value)


def has_audio(video):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            str(video)
        ],
        capture_output=True,
        text=True
    )

    return result.returncode == 0 and bool(result.stdout.strip())


def form_int(name, default, minimum, maximum):
    try:
        value = int(request.form.get(name, default))
    except (ValueError, TypeError):
        value = default

    return max(minimum, min(maximum, value))


# ==================================================
# VIDEO DOWNLOAD
# ==================================================

def download_video(upload, url, folder):

    if upload and upload.filename:

        ext = Path(
            secure_filename(upload.filename)
        ).suffix.lower()

        if ext not in VIDEO_EXT:
            raise ValueError("Unsupported video format.")

        destination = folder / ("source" + ext)
        upload.save(destination)

        if not destination.exists() or destination.stat().st_size == 0:
            raise RuntimeError("Uploaded video is empty.")

        return destination

    if not url:
        raise ValueError("Upload a video or enter a video URL.")

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Invalid video URL.")

    youtube_hosts = {
        "youtube.com", "www.youtube.com",
        "m.youtube.com", "youtu.be", "www.youtu.be"
    }

    drive_hosts = {
        "drive.google.com", "www.drive.google.com",
        "docs.google.com"
    }

    # YOUTUBE
    if host in youtube_hosts:

        options = {
            "format": "best[ext=mp4]/best",
            "outtmpl": str(folder / "source.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": False,
            "merge_output_format": "mp4",
            "socket_timeout": 45,
            "retries": 3,
            "extractor_retries": 3,
            "fragment_retries": 3
        }

        if os.path.isfile(COOKIES_FILE):
            options["cookiefile"] = COOKIES_FILE

        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                downloader.download([url])

        except Exception as error:
            raise RuntimeError(
                "YouTube download failed. YouTube may require valid "
                "cookies or may block the server. " + str(error)
            ) from error

        files = [
            p for p in folder.glob("source.*")
            if p.is_file()
            and p.suffix.lower() not in {".part", ".ytdl"}
        ]

        if not files:
            raise RuntimeError("YouTube did not return a video file.")

        return files[0]

    # GOOGLE DRIVE
    if host in drive_hosts:

        destination = folder / "source"

        try:
            result = gdown.download(
                url=url,
                output=str(destination),
                quiet=True
            )

        except Exception as error:
            raise RuntimeError(
                "Google Drive download failed: " + str(error)
            ) from error

        if not result:
            raise RuntimeError(
                "Google Drive download failed. "
                "Set sharing to Anyone with the link."
            )

        downloaded = Path(result)

        if not downloaded.exists() or downloaded.stat().st_size == 0:
            raise RuntimeError("Google Drive file is empty.")

        return downloaded

    raise ValueError(
        "Use YouTube, public Google Drive, or upload a video."
    )


# ==================================================
# MUSIC UPLOAD
# ==================================================

def get_music(upload, folder):

    if not upload or not upload.filename:
        return None

    ext = Path(
        secure_filename(upload.filename)
    ).suffix.lower()

    if ext not in AUDIO_EXT:
        raise ValueError("Unsupported music format.")

    destination = folder / ("music" + ext)
    upload.save(destination)

    if not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError("Music file is empty.")

    return destination


# ==================================================
# AI TRANSCRIPTION
# ==================================================

def transcribe(video):

    segments, _ = get_model().transcribe(
        str(video),
        vad_filter=True
    )

    result = []

    for segment in segments:
        result.append({
            "start": float(segment.start),
            "end": float(segment.end),
            "text": segment.text.strip()
        })

    return result


# ==================================================
# SUBTITLE FUNCTIONS
# ==================================================

def ass_color(value, default):

    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value or ""):
        value = default

    value = value.lstrip("#")

    return (
        "&H00" + value[4:6] + value[2:4] + value[0:2]
    ).upper()


def ass_time(seconds):

    cs = max(0, int(seconds * 100))

    hours, remainder = divmod(cs, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)

    return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"


def create_subtitles(filename, segments, start, end, settings):

    font = settings["font"]
    size = settings["font_size"]

    alignment = {
        "bottom": 2,
        "middle": 5,
        "top": 8
    }.get(settings["position"], 2)

    bold = -1 if settings["bold"] else 0
    margin = 90 if alignment != 5 else 0

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, "
        "SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font},{size},"
        f"{ass_color(settings['font_color'], '#FFFFFF')},"
        f"&H000000FF,"
        f"{ass_color(settings['outline_color'], '#000000')},"
        f"&H80000000,{bold},0,0,0,100,100,0,0,1,"
        f"{settings['outline']},1,{alignment},55,55,{margin},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, "
        "MarginL, MarginR, MarginV, Effect, Text"
    ]

    for segment in segments:

        s = max(start, segment["start"])
        e = min(end, segment["end"])

        if e <= s:
            continue

        text = segment["text"].strip()

        if settings["uppercase"]:
            text = text.upper()

        text = (
            text.replace("{", r"\{")
            .replace("}", r"\}")
            .replace("\n", " ")
        )

        if text:
            lines.append(
                f"Dialogue: 0,{ass_time(s-start)},"
                f"{ass_time(e-start)},Default,,0,0,0,,{text}"
            )

    filename.write_text("\n".join(lines), encoding="utf-8")


# ==================================================
# CLIP SELECTION
# ==================================================

def choose_clips(segments, total, count, length):

    length = min(float(length), total)
    step = max(1.0, length / 3.0)

    candidates = []
    position = 0.0

    while position < total:

        end = min(total, position + length)

        score = sum(
            max(
                0.0,
                min(s["end"], end) - max(s["start"], position)
            )
            for s in segments
        )

        candidates.append((score, position))
        position += step

    candidates.sort(key=lambda x: x[0], reverse=True)

    selected = []

    for _score, position in candidates:

        if all(
            abs(position - old) >= length * 0.7
            for old in selected
        ):
            selected.append(position)

        if len(selected) >= count:
            break

    return sorted(selected or [0.0])


# ==================================================
# VIDEO CLIP CREATION
# ==================================================

def create_clip(
    source,
    output,
    start,
    length,
    segments,
    settings,
    music
):

    video_filter = (
        "scale=1080:1920:"
        "force_original_aspect_ratio=increase,"
        "crop=1080:1920"
    )

    subtitle_file = output.with_suffix(".ass")

    if settings["subtitles"]:

        create_subtitles(
            subtitle_file,
            segments,
            start,
            start + length,
            settings
        )

        subtitle_path = (
            str(subtitle_file)
            .replace("\\", "/")
            .replace(":", r"\:")
            .replace("'", r"\'")
        )

        video_filter += f",ass='{subtitle_path}'"

    source_audio = has_audio(source)

    original_volume = settings["original_volume"] / 100
    music_volume = settings["music_volume"] / 100

    command = [
        "ffmpeg", "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-ss", str(start),
        "-i", str(source)
    ]

    use_music = music is not None and music_volume > 0

    if use_music:

        command += [
            "-stream_loop", "-1",
            "-i", str(music)
        ]

        if source_audio and original_volume > 0:

            audio_filter = (
                f"[0:a:0]volume={original_volume}[original];"
                f"[1:a:0]volume={music_volume}[music];"
                "[original][music]"
                "amix=inputs=2:duration=first:"
                "dropout_transition=2[aout]"
            )

        else:

            audio_filter = (
                f"[1:a:0]volume={music_volume}[aout]"
            )

        command += [
            "-filter_complex", audio_filter,
            "-map", "0:v:0",
            "-map", "[aout]"
        ]

    else:

        command += ["-map", "0:v:0"]

        if source_audio and original_volume > 0:

            command += [
                "-map", "0:a:0",
                "-af", f"volume={original_volume}"
            ]

        else:
            command += ["-an"]

    command += [
        "-t", str(length),
        "-vf", video_filter,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output)
    ]

    run_command(command)

    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("FFmpeg failed to create clip.")

    if subtitle_file.exists():
        subtitle_file.unlink()


# ==================================================
# FORM SETTINGS
# ==================================================

def get_settings():

    font = request.form.get("font", "Arial")

    if font not in FONTS:
        font = "Arial"

    position = request.form.get("position", "bottom")

    if position not in {"bottom", "middle", "top"}:
        position = "bottom"

    font_color = request.form.get("font_color", "#FFFFFF")
    outline_color = request.form.get("outline_color", "#000000")

    if not re.fullmatch(r"#[0-9a-fA-F]{6}", font_color):
        font_color = "#FFFFFF"

    if not re.fullmatch(r"#[0-9a-fA-F]{6}", outline_color):
        outline_color = "#000000"

    return {
        "subtitles": request.form.get("subtitles") == "on",
        "font": font,
        "font_size": form_int("font_size", 42, 16, 90),
        "font_color": font_color,
        "outline_color": outline_color,
        "outline": form_int("outline", 3, 0, 8),
        "position": position,
        "bold": request.form.get("bold") == "on",
        "uppercase": request.form.get("uppercase") == "on",
        "music_volume": form_int("music_volume", 25, 0, 100),
        "original_volume": form_int("original_volume", 100, 0, 100)
    }


# ==================================================
# FLASK ROUTES
# ==================================================

@app.get("/")
def home():
    return render_template("index.html", error=None)


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "app": "CLIPSHORT AI"
    })


@app.post("/generate")
def generate():

    folder = None

    try:

        clip_count = form_int("clip_count", 5, 1, 30)
        clip_length = form_int("clip_length", 30, 5, 90)

        settings = get_settings()

        folder = Path(
            tempfile.mkdtemp(
                prefix="clipshort_",
                dir=str(BASE_DIR)
            )
        )

        # VIDEO
        source = download_video(
            request.files.get("video"),
            request.form.get("source_url", "").strip(),
            folder
        )

        # MUSIC
        music = get_music(
            request.files.get("music"),
            folder
        )

        # DURATION
        total = get_duration(source)

        if total < 5:
            raise ValueError("Video must be at least 5 seconds long.")

        clip_length = min(float(clip_length), total)

        # TRANSCRIPTION
        segments = transcribe(source)

        # CLIP SELECTION
        positions = choose_clips(
            segments,
            total,
            clip_count,
            clip_length
        )

        outputs = []

        for number, position in enumerate(positions, start=1):

            duration = min(clip_length, total - position)

            if duration <= 0:
                continue

            output = folder / f"clip_{number:02}.mp4"

            create_clip(
                source,
                output,
                position,
                duration,
                segments,
                settings,
                music
            )

            outputs.append(output)

        if not outputs:
            raise RuntimeError("No clips generated.")

        # ZIP EXPORT
        archive = folder / "clipshort_exports.zip"

        with zipfile.ZipFile(
            archive,
            "w",
            zipfile.ZIP_DEFLATED
        ) as zip_file:

            for output in outputs:
                zip_file.write(output, output.name)

        response = send_file(
            archive,
            as_attachment=True,
            download_name="clipshort_ai_clips.zip",
            mimetype="application/zip"
        )

        response.call_on_close(
            lambda: shutil.rmtree(folder, ignore_errors=True)
        )

        return response

    except Exception as error:

        app.logger.exception("Clip generation failed")

        message = f"Clip generation error: {error}"

        return render_template(
            "index.html",
            error=message
        ), 400


# ==================================================
# START SERVER
# ==================================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", "10000"))

    app.run(
        host="0.0.0.0",
        port=port
    )
    
