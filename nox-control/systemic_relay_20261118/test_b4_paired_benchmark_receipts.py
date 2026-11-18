import copy
import unittest
from b4_paired_benchmark_receipts import compare_paired

H = "a" * 64

def example():
    run = dict(benchmark_id="NOX_OWNER_SOURCE", benchmark_revision="v1",
        task_split_sha256=H, verifier_sha256=H, harness_sha256=H,
        budget_policy_sha256=H, environment_sha256=H, artifact_sha256=H,
        evaluation_receipt_sha256=H, native_verified=True, holdout_isolated=True,
        all_declared_tasks_accounted=True,
        denominator_kind="ONE_OUTCOME_PER_DECLARED_TASK", max_task_ms=1000,
        declared_task_ids=["t1", "t2", "t3"], outcomes=[])
    for task, status, delay in [("t1", "PASS", 20), ("t2", "TIMEOUT", 1000), ("t3", "FAIL", 35)]:
        run["outcomes"].append(dict(task_id=task, status=status, latency_ms=delay,
            peak_rss_bytes=512, output_tokens=12, history_saved=True,
            background_completed=True, trace_sha256=H))
    return run

class PairedReceiptTests(unittest.TestCase):
    def test_all_outcomes_in_denominator_and_latency(self):
        b = example(); c = copy.deepcopy(b); c["outcomes"][2]["status"] = "PASS"
        result = compare_paired(b, c)
        self.assertTrue(result["comparable"])
        self.assertEqual(result["baseline"]["passed"], 1)
        self.assertEqual(result["candidate"]["passed"], 2)
        self.assertEqual(result["baseline"]["p95_latency_ms_all_tasks"], 1000)
        self.assertEqual(result["pass_rate_delta"], 1/3)
        self.assertEqual(result["fixed_task_ids"], ["t3"])
        self.assertFalse(result["promotion_authorized"])
    def test_missing_task_holds(self):
        b=example(); c=example();c["outcomes"].pop()
        self.assertEqual(compare_paired(b,c)["reason"],"OUTCOME_COUNT")
    def test_duplicate_task_holds(self):
        b=example();c=example();c["outcomes"][1]["task_id"]="t1"
        self.assertEqual(compare_paired(b,c)["reason"],"MISSING_OR_DUPLICATE_TASK")
    def test_rejected_mismatched_environment(self):
        b=example();c=example();c["environment_sha256"]="b"*64
        self.assertEqual(compare_paired(b,c)["reason"],"EVALUATION_PROTOCOL_MISMATCH")
    def test_rejected_false_verified(self):
        b=example();c=example();c["native_verified"]=False
        self.assertEqual(compare_paired(b,c)["reason"],"INDEPENDENT_VERIFICATION_REQUIRED")
    def test_overbudget_timeout_still_counted(self):
        b=example();c=example();c["outcomes"][1]["latency_ms"]=1450
        out=compare_paired(b,c)
        self.assertTrue(out["comparable"])
        self.assertEqual(out["candidate"]["over_budget_walltime"],1)
        self.assertEqual(out["candidate"]["failures_including_timeouts"],2)
        self.assertEqual(out["candidate"]["p95_latency_ms_all_tasks"],1450)
    def test_reported_pass_over_budget_counts_as_failure(self):
        b=example();c=copy.deepcopy(b)
        c["outcomes"][0]["latency_ms"]=1001  # alleged PASS, but over 1000ms budget
        out=compare_paired(b,c)
        self.assertTrue(out["comparable"])
        self.assertEqual(out["baseline"]["passed"],1)
        self.assertEqual(out["candidate"]["passed"],0)
        self.assertEqual(out["candidate"]["failures_including_timeouts"],3)
        self.assertEqual(out["candidate"]["over_budget_reported_passes"],1)
        self.assertEqual(out["candidate"]["timed_out_or_exhausted"],2)
        self.assertEqual(out["candidate"]["p95_latency_ms_all_tasks"],1001)
        self.assertEqual(out["regressed_task_ids"],["t1"])
        self.assertTrue(out["quality_or_history_regression"])
    def test_recovered_over_budget_pass_is_a_fixed_task(self):
        b=example();b["outcomes"][0]["latency_ms"]=1001
        c=copy.deepcopy(b);c["outcomes"][0]["latency_ms"]=999
        out=compare_paired(b,c)
        self.assertEqual(out["fixed_task_ids"],["t1"])
        self.assertEqual(out["pass_rate_delta"],1/3)
    def test_rejected_boolean_latency(self):
        b=example();c=example();c["outcomes"][0]["latency_ms"]=True
        self.assertEqual(compare_paired(b,c)["reason"],"INVALID_LATENCY")
    def test_preservation_regression(self):
        b=example();c=example();c["outcomes"][0]["history_saved"]=False
        out=compare_paired(b,c)
        self.assertTrue(out["quality_or_history_regression"])
        self.assertEqual(out["candidate"]["history_saved"],2)
    def test_unhashable_status_holds(self):
        b=example();c=example();c["outcomes"][0]["status"] = []
        self.assertEqual(compare_paired(b,c)["reason"],"UNKNOWN_STATUS")
    def test_swapped_history_is_still_regression(self):
        b=example(); b["outcomes"][1]["history_saved"] = False
        c=copy.deepcopy(b); c["outcomes"][0]["history_saved"] = False
        c["outcomes"][1]["history_saved"] = True
        self.assertTrue(compare_paired(b,c)["quality_or_history_regression"])
    def test_no_rank_from_unchanged_records(self):
        out=compare_paired(example(),example())
        self.assertTrue(out["comparable"])
        self.assertFalse(out["rank_claim_authorized"])
        self.assertFalse(out["measured_nox_gain"])
    def test_order_drift_holds(self):
        b=example();c=example();c["declared_task_ids"].reverse()
        self.assertEqual(compare_paired(b,c)["reason"],"TASK_ORDER_MISMATCH")

if __name__ == '__main__': unittest.main()
