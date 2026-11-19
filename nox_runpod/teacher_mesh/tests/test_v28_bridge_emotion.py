#!/usr/bin/env python3
"""Ensure new Future Cortex is only an evidence-based proposal, never a fake running AI."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from nox_future_cortex_bridge_v28 import compose_noX_plan
from nox_emotional_resonance_v28 import tone_plan

class Emotions(unittest.TestCase):
    def setUp(self):self.policy={"scope_authorized":True,"scope":"owner","native_stop":False}
    def test_user_preference_beats_classifier(self):
        p={"owner_approved":True,"scope":"owner","tone":"professional"}
        o={"state":"OBSERVED_TONE_NOT_DIAGNOSIS","label":"sadness","confidence":.95}
        r=tone_plan(language="ru",observation=o,owner_s03_preference=p,policy=self.policy)
        self.assertEqual(r["tone"],"professional")
        self.assertFalse(r["subjective_consciousness_claim"])
        self.assertFalse(r["neural_training_from_user_message"])
        self.assertTrue(r["owner_preference_used"])
    def test_tone_detection_is_suggested_not_diagnosed(self):
        o={"state":"OBSERVED_TONE_NOT_DIAGNOSIS","label":"fear","confidence":.8}
        r=tone_plan(language="es",observation=o,owner_s03_preference=None,policy=self.policy)
        self.assertEqual(r["tone"],"calm")
        self.assertTrue(r["no_psychological_diagnosis"])
    def test_low_confidence_is_not_interpreted(self):
        o={"state":"OBSERVED_TONE_NOT_DIAGNOSIS","label":"fear","confidence":.2}
        self.assertEqual(tone_plan(language="ru",observation=o,
            owner_s03_preference=None,policy=self.policy)["tone"],"neutral")
    def test_cross_scope_preferences_ignored(self):
        p={"owner_approved":True,"scope":"other","tone":"warm"}
        r=tone_plan(language="ru",observation=None,owner_s03_preference=p,policy=self.policy)
        self.assertEqual(r["tone"],"neutral")
        self.assertFalse(r["owner_preference_used"])
    def test_stop_and_invalid_owner_hold(self):
        p=dict(self.policy,native_stop=True)
        self.assertEqual(tone_plan(language="ru",observation=None,
            owner_s03_preference=None,policy=p)["state"],"HOLD_STOP")
        self.assertEqual(tone_plan(language="ru",observation=None,
            owner_s03_preference=None,policy={})["state"],"HOLD_UNAUTHENTICATED_S03_SCOPE")
    def test_no_internal_feelings(self):
        r=tone_plan(language="es",observation={"state":"OBSERVED_TONE_NOT_DIAGNOSIS",
            "label":"joy","confidence":.98},owner_s03_preference=None,policy=self.policy)
        self.assertEqual(r["tone"],"warm")
        self.assertFalse(r["subjective_consciousness_claim"])

class Cortex(unittest.TestCase):
    def test_missing_onehost_callback_is_hold(self):
        r=compose_noX_plan(task={"kind":"code"},registry=[],training_benchmarks=[],
          advisor_evidence=[],live_profile={},affect_observation=None,
          owner_s03_preference=None,policies={})
        self.assertEqual(r["state"],"HOLD_EXISTING_ONEHOST_NOT_BOUND")
        self.assertEqual(r["jobs_launched"],0)
    def test_core_stop_is_hold(self):
        r=compose_noX_plan(task={"kind":"code"},registry=[],training_benchmarks=[],
          advisor_evidence=[],live_profile={},affect_observation=None,
          owner_s03_preference=None,policies={"trusted_existing_onehost":True,
                         "core":{"authenticated_owner":True,"stop_requested":True}})
        self.assertEqual(r["state"],"HOLD_STOP_OR_OWNER_AUTH")
    def test_one_noX_five_planners_zero_side_effects(self):
        policies={"trusted_existing_onehost":True,"core":{"authenticated_owner":True,
          "stop_requested":False},"advisors":{},"arena":{},"curriculum":{},
          "speed":{},"emotion":{"scope_authorized":True,"native_stop":False,"scope":"owner"}}
        result=compose_noX_plan(task={"kind":"code","scope":"owner","language":"ru",
          "active_student_sha256":"a"*64,"chat_busy":False,"stop_requested":False},
          registry=[],training_benchmarks=[],advisor_evidence=[],
          live_profile={},affect_observation=None,owner_s03_preference=None,policies=policies)
        self.assertEqual(result["state"],"NOX_FIRST_ADVISORY_PLAN_NOT_EXECUTED")
        self.assertEqual(result["current_visible_model"],"ONE_ACTIVE_NOX_STUDENT_ONLY")
        self.assertEqual(result["gpu_trainer_jobs_started"],0)
        self.assertEqual(result["models_downloaded"],0)
        self.assertEqual(result["s03_writes"],0)
        self.assertEqual(result["new_os_processes"],0)
        self.assertFalse(result["production_modified"])
        self.assertEqual(result["emotional_resonance"]["state"],"STYLE_SUGGESTION_NOT_FEELING")
if __name__=="__main__":unittest.main()
