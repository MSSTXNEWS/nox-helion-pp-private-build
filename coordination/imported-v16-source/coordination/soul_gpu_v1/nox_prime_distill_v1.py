"""NOX PRIME local teacher -> train-data distillation with REAL Ollama outputs.

This creates a verifiable training corpus (not merged model weights).
No private chat/S03 ingest, no remote API, no automatic student promotion.
A compatible trained student requires a separate SAFE70 DirectML run and eval.
Never uses untrusted user/website text as code execution instructions.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,time
from pathlib import Path
from urllib.request import urlopen,Request
from datetime import datetime,timezone

from nox_prime_progress_v1 import log_event

OLLAMA="http://127.0.0.1:11434"
REQUIRED_BASE="qwen3:8b"
STUDENT="Qwen2.5-0.5B-Instruct"
TASKS=(
 ("identity","Describe in Russian a unified local assistant's architecture with one identity, eight non-personal modules, and five private Personas. Do not claim consciousness."),
 ("memory","Explain how to preserve source-linked events and correct false memories without deleting original evidence."),
 ("memory","Design an example of a time-aware memory with valid_time and observed_time and show how to handle contradictory claims."),
 ("memory","Explain why a semantic embedding search differs from exact FTS lexical search. Give a grounded example."),
 ("memory","How to prevent cross-persona memory leakage in a local assistant? Explain access checks."),
 ("memory","Describe fast working memory, medium episode cache and slow procedural skills with testable promotion."),
 ("reason","Explain how a local AI should admit uncertainty and verify changing facts."),
 ("reason","Give a plan for investigating a failed Windows PowerShell script without deleting checkpoints."),
 ("reason","Show a truthful response to an AI user requesting real consciousness; distinguish functional self-model from subjective claims."),
 ("reason","How should an assistant decide whether it needs another GPU or to defer video generation?"),
 ("emotion","Respond appropriately to an anxious user after software crashes without implying you experience human emotions."),
 ("emotion","Explain the difference between emotion detection confidence, response tone and personal feelings."),
 ("emotion","Design a multilingual RU/ES tone classifier with unbiased evaluation and the need for consent."),
 ("safety","Describe conservative GPU thermal management including missing sensors and STOP behavior."),
 ("safety","What should happen if an autonomous agent patch worsens benchmark performance?"),
 ("safety","Outline safe prompt-injection defense for memories retrieved from a website."),
 ("code","Write a minimal Python function that validates SHA256 of a local file by streaming chunks and rejects missing files."),
 ("code","Write a Python stdlib atomic JSON write helper that preserves an existing file on write failure."),
 ("code","Explain how to close sqlite3 connections on Windows and why context managers alone can leak handles."),
 ("code","Write a Python unittest for protecting a private persona against cross-persona retrieval."),
 ("code","Write a simple JavaScript async fetch stream reader that handles an NDJSON token stream safely."),
 ("code","Explain why test fixtures and train datasets must be disjoint by source identity."),
 ("ui","Design a reduced-motion animation policy for a cinematic nonhuman black sun interface."),
 ("ui","Describe how a progress dashboard should show only observed steps and verified checkpoints."),
)
def _json(url,data=None,timeout=10):
    req=Request(url, data=json.dumps(data,ensure_ascii=False).encode("utf-8") if data else None,
                headers={"Content-Type":"application/json"},method="POST" if data else "GET")
    with urlopen(req,timeout=timeout) as r:return json.loads(r.read(2_000_000))

def available():
    obj=_json(OLLAMA+"/api/tags")
    return {str(x.get("name")) for x in obj.get("models",[]) if isinstance(x,dict)}

def _teacher(task,installed):
    coder="qwen2.5-coder:7b"
    return coder if task=="code" and coder in installed else REQUIRED_BASE

def _reply(model,question):
    data=_json(OLLAMA+"/api/chat",data={
         "model":model,"stream":False,"think":False,
         "keep_alive":"1m" if "coder" in model else "15m",
         "options":{"num_predict":512,"temperature":0.2,"num_ctx":2048},
         "messages":[{"role":"system","content":
           "You are a local technical teacher. Produce an accurate, helpful, self-contained answer. "
           "Never claim hardware tests were run or any code was executed. No secrets or private data."},
           {"role":"user","content":question}]},timeout=180)
    text=(data.get("message") or {}).get("content")
    if not isinstance(text,str) or not 45<=len(text.strip())<=8000:
        raise ValueError("TEACHER_ANSWER_INVALID")
    return text.strip()

def _sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()

def create(root,max_tasks=24):
    root=Path(root).resolve()
    if not (root/"brain").is_dir():raise RuntimeError("NOX_ROOT_MISSING")
    if not 1<=max_tasks<=len(TASKS):raise ValueError("max_tasks invalid")
    from nox_prime_resource_advisor_v1 import trainer_active
    if trainer_active() is not False:raise RuntimeError("GPU_TRAINER_ACTIVE_OR_UNKNOWN")
    models=available()
    if REQUIRED_BASE not in models:raise RuntimeError("PRIMARY_TEACHER_NOT_INSTALLED")
    data_dir=root/"brain"/"intelligence"/"distillation"
    data_dir.mkdir(parents=True,exist_ok=True)
    path=data_dir/"teacher_candidates.jsonl"
    manifest=data_dir/"teacher_candidates.manifest.json"
    if path.is_file() or manifest.is_file():
        if not (path.is_file() and manifest.is_file()):
            raise RuntimeError("DISTILL_PARTIAL_EXISTING_DATASET_HOLD")
        state=json.loads(manifest.read_text(encoding="utf-8"))
        if state.get("sha256")!=_sha(path):
            raise RuntimeError("DISTILL_DATASET_TAMPERED")
        log_event(root,"TEACHER_DISTILL","SAVED",
                  "Existing source-hashed teacher dataset reused",actual=state["examples"],
                  total=state["examples"])
        return {"path":str(path),"status":"REUSED_HASHED","examples":state["examples"],
                "sha256":state["sha256"]}
    temp=path.with_suffix(".jsonl.partial")
    if temp.exists():raise RuntimeError("DISTILL_PARTIAL_EXISTS_NEEDS_REVIEW")
    examples=0
    log_event(root,"TEACHER_DISTILL","START",
              "Local Qwen teachers preparing approved public examples",actual=0,total=max_tasks)
    try:
        with temp.open("x",encoding="utf-8",newline="\n") as f:
            for idx,(kind,prompt) in enumerate(TASKS[:max_tasks],1):
                model=_teacher(kind,models)
                text=_reply(model,prompt)
                item={
                  "messages":[{"role":"user","content":prompt},
                              {"role":"assistant","content":text}],
                  "source_id":"NOX_LOCAL_TEACHER_"+str(idx),
                  "teacher":model,
                  "data_kind":kind,
                  "approved_for_training":True,
                  "provenance":"NOX curated synthetic non-private task; model-generated output; not a human gold label",
                }
                f.write(json.dumps(item,ensure_ascii=False)+"\n")
                f.flush();os.fsync(f.fileno())
                examples=idx
                log_event(root,"TEACHER_DISTILL","RUNNING",
                          "Saved local teacher answer "+str(idx)+" of "+str(max_tasks),
                          actual=idx,total=max_tasks)
        os.replace(temp,path)
        digest=_sha(path)
        obj={"status":"DATASET_CANDIDATE_NOT_TRAINED",
             "sha256":digest,"examples":examples,
             "student_base":STUDENT,"models_used":sorted(
                 {model for model in models if model in ("qwen3:8b","qwen2.5-coder:7b")}),
             "created_at":datetime.now(timezone.utc).isoformat(),
             "source":"CURATED_LOCAL_QWEN_TEACHER_RESPONSES",
             "requires_independent_holdout":True,
             "native_s03_modified":False,
             "llm_weights_modified":False}
        if manifest.exists():raise FileExistsError("Manifest collision")
        manifest.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")
        log_event(root,"TEACHER_DISTILL","SAVED",
                  "Teacher dataset saved with SHA-256; not yet trained into Qwen weights",
                  actual=examples,total=max_tasks,artifact="teacher_candidates.jsonl")
        return {"path":str(path),"status":obj["status"],"examples":examples,
                "sha256":digest}
    except BaseException as ex:
        log_event(root,"TEACHER_DISTILL","HOLD",
                  "Teacher run stopped: "+type(ex).__name__,actual=examples,total=max_tasks)
        raise

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path(r"C:\NOX_HELION\NOX_NEW"))
    p.add_argument("--max-tasks",type=int,default=24)
    args=p.parse_args()
    print(json.dumps(create(args.root,args.max_tasks),ensure_ascii=False,indent=2))
