import streamlit as st
import requests, os, re, subprocess, tempfile
import imageio_ffmpeg

st.set_page_config(page_title="ClipShort AI", page_icon="✂️", layout="centered")

# --- UI ---
st.markdown("""
<style>
.stApp { background: linear-gradient(180deg, #0f0c29 0%, #302b63 50%, #24243e 100%) !important; }
h1, h2, h3, p, label { color: white !important; }
.stTextInput input, .stTextArea textarea { background: white !important; color: black !important; -webkit-text-fill-color: black !important; border-radius: 12px !important; font-weight: 600 !important; font-size: 15px !important; }
.stTextInput input { height: 48px !important; }
.stTextInput input::placeholder, .stTextArea textarea::placeholder { color: #888 !important; -webkit-text-fill-color: #888 !important; }
.stSelectbox div[data-baseweb="select"] div { background: white !important; color: black !important; border-radius: 12px !important; }
div[data-baseweb="select"] span { color: black !important; font-weight: 600 !important; }
div[data-baseweb="menu"] div { color: black !important; background: white !important; }
.stButton button { background: linear-gradient(90deg, #FF512F, #DD2476) !important; color: white !important; border: none !important; border-radius: 50px !important; font-weight: 700 !important; width: 100% !important; height: 50px !important; font-size: 16px !important; }
.stDownloadButton button { background: #00C853 !important; border-radius: 12px !important; height: 46px !important; }
.card { background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.15); border-radius: 16px; padding: 16px; margin: 14px 0; }
.badge { background: #FFD700; color: black; padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 800; }
video { border-radius: 16px !important; max-height: 520px !important; object-fit: cover !important; }
</style>
""", unsafe_allow_html=True)

if "video_path" not in st.session_state: st.session_state["video_path"] = None
if "clips" not in st.session_state: st.session_state["clips"] = []
if "selected_clip" not in st.session_state: st.session_state["selected_clip"] = 0
if "viral_done" not in st.session_state: st.session_state["viral_done"] = False

def get_drive_id(link):
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", link)
    if m: return m.group(1)
    m = re.search(r"id=([a-zA-Z0-9_-]+)", link)
    return m.group(1) if m else None

def download_drive(link, out_path):
    fid = get_drive_id(link)
    if not fid:
        st.error("Could not find ID in link")
        return False
    try:
        import gdown
        gdown.download(f"https://drive.google.com/uc?id={fid}", out_path, quiet=True, fuzzy=True)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            with open(out_path, "rb") as f: h = f.read(30)
            if b"<html" not in h.lower():
                return True
    except Exception as e:
        st.write(f"gdown failed, trying direct: {e}")
    try:
        session = requests.Session()
        url = f"https://drive.google.com/uc?export=download&id={fid}"
        r = session.get(url, stream=True)
        for key, val in r.cookies.items():
            if key.startswith("download_warning"):
                url = f"https://drive.google.com/uc?export=download&confirm={val}&id={fid}"
                r = session.get(url, stream=True)
                break
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(1024*1024):
                if chunk: f.write(chunk)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            with open(out_path, "rb") as f: h = f.read(30)
            if b"<html" not in h.lower():
                return True
            else:
                st.error("Drive link is NOT set to 'Anyone with link'. Go to Drive > Share > Anyone with link.")
                return False
    except Exception as e:
        st.error(f"Download error: {e}")
    return False

def get_duration(path):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    res = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+)", res.stderr)
    if m: return int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))
    return 0

def fmt_time(t):
    h = int(t//3600); m = int((t%3600)//60); s = int(t%60); ms = int((t%1)*1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def make_srt_from_audio(audio_path, srt_path, fallback_text):
    # Real subtitles with Whisper AI. If Whisper fails, fallback text is used so clip is never empty.
    try:
        import whisper
        model = whisper.load_model("tiny")
        result = model.transcribe(audio_path, fp16=False)
        if result.get("segments"):
            with open(srt_path, "w", encoding="utf-8") as f:
                for i, seg in enumerate(result["segments"]):
                    txt = seg["text"].strip().upper()
                    if not txt: continue
                    words = txt.split()
                    lines = [" ".join(words[j:j+4]) for j in range(0, len(words), 4)]
                    txt_wrapped = "\\N".join(lines)
                    f.write(f"{i+1}\n{fmt_time(seg['start'])} --> {fmt_time(seg['end'])}\n{txt_wrapped}\n\n")
            if os.path.getsize(srt_path) > 20:
                return True
    except Exception as e:
        print(f"Whisper failed: {e}")
    words = fallback_text.upper().split()
    lines = [" ".join(words[j:j+4]) for j in range(0, len(words), 4)]
    wrapped = "\\N".join(lines)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(f"1\n00:00:00,000 --> 00:00:30,000\n{wrapped}\n\n")
    return False

def make_clip(input_path, output_path, start, duration, aspect, captions_on, caption_text, caption_color, font, font_size, font_style, subtitle_position, outline_size, music_option, music_volume, fade_music, uploaded_music_path, effect):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    tmpdir = tempfile.mkdtemp()
    srt_path = os.path.join(tmpdir, "subs.srt")
    # Escape Windows path colon for FFmpeg subtitles filter
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")

    # --- EFFECT ---
    if "9:16" in aspect:
        base_crop = "crop=ih*9/16:ih,scale=1080:1920:force_original_aspect_ratio=disable"
    elif "1:1" in aspect:
        base_crop = "crop=min(iw\\,ih):min(iw\\,ih),scale=1080:1080"
    else:
        base_crop = "scale=1920:1080:force_original_aspect_ratio=disable"

    effect_map = {
        "No Effect - Original": "",
        "🔥 Vibrant - Reels Pop": ",eq=contrast=1.15:saturation=1.4:brightness=0.05",
        "🎬 Cinematic - Movie Look": ",eq=contrast=1.2:brightness=-0.05:saturation=1.1",
        "⚫ Black & White - Classic": ",hue=s=0,eq=contrast=1.1",
        "📸 Vintage - Old Film": ",eq=contrast=1.1:brightness=0.03:saturation=0.8",
        "✨ Sharpen + HDR - Ultra Clear": ",unsharp=5:5:1.0:5:5:0.0,eq=contrast=1.1:saturation=1.2",
        "🌑 Dark Mode - Night Gaming": ",eq=contrast=1.2:brightness=-0.08:saturation=1.2",
    }
    base_vf = base_crop + effect_map.get(effect, "")
    vf = base_vf

    # --- FONT SIZE + STYLE + SUBTITLE ---
    if captions_on:
        audio_path = os.path.join(tmpdir, "audio.wav")
        cmd_a = [ffmpeg, "-y", "-ss", str(start), "-t", str(duration), "-i", input_path, "-vn", "-ac", "1", "-ar", "16000", audio_path]
        subprocess.run(cmd_a, capture_output=True)
        if os.path.exists(audio_path):
            make_srt_from_audio(audio_path, srt_path, caption_text)
        else:
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(f"1\n00:00:00,000 --> 00:00:30,000\n{caption_text.upper()}\n\n")

        font_map = {
            "Poppins Bold - Clean & Modern": "Arial",
            "Montserrat Bold - YouTube Style": "Arial Black",
            "Bebas Neue - Tall & Viral Reels": "Arial Narrow",
            "Anton - Bold Movie Style": "Impact",
            "Oswald Bold - News Style": "Arial",
            "Impact - Meme Style": "Impact"
        }
        ffmpeg_font = font_map.get(font, "Arial")
        color_map = {"Yellow": "&H00FFFF&", "White": "&HFFFFFF&", "Cyan": "&HFFFF00&", "Pink": "&HFF00FF&", "Green": "&H00FF00&", "Orange": "&H0080FF&"}
        color_code = color_map.get(caption_color, "&H00FFFF&")

        if "No Box" in font_style:
            border_style, outline, shadow = 1, outline_size, 0
        elif "Outline Only" in font_style:
            border_style, outline, shadow = 1, outline_size + 1, 0
        elif "Shadow" in font_style:
            border_style, outline, shadow = 1, 1, 2
        else:
            border_style, outline, shadow = 3, outline_size, 1

        if "Middle" in subtitle_position:
            alignment, margin_v = 5, 0
        elif "Top" in subtitle_position:
            alignment, margin_v = 8, 100
        else:
            alignment, margin_v = 2, 220

        # FontSize = slider value, WrapStyle=2 = Auto wrap, never cut off, MarginL/R=60 = Side padding
        vf = f"{base_vf},subtitles='{srt_escaped}':force_style='FontName={ffmpeg_font},FontSize={font_size},PrimaryColour={color_code},OutlineColour=&H80000000&,BorderStyle={border_style},Outline={outline},Shadow={shadow},Alignment={alignment},MarginV={margin_v},MarginL=60,MarginR=60,Bold=1,WrapStyle=2'"

    # --- MUSIC ---
    music_path = None
    if music_option != "No Music - Original Audio Only":
        if music_option == "📤 Upload My Own Music" and uploaded_music_path and os.path.exists(uploaded_music_path):
            music_path = uploaded_music_path

    if music_path and os.path.exists(music_path):
        mv = music_volume / 100.0
        if fade_music:
            audio_filter = f"[0:a]volume=1.0[a0];[1:a]volume={mv},afade=t=in:st=0:d=1,afade=t=out:st={duration-1}:d=1[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        else:
            audio_filter = f"[0:a]volume=1.0[a0];[1:a]volume={mv}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        cmd = [ffmpeg, "-y", "-ss", str(start), "-t", str(duration), "-i", input_path, "-stream_loop", "-1", "-i", music_path,
               "-vf", vf, "-filter_complex", audio_filter, "-map", "0:v", "-map", "[aout]", "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", "-crf", "23", "-shortest", output_path]
    else:
        cmd = [ffmpeg, "-y", "-ss", str(start), "-t", str(duration), "-i", input_path, "-vf", vf, "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", "-crf", "23", output_path]

    subprocess.run(cmd, capture_output=True)
    return os.path.exists(output_path) and os.path.getsize(output_path) > 10000

# --- HEADER ---
st.markdown('<div style="text-align:center; padding-top:10px;"><span class="badge">✨ 100% FREE • NO WATERMARK • 1080p HD</span></div>', unsafe_allow_html=True)
st.markdown('<h1 style="text-align:center; font-size:40px;">✂️ ClipShort AI</h1>', unsafe_allow_html=True)
st.markdown('<p style="text-align:center; font-size:16px;">Turn Any Video Into Viral Shorts in 1 Click</p>', unsafe_allow_html=True)
st.markdown('<div class="card"><b>📤 Upload - Up to 200MB</b><br><b>☁️ Drive - Up to 4GB</b><br><small>For YouTube: YouTube Studio > Download > Upload to Drive > Paste link here</small></div>', unsafe_allow_html=True)

# --- STEP 1 ---
st.markdown('<div class="card"><h3>1. Upload Your Video</h3></div>', unsafe_allow_html=True)
uploaded = st.file_uploader("Choose a video file", type=["mp4","mov","mkv","webm"])
drive_link = st.text_input("Paste Google Drive Link", placeholder="https://drive.google.com/file/d/... - Set to Anyone with link")
if drive_link and st.button("Download from Drive"):
    with st.spinner("Downloading from Drive... Please wait"):
        tmp = tempfile.mktemp(suffix=".mp4")
        if download_drive(drive_link, tmp):
            st.session_state["video_path"] = tmp
            st.session_state["clips"] = []
            st.session_state["viral_done"] = False
            st.success("Downloaded! Video is ready below.")
            st.rerun()
        else:
            st.error("Download failed. Go to Drive > Share > Anyone with link and try again.")
yt_link = st.text_input("Or Paste YouTube Link - Info Only", placeholder="https://youtu.be/...")
if st.button("Get Video Info"):
    st.warning("YouTube direct download is blocked. Please download from YouTube Studio and upload here.")

video_path = st.session_state.get("video_path")
if uploaded:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tf:
        tf.write(uploaded.read())
        video_path = tf.name
        st.session_state["video_path"] = video_path
if video_path and os.path.exists(video_path):
    with open(video_path, "rb") as f: video_bytes = f.read()
    st.video(video_bytes)
    st.caption(f"Video loaded: {len(video_bytes)//1024//1024} MB")

# --- STEP 2 ---
st.markdown('<div class="card"><h3>2. Clip Settings</h3></div>', unsafe_allow_html=True)
prompt = st.text_input("Prompt", placeholder="Moment most likely to go viral")
clip_len = st.slider("Clip Length (seconds)", 15, 60, 30)
aspect = st.selectbox("Aspect Ratio", ["9:16 - Shorts / Reels", "1:1 - Post", "16:9 - YouTube"])
quality = st.selectbox("Video Quality", ["1080p - HD (Best for Shorts)", "720p - Fast (Testing Only)"])
num_clips = st.slider("Number of Clips", 1, 3, 1)
captions = st.toggle("Auto Captions", value=True)

# --- STEP 3 - FONT ---
st.markdown('<div class="card"><h3>3. Captions - Font Size & Style 🎨</h3></div>', unsafe_allow_html=True)
caption_text = st.text_input("Caption Text", value="FOLLOW FOR MORE")
c1, c2 = st.columns(2)
with c1:
    font = st.selectbox("Caption Font Style", ["Poppins Bold - Clean & Modern", "Montserrat Bold - YouTube Style", "Bebas Neue - Tall & Viral Reels", "Anton - Bold Movie Style", "Oswald Bold - News Style", "Impact - Meme Style"])
with c2:
    caption_color = st.selectbox("Caption Color", ["Yellow", "White", "Cyan", "Pink", "Green", "Orange"])
c3, c4 = st.columns(2)
with c3:
    font_size = st.slider("Font Size", 14, 48, 22)
    if font_size <= 26: st.caption(f"✅ {font_size}px - Perfect - Will not cut off")
    elif font_size <= 34: st.caption(f"⚠️ {font_size}px - Large - Will show in 2 lines")
    else: st.caption(f"🚨 {font_size}px - Very Large - May cut off!")
with c4:
    font_style = st.selectbox("Subtitle Style", ["Bold + Black Box - Viral Reels", "Bold + No Box - Clean", "Outline Only - Gaming Style", "Shadow - Cinematic"])
c5, c6 = st.columns(2)
with c5:
    subtitle_position = st.selectbox("Subtitle Position", ["Bottom Center - Reels Style", "Middle Center", "Top Center"])
with c6:
    outline_size = st.slider("Outline / Border Thickness", 1, 5, 2)

# --- STEP 4 - MUSIC ---
st.markdown('<div class="card"><h3>4. Background Music 🎵</h3></div>', unsafe_allow_html=True)
music_option = st.selectbox("Choose Music", ["No Music - Original Audio Only", "📤 Upload My Own Music"])
if music_option != "No Music - Original Audio Only":
    m1, m2 = st.columns(2)
    with m1:
        music_volume = st.slider("Music Volume", 0, 100, 20)
        st.caption(f"Music: {music_volume}% | Voice: {100-music_volume}%")
    with m2:
        fade_music = st.toggle("Fade In / Fade Out", value=True)
else:
    music_volume = 0
    fade_music = False
uploaded_music = None
if music_option == "📤 Upload My Own Music":
    uploaded_music = st.file_uploader("Upload Your Song (MP3)", type=["mp3", "wav", "m4a"])
    if uploaded_music:
        st.success(f"Music Uploaded: {uploaded_music.name} ✅")
        st.audio(uploaded_music)
    else:
        st.info("👆 Upload an MP3 - Trending song / Gaming beat - 100% reliable")

# --- STEP 5 - EFFECT ---
st.markdown('<div class="card"><h3>5. Video Effect ✨</h3></div>', unsafe_allow_html=True)
effect = st.selectbox("Choose Effect", ["No Effect - Original", "🔥 Vibrant - Reels Pop", "🎬 Cinematic - Movie Look", "⚫ Black & White - Classic", "📸 Vintage - Old Film", "✨ Sharpen + HDR - Ultra Clear", "🌑 Dark Mode - Night Gaming"])

# --- GENERATE ---
if video_path and os.path.exists(video_path):
    if st.button("🔥 Generate Viral Clips"):
        duration = get_duration(video_path)
        if duration == 0:
            st.error("Could not read video. Please re-upload.")
        else:
            uploaded_music_path = None
            if uploaded_music:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tf_m:
                    tf_m.write(uploaded_music.read())
                    uploaded_music_path = tf_m.name
            with st.spinner(f"Generating: {font} {font_size}px + {music_option} + {effect}... Please wait"):
                st.session_state["clips"] = []
                st.session_state["selected_clip"] = 0
                for i in range(num_clips):
                    start = max(0, (duration // (num_clips + 1)) * (i + 1))
                    out = tempfile.mktemp(suffix=f"_clip{i+1}.mp4")
                    ok = make_clip(video_path, out, start, min(clip_len, duration - start), aspect, captions, caption_text, caption_color, font, font_size, font_style, subtitle_position, outline_size, music_option, music_volume, fade_music, uploaded_music_path, effect)
                    if ok:
                        with open(out, "rb") as f: cb = f.read()
                        st.session_state["clips"].append({"name": f"Clip {i+1}", "data": cb})
                    else:
                        st.error(f"Failed to create Clip {i+1}")
                st.session_state["viral_done"] = True
            st.balloons()
            st.rerun()
else:
    st.info("👆 Upload a video first to generate clips")

# --- SHOW ONLY ONE CLIP - NO DOUBLE AUDIO ---
if st.session_state["clips"]:
    st.markdown('<div class="card"><h3>✅ Your Clips Ready - Play One At A Time</h3><p>👆 Select a clip - Only one will play.</p></div>', unsafe_allow_html=True)
    clip_names = [c["name"] for c in st.session_state["clips"]]
    selected = st.radio("Choose Clip to Play:", clip_names, index=st.session_state["selected_clip"], horizontal=True, key="clip_selector_single")
    sel_idx = clip_names.index(selected)
    st.session_state["selected_clip"] = sel_idx
    c = st.session_state["clips"][sel_idx]
    st.success(f"{c['name']} Ready! - 1080p HD + {font} {font_size}px + {music_option} + {effect}")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.video(c["data"])
    st.download_button(f"⬇️ Download {c['name']}", c["data"], file_name=f"clipshort_{c['name'].lower().replace(' ','')}.mp4", mime="video/mp4", key=f"dl_single_{sel_idx}")

    if st.session_state["viral_done"]:
        st.markdown('<div class="card"><h3>🚀 Viral Title & Description - Auto Generated</h3></div>', unsafe_allow_html=True)
        base_topic = prompt if prompt else caption_text if caption_text else "This Video"
        if base_topic == "FOLLOW FOR MORE":
            base_topic = "This Amazing Moment"
        titles = [f"{base_topic} 😱 You Won't Believe This! #shorts", f"OMG! {base_topic} 🔥 Viral Moment!", f"{base_topic} - Watch Till End! 👀"]
        st.write("**👇 Copy and paste into YouTube Title:**")
        selected_title = st.selectbox("Choose Best Title", titles, key="title_select_fixed")
        st.text_input("Your Viral Title", value=selected_title, key="viral_title_fixed")
        desc = f"""{selected_title}\n\n{base_topic} - This is the most viral moment from this video! Watch till end and let me know your reaction in comments 👇\n\n🔥 Follow @ClipShort AI for more viral shorts!\n\n#shorts #viral #trending #youtubeshorts #reels #fyp #viralvideo #shortsfeed\n"""
        st.write("**👇 Description - Copy All:**")
        st.text_area("Your Viral Description", value=desc, height=180, key="viral_desc_fixed")
        hashtags = "#shorts #viral #trending #youtubeshorts #reels #fyp #viralvideo #shortsfeed #clipshortai #foryou"
        st.write("**👇 Hashtags:**")
        st.text_input("Hashtags", value=hashtags, key="hashtags_fixed")
        st.success("✅ Title + Description Re
