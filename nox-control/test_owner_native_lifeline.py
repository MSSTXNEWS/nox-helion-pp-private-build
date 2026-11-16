"""NOX bounded native deployment: self-contained no-loss regression tests."""
import importlib.util
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import hashlib

path=Path(__file__).with_name("owner_native_lifeline.py")
spec=importlib.util.spec_from_file_location("owner_native_lifeline",path)
n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)

class InstallerTests(unittest.TestCase):
    def test_existing_mismatch_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"config";p.write_bytes(b"original")
            with self.assertRaisesRegex(RuntimeError,"HOLD_LIFELINE_EXISTING_FILE_CONFLICT"):
                n.preserve_or_write(p,b"other",0o600)
            self.assertEqual(p.read_bytes(),b"original")
    def test_matching_existing_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"same";p.write_bytes(b"same")
            self.assertFalse(n.preserve_or_write(p,b"same",0o600))
    def test_new_atomic_write(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"new";self.assertTrue(n.preserve_or_write(p,b"safe",0o600))
            self.assertEqual(p.read_bytes(),b"safe")
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);origin=root/"old";origin.write_bytes(b"keep")
            link=root/"link";link.symlink_to(origin)
            with self.assertRaisesRegex(RuntimeError,"HOLD_LIFELINE_PATH_SYMLINK"):
                n.preserve_or_write(link,b"replace",0o600)
            self.assertEqual(origin.read_bytes(),b"keep")
    def test_bundle_hash_and_limit(self):
        content=b"verified source value"
        n.BUNDLE={"nox_native_lifeline.py":{"content":base64.b64encode(content).decode(),
                      "sha256":hashlib.sha256(content).hexdigest()}}
        self.assertEqual(n.bytes_checked("nox_native_lifeline.py"),content)
        n.BUNDLE["nox_native_lifeline.py"]["sha256"]="0"*64
        with self.assertRaisesRegex(RuntimeError,"HOLD_LIFELINE_BUNDLE_DIGEST"):
            n.bytes_checked("nox_native_lifeline.py")
    def test_wrong_supervisor_identity_rejected(self):
        with patch.object(n,"call",return_value=SimpleNamespace(stdout="evil RUNNING pid 1\n",returncode=0)):
            self.assertEqual(n.info("nox-dispatcher-t855u")["state"],"UNKNOWN")

if __name__=="__main__":unittest.main()
