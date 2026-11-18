"""Read-only, paired NOX benchmark receipt comparator.

Does not run models or authorize deployment, rank claims, training, or promotion.
All declared tasks, including failures and timeouts, remain in the denominator.
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
        _require(_integer(event.get("latency_ms"), run["max_task_ms"]),
                 "INVALID_LATENCY")
        _require(_integer(event.get("peak_rss_bytes"), 2 ** 63 - 1)
                 and _integer(event.get("output_tokens"), 10 ** 10), "INVALID_RESOURCE")
        _require(type(event.get("history_saved")) is bool
                 and type(event.get("background_completed")) is bool,
                 "MISSING_QUALITY_OR_BACKGROUND_PROOF")
        _require(type(event.get("trace_sha256")) is str
                 and SHA.fullmatch(event["trace_sha256"]), "TRACE_PIN")
        mapped[task] = event
    _require(set(mapped) == task_ids, "TASK_SET_MISMATCH")
    return mapped


def _p95(values):
    values = sorted(values)
    return values[math.ceil(.95 * len(values)) - 1]  # nearest rank, every task


def _metrics(events):
    rows = list(events.values())
    n = len(rows)
    return {
        "denominator": n,
        "passed": sum(row["status"] == "PASS" for row in rows),
        "failures_including_timeouts": sum(row["status"] != "PASS" for row in rows),
        "timed_out_or_exhausted": sum(row["status"] in ("TIMEOUT", "BUDGET_EXHAUSTED") for row in rows),
        "history_saved": sum(row["history_saved"] for row in rows),
        "background_completed": sum(row["background_completed"] for row in rows),
        "p95_latency_ms_all_tasks": _p95([row["latency_ms"] for row in rows]),
        "total_output_tokens": sum(row["output_tokens"] for row in rows),
        "peak_rss_bytes_max": max(row["peak_rss_bytes"] for row in rows),
    }


def compare_paired(baseline, candidate):
    """Compare two independently verified receipts for exactly the same tasks.

    Errors yield HOLD rather than an optimistic partial score. Latency includes
    failed/timed-out runs and uses nearest-rank p95; no Arena or TOP30 mapping.
    """
    answer = {"schema": "NOX_B4_PAIRED_COMPARISON_V1", "comparable": False,
              "promotion_authorized": False, "rank_claim_authorized": False,
              "measured_nox_gain": False}
    try:
        old = _validated(baseline)
        new = _validated(candidate)
        _require(all(baseline.get(key) == candidate.get(key) for key in CONTRACT),
                 "EVALUATION_PROTOCOL_MISMATCH")
        _require(baseline["declared_task_ids"] == candidate["declared_task_ids"],
                 "TASK_ORDER_MISMATCH")
    except ReceiptHold as err:
        return {**answer, "state": "HOLD", "reason": str(err)}
    before, after = _metrics(old), _metrics(new)
    fixed = [task for task in baseline["declared_task_ids"]
             if old[task]["status"] != "PASS" and new[task]["status"] == "PASS"]
    regressed = [task for task in baseline["declared_task_ids"]
                 if old[task]["status"] == "PASS" and new[task]["status"] != "PASS"]
    return {**answer, "comparable": True, "state": "DESCRIPTIVE_ONLY",
            "reason": None, "baseline": before, "candidate": after,
            "fixed_task_ids": fixed, "regressed_task_ids": regressed,
            "pass_rate_delta": (after["passed"] - before["passed"]) / before["denominator"],
            "p95_latency_delta_ms": (after["p95_latency_ms_all_tasks"]
                                     - before["p95_latency_ms_all_tasks"]),
            "quality_or_history_regression": bool(regressed or any(
                (old[task]["history_saved"] and not new[task]["history_saved"]) or
                (old[task]["background_completed"] and not new[task]["background_completed"])
                for task in baseline["declared_task_ids"]))}
