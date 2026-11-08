"""NOX PRIME V2 teacher absorption, ONE sequential resident GPU model at a time.

It queries each installed *compatible* language/code teacher on a fixed public
curriculum, with per-row source/digest. This is DATA PREPARATION only, NOT
neural weight merging, student training, readiness, or proven task competence.
Non-text modalities require their own student architectures.

Native OneHost/S03 and 5 PersonaID stores are never read or written here.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,time,uuid
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen

from nox_prime_absorption_registry_v1 import inventory,store
from nox_prime_progress_v1 import log_event
from nox_prime_resource_advisor_v1 import trainer_active
from nox_prime_distill_v1 import TASKS

OLLAMA="http://127.0.0.1:11434"
MAX_MODELS=40
MAX_INPUT=1800
MAX_ANSWER=8000
MAX_MODEL_DISK_BYTES=6_500_000_000

def _call(endpoint,data,timeout):
    req=Request(OLLAMA+endpoint,data=json.dumps(data,ensure_ascii=False).encode('utf-8'),
        method="POST",headers={"Content-Type":"application/json"})
    with urlopen(req,timeout=timeout) as resp:
        obj=json.loads(resp.read(1_200_000))
    if not isinstance(obj,dict):raise ValueError("INVALID_LOCAL_OLLAMA_RESPONSE")
    return obj

def _teacher_text(model,prompt):
    payload={"model":model,"stream":False,"think":False,
        "keep_alive":"2m",
        "options":{"num_predict":420,"temperature":0.15,"num_ctx":2048},
        "messages":[{"role":"system","content":
            "You are a technical model evaluated as one possible NOX PRIME donor. "
            "Use source-aware and technically accurate reasoning; say when a claim "
            "is uncertain. Do not claim to have run code, downloaded weights, "
            "made changes, or achieved consciousness. No personal data."},
            {"role":"user","content":prompt[:MAX_INPUT]}]}
    response=_call("/api/chat",payload,timeout=150)
    answer=(response.get("message") or {}).get("content")
    if not isinstance(answer,str) or not 60<=len(answer.strip())<=MAX_ANSWER:
        raise RuntimeError("TEACHER_EMPTY_OR_OVERSIZE_ANSWER")
    return answer.strip(), {
        "eval_count":response.get("eval_count") if type(response.get("eval_count"))==int else None,
        "eval_duration_ns":response.get("eval_duration") if type(response.get("eval_duration"))==int else None
    }

def _unload(name):
    try:
        # Only release selected teacher model, do not touch unrelated processes.
        _call("/api/generate",{"model":name,"prompt":"","stream":False,
             "keep_alive":0,"options":{"num_predict":1}},timeout=30)
    except (OSError,ValueError,TimeoutError):
        pass

def _sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for data in iter(lambda:f.read(1048576),b""):
            h.update(data)
    return h.hexdigest()

def run(root,questions_per_model=3,max_models=40):
    root=Path(root).resolve()
    if not (root/"brain").is_dir():raise RuntimeError("NOX_BRAIN_NOT_FOUND")
    if not 1<=questions_per_model<=12:raise ValueError("QUESTIONS_OUT_OF_RANGE")
    if not 1<=max_models<=MAX_MODELS:raise ValueError("MODEL_CAP_OUT_OF_RANGE")
    if trainer_active() is not False:
        raise RuntimeError("GPU_ALREADY_TRAINING_OR_UNKNOWN")
    state=inventory(root)
    registry=store(root,state)
    eligible=[x for x in state["models"] if
        x["gate"]=="ELIGIBLE_FOR_SAFE_PROBE" and x["digest"] and
        (x["size_bytes"] is not None and x["size_bytes"]<=MAX_MODEL_DISK_BYTES)]
    excluded=[{"name":m["name"],"model_type":m["model_type"],"gate":m["gate"],
               "reason":"requires modality-specific student or hardware budget"}
               for m in state["models"] if m not in eligible]
    # Stage-1 fast lane: prioritize measured prime/coder teachers first.
    # Other installed models stay cataloged for later competence-specific runs.
    priority={"qwen3:8b":0,"qwen2.5-coder:7b":1}
    eligible.sort(key=lambda row:(priority.get(row["name"],2),row["name"]))
    eligible=eligible[:max_models]
    if not eligible:raise RuntimeError("NO_ELIGIBLE_LOCAL_TEXT_TEACHERS")
    # Distill different examples from a stable curriculum across donor types.
    jobs=[]
    for donor in eligible:
        available_tasks=[(kind,prompt) for kind,prompt in TASKS if
           donor["model_type"]=="code_llm" and kind in ("code","reason","safety")
           or donor["model_type"]=="text_llm" and kind!="code"]
        if not available_tasks:
            excluded.append({"name":donor["name"],"reason":"NO_COMPATIBLE_CURRICULUM"})
            continue
        for k,(kind,prompt) in enumerate(available_tasks[:questions_per_model]):
            jobs.append((donor,kind,prompt,k))
    if not jobs:raise RuntimeError("NO_SAFE_JOBS")
    outdir=root/"brain"/"intelligence"/"absorption"
    outdir.mkdir(parents=True,exist_ok=True)
    nonce=uuid.uuid4().hex[:10]
    temp=outdir/("multi_teacher_"+nonce+".jsonl.partial")
    destination=outdir/("multi_teacher_"+nonce+".jsonl")
    manifest=outdir/("multi_teacher_"+nonce+".manifest.json")
    completed=0
    failures=[]
    teachers=[]
    current_teacher=None
    log_event(root,"TEACHER_DISTILL","START",
         "Sequential local text/coder teacher distillation started",actual=0,total=len(jobs))
    try:
        with temp.open("x",encoding="utf-8",newline="\n") as f:
            for donor,kind,prompt,k in jobs:
                model=donor["name"]
                if trainer_active() is not False:
                    raise RuntimeError("GPU_TRAINER_APPEARED_DURING_TEACHER_RUN")
                if current_teacher!=model:
                    if current_teacher:_unload(current_teacher)
                    current_teacher=model
                try:
                    answer,usage=_teacher_text(model,prompt)
                    record={"messages":[{"role":"user","content":prompt},
                            {"role":"assistant","content":answer}],
                            "category":kind,"source_model":model,
                            "source_model_digest":donor["digest"],
                            "teacher_prompt_sha256":hashlib.sha256(
                                prompt.encode("utf-8")).hexdigest(),
                            "license_and_rights":"OWNER_MUST_REVIEW_BEFORE_STUDENT_TRAINING",
                            "human_verified":False,"model_generated":True,
                            "student_weights_trained":False,
                            "performance":usage}
                    f.write(json.dumps(record,ensure_ascii=False)+"\n")
                    f.flush();os.fsync(f.fileno())
                    completed+=1
                    if model not in teachers:teachers.append(model)
                    log_event(root,"TEACHER_DISTILL","RUNNING",
                        "Captured actual response from "+model,
                        actual=completed,total=len(jobs))
                except (OSError,ValueError,RuntimeError,TimeoutError) as ex:
                    failures.append({"model":model,"task":kind,
                                     "reason":type(ex).__name__})
                    log_event(root,"TEACHER_DISTILL","HOLD",
                        "Teacher "+model+" failed "+type(ex).__name__,
                        actual=completed,total=len(jobs))
        if current_teacher:
            _unload(current_teacher)
            current_teacher=None
        if completed<1:raise RuntimeError("NO_TEACHER_EXAMPLES_CAPTURED")
        # Preserve partial if all jobs failed; otherwise materialize one immutable corpus.
        os.replace(temp,destination)
        sha=_sha(destination)
        report={"schema":"NOX_MULTI_TEACHER_CANDIDATES_V2",
                "created_utc":datetime.now(timezone.utc).isoformat(),
                "source_registry":registry["path"],
                "registry_sha256":registry["sha256"],
                "source_models":teachers,"examples":completed,"jobs":len(jobs),
                "failed_or_held":failures,"excluded_models":excluded,
                "student_architecture":"NOT_YET_TRAINED",
                "needs_train_data_approval":True,
                "needs_independent_eval":True,
                "dataset_sha256":sha,"dataset_path":str(destination),
                "original_models_retained":True,
                "s03_modified":False,"student_weights_modified":False,
                "status":"DISTILLATION_DATA_READY_NOT_NEURAL_MERGE"}
        with manifest.open("x",encoding="utf-8") as f:
            json.dump(report,f,ensure_ascii=False,indent=2)
        log_event(root,"TEACHER_DISTILL","SAVED",
            "Source-hashed multi-teacher data prepared; student training NOT done",
            actual=completed,total=len(jobs))
        return {"dataset":str(destination),"sha256":sha,
                "models_scanned":state["installed_total"],
                "models_used":len(teachers),"examples":completed,
                "skipped":len(excluded),"failed":len(failures),
                "state":report["status"]}
    except BaseException as exc:
        if current_teacher:
            _unload(current_teacher)
        log_event(root,"TEACHER_DISTILL","HOLD",
                  "Multi-teacher candidate preparation HOLD: "+type(exc).__name__,
                  actual=completed,total=len(jobs))
        raise

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path(r"C:\NOX_HELION\NOX_NEW"))
    p.add_argument("--questions-per-model",type=int,default=3)
    p.add_argument("--max-models",type=int,default=40)
    a=p.parse_args()
    print(json.dumps(run(a.root,a.questions_per_model,a.max_models),
                     ensure_ascii=False,indent=2))
