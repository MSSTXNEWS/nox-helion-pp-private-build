"""NOX V16 coordinator REPORT_GATE offline schema validator.

This validates one evidence ENVELOPE only. It cannot read Google Drive itself.
Only a connected authenticated coordinator may promote REPORT_GATE from
SCHEMA_PASS_REMOTE_READBACK_REQUIRED to VERIFIED after real revision/readback.
No filesystem mutations, no network, no auto-executing saved instruction text.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

HASH256 = re.compile(r"^[a-f0-9]{64}$")
GIT_SHA1 = re.compile(r"^[a-f0-9]{40}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
GATES = {f"G{i}" for i in range(1,8)}
DOCS = ("own_report","e06_report","e06_lessons")
PRESTART_DOCS = ("v16_revision","master_revision","e06_report_revision",
                 "e06_lessons_revision","last_own_receipt")
STATUS = {"DONE","HOLD","FAILED"}

class ReportInvalid(ValueError):
    pass

def require(ok: bool, reason: str):
    if not ok:raise ReportInvalid(reason)

def text_field(doc: dict, key: str, min_chars=1):
    v=doc.get(key)
    require(isinstance(v,str) and len(v.strip())>=min_chars,
            "MISSING_"+key.upper())
    return v

def validate(report:dict) -> dict:
    require(isinstance(report,dict),"REPORT_OBJECT_REQUIRED")
    run_id=text_field(report,"run_id")
    require(SAFE_ID.fullmatch(run_id) is not None,"RUN_ID_INVALID")
    owner=report.get("owner")
    require(type(owner) is int and owner in range(1,8),"OWNER_INVALID")
    trigger=text_field(report,"trigger")
    require(re.fullmatch(r"1{1,32}",trigger) is not None,"TRIGGER_NOT_ONES")
    cycle_count=report.get("cycle_count")
    cycle_index=report.get("cycle_index")
    require(type(cycle_count) is int and 1<=cycle_count<=32,
            "CYCLE_COUNT_INVALID")
    require(cycle_count==len(trigger),"TRIGGER_LENGTH_CYCLE_COUNT_MISMATCH")
    require(type(cycle_index) is int and 1<=cycle_index<=cycle_count,
            "CYCLE_INDEX_INVALID")
    require(report.get("instruction_version")=="NOX-V16-REPORT-GATE-R1",
            "UNKNOWN_INSTRUCTION_VERSION")
    instructions=report.get("instructions_read")
    require(isinstance(instructions,dict),"PRESTART_MISSING")
    for field in PRESTART_DOCS:text_field(instructions,field)
    learning=report.get("learning")
    require(isinstance(learning,dict),"LEARNING_MISSING")
    for key in ("prior_run_id","observed_error","root_cause",
                "changed_method","regression_check"):
        text_field(learning,key,4)
    if learning["prior_run_id"]!="NO_PRIOR":
        require(SAFE_ID.fullmatch(learning["prior_run_id"]) is not None,
                "PRIOR_RUN_ID_INVALID")
        require(learning["prior_run_id"]!=run_id,
                "SELF_LEARNING_MUST_REFERENCE_PREVIOUS_RUN")
    tasks=report.get("tasks")
    require(isinstance(tasks,list) and 1<=len(tasks)<=10,"TASKS_REQUIRE_UP_TO_TEN")
    task_ids=set()
    done=hold=failed=0
    for task in tasks:
        require(isinstance(task,dict),"TASK_RECORD_INVALID")
        task_id=text_field(task,"task_id")
        require(SAFE_ID.fullmatch(task_id) is not None,"TASK_ID_INVALID")
        require(task_id not in task_ids,"DUPLICATE_TASK_ID")
        task_ids.add(task_id)
        require(task.get("owner")==owner,"TASK_OWNER_MISMATCH")
        state=task.get("status")
        require(state in STATUS,"TASK_STATUS_INVALID")
        text_field(task,"description",8)
        if state=="DONE":
            done+=1
            for field in ("file_path","pre_sha256","post_sha256","patch_sha256",
                          "receipt_id","test_result"):
                text_field(task,field)
            for field in ("post_sha256","patch_sha256"):
                require(HASH256.fullmatch(task[field]) is not None,
                        "TASK_"+field.upper()+"_INVALID")
            require(task["pre_sha256"]=="ABSENT" or
                    HASH256.fullmatch(task["pre_sha256"]) is not None,
                    "TASK_PREIMAGE_INVALID")
            require(task["pre_sha256"]!=task["post_sha256"] or
                    task["pre_sha256"]=="ABSENT",
                    "NO_PHYSICAL_FILE_DELTA")
            require(not task["file_path"].startswith(("../","/")) and
                    ".." not in task["file_path"].split("/"),
                    "FILE_PATH_UNSAFE")
        else:
            text_field(task,"blocker")
            if state=="HOLD":hold+=1
            else:failed+=1
    # The item count does NOT grant 100% automatically.
    evidence=report.get("evidence")
    require(isinstance(evidence,dict),"EVIDENCE_MISSING")
    require(GIT_SHA1.fullmatch(text_field(evidence,"git_commit_sha1")) is not None,
            "GIT_SHA_INVALID")
    text_field(evidence,"component_result")
    require(type(evidence.get("native_exe_accepted")) is bool,
            "NATIVE_EXE_ACCEPTANCE_UNKNOWN")
    if evidence["native_exe_accepted"]:
        require(HASH256.fullmatch(text_field(evidence,"exe_sha256")) is not None,
                "EXE_SHA_REQUIRED_FOR_ACCEPTED")
        text_field(evidence,"e07_receipt_id")
    writes=report.get("writes")
    require(isinstance(writes,dict),"WRITES_MISSING")
    for name in DOCS:
        receipt=writes.get(name)
        require(isinstance(receipt,dict),"WRITE_"+name.upper()+"_MISSING")
        text_field(receipt,"document_id")
        require(receipt.get("run_id")==run_id,"WRITE_"+name.upper()+"_RUN_ID_MISMATCH")
        require(receipt.get("readback") is True,"WRITE_"+name.upper()+"_NO_READBACK")
        text_field(receipt,"readback_revision")
    master=writes.get("master")
    require(isinstance(master,dict) and master.get("status") in ("PASS","MASTER_HOLD"),
            "MASTER_STATUS_INVALID")
    if master.get("status")=="MASTER_HOLD":
        text_field(master,"reason",6)
    else:
        require(master.get("integrity_verified") is True,
                "MASTER_APPEND_REQUIRES_VERIFIED_INTEGRITY")
        text_field(master,"readback_revision")
    gates=report.get("quality_gates")
    require(isinstance(gates,dict) and set(gates)==GATES,
            "SEVEN_PROCESS_GATES_REQUIRED")
    for g in GATES:
        val=gates[g]
        require(isinstance(val,dict) and val.get("status") in ("PASS","HOLD","FAIL"),
                "INVALID_"+g+"_STATE")
        text_field(val,"evidence")
    require((len(tasks)==10 and done==10) or gates["G2"]["status"]!="PASS",
            "TEN_REAL_TASKS_REQUIRED_FOR_G2_PASS")
    if gates["G6"]["status"]=="PASS":
        require(all(writes[k]["readback"] is True for k in DOCS),
                "G6_UNVERIFIED_REMOTE_READBACK")
    scores={"G1":15,"G2":20,"G3":20,"G4":10,"G5":20,"G6":10,"G7":5}
    process_pct=sum(score for gate,score in scores.items()
                    if gates[gate]["status"]=="PASS")
    return {"schema":"NOX-V16-REPORT-GATE-VALIDATION-V1",
            "run_id":run_id,"owner":owner,"cycle_index":cycle_index,
            "cycle_count":cycle_count,"tasks_in_envelope":len(tasks),
            "completed_unique_tasks":done,"blocked_tasks":hold,
            "failed_tasks":failed,
            "process_gate_score_percent_schema_only":process_pct,
            "all_process_gates_claim_pass":all(gates[g]["status"]=="PASS" for g in GATES),
            "result":"SCHEMA_PASS_REMOTE_DRIVE_READBACK_STILL_REQUIRED",
            "product_release_from_this_envelope":"NOT_ASSERTED"}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("report",type=Path)
    args=p.parse_args(argv)
    try:
        if args.report.is_symlink() or not args.report.is_file():
            raise ReportInvalid("REPORT_PATH_UNTRUSTED")
        result=validate(json.loads(args.report.read_text(encoding="utf-8")))
    except (OSError,UnicodeError,json.JSONDecodeError,ReportInvalid) as error:
        print("NOX_REPORT_GATE_HOLD:",str(error),file=sys.stderr)
        return 1
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
