import os, uuid, subprocess, json
from flask import Flask, render_template_string, request, send_file
import gdown, yt_dlp
app = Flask(__name__)
UPLOAD_FOLDER="uploads"; CLIPS_FOLDER="clips"; MUSIC_FOLDER="music"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CLIPS_FOLDER, exist_ok=True)
os.makedirs(MUSIC_FOLDER, exist_ok=True)

CACHE = {}

HTML = """
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ClipShort V3 - LIVE Subtitles + Music + Effects</title>
<style>
*{box-sizing:border-box} body{background:#0a0a1a;color:white;font-family:Arial;padding:10px;margin:0}
.top{background:linear-gradient(90deg,#FF0000,#FF00AA,#AA00FF);padding:18px;border-radius:16px;text-align:center}
.top h1{margin:0;font-size:26px}.top p{margin:4px;opacity:.9}
.card{background:#1a1a3a;padding:14px;border-radius:16px;margin:12px 0}
input,select{width:100%;padding:12px;border-radius:10px;border:none;margin:6px 0;color:black;font-size:15px}
button{width:100%;padding:13px;border:none;border-radius:12px;font-weight:bold;cursor:pointer;margin-top:6px;font-size:15px}
.green{background:#00e676;color:black}.blue{background:#2196F3;color:white}.red{background:#FF1744;color:white}.yellow{background:#FFD600;color:black}.purple{background:#AA00FF;color:white}.orange{background:#FF6D00;color:white}
.pills{display:flex;gap:8px;margin:6px 0;flex-wrap:wrap}.pills button{flex:1;padding:10px;background:#2a2a5a;color:white;min-width:70px}
.pills button.active{background:#FFD600;color:black}
label{font-size:13px;color:#ccc}.range{width:100%}.row{display:flex;gap:8px}.row>*{flex:1}
small{color:#aaa}.live{color:#00e676;font-weight:bold}
.badge{background:#00e676;color:black;padding:3px 8px;border-radius:20px;font-size:11px}
</style>
<script>
function setClips(n){document.getElementById('num_clips').value=n; document.querySelectorAll('.clips-pill button').forEach(b=>b.classList.remove('active')); event.target.classList.add('active')}
function setVal(id,v){document.getElementById(id).value=v}
function setStyle(s){document.getElementById('style').value=s; document.querySelectorAll('.style-pill button').forEach(b=>b.classList.remove('active')); event.target.classList.add('active')}
function setEffect(s){document.getElementById('effect').value=s; document.querySelectorAll('.effect-pill button').forEach(b=>b.classList.remove('active')); event.target.classList.add('active')}
function setMusic(s){document.getElementById('music').value=s; document.querySelectorAll('.music-pill button').forEach(b=>b.classList.remove('active')); event.target.classList.add('active')}
</script></head><body>
<div class="top"><h1>⚡ ClipShort V3 - PRO</h1><p><span class="live">● LIVE</span> Subtitles + Music + Effects</p></div>

<div class="card"><h3>📤 1. Upload Video</h3>
<form action="/upload" method="post" enctype="multipart/form-data"><input type="file" name="video"><button class="green" type="submit">Upload Video</button></form>
<form action="/drive" method="post"><input name="drive_url" placeholder="Google Drive Link"><button class="blue" type="submit">📥 Drive</button></form>
<form action="/youtube" method="post"><input name="yt_url" placeholder="YouTube Link"><button class="red" type="submit">▶️ YouTube</button></form>
<small>Current: {{ last_video or 'No video yet' }}</small></div>

<div class="card"><h3>🎵 2. Music - Upload Your Own</h3>
<form action="/upload_music" method="post" enctype="multipart/form-data"><input type="file" name="music"><button class="orange" type="submit">🎵 Upload Music (MP3)</button></form>
<small>Music: {{ last_music or 'No music - Will use Original Audio' }}</small></div>

<div class="card"><h3>✨ 3. CREATE CLIP - LIVE Subtitles + Music + Effects</h3>
<form action="/make" method="post"><input type="hidden" name="video_path" value="{{ last_video or '' }}">

<label>🔴 LIVE Subtitles</label>
<select name="captions"><option value="live">LIVE - Word by Word Karaoke 🔥</option><option value="on">Normal Subtitles</option><option value="off">OFF</option></select>

<label>Caption Style</label>
<div class="pills style-pill"><button type="button" onclick="setStyle('karaoke')">🔥 Karaoke</button><button type="button" onclick="setStyle('tiktok')">📱 TikTok</button><button type="button" onclick="setStyle('clean')">Clean</button><button type="button" onclick="setStyle('neon')">💜 Neon</button><button type="button" onclick="setStyle('bold')">Bold</button></div>
<input type="hidden" id="style" name="style" value="karaoke">

<label>Font Size: <span id="fsVal">52</span> px</label>
<input type="range" class="range" name="font_size" min="24" max="90" value="52" oninput="document.getElementById('fsVal').innerText=this.value">
<label>Font Color</label><select name="font_color"><option value="yellow">Yellow 💛</option><option value="white">White 🤍</option><option value="cyan">Cyan 💙</option><option value="green">Green 💚</option><option value="pink">Pink 💖</option></select>

<label>🎵 Music</label>
<div class="pills music-pill"><button type="button" onclick="setMusic('none')">No Music</button><button type="button" onclick="setMusic('uploaded')">My Music 🎵</button><button type="button" onclick="setMusic('mix')">Mix - Music + Voice</button></div>
<input type="hidden" id="music" name="music" value="none">
<label>Music Volume: <span id="mvVal">30</span>%</label>
<input type="range" class="range" name="music_volume" min="0" max="100" value="30" oninput="document.getElementById('mvVal').innerText=this.value">

<label>✨ Video Effect</label>
<div class="pills effect-pill"><button type="button" onclick="setEffect('none')">None</button><button type="button" onclick="setEffect('zoom')">🔍 Zoom In</button><button type="button" onclick="setEffect('shake')">📳 Shake</button><button type="button" onclick="setEffect('vintage')">🎞️ Vintage</button><button type="button" onclick="setEffect('flash')">⚡ Flash</button><button type="button" onclick="setEffect('slowmo')">🐢 Slow-Mo</button></div>
<input type="hidden" id="effect" name="effect" value="none">

<input name="hook_text" placeholder="🔥 Hook Text - Ex: He Said WHAT?!">
<input name="find" placeholder="🔍 Find Moment - Ex: playoffs">
<label>Clip Length (Seconds)</label><input name="duration" value="30">
<label>How Many Clips?</label>
<div class="pills clips-pill"><button type="button" onclick="setClips(1)">1</button><button type="button" onclick="setClips(5)">5</button><button type="button" onclick="setClips(10)">10</button><button type="button" onclick="setClips(30)">30</button></div>
<input type="hidden" id="num_clips" name="num_clips" value="5">
<button class="yellow" type="submit">⚡ CREATE CLIPS - LIVE!</button>
</form></div>

{% if clip %}
<div class="card"><h3>✏️ 4. EDIT Clip</h3>
<form action="/edit" method="post"><input type="hidden" name="clip_path" value="{{ clip }}">
<div class="row"><input name="new_start" placeholder="Start" value="0"><input name="new_duration" placeholder="Duration" value="30"></div>
<input name="edit_text" placeholder="Text - Ex: Follow!"><input name="edit_hook" placeholder="Hook - Ex: Wait For It!">
<label>Edit Font Size</label><input type="range" class="range" name="edit_font" min="30" max="90" value="60">
<button class="purple" type="submit">✏️ SAVE EDIT</button></form></div>
{% endif %}

{% if message %}<div class="card"><h3>{{ message | safe }}</h3>{% if clip %}<br><a href="/download/{{ clip }}"><button class="green">⬇️ Download Clip 1</button></a><br><br><video controls width="100%" src="/download/{{ clip }}"></video>{% endif %}</div>{% endif %}
</body></html>
"""

def clean(t): return t.replace("'","").replace(":","").replace(",","").replace('"',"").replace("\\","").strip() if t else ""
def get_duration(p):
    try:
        r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",p],capture_output=True,text=True,timeout=20)
        return float(r.stdout.strip())
    except: return 0

def get_segments(path):
    if path in CACHE: return CACHE[path]
    try:
        import whisper
        model=whisper.load_model("tiny")
        res=model.transcribe(path, fp16=False)
        segs=res.get("segments",[])
        # LIVE: Split into WORDS for karaoke effect
        words=[]
        for s in segs:
            if "words" in s and s["words"]:
                for w in s["words"]: words.append(w)
            else:
                words.append({"start":s["start"],"end":s["end"],"text":s["text"]})
        CACHE[path]=words
        return words
    except Exception as e:
        print("Whisper fail",e); return []

def make_live_srt(words,path,style):
    # LIVE Subtitles: Each word = 1 subtitle = Karaoke Live effect!
    def fmt(t):
        h=int(t//3600); m=int((t%3600)//60); s=int(t%60); ms=int((t%1)*1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    with open(path,"w",encoding="utf-8") as f:
        for i,w in enumerate(words):
            # Show 3 words at a time for LIVE feel
            txt=" ".join([x.get("text","").strip() for x in words[max(0,i-1):i+2]])
            f.write(f"{i+1}\n{fmt(w['start'])} --> {fmt(w['end'])}\n{txt.upper()}\n\n")

def make_normal_srt(words,path):
    def fmt(t):
        h=int(t//3600); m=int((t%3600)//60); s=int(t%60); ms=int((t%1)*1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    with open(path,"w",encoding="utf-8") as f:
        for i,w in enumerate(words):
            f.write(f"{i+1}\n{fmt(w['start'])} --> {fmt(w['end'])}\n{w.get('text','').strip()}\n\n")

def get_effect_vf(effect):
    if effect=="zoom": return "scale=2160:3840,crop=1080:1920:(in_w-out_w)/2:(in_h-out_h)/2,scale=1080:1920"
    if effect=="shake": return "crop=iw-20:ih-20,scale=1080:1920"
    if effect=="vintage": return "curves=vintage,noise=alls=10:allf=t"
    if effect=="flash": return "eq=brightness=0.1:contrast=1.2"
    if effect=="slowmo": return "setpts=1.25*PTS"
    return "scale=1080:1920"

def make_clip(inp,start,duration,cap_mode,style,font_size,font_color,hook_text,find,words,music_mode,music_path,music_vol,effect):
    out=f"{CLIPS_FOLDER}/{uuid.uuid4().hex[:8]}_clip.mp4"
    if find and words:
        for w in words:
            if find.lower() in w.get("text","").lower():
                start=max(0,int(w.get("start",start))-1); break
    # Base VF: Crop 9:16 + Effect
    if effect=="zoom":
        vf="crop=ih*9/16:ih,scale=2160:3840,zoompan=z='min(zoom+0.0015,1.5)':d=125:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920"
    elif effect=="vintage":
        vf="crop=ih*9/16:ih,scale=1080:1920,curves=vintage,eq=saturation=0.8"
    elif effect=="flash":
        vf="crop=ih*9/16:ih,scale=1080:1920,eq=brightness=0.05:contrast=1.15"
    else:
        vf="crop=ih*9/16:ih,scale=1080:1920"
    # LIVE Subtitles
    if cap_mode in ["live","on"] and words:
        srt=f"{UPLOAD_FOLDER}/{uuid.uuid4().hex}.srt"
        if cap_mode=="live": make_live_srt(words,srt,style)
        else: make_normal_srt(words,srt)
        srt_esc=srt.replace(":","\\:")
        colors={"yellow":"&H00FFFF&","white":"&HFFFFFF&","cyan":"&HFFFF00&","green":"&H0000FF00&","pink":"&HFF00FF&"}
        col=colors.get(font_color,"&H00FFFF&")
        if style=="tiktok": st=f"FontSize={font_size},PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Bold=1,Alignment=2,MarginV=350,BorderStyle=1,Outline=4,Shadow=2"
        elif style=="neon": st=f"FontSize={font_size},PrimaryColour=&H00FFFF&,OutlineColour=&HFF00FF&,Bold=1,Alignment=2,MarginV=300"
        elif style=="bold": st=f"FontSize={font_size},PrimaryColour={col},OutlineColour=&H000000&,Bold=1,Alignment=2,MarginV=350"
        elif style=="clean": st=f"FontSize={font_size},PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Bold=0,Alignment=2,MarginV=280"
        else: st=f"FontSize={font_size},PrimaryColour={col},OutlineColour=&H000000&,Bold=1,Alignment=2,MarginV=300"  # Karaoke
        vf+=f",subtitles='{srt_esc}':force_style='{st}'"
    if hook_text:
        safe=clean(hook_text)
        if safe: vf+=f",drawtext=text='{safe}':fontcolor=white:fontsize=70:borderw=5:bordercolor=black:x=(w-text_w)/2:y=150"
    # Build FFmpeg Command
    cmd=["ffmpeg","-y","-ss",str(start),"-i",inp]
    # MUSIC: Add second input if needed
    if music_mode in ["uploaded","mix"] and music_path and os.path.exists(music_path):
        cmd+=["-i",music_path]
        vol=music_vol/100.0
        if music_mode=="uploaded":
            # Only Music, no original voice
            cmd+=["-t",str(duration),"-vf",vf,"-filter_complex",f"[0:a]volume=0.3[a0];[1:a]volume={vol}[a1];[a0][a1]amix=inputs=2:duration=first[aout]","-map","0:v","-map","[aout]","-c:v","libx264","-preset","ultrafast","-c:a","aac",out]
        else:
            cmd+=["-t",str(duration),"-vf",vf,"-filter_complex",f"[0:a]volume=1.0[a0];[1:a]volume={vol}[a1];[a0][a1]amix=inputs=2:duration=first[aout]","-map","0:v","-map","[aout]","-c:v","libx264","-preset","ultrafast","-c:a","aac",out]
    else:
        cmd+=["-t",str(duration),"-vf",vf,"-c:v","libx264","-preset","ultrafast","-c:a","aac",out]
    subprocess.run(cmd,capture_output=True,timeout=600)
    return out

last={"path":"","music":""}
@app.route("/")
def home(): return render_template_string(HTML,last_video=last["path"],last_music=last["music"])
@app.route("/health")
def health(): return "OK - V3 Live!"
def handle(p,msg):
    last["path"]=p; return render_template_string(HTML,message=msg,last_video=p,last_music=last["music"])
@app.route("/upload",methods=["POST"])
def upload():
    f=request.files.get("video")
    if not f or f.filename=="": return render_template_string(HTML,message="❌ No File!",last_video=last["path"],last_music=last["music"])
    p=f"{UPLOAD_FOLDER}/{uuid.uuid4().hex}.mp4"; f.save(p); return handle(p,"✅ Upload Done!")
@app.route("/upload_music",methods=["POST"])
def upload_music():
    f=request.files.get("music")
    if not f or f.filename=="": return render_template_string(HTML,message="❌ No Music File!",last_video=last["path"],last_music=last["music"])
    p=f"{MUSIC_FOLDER}/{uuid.uuid4().hex}.mp3"; f.save(p); last["music"]=p
    return render_template_string(HTML,message="✅ Music Uploaded! Now Select - My Music / Mix",last_video=last["path"],last_music=p)
@app.route("/drive",methods=["POST"])
def drive():
    url=request.form.get("drive_url","").strip()
    try:
        fid=url.split("/d/")[1].split("/")[0] if "/d/" in url else url.split("id=")[1].split("&")[0] if "id=" in url else url
        p=f"{UPLOAD_FOLDER}/{uuid.uuid4().hex}.mp4"; gdown.download(f"https://drive.google.com/uc?id={fid}",p,quiet=False)
        if not os.path.exists(p) or os.path.getsize(p)<1000: return render_template_string(HTML,message="❌ Drive - Make Anyone With Link!",last_video=last["path"],last_music=last["music"])
        return handle(p,"✅ Drive Done!")
    except Exception as e: return render_template_string(HTML,message=f"❌ Drive: {e}",last_video=last["path"],last_music=last["music"])
@app.route("/youtube",methods=["POST"])
def youtube():
    url=request.form.get("yt_url","").strip()
    try:
        tmpl=f"{UPLOAD_FOLDER}/{uuid.uuid4().hex}.%(ext)s"
        opts={'format':'best[height<=720][ext=mp4]/best[ext=mp4]/best','outtmpl':tmpl,'quiet':True,'nocheckcertificate':True,'user_agent':'Mozilla/5.0','extractor_args':{'youtube':{'player_client':['android','web']}}}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info=ydl.extract_info(url,download=True); dl=ydl.prepare_filename(info)
        return handle(dl,"✅ YouTube Done!")
    except Exception as e: return render_template_string(HTML,message=f"❌ YT: {e}",last_video=last["path"],last_music=last["music"])
@app.route("/make",methods=["POST"])
def make():
    p=request.form.get("video_path")
    if not p or not os.path.exists(p): return render_template_string(HTML,message="❌ Upload Video First!",last_video=last["path"],last_music=last["music"])
    try:
        duration=int(request.form.get("duration") or 30); num=int(request.form.get("num_clips") or 5)
        if num>30: num=30
        if duration>90: duration=90
        font_size=int(request.form.get("font_size") or 52); music_vol=int(request.form.get("music_volume") or 30)
        cap_mode=request.form.get("captions","live")
        words=get_segments(p) if cap_mode in ["live","on"] or request.form.get("find") else []
        total=get_duration(p) or duration*num; gap=total/num
        clips=[]
        for i in range(num):
            st=int(i*gap)
            if st+duration>total: st=int(max(0,total-duration))
            c=make_clip(p,st,duration,cap_mode,request.form.get("style","karaoke"),font_size,request.form.get("font_color","yellow"),request.form.get("hook_text",""),request.form.get("find",""),words,request.form.get("music","none"),last["music"],music_vol,request.form.get("effect","none"))
            clips.append(os.path.basename(c))
        msg=f"✅ {len(clips)} CLIPS READY - LIVE Subtitles + Music + Effects!"
        extra="<br><br>".join([f"<a href='/download/{c}'><button class='green'>⬇️ Clip {idx+1} - Download</button></a>" for idx,c in enumerate(clips)])
        return render_template_string(HTML,message=msg+"<br><br>"+extra,clip=clips[0],last_video=p,last_music=last["music"])
    except Exception as e: return render_template_string(HTML,message=f"❌ {e}",last_video=last["path"],last_music=last["music"])
@app.route("/edit",methods=["POST"])
def edit():
    name=request.form.get("clip_path"); inp=os.path.join(CLIPS_FOLDER,name)
    if not os.path.exists(inp): return render_template_string(HTML,message="❌ Clip Not Found!")
    try:
        ns=int(request.form.get("new_start") or 0); nd=int(request.form.get("new_duration") or 30); ef=int(request.form.get("edit_font") or 60)
        out=f"{CLIPS_FOLDER}/{uuid.uuid4().hex[:8]}_edited.mp4"; vf="scale=1080:1920"
        hk=clean(request.form.get("edit_hook","")); tx=clean(request.form.get("edit_text",""))
        if hk: vf+=f",drawtext=text='{hk}':fontcolor=white:fontsize={ef}:borderw=5:bordercolor=black:x=(w-text_w)/2:y=150"
        if tx: vf+=f",drawtext=text='{tx}':fontcolor=yellow:fontsize={ef-10}:borderw=4:bordercolor=black:x=(w-text_w)/2:y=h-250"
        cmd=["ffmpeg","-y","-ss",str(ns),"-i",inp,"-t",str(nd),"-vf",vf,"-c:v","libx264","-preset","ultrafast","-c:a","aac",out]
        subprocess.run(cmd,capture_output=True,timeout=300)
        return render_template_string(HTML,message=f"✅ EDIT DONE - {nd} Sec!",clip=os.path.basename(out),last_video=last["path"],last_music=last["music"])
    except Exception as e: return render_template_string(HTML,message=f"❌ Edit: {e}")
@app.route("/download/<name>")
def dl(name):
    path=os.path.join(CLIPS_FOLDER,name)
    return send_file(path,as_attachment=True) if os.path.exists(path) else ("Not found",404)
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
