"""T06 original same-VM source/NSIS attestation. No native install occurs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_source_receipt_guard.py"
SPEC = importlib.util.spec_from_file_location("t06_receipt_guard", MODULE)
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)
HEAD = "a" * 40
R11 = "90076eba83a213ba2b410632ced3288d41a6691ab63f81ad0520aa3cbbbfcb52"


class CandidateReceiptTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.compile = root / "T06_COMPILE_EVIDENCE.json"
        self.candidate = root / "ONEHOST_CANDIDATE_RECEIPT.json"
        self.setup = root / "NOX-HELION-V16-ONEHOST-CANDIDATE-SETUP.exe"
        self.setup.write_bytes(b"MZ exact local Windows test fixture, never installed")
        self.comp = {"source_git_sha": HEAD, "original_zip_sha256": R11,
                     "original_files_staged": 729, "dotnet_build_exit": 0}
        self.cand = {"schema": "NOX-E06-ONEHOST-CANDIDATE-v1",
                     "source_zip_sha256": R11, "release_accepted": False,
                     "e07": "NOT_ACCEPTED", "wpf_source_compilation": "PASS",
                     "backend_native_stdio_windows_exe_smoke": "PASS",
                     "setup_sha256": hashlib.sha256(self.setup.read_bytes()).hexdigest(),
                     "setup_bytes": self.setup.stat().st_size}
        self.save()

    def save(self):
        self.compile.write_text(json.dumps(self.comp), encoding="utf-8")
        self.candidate.write_text(json.dumps(self.cand), encoding="utf-8")

    def verify(self):
        return GUARD.attest_candidate(HEAD, self.compile, self.candidate, self.setup, R11)

    def test_real_source_and_setup_bytes(self):
        self.assertEqual(self.verify(), self.cand["setup_sha256"])

    def test_stale_source_commit_hold(self):
        self.comp["source_git_sha"] = "b" * 40
        self.save()
        with self.assertRaisesRegex(RuntimeError, "EXACT_HEAD_OR_729"):
            self.verify()

    def test_source729_and_r11_are_required(self):
        for field, bad in (("original_files_staged", 728),
                           ("original_zip_sha256", "b" * 64),
                           ("dotnet_build_exit", True)):
            old = self.comp[field]
            self.comp[field] = bad
            self.save()
            with self.assertRaisesRegex(RuntimeError, "EXACT_HEAD_OR_729"):
                self.verify()
            self.comp[field] = old

    def test_replaced_setup_bytes_hold(self):
        self.setup.write_bytes(b"MZ replaced payload")
        with self.assertRaisesRegex(RuntimeError, "SETUP"):
            self.verify()

    def test_candidate_e07_and_schema_never_borrowed(self):
        for field, bad in (("release_accepted", True), ("e07", "ACCEPTED"),
                           ("backend_native_stdio_windows_exe_smoke", "HOLD")):
            old = self.cand[field]
            self.cand[field] = bad
            self.save()
            with self.assertRaisesRegex(RuntimeError, "CANDIDATE_SCHEMA"):
                self.verify()
            self.cand[field] = old

    def test_duplicate_json_property_is_refused(self):
        self.compile.write_text('{"source_git_sha":"%s","source_git_sha":"%s"}' % (HEAD, HEAD))
        with self.assertRaisesRegex(RuntimeError, "INVALID_JSON"):
            self.verify()

    def test_symlinked_setup_denied(self):
        target = self.setup.with_name("attacker.exe")
        self.setup.rename(target)
        try:
            self.setup.symlink_to(target)
        except (NotImplementedError, OSError):
            self.skipTest("symlinks unavailable on host")
        with self.assertRaisesRegex(RuntimeError, "SETUP_IDENTITY"):
            self.verify()

    def test_unbounded_receipt_refused(self):
        self.compile.write_bytes(b" " * 131073)
        with self.assertRaisesRegex(RuntimeError, "RECEIPT_MISSING"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
