#!/usr/bin/env python3
"""NOX provenance-preserving S03 memory and neural integration gate.
Imports all 3 teacher corpora. Trains an ISOLATED NOX 9B LoRA only after
a meaningful held-out set and GPU headroom, then publishes a verified adapter.
Never overwrites A5000's active checkpoints or mislabels an adapter as merged weights.
"""
import argparse,datetime,fcntl,hashlib,importlib.util,json,os,pathlib,sqlite3,sys,time,traceback,subprocess
ROOT=pathlib.Path("/workspace/nox")
DIR=ROOT/"memory/THREE_TEACHERS"
CUR=ROOT/"distillation"
STATE=ROOT/"dispatcher/a40_v4"
RUN=ROOT/"checkpoints/NOX_A40_NEURAL_INTEGRATION"
for d in (DIR,CUR,STATE,RUN):d.mkdir(exist_ok=True,parents=True)
DB=DIR/"nox_memory.sqlite3"
INPUTS={
 "qwen9":["nox_prime_9b_teacher.jsonl","nox_9b_knowledge_stage2.jsonl","nox_teacher_qwen9_A40.jsonl","nox_teacher_qwen9.jsonl"],
 "qwen27":["nox_teacher_qwen27.jsonl","nox_27b_teacher_knowledge.jsonl"],
 "deepseek32":["nox_teacher_deepseek32.jsonl"]
}
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def atom(p,data):
 q=p.with_suffix(p.suffix+".tmp")
 with q.open("w",encoding="utf-8") as f:
  json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(q,p)
def dbconn():
 c=sqlite3.connect(DB,timeout=15)
 c.execute("PRAGMA journal_mode=WAL");c.execute("PRAGMA synchronous=FULL")
 c.execute("""CREATE TABLE IF NOT EXISTS items(
 teacher TEXT NOT NULL,hash TEXT NOT NULL,source TEXT NOT NULL,source_id TEXT,
 topic TEXT,content TEXT NOT NULL,acquired TEXT NOT NULL,quality TEXT NOT NULL,
 PRIMARY KEY (teacher,hash))""")
 return c
def scan(c):
 counts={}
 with c:
  for teacher,names in INPUTS.items():
   for name in names:
    p=CUR/name
    if not p.is_file() or p.stat().st_size>450_000_000:continue
    with p.open(encoding="utf-8") as f:
     for line in f:
      if len(line)>600000:continue
      try:
       a=json.loads(line);t=str(a.get("text") or "").strip()
       if len(t)<80:continue
       orig=str(a.get("teacher") or "").lower()
       if teacher=="qwen27" and orig and "27" not in orig:continue
       if teacher=="deepseek32" and orig and "deepseek" not in orig and "32" not in orig:continue
       h=hashlib.sha256(t.encode()).hexdigest()
       c.execute("INSERT OR IGNORE INTO items VALUES(?,?,?,?,?,?,?,?)",
         (teacher,h,"distillation/"+name,str(a.get("id",""))[:140],
          str(a.get("topic",""))[:150],t,now(),"TEACHER_GENERATED_NOT_FACT_CHECKED"))
      except (ValueError,TypeError,sqlite3.Error):continue
  for teacher in INPUTS:counts[teacher]=c.execute("SELECT count(*) FROM items WHERE teacher=?",(teacher,)).fetchone()[0]
 return counts
def exports(c,counts):
 train=[];holdout=[]
 # A train/test split that's stable across restarts and deduplicated across teachers.
 used=set()
 for teacher,h,source,topic,content in c.execute("SELECT teacher,hash,source,topic,content FROM items ORDER BY teacher,hash"):
  if h in used:continue
  used.add(h)
  row={"id":h,"text":content,"teacher":teacher,"topic":topic,"source":source,"verified":False}
  if int(h[:8],16)%10==0:holdout.append(row)
  else:train.append(row)
 for name,rows in (("train",train),("holdout",holdout)):
  target=DIR/(name+".jsonl");tmp=target.with_suffix(".tmp")
  with tmp.open("w",encoding="utf-8") as f:
   for x in rows:f.write(json.dumps(x,ensure_ascii=False)+"\n")
   f.flush();os.fsync(f.fileno())
  os.replace(tmp,target)
 atom(DIR/"status.json",{"utc":now(),"teachers":counts,"train":len(train),
   "holdout":len(holdout),"verified_weight_merge":False,
   "status":"S03_KNOWLEDGE_INTEGRATED_NOT_NEURAL_WEIGHTS",
   "neural_adapter_receipt":str(RUN/"pass1/SUCCESS.json")})
 return train,holdout
def gpu_free():
 x=subprocess.check_output(["nvidia-smi","--query-gpu=memory.free,temperature.gpu","--format=csv,noheader,nounits"],text=True,timeout=10).splitlines()[0]
 return tuple(int(i.strip()) for i in x.split(","))
def train_isolated(train,holdout):
 # Refuse to claim integration if all teachers haven't contributed enough data.
 counts={t:sum(1 for a in train if a["teacher"]==t) for t in INPUTS}
 if min(counts.values())<8 or len(train)<48 or len(holdout)<8:return "WAITING_FOR_THREE_TEACHERS_48_TRAIN_8_HOLDOUT"
 if (RUN/"pass1/SUCCESS.json").is_file():return "ALREADY_TRAINED_NEEDS_EVALUATION"
 g,temp=gpu_free()
 if g<12500 or temp>=75:return "GPU_RESERVED_OR_TOO_HOT"
 base=ROOT/"models/NOX_9B_UNIFIED"
 code=ROOT/"tools/nox_prime_9b.py"
 if not (base/"NOX_UNIFIED_RECEIPT.json").is_file() or not code.is_file():return "BASE_OR_TRAINER_NOT_READY"
 # Publish a durable training snapshot, isolated from concurrently written corpora.
 corpus=RUN/"train_snapshot.jsonl"
 if not corpus.exists():
  with corpus.open("x",encoding="utf-8") as f:
   for row in train:f.write(json.dumps(row,ensure_ascii=False)+"\n")
   f.flush();os.fsync(f.fileno())
 atom(RUN/"training_manifest.json",{"utc":now(),"base":str(base),"sources":counts,
  "train_records":len(train),"heldout_records":len(holdout),
  "heldout_file":str(DIR/"holdout.jsonl"),
  "meaning":"isolated LoRA fine-tuning; no claim of full evaluated model merge"})
 import torch
 spec=importlib.util.spec_from_file_location("nox_a40_neural_trainer",str(code))
 mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
 mod.BASE=base;mod.WORK=RUN;mod.CORPUS=corpus
 tok,model=mod.load_4bit()
 try:
  mod.train(tok,model,1,512,4,16,batch_size=1)
 finally:
  del model
  torch.cuda.empty_cache()
 if not (RUN/"pass1/SUCCESS.json").exists():raise RuntimeError("TRAINING_NOT_SAVED")
 atom(RUN/"NEURAL_INTEGRATION_RECEIPT.json",
      {"status":"TRAINED_ISOLATED_LORA_NOT_BENCHMARKED_NOT_MERGED",
       "utc":now(),"base":str(base),"adapter":str(RUN/"pass1/adapter"),
       "train_records":len(train),"holdout_records":len(holdout),
       "three_teacher_provenance":counts})
 return "NEURAL_ADAPTER_SAVED"
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--role",choices=("memory","integrator"),required=True)
 a=p.parse_args()
 with (STATE/(a.role+".lock")).open("a+") as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:
   print("NOX_"+a.role.upper()+"_ALREADY_RUNNING",flush=True);return
  c=dbconn()
  while not (STATE/"STOP").exists():
   try:
    if a.role=="memory":
     counts=scan(c);train,holdout=exports(c,counts)
     state={"utc":now(),"event":"NOX_THREE_TEACHER_S03_MEMORY","counts":counts,"train":len(train),"holdout":len(holdout)}
    else:
     trainpath=DIR/"train.jsonl";testpath=DIR/"holdout.jsonl"
     train=[json.loads(x) for x in trainpath.read_text(encoding="utf-8").splitlines()] if trainpath.exists() else []
     holdout=[json.loads(x) for x in testpath.read_text(encoding="utf-8").splitlines()] if testpath.exists() else []
     outcome=train_isolated(train,holdout)
     state={"utc":now(),"event":"NOX_NEURAL_INTEGRATOR","train":len(train),"holdout":len(holdout),"neural_status":outcome}
    atom(STATE/(a.role+"_status.json"),state)
    print(json.dumps(state,ensure_ascii=False),flush=True)
   except Exception as e:
    print(json.dumps({"event":"NOX_"+a.role.upper()+"_EXCEPTION","reason":str(e)[:300],
      "trace":traceback.format_exc()[-700:]}),flush=True)
   if a.role=="memory":c.execute("PRAGMA wal_checkpoint(PASSIVE)")
   for _ in range(60):
    if (STATE/"STOP").exists():break
    time.sleep(1)
if __name__=="__main__":main()
