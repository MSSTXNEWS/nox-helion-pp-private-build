import json
import unittest
import test_typed_failed_poststate as fixture
from typed_failed_poststate import classify_typed_failed_turn as old
from pending_wire import classify_wire_failed_turn as new
from test_b5_chain_guard import sha

class PendingWireTest(unittest.TestCase):
    def test_failed_turn_wire_identity(self):
        for n in (1, 2):
            for mid, text, attempt, expected in (
                ("message-é🪐", "¿Qué recuerdas?\nПомни 🪐", "attempt-next", "HOLD_S03_FAILURE_PENDING_USER"),
                ("msg\u200bhidden", "¿Qué recuerdas?", "attempt-next", "HOLD_S03_FAILURE_PENDING_ID_INVALID"),
                ("msg\x00hidden", "Помни", "attempt-next", "HOLD_S03_FAILURE_PENDING_ID_INVALID"),
                ("message-next", "Hola\ud800", "attempt-next", "HOLD_S03_FAILURE_PENDING_TEXT_INVALID"),
                ("message-next", "Помни", "attempt\u200bnext", "HOLD_S03_FAILURE_ATTEMPT_ID_INVALID"),
            ):
                with self.subTest(n=n, mid=mid, text=repr(text), attempt=attempt):
                    args = fixture.TypedFailureTest().scenario(n, True, True, True)
                    doc = json.loads(args["snapshot_raw"])
                    doc["attempt_id"] = attempt
                    doc["messages"][-1].update(message_id=mid, content=text)
                    b = json.dumps(doc, ensure_ascii=True).encode("utf-8")
                    receipt = json.loads(args["admission_raw"])
                    receipt.update(attempt_id=attempt, snapshot_sha256=sha(b), user_message_id=mid)
                    r = json.dumps(receipt, ensure_ascii=True).encode("utf-8")
                    args.update(attempt_id=attempt, prompt=text, snapshot_raw=b, snapshot_sha256=sha(b),
                                admission_raw=r, admission_sha256=sha(r))
                    self.assertEqual(old(**args), "HOLD_S03_FAILURE_PENDING_USER")
                    self.assertEqual(new(**args), expected)
            args = fixture.TypedFailureTest().scenario(n, True, True, False)
            self.assertEqual(new(**args), "HOLD_S03_FAILURE_PREFIX_INTACT")
        print("R83: 12 failed-turn cases; 8 invalid pending witnesses rejected; all HOLD")
