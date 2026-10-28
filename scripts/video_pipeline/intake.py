from pathlib import Path
import json
import re
import shutil
from .common import *

def doctor(deep=False):
    import importlib.metadata
    import ctranslate2
    import faster_whisper
    import numpy
    import opencc
    required=[SCRIPTS/"models/large-v3-turbo/model.bin",SCRIPTS/"fonts/xinqingnian.ttf",SCRIPTS/"config/subtitle_style.json"]
    for p in required:
        if not p.is_file(): raise FileNotFoundError(str(p))
    for name in ["ffmpeg","ffprobe"]:
        if not shutil.which(name): raise RuntimeError(f"Missing {name}")
    result=dict(python_ready=True,ffmpeg=shutil.which("ffmpeg"),ffprobe=shutil.which("ffprobe"),
                model_bytes=required[0].stat().st_size,font_available=True,network_required=False)
    if deep:
        actual=digest(required[0]); expected=read(SCRIPTS/"config/environment.json")["model_sha256"]
        if actual!=expected: raise ValueError("Model checksum mismatch")
        result["model_sha256_verified"]=True
    return result

def ingest(input_path,timestamp=None):
    source=rooted(input_path)
    if not source.is_file(): raise FileNotFoundError(str(source))
    capture=timestamp or (re.search(r"(?<!\d)(20\d{12})(?!\d)",source.stem).group(1) if re.search(r"(?<!\d)(20\d{12})(?!\d)",source.stem) else None)
    if not capture: raise ValueError("No full capture timestamp in filename; supply --timestamp YYYYMMDDHHMMSS")
    folder=timestamp_name(capture)+"_未命名"
    source_hash=digest(source)
    for existing in (ROOT/"process").glob("*/manifest.json"):
        old=read(existing)
        if old.get("original_sha256")==source_hash:
            return dict(job=rel(existing.parent),status=old["status"],resumed=True)
    data=probe(source); info=media_info(data)
    job=ROOT/"process"/folder
    if job.exists(): raise FileExistsError(str(job))
    job.mkdir(parents=True)
    manifest=dict(layout_version=2,original_filename=source.name,original_source_path=rel(source),source_path=rel(source),
                  capture_timestamp=capture,capture_date_from_filename=timestamp_name(capture)[:10],
                  process_dir=rel(job),original_sha256=source_hash,media=info,duration_seconds=info["duration"],
                  status="ingested",editing_approved=False,created_at_utc=now())
    write(job/"manifest.json",manifest); write(job/"source_probe.json",data)
    shutil.copy2(SCRIPTS/"config/subtitle_style.json",job/"subtitle_style.json")
    ffmpeg(job,["-loglevel","error","-n","-i",source,"-map","0:a:0","-ac","1","-ar","16000","-c:a","pcm_s16le","audio.wav"],"audio_extract.log")
    ffmpeg(job,["-loglevel","info","-i","audio.wav","-af","silencedetect=noise=-35dB:d=0.25","-f","null","-"],"silence.log")
    text=(job/"silence.log").read_text(encoding="utf-8",errors="replace")
    pauses=[]; start=None
    for line in text.splitlines():
        match=re.search(r"silence_start: ([0-9.]+)",line)
        if match: start=float(match.group(1))
        match=re.search(r"silence_end: ([0-9.]+).*silence_duration: ([0-9.]+)",line)
        if match and start is not None:
            pauses.append(dict(start=start,end=float(match.group(1)),duration=float(match.group(2)))); start=None
    write(job/"silences.json",pauses)
    at=min(10.0,info["duration"]/2)
    ffmpeg(job,["-loglevel","error","-n","-ss",at,"-i",source,"-map","0:v:0","-frames:v","1","-vf","scale=960:-2","-update","1","source_frame.jpg"],"source_frame.log")
    return dict(job=rel(job),status="ingested",media=info)

def rewrite_job_references(job,old_prefix,new_prefix):
    def fix(x):
        if isinstance(x,str): return x.replace(old_prefix,new_prefix)
        if isinstance(x,list): return [fix(v) for v in x]
        if isinstance(x,dict): return {k:fix(v) for k,v in x.items()}
        return x
    for p in job.rglob("*"):
        if p.is_file() and p.suffix==".json": write(p,fix(read(p)))
        elif p.is_file() and p.suffix==".md":
            p.write_text(p.read_text(encoding="utf-8-sig").replace(old_prefix,new_prefix),encoding="utf-8-sig")

def archive(job,title):
    m=read(job/"manifest.json")
    if m["status"]=="completed": raise ValueError("Completed video cannot be re-archived")
    if not (job/"transcript_asr.json").exists(): raise ValueError("Transcribe before naming the video")
    title=safe_title(title)
    prefix=timestamp_name(m["capture_timestamp"])
    target_job=ROOT/"process"/(prefix+"_"+title)
    if target_job!=job and target_job.exists(): raise FileExistsError(str(target_job))
    previous_source=m["source_path"]
    source=rooted(previous_source)
    if digest(source)!=m["original_sha256"]: raise ValueError("Source hash mismatch")
    target=ROOT/"raw"/(prefix[:10]+"_"+title+source.suffix.lower())
    if target!=source and target.exists(): target=target.with_stem(target.stem+"_"+prefix[11:])
    if target!=source and target.exists(): raise FileExistsError(str(target))
    m["archive_intent"]=dict(source_path=rel(target),process_dir=rel(target_job))
    write(job/"manifest.json",m)
    if source!=target: move(source,target)
    m.update(title=title,source_path=rel(target),status="archived",archived_sha256=digest(target))
    if m["archived_sha256"]!=m["original_sha256"]: raise ValueError("Archived hash mismatch")
    write(job/"manifest.json",m)
    old=rel(job)
    if job!=target_job: move(job,target_job)
    rewrite_job_references(target_job,old,rel(target_job))
    m=read(target_job/"manifest.json"); m.update(process_dir=rel(target_job)); m.pop("archive_intent",None)
    write(target_job/"manifest.json",m)
    transcript=target_job/"逐字稿.md"
    if transcript.exists():
        text=transcript.read_text(encoding="utf-8-sig").replace("# 逐字稿："+m["original_filename"],"# 逐字稿："+title)
        transcript.write_text(text.replace("`"+previous_source+"`","`"+m["source_path"]+"`"),encoding="utf-8-sig")
    asr=read(target_job/"transcript_asr.json"); asr["source_path"]=m["source_path"]
    write(target_job/"transcript_asr.json",asr)
    return dict(job=rel(target_job),source_path=m["source_path"],source_hash_verified=True)

def review(job,spec_path,trim_pauses=False):
    m=read(job/"manifest.json")
    if m["status"]=="completed": raise ValueError("Completed video: create a new revision explicitly instead")
    if not m.get("title") or not m["source_path"].startswith("raw/"): raise ValueError("Archive and name the original first")
    spec=read(rooted(spec_path)); duration=m["duration_seconds"]
    if not spec.get("summary"): raise ValueError("Review spec needs a content-specific summary")
    cuts=list(spec.get("cuts",[]))
    if trim_pauses:
        for p in read(job/"silences.json"):
            if p["duration"]<0.6: continue
            s,e=p["start"]+0.15,min(p["end"]-0.15,duration)
            if s>=e or any(s<c["end"] and e>c["start"] for c in cuts): continue
            cuts.append(dict(start=s,end=e,kind="pause",text="较长停顿",reason="压短停顿，保留两侧各约 0.15 秒。"))
    cuts,merged,keeps=normalize_cuts(cuts,duration)
    estimate=sum(e-s for s,e in keeps)
    plan=dict(schema_version=1,status="awaiting_user_approval",source_path=m["source_path"],source_sha256=m["original_sha256"],
              title=m["title"],summary=spec["summary"],preserve=spec.get("preserve",[]),original_duration=duration,
              cuts=cuts,merged_remove_intervals=merged,proposed_keep_intervals=keeps,estimated_duration=estimate,
              transcript_corrections=spec.get("corrections",[]))
    previous=job/"edit_plan.json"
    if previous.exists():
        history=job/"history"; history.mkdir(exist_ok=True)
        shutil.copy2(previous,history/("edit_plan_"+digest(previous)[:12]+".json"))
    write(previous,plan)
    body=f"# 剪辑稿（待确认）：{m['title']}\n\n状态：待审核；尚未执行本稿的剪辑。\n\n"
    body+=f"原片：`{m['source_path']}`\n\n原片 {stamp(duration)}；预计剪后 {stamp(estimate)}（不含约 0.3 秒收尾缓冲）。\n\n{spec['summary']}\n\n"
    if plan["preserve"]: body+="保留内容："+"；".join(plan["preserve"])+"。\n\n"
    for c in cuts:
        body+=f"## {c['id']} · {stamp(c['start'])}–{stamp(c['end'])}\n\n删除／压短：{c['text']}\n\n理由：{c['reason']}\n\n"
    if spec.get("corrections"):
        body+="## 转写校对与待复核\n\n"
        for c in spec["corrections"]:
            body+=f"- {stamp(c.get('start',0))} · {c['from']} → {c['to']}：{c.get('basis',c.get('reason','待复核'))}\n"
        body+="\n"
    if (job/"transcript_asr.json").exists():
        asr=read(job/"transcript_asr.json"); accepted,_=clean_segments(asr)
        speech=[c for c in cuts if c["kind"]=="speech"]
        paragraphs=[]
        for seg in accepted:
            kept="".join(w["word"] for w in seg["words"] if not any(c["start"]<=(w["start"]+w["end"])/2<c["end"] for c in speech))
            if kept.strip(): paragraphs.append(kept.replace(",","，"))
        preview="\n\n".join(paragraphs)
        for c in spec.get("corrections",[]): preview=preview.replace(c["from"],c["to"])
        body+="## 剪后文字预览\n\n按原片词级位置拼接，标点会按剪后语义整理；停顿删段不删除文字，实际切点需复核。\n\n"+preview+"\n\n"
    from .captions import layout
    info=m.get("media") or media_info(read(job/"source_probe.json"))
    settings=layout(read(job/"subtitle_style.json"),info["width"],info["height"])
    body+=f"## 字幕与审核\n\n沿用已确认的新青年体、白字和黄色重点词、深色描边、下三分之一位置。本条 {info['width']}×{info['height']}，字号 {settings['size']:g}，单行最多 {settings['max_characters']} 字；外观见同目录字幕外观预览.jpg。剪后重新转写并对齐字幕。\n\n时间码是原片定位；短切必须复核吞字与自然程度。请确认本稿后再执行剪辑。\n"
    (job/"剪辑稿_待确认.md").write_text(body,encoding="utf-8-sig")
    m.update(status="awaiting_edit_approval",editing_approved=False,review_path=rel(job/"剪辑稿_待确认.md"))
    write(job/"manifest.json",m)
    return dict(job=rel(job),status=m["status"],plan_sha256=digest(previous),cuts=len(cuts),estimated_duration=round(estimate,3))

def approve(job,message,plan_hash):
    m=read(job/"manifest.json")
    if m["status"]=="completed": raise ValueError("Video already completed")
    actual=digest(job/"edit_plan.json")
    if actual!=plan_hash.upper(): raise ValueError("Approval refers to a different edit-plan version")
    if not message.strip(): raise ValueError("Quote the user's actual approval message")
    approval=dict(user_message=message,plan_sha256=actual,source_sha256=m["original_sha256"],recorded_at_utc=now())
    write(job/"approval.json",approval)
    shutil.copy2(job/"edit_plan.json",job/"edit_plan_approved.json")
    m.update(status="approved",editing_approved=True); write(job/"manifest.json",m)
    return dict(status="approved",job=rel(job),plan_sha256=actual)
