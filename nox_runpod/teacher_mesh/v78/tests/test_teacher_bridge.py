import unittest
from nox_runpod.teacher_mesh.v78.internet_teacher_bridge import (
    TeacherPorts, discover_candidate, consult_teacher, discovery_via_existing_native_port
)

class TeacherBridgeTests(unittest.TestCase):
    def setUp(self):
        self.records = []
        self.ports = TeacherPorts(
            discover_metadata=lambda mid: {"id":mid,"sha":"a"*40,"license":"apache-2.0","gated":False},
            consent_for_external_prompt=lambda scope, model: True,
            safe_to_use_teacher=lambda model: True,
            native_teacher_infer=lambda model, q: {"answer":"Verified example"},
            independently_check=lambda q,a,m: {"verified":True,"score":0.95,"source_uri":"https://example.org/evidence"},
            s03_write=lambda entry: self.persist(entry),
            s03_verify=lambda receipt,entry: entry in self.records and receipt.get("id")=="receipt-1",
            approved_lesson=lambda question,answer,evidence: {"text":"Verified public fact","source_uri":evidence["source_uri"],
                      "privacy_approved":True,"rights_verified":True,"independent_review":True}
        )
    def persist(self, entry):
        self.records.append(entry)
        return {"id":"receipt-1"}
    def test_metadata_pinned(self):
        self.assertEqual(discovery_via_existing_native_port("org/model",self.ports.discover_metadata)["state"],
                         "CANDIDATE_REVIEWED_NOT_INSTALLED")
    def test_unpinned_fails(self):
        self.assertEqual(discover_candidate("org/model",metadata={"id":"org/model","sha":"main","license":"apache-2.0","gated":False})["state"],
                         "HOLD_UNPINNED_REVISION")
    def test_unknown_license_fails(self):
        self.assertEqual(discover_candidate("org/model",metadata={"id":"org/model","sha":"a"*40,"license":"unknown","gated":False})["state"],
                         "HOLD_LICENSE_OR_GATED")
    def test_remote_code_fails(self):
        self.assertEqual(discover_candidate("org/model",metadata={"id":"org/model","sha":"a"*40,"license":"mit","gated":False,"trust_remote_code":True})["state"],
                         "HOLD_REMOTE_CODE")
    def test_private_s03_not_exported(self):
        self.assertEqual(consult_teacher(model_id="org/model",question="secret",conversation_scope="owner1",
                         ports=self.ports,owner_approved=True,prompt_contains_private_s03=True)["state"],
                         "HOLD_PRIVACY_OR_OWNER_APPROVAL")
        self.assertFalse(self.records)
    def test_consent_required(self):
        self.assertEqual(consult_teacher(model_id="org/model",question="hi",conversation_scope="owner1",
                         ports=self.ports)["state"],"HOLD_PRIVACY_OR_OWNER_APPROVAL")
    def test_verified_s03_not_weights(self):
        r=consult_teacher(model_id="org/model",question="hi",conversation_scope="owner1",ports=self.ports,owner_approved=True)
        self.assertEqual(r["state"],"TEACHER_HELP_AND_S03_VERIFIED")
        self.assertIs(r["neural_weights_changed"],False)
        self.assertEqual(len(self.records),1)
        self.assertEqual(self.records[0]["verified_lesson_text"], "Verified public fact")
        self.assertNotIn("hi", str(self.records[0]))
    def test_no_false_learning_without_s03_receipt(self):
        p=self.ports
        p=TeacherPorts(p.discover_metadata,p.consent_for_external_prompt,p.safe_to_use_teacher,p.native_teacher_infer,
                       p.independently_check,p.s03_write,lambda r,e:False,p.approved_lesson)
        r=consult_teacher(model_id="org/model",question="hi",conversation_scope="owner1",ports=p,owner_approved=True)
        self.assertEqual(r["state"],"HOLD_S03_NOT_DURABLE")

    def test_no_memory_without_lesson_review(self):
        p=self.ports
        p=TeacherPorts(p.discover_metadata,p.consent_for_external_prompt,p.safe_to_use_teacher,p.native_teacher_infer,
                       p.independently_check,p.s03_write,p.s03_verify,None)
        r=consult_teacher(model_id="org/model",question="hi",conversation_scope="owner1",ports=p,owner_approved=True)
        self.assertEqual(r["state"],"HOLD_NATIVE_LESSON_REVIEW_MISSING")
        self.assertFalse(self.records)
    def test_refuse_unreviewed_lesson(self):
        p=self.ports
        p=TeacherPorts(p.discover_metadata,p.consent_for_external_prompt,p.safe_to_use_teacher,p.native_teacher_infer,
                       p.independently_check,p.s03_write,p.s03_verify,
                       lambda q,a,e: {"text":"unverified","source_uri":e["source_uri"],"privacy_approved":True,
                                       "rights_verified":True,"independent_review":False})
        r=consult_teacher(model_id="org/model",question="hi",conversation_scope="owner1",ports=p,owner_approved=True)
        self.assertEqual(r["state"],"HOLD_LESSON_SOURCE_OR_REVIEW")
        self.assertFalse(self.records)

if __name__=="__main__":unittest.main()
