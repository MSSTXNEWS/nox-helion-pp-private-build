"""Offline tests: owner-only signer refuses unsafe or duplicate commands."""
import unittest
from nox_runpod.teacher_mesh.v49.sign_readonly import prepare_request
from nox_runpod.teacher_mesh.v49.onehost_bridge import INBOX_SCHEMA, OutboundOneHostBridge, sign_request
from nox_runpod.teacher_mesh.v49.tests.test_onehost_bridge import HostFixture, KEY

EMPTY = {"schema": INBOX_SCHEMA, "instance_id": 60509551, "requests": []}


class TestSigner(unittest.TestCase):
    def test_only_one_signed_request(self):
        data = prepare_request(EMPTY, action="server.status",
            actor="MSSTXNEWS", run_id="43594171493", key=KEY, now=1090)
        self.assertEqual(len(data["requests"]), 1)
        request = data["requests"][0]
        self.assertEqual(request["signature"], sign_request(request, KEY))
        self.assertTrue(HostFixture().bridge._valid(request)[0])

    def test_non_owner_rejected(self):
        with self.assertRaises(ValueError):
            prepare_request(EMPTY, action="server.status",
                actor="intruder", run_id="43594171493", key=KEY, now=1090)

    def test_native_write_action_rejected(self):
        with self.assertRaises(ValueError):
            prepare_request(EMPTY, action="nox.queue.enqueue",
                actor="MSSTXNEWS", run_id="43594171493", key=KEY, now=1090)

    def test_cannot_replace_pending_request(self):
        data = prepare_request(EMPTY, action="server.status",
            actor="MSSTXNEWS", run_id="43594171493", key=KEY, now=1090)
        with self.assertRaises(ValueError):
            prepare_request(data, action="server.status",
                actor="MSSTXNEWS", run_id="43594171494", key=KEY, now=1091)

    def test_key_missing(self):
        with self.assertRaises(ValueError):
            prepare_request(EMPTY, action="server.status",
                actor="MSSTXNEWS", run_id="43594171493", key=b"", now=1090)

    def test_bad_run_id(self):
        with self.assertRaises(ValueError):
            prepare_request(EMPTY, action="server.status",
                actor="MSSTXNEWS", run_id="evil-command", key=KEY, now=1090)


if __name__ == "__main__":
    unittest.main()
