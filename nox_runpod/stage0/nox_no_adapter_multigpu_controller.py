#!/usr/bin/env python3
"""NOX multi-GPU policy supervisor. NO ADAPTER TRAINING, ever.
A5000: 2 useful jobs = existing isolated CUDA teacher-generation + curated knowledge memory.
A40: 4 useful jobs = 2 teacher CUDA jobs (available models), three-teacher memory, neural full-weight integrator gate.
Operations can report HOLD; never claim all teacher skills moved just because examples generated.
All machines share /workspace, so target paths must be disjoint.
"""
import argparse,datetime,fcntl,json,os,pathlib,signal,subprocess,sys,time,hashlib,sqlite3
R=pathlib.Path("/workspace/nox")
S=R/"dispatcher/NOX_MULTI_GPU"
L=R/"logs"
S.mkdir(parents=True,exist_ok=True);L.mkdir(exist_ok=True)
W=R/"tools"
STOP=S/"STOP"
def event(role,kind,**kw):
 e={"at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"role":role,"event":kind,**kw}
 print(json.dumps(e,ensure_ascii=False),flush=True)
 with (L/("NOX_ORCHESTRATOR_"+role+".jsonl")).open("a",encoding="utf-8") as f:
  f.write(json.dumps(e,ensure_ascii=False)+"\n");f.flush();os.fsync(f.fileno())
def gpu():
 try:
  x=subprocess.check_output(["nvidia-smi","--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu","--format=csv,noheader,nounits"],text=True,timeout=12).strip().splitlines()[0]
  a=[v.strip() for v in x.split(",")]
  return {"name":a[0],"util":int(a[1]),"used_mib":int(a[2]),"total_mib":int(a[3]),"temp":int(a[4])}
 except Exception as e:return {"error":str(e)[:200]}
def shell(cmd):
 try:return subprocess.check_output(cmd,text=True,stderr=subprocess.STDOUT,timeout=12).strip()
 except Exception as e:return "ERROR:"+str(e)[:140]
def check_process(pattern):
 # Process names must be exact Python script paths, not arbitrary substring from pgrep wrappers.
 p=subprocess.run(["ps","-eo","pid=,args="],capture_output=True,text=True,timeout=10)
 for line in p.stdout.splitlines():
  if pattern in line and ("python" in line or "bash " in line):
   if "NOX_MULTI_GPU" not in line:return True
 return False
def safe_free(min_gib):
 try:
  st=os.statvfs("/workspace")
  return st.f_bavail*st.f_frsize >= min_gib*(1024**3)
 except Exception:return False
def persist(role,slots,decisions):
 g=gpu()
 state={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"host":role,"gpu":g,
   "slots":slots,"decisions":decisions,"train_mode":"MULTI_PASS_DISTILLATION_FULL_WEIGHTS_ONLY",
   "adapters_allowed":False,"actual_full_weight_integration_verified":False}
 p=S/(role+"_snapshot.json");q=p.with_suffix(".tmp")
 q.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8");os.replace(q,p)
def curate():
 # No SQLite on shared network volume: lock-protocol failures from WAL on NFS.
 # A40 owns durable atomic JSONL knowledge export. A5000 reads A40's counts.
 out=R/"memory/THREE_TEACHERS"
 out.mkdir(parents=True,exist_ok=True)
 sources={
 "qwen9":["nox_prime_9b_teacher.jsonl","nox_9b_knowledge_stage2.jsonl","NOX_A40_CUDA_DISTILLATION.jsonl","NOX_A5000_PURE_DISTILLATION.jsonl","NOX_A40_CUDA_PARALLEL_MEMORY_REASONING.jsonl","NOX_A5000_SECOND_TEACHER_KNOWLEDGE.jsonl"],
 "qwen27":["nox_teacher_qwen27.jsonl","nox_27b_teacher_knowledge.jsonl"],
 "deepseek32":["nox_teacher_deepseek32.jsonl"]}
 items={};counts={}
 for teacher,names in sources.items():
  for name in names:
   p=R/"distillation"/name
   if not p.is_file() or p.stat().st_size>500_000_000:continue
   try:
    with p.open(encoding="utf-8") as f:
     for line in f:
      if len(line)>500000:continue
      try:
       row=json.loads(line);body=str(row.get("text") or "").strip()
       if len(body)<100:continue
       orig=str(row.get("teacher") or "")
       if teacher=="qwen27" and orig and "27" not in orig:continue
       if teacher=="deepseek32" and orig and "deepseek" not in orig.lower() and "32" not in orig:continue
       sha=hashlib.sha256(body.encode()).hexdigest()
       k=teacher+":"+sha
       items.setdefault(k,{"teacher":teacher,"sha256":sha,"source":name,
         "source_id":str(row.get("id",""))[:100],"topic":str(row.get("topic",""))[:120],
         "text":body,"verified":False})
      except (ValueError,TypeError,KeyError):continue
   except OSError:continue
  counts[teacher]=sum(1 for x in items.values() if x["teacher"]==teacher)
 tmp=out/"knowledge_sources.tmp.jsonl"
 with tmp.open("w",encoding="utf-8") as f:
  for k in sorted(items):
   f.write(json.dumps(items[k],ensure_ascii=False)+"\\n")
  f.flush();os.fsync(f.fileno())
 os.replace(tmp,out/"knowledge_sources.jsonl")
 stamp={"counts":counts,"at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "status":"THREE_TEACHER_MEMORY_SOURCES_ONLY_NOT_TRAINED_WEIGHTS"}
 x=out/"counts.tmp.json";x.write_text(json.dumps(stamp,indent=2));os.replace(x,out/"counts.json")
 return counts
def supervisor(role):
 lock=(S/(role+".lock")).open("a+")
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  print("NOX_"+role+"_ALREADY_RUNNING",flush=True);return
 if role=="A5000":
  # Running primary CUDA teacher process is left intact. New CPU memory curation
  # is the second useful worker; don't interfere with existing knowledge trainer.
  plans=[("CUDA_TEACHER",None),("MEMORY_CURATE",None)]
 else:
  plans=[("CUDA_TEACHER_1",None),("CUDA_TEACHER_2",None),
    ("MEMORY_CURATE",None),("FULL_WEIGHT_INTEGRATOR",None)]
 event(role,"SUPERVISOR_START",slots=len(plans))
 while not STOP.exists():
  decisions={}
  g=gpu()
  if role=="A5000":
   # Distillation job from previous command may already be running. Refuse blind duplicates.
   live=check_process("/workspace/nox/tools/a5000_pure_distillation.py")
   decisions["CUDA_TEACHER"]=("ACTIVE" if live else "HOLD_NEEDS_PRIOR_VERIFIED_LAUNCH")
   try:
    state=R/"memory/THREE_TEACHERS/counts.json"
    decisions["MEMORY_CURATE"]="A40_CANONICAL:"+state.read_text()[:300] if state.is_file() else "WAIT_A40_MEMORY"
   except Exception as e:decisions["MEMORY_CURATE"]="ERROR:"+str(e)[:100]
  else:
   for idx,name in enumerate(("CUDA_TEACHER_1","CUDA_TEACHER_2")):
    pattern="/workspace/nox/tools/"+("a40_cuda_distillation_direct.py" if idx==0 else "a40_cuda_secondary_memory.py")
    active=check_process(pattern)
    decisions[name]="ACTIVE" if active else "HOLD_NOT_RUNNING"
   try:decisions["MEMORY_CURATE"]="READY:"+json.dumps(curate())
   except Exception as e:decisions["MEMORY_CURATE"]="ERROR:"+str(e)[:100]
   # Gate full-weight 9B student training. Do not fake with LoRA.
   # 9B bf16 weight+gradient+AdamW states exceed available A40 VRAM.
   c=R/"memory/THREE_TEACHERS/counts.json"
   counts=json.loads(c.read_text())["counts"] if c.is_file() else {}
   if min((counts.get(t,0) for t in ("qwen9","qwen27","deepseek32")),default=0)<8:
    decisions["FULL_WEIGHT_INTEGRATOR"]="HOLD_WAIT_THREE_TEACHER_CORPORA"
   else:
    decisions["FULL_WEIGHT_INTEGRATOR"]="HOLD_FULL_WEIGHT_MEMORY_OFFLOAD_IMPLEMENTATION_NOT_VERIFIED"
  persist(role,len(plans),decisions)
  event(role,"MINUTE_HEARTBEAT",gpu=g,slots=decisions)
  for _ in range(60):
   if STOP.exists():break
   time.sleep(1)
if __name__=="__main__":
 a=argparse.ArgumentParser();a.add_argument("--role",choices=("A5000","A40"),required=True)
 supervisor(a.parse_args().role)
