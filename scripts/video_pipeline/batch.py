"""Batch intake and versioned, explicitly unapproved rough-cut review."""
import html
import shutil
from urllib.parse import quote,unquote
from html.parser import HTMLParser
from .common import *


def batch_path(name):
    if name != safe_title(name) or name in ('.','..'): raise ValueError('Invalid batch name')
    return rooted(ROOT/'review'/name)


def create(name):
    folder=batch_path(name); manifest=folder/'batch.json'
    if manifest.exists(): return read(manifest)
    files=sorted(p for p in (ROOT/'Inbox').iterdir() if p.suffix.lower() in ('.mp4','.mov','.mkv'))
    if not files: raise ValueError('Inbox has no videos')
    data=dict(batch=name,created_at_utc=now(),items=[dict(source=rel(p),original_filename=p.name,status='queued') for p in files])
    write(manifest,data); refresh(name)
    return data


def resolve(item):
    if item.get('job') and rooted(item['job']).is_dir(): return job_path(item['job'])
    matches=[p.parent for p in (ROOT/'process').glob('*/manifest.json') if read(p).get('original_filename')==item['original_filename']]
    if len(matches)>1: raise ValueError('Ambiguous original filename')
    return matches[0] if matches else None


def prepare(name):
    from . import intake,asr
    path=batch_path(name)/'batch.json'; data=read(path)
    for item in data['items']:
        try:
            job=resolve(item)
            if job is None: job=job_path(intake.ingest(item['source'])['job'])
            m=read(job/'manifest.json')
            if m.get('batch_id') not in (None,name): raise ValueError('Video already belongs to another batch')
            m['batch_id']=name; write(job/'manifest.json',m)
            item.update(job=rel(job),status='transcribing'); item.pop('error',None)
            write(path,data); refresh(name)
            asr.transcribe(job)
            item['status']='needs_edit_spec'
        except Exception as exc:
            item.update(status='failed',error=str(exc))
        write(path,data); refresh(name)
    return data


def validate_rough(job,version=None):
    r=read(job/'rough_current.json')
    if version and r['version']!=version: raise ValueError('Approval refers to another rough version')
    if r['plan_sha256']!=digest(job/'edit_plan.json'): raise ValueError('Rough cut is stale; regenerate it')
    m=read(job/'manifest.json')
    if r['source_sha256']!=m['original_sha256'] or digest(rooted(m['source_path']))!=r['source_sha256']:
        raise ValueError('Rough source changed')
    for key in ('video','transcript','timeline'):
        if digest(rooted(r[key]))!=r[key+'_sha256']: raise ValueError('Rough artifact changed: '+key)
    return r


def rough(job):
    from .editing import build_timeline,video_filter
    from opencc import OpenCC
    m=read(job/'manifest.json'); plan=read(job/'edit_plan.json'); ph=digest(job/'edit_plan.json')
    if m['status']=='completed': raise ValueError('Do not replace a completed video')
    if plan['source_sha256']!=m['original_sha256'] or digest(rooted(m['source_path']))!=m['original_sha256']:
        raise ValueError('Source hash mismatch')
    version=ph[:12]
    if (job/'rough_current.json').exists() and read(job/'rough_current.json')['plan_sha256']==ph:
        return validate_rough(job)
    base=batch_path(m['batch_id'])/timestamp_name(m['capture_timestamp']) if m.get('batch_id') else job/'rough'
    folder=base/version
    if folder.exists():
        # A partial failed render is retained; retry in a new folder.
        folder=base/(version+'_'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S'))
    folder.mkdir(parents=True)
    rp=build_timeline(job,m,ph); write(folder/'timeline.json',rp)
    n=len(rp['keeps']); samples=rp['target_audio_samples']
    scale="scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2"
    vg=video_filter(job,rp,False).replace('[0:v:0]',f'[0:v:0]{scale},',1)
    ag=[f'[0:a:0]aresample=48000,asplit={n}'+''.join(f'[as{i}]' for i in range(n))]
    for i,c in enumerate(rp['keeps']):
        ss,es=round(c['source_start']*48000),round(c['source_end']*48000)
        duration=(es-ss)/48000
        ag.append(f'[as{i}]atrim=start_sample={ss}:end_sample={es},asetpts=PTS-STARTPTS,afade=t=in:d=0.004,afade=t=out:st={max(0,duration-.004):.8f}:d=0.004[a{i}]')
    ag.append(''.join(f'[a{i}]' for i in range(n))+f'concat=n={n}:v=0:a=1,apad=whole_len={samples},atrim=end_sample={samples}[aout]')
    (folder/'rough.ffgraph').write_text(vg+';'+';'.join(ag),encoding='utf-8')
    ffmpeg(folder,['-loglevel','error','-n','-filter_complex_threads','4','-i',rooted(m['source_path']),
        '-filter_complex_script','rough.ffgraph','-map','[vout]','-map','[aout]','-c:v','libx264','-preset','veryfast',
        '-crf','24','-threads','8','-pix_fmt','yuv420p','-fps_mode','cfr','-r',rp['fps'],'-c:a','aac','-b:a','128k',
        '-ar','48000','-movflags','+faststart','粗剪.mp4'],'render.log')
    p=probe(folder/'粗剪.mp4',True)
    v=next(s for s in p['streams'] if s['codec_type']=='video'); a=next(s for s in p['streams'] if s['codec_type']=='audio')
    if int(v['nb_read_frames'])!=rp['total_frames'] or abs(float(a['duration'])-float(v['duration']))>.06:
        raise ValueError('Rough cut frame count or A/V duration mismatch')
    ffmpeg(folder,['-v','error','-xerror','-i','粗剪.mp4','-f','null','-'],'decode.log')
    cc=OpenCC('t2s'); rows=[]; boundary=[]
    segments,_=clean_segments(read(job/'transcript_asr.json'))
    def mapped(t):
        for c in rp['keeps']:
            if t<c['source_start']: return c['output_start']
            if t<=c['source_end']: return c['output_start']+t-c['source_start']
        return rp['content_frames']/float(Fraction(rp['fps']))
    speech=[c for c in plan['cuts'] if c['kind']=='speech']
    for seg in segments:
        words=[w for w in seg.get('words',[]) if not any(c['start']<=(w['start']+w['end'])/2<c['end'] for c in speech)]
        if not words: continue
        start,end=mapped(words[0]['start']),mapped(words[-1]['end'])
        text=cc.convert(''.join(w['word'] for w in words)).strip()
        rows.append(dict(start=round(start,3),end=round(max(start,end),3),text=text))
        for w in words:
            if any(w['start']<edge<w['end'] for c in rp['keeps'] for edge in (c['source_start'],c['source_end'])):
                boundary.append(round(mapped(w['start']),3))
    note='原片机器转写按实际帧时间线映射到粗剪；未重新识别、未逐句人工听校。请重点核对切点和识别疑点。'
    md=f"# {m['title']} · 粗剪 {version}\n\n{note}\n\n"+'\n\n'.join(f"**{stamp(r['start'])}–{stamp(r['end'])}** {r['text']}" for r in rows)
    (folder/'逐字稿.md').write_text(md,encoding='utf-8-sig')
    content='<h1>'+html.escape(m['title'])+'</h1><p>'+note+'</p>'+''.join(f"<p><b>{stamp(r['start'])}–{stamp(r['end'])}</b> {html.escape(r['text'])}</p>" for r in rows)
    (folder/'逐字稿.html').write_text('<meta charset="utf-8"><style>body{max-width:850px;margin:40px auto;font:18px/1.8 sans-serif}</style>'+content,encoding='utf-8')
    write(folder/'transcript.json',dict(note=note,rows=rows,boundary_review_seconds=boundary))
    if digest(job/'edit_plan.json')!=ph:
        write(folder/'superseded.json',dict(reason='Edit plan changed while this preview was rendering',rendered_plan_sha256=ph,current_plan_sha256=digest(job/'edit_plan.json')))
        raise ValueError('Edit plan changed during rendering; retain this attempt and regenerate the current plan')
    shutil.copy2(job/'edit_plan.json',folder/'edit_plan.json')
    r=dict(version=version,plan_sha256=ph,source_sha256=m['original_sha256'],status='awaiting_rough_approval',
           video=rel(folder/'粗剪.mp4'),transcript=rel(folder/'逐字稿.html'),timeline=rel(folder/'timeline.json'),
           duration=rp['total_duration'],original_duration=m['duration_seconds'],boundary_review_seconds=boundary,
           verified_frames=rp['total_frames'],decode_verified=True,note=note,created_at_utc=now())
    for key in ('video','transcript','timeline'): r[key+'_sha256']=digest(rooted(r[key]))
    write(folder/'rough.json',r); write(job/'rough_current.json',r)
    m.update(status='awaiting_rough_approval',editing_approved=False); write(job/'manifest.json',m)
    return r


def transcribe_rough(job):
    """Recognize the actual preview audio, retaining the earlier mapped evidence."""
    from . import asr
    r=validate_rough(job); folder=rooted(r['video']).parent
    if r.get('transcript_method')=='rough_audio_asr': return r
    history=folder/'history/mapped_transcript';history.mkdir(parents=True,exist_ok=True)
    for filename in ('逐字稿.md','逐字稿.html','transcript.json','rough.json'):
        source=folder/filename
        if source.exists() and not (history/filename).exists(): shutil.copy2(source,history/filename)
    if not (folder/'audio.wav').exists():
        ffmpeg(folder,['-v','error','-n','-i','粗剪.mp4','-map','0:a:0','-ac','1','-ar','16000','-c:a','pcm_s16le','audio.wav'],'rough_audio_extract.log')
    asr.transcribe(job,rough=True)
    data=read(folder/'transcript_asr.json');segments,rejected=clean_segments(data)
    rows=[dict(start=s['start'],end=s['end'],text=s['text_simplified'].replace(',','，')) for s in segments]
    note='直接从当前粗剪音频重新机器转写；时间码对应粗剪。未逐句人工听校，专有名词和同音字仍需核对。'
    title=read(job/'manifest.json')['title']
    md=f"# {title} · 粗剪 {r['version']}\n\n{note}\n\n"+'\n\n'.join(f"**{stamp(s['start'])}–{stamp(s['end'])}** {s['text']}" for s in rows)
    (folder/'逐字稿.md').write_text(md,encoding='utf-8-sig')
    body=f'<h1>{html.escape(title)}</h1><p>{note}</p>'+''.join(f"<p><b>{stamp(s['start'])}–{stamp(s['end'])}</b> {html.escape(s['text'])}</p>" for s in rows)
    (folder/'逐字稿.html').write_text('<meta charset="utf-8"><style>body{max-width:850px;margin:40px auto;font:18px/1.8 sans-serif}</style>'+body,encoding='utf-8')
    write(folder/'transcript.json',dict(note=note,rows=rows,excluded_degenerate_segments=[s['id'] for s in rejected]))
    r.update(transcript_method='rough_audio_asr',note=note,transcript_sha256=digest(folder/'逐字稿.html'),
             transcript_audio_sha256=data['input_audio_sha256'],transcribed_at_utc=now())
    write(folder/'rough.json',r);write(job/'rough_current.json',r)
    return r


def render_batch(name,transcribe_only=False):
    path=batch_path(name)/'batch.json'; data=read(path)
    for item in data['items']:
        try:
            job=resolve(item)
            if job is None: raise ValueError('Run batch-prepare first')
            item['job']=rel(job); item.pop('error',None)
            if not transcribe_only: rough(job)
            transcribe_rough(job); item['status']='awaiting_rough_approval'
        except Exception as exc: item.update(status='failed',error=str(exc))
        write(path,data); refresh(name)
    return data


def refresh(name):
    folder=batch_path(name); path=folder/'batch.json'; data=read(path); rows=[]; ready=0
    def link(target,label):
        p=rooted(target)
        if not p.is_file(): return '<span>尚未生成</span>'
        href=quote(os.path.relpath(p,folder).replace('\\','/'),safe='/')
        return f'<a href="{href}" target="_blank">{html.escape(label)}</a>'
    for i,item in enumerate(data['items'],1):
        job=resolve(item); title=item['original_filename']; status=item['status']; assets=[]; version=''; issues=[]
        if item.get('error'): issues.append(item['error'])
        if job:
            item['job']=rel(job); m=read(job/'manifest.json'); title=m.get('title') or title
            issues.extend(m.get('review_notes',[]))
            status=m['status'] if not item.get('error') else 'failed'
            if item['status']=='transcribing' and m['status']=='ingested': status='transcribing'
            item['status']=status
            if (job/'rough_current.json').exists():
                r=read(job/'rough_current.json'); version=r['version']
                valid=r['plan_sha256']==digest(job/'edit_plan.json') and all(rooted(r[k]).is_file() for k in ('video','transcript','timeline'))
                if valid:
                    assets+=[link(r['video'],'播放粗剪'),link(r['transcript'],'粗剪逐字稿')]
                    comparison=rooted(r['video']).parent/'修订复核.html'
                    if comparison.exists(): assets.append(link(comparison,'本轮改动 / 切点对照'))
                    if status=='awaiting_rough_approval': ready+=1
                    issues.append(f"原片 {stamp(r['original_duration'])} → 粗剪 {stamp(r['duration'])}")
                    if r['boundary_review_seconds']:
                        points=sorted(set(r['boundary_review_seconds']))
                        issues.append('切点复核线索：'+', '.join(stamp(t) for t in points[:6])+(f' 等 {len(points)} 处' if len(points)>6 else ''))
                else: issues.append('剪辑稿已更新或预览缺失，需重新生成粗剪'); status='stale'
            assets.append(link(job/'剪辑稿_待确认.md','删改明细'))
            if m.get('final_path'): assets.append(link(m['final_path'],'成片预览'))
            package=ROOT/'package'/job.name
            if package.exists():
                if (package/'发布包.json').exists():
                    packaging_status=read(package/'发布包.json').get('status')
                    status={'selected':'标题封面已选定','upload_ready':'待上传材料就绪','published':'已发布并归档'}.get(packaging_status,'待你选标题封面')
                for page in sorted(package.glob('*.html')): assets.append(link(page,'标题封面 · '+page.stem))
                if (package/'upload_manifest.json').exists():
                    delivery=read(package/'upload_manifest.json').get('upload_path')
                    if delivery: assets.append(link(rooted(delivery)/'标题.txt','已选标题'))
        labels={'queued':'排队中','ingested':'待转写','transcribing':'转写中','transcribed':'待编剪辑稿','needs_edit_spec':'待编剪辑稿','archived':'待编剪辑稿','awaiting_edit_approval':'待生成粗剪','awaiting_rough_approval':'待你审粗剪','approved':'内容已确认','completed':'成片完成','failed':'处理失败','stale':'粗剪需更新'}
        key=item['original_filename']+'@'+version
        i=item.get('original_number',i)
        rows.append(f'<tr><td>{i}</td><td><strong>{html.escape(title)}</strong><br><small>{html.escape(version)}</small></td><td>'+ '<br>'.join(assets)+f'</td><td>{html.escape(labels.get(status,status))}</td><td>{html.escape("；".join(issues))}</td><td><textarea data-key="{html.escape(key,quote=True)}" placeholder="通过，或 01:20 删掉第二个例子"></textarea></td></tr>')
    page='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>批次审片清单</title><style>body{font:16px/1.6 system-ui;margin:32px;background:#f4f6f8;color:#182333}table{width:100%;border-collapse:collapse;background:white}th,td{padding:14px;border:1px solid #dbe1e8;text-align:left;vertical-align:top}a{color:#135ab5}textarea{width:230px;height:100px}button{padding:10px 18px;margin:12px 0}small{color:#65758a}</style>'''
    page+=f'<h1>{html.escape(name)} · 集中审阅</h1><p>共 {len(data["items"])} 条，{ready} 条待审粗剪。粗剪未烧录字幕，保留原片；标题封面将在内容确认后准备。</p><p>可直接在聊天中按编号反馈。下方意见仅保存在当前浏览器，点击导出后把文件交给 agent；填写或导出不自动批准。逐字稿的识别来源见各稿说明，均未全片人工听校。</p><button onclick="exportNotes()">导出本批反馈</button><table><thead><tr><th>编号</th><th>视频 / 版本</th><th>审阅材料</th><th>状态</th><th>说明 / 疑问</th><th>你的意见</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'
    page+='''<script>const prefix=location.pathname;document.querySelectorAll('textarea').forEach(t=>{try{t.value=localStorage.getItem(prefix+t.dataset.key)||''}catch(e){}t.oninput=()=>{try{localStorage.setItem(prefix+t.dataset.key,t.value)}catch(e){}}});function exportNotes(){let items=[...document.querySelectorAll('textarea')].filter(t=>t.value.trim()).map(t=>({video_version:t.dataset.key,message:t.value}));let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({page:location.pathname,items},null,2)],{type:'application/json'}));a.download='审片反馈.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}</script></html>'''
    from . import package_review
    gallery=package_review.build(folder,data)
    if gallery:
        page=page.replace('<h1>', '<p>'+link(gallery,'打开标题与封面集中审阅（图片配对）')+'</p><h1>',1)
        page=page.replace('粗剪未烧录字幕，保留原片；标题封面将在内容确认后准备。','已完成条目提供带字幕成片与标题封面候选，原片和粗剪历史均保留。')
    if data.get('excluded_items'):
        page=page.replace('<table>', '<p>已退出本批：'+html.escape('；'.join('原第 '+str(x.get('original_number',''))+' 条：'+x.get('exclusion_reason','') for x in data['excluded_items']))+'。素材和记录保留。</p><table>',1)
    (folder/'审片清单.html').write_text(page,encoding='utf-8'); write(path,data)
    root=ROOT/'review'
    index='<meta charset="utf-8"><h1>视频审阅入口</h1>'+''.join(f'<p><a href="{quote(p.parent.name)}/%E5%AE%A1%E7%89%87%E6%B8%85%E5%8D%95.html">{html.escape(p.parent.name)}</a></p>' for p in sorted(root.glob('*/batch.json'),reverse=True))
    (root/'审阅入口.html').write_text(index,encoding='utf-8')
    return dict(batch=name,total=len(data['items']),ready=ready,page=rel(folder/'审片清单.html'))


def check(name):
    """Check on-disk review links and the exact source/preview fingerprints."""
    folder=batch_path(name); data=read(folder/'batch.json'); results=[]
    for item in data['items']:
        result=dict(video=item['original_filename'],passed=False)
        try:
            job=resolve(item)
            if job is None: raise ValueError('Missing video job')
            r=validate_rough(job)
            if r.get('transcript_method')!='rough_audio_asr': raise ValueError('Rough audio transcription is pending')
            if digest(rooted(r['video']).parent/'audio.wav')!=r['transcript_audio_sha256']:
                raise ValueError('Transcript audio changed')
            result.update(passed=True,version=r['version'],duration=r['duration'],video_path=r['video'],
                          source_hash_verified=True,preview_hash_verified=True,transcript_audio_hash_verified=True,
                          decode_verified=r['decode_verified'],frames=r['verified_frames'])
        except Exception as exc: result['error']=str(exc)
        results.append(result)
    class Links(HTMLParser):
        def __init__(self): super().__init__(); self.targets=[]
        def handle_starttag(self,tag,attrs):
            if tag=='a': self.targets.extend(value for key,value in attrs if key=='href')
    parser=Links(); parser.feed((folder/'审片清单.html').read_text(encoding='utf-8'))
    missing=[href for href in parser.targets if not rooted(folder/unquote(href)).is_file()]
    report=dict(batch=name,passed=all(r['passed'] for r in results) and not missing,items=results,
                checked_local_links=len(parser.targets),missing_links=missing,checked_at_utc=now(),
                note='文件、哈希与渲染技术检查；不代表全片人工听校或用户已批准。')
    write(folder/'batch_verification.json',report)
    return report
