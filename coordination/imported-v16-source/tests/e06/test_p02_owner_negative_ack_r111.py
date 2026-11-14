"""BOOST03 R111: real source regression for negative owner ACK crossing native P02.

No extra host/server and no native Windows E07 acceptance implied.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
P02 = ROOT / "Packages/P02/worker-python/p02_native_ingress.py"
STAGER = ROOT / "coordination/e06/stage_native_stdio.py"
spec = importlib.util.spec_from_file_location("p02_native_ingress_r111", P02)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


class TrustedOwner:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def execute(self, route, payload, session):
        self.calls += 1
        return self.result


class OwnerNegativeAck(unittest.TestCase):
    def invoke(self, owner_result, route="helion.chat"):
        owner = TrustedOwner(owner_result)
        ingress = module.NativeIngress(owner, lambda: object(), expected_run_id="run-r111")
        envelope = {"protocol":"NOX-P02-NATIVE-v1", "requestId":"a"*32,
                    "route":route, "payload":{"text":"hello"}, "runId":"run-r111"}
        payload = json.dumps(envelope, separators=(",", ":")).encode()
        return owner, ingress, payload

    def test_revocation_never_becomes_native_ok(self):
        for state in ("CONSENT_REVOKED", "REVOKED", "REVOKED_BY_OWNER",
                      "consent_revoked", " consent_revoked ", "CANCELED",
                      "CANCELED_BY_CLIENT", "CANCELLED"):
            with self.subTest(status=state):
                owner, ingress, payload = self.invoke({"status":state})
                with self.assertRaisesRegex(module.ProtocolHold, "NATIVE_OWNER_RESULT_HOLD"):
                    ingress.handle(payload)
                self.assertEqual(owner.calls, 1)

    def test_stop_pending_never_becomes_native_ok(self):
        for state in ("STOP_REQUESTED", "STOPPING", "STOPPING_BY_OWNER"):
            with self.subTest(status=state):
                owner, ingress, payload = self.invoke({"status":state})
                with self.assertRaisesRegex(module.ProtocolHold, "NATIVE_OWNER_RESULT_HOLD"):
                    ingress.handle(payload)
                self.assertEqual(owner.calls, 1)

    def test_explicit_ok_true_cannot_override_revoked_status(self):
        owner, ingress, payload = self.invoke({"ok":True, "status":"CONSENT_REVOKED"})
        with self.assertRaisesRegex(module.ProtocolHold, "NATIVE_OWNER_RESULT_HOLD"):
            ingress.handle(payload)
        self.assertEqual(owner.calls, 1)

    def test_stopped_ack_only_for_stop_and_pause(self):
        owner, ingress, payload = self.invoke({"status":"STOPPED"}, "chat.stop")
        answer = json.loads(ingress.handle(payload))
        self.assertEqual(answer["status"], "OK")
        self.assertEqual(answer["result"]["status"], "STOPPED")
        owner, ingress, payload = self.invoke({"status":"STOPPED"}, "helion.chat")
        with self.assertRaises(module.ProtocolHold):
            ingress.handle(payload)

    def test_stop_request_ack_is_not_completion(self):
        owner, ingress, payload = self.invoke({"status":"STOP_REQUESTED"}, "chat.stop")
        with self.assertRaises(module.ProtocolHold):
            ingress.handle(payload)

    def test_valid_queue_and_success_unchanged(self):
        for value in ({"status":"QUEUED", "runId":"trusted-job"}, {"status":"OK", "text":"ok"}):
            owner, ingress, payload = self.invoke(value)
            answer = json.loads(ingress.handle(payload))
            self.assertEqual(answer["status"], "OK")
            self.assertEqual(answer["result"], value)

    def test_nonboolean_ok_rejected(self):
        owner, ingress, payload = self.invoke({"status":"OK", "ok":"true"})
        with self.assertRaises(module.ProtocolHold):
            ingress.handle(payload)

    def test_stager_pins_exact_native_ingress_source(self):
        content = P02.read_bytes()
        stager = STAGER.read_text(encoding="utf-8")
        pin = ("('Packages/P02/worker-python/p02_native_ingress.py', "
               "'p02_native_ingress.py', '" + git_blob(content) + "')")
        self.assertEqual(stager.count(pin), 1)
        self.assertIn('"CONSENT_REVOKED", "REVOKED"', content.decode())
        self.assertIn('"STOP_REQUESTED", "STOPPING", "CANCELED", "CANCELLED"', content.decode())

if __name__ == "__main__":
    unittest.main()
