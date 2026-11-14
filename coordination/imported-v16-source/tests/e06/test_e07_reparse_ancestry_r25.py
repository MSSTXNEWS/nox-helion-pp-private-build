"""Fail-closed source guard for the original E07 immutable handoff.
Source-level only; the real Windows reparse and E07 tests are NOT_RUN here.
"""
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "coordination/e06/Emit-E07ImmutableHandoff.ps1"


def guarded(text):
    name = "function AssertE07NoReparseAncestors([string]$path) {"
    if text.count(name) != 1:
        return False
    walker = text.split(name, 1)[1].split("function FileSha(", 1)[0]
    filehash = text.split("function FileSha([string]$path) {", 1)[1].split("$commit=", 1)[0]
    out = text.split("if (Test-Path -LiteralPath $Output)", 1)[1].split("# FileMode.CreateNew", 1)[0]
    checks = ("GetFullPath($path)", "while ($true)", "GetDirectoryName($cursor)",
              "Test-Path -LiteralPath $cursor", "Get-Item -LiteralPath $cursor -Force",
              "FileAttributes]::ReparsePoint", "E07_REPARSE_ANCESTOR")
    return (
        all(check in walker for check in checks)
        and "AssertE07NoReparseAncestors $path" in filehash
        and filehash.index("AssertE07NoReparseAncestors $path") < filehash.index("Get-FileHash")
        and out.count("AssertE07NoReparseAncestors $Output") == 2
        and out.index("AssertE07NoReparseAncestors $Output") < out.index("New-Item -ItemType Directory -Path $parent")
        and out.rindex("AssertE07NoReparseAncestors $Output") > out.index("New-Item -ItemType Directory -Path $parent")
    )


class E07ReparseAncestry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = SOURCE.read_text(encoding="utf-8")

    def test_complete_input_output_ancestry_protected(self):
        self.assertTrue(guarded(self.original))

    def test_omitting_hash_input_fence_fails(self):
        self.assertFalse(guarded(self.original.replace(" AssertE07NoReparseAncestors $path\n", "", 1)))

    def test_omitting_output_fence_fails(self):
        self.assertFalse(guarded(self.original.replace("AssertE07NoReparseAncestors $Output\n", "", 1)))

    def test_broken_parent_traversal_fails(self):
        self.assertFalse(guarded(self.original.replace("GetDirectoryName($cursor)", "GetDirectoryName($path)", 1)))

    def test_missing_reparse_check_fails(self):
        self.assertFalse(guarded(self.original.replace("FileAttributes]::ReparsePoint", "FileAttributes]::Normal", 1)))

    def test_no_lost_source_sha_and_release_gate(self):
        for needle in ("E07_OWNER_729_FILE_SHA_DIFFERS", "E07_OWNER_SOURCE_PART_IDENTITY_MISMATCH",
                       "release_accepted=$false", "independent_e07_cases_accepted=0"):
            self.assertIn(needle, self.original)


if __name__ == "__main__":
    unittest.main()
