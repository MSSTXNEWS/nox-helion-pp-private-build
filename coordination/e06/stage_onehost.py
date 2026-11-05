"""E06 owner scope: apply ONE additive WPF -> Python diagnostic hook to pinned R08.
Stage only. Never writes originals, model files, user data or a second router.
"""
from __future__ import annotations
import hashlib, json, difflib, sys
from pathlib import Path

RUN_ID = "NOX-V16-E06-EXPRESS-ONEHOST-20261028-R10"
ORIGINAL_BRIDGE_SHA256 = "ee978b13a7f1058b1a509a506feef495efe440f410ab63103088fefa08e1d86f"
ORIGINAL_EXE_SHA256 = "4e488372cf3f6410d268a7ef72b3e4b359a7a3e6642c7a16ac2e6f7eb06fc5f3"
ANCHOR = 'case "models.preflight":\n                    await RunDiagnosticsAsync(requestId);\n                    return;'
REPLACEMENT = 'case "models.preflight":\n                    await RunDiagnosticsAsync(requestId);\n                    await ReportOriginalPythonDiagnosticAsync(requestId, route);\n                    return;'

def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def main():
    if len(sys.argv) != 4:
        raise SystemExit("USAGE: stage_onehost.py STAGED_R11 E06_ADDON_CS PYTHON_EXE")
    stage = Path(sys.argv[1]).resolve()
    e06 = Path(sys.argv[2]).resolve()
    python_exe = Path(sys.argv[3]).resolve()
    original = stage / "Integration" / "Pack01HostBridge.cs"
    if not original.is_file() or original.is_symlink():
        raise SystemExit("OWNER6_WPF_SOURCE_MISSING")
    before = original.read_bytes()
    if digest(before) != ORIGINAL_BRIDGE_SHA256:
        raise SystemExit("OWNER6_WPF_PREIMAGE_SHA_HOLD")
    old = before.decode("utf-8-sig")
    if old.count(ANCHOR) != 1:
        raise SystemExit("OWNER6_WPF_ROUTE_PREIMAGE_DRIFT")
    new_text = old.replace(ANCHOR, REPLACEMENT)
    patched = new_text.encode("utf-8")
    if not e06.is_file() or e06.is_symlink():
        raise SystemExit("OWNER6_NEW_PARTIAL_MISSING")
    extra = e06.read_bytes()
    if b"ReportOriginalPythonDiagnosticAsync" not in extra:
        raise SystemExit("OWNER6_PARTIAL_FUNCTION_MISSING")
    if not python_exe.is_file() or python_exe.is_symlink() or digest(python_exe.read_bytes()) != ORIGINAL_EXE_SHA256:
        raise SystemExit("ORIGINAL_PYTHON_EXE_SHA_HOLD")
    dest = stage / "Integration" / "OriginalPythonDiagnosticBridge.cs"
    if dest.exists():
        raise SystemExit("OWNER_CONFLICT_EXISTING_ADAPTER")
    original.write_bytes(patched)
    dest.write_bytes(extra)
    patch = "".join(difflib.unified_diff(old.splitlines(True), new_text.splitlines(True),
                                         fromfile="Pack01HostBridge.cs.pre", tofile="Pack01HostBridge.cs.post"))
    records = [
        {"path": "R11/Integration/Pack01HostBridge.cs", "owner": 6,
         "pre_sha256": digest(before), "post_sha256": digest(patched),
         "patch_sha256": digest(patch.encode("utf-8"))},
        {"path": "R11/Integration/OriginalPythonDiagnosticBridge.cs", "owner": 6,
         "pre_sha256": None, "post_sha256": digest(extra),
         "patch_sha256": digest(extra)}
    ]
    receipt = {"schema": "NOX-E06-ONEHOST-R10-SOURCE-RECEIPT",
               "run_id": RUN_ID, "original_python_binary_sha256": ORIGINAL_EXE_SHA256,
               "original_archive_sha256": "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a",
               "files": records, "owner3_compiler_overlay": "REQUIRES_OWNER_APPROVAL",
               "release_accepted": False, "windows_runtime_accepted": False}
    out = stage.parent/"E06_R10_SOURCE_RECEIPT.json"
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
    print("E06_R10_STAGED_ONEHOST_SHA_PIN_PASS", digest(patched), digest(extra))
if __name__ == "__main__":
    main()
