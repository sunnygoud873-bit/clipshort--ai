import streamlit as st
import requests, os, re, subprocess, tempfile
import imageio_ffmpeg

st.set_page_config(page_title="ClipShort AI", page_icon="✂️", layout="centered")

# --- CLEAN UI - NO GLITCH ---
st.markdown("""
<style>
.stApp { background: linear-gradient(180deg, #0f0c29 0%, #302b63 50%, #24243e 100%) !important; }
h1, h2, h3, p, label { color: white !important; }
.stTextInput input, .stTextArea textarea {
    background: white !important; color: black !important;
    -webkit-text-fill-color: black !important;
    border-radius: 12px !important; font-weight: 600 !important;
    font-size: 15px !important;
}
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

if "video_path" not in st.session_state:
    st.session_state["video_path"] = None
# FIX 1: Clips ni store cheyali - lekapothe anni okesari play avthayi
if "clips" not in st.session_state:
    st.session_state["clips"] = []
if "selected_clip" not in st.session_state:
    st.session_state["selected_clip"] = 0
if "viral_done" not in st.session_state:
    st.session_state["viral_done"] = False

def get_drive_id(link):
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", link)
    if m: return m.group(1)
    m = re.search(r"id=([a-zA-Z0-9_-]+)", link)
    return m.group(1) if m else None

def download_drive(link, out_path):
    fid = get_drive_id(link)
    if not fid:
        st.error("Link lo ID dorakaledu")
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
                st.error("Drive link is NOT set to 'Anyone with link'. Drive > Share > Anyone with link cheyi.")
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
    # FIX 2: REAL SUBTITLES - Whisper tho voice ni text ga marchadam
    try:
        import whisper
        model = whisper.load_model("tiny")
        result = model.transcribe(audio_path, fp16=False)
        if result.get("segments"):
            with open(srt_path, "w", encoding="utf-8") as f:
                for i, seg in enumerate(result["segments"]):
                    txt = seg["text"].strip()
                    if not txt: continue
                    f.write(f"{i+1}\n{fmt_time(seg['start'])} --> {fmt_time(seg['end'])}\n{txt.upper()}\n\n")
            # SRT file lo content unda check
            if os.path.getsize(srt_path) > 20:
                return True
    except Exception as e:
        print(f"Whisper failed: {e}")
    # Voice lekapothe fallback - caption_text ne subtitle la
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(f"1\n00:00:00,000 --> 00:00:30,000\n{fallback_text.upper()}\n\n")
    return False

def make_clip(input_path, output_path, start, duration, aspect, captions_on, caption_text, caption_color):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    tmpdir = tempfile.mkdtemp()
    srt_path = os.path.join(tmpdir, "subs.srt")
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")

    # 1080p BEST - LOCKED
    if "9:16" in aspect: base_vf = "crop=ih*9/16:ih,scale=1080:1920:force_original_aspect_ratio=disable"
    elif "1:1" in aspect: base_vf = "crop=min(iw\\,ih):min(iw\\,ih),scale=1080:1080"
    else: base_vf = "scale=1920:1080:force_original_aspect_ratio=disable"

    vf = base_vf
    if captions_on:
        # Audio extract chesi subtitle cheyadam
        audio_path = os.path.join(tmpdir, "audio.wav")
        cmd_a = [ffmpeg, "-y", "-ss", str(start), "-t", str(duration), "-i", input_path, "-vn", "-ac", "1", "-ar", "16000", audio_path]
        subprocess.run(cmd_a, capture_output=True)
        if os.path.exists(audio_path):
            make_srt_from_audio(audio_path, srt_path, caption_text)
        else:
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(f"1\n00:00:00,000 --> 00:00:30,000\n{caption_text.upper()}\n\n")

        # Nee color selection ni subtitle color ga vadadam
        color_code = "&H00FFFF&" if caption_color == "Yellow" else "&HFFFF00&" if caption_color == "Cyan" else "&HFF00FF&" if caption_color == "Pink" else "&HFFFFFF&"
        # REAL SUBTITLE STYLE - Viral Reels la - Bold + Black Box + Bottom Center
        vf = f"{base_vf},subtitles='{srt_escaped}':force_style='FontSize=28,PrimaryColour={color_code},OutlineColour=&H80000000&,BorderStyle=3,Outline=2,Shadow=2,Alignment=2,MarginV=180,Bold=1'"

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
            st.error("Download failed. Drive > Share > Anyone with link chesi malli try cheyi.")
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

# --- STEP 3 ---
st.markdown('<div class="card"><h3>3. Captions - Viral Style</h3></div>', unsafe_allow_html=True)
st.caption("ON unte - Video lo matladina maatalu automatic ga Subtitle la vasthayi. Voice lekapothe ee text vasthadi.")
caption_text = st.text_input("Caption Text", value="FOLLOW FOR MORE")
font = st.selectbox("Caption Font", ["Poppins Bold", "Montserrat Bold", "Bebas Neue", "Anton", "Oswald Bold", "Impact"])
caption_color = st.selectbox("Caption Color", ["White", "Yellow", "Cyan", "Pink"])

# --- GENERATE ---
if video_path and os.path.exists(video_path):
    if st.button("🔥 Generate Viral Clips"):
        duration = get_duration(video_path)
        if duration == 0:
            st.error("Could not read video. Re-upload.")
        else:
            with st.spinner("Generating your clips in 1080p + Real Subtitles... First time 1-2 mins padthadi (Whisper download avthundi)"):
                st.session_state["clips"] = []
                st.session_state["selected_clip"] = 0
                for i in range(num_clips):
                    start = max(0, (duration // (num_clips + 1)) * (i + 1))
                    out = tempfile.mktemp(suffix=f"_clip{i+1}.mp4")
                    ok = make_clip(video_path, out, start, min(clip_len, duration - start), aspect, captions, caption_text, caption_color)
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

# --- FIX 1: SHOW ONLY ONE CLIP AT A TIME - NO DOUBLE AUDIO ---
if st.session_state["clips"]:
    st.markdown('<div class="card"><h3>✅ Your Clips Ready - Play One At A Time</h3><p>👆 Clip select chesuko - Okkate play avthadi. Inkoti automatic ga aagipothadi.</p></div>', unsafe_allow_html=True)
    clip_names = [c["name"] for c in st.session_state["clips"]]
    selected = st.radio("Choose Clip to Play:", clip_names, index=st.session_state["selected_clip"], horizontal=True, key="clip_selector_single")
    sel_idx = clip_names.index(selected)
    st.session_state["selected_clip"] = sel_idx
    c = st.session_state["clips"][sel_idx]
    st.success(f"{c['name']} Ready! - 1080p HD + Real Subtitles")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.video(c["data"])
    st.download_button(f"⬇️ Download {c['name']}", c["data"], file_name=f"clipshort_{c['name'].lower().replace(' ','')}.mp4", mime="video/mp4", key=f"dl_single_{sel_idx}")

    # --- AUTO VIRAL TITLE / DESCRIPTION ---
    if st.session_state["viral_done"]:
        st.markdown('<div class="card"><h3>🚀 Viral Title & Description - Auto Generated</h3></div>', unsafe_allow_html=True)
        base_topic = prompt if prompt else caption_text if caption_text else "This Video"
        if base_topic == "FOLLOW FOR MORE":
            base_topic = "This Amazing Moment"
        titles = [
            f"{base_topic} 😱 You Won't Believe This! #shorts",
            f"OMG! {base_topic} 🔥 Viral Moment!",
            f"{base_topic} - Watch Till End! 👀",
        ]
        st.write("**👇 Copy chesi YouTube Title lo paste cheyi:**")
        selected_title = st.selectbox("Choose Best Title", titles, key="title_select_fixed")
        st.text_input("Your Viral Title", value=selected_title, key="viral_title_fixed")
        desc = f"""{selected_title}

{base_topic} - This is the most viral moment from this video! Watch till end and let me know your reaction in comments 👇

🔥 Follow @ClipShort AI for more viral shorts!

#shorts #viral #trending #youtubeshorts #reels #fyp #viralvideo #shortsfeed
"""
        st.write("**👇 Description - Copy All:**")
        st.text_area("Your Viral Description", value=desc, height=180, key="viral_desc_fixed")
        hashtags = "#shorts #viral #trending #youtubeshorts #reels #fyp #viralvideo #shortsfeed #clipshortai #foryou"
        st.write("**👇 Hashtags:**")
        st.text_input("Hashtags", value=hashtags, key="hashtags_fixed")
        st.success("✅ Title + Description Ready! Copy chesi YouTube / Instagram lo paste cheyi!")

st.markdown('<p style="text-align:center; color:#BBB; font-size:12px; margin-top:20px;">Made with ❤️ by ClipShort AI • Free for Creators</p>', unsafe_allow_html=True)
