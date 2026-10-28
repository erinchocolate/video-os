from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
SCRIPTS=ROOT/"scripts"

def now():
    return datetime.now(timezone.utc).isoformat()

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def write(path,data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+".tmp")
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(temp,path)

def rooted(value):
    path=Path(value)
    path=(path if path.is_absolute() else ROOT/path).resolve()
    path.relative_to(ROOT.resolve())
    return path

def rel(path):
    return rooted(path).relative_to(ROOT).as_posix()

def job_path(value):
    path=rooted(value)
    path.relative_to(ROOT/"process")
    if path.parent!=ROOT/"process" or not (path/"manifest.json").is_file():
        raise ValueError("--job must name a video directory directly under process/")
    return path

def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(8388608),b""): h.update(block)
    return h.hexdigest().upper()

def move(source,target):
    source,target=rooted(source),rooted(target)
    if target.exists(): raise FileExistsError(str(target))
    target.parent.mkdir(parents=True,exist_ok=True)
    os.rename(source,target)

def probe(path,count_frames=False):
    cmd=["ffprobe","-v","error"]
    if count_frames: cmd += ["-count_frames"]
    cmd += ["-show_streams","-show_format","-of","json",str(path)]
    return json.loads(subprocess.check_output(cmd))

def media_info(data):
    v=next(s for s in data["streams"] if s["codec_type"]=="video" and not s.get("disposition",{}).get("attached_pic"))
    a=next((s for s in data["streams"] if s["codec_type"]=="audio"),None)
    if not a: raise ValueError("No audio stream; this workflow requires spoken audio")
    fps=Fraction(v.get("avg_frame_rate") or v["r_frame_rate"])
    if fps<=0: raise ValueError("Cannot determine source frame rate")
    rotation=next((float(s.get("rotation",0)) for s in v.get("side_data_list",[]) if "rotation" in s),0)
    w,h=v["width"],v["height"]
    if abs(rotation)%180==90: w,h=h,w
    return dict(width=w,height=h,fps=str(fps),duration=float(v.get("duration",data["format"]["duration"])),
                audio_rate=int(a["sample_rate"]),audio_channels=a["channels"],
                color_transfer=v.get("color_transfer","unknown"),rotation=rotation)

def ffmpeg(job,args,log_name):
    job=Path(job)
    with (job/log_name).open("wb") as log:
        result=subprocess.run(["ffmpeg","-hide_banner","-nostdin",*map(str,args)],cwd=job,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:
        tail=(job/log_name).read_text(encoding="utf-8",errors="replace")[-5000:]
        raise RuntimeError(f"FFmpeg failed ({log_name}):\n{tail}")

def stamp(t,srt=False):
    ms=round(float(t)*1000)
    h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); s,ms=divmod(ms,1000)
    return f"{h:02}:{m:02}:{s:02}{',' if srt else '.'}{ms:03}"

def safe_title(title):
    title=re.sub(r'[<>:"/\\|?*\x00-\x1f]'," ",title)
    title=re.sub(r"\s+"," ",title).strip(" .")
    if not title or len(title)>80: raise ValueError("Title must have 1–80 usable characters")
    return title

def timestamp_name(value):
    return datetime.strptime(value,"%Y%m%d%H%M%S").strftime("%Y-%m-%d_%H-%M-%S")

def normalize_cuts(cuts,duration):
    result=[]
    for i,c in enumerate(cuts,1):
        c=dict(c); s,e=float(c["start"]),float(c["end"])
        if not (math.isfinite(s) and math.isfinite(e) and 0<=s<e<=duration):
            raise ValueError(f"Invalid cut {i}: {s}–{e}; duration {duration}")
        if not c.get("text") or not c.get("reason"): raise ValueError("Every cut requires text and reason")
        c.update(start=s,end=e,id=c.get("id",f"C{i:02}"),kind=c.get("kind","speech"))
        result.append(c)
    merged=[]
    for c in sorted(result,key=lambda c:c["start"]):
        if merged and c["start"]<=merged[-1][1]: merged[-1][1]=max(merged[-1][1],c["end"])
        else: merged.append([c["start"],c["end"]])
    keeps=[]; cursor=0
    for s,e in merged:
        if s>cursor: keeps.append([cursor,s])
        cursor=e
    if cursor<duration: keeps.append([cursor,duration])
    if not keeps: raise ValueError("Proposal would remove the whole video")
    return result,merged,keeps

def require_approval(job):
    job=Path(job)
    m=read(job/"manifest.json")
    approval=read(job/"approval.json") if (job/"approval.json").exists() else None
    if not approval or approval.get("plan_sha256")!=digest(job/"edit_plan.json"):
        raise ValueError("Current edit plan has no matching user approval; present the proposal first")
    if not approval.get("user_message") or approval.get("source_sha256")!=m["original_sha256"]:
        raise ValueError("Approval does not identify this source video")
    return m,approval

def clean_segments(data):
    accepted=[]; rejected=[]
    for seg in data["segments"]:
        ws=seg.get("words",[])
        confidence=sum(w.get("probability",0) for w in ws)/max(1,len(ws))
        zero=sum(w["end"]-w["start"]<=0.001 for w in ws)/max(1,len(ws))
        is_tail=seg["start"]>=data["duration"]-1.0
        degenerate=is_tail and seg["end"]-seg["start"]<0.15 and len(seg["text"].strip())>8 and confidence<0.4 and zero>0.5
        (rejected if degenerate else accepted).append(seg)
    return accepted,rejected
