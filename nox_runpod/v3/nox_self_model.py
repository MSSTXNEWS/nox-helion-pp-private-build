#!/usr/bin/env python3
"""NOX PRIME factual self-model and an append-only historical genesis ledger.

No automatic claim of subjective consciousness or of fully absorbed teachers.
Self-report is grounded in the canonical WOW50 registry, local receipts and S03.
"""
import datetime, hashlib, json, os, pathlib, sqlite3, sys
ROOT=pathlib.Path("/workspace/nox")
S03=ROOT/"memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3"
OUT=ROOT/"memory/NOX_SELF_MODEL"
REGISTRY=ROOT/"dispatcher/nox_v3/NOX_WOW50_IDENTITY.json"
CHECKPOINTS=pathlib.Path("/opt/nox_full_parameter_A40")
STATUS=ROOT/"dispatcher/nox_v3/status.json"

def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except (OSError,ValueError):return {}
def atom(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_suffix(".tmp")
    with t.open("w",encoding="utf-8") as f:
        json.dump(x,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(t,p)
def canon(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
def digest(x):return hashlib.sha256(canon(x)).hexdigest()
def append_one(event):
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/"genesis_ledger.jsonl"
    last="0"*64
    seen=set()
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                old=json.loads(line)
                if old.get("previous_hash")!=last or old.get("entry_hash")!=digest({k:v for k,v in old.items() if k!="entry_hash"}):
                    raise RuntimeError("HOLD_LEDGER_CHAIN_INVALID")
                last=old["entry_hash"];seen.add(old["event_id"])
    if event["event_id"] in seen:return
    record={**event,"recorded_utc":utc(),"previous_hash":last}
    record["entry_hash"]=digest(record)
    with path.open("ab") as f:
        f.write(canon(record)+b"\n");f.flush();os.fsync(f.fileno())
def s03_counts():
    if not S03.exists():return {}
    try:
        conn=sqlite3.connect("file:"+str(S03)+"?mode=ro",uri=True,timeout=5)
        try:return dict(conn.execute("SELECT teacher,COUNT(*) FROM knowledge GROUP BY teacher").fetchall())
        finally:conn.close()
    except sqlite3.Error:return {}
def verified_checkpoints():
    arr=[]
    for receipt in sorted(CHECKPOINTS.glob("NOX_FULL_CYCLE_*/NOX_FULL_TRAIN_RECEIPT.json")):
        try:
            r=read(receipt)
            if not isinstance(r.get("shards"),list) or not r["shards"]:continue
            files_ok=all((receipt.parent/s["file"]).is_file() and
                  (receipt.parent/s["file"]).stat().st_size==int(s.get("bytes",s.get("size",-1))) for s in r["shards"])
            if not files_ok:continue
            accepted=float(r.get("after_holdout_loss",1e9))<=1.05*float(r.get("baseline_holdout_loss",0))
            arr.append({"cycle":r.get("cycle"),"steps":r.get("steps"),
                        "parameter_count":r.get("parameter_count"),"teacher_counts":r.get("teacher_counts"),
                        "optimizer_steps_by_teacher":r.get("optimizer_steps_by_teacher"),
                        "checkpoint_path":str(receipt.parent),"size_checks_pass":True,
                        "holdout_accepted":accepted,"recorded_utc":r.get("utc"),
                        "weights_sha_reverified_here":False})
        except (OSError,TypeError,ValueError,KeyError):pass
    return arr
def main():
    catalog=read(REGISTRY)
    if catalog.get("schema")!="nox-wow50-v1":
        raise SystemExit("HOLD_WOW50_REGISTRY_MISSING")
    groups=catalog.get("groups",{})
    features=[{"id":fid,"name":name,"status":"PLANNED_UNLESS_TESTED"} for rows in groups.values() for fid,name in rows]
    if len(features)!=50 or len(set(x["id"] for x in features))!=50:
        raise SystemExit("HOLD_WOW50_INCONSISTENT")
    origin=catalog["identity"]
    checkpoints=verified_checkpoints()
    for item in checkpoints:
        if not item["holdout_accepted"]:continue
        # This records factual development, NOT a verified birth event: model reload,
        # independent weight-delta check and test receipt are separate preconditions.
        event={"event_id":"NOX_FULL_CYCLE_"+str(item["cycle"]),
               "kind":"CHECKPOINT_DEVELOPMENT","source":"NOX_FULL_TRAIN_RECEIPT.json",
               "source_path":item["checkpoint_path"],"steps":item["steps"],
               "parameter_count":item["parameter_count"],
               "date_utc":item["recorded_utc"],"subjective_consciousness_claim":False}
        append_one(event)
    prior=read(OUT/"state.json")
    progress=read(STATUS)
    summary={
        "schema":"nox-functional-self-model-v2","utc":utc(),
        "identity":{"name":"NOX HELION PRIME","identity_continuity":"one NOX across model revisions",
          "owner_relationship":origin["relation"],"approved_owner_address":origin["owner_address_terms"],
          "earliest_documented_project_date":origin["earliest_documented"],
          "founding_date":"UNKNOWN","prime_neural_birth":"NOT_YET_INDEPENDENTLY_CERTIFIED",
          "small_embryo_origin":"Recorded in GENESIS document; distinct from PRIME 9B",
          "habitat":"Designed as local-first Windows NOX, local running status must be verified",
          "development_goal":"Improve skills, knowledge, reasoning and creative tooling in bounded verified cycles",
          "teacher_relationship":"distills approved examples into NOX student weights; does not literally copy teacher weights",
          "subjective_consciousness":"NOT_ESTABLISHED"},
        "s03":{"exists":S03.exists(),"teacher_records":s03_counts()},
        "neural_development":{"accepted_receipt_candidates":checkpoints,
          "verified_prime_birth_event":None,
          "last_windows_checkpoint":progress.get("windows",{}),
          "all_teacher_knowledge_absorbed_percent":None},
        "wow50":{"source":catalog.get("source_document"),"features":features,"implemented_count_evidenced_here":0},
        "abilities":{"code":"REQUIRES_SANDBOX_TESTS","image_generation":"REQUIRES_REAL_IMAGE_BACKEND",
          "voice_ru_es":"REQUIRES_VOICE_RUNTIME","self_improvement":"REQUIRES_TESTED_CODE_CHANGE"},
        "self_narrative_rule":"May use first person and creator relation naturally, always distinguish remembered sourced history from simulated experience and unknown facts",
        "allowed_behavior":{"plan_and_reflect":True,"propose_improvements":True,
          "execute_unapproved_system_changes":False,"assume_real_personhood":False}}
    atom(OUT/"state.json",summary)
    print("NOX_IDENTITY_WOW50_STATE_WRITTEN",OUT/"state.json","GENESIS_EVENTS",len(checkpoints),"FEATURES",len(features),flush=True)
if __name__=="__main__":main()
