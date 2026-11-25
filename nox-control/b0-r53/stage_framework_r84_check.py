"""Exact donor-byte fixture: no archive rebuild or joint staging."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from stage_framework_r81 import SOURCE as R80_SOURCE, SOURCE_PIN as R80_PIN, blob
 
from stage_framework_r84 import DEPENDENCIES, DEST, SOURCE_PIN, stage_r83, R80_DEST


class R84Stage(unittest.TestCase):
    def test_pinned_addendum(self):
        donor = Path(os.environ["B0_R84_DONOR"]).resolve(strict=True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            for name, pin in DEPENDENCIES.items():
                raw = (R80_SOURCE if name == R80_DEST else donor / name).read_bytes()
                self.assertEqual(blob(raw), pin, name)
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            r80 = root / R80_DEST
            original = r80.read_bytes()
            r80.unlink()
            with self.assertRaisesRegex(ValueError, "HOLD_R84_DEPENDENCY"):
                stage_r83(root)
            r80.write_bytes(original + b"\n")
            with self.assertRaisesRegex(ValueError, "HOLD_R84_DEPENDENCY"):
                stage_r83(root)
            r80.write_bytes(original)
            self.assertFalse((root / DEST).exists())
            target = stage_r83(root)
            self.assertEqual(blob(target.read_bytes()), SOURCE_PIN)
            with self.assertRaisesRegex(ValueError, "HOLD_R84_OVERWRITE"):
                stage_r83(root)
            script = """
import pathlib, sys
wire = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(wire))
import b0_framework_r83 as r83, b0_framework_r80 as r80, b0_proxy_stream_iter as r74
assert r83.R80Body is r80.FrameworkDeltaBody
assert r80.ProxyDeltaBody is r74.ProxyDeltaBody
assert all(pathlib.Path(m.__file__).parent == wire for m in (r83,r80,r74))
class Bad:
    closed=0
    def __iter__(self): raise StopIteration
    def close(self): self.closed += 1
u=Bad()
try: r83.FrameworkDeltaBody(u)
except RuntimeError as exc: assert str(exc) == 'HOLD_PROXY_FRAMEWORK_INIT_FALSE_EOF'
else: raise AssertionError('false EOF')
assert u.closed == 1
assert 'b0_http_chunked_r76' not in sys.modules
"""
            subprocess.run([sys.executable, "-I", "-B", "-c", script, str(target.parent)],
                           check=True, cwd=root)
            after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(set(after)-set(before), {Path(DEST)})
            self.assertEqual({p: after[p] for p in before}, before)
            print("exact_pinned_dependencies=%d additive=1 native_accepted=false" % len(before))
