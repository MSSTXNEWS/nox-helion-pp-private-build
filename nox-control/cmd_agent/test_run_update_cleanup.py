#!/usr/bin/env python3
"""Offline source-only check: no provider access, SSH, or secrets."""
import importlib.util
import os
import subprocess
import tempfile
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


class LocalPrivateKeyCleanup(TestCase):
    """Exercise the real owner function with all external effects stubbed."""

    def test_private_key_directory_removed_after_verified_provider_detach(self):
        folder = Path(tempfile.mkdtemp())
        key_path = folder / "k"
        def stub_run(args, **kwargs):
            if args[0] == "ssh-keygen":
                key_path.write_text("OFFLINE_PRIVATE_TEST_KEY", encoding="utf-8")
                (folder / "k.pub").write_text(PUB, encoding="utf-8")
                return subprocess.CompletedProcess(args, 0)
            self.assertEqual(args[0], "ssh")
            return subprocess.CompletedProcess(args, 0, stdout="offline ok", stderr="")
        instance = {"actual_status": "running", "public_ipaddr": "127.0.0.1",
                    "ports": {"22/tcp": [{"HostPort": "2222"}]}}
        calls = [instance, {}, {"ssh_keys": [{"id": ID, "ssh_key": PUB}]},
                 {}, {"ssh_keys": []}]
        with patch.object(mod, "api", side_effect=calls) as fake_api, \
             patch.object(mod.tempfile, "mkdtemp", return_value=str(folder)), \
             patch.object(mod.subprocess, "run", side_effect=stub_run), \
             patch.object(mod.time, "sleep", return_value=None):
            mod.main()
        self.assertEqual(fake_api.call_count, 5)
        self.assertFalse(folder.exists(), "private key directory must be removed")

    def test_ssh_keygen_failure_still_removes_local_directory(self):
        folder = Path(tempfile.mkdtemp())
        instance = {"actual_status": "running", "public_ipaddr": "127.0.0.1",
                    "ports": {"22/tcp": [{"HostPort": "2222"}]}}
        with patch.object(mod, "api", return_value=instance), \
             patch.object(mod.tempfile, "mkdtemp", return_value=str(folder)), \
             patch.object(mod.subprocess, "run", side_effect=OSError("offline keygen failed")):
            with self.assertRaises(OSError):
                mod.main()
        self.assertFalse(folder.exists(), "failed keygen must not retain private key directory")


class ProviderOrphanRecovery(TestCase):
    def test_unique_generated_key_is_detached_without_remote_dispatch(self):
        # POST was accepted, yet eight initial provider reads missed the ID.
        # Final recovery lookup must remove ONLY this exact generated key.
        folder = Path(tempfile.mkdtemp())
        key_path = folder / "k"
        instance = {"actual_status": "running", "public_ipaddr": "127.0.0.1",
                    "ports": {"22/tcp": [{"HostPort": "2222"}]}}
        def stub_run(args, **kwargs):
            self.assertEqual(args[0], "ssh-keygen", "ambiguous key ID must fence SSH")
            key_path.write_text("OFFLINE_PRIVATE_TEST_KEY", encoding="utf-8")
            (folder / "k.pub").write_text(PUB, encoding="utf-8")
            return subprocess.CompletedProcess(args, 0)
        calls = [instance, {}, *([{"ssh_keys": []}] * 8),
                 {"ssh_keys": [{"id": ID, "ssh_key": PUB}]},
                 {}, {"ssh_keys": []}]
        with patch.object(mod, "api", side_effect=calls) as fake_api, \
             patch.object(mod.tempfile, "mkdtemp", return_value=str(folder)), \
             patch.object(mod.subprocess, "run", side_effect=stub_run) as fake_run, \
             patch.object(mod.time, "sleep", return_value=None):
            with self.assertRaisesRegex(SystemExit, "HOLD_UNCONFIRMED_EPHEMERAL_KEY_ID"):
                mod.main()
        self.assertFalse(folder.exists())
        self.assertEqual(fake_run.call_count, 1, "no SSH replay or dispatch")
        self.assertEqual(fake_api.call_count, len(calls))
        self.assertEqual(fake_api.call_args_list[-2].args[0], "DELETE")
        self.assertEqual(fake_api.call_args_list[-1].args[0], "GET")

    def test_ambiguous_recovered_identity_holds_without_key_deletion(self):
        # Never delete a different operator's key when matching is ambiguous.
        with patch.object(mod, "api", return_value={"ssh_keys": [
            {"id": ID, "ssh_key": PUB},
            {"id": ID + 1, "ssh_key": PUB}]}):
            with self.assertRaisesRegex(RuntimeError, "RECOVERY_NOT_UNIQUE"):
                mod.locate_uploaded_key_id(PUB)

    def test_invalid_provider_shape_holds_without_guessing(self):
        with patch.object(mod, "api", return_value={"unknown": []}):
            with self.assertRaisesRegex(RuntimeError, "RECOVERY_READBACK_SHAPE"):
                mod.locate_uploaded_key_id(PUB)

    def test_duplicate_registration_identity_never_dispatches_ssh(self):
        # Two keys with the same public fingerprint: the first match is NOT
        # sufficient permission to execute a remote action.
        folder = Path(tempfile.mkdtemp())
        key_path = folder / "k"
        instance = {"actual_status": "running", "public_ipaddr": "127.0.0.1",
                    "ports": {"22/tcp": [{"HostPort": "2222"}]}}
        duplicates = {"ssh_keys": [{"id": ID, "ssh_key": PUB},
                                   {"id": ID + 1, "ssh_key": PUB}]}
        def stub_run(args, **kwargs):
            self.assertEqual(args[0], "ssh-keygen", "ambiguous key identity must fence SSH")
            key_path.write_text("OFFLINE_PRIVATE_TEST_KEY", encoding="utf-8")
            (folder / "k.pub").write_text(PUB, encoding="utf-8")
            return subprocess.CompletedProcess(args, 0)
        # GET instance, POST key, first GET ambiguity, final recovery GET.
        with patch.object(mod, "api", side_effect=[instance, {}, duplicates, duplicates]) as fake_api, \
             patch.object(mod.tempfile, "mkdtemp", return_value=str(folder)), \
             patch.object(mod.subprocess, "run", side_effect=stub_run) as fake_run:
            with self.assertRaises(SystemExit):
                mod.main()
        self.assertEqual(fake_run.call_count, 1)
        self.assertEqual([c.args[0] for c in fake_api.call_args_list], ["GET", "POST", "GET", "GET"])
        self.assertFalse(folder.exists(), "private key directory must still be removed")

if __name__ == "__main__":
    main()
