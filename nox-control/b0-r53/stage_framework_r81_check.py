"""Verify one additive entrypoint on the actual extracted immutable R111 root."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from stage_framework_r81 import stage_framework, DEST, PINS, SOURCE_PIN, blob

class StagedFramework(unittest.TestCase):
    def test_extracted_framework(self):
        root = Path(os.environ["B0_STAGE_ROOT"]).resolve()
        snapshot = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        # Reject changed historical wire, without creating the successor.
        path = root/next(k for k in PINS if k.endswith("b0_proxy_stream_iter.py"))
        original = path.read_bytes()
        try:
            path.write_bytes(original+b"\n")
            with self.assertRaisesRegex(ValueError, "HOLD_FRAMEWORK_DEPENDENCY"):
                stage_framework(root)
            self.assertFalse((root/DEST).exists())
        finally:
            path.write_bytes(original)
        target = stage_framework(root)
        self.assertEqual(blob(target.read_bytes()), SOURCE_PIN)
        with self.assertRaisesRegex(ValueError, "HOLD_FRAMEWORK_OVERWRITE"):
            stage_framework(root)
        self.assertEqual({p.relative_to(root) for p in root.rglob("*") if p.is_file()}-set(snapshot), {Path(DEST)})
        for path, raw in snapshot.items():
            self.assertEqual((root/path).read_bytes(), raw, str(path))
        script = r"""
import sys,pathlib
wire=pathlib.Path(sys.argv[1])
sys.path.insert(0,str(wire))
import b0_framework_r80 as f, b0_proxy_stream_iter as i, b0_named_delta_encoder as e
assert f.ProxyDeltaBody is i.ProxyDeltaBody
assert all(pathlib.Path(m.__file__).parent==wire for m in (f,i,e))
assert 'b0_http_chunked_r76' not in sys.modules
class Up:
    def __init__(self): self.reads=0; self.closed=0
    def __iter__(self): return self
    def __next__(self): self.reads+=1; raise StopIteration
    def close(self): self.closed+=1
u=Up(); body=f.FrameworkDeltaBody(u); body.close()
try: next(body)
except RuntimeError as exc: assert str(exc)=='HOLD_PROXY_FRAMEWORK_CANCELLED'
else: raise AssertionError('cancel treated as EOF')
assert u.reads==0 and u.closed==1
u=Up(); body=f.FrameworkDeltaBody(u)
assert list(body)==[] and u.reads==1 and u.closed==1
assert 'b0_http_chunked_r76' not in sys.modules
print('framework_entrypoint=staged cancellation=HOLD clean_drain=transport_only native_accepted=false')
"""
        subprocess.run([sys.executable,"-I","-B","-c",script,str(target.parent)],check=True,cwd=root)
        print("unchanged_files=%d additive_files=1 native_accepted=false"%len(snapshot))
