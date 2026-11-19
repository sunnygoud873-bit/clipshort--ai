import streamlit as st
import subprocess, os

st.set_page_config(page_title="ClipShort AI", page_icon="✂️")
st.title("✂️ ClipShort AI - Made by Uday")
st.write("YouTube Link / Upload -> Clip -> Vertical Short")

# 1. VIDEO TISKOVADAM
option = st.radio("Video ekkada nundi?", ["📤 Video Upload Chey", "🔗 YouTube Link"])

video_file = "input.mp4"

if option == "📤 Video Upload Chey":
    uploaded = st.file_uploader("Video Upload Chey", type=['mp4','mov','mkv','webm'])
    if uploaded:
        with open(video_file, "wb") as f:
            f.write(uploaded.read())
        st.success("Upload Aindi!")
        st.video(video_file)

else:
    url = st.text_input("YouTube Link Paste Chey")
    if st.button("📥 Download Video") and url:
        with st.spinner("Downloading..."):
            # 403 Fix - Android Client
            cmd = ["yt-dlp", "--extractor-args", "youtube:player_client=android", "-f", "mp4", "-o", video_file, url]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if os.path.exists(video_file):
                st.success("Download Aindi!")
                st.video(video_file)
            else:
                st.error("YouTube Block Chesindi! Video ni download chesi Upload Option vadhu bro.")

# 2. CLIPPING & CONVERT
if os.path.exists(video_file):
    st.divider()
    st.subheader("✂️ Clipping Settings")
    
    col1, col2 = st.columns(2)
    with col1:
        start = st.number_input("Start Time (seconds)", min_value=0, value=0)
    with col2:
        duration = st.number_input("Clip Length (seconds)", min_value=5, max_value=60, value=30)
    
    if st.button("🚀 MAKE SHORT NOW", type="primary"):
        with st.spinner("Short Chestunnam... 30 sec wait chey..."):
            # Vertical 9:16 Convert + Crop + Trim
            cmd2 = [
                "ffmpeg", "-y", "-ss", str(start), "-t", str(duration),
                "-i", video_file,
                "-vf", "crop=ih*9/16:ih,scale=1080:1920",
                "-c:v", "libx264", "-c:a", "aac",
                "short_output.mp4"
            ]
            subprocess.run(cmd2, capture_output=True)
            
            if os.path.exists("short_output.mp4"):
                st.success("Short Ready bro! 🔥")
                st.video("short_output.mp4")
                with open("short_output.mp4", "rb") as f:
                    st.download_button("⬇️ DOWNLOAD SHORT", f, file_name="clipshort_by_uday.mp4", mime="video/mp4")
            else:
                st.error("Convert avvaledu, malli try chey.")

st.markdown("---")
st.markdown("Made by Uday | ClipShort AI • Professional Edition")
