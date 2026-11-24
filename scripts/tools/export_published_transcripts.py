"""Export verified published transcripts to a numbered Markdown collection."""
import argparse,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_pipeline.common import *
from video_pipeline import packaging

def export(batch,vault):
 destination=Path(vault).resolve()
 if not destination.is_dir():raise ValueError('Existing destination folder required')
 data=read(ROOT/'review'/batch/'batch.json');pending=[]
 numbers=[int(m.group(1)) for p in destination.glob('*.md') if (m:=re.match(r'^(\d+)\s',p.name))]
 number=max(numbers,default=0)
 for item in data['items']:
  job=rooted(item['job']);pkg=packaging.package_path(job);delivery=read(pkg/'upload_manifest.json')
  if not delivery.get('posted_to_platform'):raise ValueError('User-confirmed publication required: '+job.name)
  packaging.upload_check(job)
  selection=read(pkg/'发布选择.json');source=rooted(selection['transcript_path'])
  record=pkg/'obsidian_export.json'
  if record.exists():
   old=read(record);target=Path(old['destination'])
   if target.parent!=destination or not target.exists() or digest(target)!=old['sha256']:raise ValueError('Prior export changed; review manually')
   continue
  number+=1
  title=re.sub(r'[<>:"/\\|?*\x00-\x1f]','',selection['publication_title']).rstrip('. ')
  target=destination/f'{number:02} {title}.md'
  if target.exists():raise FileExistsError(target)
  pending.append((source,target,record,selection['publication_title']))
 for source,target,record,title in pending:
  with target.open('xb') as output:output.write(source.read_bytes())
  assert digest(source)==digest(target)
  write(record,dict(destination=str(target),sha256=digest(target),source=rel(source),publication_title=title,exported_at_utc=now()))
  print(target,flush=True)
 return len(pending)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',required=True);p.add_argument('--vault',required=True);a=p.parse_args();print('Exported:',export(a.batch,a.vault))
