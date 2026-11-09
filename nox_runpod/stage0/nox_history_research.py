#!/usr/bin/env python3
"""NOX: durable self-history + research evidence, no private/S03 harvesting.
This creates a traceable knowledge source corpus, not autonomous retraining.
"""
import hashlib,json,pathlib,urllib.request,datetime,os
R=pathlib.Path("/workspace/nox")
OUT=R/"memory/nox_stage2_research"
OUT.mkdir(parents=True,exist_ok=True)
LINKS=[
("PyTorch training", "https://pytorch.org/tutorials/beginner/basics/optimization_tutorial.html"),
("Hugging Face PEFT", "https://huggingface.co/docs/peft/index"),
("Hugging Face Transformers", "https://huggingface.co/docs/transformers/index"),
("RunPod Pods", "https://docs.runpod.io/pods/overview"),
]
def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
 return h.hexdigest()
def append(path,row):
 with path.open("a",encoding="utf-8") as f:
  f.write(json.dumps(row,ensure_ascii=False)+"\n");f.flush();os.fsync(f.fileno())
def main():
 now=datetime.datetime.now(datetime.timezone.utc).isoformat()
 history=OUT/"history.jsonl"
 records=[]
 for label,file in [
  ("Embryo manifest",R/"embryo/NOX_EMBRYO_TRANSFER_STAGE/embryo_manifest.json"),
  ("Inherited 9B weight manifest",R/"models/NOX_PRIME_9B_INHERITED/transfer_manifest.json"),
  ("First merged NOX 9B receipt",R/"models/NOX_9B_UNIFIED/NOX_UNIFIED_RECEIPT.json"),
  ("Stage 2 knowledge result",R/"models/NOX_9B_KNOWLEDGE_UNIFIED/NOX_UNIFIED_RECEIPT.json")]:
  if file.is_file():
   records.append({"event":"NOX_VERIFIED_ARTIFACT","utc":now,"label":label,
                   "path":str(file),"sha256":sha(file),"bytes":file.stat().st_size})
 for r in records:append(history,r)
 research=OUT/"research.jsonl"
 seen=set()
 if research.exists():
  for line in research.read_text(encoding="utf-8").splitlines():
   try:seen.add(json.loads(line)["url"])
   except (ValueError,KeyError):pass
 for label,url in LINKS:
  if url in seen:continue
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"NOX-HELION-Research/1.0"})
   with urllib.request.urlopen(req,timeout=18) as f:
    blob=f.read(100000)
   append(research,{"title":label,"url":url,"utc":now,
                    "source_sha256":hashlib.sha256(blob).hexdigest(),
                    "excerpt":blob.decode("utf-8","replace")[:12000],
                    "verification":"PUBLIC_UNTRUSTED_SOURCE_NOT_INSTRUCTION"})
  except Exception as ex:
   append(OUT/"research_errors.jsonl",{"url":url,"utc":now,"error":type(ex).__name__})
 print(json.dumps({"event":"NOX_HISTORY_AND_RESEARCH_ARCHIVED","history_records":len(records),
 "research_path":str(research),"history_path":str(history)}),flush=True)
if __name__=="__main__":main()
