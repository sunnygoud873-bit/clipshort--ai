import streamlit as st
import requests
import os
import re
import subprocess
import tempfile
import imageio_ffmpeg

st.set_page_config(
    page_title="ClipShort AI",
    page_icon="✂️",
    layout="wide"
)

# ================= UI COLOUR MANAGEMENT =================
THEMES = {
    "Dark Purple - Default": {
        "bg": "#0f0c29",
        "card": "rgba(255,255,255,0.10)",
        "text": "#FFFFFF",
        "subtext": "#B0B0B0",
        "primary": "#DD2476",
        "primary2": "#FF512F",
        "success": "#00C853",
        "input_bg": "#FFFFFF",
        "input_text": "#000000",
    },
    "Neon Black - Gaming": {
        "bg": "#000000",
        "card": "rgba(0,255,136,0.08)",
        "text": "#FFFFFF",
        "subtext": "#00FF88",
        "primary": "#00FF88",
        "primary2": "#00D4FF",
        "success": "#00FF88",
        "input_bg": "#1A1A1A",
        "input_text": "#FFFFFF",
    },
    "Clean White - Light": {
        "bg": "#F5F5F5",
        "card": "#FFFFFF",
        "text": "#000000",
        "subtext": "#666666",
        "primary": "#6C5CE7",
        "primary2": "#A29BFE",
        "success": "#00B894",
        "input_bg": "#FFFFFF",
        "input_text": "#000000",
    },
}

CAPTION_COLOURS = {
    "Yellow": "&H00FFFF&",
    "White": "&HFFFFFF&",
    "Cyan": "&HFFFF00&",
    "Pink": "&HFF00FF&",
    "Green": "&H00FF00&",
    "Orange": "&H0080FF&",
    "Red": "&H0000FF&",
    "Neon Green": "&H00FF88&",
}

PREVIEW_COLOURS = {
    "Yellow": "#FFE600",
    "White": "#FFFFFF",
    "Cyan": "#00E5FF",
    "Pink": "#FF00AA",
    "Green": "#00FF00",
    "Orange": "#FF8000",
    "Red": "#FF0000",
    "Neon Green": "#00FF88",
}

if "ui_theme" not in st.session_state:
    st.session_state["ui_theme"] = "Dark Purple - Default"

theme_name = st.sidebar.selectbox(
    "UI Theme - Colour Management",
    list(THEMES.keys()),
    index=list(THEMES.keys()).index(st.session_state["ui_theme"])
)
st.session_state["ui_theme"] = theme_name
T = THEMES[theme_name]

st.markdown(f"""
<style>
* {{ box-sizing: border-box !important; }}
.stApp {{ background: {T['bg']} !important; }}
.main .block-container {{
  max-width: 720px !important;
  padding: 12px 12px 80px 12px !important;
  margin: auto !important;
}}
h1, h2, h3, p, label, span {{ color: {T['text']} !important; }}
.stCaption, small {{ color: {T['subtext']} !important; }}
.stTextInput input, .stTextArea textarea {{
  background: {T['input_bg']} !important;
  color: {T['input_text']} !important;
  border-radius: 12px !important;
  font-weight: 600 !important;
  width: 100% !important;
  border: 2px solid {T['primary']} !important;
}}
.stSelectbox > div > div {{
  background: {T['input_bg']} !important;
  color: {T['input_text']} !important;
  border-radius: 12px !important;
}}
.stButton button {{
  background: linear-gradient(90deg, {T['primary']}, {T['primary2']}) !important;
  color: white !important;
  border-radius: 50px !important;
  font-weight: 700 !important;
  width: 100% !important;
  height: 52px !important;
  border: none !important;
}}
.stDownloadButton button {{
  background: {T['success']} !important;
  color: white !important;
  border-radius: 12px !important;
  width: 100% !important;
  border: none !important;
}}
.stFileUploader, .stFileUploader > div {{ width: 100% !important; }}
.card {{
  background: {T['card']};
  border: 1px solid {T['primary']};
  border-radius: 16px;
  padding: 14px;
  margin: 12px 0;
  width: 100% !important;
}}
.colour-preview {{
  width: 100%;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 20px;
  margin: 8px 0;
  border: 2px solid white;
}}
video {{
  border-radius: 16px !important;
  width: 100% !important;
  max-height: 560px !important;
  object-fit: contain !important;
  border: 2px solid {T['primary']} !important;
}}
@media (max-width: 600px) {{
  .main .block-container {{ padding: 8px 8px 80px 8px !important; }}
  h1 {{ font-size: 28px !important; }}
  video {{ max-height: 420px !important; }}
}}
</style>
""", unsafe_allow_html=True)

if "video_path" not in st.session_state:
    st.session_state["video_path"] = None
if "clips" not in st.session_state:
    st.session_state["clips"] = []
if "selected_clip" not in st.session_state:
    st.session_state["selected_clip"] = 0
if "viral_done" not in st.session_state:
    st.session_state["viral_done"] = False
if "sub_debug" not in st.session_state:
    st.session_state["sub_debug"] = ""

def get_drive_id(link):
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", link)
    if m:
        return m.group(1)
    m = re.search(r"id=([a-zA-Z0-9_-]+)", link)
    if m:
        return m.group(1)
    return None

def download_drive(link, out_path):
    fid = get_drive_id(link)
    if not fid:
        st.error("Could not find ID in link")
        return False
    try:
        import gdown
        url = "https://drive.google.com/uc?id=" + fid
        gdown.download(url, out_path, quiet=True, fuzzy=True)
        if os.path.exists(out_path):
            if os.path.getsize(out_path) > 10000:
                f = open(out_path, "rb")
                h = f.read(30)
                f.close()
                if b"<html" not in h.lower():
                    return True
    except Exception:
        pass
    try:
        session = requests.Session()
        url = "https://drive.google.com/uc?export=download&id=" + fid
        r = session.get(url, stream=True)
        for key, val in r.cookies.items():
            if key.startswith("download_warning"):
                url = "https://drive.google.com/uc?export=download&confirm=" + val + "&id=" + fid
                r = session.get(url, stream=True)
                break
        f = open(out_path, "wb")
        for chunk in r.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)
        f.close()
        if os.path.exists(out_path):
            if os.path.getsize(out_path) > 10000:
                f = open(out_path, "rb")
                h = f.read(30)
                f.close()
                if b"<html" not in h.lower():
                    return True
                st.error("Set Drive to Anyone with link")
                return False
    except Exception:
        st.error("Download error")
    return False

def get_duration(path):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    res = subprocess.run(
        [ffmpeg, "-i", path],
        capture_output=True,
        text=True
    )
    m = re.search(r"Duration: (\d+):(\d+):(\d+)", res.stderr)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        s = int(m.group(3))
        return h * 3600 + mi * 60 + s
    return 0

def fmt_time(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def fmt_ass_time(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int((t % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def split_lines(txt, max_words):
    words = txt.upper().split()
    lines = []
    for j in range(0, len(words), max_words):
        lines.append(" ".join(words[j:j+max_words]))
    return lines

def write_ass(ass_path, segments, font_name, font_size, colour, bstyle, outline, shadow, align, marg_v):
    # ASS header - Style ikkade fix, FFmpeg ki force_style avasaram ledu
    header = "[Script Info]\n"
    header += "ScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
    header += "[V4+ Styles]\n"
    header += "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
    # BackColour black with alpha 80 = &H80000000&
    style_line = f"Style: Default,{font_name},{font_size},{colour},&HFFFFFF&,&H80000000&,&H80000000&,-1,0,0,0,100,100,0,0,{bstyle},{outline},{shadow},{align},130,130,{marg_v},1\n\n"
    header += style_line
    header += "[Events]\n"
    header += "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    body = ""
    for (s, e, txt) in segments:
        # ASS lo new line = \\N
        txt_esc = txt.replace(",", " ").replace(":", " ")
        body += f"Dialogue: 0,{fmt_ass_time(s)},{fmt_ass_time(e)},Default,,0,0,0,,{txt_esc}\n"
    f = open(ass_path, "w", encoding="utf-8")
    f.write(header + body)
    f.close()
    return os.path.getsize(ass_path)

def make_ass_from_audio(audio_path, ass_path, fallback_text, max_words, duration, style_params):
    font_name, font_size, colour, bstyle, outline, shadow, align, marg_v = style_params
    segments = []
    whisper_ok = False
    try:
        import whisper
        model = whisper.load_model("tiny")
        result = model.transcribe(audio_path, fp16=False)
        if result.get("segments"):
            for seg in result["segments"]:
                txt = seg["text"].strip()
                if not txt:
                    continue
                lines = split_lines(txt, max_words)
                txt2 = "\\N".join(lines)
                segments.append((seg["start"], seg["end"], txt2))
            if len(segments) > 0:
                whisper_ok = True
    except Exception as e:
        whisper_ok = False
    if not whisper_ok or len(segments) == 0:
        # FALLBACK - 100% Guarantee subtitles vasthayi
        # Caption text ni 3 parts ga split chesi full duration ki pettam
        lines = split_lines(fallback_text, max_words)
        # Prathi 5 sec ki oka line chupistham - Video motham subtitles untayi
        chunk = max(4, duration / max(1, len(lines)))
        for i, ln in enumerate(lines):
            s = i * chunk
            e = min(duration, s + chunk)
            if s < duration:
                segments.append((s, e, ln))
        if len(segments) == 0:
            segments.append((0, duration, "\\N".join(lines)))
    size = write_ass(ass_path, segments, font_name, font_size, colour, bstyle, outline, shadow, align, marg_v)
    return whisper_ok, len(segments), size

def get_safe_font_size(font_size, max_words):
    if max_words <= 2:
        return font_size
    if max_words == 3:
        if font_size > 20:
            return 20
        return font_size
    if font_size > 18:
        return 18
    return font_size

def make_clip(
    input_path, output_path, start, duration,
    aspect, captions_on, caption_text,
    caption_color, font, font_size,
    font_style, subtitle_position,
    outline_size, music_option,
    music_volume, fade_music,
    uploaded_music_path, effect,
    max_words
):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    tmpdir = tempfile.mkdtemp()
    ass_path = os.path.join(tmpdir, "subs.ass")
    # FFmpeg ki path escape - Windows / Linux rendu work avvali
    ass_esc = ass_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    if "9:16" in aspect:
        base_crop = "crop=ih*9/16:ih,scale=1080:1920:force_original_aspect_ratio=disable"
    elif "1:1" in aspect:
        base_crop = "crop=min(iw\\,ih):min(iw\\,ih),scale=1080:1080"
    else:
        base_crop = "scale=1920:1080:force_original_aspect_ratio=disable"

    if "Vibrant" in effect:
        eff = ",eq=contrast=1.15:saturation=1.4:brightness=0.05"
    elif "Cinematic" in effect:
        eff = ",eq=contrast=1.2:brightness=-0.05:saturation=1.1"
    elif "Black" in effect:
        eff = ",hue=s=0,eq=contrast=1.1"
    elif "Vintage" in effect:
        eff = ",eq=contrast=1.1:brightness=0.03:saturation=0.8"
    elif "Sharpen" in effect:
        eff = ",unsharp=5:5:1.0:5:5:0.0,eq=contrast=1.1:saturation=1.2"
    elif "Dark Mode" in effect:
        eff = ",eq=contrast=1.2:brightness=-0.08:saturation=1.2"
    else:
        eff = ""

    base_vf = base_crop + eff
    vf = base_vf

    sub_status = "OFF"
    if captions_on:
        # Font map
        if "Montserrat" in font:
            ff_font = "Arial Black"
        elif "Bebas" in font:
            ff_font = "Arial Narrow"
        elif "Anton" in font:
            ff_font = "Impact"
        elif "Impact" in font:
            ff_font = "Impact"
        else:
            ff_font = "Arial"

        col = CAPTION_COLOURS.get(caption_color, "&H00FFFF&")

        if "No Box" in font_style:
            bstyle = 1
            outl = outline_size
            shad = 0
        elif "Outline Only" in font_style:
            bstyle = 1
            outl = outline_size + 1
            shad = 0
        elif "Shadow" in font_style:
            bstyle = 1
            outl = 1
            shad = 2
        else:
            bstyle = 3
            outl = outline_size
            shad = 1

        if "Middle" in subtitle_position:
            align = 5
            marg = 0
        elif "Top" in subtitle_position:
            align = 8
            marg = 140
        else:
            align = 2
            marg = 300

        safe_size = get_safe_font_size(font_size, max_words)
        style_params = (ff_font, safe_size, col, bstyle, outl, shad, align, marg)

        # Audio extract chesi Whisper ki ivvu
        audio_path = os.path.join(tmpdir, "audio.wav")
        cmd_a = [
            ffmpeg, "-y",
            "-ss", str(start),
            "-t", str(duration),
            "-i", input_path,
            "-vn", "-ac", "1", "-ar", "16000",
            audio_path
        ]
        subprocess.run(cmd_a, capture_output=True)
        if os.path.exists(audio_path):
            whisper_ok, nseg, sz = make_ass_from_audio(
                audio_path, ass_path, caption_text, max_words, duration, style_params
            )
            if whisper_ok:
                sub_status = f"Whisper OK - {nseg} lines - {sz} bytes"
            else:
                sub_status = f"Fallback Text - {nseg} lines - {sz} bytes - Whisper failed, kani subtitles vasthayi"
        else:
            # Audio lekapoina ASS create cheyi
            lines = split_lines(caption_text, max_words)
            segs = []
            chunk = max(4, duration / max(1, len(lines)))
            for i, ln in enumerate(lines):
                segs.append((i * chunk, min(duration, (i + 1) * chunk), ln))
            sz = write_ass(ass_path, segs, ff_font, safe_size, col, bstyle, outl, shad, align, marg)
            sub_status = f"No Audio - Fallback - {sz} bytes"

        # SUBTITLES FIX: force_style vadakunda, direct ASS file
        # ASS lone style undi kabatti FFmpeg direct ga burn chesthadi
        vf = base_vf + ",subtitles='" + ass_esc + "'"
        st.session_state["sub_debug"] = sub_status

    music_path = None
    if music_option != "No Music":
        if uploaded_music_path:
            if os.path.exists(uploaded_music_path):
                music_path = uploaded_music_path

    if music_path:
        mv = music_volume / 100.0
        if fade_music:
            af = "[0:a]volume=1.0[a0];"
            af += "[1:a]volume=" + str(mv)
            af += ",afade=t=in:st=0:d=1"
            af += ",afade=t=out:st=" + str(duration - 1) + ":d=1[a1];"
            af += "[a0][a1]amix=inputs=2:duration=first[aout]"
        else:
            af = "[0:a]volume=1.0[a0];"
            af += "[1:a]volume=" + str(mv) + "[a1];"
            af += "[a0][a1]amix=inputs=2:duration=first[aout]"
        cmd = [
            ffmpeg, "-y",
            "-ss", str(start),
            "-t", str(duration),
            "-i", input_path,
            "-stream_loop", "-1",
            "-i", music_path,
            "-vf", vf,
            "-filter_complex", af,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-crf", "23",
            "-shortest", output_path
        ]
    else:
        cmd = [
            ffmpeg, "-y",
            "-ss", str(start),
            "-t", str(duration),
            "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-crf", "23",
            output_path
        ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if os.path.exists(output_path):
        if os.path.getsize(output_path) > 10000:
            return True, sub_status
    # FFmpeg error unte chupinchu - Subtitle error aithe telusthadi
    st.session_state["sub_debug"] = "FFmpeg Error: " + res.stderr[-500:]
    return False, sub_status

st.markdown(
    '<h1 style="text-align:center;">ClipShort AI</h1>',
    unsafe_allow_html=True
)
st.markdown(
    '<p style="text-align:center;">Turn Any Video Into Viral Shorts</p>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="card"><h3>1. Upload Your Video</h3></div>',
    unsafe_allow_html=True
)
uploaded = st.file_uploader(
    "Choose a video file",
    type=["mp4", "mov", "mkv", "webm"]
)
drive_link = st.text_input(
    "Paste Google Drive Link",
    placeholder="https://drive.google.com/file/d/..."
)
if drive_link and st.button("Download from Drive"):
    with st.spinner("Downloading..."):
        tmp = tempfile.mktemp(suffix=".mp4")
        if download_drive(drive_link, tmp):
            st.session_state["video_path"] = tmp
            st.session_state["clips"] = []
            st.session_state["viral_done"] = False
            st.success("Downloaded! Video is ready.")
            st.rerun()
        else:
            st.error("Download failed. Set Drive to Anyone with link.")

video_path = st.session_state.get("video_path")
if uploaded:
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tf.write(uploaded.read())
    tf.close()
    video_path = tf.name
    st.session_state["video_path"] = video_path
if video_path and os.path.exists(video_path):
    f = open(video_path, "rb")
    vb = f.read()
    f.close()
    st.video(vb)
    mb = len(vb) // 1024 // 1024
    st.caption("Video loaded: " + str(mb) + " MB")

st.markdown(
    '<div class="card"><h3>2. Clip Settings</h3></div>',
    unsafe_allow_html=True
)
prompt = st.text_input(
    "Prompt",
    placeholder="Moment most likely to go viral"
)
clip_len = st.slider("Clip Length (seconds)", 15, 60, 30)
st.caption("Normal Clip: 30 Sec - Best for Shorts / Reels")
aspect = st.selectbox(
    "Aspect Ratio",
    ["9:16 - Shorts / Reels", "1:1 - Post", "16:9 - YouTube"]
)
num_clips = st.slider("Number of Clips", 1, 3, 1)
captions = st.toggle("Auto Captions", value=True)
if captions:
    st.success("Subtitles ON - Video lo kanipisthayi")
else:
    st.warning("Subtitles OFF - Toggle ON cheyi, lekapothe subtitles ravu!")

st.markdown(
    '<div class="card"><h3>3. Captions - Position, Style & Colour</h3></div>',
    unsafe_allow_html=True
)
caption_text = st.text_input("Caption Text", value="FOLLOW FOR MORE")
st.caption("Whisper fail ayina kuda ee text subtitles la vasthadi - Guarantee")

c1, c2 = st.columns(2)
with c1:
    font = st.selectbox(
        "Caption Font Style",
        [
            "Poppins Bold - Clean",
            "Montserrat Bold - YouTube",
            "Bebas Neue - Viral Reels",
            "Anton - Bold Movie",
            "Oswald Bold - News",
            "Impact - Meme Style"
        ]
    )
with c2:
    caption_color = st.selectbox(
        "Caption Color",
        list(CAPTION_COLOURS.keys())
    )

preview_hex = PREVIEW_COLOURS.get(caption_color, "#FFE600")
st.markdown(
    f'<div class="colour-preview" style="background:{preview_hex}; color:black;">{caption_text.upper()} - {caption_color}</div>',
    unsafe_allow_html=True
)
st.caption("This is exactly how it will look in video - Same colour")

c3, c4 = st.columns(2)
with c3:
    words_opt = st.selectbox(
        "Words Per Line - Anti Cut",
        [
            "2 Words - Word Cut - Safest - Opus Style",
            "3 Words - Balanced",
            "4 Words - Long - May Cut on Phone"
        ]
    )
    if "2 Words" in words_opt:
        max_words = 2
    elif "3 Words" in words_opt:
        max_words = 3
    else:
        max_words = 4
with c4:
    font_style = st.selectbox(
        "Subtitle Style",
        [
            "Bold + Black Box - Viral Reels",
            "Bold + No Box - Clean",
            "Outline Only - Gaming",
            "Shadow - Cinematic"
        ]
    )

c5, c6 = st.columns(2)
with c5:
    font_size = st.slider("Font Size", 14, 48, 22)
    if font_size <= 26:
        st.caption("Perfect - Will not cut off")
    elif font_size <= 34:
        st.caption("Large - Will show in 2 lines")
    else:
        st.caption("Very Large - May cut off")
with c6:
    outline_size = st.slider("Outline Thickness", 1, 5, 2)

subtitle_position = st.selectbox(
    "Caption Position - Safe Area",
    [
        "Bottom Center - Safe for Shorts - Above Buttons",
        "Middle Center - Face Video",
        "Top Center - Below Notch"
    ]
)
st.caption("Bottom = 300px above bottom, so Like/Comment buttons do not hide text")

st.markdown(
    '<div class="card"><h3>4. Background Music</h3></div>',
    unsafe_allow_html=True
)
music_option = st.selectbox(
    "Choose Music",
    ["No Music - Original Audio Only", "Upload My Own Music"]
)
if music_option != "No Music - Original Audio Only":
    m1, m2 = st.columns(2)
    with m1:
        music_volume = st.slider("Music Volume", 0, 100, 20)
        st.caption("Music: " + str(music_volume) + "%")
    with m2:
        fade_music = st.toggle("Fade In / Fade Out", value=True)
else:
    music_volume = 0
    fade_music = False
uploaded_music = None
if music_option == "Upload My Own Music":
    uploaded_music = st.file_uploader(
        "Upload Your Song (MP3)",
        type=["mp3", "wav", "m4a"]
    )
    if uploaded_music:
        st.success("Music Uploaded: " + uploaded_music.name)
        st.audio(uploaded_music)
    else:
        st.info("Upload an MP3 - Trending song / Gaming beat")

st.markdown(
    '<div class="card"><h3>5. Video Effect</h3></div>',
    unsafe_allow_html=True
)
effect = st.selectbox(
    "Choose Effect",
    [
        "No Effect - Original",
        "Vibrant - Reels Pop",
        "Cinematic - Movie Look",
        "Black and White - Classic",
        "Vintage - Old Film",
        "Sharpen + HDR - Ultra Clear",
        "Dark Mode - Night Gaming"
    ]
)

if video_path and os.path.exists(video_path):
    if st.button("Generate Viral Clips"):
        duration = get_duration(video_path)
        if duration == 0:
            st.error("Could not read video. Re-upload.")
        else:
            uploaded_music_path = None
            if uploaded_music:
                tfm = tempfile.NamedTemporaryFile(
                    delete=False, suffix=".mp3"
                )
                tfm.write(uploaded_music.read())
                tfm.close()
                uploaded_music_path = tfm.name
            with st.spinner("Generating... Please wait - Subtitles burning..."):
                st.session_state["clips"] = []
                st.session_state["selected_clip"] = 0
                for i in range(num_clips):
                    start = (duration // (num_clips + 1)) * (i + 1)
                    if start < 0:
                        start = 0
                    out = tempfile.mktemp(suffix="_clip.mp4")
                    ok, sub_msg = make_clip(
                        video_path, out, start,
                        min(clip_len, duration - start),
                        aspect, captions, caption_text,
                        caption_color, font, font_size,
                        font_style, subtitle_position,
                        outline_size, music_option,
                        music_volume, fade_music,
                        uploaded_music_path, effect,
                        max_words
                    )
                    if ok:
                        f = open(out, "rb")
                        cb = f.read()
                        f.close()
                        st.session_state["clips"].append(
                            {"name": "Clip " + str(i + 1), "data": cb}
                        )
                        st.info("Subtitles: " + sub_msg)
                    else:
                        st.error("Failed to create Clip " + str(i + 1))
                        st.error(sub_msg)
                st.session_state["viral_done"] = True
            st.balloons()
            st.rerun()
else:
    st.info("Upload a video first to generate clips")

if st.session_state["clips"]:
    st.markdown(
        '<div class="card"><h3>Your Clips Ready</h3></div>',
        unsafe_allow_html=True
    )
    if st.session_state.get("sub_debug"):
        st.caption("Debug: " + st.session_state["sub_debug"])
    clip_names = []
    for c in st.session_state["clips"]:
        clip_names.append(c["name"])
    selected = st.radio(
        "Choose Clip to Play:",
        clip_names,
        index=st.session_state["selected_clip"],
        horizontal=True
    )
    sel_idx = clip_names.index(selected)
    st.session_state["selected_clip"] = sel_idx
    c = st.session_state["clips"][sel_idx]
    st.success(c["name"] + " Ready - 1080p HD + Subtitles Burned")
    st.video(c["data"])
    st.download_button(
        "Download " + c["name"],
        c["data"],
        file_name="clipshort_clip.mp4",
        mime="video/mp4"
    )

    if st.session_state["viral_done"]:
        st.markdown(
            '<div class="card"><h3>Viral Title and Description</h3></div>',
            unsafe_allow_html=True
        )
        base_topic = prompt
        if not base_topic:
            base_topic = caption_text
        if base_topic == "FOLLOW FOR MORE":
            base_topic = "This Amazing Moment"
        t1 = base_topic + " You Wont Believe This! #shorts"
        t2 = "OMG! " + base_topic + " Viral Moment!"
        t3 = base_topic + " - Watch Till End!"
        titles = [t1, t2, t3]
        st.write("Copy and paste into YouTube Title:")
        selected_title = st.selectbox("Choose Best Title", titles)
        st.text_input("Your Viral Title", value=selected_title)
        desc = selected_title + "\n\n"
        desc += base_topic + " - This is the most viral moment. "
        desc += "Watch till end and comment your reaction.\n\n"
        desc += "Follow ClipShort AI for more viral shorts!\n\n"
        desc += "#shorts #viral #trending #youtubeshorts #reels #fyp"
        st.write("Description - Copy All:")
        st.text_area("Your Viral Description", value=desc, height=180)
        htags = "#shorts #viral #trending #youtubeshorts #reels #fyp"
        st.write("Hashtags:")
        st.text_input("Hashtags", value=htags)
        st.success("Title + Description Ready!")

st.markdown(
    '<p style="text-align:center;">Made by ClipShort AI - Free for Creators</p>',
    unsafe_allow_html=True
)
