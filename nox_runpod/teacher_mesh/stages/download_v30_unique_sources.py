#!/usr/bin/env python3
"""NOX V30: acquire only NEW opt-in, pinned external source repositories.
No code execution, installs, dataset downloads or GPU activity.
Existing NOX catalog 200 + V29 14 archived repos stay untouched.
"""
from __future__ import annotations
import datetime, hashlib, json, os, pathlib, re, subprocess, tempfile, zipfile, urllib.request, shutil, sys
from urllib.error import URLError

GROUPS = {
    "agent_reinforcement": [
        "microsoft/agent-lightning",
        "pydantic/pydantic-ai",
        "langchain-ai/deepagents",
    ],
    "quality_and_safety": [
        "promptfoo/promptfoo",
        "NVIDIA/garak",
    ],
}
MAX_BYTES=125_000_000
SCHEMA="nox-v30-new-future-open-source-acquisition-v1"

def acquire(repo:str,directory:pathlib.Path)->dict:
    record={"repo":repo,"status":"HOLD_NOT_DOWNLOADED",
            "origin":"https://github.com/"+repo,
            "license":"REVIEW_REQUIRED","installed":False,"executed":False}
    cmd=subprocess.run(["git","ls-remote","https://github.com/"+repo+".git","HEAD"],
        capture_output=True,text=True,timeout=75,env={**os.environ,"GIT_TERMINAL_PROMPT":"0"})
    if cmd.returncode:
        raise RuntimeError("PIN_RESOLUTION_FAILED")
    sha=cmd.stdout.strip().split()[0] if cmd.stdout.strip() else None
    if not isinstance(sha,str) or not re.fullmatch(r"[a-f0-9]{40}",sha):
        raise RuntimeError("INVALID_UPSTREAM_PIN")
    record["commit_sha"]=sha
    path=directory/(repo.replace("/","_")+"_"+sha[:12]+".zip")
    part=path.with_suffix(".partial")
    url="https://codeload.github.com/"+repo+"/zip/"+sha
    h=hashlib.sha256();size=0
    try:
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={
                "User-Agent":"NOX-v30-pinned-source-audit/2026-11-13"}),timeout=150) as stream, part.open("wb") as f:
                while True:
                    chunk=stream.read(1024*1024)
                    if not chunk:break
                    size+=len(chunk)
                    if size>MAX_BYTES:raise ValueError("PINNED_ARCHIVE_TOO_LARGE")
                    h.update(chunk);f.write(chunk)
            method="PINNED_CODELOAD"
        except Exception as err:
            part.unlink(missing_ok=True)
            with tempfile.TemporaryDirectory() as tmp:
                checkout=pathlib.Path(tmp)/"checkout"
                env={**os.environ,"GIT_TERMINAL_PROMPT":"0","GIT_LFS_SKIP_SMUDGE":"1"}
                clone=subprocess.run(["git","clone","--quiet","--depth","1","--filter=blob:none",
                   "--no-tags","https://github.com/"+repo+".git",str(checkout)],
                   capture_output=True,text=True,timeout=150,env=env)
                if clone.returncode:raise RuntimeError("CODELOAD_AND_GIT_UNAVAILABLE") from err
                observed=subprocess.check_output(["git","-C",str(checkout),"rev-parse","HEAD"],text=True).strip()
                if observed!=sha:raise RuntimeError("GIT_HEAD_MOVED_DURING_DOWNLOAD")
                with zipfile.ZipFile(part,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
                    for rel in subprocess.check_output(["git","-C",str(checkout),"ls-files","-z"]).decode().split("\0"):
                        if not rel:continue
                        f=checkout/rel
                        if not f.is_file() or f.is_symlink():continue
                        size+=f.stat().st_size
                        if size>MAX_BYTES:raise ValueError("GIT_TRACKED_FILES_OVER_LIMIT")
                        z.write(f,arcname=repo.replace("/","-")+"-"+sha+"/"+rel)
                method="PINNED_GIT_TRACKED_ZIP"
        if size<1000 or not zipfile.is_zipfile(part):raise ValueError("BAD_SOURCE_ARCHIVE")
        with zipfile.ZipFile(part) as z:
            bad=z.testzip()
            if bad is not None:raise ValueError("ZIP_CRC_ERROR_"+bad)
            names=[f.filename for f in z.infolist() if not f.is_dir()]
            if len(names)<3 or any(f.startswith("/") or ".." in pathlib.PurePosixPath(f).parts or "\\" in f for f in names):
                raise ValueError("UNSAFE_SOURCE_PATHS")
        os.replace(part,path)
        record.update(status="PINNED_SOURCE_SHA256_CRC_VERIFIED",
            acquisition_method=method,archive=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            bytes=path.stat().st_size,entries=len(names))
        return record
    finally:part.unlink(missing_ok=True)

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--group",choices=GROUPS,required=True)
    ap.add_argument("--out",required=True,type=pathlib.Path)
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    out=[]
    for repo in GROUPS[args.group]:
        try:record=acquire(repo,args.out)
        except Exception as err:
            record={"repo":repo,"status":"HOLD_NOT_DOWNLOADED","reason":str(err),
                    "installed":False,"executed":False}
        out.append(record)
        print(json.dumps({"repo":repo,"status":record["status"],"size":record.get("bytes",0),
                          "reason":record.get("reason","")}),flush=True)
    manifest={"schema":SCHEMA,"group":args.group,"generated_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "requested":len(out),"verified":sum(x["status"]=="PINNED_SOURCE_SHA256_CRC_VERIFIED" for x in out),
        "status":"VERIFIED_ALL" if all(x["status"]=="PINNED_SOURCE_SHA256_CRC_VERIFIED" for x in out) else "HOLD_PARTIAL",
        "repo_records":out,"source_only":True,"training_license_review_required":True,
        "production_modified":False,"nox_model_updated":False}
    (args.out/"NOX_V30_UPSTREAM_PROVENANCE.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (args.out/"SHA256SUMS.txt").write_text("".join(x["sha256"]+"  "+x["archive"]+"\n"
             for x in out if x["status"]=="PINNED_SOURCE_SHA256_CRC_VERIFIED"),encoding="utf-8")
    if manifest["verified"]==0:raise SystemExit("HOLD_NO_REAL_SOURCES")
if __name__=="__main__":main()
