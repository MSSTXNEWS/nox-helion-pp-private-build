"""Original T06 three-part SourceLock must remain fail-closed with python -O.

Runs the actual builder's verification block, not an invented replacement.
Does not extract the real 729 ZIP, invoke PyInstaller or mark E07 PASS.
"""
import hashlib
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BUILDER = ROOT / "coordination/e06/t06_native_proven_builder.py"


class OriginalThreePartOptimizedGateTests(unittest.TestCase):
    def _check(self, parts, expected):
        source = BUILDER.read_text(encoding="utf-8")
        start = "original_sha=hashlib.sha256(); original_bytes=io.BytesIO()"
        end = "# Run one actual Windows Python source process"
        self.assertEqual(source.count(start), 1)
        self.assertEqual(source.count(end), 1)
        block = source.split(start, 1)[1].split(end, 1)[0]
        body = start + block
        # Execute only exact source bytes of the original verification logic.
        code = ("import hashlib,io,pathlib,sys\n"
                "root=pathlib.Path(sys.argv[1])\n"
                "original_parts=('source_00.part','source_01.part','source_02.part')\n"
                "original_expected=sys.argv[2]\n"
                + body + "\nprint('G1_ORIGINAL_SOURCELOCK_VERIFIED')\n")
        with tempfile.TemporaryDirectory(prefix="nox-t06-g1-") as tmp:
            folder = pathlib.Path(tmp)
            for idx, content in enumerate(parts):
                (folder / f"source_{idx:02d}.part").write_bytes(content)
            return subprocess.run(
                [sys.executable, "-O", "-c", code, str(folder), expected],
                capture_output=True, text=True, timeout=15, check=False)

    def test_exact_three_parts_pass_under_optimized_python(self):
        parts = [b"official test part A", b"official test part B", b"official test part C"]
        digest = hashlib.sha256(b"".join(parts)).hexdigest()
        result = self._check(parts, digest)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("G1_ORIGINAL_SOURCELOCK_VERIFIED", result.stdout)

    def test_wrong_sha_fails_closed_under_optimized_python(self):
        parts = [b"official test part A", b"tampered test B", b"official test part C"]
        digest = hashlib.sha256(b"different archive").hexdigest()
        result = self._check(parts, digest)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("T06_ORIGINAL_THREE_PART_SHA_HOLD", result.stderr)
        self.assertNotIn("G1_ORIGINAL_SOURCELOCK_VERIFIED", result.stdout)

    def test_missing_part_fails_with_source_identity_error_under_optimized_python(self):
        parts = [b"official test part A", b"official test part B"]
        digest = hashlib.sha256(b"".join(parts)).hexdigest()
        result = self._check(parts, digest)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("T06_ORIGINAL_PART_ABSENT", result.stderr)
        self.assertNotIn("G1_ORIGINAL_SOURCELOCK_VERIFIED", result.stdout)


if __name__ == "__main__":
    unittest.main()
