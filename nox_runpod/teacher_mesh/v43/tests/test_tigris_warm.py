"""Offline, credential-free safety tests for the NOX Tigris integration."""
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nox"))
import tigris_warm as vault


class Body(io.BytesIO):
    def iter_chunks(self, chunk_size):
        while chunk := self.read(chunk_size):
            yield chunk


class NotFound(Exception):
    response = {"Error": {"Code": "404"}}


class FakeS3:
    def __init__(self):
        self.data = {}
    def list_objects_v2(self, **kwargs):
        assert kwargs["Bucket"] == "nox"
        return {"Contents": []}
    def head_object(self, **kwargs):
        key = kwargs["Key"]
        if key not in self.data:
            raise NotFound()
        body, meta = self.data[key]
        return {"ContentLength": len(body), "Metadata": meta}
    def upload_fileobj(self, file, bucket, key, ExtraArgs=None, Config=None):
        assert bucket == "nox"
        self.data[key] = (file.read(), ExtraArgs["Metadata"])
    def get_object(self, **kwargs):
        value, meta = self.data[kwargs["Key"]]
        return {"Body": Body(value), "ContentLength": len(value), "Metadata": meta}


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        stop_patch = patch.object(vault, "STOP_PATHS", (str(self.root / "STOP"),))
        stop_patch.start()
        self.addCleanup(stop_patch.stop)
        self.models = self.root / "models"
        self.models.mkdir()
        self.f = self.models / "model.gguf"
        self.f.write_bytes(b"test-weight-" * 256)
        self.s3 = FakeS3()

    def test_probe_read_only(self):
        self.assertEqual(vault.probe(self.s3)["state"], "READ_ACCESS_OK")
        self.assertEqual(self.s3.data, {})

    def test_backup_verify_restore_and_existing_no_overwrite(self):
        with patch("boto3.s3.transfer.TransferConfig", return_value=object()):
            report = vault.backup(self.s3, self.models, self.f)
        self.assertEqual(report["state"], "OFFSITE_HEAD_CONFIRMED_RESTORE_NOT_YET_TESTED")
        key = report["key"]
        self.assertTrue(self.f.exists())
        self.assertEqual(vault.verify_remote(self.s3, key)["state"], "REMOTE_SHA256_READBACK_PASS")
        with patch.object(vault, "_disk_free_for", return_value=60 * 1024**3):
            r = vault.restore(self.s3, key, self.root / "cache")
        self.assertEqual(r["state"], "RESTORED_LOCAL_SHA256_VERIFIED")
        self.assertEqual(Path(r["local"]).read_bytes(), self.f.read_bytes())
        with patch.object(vault, "_disk_free_for", side_effect=AssertionError("should not query disk")):
            r2 = vault.restore(self.s3, key, self.root / "cache")
        self.assertEqual(r2["state"], "LOCAL_SHA256_VERIFIED")

    def test_refuse_insufficient_disk_without_new_cache(self):
        digest = hashlib.sha256(self.f.read_bytes()).hexdigest()
        key = f"models/sha256/{digest}/model.gguf"
        self.s3.data[key] = (self.f.read_bytes(), {"sha256": digest})
        cache = self.root / "no_cache_created"
        with patch.object(vault, "_disk_free_for", return_value=10):
            r = vault.restore(self.s3, key, cache)
        self.assertEqual(r["state"], "HOLD_DISK_RESERVE")
        self.assertFalse(cache.exists())

    def test_corrupt_remote_bytes_fail_and_leave_no_file(self):
        digest = hashlib.sha256(self.f.read_bytes()).hexdigest()
        key = f"models/sha256/{digest}/model.gguf"
        self.s3.data[key] = (b"Z" * len(self.f.read_bytes()), {"sha256": digest})
        with self.assertRaisesRegex(vault.Hold, "HOLD_REMOTE_BYTES_SHA_MISMATCH"):
            vault.verify_remote(self.s3, key)
        cache = self.root / "cache"
        with patch.object(vault, "_disk_free_for", return_value=60 * 1024**3):
            with self.assertRaisesRegex(vault.Hold, "HOLD_RESTORED_SHA256_MISMATCH"):
                vault.restore(self.s3, key, cache)
        self.assertEqual(list(cache.iterdir()), [])

    def test_unsafe_sources_rejected(self):
        outside = self.root / "outside.gguf"
        outside.write_bytes(b"secret")
        with self.assertRaisesRegex(vault.Hold, "HOLD_SOURCE_OUTSIDE_MODEL_ROOT"):
            vault.guarded_source(self.models, outside)
        link = self.models / "link.gguf"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(vault.Hold, "HOLD_SYMLINK"):
            vault.guarded_source(self.models, link)

    def test_no_stop_bypass(self):
        with patch.object(vault, "stopped", return_value=True):
            with self.assertRaisesRegex(vault.Hold, "HOLD_NOX_STOP_ACTIVE"):
                vault.probe(self.s3)
            with self.assertRaisesRegex(vault.Hold, "HOLD_NOX_STOP_ACTIVE"):
                vault.backup(self.s3, self.models, self.f)

    def test_no_overwrite_when_existing_file_modified(self):
        digest = hashlib.sha256(self.f.read_bytes()).hexdigest()
        key = f"models/sha256/{digest}/model.gguf"
        self.s3.data[key] = (self.f.read_bytes(), {"sha256": digest})
        cache = self.root / "cache"
        cache.mkdir()
        dest = cache / f"{digest}-model.gguf"
        dest.write_bytes(b"a" * len(self.f.read_bytes()))
        with self.assertRaisesRegex(vault.Hold, "HOLD_EXISTING_CACHE_SHA_MISMATCH"):
            vault.restore(self.s3, key, cache)
        self.assertEqual(dest.read_bytes(), b"a" * len(self.f.read_bytes()))

    def test_reject_foreign_key_and_non_model_file(self):
        with self.assertRaisesRegex(vault.Hold, "HOLD_INVALID_CONTENT_ADDRESS"):
            vault.restore(self.s3, "../../secrets.txt", self.root / "cache")
        bad = self.models / "credentials.json"
        bad.write_text("{}")
        with self.assertRaisesRegex(vault.Hold, "HOLD_NON_MODEL_BINARY"):
            vault.guarded_source(self.models, bad)

    def test_missing_credentials_fail_closed(self):
        with patch.dict(os.environ, {"AWS_ACCESS_KEY_ID": "", "AWS_SECRET_ACCESS_KEY": ""}):
            with self.assertRaisesRegex(vault.Hold, "HOLD_TIGRIS_CREDENTIALS_NOT_PROVISIONED"):
                vault.s3_from_env()


    def _fake_ram(self, free=60 * 1024**3):
        return (patch.object(vault, "_ram_root_guard", side_effect=lambda p: Path(p).absolute()),
                patch.object(vault, "_ram_available_bytes", return_value=free))

    def test_warm_ram_direct_no_disk_and_repeat(self):
        digest = hashlib.sha256(self.f.read_bytes()).hexdigest()
        key = f"models/sha256/{digest}/model.gguf"
        self.s3.data[key] = (self.f.read_bytes(), {"sha256": digest})
        ram = self.root / "ram"
        check, free = self._fake_ram()
        with check, free:
            r = vault.warm_ram(self.s3, key, ram)
            self.assertEqual(r["state"], "WARM_RAM_SHA_VERIFIED")
            self.assertTrue(r["disk_downloaded"] is False and r["student_evicted"] is False)
            self.assertEqual(Path(r["local"]).read_bytes(), self.f.read_bytes())
            self.assertEqual(vault.warm_ram(self.s3, key, ram)["state"],
                             "ALREADY_IN_RAM_SHA_VERIFIED")

    def test_warm_ram_refuses_low_memory_before_writing(self):
        digest = hashlib.sha256(self.f.read_bytes()).hexdigest()
        key = f"models/sha256/{digest}/model.gguf"
        self.s3.data[key] = (self.f.read_bytes(), {"sha256": digest})
        ram = self.root / "ram"
        check, free = self._fake_ram(free=32)
        with check, free:
            state = vault.warm_ram(self.s3, key, ram)["state"]
        self.assertEqual(state, "HOLD_RAM_RESERVE")
        self.assertFalse(ram.exists())

    def test_warm_ram_corrupt_remote_leaves_no_published_file(self):
        digest = hashlib.sha256(self.f.read_bytes()).hexdigest()
        key = f"models/sha256/{digest}/model.gguf"
        self.s3.data[key] = (b"Z" * len(self.f.read_bytes()), {"sha256": digest})
        ram = self.root / "ram"
        check, free = self._fake_ram()
        with check, free:
            with self.assertRaisesRegex(vault.Hold, "HOLD_RAM_STREAM_SHA_MISMATCH"):
                vault.warm_ram(self.s3, key, ram)
        self.assertEqual(list(ram.iterdir()), [])

    def test_ram_mode_rejects_non_tmpfs_and_stop_unknown(self):
        with self.assertRaisesRegex(vault.Hold, "HOLD_RAM_ROOT_NOT_DEDICATED_TMPFS"):
            vault._ram_root_guard(self.root)
        with patch("pathlib.Path.exists", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(vault.Hold, "HOLD_STOP_STATE_UNREADABLE"):
                vault.stopped()

    def test_warm_ram_stop_never_writes(self):
        digest = hashlib.sha256(self.f.read_bytes()).hexdigest()
        key = f"models/sha256/{digest}/model.gguf"
        self.s3.data[key] = (self.f.read_bytes(), {"sha256": digest})
        with patch.object(vault, "stopped", return_value=True):
            with self.assertRaisesRegex(vault.Hold, "HOLD_NOX_STOP_ACTIVE"):
                vault.warm_ram(self.s3, key, self.root / "ram")
        self.assertFalse((self.root / "ram").exists())



    def test_memfd_streamed_to_ram_and_closed_by_owner(self):
        if not hasattr(os, "memfd_create"):
            self.skipTest("Linux memfd not available")
        digest = hashlib.sha256(self.f.read_bytes()).hexdigest()
        key = f"models/sha256/{digest}/model.gguf"
        self.s3.data[key] = (self.f.read_bytes(), {"sha256": digest})
        with patch.object(vault, "_memfd_available_bytes", return_value=60*1024**3):
            with vault.warm_memfd(self.s3, key) as weight:
                self.assertEqual(weight.sha256, digest)
                self.assertEqual(weight.bytes, self.f.stat().st_size)
                self.assertTrue(weight.local.startswith("/proc/self/fd/"))
                os.lseek(weight.fd, 0, os.SEEK_SET)
                self.assertEqual(os.read(weight.fd, weight.bytes), self.f.read_bytes())
            with self.assertRaisesRegex(vault.Hold, "HOLD_MEMFD_CLOSED"):
                _ = weight.local

    def test_memfd_holds_if_not_enough_ram(self):
        digest = hashlib.sha256(self.f.read_bytes()).hexdigest()
        key = f"models/sha256/{digest}/model.gguf"
        self.s3.data[key] = (self.f.read_bytes(), {"sha256": digest})
        with patch.object(vault, "_memfd_available_bytes", return_value=128):
            result = vault.warm_memfd(self.s3, key)
        self.assertEqual(result["state"], "HOLD_RAM_RESERVE")

    def test_memfd_corrupt_stream_rejects(self):
        if not hasattr(os, "memfd_create"):
            self.skipTest("Linux memfd not available")
        digest = hashlib.sha256(self.f.read_bytes()).hexdigest()
        key = f"models/sha256/{digest}/model.gguf"
        self.s3.data[key] = (b"Z"*self.f.stat().st_size, {"sha256": digest})
        with patch.object(vault, "_memfd_available_bytes", return_value=60*1024**3):
            with self.assertRaisesRegex(vault.Hold, "HOLD_MEMFD_SHA_MISMATCH"):
                vault.warm_memfd(self.s3, key)

    def test_memfd_stop_cannot_stage_weights(self):
        digest = hashlib.sha256(self.f.read_bytes()).hexdigest()
        key = f"models/sha256/{digest}/model.gguf"
        self.s3.data[key] = (self.f.read_bytes(), {"sha256": digest})
        with patch.object(vault, "stopped", return_value=True):
            with self.assertRaisesRegex(vault.Hold, "HOLD_NOX_STOP_ACTIVE"):
                vault.warm_memfd(self.s3, key)


if __name__ == "__main__":
    unittest.main()
