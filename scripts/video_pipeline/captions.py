import copy
from .common import *

def layout(style,width,height):
    scale=min(width,height)/1080
    base_size=style.get("portrait_font_size_at_1080p",style["font_size_at_1080p"]) if height>width else style["font_size_at_1080p"]
    size=base_size*scale
    side=round(160*width/1920)
    limit=min(style["max_characters_per_line"],int((width-2*side)/(size*1.05)))
    return dict(size=size,side=side,outline=style["outline_px"]*scale,
                bottom=round(style["bottom_margin_px"]*height/1080),max_characters=max(1,limit))

def norm(text):
    return "".join(c for c in text if c.isalnum())

def character_stream(data):
    from opencc import OpenCC
    cc=OpenCC("t2s"); chars=[]
    accepted,rejected=clean_segments(data)
    for seg in accepted:
        for w in seg["words"]:
            text=norm(cc.convert(w["word"]))
            for i,c in enumerate(text):
                duration=w["end"]-w["start"]
                chars.append(dict(char=c,start=w["start"]+duration*i/len(text),end=w["start"]+duration*(i+1)/len(text)))
    return chars,rejected

def correct_characters(chars,corrections):
    for correction in corrections:
        before,after=norm(correction["from"]),norm(correction["to"])
        if not before or not after or not correction.get("reason"): raise ValueError("Corrections need from/to/reason")
        text="".join(c["char"] for c in chars)
        matches=[m.start() for m in re.finditer(re.escape(before),text)]
        if "near" in correction: matches=[i for i in matches if abs(chars[i]["start"]-correction["near"])<2]
        if len(matches)!=1: raise ValueError(f"Correction has {len(matches)} matches; add near (audio seconds) to identify it")
        i=matches[0]; start,end=chars[i]["start"],chars[i+len(before)-1]["end"]
        replacements=[dict(char=c,start=start+(end-start)*n/len(after),end=start+(end-start)*(n+1)/len(after)) for n,c in enumerate(after)]
        chars[i:i+len(before)]=replacements
    return chars

def ass_stamp(t):
    cs=round(t*100); h,cs=divmod(cs,360000); m,cs=divmod(cs,6000); s,cs=divmod(cs,100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"

def header(style,width,height):
    settings=layout(style,width,height)
    size,margin,outline,side=settings["size"],settings["bottom"],settings["outline"],settings["side"]
    family=style["font"]
    if any(c in family for c in ",\r\n"): raise ValueError("Invalid ASS font family")
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{family},{size:.3f},&H00FFFFFF,&H0000D7FF,&H00141414,&H60000000,{int(bool(style.get('bold')))*-1},0,0,0,100,100,1,0,1,{outline:.3f},1,2,{side},{side},{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

def colored(text,emphasis):
    if any(c in text for c in "{}\\\r\n"): raise ValueError("Caption contains ASS control characters")
    if emphasis:
        if emphasis not in text: raise ValueError(f"Emphasis {emphasis!r} is absent from {text!r}")
        return text.replace(emphasis,r"{\c&H0000D7FF&}"+emphasis+r"{\c&H00FFFFFF&}",1)
    return text

def subtitles(job,spec_path):
    m,approval=require_approval(job); rp=read(job/"render_plan.json")
    if rp["plan_sha256"]!=approval["plan_sha256"]: raise ValueError("Caption timeline belongs to another edit plan")
    asr=read(job/"edited/transcript_asr.json")
    if asr.get("input_audio_sha256")!=digest(job/"edited/audio.wav"): raise ValueError("Transcribe the current edited audio first")
    style=read(job/"subtitle_style.json"); spec=read(rooted(spec_path))
    settings=layout(style,rp["width"],rp["height"])
    chars,rejected=character_stream(asr)
    chars=correct_characters(chars,spec.get("corrections",[]))
    lines=[dict(text=line) if isinstance(line,str) else dict(line) for line in spec["lines"]]
    if not lines: raise ValueError("Provide semantic caption lines for the edited speech")
    text="".join(c["char"] for c in chars)
    expected="".join(norm(line["text"]) for line in lines)
    if text!=expected:
        mismatch=next((i for i,(x,y) in enumerate(zip(text,expected)) if x!=y),min(len(text),len(expected)))
        raise ValueError(f"Caption text differs from edited ASR around character {mismatch}: ASR={text[max(0,mismatch-20):mismatch+40]!r}, captions={expected[max(0,mismatch-20):mismatch+40]!r}. Record justified corrections; do not invent speech.")
    cues=[]; offset=0
    for i,line in enumerate(lines):
        length=len(norm(line["text"]))
        if not length or len(line["text"])>settings["max_characters"]: raise ValueError(f"Empty or too-long caption (limit {settings['max_characters']} for this frame): {line}")
        span=chars[offset:offset+length]; offset+=length
        colored(line["text"],line.get("emphasis"))
        start=max(0,span[0]["start"]-0.04)
        if 'start_override' in line:
            start=float(line['start_override'])
            if not line.get('timing_basis') or not math.isfinite(start) or not 0<=start<span[-1]['end']:
                raise ValueError('Manual subtitle start needs a timing basis and must precede its speech end')
        cues.append(dict(index=i+1,start=round(start,2),speech_end=span[-1]["end"],text=line["text"],emphasis=line.get("emphasis"),
                         **(dict(timing_basis=line['timing_basis']) if 'start_override' in line else {})))
    for i,cue in enumerate(cues):
        end=min(cue["speech_end"]+0.12,rp["total_duration"])
        if i<len(cues)-1:
            next_start=cues[i+1]["start"]; end=min(end,next_start)
            if 0<=next_start-end<=0.25: end=next_start
        else: end=rp["total_duration"]
        cue["end"]=round(end,2)
        if cue["end"]-cue["start"]<0.5: raise ValueError(f"Caption flashes too briefly; merge semantic fragments: {cue}")
        if i and cues[i-1]["end"]>cue["start"]: raise ValueError("Caption overlap")
    ass=header(style,rp["width"],rp["height"])
    ass+="\n".join(f"Dialogue: 0,{ass_stamp(c['start'])},{ass_stamp(c['end'])},Default,,0,0,0,,{colored(c['text'],c['emphasis'])}" for c in cues)+"\n"
    (job/"final_subtitles.ass").write_text(ass,encoding="utf-8-sig")
    (job/"final_subtitles.srt").write_text("\n\n".join(f"{c['index']}\n{stamp(c['start'],True)} --> {stamp(c['end'],True)}\n{c['text']}" for c in cues)+"\n",encoding="utf-8-sig")
    write(job/"final_subtitles.json",dict(style=style,style_sha256=digest(job/"subtitle_style.json"),edited_audio_sha256=rp["edited_audio_sha256"],
          layout=settings,cues=cues,corrections=spec.get("corrections",[]),rejected_degenerate_segments=[s["id"] for s in rejected]))
    (job/"成片字幕稿.md").write_text("# 成片字幕稿\n\n"+"\n\n".join(f"{stamp(c['start'])}–{stamp(c['end'])}　{c['text']}" for c in cues)+"\n",encoding="utf-8-sig")
    m["status"]="subtitles_ready"
    if (job/'subtitle_review_request.json').exists() and read(job/'subtitle_review_request.json').get('required'):
        m['subtitle_review_status']='pending'
    write(job/"manifest.json",m)
    return dict(job=rel(job),captions=len(cues),max_characters=max(len(c["text"]) for c in cues),rejected_degenerate_segments=len(rejected))

def preview(job,text,emphasis,at):
    m=read(job/"manifest.json"); style={**read(SCRIPTS/"config/subtitle_style.json"),**read(job/"subtitle_style.json")}
    info=m.get("media") or media_info(read(job/"source_probe.json"))
    if not 0<=at<info["duration"]: raise ValueError("Preview timestamp is outside source")
    if len(text)>layout(style,info["width"],info["height"])["max_characters"]: raise ValueError("Preview text exceeds safe line width for this frame")
    ass=header(style,info["width"],info["height"])+f"Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{colored(text,emphasis)}\n"
    (job/"subtitle_preview.ass").write_text(ass,encoding="utf-8-sig")
    font_relative=os.path.relpath(SCRIPTS/"fonts",job).replace("\\","/")
    ffmpeg(job,["-loglevel","info","-y","-ss",at,"-i",rooted(m["source_path"]),"-map","0:v:0","-vf",f"ass=subtitle_preview.ass:fontsdir={font_relative}","-frames:v","1","-q:v","2","-update","1","字幕外观预览.jpg"],"subtitle_preview.log")
    log=(job/"subtitle_preview.log").read_text(encoding="utf-8",errors="replace")
    if not any(style["postscript_name"] in line.split("->")[-1] for line in log.splitlines() if "fontselect:" in line): raise ValueError("Preview font did not load; no silent font substitution")
    return dict(preview=rel(job/"字幕外观预览.jpg"),font_confirmed=style["display_name"])
