"""B03: real original T06 Windows packager stages PowerShell 5.1 comments.

Source-level regression only; it does not install a Windows executable or grant E07.
"""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "coordination/e06/t06_package_original_onehost.py"
SPEC = importlib.util.spec_from_file_location("b03_actual_original_t06", ORIGINAL)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class B03OriginalT06RemoverComments(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        r11 = Path(self.temp.name) / "R11"
        installer = r11 / "Installer"
        installer.mkdir(parents=True)
        self.script = installer / "Remove-InstalledPayload.ps1"
        self.before = (
            "# approved NX03-only disposable test fixture\n"
            + MOD._B03_PS51_REMOVER_COMMENT_BLOCK
            + "foreach ($entry in $checked) {\n"
            + "  throw 'P01_UNINSTALL_POST_REMOVE_RESIDUE'\n"
            + "}\n"
            + "Write-Output 'P01_UNINSTALL_PAYLOAD_PASS'\n"
        ).encode("utf-8")
        self.script.write_bytes(self.before)

    def receipt(self):
        return {
            "changed": True,
            "reviewed_git_blob": MOD._B03_REVIEWED_REMOVE_GIT_BLOB,
            "original_donor_changed": False,
            "release_accepted": False,
            "independent_e07": "NOT_RUN",
            "staged_sha256": hashlib.sha256(self.script.read_bytes()).hexdigest(),
        }

    def test_only_five_reviewed_comments_change_and_receipt_is_diagnostic(self):
        receipt = MOD.stage_reviewed_remover_ps51_comments(self.script, self.receipt())
        after = self.script.read_bytes()
        self.assertEqual(receipt["comment_lines_corrected"], 5)
        self.assertFalse(receipt["release_accepted"])
        self.assertEqual(receipt["independent_e07"], "NOT_RUN")
        self.assertEqual(
            after.replace(b"# D03", b"// D03").replace(
                b"\n# ", b"\n// "), self.before)
        self.assertIn(b"P01_UNINSTALL_POST_REMOVE_RESIDUE", after)
        self.assertIn(b"P01_UNINSTALL_PAYLOAD_PASS", after)

    def test_bad_receipt_does_not_modify_script(self):
        receipt = self.receipt()
        receipt["staged_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "RECEIPT_HOLD"):
            MOD.stage_reviewed_remover_ps51_comments(self.script, receipt)
        self.assertEqual(self.script.read_bytes(), self.before)

    def test_extra_unreviewed_comment_does_not_modify_script(self):
        self.script.write_bytes(self.before + b"// unreviewed comment\n")
        original = self.script.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "PREIMAGE_HOLD"):
            MOD.stage_reviewed_remover_ps51_comments(self.script, self.receipt())
        self.assertEqual(self.script.read_bytes(), original)

    def test_symlinked_disposable_owner_rejected(self):
        real = self.script.with_name("foreign.txt")
        real.write_bytes(self.before)
        self.script.unlink()
        try:
            self.script.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable on this host")
        with self.assertRaisesRegex(RuntimeError, "REPARSE_HOLD"):
            MOD.stage_reviewed_remover_ps51_comments(self.script, self.receipt())
        self.assertEqual(real.read_bytes(), self.before)

    def test_double_stage_fails_closed_without_mutation(self):
        MOD.stage_reviewed_remover_ps51_comments(self.script, self.receipt())
        actual = self.script.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "PREIMAGE_HOLD"):
            MOD.stage_reviewed_remover_ps51_comments(self.script, self.receipt())
        self.assertEqual(self.script.read_bytes(), actual)


if __name__ == "__main__":
    unittest.main()
