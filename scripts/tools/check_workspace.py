"""Check project routing, migrated paths, media integrity, and approval state."""
from pathlib import Path
import json
import re
import sys

SCRIPTS=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SCRIPTS),str(SCRIPTS/"vendor")]
sys.stdout.reconfigure(encoding="utf-8")
from video_pipeline.common import ROOT,read,digest,rel,require_approval
from video_pipeline import packaging

def main():
    docs=[ROOT/"AGENTS.md",ROOT/"工作流说明.md",*sorted((ROOT/"skill").rglob("*.md"))]
    links=0
    for doc in docs:
        text=doc.read_text(encoding="utf-8-sig")
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)",text):
            if "://" in link or link.startswith("#"): continue
            link=link.split("#")[0].strip("<>")
            if not (doc.parent/link).resolve().exists(): raise ValueError(f"Missing documentation target: {doc.name} -> {link}")
            links+=1
    code=[SCRIPTS/"video.py",*sorted((SCRIPTS/"video_pipeline").glob("*.py"))]
    for p in code:
        compile(p.read_text(encoding="utf-8"),str(p),"exec")
        if "2026-10-08_sample" in p.read_text(encoding="utf-8"): raise ValueError("Sample-specific path in active pipeline")
    jobs=[]
    for file in sorted((ROOT/"process").glob("*/manifest.json")):
        m=read(file); job=file.parent
        assert m["process_dir"]==rel(job)
        assert digest(ROOT/m["source_path"])==m["original_sha256"]
        result=dict(job=rel(job),status=m["status"],source_hash_verified=True)
        if m["status"]=="completed":
            assert digest(ROOT/m["final_path"])==m["final_sha256"]
            result["final_hash_verified"]=True
        elif m["status"]=="awaiting_edit_approval":
            try: require_approval(job)
            except ValueError: result["unapproved_edit_blocked"]=True
            else: raise ValueError("Pending-review video unexpectedly has executable approval")
            assert not (job/"edited_audio.wav").exists()
        jobs.append(result)
    assert not (ROOT/"work").exists(),"Old mixed work directory still exists"
    packages=[]
    for path in sorted((ROOT/'package').glob('*/发布包.json')):
        data=read(path);job=ROOT/data['source_job']
        assert not (job/'publishing').exists(),'Publication materials still mixed into process'
        assert (path.parent/'materials').is_dir()
        result=dict(package=rel(path.parent),status=data['status'])
        if data['status']=='upload_ready':
            result.update(upload_verified=packaging.upload_check(job)['passed'])
        packages.append(result)
    print(json.dumps(dict(passed=True,documentation_files=len(docs),valid_local_links=links,
                          skills=len(list((ROOT/"skill").glob("*/SKILL.md"))),jobs=jobs,
                          packages=packages,active_scripts_have_no_sample_path=True),ensure_ascii=False,indent=2))

if __name__=="__main__": main()
