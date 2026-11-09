#!/usr/bin/env python3
"""NOX 27B teacher dispatcher. Download teacher in background and, only once GPU
has genuine headroom, generate provenance-labelled curriculum for NOX student.
Does NOT claim direct weight merge or consciousness. All source data is untrusted.
"""
import os,sys,json,time,datetime,pathlib,subprocess,fcntl,signal,hashlib,shutil
ROOT=pathlib.Path("/workspace/nox")
TOOLS=ROOT/"tools";LOG=ROOT/"logs";STATE=ROOT/"dispatcher"
for d in (TOOLS,LOG,STATE):d.mkdir(parents=True,exist_ok=True)
STOP=STATE/"STOP_TEACHER_27B"; LOCK=STATE/"teacher_27b.lock"
RECEIPT=ROOT/"teachers/Qwen3.5-27B/teacher_receipt.json"
DONE=STATE/"teacher_27b_knowledge_receipt.json"
OUT=ROOT/"distillation/nox_27b_teacher_knowledge.jsonl"
PROMPTS=[
("identity","What is the difference between an AI system's functional self-model and subjective consciousness? Explain practical evidence and limits."),
("memory","Design an event-sourced autobiographical memory for a local AI assistant, with dates, provenance, updates and forgetting."),
("memory","Explain retrieval-augmented generation, vector stores, episodic memory and error correction with concrete tests."),
("reasoning","Solve a multi-stage engineering problem systematically; check assumptions and uncertainty."),
("reflection","Design a self-review loop that can identify and correct factual mistakes without inventing evidence."),
("agency","Explain how an autonomous coding agent can use permissions, logs, STOP switches and reproducible verification."),
("learning","Explain knowledge distillation from a frozen teacher into a smaller student and how to evaluate transfer."),
("engineering","Design a checkpoint/rollback strategy for GPU QLoRA with meaningful holdout evaluation."),
("language","Explain a challenging concept clearly in both Russian and Spanish, preserving nuance."),
("software","Compare two architectures for a local Windows-first AI with memory and GPU learning.")]
def write(event,**fields):
 obj={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"event":event,**fields}
 print(json.dumps(obj,ensure_ascii=False),flush=True)
 with (STATE/"teacher_27b_events.jsonl").open("a",encoding="utf-8") as f:f.write(json.dumps(obj,ensure_ascii=False)+"\n")
def gpu():
 p=subprocess.run(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu","--format=csv,noheader,nounits"],text=True,capture_output=True,timeout=15,check=True)
 return [int(x.strip()) for x in p.stdout.strip().splitlines()[0].split(",")]
def gpu_busy():
 # Check active GPU-heavy tasks; do not load 27B on the same GPU as 9B train.
 p=subprocess.run(["nvidia-smi","--query-compute-apps=pid,used_gpu_memory","--format=csv,noheader,nounits"],text=True,capture_output=True,timeout=15)
 return bool(p.stdout.strip() and "No running processes found" not in p.stdout)
def active_student():
 p=subprocess.run(["ps","-eo","args="],text=True,capture_output=True,timeout=10)
 return any(("nox_prime_9b.py" in x or "nox_parallel_9b_lane.py" in x or "knowledge_after_merge.py" in x) and "grep" not in x for x in p.stdout.splitlines())
def try_generate():
 if not RECEIPT.is_file():return "waiting_for_27b_download"
 receipt=json.loads(RECEIPT.read_text())
 f=ROOT/"teachers/Qwen3.5-27B"/receipt.get("filename","")
 if not f.is_file() or f.stat().st_size!=receipt.get("bytes"):return "teacher_incomplete"
 if DONE.is_file():return "teacher_knowledge_already_saved"
 util,used,total,temp=gpu()
 if util>20 or temp>=75 or used>2048 or total-used<19000 or gpu_busy() or active_student():
  return f"waiting_for_free_GPU_util_{util}_usedMiB_{used}"
 if shutil.disk_usage("/workspace").free < 3*1024**3:return "waiting_for_disk_headroom"
 llama=shutil.which("llama-cli") or shutil.which("llama-completion")
 if not llama:return "HOLD_LLAMA_CPP_NOT_INSTALLED"
 rows={}
 if OUT.is_file():
  for line in OUT.read_text(encoding="utf-8").splitlines():
   try:
    row=json.loads(line)
    if row.get("id") and row.get("text"):rows[row["id"]]=row
   except ValueError:pass
 for topic,q in PROMPTS:
  if STOP.exists() or active_student():break
  n=hashlib.sha256((topic+":"+q).encode()).hexdigest()[:20]
  if n in rows:continue
  util,used,total,temp=gpu()
  if temp>=75 or total-used<18000:return "paused_GPU_headroom"
  cmd=[llama,"-m",str(f),"-p",q,"-n","450","-c","2048","-ngl","-1","--no-display-prompt"]
  try:r=subprocess.run(cmd,text=True,capture_output=True,timeout=360,check=True)
  except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
   write("TEACHER_INFERENCE_HOLD",reason=str(exc)[:180]);return "inference_failed_without_checkpoint_loss"
  ans=r.stdout.strip()
  if len(ans)<100:return "teacher_output_too_short"
  row={"id":n,"teacher":"Qwen3.5-27B","topic":topic,"question":q,"text":ans,
       "origin":"synthetic teacher answer","verified":"NOT_FACT_CHECKED",
       "donor_revision":receipt.get("revision")}
  OUT.parent.mkdir(exist_ok=True,parents=True)
  with OUT.open("a",encoding="utf-8") as o:o.write(json.dumps(row,ensure_ascii=False)+"\n");o.flush();os.fsync(o.fileno())
  rows[n]=row
  write("TEACHER_27B_EXAMPLE_SAVED",count=len(rows),target=len(PROMPTS))
 if len(rows)>=len(PROMPTS):
  DONE.write_text(json.dumps({"status":"KNOWLEDGE_DATA_READY_NOT_DISTILLED_INTO_STUDENT_WEIGHTS",
   "examples":len(rows),"source":str(OUT),"donor":receipt.get("repo"),
   "saved_at":datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2))
  return "knowledge_corpus_ready_for_evaluated_student_training"
 return "paused_or_partial"
def main():
 lock=LOCK.open("a+")
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:print("NOX_TEACHER_DISPATCHER_ALREADY_RUNNING");return
 write("TEACHER_DISPATCHER_STARTED",mode="27B queued, primary NOX untouched")
 while not STOP.exists():
  try:
   result=try_generate();write("TEACHER_27B_DISPATCH",decision=result)
   if result in ("knowledge_corpus_ready_for_evaluated_student_training","teacher_knowledge_already_saved"):break
  except Exception as e:write("TEACHER_27B_ERROR",error=str(e)[:250])
  for _ in range(60):
   if STOP.exists():break
   time.sleep(5)
 write("TEACHER_DISPATCHER_EXIT",no_pod_stop=True)
if __name__=="__main__":main()
