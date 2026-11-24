"""Archive a complete manually published batch, preserving delivery hashes."""
import argparse,sys,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_pipeline.common import *
from video_pipeline import packaging,batch

def archive(name,message):
 if not message.strip():raise ValueError('User publication confirmation required')
 source=(ROOT/'upload'/name).resolve();target=(ROOT/'upload/published'/name).resolve()
 source.relative_to((ROOT/'upload').resolve());target.relative_to((ROOT/'upload/published').resolve())
 if source.parent!=ROOT/'upload' or target.exists():raise ValueError('Invalid batch or archive already exists')
 data=read(ROOT/'review'/name/'batch.json');records=[]
 for item in data['items']:
  job=rooted(item['job']);pkg=packaging.package_path(job)
  packaging.upload_check(job)
  manifest=read(pkg/'upload_manifest.json');old=rooted(manifest['upload_path'])
  old.relative_to(source)
  records.append((job,pkg,manifest,old))
 before={p.relative_to(source).as_posix():digest(p) for p in source.rglob('*') if p.is_file()}
 target.parent.mkdir(exist_ok=True);shutil.move(str(source),str(target))
 assert before=={p.relative_to(target).as_posix():digest(p) for p in target.rglob('*') if p.is_file()}
 for job,pkg,m,old in records:
  m.update(upload_path=rel(target/old.relative_to(source)),posted_to_platform=True,publication_confirmation=message,published_at_utc=now())
  write(pkg/'upload_manifest.json',m)
  p=read(pkg/'发布包.json');p.update(status='published',upload_path=m['upload_path']);write(pkg/'发布包.json',p)
  packaging.upload_check(job)
  packaging.event(pkg,'user_reported_published',dict(message=message,archive=m['upload_path']))
 write(target/'发布归档记录.json',dict(batch=name,user_message=message,platforms='用户未逐一列明',files_verified=before,archived_at_utc=now()))
 data.update(review_archived=True,review_archived_at_utc=now())
 write(ROOT/'review'/name/'batch.json',data)
 batch.refresh(name)
 return rel(target)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',required=True);p.add_argument('--message',required=True);a=p.parse_args();print(archive(a.batch,a.message))
