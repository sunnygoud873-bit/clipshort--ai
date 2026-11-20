
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import gdown
import yt_dlp
from flask import Flask, request, render_template, send_file, jsonify
from faster_whisper import WhisperModel
from werkzeug.utils import secure_filename

# --------------------------------------------------
# APP CONFIGURATION
# --------------------------------------------------

app = Flask(__name__, template_folder=".")
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024

JOBS = Path("/tmp/clipshort_jobs")
JOBS.mkdir(parents=True, exist_ok=True)

MODEL_NAME = os.getenv("WHISPER_MODEL", "tiny")
whisper_model = None

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}

FONTS = {
    "Arial", "DejaVu Sans", "Liberation Sans",
    "Montserrat", "Roboto", "Poppins", "Impact", "Georgia"
}


# --------------------------------------------------
# SYSTEM HELPERS
# --------------------------------------------------

def run_command(args):
    result = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            (result.stderr or result.stdout)[-2500:]
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
    value = run_command([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video)
    ])

    return float(value or 0)


# --------------------------------------------------
# VIDEO IMPORT
# --------------------------------------------------

def download_video(upload, url, folder):

    if upload and upload.filename:

        ext = Path(
            secure_filename(upload.filename)
        ).suffix.lower()

        if ext not in VIDEO_EXT:
            raise ValueError("Unsupported video format.")

        destination = folder / ("source" + ext)

        upload.save(destination)

        return destination

    if not url:
        raise ValueError("Upload a video or enter a video URL.")

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
        "docs.google.com"
    }

    if host in youtube_hosts:

        options = {
            "format": "best[ext=mp4]/best",
            "outtmpl": str(folder / "source.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
            "socket_timeout": 30,
            "retries": 2
        }

        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.download([url])

        files = [
            p for p in folder.glob("source.*")
            if p.is_file()
            and p.suffix not in {".part", ".ytdl"}
        ]

        if not files:
            raise RuntimeError("YouTube video download failed.")

        return files[0]

    if host in drive_hosts:

        result = gdown.download(
            url,
            str(folder / "source"),
            quiet=True,
            fuzzy=True
        )

        if not result:
            raise RuntimeError(
                "Google Drive download failed. "
                "Set sharing to Anyone with the link."
            )

        return Path(result)

    raise ValueError(
        "Use YouTube, public Google Drive, or upload a video."
    )


# --------------------------------------------------
# BACKGROUND MUSIC
# --------------------------------------------------

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

    return destination


# --------------------------------------------------
# AUTOMATIC SUBTITLES
# --------------------------------------------------

def transcribe(video):

    segments, info = get_whisper().transcribe(
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


# --------------------------------------------------
# CAPTION SETTINGS
# --------------------------------------------------

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

    centiseconds = max(0, int(seconds * 100))

    hours, remaining = divmod(centiseconds, 360000)
    minutes, remaining = divmod(remaining, 6000)
    seconds, centiseconds = divmod(remaining, 100)

    return (
        f"{hours}:{minutes:02}:"
        f"{seconds:02}.{centiseconds:02}"
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

    font_size = max(
        16,
        min(90, settings["font_size"])
    )

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


# --------------------------------------------------
# AI CLIP SELECTION
# --------------------------------------------------

def choose_clips(
    segments,
    total_duration,
    clip_count,
    clip_length
):

    clip_length = min(
        clip_length,
        total_duration
    )

    step = max(1, clip_length // 3)

    candidates = []

    position = 0

    while position < total_duration:

        end = min(
            total_duration,
            position + clip_length
        )

        speech_score = sum(
            max(
                0,
                min(s["end"], end)
                - max(s["start"], position)
            )
            for s in segments
        )

        candidates.append(
            (speech_score, position)
        )

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


# --------------------------------------------------
# VIDEO EXPORT
# --------------------------------------------------

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

    command = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(source)
    ]

    if music:

        command += [
            "-stream_loop", "-1",
            "-i", str(music)
        ]

        audio_filter = (
            f"[0:a]volume={settings['original_volume']/100}[a0];"
            f"[1:a]volume={settings['music_volume']/100}[a1];"
            "[a0][a1]amix=inputs=2:"
            "duration=first:dropout_transition=2[a]"
        )

        command += [
            "-t", str(length),
            "-vf", filters,
            "-filter_complex", audio_filter,
            "-map", "0:v:0",
            "-map", "[a]"
        ]

    else:

        command += [
            "-t", str(length),
            "-vf", filters,
            "-map", "0:v:0",
            "-map", "0:a?"
        ]

        if settings["original_volume"] == 0:
            command += ["-an"]
        else:
            command += [
                "-af",
                f"volume={settings['original_volume']/100}"
            ]

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

    if subtitle_file.exists():
        subtitle_file.unlink()


# --------------------------------------------------
# WEBSITE
# --------------------------------------------------

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify(status="ok")


# --------------------------------------------------
# GENERATE CLIPS
# --------------------------------------------------

@app.post("/generate")
def generate():

    try:

        clip_count = max(
            1,
            min(30, int(request.form.get("clip_count", 5)))
        )

        clip_length = max(
            5,
            min(90, int(request.form.get("clip_length", 30)))
        )

        settings = {

            "subtitles":
                request.form.get("subtitles") == "on",

            "font":
                request.form.get("font", "Arial"),

            "font_size":
                max(16, min(
                    90,
                    int(request.form.get("font_size", 42))
                )),

            "font_color":
                request.form.get("font_color", "#FFFFFF"),

            "outline_color":
                request.form.get("outline_color", "#000000"),

            "outline":
                max(0, min(
                    8,
                    int(request.form.get("outline", 3))
                )),

            "position":
                request.form.get("position", "bottom"),

            "bold":
                request.form.get("bold") == "on",

            "uppercase":
                request.form.get("uppercase") == "on",

            "music_volume":
                max(0, min(
                    100,
                    int(request.form.get("music_volume", 25))
                )),

            "original_volume":
                max(0, min(
                    100,
                    int(request.form.get("original_volume", 100))
                ))
        }

        folder = Path(
            tempfile.mkdtemp(
                prefix="job_",
                dir=JOBS
            )
        )

        source = download_video(
            request.files.get("video"),
            request.form.get("source_url", "").strip(),
            folder
        )

        music = get_music(
            request.files.get("music"),
            folder
        )

        total = get_duration(source)

        if total < 5:
            raise ValueError(
                "Video must be at least 5 seconds long."
            )

        clip_length = min(
            clip_length,
            int(total)
        )

        # Speech transcription is used for clip scoring.
        segments = transcribe(source)

        positions = choose_clips(
            segments,
            total,
            clip_count,
            clip_length
        )

        outputs = []

        for index, position in enumerate(
            positions,
            start=1
        ):

            output = folder / f"clip_{index:02}.mp4"

            create_clip(
                source,
                output,
                position,
                min(clip_length, total - position),
                segments,
                settings,
                music
            )

            outputs.append(output)

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
            download_name="clipshort_ai_clips.zip"
        )

    except Exception as error:

        app.logger.exception(
            "Clip generation failed"
        )

        return (
            f"Clip generation error: {error}",
            400
        )


# --------------------------------------------------
# START SERVER
# --------------------------------------------------

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
)
    
