"""Behavioral publication tests on newly generated synthetic media, not user files."""
import json
from pathlib import Path
import subprocess
import sys

SCRIPTS=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SCRIPTS),str(SCRIPTS/'vendor')]
sys.stdout.reconfigure(encoding='utf-8')
from video_pipeline import common,packaging
from tools import build_publication_package as builder,refine_publication_cover as refiner


def rejects(fn):
    try:fn()
    except (ValueError,FileNotFoundError,FileExistsError):return
    raise AssertionError('Expected the operation to be rejected')


def main():
    subprocess.run([sys.executable,'-X','utf8',str(SCRIPTS/'tests/test_workflow.py')],check=True,stdout=subprocess.DEVNULL)
    fixture=Path(common.read(SCRIPTS/'cache/selftest/latest_report.json')['fixture_path'])
    for module in [common,packaging,builder,refiner]:module.ROOT=fixture
    job=next((fixture/'process').iterdir())
    result=packaging.prepare(job)
    package=packaging.package_path(job);materials=packaging.materials_path(job)
    assert 'package/' in result['sheet'] and not (job/'publishing').exists()
    frames=common.read(materials/'frames.json')['frames']
    from PIL import Image,ImageOps
    photo=ImageOps.fit(Image.open(common.rooted(frames[0]['path'])).convert('RGB'),(108,192))
    uncut=dict(mode='uncut_photo',landscape_plate=frames[0]['path'])
    portrait=refiner.backdrop(photo,(108,192),uncut)
    assert portrait.tobytes()==ImageOps.fit(photo,(108,192),Image.Resampling.LANCZOS,centering=(.5,.62)).tobytes()
    wide=refiner.backdrop(photo,(192,108),uncut)
    ph=round(108*1.35);pw=round(ph*photo.width/photo.height);y=-round(108*.15)
    expected=photo.resize((pw,ph),Image.Resampling.LANCZOS).crop((0,-y,pw,108-y))
    assert wide.crop((192-pw,0,192,108)).tobytes()==expected.tobytes()
    assert all(0<=f['output_time']<4.32 for f in frames)
    assert packaging.prepare(job)['status']=='existing_materials_preserved'
    spec=dict(description='合成夹具说明，不是真实发布文案',topics=['合成测试'],recommended=['01','07','17'],
              transcript_paragraphs=['测试字幕流程'],platform_notes=[],candidates=[])
    for i in range(1,21):
        spec['candidates'].append(dict(id=f'{i:02}',group=f'合成方向{(i-1)//5+1}',
            title=f'合成测试：方案{i:02}',cover_lines=['测试方案',f'第{i:02}种'],design='highlight' if i%2 else 'direct',
            frame_id=frames[(i-1)%len(frames)]['id'],evidence='合成字幕夹具',rationale='验证独立候选和导出'))
    common.write(materials/'package_spec.json',spec)
    built=packaging.build(job,materials/'package_spec.json')
    assert built['candidates']==20 and built['cover_exports']==80
    rejects(lambda:packaging.upload_ready(job))
    # Simulate an old layout, then test the real migration and reference updates.
    old=common.rooted(job/'publishing');materials=common.rooted(materials)
    old.relative_to(fixture);materials.relative_to(fixture)
    frame_data=common.read(materials/'frames.json')
    for frame in frame_data['frames']:
        frame['path']=frame['path'].replace(common.rel(materials),common.rel(old))
    common.write(materials/'frames.json',frame_data)
    materials.rename(old)
    moved=packaging.migrate(job)
    assert moved['all_files_verified_before_reference_updates'] and not old.exists()
    assert all(common.rooted(f['path']).is_file() for f in common.read(materials/'frames.json')['frames'])
    packaging.check(job)
    common.write(materials/'feedback.json',dict(action='narrow',candidate_ids=['01','20'],message='合成夹具缩小范围'))
    assert packaging.feedback(job,materials/'feedback.json')['status']=='shortlisted'
    common.write(materials/'feedback.json',dict(action='revise',candidate_ids=['01'],message='合成夹具继续改版'))
    assert packaging.feedback(job,materials/'feedback.json')['status']=='awaiting_revision'
    revision=dict(publication_title='合成修订标题',cover_lines=['测试方案','新版'],frame_id=frames[0]['id'],
                  revision_name='测试修订_v2',feedback='合成夹具反馈',variants=[
                      dict(id='new',style='direct',label='新版',description='合成版式')])
    common.write(materials/'revision.json',revision)
    assert packaging.refine(job,materials/'revision.json')['exports']==4
    # Select an earlier cover with a title from another candidate, not the latest revision.
    chosen=package/'候选/01'
    choice=dict(publication_title=spec['candidates'][19]['title'],cover_text='测试方案第01种',
                cover_directory=common.rel(chosen),visual_note='合成夹具验证，不代表用户视觉验收')
    common.write(materials/'final_selection.json',choice)
    rejects(lambda:packaging.select(job,materials/'final_selection.json',''))
    packaging.select(job,materials/'final_selection.json','合成夹具最终选择旧版，与用户无关')
    cover=chosen/'封面_16x9.jpg';original=cover.read_bytes()
    cover.write_bytes(original+b'changed')
    rejects(lambda:packaging.upload_ready(job))
    cover.write_bytes(original)
    transcript=package/'成片文字稿.md';prior=transcript.read_bytes()
    transcript.write_bytes(prior+'额外内容'.encode('utf-8'))
    rejects(lambda:packaging.upload_ready(job))
    transcript.write_bytes(prior)
    ready=packaging.upload_ready(job)
    assert ready['files']==8 and ready['title']==spec['candidates'][19]['title']
    assert ready['selected_cover_directory']==common.rel(chosen)
    target=common.rooted(ready['upload_path'])
    assert (target/'标题.txt').read_text(encoding='utf-8-sig').strip()==choice['publication_title']
    assert common.digest(target/'封面/封面_16x9.jpg')==common.digest(cover)
    assert common.rooted(common.read(job/'manifest.json')['final_path']).exists() and cover.exists()
    rejects(lambda:packaging.upload_ready(job))
    cover.write_bytes(original+b'changed-again')
    rejects(lambda:packaging.upload_check(job))
    cover.write_bytes(original)
    exported=target/'封面/封面_16x9.jpg';exported.write_bytes(exported.read_bytes()+b'changed')
    rejects(lambda:packaging.upload_check(job))
    exported.write_bytes(original)
    packaging.upload_check(job)
    # Feedback invalidates selection; a new explicit choice can produce a named delivery revision.
    common.write(materials/'feedback.json',dict(action='revise',message='合成夹具导出后再修改'))
    packaging.feedback(job,materials/'feedback.json')
    rejects(lambda:packaging.upload_ready(job,'v2'))
    packaging.select(job,materials/'final_selection.json','合成夹具重新选定')
    next_delivery=packaging.upload_ready(job,'v2')
    assert target.exists() and next_delivery['upload_path']!=ready['upload_path']
    report=dict(passed=True,synthetic_fixture_only=True,fixture_path=str(fixture),checks=[
        'duration-aware still extraction in package and existing materials preserved', '20 unique title/cover pairs and 80 actual images',
        'uncut photo mode preserves original portrait and rectangular foreground pixels without matte',
        'publication material migration preserves hashes and updates live references',
        'narrow and revise feedback branches', 'final selection required',
        'mixed title with earlier cover instead of latest revision',
        'changed selected cover or transcript blocks export', 'five material types copied as eight files',
        'video and cover archives preserved', 'changed upload file or source cover detected',
        'existing upload not overwritten', 'new feedback invalidates choice and named delivery preserves older output'])
    common.write(SCRIPTS/'cache/selftest/latest_packaging_report.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
