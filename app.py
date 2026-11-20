import streamlit as st
import subprocess, tempfile, shutil, re, time, os
from pathlib import Path
from urllib.parse import urlparse, parse_qs

st.set_page_config(page_title="CLIPSHORT AI", page_icon="🎬", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
.stApp { background: #0b1120 !important; }
h1,h2,h3,p,label,span,div { color: white !important; }
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
.hero { padding: 28px; border-radius: 20px; background: linear-gradient(125deg,#172554,#312e81,#581c87); border: 1px solid #4338ca; }
.hero h1 { font-size: 38px; font-weight: 800; color: #fff !important; margin: 0; }
.hero p { color: #c7d2fe !important; }
div.stButton > button, div.stDownloadButton > button { background: linear-gradient(100deg,#6366f1,#9333ea) !important; color: white !important; border: none !important; border-radius: 12px !important; min-height: 48px !important; font-weight: 700 !important; }
[data-testid="stSelectbox"] div[data-baseweb="select"] > div { background: white !important; color: black !important; }
[data-testid="stSelectbox"] div[data-baseweb="select"] span { color: black !important; }
div[data-baseweb="popover"] * { color: black !important; background: white !important; }
.turbo-box { padding: 16px; border-radius: 14px; background: #022c22; border: 1px solid #10b981; }
.preview-box { padding: 16px; border-radius: 14px; background: #1e293b; border: 2px dashed #f59e0b; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="hero"><h1>🎬 CLIPSHORT AI</h1><p>🇬🇧 English + 🇮🇳 Indian · AI Video Clipping Studio · Auto Subtitles · Music · Shorts</p></div>', unsafe_allow_html=True)

if "preview_done" not in st.session_state:
    st.session_state.preview_done = False
if "preview_bytes" not in st.session_state:
    st.session_state.preview_bytes = None

# ===== FIX 1: INDIAN FONTS AUTO INSTALL =====
@st.cache_resource
def ensure_indian_fonts():
    try:
        font_dir = Path.home() / ".fonts"
        font_dir.mkdir(exist_ok=True)
        fonts = {
            "NotoSansTelugu-Regular.ttf": "https://github.com/notofonts/notofonts.github.io/raw/main/fonts/NotoSansTelugu/hinted/ttf/NotoSansTelugu-Regular.ttf",
            "NotoSansDevanagari-Regular.ttf": "https://github.com/notofonts/notofonts.github.io/raw/main/fonts/NotoSansDevanagari/hinted/ttf/NotoSansDevanagari-Regular.ttf",
            "NotoSansTamil-Regular.ttf": "https://github.com/notofonts/notofonts.github.io/raw/main/fonts/NotoSansTamil/hinted/ttf/NotoSansTamil-Regular.ttf",
            "NotoSansKannada-Regular.ttf": "https://github.com/notofonts/notofonts.github.io/raw/main/fonts/NotoSansKannada/hinted/ttf/NotoSansKannada-Regular.ttf",
            "NotoSansMalayalam-Regular.ttf": "https://github.com/notofonts/notofonts.github.io/raw/main/fonts/NotoSansMalayalam/hinted/ttf/NotoSansMalayalam-Regular.ttf",
            "NotoSansBengali-Regular.ttf": "https://github.com/notofonts/notofonts.github.io/raw/main/fonts/NotoSansBengali/hinted/ttf/NotoSansBengali-Regular.ttf",
            "NotoSansGujarati-Regular.ttf": "https://github.com/notofonts/notofonts.github.io/raw/main/fonts/NotoSansGujarati/hinted/ttf/NotoSansGujarati-Regular.ttf",
            "NotoSansGurmukhi-Regular.ttf": "https://github.com/notofonts/notofonts.github.io/raw/main/fonts/NotoSansGurmukhi/hinted/ttf/NotoSansGurmukhi-Regular.ttf",
        }
        import urllib.request
        for name, url in fonts.items():
            p = font_dir / name
            if not p.exists() or p.stat().st_size < 10000:
                try:
                    urllib.request.urlretrieve(url, str(p))
                except: pass
        subprocess.run(["fc-cache", "-f", str(font_dir)], capture_output=True)
        return True
    except: return False

ensure_indian_fonts()

def run_cmd(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0: raise RuntimeError((r.stderr or r.stdout)[-3000:])
    return r.stdout.strip()
def check_ffmpeg(): return shutil.which("ffmpeg") is not None
def get_duration(path):
    v = run_cmd(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)])
    return float(v)
def has_audio(path):
    r = subprocess.run(["ffprobe","-v","error","-select_streams","a:0","-show_entries","stream=codec_type","-of","csv=p=0",str(path)], capture_output=True, text=True)
    return bool(r.stdout.strip())
def get_drive_id(url):
    p = urlparse(url.strip())
    m = re.search(r"/file/d/([A-Za-z0-9_-]+)", p.path)
    if m: return m.group(1)
    q = parse_qs(p.query)
    if q.get("id"): return q["id"][0]
    raise ValueError("Invalid Drive link.")

def download_drive(url, folder, prog, txt):
    import requests
    fid = get_drive_id(url)
    target = folder / "drive_video.mp4"
    dl_url = f"https://drive.google.com/uc?export=download&id={fid}&confirm=t"
    s = requests.Session()
    r = s.get(dl_url, stream=True, timeout=60)
    try:
        for c in r.cookies:
            if c.name.startswith("download_warning"):
                r = s.get(f"https://drive.google.com/uc?export=download&id={fid}&confirm={c.value}", stream=True, timeout=60)
                break
    except: pass
    total_size = int(r.headers.get('content-length', 0))
    downloaded = 0
    start = time.time()
    with open(target, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024*1024*2):
            if chunk:
                f.write(chunk); downloaded += len(chunk)
                elapsed = time.time() - start
                if elapsed > 0:
                    speed = downloaded/1024/1024/elapsed
                    if total_size > 0:
                        pct = downloaded/total_size
                        prog.progress(min(pct,1.0))
                        txt.text(f"⚡ Downloading... {downloaded/1024/1024:.1f} MB / {total_size/1024/1024:.1f} MB | Speed: {speed:.1f} MB/s | {pct*100:.0f}%")
                    else:
                        txt.text(f"⚡ Downloading... {downloaded/1024/1024:.1f} MB | Speed: {speed:.1f} MB/s")
    prog.progress(1.0)
    txt.text(f"✅ Download Done! {downloaded/1024/1024:.1f} MB")
    if not target.exists() or target.stat().st_size < 10000:
        raise RuntimeError("Drive failed. Set Anyone with link -> Viewer.")
    return target

def download_youtube(url, folder):
    import yt_dlp
    opts = {"format":"best[height<=720][ext=mp4]/best[height<=720]/best","outtmpl":str(folder/"youtube_video.%(ext)s"),"noplaylist":True,"quiet":True}
    with yt_dlp.YoutubeDL(opts) as d: d.download([url])
    files = list(folder.glob("youtube_video.*"))
    if not files: raise RuntimeError("YouTube blocked. Upload video instead.")
    return files[0]

LANGUAGE_CODES = {
    "English - English": "en",
    "English (Translate) - Any Language to English": "translate",
    "Telugu - తెలుగు": "te",
    "Hindi - हिन्दी": "hi",
    "Tamil - தமிழ்": "ta",
    "Kannada - ಕನ್ನಡ": "kn",
    "Malayalam - മലയാളം": "ml",
    "Bengali - বাংলা": "bn",
    "Marathi - मराठी": "mr",
    "Gujarati - ગુજરાતી": "gu",
    "Punjabi - ਪੰਜਾਬੀ": "pa",
    "Urdu - اردو": "ur",
    "Odia - ଓଡ଼ିଆ": "or",
    "Assamese - অসমীয়া": "as",
    "Auto Detect - Automatic": "auto",
}
# FIX: Font per language - Telugu ki Telugu font, Hindi ki Devanagari font
FONT_FOR_LANG = {
    "te": "Noto Sans Telugu",
    "hi": "Noto Sans Devanagari",
    "mr": "Noto Sans Devanagari",
    "ta": "Noto Sans Tamil",
    "kn": "Noto Sans Kannada",
    "ml": "Noto Sans Malayalam",
    "bn": "Noto Sans Bengali",
    "as": "Noto Sans Bengali",
    "gu": "Noto Sans Gujarati",
    "pa": "Noto Sans Gurmukhi",
    "ur": "Noto Sans",
    "or": "Noto Sans Oriya",
    "en": "Noto Sans",
    "translate": "Noto Sans",
    "auto": "Noto Sans",
}

@st.cache_resource
def load_whisper():
    from faster_whisper import WhisperModel
    # FIX 5: Try small, fail aithe tiny - OOM Rakunda
    try:
        return WhisperModel("small", device="cpu", compute_type="int8")
    except:
        return WhisperModel("tiny", device="cpu", compute_type="int8")

def transcribe_video(path, language):
    try:
        audio_path = Path(str(path) + "_audio.wav")
        subprocess.run(["ffmpeg","-y","-i",str(path),"-vn","-ac","1","-ar","16000","-af","loudnorm,volume=2.0","-c:a","pcm_s16le",str(audio_path)], capture_output=True)
        if not audio_path.exists() or audio_path.stat().st_size < 1000:
            return []
        model = load_whisper()
        code = LANGUAGE_CODES.get(language, "te")
        opts = {"vad_filter": False, "beam_size": 1, "temperature": 0.0, "no_speech_threshold": 0.3}
        if code == "translate":
            opts["task"] = "translate"
        elif code == "auto":
            pass
        else:
            opts["language"] = code
        segments,_ = model.transcribe(str(audio_path), **opts)
        out=[]
        for s in segments:
            txt = s.text.strip()
            if txt and getattr(s,"no_speech_prob",0) < 0.95:
                out.append({"start":float(s.start),"end":float(s.end),"text":txt})
        return out
    except Exception as e:
        print(f"Subtitle skipped: {e}")
        return []

def choose_starts(segments,total,length,count):
    if total<=length: return [0.0]
    step=max(2.0,min(length/5,6.0)); cands=[]; start=0.0
    while start+length<=total:
        end=start+length
        score=sum(max(0.0,min(s["end"],end)-max(s["start"],start)) for s in segments)
        cands.append((score,start)); start+=step
    cands.sort(key=lambda x:x[0],reverse=True)
    sel=[]
    for _,s in cands:
        if all(abs(s-p)>=length*0.65 for p in sel): sel.append(s)
        if len(sel)>=count: break
    return sorted(sel or [0.0])

def ass_time(sec):
    h=int(sec//3600); m=int((sec%3600)//60); r=sec%60
    return f"{h}:{m:02d}:{r:05.2f}"
def ass_color(v):
    v=v.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}",v): v="FFFFFF"
    return f"&H00{v[4:6]}{v[2:4]}{v[0:2]}&".upper()

RATIOS = {
    "9:16 - Shorts / Reels / TikTok (Vertical)": (1080,1920),
    "16:9 - YouTube (Horizontal)": (1920,1080),
    "1:1 - Instagram Post (Square)": (1080,1080),
    "4:5 - Instagram Portrait": (1080,1350),
    "4:3 - Classic": (1440,1080),
}
RESOLUTIONS = {
    "480p - Fast / Low Size": 480,
    "720p - HD / Balanced": 720,
    "1080p - Full HD / Best Quality": 1080,
}

def get_output_size(ratio_label, res_label):
    base_w, base_h = RATIOS[ratio_label]
    target = RESOLUTIONS[res_label]
    # FIX 4: Short side ni target chey - 9:16 lo width=target, 16:9 lo height=target
    if base_w <= base_h:
        # Vertical / Square - width is short side
        scale = target / base_w if base_w < base_h else target / base_w
        # 9:16: 480p = 480x854, 720p=720x1280, 1080p=1080x1920
        # 1:1: 480x480, 720x720, 1080x1080
        w = target
        h = int(base_h * (target / base_w))
    else:
        # 16:9 Horizontal - height is short side
        h = target
        w = int(base_w * (target / base_h))
    w = w - (w % 2); h = h - (h % 2)
    return w, h

def write_subtitles(f, segments, cs, ce, cfg, out_h):
    align={"Bottom":2,"Middle":5,"Top":8}[cfg["position"]]
    bold=-1 if cfg["bold"] else 0
    border=3 if cfg["background"] else 1
    outline=0 if cfg["background"] else cfg["outline"]
    # FIX 1: Language ki correct font
    lang_code = LANGUAGE_CODES.get(cfg["language"], "te")
    font = FONT_FOR_LANG.get(lang_code, "Noto Sans")
    fs = cfg["font_size"]
    if out_h <= 854: fs = max(18, int(cfg["font_size"] * 0.45))
    elif out_h <= 1280: fs = max(22, int(cfg["font_size"] * 0.65))
    margin_v = int(90 * (out_h / 1920)) if out_h < 1920 else 90
    rows=["[Script Info]","ScriptType: v4.00+",f"PlayResX: {cfg['out_w']}","PlayResY: {cfg['out_h']}","","[V4+ Styles]","Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",f"Style: Default,{font},{fs},{ass_color(cfg['text_color'])},&H000000FF&,{ass_color(cfg['outline_color'])},{ass_color(cfg['background_color'])},{bold},0,0,0,100,100,0,0,{border},{outline},{cfg['shadow']},{align},60,60,{margin_v},1","","[Events]","Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for s in segments:
        st_=max(s["start"],cs); en=min(s["end"],ce)
        if en<=st_: continue
        cap=s["text"].replace("\\",r"\\").replace("{",r"\{").replace("}",r"\}").replace("\n"," ")
        if cfg["uppercase"]: cap=cap.upper()
        rows.append(f"Dialogue: 0,{ass_time(st_-cs)},{ass_time(en-cs)},Default,,0,0,0,,{cap}")
    f.write_text("\n".join(rows),encoding="utf-8")

def sub_path(p):
    v=str(p.resolve()).replace("\\","/")
    return v.replace(":","\\:").replace("'","\\'").replace(",","\\,")
def render_clip(source,output,start,length,segments,cfg,music):
    out_w, out_h = cfg["out_w"], cfg["out_h"]
    args=["ffmpeg","-y","-ss",str(start),"-i",str(source)]
    if music: args+=["-stream_loop","-1","-i",str(music)]
    filters=[f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase",f"crop={out_w}:{out_h}","setsar=1","fps=30"]
    sub_file=output.with_suffix(".ass")
    if cfg["subtitles"] and segments:
        write_subtitles(sub_file,segments,start,start+length,cfg,out_h)
        filters.append("ass='"+sub_path(sub_file)+"'")
    args+=["-t",str(length),"-vf",",".join(filters),"-c:v","libx264","-preset",cfg["preset"],"-crf",str(cfg["crf"]),"-pix_fmt","yuv420p"]
    src_audio=has_audio(source)
    if music and src_audio:
        args+=["-filter_complex",f"[0:a]volume={cfg['source_volume']}[a0];[1:a]volume={cfg['music_volume']}[a1];[a0][a1]amix=inputs=2:duration=first[aout]","-map","0:v:0","-map","[aout]","-c:a","aac"]
    elif music:
        args+=["-map","0:v:0","-map","1:a:0","-af",f"volume={cfg['music_volume']}","-c:a","aac"]
    elif src_audio:
        args+=["-af",f"volume={cfg['source_volume']}","-c:a","aac"]
    else: args+=["-an"]
    args+=["-movflags","+faststart",str(output)]
    run_cmd(args)
    if sub_file.exists(): sub_file.unlink()

def get_source(work, source_type, video_url, video_upload):
    if source_type=="Google Drive":
        prog = st.progress(0); txt = st.empty()
        return download_drive(video_url,work,prog,txt)
    elif source_type=="YouTube":
        st.write("Downloading YouTube...")
        return download_youtube(video_url,work)
    else:
        source=work/("uploaded_video"+Path(video_upload.name).suffix.lower())
        with source.open("wb") as f: shutil.copyfileobj(video_upload,f,length=8*1024*1024)
        return source

def get_music(work, music_upload):
    if music_upload is None: return None
    music=work/("background_music"+Path(music_upload.name).suffix.lower())
    with music.open("wb") as f: shutil.copyfileobj(music_upload,f,length=1024*1024)
    return music

# ============ UI ============
st.subheader("📁 Video Source")
source_type=st.radio("Choose source",["Google Drive","Upload video","YouTube"],horizontal=True, key="src_type")
video_url=""; video_upload=None
if source_type=="Google Drive":
    video_url=st.text_input("Google Drive sharing link",placeholder="Paste your Drive link")
    st.caption("Drive: Anyone with the link → Viewer.")
elif source_type=="Upload video":
    video_upload=st.file_uploader("Upload video",type=["mp4","mov","mkv","webm","avi","m4v"])
else:
    video_url=st.text_input("YouTube URL",placeholder="Paste YouTube video link")

st.subheader("🎵 Background Music")
music_upload=st.file_uploader("Upload music (optional)",type=["mp3","wav","m4a","aac","ogg","flac"])

st.subheader("⚡ Internet Speed Booster")
turbo = st.toggle("🚀 TURBO MODE - Fast Download + Fast Render", value=True)
if turbo:
    st.markdown('<div class="turbo-box">✅ <b>TURBO ON</b> - Download: MAX Speed | Render: ULTRAFAST | AI: Small Model</div>', unsafe_allow_html=True)
else:
    st.info("🐢 TURBO OFF - Normal Mode")

with st.expander("⚙️ EDIT SETTINGS - Click To Open", expanded=True):
    c1,c2,c3 = st.columns(3)
    with c1:
        clip_count=st.slider("Maximum clips",1,30,3)
        clip_length=st.slider("Clip duration (seconds)",10,90,30)
        subtitles=st.toggle("Automatic subtitles",value=True)
        language=st.selectbox("🌍 Subtitle language - English + Indian", list(LANGUAGE_CODES.keys()), index=2)
    with c2:
        font_size=st.slider("Font size",18,80,48)
        bold=st.toggle("Bold font",True); uppercase=st.toggle("Uppercase text",False)
        position=st.selectbox("Caption position",["Bottom","Middle","Top"])
    with c3:
        text_color=st.color_picker("Text colour","#FFFFFF")
        outline_color=st.color_picker("Outline colour","#000000")
        outline=st.slider("Outline thickness",0,10,3)
        background=st.toggle("Caption background",False)
        background_color=st.color_picker("Caption background colour","#151515")
        shadow=st.slider("Caption shadow",0,5,2)
    c4,c5,c6 = st.columns(3)
    with c4: source_volume=st.slider("Original audio volume",0.0,2.0,1.5)
    with c5: music_volume=st.slider("Background music volume",0.0,2.0,0.25)
    with c6: quality=st.selectbox("Video quality",["Fast","Balanced","High"],index=1)
    st.markdown("---")
    st.markdown("### 📐 Ratio & Resolution")
    r1,r2 = st.columns(2)
    with r1:
        ratio_label = st.selectbox("📐 Aspect Ratio", list(RATIOS.keys()), index=0)
    with r2:
        res_label = st.selectbox("🎞️ Resolution", list(RESOLUTIONS.keys()), index=1)
    out_w, out_h = get_output_size(ratio_label, res_label)
    st.info(f"✅ Selected: **{ratio_label.split(' - ')[0]}** | **{res_label.split(' - ')[0]}** | Output: **{out_w} x {out_h}**")

cfg={"subtitles":subtitles,"font_size":font_size,"text_color":text_color,"outline_color":outline_color,"outline":outline,"position":position,"bold":bold,"uppercase":uppercase,"background":background,"background_color":background_color,"shadow":shadow,"source_volume":source_volume,"music_volume":music_volume,"preset":{"Fast":"ultrafast","Balanced":"veryfast","High":"fast"}[quality],"crf":{"Fast":27,"Balanced":23,"High":19}[quality],"out_w":out_w,"out_h":out_h,"ratio":ratio_label,"resolution":res_label,"language":language}
if turbo:
    cfg["preset"]="ultrafast"; cfg["crf"]=28

# ============ STEP 1: PREVIEW - MANDATORY ============
st.subheader("👀 Step 1: Preview (Mandatory)")
st.markdown('<div class="preview-box">⚠️ <b>MANDATORY:</b> First Preview Chudu - Tarvatha Ne Generate Button Open Avuthundi!</div>', unsafe_allow_html=True)
# FIX 3: Unique key
if st.button("👀 GENERATE PREVIEW - 5 Sec Sample", use_container_width=True, key="btn_preview"):
    if source_type=="Upload video" and video_upload is None:
        st.error("Please upload a video first."); st.stop()
    if source_type!="Upload video" and not video_url.strip().startswith(("https://","http://")):
        st.error("Please enter a valid video link."); st.stop()
    if not check_ffmpeg():
        st.error("FFmpeg missing. packages.txt lo ffmpeg ledu - Admin ki cheppu."); st.stop()
    work=Path(tempfile.mkdtemp(prefix="preview_"))
    try:
        with st.status("Making Preview...",expanded=True) as status:
            source=get_source(work, source_type, video_url, video_upload)
            music=get_music(work, music_upload)
            total=get_duration(source)
            segs=[]
            if cfg["subtitles"]:
                st.write(f"Transcribing in {language}... Please wait")
                segs=transcribe_video(source,language)
                if segs: st.write(f"✅ Found {len(segs)} subtitle lines in {language}")
                else: st.warning("⚠️ No speech found in preview - Check if video has voice")
            preview_out=work/"preview.mp4"
            render_clip(source,preview_out,0,5,segs,cfg,music)
            status.update(label="Preview Ready!"
