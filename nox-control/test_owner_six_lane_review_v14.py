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
        r = receipt("V14-memory-1")
        self.assertEqual(coordinator_reconcile(batch(), [r, r])["done"], 1)

    def test_child_without_predecessor_holds(self):
        r = coordinator_reconcile(batch(), [receipt("V14-web-2")])
        self.assertEqual(r["state"], "HOLD_DEPENDENCY_READBACK")
        self.assertEqual(r["done"], 0)
        self.assertEqual(r["blocked_dependency_ids"], ["V14-web-2"])

    def test_reversed_complete_dag_counts_in_order(self):
        r = coordinator_reconcile(batch(), [receipt("V14-web-3"), receipt("V14-web-1"), receipt("V14-web-2")])
        self.assertEqual(r["task_ids"], ["V14-web-1", "V14-web-2", "V14-web-3"])
        self.assertEqual(r["done"], 3)

    def test_gap_stays_blocked(self):
        r = coordinator_reconcile(batch(), [receipt("V14-memory-3"), receipt("V14-memory-1")])
        self.assertEqual(r["task_ids"], ["V14-memory-1"])
        self.assertEqual(r["blocked_dependency_ids"], ["V14-memory-3"])

    def test_failed_parent_does_not_unlock_child(self):
        parent = receipt("V14-safety-1")
        parent["rollback_verified"] = False
        r = coordinator_reconcile(batch(), [parent, receipt("V14-safety-2")])
        self.assertEqual(r["state"], "HOLD_DEPENDENCY_READBACK")
        self.assertEqual(r["done"], 0)

    def test_independent_lane_proceeds(self):
        r = coordinator_reconcile(batch(), [receipt("V14-web-2"), receipt("V14-maya-1")])
        self.assertEqual(r["task_ids"], ["V14-maya-1"])
        self.assertEqual(r["blocked_dependency_ids"], ["V14-web-2"])

    def test_conflicting_receipts_do_not_complete(self):
        first = receipt("V14-web-1")
        second = dict(first, result_sha256="b"*64)
        out = coordinator_reconcile(batch(), [first, second])
        self.assertEqual(out["state"], "HOLD_CONFLICTING_NATIVE_RECEIPTS")
        self.assertEqual(out["done"], 0)
        self.assertEqual(out["conflicting_task_ids"], ["V14-web-1"])

    def test_conflicting_parent_never_unlocks_child(self):
        first = receipt("V14-web-1")
        second = dict(first, result_sha256="c"*64)
        out = coordinator_reconcile(batch(), [first, receipt("V14-web-2"), second])
        self.assertEqual(out["done"], 0)
        self.assertEqual(out["blocked_dependency_ids"], ["V14-web-2"])
        self.assertEqual(out["conflicting_task_ids"], ["V14-web-1"])

    def test_conflict_isolated_from_independent_role(self):
        first = receipt("V14-web-1")
        second = dict(first, result_sha256="d"*64)
        out = coordinator_reconcile(batch(), [first, second, receipt("V14-maya-1")])
        self.assertEqual(out["state"], "HOLD_CONFLICTING_NATIVE_RECEIPTS")
        self.assertEqual(out["task_ids"], ["V14-maya-1"])
        self.assertEqual(out["done"], 1)

    def test_identical_native_replay_remains_idempotent(self):
        first = receipt("V14-web-1")
        out = coordinator_reconcile(batch(), [first, dict(first)])
        self.assertEqual(out["state"], "NATIVE_EVIDENCE_READBACK")
        self.assertEqual(out["task_ids"], ["V14-web-1"])
        self.assertEqual(out["conflicting_task_ids"], [])

if __name__ == "__main__":
    unittest.main()
