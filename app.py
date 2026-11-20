import streamlit as st
import requests
import os
import re
import subprocess
import tempfile
import imageio_ffmpeg

st.set_page_config(page_title="ClipShort AI - Pro Editor", page_icon="✂️", layout="wide")

# ---------- THEMES ----------
THEMES = {
    "Dark Purple": {"bg": "#0f0c29", "card": "rgba(255,255,255,0.10)", "text": "#FFFFFF", "subtext": "#B0B0B0", "primary": "#DD2476", "primary2": "#FF512F", "success": "#00C853", "input_bg": "#FFFFFF", "input_text": "#000000"},
    "Neon Black": {"bg": "#000000", "card": "rgba(0,255,136,0.08)", "text": "#FFFFFF", "subtext": "#00FF88", "primary": "#00FF88", "primary2": "#00D4FF", "success": "#00FF88", "input_bg": "#1A1A1A", "input_text": "#FFFFFF"},
    "Clean White": {"bg": "#F5F5F5", "card": "#FFFFFF", "text": "#000000", "subtext": "#666666", "primary": "#6C5CE7", "primary2": "#A29BFE", "success": "#00B894", "input_bg": "#FFFFFF", "input_text": "#000000"},
}
CAPTION_COLOURS = {"Yellow": "&H00FFFF&", "White": "&HFFFFFF&", "Cyan": "&HFFFF00&", "Pink": "&HFF00FF&", "Green": "&H00FF00&", "Orange": "&H0080FF&", "Red": "&H0000FF&", "Custom": "CUSTOM"}
PREVIEW_COLOURS = {"Yellow": "#FFE600", "White": "#FFFFFF", "Cyan": "#00E5FF", "Pink": "#FF00AA", "Green": "#00FF00", "Orange": "#FF8000", "Red": "#FF0000"}

if "ui_theme" not in st.session_state:
    st.session_state["ui_theme"] = "Dark Purple"
theme_name = st.sidebar.selectbox("UI Theme", list(THEMES.keys()), index=list(THEMES.keys()).index(st.session_state["ui_theme"]))
st.session_state["ui_theme"] = theme_name
T = THEMES[theme_name]

st.markdown(f"""
<style>
.stApp {{ background: {T['bg']} !important; }}
.main .block-container {{ max-width: 760px !important; padding: 12px 12px 80px 12px !important; margin: auto !important; }}
h1, h2, h3, p, label, span {{ color: {T['text']} !important; }}
.stCaption, small {{ color: {T['subtext']} !important; }}
.stTextInput input, .stTextArea textarea {{ background: {T['input_bg']} !important; color: {T['input_text']} !important; border-radius: 12px !important; font-weight: 600 !important; border: 2px solid {T['primary']} !important; }}
.stSelectbox > div > div {{ background: {T['input_bg']} !important; color: {T['input_text']} !important; border-radius: 12px !important; }}
.stButton button {{ background: linear-gradient(90deg, {T['primary']}, {T['primary2']}) !important; color: white !important; border-radius: 50px !important; font-weight: 700 !important; width: 100% !important; height: 52px !important; border: none !important; }}
.stDownloadButton button {{ background: {T['success']} !important; color: white !important; border-radius: 12px !important; width: 100% !important; border: none !important; }}
.card {{ background: {T['card']}; border: 1px solid {T['primary']}; border-radius: 16px; padding: 14px; margin: 12px 0; }}
.colour-preview {{ width: 100%; height: 60px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-weight: 800; margin: 8px 0; border: 2px solid white; }}
video {{ border-radius: 16px !important; width: 100% !important; max-height: 560px !important; object-fit: contain !important; border: 2px solid {T['primary']} !important; }}
</style>
""", unsafe_allow_html=True)

for k, v in [("video_path", None), ("clips", []), ("selected_clip", 0), ("viral_done", False), ("last_upload_name", None), ("whisper_model", None)]:
    if k not in st.session_state:
        st.session_state[k] = v

def get_drive_id(link):
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", link)
    if m: return m.group(1)
    m = re.search(r"id=([a-zA-Z0-9_-]+)", link)
    if m: return m.group(1)
    return None

def download_drive(link, out_path):
    fid = get_drive_id(link)
    if not fid: return False
    try:
        import gdown
        gdown.download(f"https://drive.google.com/uc?id={fid}&export=download&confirm=t", out_path, quiet=False, fuzzy=True, use_cookies=False)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            with open(out_path, "rb") as f:
                if b"<html" not in f.read(30).lower(): return True
    except Exception: pass
    try:
        r = requests.get(f"https://drive.google.com/uc?export=download&id={fid}", stream=True, timeout=300)
        if 'Content-Disposition' not in r.headers:
            for k, v in r.cookies.items():
                if k.startswith('download_warning'):
                    r = requests.get(f"https://drive.google.com/uc?export=download&id={fid}&confirm={v}", stream=True, timeout=300); break
        with open(out_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if chunk: f.write(chunk)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            with open(out_path, "rb") as f:
                if b"<html" not in f.read(30).lower(): return True
    except Exception as e: st.error(f"Drive Error: {e}")
    return False

def download_youtube(url, out_path):
    try:
        import yt_dlp
        ydl_opts = {'format': 'mp4/best[ext=mp4]/best', 'outtmpl': out_path.replace(".mp4", ".%(ext)s"), 'quiet': True, 'no_warnings': True, 'merge_output_format': 'mp4'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        if os.path.exists(out_path): return True
        base = out_path.replace(".mp4", "")
        for f in os.listdir(os.path.dirname(out_path) or "."):
            if f.startswith(os.path.basename(base)) and f.endswith(".mp4"):
                os.rename(os.path.join(os.path.dirname(out_path) or ".", f), out_path); return True
        return False
    except Exception as e: st.error(f"YouTube Error: {e}")
    return False

def get_duration(path):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    res = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+)", res.stderr)
    if m: return int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))
    return 0

def fmt_ass_time(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60); cs = int((t % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def split_lines(txt, max_words):
    words = txt.upper().split(); lines = []
    for j in range(0, len(words), max_words): lines.append(" ".join(words[j:j+max_words]))
    return lines

def hex_to_ass(hex_color):
    # #FFE600 -> &H00E6FF& (BGR)
    hex_color = hex_color.lstrip("#")
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H00{b}{g}{r}&".upper()

def write_ass(ass_path, segments, font_name, font_size, colour, bstyle, outline, shadow, align, marg_v, bold, italic):
    header = "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
    header += f"Style: Default,{font_name},{font_size},{colour},&HFFFFFF&,&H80000000&,&H80000000&,{-1 if bold else 0},{-1 if italic else 0},0,0,100,100,0,0,{bstyle},{outline},{shadow},{align},130,130,{marg_v},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    body = ""
    for (s, e, txt) in segments:
        body += f"Dialogue: 0,{fmt_ass_time(s)},{fmt_ass_time(e)},Default,,0,0,0,,{txt.replace(',', ' ').replace(':', ' ')}\n"
    open(ass_path, "w", encoding="utf-8").write(header + body)

def get_whisper_model():
    if st.session_state["whisper_model"] is None:
        try:
            import whisper
            st.session_state["whisper_model"] = whisper.load_model("tiny")
        except Exception: st.session_state["whisper_model"] = False
    return st.session_state["whisper_model"] if st.session_state["whisper_model"] else None

def make_clip(input_path, output_path, start, duration, aspect, captions_on, caption_text, caption_color_ass, font_name_ff, font_size, font_style, subtitle_position, outline_size, marg_v_custom, bold, italic, music_path_input, music_volume, orig_volume, fade_music, music_start, edit):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    tmpdir = tempfile.mkdtemp()
    ass_path = os.path.join(tmpdir, "subs.ass")
    ass_esc = ass_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    if "9:16" in aspect: base_crop = "crop=ih*9/16:ih,scale=1080:1920"
    elif "1:1" in aspect: base_crop = "crop='min(iw,ih)':'min(iw,ih)',scale=1080:1080"
    elif "4:5" in aspect: base_crop = "crop=ih*4/5:ih,scale=1080:1350"
    else: base_crop = "scale=1920:1080"
    # EDITING - Brightness / Contrast / Saturation / Sharpness
    eq = f",eq=brightness={edit['brightness']}:contrast={edit['contrast']}:saturation={edit['saturation']}"
    if edit['sharpness'] > 0: eq += f",unsharp=5:5:{edit['sharpness']}:5:5:0.0"
    if "Vibrant" in edit['preset']: eq += ",eq=contrast=1.15:saturation=1.4"
    elif "Cinematic" in edit['preset']: eq += ",eq=contrast=1.2:brightness=-0.05:saturation=1.1"
    elif "Black" in edit['preset']: eq += ",hue=s=0,eq=contrast=1.1"
    elif "Vintage" in edit['preset']: eq += ",eq=contrast=1.1:brightness=0.03:saturation=0.8"
    # Flip / Rotate
    extra = ""
    if edit['flip'] == "Horizontal": extra += ",hflip"
    elif edit['flip'] == "Vertical": extra += ",vflip"
    if edit['rotate'] == "90°": extra += ",transpose=1"
    elif edit['rotate'] == "180°": extra += ",transpose=2,transpose=2"
    elif edit['rotate'] == "270°": extra += ",transpose=2"
    # Speed - setpts
    speed = edit['speed']
    base_vf = base_crop + eq + extra
    if speed != 1.0:
        base_vf += f",setpts={1/speed}*PTS"
    vf = base_vf
    if captions_on:
        col = caption_color_ass
        if "No Box" in font_style: bstyle, outl, shad = 1, outline_size, 0
        elif "Outline Only" in font_style: bstyle, outl, shad = 1, outline_size + 1, 0
        elif "Shadow" in font_style: bstyle, outl, shad = 1, 1, 2
        else: bstyle, outl, shad = 3, outline_size, 1
        if "Middle" in subtitle_position: align, marg = 5, 0
        elif "Top" in subtitle_position: align, marg = 8, 140
        elif "Custom" in subtitle_position: align, marg = 2, marg_v_custom
        else: align, marg = 2, 300
        if max_words_global <= 2: safe_size = font_size
        elif max_words_global == 3: safe_size = min(font_size, 28)
        else: safe_size = min(font_size, 24)
        audio_path = os.path.join(tmpdir, "audio.wav")
        subprocess.run([ffmpeg, "-y", "-ss", str(start), "-t", str(duration), "-i", input_path, "-vn", "-ac", "1", "-ar", "16000", audio_path], capture_output=True)
        segments = []; whisper_ok = False; model = get_whisper_model()
        if model is not None:
            try:
                result = model.transcribe(audio_path, fp16=False)
                if result.get("segments"):
                    for seg in result["segments"]:
                        txt = seg["text"].strip()
                        if not txt: continue
                        lines = split_lines(txt, max_words_global)
                        segments.append((seg["start"], seg["end"], "\\N".join(lines)))
                    if segments: whisper_ok = True
            except Exception: whisper_ok = False
        if not whisper_ok or not segments:
            lines = split_lines(caption_text, max_words_global)
            chunk = max(4, duration / max(1, len(lines)))
            for i, ln in enumerate(lines):
                s = i * chunk; e = min(duration, s + chunk)
                if s < duration: segments.append((s, e, ln))
            if not segments: segments.append((0, duration, "\\N".join(lines)))
        write_ass(ass_path, segments, font_name_ff, safe_size, col, bstyle, outl, shad, align, marg, bold, italic)
        vf = base_vf + ",subtitles='" + ass_esc + "'"
    # AUDIO - Music + Speed + Volume
    af_parts = []
    # Speed for audio: atempo
    atempo = ""
    if speed != 1.0:
        # atempo supports 0.5-2.0
        atempo = f",atempo={speed}"
    if music_path_input and os.path.exists(music_path_input):
        mv = music_volume / 100.0
        ov = orig_volume / 100.0
        if fade_music:
            af = f"[0:a]volume={ov},atempo={speed}[a0];[1:a]volume={mv},afade=t=in:st=0:d=1,afade=t=out:st={max(1,duration-1)}:d=1,atrim=start={music_start},asetpts=PTS-STARTPTS[a1];[a0][a1]amix=inputs=2:duration=first[aout]"
            # atempo already in a0, fix duplicate if speed==1
            if speed == 1.0: af = af.replace(",atempo=1.0", "")
        else:
            af = f"[0:a]volume={ov}[a0];[1:a]volume={mv},atrim=start={music_start},asetpts=PTS-STARTPTS[a1];[a0][a1]amix=inputs=2:duration=first[aout]"
        cmd = [ffmpeg, "-y", "-ss", str(start), "-t", str(duration), "-i", input_path, "-stream_loop", "-1", "-i", music_path_input, "-vf", vf, "-filter_complex", af, "-map", "0:v", "-map", "[aout]", "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", "-crf", "23", "-shortest", output_path]
    else:
        if speed != 1.0 or orig_volume != 100:
            af = f"[0:a]volume={orig_volume/100.0},atempo={speed}[aout]"
            cmd = [ffmpeg, "-y", "-ss", str(start), "-t", str(duration), "-i", input_path, "-vf", vf, "-filter_complex", af, "-map", "0:v", "-map", "[aout]", "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", "-crf", "23", output_path]
        else:
            cmd = [ffmpeg, "-y", "-ss", str(start), "-t", str(duration), "-i", input_path, "-vf", vf, "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", "-crf", "23", output_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if os.path.exists(output_path) and os.path.getsize(output_path) > 10000: return True
    if result.stderr: st.error(result.stderr[-500:])
    return False

max_words_global = 2

# ---------- UI ----------
st.markdown('<h1 style="text-align:center;">ClipShort AI - Pro Editor</h1>', unsafe_allow_html=True)
st.markdown('<p style="text-align:center;">Turn Any Video Into Viral Shorts - Full Editing</p>', unsafe_allow_html=True)

st.markdown('<div class="card"><h3>1. Upload Your Video - 4GB Support</h3></div>', unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["📤 Upload - 4GB", "📺 YouTube Link", "📁 Google Drive Link"])
with tab1:
    uploaded = st.file_uploader("Choose a video file - Upto 4GB", type=["mp4", "mov", "mkv", "webm"], key="main_upload")
    if uploaded and st.session_state["last_upload_name"] != uploaded.name + str(uploaded.size):
        st.info(f"File: {uploaded.name} - {uploaded.size/(1024*1024):.1f} MB")
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        with st.spinner("Saving..."):
            for chunk in uploaded: tf.write(chunk)
        tf.close()
        st.session_state["video_path"] = tf.name
        st.session_state["last_upload_name"] = uploaded.name + str(uploaded.size)
        st.session_state["clips"] = []; st.session_state["viral_done"] = False
        st.success("✅ Upload Successful!"); st.rerun()
with tab2:
    youtube_link = st.text_input("Paste YouTube Link", placeholder="https://youtube.com/watch?v=...", key="yt_link")
    if youtube_link and st.button("Download from YouTube", key="yt_btn"):
        with st.spinner("YouTube Downloading..."):
            tmp = tempfile.mktemp(suffix=".mp4")
            if download_youtube(youtube_link, tmp):
                st.session_state["video_path"] = tmp; st.session_state["clips"] = []; st.session_state["viral_done"] = False
                st.success("✅ YouTube Downloaded!"); st.rerun()
            else: st.error("YouTube Failed!")
with tab3:
    drive_link = st.text_input("Paste Google Drive Link", placeholder="https://drive.google.com/file/d/...", key="drive_link")
    if drive_link and st.button("Download from Drive", key="drive_btn"):
        with st.spinner("Drive Downloading..."):
            tmp = tempfile.mktemp(suffix=".mp4")
            if download_drive(drive_link, tmp):
                st.session_state["video_path"] = tmp; st.session_state["clips"] = []; st.session_state["viral_done"] = False
                st.success("✅ Drive Downloaded!"); st.rerun()
            else: st.error("❌ Drive Failed. Share -> Anyone with the link -> Viewer - Chesava?")

video_path = st.session_state.get("video_path")
if video_path and os.path.exists(video_path):
    st.video(video_path)
    st.caption(f"Loaded: {os.path.getsize(video_path)/(1024*1024):.1f} MB")

# ---------- 2. CLIP SETTINGS - 1 TO 30 ----------
st.markdown('<div class="card"><h3>2. Clip Settings - 1 to 30 Clips</h3></div>', unsafe_allow_html=True)
prompt = st.text_input("Prompt", placeholder="Moment most likely to go viral")
c_clip1, c_clip2 = st.columns(2)
with c_clip1:
    clip_len = st.slider("Clip Length (seconds)", 5, 90, 30)
    aspect = st.selectbox("Aspect Ratio", ["9:16 - Shorts / Reels", "1:1 - Post", "4:5 - Instagram Post", "16:9 - YouTube"])
with c_clip2:
    num_clips = st.slider("Number of Clips - 1 to 30", 1, 30, 1)
    captions = st.toggle("Auto Captions", value=True)
    auto_mode = st.selectbox("Clip Pick Mode", ["Auto - Equal Split - Full Video", "Start to End - First Part Only"])

# Trim - Start / End
st.markdown("**✂️ Trim Video - Start / End**")
trim_start = st.slider("Trim Start (seconds) - Video Ekkada Nundi Start Avvali?", 0, 600, 0)
trim_end = st.slider("Trim End (seconds) - 0 = Full Video", 0, 600, 0)
if trim_end > 0 and trim_end <= trim_start:
    st.warning("Trim End > Trim Start Undali!")

# ---------- 3. FONT - FULL ----------
st.markdown('<div class="card"><h3>3. Font Change + Size - Full Control</h3></div>', unsafe_allow_html=True)
caption_text = st.text_input("Caption Text", value="FOLLOW FOR MORE")
f1, f2 = st.columns(2)
with f1:
    font_choice = st.selectbox("✍️ Font Change - Choose Font", ["Poppins Bold - Clean", "Montserrat Bold - YouTube", "Bebas Neue - Viral Reels", "Anton - Bold Movie", "Oswald Bold - News", "Impact - Meme Style", "Arial Black - Simple", "Arial Narrow - Compact", "Verdana Bold - Clear", "Georgia Bold - Premium"])
    # Map to FFmpeg font
    FONT_MAP = {"Poppins Bold - Clean": "Arial Black", "Montserrat Bold - YouTube": "Arial Black", "Bebas Neue - Viral Reels": "Arial Narrow", "Anton - Bold Movie": "Impact", "Oswald Bold - News": "Arial Narrow", "Impact - Meme Style": "Impact", "Arial Black - Simple": "Arial Black", "Arial Narrow - Compact": "Arial Narrow", "Verdana Bold - Clear": "Verdana", "Georgia Bold - Premium": "Georgia"}
    font_name_ff = FONT_MAP[font_choice]
with f2:
    caption_color_name = st.selectbox("Caption Color", list(CAPTION_COLOURS.keys()) + ["Custom - Color Picker"])
    if "Custom" in caption_color_name:
        custom_hex = st.color_picker("Pick Any Color", "#FFE600")
        caption_color_ass = hex_to_ass(custom_hex)
        preview_hex = custom_hex
    else:
        caption_color_ass = CAPTION_COLOURS[caption_color_name]
        preview_hex = PREVIEW_COLOURS.get(caption_color_name, "#FFE600")

f3, f4, f5 = st.columns(3)
with f3:
    font_size = st.slider("🔠 Font Size", 10, 80, 22, help="10 = Chinna, 80 = Peddha - Phone lo cut avvakunda 22-28 best")
with f4:
    bold = st.toggle("Bold", value=True)
    italic = st.toggle("Italic", value=False)
with f5:
    outline_size = st.slider("Outline Thickness", 0, 8, 2)
    shadow_size = st.slider("Shadow (Style lo Shadow select cheyi)", 0, 5, 1)

# Live Preview
st.markdown(f'<div class="colour-preview" style="background:{preview_hex}; color:black; font-size:{min(font_size,32)}px;">{caption_text.upper()} - {font_choice}</div>', unsafe_allow_html=True)

f6, f7 = st.columns(2)
with f6:
    words_opt = st.selectbox("Words Per Line", ["2 Words - Word Cut - Safest - Opus Style", "3 Words - Balanced", "4 Words - Long", "1 Word - Karaoke Style", "5 Words - Full Sentence"])
    if "1 Word" in words_opt: max_words_global = 1
    elif "2 Words" in words_opt: max_words_global = 2
    elif "3 Words" in words_opt: max_words_global = 3
    elif "4 Words" in words_opt: max_words_global = 4
    else: max_words_global = 5
with f7:
    font_style = st.selectbox("Subtitle Style", ["Bold + Black Box - Viral Reels", "Bold + No Box - Clean", "Outline Only - Gaming", "Shadow - Cinematic"])

f8, f9 = st.columns(2)
with f8:
    subtitle_position = st.selectbox("Caption Position", ["Bottom Center - Safe for Shorts", "Middle Center - Face Video", "Top Center - Below Notch", "Custom - Slider tho Pettukoo"])
with f9:
    marg_v_custom = st.slider("Custom Position - Up / Down (0=Bottom, 900=Top)", 0, 900, 300)
    st.caption("Custom select cheste idi work avthadi")

# ---------- 4. MUSIC - FULL ----------
st.markdown('<div class="card"><h3>4. Music Add - Full Control</h3></div>', unsafe_allow_html=True)
music_option = st.selectbox("Choose Music", ["No Music - Original Audio Only", "Upload My Own Music", "Music + Original Mix"])
uploaded_music = None
music_volume = 20; orig_volume = 100; fade_music = True; music_start = 0
if music_option != "No Music - Original Audio Only":
    uploaded_music = st.file_uploader("🎵 Upload Your Song (MP3 / WAV)", type=["mp3", "wav", "m4a"], key="music_upload")
    if uploaded_music:
        st.success("Music Uploaded: " + uploaded_music.name)
        st.audio(uploaded_music)
    m1, m2, m3 = st.columns(3)
    with m1:
        music_volume = st.slider("🎵 Music Volume", 0, 100, 20)
        orig_volume = st.slider("🎤 Original Voice Volume", 0, 100, 100)
    with m2:
        fade_music = st.toggle("Fade In / Fade Out", value=True)
        loop_music = st.toggle("Loop Music - Clip Antha Repeat", value=True)
    with m3:
        music_start = st.slider("Music Start Time (sec) - Song Ekkada Nundi?", 0, 120, 0)
        st.caption("Song lo 30 sec nundi kavali ante 30 pettu")

# ---------- 5. EDITING - ALL SETTINGS ----------
st.markdown('<div class="card"><h3>5. Editing - All Settings</h3></div>', unsafe_allow_html=True)
e1, e2, e3 = st.columns(3)
with e1:
    brightness = st.slider("☀️ Brightness", -0.5, 0.5, 0.0, step=0.05)
    contrast = st.slider("🌓 Contrast", 0.5, 2.0, 1.0, step=0.05)
with e2:
    saturation = st.slider("🎨 Saturation / Colour", 0.0, 2.5, 1.0, step=0.1)
    sharpness = st.slider("🔍 Sharpness", 0.0, 2.0, 0.0, step=0.1)
with e3:
    speed = st.slider("⏩ Speed", 0.5, 2.0, 1.0, step=0.25, help="0.5 = Slow Motion, 2.0 = Fast")
    volume_boost = st.slider("🔊 Volume Boost (Original)", 0, 200, 100)

e4, e5, e6 = st.columns(3)
with e4:
    effect_preset = st.selectbox("Preset Effect", ["No Effect - Original", "Vibrant - Reels Pop", "Cinematic - Movie Look", "Black and White - Classic", "Vintage - Old Film"])
with e5:
    flip = st.selectbox("Flip", ["No Flip", "Horizontal", "Vertical"])
with e6:
    rotate = st.selectbox("Rotate", ["0° - Normal", "90°", "180°", "270°"])

edit_dict = {"brightness": brightness, "contrast": contrast, "saturation": saturation, "sharpness": sharpness, "speed": speed, "preset": effect_preset, "flip": flip, "rotate": rotate}

# ---------- GENERATE ----------
if video_path and os.path.exists(video_path):
    if st.button("🚀 Generate Viral Clips - 1 to 30"):
        duration_total = get_duration(video_path)
        # Trim apply
        start_offset = trim_start
        end_limit = trim_end if trim_end > 0 else duration_total
        usable = max(10, end_limit - start_offset)
        if duration_total == 0:
            st.error("Could not read video.")
        else:
            uploaded_music_path = None
            if uploaded_music:
                tfm = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                tfm.write(uploaded_music.read()); tfm.close(); uploaded_music_path = tfm.name
            with st.spinner(f"Generating {num_clips} Clips... Subtitles burning..."):
                st.session_state["clips"] = []; st.session_state["selected_clip"] = 0
                progress = st.progress(0)
                for i in range(num_clips):
                    if auto_mode.startswith("Start"):
                        start = start_offset + i * clip_len
                    else:
                        # Equal split across usable duration
                        start = start_offset + (usable // (num_clips + 1)) * (i + 1) if num_clips > 1 else start_offset + usable // 2
                        if num_clips == 1:
                            start = start_offset + usable // 3
                    start = min(start, max(0, end_limit - 5))
                    dur = min(clip_len, max(5, end_limit - start))
                    # Speed tho duration adjust - ffmpeg lo setpts handle chesthadi, dur same
                    out = tempfile.mktemp(suffix="_clip.mp4")
                    ok = make_clip(video_path, out, start, dur, aspect, captions, caption_text, caption_color_ass, font_name_ff, font_size, font_style, subtitle_position, outline_size, marg_v_custom, bold, italic, uploaded_music_path, music_volume, volume_boost if music_option == "No Music - Original Audio Only" else orig_volume, fade_music, music_start, edit_dict)
                    if ok:
                        st.session_state["clips"].append({"name": f"Clip {i+1} - {int(start)}s", "path": out, "data": open(out, "rb").read()})
                    else:
                        st.error(f"Failed Clip {i+1}")
                    progress.progress((i+1)/num_clips)
                st.session_state["viral_done"] = True
            st.balloons(); st.rerun()
else:
    st.info("Upload a video first - Upload / YouTube / Drive - Edhaina Okati!")

if st.session_state["clips"]:
    st.markdown('<div class="card"><h3>Your Clips Ready</h3></div>', unsafe_allow_html=True)
    clip_names = [c["name"] for c in st.session_state["clips"]]
    # 30 clips ki dropdown better
    selected = st.selectbox("Choose Clip to Play:", clip_names, index=min(st.session_state["selected_clip"], len(clip_names)-1))
    sel_idx = clip_names.index(selected); st.session_state["selected_clip"] = sel_idx
    c = st.session_state["clips"][sel_idx]
    st.success(c["name"] + " Ready - 1080p HD + Subtitles Burned")
    st.video(c["path"])
    st.download_button("Download " + c["name"], c["data"], file_name="clipshort_clip.mp4", mime="video/mp4")
    if st.session_state["viral_done"]:
        st.markdown('<div class="card"><h3>Viral Title and Description</h3></div>', unsafe_allow_html=True)
        base_topic = prompt if prompt else caption_text
        if base_topic == "FOLLOW FOR MORE": base_topic = "This Amazing Moment"
        titles = [base_topic + " You Wont Believe This! #shorts", "OMG! " + base_topic + " Viral Moment!", base_topic + " - Watch Till End!"]
        selected_title = st.selectbox("Choose Best Title", titles)
        st.text_input("Your Viral Title", value=selected_title)
        desc = selected_title + "\n\n" + base_topic + " - This is the most viral moment. Watch till end.\n\nFollow ClipShort AI for more viral shorts!\n\n#shorts #viral #trending #youtubeshorts #reels #fyp"
        st.text_area("Your Viral Description", value=desc, height=180)
        st.text_input("Hashtags", value="#shorts #viral #trending #youtubeshorts #reels #fyp")
        st.success("Title + Description Ready!")

st.markdown('<p style="text-align:center;">Made by ClipShort AI - Pro Editor</p>', unsafe_allow_html=True)
