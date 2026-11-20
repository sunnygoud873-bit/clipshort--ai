
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
import logging

from pathlib import Path
from urllib.parse import urlparse

import gdown
import yt_dlp

from flask import (
    Flask, request, render_template,
    send_file, jsonify
)
from werkzeug.utils import secure_filename
from faster_whisper import WhisperModel


# ==================================================
# CONFIGURATION
# ==================================================

app = Flask(__name__, template_folder=".")
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024

logging.basicConfig(level=logging.INFO)

JOBS = Path("/tmp/clipshort_jobs")
JOBS.mkdir(parents=True, exist_ok=True)

MODEL_NAME = os.getenv("WHISPER_MODEL", "tiny")
YOUTUBE_COOKIES = os.getenv(
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
# SYSTEM HELPERS
# ==================================================

def run_command(command):
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            (result.stderr or result.stdout)[-3000:]
        )

    return result.stdout.strip()


def get_whisper():
    global whisper_model

    if whisper_model is None:
        whisper_model = WhisperModel(
            MODEL_NAME,
            device="cpu",
            compute_type="int8"
        )

    return whisper_model


def get_duration(video):
    result = run_command([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video)
    ])

    return float(result or 0)


def has_audio(video):
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            str(video)
        ],
        capture_output=True,
        text=True
    )

    return bool(result.stdout.strip())


# ==================================================
# VIDEO IMPORT
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
        raise ValueError(
            "Upload a video or enter a video URL."
        )

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Invalid URL.")

    youtube_hosts = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "www.youtu.be"
    }

    drive_hosts = {
        "drive.google.com",
        "www.drive.google.com",
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

        if os.path.isfile(YOUTUBE_COOKIES):
            options["cookiefile"] = YOUTUBE_COOKIES

        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                downloader.download([url])

        except Exception as error:
            raise RuntimeError(
                f"YouTube download failed: {error}"
            ) from error

        files = [
            p for p in folder.glob("source.*")
            if p.is_file()
            and p.suffix not in {".part", ".ytdl"}
        ]

        if not files:
            raise RuntimeError(
                "YouTube did not provide a video. "
                "Check your cookies or upload the video directly."
            )

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
                f"Google Drive download failed: {error}"
            ) from error

        if not result:
            raise RuntimeError(
                "Google Drive download failed. "
                "Set sharing to Anyone with the link."
            )

        downloaded = Path(result)

        if not downloaded.exists() or downloaded.stat().st_size == 0:
            raise RuntimeError(
                "Google Drive returned an empty file."
            )

        return downloaded

    raise ValueError(
        "Use YouTube, Google Drive, or upload a video."
    )


# ==================================================
# BACKGROUND MUSIC
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
        raise ValueError("Music file is empty.")

    return destination


# ==================================================
# AUTOMATIC SUBTITLES
# ==================================================

def transcribe(video):

    segments, info = get_whisper().transcribe(
        str(video),
        vad_filter=True
    )

    results = []

    for segment in segments:
        results.append({
            "start": float(segment.start),
            "end": float(segment.end),
            "text": segment.text.strip()
        })

    return results


# ==================================================
# CAPTION SETTINGS
# ==================================================

def ass_color(value, default):

    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value or ""):
        value = default

    value = value.lstrip("#")

    return (
        "&H00"
        + value[4:6]
        + value[2:4]
        + value[0:2]
    ).upper()


def ass_time(seconds):

    cs = max(0, int(seconds * 100))

    hours, remaining = divmod(cs, 360000)
    minutes, remaining = divmod(remaining, 6000)
    seconds, cs = divmod(remaining, 100)

    return (
        f"{hours}:{minutes:02}:"
        f"{seconds:02}.{cs:02}"
    )


def create_subtitles(
    filename,
    segments,
    clip_start,
    clip_end,
    settings
):

    font = settings["font"]

    if font not in FONTS:
        font = "Arial"

    font_size = max(16, min(90, settings["font_size"]))

    alignment = {
        "bottom": 2,
        "middle": 5,
        "top": 8
    }.get(settings["position"], 2)

    margin = 90 if alignment != 5 else 0
    bold = -1 if settings["bold"] else 0

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

        f"Style: Default,{font},{font_size},"
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

        start = max(clip_start, segment["start"])
        end = min(clip_end, segment["end"])

        if end <= start:
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
                f"Dialogue: 0,"
                f"{ass_time(start - clip_start)},"
                f"{ass_time(end - clip_start)},"
                f"Default,,0,0,0,,{text}"
            )

    filename.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    return filename


# ==================================================
# AI CLIP SELECTION
# ==================================================

def choose_clips(
    segments,
    total_duration,
    clip_count,
    clip_length
):

    clip_length = min(clip_length, total_duration)
    step = max(1, clip_length // 3)

    candidates = []
    position = 0

    while position < total_duration:

        end = min(
            total_duration,
            position + clip_length
        )

        score = sum(
            max(
                0,
                min(s["end"], end) -
                max(s["start"], position)
            )
            for s in segments
        )

        candidates.append((score, position))
        position += step

    candidates.sort(
        key=lambda item: item[0],
        reverse=True
    )

    selected = []

    for score, position in candidates:

        if all(
            abs(position - old) >= clip_length * 0.7
            for old in selected
        ):
            selected.append(position)

        if len(selected) >= clip_count:
            break

    return sorted(selected or [0])


# ==================================================
# VIDEO EXPORT
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

    filters = (
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

        filters += f",ass='{subtitle_path}'"

    source_has_audio = has_audio(source)

    command = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-i", str(source)
    ]

    # MUSIC MIX
    if music:

        command += [
            "-stream_loop", "-1",
            "-i", str(music)
        ]

        if source_has_audio:

            audio_filter = (
                f"[0:a]volume="
                f"{settings['original_volume']/100}[a0];"

                f"[1:a]volume="
                f"{settings['music_volume']/100}[a1];"

                "[a0][a1]amix=inputs=2:"
                "duration=first:"
                "dropout_transition=2[a]"
            )

        else:

            audio_filter = (
                f"[1:a]volume="
                f"{settings['music_volume']/100}[a]"
            )

        command += [
            "-t", str(length),
            "-vf", filters,
            "-filter_complex", audio_filter,
            "-map", "0:v:0",
            "-map", "[a]"
        ]

    # ORIGINAL AUDIO ONLY
    else:

        command += [
            "-t", str(length),
            "-vf", filters,
            "-map", "0:v:0"
        ]

        if source_has_audio and settings["original_volume"] > 0:

            command += [
                "-map", "0:a:0",
                "-af",
                f"volume={settings['original_volume']/100}"
            ]

        else:
            command += ["-an"]

    command += [
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
        raise RuntimeError("FFmpeg did not create the output clip.")

    if subtitle_file.exists():
        subtitle_file.unlink()


# ==================================================
# FORM SETTINGS
# ==================================================

def bounded_setting(name, default, minimum, maximum):

    try:
        value = int(request.form.get(name, default))
    except (TypeError, ValueError):
        value = default

    return max(minimum, min(maximum, value))


def get_settings():

    return {
        "subtitles": request.form.get("subtitles") == "on",
        "font": request.form.get("font", "Arial"),

        "font_size": bounded_setting(
            "font_size", 42, 16, 90
        ),

        "font_color": request.form.get(
            "font_color", "#FFFFFF"
        ),

        "outline_color": request.form.get(
            "outline_color", "#000000"
        ),

        "outline": bounded_setting(
            "outline", 3, 0, 8
        ),

        "position": request.form.get(
            "position", "bottom"
        ),

        "bold": request.form.get("bold") == "on",

        "uppercase": request.form.get("uppercase") == "on",

        "music_volume": bounded_setting(
            "music_volume", 25, 0, 100
        ),

        "original_volume": bounded_setting(
            "original_volume", 100, 0, 100
        )
    }


# ==================================================
# WEBSITE
# ==================================================

@app.get("/")
def index():
    return render_template("index.html", error=None)


@app.get("/health")
def health():

    return jsonify({
        "status": "ok",
        "app": "CLIPSHORT AI"
    })


# ==================================================
# GENERATE CLIPS
# ==================================================

@app.post("/generate")
def generate():

    folder = None

    try:

        clip_count = bounded_setting(
            "clip_count", 5, 1, 30
        )

        clip_length = bounded_setting(
            "clip_length", 30, 5, 90
        )

        settings = get_settings()

        folder = Path(
            tempfile.mkdtemp(
                prefix="job_",
                dir=JOBS
            )
        )

        # IMPORT VIDEO
        source = download_video(
            request.files.get("video"),
            request.form.get("source_url", "").strip(),
            folder
        )

        # IMPORT MUSIC
        music = get_music(
            request.files.get("music"),
            folder
        )

        # CHECK VIDEO
        total = get_duration(source)

        if total < 5:
            raise ValueError(
                "Video must be at least 5 seconds long."
            )

        clip_length = min(
            clip_length,
            int(total)
        )

        # TRANSCRIPTION
        segments = transcribe(source)

        # SELECT CLIPS
        positions = choose_clips(
            segments,
            total,
            clip_count,
            clip_length
        )

        outputs = []

        # GENERATE EACH CLIP
        for index, position in enumerate(
            positions,
            start=1
        ):

            output = folder / f"clip_{index:02}.mp4"

            duration = min(
                clip_length,
                total - position
            )

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
            raise RuntimeError("No clips were generated.")

        # CREATE ZIP
        archive = folder / "clipshort_exports.zip"

        with zipfile.ZipFile(
            archive,
            "w",
            zipfile.ZIP_DEFLATED
        ) as zip_file:

            for output in outputs:
                zip_file.write(
                    output,
                    output.name
                )

        return send_file(
            archive,
            as_attachment=True,
            download_name="clipshort_ai_clips.zip",
            mimetype="application/zip"
        )

    except Exception as error:

        app.logger.exception(
            "CLIPSHORT AI generation failed"
        )

        message = f"Clip generation error: {error}"

        return render_template(
            "index.html",
            error=message
        ), 400


# ==================================================
# START SERVER
# ==================================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
    
