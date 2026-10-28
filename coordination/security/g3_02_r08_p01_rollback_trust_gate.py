#!/usr/bin/env python3
"""E06 R08: read-only fail-closed test of pinned P01 rollback source (NOT native QA)."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

OWNER_COMMIT = "8e42bb15aecbee8412c342b0e9049b6cce044297"
OWNER_PATH = "stage/proposals/P01/C09/Installer/NOX-HELION-Setup.nsi"
OWNER_GIT_BLOB = "75ce8a88bfbcf5d79dccab677bc2fbe6c82bb042"
BASELINE_COMMIT = "0b3a7d435be735148d64171deb9027093a89646e"
BASELINE_TREE = "f108d604c444f718b32aaecfd07b90b8f91b9a6f"

def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()

def block(source: str, begin: str, end: str) -> str:
    start = source.find(begin)
    if start < 0:
        return ""
    finish = source.find(end, start + len(begin))
    return "" if finish < 0 else source[start:finish + len(end)]

def assess(source: str) -> dict:
    install = block(source, 'Section "NOX HELION application"', 'SectionEnd')
    restore = block(source, 'Function RestorePrevious', 'FunctionEnd')
    restore_call = install.find("Call RestorePrevious")
    preflight = install.find("Preflight:")
    move_current = restore.find('Rename "$INSTDIR" "$TmpDir"')
    activate_backup = restore.find('Rename "$BackupDir" "$INSTDIR"')
    earliest_move = min((x for x in (move_current, activate_backup) if x >= 0), default=-1)
    before_move = restore[:earliest_move] if earliest_move >= 0 else ""
    facts = {
        "rollback_skips_install_preflight": restore_call >= 0 and (preflight < 0 or restore_call < preflight),
        "backup_activated": activate_backup >= 0,
        "marker_only_backup_admission": 'IfFileExists "$BackupDir\\nox-p01-owned.txt"' in restore,
        "backup_manifest_read_before_move": "payload.sha256.json" in before_move,
        "ancestor_gate_before_move": "Call AssertRollbackPathSafety" in before_move,
        "digest_gate_before_move": "Call AssertRollbackBackupDigest" in before_move,
    }
    holds = []
    if not install or not restore:
        holds.append("MISSING_INSTALL_OR_RESTORE_SOURCE")
    if facts["backup_activated"] and facts["rollback_skips_install_preflight"]:
        holds.append("ROLLBACK_BYPASSES_NORMAL_PREFLIGHT")
    if facts["backup_activated"] and not facts["ancestor_gate_before_move"]:
        holds.append("ROLLBACK_PATH_REPARSE_NOT_ATTESTED_AT_COMMIT")
    if facts["backup_activated"] and not facts["digest_gate_before_move"]:
        holds.append("BACKUP_CONTENT_NOT_ATTESTED_BEFORE_ACTIVATION")
    if facts["backup_activated"] and facts["marker_only_backup_admission"] and not facts["backup_manifest_read_before_move"]:
        holds.append("BACKUP_MARKER_PRESENT_NOT_PROVEN_TRUSTED")
    return {"status": "HOLD_OWNER_FIX_REQUIRED" if holds else "STATIC_CALLS_PRESENT_NOT_WINDOWS_ACCEPTED",
            "facts": facts, "holds": holds,
            "notice": "Static call names cannot prove implementation, manifest authenticity, native rollback or safety."}

FIXTURE = r'''Section "NOX HELION application"
  If $RollbackRequested == 1
    Call RestorePrevious
  EndIf
  Preflight:
  nsExec::ExecToStack 'powershell -File Preflight-InstallPath.ps1'
SectionEnd
Function RestorePrevious
  IfFileExists "$BackupDir\nox-p01-owned.txt" 0 NoPrevious
  Rename "$INSTDIR" "$TmpDir"
  Rename "$BackupDir" "$INSTDIR"
FunctionEnd
'''

def self_test() -> int:
    checks = []
    bad = assess(FIXTURE)
    checks.append(("owner_pattern_hold", bad["status"] == "HOLD_OWNER_FIX_REQUIRED"))
    checks.append(("preflight_bypass", "ROLLBACK_BYPASSES_NORMAL_PREFLIGHT" in bad["holds"]))
    checks.append(("missing_ancestor_gate", "ROLLBACK_PATH_REPARSE_NOT_ATTESTED_AT_COMMIT" in bad["holds"]))
    checks.append(("missing_digest_gate", "BACKUP_CONTENT_NOT_ATTESTED_BEFORE_ACTIVATION" in bad["holds"]))
    checks.append(("marker_is_not_trust", "BACKUP_MARKER_PRESENT_NOT_PROVEN_TRUSTED" in bad["holds"]))
    path_only = FIXTURE.replace('  Rename "$INSTDIR"', '  Call AssertRollbackPathSafety\n  Rename "$INSTDIR"')
    checks.append(("path_only_insufficient", "BACKUP_CONTENT_NOT_ATTESTED_BEFORE_ACTIVATION" in assess(path_only)["holds"]))
    digest_only = FIXTURE.replace('  Rename "$INSTDIR"', '  Call AssertRollbackBackupDigest\n  Rename "$INSTDIR"')
    checks.append(("digest_only_insufficient", "ROLLBACK_PATH_REPARSE_NOT_ATTESTED_AT_COMMIT" in assess(digest_only)["holds"]))
    late = FIXTURE.replace('  Rename "$BackupDir" "$INSTDIR"', '  Rename "$BackupDir" "$INSTDIR"\n  Call AssertRollbackPathSafety\n  Call AssertRollbackBackupDigest')
    checks.append(("post_move_too_late", assess(late)["status"] == "HOLD_OWNER_FIX_REQUIRED"))
    both = FIXTURE.replace('  Rename "$INSTDIR"', '  Call AssertRollbackPathSafety\n  Call AssertRollbackBackupDigest\n  Rename "$INSTDIR"')
    checks.append(("calls_do_not_prove_windows", assess(both)["status"] == "STATIC_CALLS_PRESENT_NOT_WINDOWS_ACCEPTED"))
    checks.append(("missing_source_hold", assess("")["status"] == "HOLD_OWNER_FIX_REQUIRED"))
    checks.append(("mismatch_pin_detectable", git_blob_sha1(FIXTURE.encode()) != OWNER_GIT_BLOB))
    for label, good in checks:
        print(("PASS " if good else "FAIL ") + label)
    print(str(sum(x for _, x in checks)) + "/" + str(len(checks)) + " synthetic checks")
    return 0 if all(x for _, x in checks) else 1

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--owner-nsi", type=Path)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.owner_nsi:
        parser.error("Supply --owner-nsi pinned PR28 checkout, or --self-test")
    raw = args.owner_nsi.read_bytes()
    blob = git_blob_sha1(raw)
    result = {"owner_commit": OWNER_COMMIT, "owner_path": OWNER_PATH,
              "expected_git_blob": OWNER_GIT_BLOB, "actual_git_blob": blob,
              "source_sha256": hashlib.sha256(raw).hexdigest(),
              "baseline_commit": BASELINE_COMMIT, "baseline_tree": BASELINE_TREE}
    if blob != OWNER_GIT_BLOB:
        result["status"] = "HOLD_PREIMAGE_DRIFT"
        print(json.dumps(result, indent=2))
        return 3
    result.update(assess(raw.decode("utf-8", "strict")))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] == "HOLD_OWNER_FIX_REQUIRED" else 0

if __name__ == "__main__":
    raise SystemExit(main())
