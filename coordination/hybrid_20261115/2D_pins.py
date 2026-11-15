"""NOX AUTO 2D: offline validation of *public metadata*, not file downloads.

The verified SHA256 values are Hugging Face Git-LFS/Xet remote-file pointers.
Never treat them as local download or model/training receipts.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

SHA = re.compile(r"[0-9a-f]{64}\Z")
REV = re.compile(r"[0-9a-f]{40}\Z")
PATH = re.compile(r"[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*\Z")
ERROR_ID = "NOX-P1-HYBRID-DATASETS-LACK-IMMUTABLE-SHA-20261115"


def validate(data):
    if data.get("schema") != "NOX_2D_PINNED_PUBLIC_DATASET_EVIDENCE_V1":
        raise ValueError("HOLD_UNKNOWN_SCHEMA")
    if data.get("instructions_version") != "0.0.6" or data.get("error_id") != ERROR_ID:
        raise ValueError("HOLD_UNEXPECTED_OWNER_SCOPE")
    if data.get("active_hf_base_verified") is not False or data.get("active_hf_base_revision") is not None:
        raise ValueError("HOLD_UNVERIFIED_NOX_HF_BASE")
    if data.get("approved_for_training") is not False or any(data.get(k) != 0 for k in ("native_download_count", "native_optimizer_steps", "native_merge_count")):
        raise ValueError("HOLD_FALSE_NATIVE_CLAIM")
    rows = data.get("datasets")
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError("HOLD_DATASET_CATALOGUE")
    ids, unique_paths, total, count = set(), set(), 0, 0
    expected = {"OpenAssistant/oasst2": 2, "google-research-datasets/go_emotions": 3}
    for row in rows:
        repo = row.get("repo_id")
        if repo not in expected or repo in ids or row.get("repo_type") != "dataset":
            raise ValueError("HOLD_REPO_ID")
        ids.add(repo)
        if not isinstance(row.get("revision"), str) or not REV.fullmatch(row["revision"]):
            raise ValueError("HOLD_MUTABLE_REVISION")
        if row.get("licence_card") != "apache-2.0" or row.get("sensitive_data_filter_required") is not True:
            raise ValueError("HOLD_RIGHTS_OR_PRIVACY")
        langs = row.get("language_card")
        if not isinstance(langs, list) or (repo == "OpenAssistant/oasst2" and not {"ru", "es"}.issubset(langs)) or (repo.endswith("go_emotions") and langs != ["en"]):
            raise ValueError("HOLD_LANGUAGE_PROVENANCE")
        if row.get("split_group_key") != ("message_tree_id" if repo.endswith("oasst2") else "id"):
            raise ValueError("HOLD_HOLDOUT_LEAKAGE_POLICY")
        files = row.get("files")
        if not isinstance(files, list) or len(files) != expected[repo]:
            raise ValueError("HOLD_FILE_COVERAGE")
        for f in files:
            path = f.get("path")
            if not isinstance(path, str) or not PATH.fullmatch(path) or path.startswith(".") or "/.." in path:
                raise ValueError("HOLD_UNSAFE_PATH")
            if (repo, path) in unique_paths:
                raise ValueError("HOLD_DUPLICATE_FILE")
            unique_paths.add((repo, path))
            digest = f.get("sha256")
            if not isinstance(digest, str) or not SHA.fullmatch(digest):
                raise ValueError("HOLD_LFS_DIGEST")
            size = f.get("size_bytes")
            if type(size) is not int or not 0 < size <= 256*1024*1024:
                raise ValueError("HOLD_EXACT_SIZE")
            count += 1; total += size
    if ids != set(expected) or total != 70138500:
        raise ValueError("HOLD_FILE_SIZE_TOTAL")
    adapters = data.get("adapters_research_only")
    if not isinstance(adapters, list) or len(adapters) != 2:
        raise ValueError("HOLD_ADAPTER_WATCHLIST")
    for a in adapters:
        if a.get("may_merge") is not False or a.get("adapter_weight_sha256") is not None or a.get("exact_weight_bytes") is not None:
            raise ValueError("HOLD_UNVERIFIED_ADAPTER_MERGE")
        if a.get("declared_base") != "Qwen/Qwen3.5-9B":
            raise ValueError("HOLD_ADAPTER_BASE_DRIFT")
    if adapters[1].get("licence_card") is not None or adapters[1].get("untrusted_pickle_training_args_bin") is not True:
        raise ValueError("HOLD_UNTRUSTED_ADAPTER_ARTIFACT")
    return {"status": "SOURCE_METADATA_VALIDATED_NOT_DOWNLOADED", "files": count,
            "total_remote_file_bytes": total, "datasets": len(ids), "adapters_quarantined": len(adapters)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", default=str(Path(__file__).with_name("2D_pins.json")))
    args = p.parse_args(argv)
    try:
        result = validate(json.loads(Path(args.manifest).read_text(encoding="utf-8")))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print("HOLD_PIN_VALIDATION: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
