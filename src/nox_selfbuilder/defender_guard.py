"""Existing Windows Defender antivirus gate for reviewed NOX donor files.

Static PowerShell script, file path via process environment, no shell commands
from scraped web pages, no exclusions, policy changes or auto-execution.
A completed scan does NOT prove downloaded code is benign or license-cleared.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_REPORT_BYTES = 4096

_SCRIPT = r"""$ErrorActionPreference='Stop'
try {
 Import-Module Defender -ErrorAction Stop
 $p=$env:NOX_DONOR_SCAN_FILE
 if ([string]::IsNullOrWhiteSpace($p) -or -not (Test-Path -LiteralPath $p -PathType Leaf)) {exit 9}
 $v=Get-MpComputerStatus -ErrorAction Stop
 if ($v.AMRunningMode -ne 'Normal' -or $v.RealTimeProtectionEnabled -ne $true) {
   @{state='DEFENDER_INACTIVE'} | ConvertTo-Json -Compress
   exit 9
 }
 Start-MpScan -ScanType CustomScan -ScanPath $p -ErrorAction Stop
 $threats=@(Get-MpThreatDetection -ErrorAction Stop)
 if ($threats.Count -gt 0) {
   @{state='DEFENDER_DETECTIONS_REQUIRE_REVIEW';count=$threats.Count}|ConvertTo-Json -Compress
   exit 8
 }
 @{state='DEFENDER_SCAN_COMPLETED_REVIEW_REQUIRED'}|ConvertTo-Json -Compress
 exit 0
} catch {
 @{state='DEFENDER_UNAVAILABLE'}|ConvertTo-Json -Compress
 exit 9
}
"""


class DefenderHold(RuntimeError):
    pass


def _sha(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_donor_file(path, *, staging_root, run=subprocess.run, platform=None):
    """Scan one immutable scoped donor; fail-closed, never mark production ready."""
    if platform is None:
        platform = os.name
    if platform != "nt":
        return {"status": "HOLD", "reason": "DEFENDER_WINDOWS_ONLY",
                "scan_completed": False, "source_executed": False}
    root = Path(staging_root)
    target = Path(path)
    if not root.is_dir() or root.is_symlink():
        raise DefenderHold("DEFENDER_APPROVED_STAGING_REQUIRED")
    if not target.is_file() or target.is_symlink():
        raise DefenderHold("DEFENDER_REGULAR_DONOR_FILE_REQUIRED")
    safe_root = root.resolve(strict=True)
    safe = target.resolve(strict=True)
    if not safe.is_relative_to(safe_root):
        raise DefenderHold("DEFENDER_STAGING_ESCAPE_DENIED")
    if any(p.is_symlink() for p in (target, *target.parents) if p != root and p.is_relative_to(root)):
        raise DefenderHold("DEFENDER_PATH_SYMLINK_DENIED")
    size = safe.stat().st_size
    if not 0 < size <= MAX_FILE_BYTES:
        raise DefenderHold("DEFENDER_BOUNDED_FILE_REQUIRED")
    before = _sha(safe)
    env = dict(os.environ)
    env["NOX_DONOR_SCAN_FILE"] = str(safe)
    try:
        p = run(["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-Command", _SCRIPT], env=env, capture_output=True,
                timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "HOLD", "reason": "DEFENDER_SCAN_UNAVAILABLE",
                "scan_completed": False, "source_executed": False,
                "sha256": before}
    if _sha(safe) != before:
        raise DefenderHold("DEFENDER_POSTSCAN_SOURCE_CHANGED")
    try:
        raw = p.stdout[-MAX_REPORT_BYTES:]
        result = json.loads(raw.decode("utf-8-sig").strip())
    except (ValueError, UnicodeError, AttributeError):
        result = {}
    completed = (p.returncode == 0 and
                 result.get("state") == "DEFENDER_SCAN_COMPLETED_REVIEW_REQUIRED")
    return {"schema": "NOX-DEFENDER-DONOR-RECEIPT-v1",
            "status": "SCAN_COMPLETED_REVIEW_REQUIRED" if completed else "HOLD",
            "reason": None if completed else result.get("state", "DEFENDER_UNVERIFIED"),
            "sha256": before, "scan_completed": completed,
            "malware_free_proven": False, "license_approved": False,
            "production_admitted": False, "source_executed": False}
