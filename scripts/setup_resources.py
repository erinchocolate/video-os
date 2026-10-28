"""Offline checks by default; restore packages/model only with explicit flags."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.request import Request, urlopen

sys.stdout.reconfigure(encoding="utf-8")
SCRIPTS=Path(__file__).resolve().parent
sys.path.insert(0,str(SCRIPTS/"vendor"))

def main():
    p=argparse.ArgumentParser(description="Check packaged resources or explicitly restore missing local resources")
    p.add_argument("--check",action="store_true")
    p.add_argument("--init",action="store_true",help="Create empty workspace/resource directories; no packages required")
    p.add_argument("--packages",action="store_true",help="Install pinned packages inside scripts/vendor, requires network")
    p.add_argument("--model",action="store_true",help="Download public ASR model, never upload media")
    p.add_argument("--font",type=Path,help="Copy a locally licensed XinQingNian TTF; never overwrite a different existing font")
    args=p.parse_args()
    for name in ["Inbox","raw","final","process","package","upload","scripts/vendor","scripts/models","scripts/fonts","scripts/cache"]:
        (SCRIPTS.parent/name).mkdir(parents=True,exist_ok=True)
    if args.init and not (args.check or args.packages or args.model or args.font):
        print("Workspace directories ready; no resources downloaded.")
        return
    if args.packages:
        subprocess.run([sys.executable,"-m","pip","install","--target",str(SCRIPTS/"vendor"),"--cache-dir",str(SCRIPTS/"cache/pip"),"-r",str(SCRIPTS/"requirements.lock.txt")],check=True)
    if args.model:
        from video_pipeline.common import digest
        config=json.loads((SCRIPTS/"config/environment.json").read_text(encoding="utf-8"))
        folder=SCRIPTS/"models/large-v3-turbo"; folder.mkdir(parents=True,exist_ok=True)
        base="https://huggingface.co/"+config["model_repo"]+"/resolve/main/"
        for name in ["config.json","preprocessor_config.json","tokenizer.json","vocabulary.json","model.bin"]:
            target=folder/name
            if target.exists():
                if name=="model.bin" and digest(target)!=config["model_sha256"]:
                    raise ValueError("Existing model checksum mismatch; preserve it before replacement")
                continue
            temporary=target.with_suffix(target.suffix+".part"); sha=hashlib.sha256(); received=0
            with urlopen(Request(base+name,headers={"User-Agent":"video-os-resource-setup"}),timeout=60) as response:
                expected=int(response.headers.get("content-length","0"))
                with temporary.open("wb") as output:
                    while chunk:=response.read(1048576):
                        output.write(chunk); sha.update(chunk); received+=len(chunk)
                if expected and received!=expected: raise ValueError("Incomplete model download")
            if name=="model.bin" and sha.hexdigest().upper()!=config["model_sha256"]: raise ValueError("Downloaded model checksum mismatch")
            temporary.replace(target)
            print("Downloaded "+name,flush=True)
    if args.font:
        from video_pipeline.common import digest
        source=args.font.resolve(strict=True)
        target=SCRIPTS/"fonts/xinqingnian.ttf"
        with source.open("rb") as font:
            if font.read(4) not in (b"\x00\x01\x00\x00",b"OTTO",b"ttcf"):
                raise ValueError("Font input must be a TrueType/OpenType font")
        if target.exists():
            if digest(source)!=digest(target):
                raise ValueError("Existing font differs; preserve it before replacement")
        else:
            shutil.copy2(source,target)
    from video_pipeline.intake import doctor
    print(json.dumps(doctor(deep=True),ensure_ascii=False,indent=2))

if __name__=="__main__": main()
