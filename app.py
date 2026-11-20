import os, re, subprocess, tempfile, zipfile
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, request, render_template, send_file, jsonify
from werkzeug.utils import secure_filename
import yt_dlp
import gdown
from faster_whisper import WhisperModel

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_MB", "1024")) * 1024 * 1024
JOBS = Path("/tmp/clipshort_jobs")
JOBS.mkdir(exist_ok=True)
MODEL_SIZE = os.getenv("WHISPER_MODEL", "tiny")
_whisper = None
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
FONTS = {"Arial", "DejaVu Sans", "Liberation Sans", "Montserrat", "Roboto", "Poppins", "Impact", "Georgia"}

def run(args):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout or "Command failed")[-2200:])
    return p.stdout.strip()

def whisper():
    global _whisper
    if _whisper is None:
        _whisper = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    return _whisper

def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=noprint_wrappers=1:nokey=1", str(path)]) or 0)

def get_video(upload, url, folder):
    if upload and upload.filename:
        ext = Path(secure_filename(upload.filename)).suffix.lower()
        if ext not in VIDEO_EXT:
            raise ValueError("Upload MP4, MOV, MKV, WEBM, AVI or M4V.")
        dest = folder / ("source" + ext)
        upload.save(dest)
        return dest
    if not url:
        raise ValueError("Upload a video or paste a YouTube / Google Drive link.")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Enter a valid HTTPS link.")
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}:
        opts = {"format": "best[ext=mp4]/best", "outtmpl": str(folder / "source.%(ext)s"),
                "noplaylist": True, "quiet": True, "no_warnings": True,
                "merge_output_format": "mp4", "socket_timeout": 30, "retries": 2}
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        found = [p for p in folder.glob("source.*") if p.is_file() and p.suffix not in {".part", ".ytdl"}]
        if not found:
            raise RuntimeError("Could not download video from that link.")
        return found[0]
    if host in {"drive.google.com", "docs.google.com"}:
        result = gdown.download(url, str(folder / "source"), quiet=True, fuzzy=True)
        if not result:
            raise RuntimeError("Google Drive download failed. Set sharing to Anyone with the link.")
        p = Path(result)
        # Detect media using ffprobe; extension is not required by ffmpeg.
        return p
    raise ValueError("Supported links: YouTube and public Google Drive share links.")

def get_music(upload, folder):
    if not upload or not upload.filename:
        return None
    ext = Path(secure_filename(upload.filename)).suffix.lower()
    if ext not in AUDIO_EXT:
        raise ValueError("Music file must be MP3, WAV, M4A, AAC, OGG or FLAC.")
    p = folder / ("music" + ext)
    upload.save(p)
    return p

def hex_ass(value, default):
    value = value if re.fullmatch(r"#[0-9a-fA-F]{6}", value or "") else default
    h = value[1:]
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()

def ass_time(t):
    cs = max(0, int(t * 100))
    h, r = divmod(cs, 360000); m, r = divmod(r, 6000); s, c = divmod(r, 100)
    return f"{h}:{m:02}:{s:02}.{c:02}"

def make_subtitles(path, segments, start, end, settings):
    font = settings["font"] if settings["font"] in FONTS else "Arial"
    size = max(16, min(90, settings["font_size"]))
    align = {"bottom": 2, "middle": 5, "top": 8}.get(settings["position"], 2)
    margin = 90 if settings["position"] != "middle" else 0
    bold = -1 if settings["bold"] else 0
    outline = max(0, min(8, settings["outline"]))
    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920",
        "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font},{size},{hex_ass(settings['font_color'],'#FFFFFF')},&H000000FF,{hex_ass(settings['outline_color'],'#000000')},&H80000000,{bold},0,0,0,100,100,0,0,1,{outline},1,{align},55,55,{margin},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    for seg in segments:
        a, b = max(start, seg["start"]), min(end, seg["end"])
        if b <= a:
            continue
        txt = seg["text"].strip().replace("{", r"\{").replace("}", r"\}").replace("\n", " ")
        if settings["uppercase"]:
            txt = txt.upper()
        if txt:
            lines.append(f"Dialogue: 0,{ass_time(a-start)},{ass_time(b-start)},Default,,0,0,0,,{txt}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path

def transcribe(path):
    segments, _ = whisper().transcribe(str(path), vad_filter=True)
    return [{"start": float(s.start), "end": float(s.end), "text": s.text} for s in segments]

def choose_clips(segs, total, count, length):
    length = min(length, total)
    if length <= 0: raise ValueError("Invalid clip length.")
    step = max(1, length // 3)
    candidates = []
    pos = 0.0
    while pos < total:
        end = min(total, pos + length)
        speech = sum(max(0, min(s["end"], end) - max(s["start"], pos)) for s in segs)
        candidates.append((speech, pos))
        pos += step
    candidates.sort(key=lambda x: x[0], reverse=True)
    picked = []
    for score, pos in candidates:
        if all(abs(pos - old) >= length * .7 for old in picked):
            picked.append(pos)
        if len(picked) >= count: break
    return sorted(picked or [0])

def create_clip(src, out, start, length, segs, settings, music):
    ass = out.with_suffix(".ass")
    if settings["subtitles"]:
        make_subtitles(ass, segs, start, start + length, settings)
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    if settings["subtitles"]:
        ass_path = ass.as_posix().replace("\\", "/").replace(":", "\\:")
        vf += ",ass=" + ass_path
    base = ["ffmpeg", "-y", "-ss", str(start), "-i", str(src)]
    if music:
        base += ["-stream_loop", "-1", "-i", str(music)]
        filter_complex = f"[0:a]volume={settings['original_volume'] / 100}[a0];[1:a]volume={settings['music_volume'] / 100}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]"
        base += ["-t", str(length), "-vf", vf, "-filter_complex", filter_complex,
                 "-map", "0:v:0", "-map", "[a]"]
    else:
        base += ["-t", str(length), "-vf", vf, "-map", "0:v:0", "-map", "0:a?"]
        if settings["original_volume"] == 0:
            base += ["-an"]
        else:
            base += ["-af", f"volume={settings['original_volume'] / 100}"]
    base += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
    run(base)
    if ass.exists(): ass.unlink()

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/health")
def health():
    return jsonify(status="ok")

@app.post("/generate")
def generate():
    try:
        count = max(1, min(30, int(request.form.get("clip_count", 5))))
        clip_len = max(5, min(90, int(request.form.get("clip_length", 30))))
        settings = {
            "subtitles": request.form.get("subtitles") == "on",
            "font": request.form.get("font", "Arial"),
            "font_size": max(16, min(90, int(request.form.get("font_size", 42)))),
            "font_color": request.form.get("font_color", "#FFFFFF"),
            "outline_color": request.form.get("outline_color", "#000000"),
            "outline": max(0, min(8, int(request.form.get("outline", 3)))),
            "position": request.form.get("position", "bottom"),
            "bold": request.form.get("bold") == "on",
            "uppercase": request.form.get("uppercase") == "on",
            "music_volume": max(0, min(100, int(request.form.get("music_volume", 25)))),
            "original_volume": max(0, min(100, int(request.form.get("original_volume", 100)))),
        }
        folder = Path(tempfile.mkdtemp(prefix="job_", dir=JOBS))
        src = get_video(request.files.get("video"), request.form.get("source_url", "").strip(), folder)
        music = get_music(request.files.get("music"), folder)
        total = duration(src)
        if total < 5: raise ValueError("Video must be at least 5 seconds long.")
        clip_len = min(clip_len, int(total))
        segments = transcribe(src) if settings["subtitles"] or True else []
        starts = choose_clips(segments, total, count, clip_len)
        outputs = []
        for i, start in enumerate(starts, 1):
            out = folder / f"clip_{i:02}.mp4"
            create_clip(src, out, start, min(clip_len, total-start), segments, settings, music)
            outputs.append(out)
        archive = folder / "clipshort_ai_exports.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for p in outputs: z.write(p, p.name)
        return send_file(archive, as_attachment=True, download_name="clipshort_ai_exports.zip")
    except Exception as e:
        return render_template("index.html", error=str(e)), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
