"""Behavior tests using synthetic media in scripts/cache/selftest, never user media."""
import json
from pathlib import Path
import subprocess
import sys
import uuid

SCRIPTS=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SCRIPTS),str(SCRIPTS/"vendor")]
sys.stdout.reconfigure(encoding="utf-8")
from video_pipeline import common,intake,editing,captions,subtitle_review

def rejects(fn):
    try: fn()
    except (ValueError,FileNotFoundError): return
    raise AssertionError("Expected operation to be rejected")

def main():
    style=common.read(SCRIPTS/"config/subtitle_style.json")
    portrait=captions.layout(style,1080,1920)
    assert portrait["size"]==100 and portrait["max_characters"]==8
    landscape=captions.layout(style,1920,1080)
    assert landscape["size"]==84 and landscape["max_characters"]==16
    fixture=SCRIPTS/"cache/selftest"/uuid.uuid4().hex
    fixture.mkdir(parents=True)
    for folder in ["Inbox","raw","final","process"]: (fixture/folder).mkdir()
    for module in [common,intake,editing,captions]: module.ROOT=fixture
    source=fixture/"Inbox/DJI_20990101000000_fixture.mp4"
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-n","-f","lavfi","-i","testsrc2=size=640x360:rate=25:duration=5",
                    "-f","lavfi","-i","sine=frequency=220:sample_rate=44100:duration=5","-c:v","libx264","-preset","ultrafast","-crf","28","-c:a","aac","-shortest",str(source)],check=True)
    ingested=intake.ingest(str(source))
    job=common.job_path(ingested["job"])
    # Explicit fake ASR fixture: the synthetic sine is not presented as speech.
    common.write(job/"transcript_asr.json",dict(segments=[],fixture=True))
    archived=intake.archive(job,"脚本自检")
    job=common.job_path(archived["job"])
    assert common.digest(common.rooted(archived["source_path"]))==common.read(job/"manifest.json")["original_sha256"]
    spec=job/"edit_spec.json"
    common.write(spec,dict(summary="合成视频测试，不是用户剪辑方案",cuts=[dict(start=1,end=2,text="合成测试段",reason="验证帧率和时间线")]))
    proposal=intake.review(job,spec)
    assert proposal["status"]=="awaiting_edit_approval"
    rejects(lambda:editing.edit(job))
    assert not (job/"edited_audio.wav").exists()
    rejects(lambda:intake.approve(job,"模拟确认","0"*64))
    intake.approve(job,"合成夹具的模拟确认（不对应用户素材）",proposal["plan_sha256"])
    original=(job/"edit_plan.json").read_bytes()
    changed=common.read(job/"edit_plan.json"); changed["cuts"][0]["end"]=2.1
    common.write(job/"edit_plan.json",changed)
    rejects(lambda:editing.edit(job))
    (job/"edit_plan.json").write_bytes(original)
    result=editing.edit(job)
    assert result["fps"]=="25"
    assert abs(result["duration"]-4.32)<0.001
    words=[dict(word=c,start=0.2+i*0.4,end=0.6+i*0.4,probability=1.0) for i,c in enumerate("测试字幕流程")]
    fake_asr=dict(duration=4.32,input_audio_sha256=common.digest(job/"edited/audio.wav"),segments=[dict(id=0,start=.2,end=2.6,text="测试字幕流程",words=words)],fixture=True)
    common.write(job/"edited/transcript_asr.json",fake_asr)
    common.write(job/"caption_spec_bad.json",dict(lines=["不存在的话"]))
    rejects(lambda:captions.subtitles(job,job/"caption_spec_bad.json"))
    common.write(job/'caption_timing.json',dict(lines=[dict(text='测试字幕',start_override=.6,timing_basis='合成夹具已知发音时间'), '流程']))
    captions.subtitles(job,job/'caption_timing.json')
    timed=common.read(job/'final_subtitles.json')['cues']
    assert timed[0]['start']==.6 and ''.join(c['text'] for c in timed)=='测试字幕流程'
    common.write(job/'caption_timing_bad.json',dict(lines=[dict(text='测试字幕',start_override=.6), '流程']))
    rejects(lambda:captions.subtitles(job,job/'caption_timing_bad.json'))
    common.write(job/'caption_timing_bad.json',dict(lines=[dict(text='测试字幕',start_override=1.7,timing_basis='合成夹具过短显示'), '流程']))
    rejects(lambda:captions.subtitles(job,job/'caption_timing_bad.json'))
    common.write(job/"caption_spec.json",dict(lines=[dict(text="测试字幕",emphasis="字幕"),"流程"]))
    captions.subtitles(job,job/"caption_spec.json")
    captions.preview(job,"测试字幕","字幕",.5)
    common.write(job/'subtitle_review_request.json',dict(required=True,user_message='合成夹具要求字幕审核'))
    rejects(lambda:editing.render(job))
    draft=subtitle_review.prepare(job)
    assert (job/'字幕审核_无字剪辑版.mp4').exists() and (job/'字幕审核.html').exists()
    rejects(lambda:subtitle_review.approve(job,'合成夹具字幕确认','0'*64))
    subtitle_review.approve(job,'合成夹具字幕确认（不是用户素材）',draft['subtitle_sha256'])
    ass=(job/'final_subtitles.ass').read_bytes()
    (job/'final_subtitles.ass').write_bytes(ass+b'changed')
    rejects(lambda:editing.render(job))
    (job/'final_subtitles.ass').write_bytes(ass)
    editing.render(job); editing.frames(job)
    verified=editing.verify(job)
    assert verified["technical_checks_passed"] and verified["width"]==640 and verified["video_frames"]==108
    prior_style=(job/"subtitle_style.json").read_bytes()
    altered=common.read(job/"subtitle_style.json"); altered["font_size_at_1080p"]=96
    common.write(job/"subtitle_style.json",altered)
    rejects(lambda:editing.publish(job,"模拟视觉检查"))
    (job/"subtitle_style.json").write_bytes(prior_style)
    published=editing.publish(job,"自动化夹具模拟视觉记录；本测试不是用户成片的人工视觉验收")
    assert common.rooted(published["final_path"]).exists()
    rejects(lambda:editing.publish(job,"不能覆盖已完成输出"))
    rejects(lambda:common.normalize_cuts([dict(start=-1,end=1,text="x",reason="x")],5))
    rejects(lambda:common.normalize_cuts([dict(start=0,end=5,text="x",reason="x")],5))
    report=dict(passed=True,synthetic_fixture_only=True,fixture_path=str(fixture),checks=[
        "ingest/archive preserve source checksum", "unapproved edit blocked", "wrong approval hash rejected",
        "changed approved proposal invalidates approval", "25 fps rather than sample 59.94 fps",
        "44.1 kHz input correctly resampled before sample trims", "caption text mismatch rejected",
        "font loaded and subtitle preview rendered", "full render/decode/verification/publish",
        "completed output cannot be overwritten", "invalid or whole-video deletion rejected",
        "portrait uses 100px and 8 characters while landscape keeps 84px", "changed style invalidates verified publication",
        "requested subtitle review blocks burning until approval", "playable unburned review uses the edited timeline",
        "changed subtitle files invalidate approval", "evidenced subtitle start adjustment preserves text and rejects missing basis or flashing"])
    common.write(SCRIPTS/"cache/selftest/latest_report.json",report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
