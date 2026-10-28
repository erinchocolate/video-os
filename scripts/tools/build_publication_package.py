"""Publication-package renderer. Per-video editorial input stays in package/materials.

This is a local design tool, not an upload client. No selection is treated as approval.
"""
import argparse
from functools import lru_cache
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SCRIPTS), str(SCRIPTS / 'vendor')]
sys.stdout.reconfigure(encoding='utf-8')
from PIL import Image, ImageDraw, ImageFont, ImageOps
from video_pipeline.common import ROOT, digest, job_path, now, read, rel, rooted, write
from video_pipeline.packaging import cover_sizes,materials_path,package_path,PROFILE_PATH

SIZES = cover_sizes()
FONT = SCRIPTS / 'fonts/xinqingnian.ttf'
SMALL_FONT = Path('C:/Windows/Fonts/msyh.ttc')


def require_completed(job):
    m = read(job / 'manifest.json')
    if m['status'] != 'completed':
        raise ValueError('Package input must be a completed final video')
    if digest(rooted(m['final_path'])) != m['final_sha256']:
        raise ValueError('Final video changed; review the source manifest')
    return m


def prepare(job):
    m = require_completed(job)
    if digest(rooted(m['source_path'])) != m['original_sha256']:
        raise ValueError('Raw source hash mismatch')
    rp = read(job / 'render_plan.json')
    work = materials_path(job)
    work.mkdir(parents=True,exist_ok=True)
    folder = work / 'frames'
    folder.mkdir(exist_ok=True)
    if (work/'frames.json').exists():
        prior=read(work/'frames.json')
        if prior['source_sha256']!=m['original_sha256'] or any(digest(rooted(f['path']))!=f['sha256'] for f in prior['frames']):
            raise ValueError('Existing still provenance changed; preserve a revision before preparing again')
        return dict(frames=len(prior['frames']),sheet=rel(work/'原始画面候选.jpg'),status='existing_materials_preserved')
    # Every still comes from retained content, before burned subtitles.
    duration=rp['keeps'][-1]['output_end']
    count=min(24,max(4,round(duration*2)))
    times=[duration*(i+.5)/count for i in range(count)]
    records = []
    for i, t in enumerate(times, 1):
        keep = next(k for k in rp['keeps'] if k['output_start'] <= t < k['output_end'])
        source_t = keep['source_start'] + t - keep['output_start']
        target = folder / f'{i:02}.jpg'
        with (work / f'frame_{i:02}.log').open('wb') as log:
            subprocess.run(['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'error', '-y',
                            '-ss', str(source_t), '-i', str(rooted(m['source_path'])),
                            '-frames:v', '1', '-q:v', '2', '-update', '1', str(target)],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        records.append(dict(id=f'{i:02}', output_time=t, source_time=source_t,
                            path=rel(target), sha256=digest(target)))
    write(work / 'frames.json', dict(source_sha256=m['original_sha256'], frames=records))
    with Image.open(rooted(records[0]['path'])) as first:
        tile_h=round(226*first.height/first.width)
    row_h=tile_h+52
    sheet = Image.new('RGB', (6 * 242 + 16, ((count+5)//6) * row_h + 64), '#eeeae0')
    d = ImageDraw.Draw(sheet)
    for i, r in enumerate(records):
        x = 16 + (i % 6) * 242
        y = 16 + (i // 6) * row_h
        im = Image.open(rooted(r['path'])).convert('RGB')
        im.thumbnail((226, tile_h))
        sheet.paste(im, (x, y))
        d.text((x, y + tile_h+4), f"{r['id']}   final {r['output_time']:.1f}s", font=font(19, True), fill='#151718')
    sheet.save(work / '原始画面候选.jpg', quality=92)
    return dict(frames=len(records), sheet=rel(work / '原始画面候选.jpg'))


@lru_cache(maxsize=200)
def font(size, small=False):
    return ImageFont.truetype(str(SMALL_FONT if small else FONT), max(12, round(size)))


def label(draw, xy, text, size, color, small=False, anchor='lt'):
    f = font(size, small)
    draw.text(xy, text, font=f, fill=color, anchor=anchor)


def photo_at(canvas, photo, box, centering=(0.5, 0.38)):
    x, y, w, h = map(round, box)
    im = ImageOps.fit(photo, (w, h), method=Image.Resampling.LANCZOS, centering=centering)
    canvas.paste(im, (x, y))


def fitted_size(draw, lines, width, initial):
    size = round(initial)
    while any(draw.textbbox((0, 0), line, font=font(size))[2] > width for line in lines):
        size -= 1
        if size < 40:
            raise ValueError('Cover text is too long to remain legible')
    return size


def block(draw, lines, x, y, width, initial, colors, gap=1.20):
    size = fitted_size(draw, lines, width, initial)
    for i, line in enumerate(lines):
        label(draw, (round(x), round(y + i * size * gap)), line, size, colors[i % len(colors)])
    return size


def cover(item, source, size):
    if item['design'] in ['direct','highlight']:
        from tools.refine_publication_cover import render
        return render(Image.open(source).convert('RGB'),size,item['cover_lines'],item['design'],item.get('background'))[0]
    w, h = size
    portrait = h > w
    style = item['design']
    accent = item['accent']
    ink, paper = '#182026', '#F4F0E7'
    photo = Image.open(source).convert('RGB')
    canvas = Image.new('RGB', (w, h), paper)
    d = ImageDraw.Draw(canvas)
    lines = item['cover_lines']
    foot = item.get('cover_subtitle','')
    category = item.get('category','内容分享')
    if portrait:
        scale = w / 1080
        if style == 'bold':
            photo_at(canvas, photo, (0, 0, w, h), (0.5, 0.62))
            panel = round(h * 0.69)
            d.rectangle((0, panel, w, h), fill=ink)
            label(d, (64*scale, panel+38*scale), category, 29*scale, '#CDD1D0', True)
            block(d, lines, 58*scale, panel+100*scale, w-116*scale,
                  min(153*scale, h*0.092, (h-panel-190*scale)/2.3), ['#FFFFFF', accent])
            label(d, (64*scale, h-86*scale), foot, 30*scale, '#DEE0DD', True)
        elif style == 'paper':
            label(d, (64*scale, 48*scale), item.get('eyebrow',category+' / 一次思考'), 30*scale, ink, True)
            ph = round(h * 0.56)
            photo_at(canvas, photo, (58*scale, 120*scale, w-116*scale, ph))
            y = 120*scale + ph + 58*scale
            block(d, lines, 60*scale, y, w-120*scale, min(148*scale,h*.084), [ink, item['dark_accent']])
            d.rectangle((64*scale, h-104*scale, 132*scale, h-96*scale), fill=item['dark_accent'])
            label(d, (156*scale, h-120*scale), foot, 29*scale, ink, True)
        elif style == 'compare':
            photo_at(canvas, photo, (0, 0, w, h), (0.5, 0.62))
            panel = round(h * 0.68)
            d.rectangle((0,panel,w,h), fill=paper)
            sz = fitted_size(d, lines, w-140*scale, min(140*scale,h*.079))
            label(d,(70*scale,panel+45*scale),lines[0],sz,ink)
            y2=panel+45*scale+sz*1.28
            d.rectangle((56*scale,y2-8*scale,w-56*scale,y2+sz*1.10),fill=accent)
            label(d,(70*scale,y2),lines[1],sz,ink)
            label(d,(70*scale,h-82*scale),foot,29*scale,ink,True)
        elif style == 'ink':
            canvas.paste(Image.new('RGB',(w,h),item['dark_accent']),(0,0))
            photo_at(canvas,photo,(48*scale,110*scale,w-96*scale,h*.57))
            label(d,(58*scale,42*scale),category+' / 方法与实践',29*scale,'#F2F0E7',True)
            y=110*scale+h*.57+48*scale
            block(d,lines,56*scale,y,w-112*scale,min(146*scale,h*.083),['#FFFFFF',accent])
            label(d,(58*scale,h-85*scale),foot,29*scale,'#E6EAE6',True)
        elif style == 'action':
            d.rectangle((0,0,w,h*.30),fill=accent)
            label(d,(64*scale,40*scale),category+' / 回到行动',29*scale,ink,True)
            block(d,lines,58*scale,103*scale,w-116*scale,min(147*scale,h*.082),[ink])
            photo_at(canvas,photo,(0,h*.30,w,h*.70),(0.5,.42))
            d.rectangle((0,h-102*scale,w,h),fill=ink)
            label(d,(64*scale,h-78*scale),foot,30*scale,'#FFFFFF',True)
        else:
            raise ValueError('Unknown design: '+style)
    else:
        scale=h/900
        split=.53 if w/h>1.5 else .51
        photo_x=round(w*split)
        background = ink if style=='bold' else item['dark_accent'] if style=='ink' else paper
        d.rectangle((0,0,w,h),fill=background)
        photo_at(canvas,photo,(photo_x,0,w-photo_x,h),(.5,.40))
        fg='#FFFFFF' if style in ['bold','ink'] else ink
        pad=round(55*scale)
        label(d,(pad,65*scale),category,29*scale,fg,True)
        if style=='action':
            d.rectangle((0,0,photo_x,146*scale),fill=accent)
            label(d,(pad,65*scale),category+' / 行动',29*scale,ink,True)
        yy=260*scale
        fs=fitted_size(d,lines,photo_x-pad*2,118*scale)
        if style=='compare':
            label(d,(pad,yy),lines[0],fs,ink)
            yy2=yy+fs*1.50
            d.rectangle((pad-12*scale,yy2-12*scale,photo_x-25*scale,yy2+fs*1.12),fill=accent)
            label(d,(pad,yy2),lines[1],fs,ink)
        else:
            cols=[fg,accent] if style in ['bold','ink'] else [ink,item['dark_accent']]
            block(d,lines,pad,yy,photo_x-pad*2,fs,cols,gap=1.35)
        # Supporting text wraps deliberately instead of being cropped by the portrait.
        foot_size=min(29*scale,(photo_x-pad*2)/max(1,len(foot))*1.05)
        label(d,(pad,h-120*scale),foot,foot_size,fg,True)
        d.rectangle((pad,179*scale,pad+90*scale,187*scale),fill=accent)
    return canvas


def normalized(text):
    return ''.join(re.findall(r'[\u3400-\u9fffA-Za-z0-9]',text))


def validate_spec(spec, subs):
    if len(spec['candidates']) != 20:
        raise ValueError('This pilot requires 20 complete candidates')
    ids=[c['id'] for c in spec['candidates']]
    if ids != [f'{i:02}' for i in range(1,21)]:
        raise ValueError('Candidate IDs must be 01–20 in order')
    if len({c['title'] for c in spec['candidates']}) != 20:
        raise ValueError('Repeated titles')
    if normalized(''.join(spec['transcript_paragraphs'])) != normalized(''.join(c['text'] for c in subs['cues'])):
        raise ValueError('Readable transcript must match final captions without paraphrasing')
    for c in spec['candidates']:
        if len(c['cover_lines']) != 2 or any(len(t)>9 for t in c['cover_lines']):
            raise ValueError('Use two short cover lines per candidate')
        if not c['evidence'] or not c['rationale']:
            raise ValueError('Every title needs final-content evidence and a pairing rationale')


def build(job, spec_path):
    m=require_completed(job)
    spec_path=rooted(spec_path)
    target=package_path(job)
    spec_path.relative_to(target)
    spec=read(spec_path)
    subs=read(job/'final_subtitles.json')
    validate_spec(spec,subs)
    frames=read(materials_path(job)/'frames.json')
    frames_by_id={r['id']:r for r in frames['frames']}
    if (target/'发布包.json').exists():
        raise FileExistsError('Preserve the existing package; do not overwrite a user selection: '+str(target))
    target.mkdir(parents=True,exist_ok=True)
    shutil.copy2(rooted(m['final_path']),target/'成片.mp4')
    shutil.copy2(job/'final_subtitles.srt',target/'成片字幕.srt')
    shutil.copy2(job/'final_subtitles.ass',target/'成片字幕.ass')
    (target/'成片文字稿.md').write_text('# 成片文字稿\n\n'+'\n\n'.join(spec['transcript_paragraphs'])+'\n',encoding='utf-8-sig')
    (target/'通用发布说明.txt').write_text(spec['description']+'\n',encoding='utf-8-sig')
    (target/'可选话题.txt').write_text(' '.join('#'+t for t in spec['topics'])+'\n',encoding='utf-8-sig')
    candidates=[]
    for c in spec['candidates']:
        frame=frames_by_id[c['frame_id']]
        if digest(rooted(frame['path'])) != frame['sha256']:
            raise ValueError('Selected frame changed')
        folder=target/'候选'/c['id']
        folder.mkdir(parents=True)
        images={}
        for key,size in SIZES.items():
            name=f'封面_{key}.jpg'
            im=cover(c,rooted(frame['path']),size)
            im.save(folder/name,quality=94,subsampling=0,optimize=True)
            # The gallery opens files directly; no local server or fetch is needed.
            images[key]=(folder/name).relative_to(target).as_posix()
        (folder/'标题.txt').write_text(c['title']+'\n',encoding='utf-8-sig')
        notes=(f"# 方案 {c['id']}\n\n标题：{c['title']}\n\n封面主字：{' / '.join(c['cover_lines'])}\n\n"
               f"创意方向：{c['group']}\n\n配对理由：{c['rationale']}\n\n"
               f"成片依据：{c['evidence']}\n\n发布说明：共用 ../../通用发布说明.txt。\n\n"
               '同一文案和设计附 9:16、3:4、16:9、4:3 四种尺寸；没有按平台改写内容。\n')
        (folder/'方案说明.md').write_text(notes,encoding='utf-8-sig')
        candidates.append(dict(c,images=images,frame_provenance=frame))
        print('Rendered candidate '+c['id'],flush=True)
    data=dict(package_id=job.name,source_job=rel(job),source_final=m['final_path'],
              final_sha256=m['final_sha256'],subtitle_sha256=digest(job/'final_subtitles.json'),
              spec_sha256=digest(spec_path),created_at_utc=now(),status='awaiting_user_selection',
              materials_dir=rel(materials_path(job)),cover_export_sizes={k:list(v) for k,v in SIZES.items()},
              selected_candidate=None,title=m['title'],description=spec['description'],topics=spec['topics'],
              recommended=spec['recommended'],platform_notes=spec['platform_notes'],candidates=candidates)
    write(target/'发布包.json',data)
    write_gallery(target,data)
    (target/'选择说明.md').write_text(
        '# 发布包使用说明\n\n先打开“候选总览.html”，比较20组标题和封面。默认尚未选定。\n\n'
        '可按创意方向筛选、收藏候选、切换封面比例、复制标题和通用说明；最后告诉 agent 方案编号。\n\n'
        '浏览器中的收藏仅保存在本机；“导出选择”生成一个选择记录，不会上传、发布或自动写入本目录。\n\n'
        '成片.mp4 是 final 中已检查成片的完整副本。原片逐字稿和过程证据继续保存在 process；'
        '本目录的文字稿与字幕是对应当前成片的导出快照。\n\n'
        '候选/01 至 候选/20 各有一个标题及同一设计的四种尺寸。选定后使用同一个标题、通用说明和同组封面；'
        '尺寸适配不代表另选方案。封面适用性请在实际上传界面预览确认。\n\n'
        '平台标签是创意角度参考，不是算法效果承诺。本轮不进行实际上传。\n\n'
        '具体操作见工作区 skill/video-package/SKILL.md；最终选定后使用 upload-ready 生成待上传文件。\n',encoding='utf-8-sig')
    platform='\n\n'.join(f"- {n['text']}\n  来源：{n.get('source','本次设计约定')}" for n in spec['platform_notes'])
    checked=read(PROFILE_PATH)['checked_date']
    (target/'尺寸与平台说明.md').write_text('# 尺寸与平台说明快照\n\n'+platform+'\n\n共享规格见工作区skill/video-package/references/platforms.json。平台资料核对日期：'+checked+'。上传时以实际界面为准。\n',encoding='utf-8-sig')
    overview(target,data)
    return check(target)


def write_gallery(target,data):
    template=(SCRIPTS/'templates/publication_gallery.html').read_text(encoding='utf-8')
    embedded=json.dumps(data,ensure_ascii=False).replace('<','\\u003c')
    page=template.replace('__PACKAGE_DATA__',embedded)
    page=page.replace('__VIDEO_TITLE__',html.escape(data['title']))
    page=page.replace('__CAPTURE_DATE__',html.escape(data['package_id'][:10].replace('-','.')))
    if data.get('cover_revision'):
        revision=rooted(data['cover_revision']).relative_to(target).as_posix()
        latest=html.escape(revision+'/封面修订总览.html',quote=True)
        chosen=html.escape(data['selected_publication_title'])
        label='查看封面修订'
        if data.get('selected_cover_directory'):
            selected=rooted(data['selected_cover_directory']).relative_to(target).as_posix()
            latest=html.escape(selected+'/封面_16x9.jpg',quote=True)
            label='查看最终选定封面'
        notice=(f'<aside style="padding:18px 40px;background:#e8c45b;color:#1e2928">'
                f'标题已确定：<strong>{chosen}</strong>。 '
                f'<a href="{latest}">{label}</a></aside>')
        page=page.replace('<body>','<body>'+notice,1)
        page=page.replace('第一轮样例 · 等待你挑选','第一轮候选归档 · 当前选择见顶部入口')
    (target/'候选总览.html').write_text(page,encoding='utf-8')


def overview(target,data):
    # Four smaller sheets keep the actual exported cover typography readable.
    for group in range(4):
        group_items=data['candidates'][group*5:(group+1)*5]
        out=Image.new('RGB',(5*330+48,670),'#F4F0E7')
        d=ImageDraw.Draw(out)
        label(d,(24,18),group_items[0]['group'],24,'#182026',True)
        for i,c in enumerate(group_items):
            im=Image.open(target/c['images']['3x4'])
            im.thumbnail((310,414))
            x=24+i*330
            out.paste(im,(x,74))
            label(d,(x,507),'方案 '+c['id'],23,'#182026',True)
            title=c['title']
            for row,start in enumerate(range(0,len(title),12)):
                label(d,(x,546+row*32),title[start:start+12],21,'#182026',True)
        out.save(target/f'总览_{group+1:02}.jpg',quality=94)


def check(target):
    data=read(target/'发布包.json')
    if digest(target/'成片.mp4') != data['final_sha256']:
        raise ValueError('Packaged video differs from final')
    source=rooted(data['source_job'])
    if digest(source/'final_subtitles.json') != data['subtitle_sha256']:
        raise ValueError('Source subtitles changed after packaging')
    if digest(target/'成片字幕.srt') != digest(source/'final_subtitles.srt'):
        raise ValueError('Exported subtitles differ')
    if normalized((target/'成片文字稿.md').read_text(encoding='utf-8-sig').split('\n\n',1)[1]) != normalized(''.join(c['text'] for c in read(source/'final_subtitles.json')['cues'])):
        raise ValueError('Transcript export differs from final captions')
    count=0
    expected={k:tuple(v) for k,v in data.get('cover_export_sizes',SIZES).items()}
    hashes=[]
    for c in data['candidates']:
        for key,path in c['images'].items():
            im=Image.open(target/path)
            if im.size != expected[key] or im.format != 'JPEG':
                raise ValueError('Bad cover export: '+path)
            im.verify()
            count+=1
        hashes.append(digest(target/c['images']['9x16']))
    if len(set(hashes)) != 20:
        raise ValueError('Repeated main cover files')
    report=dict(passed=True,candidates=len(data['candidates']),cover_exports=count,
                video_copy_hash_verified=True,subtitle_copy_verified=True,
                readable_transcript_matches_final=True,selected_candidate=data['selected_candidate'],
                checked_at_utc=now(),package=rel(target))
    write(target/'文件检查.json',report)
    write(target/'materials/package_record.json',dict(package=rel(target),spec_sha256=data['spec_sha256'],
          final_sha256=data['final_sha256'],status=data['status'],checked_at_utc=now()))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    subs=p.add_subparsers(dest='command',required=True)
    s=subs.add_parser('prepare');s.add_argument('--job',required=True)
    s=subs.add_parser('build');s.add_argument('--job',required=True);s.add_argument('--spec',required=True)
    s=subs.add_parser('check');s.add_argument('--package',required=True)
    args=p.parse_args()
    if args.command=='prepare':return prepare(job_path(args.job))
    if args.command=='build':return build(job_path(args.job),args.spec)
    return check(rooted(args.package))


if __name__=='__main__':
    print(json.dumps(main(),ensure_ascii=False,indent=2))
