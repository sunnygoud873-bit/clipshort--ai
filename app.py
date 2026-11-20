import streamlit as st
import requests
import os
import re
import subprocess
import tempfile
import imageio_ffmpeg

st.set_page_config(page_title="ClipShort AI", page_icon="✂️", layout="wide")

THEMES = {
    "Dark Purple": {"bg": "#0f0c29", "card": "rgba(255,255,255,0.10)", "text": "#FFFFFF", "subtext": "#B0B0B0", "primary": "#DD2476", "primary2": "#FF512F", "success": "#00C853", "input_bg": "#FFFFFF", "input_text": "#000000"},
    "Neon Black": {"bg": "#000000", "card": "rgba(0,255,136,0.08)", "text": "#FFFFFF", "subtext": "#00FF88", "primary": "#00FF88", "primary2": "#00D4FF", "success": "#00FF88", "input_bg": "#1A1A1A", "input_text": "#FFFFFF"},
    "Clean White": {"bg": "#F5F5F5", "card": "#FFFFFF", "text": "#000000", "subtext": "#666666", "primary": "#6C5CE7", "primary2": "#A29BFE", "success": "#00B894", "input_bg": "#FFFFFF", "input_text": "#000000"},
}
CAPTION_COLOURS = {"Yellow": "&H00FFFF&", "White": "&HFFFFFF&", "Cyan": "&HFFFF00&", "Pink": "&HFF00FF&", "Green": "&H00FF00&", "Orange": "&H0080FF&", "Red": "&H0000FF&"}
PREVIEW_COLOURS = {"Yellow": "#FFE600", "White": "#FFFFFF", "Cyan": "#00E5FF", "Pink": "#FF00AA", "Green": "#00FF00", "Orange": "#FF8000", "Red": "#FF0000"}

if "ui_theme" not in st.session_state:
    st.session_state["ui_theme"] = "Dark Purple"
theme_name = st.sidebar.selectbox("UI Theme", list(THEMES.keys()), index=list(THEMES.keys()).index(st.session_state["ui_theme"]))
st.session_state["ui_theme"] = theme_name
T = THEMES[theme_name]

st.markdown(f"""
<style>
.stApp {{ background: {T['bg']} !important; }}
.main .block-container {{ max-width: 720px !important; padding: 12px 12px 80px 12px !important; margin: auto !important; }}
h1, h2, h3, p, label, span {{ color: {T['text']} !important; }}
.stCaption, small {{ color: {T['subtext']} !important; }}
.stTextInput input, .stTextArea textarea {{ background: {T['input_bg']} !important; color: {T['input_text']} !important; border-radius: 12px !important; font-weight: 600 !important; border: 2px solid {T['primary']} !important; }}
.stSelectbox > div > div {{ background: {T['input_bg']} !important; color: {T['input_text']} !important; border-radius: 12px !important; }}
.stButton button {{ background: linear-gradient(90deg, {T['primary']}, {T['primary2']}) !important; color: white !important; border-radius: 50px !important; font-weight: 700 !important; width: 100% !important; height: 52px !important; border: none !important; }}
.stDownloadButton button {{ background: {T['success']} !important; color: white !important; border-radius: 12px !important; width: 100% !important; border: none !important; }}
.card {{ background: {T['card']}; border: 1px solid {T['primary']}; border-radius: 16px; padding: 14px; margin: 12px 0; }}
.colour-preview {{ width: 100%; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 20px; margin: 8px 0; border: 2px solid white; }}
video {{ border-radius: 16px !important; width: 100% !important; max-height: 560px !important; object-fit: contain !important; border: 2px solid {T['primary']} !important; }}
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
        return False
    try:
        import gdown
        url = f"https://drive.google.com/uc?id={fid}&export=download&confirm=t"
        gdown.download(url, out_path, quiet=False, fuzzy=True, use_cookies=False)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            with open(out_path, "rb") as f:
                if b"<html" not in f.read(30).lower():
                    return True
    except Exception:
        pass
    try:
        dl_url = f"https://drive.google.com/uc?export=download&id={fid}"
        r = requests.get(dl_url, stream=True, timeout=120)
        if 'Content-Disposition' not in r.headers:
            for k, v in r.cookies.items():
                if k.startswith('download_warning'):
                    r = requests.get(f"https://drive.google.com/uc?export=download&id={fid}&confirm={v}", stream=True, timeout=120)
                    break
        with open(out_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            with open(out_path, "rb") as f:
                if b"<html" not in f.read(30).lower():
                    return True
    except Exception as e:
        st.error(f"Drive Error: {e}")
    return False

def download_youtube(url, out_path):
    try:
        import yt_dlp
        ydl_opts = {'format': 'mp4/best', 'outtmpl': out_path, 'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            return True
    except Exception as e:
        st.error(f"YouTube Error: {e}")
    return False

def get_duration(path):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    res = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+)", res.stderr)
    if m:
        return int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))
    return 0

def fmt_ass_time(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60); cs = int((t % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def split_lines(txt, max_words):
    words = txt.upper().split(); lines = []
    for j in range(0, len(words), max_words):
        lines.append(" ".join(words[j:j+max_words]))
    return lines

def write_ass(ass_path, segments, font_name, font_size, colour, bstyle, outline, shadow, align, marg_v):
    header = "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
    header += "[V4+ Styles]\n"
    header += "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
    header += f"Style: Default,{font_name},{font_size},{colour},&HFFFFFF&,&H80000000&,&H80000000&,-1,0,0,0,100,100,0,0,{bstyle},{outline},{shadow},{align},130,130,{marg_v},1\n\n"
    header += "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    body = ""
    for (s, e, txt) in segments:
        txt_esc = txt.replace(",", " ").replace(":", " ")
        body += f"Dialogue: 0,{fmt_ass_time(s)},{fmt_ass_time(e)},Default,,0,0,0,,{txt_esc}\n"
    open(ass_path, "w", encoding="utf-8").write(header + body)

def make_clip(input_path, output_path, start, duration, aspect, captions_on, caption_text, caption_color, font, font_size, font_style, subtitle_position, outline_size, music_option, music_volume, fade_music, uploaded_music_path, effect, max_words):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    tmpdir = tempfile.mkdtemp()
    ass_path = os.path.join(tmpdir, "subs.ass")
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
    if captions_on:
        if "Montserrat" in font:
            ff_font = "Arial Black"
        elif "Bebas" in font:
            ff_font = "Arial Narrow"
        elif "Anton" in font or "Impact" in font:
            ff_font = "Impact"
        else:
            ff_font = "Arial"
        col = CAPTION_COLOURS.get(caption_color, "&H00FFFF&")
        if "No Box" in font_style:
            bstyle, outl, shad = 1, outline_size, 0
        elif "Outline Only" in font_style:
            bstyle, outl, shad = 1, outline_size + 1, 0
        elif "Shadow" in font_style:
            bstyle, outl, shad = 1, 1, 2
        else:
            bstyle, outl, shad = 3, outline_size, 1
        if "Middle" in subtitle_position:
            align, marg = 5, 0
        elif "Top" in subtitle_position:
            align, marg = 8, 140
        else:
            align, marg = 2, 300
        if max_words <= 2:
            safe_size = font_size
        elif max_words == 3:
            safe_size = min(font_size, 20)
        else:
            safe_size = min(font_size, 18)
        audio_path = os.path.join(tmpdir, "audio.wav")
        subprocess.run([ffmpeg, "-y", "-ss", str(start), "-t", str(duration), "-i", input_path, "-vn", "-ac", "1", "-ar", "16000", audio_path], capture_output=True)
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
                    segments.append((seg["start"], seg["end"], "\\N".join(lines)))
                if segments:
                    whisper_ok = True
        except Exception:
            whisper_ok = False
        if not whisper_ok or not segments:
            lines = split_lines(caption_text, max_words)
            chunk = max(4, duration / max(1, len(lines)))
            for i, ln in enumerate(lines):
                s = i * chunk; e = min(duration, s + chunk)
                if s < duration:
                    segments.append((s, e, ln))
            if not segments:
                segments.append((0, duration, "\\N".join(lines)))
        write_ass(ass_path, segments, ff_font, safe_size, col, bstyle, outl, shad, align, marg)
        vf = base_vf + ",subtitles='" + ass_esc + "'"
    music_path = None
    if music_option != "No Music" and uploaded_music_path and os.path.exists(uploaded_music_path):
        music_path = uploaded_music_path
    if music_path:
        mv = music_volume / 100.0
        if fade_music:
            af = "[0:a]volume=1.0[a0];[1:a]volume=" + str(mv) + ",afade=t=in:st=0:d=1,afade=t=out:st=" + str(duration - 1) + ":d=1[a1];[a0][a1]amix=inputs=2:duration=first[aout]"
        else:
            af = "[0:a]volume=1.0[a0];[1:a]volume=" + str(mv) + "[a1];[a0][a1]amix=inputs=2:duration=first[aout]"
        cmd = [ffmpeg, "-y", "-ss", str(start), "-t", str(duration), "-i", input_path, "-stream_loop", "-1", "-i", music_path, "-vf", vf, "-filter_complex", af, "-map", "0:v", "-map", "[aout]", "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", "-crf", "23", "-shortest", output_path]
    else:
        cmd = [ffmpeg, "-y", "-ss", str(start), "-t", str(duration), "-i", input_path, "-vf", vf, "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", "-crf", "23", output_path]
    subprocess.run(cmd, capture_output=True)
    if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
        return True
    return False

st.markdown('<h1 style="text-align:center;">ClipShort AI</h1>', unsafe_allow_html=True)
st.markdown('<p style="text-align:center;">Turn Any Video Into Viral Shorts</p>', unsafe_allow_html=True)

st.markdown('<div class="card"><h3>1. Upload Your Video - 4GB Support</h3></div>', unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["📤 Upload - 4GB", "📺 YouTube Link", "📁 Google Drive Link"])
with tab1:
    uploaded = st.file_uploader("Choose a video file - Upto 4GB", type=["mp4", "mov", "mkv", "webm"], key="main_upload")
    if uploaded:
        st.info(f"File: {uploaded.name} - {uploaded.size/(1024*1024):.1f} MB")
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        with st.spinner("Saving..."):
            for chunk in uploaded:
                tf.write(chunk)
        tf.close()
        st.session_state["video_path"] = tf.name
        st.session_state["clips"] = []
        st.session_state["viral_done"] = False
        st.success("✅ Upload Successful!")
        st.rerun()
with tab2:
    youtube_link = st.text_input("Paste YouTube Link", placeholder="https://youtube.com/watch?v=...", key="yt_link")
    if youtube_link and st.button("Download from YouTube", key="yt_btn"):
        with st.spinner("YouTube Downloading..."):
            tmp = tempfile.mktemp(suffix=".mp4")
            if download_youtube(youtube_link, tmp):
                st.session_state["video_path"] = tmp
                st.session_state["clips"] = []
                st.session_state["viral_done"] = False
                st.success("✅ YouTube Downloaded!")
                st.rerun()
            else:
                st.error("YouTube Failed. Private / Age Restricted Aithe Radhu!")
with tab3:
    drive_link = st.text_input("Paste Google Drive Link", placeholder="https://drive.google.com/file/d/...", key="drive_link")
    if drive_link and st.button("Download from Drive", key="drive_btn"):
        with st.spinner("Drive Downloading... 4GB ki Time Pattuddi..."):
            tmp = tempfile.mktemp(suffix=".mp4")
            if download_drive(drive_link, tmp):
                st.session_state["video_path"] = tmp
                st.session_state["clips"] = []
                st.session_state["viral_done"] = False
                st.success("✅ Drive Downloaded!")
                st.rerun()
            else:
                st.error("❌ Drive Failed. Share -> Anyone with the link -> Viewer - Chesava?")

video_path = st.session_state.get("video_path")
if video_path and os.path.exists(video_path):
    st.video(open(video_path, "rb").read())
    st.caption(f"Loaded: {os.path.getsize(video_path)/(1024*1024):.1f} MB")

st.markdown('<div class="card"><h3>2. Clip Settings</h3></div>', unsafe_allow_html=True)
prompt = st.text_input("Prompt", placeholder="Moment most likely to go viral")
clip_len = st.slider("Clip Length (seconds)", 15, 60, 30)
aspect = st.selectbox("Aspect Ratio", ["9:16 - Shorts / Reels", "1:1 - Post", "16:9 - YouTube"])
num_clips = st.slider("Number of Clips", 1, 3, 1)
captions = st.toggle("Auto Captions", value=True)

st.markdown('<div class="card"><h3>3. Captions</h3></div>', unsafe_allow_html=True)
caption_text = st.text_input("Caption Text", value="FOLLOW FOR MORE")
c1, c2 = st.columns(2)
with c1:
    font = st.selectbox("Caption Font Style", ["Poppins Bold - Clean", "Montserrat Bold - YouTube", "Bebas Neue - Viral Reels", "Anton - Bold Movie", "Oswald Bold - News", "Impact - Meme Style"])
with c2:
    caption_color = st.selectbox("Caption Color", list(CAPTION_COLOURS.keys()))
preview_hex = PREVIEW_COLOURS.get(caption_color, "#FFE600")
st.markdown(f'<div class="colour-preview" style="background:{preview_hex}; color:black;">{caption_text.upper()} - {caption_color}</div>', unsafe_allow_html=True)
c3, c4 = st.columns(2)
with c3:
    words_opt = st.selectbox("Words Per Line", ["2 Words - Word Cut - Safest - Opus Style", "3 Words - Balanced", "4 Words - Long - May Cut on Phone"])
    max_words = 2 if "2 Words" in words_opt else (3 if "3 Words" in words_opt else 4)
with c4:
    font_style = st.selectbox("Subtitle Style", ["Bold + Black Box - Viral Reels", "Bold + No Box - Clean", "Outline Only - Gaming", "Shadow - Cinematic"])
c5, c6 = st.columns(2)
with c5:
    font_size = st.slider("Font Size", 14, 48, 22)
with c6:
    outline_size = st.slider("Outline Thickness", 1, 5, 2)
subtitle_position = st.selectbox("Caption Position", ["Bottom Center - Safe for Shorts - Above Buttons", "Middle Center - Face Video", "Top Center - Below Notch"])

st.markdown('<div class="card"><h3>4. Background Music</h3></div>', unsafe_allow_html=True)
music_option = st.selectbox("Choose Music", ["No Music - Original Audio Only", "Upload My Own Music"])
if music_option != "No Music - Original Audio Only":
    m1, m2 = st.columns(2)
    with m1:
        music_volume = st.slider("Music Volume", 0, 100, 20)
    with m2:
        fade_music = st.toggle("Fade In / Fade Out", value=True)
else:
    music_volume, fade_music = 0, False
uploaded_music = None
if music_option == "Upload My Own Music":
    uploaded_music = st.file_uploader("Upload Your Song (MP3)", type=["mp3", "wav", "m4a"], key="music_upload")
    if uploaded_music:
        st.success("Music Uploaded: " + uploaded_music.name)
        st.audio(uploaded_music)

st.markdown('<div class="card"><h3>5. Video Effect</h3></div>', unsafe_allow_html=True)
effect = st.selectbox("Choose Effect", ["No Effect - Original", "Vibrant - Reels Pop", "Cinematic - Movie Look", "Black and White - Classic", "Vintage - Old Film", "Sharpen + HDR - Ultra Clear", "Dark Mode - Night Gaming"])

if video_path and os.path.exists(video_path):
    if st.button("Generate Viral Clips"):
        duration = get_duration(video_path)
        if duration == 0:
            st.error("Could not read video.")
        else:
            uploaded_music_path = None
            if uploaded_music:
                tfm = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                tfm.write(uploaded_music.read())
                tfm.close()
                uploaded_music_path = tfm.name
            with st.spinner("Generating... Subtitles burning..."):
                st.session_state["clips"] = []
                st.session_state["selected_clip"] = 0
                for i in range(num_clips):
                    start = (duration // (num_clips + 1)) * (i + 1)
                    out = tempfile.mktemp(suffix="_clip.mp4")
                    ok = make_clip(video_path, out, start, min(clip_len, duration - start), aspect, captions, caption_text, caption_color, font, font_size, font_style, subtitle_position, outline_size, music_option, music_volume, fade_music, uploaded_music_path, effect, max_words)
                    if ok:
                        st.session_state["clips"].append({"name": "Clip " + str(i + 1), "data": open(out, "rb").read()})
                    else:
                        st.error("Failed Clip " + str(i + 1))
                st.session_state["viral_done"] = True
            st.balloons()
            st.rerun()
else:
    st.info("Upload a video first - Upload / YouTube / Drive - Edhaina Okati!")

if st.session_state["clips"]:
    st.markdown('<div class="card"><h3>Your Clips Ready</h3></div>', unsafe_allow_html=True)
    clip_names = [c["name"] for c in st.session_state["clips"]]
    selected = st.radio("Choose Clip to Play:", clip_names, index=st.session_state["selected_clip"], horizontal=True)
    sel_idx = clip_names.index(selected)
    st.session_state["selected_clip"] = sel_idx
    c = st.session_state["clips"][sel_idx]
    st.success(c["name"] + " Ready - 1080p HD + Subtitles Burned")
    st.video(c["data"])
    st.download_button("Download " + c["name"], c["data"], file_name="clipshort_clip.mp4", mime="video/mp4")
    if st.session_state["viral_done"]:
        st.markdown('<div class="card"><h3>Viral Title and Description</h3></div>', unsafe_allow_html=True)
        base_topic = prompt if prompt else caption_text
        if base_topic == "FOLLOW FOR MORE":
            base_topic = "This Amazing Moment"
        titles = [base_topic + " You Wont Believe This! #shorts", "OMG! " + base_topic + " Viral Moment!", base_topic + " - Watch Till End!"]
        selected_title = st.selectbox("Choose Best Title", titles)
        st.text_input("Your Viral Title", value=selected_title)
        desc = selected_title + "\n\n" + base_topic + " - This is the most viral moment. Watch till end.\n\nFollow ClipShort AI for more viral shorts!\n\n#shorts #viral #trending #youtubeshorts #reels #fyp"
        st.text_area("Your Viral Description", value=desc, height=180)
        st.text_input("Hashtags", value="#shorts #viral #trending #youtubeshorts #reels #fyp")
        st.success("Title + Description Ready!")

st.markdown('<p style="text-align:center;">Made by ClipShort AI</p>', unsafe_allow_html=True)
