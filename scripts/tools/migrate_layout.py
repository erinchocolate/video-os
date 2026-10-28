"""One-time, non-overwriting migration of the accepted sample and shared tools."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT=Path(__file__).resolve().parent.parent
OLD="work/2026-10-08_sample"
NEW="process/2026-10-08_09-34-30_回应之前，先问问对方的感受"

def move(source,target):
    source,target=ROOT/source,ROOT/target
    source.resolve().relative_to(ROOT.resolve())
    target.resolve().relative_to(ROOT.resolve())
    if target.exists(): raise FileExistsError(str(target))
    target.parent.mkdir(parents=True,exist_ok=True)
    os.rename(source,target)

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(8388608),b""): h.update(b)
    return h.hexdigest().upper()

if not (ROOT/OLD).exists():
    raise SystemExit("Original sample directory missing; migration not repeated")
m=json.loads((ROOT/OLD/"manifest.json").read_text(encoding="utf-8"))
original_hashes={k:digest(ROOT/m[k]) for k in ["source_path","final_path"]}
assert original_hashes["source_path"]==m["original_sha256"]
assert original_hashes["final_path"]==m["final_sha256"]
inventory=sorted(p.relative_to(ROOT/OLD).as_posix() for p in (ROOT/OLD).rglob("*") if p.is_file())
move(OLD,NEW)
job=ROOT/NEW
snapshot=job/"history/metadata_before_layout"
snapshot.mkdir(parents=True)
for p in job.rglob("*.json"):
    if "history" not in p.relative_to(job).parts:
        target=snapshot/p.relative_to(job)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,target)
for name in ["finish_sample.py","generate_sample_subtitles.py","prepare_sample_review.py","preview_subtitle_style.py","transcribe_local.py","verify_asr.py"]:
    move("work/"+name,NEW+"/history/sample_scripts/"+name+".txt")
move("work","scripts")
for a,b in [("_fonts","fonts"),("_models","models"),("_python","vendor"),("_hf","cache/huggingface"),("_pip_cache","cache/pip")]:
    if (ROOT/"scripts"/a).exists(): move("scripts/"+a,"scripts/"+b)
move("scripts/migrate_layout.py","scripts/tools/migrate_layout.py")
replacements=[(OLD,NEW),(str(ROOT/OLD),str(ROOT/NEW)),("work/_fonts","scripts/fonts"),("work/_models","scripts/models"),("work/_python","scripts/vendor")]
def fix(value):
    if isinstance(value,dict): return {k:fix(v) for k,v in value.items()}
    if isinstance(value,list): return [fix(v) for v in value]
    if isinstance(value,str):
        for a,b in replacements: value=value.replace(a,b)
    return value
for p in job.rglob("*"):
    if not p.is_file() or "history" in p.relative_to(job).parts: continue
    if p.suffix==".json":
        data=fix(json.loads(p.read_text(encoding="utf-8-sig")))
        p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    elif p.suffix in [".md",".ffgraph",".ass"]:
        text=fix(p.read_text(encoding="utf-8-sig")).replace("fontsdir=../_fonts","fontsdir=../../scripts/fonts")
        p.write_text(text,encoding="utf-8-sig" if p.suffix in [".md",".ass"] else "utf-8")
m=fix(m)
m.update(layout_version=2,capture_timestamp="20261008093430",process_dir=NEW)
(job/"manifest.json").write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding="utf-8")
assert all(digest(ROOT/m[k])==v for k,v in original_hashes.items())
audit=dict(old_process_dir=OLD,new_process_dir=NEW,original_media_hashes=original_hashes,
           media_bytes_unchanged=True,original_process_files=inventory,
           historical_scripts="history/sample_scripts/*.py.txt are snapshots, not executable entrypoints")
(job/"history/layout_migration.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(dict(process_dir=NEW,shared_tools="scripts",media_bytes_unchanged=True,preserved_process_files=len(inventory)),ensure_ascii=False,indent=2))
