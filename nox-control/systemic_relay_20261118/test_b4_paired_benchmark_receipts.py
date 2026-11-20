import copy
import hashlib
import json
import unittest
from b4_paired_benchmark_receipts import (ReceiptHold, compare_paired,
                                          measure_openai_sse_wire,
                                          measure_two_turn_openai_sse_capture,
                                          verify_two_turn_openai_posted_history,
                                          verify_two_turn_http_trace_envelope,
                                          verify_cdp_receipt_against_http_trace)

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
            cache_tokens_reused=3, prompt_tokens_evaluated=60,
            sse_terminal_seen=(status == "PASS"),
            model_finish_reason=("stop" if status == "PASS" else "length")))
    return run

class PairedReceiptTests(unittest.TestCase):
    def test_all_outcomes_in_denominator_and_latency(self):
        b = example(); c = copy.deepcopy(b); c["outcomes"][2]["status"] = "PASS"
        c["outcomes"][2]["first_text_ms"] = 10  # a real visible reply
        c["outcomes"][2]["sse_terminal_seen"] = True
        c["outcomes"][2]["model_finish_reason"] = "stop"
        result = compare_paired(b, c)
        self.assertTrue(result["comparable"])
        self.assertEqual(result["baseline"]["passed"], 1)
        self.assertEqual(result["candidate"]["passed"], 2)
        self.assertEqual(result["baseline"]["p95_latency_ms_all_tasks"], 1000)
        self.assertEqual(result["pass_rate_delta"], 1/3)
        self.assertEqual(result["fixed_task_ids"], ["t3"])
        self.assertFalse(result["promotion_authorized"])
    def test_empty_reasoning_only_or_unsaved_pass_is_not_chat_success(self):
        b = example()
        for field, value in (("first_text_ms", None),
                             ("output_tokens", 0),
                             ("history_saved", False)):
            with self.subTest(field=field):
                c = copy.deepcopy(b)
                c["outcomes"][0][field] = value
                out = compare_paired(b, c)
                self.assertTrue(out["comparable"])
                self.assertEqual(out["baseline"]["passed"], 1)
                self.assertEqual(out["candidate"]["passed"], 0)
                self.assertEqual(out["candidate"]["reported_pass_without_usable_chat"], 1)
                self.assertEqual(out["candidate_reported_pass_without_usable_chat_task_ids"], ["t1"])
                self.assertEqual(out["regressed_task_ids"], ["t1"])
                self.assertTrue(out["quality_or_history_regression"])
                self.assertFalse(out["promotion_authorized"])

    def test_reported_pass_cannot_skip_required_background_completion(self):
        b = example(); c = copy.deepcopy(b)
        # A visible final SSE + S03 history is not a complete owner turn
        # if the required background operation was silently skipped.
        c["outcomes"][0]["background_completed"] = False
        out = compare_paired(b, c)
        self.assertTrue(out["comparable"])
        self.assertEqual(out["baseline"]["passed"], 1)
        self.assertEqual(out["candidate"]["passed"], 0)
        self.assertEqual(out["candidate"]["reported_pass_without_usable_chat"], 1)
        self.assertEqual(out["candidate_reported_pass_without_usable_chat_task_ids"], ["t1"])
        self.assertEqual(out["background_completion_changed_task_ids"], ["t1"])
        self.assertTrue(out["quality_or_history_regression"])
        self.assertFalse(out["promotion_authorized"])

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

    def test_dropped_durable_or_background_work_cannot_fake_same_work_speedup(self):
        b = example()
        for field, task, expected in (("history_saved", "t1", ["t1"]),
                                      ("background_completed", "t2", ["t2"])):
            with self.subTest(field=field):
                c = copy.deepcopy(b)
                idx = 0 if task == "t1" else 1
                c["outcomes"][idx][field] = False
                c["outcomes"][1]["latency_ms"] = 900  # aggregate p95 improves
                out = compare_paired(b, c)
                self.assertTrue(out["comparable"])
                self.assertEqual(out["p95_latency_delta_ms"], -100)
                self.assertTrue(out["latency_side_effects_confounder"])
                self.assertEqual(out["history_durability_changed_task_ids"],
                                 expected if field == "history_saved" else [])
                self.assertEqual(out["background_completion_changed_task_ids"],
                                 expected if field == "background_completed" else [])
                self.assertTrue(out["latency_observed_workload_confounder"])
                self.assertIsNone(out["p95_latency_delta_ms_same_observed_work"])
                self.assertTrue(out["quality_or_history_regression"])
                self.assertFalse(out["measured_nox_gain"])

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

    def test_changed_strict_sse_visible_answer_blocks_same_work_speedup(self):
        # Different answers of equal length and token count make speedup N/A.
        def bound(value):
            run = example()
            run["declared_task_ids"] = ["t1"]
            run["outcomes"] = [run["outcomes"][0]]
            run["sse_binding_required"] = True
            chunks = [
                (5, ("data: " + json.dumps({
                    "choices": [{"delta": {"content": value},
                                 "finish_reason": None}]}) + "\n\n").encode()),
                (8, b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'),
                (10, b"data: [DONE]\n\n"),
            ]
            wire = measure_openai_sse_wire(chunks)
            row = run["outcomes"][0]
            row.update(first_text_ms=5, trace_sha256=wire["timed_trace_sha256"],
                       sse_wire_witness=wire,
                       sse_raw_wire_sha256=wire["raw_wire_sha256"],
                       sse_visible_text_sha256=wire["visible_text_sha256"])
            return run

        b, c = bound("ready"), bound("later")
        c["outcomes"][0]["latency_ms"] = 15
        out = compare_paired(b, c)
        self.assertTrue(out["comparable"])
        self.assertEqual(out["baseline"]["passed"], 1)
        self.assertEqual(out["candidate"]["passed"], 1)
        self.assertEqual(out["output_tokens_changed_task_ids"], [])
        self.assertEqual(out["visible_output_changed_task_ids"], ["t1"])
        self.assertTrue(out["latency_visible_content_confounder"])
        self.assertEqual(out["p95_latency_delta_ms"], -5)
        self.assertIsNone(out["p95_latency_delta_ms_same_observed_work"])
        self.assertTrue(out["latency_observed_workload_confounder"])
        self.assertFalse(out["quality_or_history_regression"])

        same = compare_paired(b, copy.deepcopy(b))
        self.assertEqual(same["visible_output_changed_task_ids"], [])
        self.assertFalse(same["latency_visible_content_confounder"])
        self.assertEqual(same["p95_latency_delta_ms_same_observed_work"], 0)
        # Historical unbound digest claims are NOT verified SSE content.
        legacy, legacy2 = example(), example()
        legacy["outcomes"][0]["sse_visible_text_sha256"] = "b" * 64
        legacy2["outcomes"][0]["sse_visible_text_sha256"] = "c" * 64
        old = compare_paired(legacy, legacy2)
        self.assertTrue(old["comparable"])
        self.assertEqual(old["visible_output_changed_task_ids"], [])

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

    def test_stream_disconnect_after_text_is_not_a_success(self):
        b = example(); c = copy.deepcopy(b)
        c["outcomes"][0]["sse_terminal_seen"] = False
        out = compare_paired(b, c)
        self.assertTrue(out["comparable"])
        self.assertEqual(out["candidate"]["passed"], 0)
        self.assertEqual(out["candidate"]["reported_pass_without_terminal_sse"], 1)
        self.assertEqual(out["candidate_reported_pass_without_terminal_sse_task_ids"], ["t1"])
        self.assertEqual(out["sse_finality_changed_task_ids"], ["t1"])
        self.assertEqual(out["regressed_task_ids"], ["t1"])
        self.assertIsNone(out["p95_latency_delta_ms_same_observed_work"])

    def test_finish_reason_length_is_partial_even_after_done(self):
        b = example(); c = copy.deepcopy(b)
        c["outcomes"][0]["model_finish_reason"] = "length"
        out = compare_paired(b, c)
        self.assertTrue(out["comparable"])
        self.assertEqual(out["candidate"]["passed"], 0)
        self.assertEqual(out["candidate_reported_pass_without_terminal_sse_task_ids"], ["t1"])
        self.assertTrue(out["latency_observed_workload_confounder"])
        self.assertTrue(out["quality_or_history_regression"])

    def test_missing_or_untyped_stream_finality_holds(self):
        b = example()
        for value in ("missing", "yes", None):
            with self.subTest(value=value):
                c = copy.deepcopy(b)
                if value == "missing":
                    del c["outcomes"][0]["sse_terminal_seen"]
                else:
                    c["outcomes"][0]["sse_terminal_seen"] = value
                self.assertEqual(compare_paired(b, c)["reason"], "SSE_TERMINAL_PROOF")


    def test_failed_task_losing_sse_terminal_is_not_hidden_by_pass_rate(self):
        b = example()
        # A failed chat turn initially received a normal terminal marker.
        # After a network interruption it remains FAIL, so PASS totals cannot
        # expose that its streaming reliability deteriorated.
        b["outcomes"][2]["sse_terminal_seen"] = True
        b["outcomes"][2]["model_finish_reason"] = "stop"
        c = copy.deepcopy(b)
        c["outcomes"][2]["sse_terminal_seen"] = False
        c["outcomes"][2]["model_finish_reason"] = "error"
        out = compare_paired(b, c)
        self.assertEqual(out["baseline"]["passed"], out["candidate"]["passed"])
        self.assertEqual(out["baseline"]["sse_terminal_seen"], 2)
        self.assertEqual(out["candidate"]["sse_terminal_seen"], 1)
        self.assertEqual(out["candidate"]["sse_terminal_missing"], 2)
        self.assertEqual(out["sse_terminal_lost_task_ids"], ["t3"])
        self.assertEqual(out["sse_normal_completion_regressed_task_ids"], ["t3"])
        self.assertEqual(out["sse_terminal_coverage_delta"], -1 / 3)
        self.assertTrue(out["sse_reliability_regression"])
        self.assertTrue(out["quality_or_history_regression"])
        self.assertIsNone(out["p95_latency_delta_ms_same_observed_work"])

    def test_failed_task_terminal_recovery_exposed_without_false_pass(self):
        b = example()
        c = copy.deepcopy(b)
        c["outcomes"][2]["sse_terminal_seen"] = True
        c["outcomes"][2]["model_finish_reason"] = "stop"
        out = compare_paired(b, c)
        self.assertEqual(out["baseline"]["passed"], out["candidate"]["passed"])
        self.assertEqual(out["sse_terminal_restored_task_ids"], ["t3"])
        self.assertEqual(out["sse_terminal_coverage_delta"], 1 / 3)
        self.assertEqual(out["candidate"]["sse_normal_completion"], 2)
        self.assertFalse(out["sse_reliability_regression"])
        self.assertFalse(out["promotion_authorized"])

    def test_nonstop_failed_task_losing_terminal_is_reliability_regression(self):
        b = example()
        # An already-failed task can lose its SSE terminal after a network
        # fault. Its original finish reason need not have been normal 'stop'.
        b["outcomes"][2]["sse_terminal_seen"] = True
        b["outcomes"][2]["model_finish_reason"] = "length"
        c = copy.deepcopy(b)
        c["outcomes"][2]["sse_terminal_seen"] = False
        c["outcomes"][2]["model_finish_reason"] = "error"
        out = compare_paired(b, c)
        self.assertTrue(out["comparable"])
        self.assertEqual(out["baseline"]["passed"], out["candidate"]["passed"])
        self.assertEqual(out["sse_terminal_lost_task_ids"], ["t3"])
        self.assertEqual(out["sse_normal_completion_regressed_task_ids"], [])
        self.assertEqual(out["sse_terminal_coverage_delta"], -1 / 3)
        self.assertTrue(out["sse_reliability_regression"])
        self.assertTrue(out["quality_or_history_regression"])
        self.assertIsNone(out["p95_latency_delta_ms_same_observed_work"])
        self.assertFalse(out["promotion_authorized"])


    def test_sse_wire_ttft_fragmented_unicode_heartbeat_and_terminal(self):
        reasoning = ("data: " + json.dumps(
            {"choices": [{"delta": {"reasoning_content": "hidden"},
                          "finish_reason": None}]}) + "\r\n\r\n").encode()
        visible = ("data: " + json.dumps(
            {"choices": [{"delta": {"content": "Привет 😀"},
                          "finish_reason": None}]}, ensure_ascii=False) + "\r\n\r\n").encode()
        split = visible.index("😀".encode()) + 2  # split inside UTF-8 scalar
        end = ("data: " + json.dumps(
            {"choices": [{"delta": {}, "finish_reason": "stop"}]}) + "\r\n\r\n").encode()
        chunks = [(1, b": heartbeat\r\n\r\n"), (5, reasoning),
                  (10, visible[:split]), (16, visible[split:]),
                  (22, end), (25, b"data: [DONE]\r\n\r\n")]
        witness = measure_openai_sse_wire(chunks)
        self.assertEqual(witness["first_text_ms"], 16)
        self.assertEqual(witness["completion_ms"], 25)
        self.assertEqual(witness["model_finish_reason"], "stop")
        self.assertTrue(witness["sse_terminal_seen"])
        self.assertTrue(witness["wire_completed_normally"])
        self.assertEqual(witness["visible_text_sha256"],
                         hashlib.sha256("Привет 😀".encode()).hexdigest())
        self.assertEqual(witness["raw_wire_sha256"],
                         hashlib.sha256(b"".join(x for _, x in chunks)).hexdigest())
        self.assertFalse(witness["native_verified"])
        self.assertFalse(witness["s03_durable_verified"])
        # Timings are sealed separately: same bytes at different times != same receipt.
        shifted = [(ms + 7, chunk) for ms, chunk in chunks]
        self.assertEqual(measure_openai_sse_wire(shifted)["raw_wire_sha256"],
                         witness["raw_wire_sha256"])
        self.assertNotEqual(measure_openai_sse_wire(shifted)["timed_trace_sha256"],
                            witness["timed_trace_sha256"])

    def test_sse_wire_eof_cannot_forge_terminal_or_stop(self):
        visible = b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\n'
        witness = measure_openai_sse_wire([(7, visible), (8, b"data: [DONE]\n")])
        self.assertEqual(witness["first_text_ms"], 7)
        self.assertFalse(witness["sse_terminal_seen"])
        self.assertTrue(witness["partial_frame_at_eof"])
        self.assertFalse(witness["wire_completed_normally"])
        terminal_no_stop = measure_openai_sse_wire([
            (1, visible.replace(b'"stop"', b'"length"')),
            (2, b"data: [DONE]\n\n")])
        self.assertTrue(terminal_no_stop["sse_terminal_seen"])
        self.assertFalse(terminal_no_stop["wire_completed_normally"])

    def test_sse_wire_nonfinite_json_constants_never_certify_chat(self):
        # CPython's json.loads accepts these invalid JSON constants even in
        # ignored metadata; malformed streams must never certify completion.
        prefix = b'{"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]'
        bad_suffixes = (b',"debug":NaN}',
                        b',"debug":{"value":Infinity}}',
                        b',"debug":[-Infinity]}')
        for suffix in bad_suffixes:
            with self.subTest(suffix=suffix):
                with self.assertRaisesRegex(
                        ReceiptHold, "SSE_NONFINITE_JSON_CONSTANT"):
                    measure_openai_sse_wire([
                        (2, b"data: " + prefix + suffix + b"\n\n"),
                        (5, b"data: [DONE]\n\n")])
        good = measure_openai_sse_wire([
            (2, b"data: " + prefix + b'}\n\n'),
            (5, b"data: [DONE]\n\n")])
        self.assertTrue(good["wire_completed_normally"])
        self.assertEqual(good["first_text_ms"], 2)
        self.assertEqual(good["completion_ms"], 5)

    def test_sse_wire_nonfinite_exponent_is_not_clean_terminal(self):
        # CPython accepts syntactically valid JSON exponent overflow as inf.
        # Even ignored model metadata must not certify a normal SSE answer.
        prefix = b'{"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]'
        for numeric in (b'1e999', b'-1e999', b'3.14e999'):
            with self.subTest(number=numeric):
                with self.assertRaisesRegex(
                        ReceiptHold, "SSE_NONFINITE_JSON_NUMBER"):
                    measure_openai_sse_wire([
                        (2, b"data: " + prefix + b',"debug":' + numeric + b'}\n\n'),
                        (5, b"data: [DONE]\n\n")])
        valid = measure_openai_sse_wire([
            (2, b"data: " + prefix + b',"debug":1.25e2}\n\n'),
            (5, b"data: [DONE]\n\n")])
        self.assertTrue(valid["wire_completed_normally"])
        self.assertEqual(valid["first_text_ms"], 2)
        self.assertEqual(valid["completion_ms"], 5)

    def test_sse_wire_rejects_duplicate_json_fields_at_every_depth(self):
        # json.loads normally uses last-wins and could invent a normal stop.
        ambiguous = (
            b'{"choices":[],"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}',
            b'{"choices":[{"delta":{"content":"ok"},"finish_reason":"length","finish_reason":"stop"}]}',
            b'{"choices":[{"delta":{"content":"hidden","content":"ok"},"finish_reason":"stop"}]}',
            b'{"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}],"usage":{"total_tokens":1,"total_tokens":2}}',
        )
        for payload in ambiguous:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ReceiptHold, "SSE_DUPLICATE_JSON_FIELD"):
                    measure_openai_sse_wire([
                        (2, b"data: " + payload + b"\n\n"),
                        (5, b"data: [DONE]\n\n")])
        # Normal unambiguous streaming still preserves TTFT and finality.
        ordinary = measure_openai_sse_wire([
            (2, b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\n'),
            (5, b"data: [DONE]\n\n")])
        self.assertTrue(ordinary["wire_completed_normally"])
        self.assertEqual(ordinary["first_text_ms"], 2)
        self.assertEqual(ordinary["completion_ms"], 5)

    def test_sse_wire_rejects_duplicate_done_invalid_json_and_utf8(self):
        for chunks, reason in (
            ([(1, b"data: [DONE]\n\n"), (2, b"data: [DONE]\n\n")],
             "SSE_AFTER_TERMINAL"),
            ([(1, b"data: {bad json}\n\n")], "SSE_INVALID_JSON"),
            ([(1, b"data: \xff\n\n")], "SSE_INVALID_UTF8"),
        ):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ReceiptHold, reason):
                    measure_openai_sse_wire(chunks)

    def test_sse_wire_final_usage_chunk_is_not_an_error_or_terminal(self):
        # OpenAI-compatible stream_options.include_usage emits an extra
        # choices=[] chunk before [DONE], without a delta or finish_reason.
        visible = b'data: {"choices":[{"delta":{"content":"ready"},"finish_reason":null}]}\n\n'
        stop = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        usage = (b'data: {"choices":[],"usage":{"prompt_tokens":17,'
                 b'"completion_tokens":2,"total_tokens":19}}\n\n')
        chunks = [(4, visible), (8, stop), (11, usage[:22]),
                  (15, usage[22:]), (18, b"data: [DONE]\n\n")]
        witness = measure_openai_sse_wire(chunks)
        self.assertTrue(witness["wire_completed_normally"])
        self.assertEqual(witness["parsed_events"], 3)
        self.assertEqual(witness["first_text_ms"], 4)
        self.assertEqual(witness["completion_ms"], 18)
        self.assertEqual(witness["model_finish_reason"], "stop")
        self.assertEqual(witness["visible_text_sha256"],
                         hashlib.sha256(b"ready").hexdigest())
        self.assertFalse(witness["native_verified"])
        before_done = measure_openai_sse_wire(chunks[:-1])
        self.assertFalse(before_done["wire_completed_normally"])
        self.assertFalse(before_done["sse_terminal_seen"])

    def test_sse_wire_usage_counts_must_add_up(self):
        visible = b'data: {"choices":[{"delta":{"content":"ready"},"finish_reason":"stop"}]}\n\n'
        done = b"data: [DONE]\n\n"
        def usage_frame(prompt, completion, total):
            return ("data: " + json.dumps(
                {"choices": [], "usage": {"prompt_tokens": prompt,
                 "completion_tokens": completion, "total_tokens": total}}
            ) + "\n\n").encode("utf-8")

        for prompt, completion, total in ((17, 2, 18), (17, 2, 20),
                                          (0, 1, 0)):
            with self.subTest(prompt=prompt, completion=completion, total=total):
                with self.assertRaisesRegex(ReceiptHold,
                                            "SSE_USAGE_COUNT_MISMATCH"):
                    measure_openai_sse_wire([
                        (3, visible), (5, usage_frame(prompt, completion, total)),
                        (8, done)])

        good = [(3, visible), (5, usage_frame(17, 2, 19)), (8, done)]
        receipt = measure_openai_sse_wire(good)
        self.assertTrue(receipt["wire_completed_normally"])
        self.assertEqual(receipt["first_text_ms"], 3)
        self.assertEqual(receipt["completion_ms"], 8)
        self.assertEqual(receipt["raw_wire_sha256"],
                         hashlib.sha256(b"".join(chunk for _, chunk in good)).hexdigest())
        zero = measure_openai_sse_wire([
            (3, visible), (5, usage_frame(0, 0, 0)), (8, done)])
        self.assertTrue(zero["wire_completed_normally"])
        no_usage = measure_openai_sse_wire([(3, visible), (8, done)])
        self.assertTrue(no_usage["wire_completed_normally"])

    def test_sse_wire_empty_choices_requires_valid_final_usage_and_prior_finish(self):
        visible = b'data: {"choices":[{"delta":{"content":"ready"},"finish_reason":"stop"}]}\n\n'
        good_usage = (b'data: {"choices":[],"usage":{"prompt_tokens":17,'
                      b'"completion_tokens":2,"total_tokens":19}}\n\n')
        bad_usage = b'data: {"choices":[],"usage":{"total_tokens":19}}\n\n'
        no_usage = b'data: {"choices":[]}\n\n'
        for chunks in ([(1, good_usage)], [(1, visible), (2, bad_usage)],
                       [(1, visible), (2, no_usage)]):
            with self.subTest(chunks=chunks):
                with self.assertRaisesRegex(ReceiptHold, "SSE_USAGE_CHUNK_SCHEMA"):
                    measure_openai_sse_wire(chunks)


    def test_sse_wire_finality_is_immutable_until_done(self):
        visible = b'data: {"choices":[{"delta":{"content":"ready"},"finish_reason":null}]}\n\n'
        stop = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        usage = (b'data: {"choices":[],"usage":{"prompt_tokens":17,'
                 b'"completion_tokens":2,"total_tokens":19}}\n\n')
        late_text = b'data: {"choices":[{"delta":{"content":"oops"},"finish_reason":null}]}\n\n'
        duplicate_final = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        done = b"data: [DONE]\n\n"
        for suffix, reason in (
            (late_text, "SSE_POST_FINISH_EVENT"),
            (duplicate_final, "SSE_POST_FINISH_EVENT"),
            (usage + usage, "SSE_DUPLICATE_USAGE"),
            (usage + late_text, "SSE_POST_FINISH_EVENT"),
        ):
            with self.subTest(reason=reason, suffix=suffix[:20]):
                with self.assertRaisesRegex(ReceiptHold, reason):
                    measure_openai_sse_wire([
                        (2, visible), (4, stop), (8, suffix), (10, done)])
        accepted = measure_openai_sse_wire([
            (2, visible), (4, stop), (8, usage), (10, done)])
        self.assertTrue(accepted["wire_completed_normally"])
        self.assertEqual(accepted["visible_utf8_bytes"], 5)
        self.assertEqual(accepted["completion_ms"], 10)

    def test_sse_wire_lone_surrogate_is_structured_hold(self):
        # json.loads accepts escaped unpaired UTF-16 code units, even
        # though they cannot be encoded as genuine UTF-8 visible text.
        for codepoint in (0xD800, 0xDC00):
            with self.subTest(codepoint=hex(codepoint)):
                payload = ("data: " + json.dumps(
                    {"choices": [{"delta": {"content": chr(codepoint)},
                                  "finish_reason": None}]}) + "\n\n").encode("ascii")
                with self.assertRaisesRegex(
                        ReceiptHold, "SSE_INVALID_UNICODE_SCALAR"):
                    measure_openai_sse_wire([(3, payload)])

        # A legitimate supplementary scalar encoded as a surrogate pair
        # in JSON decodes to one code point and remains fully supported.
        pair = ("data: " + json.dumps(
            {"choices": [{"delta": {"content": "😀"},
                          "finish_reason": None}]}) + "\n\n").encode("ascii")
        stop = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        done = b"data: [DONE]\n\n"
        receipt = measure_openai_sse_wire([
            (2, pair), (5, stop), (7, done)])
        self.assertTrue(receipt["wire_completed_normally"])
        self.assertEqual(receipt["first_text_ms"], 2)
        self.assertEqual(receipt["completion_ms"], 7)
        self.assertEqual(receipt["visible_text_sha256"],
                         hashlib.sha256("😀".encode("utf-8")).hexdigest())

    def test_sse_wire_whitespace_does_not_forge_usable_first_text(self):
        # All bytes still contribute to the original text digest, but a
        # blank-only stream is not a successful user-visible chat answer.
        blank = ('data: ' + json.dumps(
            {"choices": [{"delta": {"content": " \n\t"}, "finish_reason": None}]})
            + '\n\n').encode()
        actual = b'data: {"choices":[{"delta":{"content":"ready"},"finish_reason":null}]}\n\n'
        stop = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        done = b'data: [DONE]\n\n'
        only_blank = measure_openai_sse_wire([
            (2, blank), (6, stop), (9, done)])
        self.assertTrue(only_blank["sse_terminal_seen"])
        self.assertEqual(only_blank["model_finish_reason"], "stop")
        self.assertIsNone(only_blank["first_text_ms"])
        self.assertFalse(only_blank["wire_completed_normally"])
        self.assertEqual(only_blank["visible_utf8_bytes"], len(" \n\t".encode()))
        self.assertEqual(only_blank["visible_text_sha256"],
                         hashlib.sha256(" \n\t".encode()).hexdigest())
        with_text = measure_openai_sse_wire([
            (2, blank), (5, actual), (6, stop), (9, done)])
        self.assertEqual(with_text["first_text_ms"], 5)
        self.assertTrue(with_text["wire_completed_normally"])
        self.assertEqual(with_text["visible_text_sha256"],
                         hashlib.sha256(" \n\tready".encode()).hexdigest())

    def test_sse_wire_zero_width_and_control_only_are_not_first_visible_text(self):
        # The stream may finish normally while emitting zero visible glyphs.
        # Zero-width format characters/control codes must not forge TTFT.
        invisible = "\u200b\u200d\u2060\x00 \n\t"
        visible = "¡Hola, Привет 😀"
        def frame(value, reason=None):
            return ("data: " + json.dumps(
                {"choices": [{"delta": {"content": value},
                              "finish_reason": reason}]}) + "\n\n").encode("utf-8")
        stop = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        done = b"data: [DONE]\n\n"
        blank_only = measure_openai_sse_wire([
            (2, frame(invisible)), (7, stop), (9, done)])
        self.assertIsNone(blank_only["first_text_ms"])
        self.assertFalse(blank_only["wire_completed_normally"])
        self.assertTrue(blank_only["sse_terminal_seen"])
        self.assertEqual(blank_only["completion_ms"], 9)
        self.assertEqual(blank_only["visible_utf8_bytes"],
                         len(invisible.encode("utf-8")))
        self.assertEqual(blank_only["visible_text_sha256"],
                         hashlib.sha256(invisible.encode("utf-8")).hexdigest())
        resumed = measure_openai_sse_wire([
            (2, frame(invisible)), (5, frame(visible)),
            (7, stop), (9, done)])
        self.assertEqual(resumed["first_text_ms"], 5)
        self.assertEqual(resumed["completion_ms"], 9)
        self.assertTrue(resumed["wire_completed_normally"])
        self.assertEqual(resumed["visible_text_sha256"],
                         hashlib.sha256((invisible + visible).encode("utf-8")).hexdigest())

    def test_sse_wire_choice_index_must_be_zero_when_present(self):
        # A one-choice response with index=1 belongs to a different choice;
        # bool/float/string indices must not pass integer equality for zero.
        delta = {"content": "ready"}
        finish = {"delta": {}, "finish_reason": "stop"}
        done = b"data: [DONE]\n\n"
        def frame(choice):
            return ("data: " + json.dumps(
                {"choices": [choice]}) + "\n\n").encode("utf-8")
        for bad_index in (-1, 1, True, False, 0.0, "0", None):
            with self.subTest(index=bad_index):
                bad = {"index": bad_index, "delta": delta,
                       "finish_reason": None}
                with self.assertRaisesRegex(
                        ReceiptHold, "SSE_CHOICE_INDEX_SCHEMA"):
                    measure_openai_sse_wire([(2, frame(bad)),
                                             (5, frame({"index": 0, **finish})),
                                             (7, done)])
        # Explicitly correct index and historic index-absent receipts remain
        # usable, with preserved first visible text and terminal clock.
        for with_index in (True, False):
            with self.subTest(with_index=with_index):
                content = {"delta": delta, "finish_reason": None}
                last = dict(finish)
                if with_index:
                    content["index"] = 0
                    last["index"] = 0
                receipt = measure_openai_sse_wire([
                    (2, frame(content)), (5, frame(last)), (7, done)])
                self.assertTrue(receipt["wire_completed_normally"])
                self.assertEqual(receipt["first_text_ms"], 2)
                self.assertEqual(receipt["completion_ms"], 7)
                self.assertEqual(receipt["visible_text_sha256"],
                                 hashlib.sha256(b"ready").hexdigest())

    def test_sse_wire_unsupported_named_event_cannot_forge_finality(self):
        # EventSource delivers named events separately from default/message.
        # They are not trusted chat/completions data even if the bytes match.
        visible = b'data: {"choices":[{"delta":{"content":"ready"},"finish_reason":null}]}\n\n'
        stop = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        done = b"data: [DONE]\n\n"
        for named in (b"event: ping\n", b"event: status\n",
                      b"event: done\n", b"event: error \n"):
            with self.subTest(event=named):
                # Pretending that [DONE] is a model terminal is fail-closed.
                with self.assertRaisesRegex(
                        ReceiptHold, "SSE_UNSUPPORTED_EVENT_TYPE"):
                    measure_openai_sse_wire([
                        (3, visible), (5, stop), (7, named + done)])
                # Nor can non-message events impersonate a visible delta.
                with self.assertRaisesRegex(
                        ReceiptHold, "SSE_UNSUPPORTED_EVENT_TYPE"):
                    measure_openai_sse_wire([(2, named + visible)])

        valid = [(2, b"event: message\n" + visible),
                 (5, b"event: message\n" + stop),
                 (7, b"event: message\n" + done)]
        result = measure_openai_sse_wire(valid)
        self.assertTrue(result["wire_completed_normally"])
        self.assertEqual(result["first_text_ms"], 2)
        self.assertEqual(result["completion_ms"], 7)
        self.assertEqual(result["raw_wire_sha256"],
                         hashlib.sha256(b"".join(data for _, data in valid)).hexdigest())

    def test_sse_wire_explicit_error_event_never_forges_terminal(self):
        # OpenAI-compatible stream payloads are default/message SSE events.
        # event: error is an error signal, even if payload impersonates
        # a valid-looking [DONE] or a successful model chunk.
        visible = b'data: {"choices":[{"delta":{"content":"ready"},"finish_reason":null}]}\n\n'
        stop = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        done = b'data: [DONE]\n\n'
        valid = [(3, b"event: message\n" + visible), (5, stop), (7, done)]
        measured = measure_openai_sse_wire(valid)
        self.assertTrue(measured["wire_completed_normally"])
        self.assertEqual(measured["first_text_ms"], 3)
        self.assertEqual(measured["completion_ms"], 7)
        self.assertEqual(measured["raw_wire_sha256"],
                         hashlib.sha256(b"".join(chunk for _, chunk in valid)).hexdigest())

        for error_line in (b"event: error\n", b"event:error\n"):
            with self.subTest(error_line=error_line):
                with self.assertRaisesRegex(ReceiptHold, "SSE_ERROR_EVENT"):
                    measure_openai_sse_wire([
                        (3, visible), (5, stop),
                        (7, error_line + done)])
                # An error event without data is still a failure, never a
                # harmless heartbeat that a later [DONE] could supersede.
                with self.assertRaisesRegex(ReceiptHold, "SSE_ERROR_EVENT"):
                    measure_openai_sse_wire([
                        (3, visible), (5, stop),
                        (6, error_line), (7, done)])

    def test_sse_nonspacing_marks_are_not_first_visible_text(self):
        # Python marks the combining grapheme joiner, variation selector and
        # other Unicode marks printable, despite no independent visible glyph.
        marks = "\u034f\ufe0f\u0301\u0488"
        def frame(text):
            return ("data: " + json.dumps(
                {"choices": [{"delta": {"content": text},
                               "finish_reason": None}]}) + "\n\n").encode("ascii")
        stop = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        done = b"data: [DONE]\n\n"
        invisible_only = measure_openai_sse_wire([
            (2, frame(marks)), (5, stop), (8, done)])
        self.assertIsNone(invisible_only["first_text_ms"])
        self.assertFalse(invisible_only["wire_completed_normally"])
        self.assertEqual(invisible_only["completion_ms"], 8)
        self.assertEqual(invisible_only["visible_text_sha256"],
                         hashlib.sha256(marks.encode("utf-8")).hexdigest())
        visible = measure_openai_sse_wire([
            (2, frame(marks)), (4, frame("Привет, ¡hola! 😀")),
            (5, stop), (8, done)])
        self.assertEqual(visible["first_text_ms"], 4)
        self.assertEqual(visible["completion_ms"], 8)
        self.assertTrue(visible["wire_completed_normally"])
        self.assertEqual(visible["visible_text_sha256"],
                         hashlib.sha256((marks + "Привет, ¡hola! 😀").encode()).hexdigest())



    def test_bound_post_done_partial_eof_is_failed_chat_not_valid_speedup(self):
        # [DONE] and stop are insufficient when EOF contains a partial
        # undelivered next frame. Never score a valid completed turn.
        frames = [
            (5, b'data: {"choices":[{"delta":{"content":"ready"},"finish_reason":null}]}\n\n'),
            (8, b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'),
            (10, b'data: [DONE]\n\n'),
        ]
        clean = measure_openai_sse_wire(frames)
        incomplete = measure_openai_sse_wire(frames + [(18, b'data: {"choices":')])
        self.assertTrue(clean["wire_completed_normally"])
        self.assertTrue(incomplete["sse_terminal_seen"])
        self.assertEqual(incomplete["model_finish_reason"], "stop")
        self.assertTrue(incomplete["partial_frame_at_eof"])
        self.assertFalse(incomplete["wire_completed_normally"])

        def bound_run(wire):
            run = example()
            run["sse_binding_required"] = True
            run["declared_task_ids"] = ["t1"]
            run["outcomes"] = [run["outcomes"][0]]
            row = run["outcomes"][0]
            row.update(first_text_ms=5, latency_ms=20,
                       trace_sha256=wire["timed_trace_sha256"],
                       sse_wire_witness=wire,
                       sse_raw_wire_sha256=wire["raw_wire_sha256"],
                       sse_visible_text_sha256=wire["visible_text_sha256"])
            return run

        out = compare_paired(bound_run(clean), bound_run(incomplete))
        self.assertTrue(out["comparable"])
        self.assertEqual(out["baseline"]["passed"], 1)
        self.assertEqual(out["candidate"]["passed"], 0)
        self.assertEqual(out["candidate"]["reported_pass_without_usable_chat"], 1)
        self.assertEqual(out["candidate"]["sse_normal_completion"], 0)
        self.assertEqual(out["sse_normal_completion_regressed_task_ids"], ["t1"])
        self.assertEqual(out["sse_finality_changed_task_ids"], ["t1"])
        self.assertTrue(out["sse_reliability_regression"])
        self.assertTrue(out["quality_or_history_regression"])
        self.assertTrue(out["latency_observed_workload_confounder"])
        self.assertIsNone(out["p95_latency_delta_ms_same_observed_work"])

    def test_strict_sse_witness_binding_prevents_detached_timing_and_finality(self):
        # Synthetic source-only witness, not authenticated browser/S03 proof.
        chunks = [
            (5, b'data: {"choices":[{"delta":{"content":"ready"},"finish_reason":null}]}\n\n'),
            (8, b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'),
            (10, b'data: [DONE]\n\n'),
        ]
        wire = measure_openai_sse_wire(chunks)
        b = example()
        b["declared_task_ids"] = ["t1"]
        b["outcomes"] = [b["outcomes"][0]]
        b["sse_binding_required"] = True
        row = b["outcomes"][0]
        row.update(first_text_ms=5, trace_sha256=wire["timed_trace_sha256"],
                   sse_wire_witness=wire,
                   sse_raw_wire_sha256=wire["raw_wire_sha256"],
                   sse_visible_text_sha256=wire["visible_text_sha256"])
        self.assertTrue(compare_paired(b, copy.deepcopy(b))["comparable"])
        for field, bad, reason in (
                ("first_text_ms", 6, "SSE_WITNESS_TTFT_MISMATCH"),
                ("trace_sha256", H, "SSE_WITNESS_TRACE_MISMATCH"),
                ("sse_raw_wire_sha256", H, "SSE_WITNESS_HASH_MISMATCH"),
                ("sse_terminal_seen", False, "SSE_WITNESS_FINALITY_MISMATCH"),
                ("model_finish_reason", "length", "SSE_WITNESS_FINALITY_MISMATCH"),
                ("latency_ms", 9, "SSE_WITNESS_COMPLETION_MISMATCH")):
            with self.subTest(field=field):
                altered = copy.deepcopy(b)
                altered["outcomes"][0][field] = bad
                self.assertEqual(compare_paired(b, altered)["reason"], reason)
        missing = copy.deepcopy(b)
        del missing["outcomes"][0]["sse_wire_witness"]
        self.assertEqual(compare_paired(b, missing)["reason"], "SSE_WITNESS_REQUIRED")
        inconsistent = copy.deepcopy(b)
        inconsistent["outcomes"][0]["sse_wire_witness"]["wire_completed_normally"] = False
        self.assertEqual(compare_paired(b, inconsistent)["reason"],
                         "SSE_WITNESS_NORMALITY_MISMATCH")
        optional = copy.deepcopy(b)
        del optional["sse_binding_required"]
        self.assertEqual(compare_paired(b, optional)["reason"],
                         "EVALUATION_PROTOCOL_MISMATCH")

    def test_strict_sse_witness_walltime_must_cover_last_received_byte(self):
        # A [DONE] at 10 ms may be followed by heartbeat bytes at 18 ms.
        # Reporting 12 ms total latency would detach walltime from raw trace
        # even though TTFT, finality, [DONE] and all hashes agree.
        chunks = [
            (5, b'data: {"choices":[{"delta":{"content":"ready"},"finish_reason":null}]}\n\n'),
            (8, b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'),
            (10, b'data: [DONE]\n\n'),
            (18, b': heartbeat\n\n'),
        ]
        wire = measure_openai_sse_wire(chunks)
        self.assertTrue(wire["wire_completed_normally"])
        self.assertEqual(wire["completion_ms"], 10)
        self.assertEqual(wire["last_byte_ms"], 18)
        baseline = example()
        baseline["declared_task_ids"] = ["t1"]
        baseline["outcomes"] = [baseline["outcomes"][0]]
        baseline["sse_binding_required"] = True
        event = baseline["outcomes"][0]
        event.update(latency_ms=18, first_text_ms=5,
                     trace_sha256=wire["timed_trace_sha256"],
                     sse_wire_witness=wire,
                     sse_raw_wire_sha256=wire["raw_wire_sha256"],
                     sse_visible_text_sha256=wire["visible_text_sha256"])
        self.assertTrue(compare_paired(baseline, copy.deepcopy(baseline))["comparable"])
        forged = copy.deepcopy(baseline)
        forged["outcomes"][0]["latency_ms"] = 12
        self.assertEqual(compare_paired(baseline, forged)["reason"],
                         "SSE_WITNESS_LAST_BYTE_MISMATCH")
        impossible = copy.deepcopy(baseline)
        impossible["outcomes"][0]["sse_wire_witness"]["last_byte_ms"] = 9
        self.assertEqual(compare_paired(baseline, impossible)["reason"],
                         "SSE_WITNESS_LAST_BYTE_MISMATCH")
        untyped = copy.deepcopy(baseline)
        untyped["outcomes"][0]["sse_wire_witness"]["last_byte_ms"] = True
        self.assertEqual(compare_paired(baseline, untyped)["reason"],
                         "SSE_WITNESS_LAST_BYTE_MISMATCH")


    def test_two_turn_offline_sse_capture_fail_closed(self):
        # Real wire bytes with two separately measured streams; fixture is
        # offline only and cannot prove a browser POST or canonical S03 rows.
        visible = (b'data: {"choices":[{"delta":{"content":"listo"},'
                   b'"finish_reason":null}]}\n\n')
        finish = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        done = b'data: [DONE]\n\n'
        def turn(number, exchange, at):
            return {"turn_number": number, "dialog_id": "dialog-1",
                    "exchange_id": exchange, "route_sha256": "a" * 64,
                    "model_sha256": "b" * 64,
                    "timed_chunks": [(at, visible), (at + 2, finish),
                                     (at + 4, done)]}
        pair = [turn(1, "exchange-1", 5), turn(2, "exchange-2", 9)]
        good = measure_two_turn_openai_sse_capture(pair)
        self.assertEqual([x["first_text_ms"] for x in good["turns"]], [5, 9])
        self.assertEqual([x["completion_ms"] for x in good["turns"]], [9, 13])
        self.assertEqual(good["state"], "OFFLINE_SOURCE_TRACE_CONSISTENT_ONLY")
        self.assertFalse(good["browser_authenticated"])
        self.assertFalse(good["native_verified"])
        self.assertFalse(good["s03_durable_verified"])
        self.assertFalse(good["one_model_post_per_turn_verified"])
        tamper = [
            (lambda t: t.pop(), "SSE_TWO_TURN_COUNT"),
            (lambda t: t[1].update(turn_number=1), "SSE_TWO_TURN_ORDER"),
            (lambda t: t[1].update(exchange_id="exchange-1"),
             "SSE_TWO_TURN_EXCHANGE"),
            (lambda t: t[1].update(dialog_id="dialog-2"),
             "SSE_TWO_TURN_IDENTITY_DRIFT"),
            (lambda t: t[1].update(route_sha256="c" * 64),
             "SSE_TWO_TURN_IDENTITY_DRIFT"),
            (lambda t: t[1].update(model_sha256="c" * 64),
             "SSE_TWO_TURN_IDENTITY_DRIFT"),
            (lambda t: t[1].update(model_sha256="wrong"),
             "SSE_TWO_TURN_PINS"),
            (lambda t: t[1].update(timed_chunks=[
                (9, visible), (11, finish), (13, b"data: [DONE]\n")]),
             "SSE_TWO_TURN_NOT_CLEAN"),
        ]
        for corrupt, reason in tamper:
            item = copy.deepcopy(pair)
            corrupt(item)
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ReceiptHold, reason):
                    measure_two_turn_openai_sse_capture(item)


    def test_two_turn_posted_history_binds_first_assistant_sse_text(self):
        # Real parser, two raw SSE streams and two raw outbound request bodies.
        # Does not assert browser authentication or independent S03 persistence.
        frame = lambda content: (b'data: {"choices":[{"delta":{"content":"'
                                 + content + b'"},"finish_reason":null}]}\n\n')
        finish = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        done = b'data: [DONE]\n\n'
        def turn(n, exchange, word):
            return {"turn_number": n, "dialog_id": "same",
                    "exchange_id": exchange, "route_sha256": "a" * 64,
                    "model_sha256": "b" * 64,
                    "timed_chunks": [(5, frame(word)), (9, finish), (11, done)]}
        turns = [turn(1, "ex1", b"hola"), turn(2, "ex2", b"listo")]
        capture = measure_two_turn_openai_sse_capture(turns)
        history = [{"role": "system", "content": "smoke"},
                   {"role": "user", "content": "hola"}]
        requests = [
            {"model": "same-model", "messages": history},
            {"model": "same-model", "messages": copy.deepcopy(history) +
             [{"role": "assistant", "content": "hola"},
              {"role": "user", "content": "sigue"}]},
        ]
        def attach(reqs):
            return [dict(t, posted_request_body=json.dumps(
                obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                for t, obj in zip(turns, reqs)]
        valid = verify_two_turn_openai_posted_history(attach(requests), capture)
        self.assertEqual(valid["state"],
                         "OFFLINE_REQUEST_AND_SSE_SOURCE_CONSISTENT_ONLY")
        self.assertEqual(len(valid["posted_request_sha256"]), 2)
        self.assertEqual(valid["first_assistant_visible_sha256"],
                         capture["turns"][0]["wire_witness"]["visible_text_sha256"])
        self.assertFalse(valid["browser_authenticated"])
        self.assertFalse(valid["native_verified"])
        self.assertFalse(valid["s03_durable_verified"])
        self.assertFalse(valid["one_model_post_per_turn_verified"])
        changes = [
            (lambda r: r[1].update(model="different"),
             "SSE_TWO_TURN_REQUEST_MODEL_DRIFT"),
            (lambda r: r[1]["messages"][0].update(content="different"),
             "SSE_TWO_TURN_HISTORY_PREFIX"),
            (lambda r: r[1]["messages"][-2].update(content="fake"),
             "SSE_TWO_TURN_HISTORY_HASH_MISMATCH"),
            (lambda r: r[1]["messages"].pop(-2),
             "SSE_TWO_TURN_HISTORY_ORDER"),
            (lambda r: r[1]["messages"][-1].update(content=""),
             "SSE_TWO_TURN_HISTORY_ORDER"),
        ]
        for change, code in changes:
            broken = copy.deepcopy(requests)
            change(broken)
            with self.subTest(code=code):
                with self.assertRaisesRegex(ReceiptHold, code):
                    verify_two_turn_openai_posted_history(attach(broken), capture)
        duplicate = attach(requests)
        duplicate[1]["posted_request_body"] = (
            b'{"model":"same-model","model":"other","messages":[]}')
        with self.assertRaisesRegex(ReceiptHold,
                                    "SSE_TWO_TURN_REQUEST_DUPLICATE_KEY"):
            verify_two_turn_openai_posted_history(duplicate, capture)
        wrong_exchange = attach(requests)
        wrong_exchange[1]["exchange_id"] = "ex1"
        with self.assertRaisesRegex(ReceiptHold,
                                    "SSE_TWO_TURN_REQUEST_EXCHANGE"):
            verify_two_turn_openai_posted_history(wrong_exchange, capture)


    def test_two_turn_http_trace_binds_request_and_sse_without_auth_claim(self):
        frame = lambda word: (
            b'data: {"choices":[{"delta":{"content":"' + word +
            b'"},"finish_reason":null}]}\n\n')
        stop = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        done = b'data: [DONE]\n\n'
        turns = []
        for n, exchange, word in ((1, "ex1", b"hola"),
                                  (2, "ex2", b"listo")):
            turns.append({
                "turn_number": n, "dialog_id": "same-dialog",
                "exchange_id": exchange, "route_sha256": "a" * 64,
                "model_sha256": "b" * 64,
                "timed_chunks": [(5, frame(word)), (9, stop), (11, done)]})
        history = [{"role": "system", "content": "smoke"},
                   {"role": "user", "content": "hola"}]
        requests = [
            {"model": "same-model", "messages": history},
            {"model": "same-model", "messages": copy.deepcopy(history) + [
                {"role": "assistant", "content": "hola"},
                {"role": "user", "content": "sigue"}]},
        ]
        for turn, request in zip(turns, requests):
            turn["posted_request_body"] = json.dumps(
                request, separators=(",", ":")).encode()
        capture = measure_two_turn_openai_sse_capture(turns)
        trace = []
        for idx, turn in enumerate(turns):
            witness = capture["turns"][idx]["wire_witness"]
            start = 1000 + 1000 * idx
            trace.append({
                "turn_number": idx + 1, "exchange_id": turn["exchange_id"],
                "network_event_id": "network-" + str(idx + 1),
                "method": "POST", "target_path": "/nox/chat",
                "request_content_type": "application/json",
                "response_content_type": "text/event-stream",
                "response_status": 200,
                "request_body_sha256": hashlib.sha256(
                    turn["posted_request_body"]).hexdigest(),
                "response_wire_sha256": witness["raw_wire_sha256"],
                "response_timed_trace_sha256": witness["timed_trace_sha256"],
                "request_sent_monotonic_ms": start,
                "response_first_byte_monotonic_ms": start + 3,
                "response_closed_monotonic_ms": start + 16,
            })
        valid = verify_two_turn_http_trace_envelope(
            turns, capture, trace, "/nox/chat")
        self.assertEqual(valid["schema"],
                         "NOX_B4_TWO_TURN_HTTP_TRACE_ENVELOPE_V1")
        self.assertEqual(len(valid["turns"]), 2)
        self.assertEqual(len(valid["trace_metadata_sha256"]), 64)
        self.assertFalse(valid["browser_authenticated"])
        self.assertFalse(valid["independent_network_trace_verified"])
        self.assertFalse(valid["native_verified"])
        self.assertFalse(valid["s03_durable_verified"])
        self.assertFalse(valid["one_model_post_per_turn_verified"])
        violations = [
            ("request_body_sha256", "f" * 64,
             "SSE_HTTP_TRACE_DIGEST_MISMATCH"),
            ("response_wire_sha256", "f" * 64,
             "SSE_HTTP_TRACE_DIGEST_MISMATCH"),
            ("response_timed_trace_sha256", "f" * 64,
             "SSE_HTTP_TRACE_DIGEST_MISMATCH"),
            ("network_event_id", "network-1",
             "SSE_HTTP_TRACE_EVENT_ID"),
            ("method", "GET", "SSE_HTTP_TRACE_REQUEST"),
            ("response_status", 503, "SSE_HTTP_TRACE_RESPONSE"),
            ("response_content_type", "application/json",
             "SSE_HTTP_TRACE_RESPONSE"),
            ("request_sent_monotonic_ms", 1010,
             "SSE_HTTP_TRACE_CLOCK_MISMATCH"),
            ("response_closed_monotonic_ms", 2004,
             "SSE_HTTP_TRACE_CLOCK_MISMATCH"),
        ]
        for field, value, reason in violations:
            broken = copy.deepcopy(trace)
            broken[1][field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ReceiptHold, reason):
                    verify_two_turn_http_trace_envelope(
                        turns, capture, broken, "/nox/chat")
        forged_sse = copy.deepcopy(capture)
        forged_sse["turns"][0]["first_text_ms"] = 0
        with self.assertRaisesRegex(
                ReceiptHold, "SSE_HTTP_TRACE_CAPTURE_MISMATCH"):
            verify_two_turn_http_trace_envelope(
                turns, forged_sse, trace, "/nox/chat")
        with self.assertRaisesRegex(
                ReceiptHold, "SSE_HTTP_TARGET_POLICY"):
            verify_two_turn_http_trace_envelope(
                turns, capture, trace, "//fake/../nox/chat")



class CdpReceiptCrosscheckTests(unittest.TestCase):
    def test_strict_cdp_vs_http_and_real_sse_parser_synthetic(self):
        frame = lambda word: (
            b'data: {"choices":[{"delta":{"content":"' + word +
            b'"},"finish_reason":null}]}\n\n')
        stop = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        done = b'data: [DONE]\n\n'
        turns = []
        for n, exchange, word in ((1, "ex1", b"hola"),
                                  (2, "ex2", b"listo")):
            turns.append({
                "turn_number": n, "dialog_id": "same-dialog",
                "exchange_id": exchange, "route_sha256": "a" * 64,
                "model_sha256": "b" * 64,
                "timed_chunks": [(5, frame(word)), (9, stop), (11, done)]})
        prefix = [{"role": "system", "content": "smoke"},
                  {"role": "user", "content": "hola"}]
        requests = [
            {"model": "same-model", "messages": prefix},
            {"model": "same-model", "messages": copy.deepcopy(prefix) + [
                {"role": "assistant", "content": "hola"},
                {"role": "user", "content": "sigue"}]},
        ]
        for turn, request in zip(turns, requests):
            turn["posted_request_body"] = json.dumps(
                request, separators=(",", ":")).encode()
        capture = measure_two_turn_openai_sse_capture(turns)
        network, cdp_turns = [], []
        for i, turn in enumerate(turns):
            wire = capture["turns"][i]["wire_witness"]
            sent = 1000 * (i + 1)
            req_sha = hashlib.sha256(
                turn["posted_request_body"]).hexdigest()
            event_id = "network-" + str(i + 1)
            network.append({
                "turn_number": i + 1, "exchange_id": turn["exchange_id"],
                "network_event_id": event_id, "method": "POST",
                "target_path": "/nox/chat",
                "request_content_type": "application/json",
                "response_content_type": "text/event-stream",
                "response_status": 200,
                "request_body_sha256": req_sha,
                "response_wire_sha256": wire["raw_wire_sha256"],
                "response_timed_trace_sha256": wire["timed_trace_sha256"],
                "request_sent_monotonic_ms": sent,
                "response_first_byte_monotonic_ms": sent + 3,
                "response_closed_monotonic_ms": sent + 16,
            })
            cdp_turns.append({
                "turn": i + 1, "cdp_request_id": event_id,
                "request_sha256": req_sha,
                "cdp_decoded_body_sha256": wire["raw_wire_sha256"],
                "status": 200, "mime": "text/event-stream",
                "first_network_byte_ms": 3, "ttft_ms": 5,
                "sse_done_ms": 11, "close_ms": 16,
                "stream_timing_complete": True,
            })
        cdp = {
            "schema": "nox-b4-cdp-v1", "cdp_consistent": True,
            "ttft_sse_verified": True,
            "browser_authenticated": False, "remote_attested": False,
            "native_verified": False, "canonical_s03_verified": False,
            "one_model_post_per_turn_verified": False,
            "tcp_wire_verified": False, "turns": cdp_turns,
        }
        verify = lambda receipt: verify_cdp_receipt_against_http_trace(
            turns, capture, network, "/nox/chat", receipt)
        result = verify(cdp)
        self.assertEqual(result["turns_checked"], 2)
        self.assertEqual(len(result["cdp_metadata_sha256"]), 64)
        self.assertFalse(result["browser_authenticated"])
        self.assertFalse(result["native_verified"])
        self.assertFalse(result["promotion_authorized"])
        for field, value, error in [
            ("stream_timing_complete", False, "SSE_CDP_UNMEASURED"),
            ("status", 503, "SSE_CDP_HTTP_RESPONSE"),
            ("mime", "application/json", "SSE_CDP_HTTP_RESPONSE"),
            ("request_sha256", "f" * 64, "SSE_CDP_DIGEST_MISMATCH"),
            ("cdp_decoded_body_sha256", "f" * 64,
             "SSE_CDP_DIGEST_MISMATCH"),
            ("first_network_byte_ms", 4, "SSE_CDP_TIMING_MISMATCH"),
            ("ttft_ms", 4, "SSE_CDP_TIMING_MISMATCH"),
            ("sse_done_ms", 10, "SSE_CDP_TIMING_MISMATCH"),
            ("close_ms", 15, "SSE_CDP_TIMING_MISMATCH"),
            ("cdp_request_id", "network-1", "SSE_CDP_EVENT_ID"),
            ("ttft_ms", True, "SSE_CDP_TIMING_SCHEMA"),
            ("sse_done_ms", None, "SSE_CDP_TIMING_SCHEMA"),
        ]:
            with self.subTest(field=field, value=value):
                bad = copy.deepcopy(cdp)
                bad["turns"][1][field] = value
                with self.assertRaisesRegex(ReceiptHold, error):
                    verify(bad)
        for field, value, error in [
            ("ttft_sse_verified", False, "SSE_CDP_UNMEASURED"),
            ("cdp_consistent", False, "SSE_CDP_UNMEASURED"),
            ("remote_attested", True, "SSE_CDP_TRUST_FLAG"),
            ("native_verified", True, "SSE_CDP_TRUST_FLAG"),
        ]:
            with self.subTest(field=field):
                bad = copy.deepcopy(cdp)
                bad[field] = value
                with self.assertRaisesRegex(ReceiptHold, error):
                    verify(bad)
        with self.assertRaisesRegex(ReceiptHold, "SSE_CDP_RECEIPT_SCHEMA"):
            verify({"schema": "nox-b4-cdp-v1", "turns": []})


if __name__ == '__main__': unittest.main()
