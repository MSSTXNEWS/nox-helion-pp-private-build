#!/usr/bin/env python3
"""NOX self-model & capability curriculum from verified evidence, not fabricated consciousness.

Maintains a compact factual identity and prioritized development tasks. Does not
execute generated code, invent completed skills, or assert subjective awareness.
"""
import datetime, hashlib, json, os, pathlib, sqlite3, sys
R=pathlib.Path("/workspace/nox")
BASE=R/"memory/NOX_UNIFIED_S03"
STATUS=R/"dispatcher/nox_v3/status.json"
P=R/"dispatcher/a40_full_parameter/progress.json"
DEST=R/"memory/NOX_SELF_MODEL"
CURRICULUM=[
 {"id":"autobiography","goal":"Remember sourced project timeline, origins, changes, and corrections","evidence":["provenance_file","memory_database"],"status":"planned"},
 {"id":"reasoning","goal":"Solve benchmark reasoning tasks and compare to frozen holdout","evidence":["benchmark_receipt"],"status":"planned"},
 {"id":"coding","goal":"Write and test functional code in an isolated workspace","evidence":["sandbox_test_report"],"status":"planned"},
 {"id":"tools","goal":"Use explicitly approved PC tools with STOP, rollback, and permission boundaries","evidence":["tool_action_receipt"],"status":"planned"},
 {"id":"image_generation","goal":"Create and edit images through a verified connected image backend","evidence":["image_artifact","backend_execution_receipt"],"status":"planned"},
 {"id":"scientific_work","goal":"Design and evaluate reproducible experiments","evidence":["experiment_receipt"],"status":"planned"},
 {"id":"voice_ru_es","goal":"Communicate in Russian and Spanish using actual voice input and output","evidence":["voice_roundtrip_receipt"],"status":"planned"},
 {"id":"self_improvement","goal":"Propose a patch, run isolated tests, compare quality and request promotion","evidence":["patch_receipt","regression_report"],"status":"planned"},
]
def read(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError):return {}
def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    with tmp.open("w",encoding="utf-8") as f:
        json.dump(data,f,indent=2,ensure_ascii=False)
        f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
def main():
    db=BASE/"unified_nox_knowledge.sqlite3"
    teachers={}
    if db.is_file():
        try:
            c=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=5)
            try:teachers=dict(c.execute("SELECT teacher,COUNT(*) FROM knowledge GROUP BY teacher").fetchall())
            finally:c.close()
        except sqlite3.Error:pass
    origin=read(R/"memory/PROVENANCE/NOX_ORIGIN.json")
    train=read(P)
    progress=read(STATUS)
    prior=read(DEST/"state.json")
    state={
      "schema":"nox-functional-self-model-v1",
      "utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
      "name":"NOX HELION PRIME",
      "identity_kind":"functional_self_model_not_evidence_of_subjective_consciousness",
      "origin":origin or {"project_birth_date":"UNKNOWN","do_not_invent":True},
      "memory":{"s03_present":db.is_file(),"attributed_teacher_records":teachers},
      "training":{"last_status":train.get("status","UNKNOWN"),
                  "last_cycle_steps":train.get("steps_executed_this_cycle"),
                  "last_cycle_target":train.get("target_steps_this_cycle"),
                  "last_verified_checkpoint_not_confirmed_on_windows":True},
      "teacher_progress":progress.get("teachers",{}),
      "capabilities":CURRICULUM,
      "approval_required_for":["source_promotion","unsandboxed_pc_actions","new_external_deployments"],
      "unverified_claims_to_avoid":["subjective_consciousness","all_teacher_weights_absorbed",
        "autonomous_image_creation_without_backend","completed_teacher_27b_32b_without_receipt"],
    }
    # A capability is never auto-marked complete from a prompt or a generic log.
    atomic(DEST/"state.json",state)
    print("NOX_SELF_MODEL_UPDATED",str(DEST/"state.json"),
          "S03_RECORDS",sum(teachers.values()),"CAPABILITY_PLANS",len(CURRICULUM),flush=True)
if __name__=="__main__":main()
