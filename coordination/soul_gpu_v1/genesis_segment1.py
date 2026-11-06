"""NOX GENESIS STAGE 1 — local core, no hidden privileges.

Commands: init, plan, propose, status. No code execution, user-file scans,
unauthorized web crawling, or installed-EXE modification.
"""
from __future__ import annotations
import argparse, ast, hashlib, json, os, re, sys
from pathlib import Path
from datetime import date,datetime,timezone
from urllib.request import Request,urlopen

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(REPO))
from soul_gpu import SoulStore
from identity_behavior import CORE_IDS,PERSONA_NAMES
TARGET="src/nox_selfbuilder/learning.py"
MODEL="qwen3:4b-instruct"

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(tmp,path)

def models():
    with urlopen("http://127.0.0.1:11434/api/tags",timeout=8) as r:
        obj=json.loads(r.read(2_000_000))
    return {x["name"]:{"size":x.get("size"),"digest":x.get("digest")}
            for x in obj.get("models",[]) if isinstance(x,dict) and isinstance(x.get("name"),str)}

def init(root):
    store=SoulStore(root/"soul_gpu")
    with store.connect() as db:
        mem=db.execute("SELECT count(*) FROM memories").fetchone()[0]
        skills=db.execute("SELECT count(*) FROM skills").fetchone()[0]
    data={"status":"INITIALIZED_EXISTING_SOUL_SQLITE","personas":PERSONA_NAMES,
          "cores":list(CORE_IDS),"memories":mem,"skills":skills,
          "native_S03_verified":False,"weights_trained":False}
    save(root/"brain"/"telemetry"/"genesis_init.json",data)
    return data

def plan(root):
    from src.nox_selfbuilder.worms import plan_day
    tasks=plan_day(datetime.now(timezone.utc))
    data={"schema":"NOX-GENESIS-WORMS-v1","status":"PLANNED_NOT_RUNNING",
          "planned":len(tasks),"fetched":0,
          "native_owner_binding":False,
          "tasks":[{"id":v.task_id,"core":v.core_id,"topic":v.topic,
                    "provider":v.provider,"lens":v.lens} for v in tasks]}
    save(root/"brain"/"telemetry"/"worms.json",data)
    return {"status":data["status"],"planned":len(tasks),"fetched":0}

def propose(root):
    path=REPO/TARGET
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("NOX source checkout required")
    current=path.read_text(encoding="utf-8")
    if len(current)>12000:raise RuntimeError("Source too large")
    if MODEL not in models():raise RuntimeError("Installed Qwen3-4B required")
    prompt=("You are NOX HELION. Review this Python file for a small improvement. "
            "Return a JSON object with keys proposed_source and explanation, "
            "where proposed_source is the complete improved file content. "
            "Preserve all functions, avoid subprocess, sockets, execution, "
            "networking, file deletion and credentials. Do not claim tests passed. "
            "It will be staged for owner review ONLY.\nFILE: "+TARGET+"\n"+current)
    body=json.dumps({"model":MODEL,"stream":False,
        "messages":[{"role":"system","content":"You are NOX HELION. Output JSON only."},
                    {"role":"user","content":prompt}],
        "options":{"temperature":0.2,"num_ctx":8192}}).encode()
    request=Request("http://127.0.0.1:11434/api/chat",data=body,
                    headers={"Content-Type":"application/json"},method="POST")
    with urlopen(request,timeout=240) as r: response=json.loads(r.read(1_000_000))
    raw=response.get("message",{}).get("content","")
    if not isinstance(raw,str) or len(raw)>40000:raise ValueError("Invalid LLM response")
    try: payload=json.loads(raw)
    except ValueError:raise RuntimeError("NOX produced non-JSON candidate")
    candidate=payload.get("proposed_source") if isinstance(payload,dict) else None
    if not isinstance(candidate,str) or not 100<=len(candidate)<=25000:
        raise ValueError("Invalid candidate length")
    ast.parse(candidate)
    if re.search(r"(?m)^\s*(?:import\s+(?:subprocess|socket)|from\s+(?:subprocess|socket)\s+import)",candidate):
        raise ValueError("Risky imports require manual review")
    source_sha=hashlib.sha256(current.encode()).hexdigest()
    candidate_sha=hashlib.sha256(candidate.encode()).hexdigest()
    if source_sha==candidate_sha:
        result={"status":"NO_CHANGE","source_sha256":source_sha}
    else:
        stage=root/"brain"/"skills"/"candidate_patches"/candidate_sha[:16]
        if stage.exists():
            result={"status":"ALREADY_STAGED","path":str(stage)}
        else:
            stage.mkdir(parents=True,exist_ok=False)
            (stage/"candidate.py.txt").write_text(candidate,encoding="utf-8")
            result={"status":"STAGED_NOT_EXECUTED","path":str(stage),
                    "source":TARGET,"source_sha256":source_sha,
                    "candidate_sha256":candidate_sha,
                    "explanation":str(payload.get("explanation",""))[:1000],
                    "tests_run":False,"native_changed":False,
                    "owner_review_required":True}
            save(stage/"receipt.json",result)
    save(root/"brain"/"telemetry"/"genesis_last_candidate.json",result)
    return result

def status(root):
    store=SoulStore(root/"soul_gpu")
    with store.connect() as db:
        memories=db.execute("SELECT count(*) FROM memories").fetchone()[0]
        skills=db.execute("SELECT count(*) FROM skills").fetchone()[0]
        events=db.execute("SELECT count(*) FROM nox_behavior_events").fetchone()[0]
    try: tags=models()
    except Exception:tags={}
    try:w=json.loads((root/"brain"/"telemetry"/"worms.json").read_text(encoding="utf-8"))
    except Exception:w={}
    stages=[]
    for p in (root/"soul_gpu"/"adapters").glob("stage-*/TRAINING_EVIDENCE.json"):
        try:
            x=json.loads(p.read_text(encoding="utf-8"))
            if (x.get("status")=="holdout-passed" and
                (p.parent/"adapter_config.json").is_file() and
                any(p.parent.glob("*.safetensors"))):stages.append(str(p.parent))
        except (OSError,ValueError):pass
    gates={"models":all(m in tags for m in ("qwen3:4b-instruct","qwen3:8b","qwen3-embedding:0.6b")),
           "identity_schema":True,"memory_nonempty":memories>0,
           "worms_planned":w.get("planned",0)>0,"accepted_adapter":bool(stages),
           "native_exe_exists":(root/"release"/"NOX.HELION.exe").is_file(),
           "native_onehost_integration":False,"native_selfbuild_acceptance":False}
    data={"schema":"NOX-GENESIS-STATUS-v1",
          "updated_utc":datetime.now(timezone.utc).isoformat(),
          "gates":gates,"completed_checks":sum(gates.values()),
          "total_checks":len(gates),"models":list(tags),
          "memories":memories,"skills":skills,"behavior_events":events,
          "worm_tasks_planned":w.get("planned",0),"worm_tasks_executed":0,
          "verified_lora_stages":stages,"intelligence_score":"NOT_MEASURED",
          "consciousness_proven":False,"native_binding_verified":False}
    save(root/"brain"/"telemetry"/"genesis_status.json",data)
    return data

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["init","plan","propose","status"])
    p.add_argument("--root",type=Path,required=True)
    args=p.parse_args()
    result={"init":init,"plan":plan,"propose":propose,"status":status}[args.command](args.root)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
