"""Convert local, attributable Qwen teacher responses into an ACTUAL student corpus.

The student model is the existing Qwen2.5-0.5B base, NOT the 8B PRIME LLM.
Only explicitly allowlisted Qwen donor models are accepted; all others remain
inventoried/candidate-only until source and license rights are reviewed.
The holdout is separate and NEVER fed to the trainer. No S03/user data.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re
from pathlib import Path
from datetime import datetime,timezone
from nox_prime_progress_v1 import log_event

ALLOWLIST={"qwen3:8b","qwen2.5-coder:7b"}
STUDENT="Qwen2.5-0.5B-Instruct"
_SHA=re.compile(r"^[a-f0-9]{64}$")
MAX_BYTES=40_000_000

def _sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def _latest(root):
    d=Path(root)/"brain"/"intelligence"/"absorption"
    candidates=sorted(d.glob("multi_teacher_*.manifest.json"),
                      key=lambda p:p.stat().st_mtime,reverse=True) if d.is_dir() else []
    for f in candidates:
        try:
            o=json.loads(f.read_text(encoding="utf-8"))
            source=Path(o["dataset_path"]).resolve()
            if source.parent!=d.resolve() or source.is_symlink() or not source.is_file():
                continue
            if o.get("schema")!="NOX_MULTI_TEACHER_CANDIDATES_V2":
                continue
            sha=o.get("dataset_sha256")
            if not isinstance(sha,str) or not _SHA.fullmatch(sha):
                continue
            if source.stat().st_size>MAX_BYTES or _sha(source)!=sha:
                continue
            return f,source,o
        except (OSError,ValueError,KeyError,TypeError):
            continue
    raise RuntimeError("NO_HASHED_MULTI_TEACHER_DATASET")

def build(root):
    root=Path(root).resolve()
    m,source,manifest=_latest(root)
    output=root/"brain"/"intelligence"/"distillation"
    output.mkdir(parents=True,exist_ok=True)
    source_sha=_sha(source)
    tag=source_sha[:16]
    destination=output/("multi_teacher_student_"+tag+".jsonl")
    holdout=output/("multi_teacher_holdout_"+tag+".jsonl")
    report=output/("multi_teacher_student_"+tag+".manifest.json")
    current=output/"MULTI_TEACHER_CURRENT.json"
    def activate():
        # Atomic pointer update; prior versions of weights and datasets remain.
        data={"schema":"NOX_MULTI_TEACHER_CURRENT_V1","train":destination.name,
              "heldout":holdout.name,"manifest":report.name,
              "source_sha256":source_sha}
        tmp=output/("."+current.name+"."+tag+".tmp")
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        os.replace(tmp,current)
    if any(x.exists() for x in (destination,holdout,report)):
        if not (destination.is_file() and holdout.is_file() and report.is_file()):
            raise RuntimeError("STUDENT_DATASET_PARTIAL_EXISTS")
        obj=json.loads(report.read_text(encoding="utf-8"))
        if (_sha(destination)!=obj.get("train_sha256") or
            _sha(holdout)!=obj.get("heldout_sha256") or
            obj.get("source_sha256")!=_sha(source)):
            raise RuntimeError("STUDENT_DATASET_INTEGRITY_HOLD")
        activate()
        return {"status":"REUSED_VERIFIED_DATASET","train_examples":obj["train_examples"],
                "heldout_examples":obj["heldout_examples"],"path":str(destination)}
    records={}
    for line in source.read_text(encoding="utf-8").splitlines():
        try: row=json.loads(line)
        except (ValueError,TypeError):continue
        if not isinstance(row,dict) or row.get("source_model") not in ALLOWLIST:
            continue
        digest=row.get("source_model_digest")
        if not isinstance(digest,str) or not _SHA.fullmatch(digest):
            continue
        msgs=row.get("messages")
        if not isinstance(msgs,list) or len(msgs)!=2:
            continue
        if (msgs[0].get("role"),msgs[1].get("role"))!=("user","assistant"):
            continue
        question=msgs[0].get("content")
        answer=msgs[1].get("content")
        if not isinstance(question,str) or not isinstance(answer,str):
            continue
        if not 20<=len(question)<=1800 or not 60<=len(answer)<=8000:
            continue
        question_sha=hashlib.sha256(question.encode("utf-8")).hexdigest()
        if row.get("teacher_prompt_sha256")!=question_sha:
            continue
        key=question_sha+":"+digest
        records[key]={"messages":[{"role":"user","content":question},
                                 {"role":"assistant","content":answer}],
                      "teacher_model":row["source_model"],
                      "teacher_digest":digest,
                      "teacher_prompt_sha256":question_sha,
                      "source":"NOX_PUBLIC_CURRICULUM_LOCAL_TEACHER",
                      "unverified_teacher_content":True}
    rows=sorted(records.values(),key=lambda v:v["teacher_prompt_sha256"]+v["teacher_digest"])
    # Split by unique prompt across teacher models, NOT by raw row index.
    prompts=sorted({x["teacher_prompt_sha256"] for x in rows})
    held={key for i,key in enumerate(prompts) if i%5==0}
    train=[r for r in rows if r["teacher_prompt_sha256"] not in held]
    eval_rows=[r for r in rows if r["teacher_prompt_sha256"] in held]
    if len(train)<8 or len(eval_rows)<2:
        raise RuntimeError("NOT_ENOUGH_INDEPENDENT_TEACHER_SAMPLES")
    if {r["teacher_prompt_sha256"] for r in train} & {r["teacher_prompt_sha256"] for r in eval_rows}:
        raise RuntimeError("TRAIN_HOLDOUT_LEAKAGE")
    # Never replace existing files; all three outputs are written once.
    for target,items in ((destination,train),(holdout,eval_rows)):
        with target.open("x",encoding="utf-8",newline="\n") as f:
            for item in items:
                f.write(json.dumps(item,ensure_ascii=False)+"\n")
    obj={"schema":"NOX_PRIME_STUDENT_TRAIN_V1",
         "source_manifest":str(m),"source_sha256":_sha(source),
         "train_sha256":_sha(destination),"heldout_sha256":_sha(holdout),
         "train_examples":len(train),"heldout_examples":len(eval_rows),
         "student_base":STUDENT,
         "allowed_teacher_models":sorted({r["teacher_model"] for r in rows}),
         "source_rights":"qwen3/qwen2.5-coder official-family candidate, license audit required before external redistribution",
         "holdout_isolation":"SPLIT_BY_TEACHER_PROMPT_SHA256",
         "created_utc":datetime.now(timezone.utc).isoformat(),
         "status":"TRAINING_READY_RESEARCH_STUDENT_NOT_ACCEPTED",
         "no_private_S03_data":True,"originals_deleted":False}
    with report.open("x",encoding="utf-8") as f:
        json.dump(obj,f,ensure_ascii=False,indent=2)
    activate()
    log_event(root,"DATASET_PREP","SAVED",
        "Real Qwen teacher student/holdout split saved; other donor weights kept",
        actual=len(train)+len(eval_rows),total=len(train)+len(eval_rows))
    return {"status":obj["status"],"train_examples":len(train),
            "heldout_examples":len(eval_rows),"path":str(destination),
            "train_sha256":obj["train_sha256"]}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path(r"C:\NOX_HELION\NOX_NEW"))
    a=p.parse_args()
    print(json.dumps(build(a.root),ensure_ascii=False,indent=2))
