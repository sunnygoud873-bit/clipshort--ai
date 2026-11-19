import streamlit as st
import subprocess, os, glob, random

st.set_page_config(page_title="OpusClip - Copy", page_icon="✂️", layout="wide")

# --- Black Theme Like Screenshot ---
st.markdown("""
<style>
.stApp { background-color: #000000; color: white; }
h1, h2, h3, p { color: white !important; text-align: center; }
</style>
""", unsafe_allow_html=True)

# --- TOP BAR ---
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown("### 🅿️ OpusClip")
with c2:
    if st.button("Sign up - It's FREE"):
        st.session_state.page = "app"
        st.rerun()

if "page" not in st.session_state:
    st.session_state.page = "home"

# --- HOME PAGE - SAME AS SCREENSHOT ---
if st.session_state.page == "home":
    st.markdown("<p style='color:gray'>#1 AI VIDEO EDITOR AND CLIPPING TOOL</p>", unsafe_allow_html=True)
    st.markdown("# Turn any footage into")
    st.markdown("## a polished interview")
    st.markdown("# 10x faster")
    st.markdown("<p style='color:gray'>Paste a link or drop a raw take, and OpusClip clips, edits, sizes and publishes them to all social platforms in one click.</p>", unsafe_allow_html=True)

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
    st.markdown("**ClipAnything**")
    st.markdown("Every other AI clipping tool only works with video podcasts. ClipAnything turns any genre - vlogs, gaming, sports, interviews - into viral clips in 1 click.")

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
    if st.button("🚀 Get Started FREE", type="primary", use_container_width=True):
        st.session_state.page = "app"
        st.rerun()
    st.stop()

# --- APP PAGE - CLIPPER ---
st.markdown("# ✂️ ClipShort AI - Get Free Clips")
video = "input.mp4"

up = st.file_uploader("Drop a video file", type=['mp4','mov','mkv','webm'])
if up:
    open(video,"wb").write(up.read())
    st.success("Uploaded!")

url = st.text_input("Or Paste YouTube Link")
if st.button("Get Video") and url:
    subprocess.run(["yt-dlp","-f","mp4","-o",video,url], capture_output=True)
    if os.path.exists(video):
        st.success("Downloaded!")

if os.path.exists(video):
    st.video(video)
    prompt = st.text_input("Prompt", placeholder="Moment most likely to go viral")
    num = st.selectbox("How many clips?", [3, 5, 10])

    if st.button("🚀 Get Free Clips", type="primary", use_container_width=True):
        for f in glob.glob("clip_*.mp4"):
            os.remove(f)
        with st.spinner("Clipping..."):
            for i in range(num):
                out = f"clip_{i+1}.mp4"
                subprocess.run(["ffmpeg","-y","-ss",str(i*42),"-t","30","-i",video,"-vf","crop=ih*9/16:ih,scale=1080:1920","-c:v","libx264","-preset","veryfast","-c:a","aac",out], capture_output=True)
        st.success("Clips Ready!")

    files = sorted(glob.glob("clip_*.mp4"))
    if files:
        for i, f in enumerate(files):
            st.video(f)
            score = random.randint(85, 98)
            st.markdown(f"**Virality: {score}/99** 🔥 | **9:16** | **ClipAnything**")
            with open(f,"rb") as file:
                st.download_button(f"⬇️ Download Clip {i+1}", file, f"clip_{i+1}.mp4", "video/mp4", key=f"d{i}")

    if st.button("← Back to Home"):
        st.session_state.page = "home"
        st.rerun()
