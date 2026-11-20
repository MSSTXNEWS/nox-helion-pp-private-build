"""Read-only, paired NOX benchmark receipt comparator.

Does not run models or authorize deployment, rank claims, training, or promotion.
All declared tasks, including failures and timeouts, remain in the denominator.
The independently assembled full input must match the bytes actually sent to serving.
Streaming first-text coverage and llama.cpp KV-cache timings must be accounted for,
otherwise a fast aggregate can hide a no-text response or a cold-cache regression.
"""
from __future__ import annotations
import codecs
import hashlib
import json
import math
import re
import unicodedata

SHA = re.compile(r"[0-9a-f]{64}\Z")
OUTCOMES = frozenset({"PASS", "FAIL", "TIMEOUT", "BUDGET_EXHAUSTED", "ERROR"})
CONTRACT = ("benchmark_id", "benchmark_revision", "task_split_sha256",
            "verifier_sha256", "harness_sha256", "budget_policy_sha256",
            "environment_sha256", "denominator_kind", "max_task_ms",
            "sse_binding_required")
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



def _validate_sse_witness_binding(event):
    """Cross-check SSE wire timing and hashes against a paired outcome.

    Source consistency only: cannot authenticate browser, serving SHA or S03.
    """
    witness = event.get("sse_wire_witness")
    _require(isinstance(witness, dict) and
             witness.get("protocol") == "OPENAI_CHAT_COMPLETIONS_SSE_V1",
             "SSE_WITNESS_REQUIRED")
    for event_key, wire_key in (
            ("sse_raw_wire_sha256", "raw_wire_sha256"),
            ("sse_visible_text_sha256", "visible_text_sha256")):
        pin = event.get(event_key)
        seen = witness.get(wire_key)
        _require(type(pin) is str and SHA.fullmatch(pin) and
                 type(seen) is str and SHA.fullmatch(seen), "SSE_WITNESS_PIN")
        _require(pin == seen, "SSE_WITNESS_HASH_MISMATCH")
    timed = witness.get("timed_trace_sha256")
    _require(type(timed) is str and SHA.fullmatch(timed), "SSE_WITNESS_PIN")
    _require(event["trace_sha256"] == timed, "SSE_WITNESS_TRACE_MISMATCH")
    _require(witness.get("first_text_ms") == event["first_text_ms"] and
             type(witness.get("first_text_ms")) is type(event["first_text_ms"]),
             "SSE_WITNESS_TTFT_MISMATCH")
    _require(witness.get("sse_terminal_seen") is event["sse_terminal_seen"] and
             witness.get("model_finish_reason") == event["model_finish_reason"],
             "SSE_WITNESS_FINALITY_MISMATCH")
    end = witness.get("completion_ms")
    _require((end is None and not event["sse_terminal_seen"]) or
             (_integer(end, 86_400_000) and event["sse_terminal_seen"]
              and end <= event["latency_ms"]),
             "SSE_WITNESS_COMPLETION_MISMATCH")
    # [DONE] can arrive before later heartbeat bytes. The paired task's
    # claimed wall time must cover the ENTIRE observed wire, not just [DONE].
    # This is a source trace consistency fence, not live-host authentication.
    last_byte = witness.get("last_byte_ms")
    _require(_integer(last_byte, 86_400_000)
             and last_byte <= event["latency_ms"]
             and (end is None or end <= last_byte)
             and (event["first_text_ms"] is None or
                  event["first_text_ms"] <= last_byte),
             "SSE_WITNESS_LAST_BYTE_MISMATCH")
    _require(type(witness.get("partial_frame_at_eof")) is bool and
             type(witness.get("wire_completed_normally")) is bool and
             witness["wire_completed_normally"] is bool(
                 event["sse_terminal_seen"] and
                 event["model_finish_reason"] == "stop" and
                 event["first_text_ms"] is not None and
                 not witness["partial_frame_at_eof"]),
             "SSE_WITNESS_NORMALITY_MISMATCH")


def _validated(run):
    _require(isinstance(run, dict), "RUN_SCHEMA")
    _require(type(run.get("sse_binding_required", False)) is bool,
             "SSE_BINDING_POLICY")
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
        # A visible first delta and a saved partial response do not prove
        # completion. The trusted SSE reader must observe the route's terminal
        # sentinel/event (e.g. [DONE]) and the model's final finish reason.
        _require(type(event.get("sse_terminal_seen")) is bool
                 and type(event.get("model_finish_reason")) is str
                 and event["model_finish_reason"] in
                 ("stop", "length", "tool_calls", "content_filter",
                  "cancelled", "error", "unknown"), "SSE_TERMINAL_PROOF")
        # Historical receipts remain readable; new strict wire provenance
        # must be complete, and any supplied witness must match its outcome.
        if run.get("sse_binding_required", False) or "sse_wire_witness" in event:
            _validate_sse_witness_binding(event)
        mapped[task] = event
    _require(set(mapped) == task_ids, "TASK_SET_MISMATCH")
    return mapped


def _p95(values):
    values = sorted(values)
    return values[math.ceil(.95 * len(values)) - 1]  # nearest rank, every task


def _bound_sse_wire_normal(event):
    """A received [DONE] is not clean EOF if a bound SSE frame remains partial."""
    witness = event.get("sse_wire_witness")
    return witness is None or witness["wire_completed_normally"] is True


def _within_budget_pass(event, max_task_ms):
    """Chat success requires a visible, durable answer within the exact budget.

    A server status of PASS alone is not proof: reasoning-only/empty streams
    and missing S03 history must remain in the failure denominator.
    """
    return (event["status"] == "PASS" and event["latency_ms"] <= max_task_ms
            and event["first_text_ms"] is not None
            and event["output_tokens"] > 0 and event["history_saved"]
            and event["background_completed"] and _bound_sse_wire_normal(event)
            and event["sse_terminal_seen"] and event["model_finish_reason"] == "stop")


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
        "reported_pass_without_usable_chat": sum(
            row["status"] == "PASS" and row["latency_ms"] <= max_task_ms
            and not _within_budget_pass(row, max_task_ms) for row in rows),
        "reported_pass_without_terminal_sse": sum(
            row["status"] == "PASS" and row["latency_ms"] <= max_task_ms
            and (not row["sse_terminal_seen"] or row["model_finish_reason"] != "stop")
            for row in rows),
        # Count every declared task, not just upstream PASS labels: a broken
        # stream on a FAIL/TIMEOUT must still show in the reliability denominator.
        "sse_terminal_seen": sum(row["sse_terminal_seen"] for row in rows),
        "sse_terminal_missing": sum(not row["sse_terminal_seen"] for row in rows),
        "sse_normal_completion": sum(row["sse_terminal_seen"] and
                                     row["model_finish_reason"] == "stop" and
                                     _bound_sse_wire_normal(row)
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
    # Report upstream PASS labels that conceal reasoning-only/blank streams,
    # zero observed output tokens, or absent durable history.
    unusable_reported = [task for task in baseline["declared_task_ids"]
                         if new[task]["status"] == "PASS"
                         and new[task]["latency_ms"] <= candidate["max_task_ms"]
                         and not _within_budget_pass(new[task], candidate["max_task_ms"])]
    unfinished_streams = [task for task in baseline["declared_task_ids"]
                          if new[task]["status"] == "PASS"
                          and new[task]["latency_ms"] <= candidate["max_task_ms"]
                          and (not new[task]["sse_terminal_seen"]
                               or new[task]["model_finish_reason"] != "stop")]
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
    # A constant aggregate token total can hide a shorter answer in one task
    # and a longer answer in another. Neither is equivalent generation work.
    sse_finality_changed = [task for task in baseline["declared_task_ids"]
                            if (old[task]["sse_terminal_seen"] != new[task]["sse_terminal_seen"]
                                or old[task]["model_finish_reason"] != new[task]["model_finish_reason"]
                                or _bound_sse_wire_normal(old[task]) !=
                                _bound_sse_wire_normal(new[task]))]
    # Report stream reliability independently of PASS; a failed task may still
    # lose its terminal event while the aggregate pass count stays constant.
    sse_terminal_lost = [task for task in baseline["declared_task_ids"]
                         if old[task]["sse_terminal_seen"] and not new[task]["sse_terminal_seen"]]
    sse_terminal_restored = [task for task in baseline["declared_task_ids"]
                             if not old[task]["sse_terminal_seen"] and new[task]["sse_terminal_seen"]]
    sse_normal_completion_regressed = [task for task in baseline["declared_task_ids"]
                                       if old[task]["sse_terminal_seen"]
                                       and old[task]["model_finish_reason"] == "stop"
                                       and _bound_sse_wire_normal(old[task])
                                       and (not new[task]["sse_terminal_seen"] or
                                            new[task]["model_finish_reason"] != "stop" or
                                            not _bound_sse_wire_normal(new[task]))]
    # Dropping durable S03 writes or background work can make TTFT/completion
    # appear faster without any inference gain. Compare those side effects by ID.
    durability_changed = [task for task in baseline["declared_task_ids"]
                          if old[task]["history_saved"] != new[task]["history_saved"]]
    background_changed = [task for task in baseline["declared_task_ids"]
                          if old[task]["background_completed"] != new[task]["background_completed"]]
    # Equal token counts do not guarantee the same user-visible answer.
    # Only SSE-parser-bound output digests are comparable; naked unbound
    # digests in historical receipts cannot be used as evidence.
    visible_output_changed = [
        task for task in baseline["declared_task_ids"]
        if (("sse_wire_witness" in old[task]) !=
            ("sse_wire_witness" in new[task]) or
            ("sse_wire_witness" in old[task] and
             old[task]["sse_visible_text_sha256"] !=
             new[task]["sse_visible_text_sha256"]))]
    output_tokens_changed = [task for task in baseline["declared_task_ids"]
                             if old[task]["output_tokens"] != new[task]["output_tokens"]]
    status_changed = [task for task in baseline["declared_task_ids"]
                      if old[task]["status"] != new[task]["status"]]
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
    # This conservative like-for-like latency view is N/A if any observed
    # completion size, terminal status, text coverage, or KV prefill differs.
    # Matching these witnesses still cannot prove identical hidden compute.
    same_observed_work = (not cache_changed and not sse_finality_changed
                          and not output_tokens_changed and not visible_output_changed
                          and not durability_changed
                          and not background_changed
                          and not status_changed and old_seen == new_seen)
    return {**answer, "comparable": True, "state": "DESCRIPTIVE_ONLY",
            "reason": None, "baseline": before, "candidate": after,
            "fixed_task_ids": fixed, "regressed_task_ids": regressed,
            "candidate_reported_pass_without_usable_chat_task_ids": unusable_reported,
            "candidate_reported_pass_without_terminal_sse_task_ids": unfinished_streams,
            "sse_finality_changed_task_ids": sse_finality_changed,
            "sse_terminal_lost_task_ids": sse_terminal_lost,
            "sse_terminal_restored_task_ids": sse_terminal_restored,
            "sse_normal_completion_regressed_task_ids": sse_normal_completion_regressed,
            "sse_terminal_coverage_delta": (after["sse_terminal_seen"] -
                                             before["sse_terminal_seen"]) / before["denominator"],
            "sse_reliability_regression": bool(sse_terminal_lost or sse_normal_completion_regressed),
            "latency_regressed_task_ids": latency_regressed,
            "peak_rss_regressed_task_ids": rss_regressed,
            "cache_state_changed_task_ids": cache_changed,
            "cache_reuse_regressed_task_ids": cache_reuse_regressed,
            "cache_reuse_lost_task_ids": cache_reuse_lost,
            "prompt_prefill_regressed_task_ids": prefill_regressed,
            "latency_cache_state_confounder": bool(cache_changed),
            "history_durability_changed_task_ids": durability_changed,
            "background_completion_changed_task_ids": background_changed,
            "latency_side_effects_confounder": bool(durability_changed or background_changed),
            "output_tokens_changed_task_ids": output_tokens_changed,
            "visible_output_changed_task_ids": visible_output_changed,
            "latency_visible_content_confounder": bool(visible_output_changed),
            "outcome_status_changed_task_ids": status_changed,
            "latency_observed_workload_confounder": not same_observed_work,
            "p95_latency_delta_ms_same_observed_work": (
                after["p95_latency_ms_all_tasks"] - before["p95_latency_ms_all_tasks"]
                if same_observed_work else None),
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
            "quality_or_history_regression": bool(regressed or first_text_lost or
                                                  sse_terminal_lost or
                                                  sse_normal_completion_regressed or any(
                (old[task]["history_saved"] and not new[task]["history_saved"]) or
                (old[task]["background_completed"] and not new[task]["background_completed"])
                for task in baseline["declared_task_ids"]))}


def measure_openai_sse_wire(timed_chunks):
    """Produce a read-only wire witness; never POST or infer S03 durability.

    Each item is (monotonic elapsed_ms, raw HTTP body bytes) from an independently
    authenticated OpenAI-compatible chat/completions SSE reader. Elapsed times
    are at completed SSE event dispatch (not estimated generation-token times).
    The parser keeps full byte/text hashes without retaining or truncating text.
    A different server/proxy event contract requires a separate reviewed parser.
    No field returned here alone proves native verification or task success.
    """
    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    raw_hash, timed_hash, visible_hash = (hashlib.sha256() for _ in range(3))
    line, data_lines = "", []
    last_cr = False
    last_ms = -1
    raw_bytes = 0
    visible_bytes = 0
    first_text_ms = None
    terminal_ms = None
    finish_reason = None
    terminal_seen = False
    usage_seen = False
    event_count = 0

    def _unique_json_object(pairs):
        # JSON permits repeated field names and otherwise silently retains the
        # last value. Ambiguous choices/delta/finish_reason are not wire proof.
        obj = {}
        for key, value in pairs:
            _require(key not in obj, "SSE_DUPLICATE_JSON_FIELD")
            obj[key] = value
        return obj

    def _reject_nonfinite_json(_literal):
        # Python accepts NaN/Infinity by default, despite RFC JSON forbidding
        # them. Even ignored metadata must not turn malformed wire into PASS.
        raise ReceiptHold("SSE_NONFINITE_JSON_CONSTANT")

    def _finite_json_float(number):
        # JSON exponent notation can overflow a Python float to infinity.
        # parse_constant does not catch e.g. 1e999 or -1e999.
        parsed = float(number)
        _require(math.isfinite(parsed), "SSE_NONFINITE_JSON_NUMBER")
        return parsed

    def dispatch(at_ms):
        nonlocal data_lines, visible_bytes, first_text_ms
        nonlocal terminal_ms, finish_reason, terminal_seen, event_count, usage_seen
        if not data_lines:
            return
        payload = "\n".join(data_lines)
        data_lines = []
        _require(not terminal_seen, "SSE_AFTER_TERMINAL")
        if payload == "[DONE]":
            terminal_seen = True
            terminal_ms = at_ms
            return
        try:
            obj = json.loads(payload, object_pairs_hook=_unique_json_object,
                             parse_constant=_reject_nonfinite_json,
                             parse_float=_finite_json_float)
        except ReceiptHold:
            raise
        except (ValueError, TypeError) as exc:
            raise ReceiptHold("SSE_INVALID_JSON") from exc
        _require(isinstance(obj, dict) and isinstance(obj.get("choices"), list),
                 "SSE_CHOICE_SCHEMA")
        # The last include_usage chunk has choices=[] and no text/finish reason.
        # It is a real SSE event, but only [DONE] closes the wire receipt.
        if not obj["choices"]:
            _require(not usage_seen, "SSE_DUPLICATE_USAGE")
            usage = obj.get("usage")
            _require(finish_reason is not None and isinstance(usage, dict)
                     and all(_integer(usage.get(key), 10 ** 10) for key in
                             ("prompt_tokens", "completion_tokens", "total_tokens")),
                     "SSE_USAGE_CHUNK_SCHEMA")
            # Both counters are individually well-formed, but a fabricated
            # aggregate must never pass as trustworthy completion statistics.
            _require(usage["total_tokens"] ==
                     usage["prompt_tokens"] + usage["completion_tokens"],
                     "SSE_USAGE_COUNT_MISMATCH")
            usage_seen = True
            event_count += 1
            return
        # Model finality is immutable: only one usage-only event and [DONE]
        # may follow. Late text or repeated final choices are not valid proof.
        _require(finish_reason is None, "SSE_POST_FINISH_EVENT")
        _require(len(obj["choices"]) == 1 and isinstance(obj["choices"][0], dict),
                 "SSE_CHOICE_SCHEMA")
        choice = obj["choices"][0]
        # If the upstream OpenAI choice index is supplied, it must denote
        # the sole selected choice (0), not another completion candidate.
        # Keep index-omitting legacy fixtures compatible; reject bool/float.
        _require("index" not in choice or
                 (type(choice["index"]) is int and choice["index"] == 0),
                 "SSE_CHOICE_INDEX_SCHEMA")
        delta = choice.get("delta")
        _require(isinstance(delta, dict), "SSE_DELTA_SCHEMA")
        content = delta.get("content")
        _require(content is None or isinstance(content, str), "SSE_CONTENT_SCHEMA")
        if content:
            # JSON permits unpaired escaped UTF-16 surrogates, which are not
            # valid Unicode scalar values. Reject them as structured HOLD,
            # rather than letting encode() escape our evidence contract.
            try:
                encoded = content.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ReceiptHold("SSE_INVALID_UNICODE_SCALAR") from exc
            # Keep every transmitted content byte in the digest; whitespace
            # alone is not usable first text or evidence of a meaningful answer.
            # Unicode format/control and zero-width-only deltas are not a
            # visible first token. Preserve ALL original bytes in text SHA;
            # use a rendering-aware timestamp, not whitespace alone.
            if first_text_ms is None and any(
                    ch.isprintable() and not ch.isspace()
                    and unicodedata.category(ch) not in ("Mn", "Me")
                    for ch in content):
                first_text_ms = at_ms
            visible_hash.update(encoded)
            visible_bytes += len(encoded)
        reason = choice.get("finish_reason")
        _require(reason is None or reason in
                 ("stop", "length", "tool_calls", "content_filter",
                  "cancelled", "error", "unknown"), "SSE_FINISH_SCHEMA")
        if reason is not None:
            _require(finish_reason is None or finish_reason == reason,
                     "SSE_CONFLICTING_FINISH")
            finish_reason = reason
        event_count += 1

    def accept_line(value, at_ms):
        nonlocal data_lines
        if not value:
            dispatch(at_ms)
            return
        if value.startswith(":"):
            return  # heartbeat/comment is not visible text or completion
        field, sep, data = value.partition(":")
        if field == "event":
            # OpenAI-compatible data chunks use the default/message event.
            # An explicit SSE error is a transport failure, not an ordinary
            # completion even if its data looks like [DONE] or a valid delta.
            event_name = data[1:] if sep and data.startswith(" ") else data
            _require(event_name != "error", "SSE_ERROR_EVENT")
            # This witness is explicitly OpenAI chat/completions data SSE.
            # Named non-message events (e.g. ping, status) must never
            # impersonate model deltas or the terminal [DONE] marker.
            _require(event_name in ("", "message"), "SSE_UNSUPPORTED_EVENT_TYPE")
        if field == "data":
            if sep and data.startswith(" "):
                data = data[1:]
            data_lines.append(data)

    def accept_text(text, at_ms):
        nonlocal line, last_cr
        for ch in text:
            if ch == "\n" and last_cr:
                last_cr = False
                continue
            if ch in ("\r", "\n"):
                accept_line(line, at_ms)
                line = ""
                last_cr = ch == "\r"
            else:
                last_cr = False
                line += ch
                _require(len(line) <= 262144, "SSE_FRAME_OVER_LIMIT")

    for item in timed_chunks:
        _require(isinstance(item, (tuple, list)) and len(item) == 2,
                 "SSE_CHUNK_SCHEMA")
        at_ms, chunk = item
        _require(_integer(at_ms, 86400000) and at_ms >= last_ms
                 and isinstance(chunk, bytes), "SSE_CHUNK_SCHEMA")
        last_ms = at_ms
        raw_bytes += len(chunk)
        _require(raw_bytes <= 8388608, "SSE_WIRE_OVER_LIMIT")
        raw_hash.update(chunk)
        timed_hash.update(at_ms.to_bytes(8, "big"))
        timed_hash.update(len(chunk).to_bytes(8, "big"))
        timed_hash.update(chunk)
        try:
            accept_text(decoder.decode(chunk), at_ms)
        except UnicodeDecodeError as exc:
            raise ReceiptHold("SSE_INVALID_UTF8") from exc
    try:
        accept_text(decoder.decode(b"", final=True), max(last_ms, 0))
    except UnicodeDecodeError as exc:
        raise ReceiptHold("SSE_INVALID_UTF8") from exc
    if last_cr:
        accept_line(line, max(last_ms, 0))
        line = ""
    # EventSource semantics: a final data frame without a blank line is
    # incomplete, not an event. Never synthesize [DONE] from socket EOF.
    return {
        "protocol": "OPENAI_CHAT_COMPLETIONS_SSE_V1",
        "raw_wire_sha256": raw_hash.hexdigest(),
        "timed_trace_sha256": timed_hash.hexdigest(),
        "visible_text_sha256": visible_hash.hexdigest(),
        "raw_wire_bytes": raw_bytes,
        "visible_utf8_bytes": visible_bytes,
        "parsed_events": event_count,
        "first_text_ms": first_text_ms,
        "completion_ms": terminal_ms,
        "last_byte_ms": None if last_ms < 0 else last_ms,
        "sse_terminal_seen": terminal_seen,
        "model_finish_reason": finish_reason or "unknown",
        "partial_frame_at_eof": bool(line or data_lines),
        "wire_completed_normally": bool(terminal_seen and finish_reason == "stop"
                                         and first_text_ms is not None and not (line or data_lines)),
        "native_verified": False,
        "s03_durable_verified": False,
    }


def measure_two_turn_openai_sse_capture(turns):
    """Offline read-only SAME-DIALOG two-turn SSE consistency gate.

    Each turn must carry a distinct exchange ID and ordinal (1,2), identical
    declared dialog/route/model pins, plus raw monotonic timed SSE chunks.
    These caller-declared pins are NOT host/browser authentication. This helper
    NEVER sends model POSTs, reads S03, or makes a native acceptance claim.
    """
    _require(type(turns) is list and len(turns) == 2, "SSE_TWO_TURN_COUNT")
    identity = None
    exchanges = set()
    results = []
    for ordinal, item in enumerate(turns, 1):
        _require(type(item) is dict, "SSE_TWO_TURN_SCHEMA")
        _require(type(item.get("turn_number")) is int and
                 item["turn_number"] == ordinal, "SSE_TWO_TURN_ORDER")
        dialog = item.get("dialog_id")
        exchange = item.get("exchange_id")
        _require(type(dialog) is str and 1 <= len(dialog) <= 160,
                 "SSE_TWO_TURN_DIALOG")
        _require(type(exchange) is str and 1 <= len(exchange) <= 160
                 and exchange not in exchanges, "SSE_TWO_TURN_EXCHANGE")
        exchanges.add(exchange)
        route = item.get("route_sha256")
        model = item.get("model_sha256")
        _require(type(route) is str and SHA.fullmatch(route) and
                 type(model) is str and SHA.fullmatch(model),
                 "SSE_TWO_TURN_PINS")
        declared = (dialog, route, model)
        if identity is None:
            identity = declared
        _require(identity == declared, "SSE_TWO_TURN_IDENTITY_DRIFT")
        chunks = item.get("timed_chunks")
        _require(type(chunks) is list and 1 <= len(chunks) <= 4096,
                 "SSE_TWO_TURN_CHUNKS")
        witness = measure_openai_sse_wire(chunks)
        _require(witness["wire_completed_normally"] is True and
                 _integer(witness["first_text_ms"], 86_400_000) and
                 _integer(witness["completion_ms"], 86_400_000) and
                 _integer(witness["last_byte_ms"], 86_400_000) and
                 witness["first_text_ms"] <= witness["completion_ms"] <=
                 witness["last_byte_ms"], "SSE_TWO_TURN_NOT_CLEAN")
        results.append({
            "turn_number": ordinal,
            "exchange_id": exchange,
            "first_text_ms": witness["first_text_ms"],
            "completion_ms": witness["completion_ms"],
            "last_byte_ms": witness["last_byte_ms"],
            "wire_witness": witness,
        })
    return {
        "schema": "NOX_B4_TWO_TURN_OFFLINE_SSE_V1",
        "state": "OFFLINE_SOURCE_TRACE_CONSISTENT_ONLY",
        "dialog_id": identity[0],
        "declared_route_sha256": identity[1],
        "declared_model_sha256": identity[2],
        "turns": results,
        "browser_authenticated": False,
        "native_verified": False,
        "s03_durable_verified": False,
        "one_model_post_per_turn_verified": False,
    }


def verify_two_turn_openai_posted_history(turns, capture):
    """Read-only request-history consistency proof for a simple two-turn chat.

    Exact caller-supplied outbound OpenAI JSON request bodies are checked
    against the independently parsed first SSE response. Nothing is POSTed.
    This does NOT authenticate the HTTP capture or prove S03 durability.
    Strict smoke-test profile: turn 2 must extend turn 1 with exactly the
    assistant's complete visible response and a subsequent user message.
    """
    _require(type(turns) is list and len(turns) == 2 and
             type(capture) is dict and
             capture.get("schema") == "NOX_B4_TWO_TURN_OFFLINE_SSE_V1" and
             type(capture.get("turns")) is list and len(capture["turns"]) == 2,
             "SSE_TWO_TURN_REQUEST_CAPTURE")
    parsed = []
    hashes = []

    def _unique_request_object(pairs):
        obj = {}
        for key, value in pairs:
            _require(key not in obj, "SSE_TWO_TURN_REQUEST_DUPLICATE_KEY")
            obj[key] = value
        return obj

    def _finite_request_float(raw):
        number = float(raw)
        _require(math.isfinite(number), "SSE_TWO_TURN_REQUEST_NONFINITE")
        return number

    def _reject_request_constant(_):
        raise ReceiptHold("SSE_TWO_TURN_REQUEST_NONFINITE")

    for idx, turn in enumerate(turns):
        _require(type(turn) is dict and
                 type(turn.get("turn_number")) is int and
                 turn["turn_number"] == idx + 1 and
                 turn.get("exchange_id") == capture["turns"][idx].get("exchange_id"),
                 "SSE_TWO_TURN_REQUEST_EXCHANGE")
        body = turn.get("posted_request_body")
        _require(type(body) is bytes and 1 <= len(body) <= 1048576,
                 "SSE_TWO_TURN_REQUEST_BYTES")
        try:
            request = json.loads(
                body.decode("utf-8"), object_pairs_hook=_unique_request_object,
                parse_float=_finite_request_float,
                parse_constant=_reject_request_constant)
        except ReceiptHold:
            raise
        except (UnicodeError, ValueError, TypeError) as exc:
            raise ReceiptHold("SSE_TWO_TURN_REQUEST_JSON") from exc
        _require(type(request) is dict and
                 type(request.get("model")) is str and
                 1 <= len(request["model"]) <= 160 and
                 type(request.get("messages")) is list and
                 1 <= len(request["messages"]) <= 256 and
                 all(type(message) is dict and
                     type(message.get("role")) is str
                     for message in request["messages"]),
                 "SSE_TWO_TURN_REQUEST_SCHEMA")
        parsed.append(request)
        hashes.append(hashlib.sha256(body).hexdigest())
    first, second = parsed
    _require(first["model"] == second["model"],
             "SSE_TWO_TURN_REQUEST_MODEL_DRIFT")
    first_messages, second_messages = first["messages"], second["messages"]
    _require(len(second_messages) == len(first_messages) + 2 and
             second_messages[-2].get("role") == "assistant" and
             second_messages[-1].get("role") == "user" and
             type(second_messages[-2].get("content")) is str and
             type(second_messages[-1].get("content")) is str and
             bool(second_messages[-1]["content"].strip()),
             "SSE_TWO_TURN_HISTORY_ORDER")
    _require(second_messages[:len(first_messages)] == first_messages,
             "SSE_TWO_TURN_HISTORY_PREFIX")
    witness = capture["turns"][0].get("wire_witness")
    _require(type(witness) is dict and
             witness.get("wire_completed_normally") is True and
             type(witness.get("visible_text_sha256")) is str and
             SHA.fullmatch(witness["visible_text_sha256"]),
             "SSE_TWO_TURN_FIRST_WIRE")
    prior_text_hash = hashlib.sha256(
        second_messages[-2]["content"].encode("utf-8")).hexdigest()
    _require(prior_text_hash == witness["visible_text_sha256"],
             "SSE_TWO_TURN_HISTORY_HASH_MISMATCH")
    return {
        "schema": "NOX_B4_TWO_TURN_REQUEST_CONTINUITY_V1",
        "state": "OFFLINE_REQUEST_AND_SSE_SOURCE_CONSISTENT_ONLY",
        "posted_request_sha256": hashes,
        "first_assistant_visible_sha256": prior_text_hash,
        "browser_authenticated": False,
        "native_verified": False,
        "s03_durable_verified": False,
        "one_model_post_per_turn_verified": False,
    }


def verify_two_turn_http_trace_envelope(turns, capture, http_exchanges,
                                        expected_target_path):
    """Bind a caller-supplied HTTP trace to two real-parser SSE witnesses.

    Network records must come from a separately audited Chrome/HTTP collector.
    This OFFLINE routine cannot authenticate the collector or rule out unseen
    POSTs: it is never production, browser-auth, or S03 acceptance evidence.
    No bearer headers, cookies, request text, or responses enter the result.
    """
    _require(type(expected_target_path) is str and
             expected_target_path.startswith("/") and
             not expected_target_path.startswith("//") and
             "?" not in expected_target_path and
             "#" not in expected_target_path and
             ".." not in expected_target_path and
             len(expected_target_path) <= 256, "SSE_HTTP_TARGET_POLICY")
    _require(type(http_exchanges) is list and len(http_exchanges) == 2,
             "SSE_HTTP_TRACE_COUNT")
    # Reparse the EXACT claimed SSE bytes and requests rather than trusting
    # caller-supplied hash/timing fields in previously assembled objects.
    recomputed = measure_two_turn_openai_sse_capture(turns)
    _require(type(capture) is dict and capture == recomputed,
             "SSE_HTTP_TRACE_CAPTURE_MISMATCH")
    continuity = verify_two_turn_openai_posted_history(turns, recomputed)
    summaries = []
    previous_closed = None
    network_ids = set()
    for idx, (turn, network) in enumerate(zip(turns, http_exchanges)):
        _require(type(network) is dict, "SSE_HTTP_TRACE_SCHEMA")
        event_id = network.get("network_event_id")
        _require(type(event_id) is str and 1 <= len(event_id) <= 160 and
                 event_id not in network_ids, "SSE_HTTP_TRACE_EVENT_ID")
        network_ids.add(event_id)
        _require(type(network.get("turn_number")) is int and
                 network["turn_number"] == idx + 1 and
                 network.get("exchange_id") == turn["exchange_id"],
                 "SSE_HTTP_TRACE_EXCHANGE")
        _require(network.get("method") == "POST" and
                 network.get("target_path") == expected_target_path and
                 network.get("request_content_type") == "application/json",
                 "SSE_HTTP_TRACE_REQUEST")
        _require(network.get("response_status") == 200 and
                 type(network.get("response_status")) is int and
                 network.get("response_content_type") in
                 ("text/event-stream", "text/event-stream; charset=utf-8"),
                 "SSE_HTTP_TRACE_RESPONSE")
        witness = recomputed["turns"][idx]["wire_witness"]
        _require(network.get("request_body_sha256") ==
                 continuity["posted_request_sha256"][idx] and
                 network.get("response_wire_sha256") ==
                 witness["raw_wire_sha256"] and
                 network.get("response_timed_trace_sha256") ==
                 witness["timed_trace_sha256"],
                 "SSE_HTTP_TRACE_DIGEST_MISMATCH")
        sent = network.get("request_sent_monotonic_ms")
        first_byte = network.get("response_first_byte_monotonic_ms")
        closed = network.get("response_closed_monotonic_ms")
        _require(all(_integer(n, 86_400_000) for n in
                     (sent, first_byte, closed)) and
                 sent <= first_byte <= sent + witness["first_text_ms"] and
                 sent + witness["last_byte_ms"] <= closed and
                 (previous_closed is None or sent > previous_closed),
                 "SSE_HTTP_TRACE_CLOCK_MISMATCH")
        previous_closed = closed
        summaries.append({
            "turn_number": idx + 1,
            "exchange_id": turn["exchange_id"],
            "network_event_id": event_id,
            "request_body_sha256": continuity["posted_request_sha256"][idx],
            "response_wire_sha256": witness["raw_wire_sha256"],
            "response_timed_trace_sha256": witness["timed_trace_sha256"],
            "request_sent_monotonic_ms": sent,
            "response_closed_monotonic_ms": closed,
            "first_visible_ms_from_request": witness["first_text_ms"],
            "terminal_ms_from_request": witness["completion_ms"],
            "last_wire_byte_ms_from_request": witness["last_byte_ms"],
        })
    digest = hashlib.sha256(json.dumps(
        summaries, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "schema": "NOX_B4_TWO_TURN_HTTP_TRACE_ENVELOPE_V1",
        "state": "UNAUTHENTICATED_OFFLINE_NETWORK_TRACE_CONSISTENT_ONLY",
        "trace_metadata_sha256": digest,
        "turns": summaries,
        "browser_authenticated": False,
        "independent_network_trace_verified": False,
        "native_verified": False,
        "s03_durable_verified": False,
        "one_model_post_per_turn_verified": False,
    }
def verify_cdp_receipt_against_http_trace(
        turns, capture, http_exchanges, expected_target_path, cdp_receipt):
    """Strict *offline* consistency of CDP and independently supplied SSE/HTTP.

    CDP's getResponseBody is a decoded body digest, NOT raw TCP bytes.
    Only matching the exact uncompressed OpenAI SSE payload is supported.
    CDP and HTTP clocks are compared as elapsed offsets, not assumed to
    share an absolute epoch. This does not authenticate either collector,
    prove a single upstream model POST, or establish S03 durability.
    """
    envelope = verify_two_turn_http_trace_envelope(
        turns, capture, http_exchanges, expected_target_path)
    _require(type(cdp_receipt) is dict and
             cdp_receipt.get("schema") == "nox-b4-cdp-v1" and
             type(cdp_receipt.get("turns")) is list and
             len(cdp_receipt["turns"]) == 2,
             "SSE_CDP_RECEIPT_SCHEMA")
    _require(cdp_receipt.get("cdp_consistent") is True and
             cdp_receipt.get("ttft_sse_verified") is True,
             "SSE_CDP_UNMEASURED")
    # Neither a CDP connection nor a local fixture is trusted remote evidence.
    # Refuse a fabricated truthy claim rather than silently upgrading trust.
    for flag in ("browser_authenticated", "remote_attested",
                 "native_verified", "canonical_s03_verified",
                 "one_model_post_per_turn_verified", "tcp_wire_verified"):
        _require(cdp_receipt.get(flag) is False, "SSE_CDP_TRUST_FLAG")
    ids = set()
    metadata = []
    for ordinal, (cdp, network, source) in enumerate(
            zip(cdp_receipt["turns"], http_exchanges,
                capture["turns"]), 1):
        _require(type(cdp) is dict and
                 type(cdp.get("turn")) is int and
                 cdp["turn"] == ordinal and
                 type(cdp.get("cdp_request_id")) is str and
                 1 <= len(cdp["cdp_request_id"]) <= 160 and
                 cdp["cdp_request_id"] not in ids and
                 cdp["cdp_request_id"] == network["network_event_id"],
                 "SSE_CDP_EVENT_ID")
        ids.add(cdp["cdp_request_id"])
        _require(type(cdp.get("status")) is int and
                 cdp["status"] == 200 and
                 cdp.get("mime") == "text/event-stream",
                 "SSE_CDP_HTTP_RESPONSE")
        _require(cdp.get("stream_timing_complete") is True,
                 "SSE_CDP_UNMEASURED")
        wire = source["wire_witness"]
        _require(cdp.get("request_sha256") ==
                 network["request_body_sha256"] and
                 cdp.get("cdp_decoded_body_sha256") ==
                 wire["raw_wire_sha256"] and
                 cdp.get("cdp_decoded_body_sha256") ==
                 network["response_wire_sha256"],
                 "SSE_CDP_DIGEST_MISMATCH")
        first = cdp.get("first_network_byte_ms")
        ttft = cdp.get("ttft_ms")
        done = cdp.get("sse_done_ms")
        closed = cdp.get("close_ms")
        _require(all(_integer(v, 86_400_000) for v in
                     (first, ttft, done, closed)),
                 "SSE_CDP_TIMING_SCHEMA")
        # All four CDP measurements are from requestWillBeSent's timestamp;
        # Python SSE chunks must independently agree on first visible delta
        # and [DONE], not just a response header or a buffered body.
        _require(first <= ttft <= done <= closed and
                 first == network["response_first_byte_monotonic_ms"] -
                          network["request_sent_monotonic_ms"] and
                 ttft == wire["first_text_ms"] and
                 done == wire["completion_ms"] and
                 closed == network["response_closed_monotonic_ms"] -
                           network["request_sent_monotonic_ms"] and
                 closed >= wire["last_byte_ms"],
                 "SSE_CDP_TIMING_MISMATCH")
        metadata.append({
            "turn_number": ordinal, "cdp_request_id": cdp["cdp_request_id"],
            "request_sha256": cdp["request_sha256"],
            "decoded_sse_sha256": cdp["cdp_decoded_body_sha256"],
            "first_network_byte_ms": first, "ttft_ms": ttft,
            "sse_done_ms": done, "close_ms": closed,
        })
    digest = hashlib.sha256(json.dumps(
        metadata, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return {
        "schema": "NOX_B4_CDP_SSE_CROSSCHECK_V1",
        "state": "UNAUTHENTICATED_OFFLINE_CDP_HTTP_SOURCE_CONSISTENT_ONLY",
        "http_trace_metadata_sha256": envelope["trace_metadata_sha256"],
        "cdp_metadata_sha256": digest,
        "turns_checked": len(metadata),
        "browser_authenticated": False,
        "independent_network_trace_verified": False,
        "native_verified": False,
        "s03_durable_verified": False,
        "one_model_post_per_turn_verified": False,
        "promotion_authorized": False,
    }
