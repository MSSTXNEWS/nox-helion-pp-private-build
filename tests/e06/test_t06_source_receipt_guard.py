"""T06 original same-VM source/NSIS attestation. No native install occurs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_source_receipt_guard.py"
SPEC = importlib.util.spec_from_file_location("t06_receipt_guard", MODULE)
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)
HEAD = "a" * 40
R11 = "90076eba83a213ba2b410632ced3288d41a6691ab63f81ad0520aa3cbbbfcb52"



def _synthetic_pe32_fixture(machine=0x14c):
    """Source-only PE layout fixture, intentionally NOT a real NSIS installer."""
    data = bytearray(65536)
    data[:2] = b"MZ"
    data[0x3c:0x40] = (0x80).to_bytes(4, "little")
    data[0x80:0x84] = b"PE\\x00\\x00"
    data[0x84:0x86] = machine.to_bytes(2, "little")
    data[0x86:0x88] = (3).to_bytes(2, "little")
    data[0x94:0x96] = (0xe0 if machine == 0x14c else 0xf0).to_bytes(2, "little")
    data[0x98:0x9a] = (0x10b if machine == 0x14c else 0x20b).to_bytes(2, "little")
    return bytes(data)

class CandidateReceiptTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.compile = root / "T06_COMPILE_EVIDENCE.json"
        self.candidate = root / "ONEHOST_CANDIDATE_RECEIPT.json"
        self.setup = root / "NOX-HELION-V16-ONEHOST-CANDIDATE-SETUP.exe"
        self.setup.write_bytes(_synthetic_pe32_fixture())
        self.comp = {"source_git_sha": HEAD, "original_zip_sha256": R11,
                     "original_files_staged": 729, "dotnet_build_exit": 0}
        self.cand = {"schema": "NOX-E06-ONEHOST-CANDIDATE-v1",
                     "source_git_sha": HEAD,
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

    def test_borrowed_candidate_from_different_source_head_denied(self):
        self.cand["source_git_sha"] = "b" * 40
        self.save()
        with self.assertRaisesRegex(RuntimeError, "CANDIDATE_SCHEMA"):
            self.verify()

    def test_candidate_missing_or_malformed_source_head_denied(self):
        for value in (None, True, 123, ""):
            self.cand["source_git_sha"] = value
            self.save()
            with self.assertRaisesRegex(RuntimeError, "CANDIDATE_SCHEMA"):
                self.verify()
        self.cand.pop("source_git_sha")
        self.save()
        with self.assertRaisesRegex(RuntimeError, "CANDIDATE_SCHEMA"):
            self.verify()

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


    def _replace_fake_setup_with_matching_receipt(self, payload):
        self.setup.write_bytes(payload)
        self.cand["setup_sha256"] = hashlib.sha256(payload).hexdigest()
        self.cand["setup_bytes"] = len(payload)
        self.save()

    def test_tiny_168_byte_saved_copy_is_not_an_nsis_setup(self):
        self._replace_fake_setup_with_matching_receipt(b"MZ" + b"x" * 166)
        with self.assertRaisesRegex(RuntimeError, "SETUP_IDENTITY"):
            self.verify()

    def test_large_non_pe_bytes_are_not_a_setup(self):
        self._replace_fake_setup_with_matching_receipt(b"MZ" + b"x" * 65534)
        with self.assertRaisesRegex(RuntimeError, "SETUP_IDENTITY"):
            self.verify()

    def test_tampered_pe_signature_is_denied_even_if_digest_matches(self):
        raw = bytearray(_synthetic_pe32_fixture())
        raw[0x80:0x84] = b"FAKE"
        self._replace_fake_setup_with_matching_receipt(bytes(raw))
        with self.assertRaisesRegex(RuntimeError, "SETUP_IDENTITY"):
            self.verify()

    def test_unsupported_pe_machine_is_denied(self):
        raw = bytearray(_synthetic_pe32_fixture())
        raw[0x84:0x86] = (0x7777).to_bytes(2, "little")
        self._replace_fake_setup_with_matching_receipt(bytes(raw))
        with self.assertRaisesRegex(RuntimeError, "SETUP_IDENTITY"):
            self.verify()

    def test_pe32plus_fixture_source_only(self):
        self._replace_fake_setup_with_matching_receipt(_synthetic_pe32_fixture(0x8664))
        self.assertEqual(self.verify(), self.cand["setup_sha256"])

    def test_nonfinite_receipt_json_is_denied(self):
        self.candidate.write_text('{"release_accepted":NaN}', encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "INVALID_JSON"):
            self.verify()

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

    def test_symlinked_receipt_parent_denied(self):
        alias = self.compile.parent / "receipt-junction"
        try:
            alias.symlink_to(self.compile.parent, target_is_directory=True)
        except (NotImplementedError, OSError):
            self.skipTest("directory symlink unavailable")
        self.compile = alias / self.compile.name
        with self.assertRaisesRegex(RuntimeError, "RECEIPT_MISSING_OR_UNTRUSTED"):
            self.verify()

    def test_symlinked_setup_parent_denied(self):
        alias = self.setup.parent / "setup-junction"
        try:
            alias.symlink_to(self.setup.parent, target_is_directory=True)
        except (NotImplementedError, OSError):
            self.skipTest("directory symlink unavailable")
        self.setup = alias / self.setup.name
        with self.assertRaisesRegex(RuntimeError, "SETUP_IDENTITY"):
            self.verify()

    def test_unbounded_receipt_refused(self):
        self.compile.write_bytes(b" " * 131073)
        with self.assertRaisesRegex(RuntimeError, "RECEIPT_MISSING"):
            self.verify()


    def _race_leaf_to_symlink_after_lstat(self, target):
        """Simulate a reparse swap *after* the original leaf lstat returned."""
        backup = target.with_name(target.name + ".original")
        original_lstat = Path.lstat
        switched = [False]

        def swap_on_lstat(path, *args, **kwargs):
            observed = original_lstat(path, *args, **kwargs)
            if path == target and not switched[0]:
                target.rename(backup)
                try:
                    target.symlink_to(backup)
                except (NotImplementedError, OSError):
                    backup.rename(target)
                    self.skipTest("symlink creation unavailable")
                switched[0] = True
            return observed
        return swap_on_lstat

    def test_receipt_symlink_swap_between_lstat_and_read_denied(self):
        with patch.object(Path, "lstat", self._race_leaf_to_symlink_after_lstat(self.compile)):
            with self.assertRaisesRegex(RuntimeError, "RECEIPT_MISSING_OR_UNTRUSTED"):
                self.verify()

    def test_setup_symlink_swap_between_lstat_and_hash_denied(self):
        with patch.object(Path, "lstat", self._race_leaf_to_symlink_after_lstat(self.setup)):
            with self.assertRaisesRegex(RuntimeError, "SETUP_IDENTITY"):
                self.verify()


if __name__ == "__main__":
    unittest.main()
