import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import streamlit as st
import subprocess
import tempfile
import shutil
import re
import gc
import wave
import requests
from pathlib import Path
from urllib.parse import urlparse, parse_qs

st.set_page_config(page_title="CLIPSHORT AI", page_icon="🎬", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
.block-container{max-width:1280px;padding-top:1rem;padding-bottom:2rem}
.stButton>button{width:100%;border-radius:10px;min-height:44px;font-size:15px}
.stDownloadButton>button{width:100%;border-radius:10px;min-height:44px}
video{width:100%!important;border-radius:12px}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1>🎬 CLIPSHORT AI</h1><p>Clipper + YouTube Downloader + Instagram Downloader + MP3</p>", unsafe_allow_html=True)

if "preview_done" not in st.session_state:
    st.session_state.preview_done = False
if "preview_bytes" not in st.session_state:
    st.session_state.preview_bytes = None
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "CLIPPER"

def run_cmd(cmd_list):
    result = subprocess.run(cmd_list, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout)[-1200:])
    return result.stdout.strip()

def check_ffmpeg():
    return shutil.which("ffmpeg") is not None

def get_duration(path):
    try:
        out = run_cmd(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
        return float(out)
    except Exception:
        return 0.0

def has_audio(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return bool(result.stdout.strip())

def get_mime(path):
    s = str(path).lower()
    if s.endswith(".mp3"):
        return "audio/mp3"
    if s.endswith(".webm"):
        return "video/webm"
    if s.endswith(".mkv"):
        return "video/x-matroska"
    if s.endswith(".jpg") or s.endswith(".jpeg"):
        return "image/jpeg"
    if s.endswith(".png"):
        return "image/png"
    if s.endswith(".webp"):
        return "image/webp"
    return "video/mp4"

def convert_to_mp3(video_path, folder):
    mp3_path = folder / (video_path.stem + ".mp3")
    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-c:a", "libmp3lame", "-q:a", "2", str(mp3_path)]
    subprocess.run(cmd, capture_output=True, text=True)
    if not mp3_path.exists() or mp3_path.stat().st_size < 1000:
        raise RuntimeError("MP3 convert failed")
    return mp3_path

def clean_insta_url(url):
    u = url.strip().split("?")[0].split("&")[0]
    m = re.search(r"/(reel|reels|p)/([A-Za-z0-9_-]+)", u)
    if m:
        return "https://www.instagram.com/reel/" + m.group(2) + "/"
    return u + "/" if not u.endswith("/") else u

def get_video_id(url):
    u = url.strip()
    if "youtu.be/" in u:
        return u.split("youtu.be/")[-1].split("?")[0].split("&")[0].split("/")[0]
    q = parse_qs(urlparse(u).query)
    if "v" in q:
        return q["v"][0].split("&")[0]
    for pat in [r"/shorts/([A-Za-z0-9_-]{11})", r"/live/([A-Za-z0-9_-]{11})", r"/embed/([A-Za-z0-9_-]{11})", r"/v/([A-Za-z0-9_-]{11})"]:
        m = re.search(pat, u)
        if m:
            return m.group(1)
    m = re.search(r"([A-Za-z0-9_-]{11})(?:[?&#/]|$)", u)
    if m and ("youtube" in u or "youtu" in u or "sos" in u or "ssyoutube" in u):
        return m.group(1)
    return None

def clean_yt_url(url):
    vid = get_video_id(url.strip())
    if vid:
        return "https://www.youtube.com/watch?v=" + vid, vid
    return url.strip(), None

def get_drive_id(url):
    parsed = urlparse(url.strip())
    m = re.search(r"/file/d/([A-Za-z0-9_-]+)", parsed.path)
    if m:
        return m.group(1)
    q = parse_qs(parsed.query)
    if q.get("id"):
        return q["id"][0]
    raise ValueError("Invalid Drive link")

def download_drive(url, folder):
    fid = get_drive_id(url)
    target = folder / "drive_video.mp4"
    s = requests.Session()
    r = s.get("https://drive.google.com/uc?export=download&id=" + fid + "&confirm=t", stream=True, timeout=120)
    with open(target, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024 * 2):
            if chunk:
                f.write(chunk)
    if not target.exists() or target.stat().st_size < 10000:
        raise RuntimeError("Drive failed. Set Anyone with link to Viewer")
    return target

COBALT_INSTANCES = [
    "https://co.wuk.sh/",
    "https://cobalt-backend.canine.tools/",
    "https://cobalt-api.kavin.rocks/"
]

def download_from_url(vurl, folder, name):
    target = folder / name
    with requests.get(vurl, stream=True, timeout=180, headers={"User-Agent": "Mozilla/5.0"}) as dl:
        dl.raise_for_status()
        with open(target, "wb") as f:
            for chunk in dl.iter_content(chunk_size=1024 * 1024 * 2):
                if chunk:
                    f.write(chunk)
    if target.exists() and target.stat().st_size > 10000:
        return target
    raise RuntimeError("Empty file from server")

def download_via_cobalt(url, folder, filename="cobalt_video.mp4"):
    last_err = "unknown"
    for base in COBALT_INSTANCES:
        try:
            r = requests.post(base, json={"url": url.strip(), "videoQuality": "720", "filenameStyle": "basic"}, headers={"Accept": "application/json", "Content-Type": "application/json"}, timeout=30)
            if r.status_code != 200:
                last_err = str(base) + " status " + str(r.status_code)
                continue
            data = r.json()
            vurl = data.get("url")
            if not vurl:
                last_err = str(base) + " no url"
                continue
            return download_from_url(vurl, folder, filename)
        except Exception as e:
            last_err = str(e)
            continue
    raise RuntimeError("Cobalt failed: " + last_err)

def download_via_cobalt_quality(url, folder, quality, filename="cobalt_video.mp4"):
    for base in COBALT_INSTANCES:
        try:
            r = requests.post(base, json={"url": url.strip(), "videoQuality": quality, "filenameStyle": "basic"}, headers={"Accept": "application/json", "Content-Type": "application/json"}, timeout=30)
            if r.status_code != 200:
                continue
            data = r.json()
            vurl = data.get("url")
            if not vurl:
                continue
            return download_from_url(vurl, folder, filename)
        except Exception:
            continue
    raise RuntimeError("Cobalt quality fail")

def download_youtube(url, folder, want_mp3=False, quality="Auto"):
    clean_url, vid = clean_yt_url(url)
    if not vid:
        raise RuntimeError("Invalid YouTube link. Paste youtube / youtu.be / sosyoutube link")
    if quality == "Auto":
        q_list = ["1080", "720", "480", "360", "240", "144"]
    else:
        q_clean = quality.replace("p", "").strip()
        q_list = [q_clean, "720", "480", "360", "240", "144"]
    try:
        r = requests.get("https://yt.lemnoslife.com/videos?part=player,snippet&id=" + vid, timeout=20)
        if r.status_code == 200:
            d = r.json()
            items = d.get("items", [])
            if items:
                player = items[0].get("player", {})
                streams = player.get("streamingData", {})
                fmts = streams.get("formats", []) + streams.get("adaptiveFormats", [])
                if fmts:
                    if want_mp3:
                        audios = [x for x in fmts if "audio" in x.get("mimeType", "")]
                        if audios:
                            vpath = download_from_url(audios[0]["url"], folder, "youtube_audio.webm")
                            return convert_to_mp3(vpath, folder)
                    mp4s = [x for x in fmts if "mp4" in x.get("mimeType", "")]
                    if not mp4s:
                        mp4s = fmts
                    target_h = int(q_list[0]) if q_list[0].isdigit() else 720
                    mp4s = sorted(mp4s, key=lambda x: abs(int(x.get("height", 720)) - target_h))
                    return download_from_url(mp4s[0]["url"], folder, "youtube_video.mp4")
    except Exception as e:
        print("Lemnos fail", e)
    for q in q_list:
        try:
            vid_path = download_via_cobalt_quality(clean_url, folder, q, "youtube_video.mp4")
            if vid_path:
                if want_mp3:
                    return convert_to_mp3(vid_path, folder)
                return vid_path
        except Exception:
            continue
    for inv in ["https://inv.nadeko.net", "https://invidious.0011.lt", "https://iv.datura.network", "https://invidious.reallyaweso.me", "https://vid.puffyan.us"]:
        try:
            r = requests.get(inv + "/api/v1/videos/" + vid, timeout=15)
            if r.status_code != 200:
                continue
            d = r.json()
            if want_mp3:
                streams = d.get("adaptiveFormats", [])
                audios = [x for x in streams if "audio" in x.get("type", "")]
                if audios:
                    vpath = download_from_url(audios[0]["url"], folder, "youtube_audio.webm")
                    return convert_to_mp3(vpath, folder)
            streams = d.get("formatStreams", [])
            if streams:
                vid_path = download_from_url(streams[0]["url"], folder, "youtube_video.mp4")
                if want_mp3:
                    return convert_to_mp3(vid_path, folder)
                return vid_path
        except Exception:
            continue
    for host in ["https://pipedapi.kavin.rocks", "https://pipedapi-libre.kavin.rocks", "https://pipedapi.adminforge.de", "https://pipedapi.leptons.xyz"]:
        try:
            r = requests.get(host + "/streams/" + vid, timeout=15)
            if r.status_code != 200:
                continue
            d = r.json()
            cand = [s for s in d.get("videoStreams", []) if "mp4" in s.get("mimeType", "")]
            if not cand:
                cand = d.get("videoStreams", [])
            if not cand:
                continue
            target_h = int(q_list[0]) if q_list[0].isdigit() else 720
            cand = sorted(cand, key=lambda x: abs(int(str(x.get("quality", "720")).replace("p", "")) - target_h))
            vid_path = download_from_url(cand[0]["url"], folder, "youtube_video.mp4")
            if want_mp3:
                return convert_to_mp3(vid_path, folder)
            return vid_path
        except Exception:
            continue
    try:
        import yt_dlp
        if want_mp3:
            opts = {"format": "bestaudio/best", "outtmpl": str(folder / "youtube_audio.%(ext)s"), "noplaylist": True, "quiet": True, "no_warnings": True, "retries": 3, "socket_timeout": 30, "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]}
        else:
            if quality == "Auto":
                fmt = "best[ext=mp4]/best"
            else:
                h = q_list[0]
                fmt = f"best[height<={h}][ext=mp4]/best[height<={h}]/best"
            opts = {"format": fmt, "outtmpl": str(folder / "youtube_video.%(ext)s"), "noplaylist": True, "quiet": True, "no_warnings": True, "retries": 3, "socket_timeout": 30, "extractor_args": {"youtube": {"player_client": ["mweb", "ios", "tv"]}}}
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([clean_url])
        if want_mp3:
            files = list(folder.glob("youtube_audio.mp3"))
        else:
            files = [f for f in folder.glob("youtube_video.*") if f.suffix.lower() in [".mp4", ".webm", ".mkv"]]
        if files and files[0].stat().st_size > 10000:
            return files[0]
    except Exception as e:
        print("yt-dlp fail", e)
    raise RuntimeError("YouTube failed on all servers. Try again after 2 mins")

def download_instagram(url, folder, want_mp3=False):
    clean = clean_insta_url(url)
    if "instagram.com" not in clean and "instagr.am" not in clean:
        raise RuntimeError("Invalid Instagram link")
    m = re.search(r"/reel/([A-Za-z0-9_-]+)", clean)
    shortcode = m.group(1) if m else None
    try:
        vid_path = download_via_cobalt(clean, folder, "insta_video.mp4")
        if want_mp3:
            return convert_to_mp3(vid_path, folder)
        return vid_path
    except Exception as e:
        print("Insta cobalt fail", e)
    if shortcode:
        for mirror in ["https://www.ddinstagram.com", "https://d.ddinstagram.com", "https://www.vxinstagram.com"]:
            try:
                r = requests.get(mirror + "/reel/" + shortcode + "/", headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"}, timeout=20)
                if r.status_code != 200:
                    continue
                vm = re.search(r'https://[^"]+\.mp4[^"]*', r.text)
                if vm:
                    vurl = vm.group(0).replace("&amp;", "&")
                    try:
                        vid_path = download_from_url(vurl, folder, "insta_video.mp4")
                        if want_mp3:
                            return convert_to_mp3(vid_path, folder)
                        return vid_path
                    except Exception:
                        continue
                im = re.search(r'https://[^"]+\.jpg[^"]*', r.text)
                if im and not want_mp3:
                    try:
                        return download_from_url(im.group(0).replace("&amp;", "&"), folder, "insta_image.jpg")
                    except Exception:
                        continue
            except Exception:
                continue
    try:
        import yt_dlp
        if want_mp3:
            opts = {"format": "bestaudio/best", "outtmpl": str(folder / "insta_audio.%(ext)s"), "noplaylist": True, "quiet": True, "no_warnings": True, "retries": 3, "socket_timeout": 30, "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]}
        else:
            opts = {"format": "best[ext=mp4]/best", "outtmpl": str(folder / "insta_video.%(ext)s"), "noplaylist": True, "quiet": True, "no_warnings": True, "retries": 3, "socket_timeout": 30}
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([clean])
        if want_mp3:
            files = list(folder.glob("insta_audio.mp3"))
        else:
            files = [f for f in folder.glob("insta_video.*") if f.suffix.lower() in [".mp4", ".webm", ".mkv", ".jpg", ".png"]]
        if files and files[0].stat().st_size > 1000:
            return files[0]
    except Exception as e:
        print("Insta yt-dlp fail", e)
    try:
        r = requests.get(clean + "embed/", headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        vm = re.search(r'https://[^"]+\.mp4[^"]*', r.text)
        if vm:
            vurl = vm.group(0).replace("&amp;", "&")
            vid_path = download_from_url(vurl, folder, "insta_video.mp4")
            if want_mp3:
                return convert_to_mp3(vid_path, folder)
            return vid_path
    except Exception:
        pass
    raise RuntimeError("Instagram failed. Paste clean link: https://www.instagram.com/reel/Dfqu4ikT61P/")

def get_highlight_scores(video_path, total):
    try:
        import numpy as np
        ap = Path(str(video_path) + "_audio.wav")
        subprocess.run(["ffmpeg", "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(ap)], capture_output=True)
        if not ap.exists() or ap.stat().st_size < 1000:
            return None
        with wave.open(str(ap), "rb") as wf:
            n = wf.getnframes()
            rate = wf.getframerate()
            data = wf.readframes(n)
        audio = np.frombuffer(data, dtype=np.int16).astype(float) / 32768.0
        if len(audio) == 0:
            return None
        scores = []
        for i in range(int(total)):
            s = i * rate
            e = min((i + 1) * rate, len(audio))
            if e <= s:
                scores.append(0.0)
                continue
            ch = audio[s:e]
            rms = float(np.sqrt(np.mean(ch ** 2))) if len(ch) > 0 else 0
            peak = float(np.max(np.abs(ch))) if len(ch) > 0 else 0
            scores.append(rms * 0.7 + peak * 0.3)
        sm = []
        for i in range(len(scores)):
            v = scores[max(0, i - 1):min(len(scores), i + 2)]
            sm.append(sum(v) / len(v))
        if ap.exists():
            ap.unlink()
        return sm
    except Exception as e:
        print(e)
        return None

def choose_highlight_starts(scores, total, length, count, ts, te):
    if scores is None:
        return None
    cands = []
    start = ts
    step = 2.0
    while start + length <= te:
        si = int(start)
        ei = int(min(start + length, len(scores)))
        sc = sum(scores[si:ei]) if ei > si else 0
        if ei > si:
            sc = sc + max(scores[si:ei]) * 2.0
        cands.append((sc, start))
        start = start + step
    cands.sort(key=lambda x: x[0], reverse=True)
    sel = []
    for item in cands:
        s = item[1]
        ok = True
        for p in sel:
            if abs(s - p) < length * 0.65:
                ok = False
        if ok:
            sel.append(s)
        if len(sel) >= count:
            break
    if sel:
        return sorted(sel)
    return [ts]

def choose_normal_starts(total, length, count, ts, te):
    avail = te - ts
    if avail <= length:
        return [ts]
    if avail >= count * length:
        out = []
        for i in range(count):
            out.append(ts + i * length)
        return out
    if count == 1:
        return [ts + avail / 2 - length / 2]
    step = (avail - length) / (count - 1)
    out = []
    for i in range(count):
        out.append(ts + i * step)
    return out

RATIOS = {"9:16 - Shorts / Reels": (1080, 1920), "16:9 - YouTube": (1920, 1080), "1:1 - Post": (1080, 1080), "4:5 - Portrait": (1080, 1350)}
RESOLUTIONS = {"480p - Fast": 480, "720p - HD": 720, "1080p - Full HD": 1080}

def get_output_size(rl, resl):
    bw, bh = RATIOS[rl]
    t = RESOLUTIONS[resl]
    if bw <= bh:
        w = t
        h = int(bh * (t / bw))
    else:
        h = t
        w = int(bw * (t / bh))
    return w - (w % 2), h - (h % 2)

def build_effect_filter(cfg, length):
    f = []
    eff = cfg["effect"]
    b = cfg["brightness"]
    c = cfg["contrast"]
    s = cfg["saturation"]
    if eff == "Cinematic - Dark + Warm":
        b = b - 0.05
        c = c + 0.15
        s = s - 0.10
        f.append("curves=r='0/0 0.5/0.45 1/1':g='0/0 0.5/0.5 1/1':b='0/0 0.5/0.55 1/0.95'")
    elif eff == "Vivid - Color Pop":
        b = b + 0.05
        c = c + 0.20
        s = s + 0.40
    elif eff == "Black & White":
        s = 0.0
        c = c + 0.10
    elif eff == "Vintage - Old Film":
        b = b + 0.05
        c = c - 0.05
        s = s - 0.20
        f.append("noise=alls=6:allf=t")
    elif eff == "Warm - Golden":
        f.append("colorbalance=rs=0.15:gs=0.05:bs=-0.15")
    elif eff == "Cool - Blue":
        f.append("colorbalance=rs=-0.10:gs=0.0:bs=0.15")
    f.append(f"eq=brightness={b:.2f}:contrast={c:.2f}:saturation={s:.2f}")
    if cfg["sharpen"] > 0:
        f.append(f"unsharp=5:5:{cfg['sharpen']:.1f}:5:5:0.0")
    if cfg["blur"] > 0:
        f.append(f"gblur=sigma={cfg['blur']:.1f}")
    if cfg["fade_in"]:
        f.append("fade=t=in:st=0:d=0.8")
    if cfg["fade_out"]:
        f.append(f"fade=t=out:st={max(0, length - 0.8):.1f}:d=0.8")
    return f

def render_clip(source, output, start, length, cfg, music):
    args = ["ffmpeg", "-y", "-threads", "1", "-ss", str(start), "-i", str(source)]
    if music:
        args = args + ["-stream_loop", "-1", "-i", str(music)]
    fl = [f"scale={cfg['out_w']}:{cfg['out_h']}:force_original_aspect_ratio=increase", f"crop={cfg['out_w']}:{cfg['out_h']}", "setsar=1"]
    if cfg["speed"] != 1.0:
        fl.append(f"setpts={1.0 / cfg['speed']:.3f}*PTS")
    fl = fl + build_effect_filter(cfg, length)
    fl.append("fps=30")
    args = args + ["-t", str(length), "-vf", ",".join(fl), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-threads", "1", "-pix_fmt", "yuv420p"]
    sa = has_audio(source)
    if cfg["speed"] != 1.0:
        at = f"atempo={cfg['speed']:.2f},"
    else:
        at = ""
    if music and sa:
        args = args + ["-filter_complex", f"[0:a]{at}volume={cfg['source_volume']}[a0];[1:a]volume={cfg['music_volume']}[a1];[a0][a1]amix=inputs=2:duration=first[aout]", "-map", "0:v:0", "-map", "[aout]", "-c:a", "aac"]
    elif music:
        args = args + ["-map", "0:v:0", "-map", "1:a:0", "-af", f"volume={cfg['music_volume']}", "-c:a", "aac"]
    elif sa:
        args = args + ["-af", at + f"volume={cfg['source_volume']}", "-c:a", "aac"]
    else:
        args = args + ["-an"]
    args = args + ["-movflags", "+faststart", str(output)]
    run_cmd(args)
    gc.collect()

def get_source(work, stype, url, up):
    if stype == "Google Drive":
        return download_drive(url, work)
    if stype == "YouTube":
        return download_youtube(url, work, want_mp3=False, quality="Auto")
    if stype == "TikTok / Insta / X / FB (Cobalt)":
        return download_via_cobalt(clean_insta_url(url) if "instagram" in url else url, work)
    if up is None:
        raise RuntimeError("Upload file missing")
    suf = Path(up.name).suffix.lower()
    if suf not in [".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"]:
        suf = ".mp4"
    src = work / ("uploaded_video" + suf)
    with src.open("wb") as f:
        shutil.copyfileobj(up, f, length=8 * 1024 * 1024)
    return src

def get_music(work, up):
    if up is None:
        return None
    suf = Path(up.name).suffix.lower()
    if suf not in [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"]:
        suf = ".mp3"
    m = work / ("bg_music" + suf)
    with m.open("wb") as f:
        shutil.copyfileobj(up, f, length=1024 * 1024)
    return m

main_mode = st.radio("Select Section", ["CLIPPER", "DOWNLOADER"], horizontal=True, key="main_mode_final")

if main_mode != st.session_state.active_tab:
    st.session_state.preview_done = False
    st.session_state.preview_bytes = None
    st.session_state.active_tab = main_mode

if main_mode == "CLIPPER":
    st.subheader("Clipper - Highlight + Normal")
    left, right = st.columns([1.5, 1], gap="medium")
    with right:
        st.subheader("Editing Settings")
        clip_mode = st.radio("How to clip?", ["Highlight Moments - Best Parts Only", "Normal Clipping - Evenly Spaced Clips"], index=1, key="clip_mode_final")
        clip_count = st.slider("Maximum clips", 1, 30, 3, key="clip_count_final")
        clip_length = st.slider("Clip duration (seconds)", 5, 60, 30, key="clip_len_final")
        source_volume = st.slider("Original audio volume", 0.0, 2.0, 1.5, key="clip_sv_final")
        music_volume = st.slider("Music volume", 0.0, 2.0, 0.25, key="clip_mv_final")
        use_trim = st.toggle("Enable Trim", value=False, key="clip_trim_final")
        trim_start = 0.0
        trim_end = None
        if use_trim:
            trim_start = st.number_input("Start (sec)", min_value=0.0, value=0.0, step=1.0, key="clip_ts_final")
            trim_end = st.number_input("End (sec)", min_value=1.0, value=60.0, step=1.0, key="clip_te_final")
            if trim_end <= trim_start:
                st.error("End must be greater than Start")
        effect = st.selectbox("Effect", ["None - Original", "Cinematic - Dark + Warm", "Vivid - Color Pop", "Black & White", "Vintage - Old Film", "Warm - Golden", "Cool - Blue"], key="clip_eff_final")
        brightness = st.slider("Brightness", -0.3, 0.3, 0.0, step=0.01, key="clip_br_final")
        speed = st.selectbox("Speed", [0.5, 0.75, 1.0, 1.25, 1.5, 2.0], index=2, key="clip_sp_final")
        contrast = st.slider("Contrast", 0.5, 2.0, 1.0, step=0.05, key="clip_ct_final")
        sharpen = st.slider("Sharpen", 0.0, 3.0, 0.0, step=0.5, key="clip_sh_final")
        saturation = st.slider("Saturation", 0.0, 2.5, 1.0, step=0.05, key="clip_sat_final")
        blur = st.slider("Blur", 0.0, 3.0, 0.0, step=0.5, key="clip_bl_final")
        fade_in = st.toggle("Fade In", value=False, key="clip_fi_final")
        fade_out = st.toggle("Fade Out", value=False, key="clip_fo_final")
        ratio_label = st.selectbox("Aspect Ratio", list(RATIOS.keys()), index=0, key="clip_ratio_final")
        res_label = st.selectbox("Resolution", list(RESOLUTIONS.keys()), index=0, key="clip_res_final")
        out_w, out_h = get_output_size(ratio_label, res_label)
        st.info(f"{ratio_label} | {res_label} | {out_w}x{out_h}")
        cfg = {"source_volume": source_volume, "music_volume": music_volume, "out_w": out_w, "out_h": out_h, "effect": effect, "brightness": brightness, "contrast": contrast, "saturation": saturation, "sharpen": sharpen, "blur": blur, "speed": float(speed), "fade_in": fade_in, "fade_out": fade_out}
    with left:
        source_type = st.radio("Choose source", ["YouTube", "TikTok / Insta / X / FB (Cobalt)", "Google Drive", "Upload video"], horizontal=True, index=0, key="clip_src_final")
        video_url = ""
        video_upload = None
        if source_type == "Google Drive":
            video_url = st.text_input("Drive link", placeholder="Paste Drive link", key="clip_drive_final")
        elif source_type == "Upload video":
            video_upload = st.file_uploader("Upload video", type=["mp4", "mov", "mkv", "webm", "avi", "m4v"], key="clip_up_final")
        elif source_type == "TikTok / Insta / X / FB (Cobalt)":
            video_url = st.text_input("Link", placeholder="https://www.instagram.com/reel/...", key="clip_cobalt_final")
        else:
            video_url = st.text_input("YouTube URL", placeholder="Paste any YouTube link - youtube / youtu.be / sosyoutube", key="clip_yt_final")
        music_upload = st.file_uploader("Background Music (Optional)", type=["mp3", "wav", "m4a", "aac", "ogg", "flac"], key="clip_music_final")
        st.subheader("Step 1: Preview")
        if st.button("GENERATE PREVIEW - 5 Sec", use_container_width=True, key="clip_prev_final"):
            if source_type == "Upload video" and video_upload is None:
                st.error("Please upload video first")
                st.stop()
            if source_type != "Upload video" and not video_url.strip().startswith(("https://", "http://")):
                st.error("Enter valid link")
                st.stop()
            if not check_ffmpeg():
                st.error("FFmpeg missing")
                st.stop()
            work = Path(tempfile.mkdtemp(prefix="preview_"))
            try:
                st.write("Making Preview...")
                src = get_source(work, source_type, video_url, video_upload)
                mus = get_music(work, music_upload)
                if use_trim:
                    p_start = trim_start
                else:
                    p_start = 0.0
                p_out = work / "preview.mp4"
                render_clip(src, p_out, p_start, 5, cfg, mus)
                with open(p_out, "rb") as f:
                    st.session_state.preview_bytes = f.read()
                st.success("Preview Ready!")
                st.video(st.session_state.preview_bytes)
                st.session_state.preview_done = True
            except Exception as e:
                st.error("Preview Error: " + str(e))
                st.session_state.preview_done = False
        if st.session_state.preview_bytes is not None:
            st.video(st.session_state.preview_bytes)
        if st.session_state.preview_done:
            st.success("Preview Approved - Generate Now!")
        else:
            st.warning("Generate Locked - Watch Preview First")
        st.subheader("Step 2: Generate Clips")
        if st.button("GENERATE CLIPS", type="primary", use_container_width=True, disabled=not st.session_state.preview_done, key="clip_gen_final"):
            work = Path(tempfile.mkdtemp(prefix="clipshort_"))
            try:
                st.write("Processing...")
                src = get_source(work, source_type, video_url, video_upload)
                mus = get_music(work, music_upload)
                total = get_duration(src)
                if total <= 0:
                    st.error("Could not read video duration")
                    st.stop()
                st.write(f"Video: {round(total, 1)} sec")
                if use_trim:
                    t_start = trim_start
                else:
                    t_start = 0.0
                if use_trim and trim_end:
                    t_end = min(trim_end, total)
                else:
                    t_end = total
                if t_end <= t_start:
                    st.error("Trim End must be greater than Start")
                    st.stop()
                if "Highlight" in clip_mode:
                    scores = get_highlight_scores(src, total)
                    if scores is None:
                        st.warning("No audio found - Using Normal clipping")
                        starts = choose_normal_starts(total, clip_length, clip_count, t_start, t_end)
                    else:
                        starts = choose_highlight_starts(scores, total, clip_length, clip_count, t_start, t_end)
                        for idx, s in enumerate(starts):
                            st.write(f"Highlight {idx + 1}: {int(s // 60)}:{int(s % 60):02d}")
                else:
                    starts = choose_normal_starts(total, clip_length, clip_count, t_start, t_end)
                outs = []
                for i, s in enumerate(starts):
                    out = work / f"clip_{i + 1}.mp4"
                    st.write(f"Rendering {i + 1}/{len(starts)} - {int(s // 60)}:{int(s % 60):02d}")
                    render_clip(src, out, s, clip_length, cfg, mus)
                    if out.exists() and out.stat().st_size > 10000:
                        outs.append(out)
                if not outs:
                    st.error("No clips rendered. Try different video.")
                    st.stop()
                st.success(f"Done - {len(outs)} Clips Ready!")
                for i, o in enumerate(outs):
                    st.subheader(f"Clip {i + 1} - {out_w}x{out_h}")
                    st.video(str(o))
                    with open(o, "rb") as f:
                        st.download_button(f"Download Clip {i + 1}", f, file_name=f"clip_{i + 1}.mp4", mime="video/mp4", key=f"clip_dl_final_{i}")
            except Exception as e:
                st.error("Error: " + str(e))

if main_mode == "DOWNLOADER":
    st.subheader("Downloader - Video + MP3")
    st.caption("Paste any YouTube link - Auto converts to real YouTube link")
    st.markdown("### YouTube Downloader")
    yt_url = st.text_input("YouTube Link", placeholder="youtube / youtu.be / sosyoutube / ssyoutube - any link", key="dl_yt_url_final")
    yt_format = st.selectbox("Format - YouTube", ["Video - MP4", "Audio - MP3"], key="dl_yt_format_final")
    yt_quality = st.selectbox("Quality - Y2mate Style", ["Auto", "1080p", "720p", "480p", "360p", "240p", "144p"], key="dl_yt_q_final")
    if st.button("DOWNLOAD YOUTUBE", type="primary", use_container_width=True, key="dl_yt_btn_final"):
        if not yt_url.strip().startswith(("https://", "http://")):
            st.error("Please paste a valid YouTube link")
        else:
            work = Path(tempfile.mkdtemp(prefix="yt_dl_"))
            want_mp3 = "MP3" in yt_format
            try:
                with st.spinner(f"Downloading... {yt_quality} - Please wait 10-15 sec"):
                    src = download_youtube(yt_url, work, want_mp3=want_mp3, quality=yt_quality)
                if want_mp3:
                    st.success("YouTube MP3 Done!")
                    st.audio(str(src))
                    with open(src, "rb") as f:
                        st.download_button("SAVE MP3 TO PHONE - YouTube", f, file_name=src.name, mime="audio/mp3", key="dl_yt_save_mp3_final")
                else:
                    st.success(f"YouTube Video Done! - {yt_quality}")
                    st.video(str(src))
                    with open(src, "rb") as f:
                        st.download_button("SAVE VIDEO TO PHONE - YouTube", f, file_name=src.name, mime=get_mime(src), key="dl_yt_save_final")
            except Exception as e:
                st.error("Download Failed: " + str(e))
    st.divider()
    st.markdown("### Instagram Downloader")
    insta_url = st.text_input("Instagram Link", placeholder="https://instagram.com/reel/...", key="dl_insta_url_final")
    insta_format = st.selectbox("Format - Instagram", ["Video - MP4", "Audio - MP3"], key="dl_insta_format_final")
    insta_quality = st.selectbox("Quality", ["720p - HD", "480p - Fast", "1080p - Full HD"], key="dl_insta_q_final")
    if st.button("DOWNLOAD INSTAGRAM", type="primary", use_container_width=True, key="dl_insta_btn_final"):
        if not insta_url.strip().startswith(("https://", "http://")):
            st.error("Please paste a valid Instagram link")
        else:
            work = Path(tempfile.mkdtemp(prefix="insta_dl_"))
            want_mp3 = "MP3" in insta_format
            try:
                with st.spinner("Downloading... Please wait"):
                    src = download_instagram(insta_url, work, want_mp3=want_mp3)
                if want_mp3:
                    st.success("Instagram MP3 Done!")
                    st.audio(str(src))
                    with open(src, "rb") as f:
                        st.download_button("SAVE MP3 TO PHONE - Instagram", f, file_name=src.name, mime="audio/mp3", key="dl_insta_save_mp3_final")
                elif src.suffix.lower() in [".jpg", ".png", ".webp"]:
                    st.image(str(src))
                    with open(src, "rb") as f:
                        st.download_button("SAVE IMAGE", f, file_name=src.name, mime=get_mime(src), key="dl_insta_img_final")
                else:
                    st.success("Instagram Video Done!")
                    st.video(str(src))
                    with open(src, "rb") as f:
                        st.download_button("SAVE VIDEO TO PHONE - Instagram", f, file_name=src.name, mime=get_mime(src), key="dl_insta_save_final")
            except Exception as e:
                st.error("Download Failed: " + str(e))
    st.info("Tip: Any YouTube link works - sosyoutube / ssyoutube / youtu.be auto converts. Insta: Clean link https://www.instagram.com/reel/Dfqu4ikT61P/")
