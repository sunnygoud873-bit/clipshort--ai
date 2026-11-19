import streamlit as st
import requests
import os
import re
import subprocess
import tempfile
import imageio_ffmpeg

st.set_page_config(
    page_title="ClipShort AI",
    page_icon="✂️",
    layout="wide"
)

st.markdown("""
<style>
* { box-sizing: border-box !important; }
.stApp { background: #0f0c29 !important; }
.main .block-container {
  max-width: 720px !important;
  padding: 12px 12px 80px 12px !important;
  margin: auto !important;
}
h1, h2, h3, p, label { color: white !important; }
.stTextInput input, .stTextArea textarea {
  background: white !important;
  color: black !important;
  border-radius: 12px !important;
  font-weight: 600 !important;
  width: 100% !important;
}
.stButton button {
  background: #DD2476 !important;
  color: white !important;
  border-radius: 50px !important;
  font-weight: 700 !important;
  width: 100% !important;
  height: 52px !important;
}
.stDownloadButton button {
  background: #00C853 !important;
  border-radius: 12px !important;
  width: 100% !important;
}
.card {
  background: rgba(255,255,255,0.10);
  border-radius: 16px;
  padding: 14px;
  margin: 12px 0;
  width: 100% !important;
}
video {
  border-radius: 16px !important;
  width: 100% !important;
  max-height: 560px !important;
  object-fit: contain !important;
}
@media (max-width: 600px) {
  .main .block-container { padding: 8px 8px 80px 8px !important; }
  h1 { font-size: 28px !important; }
  video { max-height: 420px !important; }
}
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
        st.error("Could not find ID in link")
        return False
    try:
        import gdown
        url = "https://drive.google.com/uc?id=" + fid
        gdown.download(url, out_path, quiet=True, fuzzy=True)
        if os.path.exists(out_path):
            if os.path.getsize(out_path) > 10000:
                f = open(out_path, "rb")
                h = f.read(30)
                f.close()
                if b"<html" not in h.lower():
                    return True
    except Exception:
        pass
    try:
        session = requests.Session()
        url = "https://drive.google.com/uc?export=download&id=" + fid
        r = session.get(url, stream=True)
        for key, val in r.cookies.items():
            if key.startswith("download_warning"):
                url = "https://drive.google.com/uc?export=download&confirm=" + val + "&id=" + fid
                r = session.get(url, stream=True)
                break
        f = open(out_path, "wb")
        for chunk in r.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)
        f.close()
        if os.path.exists(out_path):
            if os.path.getsize(out_path) > 10000:
                f = open(out_path, "rb")
                h = f.read(30)
                f.close()
                if b"<html" not in h.lower():
                    return True
                st.error("Set Drive to Anyone with link")
                return False
    except Exception:
        st.error("Download error")
    return False

def get_duration(path):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    res = subprocess.run(
        [ffmpeg, "-i", path],
        capture_output=True,
        text=True
    )
    m = re.search(r"Duration: (\d+):(\d+):(\d+)", res.stderr)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        s = int(m.group(3))
        return h * 3600 + mi * 60 + s
    return 0

def fmt_time(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def split_lines(txt, max_words):
    words = txt.upper().split()
    lines = []
    for j in range(0, len(words), max_words):
        lines.append(" ".join(words[j:j+max_words]))
    return lines

def make_srt(audio_path, srt_path, fallback_text, max_words):
    try:
        import whisper
        model = whisper.load_model("tiny")
        result = model.transcribe(audio_path, fp16=False)
        if result.get("segments"):
            f = open(srt_path, "w", encoding="utf-8")
            for i, seg in enumerate(result["segments"]):
                txt = seg["text"].strip()
                if not txt:
                    continue
                lines = split_lines(txt, max_words)
                txt2 = "\\N".join(lines)
                f.write(str(i + 1) + "\n")
                f.write(fmt_time(seg["start"]) + " --> ")
                f.write(fmt_time(seg["end"]) + "\n")
                f.write(txt2 + "\n\n")
            f.close()
            if os.path.getsize(srt_path) > 20:
                return True
    except Exception:
        pass
    lines = split_lines(fallback_text, max_words)
    wrapped = "\\N".join(lines)
    f = open(srt_path, "w", encoding="utf-8")
    f.write("1\n00:00:00,000 --> 00:00:30,000\n")
    f.write(wrapped + "\n\n")
    f.close()
    return False

def get_safe_font_size(font_size, max_words):
    # If line is long, auto reduce font size - Never cut
    if max_words <= 2:
        return font_size
    if max_words == 3:
        if font_size > 20:
            return 20
        return font_size
    if font_size > 18:
        return 18
    return font_size

def make_clip(
    input_path, output_path, start, duration,
    aspect, captions_on, caption_text,
    caption_color, font, font_size,
    font_style, subtitle_position,
    outline_size, music_option,
    music_volume, fade_music,
    uploaded_music_path, effect,
    max_words
):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    tmpdir = tempfile.mkdtemp()
    srt_path = os.path.join(tmpdir, "subs.srt")
    srt_esc = srt_path.replace("\\", "/")
    srt_esc = srt_esc.replace(":", "\\:")

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
        audio_path = os.path.join(tmpdir, "audio.wav")
        cmd_a = [
            ffmpeg, "-y",
            "-ss", str(start),
            "-t", str(duration),
            "-i", input_path,
            "-vn", "-ac", "1", "-ar", "16000",
            audio_path
        ]
        subprocess.run(cmd_a, capture_output=True)
        if os.path.exists(audio_path):
            make_srt(audio_path, srt_path, caption_text, max_words)
        else:
            f = open(srt_path, "w", encoding="utf-8")
            f.write("1\n00:00:00,000 --> 00:00:30,000\n")
            lines = split_lines(caption_text, max_words)
            f.write("\\N".join(lines) + "\n\n")
            f.close()

        if "Montserrat" in font:
            ff_font = "Arial Black"
        elif "Bebas" in font:
            ff_font = "Arial Narrow"
        elif "Anton" in font:
            ff_font = "Impact"
        elif "Impact" in font:
            ff_font = "Impact"
        else:
            ff_font = "Arial"

        if caption_color == "White":
            col = "&HFFFFFF&"
        elif caption_color == "Cyan":
            col = "&HFFFF00&"
        elif caption_color == "Pink":
            col = "&HFF00FF&"
        elif caption_color == "Green":
            col = "&H00FF00&"
        elif caption_color == "Orange":
            col = "&H0080FF&"
        else:
            col = "&H00FFFF&"

        if "No Box" in font_style:
            bstyle = 1
            outl = outline_size
            shad = 0
        elif "Outline Only" in font_style:
            bstyle = 1
            outl = outline_size + 1
            shad = 0
        elif "Shadow" in font_style:
            bstyle = 1
            outl = 1
            shad = 2
        else:
            bstyle = 3
            outl = outline_size
            shad = 1

        # CAPTION POSITION - Safe Area for All Devices
        # Bottom = 300 = Above Shorts Like/Comment buttons
        # Middle = Center, Top = 140 = Below notch
        if "Middle" in subtitle_position:
            align = 5
            marg = 0
        elif "Top" in subtitle_position:
            align = 8
            marg = 140
        else:
            align = 2
            marg = 300

        safe_size = get_safe_font_size(font_size, max_words)

        style = "FontName=" + ff_font
        style += ",FontSize=" + str(safe_size)
        style += ",PrimaryColour=" + col
        style += ",OutlineColour=&H80000000&"
        style += ",BorderStyle=" + str(bstyle)
        style += ",Outline=" + str(outl)
        style += ",Shadow=" + str(shad)
        style += ",Alignment=" + str(align)
        style += ",MarginV=" + str(marg)
        # MarginL/R 60 -> 130 : 130px gap left/right, never cut
        style += ",MarginL=130,MarginR=130,Bold=1,WrapStyle=2"
        vf = base_vf + ",subtitles='" + srt_esc + "'"
        vf += ":force_style='" + style + "'"

    music_path = None
    if music_option != "No Music":
        if uploaded_music_path:
            if os.path.exists(uploaded_music_path):
                music_path = uploaded_music_path

    if music_path:
        mv = music_volume / 100.0
        if fade_music:
            af = "[0:a]volume=1.0[a0];"
            af += "[1:a]volume=" + str(mv)
            af += ",afade=t=in:st=0:d=1"
            af += ",afade=t=out:st=" + str(duration - 1) + ":d=1[a1];"
            af += "[a0][a1]amix=inputs=2:duration=first[aout]"
        else:
            af = "[0:a]volume=1.0[a0];"
            af += "[1:a]volume=" + str(mv) + "[a1];"
            af += "[a0][a1]amix=inputs=2:duration=first[aout]"
        cmd = [
            ffmpeg, "-y",
            "-ss", str(start),
            "-t", str(duration),
            "-i", input_path,
            "-stream_loop", "-1",
            "-i", music_path,
            "-vf", vf,
            "-filter_complex", af,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-crf", "23",
            "-shortest", output_path
        ]
    else:
        cmd = [
            ffmpeg, "-y",
            "-ss", str(start),
            "-t", str(duration),
            "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-crf", "23",
            output_path
        ]

    subprocess.run(cmd, capture_output=True)
    if os.path.exists(output_path):
        if os.path.getsize(output_path) > 10000:
            return True
    return False

st.markdown(
    '<h1 style="text-align:center;">ClipShort AI</h1>',
    unsafe_allow_html=True
)
st.markdown(
    '<p style="text-align:center;">Turn Any Video Into Viral Shorts</p>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="card"><h3>1. Upload Your Video</h3></div>',
    unsafe_allow_html=True
)
uploaded = st.file_uploader(
    "Choose a video file",
    type=["mp4", "mov", "mkv", "webm"],
    use_container_width=True
)
drive_link = st.text_input(
    "Paste Google Drive Link",
    placeholder="https://drive.google.com/file/d/..."
)
if drive_link and st.button("Download from Drive", use_container_width=True):
    with st.spinner("Downloading..."):
        tmp = tempfile.mktemp(suffix=".mp4")
        if download_drive(drive_link, tmp):
            st.session_state["video_path"] = tmp
            st.session_state["clips"] = []
            st.session_state["viral_done"] = False
            st.success("Downloaded! Video is ready.")
            st.rerun()
        else:
            st.error("Download failed. Set Drive to Anyone with link.")

video_path = st.session_state.get("video_path")
if uploaded:
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tf.write(uploaded.read())
    tf.close()
    video_path = tf.name
    st.session_state["video_path"] = video_path
if video_path and os.path.exists(video_path):
    f = open(video_path, "rb")
    vb = f.read()
    f.close()
    st.video(vb)
    mb = len(vb) // 1024 // 1024
    st.caption("Video loaded: " + str(mb) + " MB")

st.markdown(
    '<div class="card"><h3>2. Clip Settings</h3></div>',
    unsafe_allow_html=True
)
prompt = st.text_input(
    "Prompt",
    placeholder="Moment most likely to go viral"
)
clip_len = st.slider("Clip Length (seconds)", 15, 60, 30)
aspect = st.selectbox(
    "Aspect Ratio",
    ["9:16 - Shorts / Reels", "1:1 - Post", "16:9 - YouTube"]
)
num_clips = st.slider("Number of Clips", 1, 3, 1)
captions = st.toggle("Auto Captions", value=True)

# STEP 3 - CAPTION POSITION + STYLE - LIKE OPUS CLIP
st.markdown(
    '<div class="card"><h3>3. Captions - Position and Style</h3></div>',
    unsafe_allow_html=True
)
caption_text = st.text_input("Caption Text", value="FOLLOW FOR MORE")
st.caption("Preview like Opus: Word Cut = 2 words per line, never cuts")

c1, c2 = st.columns(2)
with c1:
    font = st.selectbox(
        "Caption Font Style",
        [
            "Poppins Bold - Clean",
            "Montserrat Bold - YouTube",
            "Bebas Neue - Viral Reels",
            "Anton - Bold Movie",
            "Oswald Bold - News",
            "Impact - Meme Style"
        ]
    )
with c2:
    caption_color = st.selectbox(
        "Caption Color",
        ["Yellow", "White", "Cyan", "Pink", "Green", "Orange"]
    )

# NEW: Words Per Line - Main Cut Fix
c3, c4 = st.columns(2)
with c3:
    words_opt = st.selectbox(
        "Words Per Line - Anti Cut",
        [
            "2 Words - Word Cut - Safest - Opus Style",
            "3 Words - Balanced",
            "4 Words - Long - May Cut on Phone"
        ]
    )
    if "2 Words" in words_opt:
        max_words = 2
    elif "3 Words" in words_opt:
        max_words = 3
    else:
        max_words = 4
with c4:
    font_style = st.selectbox(
        "Subtitle Style",
        [
            "Bold + Black Box - Viral Reels",
            "Bold + No Box - Clean",
            "Outline Only - Gaming",
            "Shadow - Cinematic"
        ]
    )

c5, c6 = st.columns(2)
with c5:
    font_size = st.slider("Font Size", 14, 48, 22)
    if font_size <= 26:
        st.caption("Perfect - Will not cut off")
    elif font_size <= 34:
        st.caption("Large - Will show in 2 lines")
    else:
        st.caption("Very Large - May cut off")
with c6:
    outline_size = st.slider("Outline Thickness", 1, 5, 2)

# NEW: Caption Position - Safe Area
subtitle_position = st.selectbox(
    "Caption Position - Safe Area",
    [
        "Bottom Center - Safe for Shorts - Above Buttons",
        "Middle Center - Face Video",
        "Top Center - Below Notch"
    ]
)
st.caption("Bottom = 300px above bottom, so Like/Comment buttons do not hide text")

st.markdown(
    '<div class="card"><h3>4. Background Music</h3></div>',
    unsafe_allow_html=True
)
music_option = st.selectbox(
    "Choose Music",
    ["No Music - Original Audio Only", "Upload My Own Music"]
)
if music_option != "No Music - Original Audio Only":
    m1, m2 = st.columns(2)
    with m1:
        music_volume = st.slider("Music Volume", 0, 100, 20)
        st.caption("Music: " + str(music_volume) + "%")
    with m2:
        fade_music = st.toggle("Fade In / Fade Out", value=True)
else:
    music_volume = 0
    fade_music = False
uploaded_music = None
if music_option == "Upload My Own Music":
    uploaded_music = st.file_uploader(
        "Upload Your Song (MP3)",
        type=["mp3", "wav", "m4a"]
    )
    if uploaded_music:
        st.success("Music Uploaded: " + uploaded_music.name)
        st.audio(uploaded_music)
    else:
        st.info("Upload an MP3 - Trending song / Gaming beat")

st.markdown(
    '<div class="card"><h3>5. Video Effect</h3></div>',
    unsafe_allow_html=True
)
effect = st.selectbox(
    "Choose Effect",
    [
        "No Effect - Original",
        "Vibrant - Reels Pop",
        "Cinematic - Movie Look",
        "Black and White - Classic",
        "Vintage - Old Film",
        "Sharpen + HDR - Ultra Clear",
        "Dark Mode - Night Gaming"
    ]
)

if video_path and os.path.exists(video_path):
    if st.button("Generate Viral Clips", use_container_width=True):
        duration = get_duration(video_path)
        if duration == 0:
            st.error("Could not read video. Re-upload.")
        else:
            uploaded_music_path = None
            if uploaded_music:
                tfm = tempfile.NamedTemporaryFile(
                    delete=False, suffix=".mp3"
                )
                tfm.write(uploaded_music.read())
                tfm.close()
                uploaded_music_path = tfm.name
            with st.spinner("Generating... Please wait"):
                st.session_state["clips"] = []
                st.session_state["selected_clip"] = 0
                for i in range(num_clips):
                    start = (duration // (num_clips + 1)) * (i + 1)
                    if start < 0:
                        start = 0
                    out = tempfile.mktemp(suffix="_clip.mp4")
                    ok = make_clip(
                        video_path, out, start,
                        min(clip_len, duration - start),
                        aspect, captions, caption_text,
                        caption_color, font, font_size,
                        font_style, subtitle_position,
                        outline_size, music_option,
                        music_volume, fade_music,
                        uploaded_music_path, effect,
                        max_words
                    )
                    if ok:
                        f = open(out, "rb")
                        cb = f.read()
                        f.close()
                        st.session_state["clips"].append(
                            {"name": "Clip " + str(i + 1), "data": cb}
                        )
                    else:
                        st.error("Failed to create Clip " + str(i + 1))
                st.session_state["viral_done"] = True
            st.balloons()
            st.rerun()
else:
    st.info("Upload a video first to generate clips")

if st.session_state["clips"]:
    st.markdown(
        '<div class="card"><h3>Your Clips Ready</h3></div>',
        unsafe_allow_html=True
    )
    clip_names = []
    for c in st.session_state["clips"]:
        clip_names.append(c["name"])
    selected = st.radio(
        "Choose Clip to Play:",
        clip_names,
        index=st.session_state["selected_clip"],
        horizontal=True
    )
    sel_idx = clip_names.index(selected)
    st.session_state["selected_clip"] = sel_idx
    c = st.session_state["clips"][sel_idx]
    st.success(c["name"] + " Ready - 1080p HD")
    st.video(c["data"])
    st.download_button(
        "Download " + c["name"],
        c["data"],
        file_name="clipshort_clip.mp4",
        mime="video/mp4",
        use_container_width=True
    )

    if st.session_state["viral_done"]:
        st.markdown(
            '<div class="card"><h3>Viral Title and Description</h3></div>',
            unsafe_allow_html=True
        )
        base_topic = prompt
        if not base_topic:
            base_topic = caption_text
        if base_topic == "FOLLOW FOR MORE":
            base_topic = "This Amazing Moment"
        t1 = base_topic + " You Wont Believe This! #shorts"
        t2 = "OMG! " + base_topic + " Viral Moment!"
        t3 = base_topic + " - Watch Till End!"
        titles = [t1, t2, t3]
        st.write("Copy and paste into YouTube Title:")
        selected_title = st.selectbox("Choose Best Title", titles)
        st.text_input("Your Viral Title", value=selected_title)
        desc = selected_title + "\n\n"
        desc += base_topic + " - This is the most viral moment. "
        desc += "Watch till end and comment your reaction.\n\n"
        desc += "Follow ClipShort AI for more viral shorts!\n\n"
        desc += "#shorts #viral #trending #youtubeshorts #reels #fyp"
        st.write("Description - Copy All:")
        st.text_area("Your Viral Description", value=desc, height=180)
        htags = "#shorts #viral #trending #youtubeshorts #reels #fyp"
        st.write("Hashtags:")
        st.text_input("Hashtags", value=htags)
        st.success("Title + Description Ready!")

st.markdown(
    '<p style="text-align:center;">Made by ClipShort AI - Free for Creators</p>',
    unsafe_allow_html=True
)
