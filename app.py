import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import streamlit as st, subprocess, tempfile, shutil, re, gc, wave, requests
from pathlib import Path
from urllib.parse import urlparse, parse_qs

st.set_page_config(page_title="CLIPSHORT AI", page_icon="🎬", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>.block-container{max-width:1280px;padding-top:1rem;padding-bottom:2rem}.stButton>button{width:100%;border-radius:10px;min-height:44px;font-size:15px}.stDownloadButton>button{width:100%;border-radius:10px;min-height:44px}video{width:100%!important;border-radius:12px}</style>""", unsafe_allow_html=True)
st.markdown("<h1>🎬 CLIPSHORT AI</h1><p>Clipper + Instagram Downloader + MP3</p>", unsafe_allow_html=True)

if "preview_done" not in st.session_state: st.session_state.preview_done=False
if "preview_bytes" not in st.session_state: st.session_state.preview_bytes=None
if "active_tab" not in st.session_state: st.session_state.active_tab="CLIPPER"

def run_cmd(cmd_list):
    r=subprocess.run(cmd_list,capture_output=True,text=True)
    if r.returncode!=0: raise RuntimeError((r.stderr or r.stdout)[-1200:])
    return r.stdout.strip()
def check_ffmpeg(): return shutil.which("ffmpeg") is not None
def get_duration(p):
    try: return float(run_cmd(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(p)]))
    except: return 0.0
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
    subprocess.run(["ffmpeg","-y","-i",str(vp),"-vn","-c:a","libmp3lame","-q:a","2",str(mp)],capture_output=True,text=True)
    if not mp.exists() or mp.stat().st_size<1000: raise RuntimeError("MP3 convert failed")
    return mp
def clean_insta_url(url):
    u=url.strip().split("?")[0].split("&")[0]
    m=re.search(r"/(reel|reels|p)/([A-Za-z0-9_-]+)",u)
    if m: return "https://www.instagram.com/reel/"+m.group(2)+"/"
    return u+"/" if not u.endswith("/") else u
def get_drive_id(url):
    parsed=urlparse(url.strip())
    m=re.search(r"/file/d/([A-Za-z0-9_-]+)",parsed.path)
    if m: return m.group(1)
    q=parse_qs(parsed.query)
    if q.get("id"): return q["id"][0]
    raise ValueError("Invalid Drive link")
def download_drive(url,folder):
    fid=get_drive_id(url); target=folder/"drive_video.mp4"; s=requests.Session()
    r=s.get("https://drive.google.com/uc?export=download&id="+fid+"&confirm=t",stream=True,timeout=120)
    with open(target,"wb") as f:
        for c in r.iter_content(chunk_size=1024*1024*2):
            if c: f.write(c)
    if not target.exists() or target.stat().st_size<10000: raise RuntimeError("Drive failed. Set Anyone with link to Viewer")
    return target
COBALT_INSTANCES=["https://co.wuk.sh/","https://cobalt-backend.canine.tools/","https://cobalt-api.kavin.rocks/"]
def download_from_url(vurl,folder,name):
    target=folder/name
    with requests.get(vurl,stream=True,timeout=180,headers={"User-Agent":"Mozilla/5.0"}) as dl:
        dl.raise_for_status()
        with open(target,"wb") as f:
            for c in dl.iter_content(chunk_size=1024*1024*2):
                if c: f.write(c)
    if target.exists() and target.stat().st_size>10000: return target
    raise RuntimeError("Empty file from server")
def download_via_cobalt(url,folder,filename="cobalt_video.mp4"):
    last="unknown"
    for base in COBALT_INSTANCES:
        try:
            r=requests.post(base,json={"url":url.strip(),"videoQuality":"720","filenameStyle":"basic"},headers={"Accept":"application/json","Content-Type":"application/json"},timeout=30)
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
                r=requests.get(mirror+"/reel/"+sc+"/",headers={"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"},timeout=20)
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
        if want_mp3: opts={"format":"bestaudio/best","outtmpl":str(folder/"insta_audio.%(ext)s"),"noplaylist":True,"quiet":True,"no_warnings":True,"retries":3,"socket_timeout":30,"postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]}
        else: opts={"format":"best[ext=mp4]/best","outtmpl":str(folder/"insta_video.%(ext)s"),"noplaylist":True,"quiet":True,"no_warnings":True,"retries":3,"socket_timeout":30}
        with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([clean])
        files=list(folder.glob("insta_audio.mp3")) if want_mp3 else [f for f in folder.glob("insta_video.*") if f.suffix.lower() in [".mp4",".webm",".mkv",".jpg",".png"]]
        if files and files[0].stat().st_size>1000: return files[0]
    except Exception as e: print("Insta yt-dlp fail",e)
    try:
        r=requests.get(clean+"embed/",headers={"User-Agent":"Mozilla/5.0"},timeout=20)
        vm=re.search(r'https://[^"]+\.mp4[^"]*',r.text)
        if vm:
            vp=download_from_url(vm.group(0).replace("&amp;","&"),folder,"insta_video.mp4")
            return convert_to_mp3(vp,folder) if want_mp3 else vp
    except: pass
    raise RuntimeError("Instagram failed. Paste clean link: https://www.instagram.com/reel/Dfqu4ikT61P/")
def get_highlight_scores(vp,total):
    try:
        import numpy as np
        ap=Path(str(vp)+"_audio.wav")
        subprocess.run(["ffmpeg","-y","-i",str(vp),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(ap)],capture_output=True)
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
        sm=[sum(scores[max(0,i-1):min(len(scores),i+2)])/len(scores[max(0,i-1):min(len(scores),i+2)]) for i in range(len(scores))]
        if ap.exists(): ap.unlink()
        return sm
    except Exception as e: print(e); return None
def choose_highlight_starts(scores,total,length,count,ts,te):
    if scores is None: return None
    cands=[]; start=ts
    while start+length<=te:
        si=int(start); ei=int(min(start+length,len(scores))); sc=sum(scores[si:ei]) if ei>si else 0
        if ei>si: sc=sc+max(scores[si:ei])*2.0
        cands.append((sc,start)); start+=2.0
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
    step=(avail-length)/(count-1); return [ts+i*step for i in range(count)]

# --- RATIO + RESOLUTION SETTINGS ---
RATIOS={
    "9:16 - Shorts / Reels": (1080,1920),
    "16:9 - Wide": (1920,1080),
    "1:1 - Post / Feed": (1080,1080),
    "4:5 - Portrait Post": (1080,1350),
    "3:4 - Portrait": (1080,1440),
    "21:9 - Cinematic": (1920,823),
}
RESOLUTIONS={
    "480p - Fast / Low Size": 480,
    "720p - HD": 720,
    "1080p - Full HD": 1080,
    "1440p - 2K": 1440,
}
def get_output_size(rl,resl):
    bw,bh=RATIOS[rl]; t=RESOLUTIONS[resl]
    if bw<=bh: w=t; h=int(bh*(t/bw))
    else: h=t; w=int(bw*(t/bh))
    return w-(w%2),h-(h%2)

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
    fl+=build_effect_filter(cfg,length); fl.append("fps=30"); vf=",".join(fl); sa=has_audio(source)
    if music and sa:
        at=f"atempo={cfg['speed']:.2f}," if cfg["speed"]!=1.0 else ""
        fc=f"[0:v]{vf}[vout];[0:a]{at}volume={cfg['source_volume']}[a0];[1:a]volume={cfg['music_volume']}[a1];[a0][a1]amix=inputs=2:duration=first[aout]"
        args+=["-t",str(length),"-filter_complex",fc,"-map","[vout]","-map","[aout]","-c:v","libx264","-preset","ultrafast","-crf","28","-c:a","aac","-pix_fmt","yuv420p"]
    else:
        args+=["-t",str(length),"-vf",vf,"-c:v","libx264","-preset","ultrafast","-crf","28","-pix_fmt","yuv420p"]
        if music: args+=["-map","0:v:0","-map","1:a:0","-af",f"volume={cfg['music_volume']}","-c:a","aac"]
        elif sa:
            at=f"atempo={cfg['speed']:.2f}," if cfg["speed"]!=1.0 else ""
            args+=["-af",at+f"volume={cfg['source_volume']}","-c:a","aac"]
        else: args+=["-an"]
    args+=["-movflags","+faststart",str(output)]; run_cmd(args); gc.collect()
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

main_mode=st.radio("Select Section",["CLIPPER","DOWNLOADER"],horizontal=True,key="main_mode_final")
if main_mode!=st.session_state.active_tab:
    st.session_state.preview_done=False; st.session_state.preview_bytes=None; st.session_state.active_tab=main_mode

if main_mode=="CLIPPER":
    st.subheader("Clipper - Highlight + Normal")
    left,right=st.columns([1.5,1],gap="medium")
    with right:
        st.subheader("Editing Settings")
        clip_mode=st.radio("How to clip?",["Highlight Moments - Best Parts Only","Normal Clipping - Evenly Spaced Clips"],index=1,key="clip_mode_final")
        clip_count=st.slider("Maximum clips",1,30,3,key="clip_count_final")
        clip_length=st.slider("Clip duration (seconds)",5,60,30,key="clip_len_final")
        source_volume=st.slider("Original audio volume",0.0,2.0,1.5,key="clip_sv_final")
        music_volume=st.slider("Music volume",0.0,2.0,0.25,key="clip_mv_final")
        use_trim=st.toggle("Enable Trim",value=False,key="clip_trim_final")
        trim_start=0.0; trim_end=None
        if use_trim:
            trim_start=st.number_input("Start (sec)",min_value=0.0,value=0.0,step=1.0,key="clip_ts_final")
            trim_end=st.number_input("End (sec)",min_value=1.0,value=60.0,step=1.0,key="clip_te_final")
            if trim_end<=trim_start: st.error("End must be greater than Start")
        effect=st.selectbox("Effect",["None - Original","Cinematic - Dark + Warm","Vivid - Color Pop","Black & White","Vintage - Old Film","Warm - Golden","Cool - Blue"],key="clip_eff_final")
        brightness=st.slider("Brightness",-0.3,0.3,0.0,step=0.01,key="clip_br_final")
        speed=st.selectbox("Speed",[0.5,0.75,1.0,1.25,1.5,2.0],index=2,key="clip_sp_final")
        contrast=st.slider("Contrast",0.5,2.0,1.0,step=0.05,key="clip_ct_final")
        sharpen=st.slider("Sharpen",0.0,3.0,0.0,step=0.5,key="clip_sh_final")
        saturation=st.slider("Saturation",0.0,2.5,1.0,step=0.05,key="clip_sat_final")
        blur=st.slider("Blur",0.0,3.0,0.0,step=0.5,key="clip_bl_final")
        fade_in=st.toggle("Fade In",value=False,key="clip_fi_final")
        fade_out=st.toggle("Fade Out",value=False,key="clip_fo_final")
        ratio_label=st.selectbox("Aspect Ratio",list(RATIOS.keys()),index=0,key="clip_ratio_final")
        res_label=st.selectbox("Resolution",list(RESOLUTIONS.keys()),index=1,key="clip_res_final")
        out_w,out_h=get_output_size(ratio_label,res_label)
        st.info(f"{ratio_label} | {res_label} | {out_w}x{out_h}")
        cfg={"source_volume":source_volume,"music_volume":music_volume,"out_w":out_w,"out_h":out_h,"effect":effect,"brightness":brightness,"contrast":contrast,"saturation":saturation,"sharpen":sharpen,"blur":blur,"speed":float(speed),"fade_in":fade_in,"fade_out":fade_out}
    with left:
        source_type=st.radio("Choose source",["Google Drive","Upload video"],horizontal=True,index=0,key="clip_src_final")
        video_url=""; video_upload=None
        if source_type=="Google Drive": video_url=st.text_input("Drive link",placeholder="Paste Drive link",key="clip_drive_final")
        elif source_type=="Upload video": video_upload=st.file_uploader("Upload video",type=["mp4","mov","mkv","webm","avi","m4v"],key="clip_up_final")
        music_upload=st.file_uploader("Background Music (Optional)",type=["mp3","wav","m4a","aac","ogg","flac"],key="clip_music_final")
        st.subheader("Step 1: Preview")
        if st.button("GENERATE PREVIEW - 5 Sec",use_container_width=True,key="clip_prev_final"):
            if source_type=="Upload video" and video_upload is None: st.error("Please upload video first"); st.stop()
            if source_type!="Upload video" and not video_url.strip().startswith(("https://","http://")): st.error("Enter valid link"); st.stop()
            if not check_ffmpeg(): st.error("FFmpeg missing"); st.stop()
            work=Path(tempfile.mkdtemp(prefix="preview_"))
            try:
                st.write("Making Preview..."); src=get_source(work,source_type,video_url,video_upload); mus=get_music(work,music_upload)
                p_out=work/"preview.mp4"; render_clip(src,p_out,trim_start if use_trim else 0.0,5,cfg,mus)
                with open(p_out,"rb") as f: st.session_state.preview_bytes=f.read()
                st.success("Preview Ready!"); st.video(st.session_state.preview_bytes); st.session_state.preview_done=True
            except Exception as e: st.error("Preview Error: "+str(e)); st.session_state.preview_done=False
        if st.session_state.preview_bytes is not None: st.video(st.session_state.preview_bytes)
        if st.session_state.preview_done: st.success("Preview Approved - Generate Now!")
        else: st.warning("Generate Locked - Watch Preview First")
        st.subheader("Step 2: Generate Clips")
        if st.button("GENERATE CLIPS",type="primary",use_container_width=True,disabled=not st.session_state.preview_done,key="clip_gen_final"):
            work=Path(tempfile.mkdtemp(prefix="clipshort_"))
            try:
                st.write("Processing..."); src=get_source(work,source_type,video_url,video_upload); mus=get_music(work,music_upload)
                total=get_duration(src)
                if total<=0: st.error("Could not read video duration"); st.stop()
                st.write(f"Video: {round(total,1)} sec")
                t_start=trim_start if use_trim else 0.0; t_end=min(trim_end,total) if use_trim and trim_end else total
                if t_end<=t_start: st.error("Trim End must be greater than Start"); st.stop()
                if "Highlight" in clip_mode:
                    scores=get_highlight_scores(src,total)
                    if scores is None: st.warning("No audio found - Using Normal clipping"); starts=choose_normal_starts(total,clip_length,clip_count,t_start,t_end)
                    else:
                        starts=choose_highlight_starts(scores,total,clip_length,clip_count,t_start,t_end)
                        for idx,s in enumerate(starts): st.write(f"Highlight {idx+1}: {int(s//60)}:{int(s%60):02d}")
                else: starts=choose_normal_starts(total,clip_length,clip_count,t_start,t_end)
                outs=[]
                for i,s in enumerate(starts):
                    out=work/f"clip_{i+1}.mp4"; st.write(f"Rendering {i+1}/{len(starts)} - {int(s//60)}:{int(s%60):02d}"); render_clip(src,out,s,clip_length,cfg,mus)
                    if out.exists() and out.stat().st_size>10000: outs.append(out)
                if not outs: st.error("No clips rendered. Try different video."); st.stop()
                st.success(f"Done - {len(outs)} Clips Ready!")
                for i,o in enumerate(outs):
                    st.subheader(f"Clip {i+1} - {out_w}x{out_h}"); st.video(str(o))
                    with open(o,"rb") as f: data=f.read()
                    st.download_button(f"Download Clip {i+1}",data,file_name=f"clip_{i+1}.mp4",mime="video/mp4",key=f"clip_dl_final_{i}")
            except Exception as e: st.error("Error: "+str(e))

if main_mode=="DOWNLOADER":
    st.subheader("Downloader - Instagram Only")
    st.markdown("### Instagram Downloader")
    insta_url=st.text_input("Instagram Link",placeholder="https://instagram.com/reel/...",key="dl_insta_url_final")
    insta_format=st.selectbox("Format - Instagram",["Video - MP4","Audio - MP3"],key="dl_insta_format_final")
    insta_quality=st.selectbox("Quality",["720p - HD","480p - Fast","1080p - Full HD"],key="dl_insta_q_final")
    if st.button("DOWNLOAD INSTAGRAM",type="primary",use_container_width=True,key="dl_insta_btn_final"):
        if not insta_url.strip().startswith(("https://","http://")): st.error("Please paste a valid Instagram link")
        else:
            work=Path(tempfile.mkdtemp(prefix="insta_dl_")); want_mp3="MP3" in insta_format
            try:
                with st.spinner("Downloading... Please wait"): src=download_instagram(insta_url,work,want_mp3=want_mp3)
                if want_mp3:
                    st.success("Instagram MP3 Done!"); st.audio(str(src))
                    with open(src,"rb") as f: data=f.read()
                    st.download_button("SAVE MP3 TO PHONE - Instagram",data,file_name=src.name,mime="audio/mp3",key="dl_insta_save_mp3_final")
                elif src.suffix.lower() in [".jpg",".png",".webp"]:
                    st.image(str(src))
                    with open(src,"rb") as f: data=f.read()
                    st.download_button("SAVE IMAGE",data,file_name=src.name,mime=get_mime(src),key="dl_insta_img_final")
                else:
                    st.success("Instagram Video Done!"); st.video(str(src))
                    with open(src,"rb") as f: data=f.read()
                    st.download_button("SAVE VIDEO TO PHONE - Instagram",data,file_name=src.name,mime=get_mime(src),key="dl_insta_save_final")
            except Exception as e: st.error("Download Failed: "+str(e))
    st.info("Tip: Insta Clean link: https://www.instagram.com/reel/Dfqu4ikT61P/")
