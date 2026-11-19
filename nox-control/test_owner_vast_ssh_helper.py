"""Offline regressions for the pinned owner Vast SSH helper."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as probe

PUBLIC = "ssh-ed25519 " + base64.b64encode(bytes(range(32))).decode("ascii") + " qa-run"
OTHER = "ssh-ed25519 " + base64.b64encode(bytes(range(1, 33))).decode("ascii") + " other"
TOKEN = "synthetic-test-token"


class _Response:
    def __init__(self, content=b"{}"):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.content[:limit]


class OwnerVastHelperTests(unittest.TestCase):
    def test_helper_matches_only_exact_public_key_identity(self):
        payload = {"ssh_keys": json.dumps([
            {"id": 12, "public_key": OTHER},
            {"id": 23, "public_key": PUBLIC},
            {"id": 24, "public_key": PUBLIC + "x"},
        ])}
        with mock.patch.object(probe, "api", return_value=payload) as request:
            self.assertEqual(probe.match(TOKEN, PUBLIC), [23])
        request.assert_called_once_with("GET", "/instances/60509551/ssh", TOKEN)

    def test_owner_api_uses_fixed_https_origin_and_bearer_header(self):
        seen = {}

        def fake_open(request):
            seen["url"] = request.full_url
            seen["method"] = request.get_method()
            seen["authorization"] = request.get_header("Authorization")
            return _Response(b'{"instances":[]}')

        with mock.patch.object(probe, "_open", side_effect=fake_open):
            self.assertEqual(probe.api("GET", "/instances/", TOKEN), {"instances": []})
        self.assertEqual(seen, {
            "url": "https://console.vast.ai/api/v0/instances/",
            "method": "GET",
            "authorization": "Bearer " + TOKEN,
        })

    def test_api_rejects_out_of_scope_route_before_network(self):
        with mock.patch.object(probe, "_open") as request:
            with self.assertRaisesRegex(RuntimeError, "HOLD_PROVIDER_REQUEST_SCOPE"):
                probe.api("GET", "/instances/60509552/ssh", TOKEN)
        request.assert_not_called()

    def test_cleanup_detaches_only_the_recorded_key_and_verifies_absence(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / "runner"
            runner.mkdir(mode=0o700)
            key_path = runner / "owner-ssh-ed25519"
            track_path = runner / "ssh-key-track.json"
            key_path.write_text("private test material", encoding="utf-8")
            key_path.with_suffix(".pub").write_text(PUBLIC, encoding="utf-8")
            (runner / "known_hosts").write_text("host pin", encoding="utf-8")
            (runner / "owner-ssh.sock").write_text("stale socket marker", encoding="utf-8")
            track_path.write_text(json.dumps({"public": PUBLIC, "key_id": 23}), encoding="utf-8")

            responses = [
                {"ssh_keys": json.dumps([{"id": 23, "public_key": PUBLIC}])},
                {"success": True},
                {"ssh_keys": "[]"},
            ]
            calls = []

            def fake_api(method, path, key, body=None):
                calls.append((method, path, key, body))
                return responses.pop(0)

            with (
                mock.patch.object(probe, "RUNNER", runner),
                mock.patch.object(probe, "KEY", key_path),
                mock.patch.object(probe, "TRACK", track_path),
                mock.patch.dict("os.environ", {"NOX2": TOKEN}),
                mock.patch.object(probe, "api", side_effect=fake_api),
            ):
                self.assertTrue(probe.cleanup())

            self.assertEqual(calls, [
                ("GET", "/instances/60509551/ssh", TOKEN, None),
                ("DELETE", "/instances/60509551/ssh/23", TOKEN, None),
                ("GET", "/instances/60509551/ssh", TOKEN, None),
            ])
            self.assertFalse(runner.exists())

    def test_cleanup_refuses_to_detach_a_different_key_id(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / "runner"
            runner.mkdir(mode=0o700)
            track_path = runner / "ssh-key-track.json"
            track_path.write_text(json.dumps({"public": PUBLIC, "key_id": 23}), encoding="utf-8")
            calls = []

            def fake_api(method, path, key, body=None):
                calls.append((method, path))
                return {"ssh_keys": json.dumps([{"id": 24, "public_key": PUBLIC}])}

            with (
                mock.patch.object(probe, "RUNNER", runner),
                mock.patch.object(probe, "KEY", runner / "owner-ssh-ed25519"),
                mock.patch.object(probe, "TRACK", track_path),
                mock.patch.dict("os.environ", {"NOX2": TOKEN}),
                mock.patch.object(probe, "api", side_effect=fake_api),
            ):
                self.assertFalse(probe.cleanup())

            self.assertEqual(calls, [("GET", "/instances/60509551/ssh")])
            self.assertTrue(track_path.exists())

    def test_cleanup_without_tracking_is_local_only(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / "runner"
            runner.mkdir(mode=0o700)
            key_path = runner / "owner-ssh-ed25519"
            key_path.write_text("temporary private test material", encoding="utf-8")
            with (
                mock.patch.object(probe, "RUNNER", runner),
                mock.patch.object(probe, "KEY", key_path),
                mock.patch.object(probe, "TRACK", runner / "ssh-key-track.json"),
                mock.patch.object(probe, "api") as request,
            ):
                self.assertTrue(probe.cleanup())
            request.assert_not_called()
            self.assertFalse(runner.exists())


if __name__ == "__main__":
    unittest.main()
