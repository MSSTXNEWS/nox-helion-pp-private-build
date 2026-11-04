"""G3 targeted real-source regression: native producer failures are diagnosable, not PASS."""
import ast
import os
import re
import stat
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_local_onehost_bridge.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
HELPER = [node for node in TREE.body
          if isinstance(node, ast.FunctionDef) and node.name == "producer_failure_witness"]
assert len(HELPER) == 1, "T06_NATIVE_PRODUCER_FIRST_FAILURE_WITNESS_ABSENT"
NS = {"os": os, "re": re, "stat": stat}
exec(compile(ast.Module(body=HELPER, type_ignores=[]), str(SOURCE), "exec"), NS)
witness = NS["producer_failure_witness"]

class NativeProducerFirstFailure(unittest.TestCase):
    def test_real_error_codes_no_secret_values(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "01_NATIVE_PYINSTALLER.log"
            log.write_text("token=private-secret\nTraceback\nRuntimeError: T06_ORIGINAL_PYTHON_NATIVE_EXE_BUILD_FAILED\n", encoding="utf-8")
            proof = witness(log, 1)
            self.assertEqual(proof["diagnostic_tokens"], ["T06_ORIGINAL_PYTHON_NATIVE_EXE_BUILD_FAILED"])
            self.assertEqual(proof["exception_types"], ["RuntimeError"])
            self.assertNotIn("private-secret", repr(proof))
            self.assertIs(proof["release_accepted"], False)

    def test_missing_log_cannot_invent_success(self):
        with tempfile.TemporaryDirectory() as directory:
            proof = witness(Path(directory) / "not-created.log", 124)
            self.assertEqual(proof["producer_exit_code"], 124)
            self.assertIsNone(proof["log_bytes"])
            self.assertEqual(proof["diagnostic_tokens"], [])
            self.assertIs(proof["release_accepted"], False)

    def test_bounded_large_log_and_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "real.log"
            log.write_bytes(b"PRIVATE" * 15000 +
                            b"RuntimeError: T06_NATIVE_PRODUCER_FAIL\n" * 2)
            proof = witness(log, 2)
            self.assertEqual(proof["diagnostic_tokens"], ["T06_NATIVE_PRODUCER_FAIL"])
            self.assertEqual(proof["exception_types"], ["RuntimeError"])
            self.assertGreater(proof["log_bytes"], 65536)

    def test_symlink_log_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "secret.log"
            target.write_text("RuntimeError: T06_SHOULD_NOT_LEAK", encoding="utf-8")
            link = root / "result.log"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks not supported by local OS rights")
            proof = witness(link, 1)
            self.assertEqual(proof["diagnostic_tokens"], [])
            self.assertIsNone(proof["log_bytes"])

    def test_original_builder_failure_keeps_hold(self):
        self.assertIn("producer_failure_witness(OUT/first[\"log\"],first[\"return_code\"])",
                      SOURCE.read_text(encoding="utf-8"))
        self.assertIn('raise RuntimeError("T06_LOCAL_NATIVE_PRODUCER_FAILED")',
                      SOURCE.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
