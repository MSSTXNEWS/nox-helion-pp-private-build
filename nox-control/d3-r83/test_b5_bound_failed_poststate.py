import unittest
from test_b5_chain_guard import checkpoint, DIALOG, SESSION, TEXT, raw, sha
from b5_failed_poststate import classify_failed_turn
from b5_bound_failed_poststate import classify_bound_failed_turn

class BoundPendingTests(unittest.TestCase):
    def args(self, n, rows):
        wire=raw(dict(source="canonical_s03", independent=True, dialog_id=DIALOG,
                      session_id=SESSION, attempt_id="attempt-next", messages=rows))
        return dict(dialog_id=DIALOG, session_id=SESSION, attempt_id="attempt-next",
                    prompt=TEXT[2*n], prior_chain=tuple(checkpoint(i) for i in range(1,n+1)),
                    snapshot_raw=wire, snapshot_sha256=sha(wire))

    def test_identical_prompt_foreign_row(self):
        for n in (1,2):
            rows=checkpoint(n+1)[0][:-1]
            expected=rows[-1]["message_id"]
            rows[-1]["message_id"]="unrelated-pending-id"
            args=self.args(n,rows)
            self.assertEqual(classify_failed_turn(**args),"HOLD_S03_FAILURE_PENDING_USER")
            self.assertEqual(classify_bound_failed_turn(expected_user_message_id=expected,**args),
                             "HOLD_S03_FAILURE_PENDING_ID_MISMATCH")

    def test_missing_or_invalid_admission_identity(self):
        for n in (1,2):
            args=self.args(n,checkpoint(n+1)[0][:-1])
            for value in (None,""," padded ",False,1):
                self.assertEqual(classify_bound_failed_turn(expected_user_message_id=value,**args),
                                 "HOLD_S03_FAILURE_PENDING_ID_UNPROVEN")

    def test_exact_pending_and_nonpending_results(self):
        for n in (1,2):
            rows=checkpoint(n+1)[0][:-1]
            expected=rows[-1]["message_id"]
            self.assertEqual(classify_bound_failed_turn(expected_user_message_id=expected,
                              **self.args(n,rows)),"HOLD_S03_FAILURE_PENDING_USER")
            for observed,result in ((checkpoint(n)[0],"HOLD_S03_FAILURE_PREFIX_INTACT"),
                                     (checkpoint(n+1)[0],"HOLD_S03_FAILURE_UNEXPECTED_ROWS")):
                self.assertEqual(classify_bound_failed_turn(**self.args(n,observed)),result)
