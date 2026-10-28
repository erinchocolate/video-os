import dataclasses
import time
import wave
from .common import *

def transcribe(job,edited=False,start=None,end=None):
    import numpy as np
    from faster_whisper import WhisperModel
    from opencc import OpenCC
    m=read(job/"manifest.json")
    folder=job/"edited" if edited else job
    wav_path=folder/"audio.wav"
    if edited:
        _,approval=require_approval(job)
        rp=read(job/"render_plan.json")
        if rp["plan_sha256"]!=approval["plan_sha256"]: raise ValueError("Edited audio belongs to an older proposal")
        if digest(job/"edited_audio.wav")!=rp["edited_audio_sha256"]: raise ValueError("Edited audio checksum mismatch")
    if (folder/"transcript_asr.json").exists() and start is None:
        data=read(folder/"transcript_asr.json")
        if data.get("input_audio_sha256")==digest(wav_path):
            return dict(job=rel(job),edited=edited,resumed=True,segments=len(data["segments"]))
        raise ValueError("Audio changed: retain old transcript in history before transcribing again")
    with wave.open(str(wav_path),"rb") as wav:
        if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())!=(1,2,16000): raise ValueError("ASR expects 16 kHz mono PCM WAV")
        audio=np.frombuffer(wav.readframes(wav.getnframes()),dtype="<i2").astype(np.float32)/32768.0
    offset=0 if start is None else start
    finish=len(audio)/16000 if end is None else end
    if not 0<=offset<finish<=len(audio)/16000+0.001: raise ValueError("Invalid transcription range")
    audio=audio[round(offset*16000):round(finish*16000)]
    print("Local ASR: CPU/int8, large-v3-turbo",flush=True)
    started=time.monotonic()
    model=WhisperModel(str(SCRIPTS/"models/large-v3-turbo"),device="cpu",compute_type="int8",cpu_threads=12)
    options=dict(language="zh",beam_size=5,word_timestamps=True,vad_filter=True,
                 vad_parameters=dict(min_silence_duration_ms=400,speech_pad_ms=200),
                 initial_prompt="普通话口播逐字稿。嗯，啊，呃，那个，就是，然后。使用简体中文。",
                 condition_on_previous_text=False,hallucination_silence_threshold=0.5)
    segments,info=model.transcribe(audio,**options)
    cc=OpenCC("t2s"); result=[]
    progress_name="asr_progress.jsonl" if start is None else f"spot_{offset:.2f}_{finish:.2f}.jsonl"
    with (folder/progress_name).open("w",encoding="utf-8") as progress:
        for seg in segments:
            data=dataclasses.asdict(seg)
            data["start"]+=offset; data["end"]+=offset
            for w in data["words"]: w["start"]+=offset; w["end"]+=offset
            data["text_simplified"]=cc.convert(data["text"])
            result.append(data); progress.write(json.dumps(data,ensure_ascii=False)+"\n"); progress.flush()
            print(f"[{stamp(data['start'])}–{stamp(data['end'])}] {data['text_simplified']}",flush=True)
    payload=dict(source_path=m["source_path"],input_audio=rel(wav_path),input_audio_sha256=digest(wav_path),
                 model="large-v3-turbo",device="cpu",compute_type="int8",options=options,edited=edited,
                 duration=finish,range_start=offset,segments=result,elapsed_seconds=round(time.monotonic()-started,1),
                 note="机器转写初稿，未宣称逐句听校；原始识别与词级时间点保留。")
    if start is not None:
        output=folder/f"spot_{offset:.2f}_{finish:.2f}.json"; write(output,payload)
        return dict(spot_check=rel(output),segments=len(result))
    write(folder/"transcript_asr.json",payload)
    accepted,rejected=clean_segments(payload)
    flags=dict(degenerate_segments=[s["id"] for s in rejected],
               low_confidence_words=[w for s in accepted for w in s["words"] if w["probability"]<0.6],
               replacement_character_segments=[s["id"] for s in result if "\ufffd" in s["text"]])
    write(folder/"review_flags.json",flags)
    text="\n".join(f"[{stamp(s['start'])}–{stamp(s['end'])}] {s['text_simplified']}" for s in accepted)+"\n"
    (folder/"transcript_asr.txt").write_text(text,encoding="utf-8-sig")
    (folder/"transcript_asr.srt").write_text("\n\n".join(f"{i}\n{stamp(s['start'],True)} --> {stamp(s['end'],True)}\n{s['text_simplified']}" for i,s in enumerate(accepted,1))+"\n",encoding="utf-8-sig")
    title=m.get("title",m["original_filename"])
    md=f"# {'剪后' if edited else ''}逐字稿：{title}\n\n原片：`{m['source_path']}`\n\n本地识别初稿，保留口头语和重复；时间码对应{'剪后音频' if edited else '原片'}。待复核项见 `review_flags.json`；原始词级结果见 `transcript_asr.json`。\n\n"
    md+="\n\n".join(f"**{stamp(s['start'])}–{stamp(s['end'])}**\n\n{s['text_simplified'].replace(',', '，')}" for s in accepted)+"\n"
    (folder/"逐字稿.md").write_text(md,encoding="utf-8-sig")
    if not edited and m["status"]=="ingested": m["status"]="transcribed"; write(job/"manifest.json",m)
    return dict(job=rel(job),edited=edited,segments=len(accepted),flagged_degenerate_segments=len(rejected),elapsed_seconds=payload["elapsed_seconds"])

def correct_transcript(job,spec_path,edited=False):
    folder=job/"edited" if edited else job
    spec=read(rooted(spec_path))
    corrections=spec if isinstance(spec,list) else spec.get("corrections",[])
    if not corrections: raise ValueError("No transcript corrections supplied")
    output=folder/"逐字稿.md"
    original=folder/"history/逐字稿_识别初稿.md"
    if not original.exists():
        original.parent.mkdir(parents=True,exist_ok=True)
        original.write_bytes(output.read_bytes())
    text=original.read_text(encoding="utf-8-sig")
    notes=[]
    for c in corrections:
        before,after=c["from"],c["to"]
        basis=c.get("basis") or c.get("reason")
        if not basis or not before or not after: raise ValueError("Corrections need from/to and basis/reason")
        if text.count(before)!=1: raise ValueError(f"Use a unique full phrase to identify correction: {before!r}")
        text=text.replace(before,after,1)
        notes.append(f"- {before} → {after}：{basis}")
    output.write_text(text+"\n\n## 校对记录\n\n"+"\n".join(notes)+"\n",encoding="utf-8-sig")
    write(folder/"transcript_corrections.json",corrections)
    return dict(transcript=rel(output),corrections=len(corrections),raw_asr_preserved=True)
