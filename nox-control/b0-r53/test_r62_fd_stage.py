"""Exact isolated FD composition test; no production traffic."""
from pathlib import Path
import hashlib
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
PINS = {
    "b0_resume_bridge.py": "a090f0bd0cf9a654b7aeee9c694338bd184fb92f",
    "owner_chat_probe.py": "87b9f3d2e3eb109327bd9f403b26b53d926ab803",
    "test_b0_resume_bridge.py": "c0bae6c1086241c95fc29584ff4044717ea7d790",
    "r60_canonical_stage/b5_r55_pinned.py": "df94c535273dde1fd2609f555d1d615eacfda831",
    "r61_chain_stage/b5_chain_guard.py": "f321f4ad36867e434ba72db9264a88cf23a91fb8",
    "r61_chain_stage/b0_chain_bound.py": "c0f7b2b3006458695f0658c5d850e00669cd51dd",
    "r61_chain_stage/test_chain_bound.py": "c1ae1176213258da8baedcd404e7b2ac19abd24a",
    "r62_fd_stage/b5_retained_ingress.py": "75af979a9d84216485e0333f8f9afcffb61f6ce6",
}

class R62FDStageTest(unittest.TestCase):
    def test_exact_owner_fd_composition(self):
        with tempfile.TemporaryDirectory(prefix="nox-b0-r62-") as tmp:
            target = Path(tmp)
            for path, pin in PINS.items():
                p = ROOT / path
                raw = p.read_bytes()
                actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                self.assertEqual(actual, pin)
                (target / p.name).write_bytes(raw)
                print("B0_R62_PIN", p.name, actual, hashlib.sha256(raw).hexdigest(), flush=True)
            for name in ("b0_owner_fd_turn3.py", "test_owner_fd_turn3.py"):
                raw = (ROOT / "r62_fd_stage" / name).read_bytes()
                (target / name).write_bytes(raw)
                print("B0_R62_SOURCE", name, hashlib.sha256(raw).hexdigest(), flush=True)
            command = [sys.executable, "-I", "-B", "-c",
                       "import sys,unittest;sys.path.insert(0,'.');"
                       "s=unittest.defaultTestLoader.loadTestsFromName('test_owner_fd_turn3');"
                       "assert s.countTestCases()==5;r=unittest.TextTestRunner(verbosity=2).run(s);"
                       "print('B0_R62_NATIVE_ACCEPTED=false');sys.exit(not r.wasSuccessful())"]
            result = subprocess.run(command, cwd=target, capture_output=True, text=True, timeout=30)
            print(result.stdout, result.stderr, flush=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("Ran 5 tests", result.stderr)
