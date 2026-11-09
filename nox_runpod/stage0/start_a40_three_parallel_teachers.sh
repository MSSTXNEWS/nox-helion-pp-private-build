#!/usr/bin/env bash
# NOX A40: launch 3 independent, concurrent teacher distillation-data lanes.
# Never touch NOX training checkpoints / model writes on shared /workspace.
set -Eeuo pipefail
ROOT=/workspace/nox
STATE="$ROOT/dispatcher/a40"
LOG="$ROOT/logs"
LOCAL=/opt/nox_teachers
mkdir -p "$STATE" "$LOG" "$LOCAL" "$ROOT/tools" "$ROOT/distillation"
if [ "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" != "NVIDIA A40" ];then
 echo "HOLD_NOT_A40";exit 20
fi
test "$(stat -c %d /opt)" != "$(stat -c %d /workspace)" || { echo "HOLD_NO_SEPARATE_LOCAL_DISK";exit 21; }
exec 9>"$STATE/a40_launcher.lock"
flock -n 9 || { echo "NOX_A40_ALREADY_STARTING";exit 0; }
if [ -s "$STATE/manager.pid" ] && kill -0 "$(cat "$STATE/manager.pid")" 2>/dev/null;then
 echo "NOX_A40_MANAGER_ALREADY_RUNNING pid=$(cat "$STATE/manager.pid")";exit 0
fi
WORKER_URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/0d0ac95126370b37a8efc14ef7a84e574ad98fe8/nox_runpod/stage0/a40_three_teachers_worker.py'
curl -fLsS --retry 4 "$WORKER_URL" -o "$ROOT/tools/a40_three_teachers_worker.py.new"
python3 -m py_compile "$ROOT/tools/a40_three_teachers_worker.py.new"
mv "$ROOT/tools/a40_three_teachers_worker.py.new" "$ROOT/tools/a40_three_teachers_worker.py"
# Worker supervisor is persistent. It downloads three separately-verified model files,
# builds CUDA llama.cpp, runs 3 simultaneous inference workloads, and restarts bounded jobs.
cat > "$STATE/manager.py" <<'PY'
import datetime,hashlib,json,os,pathlib,shutil,signal,subprocess,sys,threading,time
R=pathlib.Path("/workspace/nox")
S=R/"dispatcher/a40"; L=R/"logs"; D=pathlib.Path("/opt/nox_teachers")
S.mkdir(parents=True,exist_ok=True);L.mkdir(parents=True,exist_ok=True);D.mkdir(parents=True,exist_ok=True)
STOP=S/"STOP"
TEACHERS=[
 ("qwen9","unsloth/Qwen3.5-9B-GGUF","Qwen3.5-9B-Q4_K_M.gguf",40),
 ("qwen27","unsloth/Qwen3.5-27B-GGUF","Qwen3.5-27B-Q4_K_M.gguf",20),
 ("deepseek32","unsloth/DeepSeek-R1-Distill-Qwen-32B-GGUF","DeepSeek-R1-Distill-Qwen-32B-Q3_K_M.gguf",16)]
jobs={}
events=S/"events.jsonl"
def event(kind,**fields):
 d={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"event":kind,**fields}
 with events.open("a",encoding="utf-8") as f:f.write(json.dumps(d,ensure_ascii=False)+"\n")
 print(json.dumps(d,ensure_ascii=False),flush=True)
def gpus():
 try:
  s=subprocess.check_output(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu","--format=csv,noheader,nounits"],text=True,timeout=10)
  vals=[int(x.strip()) for x in s.splitlines()[0].split(",")]
  return {"utilization":vals[0],"vram_used_mib":vals[1],"vram_total_mib":vals[2],"temp_c":vals[3]}
 except Exception as exc:return {"error":str(exc)[:130]}
def snapshot():
 x={"time":datetime.datetime.now(datetime.timezone.utc).isoformat(),"gpu":gpus(),
  "jobs":{k:{"running":v.get("proc") is not None and v["proc"].poll() is None,
             "cycle":v.get("cycle",0),"status":v.get("status","waiting")} for k,v in jobs.items()},
  "checkpoints":{x:len(list((R/"checkpoints"/x).glob("pass*/SUCCESS.json"))) for x in
     ("NOX_PRIME_9B_GENESIS","NOX_9B_KNOWLEDGE","NOX_9B_PARALLEL_TECH")},
  "network_volume":str(R)}
 p=S/"snapshot.json.tmp";p.write_text(json.dumps(x,indent=2,ensure_ascii=False));os.replace(p,S/"snapshot.json")
def disk_room(bytes_needed):
 st=shutil.disk_usage("/opt")
 return st.free > bytes_needed + 4_000_000_000
def download(id,repo,fn):
 from huggingface_hub import hf_hub_download,model_info
 folder=D/id;folder.mkdir(parents=True,exist_ok=True)
 # Never silently treat old, partially downloaded, or wrong-model files as verified.
 info=model_info(repo,files_metadata=True)
 item=next((x for x in info.siblings if x.rfilename==fn),None)
 if item is None:raise RuntimeError(f"MODEL_FILE_MISSING:{repo}/{fn}")
 expected=(item.lfs or {}).get("sha256") if isinstance(item.lfs,dict) else getattr(item.lfs,"sha256",None)
 if not expected:raise RuntimeError(f"UPSTREAM_SHA_MISSING:{repo}/{fn}")
 size=item.size or 0
 f=folder/fn
 receipt=folder/"receipt.json"
 if receipt.exists() and f.exists():
  doc=json.loads(receipt.read_text())
  if doc.get("sha256")==expected and f.stat().st_size==doc.get("bytes"):
   event("TEACHER_PRESENT_AND_VERIFIED",id=id,bytes=f.stat().st_size)
   return str(f)
 if not disk_room(max(0,size-(f.stat().st_size if f.exists() else 0))):
  raise RuntimeError(f"LOW_CONTAINER_DISK_FOR:{repo}/{fn}")
 path=pathlib.Path(hf_hub_download(repo_id=repo,filename=fn,revision=info.sha,local_dir=str(folder)))
 digest=hashlib.sha256()
 with path.open("rb") as fp:
  for chunk in iter(lambda:fp.read(8*1024*1024),b""):digest.update(chunk)
 if digest.hexdigest()!=expected:raise RuntimeError("MODEL_SHA256_MISMATCH:"+id)
 doc={"repo":repo,"revision":info.sha,"filename":fn,"bytes":path.stat().st_size,"sha256":expected,
      "kind":"teacher-only-not-student-weights"}
 tmp=folder/"receipt.tmp.json";tmp.write_text(json.dumps(doc,indent=2));os.replace(tmp,receipt)
 event("TEACHER_VERIFIED",id=id,bytes=path.stat().st_size)
 return str(path)
def build_cli():
 old=shutil.which("llama-cli")
 if old:return old
 cli=pathlib.Path("/opt/llama.cpp/build/bin/llama-cli")
 if cli.exists():return str(cli)
 if not shutil.which("git") or not shutil.which("cmake") or not shutil.which("nvcc"):
  raise RuntimeError("MISSING_GIT_CMAKE_OR_NVCC_FOR_LLAMA_CPP")
 src=pathlib.Path("/opt/llama.cpp")
 if not (src/".git").exists():
  subprocess.run(["git","clone","--filter=blob:none","--depth=1","https://github.com/ggml-org/llama.cpp.git",str(src)],check=True)
 subprocess.run(["cmake","-S",str(src),"-B",str(src/"build"),"-DGGML_CUDA=ON",
                 "-DCMAKE_CUDA_ARCHITECTURES=86","-DCMAKE_BUILD_TYPE=Release"],check=True)
 subprocess.run(["cmake","--build",str(src/"build"),"--target","llama-cli","-j","4"],check=True)
 if not cli.exists():raise RuntimeError("LLAMA_BUILD_MISSING_BINARY")
 return str(cli)
def main():
 signal.signal(signal.SIGTERM,lambda *_: STOP.touch())
 signal.signal(signal.SIGINT,lambda *_: STOP.touch())
 try:
  import huggingface_hub
 except ImportError:
  subprocess.run([sys.executable,"-m","pip","install","-q","huggingface_hub>=0.35,<2"],check=True)
 event("A40_MANAGER_START",mode="3 parallel read-only teachers, minute checkpoint logs")
 # Download models to local container disk. 27B on old A5000 is ephemeral and
 # is not assumed to exist on new A40.
 for id,repo,fn,layers in TEACHERS:
  jobs[id]={"status":"downloading","cycle":0,"layers":layers,"proc":None}
  try:
   jobs[id]["model"]=download(id,repo,fn)
   jobs[id]["status"]="downloaded"
  except Exception as exc:
   jobs[id]["status"]="download_failed"
   event("DONOR_DOWNLOAD_HOLD",id=id,error=str(exc)[:300])
 try:cli=build_cli()
 except Exception as exc:
  event("NOX_LLAMA_BUILD_HOLD",error=str(exc)[:300]);return
 for id,repo,fn,layers in TEACHERS:
  job=jobs[id]
  if "model" not in job:continue
  path=S/(id+"_cycle.txt")
  try:job["cycle"]=int(path.read_text().strip()) if path.exists() else 0
  except ValueError:job["cycle"]=0
  job["failures"]=0
 # Launch all three as distinct processes when each model is available.
 # GPU offload layers are deliberately partitioned; CPU RAM holds remaining layers.
 while not STOP.exists():
  for id,repo,fn,layers in TEACHERS:
   job=jobs[id]
   if "model" not in job:continue
   proc=job.get("proc")
   if proc is not None and proc.poll() is None:continue
   if proc is not None:
    rc=proc.poll()
    if rc==0:
     job["cycle"]+=1
     (S/(id+"_cycle.txt")).write_text(str(job["cycle"]))
     job["failures"]=0
     event("TEACHER_PASS_DONE",id=id,cycle=job["cycle"])
    else:
     job["failures"]=job.get("failures",0)+1
     event("TEACHER_RESTART",id=id,rc=rc,failures=job["failures"])
     if job["failures"]>=4:
      job["status"]="HOLD_AFTER_REPEATED_ERRORS"
      del job["model"]
      continue
   # Avoid artificial loads when GPU temperature high or VRAM exhausted.
   info=gpus()
   if info.get("temp_c",99)>=78 or info.get("vram_used_mib",99999)>43000:
    job["status"]="PAUSED_FOR_GPU_SAFETY";continue
   cmd=[sys.executable,"-u",str(R/"tools/a40_three_teachers_worker.py"),
        "--id",id,"--model",job["model"],"--gpu-layers",str(job["layers"]),
        "--cli",cli,"--passes","1"]
   env=dict(os.environ,NOX_CYCLE=str(job["cycle"]))
   log=open(L/("NOX_A40_"+id+".log"),"a")
   job["proc"]=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL,start_new_session=True,env=env)
   job["status"]="RUNNING"
   event("TEACHER_STARTED",id=id,pid=job["proc"].pid,cycle=job["cycle"],gpu_layers=job["layers"])
  snapshot()
  time.sleep(60)
 event("A40_MANAGER_STOP_REQUESTED")
 for job in jobs.values():
  proc=job.get("proc")
  if proc is not None and proc.poll() is None:
   proc.terminate()
   try:proc.wait(timeout=35)
   except subprocess.TimeoutExpired:proc.kill()
 snapshot()
if __name__=="__main__":
 try:main()
 except Exception as ex:
  event("A40_MANAGER_FATAL",error=str(ex)[:400]);raise
PY
python3 -m py_compile "$STATE/manager.py"
# Persistent supervisor independent of Windows SSH connection.
nohup setsid bash -c '
 while [ ! -e /workspace/nox/dispatcher/a40/STOP ];do
 /usr/bin/python3 -u /workspace/nox/dispatcher/a40/manager.py >>/workspace/nox/logs/NOX_A40_MANAGER.log 2>&1
 rc=$?
 echo "$(date -u +%FT%TZ) manager exit=$rc" >>/workspace/nox/logs/NOX_A40_SUPERVISOR.log
 sleep 45
 done
' </dev/null >/dev/null 2>&1 &
echo $! > "$STATE/manager.pid"
echo "NOX_A40_THREE_TEACHER_MANAGER_DETACHED pid=$(cat "$STATE/manager.pid")"
echo "THREE_PARALLEL_LANES_REQUESTED; NOX_SHARED_CHECKPOINTS_NOT_MUTATED"
echo "MINUTE_STATUS=$STATE/snapshot.json"
