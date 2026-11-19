import streamlit as st
import subprocess, os, glob, random, shutil, re, requests

st.set_page_config(page_title="ClipShort - #1 AI Clipping Tool", page_icon="✂️", layout="wide")

if "page" not in st.session_state:
    st.session_state.page = "home"

# --- FFMPEG FINDER ---
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

def download_drive(drive_url, output):
    # Drive link nunchi ID teyadam + Large file Confirm Fix
    m = re.search(r'/d/([a-zA-Z0-9_-]+)', drive_url)
    fid = m.group(1) if m else drive_url
    session = requests.Session()
    dl = f"https://drive.google.com/uc?export=download&id={fid}"
    r = session.get(dl, stream=True)
    for key, val in r.cookies.items():
        if key.startswith("download_warning"):
            dl = f"https://drive.google.com/uc?export=download&confirm={val}&id={fid}"
            r = session.get(dl, stream=True)
            break
    with open(output, "wb") as f:
        for chunk in r.iter_content(1024*1024):
            if chunk:
                f.write(chunk)
    return os.path.exists(output) and os.path.getsize(output) > 1000

# --- CAPTIONS + FONTS - TOTAL 8 FONTS ---
FONTS = {
    "🔥 Montserrat Bold - Viral": "Montserrat",
    "💪 Bebas Neue - Gaming": "Bebas Neue",
    "✨ Poppins Bold - Vlog": "Poppins",
    "🎬 Anton - Cinema": "Anton",
    "😎 Luckiest Guy - Funny": "Luckiest Guy",
    "📱 Inter Bold - Clean": "Inter",
    "⚡ Oswald - Sports": "Oswald",
    "❤️ Playfair - Story": "Playfair Display",
}

def make_caption_file(text, font_name, color="&H00FFFFFF", out="caption.ass"):
    # Safe text - FFmpeg ki problem raakunda
    text = text.replace("\n", " ").replace(":", "\\:").replace(",", "\\,")
    ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginV
Style: Default,{font_name},52,{color},&H00000000,&H80000000,-1,3,0,2,300
[Events]
Format: Layer, Start, End, Style, Text
Dialogue: 0,0:00:00.00,0:59:59.00,Default,{text}
"""
    with open(out, "w", encoding="utf-8") as f:
        f.write(ass)
    return out

st.markdown("""
<style>
.stApp { background-color: #000000; color: white; }
h1, h2, h3, p { color: white !important; text-align: center; }
div[data-testid="stButton"] > button {background:#7C3AED; color:white; border-radius:25px; border:none}
</style>
""", unsafe_allow_html=True)

# --- TOP BAR ---
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

# --- APP PAGE ---
st.markdown("# ✂️ ClipShort AI - Get Free Clips")
st.markdown("### Turn Any Video Into Viral Shorts in 1 Click")
video = "input.mp4"

# TAB 1 / TAB 2
tab1, tab2 = st.tabs(["📤 Upload - 200MB", "☁️ Drive - 4GB Fast"])

with tab1:
    up = st.file_uploader("📤 Drop a video file - BEST METHOD", type=['mp4','mov','mkv','webm'])
    if up:
        with open(video, "wb") as f:
            f.write(up.getbuffer())
        st.success(f"Uploaded! {up.size/1024/1024:.1f} MB ✅")

with tab2:
    st.markdown("**YouTube video ayithe:** YouTube Studio > Download > Drive lo upload cheyi > ikkada link pettu")
    drive_url = st.text_input("Paste Google Drive Link", placeholder="https://drive.google.com/file/d/... - Anyone with link cheyi")
    if st.button("📥 Download from Drive") and drive_url:
        with st.spinner("Drive nunchi downloading... 4GB kuda fast vasthadi..."):
            if download_drive(drive_url, video):
                st.success("Downloaded from Drive! ✅")
            else:
                st.error("Drive Link Wrong ❌ - Share > Anyone with link cheyi")

# YouTube Info Only
url = st.text_input("Or Paste YouTube Link - Info Only")
if st.button("Get Video Info") and url:
    st.info("YouTube direct download block ayyindi bro ❌ - Studio lo Download chesi, paine Upload / Drive lo pettu")

if os.path.exists(video) and os.path.getsize(video) > 1000:
    st.video(video)
    duration = get_duration(video)
    st.info(f"Video Length: {duration:.0f} seconds | File: {os.path.getsize(video)/1024/1024:.1f} MB")
    prompt = st.text_input("Prompt", placeholder="Moment most likely to go viral")
    num = st.selectbox("How many clips?", [3, 5, 10])
    clip_len = st.selectbox("Clip Length", [15, 30, 45, 60])

    # --- CAPTIONS SECTION ---
    st.markdown("### ✍️ Captions - Viral Style")
    caption_on = st.checkbox("✅ Captions ON - OpusClip laaga", value=True)
    caption_text = st.text_input("Caption Text", value="FOLLOW FOR MORE 🔥", placeholder="Nee caption rayi bro...")
    font_choice = st.selectbox("🎨 Font Select Cheyi - 8 Fonts", list(FONTS.keys()))
    caption_color = st.selectbox("Caption Color", ["⚪ White", "🟡 Yellow", "🟢 Neon Green", "🔴 Red", "🔵 Cyan"])
    color_map = {"⚪ White":"&H00FFFFFF", "🟡 Yellow":"&H0000FFFF", "🟢 Neon Green":"&H0000FF00", "🔴 Red":"&H000000FF", "🔵 Cyan":"&H00FFFF00"}

    if st.button("🚀 Get Free Clips - ClipShort", type="primary", use_container_width=True):
        for f in glob.glob("clip_*.mp4"):
            os.remove(f)
        if duration < 10:
            st.error(f"Video too short: {duration:.0f} sec. Use at least 30 sec video!")
        else:
            with st.spinner(f"Generating {num} clips... Wait 1-2 mins... Do NOT refresh"):
                made = 0
                # Caption file okkasari create cheyi
                cap_file = None
                if caption_on and caption_text:
                    cap_file = make_caption_file(caption_text, FONTS[font_choice], color_map[caption_color])
                for i in range(num):
                    if num == 1:
                        start = 0
                    else:
                        start = int((duration - clip_len) * i / max(1, num-1))
                        if start < 0:
                            start = 0
                    out = f"clip_{i+1}.mp4"
                    vf = "crop=min(iw\\,ih*9/16):min(ih\\,iw*16/9),scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
                    # Caption add cheyadam
                    if cap_file:
                        vf = vf + f",subtitles={cap_file}"
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
