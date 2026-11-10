#!/usr/bin/env python3
"""GPU teacher batch with one model load per batch via llama-server.

Provenance-gated, local HTTP only. No teacher switching or student weight claims.
"""
import argparse,datetime,fcntl,hashlib,json,os,pathlib,shutil,subprocess,sys,time,urllib.request,urllib.error,socket
R=pathlib.Path("/workspace/nox")
D=R/"dispatcher/nox_v3"
OUT=R/"distillation"
MODELS={
 "Qwen3.5-27B":R/"teachers/Qwen3.5-27B/Qwen3.5-27B-Q4_K_M.gguf",
 "DeepSeek-R1-Distill-Qwen-32B":R/"teachers/DeepSeek-R1-Distill-Qwen-32B/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf"
}
TOPICS=[
 "Develop a rigorous multi-step mathematical problem and check its solution",
 "Solve a nontrivial Python programming challenge with tests",
 "Evaluate conflicting scientific hypotheses and evidence",
 "Create a safety-focused software repair and rollback plan",
 "Explain causal inference and confounding with a concrete example",
 "Write a detailed Russian-Spanish technical explanation",
 "Plan a reproducible experiment and independent quality check",
 "Formulate a reasoning puzzle with an unambiguous answer",
 "Analyze an unfamiliar algorithm and its computational complexity",
 "Design long-term autobiographical memory with explicit provenance",
 "Correct a flawed inference and explain the error",
 "Develop a robust computer-control policy with explicit authorization",
 "Propose a data pipeline with idempotency, consistency and rollback",
 "Design a code review protocol with adversarial tests",
 "Solve a physics problem with dimensional and numerical checks",
 "Create an evaluation benchmark that resists memorization",
 "Compare alternatives under conflicting operational constraints",
 "Explain uncertainty calibration on a real-world numerical example",
 "Evaluate a set of unit tests for coverage gaps",
 "Write an original, well-structured technical lesson with examples"
]
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(8*1024*1024),b""):h.update(b)
 return h.hexdigest()
def atom(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix(".tmp")
 with tmp.open("w",encoding="utf-8") as f:
  json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def http_json(url,payload=None,timeout=15):
 data=None if payload is None else json.dumps(payload).encode()
 req=urllib.request.Request(url,data=data,headers={"Content-Type":"application/json"})
 with urllib.request.urlopen(req,timeout=timeout) as resp:
  return json.loads(resp.read(4*1024*1024))
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--teacher",choices=tuple(MODELS),required=True)
 ap.add_argument("--limit",type=int,default=10)
 ap.add_argument("--gpu-layers",type=int,default=30)
 ap.add_argument("--ctx",type=int,default=4096)
 args=ap.parse_args()
 if not 1<=args.limit<=20 or not 0<=args.gpu_layers<=50 or not 1024<=args.ctx<=8192:
  raise SystemExit("INVALID_BOUNDED_REQUEST")
 model=MODELS[args.teacher]
 proof=model.parent/"nox_teacher_proof.json"
 if not model.is_file() or not proof.is_file():
  print("HOLD_TEACHER_MODEL_OR_PROOF_MISSING",args.teacher,flush=True);return 2
 p=json.loads(proof.read_text())
 if p.get("teacher")!=args.teacher or p.get("model_file")!=model.name or p.get("status")!="SHA256_VERIFIED_SHARED":
  print("HOLD_UNVERIFIED_TEACHER_PROVENANCE",flush=True);return 2
 if model.stat().st_size!=p.get("bytes"):
  print("HOLD_MODEL_SIZE_CHANGED",flush=True);return 2
 D.mkdir(parents=True,exist_ok=True)
 lock=(D/"teacher_gpu.lock").open("a+")
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:print("HOLD_TEACHER_GPU_OWNED",flush=True);return 2
 digest_cache=D/("model_"+hashlib.sha256(str(model).encode()).hexdigest()[:12]+".json")
 expected={"bytes":model.stat().st_size,"mtime_ns":model.stat().st_mtime_ns,"sha256":p["sha256"]}
 try: old=json.loads(digest_cache.read_text())
 except (OSError,ValueError):old={}
 if old!=expected:
  if sha(model)!=p["sha256"]:raise SystemExit("HOLD_MODEL_SHA256_WRONG")
  atom(digest_cache,expected)
 server=shutil.which("llama-server")
 if not server:
  candidate=R/"tools/llama.cpp/build/bin/llama-server"
  if candidate.is_file():server=str(candidate)
 if not server:
  print("HOLD_LLAMA_SERVER_MISSING",flush=True);return 2
 # Run server only on loopback. Never stop a server we did not launch.
 host="127.0.0.1";port=18931
 sock=socket.socket()
 try:
  if sock.connect_ex((host,port))==0:
   print("HOLD_PORT_IN_USE",port,flush=True);return 2
 finally:sock.close()
 outfile=OUT/("NOX_V3_QWEN27B_TEACHER.jsonl" if args.teacher=="Qwen3.5-27B" else "NOX_V3_DEEPSEEK32B_TEACHER.jsonl")
 existing=set()
 if outfile.is_file():
  with outfile.open(encoding="utf-8",errors="replace") as f:
   for line in f:
    try:existing.add(json.loads(line)["id"])
    except (ValueError,KeyError,TypeError):pass
 OUT.mkdir(parents=True,exist_ok=True)
 log=R/"logs"/("NOX_V3_SERVER_"+("27B" if args.teacher=="Qwen3.5-27B" else "32B")+".log")
 log.parent.mkdir(parents=True,exist_ok=True)
 started=time.monotonic()
 with log.open("ab") as logf:
  cmd=[server,"-m",str(model),"-ngl",str(args.gpu_layers),"-c",str(args.ctx),
       "--host",host,"--port",str(port)]
  proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=logf,stderr=subprocess.STDOUT,start_new_session=True)
  try:
   ready=False
   for _ in range(90):
    if proc.poll() is not None:break
    try:
     health=http_json("http://127.0.0.1:"+str(port)+"/health",timeout=3)
     if health.get("status") in ("ok","no slot available"):
      ready=True;break
    except (OSError,ValueError,urllib.error.URLError):pass
    time.sleep(2)
   if not ready:
    print("HOLD_TEACHER_SERVER_NOT_READY",args.teacher,flush=True);return 2
   done=0;tokens=0
   for index in range(100):
    if done>=args.limit:break
    prompt=TOPICS[index%len(TOPICS)]+". Variant "+str(index//len(TOPICS)+1)+": provide a concrete, accurate original response with independent validation steps."
    ident=hashlib.sha256((args.teacher+"|V3|"+str(index)+"|"+prompt).encode()).hexdigest()
    if ident in existing:continue
    payload={"prompt":prompt,"n_predict":400,"temperature":0.2,"top_p":0.9,"stream":False}
    try:res=http_json("http://127.0.0.1:"+str(port)+"/completion",payload,timeout=300)
    except (OSError,ValueError,urllib.error.URLError) as e:
     print("HOLD_INFERENCE_REQUEST",type(e).__name__,flush=True);break
    answer=str(res.get("content") or "").strip()
    if not 100<=len(answer)<=4000:
     print("HOLD_OUTPUT_LENGTH",index,len(answer),flush=True);break
    rec={"id":ident,"task_id":index,"teacher":args.teacher,"source_model":str(model),
      "model_sha256":p["sha256"],"text":answer,"prompt":prompt,
      "content_sha":hashlib.sha256(answer.encode()).hexdigest(),
      "method":"LOCAL_GGUF_LLAMA_SERVER","quality":"NOT_INDEPENDENTLY_FACT_CHECKED","created_at":utc()}
    with outfile.open("a",encoding="utf-8") as f:
     f.write(json.dumps(rec,ensure_ascii=False)+"\n");f.flush();os.fsync(f.fileno())
    existing.add(ident);done+=1
    tokens+=int(res.get("tokens_predicted") or 0)
    print("NOX_V3_TEACHER_SAVED",args.teacher,"plan_task",index+1,"/100","new_batch",done,flush=True)
   elapsed=max(0.001,time.monotonic()-started)
   print("NOX_V3_TEACHER_BATCH",args.teacher,"examples",done,"generated_tokens",tokens,
     "overall_tokens_per_second",round(tokens/elapsed,2),flush=True)
  finally:
   # Own process only. Wait for graceful cleanup; no SIGKILL.
   if proc.poll() is None:
    proc.terminate()
    try:proc.wait(timeout=45)
    except subprocess.TimeoutExpired:
     print("HOLD_OWN_SERVER_STILL_EXITING",proc.pid,flush=True)
 return 0
if __name__=="__main__":sys.exit(main())
