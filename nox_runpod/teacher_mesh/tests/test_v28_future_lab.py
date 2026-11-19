#!/usr/bin/env python3
"""V28 Future NOX real-source contract tests; no GPU, remote model or fake inference."""
import hashlib,json,sys,unittest
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from nox_neural_matchmaker_v28 import match_advisors
from nox_curriculum_dna_v28 import build_curriculum,promotion_gate
from nox_adviser_arena_v28 import evaluate_teacher_arena
from nox_speed_lab_v28 import propose_speed_trials

NOW=datetime(2026,11,12,18,0,tzinfo=timezone.utc)
STUDENT="a"*64;CANDIDATE="b"*64;HARNESS="c"*64;SPLIT="d"*64;RECEIPT="e"*64
def teacher(ident="qwen-teacher",family="qwen",gain=.12):
    return {"id":ident,"role":"FROZEN_TEACHER_ONLY","local_isolated_vm":True,
            "owner_approved":True,"license_verified":True,
            "weights_sha256":"f"*64,"revision":"a"*40,
            "required_vram_mb":5000,"p95_ms":2500,"family":family,
            "verified_benchmarks":{"code":{
               "verified":True,"same_harness":True,"heldout":True,
               "contamination_review":"PASS","harness_sha256":HARNESS,
               "student_model_sha256":STUDENT,"total":100,
               "student_score":.4,"teacher_score":.4+gain}}}
def matchpolicy():
    return {"signed_by_native_owner":True,"scope":"owner",
            "allow_teacher_comparison":True,"max_advisors":2,
            "allowed_model_ids":["qwen-teacher","mistral-teacher"],
            "accepted_harness_shas":[HARNESS],
            "available_teacher_vram_mb":16000}
def task():
    return {"kind":"code","scope":"owner","chat_busy":False,
            "stop_requested":False,"user_data_private":False,
            "active_student_sha256":STUDENT}
def bench(domain,model=STUDENT,correct=54,total=100):
    return {"domain":domain,"model_sha256":model,"correct":correct,"total":total,
            "harness_sha256":HARNESS,"dataset_split_sha256":SPLIT,
            "source_receipt_sha256":RECEIPT,"independent_replay":True,
            "heldout":True,"source_separated":True,"contamination_review":"PASS",
            "observed_at_utc":NOW.isoformat()}
def curriculum_policy():
    return {"signed_by_native_owner":True,"active_student_sha256":STUDENT,
            "stop_requested":False,"max_proposals":3}
def advice(ident="teacher1",text="Independent tested solution with evidence",score=.9):
    return {"teacher_id":ident,"origin":"isolated_frozen_teacher","text":text,
            "text_sha256":hashlib.sha256(text.encode()).hexdigest(),
            "source_uri":"https://example.org/sources/"+ident,
            "training_data_rights_verified":True,"deidentified":True,
            "owner_sample_approved":True,
            "independent_grade":{"verified":True,"harness_sha256":HARNESS,
                "source_receipt_sha256":RECEIPT,"quality_score":score}}
def arena_policy():
    return {"signed_by_native_owner":True,"stop_requested":False,
            "allowed_teacher_ids":["teacher1","teacher2"],"max_evidence_capsules":2,
            "user_data_private":False}
def speed_signals():
    return {"measured":True,"sensor_valid":True,"machine_signature_verified":True,
            "source_model_sha256_verified":True,
            "p95_ttft_ms":2400,"p95_intertoken_ms":115,
            "prompt_tokens_p95":5000,"vram_utilization_pct":89,
            "repeated_prefix_rate":.55,"free_vram_mb":8000,"draft_required_mb":2000,
            "draft_model_sha_verified":True,"draft_tokenizer_compatible":True,
            "training_job_active":True,"chat_busy":False,
            "train_length_variance":.6,"gpu_compute_idle_fraction":.22,
            "kernel_architecture_verified":True,
            "backend_capabilities":{"prefix_cache":True,"chunked_prefill":True,
              "speculative":True,"kv_quant":True,"length_pack":True,
              "fused_kernel_installed":True,"async_prefetch":True}}

class MatchmakerTests(unittest.TestCase):
    def test_eligible_measured_adviser_only_and_no_model_switch(self):
        p=matchpolicy();r=match_advisors(task(),[teacher(),teacher("mistral-teacher","mistral",.13)],p,now=NOW)
        self.assertEqual(r["status"],"ADVISOR_PROPOSAL_NOT_EXECUTED")
        self.assertEqual(len(r["advisors"]),2)
        self.assertEqual(r["user_visible_model"],"CURRENT_NOX_STUDENT_ONLY")
        self.assertFalse(r["prompt_sent"])
    def test_unmeasured_teacher_rejected(self):
        m=teacher();m["verified_benchmarks"]["code"]["verified"]=False
        self.assertEqual(match_advisors(task(),[m],matchpolicy())["status"],"NO_PROVEN_ADVISOR_GAIN")
    def test_false_student_sha_cannot_make_measured_gain(self):
        m=teacher();m["verified_benchmarks"]["code"]["student_model_sha256"]="0"*64
        self.assertEqual(match_advisors(task(),[m],matchpolicy())["advisors"],[])
    def test_unapproved_harness_cannot_choose_teacher(self):
        p=matchpolicy();p["accepted_harness_shas"]=["1"*64]
        self.assertEqual(match_advisors(task(),[teacher()],p)["advisors"],[])
    def test_private_scope_or_busy_blocks(self):
        p=matchpolicy();t=task();t["user_data_private"]=True
        self.assertEqual(match_advisors(t,[teacher()],p)["status"],"HOLD_PRIVATE_COMPARISON")
        t=task();t["chat_busy"]=True
        self.assertEqual(match_advisors(t,[teacher()],p)["status"],"DEFER_CHAT_OR_STOP")
    def test_equal_family_no_duplicate_independent_adviser(self):
        p=matchpolicy();r=match_advisors(task(),[teacher(),teacher("mistral-teacher","qwen",.14)],p)
        self.assertEqual(len(r["advisors"]),1)
    def test_no_masked_teacher_if_gain_too_small(self):
        self.assertEqual(match_advisors(task(),[teacher(gain=.001)],matchpolicy())["advisors"],[])

class CurriculumTests(unittest.TestCase):
    def test_verified_gap_prioritization(self):
        records=[bench("instruction",correct=54),bench("coding",correct=84),
                 bench("long_memory",correct=34)]
        r=build_curriculum(records,curriculum_policy(),now=NOW)
        self.assertEqual(r["state"],"CURRICULUM_PROPOSED_NOT_TRAINED")
        self.assertEqual(r["proposals"][0]["domain"],"long_memory")
        self.assertEqual(r["proposals"][0]["stage"],"MEMORY_OR_EVIDENCE_ENGINEERING_FIRST")
        self.assertFalse(r["gpu_job_started"])
    def test_no_fake_l03_report_replay(self):
        r=bench("instruction");r["independent_replay"]=False
        self.assertEqual(build_curriculum([r],curriculum_policy(),now=NOW)["proposals"],[])
    def test_training_denied_on_source_split_tamper(self):
        r=bench("coding");r["source_separated"]=False
        self.assertEqual(build_curriculum([r],curriculum_policy(),now=NOW)["proposals"],[])
    def test_owner_native_stop_blocks_curriculum(self):
        p=curriculum_policy();p["stop_requested"]=True
        self.assertEqual(build_curriculum([bench("instruction")],p,now=NOW)["state"],"HOLD_NATIVE_STOP")
    def test_promotion_blocks_regression(self):
        p={"signed_by_native_owner":True,"baseline_sha256":STUDENT,
           "candidate_sha256":CANDIDATE,
           "required_domains":["instruction","coding"],
           "checkpoint_reloaded_and_sha_verified":True,
           "real_optimizer_receipt_verified":True}
        b=[bench("instruction",correct=50),bench("coding",correct=90)]
        c=[bench("instruction",model=CANDIDATE,correct=70),
           bench("coding",model=CANDIDATE,correct=85)]
        self.assertEqual(promotion_gate(baseline=b,candidate=c,policy=p,now=NOW)["state"],
                         "REJECT_MEASURED_REGRESSION")
    def test_promotion_only_for_owner_review(self):
        p={"signed_by_native_owner":True,"baseline_sha256":STUDENT,
           "candidate_sha256":CANDIDATE,"required_domains":["instruction","coding"],
           "checkpoint_reloaded_and_sha_verified":True,"real_optimizer_receipt_verified":True}
        b=[bench("instruction",correct=50),bench("coding",correct=80)]
        c=[bench("instruction",model=CANDIDATE,correct=60),bench("coding",model=CANDIDATE,correct=85)]
        r=promotion_gate(baseline=b,candidate=c,policy=p,now=NOW)
        self.assertEqual(r["state"],"READY_FOR_OWNER_REVIEW_NOT_PROMOTED")
        self.assertFalse(r["production_modified"])
    def test_same_harness_required(self):
        p={"signed_by_native_owner":True,"baseline_sha256":STUDENT,
           "candidate_sha256":CANDIDATE,"required_domains":["instruction"]}
        c=bench("instruction",model=CANDIDATE,correct=90);c["harness_sha256"]="1"*64
        self.assertEqual(promotion_gate(baseline=[bench("instruction",correct=50)],
              candidate=[c],policy=p,now=NOW)["state"],"HOLD_DIFFERENT_HARNESS_SPLIT_OR_SAMPLE_COUNT")

class ArenaTests(unittest.TestCase):
    def test_teacher_text_is_evidence_not_nox_answer(self):
        p=arena_policy();r=evaluate_teacher_arena([advice(),advice("teacher2","Different independent answer",.8)],p)
        self.assertEqual(r["state"],"EVIDENCE_READY_FOR_NOX_SYNTHESIS")
        self.assertEqual(r["user_visible_model"],"CURRENT_NOX_STUDENT_ONLY")
        self.assertTrue(r["no_teacher_text_can_overwrite_s03"])
        self.assertFalse(r["training_started"])
        self.assertEqual(r["training_candidate_count"],2)
    def test_ungraded_teacher_is_rejected(self):
        a=advice();a["independent_grade"]["verified"]=False
        self.assertEqual(evaluate_teacher_arena([a],arena_policy())["evidence_capsules"],[])
    def test_fake_hash_is_not_authoritative(self):
        a=advice();a["text_sha256"]="0"*64
        self.assertEqual(evaluate_teacher_arena([a],arena_policy())["evidence_capsules"],[])
    def test_private_policy_stop_block(self):
        p=arena_policy();p["user_data_private"]=True
        self.assertEqual(evaluate_teacher_arena([advice()],p)["state"],"HOLD_PRIVACY")
        p=arena_policy();p["stop_requested"]=True
        self.assertEqual(evaluate_teacher_arena([advice()],p)["state"],"HOLD_STOP")
    def test_duplicate_candidate_remains_one(self):
        a=advice()
        self.assertEqual(len(evaluate_teacher_arena([a,a],arena_policy())["evidence_capsules"]),1)
    def test_training_rights_never_assumed(self):
        a=advice();a["training_data_rights_verified"]=False
        self.assertEqual(evaluate_teacher_arena([a],arena_policy())["training_candidate_count"],0)

class SpeedTests(unittest.TestCase):
    def test_no_live_source_is_hold(self):
        self.assertEqual(propose_speed_trials({},{"signed_by_native_owner":True,"stop_requested":False})["state"],"HOLD_NO_LIVE_PROFILE")
    def test_no_fake_speedup_claim(self):
        r=propose_speed_trials(speed_signals(),{"signed_by_native_owner":True,"stop_requested":False})
        self.assertEqual(r["state"],"TRIALS_RECOMMENDED_NOT_APPLIED")
        self.assertTrue(r["no_claimed_speedup_without_same_workload_ab"])
        self.assertFalse(r["production_mutations"])
        self.assertTrue(all(x["auto_apply"] is False for x in r["experiments"]))
        self.assertEqual(r["max_concurrent_ab_trials"],1)
    def test_stop_blocks_speed_lab(self):
        self.assertEqual(propose_speed_trials(speed_signals(),{"signed_by_native_owner":True,"stop_requested":True})["state"],"HOLD_STOP")
    def test_low_signal_has_no_proposed_improvement(self):
        s=speed_signals();s["repeated_prefix_rate"]=0;s["p95_ttft_ms"]=50;s["p95_intertoken_ms"]=15
        s["vram_utilization_pct"]=25;s["train_length_variance"]=0
        s["gpu_compute_idle_fraction"]=0;s["backend_capabilities"]["fused_kernel_installed"]=False
        self.assertEqual(propose_speed_trials(s,{"signed_by_native_owner":True,"stop_requested":False})["state"],"NO_MEASURED_SPEED_OPPORTUNITY")
    def test_source_hardware_holds(self):
        s=speed_signals();s["sensor_valid"]=False
        self.assertEqual(propose_speed_trials(s,{"signed_by_native_owner":True,"stop_requested":False})["state"],"HOLD_HARDWARE_SOURCE_PROOF")

class CatalogTests(unittest.TestCase):
    def test_100_plus_50_new_ideas(self):
        base=Path(__file__).resolve().parent.parent
        a=json.loads((base/"NOX_WOW50_V28_EVAL_AND_ARCHITECTURE.json").read_text())
        b=json.loads((base/"NOX_FUTURE_OWN_WOW50_V28.json").read_text())
        self.assertEqual(len(a["cognitive_wow50"]),50)
        self.assertEqual(len(a["architecture_50"]),50)
        self.assertEqual(len(b["items"]),50)
        self.assertEqual(len(set(x["name"] for x in b["items"])),50)
        self.assertTrue(all(x["verified_gain"] is None for x in b["items"]))
    def test_24_future_templates_are_source_blueprints(self):
        base=Path(__file__).resolve().parent.parent
        a=json.loads((base/"NOX_V28_FUTURE_SKILL_MODEL_TEMPLATES.json").read_text())
        self.assertEqual(len(a["templates"]),24)
        self.assertEqual(len(a["model_cards"]),7)
        self.assertTrue(a["not_installed"])
        self.assertTrue(all(x["status"]=="BLUEPRINT_SOURCE_ONLY_NOT_LIVE_BOUND" for x in a["templates"]))
if __name__=="__main__":
    unittest.main()
