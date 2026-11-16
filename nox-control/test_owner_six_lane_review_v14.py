"""Source-only V14 reconciliation regressions; no native processes are started."""
import unittest
from owner_six_lane_review_v14 import ROLES, REVIEW_IDS, SCHEMA, coordinator_reconcile

def batch():
    return {"schema": SCHEMA, "state": "SIX_REVIEW_CANDIDATES_ONLY",
            "actual_processes": 6, "tasks_reviewed": len(REVIEW_IDS),
            "pids": {role: 3000+i for i, role in enumerate(ROLES)}}

def receipt(task_id):
    return {"task_id": task_id, "result_sha256": "a"*64,
            "native_verified": True, "terminal_state": "COMPLETED",
            "source_tests_passed": True, "installed_and_readback": True,
            "rollback_verified": True}

class ReconcileTest(unittest.TestCase):
    def test_exact_dag(self):
        self.assertEqual(len(REVIEW_IDS), 18)
        self.assertEqual(coordinator_reconcile(batch(), [receipt("V14-web-1")])["done"], 1)

    def test_unrelated_v14_tasks_not_completions(self):
        for task in ("V14-0-15", "V14-1-01", "V14-bogus-1", "V14-web-4"):
            with self.subTest(task=task):
                self.assertEqual(coordinator_reconcile(batch(), [receipt(task)])["done"], 0)

    def test_unverified_pids_hold(self):
        for pids in ({}, {role: 1 for role in ROLES},
                     {role: 4000 for role in ROLES}):
            with self.subTest(pids=pids):
                b = batch(); b["pids"] = pids
                self.assertEqual(coordinator_reconcile(b, [receipt("V14-web-1")])["state"],
                                 "HOLD_REVIEW_IDENTITY")

    def test_incomplete_review_holds(self):
        for key, value in (("actual_processes", 0), ("tasks_reviewed", 1)):
            b = batch(); b[key] = value
            self.assertEqual(coordinator_reconcile(b, [receipt("V14-web-1")])["done"], 0)

    def test_duplicate_once(self):
        r = receipt("V14-memory-2")
        self.assertEqual(coordinator_reconcile(batch(), [r, r])["done"], 1)

if __name__ == "__main__":
    unittest.main()
