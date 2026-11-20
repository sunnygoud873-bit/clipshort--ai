import streamlit as st
import subprocess, tempfile, shutil, re, time
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
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="hero"><h1>🎬 CLIPSHORT AI</h1><p>AI Video Clipping Studio · Automatic Subtitles · Music · Shorts</p></div>', unsafe_allow_html=True)

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

LANGUAGE_CODES = {"Hindi":"hi","Telugu":"te","Tamil":"ta","Kannada":"kn","Malayalam":"ml","Bengali":"bn","Marathi":"mr","Gujarati":"gu","Punjabi":"pa","Urdu":"ur"}

@st.cache_resource
def load_whisper():
    from faster_whisper import WhisperModel
    return WhisperModel("tiny", device="cpu", compute_type="int8")

def transcribe_video(path, language):
    try:
        audio_path = Path(str(path) + "_audio.wav")
        subprocess.run(["ffmpeg","-y","-i",str(path),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(audio_path)], capture_output=True)
        if not audio_path.exists() or audio_path.stat().st_size < 1000:
            return []
        model = load_whisper()
        opts = {"vad_filter": True, "beam_size": 1, "temperature": 0.0}
        if language == "English (Translate)": opts["task"]="translate"
        elif language in LANGUAGE_CODES: opts["language"]=LANGUAGE_CODES[language]
        segments,_ = model.transcribe(str(audio_path), **opts)
        out=[]
        for s in segments:
            txt = s.text.strip()
            if txt and getattr(s,"no_speech_prob",0) < 0.85:
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
SAFE_FONTS = {"Noto Sans":"Noto Sans","Arial":"DejaVu Sans","DejaVu Sans":"DejaVu Sans","Liberation Sans":"Liberation Sans","Montserrat":"DejaVu Sans","Roboto":"DejaVu Sans","Poppins":"DejaVu Sans","Impact":"DejaVu Sans","Georgia":"DejaVu Serif"}

def write_subtitles(f, segments, cs, ce, cfg):
    align={"Bottom":2,"Middle":5,"Top":8}[cfg["position"]]
    bold=-1 if cfg["bold"] else 0
    border=3 if cfg["background"] else 1
    outline=0 if cfg["background"] else cfg["outline"]
    font=SAFE_FONTS.get(cfg["font"],"DejaVu Sans")
    rows=["[Script Info]","ScriptType: v4.00+","PlayResX: 1080","PlayResY: 1920","","[V4+ Styles]","Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",f"Style: Default,{font},{cfg['font_size']},{ass_color(cfg['text_color'])},&H000000FF&,{ass_color(cfg['outline_color'])},{ass_color(cfg['background_color'])},{bold},0,0,0,100,100,0,0,{border},{outline},{cfg['shadow']},{align},60,60,90,1","","[Events]","Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
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
    args=["ffmpeg","-y","-ss",str(start),"-i",str(source)]
    if music: args+=["-stream_loop","-1","-i",str(music)]
    filters=["scale=1080:1920:force_original_aspect_ratio=increase","crop=1080:1920","setsar=1","fps=30"]
    sub_file=output.with_suffix(".ass")
    if cfg["subtitles"] and segments:
        write_subtitles(sub_file,segments,start,start+length,cfg)
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

st.subheader("📁 Video Source")
source_type=st.radio("Choose source",["Google Drive","Upload video","YouTube"],horizontal=True)
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
    st.markdown('<div class="turbo-box">✅ <b>TURBO ON</b> - Download: MAX Speed | Render: ULTRAFAST | AI: Tiny Fast Model</div>', unsafe_allow_html=True)
else:
    st.info("🐢 TURBO OFF - Normal Mode")

with st.expander("⚙️ EDIT SETTINGS - Click To Open", expanded=True):
    c1,c2,c3 = st.columns(3)
    with c1:
        clip_count=st.slider("Maximum clips",1,30,3)
        clip_length=st.slider("Clip duration (seconds)",10,90,30)
        subtitles=st.toggle("Automatic subtitles",value=True)
        language=st.selectbox("Subtitle language",["English (Translate)","Auto Detect","Hindi","Telugu","Tamil","Kannada","Malayalam","Bengali","Marathi","Gujarati","Punjabi","Urdu"],index=3)
    with c2:
        font=st.selectbox("Font family",["Noto Sans","Arial","DejaVu Sans","Liberation Sans","Montserrat","Roboto","Poppins","Impact","Georgia"])
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
    with c4: source_volume=st.slider("Original audio volume",0.0,2.0,1.0)
    with c5: music_volume=st.slider("Background music volume",0.0,2.0,0.25)
    with c6: quality=st.selectbox("Video quality",["Fast","Balanced","High"],index=1)

cfg={"subtitles":subtitles,"font":font,"font_size":font_size,"text_color":text_color,"outline_color":outline_color,"outline":outline,"position":position,"bold":bold,"uppercase":uppercase,"background":background,"background_color":background_color,"shadow":shadow,"source_volume":source_volume,"music_volume":music_volume,"preset":{"Fast":"ultrafast","Balanced":"veryfast","High":"fast"}[quality],"crf":{"Fast":27,"Balanced":23,"High":19}[quality]}
if turbo:
    cfg["preset"]="ultrafast"; cfg["crf"]=28

st.subheader("🚀 Generate Your Clips")
if st.button("GENERATE CLIPS",type="primary",use_container_width=True):
    if source_type=="Upload video" and video_upload is None:
        st.error("Please upload a video."); st.stop()
    if source_type!="Upload video" and not video_url.strip().startswith(("https://","http://")):
        st.error("Please enter a valid video link."); st.stop()
    if not check_ffmpeg():
        st.error("FFmpeg missing."); st.stop()
    work=Path(tempfile.mkdtemp(prefix="clipshort_"))
    try:
        with st.status("Processing your video...",expanded=True) as status:
            if source_type=="Google Drive":
                prog = st.progress(0); txt = st.empty(); txt.text("⚡ Connecting to Google Drive at MAX Speed...")
                source=download_drive(video_url,work,prog,txt)
            elif source_type=="YouTube":
                st.write("Downloading YouTube...")
                source=download_youtube(video_url,work)
            else:
                source=work/("uploaded_video"+Path(video_upload.name).suffix.lower())
                with source.open("wb") as f: shutil.copyfileobj(video_upload,f,length=8*1024*1024)
            music=None
            if music_upload is not None:
                music=work/("background_music"+Path(music_upload.name).suffix.lower())
                with music.open("wb") as f: shutil.copyfileobj(music_upload,f,length=1024*1024)
            total=get_duration(source)
            if total<=0: st.error("Video duration is 0."); st.stop()
            st.write(f"Video length: {total:.1f} sec")
            if cfg["subtitles"]:
                st.write(f"Transcribing in {language}... Please wait 1-2 min")
                segments=transcribe_video(source,language)
                if not segments:
                    st.warning("No speech found / Subtitles skipped - Making clips without subtitles")
                    cfg["subtitles"]=False
                else: st.write(f"Found {len(segments)} subtitle lines.")
            else: segments=[]
            if segments:
                starts=choose_starts(segments,total,clip_length,clip_count)
            else:
                starts=[i*clip_length for i in range(max(1, min(clip_count, int(total//clip_length))))]
                if not starts: starts=[0.0]
            st.write(f"Making {len(starts)} clips...")
            outs=[]
            for i,s in enumerate(starts):
                out=work/f"clip_{i+1}.mp4"
                st.write(f"Rendering clip {i+1}/{len(starts)}...")
                render_clip(source,out,s,clip_length,segments,cfg,music)
                if out.exists(): outs.append(out)
            status.update(label="Done!",state="complete")
        st.success(f"✅ {len(outs)} Clips Ready!")
        for i,o in enumerate(outs):
            st.subheader(f"Clip {i+1}")
            st.video(str(o))
            with open(o,"rb") as f: st.download_button(f"⬇️ Download Clip {i+1}",data=f.read(),file_name=f"clip_{i+1}.mp4",mime="video/mp4",key=f"dl_{i}")
    except Exception as e:
        st.error(f"Error: {e}")
