"""Prove owner API credentials are never inherited by operator subprocesses."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as provider


SOURCE = Path(__file__).with_name("owner_native_operator.py")
SPEC = importlib.util.spec_from_file_location("owner_native_operator_secret_test", SOURCE)
OP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OP)


class FakeSocket:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def settimeout(self, _timeout):
        return None

    def recv(self, _length):
        return b"SSH-2.0-fake\r\n"


class OperatorSecretEnvironmentTests(unittest.TestCase):
    def test_wrappers_strip_owner_secret_for_run_and_check_output(self):
        seen = []

        def fake_run(*args, **kwargs):
            seen.append(kwargs.get("env"))
            return subprocess.CompletedProcess(args[0], 0, stdout="ok", stderr="")

        def fake_check_output(*args, **kwargs):
            seen.append(kwargs.get("env"))
            return "ok\n"

        with mock.patch.dict(os.environ, {"NOX2": "never-in-child"}, clear=False), \
             mock.patch.object(OP.subprocess, "run", side_effect=fake_run), \
             mock.patch.object(OP.subprocess, "check_output", side_effect=fake_check_output):
            OP._safe_subprocess_run(["fake-run"])
            OP._safe_subprocess_check_output(["fake-check"])

        self.assertEqual(len(seen), 2)
        for child_env in seen:
            self.assertIsInstance(child_env, dict)
            self.assertNotIn("NOX2", child_env)

    def test_every_raw_subprocess_call_is_inside_a_stripping_wrapper(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        allowed = {"_safe_subprocess_run", "_safe_subprocess_check_output"}
        direct = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if (isinstance(node.func.value, ast.Name) and
                    node.func.value.id == "subprocess" and
                    node.func.attr in {"run", "check_output", "Popen", "call", "check_call"}):
                direct.append(node)
        self.assertEqual(len(direct), 2)
        names = set()
        for node in direct:
            for parent in ast.walk(tree):
                if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)) and node in ast.walk(parent):
                    names.add(parent.name)
        self.assertEqual(names, allowed)

    def test_full_preflight_owner_transport_subprocesses_never_receive_nox2(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = Path(temp) / "runner"
            key = runner / "owner_key"
            track = runner / "track.json"
            seen_envs = []
            original = (provider.RUNNER, provider.KEY, provider.TRACK)
            provider.RUNNER, provider.KEY, provider.TRACK = runner, key, track
            try:
                match_calls = 0

                def fake_api(method, path, _owner_key, payload=None):
                    if method == "GET":
                        return {"instances": {
                            "id": OP.INSTANCE, "actual_status": "running",
                            "intended_status": "running", "cur_state": "running",
                            "num_gpus": "2", "public_ipaddr": "8.8.8.8",
                            "ports": {"22/tcp": [{"HostPort": "22"}]},
                        }}
                    self.assertEqual(method, "POST")
                    self.assertEqual(path, f"/instances/{OP.INSTANCE}/ssh/")
                    self.assertIn("ssh_key", payload)
                    return {}

                def fake_match(_owner_key, _public_key):
                    nonlocal match_calls
                    match_calls += 1
                    return [] if match_calls == 1 else ["ephemeral-key-id"]

                def fake_run(args, **kwargs):
                    child_env = kwargs.get("env")
                    seen_envs.append(child_env)
                    self.assertNotIn("NOX2", child_env)
                    if args[0] == "ssh-keyscan":
                        return subprocess.CompletedProcess(args, 0,
                            stdout="host ssh-ed25519 AAAA\n", stderr="")
                    if args[0] == "ssh-keygen" and "-lf" in args:
                        return subprocess.CompletedProcess(args, 0,
                            stdout=f"256 {OP.PIN} fake-host\n", stderr="")
                    if args[0] == "ssh-keygen" and "-q" in args:
                        private = Path(args[args.index("-f") + 1])
                        private.write_text("test-only-private-key", encoding="ascii")
                        private.with_suffix(".pub").write_text(
                            "ssh-ed25519 AAAATEST owner\n", encoding="ascii")
                        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
                    if args[0] == "ssh" and "-N" in args:
                        control = next(value.split("=", 1)[1] for value in args
                                       if value.startswith("ControlPath="))
                        Path(control).touch()
                        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
                    if args[0] == "ssh" and "bash" in args:
                        return subprocess.CompletedProcess(args, 0,
                            stdout="NOX_MAINT_EMERGENCY_STOP_PREFLIGHT_COMPLETE=true\n",
                            stderr="")
                    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

                def fake_cleanup_with_receipt():
                    self.assertTrue(key.exists())
                    self.assertTrue(key.with_suffix(".pub").exists())
                    key.unlink()
                    key.with_suffix(".pub").unlink()
                    if track.exists():
                        track.unlink()
                    return True, "DETACHED_AND_VERIFIED", "REMOVED_AND_VERIFIED"

                with mock.patch.dict(os.environ, {
                        "NOX2": "owner-api-secret-sentinel",
                        "NOX_PINNED_SOURCE_SHA": "a" * 40,
                        "GITHUB_RUN_ID": "12345",
                    }, clear=False), \
                     mock.patch.object(OP, "authorize_event", return_value=8675309), \
                     mock.patch.object(OP.socket, "create_connection", return_value=FakeSocket()), \
                     mock.patch.object(provider, "api", side_effect=fake_api), \
                     mock.patch.object(provider, "match", side_effect=fake_match), \
                     mock.patch.object(provider, "cleanup_with_receipt", side_effect=fake_cleanup_with_receipt), \
                     mock.patch.object(OP.subprocess, "run", side_effect=fake_run), \
                     mock.patch.object(sys, "argv", [str(SOURCE), "emergency_stop_preflight"]):
                    self.assertEqual(OP.main(), 0)

                self.assertGreaterEqual(len(seen_envs), 6)
                self.assertTrue(all(isinstance(env, dict) and "NOX2" not in env
                                    for env in seen_envs))
                self.assertFalse(key.exists())
                self.assertFalse(key.with_suffix(".pub").exists())
            finally:
                provider.RUNNER, provider.KEY, provider.TRACK = original


if __name__ == "__main__":
    unittest.main()
