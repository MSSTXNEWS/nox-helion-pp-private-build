"""Read-only, paired NOX benchmark receipt comparator.

Does not run models or authorize deployment, rank claims, training, or promotion.
All declared tasks, including failures and timeouts, remain in the denominator.
The independently assembled full input must match the bytes actually sent to serving.
Streaming first-text coverage and llama.cpp KV-cache timings must be accounted for,
otherwise a fast aggregate can hide a no-text response or a cold-cache regression.
"""
from __future__ import annotations
import math
import re

SHA = re.compile(r"[0-9a-f]{64}\Z")
OUTCOMES = frozenset({"PASS", "FAIL", "TIMEOUT", "BUDGET_EXHAUSTED", "ERROR"})
CONTRACT = ("benchmark_id", "benchmark_revision", "task_split_sha256",
            "verifier_sha256", "harness_sha256", "budget_policy_sha256",
            "environment_sha256", "denominator_kind", "max_task_ms")
PINS = ("task_split_sha256", "verifier_sha256", "harness_sha256",
        "budget_policy_sha256", "environment_sha256", "artifact_sha256",
        "evaluation_receipt_sha256")


class ReceiptHold(ValueError):
    """Fail-closed contract mismatch; nothing has been promoted."""


def _require(condition, code):
    if not condition:
        raise ReceiptHold(code)


def _integer(value, maximum):
    return type(value) is int and 0 <= value <= maximum


def _validated(run):
    _require(isinstance(run, dict), "RUN_SCHEMA")
    _require(run.get("native_verified") is True and run.get("holdout_isolated") is True,
             "INDEPENDENT_VERIFICATION_REQUIRED")
    _require(run.get("all_declared_tasks_accounted") is True,
             "INCOMPLETE_DENOMINATOR")
    _require(run.get("denominator_kind") == "ONE_OUTCOME_PER_DECLARED_TASK",
             "DENOMINATOR_KIND")
    _require(all(type(run.get(key)) is str and SHA.fullmatch(run[key]) for key in PINS),
             "SOURCE_OR_RECEIPT_PIN")
    _require(all(type(run.get(key)) is str and 1 <= len(run[key]) <= 160
                 for key in ("benchmark_id", "benchmark_revision")), "BENCHMARK_ID")
    _require(_integer(run.get("max_task_ms"), 86_400_000) and run["max_task_ms"] > 0,
             "TASK_BUDGET")
    tasks = run.get("declared_task_ids")
    _require(isinstance(tasks, list) and 1 <= len(tasks) <= 10000
             and all(type(task) is str and 1 <= len(task) <= 160 for task in tasks),
             "TASK_SET")
    task_ids = set(tasks)
    _require(len(task_ids) == len(tasks), "TASK_SET")
    events = run.get("outcomes")
    _require(isinstance(events, list) and len(events) == len(tasks), "OUTCOME_COUNT")
    mapped = {}
    for event in events:
        _require(isinstance(event, dict), "OUTCOME_SCHEMA")
        task = event.get("task_id")
        _require(type(task) is str and task in task_ids and task not in mapped,
                 "MISSING_OR_DUPLICATE_TASK")
        _require(type(event.get("status")) is str and event["status"] in OUTCOMES, "UNKNOWN_STATUS")
        _require(_integer(event.get("latency_ms"), 86_400_000),
                 "INVALID_LATENCY")
        _require(_integer(event.get("peak_rss_bytes"), 2 ** 63 - 1)
                 and _integer(event.get("output_tokens"), 10 ** 10), "INVALID_RESOURCE")
        _require(type(event.get("history_saved")) is bool
                 and type(event.get("background_completed")) is bool,
                 "MISSING_QUALITY_OR_BACKGROUND_PROOF")
        _require(type(event.get("trace_sha256")) is str
                 and SHA.fullmatch(event["trace_sha256"]), "TRACE_PIN")
        _require(all(type(event.get(key)) is str and SHA.fullmatch(event[key])
                     for key in ("expected_full_input_sha256", "served_full_input_sha256")),
                 "FULL_INPUT_PIN")
        _require(event["expected_full_input_sha256"] == event["served_full_input_sha256"],
                 "INPUT_TRUNCATED_OR_MODIFIED")
        # An explicit None means no user-visible text arrived; do not substitute
        # completion latency and falsely report a good first-text latency.
        _require("first_text_ms" in event and
                 (event["first_text_ms"] is None or
                  _integer(event["first_text_ms"], 86_400_000)),
                 "FIRST_TEXT_PROOF")
        _require(event["first_text_ms"] is None or
                 event["first_text_ms"] <= event["latency_ms"], "FIRST_TEXT_AFTER_END")
        _require(all(_integer(event.get(key), 10 ** 10) for key in
                     ("cache_tokens_reused", "prompt_tokens_evaluated")),
                 "PROMPT_CACHE_TIMING_PROOF")
        mapped[task] = event
    _require(set(mapped) == task_ids, "TASK_SET_MISMATCH")
    return mapped


def _p95(values):
    values = sorted(values)
    return values[math.ceil(.95 * len(values)) - 1]  # nearest rank, every task


def _within_budget_pass(event, max_task_ms):
    """An asserted PASS that exceeded the task budget is not a scored PASS."""
    return event["status"] == "PASS" and event["latency_ms"] <= max_task_ms


def _metrics(events, max_task_ms):
    rows = list(events.values())
    n = len(rows)
    passed = sum(_within_budget_pass(row, max_task_ms) for row in rows)
    first_text = [row["first_text_ms"] for row in rows
                  if row["first_text_ms"] is not None]
    return {
        "denominator": n,
        "passed": passed,
        "failures_including_timeouts": n - passed,
        "timed_out_or_exhausted": sum(row["status"] in ("TIMEOUT", "BUDGET_EXHAUSTED") or
                                      (row["status"] == "PASS" and row["latency_ms"] > max_task_ms)
                                      for row in rows),
        "over_budget_reported_passes": sum(row["status"] == "PASS" and row["latency_ms"] > max_task_ms
                                          for row in rows),
        "over_budget_walltime": sum(row["latency_ms"] > max_task_ms for row in rows),
        "history_saved": sum(row["history_saved"] for row in rows),
        "background_completed": sum(row["background_completed"] for row in rows),
        "p95_latency_ms_all_tasks": _p95([row["latency_ms"] for row in rows]),
        "total_output_tokens": sum(row["output_tokens"] for row in rows),
        "first_text_observed": len(first_text),
        "first_text_missing": n - len(first_text),
        "p95_first_text_ms_observed_only": _p95(first_text) if first_text else None,
        "total_cache_tokens_reused": sum(row["cache_tokens_reused"] for row in rows),
        "total_prompt_tokens_evaluated": sum(row["prompt_tokens_evaluated"] for row in rows),
        "peak_rss_bytes_max": max(row["peak_rss_bytes"] for row in rows),
    }


def compare_paired(baseline, candidate):
    """Compare two independently verified receipts for exactly the same tasks.

    Errors yield HOLD rather than an optimistic partial score. Latency includes
    failed/timed-out runs and uses nearest-rank p95; no Arena or TOP30 mapping.
    """
    answer = {"schema": "NOX_B4_PAIRED_COMPARISON_V3", "comparable": False,
              "promotion_authorized": False, "rank_claim_authorized": False,
              "measured_nox_gain": False}
    try:
        old = _validated(baseline)
        new = _validated(candidate)
        _require(all(baseline.get(key) == candidate.get(key) for key in CONTRACT),
                 "EVALUATION_PROTOCOL_MISMATCH")
        _require(baseline["declared_task_ids"] == candidate["declared_task_ids"],
                 "TASK_ORDER_MISMATCH")
        _require(all(old[task]["expected_full_input_sha256"] ==
                     new[task]["expected_full_input_sha256"]
                     for task in baseline["declared_task_ids"]),
                 "FULL_INPUT_DIFFERENCE")
    except ReceiptHold as err:
        return {**answer, "state": "HOLD", "reason": str(err)}
    before, after = (_metrics(old, baseline["max_task_ms"]),
                     _metrics(new, candidate["max_task_ms"]))
    fixed = [task for task in baseline["declared_task_ids"]
             if not _within_budget_pass(old[task], baseline["max_task_ms"])
             and _within_budget_pass(new[task], candidate["max_task_ms"])]
    regressed = [task for task in baseline["declared_task_ids"]
                 if _within_budget_pass(old[task], baseline["max_task_ms"])
                 and not _within_budget_pass(new[task], candidate["max_task_ms"])]
    # Aggregate p95 and peak RSS can improve while individual owner tasks regress.
    # Preserve exact IDs for actionable diagnosis; this is descriptive only.
    latency_regressed = [task for task in baseline["declared_task_ids"]
                         if new[task]["latency_ms"] > old[task]["latency_ms"]]
    rss_regressed = [task for task in baseline["declared_task_ids"]
                     if new[task]["peak_rss_bytes"] > old[task]["peak_rss_bytes"]]
    # Aggregate cache_n/prompt_n deltas can cancel out across task IDs:
    # one dialogue loses its cached prefix while another gains reuse.
    # Mark such comparisons as cache-confounded, without claiming causality.
    cache_changed = [task for task in baseline["declared_task_ids"]
                     if (old[task]["cache_tokens_reused"] != new[task]["cache_tokens_reused"]
                         or old[task]["prompt_tokens_evaluated"] != new[task]["prompt_tokens_evaluated"])]
    cache_reuse_regressed = [task for task in baseline["declared_task_ids"]
                             if new[task]["cache_tokens_reused"] < old[task]["cache_tokens_reused"]]
    cache_reuse_lost = [task for task in baseline["declared_task_ids"]
                        if old[task]["cache_tokens_reused"] > 0 and
                        new[task]["cache_tokens_reused"] == 0]
    prefill_regressed = [task for task in baseline["declared_task_ids"]
                         if new[task]["prompt_tokens_evaluated"] >
                         old[task]["prompt_tokens_evaluated"]]
    first_text_lost = [task for task in baseline["declared_task_ids"]
                       if old[task]["first_text_ms"] is not None
                       and new[task]["first_text_ms"] is None]
    first_text_regressed = [task for task in baseline["declared_task_ids"]
                            if old[task]["first_text_ms"] is not None
                            and new[task]["first_text_ms"] is not None
                            and new[task]["first_text_ms"] > old[task]["first_text_ms"]]
    old_seen = [task for task in baseline["declared_task_ids"]
                if old[task]["first_text_ms"] is not None]
    new_seen = [task for task in baseline["declared_task_ids"]
                if new[task]["first_text_ms"] is not None]
    # Observed-only p95 is not comparable if the set of responses with text changed.
    first_text_p95_delta = (after["p95_first_text_ms_observed_only"] -
                            before["p95_first_text_ms_observed_only"]
                            if old_seen == new_seen and old_seen else None)
    return {**answer, "comparable": True, "state": "DESCRIPTIVE_ONLY",
            "reason": None, "baseline": before, "candidate": after,
            "fixed_task_ids": fixed, "regressed_task_ids": regressed,
            "latency_regressed_task_ids": latency_regressed,
            "peak_rss_regressed_task_ids": rss_regressed,
            "cache_state_changed_task_ids": cache_changed,
            "cache_reuse_regressed_task_ids": cache_reuse_regressed,
            "cache_reuse_lost_task_ids": cache_reuse_lost,
            "prompt_prefill_regressed_task_ids": prefill_regressed,
            "latency_cache_state_confounder": bool(cache_changed),
            "first_text_lost_task_ids": first_text_lost,
            "first_text_regressed_task_ids": first_text_regressed,
            "p95_first_text_delta_ms_same_coverage": first_text_p95_delta,
            "cache_tokens_reused_delta": (after["total_cache_tokens_reused"] -
                                          before["total_cache_tokens_reused"]),
            "prompt_tokens_evaluated_delta": (after["total_prompt_tokens_evaluated"] -
                                               before["total_prompt_tokens_evaluated"]),
            "peak_rss_delta_bytes": (after["peak_rss_bytes_max"]
                                     - before["peak_rss_bytes_max"]),
            "pass_rate_delta": (after["passed"] - before["passed"]) / before["denominator"],
            "p95_latency_delta_ms": (after["p95_latency_ms_all_tasks"]
                                     - before["p95_latency_ms_all_tasks"]),
            "quality_or_history_regression": bool(regressed or first_text_lost or any(
                (old[task]["history_saved"] and not new[task]["history_saved"]) or
                (old[task]["background_completed"] and not new[task]["background_completed"])
                for task in baseline["declared_task_ids"]))}
