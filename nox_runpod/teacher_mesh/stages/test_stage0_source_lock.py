#!/usr/bin/env python3
"""Regression tests for honest V28 source lock, no OneHost or GPU mocks."""
import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from stage0_source_lock import (CANONICAL,HERE,HOLD_GATES,verify,
     validate_source_manifest,validate_benchmark_baseline)

ROOT=HERE.parents[2]
class Stage0Tests(unittest.TestCase):
    def setUp(self):
        self.manifest=json.loads(CANONICAL.read_text(encoding="utf-8"))
        self.receipt=json.loads(
           (ROOT/self.manifest["web"]["receipt_file"]).read_text(encoding="utf-8"))
    def test_actual_source_baseline_consistent_not_live(self):
        report=verify(ROOT)
        self.assertEqual(report["status"],"SOURCE_BASELINE_VERIFIED_RUNTIME_HOLD")
        self.assertEqual(report["required_repo_files"],15)
        self.assertEqual(len(report["runtime_e07_gates"]),len(HOLD_GATES))
        self.assertTrue(all(x=="HOLD_NOT_TESTED" for x in report["runtime_e07_gates"].values()))
        self.assertFalse(report["new_weights_training"])
        self.assertFalse(report["production_modified"])
        self.assertEqual(report["training_optimizer_steps_verified"],0)
        self.assertEqual(report["physical_file_checks"][0]["state"],"HOLD_NOT_MOUNTED_NO_PHYSICAL_CLAIM")
    def test_tampered_d02_is_hold(self):
        bad=json.loads(json.dumps(self.receipt))
        bad["integrity"]["staged_d02_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"HOLD_V26_CLAIMS"):
            validate_source_manifest(self.manifest,bad)
    def test_forged_acceptance_cannot_upgrade(self):
        bad=json.loads(json.dumps(self.receipt))
        bad["gates"]["release_accepted"]=True
        with self.assertRaisesRegex(ValueError,"HOLD_V26_CLAIMS"):
            validate_source_manifest(self.manifest,bad)
    def test_no_claim_l03_independent_replay(self):
        bad=json.loads(json.dumps(self.manifest["historical_model_benchmark"]))
        bad["replayed_independently"]=True
        with self.assertRaisesRegex(ValueError,"HOLD_BENCHMARK_NOT_HISTORICAL"):
            validate_benchmark_baseline(bad)
    def test_l03_wrong_results_rejected(self):
        bad=json.loads(json.dumps(self.manifest["historical_model_benchmark"]))
        bad["subset_scores"]["IFEval"]["correct"]=95
        with self.assertRaisesRegex(ValueError,"HOLD_REPORTED_BENCHMARK"):
            validate_benchmark_baseline(bad)
    def test_legacy_weights_preserved(self):
        self.assertTrue(self.manifest["policy"]["no_old_checkpoint_deletions"])
        self.assertEqual(self.manifest["unverified_runtime_gates"],list(HOLD_GATES))
if __name__=="__main__":unittest.main()
