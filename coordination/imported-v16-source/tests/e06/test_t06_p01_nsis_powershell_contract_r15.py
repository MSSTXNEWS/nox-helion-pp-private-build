"""T06 R15: exact NSIS→PowerShell caller/callee contract, SOURCE ONLY.

Prevents a donor from silently adding an unsupported switch (R09 -PathOnly)
or merging caller and verifier changes separately. No installer is executed.
Owner T04 original version choices remain unchanged.
"""
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = Path(os.environ.get("NOX_PINNED_P01_INSTALLER_PATH",
    ROOT / "stage" / "proposals" / "P01" / "C09" / "Installer"))
SCRIPTS = ("Preflight-InstallPath.ps1", "Verify-Payload.ps1",
           "Remove-InstalledPayload.ps1")


def check_script_contract(nsis: str, scripts: dict[str, str]) -> dict[str, int]:
    """Reject unsupported named switches before any optional NSIS integration."""
    commands = re.findall(r"nsExec::ExecToStack\s+'([^'\r\n]+)'", nsis, re.I)
    if not commands:
        raise ValueError("P01_NSIS_POWERSHELL_CALLS_MISSING")
    counts = {}
    for name in SCRIPTS:
        if name not in scripts:
            raise ValueError("P01_SCRIPT_MISSING:" + name)
        header = scripts[name].split("$ErrorActionPreference", 1)[0]
        declared = {p.casefold() for p in re.findall(
            r"\[(?:string|switch|int|bool)\]\s*\$(\w+)", header, re.I)}
        if not declared:
            raise ValueError("P01_SCRIPT_SIGNATURE_MISSING:" + name)
        selected = [cmd for cmd in commands if ("\\" + name + '"').casefold()
                    in cmd.casefold()]
        if not selected:
            raise ValueError("P01_NSIS_SCRIPT_UNCALLED:" + name)
        for cmd in selected:
            tail = cmd.casefold().split(("\\" + name + '"').casefold(), 1)[1]
            supplied = {m.casefold() for m in re.findall(
                r"-([A-Za-z][A-Za-z0-9]*)\b", tail)}
            unknown = supplied - declared
            if unknown:
                raise ValueError("P01_NSIS_UNDECLARED_SCRIPT_FLAG:" + name +
                                 ":" + ",".join(sorted(unknown)))
            # Powershell's Mandatory=true is a contract too: fail before
            # activation if a caller omitted a required native parameter.
            mandatory = {m.casefold() for m in re.findall(
                r"\[Parameter\(Mandatory=\$true\)\]\s*"
                r"\[(?:string|int|bool)\]\s*\$(\w+)", header, re.I)}
            if not mandatory.issubset(supplied):
                raise ValueError("P01_NSIS_MISSING_MANDATORY_FLAG:" + name)
        counts[name] = len(selected)
    if (counts["Preflight-InstallPath.ps1"] < 1
            or counts["Verify-Payload.ps1"] < 2
            or counts["Remove-InstalledPayload.ps1"] < 1):
        raise ValueError("P01_NSIS_CALL_COVERAGE_INCOMPLETE")
    return counts


class P01NsisSourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nsis = (INSTALLER / "NOX-HELION-Setup.nsi").read_text(encoding="utf-8")
        cls.scripts = {name: (INSTALLER / name).read_text(encoding="utf-8")
                       for name in SCRIPTS}

    def test_live_three_callees_match_all_nsis_named_flags(self):
        result = check_script_contract(self.nsis, self.scripts)
        self.assertGreaterEqual(sum(result.values()), 4)

    def test_old_r09_unknown_pathonly_fails_closed(self):
        before = '-InstallRoot "$INSTDIR"'
        self.assertIn(before, self.nsis)
        broken = self.nsis.replace(before, before + " -PathOnly", 1)
        with self.assertRaisesRegex(ValueError, "P01_NSIS_UNDECLARED_SCRIPT_FLAG"):
            check_script_contract(broken, self.scripts)

    def test_partial_donor_verifier_api_fails_closed(self):
        original = '-AllowInstalledMetadata'
        self.assertIn(original, self.nsis)
        broken = self.nsis.replace(original,
            original + ' -MissingNativeVerifierFlag', 1)
        with self.assertRaisesRegex(ValueError, "P01_NSIS_UNDECLARED_SCRIPT_FLAG"):
            check_script_contract(broken, self.scripts)

    def test_source_safety_boundaries_not_replaced(self):
        self.assertNotRegex(self.nsis, r"(?i)\bRMDir\s+/r\b")
        self.assertIn("P01_INSTALL_REPARSE_ANCESTOR",
                      self.scripts["Preflight-InstallPath.ps1"])
        self.assertIn("P01_WEBVIEW2_RUNTIME_MISSING",
                      self.scripts["Preflight-InstallPath.ps1"])
        self.assertIn("Assert-VerifiedEntry",
                      self.scripts["Remove-InstalledPayload.ps1"])
        self.assertIn("Get-FileHash", self.scripts["Verify-Payload.ps1"])


if __name__ == "__main__":
    unittest.main()
