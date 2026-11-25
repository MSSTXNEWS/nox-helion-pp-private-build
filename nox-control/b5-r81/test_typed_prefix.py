"""Regression using real retained descriptor ingress, not a mocked verifier."""
import contextlib
import json
import tempfile
import unittest
from b5_retained_ingress import load_retained_chain
from typed_prefix import load_typed_chain
from test_b5_chain_guard import checkpoint, DIALOG, SESSION, raw, sha

class TypedPrefixTest(unittest.TestCase):
    def test_original_equality_gap_and_type_exact_fence(self):
        for values, valid in [((True,True,True),True), ((True,1,1),False),
                              ((1,1,1.0),False), ((0.0,-0.0,-0.0),False)]:
            with self.subTest(values=values), contextlib.ExitStack() as stack:
                artifacts=[]
                for n, value in enumerate(values, 1):
                    rows,(w,r,ws,rs)=checkpoint(n)
                    rows[0]["metadata"]={"retained_flag":value}
                    doc=json.loads(r); doc["messages"]=rows
                    r=raw(doc)
                    fds=[]
                    for b in (w,r):
                        f=stack.enter_context(tempfile.TemporaryFile())
                        f.write(b); f.flush(); fds.append(f.fileno())
                    artifacts.append((*fds,ws,sha(r)))
                args=dict(dialog_id=DIALOG,session_id=SESSION,artifacts=tuple(artifacts))
                # Old chain accepts Python-equal but JSON-distinct metadata.
                self.assertEqual(len(load_retained_chain(**args)),3)
                if valid:
                    self.assertEqual(len(load_typed_chain(**args)),3)
                else:
                    with self.assertRaisesRegex(ValueError,"HOLD_S03_TYPED_PREFIX_CHANGED"):
                        load_typed_chain(**args)
        print("Typed prefix: exact RU/ES retained chain accepted; 3 original equality gaps reproduced and rejected")

if __name__=="__main__":
    unittest.main(verbosity=2)
