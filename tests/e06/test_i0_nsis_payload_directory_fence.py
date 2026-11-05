"""I0 P01: exact original E06 NSIS payload-directory fence, source-only.

No Windows compile or installed E07 assertion. Pin the precise Git owner blob
so a later packager change cannot silently remove the guard from E06 staging.
"""
from __future__ import annotations
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"
EXPECTED_BUILDER_GIT_BLOB = "e113f56afb92c18514d8e793e974cf2098919c53"
START = "# I0 P01: inspect the entire published directory graph BEFORE enumerating files."
END = "# Include the existing program files in the conservative NSIS manifest."

def check_guard(script: str) -> None:
    if script.count(START) != 1 or script.count(END) != 1:
        raise ValueError("I0_NSIS_DIRECTORY_BARRIER_MISSING")
    start, end = script.index(START), script.index(END)
    if not start < end < script.index("$entries=@(") < script.index("& $makensisPath"):
        raise ValueError("I0_NSIS_DIRECTORY_BARRIER_TOO_LATE")
    body = script[start:end]
    checks = (
        "Assert-E06PlainPathAncestors -Candidate $payload -Scope 'NSIS_PAYLOAD'",
        "$payloadRootInfo=Get-Item -LiteralPath $payload -Force -ErrorAction Stop",
        "$payloadRootInfo.PSIsContainer",
        "throw 'E06_NSIS_PAYLOAD_ROOT_UNSAFE_HOLD'",
        "$payloadPending=New-Object 'System.Collections.Generic.Stack[string]'",
        "$payloadPending.Push($payload)",
        "$payloadDirectory=$payloadPending.Pop()",
        "Assert-E06PlainPathAncestors -Candidate $payloadDirectory -Scope 'NSIS_PAYLOAD_DIRECTORY'",
        "Get-ChildItem -LiteralPath $payloadDirectory -Directory -Force -ErrorAction Stop",
        "($childDirectory.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0",
        "throw 'E06_NSIS_PAYLOAD_DIRECTORY_REPARSE_HOLD'",
        "$payloadPending.Push($childDirectory.FullName)",
    )
    if any(body.count(part) != 1 for part in checks):
        raise ValueError("I0_NSIS_DIRECTORY_BARRIER_INCOMPLETE")
    if body.index("throw 'E06_NSIS_PAYLOAD_DIRECTORY_REPARSE_HOLD'") >= body.index(
            "$payloadPending.Push($childDirectory.FullName)"):
        raise ValueError("I0_NSIS_DIRECTORY_TRAVERSED_BEFORE_REPARSE_CHECK")
    # Recursive enumeration could follow a junction BEFORE the node is rejected.
    if "-Recurse" in body or "-FollowSymlink" in body:
        raise ValueError("I0_NSIS_UNBOUNDED_DIRECTORY_TRAVERSAL")
    if script.count("Assert-E06PlainPathAncestors -Candidate $_.FullName -Scope 'NSIS_PAYLOAD_FILE'") != 1:
        raise ValueError("I0_NSIS_FILE_ANCESTOR_FENCE_MISSING")

class NsIsDirectoryFenceSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = BUILDER.read_text(encoding="utf-8")

    def test_exact_builder_git_source_pin(self):
        result = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD:" +
             BUILDER.relative_to(ROOT).as_posix()],
            capture_output=True, text=True, check=True, timeout=15)
        self.assertEqual(result.stdout.strip(), EXPECTED_BUILDER_GIT_BLOB)

    def test_guard_precedes_manifest_and_nsis_and_is_acyclic(self):
        check_guard(self.script)

    def test_without_directory_reparse_rejection_fails(self):
        broken = self.script.replace(
            "throw 'E06_NSIS_PAYLOAD_DIRECTORY_REPARSE_HOLD'",
            "Write-Host 'unsafe bypass'", 1)
        with self.assertRaisesRegex(ValueError, "I0_NSIS_DIRECTORY_BARRIER_INCOMPLETE"):
            check_guard(broken)

    def test_without_root_anchor_fails(self):
        broken = self.script.replace(
            "Assert-E06PlainPathAncestors -Candidate $payload -Scope 'NSIS_PAYLOAD'",
            "# missing root anchor", 1)
        with self.assertRaisesRegex(ValueError, "I0_NSIS_DIRECTORY_BARRIER_INCOMPLETE"):
            check_guard(broken)

    def test_recursive_directory_enumeration_fails(self):
        broken = self.script.replace(
            "Get-ChildItem -LiteralPath $payloadDirectory -Directory -Force -ErrorAction Stop",
            "Get-ChildItem -LiteralPath $payloadDirectory -Directory -Recurse -Force -ErrorAction Stop", 1)
        with self.assertRaisesRegex(ValueError, "I0_NSIS_UNBOUNDED_DIRECTORY_TRAVERSAL"):
            check_guard(broken)

    def test_no_original_installer_source_modified(self):
        original = (ROOT / "stage/proposals/P01/C09/Installer/NOX-HELION-Setup.nsi").read_text("utf-8")
        self.assertIn('Rename "$INSTDIR" "$BackupDir"', original)
        self.assertNotIn("I0_NSIS_PAYLOAD_DIRECTORY_REPARSE_HOLD", original)
        self.assertIn("C11_NSIS_ROLLBACK_OLD_PAYLOAD_SHA_GATE_STAGED", self.script)

if __name__ == "__main__":
    unittest.main()
