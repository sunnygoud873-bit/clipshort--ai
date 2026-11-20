import os
os.environ["OMP_NUM_THREADS"]="1"
os.environ["TOKENIZERS_PARALLELISM"]="false"
import streamlit as st, subprocess, tempfile, shutil, re, gc, wave, requests
from pathlib import Path
from urllib.parse import urlparse, parse_qs

st.set_page_config(page_title="CLIPSHORT AI", page_icon="🎬", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
.block-container{max-width:1280px;padding-top:1rem;padding-bottom:2rem;padding-left:1rem;padding-right:1rem}
.stButton>button{width:100%;border-radius:10px;min-height:44px;font-size:15px}
.stDownloadButton>button{width:100%;border-radius:10px;min-height:44px}
video{width:100%!important;border-radius:12px}
@media (max-width:768px){
  .block-container{padding-left:0.6rem;padding-right:0.6rem}
  [data-testid="column"]{width:100%!important;flex:1 1 100%!important;min-width:100%!important}
  div[data-testid="stHorizontalBlock"]{flex-wrap:wrap}
}
</style>
""", unsafe_allow_html=True)
st.markdown("<h1>🎬 CLIPSHORT AI</h1><p>Clipper + YouTube Downloader + Instagram Downloader</p>", unsafe_allow_html=True)

# FIX 1: active_tab init MUST match radio value
if "preview_done" not in st.session_state: st.session_state.preview_done=False
if "preview_bytes" not in st.session_state: st.session_state.preview_bytes=None
if "active_tab" not in st.session_state: st.session_state.active_tab="🎬 CLIPPER"

def run_cmd(a):
    r=subprocess.run(a,capture_output=True,text=True)
    if r.returncode!=0: raise RuntimeError((r.stderr or r.stdout)[-1200:])
    return r.stdout.strip()
def check_ffmpeg(): return shutil.which("ffmpeg") is not None
def get_duration(p):
    try: return float(run_cmd(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(p)]))
    except: return 0.0
def has_audio(p):
    r=subprocess.run(["ffprobe","-v","error","-select_streams","a:0","-show_entries","stream=codec_type","-of","csv=p=0",str(p)],capture_output=True,text=True)
    return bool(r.stdout.strip())

# FIX 2: Correct mime for all file types
def get_mime(p):
    s=str(p).lower()
    if s.endswith(".mp3"): return "audio/mp3"
    if s.endswith(".webm"): return "video/webm"
    if s.endswith(".mkv"): return "video/x-matroska"
    if s.endswith(".jpg") or s.endswith(".jpeg"): return "image/jpeg"
    if s.endswith(".png"): return "image/png"
    if s.endswith(".webp"): return "image/webp"
    return "video/mp4"

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

COBALT_INSTANCES=["https://co.wuk.sh/","https://cobalt-backend.canine.tools/","https://cobalt-api.kavin.rocks/"]
def _dl_url(vurl,folder,name):
    target=folder/name
    with requests.get(vurl,stream=True,timeout=180,headers={"User-Agent":"Mozilla/5.0"}) as dl:
        dl.raise_for_status()
        with open(target,"wb") as f:
            for c in dl.iter_content(chunk_size=1024*1024*2):
                if c: f.write(c)
    if target.exists() and target.stat().st_size>10000: return target
    raise RuntimeError("Empty file from server")
def download_via_cobalt(url,folder,filename="cobalt_video.mp4"):
    last_err=""
    for base in COBALT_INSTANCES:
        try:
            r=requests.post(base,json={"url":url.strip(),"videoQuality":"720","filenameStyle":"basic"},headers={"Accept":"application/json","Content-Type":"application/json"},timeout=30)
            if r.status_code!=200:
                last_err=f"{base} status {r.status_code}"; continue
            j=r.json(); vurl=j.get("url")
            if not vurl:
                last_err=f"{base} no url"; continue
            return _dl_url(vurl,folder,filename)
        except Exception as e:
            last_err=str(e); continue
    # FIX 3: Show real Cobalt error
    raise RuntimeError(f"Cobalt failed: {last_err} - Try again after 2 mins")
def get_video_id(url):
    u=url.strip()
    if "youtu.be/" in u: return u.split("youtu.be/")[-1].split("?")[0].split("&")[0]
    q=parse_qs(urlparse(u).query)
    if "v" in q: return q["v"][0]
    m=re.search(r"/shorts/([A-Za-z0-9_-]+)",u)
    if m: return m.group(1)
    m=re.search(r"/live/([A-Za-z0-9_-]+)",u)
    if m: return m.group(1)
    return None
def download_youtube(url,folder):
    u=url.strip(); vid=get_video_id(u)
    if not vid: raise RuntimeError("Invalid YouTube link. Use watch?v= / youtu.be / shorts")
    try: return download_via_cobalt(u,folder,"youtube_video.mp4")
    except Exception as e: print("YT Cobalt fail:",e)
    for host in ["https://pipedapi.kavin.rocks","https://pipedapi-libre.kavin.rocks","https://pipedapi.adminforge.de","https://pipedapi.leptons.xyz"]:
        try:
            r=requests.get(f"{host}/streams/{vid}",timeout=15)
            if r.status_code!=200: continue
            d=r.json(); cand=[s for s in d.get("videoStreams",[]) if "mp4" in s.get("mimeType","")]
            if not cand: cand=d.get("videoStreams",[])
            if not cand: continue
            cand=sorted(cand,key=lambda x: int(str(x.get("quality","720")).replace("p","") or 720))
            return _dl_url(cand[0]["url"],folder,"youtube_video.mp4")
        except: continue
    try:
        import yt_dlp
        opts={"format":"18/best[ext=mp4]/best","outtmpl":str(folder/"youtube_video.%(ext)s"),"noplaylist":True,"quiet":True,"no_warnings":True,"retries":3,"socket_timeout":30,"extractor_args":{"youtube":{"player_client":["mweb","ios","tv"]}}}
        with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([u])
        files=[f for f in folder.glob("youtube_video.*") if f.suffix.lower() in [".mp4",".webm",".mkv"]]
        if files and files[0].stat().st_size>10000: return files[0]
    except Exception as e: print("yt-dlp fail",e)
    raise RuntimeError("YouTube failed on all servers. Try again after 2 mins or use Drive/Upload.")
def download_instagram(url,folder):
    u=url.strip()
    if "instagram.com" not in u and "instagr.am" not in u: raise RuntimeError("Invalid Instagram link. Use instagram.com/reel/ or /p/ link")
    try: return download_via_cobalt(u,folder,"insta_video.mp4")
    except Exception as e: print("Insta cobalt fail",e)
    try:
        import yt_dlp
        opts={"format":"best[ext=mp4]/best","outtmpl":str(folder/"insta_video.%(ext)s"),"noplaylist":True,"quiet":True,"no_warnings":True,"retries":3,"socket_timeout":30}
        with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([u])
        files=[f for f in folder.glob("insta_video.*") if f.suffix.lower() in [".mp4",".webm",".mkv",".jpg",".png"]]
        if files and files[0].stat().st_size>10000: return files[0]
    except Exception as e: print("Insta yt-dlp fail",e)
    raise RuntimeError("Instagram failed. Reel must be PUBLIC. Private videos will not download.")

def get_highlight_scores(video_path,total):
    try:
        import numpy as np
        ap=Path(str(video_path)+"_audio.wav")
        subprocess.run(["ffmpeg","-y","-i",str(video_path),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(ap)],capture_output=True)
        if not ap.exists() or ap.stat().st_size<1000: return None
        with wave.open(str(ap),"rb") as wf:
            n=wf.getnframes(); rate=wf.getframerate(); data=wf.readframes(n)
        audio=np.frombuffer(data,dtype=np.int16).astype(float)/32768.0
        if len(audio)==0: return None
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
    except Exception as e: print(e); return None
def choose_highlight_starts(scores,total,length,count,ts,te):
    if scores is None: return None
    cands=[]; start=ts; step=2.0
    while start+length<=te:
        si=int(start); ei=int(min(start+length,len(scores)))
        sc=sum(scores[si:ei]) if ei>si else 0
        if ei>si: sc+=max(scores[si:ei])*2.0
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
    if stype=="TikTok / Insta / X / FB (Cobalt)": return download_via_cobalt(url,work)
    if up is None: raise RuntimeError("Upload file missing")
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

main_mode = st.radio("Select Section", ["🎬 CLIPPER", "⬇️ DOWNLOADER"], horizontal=True, key="main_mode_radio_v3")
if main_mode != st.session_state.active_tab:
    st.session_state.preview_done=False
    st.session_state.preview_bytes=None
    st.session_state.active_tab=main_mode

if main_mode == "🎬 CLIPPER":
    st.subheader("🎬 Clipper - Highlight + Normal")
    left, right = st.columns([1.5, 1], gap="medium")
    with right:
        st.subheader("⚙️ Editing Settings")
        clip_mode=st.radio("How to clip?",["🔥 Highlight Moments - Best Parts Only (UNLIMITED)","📐 Normal Clipping - Evenly Spaced Clips"],index=1, key="clip_mode_v3")
        clip_count=st.slider("Maximum clips",1,30,3, key="clip_count_v3"); clip_length=st.slider("Clip duration (seconds)",5,60,30, key="clip_len_v3")
        source_volume=st.slider("Original audio volume",0.0,2.0,1.5, key="clip_sv_v3"); music_volume=st.slider("Music volume",0.0,2.0,0.25, key="clip_mv_v3")
        use_trim=st.toggle("Enable Trim",value=False, key="clip_trim_v3"); trim_start=0.0; trim_end=None
        if use_trim:
            trim_start=st.number_input("Start (sec)",min_value=0.0,value=0.0,step=1.0, key="clip_ts_v3")
            trim_end=st.number_input("End (sec)",min_value=1.0,value=60.0,step=1.0, key="clip_te_v3")
            if trim_end<=trim_start: st.error("End must be > Start")
        effect=st.selectbox("Effect",["None - Original","Cinematic - Dark + Warm","Vivid - Color Pop","Black & White","Vintage - Old Film","Warm - Golden","Cool - Blue"], key="clip_eff_v3")
        brightness=st.slider("Brightness",-0.3,0.3,0.0,step=0.01, key="clip_br_v3"); speed=st.selectbox("Speed",[0.5,0.75,1.0,1.25,1.5,2.0],index=2, key="clip_sp_v3")
        contrast=st.slider("Contrast",0.5,2.0,1.0,step=0.05, key="clip_ct_v3"); sharpen=st.slider("Sharpen",0.0,3.0,0.0,step=0.5, key="clip_sh_v3")
        saturation=st.slider("Saturation",0.0,2.5,1.0,step=0.05, key="clip_sat_v3"); blur=st.slider("Blur",0.0,3.0,0.0,step=0.5, key="clip_bl_v3")
        fade_in=st.toggle("Fade In",value=False, key="clip_fi_v3"); fade_out=st.toggle("Fade Out",value=False, key="clip_fo_v3")
        ratio_label=st.selectbox("Aspect Ratio",list(RATIOS.keys()),index=0, key="clip_ratio_v3")
        res_label=st.selectbox("Resolution",list(RESOLUTIONS.keys()),index=0, key="clip_res_v3")
        out_w,out_h=get_output_size(ratio_label,res_label); st.info(f"{ratio_label} | {res_label} | {out_w}x{out_h}")
        cfg={"source_volume":source_volume,"music_volume":music_volume,"out_w":out_w,"out_h":out_h,"effect":effect,"brightness":brightness,"contrast":contrast,"saturation":saturation,"sharpen":sharpen,"blur":blur,"speed":float(speed),"fade_in":fade_in,"fade_out":fade_out}
    with left:
        source_type=st.radio("Choose source",["YouTube","TikTok / Insta / X / FB (Cobalt)","Google Drive","Upload video"],horizontal=True,index=0, key="clip_src_v3")
        video_url=""; video_upload=None
        if source_type=="Google Drive": video_url=st.text_input("Drive link",placeholder="Paste Drive link", key="clip_drive_v3")
        elif source_type=="Upload video": video_upload=st.file_uploader("Upload video",type=["mp4","mov","mkv","webm","avi","m4v"], key="clip_up_v3")
        elif source_type=="TikTok / Insta / X / FB (Cobalt)": video_url=st.text_input("Link",placeholder="https://www.instagram.com/reel/...", key="clip_cobalt_v3")
        else: video_url=st.text_input("YouTube URL",placeholder="https://www.youtube.com/watch?v=...", key="clip_yt_v3")
        music_upload=st.file_uploader("🎵 Background Music (Optional)",type=["mp3","wav","m4a","aac","ogg","flac"], key="clip_music_v3")
        st.subheader("👀 Step 1: Preview")
        if st.button("GENERATE PREVIEW - 5 Sec",use_container_width=True, key="clip_prev_v3"):
            if source_type=="Upload video" and video_upload is None: st.error("Please upload video first"); st.stop()
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
        if st.button("GENERATE CLIPS",type="primary",use_container_width=True,disabled=not st.session_state.preview_done, key="clip_gen_v3"):
            work=Path(tempfile.mkdtemp(prefix="clipshort_"))
            try:
                st.write("Processing...")
                src=get_source(work,source_type,video_url,video_upload); mus=get_music(work,music_upload); total=get_duration(src)
                if total<=0: st.error("Could not read video duration"); st.stop()
                st.write(f"Video: {round(total,1)} sec - No limit")
                t_start=trim_start if use_trim else 0.0; t_end=min(trim_end,total) if use_trim and trim_end else total
                if t_end<=t_start: st.error("Trim End must be > Start"); st.stop()
                if "Highlight" in clip_mode:
                    scores=get_highlight_scores(src,total)
                    if scores is None:
                        st.warning("No audio found - Using Normal clipping")
                        starts=choose_normal_starts(total,clip_length,clip_count,t_start,t_end)
                    else:
                        starts=choose_highlight_starts(scores,total,clip_length,clip_count,t_start,t_end)
                        for idx,s in enumerate(starts): st.write(f"Highlight {idx+1}: {int(s//60)}:{int(s%60):02d}")
                else:
                    starts=choose_normal_starts(total,clip_length,clip_count,t_start,t_end)
                outs=[]
                for i,s in enumerate(starts):
                    out=work/f"clip_{i+1}.mp4"; st.write(f"Rendering {i+1}/{len(starts)} - {int(s//60)}:{int(s%60):02d}"); render_clip(src,out,s,clip_length,cfg,mus)
                    if out.exists() and out.stat().st_size>10000: outs.append(out)
                if not outs: st.error("No clips rendered. Try different video."); st.stop()
                st.success(f"Done - {len(outs)} Clips Ready!")
                for i,o in enumerate(outs):
                    st.subheader(f"Clip {i+1} - {out_w}x{out_h}"); st.video(str(o))
                    with open(o,"rb") as f: st.download_button(f"⬇️ Download Clip {i+1}",f,file_name=f"clip_{i+1}.mp4",mime="video/mp4",key=f"clip_dl_v3_{i}")
except 
