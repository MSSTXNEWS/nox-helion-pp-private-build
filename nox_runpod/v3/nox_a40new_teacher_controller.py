#!/usr/bin/env python3
"""Dedicated NOX A40NEW teacher worker (NOT the old A40 full-weight trainer).
Start on new A40 only. Reuse existing verified shared teachers, do not copy weights.
Every 10 seconds monitor; after each bounded batch start next automatically.
"""
import datetime,fcntl,json,os,pathlib,subprocess,sys,time
R=pathlib.Path("/workspace/nox")
S=R/"dispatcher/nox_a40new"
B=pathlib.Path("/opt/nox_a40new/bin")
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def emit(**kw):
 obj={"utc":utc(),"node":"A40NEW","status":"RUNNING",**kw}
 S.mkdir(parents=True,exist_ok=True)
 tmp=S/"status.json.tmp"
 with tmp.open("w") as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,S/"status.json")
 print(json.dumps(obj,ensure_ascii=False),flush=True)
def owners():
 p=subprocess.run(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=12)
 if p.returncode:return None
 return [int(x.strip()) for x in p.stdout.splitlines() if x.strip().isdigit()]
def snapshot():
 try:
  p=subprocess.run(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.free,temperature.gpu","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=8)
  return p.stdout.strip() if p.returncode==0 else "GPU_SENSOR_FAIL"
 except Exception:return "GPU_SENSOR_FAIL"
def main():
 S.mkdir(parents=True,exist_ok=True)
 with (S/"controller.lock").open("a+") as lk:
  try:fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print("NOX_A40NEW_CONTROLLER_ALREADY_RUNNING");return
  n=0
  while True:
   if (S/"STOP").exists():
    emit(status="HOLD_MANUAL_STOP");time.sleep(60);continue
   if not (R/"teachers").is_dir():
    emit(status="HOLD_SHARED_VOLUME_MISSING",hint="Reconnect /workspace");time.sleep(60);continue
   models=[
      ("Qwen3.5-27B",R/"teachers/Qwen3.5-27B/Qwen3.5-27B-Q4_K_M.gguf"),
      ("DeepSeek-R1-Distill-Qwen-32B",R/"teachers/DeepSeek-R1-Distill-Qwen-32B/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf")
   ]
   todo=[]
   for name,p in models:
    try:
     q=json.loads((p.parent/"nox_teacher_proof.json").read_text())
     if q.get("status")=="SHA256_VERIFIED_SHARED" and p.is_file() and q.get("bytes")==p.stat().st_size:
      todo.append(name)
    except (OSError,ValueError):pass
   if not todo:
    emit(status="HOLD_NO_VERIFIED_HEAVY_TEACHER",available=[str(p) for _,p in models if p.is_file()])
    time.sleep(60);continue
   server=pathlib.Path("/opt/nox_a40new/llama.cpp/build/bin/llama-server")
   if not server.is_file():
    emit(status="HOLD_LOCAL_CUDA_LLAMA_MISSING");time.sleep(60);continue
   cur=owners()
   if cur is None or cur:
    emit(status="GPU_OTHER_OWNER_PRESERVED",gpu=snapshot(),gpu_owners=cur);time.sleep(60);continue
   teacher=todo[n%len(todo)]
   n+=1
   # Apply Guardian configuration only between megablocks.
   try:cfg=json.loads((S/"guardian_config.json").read_text())
   except (OSError,ValueError):cfg={}
   parallel=max(1,min(4,int(cfg.get("parallel",3))))
   gpu_layers=max(20,min(50,int(cfg.get("gpu_layers",40))))
   ctx=max(2048,min(8192,int(cfg.get("ctx",4096))))
   batch=max(1,min(50,int(cfg.get("batch",50))))
   cmd=["python3","-u",str(B/"nox_teacher_server_batch.py"),"--node","A40NEW",
        "--teacher",teacher,"--start","0","--limit",str(batch),"--gpu-layers",str(gpu_layers),
        "--ctx",str(ctx),"--parallel",str(parallel)]
   log=R/"logs/NOX_A40NEW_TEACHERS.log";log.parent.mkdir(parents=True,exist_ok=True)
   if not pathlib.Path(cmd[2]).exists():
    emit(status="HOLD_SCRIPT_MISSING");time.sleep(60);continue
   with log.open("ab") as f:
    proc=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
    emit(status="TEACHER_BATCH_STARTED",teacher=teacher,pid=proc.pid,gpu=snapshot(),max_batch=batch,parallel=parallel,gpu_layers=gpu_layers,ctx=ctx)
    while proc.poll() is None:
     emit(status="TEACHER_BATCH_RUNNING",teacher=teacher,pid=proc.pid,gpu=snapshot())
     time.sleep(60)
   emit(status="TEACHER_BATCH_FINISHED" if proc.returncode==0 else "HOLD_TEACHER_BATCH_FAILED",
        teacher=teacher,exit_code=proc.returncode,gpu=snapshot())
   time.sleep(60)
if __name__=="__main__":
 try:main()
 except Exception as e:emit(status="HOLD_CONTROLLER_EXCEPTION",error=type(e).__name__+":"+str(e)[:280]);raise
