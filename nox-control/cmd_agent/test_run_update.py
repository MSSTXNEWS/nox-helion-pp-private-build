#!/usr/bin/env python3
"""Focused regression for independent read-only owner probe; S1 launcher is untouched."""
import contextlib
import importlib.util
import io
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("NOX2", "unusable-test-token")
SCRIPT = pathlib.Path(__file__).with_name("owner_readonly_probe.py")
spec = importlib.util.spec_from_file_location("nox_owner_probe_under_test", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

VALID = "NOX_OWNER_READONLY_V1\nnox-bridge RUNNING\nnox-dispatcher-t855u RUNNING\n"


class ProbeTest(unittest.TestCase):
    def test_no_partial_telemetry(self):
        self.assertIsNone(probe.accepted("NOX_OWNER_READONLY_V1\nnox-bridge RUNNING\n"))
        self.assertIsNone(probe.accepted(VALID + "nox-bridge RUNNING\n"))
        self.assertEqual(probe.accepted(VALID),
                         {"nox-bridge": "RUNNING", "nox-dispatcher-t855u": "RUNNING"})

    def run_mock_probe(self, detaches):
        outputs = io.StringIO()

        def fake_run(args, **kwargs):
            child_env=kwargs.get("env")
            self.assertIsInstance(child_env, dict)
            self.assertEqual(set(child_env), {"PATH", "HOME", "LANG", "LC_ALL"})
            self.assertNotIn("NOX2", child_env)
            self.assertNotIn("GITHUB_TOKEN", child_env)
            self.assertEqual(child_env["PATH"], "/usr/bin:/bin")
            self.assertTrue(pathlib.Path(child_env["HOME"]).is_dir())
            if args[0] == "ssh-keygen":
                k = pathlib.Path(args[args.index("-f") + 1])
                k.write_text("private placeholder for mocked test")
                pathlib.Path(str(k) + ".pub").write_text("ssh-ed25519 TESTKEY nox-test")
                return subprocess.CompletedProcess(args, 0)
            self.assertEqual(args[0], "ssh")
            self.assertIn("StrictHostKeyChecking=yes", args)
            self.assertNotIn("StrictHostKeyChecking=accept-new", args)
            known = next(x.split("=", 1)[1] for x in args if x.startswith("UserKnownHostsFile="))
            self.assertEqual(pathlib.Path(known).read_text(),
                             "[127.0.0.1]:2022 ssh-ed25519 " + "A" * 48 + "\n")
            self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
            return subprocess.CompletedProcess(args, 0, stdout=VALID, stderr="")

        def fake_api(method, path, body=None):
            if method == "GET" and path.endswith("/60509551/"):
                return {"actual_status": "running", "intended_status": "running", "ports": {"22/tcp": [{"HostPort": 2022}]},
                        "public_ipaddr": "127.0.0.1"}
            if method == "POST":
                return {}
            raise AssertionError("unexpected API call: " + method + " " + path)

        with patch.dict(probe.os.environ, {"NOX_VAST_SSH_HOST_PUBLIC_KEY": "ssh-ed25519 " + "A" * 48}), \
             patch.object(probe, "api", side_effect=fake_api), \
             patch.object(probe, "matching", return_value=[{"id": "test-id"}]), \
             patch.object(probe, "detach", return_value=detaches), \
             patch.object(probe.subprocess, "run", side_effect=fake_run), \
             patch.object(probe.time, "sleep"), contextlib.redirect_stdout(outputs):
            if detaches:
                probe.main()
            else:
                with self.assertRaisesRegex(RuntimeError, "HOLD_KEY_DETACH_UNVERIFIED"):
                    probe.main()
        return outputs.getvalue()

    def test_missing_host_pin_holds_before_key_attachment(self):
        def instance_only(method, path, body=None):
            self.assertEqual(method, "GET")
            return {"actual_status": "running", "intended_status": "running", "ports": {"22/tcp": [{"HostPort": 2022}]},
                    "public_ipaddr": "127.0.0.1"}
        with patch.dict(probe.os.environ, {"NOX_VAST_SSH_HOST_PUBLIC_KEY": ""}), \
             patch.object(probe, "api", side_effect=instance_only), \
             patch.object(probe.subprocess, "run") as runner:
            with self.assertRaisesRegex(RuntimeError, "HOLD_TRUSTED_HOST_KEY_PIN_REQUIRED"):
                probe.main()
            runner.assert_not_called()

    def test_intentionally_stopped_instance_holds_before_any_key_operation(self):
        """Provider intent wins when actual status is briefly stale."""
        operations = []
        def provider(method, path, body=None):
            operations.append((method, path))
            self.assertEqual(method, "GET")
            return {"actual_status": "running", "intended_status": "stopped",
                    "ports": {"22/tcp": [{"HostPort": 2022}]},
                    "public_ipaddr": "127.0.0.1"}
        with patch.object(probe, "api", side_effect=provider), \
             patch.object(probe.subprocess, "run") as runner:
            with self.assertRaisesRegex(RuntimeError, "HOLD_INSTANCE_OR_PORT"):
                probe.main()
            runner.assert_not_called()
            self.assertEqual(len(operations), 1)

    def test_supervisor_failure_cannot_be_masked_by_awk(self):
        with tempfile.TemporaryDirectory() as tmp:
            supervisor = pathlib.Path(tmp) / "supervisorctl"
            supervisor.write_text("#!/bin/sh\nexit 23\n")
            supervisor.chmod(0o755)
            result = subprocess.run(["sh", "-c", probe.REMOTE],
                                    capture_output=True, text=True,
                                    env={"PATH": tmp + ":/usr/bin:/bin"})
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("NOX_OWNER_READONLY_V1", result.stdout)
            supervisor.write_text("#!/bin/sh\nprintf 'nox-dispatcher-t855u RUNNING pid 1\\nnox-bridge RUNNING pid 2\\n'\n")
            result = subprocess.run(["sh", "-c", probe.REMOTE],
                                    capture_output=True, text=True,
                                    env={"PATH": tmp + ":/usr/bin:/bin"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNotNone(probe.accepted(result.stdout))

    def test_detach_failure_prevents_success_marker(self):
        output = self.run_mock_probe(False)
        self.assertNotIn("READ_ONLY_VERIFIED", output)
        self.assertNotIn("nox-bridge=", output)

    def test_success_only_after_verified_detach(self):
        output = self.run_mock_probe(True)
        self.assertEqual(output.count("owner_probe=READ_ONLY_VERIFIED"), 1)
        self.assertIn("nox-bridge=RUNNING", output)
        self.assertIn("nox-dispatcher-t855u=RUNNING", output)


if __name__ == "__main__":
    unittest.main()
