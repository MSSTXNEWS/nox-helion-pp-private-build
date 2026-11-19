#!/usr/bin/env python3
"""Offline tests for owner-scoped Drive authentication probe."""
from __future__ import annotations
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

path = Path(__file__).with_name("owner_native_drive_probe.py")
spec = importlib.util.spec_from_file_location("owner_native_drive_probe", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.path = Path(self.work.name) / "rclone.conf"

    def config(self, extra, *, root=None):
        root = mod.EXPECTED_ROOT if root is None else root
        self.path.write_text("[noxdrive]\ntype = drive\nroot_folder_id = " +
                             root + "\n" + extra + "\n", encoding="utf-8")
        self.path.chmod(0o600)

    def test_absent_config_does_not_pass(self):
        with patch.dict(os.environ, {"RCLONE_CONFIG": str(self.path)}):
            self.assertEqual(mod.probe()["state"], "NOT_CONNECTED")

    def test_root_enforced(self):
        self.config("token = secret", root="some-other-google-folder")
        with patch.dict(os.environ, {"RCLONE_CONFIG": str(self.path)}):
            path, cfg, _ = mod.safe_config()
            self.assertEqual(mod.inspect_config(cfg), "ROOT_NOT_PINNED")

    def test_no_credentials(self):
        self.config("")
        with patch.dict(os.environ, {"RCLONE_CONFIG": str(self.path)}):
            _, cfg, _ = mod.safe_config()
            self.assertEqual(mod.inspect_config(cfg), "CREDENTIALS_NOT_CONFIGURED")

    def test_wrong_perms(self):
        self.config("token = secret")
        self.path.chmod(0o644)
        with patch.dict(os.environ, {"RCLONE_CONFIG": str(self.path)}):
            _, cfg, state = mod.safe_config()
            self.assertEqual(state, "CONFIG_PERMISSIONS")
            self.assertIsNone(cfg)

    def test_read_connection_without_secret_output(self):
        self.config("token = SUPER_SECRET_TOKEN")
        with patch.dict(os.environ, {"RCLONE_CONFIG": str(self.path)}):
            with patch.object(mod, "check_access", return_value="READ_CONNECTED"):
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(mod.main(), 0)
        self.assertNotIn("SUPER_SECRET_TOKEN", out.getvalue())
        self.assertIn("NOX_MAINT_DRIVE_PROBE_COMPLETE=true", out.getvalue())
        row = next(x for x in out.getvalue().splitlines()
                   if x.startswith("NOX_MAINT_DRIVE_PROBE="))
        data = json.loads(row.split("=", 1)[1])
        self.assertTrue(data["read_access"])
        self.assertEqual(data["write_access"], "NOT_TESTED")

    def test_read_unavailable_not_claimed(self):
        self.config("token = secret")
        with patch.dict(os.environ, {"RCLONE_CONFIG": str(self.path)}):
            with patch.object(mod, "check_access", return_value="READ_UNAVAILABLE"):
                self.assertFalse(mod.probe()["read_access"])

    def test_runner_no_file_content_or_credentials(self):
        def runner(args, **kwargs):
            self.assertNotIn("secret", repr(args))
            self.assertEqual(kwargs["stdout"], mod.subprocess.DEVNULL)
            self.assertEqual(kwargs["stderr"], mod.subprocess.DEVNULL)
            return SimpleNamespace(returncode=0)
        self.assertEqual(mod.check_access(self.path, runner=runner,
                         which=lambda _: "/usr/bin/rclone"), "READ_CONNECTED")


if __name__ == "__main__":
    unittest.main()
