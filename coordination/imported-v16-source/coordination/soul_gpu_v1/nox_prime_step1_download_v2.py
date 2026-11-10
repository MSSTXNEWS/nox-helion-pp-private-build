"""NOX PRIME STEP-1: download only the minimum new trainable NOX base and RU/ES assets.

A real downloader, NOT a second app, automatic training/VM, or tensor merging.
One base only: Qwen3-0.6B. Reuse the resident Qwen3:8B teacher, existing S03,
LoRA, source UI, embeddings and voice assets whenever they are already verified.
The ten research roles are software/queue modules, not ten more models.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from nox_prime_download_five_v1 import download as load_base
from nox_prime_progress_v1 import log_event

MODEL_ID="Qwen/Qwen3-0.6B"
EMBED_TAG="qwen3-embedding:0.6b"
STAGES=("NOX_TRAINABLE_BASE","SEMANTIC_MEMORY","GOEMOTIONS_REUSE",
        "VOICE_RU_ES","WHISPER_RU_ES")
WHISPER_ID="ggerganov/whisper.cpp"
WHISPER_FILENAME="ggml-small.bin"
VOICE_ID="qwen3_06_customvoice"

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def reserve(root,estimate):
    free=shutil.disk_usage(root).free
    if free-int(estimate)<60_000_000_000:
        raise RuntimeError("DISK_RESERVE_HOLD: require 60GB after estimated download")

def event(root,status,message,actual):
    log_event(root,"DOWNLOAD",status,message,actual=actual,total=len(STAGES))

def model(root):
    return load_base(root,max_new_gb=5,only=["Qwen3-0.6B"])

def embedding(root):
    r=subprocess.run(["ollama","list"],capture_output=True,text=True,
                     timeout=25,check=True)
    names={row.split()[0] for row in r.stdout.splitlines()[1:] if row.split()}
    if EMBED_TAG in names:return {"state":"EXISTING_OLLAMA_TAG","tag":EMBED_TAG}
    reserve(root,2_200_000_000)
    subprocess.run(["ollama","pull",EMBED_TAG],check=True,timeout=3600)
    return {"state":"PULLED_OLLAMA_TAG","tag":EMBED_TAG}

def goemotions(root):
    # This is source-verified corpus reuse, not another English-only training.
    from nox_prime_soul_stage1_train import load_data
    folder,info=load_data(root)
    return {"state":"VERIFIED_CORPUS",
            "folder":str(folder),
            "source_commit":info.get("revision"),
            "new_neural_weights":False}

def voice(root,source):
    from download_nox_voice_max import read_manifest,model_download
    manifest=read_manifest(source/"NOX_VOICE_MAX_MODELS_MANIFEST_V1.json")
    voice_root=root/"brain"/"voice"
    results=[]
    for item in manifest["models"]:
        if item["id"] not in (VOICE_ID,"piper_ru_irina","piper_es_davefx"):
            continue
        model_download(item,voice_root,False,
                       manifest["voice_extra_budget_gb"],
                       manifest["minimum_free_disk_gb"])
        results.append(item["id"])
    if len(results)!=3:raise RuntimeError("NOX_VOICE_STARTER_MISSING_MANIFEST_ITEM")
    return {"state":"MODEL_FILES_ONLY_NOT_INFERENCE_TESTED","items":results}

def whisper(root):
    from huggingface_hub import HfApi,hf_hub_download
    target=root/"brain"/"speech"/"models"/"whisper-small"
    target.mkdir(parents=True,exist_ok=True)
    api=HfApi()
    info=api.model_info(WHISPER_ID,revision="main",files_metadata=True)
    rev=getattr(info,"sha",None)
    if not isinstance(rev,str) or len(rev)!=40:
        raise RuntimeError("WHISPER_UNPINNED")
    files={x.rfilename:getattr(x,"size",None) for x in (info.siblings or [])}
    if WHISPER_FILENAME not in files:
        raise RuntimeError("WHISPER_OFFICIAL_MODEL_NOT_FOUND")
    dest=target/("revision_"+rev[:12])
    path=dest/WHISPER_FILENAME
    receipt=dest/"NOX_WHISPER_SHA256.json"
    if receipt.is_file():
        obj=json.loads(receipt.read_text(encoding="utf-8"))
        if obj.get("revision")!=rev or obj.get("model_sha256")!=sha256(path):
            raise RuntimeError("WHISPER_EXISTING_CHECKSUM_CONFLICT")
        return {"state":"REUSED_SHA256","path":str(path)}
    reserve(root,750_000_000)
    dest.mkdir(parents=True,exist_ok=True)
    hf_hub_download(repo_id=WHISPER_ID,filename=WHISPER_FILENAME,
                    revision=rev,local_dir=str(dest))
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("WHISPER_MODEL_DOWNLOAD_INCOMPLETE")
    size=files[WHISPER_FILENAME]
    if size is not None and size!=path.stat().st_size:
        raise RuntimeError("WHISPER_UPSTREAM_SIZE_MISMATCH")
    digest=sha256(path)
    with receipt.open("x",encoding="utf-8") as f:
        json.dump({"source":WHISPER_ID,"revision":rev,
                   "file":WHISPER_FILENAME,"model_sha256":digest,
                   "bytes":path.stat().st_size,
                   "state":"SHA256_CHECKED","inference_tested":False},f,indent=2)
    return {"state":"SHA256_CHECKED","path":str(path)}

def run(root,source):
    root=Path(root).resolve()
    source=Path(source).resolve()
    if not (root/"brain").is_dir():
        raise RuntimeError("EXISTING_NOX_BRAIN_REQUIRED")
    results={}
    holds={}
    plan=[lambda:model(root),lambda:embedding(root),lambda:goemotions(root),
          lambda:voice(root,source),lambda:whisper(root)]
    event(root,"START","NOX STEP1 actual minimal-weight download and reuse",0)
    for index,(name,operation) in enumerate(zip(STAGES,plan),1):
        event(root,"RUNNING","Start "+name,index-1)
        print("NOX PRIME STEP1",index,"/",len(STAGES),name,flush=True)
        try:
            result=operation()
            results[name]=result
            event(root,"SAVED","Available with real source evidence: "+name,index)
        except Exception as exc:
            holds[name]=type(exc).__name__+": "+str(exc)[:220]
            event(root,"HOLD",name+" "+type(exc).__name__,index-1)
            print("NOX HOLD",name,holds[name],file=sys.stderr,flush=True)
            # Do not risk a later model download after the first blocked
            # mandatory component; preserve what was already downloaded.
            break
    report={"schema":"NOX_PRIME_STEP1_MINIMAL_V2",
            "when_utc":datetime.now(timezone.utc).isoformat(),
            "confirmed_groups":results,"holds":holds,
            "s03_changed":False,"prior_lora_modified":False,
            "neural_training_completed":False,
            "engines_installed":False,
            "research_worms_implemented":False,
            "next":"Train own compatible NOX base + integrate cognition and 10 research software roles"}
    summary=root/"brain"/"telemetry"/"prime_step1_download_v2.json"
    summary.parent.mkdir(parents=True,exist_ok=True)
    temp=summary.with_suffix(".tmp")
    temp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(temp,summary)
    event(root,"DONE" if not holds else "HOLD",
          "Stage1 download finished" if not holds else "Stage1 download needs review",
          len(results))
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return 0 if not holds else 2

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path(r"C:\NOX_HELION\NOX_NEW"))
    parser.add_argument("--source",type=Path,default=Path(__file__).parent)
    args=parser.parse_args()
    try:sys.exit(run(args.root,args.source))
    except Exception as exc:
        print("NOX STEP1 HOLD",type(exc).__name__,str(exc),
              file=sys.stderr,flush=True)
        sys.exit(1)
