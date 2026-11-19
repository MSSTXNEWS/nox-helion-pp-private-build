"""Offline security/compatibility checks for NOX V49; fake ports only, NOT live."""
import base64
import io
import json
import unittest

from nox_runpod.teacher_mesh.v39.native_control import HostAdmin, NativeAdmin
from nox_runpod.teacher_mesh.v49.onehost_bridge import (
    INBOX_SCHEMA, SCHEMA, NativePorts, OutboundOneHostBridge,
    digest, sign_request,
)
from nox_runpod.teacher_mesh.v49.github_https import (
    GitHubHTTPSMailbox, INBOX, RECEIPTS,
)


KEY = b"only-in-test-32-byte-hmac-key---1234"


class HostFixture:
    def __init__(self):
        self.claimed = {}
        self.events = []
        self.calls = []
        self.stopped = False
        self.allow = True
        self.audit_works = True
        self.registered = True
        self.admin = NativeAdmin(HostAdmin(
            authorize=lambda x: self.allow,
            stop=lambda: self.stopped,
            registered=lambda x: self.registered,
            inspect=self.inspect,
        ))
        self.ports = NativePorts(
            stop=lambda: self.stopped,
            claim_request=self.claim,
            append_s03=self.append,
            verify_s03=self.verify,
        )
        self.bridge = OutboundOneHostBridge(
            self.admin, self.ports, KEY, clock=lambda: 1100)

    def inspect(self, payload):
        self.calls.append(payload)
        return {"gpu": 2, "token": "must-never-leak", "status": "running"}

    def claim(self, request_id, sha):
        if request_id in self.claimed:
            return False
        self.claimed[request_id] = sha
        return True

    def append(self, event):
        if not self.audit_works:
            raise RuntimeError("native S03 unavailable")
        self.events.append(event)
        return {"hash": digest(event)}

    def verify(self, ack, event):
        return self.audit_works and ack.get("hash") == digest(event)


def req(**overrides):
    r = {
        "schema": SCHEMA,
        "request_id": "request-001",
        "instance_id": 60509551,
        "action": "server.status",
        "target_id": "NOX-60509551",
        "tenant_id": "NOX_OWNER",
        "principal_id": "owner",
        "chat_id": "main",
        "issued_at": 1000,
        "expires_at": 1200,
        "parameters": {},
    }
    r.update(overrides)
    r["signature"] = sign_request(r, KEY)
    return r


def inbox(*requests):
    return {"schema": INBOX_SCHEMA,
            "instance_id": 60509551,
            "requests": list(requests)}


class TestNativeBridge(unittest.TestCase):
    def setUp(self):
        self.h = HostFixture()

    def test_read_through_existing_onehost(self):
        r = self.h.bridge.process_one(req())
        self.assertEqual(r["state"], "READ_ONLY_FROM_NATIVE_ONEHOST")
        self.assertTrue(r["native_readback"])
        self.assertTrue(r["s03_durable"])
        self.assertFalse(r["performed"])
        self.assertNotIn("token", json.dumps(r))
        self.assertNotIn("must-never-leak", json.dumps(r))
        self.assertEqual(len(self.h.events), 1)
        self.assertEqual(len(self.h.calls), 1)

    def test_no_second_execution_on_replay(self):
        self.h.bridge.process_one(req())
        r = self.h.bridge.process_one(req())
        self.assertEqual(r["state"], "HOLD_REPLAY_OR_S03_UNAVAILABLE")
        self.assertEqual(len(self.h.calls), 1)

    def test_forgery_rejected_before_native(self):
        bad = req()
        bad["signature"] = "0" * 64
        r = self.h.bridge.process_one(bad)
        self.assertEqual(r["state"], "HOLD_BAD_SIGNATURE")
        self.assertFalse(self.h.calls)
        self.assertFalse(self.h.claimed)

    def test_modified_payload_cannot_use_old_signature(self):
        r = req()
        r["action"] = "nox.queue.status"
        result = self.h.bridge.process_one(r)
        self.assertEqual(result["state"], "HOLD_BAD_SIGNATURE")

    def test_training_write_forbidden_even_if_signed(self):
        r = self.h.bridge.process_one(req(action="nox.training.resume"))
        self.assertEqual(r["state"], "HOLD_ACTION_NOT_READ_ONLY")
        self.assertFalse(self.h.calls)

    def test_queue_enqueue_forbidden(self):
        r = self.h.bridge.process_one(req(action="nox.queue.enqueue"))
        self.assertEqual(r["state"], "HOLD_ACTION_NOT_READ_ONLY")

    def test_raw_shell_forbidden(self):
        r = self.h.bridge.process_one(req(action="run_shell"))
        self.assertEqual(r["state"], "HOLD_ACTION_NOT_READ_ONLY")

    def test_stop_has_absolute_precedence(self):
        self.h.stopped = True
        r = self.h.bridge.process_one(req())
        self.assertEqual(r["state"], "HOLD_STOP")
        self.assertFalse(self.h.claimed)

    def test_owner_acl_is_native(self):
        self.h.allow = False
        r = self.h.bridge.process_one(req())
        self.assertEqual(r["state"], "HOLD_STOP_OR_SCOPE")
        self.assertFalse(r["native_readback"])
        self.assertEqual(len(self.h.events), 1)

    def test_no_native_action_registered(self):
        self.h.registered = False
        r = self.h.bridge.process_one(req())
        self.assertEqual(r["state"], "HOLD_NATIVE_ACTION_NOT_REGISTERED")

    def test_expired(self):
        r = self.h.bridge.process_one(req(expires_at=1099))
        self.assertEqual(r["state"], "HOLD_EXPIRED_OR_FUTURE")

    def test_future(self):
        r = self.h.bridge.process_one(req(issued_at=1170, expires_at=1190))
        self.assertEqual(r["state"], "HOLD_EXPIRED_OR_FUTURE")

    def test_oversized_ttl(self):
        r = self.h.bridge.process_one(req(expires_at=1301))
        self.assertEqual(r["state"], "HOLD_TTL")

    def test_wrong_instance(self):
        r = self.h.bridge.process_one(req(instance_id=999999))
        self.assertEqual(r["state"], "HOLD_WRONG_TARGET")

    def test_untrusted_scope_is_rejected(self):
        r = self.h.bridge.process_one(req(principal_id="../bad space"))
        self.assertEqual(r["state"], "HOLD_REQUEST_VALIDATION")

    def test_missing_native_s03_is_hold_not_success(self):
        self.h.audit_works = False
        r = self.h.bridge.process_one(req())
        self.assertEqual(r["state"], "HOLD_NATIVE_OR_S03_EXCEPTION")
        self.assertEqual(r["performed"], "UNKNOWN")

    def test_batch_and_receipt_signatures(self):
        seen = []
        o = self.h.bridge.poll_once(inbox(req()), lambda x: seen.append(x) or True)
        self.assertEqual(o["published"], 1)
        self.assertEqual(len(seen), 1)
        sig = seen[0].pop("receipt_signature")
        self.assertEqual(sig, sign_request(seen[0], KEY))

    def test_too_many_jobs(self):
        o = self.h.bridge.poll_once(inbox(*[req(request_id=f"request-{i:03d}") for i in range(9)]),
                                    lambda x: True)
        self.assertEqual(o["state"], "HOLD_BATCH_SIZE")
        self.assertEqual(o["published"], 0)

    def test_bad_inbox(self):
        o = self.h.bridge.poll_once({"requests": []}, lambda x: True)
        self.assertEqual(o["state"], "HOLD_INBOX_SCHEMA")

    def test_missing_publish(self):
        o = self.h.bridge.poll_once(inbox(req()), None)
        self.assertEqual(o["state"], "HOLD_PUBLISH_PORT")
        self.assertEqual(len(self.h.calls), 0)

    def test_publish_failure_not_retried(self):
        o = self.h.bridge.poll_once(inbox(req()), lambda x: False)
        self.assertEqual(o["state"], "HOLD_RECEIPT_PUBLICATION")
        self.assertTrue(o["may_have_processed"])
        self.assertEqual(len(self.h.calls), 1)

    def test_missing_bridge_key_failclosed(self):
        with self.assertRaises(ValueError):
            OutboundOneHostBridge(self.h.admin, self.h.ports, b"tiny")

    def test_native_admin_only(self):
        with self.assertRaises(TypeError):
            OutboundOneHostBridge(object(), self.h.ports, KEY)


class FakeResponse:
    def __init__(self, payload):
        self.stream = io.BytesIO(json.dumps(payload).encode())

    def __enter__(self): return self
    def __exit__(self, *args): self.stream.close()
    def read(self, size): return self.stream.read(size)


class FakeHTTPS:
    def __init__(self):
        self.calls = []
        self.data = {
            INBOX: inbox(),
            RECEIPTS: {"schema": "NOX_ONEHOST_BRIDGE_RECEIPTS_V1", "receipts": []}
        }

    def open(self, request, timeout=15):
        self.calls.append(request)
        path = INBOX if INBOX in request.full_url else RECEIPTS
        if request.get_method() == "PUT":
            incoming = json.loads(request.data)
            body = base64.b64decode(incoming["content"])
            self.data[path] = json.loads(body)
            return FakeResponse({"commit": {"sha": "f" * 40}})
        obj = {
            "type": "file",
            "encoding": "base64",
            "sha": "a" * 40,
            "content": base64.b64encode(
                json.dumps(self.data[path]).encode()).decode(),
        }
        return FakeResponse(obj)


class TestGitHubMailbox(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHTTPS()
        self.mail = GitHubHTTPSMailbox(token="nonsecret-test-only-key", opener=self.fake)

    def test_reads_only_pinned_repo_path(self):
        got = self.mail.read_inbox()
        self.assertEqual(got["schema"], INBOX_SCHEMA)
        self.assertIn("api.github.com/repos/MSSTXNEWS/", self.fake.calls[0].full_url)
        self.assertIn("ref=feature%2Fnox-v38-synaptic-brain-20261114",
                      self.fake.calls[0].full_url)

    def test_publishes_only_signed_minimal_receipt(self):
        receipt = {
            "schema": "NOX_ONEHOST_BRIDGE_RECEIPT_V1",
            "request_id": "request-001", "action": "server.status",
            "state": "READ_ONLY_FROM_NATIVE_ONEHOST",
            "request_sha256": "a" * 64, "data_sha256": "b" * 64,
            "performed": False, "native_readback": True,
            "independent_verified": False, "s03_durable": True,
            "receipt_signature": "c" * 64,
        }
        self.assertTrue(self.mail.publish(receipt))
        self.assertEqual(len(self.fake.data[RECEIPTS]["receipts"]), 1)
        self.assertTrue(self.mail.publish(receipt))  # idempotent
        self.assertEqual(len(self.fake.data[RECEIPTS]["receipts"]), 1)

    def test_no_sensitive_data_in_receipts(self):
        self.assertFalse(self.mail.publish({
            "schema": "NOX_ONEHOST_BRIDGE_RECEIPT_V1",
            "request_id": "request-001",
            "authorization": "secret",
        }))

    def test_no_writer_token_failclosed(self):
        mail = GitHubHTTPSMailbox(opener=self.fake)
        self.assertRaises(ValueError, mail.publish, {
            "schema": "NOX_ONEHOST_BRIDGE_RECEIPT_V1",
            "request_id": "request-001",
            "receipt_signature": "c" * 64,
        })

    def test_no_signed_receipt_cannot_publish(self):
        self.assertFalse(self.mail.publish({
            "schema": "NOX_ONEHOST_BRIDGE_RECEIPT_V1",
            "request_id": "request-001",
        }))

    def test_wrong_branch_failclosed(self):
        with self.assertRaises(ValueError):
            GitHubHTTPSMailbox(token="nonsecret-test-only-key", branch="main", opener=self.fake)


if __name__ == "__main__":
    unittest.main()
