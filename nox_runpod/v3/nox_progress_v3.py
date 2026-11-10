#!/usr/bin/env python3
"""NOX V3: truthful per-teacher pipeline progress, never a claim of total absorbed knowledge.
Read-only over training artifacts; writes only atomic status report.
"""
import collections, datetime, hashlib, json, os, pathlib, sqlite3, sys, time

R=pathlib.Path("/workspace/nox")
PLAN=R/"dispatcher/nox_v3/NOX_PRIME_V3_PLAN.json"
OUT=R/"dispatcher/nox_v3/status.json"
DB=R/"memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
WEIGHTS=pathlib.Path("/opt/nox_full_parameter_A40")
TEACHERS=("Qwen3.5-9B","Qwen3.5-27B","DeepSeek-R1-Distill-Qwen-32B")
FILES={"Qwen3.5-27B":"NOX_V3_QWEN27B_TEACHER.jsonl",
       "DeepSeek-R1-Distill-Qwen-32B":"NOX_V3_DEEPSEEK32B_TEACHER.jsonl"}
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def count_teacher_files(teacher):
    filename=FILES.get(teacher)
    if filename is None:return None
    path=R/"distillation"/filename
    if not path.exists():return 0
    ids=set()
    with path.open(encoding="utf-8",errors="replace") as f:
        for line in f:
            try:
                o=json.loads(line)
                if (isinstance(o,dict) and o.get("teacher")==teacher and
                    isinstance(o.get("id"),str) and isinstance(o.get("text"),str)
                    and len(o["text"])>=100 and hashlib.sha256(o["text"].encode()).hexdigest()==o.get("content_sha")):
                    ids.add(o["id"])
            except (ValueError,UnicodeError):pass
    return len(ids)
def memory_counts():
    if not DB.is_file():return {},{}
    try:
        conn=sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True,timeout=10)
        try:
            rows=conn.execute("SELECT teacher,COUNT(*) FROM knowledge GROUP BY teacher").fetchall()
            sources=conn.execute("SELECT teacher,source_file,COUNT(*) FROM knowledge GROUP BY teacher,source_file").fetchall()
        finally:conn.close()
        return dict(rows),{t:[{"file":f,"count":n} for a,f,n in sources if a==t] for t in TEACHERS}
    except sqlite3.Error:return {},{}
def checkpoint_history():
    rows=[]
    for file in WEIGHTS.glob("*/NOX_FULL_TRAIN_RECEIPT.json") if WEIGHTS.is_dir() else []:
        try:
            r=json.loads(file.read_text(encoding="utf-8"))
            shards=r.get("shards",[])
            exists=bool(shards) and all((file.parent/s["file"]).is_file() and
                (file.parent/s["file"]).stat().st_size==int(s.get("bytes",s.get("size",-1)))
                for s in shards)
            rows.append({"cycle":r.get("cycle"),"path":str(file.parent),"steps":r.get("steps"),
              "optimizer_steps_by_teacher":r.get("optimizer_steps_by_teacher"),
              "teacher_counts_available":r.get("teacher_counts"),"holdout_before":r.get("baseline_holdout_loss"),
              "holdout_after":r.get("after_holdout_loss"),"files_exist_correct_size":exists,
              "sha256_rechecked_now":False,"saved_utc":r.get("utc")})
        except (OSError,KeyError,TypeError,ValueError):continue
    return sorted(rows,key=lambda r:r.get("saved_utc") or "")
def main():
    plan=json.loads(PLAN.read_text(encoding="utf-8"))
    mem,sources=memory_counts()
    checkpoints=checkpoint_history()
    totals=collections.Counter()
    unknown=False
    for ck in checkpoints:
        steps=ck.get("optimizer_steps_by_teacher")
        if isinstance(steps,dict):
            for teacher,n in steps.items():
                if teacher in TEACHERS and isinstance(n,int) and n>=0:totals[teacher]+=n
        else:
            unknown=True
    report={"schema":"nox-progress-v3","utc":utc(),"checkpoint_count":len(checkpoints),
       "checkpoints":checkpoints[-10:],"teachers":{},"historical_unattributed_optimizer_steps_present":unknown,
       "total_knowledge_absorbed_percent":None,
       "notes":["100% is a fixed benchmark task-set gate, not percentage of a teacher's neural weights.",
                "Data availability and optimizer steps are reported separately.",
                "Old checkpoints lacking per-step provenance cannot be retrospectively attributed."]}
    for teacher,settings in plan["teachers"].items():
        target=int(settings.get("planned_tasks",100))
        count=count_teacher_files(teacher)
        if count is None:count=mem.get(teacher,0)
        curated=mem.get(teacher,0)
        done=min(count,target)
        rate=round(100*done/target,1)
        # A complete benchmark must also pass independent quality evaluation.
        report["teachers"][teacher]={
           "model_status":settings.get("status"),"source_node":settings.get("source_node",settings.get("target_inference_node")),
           "plan_tasks":target,"teacher_generated_examples":count,"s03_examples":curated,
           "task_generation_percent":rate,"task_generation_remaining":max(0,target-done),
           "independent_quality_verified":None,"optimizer_steps_confirmed":totals[teacher],
           "windows_checkpoint_verified":None,"absorbed_knowledge_percent":None,
           "source_files":sources.get(teacher,[])}
    window=R/"dispatcher/nox_v3/windows_ack.json"
    if window.is_file():
        try:
            ack=json.loads(window.read_text(encoding="utf-8"))
            if ack.get("status")=="SHA256_VERIFIED" and ack.get("cycle"):
                report["windows"]={"status":"SHA256_VERIFIED","cycle":ack["cycle"],
                   "utc":ack.get("utc")}
        except (OSError,ValueError):pass
    else:
        report["windows"]={"status":"NOT_CONFIRMED"}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix(".tmp")
    with tmp.open("w",encoding="utf-8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(tmp,OUT)
    for teacher,t in report["teachers"].items():
        print(teacher, "tasks",str(t["teacher_generated_examples"])+"/"+str(t["plan_tasks"]),
              "S03",t["s03_examples"],"optimizer_steps",t["optimizer_steps_confirmed"],
              "knowledge_100_percent=UNMEASURABLE",flush=True)
    print("NOX_V3_STATUS",OUT,flush=True)
if __name__=="__main__":main()
