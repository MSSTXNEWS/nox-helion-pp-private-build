"""NOX PRIME Stage-1 complete download coordinator.

ONE no-GPU-download pipeline: 5 open-weight NOX candidates (ordered 0.6B
first), Ollama multilingual embeddings, optional reranker, multilingual
Whisper, Qwen voice design, Piper voices, and pinned sources for hidden engines.
No user-UI for engines, no model execution, no S03/LoRA writes, no deletion.
Does not silently start or overwrite GPU training.
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
from datetime import datetime,timezone
from nox_prime_download_five_v1 import download as download_five, digest
from nox_prime_progress_v1 import log_event

ROOT_DEFAULT=Path(r"C:\NOX_HELION\NOX_NEW")
# Source-pinned ggml-small multilingual Whisper: published SHA256 at source.
WHISPER_REPO="ggerganov/whisper.cpp"
WHISPER_SHA="90a64d80ea254cf67575b41a5971f972c79f7b45"
WHISPER_FILENAME="ggml-small.bin"
WHISPER_EXPECTED_SHA256="1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b"
# These are source-engine revisions pinned at fetch time via Git commit and
# never executed by the download coordinator.
SOURCES=(
    ("whisper_cpp", "https://github.com/ggml-org/whisper.cpp.git"),
    ("qwen3_tts", "https://github.com/QwenLM/Qwen3-TTS.git"),
)
VOICE_IDS=("piper_ru_irina","piper_es_davefx","qwen3_06_customvoice")
VOICE_OPTIONAL=("qwen3_17_voicedesign",)
EMBED_TAG="qwen3-embedding:0.6b"
STAGES=("PRIMARY_WEIGHTS","SEMANTIC_EMBEDDINGS","RE_RANKER","SPEECH_RECOGNITION",
        "VOICE_RU_ES","ENGINE_SOURCES")

def event(root,status,detail,n=0,total=6):
    # The existing FORGE dashboard already reads this event log.
    log_event(root,"DOWNLOAD",status,detail,actual=n,total=total)

def reserve(root,need):
    if shutil.disk_usage(root).free-int(need)<60_000_000_000:
        raise RuntimeError("DISK_RESERVE_HOLD: minimum 60GB free after this step")

def allowed_existing(file,expected):
    if not file.is_file() or file.is_symlink():return False
    if digest(file)!=expected:
        raise RuntimeError("EXISTING_CHECKSUM_CONFLICT: "+str(file))
    return True

def whisper(root,hf_hub_download):
    target=root/"brain"/"speech"/"models"
    target.mkdir(parents=True,exist_ok=True)
    path=target/WHISPER_FILENAME
    if allowed_existing(path,WHISPER_EXPECTED_SHA256):
        return {"status":"REUSED_SHA256","bytes":path.stat().st_size,"path":str(path)}
    if path.exists():
        raise RuntimeError("UNVERIFIED_SPEECH_MODEL_EXISTS")
    reserve(root,700_000_000)
    output=hf_hub_download(repo_id=WHISPER_REPO,filename=WHISPER_FILENAME,
                           revision=WHISPER_SHA,local_dir=str(target))
    source=Path(output)
    if source.resolve()!=path.resolve() or not allowed_existing(path,WHISPER_EXPECTED_SHA256):
        raise RuntimeError("WHISPER_SHA256_MISMATCH")
    evidence={"repo_id":WHISPER_REPO,"revision":WHISPER_SHA,
              "filename":WHISPER_FILENAME,"sha256":WHISPER_EXPECTED_SHA256,
              "size_bytes":path.stat().st_size,"state":"DOWNLOADED_AND_HASHED",
              "engine_executed":False,
              "checked_utc":datetime.now(timezone.utc).isoformat()}
    (target/"whisper_small_sha256.json").write_text(json.dumps(evidence,indent=2),
                                                     encoding="utf-8")
    return {"status":"SHA256_CHECKED","bytes":path.stat().st_size,"path":str(path)}

def semantic(root):
    p=subprocess.run(["ollama","list"],capture_output=True,text=True,timeout=30)
    if p.returncode!=0:raise RuntimeError("OLLAMA_LIST_NOT_AVAILABLE")
    names={line.split()[0] for line in p.stdout.splitlines()[1:] if line.split()}
    if EMBED_TAG in names:
        return {"status":"REUSED_OLLAMA_TAG","tag":EMBED_TAG}
    reserve(root,2_500_000_000)
    subprocess.run(["ollama","pull",EMBED_TAG],check=True,timeout=3600)
    return {"status":"PULLED_OLLAMA_TAG","tag":EMBED_TAG,
            "note":"Ollama controls checksum and local model cache"}

def _custom_reranker(root,snapshot_download,HfApi):
    model_id="Qwen/Qwen3-Reranker-0.6B"
    output=root/"brain"/"intelligence"/"reranker"/"Qwen3-Reranker-0.6B"
    # Generic HF snapshot with official commit revision and per-file SHA receipt.
    api=HfApi()
    meta=api.model_info(model_id,files_metadata=True)
    sha=getattr(meta,"sha",None)
    if not isinstance(sha,str) or len(sha)!=40:
        raise RuntimeError("RERANKER_REVISION_NOT_PINNED")
    card=getattr(meta,"card_data",None)
    license_name=getattr(card,"license",None)
    if license_name!="apache-2.0":
        raise RuntimeError("RERANKER_LICENSE_REVIEW_HOLD")
    patterns=["*.safetensors","*.json","*.txt","*.jinja","*.model","README.md","LICENSE"]
    remote=[x.rfilename for x in (meta.siblings or [])
            if x.rfilename and any(__import__("fnmatch").fnmatch(x.rfilename,p)
                                   for p in patterns)]
    if not remote or not any(n.endswith(".safetensors") for n in remote):
        raise RuntimeError("RERANKER_NO_OFFICIAL_WEIGHTS")
    dest=output/("revision_"+sha[:12])
    receipt=dest/"NOX_RERANKER_SHA256.json"
    if receipt.is_file():
        info=json.loads(receipt.read_text(encoding="utf-8"))
        if info.get("revision")==sha and set(info.get("files",{}))==set(remote):
            for name,dig in info["files"].items():
                if digest(dest/name)!=dig:raise RuntimeError("RERANKER_LOCAL_HASH_CONFLICT")
            return {"status":"REUSED_SHA256","files":len(remote),"path":str(dest)}
        raise RuntimeError("RERANKER_RECEIPT_MISMATCH")
    reserve(root,2_500_000_000)
    dest.mkdir(parents=True,exist_ok=True)
    snapshot_download(repo_id=model_id,revision=sha,
                      local_dir=str(dest),allow_patterns=patterns,max_workers=3)
    hashes={}
    for name in remote:
        file=dest/name
        if not file.is_file() or file.is_symlink():
            raise RuntimeError("RERANKER_MISSING_FILE "+name)
        hashes[name]=digest(file)
    with receipt.open("x",encoding="utf-8") as f:
        json.dump({"source":model_id,"revision":sha,"state":"SHA256_CHECKED",
                   "files":hashes,"inference_tested":False},f,indent=2)
    return {"status":"SHA256_CHECKED","files":len(remote),"path":str(dest)}

def voices(root,source,HfApi,snapshot_download):
    from download_nox_voice_max import read_manifest, model_download
    manifest=read_manifest(source/"NOX_VOICE_MAX_MODELS_MANIFEST_V1.json")
    chosen=set(VOICE_IDS+VOICE_OPTIONAL)
    voice_root=root/"brain"/"voice"
    results=[]
    for item in manifest["models"]:
        if item["id"] not in chosen:
            continue
        model_download(item,voice_root,False,
                       manifest["voice_extra_budget_gb"],
                       manifest["minimum_free_disk_gb"])
        results.append(item["id"])
    return {"status":"MODEL_FILES_ONLY","selected_ids":results,
            "voice_inference_tested":False}

def engine_sources(root):
    out=root/"brain"/"engine_sources"/"stage1"
    out.mkdir(parents=True,exist_ok=True)
    result=[]
    for name,url in SOURCES:
        target=out/name
        if target.exists():
            if (target/".git").is_dir():
                p=subprocess.run(["git","-C",str(target),"rev-parse","HEAD"],
                                 capture_output=True,text=True,timeout=20,check=True)
                result.append({"engine":name,"status":"REUSE_GIT_SOURCE",
                               "commit":p.stdout.strip()})
                continue
            raise RuntimeError("ENGINE_SOURCE_UNVERIFIED_EXISTS "+name)
        reserve(root,500_000_000)
        subprocess.run(["git","clone","--depth","1",url,str(target)],
                       check=True,timeout=300)
        p=subprocess.run(["git","-C",str(target),"rev-parse","HEAD"],
                         capture_output=True,text=True,timeout=20,check=True)
        result.append({"engine":name,"status":"SOURCE_ONLY_NOT_INSTALLED",
                       "commit":p.stdout.strip()})
    return result

def run(root,source,run_optional=True):
    root=Path(root).resolve()
    source=Path(source).resolve()
    if not (root/"brain").is_dir():
        raise RuntimeError("NOX_EXISTING_BRAIN_MISSING")
    if not (source/"nox_prime_download_five_v1.py").is_file():
        raise RuntimeError("NOX_SCRIPT_SET_MISSING")
    import huggingface_hub
    results={}
    failures=[]
    event(root,"START","Stage1 six download groups, originals kept",0)
    def group(i,name,work):
        event(root,"RUNNING",name+" starts",i-1)
        try:
            result=work()
            results[name]=result
            event(root,"SAVED",name+" source files downloaded or verified",i)
        except Exception as exc:
            message=type(exc).__name__+": "+str(exc)[:170]
            failures.append({"stage":name,"reason":message})
            event(root,"HOLD",name+" "+message[:110],i-1)
    group(1,STAGES[0],lambda:download_five(root))
    group(2,STAGES[1],lambda:semantic(root))
    group(3,STAGES[2],lambda:_custom_reranker(root,
             huggingface_hub.snapshot_download,huggingface_hub.HfApi) if run_optional
          else {"status":"OPTIONAL_SKIPPED"})
    group(4,STAGES[3],lambda:whisper(root,huggingface_hub.hf_hub_download))
    group(5,STAGES[4],lambda:voices(root,source,huggingface_hub.HfApi,
                                   huggingface_hub.snapshot_download))
    group(6,STAGES[5],lambda:engine_sources(root))
    report={"schema":"NOX_PRIME_STAGE1_DOWNLOADS_V1",
            "timestamp_utc":datetime.now(timezone.utc).isoformat(),
            "completed_groups":len(results),"failed_groups":len(failures),
            "results":results,"holds":failures,
            "weights_trained":False,"s03_changed":False,
            "engines_installed":False,"deleted_originals":False,
            "next":"GPU student training only under compatible SAFE70 policy"}
    evidence=root/"brain"/"telemetry"/"stage1_download_summary.json"
    evidence.parent.mkdir(parents=True,exist_ok=True)
    tmp=evidence.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(tmp,evidence)
    event(root,"DONE" if not failures else "HOLD",
          ("All Stage1 download groups accepted" if not failures else
           str(len(failures))+" download group(s) blocked; no deletion"),6)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if not failures else 2

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT_DEFAULT)
    p.add_argument("--source",type=Path,default=Path(__file__).parent)
    p.add_argument("--skip-optional-reranker",action="store_true")
    args=p.parse_args()
    try:sys.exit(run(args.root,args.source,not args.skip_optional_reranker))
    except Exception as e:
        print("NOX_STAGE1_FATAL_HOLD",type(e).__name__,str(e),file=sys.stderr)
        sys.exit(1)
