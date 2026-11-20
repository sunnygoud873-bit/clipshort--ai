import streamlit as st
import subprocess, tempfile, shutil, re, time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

st.set_page_config(page_title="CLIPSHORT AI", page_icon="🎬", layout="wide")
st.markdown("<h1>🎬 CLIPSHORT AI</h1><p>English + Indian | Auto Subtitles | Shorts</p>", unsafe_allow_html=True)

if "preview_done" not in st.session_state:
    st.session_state.preview_done = False
if "preview_bytes" not in st.session_state:
    st.session_state.preview_bytes = None

def run_cmd(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[-2000:])
    return r.stdout.strip()

def check_ffmpeg():
    return shutil.which("ffmpeg") is not None

def get_duration(path):
    v = run_cmd(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)])
    return float(v)

def has_audio(path):
    r = subprocess.run(["ffprobe","-v","error","-select_streams","a:0","-show_entries","stream=codec_type","-of","csv=p=0",str(path)], capture_output=True, text=True)
    return bool(r.stdout.strip())

def get_drive_id(url):
    p = urlparse(url.strip())
    m = re.search(r"/file/d/([A-Za-z0-9_-]+)", p.path)
    if m:
        return m.group(1)
    q = parse_qs(p.query)
    if q.get("id"):
        return q["id"][0]
    raise ValueError("Invalid Drive link")

def download_drive(url, folder):
    import requests
    fid = get_drive_id(url)
    target = folder / "drive_video.mp4"
    dl_url = "https://drive.google.com/uc?export=download&id=" + fid + "&confirm=t"
    s = requests.Session()
    r = s.get(dl_url, stream=True, timeout=60)
    total = int(r.headers.get("content-length", 0))
    done = 0
    with open(target, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024*1024*2):
            if chunk:
                f.write(chunk)
                done += len(chunk)
    if not target.exists() or target.stat().st_size < 10000:
        raise RuntimeError("Drive failed. Set Anyone with link Viewer")
    return target

def download_youtube(url, folder):
    import yt_dlp
    opts = {"format":"best[height<=720][ext=mp4]/best[height<=720]/best","outtmpl":str(folder/"youtube_video.%(ext)s"),"noplaylist":True,"quiet":True}
    with yt_dlp.YoutubeDL(opts) as d:
        d.download([url])
    files = list(folder.glob("youtube_video.*"))
    if not files:
        raise RuntimeError("YouTube blocked. Upload video instead")
    return files[0]

LANGUAGE_CODES = {
    "English - English": "en",
    "English (Translate)": "translate",
    "Telugu - తెలుగు": "te",
    "Hindi - हिन्दी": "hi",
    "Tamil - தமிழ்": "ta",
    "Kannada - ಕನ್ನಡ": "kn",
    "Malayalam - മലയാളം": "ml",
    "Bengali - বাংলা": "bn",
    "Marathi - मराठी": "mr",
    "Gujarati - ગુજરાતી": "gu",
    "Punjabi - ਪੰਜਾਬੀ": "pa",
    "Urdu - اردو": "ur",
    "Auto Detect": "auto",
}

FONT_FOR_LANG = {
    "te": "Noto Sans Telugu",
    "hi": "Noto Sans Devanagari",
    "mr": "Noto Sans Devanagari",
    "ta": "Noto Sans Tamil",
    "kn": "Noto Sans Kannada",
    "ml": "Noto Sans Malayalam",
    "bn": "Noto Sans Bengali",
    "gu": "Noto Sans Gujarati",
    "pa": "Noto Sans Gurmukhi",
    "en": "Noto Sans",
    "translate": "Noto Sans",
    "auto": "Noto Sans",
}

@st.cache_resource
def load_whisper():
    from faster_whisper import WhisperModel
    return WhisperModel("tiny", device="cpu", compute_type="int8")

def transcribe_video(path, language):
    try:
        audio_path = Path(str(path) + "_audio.wav")
        subprocess.run(["ffmpeg","-y","-i",str(path),"-vn","-ac","1","-ar","16000","-af","loudnorm,volume=2.0","-c:a","pcm_s16le",str(audio_path)], capture_output=True)
        if not audio_path.exists() or audio_path.stat().st_size < 1000:
            return []
        model = load_whisper()
        code = LANGUAGE_CODES.get(language, "te")
        opts = {"vad_filter": False, "beam_size": 1, "temperature": 0.0}
        if code == "translate":
            opts["task"] = "translate"
        elif code == "auto":
            pass
        else:
            opts["language"] = code
        segments, _ = model.transcribe(str(audio_path), **opts)
        out = []
        for s in segments:
            txt = s.text.strip()
            if txt and getattr(s, "no_speech_prob", 0) < 0.95:
                out.append({"start": float(s.start), "end": float(s.end), "text": txt})
        return out
    except Exception as e:
        print("Subtitle skipped", e)
        return []

def choose_starts(segments, total, length, count):
    if total <= length:
        return [0.0]
    step = max(2.0, min(length/5, 6.0))
    cands = []
    start = 0.0
    while start + length <= total:
        end = start + length
        score = 0
        for s in segments:
            score += max(0.0, min(s["end"], end) - max(s["start"], start))
        cands.append((score, start))
        start += step
    cands.sort(key=lambda x: x[0], reverse=True)
    sel = []
    for _, s in cands:
        ok = True
        for p in sel:
            if abs(s - p) < length * 0.65:
                ok = False
        if ok:
            sel.append(s)
        if len(sel) >= count:
            break
    if not sel:
        sel = [0.0]
    return sorted(sel)

def ass_time(sec):
    h = int(sec//3600)
    m = int((sec%3600)//60)
    r = sec%60
    return f"{h}:{m:02d}:{r:05.2f}"

def ass_color(v):
    v = v.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", v):
        v = "FFFFFF"
    return f"&H00{v[4:6]}{v[2:4]}{v[0:2]}&".upper()

RATIOS = {
    "9:16 - Shorts / Reels": (1080, 1920),
    "16:9 - YouTube": (1920, 1080),
    "1:1 - Instagram Post": (1080, 1080),
    "4:5 - Instagram Portrait": (1080, 1350),
}
RESOLUTIONS = {
    "480p - Fast": 480,
    "720p - HD": 720,
    "1080p - Full HD": 1080,
}

def get_output_size(ratio_label, res_label):
    base_w, base_h = RATIOS[ratio_label]
    target = RESOLUTIONS[res_label]
    if base_w <= base_h:
        w = target
        h = int(base_h * (target / base_w))
    else:
        h = target
        w = int(base_w * (target / base_h))
    w = w - (w % 2)
    h = h - (h % 2)
    return w, h

def write_subtitles(f, segments, cs, ce, cfg, out_h):
    align = {"Bottom": 2, "Middle": 5, "Top": 8}[cfg["position"]]
    bold = -1 if cfg["bold"] else 0
    border = 3 if cfg["background"] else 1
    outline = 0 if cfg["background"] else cfg["outline"]
    lang_code = LANGUAGE_CODES.get(cfg["language"], "te")
    font = FONT_FOR_LANG.get(lang_code, "Noto Sans")
    fs = cfg["font_size"]
    if out_h <= 854:
        fs = max(18, int(cfg["font_size"] * 0.45))
    elif out_h <= 1280:
        fs = max(22, int(cfg["font_size"] * 0.65))
    margin_v = int(90 * (out_h / 1920)) if out_h < 1920 else 90
    lines = []
    lines.append("[Script Info]")
    lines.append("ScriptType: v4.00+")
    lines.append("PlayResX: " + str(cfg["out_w"]))
    lines.append("PlayResY: " + str(cfg["out_h"]))
    lines.append("")
    lines.append("[V4+ Styles]")
    lines.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
    style = "Style: Default," + font + "," + str(fs) + "," + ass_color(cfg["text_color"]) + ",&H000000FF&," + ass_color(cfg["outline_color"]) + "," + ass_color(cfg["background_color"]) + "," + str(bold) + ",0,0,0,100,100,0,0," + str(border) + "," + str(outline) + "," + str(cfg["shadow"]) + "," + str(align) + ",60,60," + str(margin_v) + ",1"
    lines.append(style)
    lines.append("")
    lines.append("[Events]")
    lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")
    for s in segments:
        st_ = max(s["start"], cs)
        en = min(s["end"], ce)
        if en <= st_:
            continue
        cap = s["text"].replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", " ")
        if cfg["uppercase"]:
            cap = cap.upper()
        dlg = "Dialogue: 0," + ass_time(st_ - cs) + "," + ass_time(en - cs) + ",Default,,0,0,0,," + cap
        lines.append(dlg)
    f.write_text("\n".join(lines), encoding="utf-8")

def sub_path(p):
    v = str(p.resolve()).replace("\\", "/")
    return v.replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")

def render_clip(source, output, start, length, segments, cfg, music):
    out_w = cfg["out_w"]
    out_h = cfg["out_h"]
    args = ["ffmpeg","-y","-ss",str(start),"-i",str(source)]
    if music:
        args += ["-stream_loop","-1","-i",str(music)]
    filters = []
    filters.append("scale=" + str(out_w) + ":" + str(out_h) + ":force_original_aspect_ratio=increase")
    filters.append("crop=" + str(out_w) + ":" + str(out_h))
    filters.append("setsar=1")
    filters.append("fps=30")
    sub_file = output.with_suffix(".ass")
    if cfg["subtitles"] and segments:
        write_subtitles(sub_file, segments, start, start+length, cfg, out_h)
        filters.append("ass='" + sub_path(sub_file) + "'")
    args += ["-t",str(length),"-vf",",".join(filters),"-c:v","libx264","-preset",cfg["preset"],"-crf",str(cfg["crf"]),"-pix_fmt","yuv420p"]
    src_audio = has_audio(source)
    if music and src_audio:
        args += ["-filter_complex","[0:a]volume=" + str(cfg["source_volume"]) + "[a0];[1:a]volume=" + str(cfg["music_volume"]) + "[a1];[a0][a1]amix=inputs=2:duration=first[aout]","-map","0:v:0","-map","[aout]","-c:a","aac"]
    elif music:
        args += ["-map","0:v:0","-map","1:a:0","-af","volume=" + str(cfg["music_volume"])," -c:a","aac"]
    elif src_audio:
        args += ["-af","volume=" + str(cfg["source_volume"])," -c:a","aac"]
    else:
        args += ["-an"]
    # Fix audio args typo - rebuild clean
    args = [a.strip() for a in args]
    args += ["-movflags","+faststart",str(output)]
    run_cmd(args)
    if sub_file.exists():
        sub_file.unlink()

def get_source(work, source_type, video_url, video_upload):
    if source_type == "Google Drive":
        return download_drive(video_url, work)
    elif source_type == "YouTube":
        return download_youtube(video_url, work)
    else:
        source = work / ("uploaded_video" + Path(video_upload.name).suffix.lower())
        with source.open("wb") as f:
            shutil.copyfileobj(video_upload, f, length=8*1024*1024)
        return source

def get_music(work, music_upload):
    if music_upload is None:
        return None
    music = work / ("background_music" + Path(music_upload.name).suffix.lower())
    with music.open("wb") as f:
        shutil.copyfileobj(music_upload, f, length=1024*1024)
    return music

st.subheader("Video Source")
source_type = st.radio("Choose source", ["Google Drive","Upload video","YouTube"], horizontal=True)
video_url = ""
video_upload = None
if source_type == "Google Drive":
    video_url = st.text_input("Google Drive sharing link", placeholder="Paste Drive link")
elif source_type == "Upload video":
    video_upload = st.file_uploader("Upload video", type=["mp4","mov","mkv","webm","avi","m4v"])
else:
    video_url = st.text_input("YouTube URL", placeholder="Paste YouTube link")

st.subheader("Background Music")
music_upload = st.file_uploader("Upload music (optional)", type=["mp3","wav","m4a","aac","ogg","flac"])

st.subheader("Settings")
c1, c2 = st.columns(2)
with c1:
    clip_count = st.slider("Maximum clips", 1, 5, 3)
    clip_length = st.slider("Clip duration (seconds)", 10, 60, 30)
    subtitles = st.toggle("Automatic subtitles", value=True)
    language = st.selectbox("Subtitle language", list(LANGUAGE_CODES.keys()), index=2)
with c2:
    font_size = st.slider("Font size", 18, 80, 48)
    bold = st.toggle("Bold font", True)
    uppercase = st.toggle("Uppercase text", False)
    position = st.selectbox("Caption position", ["Bottom","Middle","Top"])

c3, c4 = st.columns(2)
with c3:
    text_color = st.color_picker("Text colour", "#FFFFFF")
    outline_color = st.color_picker("Outline colour", "#000000")
    outline = st.slider("Outline thickness", 0, 10, 3)
with c4:
    background = st.toggle("Caption background", False)
    background_color = st.color_picker("Caption background colour", "#151515")
    shadow = st.slider("Caption shadow", 0, 5, 2)

c5, c6, c7 = st.columns(3)
with c5:
    source_volume = st.slider("Original audio volume", 0.0, 2.0, 1.5)
with c6:
    music_volume = st.slider("Background music volume", 0.0, 2.0, 0.25)
with c7:
    quality = st.selectbox("Video quality", ["Fast","Balanced","High"], index=0)

st.markdown("### Ratio & Resolution")
r1, r2 = st.columns(2)
with r1:
    ratio_label = st.selectbox("Aspect Ratio", list(RATIOS.keys()), index=0)
with r2:
    res_label = st.selectbox("Resolution", list(RESOLUTIONS.keys()), index=1)
out_w, out_h = get_output_size(ratio_label, res_label)
st.info("Selected: " + ratio_label + " | " + res_label + " | " + str(out_w) + "x" + str(out_h))

cfg = {"subtitles": subtitles, "font_size": font_size, "text_color": text_color, "outline_color": outline_color, "outline": outline, "position": position, "bold": bold, "uppercase": uppercase, "background": background, "background_color": background_color, "shadow": shadow, "source_volume": source_volume, "music_volume": music_volume, "preset": {"Fast":"ultrafast","Balanced":"veryfast","High":"fast"}[quality], "crf": {"Fast":28,"Balanced":23,"High":19}[quality], "out_w": out_w, "out_h": out_h, "ratio": ratio_label, "resolution": res_label, "language": language}

st.subheader("Step 1: Preview - Mandatory")
st.warning("First Preview Chudu - Tarvatha Ne Generate Open Avuthundi")
if st.button("GENERATE PREVIEW - 5 Sec Sample", use_container_width=True, key="btn_preview"):
    if source_type == "Upload video" and video_upload is None:
        st.error("Please upload a video first")
        st.stop()
    if source_type != "Upload video" and not video_url.strip().startswith(("https://","http://")):
        st.error("Please enter a valid video link")
        st.stop()
    if not check_ffmpeg():
        st.error("FFmpeg missing")
        st.stop()
    work = Path(tempfile.mkdtemp(prefix="preview_"))
    try:
        st.write("Making Preview... Please wait")
        source = get_source(work, source_type, video_url, video_upload)
        music = get_music(work, music_upload)
        segs = []
        if cfg["subtitles"]:
            st.write("Transcribing in " + language)
            segs = transcribe_video(source, language)
            st.write("Found " + str(len(segs)) + " subtitle lines")
        preview_out = work / "preview.mp4"
        render_clip(source, preview_out, 0, 5, segs, cfg, music)
        with open(preview_out, "rb") as f:
            st.session_state.preview_bytes = f.read()
        st.success("Preview Ready")
        st.video(st.session_state.preview_bytes)
        st.session_state.preview_done = True
    except Exception as e:
        st.error("Preview Error: " + str(e))
        st.session_state.preview_done = False

if st.session_state.preview_bytes is not None:
    st.video(st.session_state.preview_bytes)

if st.session_state.preview_done:
    st.success("Preview Approved - Now Generate")
else:
    st.warning("Generate Locked - Preview First")

st.subheader("Step 2: Generate Clips")
generate_disabled = not st.session_state.preview_done
if st.button("GENERATE CLIPS", type="primary", use_container_width=True, disabled=generate_disabled, key="btn_generate"):
    work = Path(tempfile.mkdtemp(prefix="clipshort_"))
    try:
        st.write("Processing your video...")
        source = get_source(work, source_type, video_url, video_upload)
        music = get_music(work, music_upload)
        total = get_duration(source)
        st.write("Video length: " + str(round(total, 1)) + " sec")
        segments = []
        if cfg["subtitles"]:
            st.write("Transcribing in " + language)
            segments = transcribe_video(source, language)
            if not segments:
                st.warning("No speech found - Making clips without subtitles")
                cfg["subtitles"] = False
            else:
                st.write("Found " + str(len(segments)) + " subtitle lines")
        if segments:
            starts = choose_starts(segments, total, clip_length, clip_count)
        else:
            starts = []
            n = max(1, min(clip_count, int(total // clip_length)))
            for i in range(n):
                starts.append(i * clip_length)
            if not starts:
                starts = [0.0]
        st.write("Making " + str(len(starts)) + " clips...")
        outs = []
        for i, s in enumerate(starts):
            out = work / ("clip_" + str(i+1) + ".mp4")
            st.write("Rendering clip " + str(i+1) + " / " + str(len(starts)))
            render_clip(source, out, s, clip_length, segments, cfg, music)
            if out.exists():
                outs.append(out)
        st.success("Done - " + str(len(outs)) + " Clips Ready")
        for i, o in enumerate(outs):
            st.subheader("Clip " + str(i+1) + " - " + str(out_w) + "x" + str(out_h))
            st.video(str(o))
            with open(o, "rb") as f:
                st.download_button("Download Clip " + str(i+1), data=f.read(), file_name="clip_" + str(i+1) + "_" + str(out_w) + "x" + str(out_h) + ".mp4", mime="video/mp4", key="dl_" + str(i))
    except Exception as e:
        st.error("Error: " + str(e))
