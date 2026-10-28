"""Run from workspace root: python -X utf8 scripts/video.py --help."""
import argparse
import json
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding="utf-8",errors="replace")
sys.stderr.reconfigure(encoding="utf-8",errors="replace")
if not __debug__: raise SystemExit("Run without -O; verification assertions must remain enabled")
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/"vendor"))
from video_pipeline.common import ROOT,job_path,read,rel

def main():
    parser=argparse.ArgumentParser(description="Video SOP: process for editing, package for publication, upload for chosen delivery")
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("doctor"); p.add_argument("--deep",action="store_true")
    p=sub.add_parser("ingest"); p.add_argument("--input",required=True); p.add_argument("--timestamp",help="YYYYMMDDHHMMSS if absent from filename")
    p=sub.add_parser("status"); p.add_argument("--job")
    for name in ["transcribe","correct-transcript","archive","review","approve","edit","subtitles","preview","render","frames","verify","publish"]:
        p=sub.add_parser(name); p.add_argument("--job",required=True)
        if name=="transcribe":
            p.add_argument("--edited",action="store_true"); p.add_argument("--start",type=float); p.add_argument("--end",type=float)
        elif name=="correct-transcript": p.add_argument("--spec",required=True); p.add_argument("--edited",action="store_true")
        elif name=="archive": p.add_argument("--title",required=True)
        elif name=="review": p.add_argument("--spec",required=True); p.add_argument("--trim-pauses",action="store_true")
        elif name=="approve": p.add_argument("--message",required=True); p.add_argument("--plan-hash",required=True)
        elif name=="subtitles": p.add_argument("--spec",required=True)
        elif name=="preview":
            p.add_argument("--text",required=True); p.add_argument("--emphasis"); p.add_argument("--at",type=float,required=True)
        elif name=="publish": p.add_argument("--visual-note",required=True)
    for name in ['package-prepare','package-build','package-refine','package-feedback','package-select','package-check','package-migrate','upload-ready','upload-check']:
        p=sub.add_parser(name);p.add_argument('--job',required=True)
        if name in ['package-build','package-refine','package-feedback','package-select']:p.add_argument('--spec',required=True)
        if name=='package-select':p.add_argument('--message',required=True)
        if name=='upload-ready':p.add_argument('--revision',help='New delivery suffix; existing deliveries stay unchanged')
    for name in ['subtitle-review','subtitle-approve']:
        p=sub.add_parser(name);p.add_argument('--job',required=True)
        if name=='subtitle-approve':p.add_argument('--message',required=True);p.add_argument('--subtitle-hash',required=True)
    args=parser.parse_args()
    from video_pipeline import intake,asr,editing,captions
    if args.command=="doctor": return intake.doctor(args.deep)
    if args.command=="ingest": return intake.ingest(args.input,args.timestamp)
    if args.command=="status":
        if args.job: return read(job_path(args.job)/"manifest.json")
        return [dict(job=rel(p.parent),status=read(p)["status"],title=read(p).get("title")) for p in sorted((ROOT/"process").glob("*/manifest.json"))]
    job=job_path(args.job)
    if args.command in ['subtitle-review','subtitle-approve']:
        from video_pipeline import subtitle_review
        return subtitle_review.prepare(job) if args.command=='subtitle-review' else subtitle_review.approve(job,args.message,args.subtitle_hash)
    if args.command.startswith('package-') or args.command.startswith('upload-'):
        from video_pipeline import packaging
        name=args.command.replace('package-','').replace('-','_')
        fn=getattr(packaging,name)
        if args.command=='upload-ready':return fn(job,args.revision)
        if args.command=='package-select':return fn(job,args.spec,args.message)
        if hasattr(args,'spec'):return fn(job,args.spec)
        return fn(job)
    if args.command=="transcribe": return asr.transcribe(job,args.edited,args.start,args.end)
    if args.command=="correct-transcript": return asr.correct_transcript(job,args.spec,args.edited)
    if args.command=="archive": return intake.archive(job,args.title)
    if args.command=="review": return intake.review(job,args.spec,args.trim_pauses)
    if args.command=="approve": return intake.approve(job,args.message,args.plan_hash)
    if args.command=="subtitles": return captions.subtitles(job,args.spec)
    if args.command=="preview": return captions.preview(job,args.text,args.emphasis,args.at)
    if args.command=="publish": return editing.publish(job,args.visual_note)
    return getattr(editing,args.command)(job)

if __name__=="__main__":
    try:
        print(json.dumps(main(),ensure_ascii=False,indent=2))
    except (ValueError,FileNotFoundError,FileExistsError,RuntimeError,AssertionError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        raise SystemExit(2)
