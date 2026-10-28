"""Independent E06 read-only SOURCE regression for the existing Creative asset import.

TestID: E06-W1-03-R16-CREATIVE-IMPORT-JUNCTION-WRITE
Owner: W1.03 E06 QA; NEVER modifies CreativeHostBridge.cs.
Run with: python -m unittest -v test_creative_import_reparse_r16.py
Set NOX_CREATIVE_BRIDGE_PATH to the full source path in the pinned PR162 checkout.
SOURCE-only static admission and sandboxed link demonstration; NOT Windows E2E.
"""
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest

SOURCE = Path(os.getenv("NOX_CREATIVE_BRIDGE_PATH", "integrations/creative/bridge/CreativeHostBridge.cs"))


def import_method(source: str) -> str:
    begin = source.index("private void ImportCreativeAsset(")
    end = source.index("private async Task OpenCreativeProjectorAsync(", begin)
    method = source[begin:end]
    # Exclude comment-only matches from static security assertions.
    method = re.sub(r"/\*.*?\*/", "", method, flags=re.S)
    return re.sub(r"(?m)//[^\n]*", "", method)


class CreativeImportTrustR16(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.method = import_method(SOURCE.read_text(encoding="utf-8-sig"))

    def test_01_project_id_is_canonical(self):
        self.assertIn('Regex.IsMatch(project,@"\A[a-zA-Z0-9_-]{1,48}\z")', self.method)

    def test_02_file_size_budget_retained(self):
        self.assertIn("268435456L", self.method)

    def test_03_nonclobbering_random_destination_retained(self):
        self.assertIn('Guid.NewGuid().ToString("N")', self.method)
        self.assertRegex(self.method, r"File\.Copy\(path,\s*dest,\s*overwrite:false\)")

    def test_04_reparse_ancestor_gate_before_file_copy(self):
        """RED on pinned source: path allowlist does not prevent junction redirection."""
        before_copy = self.method.split("File.Copy(path,dest,overwrite:false)", 1)[0]
        self.assertIn("DirectoryInfo", before_copy,
                      "HOLD: import destination ancestry is not inspected")
        self.assertIn("FileAttributes.ReparsePoint", before_copy,
                      "HOLD: no junction/symlink gate before File.Copy")
        self.assertRegex(before_copy, r"(Path\.GetFullPath|GetFinalPathNameByHandle|OpenHandle)",
                         "HOLD: ensure path containment against trusted data root")

    def test_05_sandboxed_directory_link_redirect_is_real(self):
        """Demonstrate the directory-redirection primitive entirely in a temp sandbox."""
        with tempfile.TemporaryDirectory(prefix="nox-e06-r16-") as tmp:
            root = Path(tmp)
            projects = root / "trusted" / "creative" / "projects"
            outside = root / "outside" / "assets"
            projects.mkdir(parents=True)
            outside.mkdir(parents=True)
            source = root / "selected.png"
            source.write_bytes(b"sandbox-only")
            link = projects / "safe_project"
            try:
                link.symlink_to(root / "outside", target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlinks unavailable in sandbox: {exc}")
            destination = link / "assets" / "random_selected.png"
            shutil.copyfile(source, destination)
            self.assertEqual((outside / destination.name).read_bytes(), b"sandbox-only")


if __name__ == "__main__":
    unittest.main()
