"""NOX PRIME: read-only model, adapter, and checkpoint audit for safe training.

Lists exact Ollama model identities (manifest digests), detects only exact
duplicates, inspects existing LoRA base_model_name_or_path, source SHA receipts
and experimental affect network, and returns a non-destructive cleanup PLAN.
NO model, checkpoint, S03, HF file, or Ollama tag is removed.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.request import urlopen

PROTECTED={"qwen3:8b","qwen2.5-coder:7b","qwen3-embedding:0.6b",
           "nox-helion:latest","nox:latest"}
MAX_FILES=2500
HFS_ROOT="brain/models/NOX_PRIME_V5"
ADAPTER_ROOT="brain/intelligence/adapters"

def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(4*1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def _get(url):
    with urlopen(url,timeout=8) as resp:
        data=json.loads(resp.read(3_000_000))
    if not isinstance(data,dict):raise ValueError("BAD_OLLAMA_JSON")
    return data

def model_catalog(root,provider=_get):
    models=provider("http://127.0.0.1:11434/api/tags").get("models")
    if not isinstance(models,list):raise RuntimeError("OLLAMA_NOT_AVAILABLE")
    result=[]
    for m in models:
        if not isinstance(m,dict):continue
        name=m.get("name") or m.get("model")
        sha=m.get("digest")
        if not isinstance(name,str) or not isinstance(sha,str):continue
        sha=sha.removeprefix("sha256:").lower()
        if not re.fullmatch("[a-f0-9]{64}",sha):continue
        result.append({"tag":name,"digest":sha,"size_bytes":m.get("size"),
                       "specialization":("embedding" if "embed" in name.lower() else
                                         "code" if "coder" in name.lower() else
                                         "primary" if name=="qwen3:8b" else "other")})
    return sorted(result,key=lambda x:x["tag"])

def duplicates(rows):
    buckets=defaultdict(list)
    for row in rows:buckets[row["digest"]].append(row["tag"])
    proposed=[]
    for digest,names in buckets.items():
        if len(names)<2:continue
        sorted_names=sorted(names)
        keeper=next((n for n in sorted_names if n in PROTECTED or n.startswith("nox-")),sorted_names[0])
        for tag in sorted_names:
            if tag==keeper or tag in PROTECTED or tag.startswith("nox-"):continue
            proposed.append({"tag":tag,"same_digest_as":keeper,
                             "digest":digest,
                             "safety":"CANDIDATE_NOT_DELETED",
                             "note":"Ollama often shares blobs; deleting alias might not free bytes"})
    return proposed

def existing_adapters(root):
    root=Path(root)
    base=root/ADAPTER_ROOT
    result=[]
    if not base.is_dir():return result
    count=0
    for p in base.rglob("adapter_config.json"):
        if count>=MAX_FILES:break
        count+=1
        if p.is_symlink() or any(x.is_symlink() for x in p.parents if x!=base):
            continue
        try:
            cfg=json.loads(p.read_text(encoding="utf-8"))
            target=p.parent/"adapter_model.safetensors"
            if not target.is_file():continue
            step=None
            match=re.search(r"step-(\d+)",str(p.parent))
            if match:step=int(match.group(1))
            result.append({"path":str(p.parent.relative_to(root)),
                           "base_model":str(cfg.get("base_model_name_or_path","UNKNOWN"))[:120],
                           "step":step,"bytes":target.stat().st_size,
                           "checksum":"UNVERIFIED_LARGE" if target.stat().st_size>134_217_728
                                       else sha_file(target),
                           "keep":True,"loaded_into_prime":False})
        except (OSError,ValueError,TypeError):pass
    return sorted(result,key=lambda x:(x["step"] or 0),reverse=True)[:180]

def existing_hf(root):
    base=Path(root)/HFS_ROOT
    out=[]
    if not base.is_dir():return out
    for p in list(base.rglob("NOX_WEIGHTS_SHA256.json"))[:300]:
        if p.is_symlink():continue
        try:
            record=json.loads(p.read_text(encoding="utf-8"))
            names=record.get("sha256",{})
            if not isinstance(names,dict) or not names:continue
            integrity=all((p.parent/n).is_file() and
                sha_file(p.parent/n)==v for n,v in names.items())
            out.append({"model":record.get("model_id"),"revision":record.get("revision"),
                        "bytes":record.get("bytes"),"weights_verified":integrity,
                        "path":str(p.parent.relative_to(root)),
                        "keep":True,"trained":False})
        except (OSError,ValueError,TypeError):pass
    return out

def affect_status(root):
    p=Path(root)/"brain"/"intelligence"/"soul_stage1"/"CURRENT_VERIFIED.json"
    try:
        o=json.loads(p.read_text(encoding="utf-8"))
        weights=Path(o["model_path"]).resolve()
        safe=(Path(root).resolve()/"brain"/"intelligence"/"soul_stage1").resolve()
        if safe not in weights.parents:raise ValueError("OUTSIDE_SOUL")
        return {"scope":"EN_ONLY","claimed_f1":o.get("test_micro_f1"),
                "weights_sha256_matches":weights.is_file() and
                sha_file(weights)==o.get("model_sha256"),
                "ready_for_8b_direct_merge":False}
    except (OSError,ValueError,KeyError,TypeError):
        return {"scope":"EN_ONLY","available":False}

def audit(root,provider=_get):
    root=Path(root).resolve()
    if not (root/"brain").is_dir():raise RuntimeError("NOX_BRAIN_NOT_FOUND")
    models=model_catalog(root,provider)
    adapters=existing_adapters(root)
    hf=existing_hf(root)
    report={"schema":"NOX_PRIME_WEIGHT_AUDIT_V1",
            "created_utc":datetime.now(timezone.utc).isoformat(),
            "ollama_models":models,"ollama_tag_count":len(models),
            "distinct_ollama_digests":len({r["digest"] for r in models}),
            "exact_duplicate_tags_plan_only":duplicates(models),
            "lora_adapters":adapters,
            "lora_checkpoints_found":len(adapters),
            "trainable_hf_bases":hf,"soul_affect":affect_status(root),
            "retirement_policy":"KEEP_ALL_UNIQUE_SKILLS; DELETE_ONLY_AFTER_INDEPENDENT_BENCHMARK_AND_BACKUP",
            "immediately_deleted":[],"native_s03_changed":False,
            "target":{"resident":"qwen3:8b","existing_gpu_student":"Qwen2.5-0.5B-Instruct",
                      "next_trainable_student":"Qwen3-0.6B"},
            "warning":"Existing 0.5B adapters cannot be loaded directly into Qwen3-0.6B or Qwen3:8B."}
    path=root/"brain"/"telemetry"/"weights_audit"
    path.mkdir(parents=True,exist_ok=True)
    destination=path/("audit_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")+".json")
    with destination.open("x",encoding="utf-8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
    return {"report":str(destination),"ollama_tags":len(models),
            "unique_ollama_digests":report["distinct_ollama_digests"],
            "exact_duplicate_aliases":len(report["exact_duplicate_tags_plan_only"]),
            "adapter_checkpoints":len(adapters),"HF_bases":len(hf),
            "SOUL_EN_verified":report["soul_affect"].get("weights_sha256_matches",False),
            "deleted":0}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path(r"C:\NOX_HELION\NOX_NEW"))
    opts=p.parse_args()
    print(json.dumps(audit(opts.root),ensure_ascii=False,indent=2))
