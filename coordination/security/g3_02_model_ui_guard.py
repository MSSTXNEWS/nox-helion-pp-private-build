"""Read-only NOX V16 owner-P03 UI security regression gate.

This gate does not authorize downloads, install models, or modify owner source.
It detects known, exact SOURCE-only acceptance mistakes in PR #5 and returns
HOLD until independently reviewed native owner/rights/hardware evidence exists.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def inspect_model_window(source: str) -> dict[str, object]:
    findings: list[dict[str, str]] = []
    unlocks_download = bool(re.search(r"_download\.IsEnabled\s*=\s*eligible\s*;", source))
    manual_vram = bool(re.search(r"decimal\.TryParse\s*\(\s*_availableVram\.Text", source))
    if unlocks_download and manual_vram:
        findings.append({
            "gate": "G3-02-07-REAL-HARDWARE",
            "code": "MANUAL_VRAM_UNLOCKS_MODEL_UI",
            "owner": "E03/P03",
            "note": "The editable VRAM field influences download eligibility; real native GPU evidence is not shown by this source.",
        })
    syntax_only_license = bool(re.search(r"IsHttpsEvidence\s*\(\s*artifact\.LicenseEvidenceUrl\s*\)", source))
    no_native_verifier_input = "Func<ModelArtifactEvidence, bool>" not in source and "NativeRightsVerifier" not in source
    if unlocks_download and syntax_only_license and no_native_verifier_input:
        findings.append({
            "gate": "G3-02-07-MODEL-RIGHTS",
            "code": "LICENSE_URL_FORMAT_NOT_LICENSE_ATTESTATION",
            "owner": "E03/P03",
            "note": "An HTTPS license-evidence URL is a format check, not a signed rights receipt; a separate native owner gate is required.",
        })
    return {
        "schema": "NOX_V16_G3_02_MODEL_UI_AUDIT_V1",
        "scope": "SOURCE_ONLY_NOT_WINDOWS_SECURITY_CERTIFICATION",
        "status": "HOLD" if findings else "NO_KNOWN_PATTERN_FOUND_REQUIRES_NATIVE_VERIFICATION",
        "findings": findings,
        "review_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only P03 owner UI provenance regression")
    parser.add_argument("source", type=Path, help="Exact PR #5 ModelDownloaderWindow.xaml.cs source")
    args = parser.parse_args()
    source = args.source.read_text(encoding="utf-8")
    result = inspect_model_window(source)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
