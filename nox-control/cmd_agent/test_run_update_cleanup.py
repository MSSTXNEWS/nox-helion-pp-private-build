#!/usr/bin/env python3
"""Offline source-only check: no provider access, SSH, or secrets."""
import importlib.util
import os
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

os.environ.setdefault("NOX2", "OFFLINE_TEST_ONLY")
script = Path(__file__).with_name("run_update.py")
spec = importlib.util.spec_from_file_location("nox_cmd_update_cleanup", script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

PUB = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIofflinekey nox-update-button"
ID = 1234

class CleanupReadback(TestCase):
    def test_deleted_key_absent(self):
        with patch.object(mod, "api", side_effect=[{}, {"ssh_keys": []}]) as api:
            self.assertIsNone(mod.detach_checked_key(PUB, ID))
            self.assertEqual([call.args[0] for call in api.call_args_list], ["DELETE", "GET"])

    def test_key_still_present_fails_closed(self):
        with patch.object(mod, "api", side_effect=[{}, {"keys": [{"id": ID}]}]):
            with self.assertRaisesRegex(RuntimeError, "STILL_PRESENT"):
                mod.detach_checked_key(PUB, ID)

    def test_malformed_readback_fails_closed(self):
        with patch.object(mod, "api", side_effect=[{}, {"unexpected": []}]):
            with self.assertRaisesRegex(RuntimeError, "READBACK_SHAPE"):
                mod.detach_checked_key(PUB, ID)

    def test_delete_error_does_not_issue_ssh(self):
        with patch.object(mod, "api", side_effect=OSError("offline DELETE failure")):
            with self.assertRaises(OSError):
                mod.detach_checked_key(PUB, ID)

if __name__ == "__main__":
    main()
