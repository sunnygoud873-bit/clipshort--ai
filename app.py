import os
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["OPENBLAS_NUM_THREADS"] = "4"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import streamlit as st, subprocess, tempfile, shutil, re, gc, wave, requests, io, zipfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# ===== FAST + UNLIMITED + RESPONSIVE =====
st.set_page_config(page_title="CLIPSHORT AI", page_icon="🎬", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
.block-container{max-width:100%!important;width:100%!important;padding-top:0.5rem!important;padding-bottom:2rem!important;padding-left:1rem!important;padding-right:1rem!important}
.main{max-width:100%!important}
h1{font-size:28px!important;text-align:center}
h2{font-size:20px!important}
h3{font-size:17px!important}
.stButton>button{width:100%!important;border-radius:12px!important;min-height:52px!important;font-size:16px!important;font-weight:700!important}
.stDownloadButton>button{width:100%!important;border-radius:12px!important;min-height:56px!important;font-size:16px!important;font-weight:800!important;background:#00c853!important;color:white!important;border:none!important;box-shadow:0 4px 12px rgba(0,200,83,0.4)!important}
.stDownloadButton>button:hover{background:#00a344!important}
video{width:100%!important;height:auto!important;border-radius:12px!important}
input, select, textarea{font-size:16px!important;min-height:44px!important}
.content-wrap{width:100%!important;max-width:1400px!important;margin:0 auto!important}
@media (max-width: 600px){
  .block-container{padding-left:0.6rem!important;padding-right:0.6rem!important}
  h1{font-size:24px!important}
}
@media (min-width: 1025px){ h1{font-size:34px!important} }
/* Sticky Download Bar - Always Visible */
.sticky-bar{position:sticky;top:0;z-index:999;background:#00c853;color:white;padding:12px 16px;border-radius:12px;text-align:center;font-weight:800;font-size:16px;box-shadow:0 4px 12px rgba(0,0,0,0.3);margin-bottom:12px}
.clip-card{background:#1a1a1a;border:1px solid #333;border-radius:14px;padding:14px;margin-bottom:16px}
.download-above{margin-bottom:10px!important}
</style>""", unsafe_allow_html=True)
st.markdown("<h1>🎬 CLIPSHORT AI</h1><p style='text-align:center'>Clipper + Instagram Downloader + MP3</p>", unsafe_allow_html=True)

# FIX: Store only file paths, NOT bytes - This fixes slow + glitch
for k,v in [("preview_done",False),("preview_bytes",None),("active_tab","CLIPPER"),("clip_paths",[]),("clip_names",[]),("zip_path","")]:
    if k not in st.session_state: st.session_state[k]=v

def run_cmd(cmd_list):
    r=subprocess.run(cmd_list,capture_output=True,text=True)
    if r.returncode!=0: raise RuntimeError((r.stderr or r.stdout)[-1200:])
    return r.stdout.strip()
def check_ffmpeg(): return shutil.which("ffmpeg") is not None
@st.cache_data(show_spinner=False)
def get_duration_cached(path_str):
    try: return float(run_cmd(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",path_str]))
    except: return 0.0
def get_duration(p): return get_duration_cached(str(p))
def has_audio(p):
    r=subprocess.run(["ffprobe","-v","error","-select_streams","a:0","-show_entries","stream=codec_type","-of","csv=p=0",str(p)],capture_output=True,text=True)
    return bool(r.stdout.strip())
def get_mime(p):
    s=str(p).lower()
    if s.endswith(".mp3"): return "audio/mp3"
    if s.endswith(".webm"): return "video/webm"
    if s.endswith(".mkv"): return "video/x-matroska"
    if s.endswith((".jpg",".jpeg")): return "image/jpeg"
    if s.endswith(".png"): return "image/png"
    if s.endswith(".webp"): return "image/webp"
    return "video/mp4"
def convert_to_mp3(vp,folder):
    mp=folder/(vp.stem+".mp3")
    subprocess.run(["ffmpeg","-y","-threads","4","-i",str(vp),"-vn","-c:a","libmp3lame","-q:a","2",str(mp)],capture_output=True,text=True)
    if not mp.exists() or mp.stat().st_size<1000: raise RuntimeError("MP3 convert failed")
    return mp
def clean_insta_url(url):
    u=url.strip().split("?")[0].split("&")[0]
    m=re.search(r"/(reel|reels|p)/([A-Za-z0-9_-]+)",u)
    if m: return "https://www.instagram.com/reel/"+m.group(2)+"/"
    return u+"/" if not u.endswith("/") else u

# ========== DRIVE ==========
def get_drive_id(url):
    url=url.strip()
    m=re.search(r"/file/d/([A-Za-z0-9_-]+)",url)
    if m: return m.group(1)
    q=parse_qs(urlparse(url).query)
    if q.get("id"): return q["id"][0]
    if len(url)>20 and "/" not in url and " " not in url: return url
    raise ValueError("Invalid Drive link")
def download_drive(url,folder):
    fid=get_drive_id(url); target=folder/"drive_video.mp4"
    dl=f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"
    r=requests.get(dl,headers={"User-Agent":"Mozilla/5.0"},stream=True,timeout=600,allow_redirects=True)
    if "text/html" in r.headers.get("Content-Type",""): raise RuntimeError("Drive failed. Set Anyone with link to Viewer")
    with open(target,"wb") as f:
        for c in r.iter_content(1024*1024*4):
            if c: f.write(c)
    if not target.exists() or target.stat().st_size<10000: raise RuntimeError("Drive failed. Check link")
    with open(target,"rb") as f: hdr=f.read(500).decode("utf-8",errors="ignore")
    if "<html" in hdr or "<!DOCTYPE" in hdr:
        target.unlink(missing_ok=True); raise RuntimeError("Drive returned web page. Set Anyone with link > Viewer")
    return target

# ========== INSTAGRAM DOWNLOADER ==========
COBALT_INSTANCES=["https://co.wuk.sh/","https://cobalt-backend.canine.tools/","https://cobalt-api.kavin.rocks/"]
def download_from_url(vurl,folder,name):
    target=folder/name
    with requests.get(vurl,stream=True,timeout=600,headers={"User-Agent":"Mozilla/5.0"}) as dl:
        dl.raise_for_status()
        with open(target,"wb") as f:
            for c in dl.iter_content(1024*1024*4):
                if c: f.write(c)
    if target.exists() and target.stat().st_size>10000: return target
    raise RuntimeError("Empty file from server")
def download_via_cobalt(url,folder,filename="cobalt_video.mp4"):
    last="unknown"
    for base in COBALT_INSTANCES:
        try:
            r=requests.post(base,json={"url":url.strip(),"videoQuality":"720","filenameStyle":"basic"},headers={"Accept":"application/json","Content-Type":"application/json"},timeout=20)
            if r.status_code!=200: last=str(base)+" status "+str(r.status_code); continue
            vurl=r.json().get("url")
            if not vurl: last=str(base)+" no url"; continue
            return download_from_url(vurl,folder,filename)
        except Exception as e: last=str(e); continue
    raise RuntimeError("Cobalt failed: "+last)
def download_instagram(url,folder,want_mp3=False):
    clean=clean_insta_url(url)
    if "instagram.com" not in clean and "instagr.am" not in clean: raise RuntimeError("Invalid Instagram link")
    m=re.search(r"/reel/([A-Za-z0-9_-]+)",clean); sc=m.group(1) if m else None
    try:
        vp=download_via_cobalt(clean,folder,"insta_video.mp4")
        return convert_to_mp3(vp,folder) if want_mp3 else vp
    except Exception as e: print("Insta cobalt fail",e)
    if sc:
        for mirror in ["https://www.ddinstagram.com","https://d.ddinstagram.com","https://www.vxinstagram.com"]:
            try:
                r=requests.get(mirror+"/reel/"+sc+"/",headers={"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"},timeout=15)
                if r.status_code!=200: continue
                vm=re.search(r'https://[^"]+\.mp4[^"]*',r.text)
                if vm:
                    try:
                        vp=download_from_url(vm.group(0).replace("&amp;","&"),folder,"insta_video.mp4")
                        return convert_to_mp3(vp,folder) if want_mp3 else vp
                    except: continue
                im=re.search(r'https://[^"]+\.jpg[^"]*',r.text)
                if im and not want_mp3:
                    try: return download_from_url(im.group(0).replace("&amp;","&"),folder,"insta_image.jpg")
                    except: continue
            except: continue
    try:
        import yt_dlp
        if want_mp3: opts={"format":"bestaudio/best","outtmpl":str(folder/"insta_audio.%(ext)s"),"noplaylist":True,"quiet":True,"no_warnings":True,"retries":2,"socket_timeout":20,"postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]}
        else: opts={"format":"best[ext=mp4]/best","outtmpl":str(folder/"insta_video.%(ext)s"),"noplaylist":True,"quiet":True,"no_warnings":True,"retries":2,"socket_timeout":20}
        with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([clean])
        files=list(folder.glob("insta_audio.mp3")) if want_mp3 else [f for f in folder.glob("insta_video.*") if f.suffix.lower() in [".mp4",".webm",".mkv",".jpg",".png"]]
        if files and files[0].stat().st_size>1000: return files[0]
    except Exception as e: print("Insta yt-dlp fail",e)
    try:
        r=requests.get(clean+"embed/",headers={"User-Agent":"Mozilla/5.0"},timeout=15)
        vm=re.search(r'https://[^"]+\.mp4[^"]*',r.text)
        if vm:
            vp=download_from_url(vm.group(0).replace("&amp;","&"),folder,"insta_video.mp4")
            return convert_to_mp3(vp,folder) if want_mp3 else vp
    except: pass
    raise RuntimeError("Instagram failed. Paste clean link")

# ========== HIGHLIGHT - FAST ==========
def get_highlight_starts(src,total,length,count,ts,te):
    try:
        import numpy as np
        work=Path(src).parent; ap=work/"hl.wav"
        subprocess.run(["ffmpeg","-y","-threads","2","-i",str(src),"-vn","-ac","1","-ar","8000","-c:a","pcm_s16le",str(ap)],capture_output=True,timeout=120)
        if not ap.exists(): return None
        with wave.open(str(ap),"rb") as wf:
            rate=wf.getframerate(); data=wf.readframes(wf.getnframes())
        audio=np.frombuffer(data,dtype=np.int16).astype(float)/32768.0
        scores=[]
        for p in range(20):
            s=int((ts+(te-ts)*p/20))*rate; e=min(s+5*rate,len(audio))
            ch=audio[s:e] if e>s else audio[:1]
            scores.append(float(np.sqrt(np.mean(ch**2))) if len(ch)>0 else 0)
        order=sorted(range(20),key=lambda i: scores[i],reverse=True)
        starts=[]
        for i in order:
            s=ts+(te-ts)*i/20
            if all(abs(s-x)>=length*0.65 for x in starts): starts.append(s)
            if len(starts)>=count: break
        if ap.exists(): ap.unlink()
        return sorted(starts) if starts else None
    except Exception as e:
        print("Highlight fail",e); return None
def choose_normal_starts(total,length,count,ts,te):
    avail=te-ts
    if avail<=length: return [ts]
    if avail>=count*length: return [ts+i*length for i in range(count)]
    if count==1: return [ts+avail/2-length/2]
    step=(avail-length)/(count-1); return [ts+i*step for i in range(count)]

RATIOS={"9:16 - Shorts / Reels": (1080,1920),"16:9 - Wide": (1920,1080),"1:1 - Post / Feed": (1080,1080),"4:5 - Portrait Post": (1080,1350),"3:4 - Portrait": (1080,1440),"21:9 - Cinematic": (1920,823),}
RESOLUTIONS={"480p - Fast": 480,"720p - HD": 720,"1080p - Full HD": 1080,"1440p - 2K": 1440,}
def get_output_size(rl,resl):
    bw,bh=RATIOS[rl]; t=RESOLUTIONS[resl]
    if bw<=bh: w=t; h=int(bh*(t/bw))
    else: h=t; w=int(bw*(t/bh))
    return w-(w%2),h-(h%2)
def get_preview_size(rl):
    bw,bh=RATIOS[rl]
    if bw<=bh: w=540; h=int(bh*(540/bw))
    else: h=540; w=int(bw*(540/bh))
    return w-(w%2),h-(h%2)
def build_effect(effect):
    if effect=="None - Original": return []
    if effect=="Cinematic - Dark + Warm": return ["curves=r='0/0 0.5/0.45 1/1':g='0/0 0.5/0.5 1/1':b='0/0 0.5/0.55 1/0.95'","eq=brightness=-0.05:contrast=1.15:saturation=0.90"]
    if effect=="Vivid - Color Pop": return ["eq=brightness=0.05:contrast=1.20:saturation=1.40"]
    if effect=="Black & White": return ["eq=contrast=1.10:saturation=0"]
    if effect=="Vintage - Old Film": return ["eq=brightness=0.05:contrast=0.95:saturation=0.80","noise=alls=6:allf=t"]
    if effect=="Warm - Golden": return ["colorbalance=rs=0.15:gs=0.05:bs=-0.15"]
    if effect=="Cool - Blue": return ["colorbalance=rs=-0.10:gs=0.0:bs=0.15"]
    return []
def render_clip(source,output,start,length,cfg,music):
    args=["ffmpeg","-y","-threads","4","-ss",str(start),"-i",str(source)]
    if music: args+=["-stream_loop","-1","-i",str(music)]
    fl=[f"scale={cfg['out_w']}:{cfg['out_h']}:force_original_aspect_ratio=increase:flags=bicubic",f"crop={cfg['out_w']}:{cfg['out_h']}","setsar=1"]
    fl+=build_effect(cfg["effect"])
    vf=",".join(fl); sa=has_audio(source)
    if music and sa:
        fc=f"[0:v]{vf}[vout];[0:a]volume={cfg['source_volume']}[a0];[1:a]volume={cfg['music_volume']}[a1];[a0][a1]amix=inputs=2:duration=first[aout]"
        args+=["-t",str(length),"-filter_complex",fc,"-map","[vout]","-map","[aout]","-c:v","libx264","-preset","ultrafast","-crf","32","-c:a","aac","-b:a","128k","-pix_fmt","yuv420p"]
    else:
        args+=["-t",str(length),"-vf",vf,"-c:v","libx264","-preset","ultrafast","-crf","32","-pix_fmt","yuv420p"]
        if music: args+=["-map","0:v:0","-map","1:a:0","-af",f"volume={cfg['music_volume']}","-c:a","aac","-b:a","128k"]
        elif sa: args+=["-af",f"volume={cfg['source_volume']}","-c:a","aac","-b:a","128k"]
        else: args+=["-an"]
    args+=["-movflags","+faststart","-avoid_negative_ts","make_zero",str(output)]; run_cmd(args); gc.collect()
def get_source(work,stype,url,up):
    if stype=="Google Drive": return download_drive(url,work)
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

# ========== UI - ENGLISH ==========
main_mode=st.radio("Select Section",["CLIPPER","DOWNLOADER"],horizontal=True,key="main_mode_final")
if main_mode!=st.session_state.active_tab:
    st.session_state.preview_done=False; st.session_state.preview_bytes=None; st.session_state.active_tab=main_mode

if main_mode=="CLIPPER":
    st.subheader("Clipper - Highlight + Normal")
    source_type=st.radio("Choose source",["Google Drive","Upload video"],horizontal=True,index=0,key="clip_src_final")
    video_url=""; video_upload=None
    if source_type=="Google Drive": video_url=st.text_input("Drive link",placeholder="Paste Drive link",key="clip_drive_final")
    elif source_type=="Upload video": video_upload=st.file_uploader("Upload video - Unlimited Size",type=["mp4","mov","mkv","webm","avi","m4v"],key="clip_up_final")
    st.subheader("🎵 Music Settings")
    music_upload=st.file_uploader("Background Music (Optional) - Unlimited Size",type=["mp3","wav","m4a","aac","ogg","flac"],key="clip_music_final")
    c1,c2=st.columns(2)
    with c1: source_volume=st.slider("Original audio volume",0.0,2.0,1.0,key="clip_sv_final")
    with c2: music_volume=st.slider("Music volume",0.0,2.0,0.25,key="clip_mv_final")
    st.subheader("⚙️ Editing Settings")
    clip_mode=st.radio("How to clip?",["Highlight Moments - Best Parts Only","Normal Clipping - Evenly Spaced Clips"],index=1,key="clip_mode_final")
    clip_count=st.slider("Maximum clips",1,50,3,key="clip_count_final")
    clip_length=st.slider("Clip duration (seconds)",5,180,30,key="clip_len_final")
    use_trim=st.toggle("Enable Trim",value=False,key="clip_trim_final")
    trim_start=0.0; trim_end=None
    if use_trim:
        trim_start=st.number_input("Start (sec)",min_value=0.0,value=0.0,step=1.0,key="clip_ts_final")
        trim_end=st.number_input("End (sec) - Unlimited",min_value=1.0,value=60.0,step=1.0,max_value=100000.0,key="clip_te_final")
        if trim_end<=trim_start: st.error("End must be greater than Start")
    st.subheader("✨ Effect")
    effect=st.selectbox("Effect",["None - Original","Cinematic - Dark + Warm","Vivid - Color Pop","Black & White","Vintage - Old Film","Warm - Golden","Cool - Blue"],key="clip_eff_final")
    st.subheader("📐 Ratio + Resolution")
    ratio_label=st.selectbox("Aspect Ratio",list(RATIOS.keys()),index=0,key="clip_ratio_final")
    res_label=st.selectbox("Resolution",list(RESOLUTIONS.keys()),index=1,key="clip_res_final")
    out_w,out_h=get_output_size(ratio_label,res_label)
    st.info(f"{ratio_label} | {res_label} | {out_w}x{out_h} | Clips: {clip_count} | Length: {clip_length}s | Effect: {effect} | Music: {'Yes' if music_upload else 'No'}")
    cfg={"source_volume":source_volume,"music_volume":music_volume,"out_w":out_w,"out_h":out_h,"effect":effect}
    st.subheader("Step 1: Preview")
    if st.button("GENERATE PREVIEW - 5 Sec",use_container_width=True,key="clip_prev_final"):
        if source_type=="Upload video" and video_upload is None: st.error("Please upload video first"); st.stop()
        if source_type!="Upload video" and not video_url.strip().startswith(("https://","http://")): st.error("Enter valid link"); st.stop()
        if not check_ffmpeg(): st.error("FFmpeg missing"); st.stop()
        work=Path(tempfile.mkdtemp(prefix="preview_"))
        try:
            with st.spinner("Making Preview..."):
                src=get_source(work,source_type,video_url,video_upload); mus=get_music(work,music_upload)
                pw,ph=get_preview_size(ratio_label)
                preview_cfg=cfg.copy(); preview_cfg["out_w"]=pw; preview_cfg["out_h"]=ph
                p_out=work/"preview.mp4"; render_clip(src,p_out,trim_start if use_trim else 0.0,5,preview_cfg,mus)
                with open(p_out,"rb") as f: st.session_state.preview_bytes=f.read()
                st.session_state.preview_done=True; st.success("Preview Ready!")
        except Exception as e: st.error("Preview Error: "+str(e)); st.session_state.preview_done=False
    if st.session_state.preview_bytes is not None: st.video(st.session_state.preview_bytes)
    if st.session_state.preview_done: st.success("Preview Approved - Generate Now!")
    else: st.warning("Generate Locked - Watch Preview First")
    st.subheader("Step 2: Generate Clips")
    if st.session_state.clip_paths:
        if st.button("🗑️ Clear All Clips", key="clear_clips_final"):
            st.session_state.clip_paths=[]; st.session_state.clip_names=[]; st.session_state.zip_path=""; gc.collect(); st.rerun()
    if st.button("GENERATE CLIPS",type="primary",use_container_width=True,disabled=not st.session_state.preview_done,key="clip_gen_final"):
        work=Path(tempfile.mkdtemp(prefix="clipshort_"))
        try:
            src=get_source(work,source_type,video_url,video_upload); mus=get_music(work,music_upload)
            total=get_duration(src)
            if total<=0: st.error("Could not read video duration"); st.stop()
            st.write(f"Video: {round(total,1)} sec | {ratio_label} | {res_label} | {out_w}x{out_h}")
            t_start=trim_start if use_trim else 0.0; t_end=min(trim_end,total) if use_trim and trim_end else total
            if t_end<=t_start: st.error("Trim End must be greater than Start"); st.stop()
            if "Highlight" in clip_mode:
                with st.spinner("Finding Highlights..."):
                    starts=get_highlight_starts(src,total,clip_length,clip_count,t_start,t_end)
                if not starts:
                    st.warning("No audio - Using Normal"); starts=choose_normal_starts(total,clip_length,clip_count,t_start,t_end)
                else:
                    for idx,s in enumerate(starts): st.write(f"🔥 Highlight {idx+1}: {int(s//60)}:{int(s%60):02d}")
            else:
                starts=choose_normal_starts(total,clip_length,clip_count,t_start,t_end)
                for idx,s in enumerate(starts): st.write(f"Clip {idx+1}: {int(s//60)}:{int(s%60):02d}")
            progress=st.progress(0); status_text=st.empty(); paths=[]; names=[]
            for i,s in enumerate(starts):
                status_text.write(f"Rendering Clip {i+1}/{len(starts)} at {res_label} - {effect} - Please wait...")
                out=work/f"clip_{i+1}.mp4"; render_clip(src,out,s,clip_length,cfg,mus)
                if out.exists() and out.stat().st_size>10000:
                    paths.append(str(out)); names.append(f"clip_{i+1}.mp4")
                progress.progress((i+1)/len(starts)); gc.collect()
            status_text.empty()
            if not paths: st.error("No clips rendered"); st.stop()
            # Build ZIP once, save path - not bytes in memory
            zip_path=str(work/"clipshort_clips.zip")
            with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED) as z:
                for p,n in zip(paths,names): z.write(p,arcname=n)
            st.session_state.clip_paths=paths; st.session_state.clip_names=names; st.session_state.zip_path=zip_path
            st.success(f"Done - {len(paths)} Clips Ready!")
        except Exception as e: st.error("Error: "+str(e))

    # ========== CLIPS - LIST VIEW - FAST - DOWNLOAD ABOVE VIDEO ==========
    if st.session_state.clip_paths:
        st.divider()
        st.header(f"✅ {len(st.session_state.clip_paths)} Clips Ready")
        # TOP ZIP - Always visible
        st.markdown('<div class="sticky-bar">⬇️ ALL CLIPS READY - DOWNLOAD BELOW</div>', unsafe_allow_html=True)
        # FIX: Read ZIP only when button is rendered, not all videos
        if Path(st.session_state.zip_path).exists():
            with open(st.session_state.zip_path,"rb") as f: zip_data=f.read()
            st.download_button("⬇️ DOWNLOAD ALL CLIPS (ZIP) - TAP HERE", data=zip_data, file_name="clipshort_clips.zip", mime="application/zip", key="dl_all_zip_TOP")
        st.write("---")
        st.subheader("📋 Clip List - Select One To Preview")
        # CHANGE: List instead of loading all videos - Much faster, no glitch
        selected_idx=st.selectbox("Choose Clip", options=list(range(len(st.session_state.clip_paths))), format_func=lambda i: f"🎬 Clip {i+1} - {res_label} - {st.session_state.clip_names[i]}", key="clip_selector")
        # Show ONLY selected clip - 1 video at a time
        sel_path=st.session_state.clip_paths[selected_idx]
        sel_name=st.session_state.clip_names[selected_idx]
        if Path(sel_path).exists():
            st.markdown('<div class="clip-card">', unsafe_allow_html=True)
            st.subheader(f"🎬 Clip {selected_idx+1} - {res_label} - {ratio_label}")
            # FIX: DOWNLOAD BUTTON ABOVE VIDEO - Not below - Never hidden by video player
            with open(sel_path,"rb") as f: sel_data=f.read()
            st.download_button(f"⬇️ DOWNLOAD Clip {selected_idx+1} - TAP HERE", data=sel_data, file_name=sel_name, mime="video/mp4", key=f"dl_clip_selected_{selected_idx}")
            st.video(sel_path)
            st.markdown('</div>', unsafe_allow_html=True)
        st.write("---")
        st.subheader("📥 Download All Clips - Quick List")
        # Quick List - All download buttons in list, no videos - Fast
        for idx, (p,n) in enumerate(zip(st.session_state.clip_paths, st.session_state.clip_names)):
            c1,c2=st.columns([3,1])
            with c1: st.write(f"🎬 **Clip {idx+1}** - {n}")
            with c2:
                if Path(p).exists():
                    with open(p,"rb") as f: d=f.read()
                    st.download_button(f"⬇️ Download", data=d, file_name=n, mime="video/mp4", key=f"dl_list_{idx}")
        # BOTTOM ZIP
        if Path(st.session_state.zip_path).exists():
            with open(st.session_state.zip_path,"rb") as f: zip_data2=f.read()
            st.download_button("⬇️ DOWNLOAD ALL CLIPS (ZIP) - BOTTOM", data=zip_data2, file_name="clipshort_clips.zip", mime="application/zip", key="dl_all_zip_final")

elif main_mode=="DOWNLOADER":
    st.subheader("Downloader - Instagram + MP3")
    st.info("Paste Instagram Reel / Post link - Get Video or MP3")
    dl_url = st.text_input("Instagram Link", placeholder="https://www.instagram.com/reel/...", key="dl_url_final")
    dl_mp3 = st.toggle("Convert to MP3 Only", value=False, key="dl_mp3_final")
    if st.button("DOWNLOAD", type="primary", use_container_width=True, key="dl_btn_final"):
        if not dl_url.strip():
            st.error("Paste Instagram link first"); st.stop()
        work = Path(tempfile.mkdtemp(prefix="dl_"))
        try:
            with st.spinner("Downloading..."):
                result = download_instagram(dl_url, work, want_mp3=dl_mp3)
                with open(result, "rb") as f: data = f.read()
                st.success("Download Ready!")
                if dl_mp3:
                    st.audio(data, format="audio/mp3")
                    st.download_button("⬇️ Download MP3", data=data, file_name=result.name, mime="audio/mp3", key="dl_mp3_btn_final")
                else:
                    if result.suffix.lower() in [".jpg",".jpeg",".png",".webp"]:
                        st.image(data)
                    else:
                        st.video(data)
                    st.download_button(f"⬇️ Download {result.name}", data=data, file_name=result.name, mime=get_mime(result), key="dl_vid_btn_final")
        except Exception as e:
            st.error("Error: " + str(e))
