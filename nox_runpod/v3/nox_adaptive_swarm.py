#!/usr/bin/env python3
"""NOX PRIME adaptive CPU-only worker swarm, bound to the ONE NOX identity.

The workers inspect already sourced knowledge, surface quality defects, propose
testable next actions and evaluate local project evidence. They never fabricate
teacher outputs, touch student weights, run generated code, or promote memory
without independent provenance/quality verification. Bounded by CPU/RAM and
the active A40 full-parameter trainer's resource needs.
"""
from __future__ import annotations
import argparse, concurrent.futures, datetime, fcntl, hashlib, json, os, pathlib, sqlite3, subprocess, sys, time
R=pathlib.Path("/workspace/nox")
STATE=R/"dispatcher/nox_v3"
OUT=R/"memory/NOX_SWARM_CANDIDATES"
DB=R/"memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
MODES=("memory_integrity","knowledge_gaps","skill_curriculum","progress_audit","experiment_backlog","source_lineage")
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def atom(path,doc):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix(".tmp")
 with tmp.open("w",encoding="utf-8") as f:
  json.dump(doc,f,ensure_ascii=False,indent=2)
  f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def read(path):
 try:return json.loads(path.read_text(encoding="utf-8"))
 except (OSError,ValueError):return {}
def meminfo():
 try:
  d={}
  for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
   if line.startswith(("MemAvailable:","MemTotal:")):
    k,n,*_=line.split();d[k[:-1]]=int(n)//1024
  return d
 except OSError:return {}
def gpu():
 try:
  p=subprocess.run(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,temperature.gpu",
    "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=8)
  if p.returncode:return None
  a=p.stdout.splitlines()[0].split(",")
  return {"utilization":int(a[0]),"vram_used_mib":int(a[1]),"temperature_c":int(a[2])}
 except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):return None
def sqlite_summary():
 if not DB.is_file():return {"status":"HOLD_S03_MISSING"}
 c=sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True,timeout=10)
 try:
  counts=dict(c.execute("SELECT teacher, COUNT(*) FROM knowledge GROUP BY teacher").fetchall())
  dup=c.execute("SELECT COUNT(*) FROM (SELECT content_sha FROM knowledge GROUP BY content_sha HAVING COUNT(*)>1)").fetchone()[0]
  sources=c.execute("SELECT COUNT(DISTINCT source_file) FROM knowledge").fetchone()[0]
  return {"status":"OK","teacher_counts":counts,"duplicate_text_hash_groups":dup,"distinct_sources":sources}
 finally:c.close()
def one(mode):
 base={"utc":utc(),"worker":mode,"status":"CANDIDATE_ONLY","execution_boundary":"CPU_READ_ONLY",
       "promote_to_trained_weights":False,"memory_mutation":False}
 if mode=="memory_integrity":
  base["evidence"]=sqlite_summary()
 elif mode=="knowledge_gaps":
  a=sqlite_summary();t=a.get("teacher_counts",{})
  required=("Qwen3.5-9B","Qwen3.5-27B","DeepSeek-R1-Distill-Qwen-32B")
  base["missing_teacher_provenance"]=[m for m in required if not t.get(m)]
  base["recommended_action"]="Use original verified teacher GGUF with logged model SHA; never relabel 9B"
 elif mode=="skill_curriculum":
  p=read(STATE/"NOX_WOW50_IDENTITY.json")
  groups=p.get("groups",{})
  base["candidate_skills"]=[{"id":key,"description":name,"evidence_required":"independent_test_receipt"}
      for key,name in [x for group in groups.values() for x in group][:50]]
  base["candidate_total"]=len(base["candidate_skills"])
 elif mode=="progress_audit":
  p=read(STATE/"status.json")
  base["reported_teachers"]={k:{"optimizer_steps":v.get("optimizer_steps_confirmed"),
         "s03_examples":v.get("s03_examples"),"absorbed_knowledge_percent":None}
          for k,v in p.get("teachers",{}).items()}
  base["windows_status"]=p.get("windows",{"status":"NOT_CONFIRMED"})
 elif mode=="experiment_backlog":
  p=read(STATE/"improvement_status.json")
  base["recommendation"]=p.get("recommended_next_teacher","HOLD_UNKNOWN")
  base["next_action"]=p.get("next_action","WAIT_FOR_VERIFIED_EVIDENCE")
  base["proposed_experiment"]={"test":"Compare frozen holdout before/after new teacher batch",
       "data_contamination_prevention":True,"automatically_apply_unreviewed_code":False}
 elif mode=="source_lineage":
  proofs=[]
  for folder in ("Qwen3.5-27B","DeepSeek-R1-Distill-Qwen-32B"):
   d=read(R/"teachers"/folder/"nox_teacher_proof.json")
   proofs.append({"teacher":folder,"status":d.get("status","HOLD_UNVERIFIED"),
                 "sha256":d.get("sha256") if d.get("status")=="SHA256_VERIFIED_SHARED" else None})
  base["model_proofs"]=proofs
 else:raise RuntimeError("UNSUPPORTED_WORKER")
 canonical=json.dumps(base,ensure_ascii=False,sort_keys=True).encode()
 base["record_sha256"]=hashlib.sha256(canonical).hexdigest()
 atom(OUT/(mode+".json"),base)
 return {"worker":mode,"status":"DONE","sha256":base["record_sha256"]}
def run(node):
 STATE.mkdir(parents=True,exist_ok=True)
 lock=(STATE/("swarm_"+node+".lock")).open("a+")
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  print("NOX_SWARM_ALREADY_RUNNING",node,flush=True);return 0
 ram=meminfo();g=gpu()
 if not ram or g is None or g["temperature_c"]<=0:
  print("HOLD_SWARM_RESOURCE_SENSOR",flush=True);return 2
 if g["temperature_c"]>=70:
  print("HOLD_SWARM_GPU_TEMP",flush=True);return 2
 cpus=max(1,os.cpu_count() or 1)
 cores_usable=max(1,min(6,cpus//2,ram.get("MemAvailable",0)//2048))
 cpu_pressure=os.getloadavg()[0]/cpus
 # If the GPU is training and CPU load high, minimize swarm. Only CPU work.
 if cpu_pressure>=0.75:cores_usable=1
 elif cpu_pressure>=0.5:cores_usable=min(2,cores_usable)
 if node=="A40" and g["utilization"]>=65:cores_usable=1
 if ram.get("MemAvailable",0)<4096:cores_usable=1
 cores_usable=max(1,min(cores_usable,len(MODES)))
 start=time.monotonic()
 with concurrent.futures.ProcessPoolExecutor(max_workers=cores_usable) as pool:
  futures={pool.submit(one,mode):mode for mode in MODES}
  results=[]
  for future,mode in futures.items():
   try:results.append(future.result(timeout=60))
   except Exception as e:results.append({"worker":mode,"status":"HOLD","reason":str(e)[:180]})
 report={"utc":utc(),"node":node,"active_parallel_workers":cores_usable,"scheduled_workers":len(MODES),
         "gpu":g,"mem_available_mib":ram.get("MemAvailable"),
         "cpu_load_ratio":round(cpu_pressure,2),"elapsed_seconds":round(time.monotonic()-start,2),
         "results":results,"neural_optimizer_steps_created":0,"raw_teacher_weights_merged":False,
         "outputs":str(OUT)}
 atom(STATE/("swarm_status_"+node+".json"),report)
 print(json.dumps({"event":"NOX_SWARM_BATCH",**report},ensure_ascii=False),flush=True)
 return 0
def main():
 p=argparse.ArgumentParser();p.add_argument("--node",choices=("A40","A5000"),required=True)
 a=p.parse_args();return run(a.node)
if __name__=="__main__":sys.exit(main())
