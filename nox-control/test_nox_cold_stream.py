#!/usr/bin/env python3
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import patch

MODULE = Path(__file__).with_name("nox_cold_drive.py")
spec = importlib.util.spec_from_file_location("nox_cold_drive", MODULE)
cold = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cold)


class FakeProc:
    def __init__(self, data, result=0):
        self.stdout = io.BytesIO(data)
        self.returncode = result
    def poll(self):
        return self.returncode
    def wait(self, timeout=None):
        return self.returncode
    def terminate(self):
        pass
    def kill(self):
        pass


class ColdStreamingTests(unittest.TestCase):
    def test_remote_stream_verified_without_disk_copy(self):
        raw = b"NOX file bytes" * 2048
        with patch.object(cold.subprocess, "Popen", return_value=FakeProc(raw)) as p:
            cold.verify_remote_stream("noxdrive:NOX_COLD/file.gguf", hashlib.sha256(raw).hexdigest(), len(raw))
        self.assertEqual(p.call_args.args[0][:2], ["rclone", "cat"])
        self.assertEqual(p.call_args.args[0][2], "noxdrive:NOX_COLD/file.gguf")

    def test_remote_stream_corruption_rejected(self):
        with patch.object(cold.subprocess, "Popen", return_value=FakeProc(b"bad")):
            with self.assertRaisesRegex(RuntimeError, "mismatch"):
                cold.verify_remote_stream("noxdrive:NOX_COLD/file.gguf", hashlib.sha256(b"good").hexdigest(), 4)

    def test_symlinked_source_or_parent_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / "model.gguf"
            target.write_bytes(b"abc")
            link = root / "linked.gguf"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "Symlink"):
                cold.assert_model(link)
            (root / "other").symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "Symlink"):
                cold.assert_model(root / "other" / "model.gguf")

    def test_stale_evict_manifest_cannot_remove_source(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src = root / "model.gguf"
            src.write_bytes(b"no-delete")
            active = root / "active.json"
            active.write_text(json.dumps({"checked_at_unix": int(time.time()) - 999, "active_paths": []}))
            active.chmod(0o600)
            args = SimpleNamespace(
                file=str(src), remote="noxdrive:NOX_COLD", active_manifest=str(active),
                receipt_dir=str(root / "receipts"), evict=True,
            )
            with patch.object(cold, "command"), patch.object(cold, "verify_remote_stream"):
                with self.assertRaisesRegex(RuntimeError, "fresh owner"):
                    cold.upload(args)
            self.assertEqual(src.read_bytes(), b"no-delete")

    def test_verified_upload_preserves_source_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src = root / "model.gguf"
            src.write_bytes(b"keep")
            args = SimpleNamespace(file=str(src), remote="noxdrive:NOX_COLD",
                                   active_manifest=None, receipt_dir=str(root / "receipts"), evict=False)
            with patch.object(cold, "command"), patch.object(cold, "verify_remote_stream") as readback:
                cold.upload(args)
            readback.assert_called_once()
            self.assertTrue(src.exists())
            receipts = list((root / "receipts").glob("*.json"))
            self.assertEqual(len(receipts), 1)
            self.assertTrue(json.loads(receipts[0].read_text())["readback_verified"])


if __name__ == "__main__":
    unittest.main()
