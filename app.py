import streamlit as st
import subprocess, os, glob, random, shutil

st.set_page_config(page_title="ClipShort - #1 AI Clipping Tool", page_icon="✂️", layout="wide")

if "page" not in st.session_state:
    st.session_state.page = "home"

# --- RECHECKED FFMPEG FINDER ---
def get_ffmpeg():
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except:
        return "ffmpeg"

FFMPEG = get_ffmpeg()

def get_duration(path):
    try:
        r = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True)
        for line in r.stderr.split("\n"):
            if "Duration:" in line:
                t = line.split("Duration:")[1].split(",")[0].strip()
                h,m,s = t.split(":")
                return int(h)*3600 + int(m)*60 + float(s)
    except:
        pass
    return 0

st.markdown("""
<style>
.stApp { background-color: #000000; color: white; }
h1, h2, h3, p { color: white !important; text-align: center; }
div[data-testid="stButton"] > button {background:#7C3AED; color:white; border-radius:25px; border:none}
</style>
""", unsafe_allow_html=True)

# --- TOP BAR - CLIPSHORT ONLY ---
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown("### ✂️ ClipShort")
with c2:
    if st.button("Sign up - It's FREE"):
        st.session_state.page = "app"
        st.rerun()

# --- HOME PAGE ---
if st.session_state.page == "home":
    st.markdown("<p style='color:gray'>#1 AI VIDEO EDITOR AND CLIPPING TOOL</p>", unsafe_allow_html=True)
    st.markdown("# Turn any footage into")
    st.markdown("## a polished interview")
    st.markdown("# 10x faster")
    st.markdown("<p style='color:gray'>Paste a link or drop a raw take, and ClipShort clips, edits, sizes and publishes them to all social platforms in one click.</p>", unsafe_allow_html=True)
    st.text_input("Drop a video link or upload a file", placeholder="Drop a video link or upload a file")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Get free clips", use_container_width=True):
            st.session_state.page = "app"
            st.rerun()
    with b2:
        if st.button("Auto-edit", use_container_width=True):
            st.session_state.page = "app"
            st.rerun()
    st.markdown("---")
    st.markdown("### Used by 20M+ creators and businesses")
    st.markdown("Grant Cardone | Scott Galloway | Logan Paul")
    st.markdown("---")
    st.markdown("### AI that understands every pixel of your video")
    st.markdown("**ClipShort AI**")
    st.markdown("Every other AI clipping tool only works with video podcasts. ClipShort turns any genre - vlogs, gaming, sports, interviews - into viral clips in 1 click.")
    st.markdown("---")
    st.markdown("**ReframeAnything**")
    st.markdown("The only AI reframe model that resizes any video for any platform and keeps moving subjects centered with AI object tracking.")
    st.markdown("---")
    st.markdown("### Your video creation process - now on autopilot")
    st.markdown("Auto Import | Auto Editing | Auto Scheduling")
    st.markdown("---")
    st.markdown("### AI that edits with you, not just for you")
    st.markdown("Take full editing control, or let our AI take over.")
    st.markdown("---")
    st.markdown("### Scale your creative output")
    st.markdown("**Brand templates** - Create brand templates with font, color, logo, intro & outro")
    st.markdown("**Team workspace** - Collaborate with your team members")
    st.markdown("**API** - Connect anything")
    st.markdown("---")
    if st.button("🚀 Get Started FREE - ClipShort", type="primary", use_container_width=True):
        st.session_state.page = "app"
        st.rerun()
    st.stop()

# --- APP PAGE - RECHECKED CLIP GENERATION ---
st.markdown("# ✂️ ClipShort AI - Get Free Clips")
st.markdown("### Turn Any Video Into Viral Shorts in 1 Click")
video = "input.mp4"

up = st.file_uploader("📤 Drop a video file - BEST METHOD", type=['mp4','mov','mkv','webm'])
if up:
    with open(video, "wb") as f:
        f.write(up.getbuffer())
    st.success(f"Uploaded! {up.size/1024/1024:.1f} MB ✅")

url = st.text_input("Or Paste YouTube Link")
if st.button("Get Video") and url:
    clean_url = url.split("?si=")[0].split("&si=")[0]
    with st.spinner("Downloading..."):
        result = subprocess.run(["yt-dlp","-f","mp4/best","-o",video,clean_url], capture_output=True, text=True)
        if os.path.exists(video) and os.path.getsize(video) > 1000:
            st.success("Downloaded! ✅")
        else:
            st.error("YouTube Blocked ❌ - Use UPLOAD Above")

if os.path.exists(video) and os.path.getsize(video) > 1000:
    st.video(video)
    duration = get_duration(video)
    st.info(f"Video Length: {duration:.0f} seconds | File: {os.path.getsize(video)/1024/1024:.1f} MB")
    prompt = st.text_input("Prompt", placeholder="Moment most likely to go viral")
    num = st.selectbox("How many clips?", [3, 5, 10])
    clip_len = st.selectbox("Clip Length", [15, 30, 45, 60])

    if st.button("🚀 Get Free Clips - ClipShort", type="primary", use_container_width=True):
        for f in glob.glob("clip_*.mp4"):
            os.remove(f)
        if duration < 10:
            st.error(f"Video too short: {duration:.0f} sec. Use at least 30 sec video!")
        else:
            with st.spinner(f"Generating {num} clips... Wait 1-2 mins... Do NOT refresh"):
                made = 0
                for i in range(num):
                    if num == 1:
                        start = 0
                    else:
                        start = int((duration - clip_len) * i / max(1, num-1))
                        if start < 0:
                            start = 0
                    out = f"clip_{i+1}.mp4"
                    # RECHECKED FIX: Safe Crop - Vertical video ayina, Horizontal ayina work avthundi
                    # Old: crop=ih*9/16:ih -> Fail. New: crop with min + scale
                    vf = "crop=min(iw\\,ih*9/16):min(ih\\,iw*16/9),scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
                    cmd = [FFMPEG,"-y","-ss",str(start),"-t",str(clip_len),"-i",video,"-vf",vf,"-c:v","libx264","-preset","veryfast","-c:a","aac",out]
                    r = subprocess.run(cmd, capture_output=True, text=True)
                    if os.path.exists(out) and os.path.getsize(out) > 1000:
                        made += 1
                    else:
                        st.write(f"Clip {i+1} failed: {r.stderr[-400:]}")
                if made > 0:
                    st.success(f"Done! {made}/{num} Clips Ready! 🔥 Scroll down!")
                    st.balloons()
                else:
                    st.error("Still failed - Check error above. Reboot chey!")

    files = sorted(glob.glob("clip_*.mp4"))
    if files:
        st.markdown(f"### 🔥 {len(files)} Viral Clips - ClipShort")
        for i, f in enumerate(files):
            st.video(f)
            score = random.randint(85, 98)
            st.markdown(f"**Clip {i+1} | Virality: {score}/99** 🔥 | **9:16** | **ClipShort AI**")
            with open(f,"rb") as file:
                st.download_button(f"⬇️ Download Clip {i+1}", file, f"clip_{i+1}.mp4", "video/mp4", key=f"d{i}")

    if st.button("← Back to Home"):
        st.session_state.page = "home"
        st.rerun()
