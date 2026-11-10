#!/usr/bin/env python3
"""NOX VOICE MAX official-source downloader (downloads only, never executes model code).

Usage:
  python download_nox_voice_max.py --group starter --mode both --execute
  python download_nox_voice_max.py --group expressive --mode models --execute

Without --execute: show the plan, make NO network change. Downloads into NOX's
managed local directory, never into the user's Downloads folder.
Requires Python 3.11+, huggingface_hub for model snapshots, Git for engines.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

MANIFEST = Path(__file__).with_name("NOX_VOICE_MAX_MODELS_MANIFEST_V1.json")
SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_]{1,80}$")
GB = 1_000_000_000

def root_default():
    if os.name == "nt":
        return Path(r"C:\NOX_HELION\NOX_NEW\brain\voice")
    return Path.cwd() / "NOX_VOICE_MAX"

def sha256_file(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as stream:
        for chunk in iter(lambda:stream.read(4*1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def files_in(folder):
    return [p for p in Path(folder).rglob("*")
            if p.is_file() and ".cache" not in p.parts and ".git" not in p.parts]

def safe_id(x):
    if not isinstance(x,str) or not SAFE_NAME.fullmatch(x):
        raise ValueError("Unsafe artifact ID")
    return x

def read_manifest(path=MANIFEST):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema")!="NOX-VOICE-MAX-V1":
        raise RuntimeError("Unsupported voice catalog schema")
    for section,kind in (("models","hf"),("sources","git")):
        for item in data.get(section,[]):
            safe_id(item["id"])
            if kind=="hf" and (not item.get("hf")
                               or "/" not in item["hf"]
                               or len(item["hf"])>160):
                raise ValueError("Bad Hugging Face repo")
            if kind=="git" and not item.get("git","").startswith("https://github.com/"):
                raise ValueError("Only explicit official GitHub HTTPS repos allowed")
    return data

def voice_bytes_consumed(root):
    receipts=Path(root)/"receipts"
    total=0
    for p in receipts.glob("*.json") if receipts.is_dir() else []:
        try:
            record=json.loads(p.read_text(encoding="utf-8"))
            if record.get("status")=="DOWNLOADED_AND_HASHED":
                total+=int(record["stored_bytes"])
        except (OSError,KeyError,TypeError,ValueError):pass
    return total

def disk_gate(root, new_bytes, budget_gb, reserve_gb):
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    if new_bytes <= 0:raise ValueError("Must know positive estimated download size")
    consumed=voice_bytes_consumed(root)
    if consumed+new_bytes > budget_gb*GB:
        raise RuntimeError("VOICE_BUDGET_HOLD: %.2f GB already accounted; %.2f GB new estimated; budget %.1f GB" %
                           (consumed/GB,new_bytes/GB,budget_gb))
    free=shutil.disk_usage(root).free
    if free-new_bytes < reserve_gb*GB:
        raise RuntimeError("DISK_RESERVE_HOLD: %.2f GB free, %.2f GB estimated new, %.1f GB required reserve" %
                           (free/GB,new_bytes/GB,reserve_gb))

def source_sizes(model_info, patterns):
    siblings=getattr(model_info,"siblings",[]) or []
    files=[]
    for x in siblings:
        name=getattr(x,"rfilename",None)
        if not name or (patterns and not any(fnmatch.fnmatch(name,p) for p in patterns)):
            continue
        n=getattr(x,"size",None)
        files.append((name,n))
    return files

def model_download(item, root, dry_run, cap_gb, reserve_gb):
    repo=item["hf"]
    name=safe_id(item["id"])
    target=root/"weights"/name
    receipt_path=root/"receipts"/(name+".json")
    if target.exists() and receipt_path.is_file():
        old=json.loads(receipt_path.read_text(encoding="utf-8"))
        if old.get("status")=="DOWNLOADED_AND_HASHED":
            # Never trust a stale receipt without checking files when requested.
            for rel,hash_ in old.get("sha256",{}).items():
                p=target/rel
                if not p.is_file() or sha256_file(p)!=hash_:
                    raise RuntimeError("LOCAL_HASH_MISMATCH: "+str(p))
            print("SKIP VERIFIED",name,"already downloaded and hashed")
            return
    if target.exists():
        raise RuntimeError("UNVERIFIED_EXISTING_MODEL: "+str(target))
    if dry_run:
        print("PLAN MODEL",name,"=>",repo,
              "estimate",item.get("estimated_gb"),"GB",
              "license",item.get("license"),
              "URL",item.get("source"))
        return
    try:
        from huggingface_hub import HfApi,snapshot_download
    except ImportError as e:
        raise RuntimeError("Missing huggingface_hub. Install in an isolated NOX voice venv first.") from e
    api=HfApi()
    meta=api.model_info(repo,files_metadata=True)
    revision=getattr(meta,"sha",None)
    if not isinstance(revision,str) or not re.fullmatch("[a-f0-9]{40}",revision):
        raise RuntimeError("Could not pin official model revision: "+repo)
    patterns=item.get("patterns")
    members=source_sizes(meta,patterns)
    if not members:
        raise RuntimeError("No selected official weight files: "+repo)
    known_sizes=[int(size) for _,size in members if isinstance(size,int) and size>=0]
    estimated=max(int(float(item.get("estimated_gb",0))*GB*1.15),
                  int(sum(known_sizes)*1.10))
    disk_gate(root,estimated,cap_gb,reserve_gb)
    partial=target.with_name(target.name+".partial")
    partial.mkdir(parents=True,exist_ok=True)
    print("FETCH",repo,"rev",revision,"count",len(members),"estimate_gb",round(estimated/GB,2),flush=True)
    snapshot_download(repo_id=repo,revision=revision,allow_patterns=patterns,
                      local_dir=str(partial),max_workers=2)
    paths=files_in(partial)
    if not paths:raise RuntimeError("No saved model payload: "+name)
    hashes={str(p.relative_to(partial)).replace("\\","/"):sha256_file(p) for p in paths}
    stored=sum(p.stat().st_size for p in paths)
    if stored>int(estimated*1.03):
        raise RuntimeError("Unexpected payload expansion, HOLD: "+name)
    # Check against latest free space; do not delete partial after failure.
    # The snapshot stays staged until all its files have been individually hashed.
    partial.rename(target)
    receipt_path.parent.mkdir(parents=True,exist_ok=True)
    record={"id":name,"repo":repo,"revision":revision,
            "status":"DOWNLOADED_AND_HASHED","stored_bytes":stored,
            "license_claim":item["license"],"sha256":hashes,
            "fetched_utc":datetime.now(timezone.utc).isoformat(),
            "warning":"Downloaded weights, not an AMD Windows inference acceptance"}
    receipt_path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
    print("READY WEIGHTS",name,"bytes",stored,"sha_file_count",len(hashes),flush=True)

def engine_download(item, root, dry_run, reserve_gb):
    name=safe_id(item["id"])
    url=item["git"]
    target=root/"engine_source"/name
    if target.exists():
        if (target/".git").is_dir():
            print("SKIP ENGINE SOURCE",name,"revision",
                  subprocess.check_output(["git","-C",str(target),"rev-parse","HEAD"],text=True).strip())
            return
        raise RuntimeError("UNVERIFIED_EXISTING_SOURCE: "+str(target))
    if dry_run:
        print("PLAN ENGINE",name,url,"license",item["license"])
        return
    # Source checkout only. No pip install, no execution of downloaded scripts.
    disk_gate(root,300_000_000,50,reserve_gb)
    partial=target.with_name(target.name+".partial")
    if partial.exists():raise RuntimeError("PARTIAL_ENGINE_HOLD: "+str(partial))
    target.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(["git","clone","--depth","1","--filter=blob:none",url,str(partial)],
                   check=True)
    sha=subprocess.check_output(["git","-C",str(partial),"rev-parse","HEAD"],text=True).strip()
    partial.rename(target)
    print("ENGINE SOURCE SAVED",name,sha,"INSTALL NOT RUN",flush=True)

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=root_default())
    p.add_argument("--group",choices=["starter","starter_optional","expressive",
                                      "expressive_optional"],default="starter")
    p.add_argument("--mode",choices=["models","engines","both"],default="both")
    p.add_argument("--only",action="append",default=[],
                   help="Filter by exact model/source id; use repeatedly")
    p.add_argument("--execute",action="store_true",
                   help="Download vetted model/source candidates into NOX root")
    args=p.parse_args(argv)
    manifest=read_manifest()
    root=args.root.resolve()
    print("NOX VOICE MAX",args.group,"EXE" if args.execute else "DRY-RUN",
          "VOICE allowance +%s GB" % manifest["voice_extra_budget_gb"])
    if args.mode in ("models","both"):
        for item in manifest["models"]:
            if item["group"]==args.group and (not args.only or item["id"] in args.only):
                model_download(item,root,not args.execute,
                               manifest["voice_extra_budget_gb"],
                               manifest["minimum_free_disk_gb"])
    if args.mode in ("engines","both"):
        for item in manifest["sources"]:
            if item["group"]==args.group and (not args.only or item["id"] in args.only):
                engine_download(item,root,not args.execute,
                                manifest["minimum_free_disk_gb"])
    print("NOX VOICE MAX stage complete. Source/model download != TTS install or GPU acceptance.")

if __name__=="__main__":
    try: main()
    except Exception as e:
        print("NOX VOICE HOLD:",type(e).__name__,str(e),file=sys.stderr)
        sys.exit(1)
