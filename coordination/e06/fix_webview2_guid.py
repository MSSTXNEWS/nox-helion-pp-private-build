"""E06 R11 staging only: repair false WebView2 registry GUID in P01 owner preflight.

Exact original SHA pin; leave user files and canonical owner source unchanged.
Microsoft docs: https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution
"""
from pathlib import Path
from hashlib import sha256
from difflib import unified_diff
import json
import shutil
import sys

RUN_ID = "NOX-V16-E06-R11-20261028-WEBVIEW2-GUID"
EXPECTED = "8413580656bace887478c9f82e72433987ad8e4a552af6e67c3531b09d545239"
BAD = "{F3017226-FE2A-4295-8BDF-00C3A7E4C5}"
GOOD = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

def digest(value: bytes) -> str:
    return sha256(value).hexdigest()

def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python fix_webview2_guid.py STAGED_R11_ROOT")
    root = Path(sys.argv[1]).resolve(strict=True)
    path = root / "Installer" / "Preflight-InstallPath.ps1"
    if path.is_symlink() or not path.is_file():
        raise SystemExit("OWNER1_INSTALL_PREFLIGHT_PATH_HOLD")
    preimage = path.read_bytes()
    if digest(preimage) != EXPECTED:
        raise SystemExit("OWNER1_PREFLIGHT_PREIMAGE_SHA_HOLD")
    original = preimage.decode("utf-8-sig")
    if original.count(BAD) != 3 or GOOD in original:
        raise SystemExit("OWNER1_PREFLIGHT_GUID_CARDINALITY_HOLD")
    modified = original.replace(BAD, GOOD)
    # Encoding preservation. Original in R08 is UTF-8 without BOM.
    after = modified.encode("utf-8")
    if not after or not modified.count(GOOD) == 3:
        raise SystemExit("GUID_REPLACEMENT_HOLD")
    receipt_dir = root.parent / "E06_R11_OWNER1_WEBVIEW2_ROLLBACK"
    if receipt_dir.exists():
        raise SystemExit("ROLLBACK_PATH_EXISTS_HOLD")
    receipt_dir.mkdir()
    rollback_file = receipt_dir / "Preflight-InstallPath.ps1.original"
    rollback_file.write_bytes(preimage)
    if digest(rollback_file.read_bytes()) != EXPECTED:
        raise SystemExit("OWNER1_ROLLBACK_READBACK_HOLD")
    path.write_bytes(after)
    if path.read_bytes() != after:
        raise SystemExit("OWNER1_PATCH_READBACK_HOLD")
    diff = "".join(unified_diff(original.splitlines(True), modified.splitlines(True),
                                fromfile="Preflight-InstallPath.ps1.original",
                                tofile="Preflight-InstallPath.ps1.staged"))
    receipt = {
        "schema": "NOX-E06-OWNER1-WEBVIEW2-GUID-v1",
        "run_id": RUN_ID,
        "owner": 1,
        "executed_by": 6,
        "state": "STAGED_DIAGNOSTIC_OWNER_APPROVAL_REQUIRED",
        "path": "R11/Installer/Preflight-InstallPath.ps1",
        "pre_sha256": EXPECTED,
        "post_sha256": digest(after),
        "patch_sha256": digest(diff.encode("utf-8")),
        "rollback_original_sha256": digest(rollback_file.read_bytes()),
        "replacements": 3,
        "correct_guid": GOOD,
        "nsis_lifecycle_accepted": False,
        "e07_accepted": False,
        "release_accepted": False
    }
    receipt_path = receipt_dir / "WEBVIEW2_GUID_REPAIR_RECEIPT.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    if json.loads(receipt_path.read_text(encoding="utf-8")) != receipt:
        raise SystemExit("GUID_REPAIR_RECEIPT_READBACK_HOLD")
    print("E06_R11_CORRECT_MICROSOFT_WEBVIEW2_REGISTRY_GUID_STAGED", receipt["post_sha256"])
if __name__ == "__main__":
    main()
