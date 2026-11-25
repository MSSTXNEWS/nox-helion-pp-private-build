import json
import unittest
from test_b5_chain_guard import checkpoint, DIALOG, SESSION, TEXT, raw, sha
from b5_strict_receipted_poststate import classify_strict_receipted_failed_turn as old
from typed_failed_poststate import classify_typed_failed_turn as new

class TypedFailureTest(unittest.TestCase):
    def scenario(self, n, prior, observed, pending):
        chain=[]
        for i in range(1,n+1):
            rows,(w,r,ws,rs)=checkpoint(i)
            rows[0]["metadata"]={"flag":prior}
            doc=json.loads(r); doc["messages"]=rows; r=raw(doc)
            chain.append((rows,(w,r,ws,sha(r))))
        rows=checkpoint(n+1)[0][:-1] if pending else checkpoint(n)[0]
        rows[0]["metadata"]={"flag":observed}
        doc=dict(source="canonical_s03",independent=True,dialog_id=DIALOG,
                 session_id=SESSION,attempt_id="attempt-next",messages=rows)
        b=raw(doc)
        args=dict(dialog_id=DIALOG,session_id=SESSION,attempt_id="attempt-next",
                  prompt=TEXT[2*n],prior_chain=tuple(chain),snapshot_raw=b,snapshot_sha256=sha(b))
        if pending:
            receipt=raw(dict(schema="nox.s03.failed-attempt-binding.v1",dialog_id=DIALOG,
                session_id=SESSION,attempt_id="attempt-next",snapshot_sha256=sha(b),
                user_message_id=rows[-1]["message_id"]))
            args.update(admission_raw=receipt,admission_sha256=sha(receipt))
        return args

    def test_exact_failed_second_third(self):
        for n in (1,2):
            for pending in (False,True):
                state="HOLD_S03_FAILURE_PENDING_USER" if pending else "HOLD_S03_FAILURE_PREFIX_INTACT"
                for a,b,valid in ((True,True,True),(True,1,False),(1,1.0,False),(0.0,-0.0,False)):
                    with self.subTest(n=n,pending=pending,a=a,b=b):
                        args=self.scenario(n,a,b,pending)
                        self.assertEqual(old(**args),state)
                        self.assertEqual(new(**args),state if valid else "HOLD_S03_FAILURE_TYPED_PREFIX_CHANGED")
                args=self.scenario(n,True,True,pending)
                args["prior_chain"][-1][0][0]["metadata"]["flag"]=1
                self.assertEqual(old(**args),state)
                self.assertEqual(new(**args),"HOLD_S03_FAILURE_TYPED_PREFIX_CHANGED")
                args=self.scenario(n,True,True,pending)
                args["snapshot_sha256"]="0"*64
                self.assertEqual(new(**args),"HOLD_S03_FAILURE_INPUT")
        print("R82: 24 typed failure cases; original equality gaps reproduced; all outcomes HOLD")
if __name__=="__main__":
    unittest.main(verbosity=2)
