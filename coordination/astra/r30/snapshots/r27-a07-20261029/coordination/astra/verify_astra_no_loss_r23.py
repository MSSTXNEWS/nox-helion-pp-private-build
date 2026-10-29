#!/usr/bin/env python3
"""NOX Astra source-only path+blob preservation gate (no build, no EXE).
Usage: python coordination/astra/verify_astra_no_loss_r23.py [--repo ROOT] [--json OUT]
Git blob identity is not a physical ZIP 729-member checksum or proof of no
semantic regressions; follow with original verifier and targeted code tests.
"""
from __future__ import annotations
import argparse
import json
import pathlib
import subprocess
import sys

EXPECTED_COMMIT="817bb4146db0a2c79407d249d54fdeeb22261bb6"
MANIFEST="coordination/astra/ASTRA_V16_R23_FROZEN_968_GIT_BLOBS_20261029.json"
SOURCE_PARTS={"source_00.part","source_01.part","source_02.part"}

def run_git(root: pathlib.Path, *args: str) -> bytes:
    result=subprocess.run(["git", "-C", str(root), *args],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=False, timeout=120)
    if result.returncode:
        raise RuntimeError("GIT_SOURCE_READ_HOLD:" + " ".join(args))
    return result.stdout

def tracked(root: pathlib.Path, ref: str) -> dict[str, str]:
    # Git -z avoids splitting paths with whitespace/newlines.
    output={}
    for record in run_git(root, "ls-tree","-r","-z",ref).split(b"\0"):
        if not record:
            continue
        meta, name=record.split(b"\t",1)
        mode,kind,sha=meta.decode("ascii").split()
        if kind!="blob" or mode not in ("100644","100755","120000"):
            raise RuntimeError("GIT_NONREGULAR_SOURCE_ITEM_HOLD")
        key=name.decode("utf-8","strict")
        if key in output:
            raise RuntimeError("GIT_DUPLICATE_TRACKED_PATH_HOLD")
        output[key]=sha
    return output

def verify(repo: pathlib.Path) -> dict:
    manifest=json.loads((repo/MANIFEST).read_text("utf-8"))
    baseline=manifest["blob_inventory"]
    expected={obj["path"]:obj["git_blob_sha1"] for obj in baseline}
    if (manifest["initial_commit"]!=EXPECTED_COMMIT
            or len(baseline)!=968 or len(expected)!=968):
        raise RuntimeError("ASTRA_BASELINE_968_IDENTITY_HOLD")
    actual_baseline=tracked(repo,EXPECTED_COMMIT)
    if actual_baseline!=expected:
        raise RuntimeError("ASTRA_FROZEN_ORIGINAL_TREE_MANIFEST_DRIFT")
    # HEAD must be the actual checked-out branch, not an arbitrary worktree ref.
    current=tracked(repo,"HEAD")
    missing=sorted(set(expected)-set(current))
    changed=sorted(k for k in expected.keys()&current.keys()
                   if current[k]!=expected[k])
    original_changed=sorted(SOURCE_PARTS & set(changed))
    added=sorted(set(current)-set(expected))
    result={
        "schema":"NOX_ASTRA_R23_GIT_PATH_NO_LOSS_RECEIPT_V1",
        "source_base_commit":EXPECTED_COMMIT,
        "checked_head":run_git(repo,"rev-parse","HEAD").decode().strip(),
        "baseline_git_blobs":len(expected),
        "currently_tracked_blobs":len(current),
        "baseline_missing_paths":missing,
        "baseline_changed_paths_need_semantic_qa":changed,
        "new_added_paths":added,
        "original_source_parts_sha_changed":original_changed,
        "git_path_no_loss":not missing and not original_changed,
        "raw_729_archive_sha256_verified":False,
        "semantic_function_no_loss_verified":False,
        "product_source_code_complete":"N/D",
    }
    return result

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--repo",default=".")
    p.add_argument("--json")
    a=p.parse_args()
    try:
        result=verify(pathlib.Path(a.repo).resolve())
        rendered=json.dumps(result,ensure_ascii=False,indent=2)
        if a.json:
            target=pathlib.Path(a.json)
            if target.exists():
                raise RuntimeError("REFUSE_OVERWRITE_PRIOR_NOLOSS_RECEIPT")
            target.write_text(rendered+"\n",encoding="utf-8")
        print(rendered)
        return 0 if result["git_path_no_loss"] else 2
    except (RuntimeError,ValueError,OSError,KeyError) as e:
        print(json.dumps({"schema":"NOX_ASTRA_R23_NOLOSS_GATE_HOLD",
                          "status":"HOLD","reason":str(e)[:240]}))
        return 2

if __name__=="__main__":
    sys.exit(main())
