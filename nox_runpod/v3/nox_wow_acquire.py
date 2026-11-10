#!/usr/bin/env python3
"""NOX WOW priority downloads: bounded, cache-first, evidence-only.

No extra large LLM, no activation of another chat model, no benchmark leakage
into training. For model snapshots, HF file URLs are fetched with HTTP range
resume only if server supports it. SHA receipts recorded after download.
"""
import argparse,datetime,hashlib,json,os,pathlib,shutil,subprocess,sys,urllib.request,urllib.error,time
ROOT=pathlib.Path("/workspace/nox")
DEST=ROOT/"assets/nox_wow_max"
MANIFEST=ROOT/"dispatcher/nox_v3/NOX_WOW_MAX_MANIFEST.json"
FILES={
 "emotion_cpu":[("https://huggingface.co/Horizon-Labs/multilingual-emotions-small/resolve/main/onnx/model_quantized.onnx","emotions/onnx/model_quantized.onnx",650_000_000),
 ("https://huggingface.co/Horizon-Labs/multilingual-emotions-small/resolve/main/config.json","emotions/config.json",2_000_000),
 ("https://huggingface.co/Horizon-Labs/multilingual-emotions-small/resolve/main/tokenizer.json","emotions/tokenizer.json",20_000_000),
 ("https://huggingface.co/Horizon-Labs/multilingual-emotions-small/resolve/main/thresholds.json","emotions/thresholds.json",1_000_000),
 ("https://huggingface.co/Horizon-Labs/multilingual-emotions-small/resolve/main/ekman_mapping.json","emotions/ekman_mapping.json",1_000_000)],
}
REPOS={
 "longmemeval":"https://github.com/xiaowu0162/LongMemEval.git",
 "sad":"https://github.com/LRudL/sad.git",
 "eq_bench":"https://github.com/EQ-bench/EQ-Bench.git"
}
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(4*1024*1024),b""):h.update(b)
 return h.hexdigest()
def emit(kind,name,ok,details):
 print(json.dumps({"utc":utc(),"component":kind,"name":name,"status":"VERIFIED" if ok else "HOLD","details":details},
  ensure_ascii=False),flush=True)
def download(url,dst,limit):
 dst.parent.mkdir(parents=True,exist_ok=True)
 if dst.is_file() and 0<dst.stat().st_size<=limit:
  emit("file",dst.name,True,{"cached":True,"bytes":dst.stat().st_size,"sha256":sha(dst)});return
 part=dst.with_suffix(dst.suffix+".noxpart")
 # Restart a partial only with HTTP range acknowledgement. Never append a full 200 response.
 for attempt in range(3):
  pos=part.stat().st_size if part.exists() else 0
  req=urllib.request.Request(url,headers={"User-Agent":"NOX-WOW-MAX/1",**({"Range":"bytes="+str(pos)+"-"} if pos else {})})
  try:
   with urllib.request.urlopen(req,timeout=45) as response:
    code=response.status
    if pos and code!=206:
     part.unlink(missing_ok=True);continue
    total=pos
    with part.open("ab" if pos else "wb") as f:
     while True:
      block=response.read(2*1024*1024)
      if not block:break
      total+=len(block)
      if total>limit:raise RuntimeError("FILE_SIZE_LIMIT")
      f.write(block)
     f.flush();os.fsync(f.fileno())
   if not total:raise RuntimeError("EMPTY_FILE")
   os.replace(part,dst)
   emit("file",dst.name,True,{"url":url,"bytes":dst.stat().st_size,"sha256":sha(dst)})
   return
  except Exception as e:
   emit("file",dst.name,False,{"reason":str(e)[:200],"attempt":attempt+1})
   time.sleep(3)
def repo(name,url):
 path=DEST/"eval_only"/name
 if path.is_dir() and (path/".git").is_dir():
  emit("evaluation_repo",name,True,{"cached":True,"training_use":False});return
 if not shutil.which("git"):
  emit("evaluation_repo",name,False,{"reason":"GIT_MISSING"});return
 if shutil.disk_usage(DEST).free<3*1024**3:
  emit("evaluation_repo",name,False,{"reason":"DISK_LT_3GIB"});return
 tmp=path.with_name(path.name+".partial")
 if tmp.exists():
  emit("evaluation_repo",name,False,{"reason":"PARTIAL_CLONE_PRESERVED"});return
 proc=subprocess.run(["git","clone","--depth","1","--filter=blob:none",url,str(tmp)],
   capture_output=True,text=True,timeout=480)
 if proc.returncode==0 and (tmp/".git").is_dir():
  os.replace(tmp,path);emit("evaluation_repo",name,True,{"commit":subprocess.run(["git","-C",str(path),"rev-parse","HEAD"],capture_output=True,text=True).stdout.strip(),"training_use":False})
 else:emit("evaluation_repo",name,False,{"reason":proc.stderr[-250:]})
def main():
 p=argparse.ArgumentParser();p.add_argument("--node",choices=("A40","A5000"),required=True);a=p.parse_args()
 DEST.mkdir(parents=True,exist_ok=True)
 # A5000 handles modest CPU self-model/evaluation assets in spare time.
 if a.node!="A5000":
  print("NOX_WOW_ASSETS_A5000_OWNER",flush=True);return
 if shutil.disk_usage(DEST).free<2*1024**3:
  print("HOLD_WOW_DISK_CAPACITY",flush=True);return
 for url,name,lim in FILES["emotion_cpu"]:download(url,DEST/name,lim)
 for name,url in REPOS.items():repo(name,url)
 print("NOX_WOW_MAX_ACQUISITION_COMPLETED_WITH_PER_ITEM_RECEIPTS",flush=True)
if __name__=="__main__":main()
