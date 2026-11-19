# ClipShort AI - Professional Font + Theme by Uday
import streamlit as st
import yt_dlp
from moviepy.editor import VideoFileClip
import os, re

st.set_page_config(page_title="ClipShort AI - Professional", page_icon="✂️", layout="centered")

# --- PROFESSIONAL THEME + FONT ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0F0F0F;
    color: white;
}
h1, h2, h3 {
    font-family: 'Poppins', sans-serif !important;
    font-weight: 800 !important;
    letter-spacing: -0.5px;
}
.stApp { background: #0F0F0F; }
section[data-testid="stSidebar"] { background: #0F0F0F; }

/* Input Boxes */
.stTextInput input, .stNumberInput input, .stSelectbox > div > div {
    background-color: #1F1F1F !important;
    color: white !important;
    border: 1px solid #333333 !important;
    border-radius: 12px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 15px !important;
    padding: 12px 14px !important;
}
label { font-family: 'Poppins', sans-serif !important; font-weight: 600 !important; color: #E5E5E5 !important; font-size: 14px !important; }

/* Main Button */
.stButton > button {
    background: linear-gradient(90deg, #FF0033, #FF4D6D) !important;
    color: white !important;
    font-family: 'Poppins', sans-serif !important;
    font-weight: 700 !important;
    font-size: 17px !important;
    letter-spacing: 0.5px !important;
    border-radius: 14px !important;
    padding: 16px 20px !important;
    border: none !important;
    box-shadow: 0 8px 25px rgba(255,0,51,0.35);
}
.stButton > button:hover { transform: scale(1.01); box-shadow: 0 10px 30px rgba(255,0,51,0.5); }

/* Card */
.main-card {
    background: #1A1A1A;
    border: 1px solid #2A2A2A;
    border-radius: 18px;
    padding: 24px;
}
.badge {
    background: #1F1F1F; border: 1px solid #333; padding: 6px 12px; border-radius: 100px;
    font-size: 12px; font-weight: 600; color: #FF4D6D;
}
</style>
""", unsafe_allow_html=True)

# --- HEADER ---
st.markdown('<span class="badge">✂️ CLIPSHORT AI • PRO</span>', unsafe_allow_html=True)
st.markdown("<h1 style='font-size:42px; margin:10px 0 0 0;'>YouTube → Shorts<br>Converter</h1>", unsafe_allow_html=True)
st.markdown("<p style='color:#9CA3AF; font-size:16px; margin-top:8px;'>Turn long YouTube videos into viral Shorts in seconds.<br>Professional Studio for Creators.</p>", unsafe_allow_html=True)

st.markdown('<div class="main-card">', unsafe_allow_html=True)
link = st.text_input("YouTube Link", placeholder="Paste YouTube URL here...  https://youtube.com/watch?v=...")
col1, col2 = st.columns(2)
start = col1.number_input("⏱️ Start Time", value=10, min_value=0)
length = col2.number_input("✂️ Clip Length", value=30, min_value=5, max_value=60)
color = st.selectbox("🎨 Font Color", ["yellow", "white", "cyan", "red"])
st.markdown('</div>', unsafe_allow_html=True)

st.write("")
status = st.empty()

if st.button("🚀  MAKE SHORT NOW", use_container_width=True):
    if not link:
        st.warning("Bro, link ivvu!")
    else:
        with st.spinner("Downloading & Cutting Your Short..."):
            try:
                m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", link)
                clean = f"https://www.youtube.com/watch?v={m.group(1)}" if m else link
                opts = {
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'outtmpl': 'downloaded.mp4',
                    'quiet': True,
                    'noplaylist': True,
                    'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
                    'nocheckcertificate': True,
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([clean])
                clip = VideoFileClip("downloaded.mp4").subclip(start, start+length)
                clip = clip.resize(height=1280)
                clip.write_videofile("ClipShort_Output.mp4", codec="libx264", audio_codec="aac", verbose=False, logger=None)
                clip.close()
                if os.path.exists("downloaded.mp4"):
                    os.remove("downloaded.mp4")
                st.success("Done Bro! ✅ Short Ready")
                st.video("ClipShort_Output.mp4")
                with open("ClipShort_Output.mp4", "rb") as f:
                    st.download_button("⬇️ Download Short", f, file_name="ClipShort_Output.mp4", use_container_width=True)
            except Exception as e:
                st.error(f"Error: {e}")

st.markdown("<p style='text-align:center; color:#6B7280; font-size:12px; margin-top:30px;'>Made by Uday  |  ClipShort AI  •  Professional Edition</p>", unsafe_allow_html=True)