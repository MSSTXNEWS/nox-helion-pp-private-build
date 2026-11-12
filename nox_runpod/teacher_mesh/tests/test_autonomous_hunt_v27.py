#!/usr/bin/env python3
"""NOX HUNT V27 tests: fake native callbacks, NO network, GPU or daemon."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from autonomous_hunt_v27 import HuntDirector, NativeCallbacks, WORM_KINDS, LANES

NOW=datetime(2026,11,12,19,0,tzinfo=timezone.utc)
HEAD="c"*40
STUDENT="a"*64
CANDIDATE={
    "type":"frozen_teacher","model_id":"Qwen/Qwen3-8B","revision":"d"*40,
    "source_origin":"trusted_model_registry","license_id":"Apache-2.0",
    "license_verified_by_owner":True,"training_rights_verified":True,
    "max_bytes":1_000_000_000,
}
TRAIN={
    "mode":"student_sft","training_rights_verified":True,
    "holdout_independent":True,"dataset_reviewed":True,
    "student_sha256":STUDENT,"dataset_sha256":"d"*64,
    "optimizer_steps_budget":20,
}
IDEA={
    "worm_kind":"github_code","topic":"Investigate verified reasoning benchmark gaps",
    "lane":"reasoning","source_uri":"s03://skills/reasoning-gap",
}
def state():
    return {"origin":"existing_onehost","scope":"owner",
            "last_verified_learning_utc":(NOW-timedelta(days=2)).isoformat(),
            "verified_gap_score":0.91,"chat_busy":False,
            "trainer_running":False,"active_student_sha256":STUDENT,
            "gpu":{"telemetry_verified":True,"gpu_owner":"NOX",
                   "local_windows_gpu":True,"hotspot_valid":True,
                   "power_sensor_valid":True,"safe70_active":True,
                   "samples_hotspot_ge70":0,
                   "free_disk_gb":80,"free_vram_mb":8000,"chat_gpu_busy":False}}

class NativeHarness:
    def __init__(self):
        self.stop=False
        self.policy={"signed_by_native_owner":True,"scope":"owner",
                     "allow_autonomous_research":True,
                     "allow_autonomous_model_download":True,
                     "allow_autonomous_gpu_training":True,
                     "source_head":HEAD,
                     "expires_utc":(NOW+timedelta(days=1)).isoformat(),
                     "allowed_model_ids":["Qwen/Qwen3-8B"],
                     "max_model_bytes":2_000_000_000,
                     "max_optimizer_steps_per_job":30,
                     "min_free_disk_gb":25,"min_free_vram_mb":2048}
        self.current_state=state()
        self.models=[dict(CANDIDATE)]
        self.trains=[dict(TRAIN)]
        self.created=[]
        self.downloads=[]
        self.training_jobs=[]
        self.claims=set()
        self.worm_ticks=0
    def claim(self,scope,action,key):
        assert scope=="owner"
        joined=(action,key)
        if joined in self.claims:return False
        self.claims.add(joined)
        return True
    def callbacks(self):
        return NativeCallbacks(
            signed_policy=lambda scope:self.policy,
            native_stop=lambda:self.stop,
            source_head=lambda:HEAD,
            owner_state=lambda scope:self.current_state,
            quota_claim=self.claim,
            enqueue_existing=lambda scope,task:(self.created.append(task) or True),
            existing_worm_tick=lambda scope:self._tick_worm(),
            propose_nox_idea=lambda scope,ctx:dict(IDEA),
            model_candidate=lambda scope:self.models[0] if self.models else None,
            stage_model_existing=lambda scope,task:(self.downloads.append(task) or
                    {"sha256_verified":True,"sha256":"f"*64,"bytes":800_000_000}),
            train_candidate=lambda scope:self.trains[0] if self.trains else None,
            launch_existing_trainer=lambda scope,task:(self.training_jobs.append(task) or
                    {"accepted_by_existing_trainer":True,"job_id":"trainer_0001"}),
        )
    def _tick_worm(self):
        self.worm_ticks+=1
        return {"status":"READY_FOR_NATIVE_APPROVED_TICK"}

class TestAutonomy(unittest.TestCase):
    def test_exact_existing_20_worms_and_6_lanes(self):
        self.assertEqual(len(WORM_KINDS),20)
        self.assertEqual(len(set(WORM_KINDS)),20)
        self.assertEqual(len(LANES),6)
    def test_no_policy_is_no_action(self):
        h=NativeHarness();h.policy["signed_by_native_owner"]=False
        d=HuntDirector(h.callbacks())
        r=d.tick("owner",now=NOW)
        self.assertEqual(r["state"],"HOLD")
        self.assertFalse(h.downloads or h.training_jobs or h.created)
    def test_native_stop_no_side_effects(self):
        h=NativeHarness();h.stop=True
        r=HuntDirector(h.callbacks()).tick("owner",now=NOW)
        self.assertEqual(r["reason"],"NATIVE_STOP_UNAVAILABLE_OR_ACTIVE")
        self.assertEqual(h.worm_ticks,0)
    def test_real_source_ownership_and_stale_policy_required(self):
        h=NativeHarness();h.policy["source_head"]="f"*40
        self.assertEqual(HuntDirector(h.callbacks()).tick("owner",now=NOW)["state"],"HOLD")
        h.policy["source_head"]=HEAD;h.policy["expires_utc"]=(NOW-timedelta(seconds=1)).isoformat()
        self.assertEqual(HuntDirector(h.callbacks()).tick("owner",now=NOW)["reason"],"POLICY_EXPIRED")
    def test_can_self_create_approved_data_worm_and_request_existing_trainer(self):
        h=NativeHarness()
        r=HuntDirector(h.callbacks()).tick("owner",now=NOW)
        self.assertEqual(r["worm_created"],"EXISTING_QUEUE_ACCEPTED_DATA_ONLY")
        self.assertEqual(r["model_download"],"VERIFIED_STAGING_ONLY")
        self.assertEqual(r["gpu_train"],"EXISTING_TRAINER_JOB_ACCEPTED_NOT_OPTIMIZER_VERIFIED")
        self.assertEqual(r["training_weight_updates_verified"],0)
        self.assertFalse(r["worms_are_os_processes"])
        self.assertEqual(h.created[0]["type"],"existing_worm_research")
        self.assertTrue(h.downloads[0]["staging_only"])
        self.assertTrue(h.training_jobs[0]["no_auto_promotion"])
        self.assertTrue(h.training_jobs[0]["fail_closed_stop"])
    def test_no_duplicate_daily_jobs_in_host_quota(self):
        h=NativeHarness();d=HuntDirector(h.callbacks())
        d.tick("owner",now=NOW)
        d.tick("owner",now=NOW)
        self.assertEqual(len(h.downloads),1)
        self.assertEqual(len(h.training_jobs),1)
        self.assertEqual(len(h.created),1)
    def test_chat_has_priority(self):
        h=NativeHarness();h.current_state["chat_busy"]=True
        r=HuntDirector(h.callbacks()).tick("owner",now=NOW)
        self.assertEqual(r["state"],"CHAT_PRIORITY_IDLE_DEFER")
        self.assertEqual(h.worm_ticks,0)
        self.assertEqual(len(h.downloads),0)
    def test_invalid_local_gpu_sensor_holds_training(self):
        h=NativeHarness();h.current_state["gpu"]["hotspot_valid"]=False
        r=HuntDirector(h.callbacks()).tick("owner",now=NOW)
        self.assertEqual(r["gpu"],"HOLD_SAFE70_SENSOR_OR_THERMAL")
        self.assertEqual(h.training_jobs,[])
    def test_three_hot_readings_holds(self):
        h=NativeHarness();h.current_state["gpu"]["samples_hotspot_ge70"]=3
        r=HuntDirector(h.callbacks()).tick("owner",now=NOW)
        self.assertEqual(r["gpu"],"HOLD_SAFE70_SENSOR_OR_THERMAL")
        self.assertEqual(h.downloads,[])
    def test_no_unlicensed_model_download(self):
        h=NativeHarness();h.models[0]["training_rights_verified"]=False
        r=HuntDirector(h.callbacks()).tick("owner",now=NOW)
        self.assertNotIn("model_download",r)
        self.assertEqual(h.downloads,[])
    def test_missing_independent_holdout_no_training(self):
        h=NativeHarness();h.trains[0]["holdout_independent"]=False
        r=HuntDirector(h.callbacks()).tick("owner",now=NOW)
        self.assertNotIn("gpu_train",r)
        self.assertEqual(h.training_jobs,[])
    def test_chat_memory_source_evidence_is_not_permission(self):
        h=NativeHarness()
        h.callbacks().model_candidate("owner")["source_origin"]="untrusted_model"
        self.assertEqual(h.downloads,[])
        r=HuntDirector(h.callbacks()).tick("owner",now=NOW)
        self.assertNotIn("model_download",r)
    def test_hunger_is_a_gap_metric_not_literal_emotion(self):
        r=HuntDirector.hunger((NOW-timedelta(hours=30)).isoformat(),now=NOW,gap_score=0.75)
        self.assertEqual(r["level"],"VERY_HUNGRY")
        self.assertFalse(r["literal_emotion"])
        self.assertGreater(r["score"],0.5)
    def test_no_training_claim_from_queue_ack(self):
        h=NativeHarness()
        r=HuntDirector(h.callbacks()).tick("owner",now=NOW)
        self.assertNotIn("TRAINED",r.get("state",""))
        self.assertEqual(r["training_weight_updates_verified"],0)
        self.assertEqual(len(h.training_jobs),1)
    def test_unauthorized_new_code_worm_never_enqueued(self):
        h=NativeHarness()
        c=h.callbacks()
        callbacks=NativeCallbacks(**{**vars(c),
          "propose_nox_idea":lambda scope,ctx:dict(IDEA,execute_code=True)})
        r=HuntDirector(callbacks).tick("owner",now=NOW)
        self.assertNotIn("worm_created",r)
        self.assertEqual(h.created,[])
    def test_revoke_during_worm_invalidates(self):
        h=NativeHarness()
        c=h.callbacks()
        callbacks=NativeCallbacks(**{**vars(c),
           "existing_worm_tick":lambda scope:(setattr(h,"stop",True) or {})})
        r=HuntDirector(callbacks).tick("owner",now=NOW)
        self.assertEqual(r["reason"],"NATIVE_STOP_OR_POLICY_REVOKED_AFTER_WORMS")
        self.assertEqual(h.downloads,[])
    def test_worm_spec_new_role_is_virtual_and_bounded(self):
        self.assertFalse(HuntDirector._valid_idea(dict(IDEA,worm_kind="execute_python")))
        self.assertFalse(HuntDirector._valid_idea(dict(IDEA,worm_kind="isolated_browser")))
        self.assertTrue(HuntDirector._valid_idea(IDEA))
if __name__=="__main__":
    unittest.main()
