"""Render a non-destructive, full-photo typography revision from an existing package.

Editable native cover layout: uses the existing font and original uncaptioned frame.
Per-video editorial decisions and user feedback are supplied in package/materials.
"""
import argparse
from functools import lru_cache
import html
import json
import re
from pathlib import Path
import shutil
import sys

SCRIPTS=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SCRIPTS),str(SCRIPTS/'vendor')]
sys.stdout.reconfigure(encoding='utf-8')
from PIL import Image,ImageDraw,ImageFilter,ImageFont,ImageOps
from video_pipeline.common import ROOT,digest,job_path,now,read,rel,rooted,write
from video_pipeline.packaging import cover_sizes,materials_path,package_path

SIZES=cover_sizes()
FONT=SCRIPTS/'fonts/xinqingnian.ttf'
UI_FONT=Path('C:/Windows/Fonts/msyh.ttc')


@lru_cache(maxsize=100)
def font(size,ui=False):
    return ImageFont.truetype(str(UI_FONT if ui else FONT),round(size))


def backdrop(photo,size,background=None):
    """Wide versions retain the original person over a soft same-photo extension.

    No solid text panel, photograph card, generative retouch, or person reconstruction.
    """
    w,h=size
    if background:
        mode=background['mode']
        if mode=='uncut_photo':
            if h>w:
                return ImageOps.fit(photo,size,Image.Resampling.LANCZOS,centering=(.5,.62))
            plate=Image.open(rooted(background['landscape_plate'])).convert('RGB')
            bg=ImageOps.fit(plate,size,Image.Resampling.LANCZOS,centering=(1,.5))
            # Preserve the entire rectangular source photograph, including its
            # real surroundings and hair edges. No portrait alpha matte is used.
            ph=round(h*1.35);pw=round(ph*photo.width/photo.height)
            sharp=photo.resize((pw,ph),Image.Resampling.LANCZOS)
            y=-round(h*.15)
            bg.paste(sharp.crop((0,-y,pw,h-y)),(w-pw,0))
            return bg
        # Keep the actual portrait photograph intact. Wide adaptations use an
        # explicitly supplied, provenance-recorded extension of the same room.
        if mode=='original_scene' and h>w:
            return ImageOps.fit(photo,size,Image.Resampling.LANCZOS,centering=(.5,.62))
        if mode=='solid':
            bg=Image.new('RGB',size,background.get('color','#24343E'))
        elif mode in ['uniform_blur','original_scene']:
            portrait_plate=background.get('portrait_plate') if h>w else None
            plate=Image.open(rooted(portrait_plate or background['plate'])).convert('RGB')
            bg=ImageOps.fit(plate,size,Image.Resampling.LANCZOS,
                           centering=(.5,.62) if portrait_plate else (.5,.5))
        else:
            raise ValueError('Unknown full-background mode')
        # Imagegen supplies only the alpha matte; original-photo RGB remains authoritative.
        asset=Image.open(rooted(background['matte_asset'])).convert('RGBA')
        alpha=asset.getchannel('A').resize(photo.size,Image.Resampling.LANCZOS)
        alpha=alpha.point(lambda a:0 if a<16 else 255 if a>240 else a)
        alpha=alpha.filter(ImageFilter.MinFilter(3))
        if alpha.getextrema()!=(0,255):
            raise ValueError('Foreground asset must contain real transparency and opaque pixels')
        person=photo.convert('RGBA')
        person.putalpha(alpha)
        if h>w:
            person=ImageOps.fit(person,size,Image.Resampling.LANCZOS,centering=(.5,.62))
            bg.paste(person,(0,0),person.getchannel('A'))
        else:
            ph=round(h*1.50)
            pw=round(ph*photo.width/photo.height)
            person=person.resize((pw,ph),Image.Resampling.LANCZOS)
            x,y=w-pw,-round(h*.15)
            person=person.crop((0,-y,pw,h-y))
            bg.paste(person,(x,0),person.getchannel('A'))
        return bg
    if h>w:
        return ImageOps.fit(photo,size,Image.Resampling.LANCZOS,centering=(.5,.62))
    bg=ImageOps.fit(photo,size,Image.Resampling.LANCZOS,centering=(.1,.25))
    bg=bg.filter(ImageFilter.GaussianBlur(h*.038))
    # A translucent photographic shade keeps direct letters legible; no flat banner.
    bg=Image.blend(bg,Image.new('RGB',size,'#101716'),.36)
    ph=round(h*1.50)
    pw=round(ph*photo.width/photo.height)
    sharp=photo.resize((pw,ph),Image.Resampling.LANCZOS)
    x,y=w-pw,-round(h*.15)
    visible=sharp.crop((0,-y,pw,h-y))
    edge=round(h*.12)
    alpha=Image.new('L',(pw,h),255)
    ad=ImageDraw.Draw(alpha)
    for xx in range(edge):
        ad.line((xx,0,xx,h),fill=round(255*xx/max(1,edge-1)))
    bg.paste(visible,(x,0),alpha)
    return bg


def render(photo,size,lines,style,background=None):
    w,h=size
    im=backdrop(photo,size,background)
    draw=ImageDraw.Draw(im)
    portrait=h>w
    if portrait:
        fs=round(w*(.218 if h/w>1.5 else .176))
        x=round(w*.065)
        y=round(h*(.735 if h/w>1.5 else .735))
        width=w-x*2
        if h/w<1.5:
            fs=round(w*.172)
            y=round(h*.727)
    else:
        wide=w/h>1.5
        fs=round(h*(.215 if wide else .173))
        x=round(w*(.046 if wide else .04))
        y=round(h*(.455 if wide else .49))
        width=round(w*(.49 if wide else .43))
    padding=round(fs*.08)
    while True:
        f=font(fs)
        bboxes=[draw.textbbox((0,0),line,font=f,anchor='lt') for line in lines]
        line_w=max(b[2]-b[0] for b in bboxes)
        row=round(fs*1.20)
        total=row+max(b[3]-b[1] for b in bboxes)
        if line_w+padding*2<=width and y+total+padding<h*.965:
            break
        fs-=1
        if fs<64:
            raise ValueError('Text does not fit without losing thumbnail readability')
        padding=round(fs*.08)
    boxes=[]
    for i,line in enumerate(lines):
        yy=y+i*row
        ink=draw.textbbox((x,yy),line,font=f,anchor='lt')
        if style=='highlight':
            bg=(ink[0]-padding,ink[1]-padding,ink[2]+padding,ink[3]+padding)
            draw.rectangle(bg,fill='#FFDA24')
            draw.text((x,yy),line,font=f,anchor='lt',fill='#111512')
            boxes.append(dict(text=line,text_bounds=ink,word_background_bounds=bg))
        elif style=='direct':
            stroke=max(5,round(fs*.037))
            draw.text((x+3,yy+5),line,font=f,anchor='lt',fill='#101410',stroke_width=stroke+1,stroke_fill='#101410')
            draw.text((x,yy),line,font=f,anchor='lt',fill='#FFFFFF' if i==0 else '#FFDA24',
                      stroke_width=stroke,stroke_fill='#111512')
            boxes.append(dict(text=line,text_bounds=ink,stroke_width=stroke))
        else:
            raise ValueError('Unknown overlay style')
    return im,dict(size=size,font_size=fs,style=style,lines=boxes,subtitles=False,
                   full_width_banner=False,background=background['mode'] if background else
                   ('original_photo' if portrait else 'original_photo_with_soft_same_photo_sides'),
                   foreground_rgb_from_original=True)


def gallery(target,spec,variants):
    payload=json.dumps(variants,ensure_ascii=False).replace('<','\\u003c')
    title=html.escape(spec['publication_title'])
    text=html.escape(' / '.join(spec['cover_lines']))
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>封面第二轮 · __TITLE__</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f0e8;color:#1b2524;font:15px/1.7 "Microsoft YaHei",sans-serif}main{max-width:1450px;margin:auto;padding:36px 36px 48px}.eyebrow{color:#53665e;letter-spacing:1px;font-size:12px}h1{font-size:29px;line-height:1.5;margin:8px 0 14px}h2{font-size:20px;margin:0 0 8px}p{margin:10px 0}nav{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:20px 0;border-top:1px solid #ccd2c5;border-bottom:1px solid #ccd2c5;margin:26px 0}select{font:inherit;padding:9px 14px;background:#fffef9;border:1px solid #aebeb0;border-radius:5px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:28px}.variant{min-width:0}.variant p{color:#5b6860;font-size:14px}.preview{display:block;width:100%;height:auto;border:1px solid #ccd2c5;background:#deded3}.downloads{display:flex;gap:18px;flex-wrap:wrap;margin:15px 0 28px}a{color:#235a4c;text-underline-offset:4px}.note{margin-top:24px;padding-top:20px;border-top:1px solid #ccd2c5;color:#5b6860;font-size:13px}.foot{display:flex;gap:20px;flex-wrap:wrap;margin-top:20px}@media(max-width:760px){main{padding:22px 16px}.grid{grid-template-columns:1fr}h1{font-size:24px}}
</style><main><div class="eyebrow">封面第二轮 / 标题已确定，外观待选</div><h1>__TITLE__</h1><p>封面文字：<strong>__TEXT__</strong></p><p>人物画面铺底，只保留两行大字。比较 A、B 两版，选择喜欢的一版即可。</p><nav><label for="ratio">预览比例</label><select id="ratio"><option value="16x9">B站横版 · 16:9 · 1920×1080</option><option value="4x3">B站横版 · 4:3 · 1200×900</option><option value="9x16">竖版 · 9:16 · 1080×1920</option><option value="3x4">竖版 · 3:4 · 1080×1440</option></select></nav><div class="grid" id="grid"></div><div class="note">黄色背景只紧贴文字边界；画面没有整块 banner、眉题或副标题。横版由原照片柔化延展两侧，人物保留原始画面。各比例单独排版。标题与封面搭配取自本轮反馈，A/B 尚未替你选定。</div><div class="foot"><a href="../通用发布说明.txt">通用发布说明</a><a href="../成片.mp4">成片</a><a href="../候选总览.html">第一轮20组候选</a><a href="B站封面对比.jpg">打开两种横版比例对比图</a></div></main><script type="application/json" id="data">__DATA__</script><script>
const variants=JSON.parse(document.getElementById('data').textContent),grid=document.getElementById('grid'),ratio=document.getElementById('ratio');function render(){grid.replaceChildren();for(const v of variants){const section=document.createElement('section');section.className='variant';const h=document.createElement('h2');h.textContent=v.label;const p=document.createElement('p');p.textContent=v.description;const a=document.createElement('a');a.href=encodeURI(v.images[ratio.value]);a.target='_blank';const im=document.createElement('img');im.className='preview';im.src=a.href;im.alt=v.label+'，'+ratio.value; a.append(im);const links=document.createElement('div');links.className='downloads';for(const [key,path]of Object.entries(v.images)){const link=document.createElement('a');link.textContent=key.replace('x',':')+' JPG';link.href=encodeURI(path);link.download=key+'.jpg';links.append(link)}section.append(h,p,a,links);grid.append(section)}}ratio.onchange=render;render();</script></html>'''
    page=page.replace('__TITLE__',title).replace('__TEXT__',text).replace('__DATA__',payload)
    options=''.join(f'<option value="{key}">{"B站横版" if SIZES[key][0]>SIZES[key][1] else "竖版"} · {key.replace("x",":")} · {SIZES[key][0]}×{SIZES[key][1]}</option>'
                    for key in ['16x9','4x3','9x16','3x4'])
    page=re.sub(r'(?<=<select id="ratio">).*?(?=</select>)',lambda _:options,page,count=1)
    page=page.replace('封面第二轮',html.escape(spec.get('revision_label','封面第二轮')))
    if spec.get('gallery_intro'):
        page=page.replace('人物画面铺底，只保留两行大字。比较 A、B 两版，选择喜欢的一版即可。',html.escape(spec['gallery_intro']))
    if spec.get('background_note'):
        page=page.replace('黄色背景只紧贴文字边界；画面没有整块 banner、眉题或副标题。横版由原照片柔化延展两侧，人物保留原始画面。各比例单独排版。标题与封面搭配取自本轮反馈，A/B 尚未替你选定。',html.escape(spec['background_note']))
    (target/'封面修订总览.html').write_text(page,encoding='utf-8')


def build(job,spec_path):
    spec_path=rooted(spec_path)
    spec_path.relative_to(package_path(job))
    spec=read(spec_path)
    package=package_path(job)
    data=read(package/'发布包.json')
    if data['final_sha256']!=digest(package/'成片.mp4'):
        raise ValueError('Packaged final differs from the verified output')
    if len(spec['cover_lines'])!=2 or not spec['feedback']:
        raise ValueError('Two short cover lines and actual user feedback are required')
    record=next(f for f in read(materials_path(job)/'frames.json')['frames'] if f['id']==spec['frame_id'])
    source=rooted(record['path'])
    if digest(source)!=record['sha256']:
        raise ValueError('Original selected still changed')
    target=package/spec['revision_name']
    if target.exists():
        raise FileExistsError('Preserve existing revision: '+str(target))
    target.mkdir()
    history=materials_path(job)/'history'/spec['revision_name']
    history.mkdir(parents=True,exist_ok=False)
    for name in ['发布包.json','文件检查.json','选择说明.md','候选总览.html','发布选择.json']:
        if (package/name).exists():shutil.copy2(package/name,history/name)
    photo=Image.open(source).convert('RGB')
    variants=[]
    exports=[]
    assets=[]
    for asset in spec.get('assets',[]):
        asset_path=rooted(asset)
        asset_path.relative_to(package)
        assets.append(dict(path=rel(asset_path),sha256=digest(asset_path)))
    for variant in spec['variants']:
        folder=target/variant['id']
        folder.mkdir()
        images={}
        for ratio,size in SIZES.items():
            im,layout=render(photo,size,spec['cover_lines'],variant['style'],variant.get('background'))
            path=folder/f'封面_{ratio}.jpg'
            im.save(path,quality=95,subsampling=0,optimize=True)
            images[ratio]=path.relative_to(target).as_posix()
            with Image.open(path) as exported:
                if exported.size!=size or exported.format!='JPEG':raise ValueError('Bad image export')
                exported.verify()
            exports.append(dict(path=rel(path),sha256=digest(path),layout=layout))
        variants.append(dict(variant,images=images))
    # Compare actual exports, not a separate mockup.
    sheet=Image.new('RGB',(1488,1090*((len(variants)+1)//2)),'#F3F0E8')
    draw=ImageDraw.Draw(sheet)
    for i,v in enumerate(variants):
        x=24+(i%2)*732
        offset=(i//2)*1090
        draw.text((x,offset+15),v['label'],font=font(28,True),fill='#1B2524')
        for ratio,y,max_h in [('16x9',65,394),('4x3',510,525)]:
            im=Image.open(target/v['images'][ratio])
            im.thumbnail((700,max_h),Image.Resampling.LANCZOS)
            sheet.paste(im,(x,offset+y))
            draw.text((x,offset+y+max_h+7),ratio.replace('x',':'),font=font(20,True),fill='#1B2524')
    sheet.save(target/'B站封面对比.jpg',quality=95)
    gallery(target,spec,variants)
    (package/'发布标题.txt').write_text(spec['publication_title']+'\n',encoding='utf-8-sig')
    (package/'封面文案.txt').write_text(''.join(spec['cover_lines'])+'\n',encoding='utf-8-sig')
    previous=read(package/'发布选择.json') if (package/'发布选择.json').exists() else {}
    selection=dict(status='awaiting_cover_style_selection',publication_title=spec['publication_title'],
                   title_confirmed_by_user=True,title_source_candidate=spec.get('title_source_candidate',previous.get('title_source_candidate')),cover_text=''.join(spec['cover_lines']),
                   cover_text_confirmed_by_user=True,cover_text_source_candidate=spec.get('cover_text_source_candidate',previous.get('cover_text_source_candidate')),selected_cover_style=None,
                   feedback=spec['feedback'],revision=rel(target),spec_sha256=digest(spec_path),
                   frame_provenance=record,variants=variants,assets=assets,updated_at_utc=now())
    write(package/'发布选择.json',selection)
    write(materials_path(job)/'current_selection.json',selection)
    data.update(status=selection['status'],selected_publication_title=spec['publication_title'],
                selected_cover_text=selection['cover_text'],cover_revision=rel(target),selected_cover_style=None)
    write(package/'发布包.json',data)
    from tools.build_publication_package import write_gallery
    write_gallery(package,data)
    (package/'选择说明.md').write_text(
        '# 当前发布选择\n\n标题已按用户反馈确定：'+spec['publication_title']+'。\n\n'
        '封面文字确定为：'+selection['cover_text']+'。\n\n'
        f"本轮外观比较请打开 {spec['revision_name']}/封面修订总览.html。包含："+'；'.join(v['label'] for v in variants)+'。尚未替用户选定外观。\n\n'
        'B站准备16:9和4:3，同一版式另附9:16和3:4。均没有整块banner、眉题和副标题。\n\n'
        '第一轮20组候选继续保留。成片、通用说明、文字稿和字幕沿用已检查版本，封面修订不更改成片。\n',encoding='utf-8-sig')
    report=dict(passed=True,revision=rel(target),variants=len(variants),cover_exports=len(exports),
                selected_cover_style=None,title_confirmed=True,cover_text_confirmed=True,
                images=exports,assets=assets,final_video_unchanged=True,checked_at_utc=now())
    write(target/'修订检查.json',report)
    write(materials_path(job)/'cover_revision_record.json',report)
    return dict(passed=True,revision=rel(target),gallery=rel(target/'封面修订总览.html'),
                variants=len(variants),exports=len(exports),status=selection['status'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',required=True)
    parser.add_argument('--spec',required=True)
    args=parser.parse_args()
    print(json.dumps(build(job_path(args.job),args.spec),ensure_ascii=False,indent=2))
