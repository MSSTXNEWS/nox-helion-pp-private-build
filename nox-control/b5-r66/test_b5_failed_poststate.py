import unittest
from test_b5_chain_guard import checkpoint, DIALOG, SESSION, TEXT, raw, sha
from b5_failed_poststate import classify_failed_turn

class FailedPoststateTests(unittest.TestCase):
    def check(self, n, observed, **overrides):
        chain = tuple(checkpoint(i) for i in range(1,n+1))
        doc = dict(source="canonical_s03", independent=True, dialog_id=DIALOG,
                   session_id=SESSION, attempt_id="attempt-next", messages=observed)
        doc.update(overrides.pop("document", {}))
        wire = raw(doc)
        args = dict(dialog_id=DIALOG, session_id=SESSION, attempt_id="attempt-next",
                    prompt=TEXT[2*n], prior_chain=chain, snapshot_raw=wire,
                    snapshot_sha256=sha(wire))
        args.update(overrides)
        return classify_failed_turn(**args)

    def test_failed_second_and_third_prefix_intact_not_accepted(self):
        for n in (1,2):
            self.assertEqual(self.check(n,checkpoint(n)[0]),
                             "HOLD_S03_FAILURE_PREFIX_INTACT")

    def test_user_only_is_pending_not_completed(self):
        for n in (1,2):
            self.assertEqual(self.check(n,checkpoint(n+1)[0][:-1]),
                             "HOLD_S03_FAILURE_PENDING_USER")

    def test_assistant_or_extra_rows_are_not_success(self):
        for n in (1,2):
            self.assertEqual(self.check(n,checkpoint(n+1)[0]),
                             "HOLD_S03_FAILURE_UNEXPECTED_ROWS")

    def test_rewritten_prefix_and_pending_id_reuse(self):
        rows=checkpoint(3)[0][:-1]
        rows[0]["content"]="cambio"
        self.assertEqual(self.check(2,rows),"HOLD_S03_FAILURE_PREFIX_CHANGED")
        rows=checkpoint(3)[0][:-1]
        rows[-1]["message_id"]=rows[0]["message_id"]
        self.assertEqual(self.check(2,rows),"HOLD_S03_FAILURE_UNEXPECTED_ROWS")

    def test_wrong_pin_scope_attempt_and_duplicate_json(self):
        rows=checkpoint(2)[0]
        self.assertEqual(self.check(2,rows,snapshot_sha256="0"*64),"HOLD_S03_FAILURE_INPUT")
        for doc in ({"session_id":"foreign"},{"attempt_id":"old"},{"independent":False}):
            self.assertEqual(self.check(2,rows,document=doc),"HOLD_S03_FAILURE_SCOPE")
        bad=b'{"messages":[],"messages":[]}'
        self.assertEqual(self.check(2,rows,snapshot_raw=bad,snapshot_sha256=sha(bad)),
                         "HOLD_S03_FAILURE_INVALID")
