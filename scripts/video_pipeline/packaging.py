"""Publication decisions, package materials, and verified local upload delivery."""
import importlib
import json
from pathlib import Path
import shutil
import uuid
from .common import ROOT,SCRIPTS,digest,now,read,rel,rooted,write,move,safe_title

PROFILE_PATH=SCRIPTS.parent/'skill/video-package/references/platforms.json'


def cover_sizes():
    return {k:tuple(v) for k,v in read(PROFILE_PATH)['exports'].items()}


def package_path(job):
    return ROOT/'package'/Path(job).name


def materials_path(job):
    return package_path(job)/'materials'


def tools_module(name):
    return importlib.import_module('tools.'+name)


def prepare(job):return tools_module('build_publication_package').prepare(job)
def build(job,spec):return tools_module('build_publication_package').build(job,spec)
def refine(job,spec):return tools_module('refine_publication_cover').build(job,spec)
def check(job):return tools_module('build_publication_package').check(package_path(job))


def event(package,kind,data):
    path=package/'events'/(now().replace(':','-')+'_'+uuid.uuid4().hex[:8]+'.json')
    write(path,dict(kind=kind,created_at_utc=now(),**data))
    return path


def migrate(job):
    """One-time migration of old publication-only materials; edit evidence stays in process."""
    from PIL import Image
    package=package_path(job)
    old=rooted(Path(job)/'publishing')
    new=rooted(materials_path(job))
    old.relative_to(rooted(job));new.relative_to(rooted(package))
    if not old.exists():
        if new.is_dir():return dict(status='already_migrated',materials=rel(new))
        raise FileNotFoundError(str(old))
    if new.exists():raise FileExistsError('Do not merge publication histories: '+str(new))
    if not (package/'发布包.json').is_file():raise ValueError('Create or locate the package before migration')
    before={p.relative_to(old).as_posix():digest(p) for p in old.rglob('*') if p.is_file()}
    # Both absolute resolved directories were checked against their exact workspace parents above.
    move(old,new)
    if before!={p.relative_to(new).as_posix():digest(p) for p in new.rglob('*') if p.is_file()}:
        raise ValueError('Migration checksum mismatch; preserved files require inspection')
    old_prefix,new_prefix=rel(old),rel(new)
    replacements=0
    for path in package.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in ['.json','.md','.html','.txt']:continue
        if 'history' in path.relative_to(package).parts:continue
        content=path.read_text(encoding='utf-8-sig')
        if old_prefix in content:
            path.write_text(content.replace(old_prefix,new_prefix),encoding='utf-8')
            replacements+=1
    data=read(package/'发布包.json')
    data['materials_dir']=rel(new)
    first=data['candidates'][0]
    data['cover_export_sizes']={key:list(Image.open(package/path).size) for key,path in first['images'].items()}
    data['legacy_spec_sha256']=data['spec_sha256']
    data['spec_sha256']=digest(new/'package_spec.json')
    write(package/'发布包.json',data)
    report=dict(status='migrated',source=old_prefix,target=new_prefix,files=len(before),
                all_files_verified_before_reference_updates=True,text_references_updated=replacements,
                original_file_hashes=before,created_at_utc=now(),
                history_note='history snapshots keep original paths; this mapping resolves their former location')
    write(package/'migration.json',report)
    tools_module('build_publication_package').write_gallery(package,data)
    return {k:v for k,v in report.items() if k!='original_file_hashes'}


def feedback(job,spec):
    package=package_path(job);data=read(package/'发布包.json')
    source=rooted(spec);source.relative_to(package)
    value=read(source)
    if value.get('action') not in ['narrow','revise'] or not value.get('message','').strip():
        raise ValueError('Feedback requires narrow/revise and the actual user message')
    ids=value.get('candidate_ids',[])
    if not set(ids)<=set(c['id'] for c in data['candidates']):raise ValueError('Unknown candidate ID')
    if value['action']=='narrow' and not ids:raise ValueError('Narrowing requires candidate IDs')
    event(package,value['action'],value)
    data.update(status='awaiting_revision' if value['action']=='revise' else 'shortlisted',shortlist=ids)
    write(package/'发布包.json',data)
    if (package/'发布选择.json').exists():
        selection=read(package/'发布选择.json');selection['status']='superseded_by_feedback'
        write(package/'发布选择.json',selection)
    return dict(status=data['status'],shortlist=ids)


def text_body(path):
    text=path.read_text(encoding='utf-8-sig')
    return text.split('\n\n',1)[1] if text.startswith('#') and '\n\n' in text else text


def verify_source(package,data):
    source=rooted(data['source_job']);m=read(source/'manifest.json')
    if m['status']!='completed' or m['final_sha256']!=data['final_sha256']:
        raise ValueError('Package is not linked to the current verified final')
    if digest(rooted(m['final_path']))!=m['final_sha256']:raise ValueError('Final source changed')
    if digest(source/'final_subtitles.json')!=data['subtitle_sha256']:raise ValueError('Final captions changed')
    normal=tools_module('build_publication_package').normalized
    if normal(text_body(package/'成片文字稿.md'))!=normal(''.join(c['text'] for c in read(source/'final_subtitles.json')['cues'])):
        raise ValueError('Publication transcript does not match the final video captions')
    return source,m


def select(job,spec,message):
    from PIL import Image
    package=package_path(job);data=read(package/'发布包.json')
    source,m=verify_source(package,data)
    if not message.strip():raise ValueError('Selection requires the actual final-choice message')
    spec_path=rooted(spec);spec_path.relative_to(package)
    value=read(spec_path)
    for name in ['publication_title','cover_text','cover_directory','visual_note']:
        if not str(value.get(name,'')).strip():raise ValueError('Selection is missing '+name)
    folder=rooted(value['cover_directory']);folder.relative_to(package)
    if 'history' in folder.relative_to(package).parts:raise ValueError('Select actual assets, not a history snapshot')
    covers={}
    for ratio in cover_sizes():
        path=folder/f'封面_{ratio}.jpg'
        with Image.open(path) as image:
            w,h=image.size;rw,rh=map(int,ratio.split('x'))
            if w*rh!=h*rw or image.format!='JPEG':raise ValueError('Incorrect cover ratio: '+ratio)
            image.verify()
        covers[ratio]=dict(path=rel(path),sha256=digest(path),size=[w,h])
    description=value.get('description',(package/'通用发布说明.txt').read_text(encoding='utf-8-sig').strip())
    if not description.strip():raise ValueError('Publication description is empty')
    if (package/'发布选择.json').exists():event(package,'selection_history',dict(previous=read(package/'发布选择.json')))
    selection=dict(schema_version=1,status='selected',publication_title=value['publication_title'],
                   cover_text=value['cover_text'],cover_directory=rel(folder),covers=covers,
                   description=description,transcript_path=rel(package/'成片文字稿.md'),
                   transcript_sha256=digest(package/'成片文字稿.md'),final_path=m['final_path'],
                   final_sha256=m['final_sha256'],subtitle_sha256=data['subtitle_sha256'],
                   user_message=message,visual_note=value['visual_note'],spec_sha256=digest(spec_path),
                   selected_at_utc=now())
    event(package,'final_selection',dict(selection=selection))
    write(package/'发布选择.json',selection)
    write(materials_path(job)/'current_selection.json',dict(canonical_selection=rel(package/'发布选择.json'),
          note='Current selection lives in the package root; earlier records are in events/history'))
    data.update(status='selected',selected_candidate=None,selected_publication_title=value['publication_title'],
                selected_cover_text=value['cover_text'],selected_cover_directory=rel(folder),cover_revision=rel(folder.parent))
    write(package/'发布包.json',data)
    (package/'发布标题.txt').write_text(value['publication_title']+'\n',encoding='utf-8-sig')
    (package/'封面文案.txt').write_text(value['cover_text']+'\n',encoding='utf-8-sig')
    tools_module('build_publication_package').write_gallery(package,data)
    return dict(status='selected',title=value['publication_title'],cover_directory=rel(folder),covers=len(covers))


def upload_ready(job,revision=None):
    package=package_path(job);data=read(package/'发布包.json')
    _,m=verify_source(package,data)
    selection=read(package/'发布选择.json')
    if data['status']!='selected' or selection.get('status')!='selected' or not selection.get('user_message'):
        raise ValueError('Record an explicit final selection before preparing upload')
    if selection['final_sha256']!=m['final_sha256'] or selection['subtitle_sha256']!=data['subtitle_sha256']:
        raise ValueError('Selection belongs to another final video')
    if digest(rooted(selection['transcript_path']))!=selection['transcript_sha256']:
        raise ValueError('Transcript changed after selection')
    for cover in selection['covers'].values():
        if digest(rooted(cover['path']))!=cover['sha256']:raise ValueError('Selected cover changed after selection')
    suffix='__'+safe_title(revision) if revision else ''
    target=rooted(ROOT/'upload'/(Path(job).name+suffix))
    if target.exists():raise FileExistsError('Do not overwrite an existing upload delivery: '+str(target))
    staging=rooted(target.parent/('.staging-'+uuid.uuid4().hex))
    staging.mkdir(parents=True)
    (staging/'标题.txt').write_text(selection['publication_title']+'\n',encoding='utf-8-sig')
    (staging/'视频说明.txt').write_text(selection['description']+'\n',encoding='utf-8-sig')
    shutil.copy2(rooted(m['final_path']),staging/'最终成片.mp4')
    shutil.copy2(rooted(selection['transcript_path']),staging/'视频文字稿.md')
    (staging/'封面').mkdir()
    for ratio,cover in selection['covers'].items():
        dest=staging/'封面'/f'封面_{ratio}.jpg';shutil.copy2(rooted(cover['path']),dest)
        if digest(dest)!=cover['sha256']:raise ValueError('Copied cover checksum mismatch')
    if digest(staging/'最终成片.mp4')!=m['final_sha256']:raise ValueError('Copied video checksum mismatch')
    files={p.relative_to(staging).as_posix():digest(p) for p in staging.rglob('*') if p.is_file()}
    move(staging,target)
    manifest=dict(schema_version=1,status='upload_ready',upload_path=rel(target),
                  selection_sha256=digest(package/'发布选择.json'),source_final=m['final_path'],
                  selected_cover_directory=selection['cover_directory'],files=files,created_at_utc=now(),
                  posted_to_platform=False)
    if (package/'upload_manifest.json').exists():
        event(package,'previous_upload_delivery',dict(manifest=read(package/'upload_manifest.json')))
    write(package/'upload_manifest.json',manifest)
    data.update(status='upload_ready',upload_path=rel(target));write(package/'发布包.json',data)
    tools_module('build_publication_package').write_gallery(package,data)
    (package/'选择说明.md').write_text(
        '# 最终发布选择\n\n标题：'+selection['publication_title']+'\n\n封面文字：'+selection['cover_text']+
        '\n\n选定封面：`'+selection['cover_directory']+'`\n\n待上传目录：`'+rel(target)+
        '`\n\n成片、所选封面和文字均已复制并核对哈希，final与package保留归档。'
        '本目录保存全部候选和历轮修改。材料准备完成，不代表已经对外发布。\n',encoding='utf-8-sig')
    event(package,'upload_ready',dict(upload_path=rel(target),selection_sha256=manifest['selection_sha256']))
    return upload_check(job)


def upload_check(job):
    package=package_path(job);data=read(package/'发布包.json')
    verify_source(package,data)
    manifest=read(package/'upload_manifest.json');selection=read(package/'发布选择.json')
    if manifest['selection_sha256']!=digest(package/'发布选择.json'):
        raise ValueError('Final selection changed after delivery')
    target=rooted(manifest['upload_path']);target.relative_to(ROOT/'upload')
    actual={p.relative_to(target).as_posix():digest(p) for p in target.rglob('*') if p.is_file()}
    if actual!=manifest['files']:raise ValueError('Upload delivery is incomplete or changed')
    if (target/'标题.txt').read_text(encoding='utf-8-sig').strip()!=selection['publication_title']:
        raise ValueError('Upload title differs from the selected title')
    for ratio,c in selection['covers'].items():
        if digest(rooted(c['path']))!=c['sha256']:raise ValueError('Selected archive cover changed')
        if digest(target/'封面'/f'封面_{ratio}.jpg')!=c['sha256']:raise ValueError('Wrong selected cover was copied')
    report=dict(passed=True,upload_path=rel(target),files=len(actual),title=selection['publication_title'],
                selected_cover_directory=selection['cover_directory'],video_and_covers_verified=True,
                archives_preserved=True,posted_to_platform=False,checked_at_utc=now())
    write(package/'upload_verification.json',report)
    return report
