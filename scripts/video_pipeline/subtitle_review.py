"""Optional, user-requested subtitle approval with a playable unburned review video."""
import html
from .common import *

FILES=['final_subtitles.json','final_subtitles.srt','final_subtitles.ass','render_plan.json','subtitle_style.json']


def fingerprint(job):
    from .editing import current_render_inputs
    m,rp=current_render_inputs(job)
    subs=read(job/'final_subtitles.json')
    if subs['edited_audio_sha256']!=rp['edited_audio_sha256']:
        raise ValueError('Subtitles do not match the current edit')
    if subs['style_sha256']!=digest(job/'subtitle_style.json'):
        raise ValueError('Regenerate subtitles after changing their style')
    return {name:digest(job/name) for name in FILES}


def require_review_approval(job):
    request=job/'subtitle_review_request.json'
    if not request.exists() or not read(request).get('required'):return
    approval=read(job/'subtitle_review_approval.json') if (job/'subtitle_review_approval.json').exists() else None
    if not approval or not approval.get('user_message') or approval.get('fingerprints')!=fingerprint(job):
        raise ValueError('User requested subtitle review: obtain approval for the current subtitle draft before burning or delivering')


def approve(job,message,subtitle_hash):
    if not message.strip():raise ValueError('Quote the actual subtitle approval message')
    hashes=fingerprint(job)
    if hashes['final_subtitles.json']!=subtitle_hash.upper():raise ValueError('Approval refers to a different subtitle version')
    write(job/'subtitle_review_approval.json',dict(user_message=message,fingerprints=hashes,approved_at_utc=now()))
    m=read(job/'manifest.json');m['subtitle_review_status']='approved';write(job/'manifest.json',m)
    return dict(status='approved',subtitle_sha256=subtitle_hash.upper())


def prepare(job):
    from .editing import current_render_inputs,video_filter
    from .captions import norm
    m,rp=current_render_inputs(job)
    hashes=fingerprint(job)
    subs=read(job/'final_subtitles.json');spec=read(job/'caption_spec.json')
    request=job/'subtitle_review_request.json'
    if not request.exists():write(request,dict(required=True,status='pending',note='Subtitle review requested through subtitle-review'))
    else:
        value=read(request);value.update(required=True,status='pending');write(request,value)
    prior=job/'subtitle_review_video.json'
    video=job/'字幕审核_无字剪辑版.mp4'
    identity=dict(render_plan_sha256=hashes['render_plan.json'],edited_audio_sha256=rp['edited_audio_sha256'])
    if not (prior.exists() and video.exists() and read(prior).get('inputs')==identity and read(prior).get('video_sha256')==digest(video)):
        if video.exists():
            history=job/'history'/('subtitle_review_'+digest(video)[:12]);history.mkdir(parents=True,exist_ok=True)
            move(video,history/video.name)
        (job/'subtitle_review_video.ffgraph').write_text(video_filter(job,rp,False),encoding='utf-8')
        ffmpeg(job,['-loglevel','info','-n','-filter_complex_threads','4','-i',rooted(m['source_path']),'-i','edited_audio.wav',
                    '-filter_complex_script','subtitle_review_video.ffgraph','-map','[vout]','-map','1:a:0',
                    '-c:v','libx264','-preset','veryfast','-crf','22','-threads','12','-pix_fmt','yuv420p',
                    '-fps_mode','cfr','-r',rp['fps'],'-c:a','aac','-b:a','192k','-ar','48000',
                    '-map_metadata','-1','-movflags','+faststart','-progress','subtitle_review_progress.txt',video.name],
               'subtitle_review_render.log')
        data=probe(video,True);v=next(s for s in data['streams'] if s['codec_type']=='video');a=next(s for s in data['streams'] if s['codec_type']=='audio')
        if int(v['nb_read_frames'])!=rp['total_frames'] or abs(float(a['duration'])-float(v['duration']))>=.05:
            raise ValueError('Review video does not match the approved edit timeline')
        write(prior,dict(inputs=identity,video_sha256=digest(video),frames=int(v['nb_read_frames']),duration=float(v['duration']),
                         burned_subtitles=False,created_at_utc=now()))
    paragraphs=spec.get('review_paragraphs',[])
    if paragraphs and norm(''.join(paragraphs))!=norm(''.join(c['text'] for c in subs['cues'])):
        raise ValueError('Readable review paragraphs differ from the subtitle text')
    body='# 字幕审核稿（待确认）\n\n剪辑已按确认稿执行；时间码对应剪后视频。尚未烧录字幕或输出成片。\n\n'
    body+='请重点核对错别字、遗漏、分句与同步；按编号或时间码告诉我修改即可。加粗部分为拟显示黄色的重点词。\n\n'
    if paragraphs:body+='## 连读稿\n\n'+'\n\n'.join(paragraphs)+'\n\n'
    if subs.get('corrections'):
        body+='## 已暂校的识别疑点\n\n'
        for c in subs['corrections']:body+=f"- {c['from']} → {c['to']}：{c['reason']}\n"
        body+='\n'
    body+='## 逐条字幕\n\n'
    for c in subs['cues']:
        text=c['text'].replace(c['emphasis'],'**'+c['emphasis']+'**',1) if c.get('emphasis') else c['text']
        body+=f"{c['index']:02} · {stamp(c['start'])}–{stamp(c['end'])}　{text}\n\n"
    (job/'字幕审核稿.md').write_text(body,encoding='utf-8-sig')
    rows=[]
    for c in subs['cues']:
        rows.append(f'<button class="cue" data-index="{c["index"]-1}"><span>{c["index"]:02} · {stamp(c["start"])[3:8]}</span><strong>{html.escape(c["text"])}</strong></button>')
    payload=json.dumps(subs['cues'],ensure_ascii=False).replace('<','\\u003c')
    font=os.path.relpath(SCRIPTS/'fonts/xinqingnian.ttf',job).replace('\\','/')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>字幕审核 · __TITLE__</title>
<style>@font-face{font-family:ReviewCaption;src:url('__FONT__')}*{box-sizing:border-box}body{margin:0;background:#f3f1eb;color:#202b28;font:15px/1.7 'Microsoft YaHei',sans-serif}main{max-width:1250px;margin:auto;padding:28px}h1{font-size:25px;margin:5px 0 12px}p{color:#5c6862}a{color:#235b4d}.layout{display:grid;grid-template-columns:minmax(280px,430px) 1fr;gap:35px;align-items:start}.player{position:sticky;top:20px}.screen{position:relative;background:black;line-height:0}video{display:block;width:100%;max-height:82vh;object-fit:contain}#caption{position:absolute;left:0;right:0;bottom:21.3%;text-align:center;line-height:1.2;pointer-events:none;font-family:ReviewCaption,sans-serif;color:white;paint-order:stroke fill;-webkit-text-stroke:2px #141414;text-shadow:1px 1px 1px #141414}.yellow{color:#ffd700}.cue{display:flex;gap:20px;width:100%;padding:12px 15px;border:0;border-bottom:1px solid #d8ddd3;text-align:left;background:transparent;color:inherit;cursor:pointer;font:inherit}.cue span{color:#647268;font-size:12px;min-width:92px}.cue.active{background:#f2d375}.cue:hover{background:#e5eadf}.cue strong{font-weight:500;font-size:18px}.label{font-size:13px;letter-spacing:1px;color:#275d4f}.links{display:flex;gap:18px;flex-wrap:wrap;margin:15px 0}.note{font-size:12px}@media(max-width:760px){main{padding:16px}.layout{grid-template-columns:1fr}.player{position:static}.screen{max-width:380px;margin:auto}video{max-height:70vh}h1{font-size:21px}}</style>
<main><div class="label">剪辑完成 / 字幕待审核</div><h1>__TITLE__</h1><p>播放视频检查字幕，点击右侧条目可跳到对应时间。请按编号或时间码告诉我错字、漏字、分句和同步问题。</p><div class="layout"><div class="player"><div class="screen"><video id="video" src="字幕审核_无字剪辑版.mp4" controls playsinline preload="metadata"></video><div id="caption"></div></div><div class="links"><a href="字幕审核稿.md">打开完整审核稿</a><a href="final_subtitles.srt" download>下载SRT</a><a href="字幕审核_无字剪辑版.mp4">打开无字剪辑视频</a></div><p class="note">字幕由网页动态显示，尚未烧录。实际成片将沿用新青年体100号、白黄双色。审核版用于核对内容与时间，不是最终压制文件。</p></div><div id="cues">__ROWS__</div></div></main><script id="data" type="application/json">__DATA__</script><script>
const cues=JSON.parse(document.getElementById('data').textContent),video=document.getElementById('video'),caption=document.getElementById('caption'),buttons=[...document.querySelectorAll('.cue')];let active=-1;
function resize(){caption.style.fontSize=(video.clientWidth*100/1080)+'px'}new ResizeObserver(resize).observe(video);video.addEventListener('loadedmetadata',resize);
function update(){const i=cues.findIndex(c=>c.start<=video.currentTime&&video.currentTime<c.end);if(i===active)return;active=i;caption.replaceChildren();buttons.forEach((b,n)=>b.classList.toggle('active',n===i));if(i<0)return;const c=cues[i];if(c.emphasis){const at=c.text.indexOf(c.emphasis);caption.append(document.createTextNode(c.text.slice(0,at)));const strong=document.createElement('span');strong.className='yellow';strong.textContent=c.emphasis;caption.append(strong,document.createTextNode(c.text.slice(at+c.emphasis.length)))}else caption.textContent=c.text}
video.addEventListener('timeupdate',update);video.addEventListener('seeked',update);buttons.forEach(b=>b.onclick=()=>{video.currentTime=cues[Number(b.dataset.index)].start;update()});</script></html>'''
    page=page.replace('function resize(){caption.style.fontSize=(video.clientWidth*100/1080)+\'px\'}',
        'function resize(){const scale=Math.min(video.clientWidth/'+str(rp['width'])+',video.clientHeight/'+str(rp['height'])+');'+
        'caption.style.fontSize=('+str(subs['layout']['size'])+'*scale)+\'px\';'+
        'caption.style.left=((video.clientWidth-'+str(rp['width'])+'*scale)/2)+\'px\';caption.style.right=\'auto\';'+
        'caption.style.width=('+str(rp['width'])+'*scale)+\'px\';'+
        'caption.style.bottom=((video.clientHeight-'+str(rp['height'])+'*scale)/2+'+str(subs['layout']['bottom'])+'*scale)+\'px\';'+
        'caption.style.webkitTextStroke=('+str(subs['layout']['outline'])+'*scale)+\'px #141414\'}')
    page=page.replace('新青年体100号','新青年体'+f"{subs['layout']['size']:g}"+'号')
    page=page.replace('__TITLE__',html.escape(m['title'])).replace('__FONT__',font).replace('__ROWS__',''.join(rows)).replace('__DATA__',payload)
    (job/'字幕审核.html').write_text(page,encoding='utf-8')
    write(job/'subtitle_review.json',dict(status='pending',fingerprints=hashes,subtitle_sha256=hashes['final_subtitles.json'],
              cues=len(subs['cues']),duration=rp['total_duration'],created_at_utc=now()))
    m['subtitle_review_status']='pending';write(job/'manifest.json',m)
    return dict(status='awaiting_subtitle_review',review=rel(job/'字幕审核.html'),text=rel(job/'字幕审核稿.md'),
                subtitle_sha256=hashes['final_subtitles.json'],duration=rp['total_duration'],captions=len(subs['cues']))
