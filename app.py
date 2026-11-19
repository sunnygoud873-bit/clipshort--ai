# app.py - ALL IN ONE - ClipShort.com Style
# Files needed: app.py + requirements.txt + Procfile - Anthe!
# Run: python app.py -> http://localhost:5000

from flask import Flask, request, jsonify, send_file
import os, re, subprocess, tempfile, uuid
import imageio_ffmpeg

app = Flask(__name__)
os.makedirs("uploads", exist_ok=True)
os.makedirs("outputs", exist_ok=True)
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

CAPTION_COLOURS = {"Yellow":"&H00FFFF&","White":"&HFFFFFF&","Cyan":"&HFFFF00&","Pink":"&HFF00FF&","Green":"&H00FF00&","Orange":"&H0080FF&","Red":"&H0000FF&"}

HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>ClipShort.com - Viral Shorts Maker</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:'Segoe UI',system-ui,sans-serif}
body{background:#0f0c29;color:white;min-height:100vh}
header{background:rgba(255,255,255,.08);padding:14px 20px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:10}
.logo{font-size:22px;font-weight:900}.logo span{color:#DD2476}
nav a{color:#ccc;text-decoration:none;margin-left:18px;font-size:14px}
.hero{text-align:center;padding:36px 16px 10px}
.hero h1{font-size:42px;line-height:1.1}.hero h1 span{background:linear-gradient(90deg,#DD2476,#FF512F);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hero p{color:#bbb;margin-top:10px}
.container{max-width:720px;margin:20px auto;padding:0 14px 60px}
.card{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);border-radius:20px;padding:18px;margin:14px 0}
.card h3{margin-bottom:12px}
.upload-box{border:2px dashed #DD2476;border-radius:16px;padding:28px;text-align:center;cursor:pointer;background:rgba(221,36,118,.08);display:block}
.upload-box input{display:none}
label{font-size:13px;color:#ccc;display:block;margin:12px 0 6px}
input[type=text],select{width:100%;padding:12px;border-radius:12px;border:2px solid #DD2476;outline:none;font-weight:600}
input[type=range]{width:100%;accent-color:#DD2476}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.colour-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.colour-btn{width:44px;height:44px;border-radius:50%;border:3px solid transparent;cursor:pointer}
.colour-btn.active{border-color:white;transform:scale(1.1)}
.preview{height:52px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:20px;color:#000;margin-top:10px;border:2px solid white}
.btn{width:100%;padding:16px;border:none;border-radius:50px;background:linear-gradient(90deg,#DD2476,#FF512F);color:white;font-size:17px;font-weight:800;cursor:pointer;margin-top:16px}
.btn:disabled{opacity:.6}
.progress{display:none;text-align:center;padding:20px}
.spinner{width:40px;height:40px;border:4px solid #333;border-top:4px solid #DD2476;border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 10px}
@keyframes spin{to{transform:rotate(360deg)}}
.result{display:none}
video{width:100%;border-radius:16px;margin-top:12px;max-height:520px;background:#000}
.download{display:block;text-align:center;background:#00C853;color:white;padding:14px;border-radius:12px;text-decoration:none;font-weight:700;margin-top:12px}
@media(max-width:600px){.hero h1{font-size:30px}.row{grid-template-columns:1fr}header nav{display:none}}
</style></head>
<body>
<header><div class="logo">✂️ ClipShort<span>.com</span></div><nav><a href="#">Home</a><a href="#">Features</a><a href="#">Pricing</a></nav></header>
<div class="hero"><h1>Turn Any Video Into<br><span>Viral Shorts</span></h1><p>Just like Opus Clip - Auto Captions, Music, Effects in 1 Click</p></div>
<div class="container">
<form id="form">
<div class="card"><h3>1. Upload Your Video</h3><label class="upload-box">📁 Click to Upload Video<input type="file" id="video" accept="video/*" required><div id="fileName">No file selected</div></label></div>
<div class="card"><h3>2. Clip Settings</h3><label>Clip Length - <span id="lenVal">30</span> Sec</label><input type="range" id="clip_len" min="15" max="60" value="30"><label>Caption Text</label><input type="text" id="caption_text" value="FOLLOW FOR MORE"></div>
<div class="card"><h3>3. Captions - Colour</h3><label>Caption Colour</label><div class="colour-row" id="colours"></div><div class="preview" id="preview">FOLLOW FOR MORE</div><div class="row"><div><label>Font Size - <span id="fontVal">22</span></label><input type="range" id="font_size" min="14" max="48" value="22"></div><div><label>Effect</label><select id="effect"><option>Vibrant</option><option>Cinematic</option><option>Black and White</option><option>No Effect</option></select></div></div></div>
<div class="card"><h3>4. Music (Optional)</h3><label class="upload-box">🎵 Upload MP3<input type="file" id="music" accept="audio/*"><div id="musicName">No music</div></label></div>
<button class="btn" type="submit" id="genBtn">✨ Generate Viral Clip</button>
</form>
<div class="progress" id="progress"><div class="spinner"></div><p>Generating... Burning Subtitles...</p></div>
<div class="card result" id="result"><h3>✅ Your Clip Ready!</h3><p id="subInfo"></p><video id="vid" controls playsinline></video><a class="download" id="dl" href="#" download>⬇️ Download Clip</a></div>
</div>
<script>
const cols={Yellow:'#FFE600',White:'#FFFFFF',Cyan:'#00E5FF',Pink:'#FF00AA',Green:'#00FF00',Orange:'#FF8000',Red:'#FF0000'};
let sel='Yellow'; const wrap=document.getElementById('colours');
Object.keys(cols).forEach(k=>{const b=document.createElement('div'); b.className='colour-btn'+(k==='Yellow'?' active':''); b.style.background=cols[k]; b.title=k; b.onclick=()=>{sel=k; document.querySelectorAll('.colour-btn').forEach(x=>x.classList.remove('active')); b.classList.add('active'); updatePreview();}; wrap.appendChild(b);});
function updatePreview(){const p=document.getElementById('preview'); p.style.background=cols[sel]; p.textContent=document.getElementById('caption_text').value.toUpperCase()+' - '+sel;}
document.getElementById('caption_text').addEventListener('input',updatePreview); updatePreview();
document.getElementById('video').addEventListener('change',e=>{document.getElementById('fileName').textContent=e.target.files[0]?.name||'No file';});
document.getElementById('music').addEventListener('change',e=>{document.getElementById('musicName').textContent=e.target.files[0]?.name||'No music';});
document.getElementById('clip_len').addEventListener('input',e=>document.getElementById('lenVal').textContent=e.target.value);
document.getElementById('font_size').addEventListener('input',e=>document.getElementById('fontVal').textContent=e.target.value);
document.getElementById('form').addEventListener('submit',async e=>{e.preventDefault(); const fd=new FormData(); fd.append('video',document.getElementById('video').files[0]); const m=document.getElementById('music').files[0]; if(m) fd.append('music',m); fd.append('caption_text',document.getElementById('caption_text').value); fd.append('caption_color',sel); fd.append('clip_len',document.getElementById('clip_len').value); fd.append('font_size',document.getElementById('font_size').value); fd.append('effect',document.getElementById('effect').value); document.getElementById('progress').style.display='block'; document.getElementById('result').style.display='none'; document.getElementById('genBtn').disabled=true; document.getElementById('genBtn').textContent='Generating...'; try{const r=await fetch('/generate',{method:'POST',body:fd}); const d=await r.json(); if(d.success){const c=d.clips[0]; document.getElementById('vid').src=c.url; document.getElementById('dl').href=c.url; document.getElementById('subInfo').textContent='Subtitles: '+c.subtitles+' - Burned'; document.getElementById('result').style.display='block';} else alert('Error: '+d.error);}catch(err){alert('Failed: '+err);} document.getElementById('progress').style.display='none'; document.getElementById('genBtn').disabled=false; document.getElementById('genBtn').textContent='✨ Generate Viral Clip';});
</script></body></html>"""

def fmt_ass_time(t):
    h=int(t//3600); m=int((t%3600)//60); s=int(t%60); cs=int((t%1)*100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def split_lines(txt, max_words=2):
    words=txt.upper().split()
    return [" ".join(words[j:j+max_words]) for j in range(0,len(words),max_words)]

def write_ass(ass_path, segments, font_size, colour):
    h="[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
    h+=f"Style: Default,Arial Black,{font_size},{colour},&HFFFFFF&,&H80000000&,&H80000000&,-1,0,0,0,100,100,0,0,3,2,1,2,130,130,300,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    b=""
    for s,e,txt in segments:
        b+=f"Dialogue: 0,{fmt_ass_time(s)},{fmt_ass_time(e)},Default,,0,0,0,,{txt.replace(',',' ').replace(':',' ')}\n"
    open(ass_path,"w",encoding="utf-8").write(h+b)

def get_duration(path):
    res=subprocess.run([FFMPEG,"-i",path],capture_output=True,text=True)
    m=re.search(r"Duration: (\d+):(\d+):(\d+)",res.stderr)
    return int(m.group(1))*3600+int(m.group(2))*60+int(m.group(3)) if m else 0

@app.route("/")
def home():
    return HTML

@app.route("/generate", methods=["POST"])
def generate():
    try:
        video=request.files.get("video")
        if not video: return jsonify({"error":"No video"}),400
        caption_text=request.form.get("caption_text","FOLLOW FOR MORE")
        caption_color=request.form.get("caption_color","Yellow")
        clip_len=int(request.form.get("clip_len",30))
        font_size=int(request.form.get("font_size",22))
        effect=request.form.get("effect","Vibrant")
        music=request.files.get("music")
        uid=str(uuid.uuid4())[:8]
        in_path=os.path.join("uploads",f"{uid}_{video.filename}")
        video.save(in_path)
        total=get_duration(in_path)
        if total==0: return jsonify({"error":"Could not read video"}),400
        music_path=None
        if music and music.filename!="":
            music_path=os.path.join("uploads",f"{uid}_music.mp3")
            music.save(music_path)
        eff=",eq=contrast=1.15:saturation=1.4:brightness=0.05" if effect=="Vibrant" else ",eq=contrast=1.2:brightness=-0.05:saturation=1.1" if effect=="Cinematic" else ",hue=s=0,eq=contrast=1.1" if effect=="Black and White" else ""
        start=total//2; dur=min(clip_len,total-start)
        tmpdir=tempfile.mkdtemp()
        ass_path=os.path.join(tmpdir,"subs.ass")
        ass_esc=ass_path.replace("\\","/").replace(":","\\:").replace("'","\\'")
        colour=CAPTION_COLOURS.get(caption_color,"&H00FFFF&")
        audio_path=os.path.join(tmpdir,"audio.wav")
        subprocess.run([FFMPEG,"-y","-ss",str(start),"-t",str(dur),"-i",in_path,"-vn","-ac","1","-ar","16000",audio_path],capture_output=True)
        segments=[]; whisper_ok=False
        try:
            import whisper
            model=whisper.load_model("tiny")
            result=model.transcribe(audio_path,fp16=False)
            if result.get("segments"):
                for seg in result["segments"]:
                    txt=seg["text"].strip()
                    if not txt: continue
                    segments.append((seg["start"],seg["end"],"\\N".join(split_lines(txt,2))))
                if segments: whisper_ok=True
        except: whisper_ok=False
        if not whisper_ok or not segments:
            lines=split_lines(caption_text,2)
            chunk=max(4,dur/max(1,len(lines)))
            for idx,ln in enumerate(lines):
                s=idx*chunk; e=min(dur,s+chunk)
                if s<dur: segments.append((s,e,ln))
            if not segments: segments.append((0,dur,"\\N".join(lines)))
        write_ass(ass_path,segments,font_size,colour)
        vf="crop=ih*9/16:ih,scale=1080:1920:force_original_aspect_ratio=disable"+eff+",subtitles='"+ass_esc+"'"
        out_name=f"clip_{uid}.mp4"; out_path=os.path.join("outputs",out_name)
        if music_path:
            af="[0:a]volume=1.0[a0];[1:a]volume=0.2[a1];[a0][a1]amix=inputs=2:duration=first[aout]"
            cmd=[FFMPEG,"-y","-ss",str(start),"-t",str(dur),"-i",in_path,"-stream_loop","-1","-i",music_path,"-vf",vf,"-filter_complex",af,"-map","0:v","-map","[aout]","-c:v","libx264","-c:a","aac","-preset","fast","-crf","23","-shortest",out_path]
        else:
            cmd=[FFMPEG,"-y","-ss",str(start),"-t",str(dur),"-i",in_path,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","fast","-crf","23",out_path]
        subprocess.run(cmd,capture_output=True)
        if os.path.exists(out_path):
            return jsonify({"success":True,"clips":[{"name":out_name,"url":f"/download/{out_name}","subtitles":f"{len(segments)} lines"}]})
        return jsonify({"error":"Failed"}),500
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.route("/download/<name>")
def download(name):
    return send_file(os.path.join("outputs",name),as_attachment=True)

if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
