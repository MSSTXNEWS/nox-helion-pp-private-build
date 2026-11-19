"""Pin six logical NOX workstreams to existing original tasks.

Source-only. These tests never create native jobs, workers, automations or
claim acceptance of any original TaskID.
"""
import json
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent / "complete_executor_20261118" / "evidence"
HANDOFF = BASE / "six_lane_refill_handoff_20261119.json"
REGISTRY = ROOT / "all295_execution_disposition.json"


class SixLaneEvidenceTests(unittest.TestCase):
    def test_six_distinct_pinned_original_ids(self):
        data = json.loads(HANDOFF.read_bytes())
        canonical = json.loads(REGISTRY.read_bytes())
        original = {row["task_id"]: row for row in canonical["tasks"]}
        self.assertEqual(data["schema"], "NOX_SIX_LANE_REVIEWED_WORK_HANDOFF_V1")
        self.assertEqual(data["instructions_version"], "0.0.6")
        self.assertEqual(len(original), 295)
        self.assertEqual(data["registry_total_original_ids"], 295)
        self.assertEqual(data["registry_source_pins"], canonical["source_registry_sha256"])
        lanes = data["lanes"]
        self.assertEqual(len(lanes), 6)
        self.assertEqual({x["slot"] for x in lanes}, set(range(1, 7)))
        self.assertEqual(len({x["agent"] for x in lanes}), 6)
        self.assertEqual(len({x["automation_id"] for x in lanes}), 6)
        self.assertEqual(len({x["parent_task_id"] for x in lanes}), 6)
        self.assertEqual(len({x["repo_file"] for x in lanes}), 6)
        for lane in lanes:
            row = original[lane["parent_task_id"]]
            self.assertEqual(lane["queue_id"], row["queue_id"])
            self.assertEqual(lane["parent_spec_sha256"], row["spec_sha256"])
            self.assertEqual(lane["parent_title"], row["spec"]["title"])
            self.assertEqual(lane["required_evidence"], row["spec"]["evidence"])
            self.assertEqual(len(lane["source_blob_sha"]), 40)
            self.assertTrue(lane["task"] and lane["acceptance"])
            self.assertFalse(any(term in lane["task"].lower()
                                 for term in ("killall", "drop_caches", "sudo rm -rf")))

    def test_no_fake_native_workers_or_auto_approval(self):
        data = json.loads(HANDOFF.read_bytes())
        self.assertEqual(data["authority"], "SOURCE_WORK_ALLOCATION_ONLY")
        self.assertFalse(data["create_new_automation"])
        self.assertEqual(data["six_logical_subagents"], 6)
        self.assertEqual(data["max_native_workers_without_separate_owner_admission"], 3)
        self.assertEqual(data["original_295_accepted_by_this_pack"], 0)
        self.assertEqual(data["source"]["native_refill_state"], "REFILL_REQUIRED")
        self.assertEqual(data["source"]["new_executable_jobs_last_observed"], 0)
        self.assertEqual(len(data["source"]["manifest_sha256"]), 64)
        self.assertEqual(data["source"]["worker_cap_observed"], 3)
        self.assertIn("READY", data["fallback"])


if __name__ == "__main__":
    unittest.main()
