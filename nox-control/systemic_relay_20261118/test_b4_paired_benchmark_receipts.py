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
            background_completed=True, trace_sha256=H,
            expected_full_input_sha256=H, served_full_input_sha256=H,
            first_text_ms=10 if status == "PASS" else None,
            cache_tokens_reused=3, prompt_tokens_evaluated=60))
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
        c["outcomes"][0]["latency_ms"]=1001
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
    def test_serving_truncation_holds(self):
        b=example();c=example();c["outcomes"][0]["served_full_input_sha256"]="b"*64
        self.assertEqual(compare_paired(b,c)["reason"],"INPUT_TRUNCATED_OR_MODIFIED")
    def test_changed_full_input_holds(self):
        b=example();c=example();c["outcomes"][1]["expected_full_input_sha256"]="b"*64
        c["outcomes"][1]["served_full_input_sha256"]="b"*64
        self.assertEqual(compare_paired(b,c)["reason"],"FULL_INPUT_DIFFERENCE")
    def test_missing_input_evidence_holds(self):
        b=example();c=example(); del c["outcomes"][0]["served_full_input_sha256"]
        self.assertEqual(compare_paired(b,c)["reason"],"FULL_INPUT_PIN")


    def test_p95_speedup_must_expose_slower_individual_task(self):
        b=example();c=copy.deepcopy(b)
        # The p95 gets faster, but a foreground task becomes slower.
        c["outcomes"][0]["latency_ms"]=25
        c["outcomes"][1]["latency_ms"]=900
        out=compare_paired(b,c)
        self.assertEqual(out["p95_latency_delta_ms"],-100)
        self.assertEqual(out["latency_regressed_task_ids"],["t1"])
        self.assertFalse(out["promotion_authorized"])

    def test_max_rss_improvement_must_expose_task_memory_regression(self):
        b=example();b["outcomes"][0]["peak_rss_bytes"]=100
        b["outcomes"][1]["peak_rss_bytes"]=1000
        c=copy.deepcopy(b)
        c["outcomes"][0]["peak_rss_bytes"]=200
        c["outcomes"][1]["peak_rss_bytes"]=900
        out=compare_paired(b,c)
        self.assertEqual(out["peak_rss_delta_bytes"],-100)
        self.assertEqual(out["peak_rss_regressed_task_ids"],["t1"])
        self.assertFalse(out["rank_claim_authorized"])

    def test_cache_collapse_not_masked_by_unchanged_aggregate(self):
        b=example();c=copy.deepcopy(b)
        # Opposite per-task changes cancel: total cache and prefill stay equal.
        c["outcomes"][0]["cache_tokens_reused"]=0
        c["outcomes"][1]["cache_tokens_reused"]=6
        c["outcomes"][0]["prompt_tokens_evaluated"]=63
        c["outcomes"][1]["prompt_tokens_evaluated"]=57
        out=compare_paired(b,c)
        self.assertTrue(out["comparable"])
        self.assertEqual(out["cache_tokens_reused_delta"],0)
        self.assertEqual(out["prompt_tokens_evaluated_delta"],0)
        self.assertEqual(out["cache_state_changed_task_ids"],["t1","t2"])
        self.assertEqual(out["cache_reuse_regressed_task_ids"],["t1"])
        self.assertEqual(out["cache_reuse_lost_task_ids"],["t1"])
        self.assertEqual(out["prompt_prefill_regressed_task_ids"],["t1"])
        self.assertTrue(out["latency_cache_state_confounder"])
        self.assertFalse(out["measured_nox_gain"])

    def test_same_aggregate_tokens_hides_per_task_workload_drift(self):
        b=example();c=copy.deepcopy(b)
        c["outcomes"][0]["output_tokens"]=2
        c["outcomes"][1]["output_tokens"]=22
        c["outcomes"][0]["latency_ms"]=15  # after first visible text at 10 ms
        out=compare_paired(b,c)
        self.assertEqual(out["baseline"]["total_output_tokens"],36)
        self.assertEqual(out["candidate"]["total_output_tokens"],36)
        self.assertEqual(out["output_tokens_changed_task_ids"],["t1","t2"])
        self.assertTrue(out["latency_observed_workload_confounder"])
        self.assertIsNone(out["p95_latency_delta_ms_same_observed_work"])
        self.assertFalse(out["measured_nox_gain"])
        unmodified=compare_paired(b,copy.deepcopy(b))
        self.assertFalse(unmodified["latency_observed_workload_confounder"])
        self.assertEqual(unmodified["p95_latency_delta_ms_same_observed_work"],0)

    def test_first_text_regression_and_cache_evidence(self):
        b=example();c=copy.deepcopy(b)
        c["outcomes"][0]["first_text_ms"]=15
        c["outcomes"][0]["cache_tokens_reused"]=30
        c["outcomes"][0]["prompt_tokens_evaluated"]=5
        out=compare_paired(b,c)
        self.assertEqual(out["schema"],"NOX_B4_PAIRED_COMPARISON_V3")
        self.assertEqual(out["first_text_regressed_task_ids"],["t1"])
        self.assertEqual(out["p95_first_text_delta_ms_same_coverage"],5)
        self.assertEqual(out["cache_tokens_reused_delta"],27)
        self.assertEqual(out["prompt_tokens_evaluated_delta"],-55)
        self.assertFalse(out["promotion_authorized"])

    def test_lost_first_text_prevents_false_p95_improvement(self):
        b=example();c=copy.deepcopy(b)
        c["outcomes"][0]["first_text_ms"]=None
        out=compare_paired(b,c)
        self.assertEqual(out["first_text_lost_task_ids"],["t1"])
        self.assertIsNone(out["p95_first_text_delta_ms_same_coverage"])
        self.assertEqual(out["candidate"]["first_text_missing"],3)
        self.assertTrue(out["quality_or_history_regression"])

    def test_impossible_first_text_timestamp_holds(self):
        b=example();c=example();c["outcomes"][0]["first_text_ms"]=21
        self.assertEqual(compare_paired(b,c)["reason"],"FIRST_TEXT_AFTER_END")

    def test_missing_kv_timing_evidence_holds(self):
        b=example();c=example();del c["outcomes"][1]["prompt_tokens_evaluated"]
        self.assertEqual(compare_paired(b,c)["reason"],"PROMPT_CACHE_TIMING_PROOF")

if __name__ == '__main__': unittest.main()
