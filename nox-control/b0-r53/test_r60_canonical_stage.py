"""Offline canonical alias staging gate; never installs or sends a model POST."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "r60_canonical_stage"
PINS = {
    ROOT / "b0_resume_bridge.py": "a090f0bd0cf9a654b7aeee9c694338bd184fb92f",
    ROOT / "owner_chat_probe.py": "87b9f3d2e3eb109327bd9f403b26b53d926ab803",
    ROOT / "test_b0_resume_bridge.py": "c0bae6c1086241c95fc29584ff4044717ea7d790",
    STAGE / "b5_r55_pinned.py": "df94c535273dde1fd2609f555d1d615eacfda831",
    STAGE / "b5_browser_prefix_gate.py": "6ff5e729ce7b431b25f28e66391ae81fa9c73f4a",
    STAGE / "test_b5_b0_r56_composed.py": "1faf4032c2ce1f077ee8125ac098870caf02d0ae",
}


class CanonicalAliasStagingTest(unittest.TestCase):
    def test_exact_canonical_stage(self):
        with tempfile.TemporaryDirectory(prefix="nox-b0-r60-") as tmp:
            work = Path(tmp)
            for path, expected in PINS.items():
                raw = path.read_bytes()
                git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                self.assertEqual(git_blob, expected, str(path))
                (work / path.name).write_bytes(raw)
                print("B0_R60_PIN", path.name, git_blob, hashlib.sha256(raw).hexdigest(), flush=True)
            # Isolated interpreter, no repo/PYTHONPATH alias fallback. Only
            # fixture tests; the owner HTTP readback is mocked by the donor.
            cmd = [sys.executable, "-I", "-B", "-c",
                   "import sys,unittest;sys.path.insert(0,'.');"
                   "s=unittest.defaultTestLoader.loadTestsFromName('test_b5_b0_r56_composed.ComposedIngressTests');"
                   "assert s.countTestCases()==7; r=unittest.TextTestRunner(verbosity=2).run(s);"
                   "print('B0_R60_NATIVE_ACCEPTED=false');sys.exit(not r.wasSuccessful())"]
            result = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=30)
            print(result.stdout, result.stderr, flush=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("Ran 7 tests", result.stderr)
            self.assertIn("B0_R60_NATIVE_ACCEPTED=false", result.stdout)
