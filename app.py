import streamlit as st
import requests, os, re, subprocess, tempfile
import imageio_ffmpeg

st.set_page_config(page_title="ClipShort AI", page_icon="✂️", layout="centered")

# --- PREMIUM THEME - UI FIXED ---
st.markdown("""
<style>
.stApp { background: linear-gradient(180deg, #0f0c29 0%, #302b63 50%, #24243e 100%) !important; }
h1, h2, h3, p, label { color: white !important; }
.block-container { padding-top: 1rem !important; }

/* NAVBAR - NEW UI */
.nav { background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.15); border-radius: 16px; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.nav-logo { font-size: 20px; font-weight: 800; color: white; }
.nav-logo span { color: #FFD700; }
.nav-btn { background: #FFD700; color: black; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 800; }

/* INPUTS - VISIBLE FIX */
.stTextInput input {
    background: white !important; color: black !important;
    -webkit-text-fill-color: black !important;
    border-radius: 14px !important; font-weight: 600 !important;
    height: 50px !important; font-size: 15px !important;
}
.stTextInput input::placeholder { color: #888 !important; -webkit-text-fill-color: #888 !important; }
.stSelectbox div[data-baseweb="select"] div { background: white !important; color: black !important; border-radius: 14px !important; min-height: 50px !important; }
div[data-baseweb="select"] span { color: black !important; font-weight: 600 !important; }
div[data-baseweb="menu"] div { color: black !important; background: white !important; }

.stButton button { background: linear-gradient(90deg, #FF512F, #DD2476) !important; color: white !important; border: none !important; border-radius: 50px !important; padding: 12px 28px !important; font-weight: 700 !important; width: 100%; height: 52px !important; font-size: 16px !important; }
.stDownloadButton button { background: #00C853 !important; border-radius: 14px !important; height: 48px !important; }
.card { background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.15); border-radius: 20px; padding: 18px; margin: 12px 0; }
.badge { background: #FFD700; color: black; padding: 5px 14px; border-radius: 20px; font-size: 12px; font-weight: 800; }
.step-num { background: #FFD700; color: black; width: 28px; height: 28px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: 800; font-size: 14px; margin-right: 8px; }
.feature { background: rgba(255,255,255,0.10); border-radius: 16px; padding: 14px; text-align: center; }
.feature b { font-size: 14px !important; }
.feature span { font-size: 12px !important; color: #DDD !important; }
video { border-radius: 16px !important; }
</style>
""", unsafe_allow_html=True)

# --- UI: NAVBAR ---
st.markdown('<div class="nav"><div class="nav-logo">✂️ Clip<span>Short</span> AI</div><div class="nav-btn">✨ FREE</div></div>', unsafe_allow_html=True)

st.markdown('<div style="text-align:center"><span class="badge">✨ 100% FREE • NO WATERMARK</span><h1 style="font-size:42px;">✂️ ClipShort AI</h1><p style="font-size:17px;">Turn Any Video Into Viral Shorts in 1 Click</p></div>', unsafe_allow_html=True)

# --- UI: FEATURES FOR PEOPLE ---
f1, f2, f3 = st.columns(3)
with f1: st.markdown('<div class="feature"><div style="font-size:22px;">⚡</div><b>Fast Clipping</b><br><span>Best moments</span></div>', unsafe_allow_html=True)
with f2: st.markdown('<div class="feature"><div style="font-size:22px;">💬</div><b>Auto Captions</b><br><span>Viral subtitles</span></div>', unsafe_allow_html=True)
with f3: st.markdown('<div class="feature"><div style="font-size:22px;">📱</div><b>All Platforms</b><br><span>Shorts, Reels</span></div>', unsafe_allow_html=True)

st.markdown('<div class="card"><b>📤 Upload - Up to 200MB</b> &nbsp;|&nbsp; ☁️ <b>Drive - Up to 4GB</b><br><small>For YouTube: YouTube Studio > Download > Upload to Drive > Paste link here</small></div>', unsafe_allow_html=True)

# --- SESSION ---
if "video_path" not in st.session_state:
    st.session_state["video_path"] = None

# --- HELPERS ---
def get_drive_id(link):
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", link)
    if m: return m.group(1)
    m = re.search(r"id=([a-zA-Z0-9_-]+)", link)
    return m.group(1) if m else None

def download_drive(link, out_path):
    import gdown
    fid = get_drive_id(link)
    if not fid: return False
    try:
        gdown.download(f"https://drive.google.com/uc?id={fid}", out_path, quiet=False, fuzzy=True)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            with open(out_path, "rb") as f:
                header = f.read(30)
            if b"<html" in header.lower() or b"<!DOCTYPE" in header:
                return False
            return True
        return False
    except Exception as e:
        print(e)
        return False

def get_duration(path):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    res = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+)", res.stderr)
    if m: return int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))
    return 0

def make_clip(input_path, output_path, start, duration, aspect, captions_on, caption_text, caption_color):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    if "9:16" in aspect:
        vf = "crop=ih*9/16:ih,scale=1080:1920"
    elif "1:1" in aspect:
        vf = "crop=min(iw\\,ih):min(iw\\,ih),scale=1080:1080"
    else:
        vf = "scale=1920:1080"
    if captions_on:
        safe_text = caption_text.replace("'", "").replace(":", "")
        color = "yellow" if caption_color == "Yellow" else "cyan" if caption_color == "Cyan" else "pink" if caption_color == "Pink" else "white"
        vf += f",drawtext=text='{safe_text}':fontcolor={color}:fontsize=56:box=1:boxcolor=black@0.6:x=(w-text_w)/2:y=h-160"
    cmd = [ffmpeg, "-y", "-ss", str(start), "-t", str(duration), "-i", input_path, "-vf", vf, "-c:a", "aac", output_path]
    subprocess.run(cmd, capture_output=True)
    return os.path.exists(output_path) and os.path.getsize(output_path) > 10000

# --- STEP 1 UI ---
st.markdown('<div class="card"><h3><span class="step-num">1</span> Upload Your Video</h3></div>', unsafe_allow_html=True)
uploaded = st.file_uploader("Choose a video file", type=["mp4","mov","mkv","webm"])
drive_link = st.text_input("Paste Google Drive Link", placeholder="https://drive.google.com/file/d/... - Set to Anyone with link")

if drive_link and st.button("Download from Drive"):
    with st.spinner("Downloading from Drive... Please wait, large file takes time"):
        tmp = tempfile.mktemp(suffix=".mp4")
        if download_drive(drive_link, tmp):
            st.session_state["video_path"] = tmp
            st.success("Downloaded! Video is ready below.")
            st.rerun()
        else:
            st.error("Download failed. Set link to 'Anyone with link' and try again.")

yt_link = st.text_input("Or Paste YouTube Link - Info Only", placeholder="https://youtu.be/...")
if st.button("Get Video Info"):
    st.warning("YouTube direct download is blocked. Please download from YouTube Studio and upload here.")

# --- VIDEO PREVIEW ---
video_path = st.session_state.get("video_path")

if uploaded:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tf:
        tf.write(uploaded.read())
        video_path = tf.name
        st.session_state["video_path"] = video_path

if video_path and os.path.exists(video_path):
    with open(video_path, "rb") as f:
        video_bytes = f.read()
    st.video(video_bytes)
    st.caption(f"✅ Video loaded: {len(video_bytes)//1024//1024} MB")

# --- STEP 2 UI ---
st.markdown('<div class="card"><h3><span class="step-num">2</span> Clip Settings</h3></div>', unsafe_allow_html=True)
prompt = st.text_input("Prompt", placeholder="Moment most likely to go viral")
col1, col2 = st.columns(2)
with col1:
    clip_len = st.slider("Clip Length (seconds)", 15, 60, 30)
    aspect = st.selectbox("Aspect Ratio", ["9:16 - Shorts / Reels", "1:1 - Post", "16:9 - YouTube"])
with col2:
    captions = st.toggle("Auto Captions", value=True)
    font = st.selectbox("Caption Font", ["Poppins Bold", "Montserrat Bold", "Bebas Neue", "Anton", "Oswald Bold", "Impact"])
    num_clips = st.slider("Number of Clips", 1, 3, 1)

# --- STEP 3 UI ---
st.markdown('<div class="card"><h3><span class="step-num">3</span> Captions - Viral Style</h3></div>', unsafe_allow_html=True)
caption_text = st.text_input("Caption Text", value="FOLLOW FOR MORE")
caption_color = st.selectbox("Caption Color", ["White", "Yellow", "Cyan", "Pink"])

# --- GENERATE ---
if video_path and os.path.exists(video_path):
    if st.button("🔥 Generate Viral Clips"):
        duration = get_duration(video_path)
        if duration == 0:
            st.error("Could not read video. File may be corrupted. Re-upload from Drive.")
        else:
            with st.spinner("Generating your clips... Please wait"):
                for i in range(num_clips):
                    start = max(0, (duration // (num_clips + 1)) * (i + 1))
                    out = tempfile.mktemp(suffix=f"_clip{i+1}.mp4")
                    ok = make_clip(video_path, out, start, min(clip_len, duration - start), aspect, captions, caption_text, caption_color)
                    if ok:
                        st.success(f"Clip {i+1} Ready!")
                        with open(out, "rb") as f:
                            cb = f.read()
                        st.video(cb)
                        st.download_button(f"⬇️ Download Clip {i+1}", cb, file_name=f"clipshort_clip{i+1}.mp4", mime="video/mp4", key=f"dl{i}")
                    else:
                        st.error(f"Failed to create Clip {i+1}")
            st.balloons()
else:
    st.markdown('<div style="text-align:center; background: rgba(255,215,0,0.2); padding:14px; border-radius:14px; color:white; font-weight:600;">👆 Upload a video first to generate clips</div>', unsafe_allow_html=True)

st.markdown('<p style="text-align:center; color:#BBB !important; font-size:12px !important; margin-top:20px;">Made with ❤️ by ClipShort AI • Free for Creators</p>', unsafe_allow_html=True)
