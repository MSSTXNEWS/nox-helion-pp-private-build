#!/usr/bin/env python3
"""E06 R18 — fail-closed, isolated diagnostic adapter for the owner P01 NSIS script.

Never modifies owner source; writes a separate .nsi file and a full SHA receipt.
The x86 NSIS launcher starts the x64 Windows PowerShell via Sysnative on win-x64.
This is a candidate for a real Windows runner, NOT proof that installation passes.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
import pathlib
import subprocess

EXPECTED_GIT_BLOB_SHA1 = "75ce8a88bfbcf5d79dccab677bc2fbe6c82bb042"
OLD = "nsExec::ExecToStack 'powershell.exe -NoProfile"
NEW = (
    "nsExec::ExecToStack '"
    '"$WINDIR\\Sysnative\\WindowsPowerShell\\v1.0\\powershell.exe"'
    " -NoProfile"
)
EXPECTED_OCCURRENCES = 3


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_bytes(data: bytes) -> tuple[bytes, bytes]:
    source = data.decode("utf-8-sig")
    if source.count(OLD) != EXPECTED_OCCURRENCES:
        raise ValueError("OWNER_CONFLICT_NSEXEC_PREIMAGE_OR_SCOPE")
    if NEW in source or "Sysnative" in source:
        raise ValueError("OWNER_CONFLICT_EXISTING_X64_ADAPTER")
    # No script, execution policy, owner marker, ACL, download or rollback logic changes.
    changed = source.replace(OLD, NEW)
    if changed.count(NEW) != EXPECTED_OCCURRENCES:
        raise ValueError("NSIS_X64_ADAPTER_REPLACEMENT_COUNT_HOLD")
    if changed.replace(NEW, OLD) != source:
        raise ValueError("NSIS_ADDITIVE_ONLY_ROUNDTRIP_HOLD")
    diff = "".join(
        difflib.unified_diff(
            source.splitlines(keepends=True),
            changed.splitlines(keepends=True),
            fromfile="owner1-immutable/NOX-HELION-Setup.nsi",
            tofile="e06-r18-diagnostic/NOX-HELION-Setup.nsi",
        )
    ).encode("utf-8")
    return changed.encode("utf-8"), diff


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-nsi", required=True)
    parser.add_argument("--candidate-nsi", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--patch", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    original = pathlib.Path(args.owner_nsi)
    candidate = pathlib.Path(args.candidate_nsi)
    receipt = pathlib.Path(args.receipt)
    diff_path = pathlib.Path(args.patch)
    if any(p.exists() for p in (candidate, receipt, diff_path)):
        raise SystemExit("NO_LOSS_OUTPUT_ALREADY_EXISTS")
    if not original.is_file() or original.is_symlink():
        raise SystemExit("OWNER1_EXACT_NSI_UNAVAILABLE")
    blob = subprocess.run(
        ["git", "hash-object", "--", str(original)],
        check=True, capture_output=True, text=True
    ).stdout.strip()
    if blob != EXPECTED_GIT_BLOB_SHA1:
        raise SystemExit("OWNER1_APPROVED_GIT_BLOB_SHA1_HOLD")
    raw = original.read_bytes()
    changed, diff = patch_bytes(raw)
    if not diff:
        raise SystemExit("NO_PATCH_HOLD")
    if candidate.resolve() == original.resolve():
        raise SystemExit("NEVER_OVERWRITE_ORIGINAL")
    for path in (candidate, receipt, diff_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(changed)
    diff_path.write_bytes(diff)
    record = {
        "schema": "NOX_E06_R18_NSIS_X64_DIAGNOSTIC_RECEIPT_V1",
        "runId": args.run_id,
        "owner": 6,
        "approvedOwner": 1,
        "sourceGitBlobSha1": EXPECTED_GIT_BLOB_SHA1,
        "ownerPreSha256": sha256(raw),
        "candidatePostSha256": sha256(changed),
        "unifiedPatchSha256": sha256(diff),
        "changedNSExecCalls": EXPECTED_OCCURRENCES,
        "diagnosticOnly": True,
        "oneHostAccepted": False,
        "nativeInstallAccepted": False,
        "E07Accepted": False,
        "releaseAllowed": False,
        "rollback": "Discard E06 staging candidate; original owner file unchanged.",
    }
    receipt.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("E06_R18_OWNER1_NSI_ADAPTER_SOURCE_SHA_PASS")


if __name__ == "__main__":
    main()
