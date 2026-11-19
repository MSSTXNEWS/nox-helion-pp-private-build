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

    def test_cgroup_ram_reserve_allows_only_real_headroom(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "memory.max").write_text(str(16 * cold.GIB))
            (p / "memory.current").write_text(str(4 * cold.GIB))
            self.assertEqual(cold.assert_cgroup_ram_reserve(6 * cold.GIB, 4, root=p), 12 * cold.GIB)
            with self.assertRaisesRegex(RuntimeError, "Insufficient current cgroup"):
                cold.assert_cgroup_ram_reserve(9 * cold.GIB, 4, root=p)

    def test_unknown_cgroup_limit_cannot_load_ram(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "memory.max").write_text("max")
            (p / "memory.current").write_text("1024")
            with self.assertRaisesRegex(RuntimeError, "Cannot verify cgroup"):
                cold.assert_cgroup_ram_reserve(0, 4, root=p)

    def test_stop_flag_blocks_warm_load(self):
        with tempfile.TemporaryDirectory() as d:
            stop = Path(d) / "STOP"
            stop.write_text("owner")
            with patch.object(cold, "STOP_FLAGS", (stop,)):
                with self.assertRaisesRegex(RuntimeError, "STOP"):
                    cold.assert_nox_running()

    def test_atomic_warm_publish_preserves_concurrently_created_destination(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            partial = root / "model.gguf.partial"
            dest = root / "model.gguf"
            partial.write_bytes(b"verified new model")
            dest.write_bytes(b"currently active model")
            with self.assertRaises(FileExistsError):
                cold.publish_verified_cache(partial, dest)
            self.assertEqual(dest.read_bytes(), b"currently active model")
            self.assertEqual(partial.read_bytes(), b"verified new model")
            dest.unlink()
            cold.publish_verified_cache(partial, dest)
            self.assertEqual(dest.read_bytes(), b"verified new model")
            partial.unlink()
            self.assertEqual(dest.read_bytes(), b"verified new model")

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
