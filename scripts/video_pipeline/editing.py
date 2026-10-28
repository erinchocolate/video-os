from fractions import Fraction
import math
from .common import *

RATE=48000

def edit(job):
    m,approval=require_approval(job)
    if m["status"]=="completed": raise ValueError("Completed job: use a separate revision for another render")
    if digest(rooted(m["source_path"]))!=m["original_sha256"]: raise ValueError("Source hash mismatch")
    data=read(job/"source_probe.json"); info=media_info(data)
    if info["color_transfer"] in ["smpte2084","arib-std-b67"]:
        raise ValueError("HDR needs an explicitly reviewed tone-mapping workflow; source was preserved")
    fps=Fraction(info["fps"]); cuts=read(job/"edit_plan.json")
    _,_,intervals=normalize_cuts(cuts["cuts"],info["duration"])
    keeps=[]; cursor=0
    for s,e in intervals:
        sf,ef=round(s*fps),round(e*fps)
        if sf>=ef: raise ValueError("Retained fragment shorter than one frame; refine proposal")
        keeps.append(dict(source_start_frame=sf,source_end_frame=ef,frames=ef-sf,
                          source_start=float(sf/fps),source_end=float(ef/fps),
                          output_start=float(cursor/fps),output_end=float((cursor+ef-sf)/fps)))
        cursor+=ef-sf
    tail_frames=max(1,round(0.3*fps)); total_frames=cursor+tail_frames
    samples=round(total_frames/fps*RATE)
    rp=dict(schema_version=1,source_path=m["source_path"],source_sha256=m["original_sha256"],plan_sha256=approval["plan_sha256"],
            fps=str(fps),width=info["width"],height=info["height"],keeps=keeps,content_frames=cursor,tail_frames=tail_frames,
            total_frames=total_frames,total_duration=float(total_frames/fps),target_audio_samples=samples,
            audio_rate=RATE,note="按源帧率就近对齐切点；4 ms 去点击淡化；约 0.3 秒末帧缓冲。")
    count=len(keeps)
    graph=[f"[0:a:0]aresample={RATE},asplit={count}"+"".join(f"[as{i}]" for i in range(count))]
    for i,c in enumerate(keeps):
        ss,es=round(c["source_start"]*RATE),round(c["source_end"]*RATE); duration=(es-ss)/RATE
        graph.append(f"[as{i}]atrim=start_sample={ss}:end_sample={es},asetpts=PTS-STARTPTS,afade=t=in:d=0.004,afade=t=out:st={duration-0.004:.8f}:d=0.004[a{i}]")
    graph.append("".join(f"[a{i}]" for i in range(count))+f"concat=n={count}:v=0:a=1,apad=whole_len={samples},atrim=end_sample={samples}[aout]")
    (job/"audio_edit.ffgraph").write_text(";\n".join(graph),encoding="utf-8")
    (job/"edited").mkdir(exist_ok=True)
    if (job/"edited/transcript_asr.json").exists():
        raise ValueError("Edited transcript already exists: preserve edited/ and subtitles as a revision before re-editing")
    ffmpeg(job,["-loglevel","warning","-y","-i",rooted(m["source_path"]),"-filter_complex_script","audio_edit.ffgraph","-map","[aout]","-ar",RATE,"-c:a","pcm_s16le","edited_audio.wav"],"audio_edit.log")
    ffmpeg(job,["-loglevel","error","-y","-i","edited_audio.wav","-ac","1","-ar","16000","-c:a","pcm_s16le","edited/audio.wav"],"edited_audio_extract.log")
    rp["edited_audio_sha256"]=digest(job/"edited_audio.wav"); write(job/"render_plan.json",rp)
    m.update(status="edited",editing_approved=True,media=info); write(job/"manifest.json",m)
    return dict(job=rel(job),status="edited",duration=rp["total_duration"],fps=str(fps),clips=count)

def current_render_inputs(job):
    m,approval=require_approval(job); rp=read(job/"render_plan.json")
    if rp["plan_sha256"]!=approval["plan_sha256"]: raise ValueError("Render timeline belongs to a previous edit plan")
    if rp["edited_audio_sha256"]!=digest(job/"edited_audio.wav"): raise ValueError("Edited audio changed after timeline creation")
    return m,rp

def video_filter(job,rp,burn_subtitles=True):
    count=len(rp["keeps"]); fps=Fraction(rp["fps"])
    graph=[f"[0:v:0]fps={fps},format=yuv420p,split={count}"+"".join(f"[vs{i}]" for i in range(count))]
    for i,c in enumerate(rp["keeps"]):
        graph.append(f"[vs{i}]trim=start_frame={c['source_start_frame']}:end_frame={c['source_end_frame']},setpts=PTS-STARTPTS[v{i}]")
    fontdir=Path(__file__).resolve().parents[1]/"fonts"
    font_relative=os.path.relpath(fontdir,job).replace("\\","/")
    suffix=f"ass=final_subtitles.ass:fontsdir={font_relative}," if burn_subtitles else ''
    graph.append("".join(f"[v{i}]" for i in range(count))+f"concat=n={count}:v=1:a=0,setpts=N*{fps.denominator}/({fps.numerator}*TB),"
                 f"tpad=stop_mode=clone:stop={rp['tail_frames']},"+suffix+"format=yuv420p[vout]")
    return ";\n".join(graph)

def render(job):
    m,rp=current_render_inputs(job)
    if m["status"]=="completed": raise ValueError("Completed video cannot be overwritten")
    from .subtitle_review import require_review_approval
    require_review_approval(job)
    subtitles=read(job/"final_subtitles.json")
    if subtitles["edited_audio_sha256"]!=rp["edited_audio_sha256"]: raise ValueError("Subtitles belong to a different audio edit")
    if subtitles["style_sha256"]!=digest(job/"subtitle_style.json"): raise ValueError("Subtitle style changed; regenerate subtitles and preview")
    fps=Fraction(rp["fps"])
    (job/"video_edit.ffgraph").write_text(video_filter(job,rp),encoding="utf-8")
    ffmpeg(job,["-loglevel","info","-y","-filter_complex_threads","4","-i",rooted(m["source_path"]),"-i","edited_audio.wav", "-filter_complex_script","video_edit.ffgraph",
                "-map","[vout]","-map","1:a:0","-c:v","libx264","-preset","fast","-crf","18","-threads","12","-pix_fmt","yuv420p","-fps_mode","cfr","-r",fps,
                "-c:a","aac","-b:a","256k","-ar",RATE,"-movflags","+faststart","-map_metadata","-1","-metadata","title="+m["title"],
                "-progress","render_progress.txt","rendered.mp4"],"render.log")
    write(job/"render_inputs.json",dict(plan_sha256=digest(job/"edit_plan.json"),render_plan_sha256=digest(job/"render_plan.json"),
          ass_sha256=digest(job/"final_subtitles.ass"),style_sha256=digest(job/"subtitle_style.json"),rendered_sha256=digest(job/"rendered.mp4")))
    m["status"]="rendered_pending_verification"; write(job/"manifest.json",m)
    return dict(job=rel(job),status=m["status"],rendered=rel(job/"rendered.mp4"))

def frames(job):
    m=read(job/"manifest.json"); rp=read(job/"render_plan.json")
    info=m.get("media") or media_info(read(job/"source_probe.json"))
    source=job/"rendered.mp4" if (job/"rendered.mp4").exists() else rooted(m["final_path"])
    count=rp["total_frames"]
    numbers=sorted(set(round((count-1)*(i+0.3)/9) for i in range(9)))
    select="+".join(f"eq(n,{n})" for n in numbers)
    tile_h=round(640*rp.get("height",info["height"])/rp.get("width",info["width"])/2)*2
    ffmpeg(job,["-loglevel","error","-y","-i",source,"-vf",f"select='{select}',scale=640:{tile_h},tile=3x3:padding=8:margin=8:color=black", "-frames:v","1","-q:v","2","-update","1","成片检查_九宫格.jpg"],"frame_grid.log")
    cues=read(job/"final_subtitles.json")["cues"]
    cue=max(cues,key=lambda c:len(c["text"]))
    ffmpeg(job,["-loglevel","error","-y","-ss",(cue["start"]+cue["end"])/2,"-i",source,"-frames:v","1","-q:v","2","-update","1","成片画面.jpg"],"frame_preview.log")
    return dict(grid=rel(job/"成片检查_九宫格.jpg"),frame=rel(job/"成片画面.jpg"))

def verify(job):
    import wave
    import numpy as np
    m,rp=current_render_inputs(job); output=job/"rendered.mp4"
    inputs=read(job/"render_inputs.json")
    for file,key in [("edit_plan.json","plan_sha256"),("render_plan.json","render_plan_sha256"),("final_subtitles.ass","ass_sha256"),("subtitle_style.json","style_sha256"),("rendered.mp4","rendered_sha256")]:
        if digest(job/file)!=inputs[key]: raise ValueError(f"Render inputs changed: {file}")
    data=probe(output,True)
    v=next(s for s in data["streams"] if s["codec_type"]=="video"); a=next(s for s in data["streams"] if s["codec_type"]=="audio")
    assert (v["width"],v["height"],v["pix_fmt"])==(rp["width"],rp["height"],"yuv420p")
    assert Fraction(v["avg_frame_rate"])==Fraction(rp["fps"])
    assert int(v["nb_read_frames"])==rp["total_frames"]
    assert abs(float(v["duration"])-rp["total_duration"])<0.04
    difference=abs(float(a["duration"])-float(v["duration"]))
    assert difference<0.05
    log=(job/"render.log").read_text(encoding="utf-8",errors="replace")
    psname=read(job/"subtitle_style.json")["postscript_name"]
    fontlines=[s for s in log.splitlines() if "fontselect:" in s]
    assert any(psname in s.split("->")[-1] for s in fontlines),"Requested font was not loaded"
    assert "failed to find" not in log.lower() and "glyph 0x" not in log.lower(),"Font fallback or missing glyph; inspect render.log"
    cues=read(job/"final_subtitles.json")["cues"]
    assert all(0<=c["start"]<c["end"]<=rp["total_duration"]+0.005 for c in cues)
    assert all(x["end"]<=y["start"] for x,y in zip(cues,cues[1:]))
    with wave.open(str(job/"edited_audio.wav"),"rb") as wav:
        assert wav.getnframes()==rp["target_audio_samples"]
        samples=np.frombuffer(wav.readframes(wav.getnframes()),dtype="<i2").astype(np.int32)
    clipping=bool(np.any(np.abs(samples)>=32767))
    if clipping: raise ValueError("Audio clipping detected")
    ffmpeg(job,["-v","error","-xerror","-i",output,"-map","0:v:0","-map","0:a:0","-f","null","-"],"decode_verification.log")
    if (job/"decode_verification.log").stat().st_size: raise ValueError("Decode errors; inspect decode_verification.log")
    if digest(rooted(m["source_path"]))!=m["original_sha256"]: raise ValueError("Source changed")
    report=dict(technical_checks_passed=True,full_decode_passed=True,source_sha256_verified=True,
                rendered_sha256=digest(output),duration_seconds=float(data["format"]["duration"]),video_frames=int(v["nb_read_frames"]),
                width=v["width"],height=v["height"],fps=rp["fps"],audio_video_duration_difference_seconds=difference,
                font_confirmed=psname,subtitles=len(cues),max_caption_characters=max(len(c["text"]) for c in cues),
                clipping_detected=False,visual_review_pending=True,checked_at_utc=now())
    write(job/"verification.json",report); write(job/"final_probe.json",data)
    m["status"]="awaiting_visual_check"; write(job/"manifest.json",m)
    return report

def publish(job,visual_note):
    from .subtitle_review import require_review_approval
    require_review_approval(job)
    m,_=require_approval(job); report=read(job/"verification.json")
    if m["status"]=="completed": raise ValueError("Already published; do not overwrite")
    output=job/"rendered.mp4"
    if not report.get("technical_checks_passed") or report["rendered_sha256"]!=digest(output): raise ValueError("Verify the current render before publishing")
    inputs=read(job/"render_inputs.json")
    for file,key in [("edit_plan.json","plan_sha256"),("render_plan.json","render_plan_sha256"),("final_subtitles.ass","ass_sha256"),("subtitle_style.json","style_sha256")]:
        if digest(job/file)!=inputs[key]: raise ValueError(f"Inputs changed since verification: {file}")
    if digest(rooted(m["source_path"]))!=m["original_sha256"]: raise ValueError("Original source changed since verification")
    if not visual_note.strip(): raise ValueError("Describe the actual frame/preview checks before publishing")
    date=timestamp_name(m["capture_timestamp"])[:10]
    target=ROOT/"final"/(date+"_"+safe_title(m["title"])+"_成片.mp4")
    if target.exists(): target=target.with_stem(target.stem+"_"+timestamp_name(m["capture_timestamp"])[11:])
    if target.exists(): raise FileExistsError(str(target))
    move(output,target)
    report.update(visual_review_pending=False,visual_review_note=visual_note,published_at_utc=now()); write(job/"verification.json",report)
    m.update(status="completed",final_path=rel(target),final_duration_seconds=report["duration_seconds"],
             final_size_bytes=target.stat().st_size,final_sha256=digest(target)); write(job/"manifest.json",m)
    notes=f"# 成片说明：{m['title']}\n\n成片：`{m['final_path']}`\n\n完整原片：`{m['source_path']}`\n\n时长：{stamp(m['final_duration_seconds'])}；分辨率：{report['width']}×{report['height']}；帧率：{report['fps']}。\n\n字幕沿用已确认的字体和黄白双色。技术检查通过；视觉复核：{visual_note}\n\n所有转写、提案、审核、时间线、字幕与日志保存在本目录。\n"
    (job/"成片说明.md").write_text(notes,encoding="utf-8-sig")
    return dict(status="completed",final_path=rel(target),duration=m["final_duration_seconds"])
