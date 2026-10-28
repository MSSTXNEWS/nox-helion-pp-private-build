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

    def test_json_duplicate_keys_and_nonfinite_rejected_before_dispatch(self):
        bad = (
            b'{"protocol":"NOX-P02-NATIVE-v1","protocol":"NOX-P02-NATIVE-v1",'
            b'"runId":"' + R.encode() + b'","requestId":"' + b"1" * 32 +
            b'","route":"chat.model","payload":{}}',
            b'{"protocol":"NOX-P02-NATIVE-v1","runId":"' + R.encode() +
            b'","requestId":"' + b"2" * 32 +
            b'","route":"chat.model","payload":{"x":{"ok":1,"ok":2}}}',
            b'{"protocol":"NOX-P02-NATIVE-v1","runId":"' + R.encode() +
            b'","requestId":"' + b"3" * 32 +
            b'","route":"chat.model","payload":{"score":NaN}}',
            b'{"protocol":"NOX-P02-NATIVE-v1","runId":"' + R.encode() +
            b'","requestId":"' + b"4" * 32 +
            b'","route":"chat.model","payload":{"score":Infinity}}',
            b'{"protocol":"NOX-P02-NATIVE-v1","runId":"' + R.encode() +
            b'","requestId":"' + b"5" * 32 +
            b'","route":"chat.model","payload":{"score":1e9999}}',
        )
        for raw in bad:
            with self.subTest(raw=raw[-40:]):
                with self.assertRaisesRegex(ProtocolHold, "INVALID_JSON"):
                    self.router.handle(raw)
        self.assertFalse(self.provider.seen)

    def test_p03_read_routes_require_explicit_native_opt_in_and_bound_owner(self):
        # ModelCenter does not get a second downloader or unauthenticated route.
        with self.assertRaisesRegex(ProtocolHold, "ROUTE_OR_PAYLOAD"):
            self.router.handle(packet(12, "models.catalog"))
        ingress = NativeIngress(self.provider, lambda: self.trusted,
                                expected_run_id=R, allow_modelcenter_reads=True)
        with self.assertRaisesRegex(ProtocolHold, "OWNER_NOT_BOUND"):
            ingress.handle(packet(13, "models.catalog"))
        self.provider.routes = {"models.catalog": {"owner": 3}}
        self.provider.ports = {"models.catalog": type("Port", (), {
            "owner": 3, "evidence_id": "PINNED_OWNER3_SOURCE",
            "call": staticmethod(lambda scope, args: {"native": True}),
            "available": staticmethod(lambda: True)})()}
        response = json.loads(ingress.handle(packet(14, "models.catalog")))
        self.assertEqual(response["result"]["route"], "models.catalog")
        with self.assertRaisesRegex(ProtocolHold, "ROUTE_OR_PAYLOAD"):
            ingress.handle(packet(15, "models.pull"))
        with self.assertRaisesRegex(ProtocolHold, "ROUTE_OR_PAYLOAD"):
            ingress.handle(packet(16, "models.gguf.import"))
        self.assertEqual([item[0] for item in self.provider.seen], ["models.catalog"])

    def test_modelcenter_wrong_owner_or_empty_receipt_denied(self):
        self.provider.routes = {"models.installed": {"owner": 2}}
        self.provider.ports = {"models.installed": type("Port", (), {
            "owner": 3, "evidence_id": ""})()}
        ingress = NativeIngress(self.provider, lambda: self.trusted,
                                expected_run_id=R, allow_modelcenter_reads=True)
        with self.assertRaisesRegex(ProtocolHold, "OWNER_NOT_BOUND"):
            ingress.handle(packet(17, "models.installed"))
        self.assertFalse(self.provider.seen)

    def test_overdeep_nested_json_is_protocol_hold(self):
        payload = b"[" * 1300 + b"0" + b"]" * 1300
        with self.assertRaisesRegex(ProtocolHold, "INVALID_JSON"):
            self.router.handle(payload)
        self.assertFalse(self.provider.seen)

    def test_modelcenter_noncallable_port_cannot_pass_native_admission(self):
        self.provider.routes = {"models.catalog": {"owner": 3}}
        self.provider.ports = {"models.catalog": type("Port", (), {
            "owner": 3, "evidence_id": "FORGED_PORT_METADATA"})()}
        ingress = NativeIngress(self.provider, lambda: self.trusted,
                                expected_run_id=R, allow_modelcenter_reads=True)
        with self.assertRaisesRegex(ProtocolHold, "OWNER_NOT_BOUND"):
            ingress.handle(packet(30, "models.catalog"))
        self.assertFalse(self.provider.seen)

    def test_missing_session_fails_closed(self):
        ingress = NativeIngress(self.provider, lambda: None, expected_run_id=R)
        with self.assertRaisesRegex(ProtocolHold, "AUTHENTICATED"):
            ingress.handle(packet(8))

if __name__ == "__main__":
    unittest.main()
