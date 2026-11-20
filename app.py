import streamlit as st
import os
import re
import subprocess
import tempfile
import requests
import imageio_ffmpeg

st.set_page_config(page_title="ClipShort AI", page_icon="✂️", layout="wide")

st.markdown("""
<style>
.stApp { background: #0f0c29 !important; }
h1,h2,h3,p,label,span { color: white !important; }
.stButton button { background: linear-gradient(90deg,#DD2476,#FF512F) !important; color:white !important; border-radius:50px !important; height:52px !important; width:100% !important; font-weight:700 !important; border:none !important; }
.stDownloadButton button { background:#00C853 !important; color:white !important; width:100% !important; border:none !important; border-radius:12px !important; }
video { border-radius:16px !important; width:100% !important; border:2px solid #DD2476 !important; }
</style>
""", unsafe_allow_html=True)

if "video_path" not in st.session_state: st.session_state["video_path"] = None
if "clips" not in st.session_state: st.session_state["clips"] = []
if "last_name" not in st.session_state: st.session_state["last_name"] = None

def get_drive_id(link):
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", link)
    if m: return m.group(1)
    m = re.search(r"id=([a-zA-Z0-9_-]+)", link)
    if m: return m.group(1)
    return None

def download_drive(link, out):
    fid = get_drive_id(link)
    if not fid: return False
    try:
        import gdown
        gdown.download(f"https://drive.google.com/uc?id={fid}", out, quiet=True, fuzzy=True)
        if os.path.exists(out) and os.path.getsize(out) > 10000: return True
    except Exception: pass
    return False

def download_yt(url, out):
    try:
        import yt_dlp
        opts = {'format': 'mp4/best[ext=mp4]/best', 'outtmpl': out.replace(".mp4", ".%(ext)s"), 'quiet': True, 'merge_output_format': 'mp4'}
        with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([url])
        if os.path.exists(out): return True
        base = out.replace(".mp4","")
        for f in os.listdir(os.path.dirname(out) or "."):
            if f.startswith(os.path.basename(base)) and f.endswith(".mp4"):
                os.rename(os.path.join(os.path.dirname(out) or ".", f), out); return True
        return False
    except Exception as e:
        st.error(f"YouTube Error: {e}"); return False

def get_duration(path):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+)", r.stderr)
    if m: return int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))
    return 120

def fmt_time(t):
    h=int(t//3600); m=int((t%3600)//60); s=int(t%60); cs=int((t%1)*100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def write_ass(path, caption_text, duration, font_size, colour, max_words):
    words = caption_text.upper().split()
    lines=[]
    for j in range(0, len(words), max_words): lines.append(" ".join(words[j:j+max_words]))
    if not lines: lines=["FOLLOW FOR MORE"]
    header = "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
    header += f"Style: Default,Arial Black,{font_size},{colour},&HFFFFFF&,&H80000000&,&H80000000&,-1,0,0,0,100,100,0,0,3,2,1,2,130,130,300,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    body=""
    chunk = max(3, duration / len(lines))
    for i, ln in enumerate(lines):
        s=i*chunk; e=min(duration, s+chunk)
        body += f"Dialogue: 0,{fmt_time(s)},{fmt_time(e)},Default,,0,0,0,,{ln}\n"
    open(path,"w",encoding="utf-8").write(header+body)

def make_clip(inp, out, start, duration, aspect, captions_on, caption_text, colour_ass, font_size, max_words, music_path, music_vol, orig_vol, brightness, contrast, saturation, speed):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    tmpdir = tempfile.mkdtemp()
    ass_path = os.path.join(tmpdir, "subs.ass")
    ass_esc = ass_path.replace("\\","/").replace(":","\\:").replace("'","\\'")
    if "9:16" in aspect: crop="crop=ih*9/16:ih,scale=1080:1920"
    elif "1:1" in aspect: crop="crop='min(iw,ih)':'min(iw,ih)',scale=1080:1080"
    elif "4:5" in aspect: crop="crop=ih*4/5:ih,scale=1080:1350"
    else: crop="scale=1920:1080"
    vf = f"{crop},eq=brightness={brightness}:contrast={contrast}:saturation={saturation}"
    if speed != 1.0: vf += f",setpts={1/speed}*PTS"
    if captions_on:
        write_ass(ass_path, caption_text, duration, font_size, colour_ass, max_words)
        vf += f",subtitles='{ass_esc}'"
    if music_path and os.path.exists(music_path):
        af = f"[0:a]volume={orig_vol/100.0}[a0];[1:a]volume={music_vol/100.0}[a1];[a0][a1]amix=inputs=2:duration=first[aout]"
        cmd = [ffmpeg,"-y","-ss",str(start),"-t",str(duration),"-i",inp,"-stream_loop","-1","-i",music_path,"-vf",vf,"-filter_complex",af,"-map","0:v","-map","[aout]","-c:v","libx264","-c:a","aac","-preset","fast","-crf","23","-shortest",out]
    else:
        if speed != 1.0:
            af = f"[0:a]volume={orig_vol/100.0},atempo={speed}[aout]"
            cmd = [ffmpeg,"-y","-ss",str(start),"-t",str(duration),"-i",inp,"-vf",vf,"-filter_complex",af,"-map","0:v","-map","[aout]","-c:v","libx264","-c:a","aac","-preset","fast","-crf","23",out]
        else:
            cmd = [ffmpeg,"-y","-ss",str(start),"-t",str(duration),"-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","fast","-crf","23",out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return os.path.exists(out) and os.path.getsize(out) > 10000

# ---------- UI ----------
st.markdown('<h1 style="text-align:center;">✂️ ClipShort AI - Pro Editor</h1>', unsafe_allow_html=True)
st.markdown('<p style="text-align:center;">Turn Any Video Into Viral Shorts</p>', unsafe_allow_html=True)

st.markdown("### 1. Upload Video")
t1,t2,t3 = st.tabs(["📤 Upload", "📺 YouTube", "📁 Drive"])
with t1:
    up = st.file_uploader("Choose video - Up to 4GB", type=["mp4","mov","mkv","webm"])
    if up and st.session_state["last_name"] != up.name + str(up.size):
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        for chunk in up: tf.write(chunk)
        tf.close()
        st.session_state["video_path"]=tf.name
        st.session_state["last_name"]=up.name+str(up.size)
        st.session_state["clips"]=[]
        st.success("✅ Uploaded!"); st.rerun()
with t2:
    yt = st.text_input("YouTube Link", placeholder="https://youtube.com/watch?v=...")
    if yt and st.button("Download YouTube"):
        tmp = tempfile.mktemp(suffix=".mp4")
        if download_yt(yt, tmp):
            st.session_state["video_path"]=tmp; st.session_state["clips"]=[]; st.success("✅ Downloaded!"); st.rerun()
        else: st.error("YouTube Failed!")
with t3:
    dr = st.text_input("Google Drive Link", placeholder="https://drive.google.com/file/d/...")
    if dr and st.button("Download Drive"):
        tmp = tempfile.mktemp(suffix=".mp4")
        if download_drive(dr, tmp):
            st.session_state["video_path"]=tmp; st.session_state["clips"]=[]; st.success("✅ Downloaded!"); st.rerun()
        else: st.error("Drive Failed - Share -> Anyone with link -> Viewer")

video_path = st.session_state["video_path"]
if video_path and os.path.exists(video_path):
    st.video(video_path)
    st.caption(f"Loaded: {os.path.getsize(video_path)/(1024*1024):.1f} MB")

st.markdown("### 2. Clip Settings")
c1,c2 = st.columns(2)
with c1:
    clip_len = st.slider("Clip Length (seconds)", 5, 90, 30)
    aspect = st.selectbox("Aspect Ratio", ["9:16 - Shorts / Reels","1:1 - Post","4:5 - Instagram Post","16:9 - YouTube"])
with c2:
    num_clips = st.slider("Number of Clips", 1, 30, 1)
    captions = st.toggle("Auto Captions", value=True)
    mode = st.selectbox("Clip Pick Mode", ["Auto - Equal Split - Full Video","Start to End - First Part Only"])

trim_start = st.slider("Trim Start (sec)", 0, 600, 0)
trim_end = st.slider("Trim End (sec) - 0 = Full Video", 0, 600, 0)

st.markdown("### 3. Captions + Font")
caption_text = st.text_input("Caption Text", value="FOLLOW FOR MORE")
f1,f2,f3 = st.columns(3)
with f1:
    col_name = st.selectbox("Caption Color", ["Yellow","White","Cyan","Pink","Green","Orange"])
    COL_MAP = {"Yellow":"&H00FFFF&","White":"&HFFFFFF&","Cyan":"&HFFFF00&","Pink":"&HFF00FF&","Green":"&H00FF00&","Orange":"&H0080FF&"}
    colour_ass = COL_MAP[col_name]
with f2:
    font_size = st.slider("Font Size", 10, 80, 28)
with f3:
    words_opt = st.selectbox("Words Per Line", ["2 Words - Best","3 Words","1 Word","4 Words"])
    max_words = 2 if "2 Words" in words_opt else 3 if "3 Words" in words_opt else 1 if "1 Word" in words_opt else 4

st.markdown("### 4. Editing")
e1,e2,e3,e4 = st.columns(4)
with e1: brightness = st.slider("Brightness", -0.3, 0.3, 0.0, step=0.01)
with e2: contrast = st.slider("Contrast", 0.5, 2.0, 1.0, step=0.05)
with e3: saturation = st.slider("Saturation", 0.0, 2.5, 1.0, step=0.05)
with e4: speed = st.slider("Speed", 0.5, 2.0, 1.0, step=0.25)

st.markdown("### 5. Music")
music_file = st.file_uploader("Upload Music (MP3)", type=["mp3","wav","m4a"])
music_path = None
if music_file:
    mf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    mf.write(music_file.read()); mf.close(); music_path=mf.name
    st.success(f"Music: {music_file.name}")
m1,m2 = st.columns(2)
with m1: music_vol = st.slider("Music Volume %", 0, 100, 20)
with m2: orig_vol = st.slider("Original Volume %", 0, 100, 100)

st.markdown("### 6. Generate")
if st.button("🔥 GENERATE VIRAL CLIPS - START"):
    if not video_path or not os.path.exists(video_path):
        st.error("❌ Upload Video First!")
    else:
        total = get_duration(video_path)
        eff_start = trim_start
        eff_end = trim_end if trim_end>0 else total
        if eff_end <= eff_start: eff_end = total
        avail = eff_end - eff_start
        if "First Part" in mode:
            starts = [eff_start + i*clip_len for i in range(num_clips)]
        else:
            step = max(clip_len, avail/max(1,num_clips))
            starts = [eff_start + i*step for i in range(num_clips)]
        clips=[]; bar=st.progress(0)
        for i,s in enumerate(starts):
            if s+clip_len > eff_end: s=max(eff_start, eff_end-clip_len)
            out=tempfile.mktemp(suffix=f"_clip{i+1}.mp4")
            with st.spinner(f"Making Clip {i+1}/{num_clips}..."):
                ok=make_clip(video_path,out,s,clip_len,aspect,captions,caption_text,colour_ass,font_size,max_words,music_path,music_vol,orig_vol,brightness,contrast,saturation,speed)
            if ok: clips.append(out)
            bar.progress((i+1)/num_clips)
        st.session_state["clips"]=clips
        st.success(f"✅ {len(clips)} Clips Ready!"); st.rerun()

if st.session_state["clips"]:
    st.markdown(f"### 🎬 {len(st.session_state['clips'])} Clips Ready!")
    for i, cp in enumerate(st.session_state["clips"]):
        st.markdown(f"**Clip {i+1}**")
        st.video(cp)
        with open(cp,"rb") as f:
            st.download_button(f"⬇️ Download Clip {i+1}", data=f.read(), file_name=f"clip_{i+1}.mp4", mime="video/mp4", key=f"dl{i}")
