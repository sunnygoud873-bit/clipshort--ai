import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import streamlit as st, subprocess, tempfile, shutil, re, gc, wave, requests
from pathlib import Path
from urllib.parse import urlparse, parse_qs

st.set_page_config(page_title="CLIPSHORT AI", page_icon="🎬", layout="wide")
st.markdown("<h1>🎬 CLIPSHORT AI</h1><p>Highlight + Normal Clipping | YouTube / Drive / Upload | Fast</p>", unsafe_allow_html=True)
if "preview_done" not in st.session_state: st.session_state.preview_done=False
if "preview_bytes" not in st.session_state: st.session_state.preview_bytes=None

# ---------- UTILS ----------
def run_cmd(a):
    r=subprocess.run(a,capture_output=True,text=True)
    if r.returncode!=0: raise RuntimeError((r.stderr or r.stdout)[-1200:])
    return r.stdout.strip()
def check_ffmpeg(): return shutil.which("ffmpeg") is not None
def get_duration(p): return float(run_cmd(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(p)]))
def has_audio(p):
    r=subprocess.run(["ffprobe","-v","error","-select_streams","a:0","-show_entries","stream=codec_type","-of","csv=p=0",str(p)],capture_output=True,text=True)
    return bool(r.stdout.strip())

# ---------- DOWNLOAD ----------
def get_drive_id(url):
    p=urlparse(url.strip()); m=re.search(r"/file/d/([A-Za-z0-9_-]+)",p.path)
    if m: return m.group(1)
    q=parse_qs(p.query)
    if q.get("id"): return q["id"][0]
    raise ValueError("Invalid Drive link")
def download_drive(url,folder):
    fid=get_drive_id(url); target=folder/"drive_video.mp4"
    s=requests.Session(); r=s.get("https://drive.google.com/uc?export=download&id="+fid+"&confirm=t",stream=True,timeout=120)
    with open(target,"wb") as f:
        for c in r.iter_content(chunk_size=1024*1024*2):
            if c: f.write(c)
    if not target.exists() or target.stat().st_size<10000: raise RuntimeError("Drive failed. Set Anyone with link -> Viewer")
    return target

def get_video_id(url):
    if "youtu.be/" in url: return url.split("youtu.be/")[-1].split("?")[0].split("&")[0]
    q=parse_qs(urlparse(url).query)
    if "v" in q: return q["v"][0]
    m=re.search(r"/shorts/([A-Za-z0-9_-]+)",url)
    if m: return m.group(1)
    m=re.search(r"/live/([A-Za-z0-9_-]+)",url)
    if m: return m.group(1)
    return None

def _dl_file(video_url,folder):
    target=folder/"youtube_video.mp4"
    with requests.get(video_url,stream=True,timeout=180,headers={"User-Agent":"Mozilla/5.0"}) as dl:
        dl.raise_for_status()
        with open(target,"wb") as f:
            for c in dl.iter_content(chunk_size=1024*1024*2):
                if c: f.write(c)
    if target.exists() and target.stat().st_size>10000: return target
    raise RuntimeError("Empty file")

def download_youtube(url,folder):
    vid=get_video_id(url.strip())
    if not vid: raise RuntimeError("Invalid YouTube link. Use watch?v= / youtu.be / shorts link")
    # 1. PIPED - Best for Streamlit, no 403
    for host in ["https://pipedapi.kavin.rocks","https://pipedapi-libre.kavin.rocks","https://pipedapi.adminforge.de"]:
        try:
            r=requests.get(f"{host}/streams/{vid}",timeout=20)
            if r.status_code!=200: continue
            d=r.json(); cand=[s for s in d.get("videoStreams",[]) if "mp4" in s.get("mimeType","")]
            if not cand: cand=d.get("videoStreams",[])
            if not cand: continue
            cand=sorted(cand,key=lambda x: abs(int(str(x.get("quality","720")).replace("p","") or 720)-720))
            return _dl_file(cand[0]["url"],folder)
        except Exception as e: print("Piped fail",host,e); continue
    # 2. INVIDIOUS - Backup
    for host in ["https://vid.puffyan.us","https://invidious.privacyredirect.com","https://iv.datura.network"]:
        try:
            r=requests.get(f"{host}/api/v1/videos/{vid}",timeout=20)
            if r.status_code!=200: continue
            d=r.json(); stms=d.get("formatStreams",[])
            if not stms: continue
            stms=sorted(stms,key=lambda x: 0 if x.get("itag")==22 else 1 if x.get("itag")==18 else 2)
            return _dl_file(stms[0]["url"],folder)
        except Exception as e: print("Invidious fail",host,e); continue
    # 3. yt-dlp - Last try, pre-merged 18/22, mweb client
    try:
        import yt_dlp
        opts={"format":"18/22/best[ext=mp4]/best","outtmpl":str(folder/"youtube_video.%(ext)s"),"noplaylist":True,"quiet":True,"no_warnings":True,"retries":2,"socket_timeout":30,"extractor_args":{"youtube":{"player_client":["mweb","ios","tv"]}}}
        with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([url])
        files=[f for f in folder.glob("youtube_video.*") if f.suffix.lower() in [".mp4",".webm",".mkv"]]
        if files and files[0].stat().st_size>10000: return files[0]
    except Exception as e: print("yt-dlp fail",e)
    raise RuntimeError("YouTube download failed. Try again in 1 min or use Drive/Upload.")

# ---------- HIGHLIGHTS - UNLIMITED, NO 10 MIN LIMIT ----------
def get_highlight_scores(video_path,total):
    try:
        import numpy as np
        ap=Path(str(video_path)+"_audio.wav")
        subprocess.run(["ffmpeg","-y","-i",str(video_path),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(ap)],capture_output=True)
        if not ap.exists() or ap.stat().st_size<1000: return None
        with wave.open(str(ap),"rb") as wf:
            n=wf.getnframes(); rate=wf.getframerate(); data=wf.readframes(n)
        audio=np.frombuffer(data,dtype=np.int16).astype(float)/32768.0
        scores=[]
        for i in range(int(total)):
            s=i*rate; e=min((i+1)*rate,len(audio))
            if e<=s: scores.append(0.0); continue
            ch=audio[s:e]; rms=float(np.sqrt(np.mean(ch**2))) if len(ch)>0 else 0; peak=float(np.max(np.abs(ch))) if len(ch)>0 else 0
            scores.append(rms*0.7+peak*0.3)
        sm=[]
        for i in range(len(scores)):
            v=scores[max(0,i-1):min(len(scores),i+2)]; sm.append(sum(v)/len(v))
        try: ap.unlink()
        except: pass
        return sm
    except Exception as e: print("Highlight fail",e); return None

def choose_highlight_starts(scores,total,length,count,ts,te):
    if scores is None: return None
    cands=[]; start=ts; step=2.0
    while start+length<=te:
        s_idx=int(start); e_idx=int(min(start+length,len(scores)))
        sc=sum(scores[s_idx:e_idx]) if e_idx>s_idx else 0
        if e_idx>s_idx: sc+=max(scores[s_idx:e_idx])*2.0
        cands.append((sc,start)); start+=step
    cands.sort(key=lambda x:x[0],reverse=True); sel=[]
    for _,s in cands:
        if all(abs(s-p)>=length*0.65 for p in sel): sel.append(s)
        if len(sel)>=count: break
    return sorted(sel) if sel else [ts]

def choose_normal_starts(total,length,count,ts,te):
    avail=te-ts
    if avail<=length: return [ts]
    if avail>=count*length: return [ts+i*length for i in range(count)]
    if count==1: return [ts+avail/2-length/2]
    step=(avail-length)/(count-1)
    return [ts+i*step for i in range(count)]

# ---------- RENDER ----------
RATIOS={"9:16 - Shorts / Reels":(1080,1920),"16:9 - YouTube":(1920,1080),"1:1 - Post":(1080,1080),"4:5 - Portrait":(1080,1350)}
RESOLUTIONS={"480p - Fast":480,"720p - HD":720,"1080p - Full HD":1080}
def get_output_size(rl,resl):
    bw,bh=RATIOS[rl]; t=RESOLUTIONS[resl]
    if bw<=bh: w=t; h=int(bh*(t/bw))
    else: h=t; w=int(bw*(t/bh))
    return w-(w%2), h-(h%2)

def build_effect_filter(cfg,length):
    f=[]; eff=cfg["effect"]; b=cfg["brightness"]; c=cfg["contrast"]; s=cfg["saturation"]
    if eff=="Cinematic - Dark + Warm": b-=0.05; c+=0.15; s-=0.10; f.append("curves=r='0/0 0.5/0.45 1/1':g='0/0 0.5/0.5 1/1':b='0/0 0.5/0.55 1/0.95'")
    elif eff=="Vivid - Color Pop": b+=0.05; c+=0.20; s+=0.40
    elif eff=="Black & White": s=0.0; c+=0.10
    elif eff=="Vintage - Old Film": b+=0.05; c-=0.05; s-=0.20; f.append("noise=alls=6:allf=t")
    elif eff=="Warm - Golden": f.append("colorbalance=rs=0.15:gs=0.05:bs=-0.15")
    elif eff=="Cool - Blue": f.append("colorbalance=rs=-0.10:gs=0.0:bs=0.15")
    f.append(f"eq=brightness={b:.2f}:contrast={c:.2f}:saturation={s:.2f}")
    if cfg["sharpen"]>0: f.append(f"unsharp=5:5:{cfg['sharpen']:.1f}:5:5:0.0")
    if cfg["blur"]>0: f.append(f"gblur=sigma={cfg['blur']:.1f}")
    if cfg["fade_in"]: f.append("fade=t=in:st=0:d=0.8")
    if cfg["fade_out"]: f.append(f"fade=t=out:st={max(0,length-0.8):.1f}:d=0.8")
    return f

def render_clip(source,output,start,length,cfg,music):
    args=["ffmpeg","-y","-threads","1","-ss",str(start),"-i",str(source)]
    if music: args+=["-stream_loop","-1","-i",str(music)]
    fl=[f"scale={cfg['out_w']}:{cfg['out_h']}:force_original_aspect_ratio=increase",f"crop={cfg['out_w']}:{cfg['out_h']}","setsar=1"]
    if cfg["speed"]!=1.0: fl.append(f"setpts={1.0/cfg['speed']:.3f}*PTS")
    fl+=build_effect_filter(cfg,length); fl.append("fps=30")
    args+=["-t",str(length),"-vf",",".join(fl),"-c:v","libx264","-preset","ultrafast","-crf","28","-threads","1","-pix_fmt","yuv420p"]
    sa=has_audio(source); at=f"atempo={cfg['speed']:.2f}," if cfg["speed"]!=1.0 else ""
    if music and sa: args+=["-filter_complex",f"[0:a]{at}volume={cfg['source_volume']}[a0];[1:a]volume={cfg['music_volume']}[a1];[a0][a1]amix=inputs=2:duration=first[aout]","-map","0:v:0","-map","[aout]","-c:a","aac"]
    elif music: args+=["-map","0:v:0","-map","1:a:0","-af",f"volume={cfg['music_volume']}","-c:a","aac"]
    elif sa: args+=["-af",at+f"volume={cfg['source_volume']}","-c:a","aac"]
    else: args+=["-an"]
    args+=["-movflags","+faststart",str(output)]; run_cmd(args); gc.collect()

def get_source(work,stype,url,up):
    if stype=="Google Drive": return download_drive(url,work)
    if stype=="YouTube": return download_youtube(url,work)
    suf=Path(up.name).suffix.lower()
    if suf not in [".mp4",".mov",".mkv",".webm",".avi",".m4v"]: suf=".mp4"
    src=work/("uploaded_video"+suf)
    with src.open("wb") as f: shutil.copyfileobj(up,f,length=8*1024*1024)
    return src
def get_music(work,up):
    if up is None: return None
    suf=Path(up.name).suffix.lower()
    if suf not in [".mp3",".wav",".m4a",".aac",".ogg",".flac"]: suf=".mp3"
    m=work/("bg_music"+suf)
    with m.open("wb") as f: shutil.copyfileobj(up,f,length=1024*1024)
    return m

# ---------- UI ----------
st.subheader("📁 Video Source")
source_type=st.radio("Choose source",["YouTube","Google Drive","Upload video"],horizontal=True,index=0)
video_url=""; video_upload=None
if source_type=="Google Drive": video_url=st.text_input("Drive link",placeholder="Paste Drive link"); st.caption("Drive: Anyone with link -> Viewer")
elif source_type=="Upload video": video_upload=st.file_uploader("Upload video",type=["mp4","mov","mkv","webm","avi","m4v"])
else: video_url=st.text_input("YouTube URL",placeholder="https://www.youtube.com/watch?v=..."); st.caption("YouTube via Piped - No 403, No Cobalt needed")

st.subheader("🎵 Background Music (Optional)")
music_upload=st.file_uploader("Upload music",type=["mp3","wav","m4a","aac","ogg","flac"])
st.subheader("🎯 Clipping Mode")
clip_mode=st.radio("How to clip?",["🔥 Highlight Moments - Best Parts Only (UNLIMITED - Any Length)","📐 Normal Clipping - Evenly Spaced Clips"],index=1)
if "Highlight" in clip_mode: st.info("🔥 Highlight: Loud moments = Best moments. No 10 min limit - 1 min or 3 hours, any length works.")
else: st.info("📐 Normal: Cuts evenly, no overlap if possible.")
c1,c2=st.columns(2)
with c1: clip_count=st.slider("Maximum clips",1,30,3); clip_length=st.slider("Clip duration (seconds)",5,60,30)
with c2: quality=st.selectbox("Quality",["Fast - Low CPU","Balanced","High"],index=0); source_volume=st.slider("Original audio volume",0.0,2.0,1.5); music_volume=st.slider("Music volume",0.0,2.0,0.25)
if clip_count>10: st.warning(f"{clip_count} clips = more time. 3-5 best for daily use.")
st.subheader("✂️ Trim")
use_trim=st.toggle("Enable Trim",value=False); trim_start=0.0; trim_end=9999.0
if use_trim:
    t1,t2=st.columns(2)
    with t1: trim_start=st.number_input("Start (sec)",min_value=0.0,value=0.0,step=1.0)
    with t2: trim_end=st.number_input("End (sec)",min_value=1.0,value=60.0,step=1.0)
    if trim_end<=trim_start: st.error("End must be > Start")
else: st.caption("Trim OFF - Full video used")
st.subheader("🎨 Effects")
effect=st.selectbox("Effect",["None - Original","Cinematic - Dark + Warm","Vivid - Color Pop","Black & White","Vintage - Old Film","Warm - Golden","Cool - Blue"])
e1,e2,e3=st.columns(3)
with e1: brightness=st.slider("Brightness",-0.3,0.3,0.0,step=0.01); speed=st.selectbox("Speed",[0.5,0.75,1.0,1.25,1.5,2.0],index=2)
with e2: contrast=st.slider("Contrast",0.5,2.0,1.0,step=0.05); sharpen=st.slider("Sharpen",0.0,3.0,0.0,step=0.5)
with e3: saturation=st.slider("Saturation",0.0,2.5,1.0,step=0.05); blur=st.slider("Blur",0.0,3.0,0.0,step=0.5)
f1,f2=st.columns(2)
with f1: fade_in=st.toggle("Fade In",value=False)
with f2: fade_out=st.toggle("Fade Out",value=False)
st.markdown("### 📐 Ratio & Resolution")
r1,r2=st.columns(2)
with r1: ratio_label=st.selectbox("Aspect Ratio",list(RATIOS.keys()),index=0)
with r2: res_label=st.selectbox("Resolution",list(RESOLUTIONS.keys()),index=0)
out_w,out_h=get_output_size(ratio_label,res_label); st.info(f"{ratio_label} | {res_label} | {out_w}x{out_h}")
cfg={"source_volume":source_volume,"music_volume":music_volume,"out_w":out_w,"out_h":out_h,"effect":effect,"brightness":brightness,"contrast":contrast,"saturation":saturation,"sharpen":sharpen,"blur":blur,"speed":float(speed),"fade_in":fade_in,"fade_out":fade_out}

st.subheader("👀 Step 1: Preview")
if st.button("GENERATE PREVIEW - 5 Sec",use_container_width=True):
    if source_type=="Upload video" and video_upload is None: st.error("Upload video first"); st.stop()
    if source_type!="Upload video" and not video_url.strip().startswith(("https://","http://")): st.error("Enter valid link"); st.stop()
    if not check_ffmpeg(): st.error("FFmpeg missing"); st.stop()
    work=Path(tempfile.mkdtemp(prefix="preview_"))
    try:
        st.write("Making Preview...")
        src=get_source(work,source_type,video_url,video_upload); mus=get_music(work,music_upload)
        p_start=trim_start if use_trim else 0.0; p_out=work/"preview.mp4"; render_clip(src,p_out,p_start,5,cfg,mus)
        with open(p_out,"rb") as f: st.session_state.preview_bytes=f.read()
        st.success("Preview Ready!"); st.video(st.session_state.preview_bytes); st.session_state.preview_done=True
    except Exception as e: st.error("Preview Error: "+str(e)); st.session_state.preview_done=False
if st.session_state.preview_bytes is not None: st.video(st.session_state.preview_bytes)
if st.session_state.preview_done: st.success("Preview Approved - Generate Now!")
else: st.warning("Generate Locked - Watch Preview First")

st.subheader("🚀 Step 2: Generate Clips")
if st.button("GENERATE CLIPS",type="primary",use_container_width=True,disabled=not st.session_state.preview_done):
    work=Path(tempfile.mkdtemp(prefix="clipshort_"))
    try:
        st.write("Processing...")
        src=get_source(work,source_type,video_url,video_upload); mus=get_music(work,music_upload); total=get_duration(src)
        st.write(f"Video: {round(total,1)} sec ({round(total/60,1)} min) - No limit")
        t_start=trim_start if use_trim else 0.0; t_end=min(trim_end,total) if use_trim else total
        if t_end<=t_start: st.error("Trim End must be > Start"); st.stop()
        if "Highlight" in clip_mode:
            st.write("Analyzing audio for highlights... (any length)")
            scores=get_highlight_scores(src,total)
            if scores is None: st.warning("No audio - Using Normal"); starts=choose_normal_starts(total,clip_length,clip_count,t_start,t_end)
            else:
                starts=choose_highlight_starts(scores,total,clip_length,clip_count,t_start,t_end)
                st.write(f"Found {len(starts)} highlights!")
                for idx,s in enumerate(starts): st.write(f"Highlight {idx+1}: {int(s//60)}:{int(s%60):02d}")
        else:
            starts=choose_normal_starts(total,clip_length,clip_count,t_start,t_end); st.write(f"Normal: {len(starts)} clips")
        outs=[]
        for i,s in enumerate(starts):
            out=work/f"clip_{i+1}.mp4"; st.write(f"Rendering {i+1}/{len(starts)} - {int(s//60)}:{int(s%60):02d}"); render_clip(src,out,s,clip_length,cfg,mus)
            if out.exists(): outs.append(out)
        st.success(f"Done - {len(outs)} Clips Ready!")
        for i,o in enumerate(outs):
            st.subheader(f"Clip {i+1} - {out_w}x{out_h}")
            st.video(str(o))
            with open(o,"rb") as f: st.download_button(f"⬇️ Download Clip {i+1}",f,file_name=f"clip_{i+1}.mp4",mime="video/mp4",key=f"dl_{i}")
    except Exception as e: st.error("Error: "+str(e))
