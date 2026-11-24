"""Materialize only pinned B0/B5 inputs; offline regression, no native I/O."""
from pathlib import Path
import hashlib
import subprocess
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parent
PINS = {
    ROOT / "b0_resume_bridge.py": "a090f0bd0cf9a654b7aeee9c694338bd184fb92f",
    ROOT / "owner_chat_probe.py": "87b9f3d2e3eb109327bd9f403b26b53d926ab803",
    ROOT / "test_b0_resume_bridge.py": "c0bae6c1086241c95fc29584ff4044717ea7d790",
    ROOT / "r60_canonical_stage/b5_r55_pinned.py": "df94c535273dde1fd2609f555d1d615eacfda831",
    ROOT / "r61_chain_stage/b5_chain_guard.py": "f321f4ad36867e434ba72db9264a88cf23a91fb8",
}
class R61StageTest(unittest.TestCase):
    def test_chain_bound_exact_donors(self):
        with tempfile.TemporaryDirectory(prefix="nox-b0-r61-") as tmp:
            target = Path(tmp)
            for p, pin in PINS.items():
                raw = p.read_bytes()
                actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                self.assertEqual(actual, pin)
                (target / p.name).write_bytes(raw)
                print("B0_R61_PIN", p.name, actual, hashlib.sha256(raw).hexdigest(), flush=True)
            for name in ("b0_chain_bound.py", "test_chain_bound.py"):
                raw = (ROOT / "r61_chain_stage" / name).read_bytes()
                (target / name).write_bytes(raw)
                print("B0_R61_SOURCE", name, hashlib.sha256(raw).hexdigest(), flush=True)
            cmd = [sys.executable, "-I", "-B", "-c",
                   "import sys,unittest;sys.path.insert(0,'.');"
                   "s=unittest.defaultTestLoader.loadTestsFromName('test_chain_bound');"
                   "assert s.countTestCases()==3;r=unittest.TextTestRunner(verbosity=2).run(s);"
                   "print('B0_R61_NATIVE_ACCEPTED=false');sys.exit(not r.wasSuccessful())"]
            result = subprocess.run(cmd, cwd=target, capture_output=True, text=True, timeout=30)
            print(result.stdout, result.stderr, flush=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("Ran 3 tests", result.stderr)
