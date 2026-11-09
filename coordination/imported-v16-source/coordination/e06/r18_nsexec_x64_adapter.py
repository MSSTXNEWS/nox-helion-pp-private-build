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



def assert_new_output_paths(original: pathlib.Path, outputs: tuple[pathlib.Path, ...]) -> None:
    """Refuse aliases, existing files, dangling symlinks and junction ancestors."""
    identities: set[str] = set()
    source = original.resolve(strict=True)
    for target in outputs:
        if target.exists() or target.is_symlink():
            raise SystemExit("NO_LOSS_OUTPUT_ALREADY_EXISTS")
        resolved = target.resolve(strict=False)
        identity = str(resolved).casefold()  # Windows paths are case-insensitive.
        if resolved == source:
            raise SystemExit("NEVER_OVERWRITE_ORIGINAL")
        if identity in identities:
            raise SystemExit("NO_LOSS_OUTPUT_PATH_COLLISION")
        identities.add(identity)
        for parent in target.parents:
            is_junction = getattr(parent, "is_junction", None)
            if parent.is_symlink() or (is_junction is not None and is_junction()):
                raise SystemExit("NO_LOSS_OUTPUT_LINKED_PARENT")



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
    outputs = (candidate, receipt, diff_path)
    assert_new_output_paths(original, outputs)
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    assert_new_output_paths(original, outputs)
    # Exclusive creation fails safely on a race or newly injected symlink.
    with candidate.open("xb") as handle:
        handle.write(changed)
    with diff_path.open("xb") as handle:
        handle.write(diff)
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
    with receipt.open("xb") as handle:
        handle.write((json.dumps(record, indent=2) + "\n").encode("utf-8"))
    print("E06_R18_OWNER1_NSI_ADAPTER_SOURCE_SHA_PASS")


if __name__ == "__main__":
    main()
