#!/usr/bin/env python3
"""NOX V30 source-only safety and source admission regression tests."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from v30_student_weight_abi_gate import admit_teacher,admit_student_update

BASE={"weights_sha256":"a"*64,"tokenizer_sha256":"b"*64,"architecture_sha256":"c"*64}
CANDIDATE={"weights_sha256":"d"*64,"base_model_sha256":"a"*64,
           "tokenizer_sha256":"b"*64,"architecture_sha256":"c"*64,
           "optimizer_receipt_sha256":"e"*64,"dataset_sha256":"f"*64,
           "checkpoint_sha256":"0"*64,"optimizer_steps":1,
           "checkpoint_readback_verified":True,"optimizer_state_readback_verified":True,
           "rng_state_readback_verified":True,"safe70_verified":True,
           "production_mutated":False}
EVALS={"same_harness_sha":"1"*64,"independent_heldout":True,
       "source_disjoint":True,"anti_forgetting_passed":True,"stop_and_s03_regression_passed":True}
POLICY={"signed_by_native_owner":True,"stop_active":False,
        "allowed_teacher_ids":["Qwen/Qwen3-8B"],"max_source_bytes":5000000}
TEACHER={"model_id":"Qwen/Qwen3-8B","revision":"1"*40,
         "weights_sha256":"3"*64,"license_review":"APPROVED",
         "training_rights":True,"model_family":"qwen","source":"trusted_model_registry",
         "frozen_in_isolated_vm":True,"sends_private_s03_to_teacher":False,"max_bytes":3000000}
class AdmissionTests(unittest.TestCase):
    def test_frozen_teacher_is_data_only(self):
        data=admit_teacher({"active_model_sha256":"a"*64},TEACHER,POLICY)
        self.assertEqual(data["state"],"FROZEN_TEACHER_CANDIDATE_ONLY")
        self.assertFalse(data["trainer_launch_allowed"])
    def test_unauthorized_teacher_is_hold(self):
        t=dict(TEACHER,model_id="External/Untrusted")
        self.assertEqual(admit_teacher({"active_model_sha256":"a"*64},t,POLICY)["state"],"HOLD")
    def test_external_private_memory_never_transmitted(self):
        t=dict(TEACHER,sends_private_s03_to_teacher=True)
        self.assertEqual(admit_teacher({"active_model_sha256":"a"*64},t,POLICY)["reason"],"PRIVATE_S03_EXFILTRATION_HOLD")
    def test_no_license_no_teacher(self):
        t=dict(TEACHER,license_review="REVIEW_REQUIRED")
        self.assertEqual(admit_teacher({"active_model_sha256":"a"*64},t,POLICY)["state"],"HOLD")
    def test_stop_blocks(self):
        p=dict(POLICY,stop_active=True)
        self.assertEqual(admit_teacher({"active_model_sha256":"a"*64},TEACHER,p)["state"],"HOLD")
    def test_student_review_never_promotes(self):
        result=admit_student_update(BASE,CANDIDATE,EVALS,POLICY)
        self.assertEqual(result["state"],"STUDENT_CHANGE_EVIDENCE_REVIEW_CANDIDATE_NOT_PROMOTED")
        self.assertFalse(result["active_nox_switched"])
        self.assertFalse(result["student_weights_changed"])
    def test_mismatched_architecture_hold(self):
        bad=dict(CANDIDATE,architecture_sha256="f"*64)
        self.assertEqual(admit_student_update(BASE,bad,EVALS,POLICY)["reason"],"MODEL_ABI_OR_BASE_SHA_MISMATCH")
    def test_no_change_in_weights_hold(self):
        bad=dict(CANDIDATE,weights_sha256=BASE["weights_sha256"])
        self.assertEqual(admit_student_update(BASE,bad,EVALS,POLICY)["reason"],"NO_STUDENT_WEIGHT_CHANGE")
    def test_no_real_optimizer_hold(self):
        bad=dict(CANDIDATE,optimizer_steps=0)
        self.assertEqual(admit_student_update(BASE,bad,EVALS,POLICY)["reason"],"OPTIMIZER_CHECKPOINT_SAFE70_EVIDENCE_HOLD")
    def test_no_rng_checkpoint_hold(self):
        bad=dict(CANDIDATE,rng_state_readback_verified=False)
        self.assertEqual(admit_student_update(BASE,bad,EVALS,POLICY)["state"],"HOLD")
    def test_no_anti_forget_hold(self):
        ev=dict(EVALS,anti_forgetting_passed=False)
        self.assertEqual(admit_student_update(BASE,CANDIDATE,ev,POLICY)["state"],"HOLD")
    def test_stopped_student_hold(self):
        p=dict(POLICY,stop_active=True)
        self.assertEqual(admit_student_update(BASE,CANDIDATE,EVALS,p)["state"],"HOLD")
if __name__=="__main__":unittest.main()
