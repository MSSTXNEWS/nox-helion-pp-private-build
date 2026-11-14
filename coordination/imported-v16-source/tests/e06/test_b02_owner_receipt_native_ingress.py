"""B02: native Python must not sign explicit negative owner receipts as OK.

SOURCE_ONLY regression until it executes on a current-source Windows runner.
"""
from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Packages" / "P02" / "worker-python"))
from p02_native_ingress import NativeIngress, ProtocolHold  # noqa: E402


class Owner:
    def __init__(self, reply):
        self.reply = reply

    def execute(self, route, payload, session):
        return self.reply


class NativeOwnerReceiptB02(unittest.TestCase):
    def check(self, reply, *, route="helion.chat", held=True):
        ingress = NativeIngress(
            Owner(reply), lambda: object(), expected_run_id="B02_NATIVE_RUN")
        frame = json.dumps({
            "protocol": "NOX-P02-NATIVE-v1",
            "requestId": "4" * 32, "route": route, "payload": {},
            "runId": "B02_NATIVE_RUN",
        }).encode("utf-8")
        if held:
            with self.assertRaisesRegex(ProtocolHold, "NATIVE_OWNER_RESULT_HOLD"):
                ingress.handle(frame)
        else:
            response = json.loads(ingress.handle(frame).decode("utf-8"))
            self.assertEqual(response["status"], "OK")
            self.assertEqual(response["result"], reply)

    def test_nested_explicit_owner_denials(self):
        for reply in (
            {"ok": True, "receipt": {"ack": False}},
            {"ok": True, "owner_result": {"success": False}},
            {"ok": True, "result": {"approved": False}},
            {"ok": True, "ownerReceipt": {"authorized": False}},
            {"ok": True, "receipt": {"status": "CONSENT_REQUIRED"}},
            {"ok": True, "result": {"status": "MODEL_PROVIDER_OFFLINE_HOLD"}},
            {"ok": True, "receipt": {"ack": "true"}},
            {"ok": True, "result": {"receipt": {"ownerResult": {"ok": False}}}},
        ):
            with self.subTest(reply=reply):
                self.check(reply)

    def test_success_and_queued_are_not_equated_with_trained_weights(self):
        self.check({"ok": True, "result": {"status": "QUEUED",
                    "task_id": 7, "execution_completed": False,
                    "activation_allowed": False}}, held=False)
        self.check({"ok": True, "receipt": {"ack": True, "status": "READY"}},
                   held=False)
        self.check({"status": "STOPPED"}, route="chat.stop", held=False)

    def test_deep_unverifiable_owner_wrapper_fails_closed(self):
        self.check({"result": {"receipt": {"result": {
            "owner_result": {"ack": False}}}}})


if __name__ == "__main__":
    unittest.main()
