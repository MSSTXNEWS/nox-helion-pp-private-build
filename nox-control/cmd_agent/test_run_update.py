#!/usr/bin/env python3
"""Focused regression: probe may succeed only after key detach and full readback."""
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
SCRIPT = pathlib.Path(__file__).with_name("run_update.py")
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
            if args[0] == "ssh-keygen":
                k = pathlib.Path(args[args.index("-f") + 1])
                k.write_text("private placeholder for mocked test")
                pathlib.Path(str(k) + ".pub").write_text("ssh-ed25519 TESTKEY nox-test")
                return subprocess.CompletedProcess(args, 0)
            self.assertEqual(args[0], "ssh")
            self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
            return subprocess.CompletedProcess(args, 0, stdout=VALID, stderr="")

        def fake_api(method, path, body=None):
            if method == "GET" and path.endswith("/60509551/"):
                return {"actual_status": "running", "ports": {"22/tcp": [{"HostPort": 2022}]},
                        "public_ipaddr": "127.0.0.1"}
            if method == "POST":
                return {}
            raise AssertionError("unexpected API call: " + method + " " + path)

        with patch.object(probe, "api", side_effect=fake_api), \
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
