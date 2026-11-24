"""Local, paired title/cover review across a batch; preferences never select assets."""
import html,json,os
from urllib.parse import quote
from .common import *

def build(folder,data):
    videos=[]
    def url(path):return quote(os.path.relpath(rooted(path),folder).replace('\\','/'),safe='/')
    for i,item in enumerate(data['items'],1):
        if not item.get('job'):continue
        job=rooted(item['job']);package=ROOT/'package'/job.name
        if not (package/'发布包.json').exists():continue
        p=read(package/'发布包.json');m=read(job/'manifest.json')
        if p.get('review_revision_manifest'):
            revision=rooted(p['review_revision_manifest']);revision.relative_to(package)
            p=dict(p,candidates=read(revision)['candidates'])
        candidates=[]
        for c in p['candidates']:
            candidates.append(dict(id=c['id'],title=c['title'],group=c['group'],cover_lines=c['cover_lines'],recommended=c['id'] in p['recommended'],images={k:url(package/v) for k,v in c['images'].items()}))
        videos.append(dict(id=str(item.get('original_number',i)),job=rel(job),package_sha256=digest(package/'发布包.json'),title=p['title'],duration=m.get('final_duration_seconds'),video=url(m['final_path']),transcript=url(package/'成片文字稿.md'),description=p['description'],candidates=candidates))
    if not videos:return None
    payload=json.dumps(videos,ensure_ascii=False).replace('<','\\u003c')
    template=(SCRIPTS/'templates/batch_package_review.html').read_text(encoding='utf-8')
    page=template.replace('__DATA__',payload).replace('__BATCH__',html.escape(data['batch']))
    target=folder/'标题封面集中审阅.html';target.write_text(page,encoding='utf-8')
    write(folder/'标题封面审阅数据.json',dict(batch=data['batch'],videos=videos,excluded=data.get('excluded_items',[])))
    return target
