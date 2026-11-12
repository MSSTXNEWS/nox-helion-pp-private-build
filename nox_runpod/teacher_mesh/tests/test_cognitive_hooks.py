#!/usr/bin/env python3
"""Offline research hooks: local emotions and safe self-improvement are gated."""
import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from cognitive_emotion_local import LocalEmotionClassifier,_safe_dir
from self_improvement import Observation,propose_experiment,assess_candidate

TS="2026-11-12T01:20:00Z"

class CognitiveHooksTests(unittest.TestCase):
    def test_emotion_classifier_does_not_download_or_mislabel(self):
        with self.assertRaisesRegex(ValueError,"HOLD_EMOTION_MODEL_NOT_LOCAL"):
            LocalEmotionClassifier("/tmp/nox/missing",language="ru",
                source_model_id="cointegrated/rubert-tiny2-cedr-emotion-detection")
        with self.assertRaisesRegex(ValueError,"HOLD_UNAPPROVED_EMOTION_MODEL"):
            LocalEmotionClassifier("/tmp/nox/a",language="es",source_model_id="fake")
        root=Path("/tmp/nox")
        root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="emotion_test_",dir=root) as directory:
            (Path(directory)/"config.json").write_text("{}")
            cls=LocalEmotionClassifier(directory,language="es",
                 source_model_id="UMUTeam/MarIA-emotion-es")
            state=cls("estoy triste","es")
            self.assertEqual(state["label"],"uncertain")
            self.assertEqual(state["confidence"],0.0)

    def test_only_observed_gap_can_propose(self):
        obs=Observation("quality_001","response_quality",.60,
            "https://github.com/MSSTXNEWS/nox/actions/runs/1",True,TS)
        proposal=propose_experiment(obs,recommendation="Improve answer citations")
        self.assertEqual(proposal["state"],"PROPOSED_NOT_APPLIED")
        self.assertTrue(proposal["owner_approval_required"])
        self.assertFalse(proposal["production_changes"])
        bad=Observation("quality_001","response_quality",.60,
            "https://github.com/MSSTXNEWS/nox/actions/runs/1",False,TS)
        self.assertEqual(propose_experiment(bad,recommendation="Fix")["state"],
                         "HOLD_UNVERIFIED_OBSERVATION")
        winner=Observation("quality_001","response_quality",.74,
            "https://github.com/MSSTXNEWS/nox/actions/runs/2",True,TS)
        self.assertEqual(assess_candidate(proposal,baseline=obs,candidate=winner,
            tests_passed=True,regression_count=0,owner_approved=False)["state"],
            "READY_FOR_OWNER_REVIEW_NOT_DEPLOYED")
        approved=assess_candidate(proposal,baseline=obs,candidate=winner,
            tests_passed=True,regression_count=0,owner_approved=True)
        self.assertEqual(approved["state"],"ACCEPTED_FOR_STAGING_NOT_DEPLOYED")
        self.assertFalse(approved["production_modified"])
        self.assertEqual(assess_candidate(proposal,baseline=obs,candidate=winner,
            tests_passed=True,regression_count=1,owner_approved=True)["state"],
            "REJECT_REGRESSION")

if __name__=="__main__":
    unittest.main()
