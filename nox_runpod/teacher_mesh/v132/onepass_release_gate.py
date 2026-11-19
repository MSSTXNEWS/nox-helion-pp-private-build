"""NOX V132 ONEPASS: one reproducible evidence gate, no second backend or daemon.

This is intentionally a source/runtime ACCEPTANCE GATE, not a release flag.
A V29 route present in FastAPI is not a functional E2E; a passed training
fixture is not proof of a changed student checkpoint. No shell/network or
credentials; GitHub Actions can publish the JSON receipt as an artifact.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Mapping

MATRIX=Path("coordination/NOX_WEB_V293_92_ROUTE_HOST_PLAN.json")
SOURCE="NOX HELION WEB V29.3"
FROZEN_SHA="166becb90fce63e2db3f9a74281d756995844552cddb7b67a0ac4bd67a190aa0"
OWNER_PC="WINDOWS_OWNER_PC_REQUIRED_NOT_VAST_METRICS"
EXTERNAL="BROWSER_CONSENT_OR_EXTERNAL_PROVIDER_REVIEW"
HEX=set("0123456789abcdef")
REQUIRED_SOURCE=(
    "nox_runpod/teacher_mesh/v130/owner_s03_fact_write.py",
    "nox_runpod/teacher_mesh/v130/install_native_owner_fact.py",
    "nox_runpod/teacher_mesh/v130/tests/test_owner_s03_fact_write.py",
    "nox_runpod/teacher_mesh/v130/tests/test_install_native_owner_fact.py",
    "nox_runpod/teacher_mesh/v61/restore_offsite_chunks.py",
    "nox_runpod/teacher_mesh/v70/NOX_V70_PC_ALL_ONEPASS.ps1",
    "nox_runpod/teacher_mesh/v71/disk_budget.py",
    "nox_runpod/teacher_mesh/v41/training/no_loss_acceptance.py",
)
def _sha(content:bytes)->str:
    return hashlib.sha256(content).hexdigest()

def _valid_hash(value)->bool:
    return isinstance(value,str) and len(value)==64 and set(value)<=HEX

def _gate(ok:bool,reason:str)->dict:
    return {"state":"PASS" if ok else "HOLD","reason":None if ok else reason}

def source_report(root:Path=Path("."))->dict:
    root=Path(root)
    manifest=root/MATRIX
    doc=json.loads(manifest.read_text(encoding="utf8"))
    if doc.get("schema")!="NOX_WEB_V293_92_ROUTE_HOST_PLAN_V1":
        raise ValueError("HOLD_WEB_CONTRACT_SOURCE_SCHEMA")
    if doc.get("frozen_source",{}).get("sha256")!=FROZEN_SHA:
        raise ValueError("HOLD_FROZEN_WEB_SOURCE_SHA")
    entries=doc.get("functions")
    if not isinstance(entries,list) or len(entries)!=92:
        raise ValueError("HOLD_92_ROUTE_MATRIX")
    routes=[r.get("route") for r in entries if isinstance(r,dict)]
    if len(routes)!=92 or len(set(routes))!=92 or any(not isinstance(x,str) or not x.startswith("/api/") for x in routes):
        raise ValueError("HOLD_ROUTE_SET")
    host_counts=dict(sorted(Counter(x["host_boundary"] for x in entries).items()))
    expected={OWNER_PC,EXTERNAL,"EXISTING_ONEHOST","REQUIRES_ORIGINAL_CALLSITE_AND_OWNER_HOST_VERIFICATION"}
    if set(host_counts)!=expected or sum(host_counts.values())!=92:
        raise ValueError("HOLD_ROUTE_HOST_SPLIT")
    observed=doc.get("native_current_20261115",{})
    count=observed.get("exact_registered")
    missing=observed.get("exact_unregistered")
    if count!=23 or missing!=69 or not all(_valid_hash(observed.get(k)) for k in ("bridge_sha256","proxy_sha256")):
        raise ValueError("HOLD_NATIVE_BASELINE_EVIDENCE")
    source_checks={}
    for relative in REQUIRED_SOURCE:
        file=root/relative
        if not file.is_file() or file.is_symlink() or file.stat().st_size==0 or file.stat().st_size>3_000_000:
            raise ValueError("HOLD_REQUIRED_EXISTING_SOURCE_"+file.name)
        source_checks[relative]=_sha(file.read_bytes())
    implementation=(root/REQUIRED_SOURCE[0]).read_text(encoding="utf8")
    if "register_nox_v130_owner_fact_write" not in implementation or "s03_memory.remember(" not in implementation or "_matching(" not in implementation:
        raise ValueError("HOLD_V130_EXISTING_S03_ADAPTER")
    if "/api/nox/memory/facts" not in implementation:
        raise ValueError("HOLD_OWNER_FACT_ROUTE_MISSING")
    live_evidence={
        "web_owner_s03_last_verified":"https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43650893956",
        "native_route_census_last_verified":"https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43650602202",
        "native_s03_writer_last_verified":"https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43651709415",
        "vast_api_last_404":"https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43652955212",
        "vast_nox2_auth_error":"https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43653604598",
    }
    return {
        "schema":"NOX_V132_ONEPASS_SOURCE_ACCEPTANCE_V1",
        "instructions_version":"0.0.6",
        "source":"EXISTING_FEATURE_BRANCH_NOT_PRODUCTION",
        "web_baseline":{"name":SOURCE,"frozen_zip_sha256":FROZEN_SHA,
                        "expected_exact_paths":92,"last_observed_exact_registered":count,
                        "last_observed_unmapped":missing,
                        "current_runtime_recounted_by_this_job":False,
                        "last_observed_host_partition":host_counts},
        "v130":{"state":"SOURCE_STAGED_NOT_LIVE_VERIFIED",
                "owner_post_path":"/api/nox/memory/facts",
                "original_s03_writer":"s03_memory.remember",
                "new_database_created":False,"real_s03_mutated_by_this_gate":False,
                "requires_new_safely_authenticated_native_install":True},
        "live_runtime":{"state":"HOLD_NOX2_AUTH_ERROR","vast_instance_id":60509551,
                        "old_api_list_deprecated":True,
                        "account_auth_rejected_at_last_verified_probe":True,
                        "instance_existence_not_inferred_from_404":True,
                        "native_sha_resampled":False,
                        "requires_owner_reissue_key_direct_to_github_secret":True},
        "sources_sha256":source_checks,
        "evidence":live_evidence,
        "release":{"full_92_route_functional_e2e":False,
                   "native_gpu_stop_accepted":False,
                   "full_parameter_optimizer_steps_verified":False,
                   "checkpoint_external_restore_proven":False,
                   "windows_pc_physical_restore_proven":False,
                   "main_production_promoted":False,
                   "state":"HOLD_REQUIRED_LIVE_ACCEPTANCE"},
        "safety":{"main_weights_untouched_by_report":True,"s03_untouched_by_report":True,
                  "no_new_server":True,"no_scheduler":True,"no_paid_pod":True,
                  "no_secrets_in_receipt":True}
    }

def admission(report:Mapping, observations:Mapping)->dict:
    """Native-approval decision only; never executes an action."""
    reason=[]
    if report.get("schema")!="NOX_V132_ONEPASS_SOURCE_ACCEPTANCE_V1":
        return {"state":"HOLD_SOURCE_REPORT","performed":False}
    if not isinstance(observations,Mapping):
        return {"state":"HOLD_NATIVE_EVIDENCE","performed":False}
    tests=(
      ("owner_access_is_verified","HOLD_OWNER_AUTH_OR_API"),
      ("same_instance_60509551","HOLD_WRONG_INSTANCE"),
      ("existing_proxy_and_model_healthy","HOLD_P0_CHAT_HEALTH"),
      ("original_s03_quick_check","HOLD_S03_INTEGRITY"),
      ("owner_stop_inactive","HOLD_STOP_ACTIVE_OR_UNKNOWN"),
      ("source_sha_pins_current","HOLD_NATIVE_CONCURRENT_SHA_DRIFT"),
      ("no_active_model_generation","HOLD_CHAT_BUSY"),
      ("source_ci_passed","HOLD_SOURCE_REGRESSION"),
      ("code_backup_rollback_available","HOLD_ORIGINAL_CODE_BACKUP"),
      ("manual_owner_install_approved","HOLD_EXPLICIT_OWNER_GATE"),
    )
    for key,fail in tests:
        if observations.get(key) is not True:reason.append(fail)
    return {"state":"READY_FOR_ONE_NATIVE_INSTALL" if not reason else "HOLD",
            "reasons":reason,"performed":False,"live_weights_changed":False,
            "source_only":False,"target":"EXISTING_ONEHOST_60509551"}

def release_acceptance(*, v132:Mapping, web_routes:Mapping|None, training:Mapping|None,
                       windows:Mapping|None)->dict:
    """Production release requires independent native receipts, not booleans in planning notes."""
    failures=[]
    if v132.get("schema")!="NOX_V132_ONEPASS_SOURCE_ACCEPTANCE_V1":
        failures.append("NO_SOURCE_LOCK")
    if not isinstance(web_routes,Mapping) or web_routes.get("expected")!=92 or web_routes.get("functional_e2e_verified_count")!=92 or web_routes.get("signed_owner_native_e2e") is not True:
        failures.append("WEB_NOT_92_FUNCTIONAL_E2E")
    if not isinstance(training,Mapping) or any(training.get(k) is not True for k in (
        "full_parameter_no_adapter_verified","optimizer_delta_verified",
        "candidate_checkpoint_sha_verified","checkpoint_reload_verified",
        "independent_holdout_passed","offsite_checkpoint_restore_verified",
        "s03_external_restore_verified","native_stop_verified")):
        failures.append("FORGE_OR_NATIVE_STOP_NOT_VERIFIED")
    if not isinstance(windows,Mapping) or any(windows.get(k) is not True for k in (
        "real_owner_pc_file_sha_verified","owner_key_decryption_proven",
        "complete_restore_replay_verified","installer_no_loss_windows_accepted")):
        failures.append("WINDOWS_RESTORE_NOT_VERIFIED")
    return {"state":"HOLD" if failures else "READY_FOR_OWNER_RELEASE_REVIEW",
            "reasons":failures,"production_promoted":False}

def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path("."))
    parser.add_argument("--out",type=Path,default=Path("nox_v132_onepass_receipt.json"))
    args=parser.parse_args()
    receipt=source_report(args.root)
    target=args.out
    if target.exists():
        raise SystemExit("HOLD_OUTPUT_ALREADY_EXISTS")
    payload=json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    with target.open("x",encoding="utf8") as f:f.write(payload)
    print("NOX_V132_SOURCE_GATE=PASS")
    print("NOX_V132_LIVE_RELEASE=HOLD_REQUIRED_LIVE_ACCEPTANCE")
    print("NOX_V132_RECEIPT_SHA256="+_sha(payload.encode("utf8")))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
