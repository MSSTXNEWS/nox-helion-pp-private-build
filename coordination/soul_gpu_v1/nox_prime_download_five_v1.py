"""NOX PRIME: five official trainable base/specialist weights in a versioned NOX folder.

This is a DOWNLOAD + SHA256 verifier, NOT a merge, training, or student
acceptance. It does not run downloaded model code, delete donor originals,
touch S03, invoke Ollama training, or alter any existing checkpoints.

Order: fastest student 0.6B first, then 1.7B/4B, coder, multimodal.
Official sources only; HEAD commit pinned for each model, Apache-2.0.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
from datetime import datetime, timezone
from fnmatch import fnmatch

MODELS = (
    ("Qwen3-0.6B", "Qwen/Qwen3-0.6B", 2_000_000_000, "SOUL_BASE_0.6B"),
    ("Qwen3-1.7B", "Qwen/Qwen3-1.7B", 5_000_000_000, "SOUL_NEXT_1.7B"),
    ("Qwen3-4B", "Qwen/Qwen3-4B", 10_000_000_000, "SOUL_TARGET_4B"),
    ("Qwen2.5-Coder-1.5B-Instruct", "Qwen/Qwen2.5-Coder-1.5B-Instruct",
     4_000_000_000, "CODE_STUDENT"),
    ("Qwen3.5-2B", "Qwen/Qwen3.5-2B", 6_000_000_000, "MULTIMODAL_EXPERT"),
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PATTERNS = (
    "*.safetensors", "*.json", "*.txt", "*.jinja", "*.model",
    "*.tiktoken", "LICENSE", "README.md",
)
MAX_NEW_BYTES = 50_000_000_000
FREE_RESERVE = 60_000_000_000

def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4_194_304), b""):
            h.update(block)
    return h.hexdigest()

def matches(name):
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or "\\" in name:
        return False
    return any(fnmatch(str(p),pat) or fnmatch(p.name,pat) for pat in PATTERNS)

def event(root, status, detail, index):
    try:
        from nox_prime_progress_v1 import log_event
        log_event(root, "DOWNLOAD", status, detail, actual=index,
                  total=len(MODELS))
    except (ImportError, OSError, ValueError, TypeError) as e:
        print("DASHBOARD_EVENT_HOLD",type(e).__name__,flush=True)

def official_metadata(api, model_id):
    info = api.model_info(model_id, revision="main", files_metadata=True)
    revision = getattr(info,"sha",None)
    if not isinstance(revision,str) or not SHA_RE.fullmatch(revision):
        raise RuntimeError("UNPINNED_HF_MODEL_REVISION "+model_id)
    if getattr(info,"id",None)!=model_id:
        raise RuntimeError("INVALID_HF_MODEL_ID "+model_id)
    card = getattr(info,"card_data",None)
    license_name = getattr(card,"license",None)
    if isinstance(card,dict):
        license_name = license_name or card.get("license")
    if license_name != "apache-2.0":
        raise RuntimeError("LICENSE_REVIEW_HOLD "+model_id+" "+str(license_name))
    remote = {}
    for item in getattr(info,"siblings",()) or ():
        name = getattr(item,"rfilename",None)
        if not isinstance(name,str) or not matches(name):
            continue
        size = getattr(item,"size",None)
        if size is not None and (type(size)!=int or size<0):
            raise RuntimeError("UPSTREAM_FILE_SIZE_INVALID "+name)
        remote[name]=size
    if not remote or not any(n.endswith(".safetensors") for n in remote):
        raise RuntimeError("NO_OFFICIAL_TRAINABLE_WEIGHTS "+model_id)
    return revision,remote

def check_existing(folder,receipt_path,remote,revision):
    if not receipt_path.is_file():
        return False
    receipt=json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("revision")!=revision or receipt.get("state")!="SHA256_CHECKED":
        raise RuntimeError("CONFLICTING_EXISTING_WEIGHT_RECEIPT "+str(folder))
    hashes=receipt.get("sha256",{})
    if set(hashes)!=set(remote):
        raise RuntimeError("MODEL_FILE_MANIFEST_CHANGED "+str(folder))
    for name,expected_size in remote.items():
        path=folder/name
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("LOCAL_WEIGHT_MISSING "+str(path))
        if expected_size is not None and path.stat().st_size!=expected_size:
            raise RuntimeError("LOCAL_WEIGHT_SIZE_MISMATCH "+str(path))
        if digest(path)!=hashes[name]:
            raise RuntimeError("LOCAL_WEIGHT_HASH_MISMATCH "+str(path))
    return True

def download(root,max_new_gb=50,only=None):
    from huggingface_hub import HfApi,snapshot_download
    root=Path(root).resolve()
    if not (root/"brain").is_dir():
        raise RuntimeError("EXISTING_NOX_BRAIN_NOT_FOUND "+str(root))
    output=root/"brain"/"models"/"NOX_PRIME_V5"
    if output.exists() and output.is_symlink():
        raise RuntimeError("MODEL_ROOT_SYMLINK_DENIED")
    output.mkdir(parents=True,exist_ok=True)
    selected=tuple(x for x in MODELS if not only or x[0] in set(only))
    if not selected:raise ValueError("NO_MODELS_SELECTED")
    if only and len(selected)!=len(set(only)):
        raise ValueError("UNKNOWN_MODEL_SELECTION")
    api=HfApi()
    new_budget=0
    results=[]
    event(root,"START","Discover official model revisions and reuse existing files",0)
    for i,(label,model_id,expected_max,role) in enumerate(selected,1):
        print(f"\nNOX [{i}/{len(MODELS)}] {model_id} -> {role}",flush=True)
        revision,remote=official_metadata(api,model_id)
        dest=output/label/("revision_"+revision[:12])
        receipt=dest/"NOX_WEIGHTS_SHA256.json"
        if check_existing(dest,receipt,remote,revision):
            print("SKIP VERIFIED",model_id,revision,flush=True)
            event(root,"SAVED","Reusing verified "+label,i)
            results.append({"model":model_id,"state":"REUSED_SHA256",
                            "revision":revision,"path":str(dest)})
            continue
        # Existing unverified files are preserved; snapshot_download resumes
        # official missing content at exactly the pinned revision.
        known_remote_bytes=sum(v for v in remote.values() if type(v)==int)
        estimate=max(known_remote_bytes,expected_max)
        if new_budget+estimate>min(MAX_NEW_BYTES,int(max_new_gb*1e9)):
            event(root,"HOLD","Model download would exceed 50GB package allowance",i-1)
            raise RuntimeError("MODEL_DOWNLOAD_BUDGET_HOLD")
        free=shutil.disk_usage(root).free
        if free < FREE_RESERVE+int(estimate*1.1):
            event(root,"HOLD","Not enough free disk while preserving 60GB reserve",i-1)
            raise RuntimeError(f"DISK_RESERVE_HOLD free={free/1e9:.1f}GB required={(FREE_RESERVE+int(estimate*1.1))/1e9:.1f}GB")
        dest.mkdir(parents=True,exist_ok=True)
        event(root,"RUNNING","Fetching SHA-pinned "+label,i-1)
        print("OFFICIAL SOURCE",model_id,"REV",revision,"license=apache-2.0",
              "budget_estimate_gb",round(estimate/1e9,2),flush=True)
        snapshot_download(repo_id=model_id,revision=revision,
                          local_dir=str(dest),allow_patterns=list(PATTERNS),
                          max_workers=3)
        # SHA every downloaded original tensor/file, never label a partial set
        # as ready. The file receipt is written only after complete verification.
        hashes={}
        size_bytes=0
        for name,expected_size in remote.items():
            p=dest/name
            if not p.is_file() or p.is_symlink():
                raise RuntimeError("DOWNLOAD_INCOMPLETE "+str(p))
            size=p.stat().st_size
            if expected_size is not None and size!=expected_size:
                raise RuntimeError("DOWNLOAD_SIZE_MISMATCH "+str(p))
            size_bytes+=size
            hashes[name]=digest(p)
        if size_bytes>expected_max*1.25:
            raise RuntimeError("UPSTREAM_MODEL_UNEXPECTED_OVERSIZE "+model_id)
        document={
          "schema":"NOX_PRIME_OFFICIAL_WEIGHTS_V1",
          "model_id":model_id,"role":role,"revision":revision,
          "license":"apache-2.0","sha256":hashes,
          "bytes":size_bytes,"state":"SHA256_CHECKED",
          "created_utc":datetime.now(timezone.utc).isoformat(),
          "inference_tested":False,"training_accepted":False,
          "transferred_competencies":[],"original_models_deleted":False
        }
        if receipt.exists():
            raise RuntimeError("EXISTING_UNVERIFIED_RECEIPT_CONFLICT")
        with receipt.open("x",encoding="utf-8") as f:
            json.dump(document,f,ensure_ascii=False,indent=2)
        new_budget+=size_bytes
        event(root,"SAVED","Verified "+label+" official weights and local SHA256",i)
        print("SHA256 VERIFIED",model_id,"bytes",size_bytes,flush=True)
        results.append({"model":model_id,"state":"SHA256_CHECKED",
                        "revision":revision,"path":str(dest)})
    event(root,"DONE","NOX selected trainable bases downloaded or verified",len(selected))
    return {"completed":len(results),"new_bytes":new_budget,
            "root":str(output),"models":results,
            "important":"Downloads only; all five remain separate until compatible student training and evaluation."}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path(r"C:\NOX_HELION\NOX_NEW"))
    p.add_argument("--budget-gb",type=float,default=50)
    p.add_argument("--only",action="append",default=[],
                   help="Download ONLY selected official model IDs; e.g. Qwen3-0.6B")
    args=p.parse_args()
    try:
        result=download(args.root,args.budget_gb,args.only)
        print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    except Exception as ex:
        event(args.root,"HOLD",type(ex).__name__+" "+str(ex)[:110],0)
        print("NOX FIVE MODEL DOWNLOAD HOLD",type(ex).__name__,str(ex),
              file=sys.stderr,flush=True)
        raise SystemExit(1)
