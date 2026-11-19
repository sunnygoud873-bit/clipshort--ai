import streamlit as st
import requests, os, re, subprocess, tempfile
import imageio_ffmpeg

st.set_page_config(page_title="ClipShort AI", page_icon="✂️", layout="centered")

# --- PREMIUM THEME - FIXED ---
st.markdown("""
<style>
.stApp { background: linear-gradient(180deg, #0f0c29 0%, #302b63 50%, #24243e 100%) !important; }
h1, h2, h3, p, label { color: white !important; }

/* FIXED: White Box = Black Text - Now Visible */
.stTextInput input, .stSelectbox div[data-baseweb="select"] div {
    background: white !important;
    color: black !important;
    -webkit-text-fill-color: black !important;
    border-radius: 14px !important;
    font-weight: 600 !important;
}
.stTextInput input::placeholder { color: #888 !important; -webkit-text-fill-color: #888 !important; }
div[data-baseweb="select"] span { color: black !important; }
div[data-baseweb="menu"] div { color: black !important; background: white !important; }

.stButton button { background: linear-gradient(90deg, #FF512F, #DD2476) !important; color: white !important; border: none !important; border-radius: 50px !important; padding: 12px 28px !important; font-weight: 700 !important; width: 100%; }
.card { background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.15); border-radius: 20px; padding: 18px; margin: 12px 0; }
.badge { background: #FFD700; color: black; padding: 5px 14px; border-radius: 20px; font-size: 12px; font-weight: 800; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div style="text-align:center"><span class="badge">✨ 100% FREE • NO WATERMARK</span><h1 style="font-size:46px;">✂️ ClipShort AI</h1><p style="font-size:18px;">Turn Any Video Into Viral Shorts in 1 Click</p></div>', unsafe_allow_html=True)
st.markdown('<div class="card"><b>📤 Upload - Up to 200MB</b> &nbsp;|&nbsp; ☁️ <b>Drive - Up to 4GB</b><br><small>For YouTube: YouTube Studio > Download > Upload to Drive > Paste link here</small></div>', unsafe_allow_html=True)

# --- HELPERS ---
def get_drive_id(link):
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", link)
    if m: return m.group(1)
    m = re.search(r"id=([a-zA-Z0-9_-]+)", link)
    return m.group(1) if m else None

def download_drive(link, out_path):
    fid = get_drive_id(link)
    if not fid: return False
    url = f"https://drive.google.com/uc?export=download&id={fid}"
    r = requests.get(url, stream=True, allow_redirects=True)
    if r.status_code != 200: return False
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(1024*1024):
            if chunk: f.write(chunk)
    return os.path.getsize(out_path) > 10000

def get_duration(path):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    res = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+)", res.stderr)
    if m: return int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))
    return 0

def make_clip(input_path, output_path, start, duration, aspect, captions_on, font_name):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    if "9:16" in aspect:
        vf = "crop=ih*9/16:ih,scale=1080:1920"
    elif "1:1" in aspect:
        vf = "crop=min(iw\\,ih):min(iw\\,ih),scale=1080:1080"
    else:
        vf = "scale=1920:1080"
    if captions_on:
        vf += f",drawtext=text='CLIPSHORT AI':fontcolor=white:fontsize=48:box=1:boxcolor=black@0.6:x=(w-text_w)/2:y=h-120"
    cmd = [ffmpeg, "-y", "-ss", str(start), "-t", str(duration), "-i", input_path, "-vf", vf, "-c:a", "aac", output_path]
    subprocess.run(cmd, capture_output=True)
    return os.path.exists(output_path)

# --- INPUTS ---
uploaded = st.file_uploader("Choose a video file", type=["mp4","mov","mkv","webm"])
drive_link = st.text_input("Paste Google Drive Link", placeholder="https://drive.google.com/file/d/... - Set to Anyone with link")
yt_link = st.text_input("Or Paste YouTube Link - Info Only", placeholder="https://youtu.be/...")
if st.button("Get Video Info"):
    st.warning("YouTube direct download is blocked. Please download from YouTube Studio and upload here.")

st.markdown('<div class="card"><h3>⚙️ Clip Settings</h3></div>', unsafe_allow_html=True)
prompt = st.text_input("Prompt", placeholder="Moment most likely to go viral")
col1, col2 = st.columns(2)
with col1:
    clip_len = st.slider("Clip Length (seconds)", 15, 60, 30)
    aspect = st.selectbox("Aspect Ratio", ["9:16 - Shorts / Reels", "1:1 - Post", "16:9 - YouTube"])
with col2:
    captions = st.toggle("Auto Captions", value=True)
    font = st.selectbox("Caption Font", ["Poppins Bold", "Montserrat Bold", "Bebas Neue", "Anton", "Oswald Bold", "Impact"])
    num_clips = st.slider("Number of Clips", 1, 3, 1)

st.markdown('<h3 style="text-align:center;">✍️ Captions - Viral Style</h3>', unsafe_allow_html=True)
caption_text = st.text_input("Caption Text", value="FOLLOW FOR MORE")
caption_color = st.selectbox("Caption Color", ["White", "Yellow", "Cyan", "Pink"])

# --- PROCESS ---
video_path = None
if uploaded:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tf:
        tf.write(uploaded.read())
        video_path = tf.name
    st.video(uploaded)

if drive_link and st.button("Download from Drive"):
    with st.spinner("Downloading from Drive..."):
        tmp = tempfile.mktemp(suffix=".mp4")
        if download_drive(drive_link, tmp):
            video_path = tmp
            st.success("Downloaded! Video is ready below.")
            st.video(tmp)
        else:
            st.error("Download failed. Make sure link is set to 'Anyone with link'.")

if video_path and st.button("🔥 Generate Viral Clips"):
    duration = get_duration(video_path)
    if duration == 0:
        st.error("Could not read video. Please try another file.")
    else:
        with st.spinner("Generating your clips... Please wait"):
            for i in range(num_clips):
                start = max(0, (duration // (num_clips + 1)) * (i + 1))
                out = tempfile.mktemp(suffix=f"_clip{i+1}.mp4")
                ok = make_clip(video_path, out, start, min(clip_len, duration - start), aspect, captions, font)
                if ok:
                    st.success(f"Clip {i+1} Ready!")
                    st.video(out)
                    with open(out, "rb") as f:
                        st.download_button(f"⬇️ Download Clip {i+1}", f, file_name=f"clipshort_clip{i+1}.mp4", mime="video/mp4", key=f"dl{i}")
                else:
                    st.error(f"Failed to create Clip {i+1}")
        st.balloons()
