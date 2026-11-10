#!/usr/bin/env python3
"""One bounded GGUF teacher batch for NOX PRIME V3. No student weights touched.

Requires a real GGUF model, source proof, and a llama.cpp CLI installed on A40.
Generates traceable teacher text into the existing S03 importer path. Models
are never relabeled; 9B fallback is forbidden for 27B/32B.
"""
import argparse, datetime, fcntl, hashlib, json, os, pathlib, shutil, subprocess, sys, time

ROOT=pathlib.Path("/workspace/nox")
OUT=ROOT/"distillation"
STATE=ROOT/"dispatcher/nox_v3"
MODELS={
    "Qwen3.5-27B": ROOT/"teachers/Qwen3.5-27B/Qwen3.5-27B-Q4_K_M.gguf",
    "DeepSeek-R1-Distill-Qwen-32B": ROOT/"teachers/DeepSeek-R1-Distill-Qwen-32B/model.gguf",
}
TOPICS=[
    "Create a rigorous numerical reasoning problem with a complete checked solution",
    "Solve a challenging Python engineering problem and design edge-case tests",
    "Explain a scientific hypothesis with falsifiable experiments",
    "Critique an argument and identify uncertainties and assumptions",
    "Develop an algorithm with complexity analysis and correctness checks",
    "Derive a mathematical result and independently verify each step",
    "Design robust long-term memory with provenance and correction records",
    "Explain a difficult topic in Russian and Spanish without hallucination",
    "Propose a secure software change with rollback and safety properties",
    "Evaluate conflicting evidence and state what is not known",
    "Compare two reasoning strategies on a concrete hard problem",
    "Find subtle code bugs with reproducible tests and minimal patches",
    "Explain causal inference versus correlation with a detailed example",
    "Create a knowledge-retrieval task and a verifiable reference answer",
    "Design a benchmark question to assess forgetting after fine-tuning",
    "Formulate a multi-step planning problem with explicit constraints",
    "Explain a physics problem with dimensional and numeric validation",
    "Review a database schema for reliability and data-loss hazards",
    "Design a transparent agent self-model without claiming subjective awareness",
    "Create a practical tool-use plan with explicit success criteria",
]
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b""):h.update(chunk)
    return h.hexdigest()
def atomic(path,doc):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    with tmp.open("w",encoding="utf-8") as f:
        json.dump(doc,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--teacher",required=True,choices=sorted(MODELS))
    p.add_argument("--limit",type=int,default=2)
    p.add_argument("--ctx",type=int,default=4096)
    p.add_argument("--gpu-layers",type=int,default=20)
    a=p.parse_args()
    if not 1<=a.limit<=10 or not 512<=a.ctx<=8192 or not 0<=a.gpu_layers<=50:
        raise SystemExit("INVALID_BOUNDED_ARGUMENT")
    OUT.mkdir(parents=True,exist_ok=True);STATE.mkdir(parents=True,exist_ok=True)
    lock=(STATE/"teacher_gpu.lock").open("a+")
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: print("HOLD_TEACHER_GPU_ALREADY_OWNED",flush=True);return 2
    model=MODELS[a.teacher]
    proof=model.parent/"nox_teacher_proof.json"
    if not model.is_file() or not proof.is_file():
        print("HOLD_MODEL_OR_SHA_PROOF_MISSING",a.teacher,model,flush=True);return 2
    meta=json.loads(proof.read_text())
    if meta.get("teacher")!=a.teacher or meta.get("model_file")!=model.name or meta.get("status")!="SHA256_VERIFIED_SHARED":
        print("HOLD_PROVENANCE_MISMATCH",flush=True);return 2
    if model.stat().st_size!=meta.get("bytes"):
        print("HOLD_MODEL_SIZE_MISMATCH",flush=True);return 2
    # Recalculate hash on first run of each model revision, then cache based on stat identity.
    cache=STATE/("verified_"+hashlib.sha256(str(model).encode()).hexdigest()[:12]+".json")
    identity={"size":model.stat().st_size,"mtime_ns":model.stat().st_mtime_ns,"expected_sha":meta["sha256"]}
    try: cached=json.loads(cache.read_text())
    except (OSError,ValueError):cached={}
    if any(cached.get(k)!=v for k,v in identity.items()):
        if sha(model)!=meta["sha256"]:
            print("HOLD_MODEL_SHA256_MISMATCH",flush=True);return 2
        atomic(cache,identity)
    cli=shutil.which("llama-cli")
    if not cli:
        print("HOLD_LLAMA_CPP_CLI_MISSING_INSTALL_RUNTIME_FIRST",flush=True);return 2
    # No teacher inference may overlap a full-parameter trainer on the same A40.
    for proc in pathlib.Path("/proc").iterdir():
        if not proc.name.isdigit():continue
        try:
            args=(proc/"cmdline").read_bytes().split(bytes([0]))
            if any(b"a40_full_parameter_distill_cycle.py" in token for token in args[1:]):
                print("HOLD_FULL_PARAMETER_TRAINER_RUNNING",proc.name,flush=True);return 2
        except OSError:pass
    out=OUT/("NOX_V3_"+("QWEN27B" if a.teacher=="Qwen3.5-27B" else "DEEPSEEK32B")+"_TEACHER.jsonl")
    existing=set()
    if out.is_file():
        with out.open(encoding="utf-8",errors="replace") as f:
            for line in f:
                try:existing.add(json.loads(line)["id"])
                except (ValueError,KeyError,TypeError):pass
    done=0
    for idx in range(100):
        if done>=a.limit:break
        prompt=TOPICS[idx%len(TOPICS)]+". Variant "+str(idx//len(TOPICS)+1)+": give a distinct verified example, explicit reasoning, tests, and limitations."
        ident=hashlib.sha256((a.teacher+"|V3|"+str(idx)+"|"+prompt).encode()).hexdigest()
        if ident in existing:continue
        argv=[cli,"-m",str(model),"-p",prompt,"-n","480","-c",str(a.ctx),"-ngl",str(a.gpu_layers),"--temp","0.2"]
        try:
            result=subprocess.run(argv,capture_output=True,text=True,timeout=900,check=False)
        except subprocess.TimeoutExpired:
            print("HOLD_TEACHER_TIMEOUT",idx,flush=True);break
        if result.returncode!=0:
            print("HOLD_TEACHER_RUNTIME_ERROR",result.returncode,result.stderr[-400:],flush=True);break
        answer=result.stdout.strip()
        if answer.startswith(prompt):answer=answer[len(prompt):].strip()
        if not 100<=len(answer)<=4000:
            print("HOLD_OUTPUT_LENGTH",idx,len(answer),flush=True);break
        rec={"id":ident,"task_id":idx,"teacher":a.teacher,"source_model":str(model),
             "model_sha256":meta["sha256"],"prompt":prompt,"text":answer,
             "content_sha":hashlib.sha256(answer.encode()).hexdigest(),
             "method":"VERIFIED_MODEL_GGUF_GENERATION","quality":"NOT_INDEPENDENTLY_FACT_CHECKED",
             "created_at":utc()}
        with out.open("a",encoding="utf-8") as f:
            f.write(json.dumps(rec,ensure_ascii=False)+"\n");f.flush();os.fsync(f.fileno())
        done+=1;existing.add(ident)
        print("NOX_V3_TEACHER_EXAMPLE_SAVED",a.teacher,idx+1,"of 100",flush=True)
    print("NOX_V3_BATCH_END",a.teacher,"new",done,"distinct",len(existing),flush=True)
    return 0
if __name__=="__main__":sys.exit(main())
