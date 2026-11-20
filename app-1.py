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
from flask import Flask, request, render_template, send_file, jsonify
from werkzeug.utils import secure_filename
from faster_whisper import WhisperModel

# ============================================================
# CLIPSHORT AI - single-file Flask application
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
JOBS_DIR = Path(os.getenv("CLIPSHORT_JOBS_DIR", "/tmp/clipshort_jobs"))
JOBS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder=str(BASE_DIR))
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1 GB
app.config["JSON_SORT_KEYS"] = False
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "tiny")
YOUTUBE_COOKIES_FILE = os.getenv(
    "YOUTUBE_COOKIES_FILE", "/etc/secrets/youtube_cookies.txt"
)
whisper_model = None

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
ALLOWED_FONTS = {
    "Arial", "DejaVu Sans", "Liberation Sans", "Montserrat",
    "Roboto", "Poppins", "Impact", "Georgia"
}
YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
    "www.youtu.be", "music.youtube.com"
}
DRIVE_HOSTS = {
    "drive.google.com", "www.drive.google.com", "docs.google.com"
}


def run_command(args):
    """Run a command safely and return stdout or a useful error."""
    result = subprocess.run(
        [str(x) for x in args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Command failed").strip()
        raise RuntimeError(detail[-3500:])
    return result.stdout.strip()


def check_dependencies():
    for executable in ("ffmpeg", "ffprobe"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"Required system program '{executable}' is missing.")


def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        whisper_model = WhisperModel(
            WHISPER_MODEL_NAME,
            device="cpu",
            compute_type="int8",
        )
    return whisper_model


def get_duration(video_path):
    value = run_command([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ])
    try:
        duration = float(value)
    except (TypeError, ValueError):
        raise RuntimeError("Could not read the video duration.")
    if duration <= 0:
        raise RuntimeError("The selected video has no valid duration.")
    return duration


def video_has_audio(video_path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_type", "-of", "csv=p=0",
            str(video_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def safe_int(form_name, default, minimum, maximum):
    try:
        value = int(request.form.get(form_name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def download_video(upload, url, job_dir):
    """Accept an uploaded video, YouTube URL, or public Drive URL."""
    if upload and upload.filename:
        filename = secure_filename(upload.filename)
        extension = Path(filename).suffix.lower()
        if extension not in VIDEO_EXTENSIONS:
            raise ValueError("Unsupported video format. Use MP4, MOV, MKV, WEBM, AVI or M4V.")
        destination = job_dir / ("uploaded_video" + extension)
        upload.save(destination)
        if not destination.exists() or destination.stat().st_size == 0:
            raise RuntimeError("The uploaded video is empty.")
        return destination

    if not url:
        raise ValueError("Upload a video or paste a YouTube / Google Drive link.")

    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("Please enter a valid http or https video URL.")

    if host in YOUTUBE_HOSTS:
        output_template = str(job_dir / "youtube_source.%(ext)s")
        ydl_options = {
            "format": "bestvideo*+bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": False,
            "merge_output_format": "mp4",
            "socket_timeout": 60,
            "retries": 3,
            "fragment_retries": 3,
            "extractor_retries": 3,
            "continuedl": True,
        }
        # On Render, add youtube_cookies.txt as a Secret File and set
        # YOUTUBE_COOKIES_FILE=/etc/secrets/youtube_cookies.txt.
        if os.path.isfile(YOUTUBE_COOKIES_FILE):
            ydl_options["cookiefile"] = YOUTUBE_COOKIES_FILE

        try:
            with yt_dlp.YoutubeDL(ydl_options) as downloader:
                downloader.download([url])
        except Exception as exc:
            raise RuntimeError(
                "YouTube refused the download. If it says 'Sign in to confirm ' "
                "you're not a bot', configure a valid YouTube cookies.txt file "
                "as a private Render Secret File. Cookies can expire and Render "
                "may still be blocked. You can use Upload file or a public "
                "Google Drive link instead. Details: " + str(exc)
            ) from exc

        downloaded = [
            p for p in job_dir.glob("youtube_source.*")
            if p.is_file() and p.suffix.lower() not in {".part", ".ytdl"}
        ]
        if not downloaded:
            raise RuntimeError("yt-dlp finished but no YouTube video file was created.")
        return max(downloaded, key=lambda p: p.stat().st_size)

    if host in DRIVE_HOSTS:
        destination = job_dir / "drive_source"
        try:
            # Do not pass fuzzy=True: it is not supported by every gdown version.
            result = gdown.download(url, str(destination), quiet=True)
        except Exception as exc:
            raise RuntimeError("Google Drive download failed: " + str(exc)) from exc
        if not result:
            raise RuntimeError(
                "Google Drive download failed. Set sharing to 'Anyone with the link' "
                "and make sure the link points to a downloadable video."
            )
        downloaded = Path(result)
        if not downloaded.exists() or downloaded.stat().st_size == 0:
            raise RuntimeError("Google Drive returned an empty file.")
        return downloaded

    raise ValueError("Supported sources are YouTube, public Google Drive, or video upload.")


def get_music(upload, job_dir):
    if not upload or not upload.filename:
        return None
    filename = secure_filename(upload.filename)
    extension = Path(filename).suffix.lower()
    if extension not in AUDIO_EXTENSIONS:
        raise ValueError("Unsupported music format. Use MP3, WAV, M4A, AAC, OGG or FLAC.")
    destination = job_dir / ("background_music" + extension)
    upload.save(destination)
    if not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError("The uploaded music file is empty.")
    return destination


def transcribe_video(video_path):
    segments, _info = get_whisper_model().transcribe(
        str(video_path),
        vad_filter=True,
    )
    result = []
    for segment in segments:
        text = (segment.text or "").strip()
        if text and segment.end > segment.start:
            result.append({
                "start": float(segment.start),
                "end": float(segment.end),
                "text": text,
            })
    return result


def ass_color(value, fallback):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value or ""):
        value = fallback
    value = value.lstrip("#")
    # ASS uses &HAABBGGRR.
    return ("&H00" + value[4:6] + value[2:4] + value[0:2]).upper()


def ass_time(seconds):
    centiseconds = max(0, int(round(float(seconds) * 100)))
    hours, rem = divmod(centiseconds, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"


def create_subtitles(ass_path, segments, clip_start, clip_end, settings):
    font = settings["font"] if settings["font"] in ALLOWED_FONTS else "Arial"
    alignment = {"bottom": 2, "middle": 5, "top": 8}.get(settings["position"], 2)
    margin_v = 90 if alignment != 5 else 0
    bold = -1 if settings["bold"] else 0
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font},{settings['font_size']},"
        f"{ass_color(settings['font_color'], '#FFFFFF')},&H000000FF,"
        f"{ass_color(settings['outline_color'], '#000000')},&H80000000,"
        f"{bold},0,0,0,100,100,0,0,1,{settings['outline']},1,"
        f"{alignment},55,55,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for segment in segments:
        start = max(clip_start, segment["start"])
        end = min(clip_end, segment["end"])
        if end <= start:
            continue
        caption = segment["text"].replace("\n", " ").strip()
        if settings["uppercase"]:
            caption = caption.upper()
        caption = caption.replace("{", r"\{").replace("}", r"\}")
        if caption:
            lines.append(
                f"Dialogue: 0,{ass_time(start - clip_start)},"
                f"{ass_time(end - clip_start)},Default,,0,0,0,,{caption}"
            )
    ass_path.write_text("\n".join(lines), encoding="utf-8")


def choose_clip_starts(segments, total_duration, clip_count, clip_length):
    """Rank windows by speech coverage; this is not visual action detection."""
    clip_length = min(float(clip_length), float(total_duration))
    step = max(1.0, clip_length / 3.0)
    candidates = []
    position = 0.0
    while position < total_duration:
        end = min(total_duration, position + clip_length)
        speech_score = sum(
            max(0.0, min(s["end"], end) - max(s["start"], position))
            for s in segments
        )
        candidates.append((speech_score, position))
        position += step

    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = []
    for _score, position in candidates:
        if all(abs(position - old) >= clip_length * 0.7 for old in selected):
            selected.append(position)
        if len(selected) >= clip_count:
            break

    # If the video has no speech, still create evenly spaced clips.
    if not selected:
        if total_duration <= clip_length:
            return [0.0]
        count = min(clip_count, max(1, int(total_duration // clip_length)))
        last_start = max(0.0, total_duration - clip_length)
        if count == 1:
            return [0.0]
        return [last_start * i / (count - 1) for i in range(count)]
    return sorted(selected)


def create_clip(source, output, start, length, segments, settings, music):
    ass_path = output.with_suffix(".ass")
    video_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920"
    )
    if settings["subtitles"]:
        create_subtitles(ass_path, segments, start, start + length, settings)
        subtitle_path = str(ass_path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        video_filter += f",ass='{subtitle_path}'"

    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), "-i", str(source)]
    source_has_audio = video_has_audio(source)
    use_music = music is not None and settings["music_volume"] > 0

    if use_music:
        command += ["-stream_loop", "-1", "-i", str(music)]
        music_gain = settings["music_volume"] / 100.0
        original_gain = settings["original_volume"] / 100.0
        if source_has_audio and original_gain > 0:
            audio_filter = (
                f"[0:a:0]volume={original_gain}[original];"
                f"[1:a:0]volume={music_gain}[music];"
                "[original][music]amix=inputs=2:duration=first:"
                "dropout_transition=2[aout]"
            )
        else:
            audio_filter = f"[1:a:0]volume={music_gain}[aout]"
        command += [
            "-filter_complex", audio_filter,
            "-map", "0:v:0", "-map", "[aout]",
        ]
    else:
        command += ["-map", "0:v:0"]
        if source_has_audio and settings["original_volume"] > 0:
            command += ["-map", "0:a:0", "-af", f"volume={settings['original_volume'] / 100.0}"]
        else:
            command += ["-an"]

    command += [
        "-t", str(length),
        "-vf", video_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output),
    ]
    run_command(command)
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg did not create {output.name}.")
    if ass_path.exists():
        ass_path.unlink()


def get_settings():
    font = request.form.get("font", "Arial")
    if font not in ALLOWED_FONTS:
        font = "Arial"
    position = request.form.get("position", "bottom")
    if position not in {"bottom", "middle", "top"}:
        position = "bottom"
    font_color = request.form.get("font_color", "#FFFFFF")
    outline_color = request.form.get("outline_color", "#000000")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", font_color or ""):
        font_color = "#FFFFFF"
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", outline_color or ""):
        outline_color = "#000000"
    return {
        "subtitles": request.form.get("subtitles") == "on",
        "font": font,
        "font_size": safe_int("font_size", 42, 16, 90),
        "font_color": font_color,
        "outline_color": outline_color,
        "outline": safe_int("outline", 3, 0, 8),
        "position": position,
        "bold": request.form.get("bold") == "on",
        "uppercase": request.form.get("uppercase") == "on",
        "music_volume": safe_int("music_volume", 25, 0, 100),
        "original_volume": safe_int("original_volume", 100, 0, 100),
    }


def render_error(message, status=400):
    # The current index.html template can display the error banner via `error`.
    try:
        return render_template("index.html", error=message), status
    except Exception:
        return message, status


@app.get("/")
def home():
    return render_template("index.html", error=None)


@app.get("/health")
def health():
    return jsonify(status="ok", app="CLIPSHORT AI")


@app.post("/generate")
def generate():
    job_dir = None
    try:
        check_dependencies()
        clip_count = safe_int("clip_count", 5, 1, 30)
        clip_length = safe_int("clip_length", 30, 5, 90)
        settings = get_settings()

        job_dir = Path(tempfile.mkdtemp(prefix="clipshort_", dir=str(JOBS_DIR)))
        source = download_video(
            request.files.get("video"),
            request.form.get("source_url", "").strip(),
            job_dir,
        )
        music = get_music(request.files.get("music"), job_dir)
        total_duration = get_duration(source)
        if total_duration < 5:
            raise ValueError("Video must be at least 5 seconds long.")
        clip_length = min(float(clip_length), total_duration)

        # Whisper is needed for speech scoring and optional captions.
        # If transcription fails, create evenly spaced clips without captions.
        try:
            transcript = transcribe_video(source)
        except Exception:
            app.logger.exception("Whisper transcription failed; using evenly spaced clips")
            transcript = []
            if settings["subtitles"]:
                raise RuntimeError("Automatic subtitles failed. Try again or turn subtitles off.")

        starts = choose_clip_starts(transcript, total_duration, clip_count, clip_length)
        output_files = []
        for index, start in enumerate(starts, start=1):
            duration = min(clip_length, total_duration - start)
            if duration < 1:
                continue
            output_path = job_dir / f"clip_{index:02d}.mp4"
            create_clip(source, output_path, start, duration, transcript, settings, music)
            output_files.append(output_path)

        if not output_files:
            raise RuntimeError("No clips were generated.")

        archive_path = job_dir / "clipshort_ai_clips.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for output_path in output_files:
                archive.write(output_path, arcname=output_path.name)

        response = send_file(
            archive_path,
            as_attachment=True,
            download_name="clipshort_ai_clips.zip",
            mimetype="application/zip",
        )
        response.call_on_close(lambda: shutil.rmtree(job_dir, ignore_errors=True))
        return response

    except Exception as exc:
        app.logger.exception("Clip generation failed")
        if job_dir is not None:
            shutil.rmtree(job_dir, ignore_errors=True)
        return render_error(f"Clip generation error: {exc}", 400)


@app.errorhandler(413)
def file_too_large(_error):
    return render_error("Upload too large. Maximum upload size is 1 GB.", 413)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
