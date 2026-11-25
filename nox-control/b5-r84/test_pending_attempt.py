import json
import unittest
from test_typed_failed_poststate import TypedFailureTest
from test_b5_chain_guard import sha
from pending_wire import classify_wire_failed_turn as old
from pending_attempt import classify_pending_attempt as new

class PendingAttemptTest(unittest.TestCase):
    def test_pending_row_attempt_and_metadata(self):
        for n in (1, 2):
            for extra, expected in (
                ({}, "HOLD_S03_FAILURE_PENDING_USER"),
                ({"attempt_id": "attempt-next", "metadata": {"language": "es", "label": "Помни 🪐"}}, "HOLD_S03_FAILURE_PENDING_USER"),
                ({"attempt_id": "attempt-other"}, "HOLD_S03_FAILURE_PENDING_ATTEMPT_MISMATCH"),
                ({"attempt_id": None}, "HOLD_S03_FAILURE_PENDING_ATTEMPT_MISMATCH"),
                ({"attempt_id": 1}, "HOLD_S03_FAILURE_PENDING_ATTEMPT_MISMATCH"),
                ({"metadata": {"label": "bad\ud800"}}, "HOLD_S03_FAILURE_PENDING_METADATA_INVALID"),
                ({"metadata": {"bad\ud800": "value"}}, "HOLD_S03_FAILURE_PENDING_METADATA_INVALID"),
            ):
                with self.subTest(n=n, extra=repr(extra)):
                    args = TypedFailureTest().scenario(n, True, True, True)
                    doc = json.loads(args["snapshot_raw"])
                    doc["messages"][-1].update(extra)
                    b = json.dumps(doc, ensure_ascii=True).encode("utf-8")
                    receipt = json.loads(args["admission_raw"])
                    receipt["snapshot_sha256"] = sha(b)
                    r = json.dumps(receipt, ensure_ascii=True).encode("utf-8")
                    args.update(snapshot_raw=b, snapshot_sha256=sha(b),
                                admission_raw=r, admission_sha256=sha(r))
                    self.assertEqual(old(**args), "HOLD_S03_FAILURE_PENDING_USER")
                    self.assertEqual(new(**args), expected)
            args = TypedFailureTest().scenario(n, True, True, False)
            self.assertEqual(new(**args), "HOLD_S03_FAILURE_PREFIX_INTACT")
        print("R84: 16 second/third-turn cases; 10 invalid pending witnesses rejected; all HOLD")
