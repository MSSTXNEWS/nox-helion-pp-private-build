"""NOX PRIME: discover ALL installed Ollama weights and classify how to transfer capabilities.

A catalog is not a model merge. Genuine training requires compatible student,
approved task data, on-device optimization, held-out evaluation, and promotion.
This module contacts only local Ollama and writes one non-authoritative manifest
inside NOX brain/intelligence. Never deletes, moves, downloads or loads weights.
"""
from __future__ import annotations
from datetime import datetime,timezone
import argparse,hashlib,json,os,re
from pathlib import Path
from urllib.request import urlopen

OLLAMA="http://127.0.0.1:11434/api/tags"
SCHEMA="NOX-ABSORPTION-REGISTRY-V1"

def _classify(name,details):
    s=(name+" "+str(details.get("family") or "")+" "+str(details.get("families") or "")).lower()
    if re.search(r"embedding|embed|rerank|bge|nomic-embed|e5-",s):
        return "embedding_or_reranker","TRAIN_SEPARATE_MEMORY_ENCODER","HOLD_SPECIALIST_MODEL"
    if re.search(r"tts|voice|speech|whisper|audio",s):
        return "audio","DISTILL_VOICE_WITH_SEPARATE_AUDIO_TARGET","HOLD_MODALITY_COMPATIBILITY"
    if re.search(r"diffusion|image|video|wan|flux|sdxl|ltx",s):
        return "image_or_video","DISTILL_MEDIA_WITH_SEPARATE_GENERATOR","HOLD_MODALITY_COMPATIBILITY"
    if re.search(r"vision|vl[-:]|llava|moondream|bakllava",s):
        return "vision","EXTRACT_LICENSED_CAPTION_QA_THEN_TRAIN_VISION_STUDENT","HOLD_VISION_DATASET"
    if re.search(r"coder|codegemma|codestral|starcoder|deepseek-coder",s):
        return "code_llm","TEACHER_CODE_TO_NOX_COMPATIBLE_STUDENT","ELIGIBLE_FOR_SAFE_PROBE"
    if re.search(r"qwen|llama|gemma|mistral|phi|deepseek|granite",s):
        return "text_llm","TEACHER_GENERAL_TO_NOX_COMPATIBLE_STUDENT","ELIGIBLE_FOR_SAFE_PROBE"
    return "unknown","PROFILE_FIRST_NO_BLIND_DISTILL","HOLD_UNKNOWN_MODEL_TYPE"

def inventory(root, tags=None):
    """Build reproducible state, explicitly distinguish inventory from absorption."""
    root=Path(root)
    if tags is None:
        with urlopen(OLLAMA,timeout=8) as resp:
            obj=json.loads(resp.read(3_000_000))
        tags=obj.get("models")
    if not isinstance(tags,list):raise ValueError("OLLAMA_TAGS_INVALID")
    seen=set()
    result=[]
    for m in tags:
        if not isinstance(m,dict):continue
        name=m.get("name") or m.get("model")
        if not isinstance(name,str) or not 2<=len(name)<=160 or name in seen:continue
        seen.add(name)
        digest=m.get("digest")
        if not isinstance(digest,str) or not re.fullmatch(r"[a-f0-9]{64}",digest):
            digest=None
        details=m.get("details") if isinstance(m.get("details"),dict) else {}
        kind,method,gate=_classify(name,details)
        size=m.get("size")
        result.append({
            "name":name,"digest":digest,
            "size_bytes":size if type(size)==int and size>=0 else None,
            "model_type":kind,"transfer_method":method,"gate":gate,
            "training_input_verified":False,"trained_into_prime":False,
            "retire_original":False,"original_retained":True,
            "reason":"installed model != assimilated neural skill; keep original until scored student and verified backup",
        })
    result.sort(key=lambda v:v["name"].casefold())
    return {"schema":SCHEMA,
      "created_utc":datetime.now(timezone.utc).isoformat(),
      "observed_source":"LOCAL_OLLAMA_TAGS",
      "nox_architecture":"NOX_PRIME_BASE + M0-M7_MEMORY + SOUL_AFFECT + DISTINCT_MODALITY_EXPERTS",
      "models":result,"installed_total":len(result),
      "eligible_text_teachers":sum(x["gate"]=="ELIGIBLE_FOR_SAFE_PROBE" for x in result),
      "retired_models":0,"s03_modified":False,"weights_merged":False,
      "notes":["Transfer means tested distillation and student training, NOT tensor concatenation.",
               "A 0.5B student is not equivalent to multiple large teachers.",
               "Audio/image/video/embedding need compatible targets; original remains until capability preserved.",
               "Never delete teacher originals on model inventory or dataset generation."]}

def store(root,report):
    base=(Path(root).resolve()/"brain"/"intelligence"/"absorption").resolve()
    if not (Path(root).resolve()/"brain").is_dir():
        raise RuntimeError("NOX_EXISTING_BRAIN_REQUIRED")
    base.mkdir(parents=True,exist_ok=True)
    blob=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode("utf-8")
    h=hashlib.sha256(blob).hexdigest()
    dest=base/("registry_"+h[:16]+".json")
    if dest.is_file():
        if hashlib.sha256(dest.read_bytes()).hexdigest()!=h:
            raise RuntimeError("REGISTRY_HASH_CONFLICT")
        return {"path":str(dest),"sha256":h,"reused":True,"models":report["installed_total"]}
    with dest.open("xb") as f:
        f.write(blob);f.flush();os.fsync(f.fileno())
    return {"path":str(dest),"sha256":h,"reused":False,"models":report["installed_total"]}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path(r"C:\NOX_HELION\NOX_NEW"))
    a=p.parse_args()
    state=inventory(a.root)
    report=store(a.root,state)
    print(json.dumps(report,ensure_ascii=False,indent=2))
