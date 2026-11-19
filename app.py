import os
import uuid
import subprocess
from flask import Flask, render_template_string, request, send_file
import gdown
import yt_dlp

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
CLIPS_FOLDER = "clips"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CLIPS_FOLDER, exist_ok=True)

HTML = """
<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ClipShort PRO - Final</title>
<style>
body{background:#0f0a2e;color:white;font-family:Arial;padding:12px;text-align:center}
.card{background:#1e1650;padding:14px;border-radius:15px;margin:12px 0;text-align:left}
input,select{width:95%;padding:12px;border-radius:10px;border:none;margin:6px 0;color:black}
button{width:100%;padding:13px;border:none;border-radius:12px;font-weight:bold;cursor:pointer;margin-top:6px}
.green{background:#00c853;color:white}.blue{background:#2196F3;color:white}.red{background:#FF0000;color:white}.yellow{background:#FFD600;color:black}.purple{background:#9c27b0;color:white}
small{color:#bbb}
</style></head><body>
<h2>✂️ ClipShort PRO - FINAL</h2><p>Long Video -> 30 Clips -> Edit -> Download</p>

<div class="card"><h3>📤 1. Video - Upload / Drive / YouTube</h3>
<form action="/upload" method="post" enctype="multipart/form-data">
<input type="file" name="video"><button class="green" type="submit">Upload & Save Video</button></form>
<form action="/drive" method="post"><input name="drive_url" placeholder="Google Drive Link"><button class="blue" type="submit">📥 Download from Drive</button></form>
<form action="/youtube" method="post"><input name="yt_url" placeholder="YouTube Link"><button class="red" type="submit">▶️ Download from YouTube</button></form>
</div>

<div class="card"><h3>💬 2. Captions + Hook + Clips</h3>
<form action="/make" method="post">
<input type="hidden" name="video_path" value="{{ last_video or '' }}">
<label>Captions</label><select name="captions"><option value="on">ON ✅</option><option value="off">OFF</option></select>
<label>Caption Style</label><select name="style"><option value="karaoke">Karaoke ⭐</option><option value="wordcut">Word Cut</option><option value="handwritten">Handwritten</option></select>
<input name="negative" placeholder="Negative Keywords - Ex: umm, ah">
<label>Auto Hook</label><select name="hook"><option value="on">ON ✅</option><option value="off">OFF</option></select>
<input name="hook_text" placeholder="Hook Headline - Ex: He Said WHAT?">
<input name="find" placeholder="🔍 Find moments - Ex: playoffs">
<input name="duration" placeholder="Clip Length - Ex: 30" value="30">
<input name="num_clips" placeholder="How Many Clips? Max 30" value="5">
<button class="yellow" type="submit">✨ MAKE CLIPS - Max 30</button>
<small>Last Video: {{ last_video or 'No video yet' }}</small>
</form></div>

{% if clip %}
<div class="card"><h3>✏️ 3. EDIT CLIP</h3>
<form action="/edit" method="post">
<input type="hidden" name="clip_path" value="{{ clip }}">
<input name="new_start" placeholder="New Start Sec - Ex: 5" value="0">
<input name="new_duration" placeholder="New Duration - Ex: 15" value="30">
<input name="edit_text" placeholder="Text - Ex: Follow For More!">
<input name="edit_hook" placeholder="New Hook - Ex: Wait For End!">
<button class="purple" type="submit">✏️ SAVE EDITED CLIP</button>
</form></div>
{% endif %}

{% if message %}<div class="card"><h3>{{ message | safe }}</h3>
{% if clip %}<br><a href="/download/{{ clip }}"><button class="green">⬇️ Download Clip 1</button></a><br><br><video controls width="100%" src="/download/{{ clip }}"></video>{% endif %}
</div>{% endif %}
</body></html>
"""

def clean_text(t):
    return t.replace("'","").replace(":","").replace(",","").replace('"',"").replace("\\","").strip()

def get_duration(path):
    try:
        r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1", path], capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except:
        return 0

def get_segments(path):
    try:
        import whisper
        model = whisper.load_model("tiny")
        result = model.transcribe(path, fp16=False)
        return result.get("segments", [])
    except Exception as e:
        print("Whisper fail:", e)
        return []

def make_srt(segments, path):
    def fmt(t):
        h=int(t//3600); m=int((t%3600)//60); s=int(t%60); ms=int((t%1)*1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    with open(path,"w",encoding="utf-8") as f:
        for i,s in enumerate(segments):
            f.write(f"{i+1}\n{fmt(s['start'])} --> {fmt(s['end'])}\n{s['text'].strip()}\n\n")
    return path

def make_clip(input_path, start=0, duration=30, captions="on", style="karaoke", hook="on", hook_text="", negative="", find=""):
    out = f"{CLIPS_FOLDER}/{uuid.uuid4().hex[:8]}_clip.mp4"
    segments = []
    if captions=="on" or find:
        segments = get_segments(input_path)
    if find and segments:
        kw = find.lower()
        for s in segments:
            if kw in s.get("text","").lower():
                start = max(0, int(s.get("start", start)) - 1)
                break
    if negative and segments:
        negs=[x.strip().lower() for x in negative.split(",") if x.strip()]
        segments=[s for s in segments if not any(n in s["text"].lower() for n in negs)]
    vf = "crop=ih*9/16:ih,scale=1080:1920"
    srt_path=""
    if captions=="on" and segments:
        srt_path = f"{UPLOAD_FOLDER}/{uuid.uuid4().hex}.srt"
        make_srt(segments, srt_path)
        # ERROR FIX: srt path lo : undakudadu - escape cheyali
        srt_escaped = srt_path.replace(":","\\:")
        if style=="karaoke":
            st="FontSize=48,PrimaryColour=&H00FFFF&,OutlineColour=&H000000&,Bold=1,Alignment=2,MarginV=300"
        elif style=="handwritten":
            st="FontSize=52,PrimaryColour=&HFFFFFF&,OutlineColour=&HFF0000&,Bold=1,Alignment=2,MarginV=300"
        else:
            st="FontSize=48,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Bold=1,Alignment=2,MarginV=300"
        vf += f",subtitles='{srt_escaped}':force_style='{st}'"
    if hook=="on" and hook_text:
        safe = clean_text(hook_text)
        if safe:
            vf += f",drawtext=text='{safe}':fontcolor=white:fontsize=70:borderw=4:bordercolor=black:x=(w-text_w)/2:y=150"
    cmd=["ffmpeg","-y","-i",input_path,"-ss",str(start),"-t",str(duration),"-vf",vf,"-c:v","libx264","-preset","veryfast","-c:a","aac",out]
    subprocess.run(cmd, capture_output=True, timeout=600)
    return out

last_video_global={"path":""}

@app.route("/")
def home():
    return render_template_string(HTML, last_video=last_video_global["path"])

def handle_video(path, msg):
    last_video_global["path"]=path
    return render_template_string(HTML, message=msg, last_video=path)

@app.route("/upload", methods=["POST"])
def upload():
    f=request.files.get("video")
    if not f or f.filename=="":
        return render_template_string(HTML, message="❌ File ledu - File select cheyi!", last_video=last_video_global["path"])
    p=f"{UPLOAD_FOLDER}/{uuid.uuid4().hex}.mp4"
    f.save(p)
    return handle_video(p, "✅ Upload Done! Kindha Captions/Hook petti MAKE CLIPS nokku!")

@app.route("/drive", methods=["POST"])
def drive():
    url=request.form.get("drive_url","").strip()
    if not url:
        return render_template_string(HTML, message="❌ Drive Link ledu!")
    try:
        if "/d/" in url:
            fid=url.split("/d/")[1].split("/")[0]
        elif "id=" in url:
            fid=url.split("id=")[1].split("&")[0]
        else:
            fid=url
        p=f"{UPLOAD_FOLDER}/{uuid.uuid4().hex}.mp4"
        gdown.download(f"https://drive.google.com/uc?id={fid}", p, quiet=False)
        if not os.path.exists(p) or os.path.getsize(p) < 1000:
            return render_template_string(HTML, message="❌ Drive Error: Link Public cheyaledu! Drive > Share > Anyone with link!")
        return handle_video(p, "✅ Drive Download Done! Kindha MAKE CLIPS nokku!")
    except Exception as e:
        return render_template_string(HTML, message=f"❌ Drive Error: {e}")

@app.route("/youtube", methods=["POST"])
def youtube():
    url=request.form.get("yt_url","").strip()
    if not url:
        return render_template_string(HTML, message="❌ YouTube Link ledu!")
    try:
        tmpl=f"{UPLOAD_FOLDER}/{uuid.uuid4().hex}.%(ext)s"
        opts={'format':'best[height<=720][ext=mp4]/best[ext=mp4]/best','outtmpl':tmpl,'quiet':True,'nocheckcertificate':True,'user_agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)','extractor_args':{'youtube':{'player_client':['android','web']}}}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info=ydl.extract_info(url, download=True)
            dl=ydl.prepare_filename(info)
        return handle_video(dl, "✅ YouTube Download Done! Kindha MAKE CLIPS nokku!")
    except Exception as e:
        return render_template_string(HTML, message=f"❌ YouTube Error: {e}")

@app.route("/make", methods=["POST"])
def make():
    p=request.form.get("video_path")
    if not p or not os.path.exists(p):
        return render_template_string(HTML, message="❌ Mundhu Video Upload / Drive / YouTube cheyi!")
    try:
        duration=int(request.form.get("duration") or 30)
        num_clips=int(request.form.get("num_clips") or 1)
        if num_clips > 30: num_clips=30
        if num_clips < 1: num_clips=1
        if duration < 5: duration=5
        if duration > 90: duration=90
        total = get_duration(p)
        if total <= 0:
            total = duration * num_clips
        gap = total / num_clips if total>0 else duration
        clips_list=[]
        for i in range(num_clips):
            start_time=int(i*gap)
            if start_time + duration > total:
                start_time=int(max(0, total-duration))
            clip=make_clip(p, start=start_time, duration=duration,
                captions=request.form.get("captions","on"), style=request.form.get("style","karaoke"),
                hook=request.form.get("hook","on"), hook_text=request.form.get("hook_text",""),
                negative=request.form.get("negative",""), find=request.form.get("find",""))
            clips_list.append(os.path.basename(clip))
        msg=f"✅ LONG VIDEO - {len(clips_list)} CLIPS READY! Total: {int(total//60)} Mins!"
        html_extra="<br><br>".join([f"<a href='/download/{c}'><button class='green'>⬇️ Download Clip {idx+1}</button></a>" for idx,c in enumerate(clips_list)])
        return render_template_string(HTML, message=msg+"<br><br>"+html_extra, clip=clips_list[0], last_video=p)
    except Exception as e:
        return render_template_string(HTML, message=f"❌ Error: {e}")

@app.route("/edit", methods=["POST"])
def edit_clip():
    clip_name=request.form.get("clip_path")
    if not clip_name:
        return render_template_string(HTML, message="❌ Clip ledu!")
    input_clip=os.path.join(CLIPS_FOLDER, clip_name)
    if not os.path.exists(input_clip):
        return render_template_string(HTML, message="❌ Clip dorakaledu!")
    try:
        new_start=int(request.form.get("new_start") or 0)
        new_duration=int(request.form.get("new_duration") or 30)
        edit_text=clean_text(request.form.get("edit_text",""))
        edit_hook=clean_text(request.form.get("edit_hook",""))
        out=f"{CLIPS_FOLDER}/{uuid.uuid4().hex[:8]}_edited.mp4"
        vf="scale=1080:1920"
        if edit_hook:
            vf+=f",drawtext=text='{edit_hook}':fontcolor=white:fontsize=70:borderw=5:bordercolor=black:x=(w-text_w)/2:y=150"
        if edit_text:
            vf+=f",drawtext=text='{edit_text}':fontcolor=yellow:fontsize=55:borderw=4:bordercolor=black:x=(w-text_w)/2:y=h-250"
        cmd=["ffmpeg","-y","-i",input_clip,"-ss",str(new_start),"-t",str(new_duration),"-vf",vf,"-c:v","libx264","-preset","veryfast","-c:a","aac",out]
        subprocess.run(cmd, capture_output=True, timeout=300)
        return render_template_string(HTML, message=f"✅ EDIT DONE! {new_duration} Sec New Clip!", clip=os.path.basename(out), last_video="")
    except Exception as e:
        return render_template_string(HTML, message=f"❌ Edit Error: {e}")

@app.route("/download/<name>")
def download(name):
    path=os.path.join(CLIPS_FOLDER, name)
    if not os.path.exists(path):
        return "File not found", 404
    return send_file(path, as_attachment=True)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
