#!/usr/bin/env python3
"""Focused owner-only source staging tests: no Vast access or service restart."""
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).with_name("owner_native_drive_registry_stage.py")
spec = importlib.util.spec_from_file_location("nox_drive_registry_stage", MODULE)
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


def source_fixture():
    funcs = "".join(f"def h{i}(task): return {{'verified': False}}\n" for i in range(21))
    keys = ",\n".join(f"    'test_{i}': h{i}" for i in range(21))
    return (
        "def _nox_owner_boost_active(): return False\n"
        + funcs + "HANDLERS = {\n" + keys + "\n}\n"
        + "def run_one(task):\n"
          "    handler = HANDLERS.get(task['handler'])\n"
          "    return handler(task)\n"
    ).encode()


class StageTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.base = Path(work.name)
        self.private = self.base / "private"
        self.private.mkdir(mode=0o700)
        self.backups = self.private / "dispatcher-backups"
        self.src = self.base / "nox_dispatcher_t855u.py"
        self.src.write_bytes(source_fixture())
        self.src.chmod(0o600)
        self.bridge = self.base / "nox_drive_native_binding.py"
        self.bridge.write_bytes(b"# immutable fixture, NOT real bridge\n")
        self.bridge.chmod(0o600)
        self.src_sha = hashlib.sha256(self.src.read_bytes()).hexdigest()
        self.bridge_sha = hashlib.sha256(self.bridge.read_bytes()).hexdigest()

    def stage(self):
        return stage.stage(source=self.src, bridge=self.bridge,
                           backups=self.backups,
                           expected_dispatcher=self.src_sha,
                           expected_bridge=self.bridge_sha,
                           service_check=False)

    def test_one_atomic_stage_and_immutable_backup(self):
        original = self.src.read_bytes()
        result = self.stage()
        self.assertEqual(result["state"], "SOURCE_STAGED_NOT_LIVE")
        self.assertFalse(result["restarted"])
        self.assertFalse(result["native_handler_registered"])
        self.assertEqual(result["backup_sha256"], self.src_sha)
        self.assertEqual(result["new_sha256"],
                         hashlib.sha256(self.src.read_bytes()).hexdigest())
        self.assertEqual(self.src.read_bytes().count(stage.START.encode()), 1)
        self.assertIn(b'HANDLERS["nox.drive.first.native.v1"]', self.src.read_bytes())
        backup_files = list(self.backups.iterdir())
        self.assertEqual(len(backup_files), 1)
        self.assertEqual(backup_files[0].read_bytes(), original)
        self.assertEqual(self.stage()["state"], "ALREADY_STAGED_NOT_LIVE")
        self.assertEqual(len(list(self.backups.iterdir())), 1)

    def test_unreviewed_dispatcher_source_never_changes(self):
        original = self.src.read_bytes()
        with self.assertRaises(stage.Hold):
            stage.stage(source=self.src, bridge=self.bridge, backups=self.backups,
                        expected_dispatcher="0"*64,
                        expected_bridge=self.bridge_sha, service_check=False)
        self.assertEqual(original, self.src.read_bytes())
        self.assertFalse(self.backups.exists())

    def test_bridge_sha_mismatch_never_changes_dispatcher(self):
        original = self.src.read_bytes()
        with self.assertRaises(stage.Hold):
            stage.stage(source=self.src, bridge=self.bridge, backups=self.backups,
                        expected_dispatcher=self.src_sha,
                        expected_bridge="0"*64, service_check=False)
        self.assertEqual(original, self.src.read_bytes())

    def test_bad_registry_or_missing_run_one_fails_closed(self):
        invalid = self.src.read_bytes().replace(b"test_20", b"test_19")
        self.src.write_bytes(invalid)
        with self.assertRaises(stage.Hold):
            stage.assert_dispatcher_source(
                b"def _nox_owner_boost_active(): return False\n"
                b"HANDLERS = {}\n"
                b"def run_one(task): pass\n")
        with self.assertRaises(stage.Hold):
            self.stage()

    def test_symlink_source_forbidden(self):
        link = self.base / "link.py"
        link.symlink_to(self.src)
        with self.assertRaises(stage.Hold):
            stage.private_regular(link, 180000)

    def test_injected_handler_has_no_implicit_success(self):
        inject = stage.SHIM
        self.assertIn("HOLD_DRIVE_NATIVE_NO_VERIFIED_RECEIPT", inject)
        self.assertIn("HOLD_DRIVE_NATIVE_OWNER_CLAIM", inject)
        self.assertIn("HOLD_DRIVE_NATIVE_STOP_CHAT_OR_RESOURCES", inject)
        self.assertIn('original_task_accepted") is not False', inject)
        self.assertNotIn("supervisorctl", inject)
        self.assertNotIn("reboot", inject)


if __name__ == "__main__":
    unittest.main()
