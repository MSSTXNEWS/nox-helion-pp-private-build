#!/usr/bin/env python3
"""NOX V28 Stage 0: verify repository source baseline, without runtime side effects.

This is a read-only source/inventory gate. Previous V26 receipt is historical
evidence, NOT a proof of installed Windows OneHost or of newly trained weights.
An optional local archive/model can be hashed, but never executed or imported.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
CANONICAL=HERE/"V28_STAGE_00_SOURCE_BASELINE_20261113.json"
SCHEMA="nox-v28-stage0-verification-receipt-v1"
HOLD_GATES=("WINDOWS_ONEHOST","S03_RESTART","AUTHENTICATED_GENESIS_ENDPOINT",
            "STREAMING_STOP","VOICE_RU_ES","GPU_OPTIMIZER",
            "INDEPENDENT_WINDOWS_E07","PRODUCTION_INSTALLED")


def sha256_path(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda:file.read(4*1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_source_manifest(data:dict, receipt:dict) -> None:
    if data.get("schema")!="nox-v28-stage0-source-baseline-v1":
        raise ValueError("HOLD_BASELINE_SCHEMA")
    if data.get("instructions_version")!="0.0.6":
        raise ValueError("HOLD_AGENT_GUIDE_VERSION")
    if not all(data.get("policy",{}).get(x) is True for x in
               ("one_active_nox_student","one_onehost","one_s03","no_second_backend",
                "no_live_mutations","no_old_checkpoint_deletions")):
        raise ValueError("HOLD_PRODUCTION_POLICY")
    if receipt.get("schema")!="NOX-HELiON-WEB-WOW-V26-PHYSICAL-SOURCE-ACCEPTANCE-V1":
        raise ValueError("HOLD_V26_SOURCE_RECEIPT_SCHEMA")
    src=receipt.get("source",{})
    staged=receipt.get("candidate",{})
    integrity=receipt.get("integrity",{})
    web=data["web"]
    if any((
       src.get("sha256")!=web["source_archive_sha256"],
       staged.get("sha256")!=web["staged_candidate_sha256"],
       integrity.get("original_d02_sha256")!=web["original_d02_sha256"],
       integrity.get("staged_d02_sha256")!=web["original_d02_sha256"],
       integrity.get("unchanged_original_files")!=
            str(web["original_unchanged_files_claimed"])+"/"+str(web["original_unchanged_files_claimed"])+
                " BYTE_IDENTICAL",
       receipt.get("gates",{}).get("release_accepted") is not False,
       receipt.get("gates",{}).get("production_installed") is not False,
       receipt.get("gates",{}).get("physical_windows_onehost") is not False,
       receipt.get("gates",{}).get("gpu_training") is not False,
    )):
        raise ValueError("HOLD_V26_CLAIMS_OR_HASHES_DIVERGE")
    if list(data.get("unverified_runtime_gates",[]))!=list(HOLD_GATES):
        raise ValueError("HOLD_RUNTIME_GATES_MISCLASSIFIED")


def validate_benchmark_baseline(baseline:dict)->None:
    if baseline.get("source_report_only") is not True or baseline.get("replayed_independently") is not False:
        raise ValueError("HOLD_BENCHMARK_NOT_HISTORICAL")
    if baseline.get("model")!="nox-final-l03-Q4_K_M.gguf":
        raise ValueError("HOLD_UNRECOGNIZED_HISTORICAL_MODEL")
    for metric,(correct,total) in {
        "GSM8K":(88,100),"IFEval":(54,100),"HumanEval":(84,100),"ruMMLU":(117,200)
    }.items():
        entry=baseline.get("subset_scores",{}).get(metric,{})
        if (type(entry.get("correct")) is not int or type(entry.get("total")) is not int
            or (entry["correct"],entry["total"])!=(correct,total)):
            raise ValueError("HOLD_REPORTED_BENCHMARK_MISMATCH_"+metric)


def validate_idea_catalogs(repo:Path)->dict:
    base=repo/"nox_runpod"/"teacher_mesh"
    old=json.loads((base/"NOX_WOW50_V28_EVAL_AND_ARCHITECTURE.json").read_text(encoding="utf-8"))
    new50=json.loads((base/"NOX_FUTURE_OWN_WOW50_V28.json").read_text(encoding="utf-8"))
    new40=json.loads((base/"NOX_V28_ORIGINAL_WOW40_IDEAS.json").read_text(encoding="utf-8"))
    if (len(old["cognitive_wow50"])!=50 or len(old["architecture_50"])!=50
            or len(new50["items"])!=50 or len(new40["new_ideas"])!=40):
        raise ValueError("HOLD_IDEA_CATALOG_COUNTS")
    if new50.get("status")!="SOURCE_CANDIDATE_NOT_DEPLOYED":
        raise ValueError("HOLD_WOW50_IMPLEMENTATION_STATUS")
    if new40.get("status")!="PROPOSED_NOT_INSTALLED":
        raise ValueError("HOLD_WOW40_IMPLEMENTATION_STATUS")
    return {"original_cognitive":50,"original_architecture":50,
            "new_wow50":50,"additional_experimental_ideas":40,
            "unique_total_not_claimed":True}


def verify(repo:Path, *, web_zip:Path|None=None, model_file:Path|None=None)->dict:
    repo=repo.resolve()
    data=json.loads(CANONICAL.read_text(encoding="utf-8"))
    receipt_path=repo/data["web"]["receipt_file"]
    receipt=json.loads(receipt_path.read_text(encoding="utf-8"))
    validate_source_manifest(data,receipt)
    validate_benchmark_baseline(data["historical_model_benchmark"])
    catalogs=validate_idea_catalogs(repo)
    source={}
    for rel in data["source_files_required"]:
        file=repo/rel
        if not file.is_file() or file.is_symlink() or repo not in file.resolve().parents:
            raise ValueError("HOLD_REQUIRED_REPO_SOURCE_ABSENT_"+rel)
        source[rel]={"bytes":file.stat().st_size,"sha256":sha256_path(file)}
    observed=[]
    for label,path,expected in (
        ("staged_web_source_candidate",web_zip,data["web"]["staged_candidate_sha256"]),
        ("historical_l03_model",model_file,data["historical_model_benchmark"]["reported_model_sha256"])
    ):
        if path is None:
            observed.append({"artifact":label,"state":"HOLD_NOT_MOUNTED_NO_PHYSICAL_CLAIM"})
            continue
        if not path.is_file() or path.is_symlink():
            observed.append({"artifact":label,"state":"HOLD_FILE_MISSING"})
            continue
        actual=sha256_path(path)
        observed.append({"artifact":label,
                         "state":"LOCAL_FILE_SHA256_MATCH_NOT_INSTALLED" if actual==expected else "HOLD_SHA256_MISMATCH",
                         "expected_sha256":expected,"observed_sha256":actual,
                         "bytes":path.stat().st_size})
    return {
        "schema":SCHEMA,
        "status":"SOURCE_BASELINE_VERIFIED_RUNTIME_HOLD",
        "observed_utc":datetime.now(timezone.utc).isoformat(),
        "base_commit_reported":data["baseline_commit_sha"],
        "required_repo_files":len(source),
        "source_file_hashes":source,
        "idea_catalogs":catalogs,
        "web_original_d02_hash":data["web"]["original_d02_sha256"],
        "web_source_reported_unchanged":data["web"]["original_unchanged_files_claimed"],
        "historical_model_baseline":data["historical_model_benchmark"],
        "physical_file_checks":observed,
        "runtime_e07_gates":{gate:"HOLD_NOT_TESTED" for gate in HOLD_GATES},
        "training_optimizer_steps_verified":0,
        "production_modified":False,
        "new_weights_training":False,
        "limitations":["Source documents verified for consistency, not GPU or Windows.",
                       "Historical benchmark l03 is a user Drive report, not an independently replayed evaluation.",
                       "Source preserved ≠ staged archive installed or OneHost/S03 alive.",
                       "No old weights, chats, files or checkpoints removed."]
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo",type=Path,default=HERE.parents[2])
    ap.add_argument("--web-zip",type=Path)
    ap.add_argument("--model-file",type=Path)
    ap.add_argument("--out",type=Path)
    a=ap.parse_args()
    try:
        report=verify(a.repo,web_zip=a.web_zip,model_file=a.model_file)
    except (ValueError,FileNotFoundError,KeyError,TypeError,json.JSONDecodeError) as exc:
        print(json.dumps({"schema":SCHEMA,"status":"HOLD_SOURCE_BASELINE","reason":str(exc)}))
        raise SystemExit(2)
    body=json.dumps(report,ensure_ascii=False,indent=2)+"\n"
    if a.out:
        if a.out.exists():
            raise SystemExit("HOLD_REPORT_EXISTS_NO_OVERWRITE: "+str(a.out))
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(body,encoding="utf-8")
    print(json.dumps({"status":report["status"],"files":report["required_repo_files"],
                      "runtime_gates":"ALL_HOLD","output":str(a.out) if a.out else "stdout_only"},
                     ensure_ascii=False))
if __name__=="__main__":
    main()
