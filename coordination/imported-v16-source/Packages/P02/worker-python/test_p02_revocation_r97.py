"""BOOST03: queued authenticated IPC must re-resolve native grants after serial wait."""
import json
import threading
import unittest
from p02_native_ingress import NativeIngress, ProtocolHold

RUN = "BOOST03-R97-REVOCATION"

def frame(n, route):
    return json.dumps({"protocol": "NOX-P02-NATIVE-v1", "runId": RUN,
                       "requestId": f"{n:032x}", "route": route, "payload": {}}).encode()

class QueuedConsentRevocation(unittest.TestCase):
    def test_revoked_grant_is_not_reused_by_queued_native_call(self):
        first_entered = threading.Event()
        release_first = threading.Event()
        second_lookup = threading.Event()
        mu = threading.Lock()
        state = {"allowed": True, "lookups": 0}
        executed = []
        def native_session():
            with mu:
                state["lookups"] += 1
                allowed = state["allowed"]
                if state["lookups"] >= 2:
                    second_lookup.set()
            return {"allow": allowed}
        class OriginalOwner:
            def execute(self, route, payload, session):
                if route == "helion.chat":
                    first_entered.set()
                    if not release_first.wait(3):
                        raise RuntimeError("fixture timeout")
                executed.append((route, session["allow"]))
                return {"status": "QUEUED" if session["allow"] else "CONSENT_REQUIRED"}
        bridge = NativeIngress(OriginalOwner(), native_session, expected_run_id=RUN)
        outcomes = {}
        def invoke(key, n, route):
            try:
                outcomes[key] = json.loads(bridge.handle(frame(n, route)))["status"]
            except ProtocolHold as exc:
                outcomes[key] = str(exc)
        t1 = threading.Thread(target=invoke, args=("first", 1, "helion.chat"))
        t2 = threading.Thread(target=invoke, args=("second", 2, "chat.model"))
        t1.start()
        try:
            self.assertTrue(first_entered.wait(2), "original call never entered owner")
            t2.start()
            # On vulnerable code, the second grant is already snapshotted while
            # it waits on _serial. On fixed code, lookup happens after lock.
            second_lookup.wait(.4)
            with mu:
                state["allowed"] = False  # host revokes consent while queued
        finally:
            release_first.set()
        t1.join(3)
        if t2.ident is not None:
            t2.join(3)
        self.assertFalse(t1.is_alive())
        self.assertFalse(t2.is_alive())
        self.assertEqual(outcomes.get("first"), "OK")
        self.assertEqual(outcomes.get("second"), "NATIVE_OWNER_RESULT_HOLD")
        self.assertIn(("chat.model", False), executed)
        self.assertNotIn(("chat.model", True), executed)

if __name__ == "__main__":
    unittest.main()
