"""Focused D3 regression for the read-only observer's ephemeral SSH-key lifecycle.

No network or real key is used. Never starts the Vast owner workflow.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name("run_update.py")
spec = importlib.util.spec_from_file_location("nox_d3_ephemeral_observer", SOURCE)
observer = importlib.util.module_from_spec(spec)
with patch.dict(os.environ, {"NOX2": "synthetic-test-only"}):
    spec.loader.exec_module(observer)


class EphemeralObserverCleanup(unittest.TestCase):
    def scenario(self, mode):
        root = Path(tempfile.mkdtemp(prefix="nox-d3-test-"))
        pub = "ssh-ed25519 SYNTHETICpublickeybytes nox-update-button"
        calls = []
        listed = 0

        def fake_api(method, path, body=None):
            nonlocal listed
            calls.append((method, path))
            if method == "GET" and path.endswith("/instances/60509551/"):
                return {"instances": {
                    "id": 60509551, "actual_status": "running",
                    "public_ipaddr": "127.0.0.1",
                    "ports": {"22/tcp": [{"HostPort": "12345"}]},
                }}
            if method == "POST" and path.endswith("/ssh/"):
                self.assertEqual(body, {"ssh_key": pub})
                if mode == "post_response_lost":
                    raise OSError("synthetic lost API response after attach")
                return {}
            if method == "GET" and path.endswith("/ssh/"):
                listed += 1
                if mode == "never_visible" or (
                    mode == "delayed_listing" and listed <= 8
                ):
                    return {"ssh_keys": []}
                return {"ssh_keys": [{"id": 42, "ssh_key": pub}]}
            if method == "DELETE" and path.endswith("/ssh/42"):
                return {}
            raise AssertionError((method, path))

        def fake_process(args, **kwargs):
            if args[0] == "ssh-keygen":
                keyfile = Path(args[args.index("-f") + 1])
                keyfile.write_text("synthetic-private-key", encoding="utf-8")
                Path(str(keyfile) + ".pub").write_text(pub, encoding="utf-8")
                return SimpleNamespace(returncode=0)
            self.assertEqual(args[0], "ssh")
            self.assertIs(kwargs["stdin"], observer.subprocess.DEVNULL)
            return SimpleNamespace(returncode=0, stdout="safe telemetry", stderr="")

        try:
            with patch.object(observer.tempfile, "mkdtemp", return_value=str(root)), \
                 patch.object(observer, "api", side_effect=fake_api), \
                 patch.object(observer.subprocess, "run", side_effect=fake_process), \
                 patch.object(observer.time, "sleep", return_value=None):
                if mode == "never_visible":
                    with self.assertRaisesRegex(
                        RuntimeError, "HOLD_OBSERVER_KEY_DETACH_UNVERIFIED"
                    ):
                        observer.main()
                elif mode == "post_response_lost":
                    with self.assertRaisesRegex(OSError, "synthetic lost"):
                        observer.main()
                else:
                    observer.main()
        finally:
            self.assertFalse(root.exists(), "temporary private key was not deleted")
        return calls

    def test_late_key_listing_detaches_on_final_lookup(self):
        calls = self.scenario("delayed_listing")
        self.assertEqual(
            sum(1 for action, path in calls if action == "DELETE"), 1
        )

    def test_lost_attach_response_still_detaches_exact_key(self):
        calls = self.scenario("post_response_lost")
        self.assertEqual(
            sum(1 for action, path in calls if action == "DELETE"), 1
        )

    def test_unverified_detach_never_reports_success(self):
        calls = self.scenario("never_visible")
        self.assertFalse(any(action == "DELETE" for action, _ in calls))


if __name__ == "__main__":
    unittest.main()
