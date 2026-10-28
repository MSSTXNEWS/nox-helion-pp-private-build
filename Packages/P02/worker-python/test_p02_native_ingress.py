"""Cross-boundary tests against the exact existing dispatcher shape (no service)."""
import json
import threading
import unittest
from p02_native_ingress import NativeIngress, ProtocolHold

R = "NOX-E02-NATIVE-BOUNDARY-C9"


def packet(n, route="chat.model", payload=None, **extra):
    body = {"protocol": "NOX-P02-NATIVE-v1", "runId": R,
            "requestId": f"{n:032x}", "route": route,
            "payload": payload if payload is not None else {}}
    body.update(extra)
    return json.dumps(body).encode()


class Dispatcher:
    def __init__(self):
        self.seen = []
        self.block = threading.Event()
        self.open = threading.Event()

    def execute(self, route, payload, session):
        self.seen.append((route, session))
        if route == "helion.chat":
            self.block.set()
            if not self.open.wait(2):
                raise RuntimeError("timeout")
        if route == "chat.stop":
            self.open.set()
        return {"route": route, "user": "verified"}


class IngressTests(unittest.TestCase):
    def setUp(self):
        self.provider = Dispatcher()
        self.trusted = object()
        self.router = NativeIngress(self.provider, lambda: self.trusted, expected_run_id=R)

    def test_host_resolved_identity_not_page_identity(self):
        x = json.loads(self.router.handle(packet(1)))
        self.assertEqual(x["result"]["user"], "verified")
        self.assertIs(self.provider.seen[0][1], self.trusted)

    def test_page_authority_claim_fails_without_touching_dispatcher(self):
        with self.assertRaisesRegex(ProtocolHold, "AUTHORITY"):
            self.router.handle(packet(2, payload={"principal": "administrator"}))
        self.assertFalse(self.provider.seen)

    def test_replay_and_cross_run_rejected(self):
        self.router.handle(packet(3))
        with self.assertRaisesRegex(ProtocolHold, "REPLAY"):
            self.router.handle(packet(3))
        with self.assertRaisesRegex(ProtocolHold, "RUN_MISMATCH"):
            self.router.handle(packet(4, runId="foreign"))

    def test_invalid_frame_and_extra_session_rejected(self):
        for data in (b"{}", b"\xff", b"x" * (64 * 1024 + 1), packet(7, role="admin")):
            with self.subTest(data=data[:20]):
                with self.assertRaises(ProtocolHold):
                    self.router.handle(data)
        self.assertFalse(self.provider.seen)

    def test_stop_overtakes_active_chat_without_second_queue(self):
        outcome = []
        def chat():
            try: outcome.append(self.router.handle(packet(5, route="helion.chat")))
            except Exception as err: outcome.append(err)
        task = threading.Thread(target=chat)
        task.start()
        try:
            self.assertTrue(self.provider.block.wait(1))
            stop = json.loads(self.router.handle(packet(6, route="chat.stop")))
            self.assertEqual(stop["status"], "OK")
        finally:
            self.provider.open.set()
            task.join(timeout=1)
        self.assertFalse(task.is_alive())
        self.assertEqual(len(outcome), 1)
        self.assertIsInstance(outcome[0], bytes)

    def test_missing_session_fails_closed(self):
        ingress = NativeIngress(self.provider, lambda: None, expected_run_id=R)
        with self.assertRaisesRegex(ProtocolHold, "AUTHENTICATED"):
            ingress.handle(packet(8))

if __name__ == "__main__":
    unittest.main()
