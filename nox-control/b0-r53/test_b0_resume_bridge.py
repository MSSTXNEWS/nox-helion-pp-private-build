import hashlib
import json
import unittest
from b0_resume_bridge import bind_existing_resume, owner_prefix_sha
from b5_r55_pinned import digest, multiturn_transcript_sha256

DIALOG = "a" * 32
SESSION = "fixture-owner"
def wire(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()

def rows(n):
    pairs = [("Привет", "¡Hola! 🪐"), ("¿Recuerdas?", "Помню."),
             ("¿Y después?", "Sí, recuerdo.")]
    return [dict(role=role, content=text, message_id=f"row-{i}",
                 dialog_id=DIALOG, session_id=SESSION)
            for i, (role,text) in enumerate(
                [(role,text) for pair in pairs[:n] for role,text in
                 zip(("user","assistant"),pair)], 1)]
def witnesses(items):
    seq = len(items)//2
    common = dict(source="canonical_s03", event_id=f"evt-{seq}",
                  turn_id=f"turn-{seq}", sequence=seq, dialog_id=DIALOG,
                  session_id=SESSION,
                  full_transcript_sha256=multiturn_transcript_sha256(
                      items, expected_sequence=seq, _prefix_only=seq == 1),
                  message_ids_sha256=digest(wire([r["message_id"] for r in items])))
    w = wire(dict(common, verified=True, durable=True))
    r = wire(dict(common, independent=True, messages=items,
                  full_answer_sha256=digest(items[-1]["content"].encode())))
    return w,r,digest(w),digest(r)

def fixture(n):
    old = rows(n)
    owner = [dict(r, owner_metadata="unchanged") for r in old]
    pin = owner_prefix_sha(DIALOG,owner)
    preflight = dict(scope="EXISTING_OWNER_DIALOG_PREFIX_ONLY_NOT_INDEPENDENT_S03",
                     prefix_rows=len(owner), prefix_sha256=pin,
                     dialog_id_sha256=hashlib.sha256(DIALOG.encode()).hexdigest(),
                     prefix_pin_matched=True, model_post_issued=False,
                     dialog_created=False, browser_multiturn_accepted=False,
                     native_s03_independently_verified=False, production_accepted=False)
    return dict(preflight=preflight, expected_owner_sha=pin, dialog_id=DIALOG,
                session_id=SESSION, owner_rows=owner, canonical_rows=old,
                prior_witnesses=witnesses(old), browser_calls=7, admitted_calls=7)
class B0ResumeBridgeTests(unittest.TestCase):
    def test_existing_second_and_third_turns(self):
        for n in (1,2):
            with self.subTest(n=n):
                f=fixture(n)
                self.assertNotEqual(f["expected_owner_sha"],
                    multiturn_transcript_sha256(f["canonical_rows"],expected_sequence=n,
                                               _prefix_only=n==1))
                bridge=bind_existing_resume(**f)
                new=rows(n+1)
                args=dict(browser_rows=new,canonical_rows=new,witnesses=witnesses(new),
                          browser_calls=8,admitted_calls=8,prompt=new[-2]["content"],
                          stream_answer=new[-1]["content"],terminal_saved=True,dom_matches=True)
                self.assertEqual(bridge.finish(**args),"RESUME_EVIDENCE_MATCHED")
                self.assertEqual(bridge.finish(**args),"HOLD_RESUME_ALREADY_CONSUMED")
    def test_owner_metadata_drift(self):
        f=fixture(1)
        f["owner_rows"][0]["owner_metadata"]="changed"
        with self.assertRaisesRegex(ValueError,"HOLD_B0_RESUME_OWNER_PIN"):
            bind_existing_resume(**f)
    def test_wrong_pin_and_false_claims(self):
        for k,v in (("prefix_rows",True),("production_accepted",True),
                    ("model_post_issued",True),("native_s03_independently_verified",True),
                    ("prefix_sha256","0"*64),("dialog_id_sha256","0"*64)):
            f=fixture(1)
            f["preflight"][k]=v
            with self.subTest(k=k),self.assertRaisesRegex(ValueError,"HOLD_B0_RESUME_PREFLIGHT"):
                bind_existing_resume(**f)
    def test_independent_s03_mismatch(self):
        f=fixture(1)
        f["prior_witnesses"]=witnesses(rows(2))
        with self.assertRaisesRegex(ValueError,"HOLD_RESUME_PREFIX"):
            bind_existing_resume(**f)
    def test_distinct_owner_and_canonical_rows(self):
        f=fixture(1)
        f["canonical_rows"][1]["message_id"]="other"
        f["prior_witnesses"]=witnesses(f["canonical_rows"])
        with self.assertRaisesRegex(ValueError,"HOLD_RESUME_BROWSER_PREFIX"):
            bind_existing_resume(**f)
    def test_counter_mismatch(self):
        f=fixture(1)
        f["admitted_calls"]=6
        with self.assertRaisesRegex(ValueError,"HOLD_RESUME_PREFIX"):
            bind_existing_resume(**f)
