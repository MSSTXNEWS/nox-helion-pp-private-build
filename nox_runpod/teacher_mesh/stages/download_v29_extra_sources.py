#!/usr/bin/env python3
"""Download a bounded, real, pinned set of ADDITIONAL future-NOX source trees.

All existing NOX catalog 1-200 and prior V27/V28 source archives are preserved,
NOT duplicated here. External code is UNTRUSTED, never imported or executed.
Missing/oversized repos remain HOLD, not fabricated download successes.
GitHub archive contents are CRC tested, SHA-256 recorded, upstream revision fixed.
"""
from __future__ import annotations
import argparse,datetime,hashlib,json,os,pathlib,re,urllib.request,zipfile
from contextlib import closing

REPOS={
  "kernels":[
    "pytorch/ao","pytorch/torchtune","huggingface/safetensors",
    "flashinfer-ai/flashinfer","LMCache/LMCache","mlc-ai/xgrammar",
    "huggingface/optimum"
  ],
  "benchmarks":[
    "evalplus/evalplus","NVIDIA/RULER","open-compass/opencompass",
    "allenai/open-instruct","SWE-bench/SWE-bench",
    "sierra-research/tau2-bench","THUDM/LongBench"
  ],
}
SCHEMA="nox-v29-extra-open-source-snapshots-v1"
LIMIT_PER_REPO=90_000_000
APPROVED_FOR_RESEARCH={"MIT","Apache-2.0","BSD-3-Clause","BSD-2-Clause","MPL-2.0","CC-BY-4.0"}
HEADER="NOX-V29-pin-source-audit/1.0"
def get(url, *, token=False):
    headers={"User-Agent":HEADER,"Accept":"application/vnd.github+json"}
    if token and os.environ.get("GH_TOKEN"):
        headers["Authorization"]="Bearer "+os.environ["GH_TOKEN"]
    return urllib.request.Request(url,headers=headers)

def metadata(url,token=True):
    with urllib.request.urlopen(get(url,token=token),timeout=35) as f:return json.load(f)

def dl_to_zip(url, path):
    part=path.with_suffix(path.suffix+".partial")
    h=hashlib.sha256()
    count=0
    try:
        with closing(urllib.request.urlopen(get(url),timeout=180)) as stream,part.open("wb") as out:
            while chunk:=stream.read(2*1024*1024):
                count+=len(chunk)
                if count>LIMIT_PER_REPO:raise ValueError("UPSTREAM_REPO_ARCHIVE_OVER_LIMIT")
                h.update(chunk);out.write(chunk)
        if count<1024:raise ValueError("ARCHIVE_TOO_SMALL")
        if not zipfile.is_zipfile(part):raise ValueError("NOT_SOURCE_ZIP")
        with zipfile.ZipFile(part) as z:
            bad=z.testzip()
            if bad:raise ValueError("ZIP_CRC_FAIL_"+bad)
            members=[x for x in z.namelist() if not x.endswith("/")]
            if len(members)<2:raise ValueError("EMPTY_SOURCE_REPO")
            if any(x.startswith("/") or ".." in pathlib.PurePosixPath(x).parts for x in members):
                raise ValueError("PATH_TRAVERSAL")
        part.rename(path)
        return {"bytes":count,"sha256":h.hexdigest(),"members":len(members)}
    finally:part.unlink(missing_ok=True)

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--group",required=True,choices=tuple(REPOS))
    cli.add_argument("--out",default="out")
    a=cli.parse_args()
    root=pathlib.Path(a.out)
    root.mkdir(parents=True,exist_ok=True)
    details=[]
    for index,repo in enumerate(REPOS[a.group],1):
        owner,name=repo.split("/")
        entry={"repo":repo,"status":"HOLD_NOT_DOWNLOADED","source":"https://github.com/"+repo}
        try:
            info=metadata("https://api.github.com/repos/"+repo)
            if info.get("archived") is True:
                entry["maintenance"]="UPSTREAM_ARCHIVED"
            branch=info["default_branch"]
            commit=metadata("https://api.github.com/repos/"+repo+"/commits/"+branch)["sha"]
            license_id=(info.get("license") or {}).get("spdx_id") or "UNKNOWN"
            entry.update({"commit_sha":commit,"license_spdx":license_id,"branch":branch,
                          "rights":"LICENSE_REVIEW_REQUIRED" if license_id not in APPROVED_FOR_RESEARCH else "UPSTREAM_LICENSE_ID_READ"})
            file=(root/("%02d_%s_%s.zip"%(index,owner,name))).resolve()
            data=dl_to_zip("https://codeload.github.com/"+repo+"/zip/"+commit,file)
            entry.update({"status":"SOURCE_ARCHIVE_DOWNLOADED_SHA_CRC_VERIFIED",
                          "archive":file.name,**data,
                          "license_usage_approved_for_nox_training":False,
                          "installed":False,"executed":False})
        except Exception as error:
            entry["hold_reason"]=type(error).__name__+": "+str(error)
        details.append(entry)
        print(json.dumps({"repo":repo,"status":entry["status"],
                          "bytes":entry.get("bytes",0),
                          "reason":entry.get("hold_reason")},ensure_ascii=False),flush=True)
    complete=sum(x["status"]=="SOURCE_ARCHIVE_DOWNLOADED_SHA_CRC_VERIFIED" for x in details)
    report={"schema":SCHEMA,"group":a.group,"as_of_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status":"PARTIAL_WITH_HOLD" if complete<len(details) else "ALL_SOURCES_DOWNLOADED_VERIFIED",
            "verified_downloads":complete,"requested":len(details),
            "no_model_weights_downloaded":True,
            "no_code_executed":True,
            "no_production_changed":True,
            "sources":details,
            "note":"Source snapshots are research inputs only; installation and licensing review separate."}
    (root/"UPSTREAM_PROVENANCE.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    (root/"SHA256SUMS.txt").write_text("".join(x["sha256"]+"  "+x["archive"]+"\n"
                                           for x in details if "archive" in x))
    if complete==0:raise SystemExit("HOLD_NO_SOURCE_ARCHIVES_DOWNLOADED")
if __name__=="__main__":main()
