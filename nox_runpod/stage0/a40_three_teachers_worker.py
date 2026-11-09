#!/usr/bin/env python3
"""Three concurrent teacher inference lanes with adaptive GPU layer budgets.
Outputs training examples with provenance, never modifies NOX 9B weights.
"""
import argparse,datetime,hashlib,json,os,pathlib,random,subprocess,sys,time
P=pathlib.Path("/workspace/nox")
P.mkdir(exist_ok=True,parents=True)
QUESTIONS=[
("memory","Design a verifiable episodic and semantic memory system for a local AI: provenance, creator-provided data, timeline, update and rollback."),
("self_model","Design a functional self-model with capability monitoring, uncertainty tracking and explicit distinction from subjective consciousness."),
("reasoning","Solve a difficult multi-step reasoning problem and describe a method for verifying the answer and preventing hallucinations."),
("reflection","Design an error-correction loop for an autonomous coding agent with tests, change control, STOP and rollback."),
("multilingual","Explain sophisticated technical concepts in Russian and Spanish while preserving meaning."),
("distillation","Plan teacher-student distillation with holdout benchmarks, catastrophic forgetting checks and correct provenance."),
("long_term","Compare multi-frequency memory, retrieval, episodic timelines and continual learning in autonomous assistants."),
("skills","Generate a concise technical exercise for Python, algorithms, mathematics and systems programming with verification.")
]
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--id",required=True)
 ap.add_argument("--model",required=True)
 ap.add_argument("--gpu-layers",type=int,default=0)
 ap.add_argument("--cli",default="/opt/llama.cpp/build/bin/llama-cli")
 ap.add_argument("--passes",type=int,default=1)
 a=ap.parse_args()
 model=pathlib.Path(a.model)
 assert model.is_file() and model.stat().st_size>2_000_000_000,"model is not available"
 cli=pathlib.Path(a.cli)
 assert cli.is_file(),"llama-cli unavailable"
 out=P/"distillation"/("nox_teacher_"+a.id+".jsonl")
 out.parent.mkdir(parents=True,exist_ok=True)
 log=P/"dispatcher"/"a40"
 log.mkdir(parents=True,exist_ok=True)
 done=set()
 if out.exists():
  for line in out.read_text(encoding="utf-8").splitlines():
   try:done.add(json.loads(line)["id"])
   except Exception:pass
 for cycle in range(int(os.environ.get("NOX_CYCLE","0")),int(os.environ.get("NOX_CYCLE","0"))+a.passes):
  for topic,q in QUESTIONS:
   prompt=q+" Respond with a useful grounded educational example and explicit limitations."
   ident=hashlib.sha256((a.id+"|"+str(cycle)+"|"+topic+"|"+prompt).encode()).hexdigest()[:20]
   if ident in done:continue
   if (log/"STOP").exists():return
   cmd=[str(cli),"-m",str(model),"-p",prompt,"-c","1024","-n","450","-ngl",str(a.gpu_layers),"-t","3","--no-display-prompt"]
   try:r=subprocess.run(cmd,capture_output=True,text=True,timeout=480)
   except subprocess.TimeoutExpired:
    print(json.dumps({"event":"TEACHER_TIMEOUT","teacher":a.id,"topic":topic}),flush=True)
    continue
   if r.returncode!=0:
    print(json.dumps({"event":"TEACHER_FAILURE","teacher":a.id,"code":r.returncode,"stderr":r.stderr[-400:]}),flush=True)
    time.sleep(20);continue
   txt=r.stdout.strip()
   if len(txt)<100:continue
   row={"id":ident,"teacher":a.id,"topic":topic,"text":txt,"verified":"SYNTHETIC_NOT_FACT_CHECKED",
         "utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"model":model.name}
   with out.open("a",encoding="utf-8") as f:
    f.write(json.dumps(row,ensure_ascii=False)+"\n");f.flush();os.fsync(f.fileno())
   done.add(ident)
   print(json.dumps({"event":"TEACHER_EXAMPLE_SAVED","teacher":a.id,"topic":topic,"total":len(done)}),flush=True)
 print(json.dumps({"event":"TEACHER_LANE_COMPLETE","teacher":a.id,"examples":len(done)}),flush=True)
if __name__=="__main__":main()
