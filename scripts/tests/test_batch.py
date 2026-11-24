"""Batch rough cuts must never manufacture content approval."""
import sys
import subprocess
import uuid
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SCRIPTS),str(SCRIPTS/'vendor')]
from video_pipeline import common,intake,editing,captions,batch

def rejects(fn):
    try: fn()
    except (ValueError,FileNotFoundError): return
    raise AssertionError('Expected rejection')

def main():
    fixture=SCRIPTS/'cache/selftest'/uuid.uuid4().hex
    for name in ('Inbox','raw','process','review','upload'): (fixture/name).mkdir(parents=True)
    for module in (common,intake,editing,captions,batch): module.ROOT=fixture
    source=fixture/'Inbox/DJI_20990101000000_fixture.mp4'
    subprocess.run(['ffmpeg','-v','error','-n','-f','lavfi','-i','testsrc2=size=320x240:rate=30000/1001:duration=4',
        '-f','lavfi','-i','sine=frequency=300:sample_rate=44100:duration=4','-c:v','libx264','-preset','ultrafast',
        '-c:a','aac','-shortest',str(source)],check=True)
    batch.create('fixture')
    job=common.job_path(intake.ingest(source)['job'])
    m=common.read(job/'manifest.json');m['batch_id']='fixture';common.write(job/'manifest.json',m)
    common.write(job/'transcript_asr.json',dict(duration=4,segments=[dict(id=0,start=.2,end=.8,text='测试',words=[dict(word='测试',start=.2,end=.8,probability=1)])]))
    job=common.job_path(intake.archive(job,'测试')['job'])
    spec=job/'edit_spec.json';common.write(spec,dict(summary='Synthetic fixture',cuts=[dict(start=1,end=2,text='tone',reason='test')]))
    plan=intake.review(job,spec)
    r=batch.rough(job)
    assert not (job/'approval.json').exists() and not (job/'edited_audio.wav').exists()
    rejects(lambda:editing.edit(job))
    rejects(lambda:intake.approve(job,'fixture',plan['plan_sha256']))
    rejects(lambda:intake.approve(job,'fixture',plan['plan_sha256'],'stale'))
    assert batch.refresh('fixture')['ready']==1
    assert batch.rough(job)['version']==r['version']
    video=common.rooted(r['video']);original=video.read_bytes();video.write_bytes(original+b'changed')
    rejects(lambda:intake.approve(job,'fixture',plan['plan_sha256'],r['version']))
    video.write_bytes(original)
    intake.approve(job,'Synthetic approval, not user media',plan['plan_sha256'],r['version'])
    video.write_bytes(original+b'changed after approval')
    rejects(lambda:editing.edit(job))
    video.write_bytes(original)
    editing.edit(job)
    timeline=common.read(job/'render_plan.json'); assert timeline['keeps']==common.read(common.rooted(r['timeline']))['keeps']
    old=common.read(spec);old['cuts'][0]['end']=2.2;common.write(spec,old);intake.review(job,spec)
    rejects(lambda:batch.validate_rough(job,r['version']))
    rejects(lambda:editing.edit(job))
    r2=batch.rough(job);assert r2['version']!=r['version'] and video.exists()
    from unittest.mock import patch
    def synthetic_asr(job,rough=False):
        assert rough
        folder=common.rooted(common.read(job/'rough_current.json')['video']).parent
        assert (folder/'audio.wav').is_file()
        common.write(folder/'transcript_asr.json',dict(duration=3,fixture=True,input_audio_sha256=common.digest(folder/'audio.wav'),segments=[dict(id=0,start=.2,end=.8,text='测试',text_simplified='测试',words=[dict(word='测试',start=.2,end=.8,probability=1)])]))
    with patch('video_pipeline.asr.transcribe',synthetic_asr):
        recognized=batch.transcribe_rough(job)
    assert recognized['transcript_method']=='rough_audio_asr'
    assert batch.validate_rough(job)['transcript_sha256']==recognized['transcript_sha256']
    assert (common.rooted(recognized['video']).parent/'history/mapped_transcript/逐字稿.html').exists()
    assert not common.read(job/'manifest.json')['editing_approved']
    batch.refresh('fixture')
    assert batch.check('fixture')['passed']
    page=fixture/'review/fixture/审片清单.html';original_page=page.read_text(encoding='utf-8')
    page.write_text(original_page+'<a href="missing.mp4">broken</a>',encoding='utf-8')
    assert not batch.check('fixture')['passed']
    page.write_text(original_page,encoding='utf-8')
    # Short noise spikes inside one long pause must not create flash-frame islands.
    common.write(job/'silences.json',[dict(start=0,end=.8,duration=.8),dict(start=2,end=3,duration=1),dict(start=3.02,end=3.7,duration=.68)])
    common.write(spec,dict(summary='Synthetic pause-policy regression',cuts=[],pause_policy=dict(merge_noise_gap=.08,padding=.08,trim_empty_edges=True,preserve_ranges=[[0,1]])))
    intake.review(job,spec,trim_pauses=True)
    cuts=common.read(job/'edit_plan.json')['cuts']
    assert len(cuts)==1 and abs(cuts[0]['start']-2.08)<1e-6 and abs(cuts[0]['end']-3.62)<1e-6
    print('PASS: unapproved preview, exact timeline, version and artifact guards, revisions, batch links')

if __name__=='__main__':main()
