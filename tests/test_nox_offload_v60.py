import importlib.util
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1] / "nox-control"

def load(name):
    spec = importlib.util.spec_from_file_location(name, BASE / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

m = load("nox_cold_drive")
r2 = load("r2_archive")

class NoLossAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "models").mkdir()
        self.model = self.root / "models" / "tiny.gguf"
        self.model.write_bytes(b"TEST ONLY MODEL BYTES")
        self.sha = hashlib.sha256(self.model.read_bytes()).hexdigest()
        self.receipts = self.root / "receipts"

    def upload_args(self, **kwargs):
        v = dict(file=str(self.model), remote="noxdrive:NOX_COLD", receipt_dir=str(self.receipts),
                 active_manifest=None, evict=False)
        v.update(kwargs)
        return SimpleNamespace(**v)

    def test_protect_s03(self):
        folder = self.root / "s03"
        folder.mkdir()
        f = folder / "s03.safetensors"
        f.write_bytes(b"do not move")
        with self.assertRaises(ValueError):
            m.assert_model(f)
        self.assertTrue(f.exists())

    def test_protect_checkpoint(self):
        f = self.root / "models" / "checkpoint-model.safetensors"
        f.write_bytes(b"do not move")
        with self.assertRaises(ValueError):
            m.assert_model(f)

    def test_protect_symlink(self):
        f = self.root / "models" / "link.gguf"
        f.symlink_to(self.model)
        with self.assertRaises(ValueError):
            m.assert_model(f)

    def test_evict_disabled(self):
        with self.assertRaisesRegex(RuntimeError, "EVICTION_DISABLED"):
            m.upload(self.upload_args(evict=True))
        self.assertTrue(self.model.exists())
        self.assertFalse(self.receipts.exists())

    def test_verified_upload_keeps_source_and_writes_receipt(self):
        expected_size = self.model.stat().st_size
        with patch.object(m, "command") as transfer, patch.object(
                m, "remote_sha256", return_value=(self.sha, expected_size)):
            with patch("sys.stdout", new_callable=io.StringIO):
                m.upload(self.upload_args())
        transfer.assert_called_once()
        self.assertTrue(self.model.exists())
        receipt = next(self.receipts.glob("*.json"))
        obj = json.loads(receipt.read_text())
        self.assertTrue(obj["readback_verified"])
        self.assertFalse(obj["source_deleted"])
        self.assertEqual(obj["sha256"], self.sha)

    def test_corrupt_remote_keeps_source(self):
        with patch.object(m, "command"), patch.object(m, "remote_sha256",
                                                       return_value=("0"*64, self.model.stat().st_size)):
            with self.assertRaisesRegex(RuntimeError, "MISMATCH"):
                m.upload(self.upload_args())
        self.assertTrue(self.model.exists())
        self.assertFalse(self.receipts.exists())

    def test_remote_prefix_allowlist(self):
        for bad in ("evil:NOX_COLD", "../NOX", "noxdrive:../NOX", "C:\\\\Windows"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    m.assert_remote(bad)
        self.assertEqual(m.assert_remote("noxr2:bucket/NOX"), "noxr2:bucket/NOX")

    def test_not_ram_rejected(self):
        with self.assertRaises((RuntimeError, OSError)):
            m.ensure_linux_tmpfs(self.root.resolve())

    def test_r2_path_traversal(self):
        for name in ("../a", "/a", "a//b", "a/../b"):
            with self.assertRaises(ValueError):
                r2.object_name(name)

    def test_r2_no_credentials_fails_closed(self):
        with patch.dict("os.environ", {"RCLONE_CONFIG_NOXR2_ACCESS_KEY_ID":"",
                                       "RCLONE_CONFIG_NOXR2_SECRET_ACCESS_KEY":""}):
            with self.assertRaisesRegex(ValueError, "CREDENTIALS"):
                r2.credentials()

if __name__ == "__main__":
    unittest.main()
