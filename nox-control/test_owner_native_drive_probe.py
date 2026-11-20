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


    def test_dispatcher_surface_reports_only_public_interface_no_source_text(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "nox_dispatcher_t855u.py"
            private_source = (
                "SECRET_PRIVATE_VALUE = 'never publish this token'\n"
                "def register_handler(handler_kind, callback):\n"
                "    return True\n"
                "def claim_native_job(owner_lease, task_id):\n"
                "    return owner_lease\n"
                "HANDLER_REGISTRY = {}\n"
                "HANDLERS = {\"owner_native_project_work\": claim_native_job}\n"
                "def worker_loop(wid):\n"
                "    f = HANDLERS.get(\"owner_native_project_work\")\n"
                "    return f\n"
            )
            src.write_text(private_source, encoding="utf-8")
            res = mod.dispatcher_surface(
                source=src, runner=lambda *a, **kw: SimpleNamespace(
                    returncode=1, stdout="STOPPED", stderr=""
                )
            )
            self.assertEqual(res["state"], "SOURCE_AST_READ")
            self.assertEqual(res["source_sha256"], hashlib.sha256(private_source.encode()).hexdigest())
            self.assertEqual(res["registration_interface"], "DECLARED_FUNCTION")
            self.assertIn("register_handler(handler_kind,callback)", res["candidate_functions"])
            self.assertIn("HANDLER_REGISTRY", res["candidate_registries"])
            self.assertEqual(res["registry_kind"], "DICT_LITERAL")
            self.assertEqual(res["registered_literal_handlers"], [
                {"kind": "owner_native_project_work", "entry": "claim_native_job"}
            ])
            self.assertEqual(res["worker_registry_lookups"], ["HANDLERS_GET"])
            self.assertIn("worker_loop", res["host_handler_contracts"])
            self.assertEqual(res["host_handler_contracts"]["worker_loop"]["calls"], ["get"])
            self.assertIn("owner_native_project_work", [x["kind"] for x in res["registered_literal_handlers"]])
            self.assertFalse(res["drive_kind_declared"])
            self.assertFalse(res["live_process_verified"])
            self.assertEqual(res["native_handler_registered"], "UNVERIFIED")
            self.assertNotIn("never publish this token", json.dumps(res))

    def test_staged_source_not_claimed_live_until_process_identity_readback(self):
        source=path.read_text(encoding="utf-8")
        self.assertIn("live_process_started_at_unix",source)
        self.assertIn("process_newer_than_staged_source",source)
        self.assertIn("static_drive_hook_staged",source)
        self.assertIn("SC_CLK_TCK",source)
        self.assertIn("btime ",source)
        self.assertIn('native_handler_registered": "UNVERIFIED"',source)
        self.assertNotIn('native_handler_registered": True',source)

    def test_dispatcher_surface_rejects_symlink_source(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.py"
            original.write_text("def register_handler(kind, handler): pass")
            link = Path(directory) / "nox_dispatcher_t855u.py"
            link.symlink_to(original)
            result = mod.dispatcher_surface(source=link)
            self.assertEqual(result["state"], "HOLD_DISPATCHER_SOURCE")
            self.assertIsNone(result["source_sha256"])



    def test_alternate_private_oauth_candidate_is_reported_without_leaking_token(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "rclone.conf"
            p.write_text("[noxdrive]\ntype = drive\nroot_folder_id = "+
                         mod.EXPECTED_ROOT+"\ntoken = NEVER_EXPOSE_TOKEN\n")
            p.chmod(0o600)
            results = mod.probe_alternative_auth_configs({"TEST": p})
            self.assertEqual(results, {"TEST": "PINNED_AUTH_CANDIDATE"})
            self.assertNotIn("NEVER_EXPOSE_TOKEN", repr(results))

    def test_alternate_rejects_wrong_root_symlink_and_weak_modes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "rclone.conf"
            path.write_text("[noxdrive]\ntype = drive\nroot_folder_id = other\n"
                            "token = SECRET\n")
            path.chmod(0o600)
            self.assertEqual(mod.probe_alternative_auth_configs({"WRONG": path})["WRONG"],
                             "WRONG_ROOT")
            path.chmod(0o644)
            self.assertEqual(mod.probe_alternative_auth_configs({"WEAK": path})["WEAK"],
                             "UNSAFE_FILE")
            link=Path(d)/"config-link"
            link.symlink_to(path)
            self.assertEqual(mod.probe_alternative_auth_configs({"LINK": link})["LINK"],
                             "UNSAFE_PATH")


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
