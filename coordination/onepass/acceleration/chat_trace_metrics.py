#!/usr/bin/env python3
"""Summarize an exported NOX chat timing trace without contacting NOX.

This is an offline measurement helper: it does not call HTTP, the model,
S03, or modify serving/cache state. The trace carries timestamps captured by
an already-authorized chat acceptance run using one monotonic clock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from statistics import median


SCHEMA = "NOX_CHAT_TIMING_TRACE_V1"
OUTPUT_SCHEMA = "NOX_CHAT_TIMING_SUMMARY_V1"
EVENTS = ("request_started", "first_token", "terminal_received", "s03_readback_completed")
SAMPLE_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
HEADER_KEYS = {"schema", "scenario_id", "route_id", "served_sha256", "capture_clock"}
EVENT_KEYS = {"sample_id", "event", "monotonic_ns"}


def _object(raw: str, line_no: int) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"line {line_no}: invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"line {line_no}: expected a JSON object")
    return value


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    # Nearest-rank percentile, with one-based rank ceil(p*n).
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _metric(values_ns: list[int]) -> dict:
    values_ms = [value / 1_000_000 for value in values_ns]
    return {
        "count": len(values_ms),
        "median_ms": round(median(values_ms), 3),
        "p50_ms": round(_percentile(values_ms, 0.50), 3),
        "p95_ms": round(_percentile(values_ms, 0.95), 3),
        "max_ms": round(max(values_ms), 3),
    }


def summarize(path: Path) -> dict:
    raw = path.read_bytes()
    lines = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError("trace requires one header and at least one event")

    header = _object(lines[0], 1)
    if set(header) != HEADER_KEYS or header.get("schema") != SCHEMA:
        raise ValueError("line 1: unexpected trace header/schema")
    if not all(isinstance(header.get(key), str) and header[key] for key in ("scenario_id", "route_id")):
        raise ValueError("line 1: scenario_id and route_id are required")
    if not isinstance(header.get("served_sha256"), str) or not SHA256.fullmatch(header["served_sha256"]):
        raise ValueError("line 1: exact served_sha256 is required")
    if header.get("capture_clock") != "monotonic_ns":
        raise ValueError("line 1: capture_clock must be monotonic_ns")

    samples: dict[str, dict[str, int]] = {}
    for line_no, raw_line in enumerate(lines[1:], start=2):
        event = _object(raw_line, line_no)
        if set(event) != EVENT_KEYS:
            raise ValueError(f"line {line_no}: only sample_id, event, monotonic_ns are allowed")
        sample_id = event.get("sample_id")
        name = event.get("event")
        timestamp = event.get("monotonic_ns")
        if not isinstance(sample_id, str) or not SAMPLE_ID.fullmatch(sample_id):
            raise ValueError(f"line {line_no}: sample_id must be an opaque safe identifier")
        if name not in EVENTS:
            raise ValueError(f"line {line_no}: unknown event")
        if type(timestamp) is not int or timestamp < 0:
            raise ValueError(f"line {line_no}: monotonic_ns must be a nonnegative integer")
        row = samples.setdefault(sample_id, {})
        if name in row:
            raise ValueError(f"line {line_no}: duplicate event for sample")
        row[name] = timestamp

    metrics = {"ttft": [], "stream_total": [], "persistence_after_terminal": [], "end_to_s03_readback": []}
    incomplete = 0
    for row in samples.values():
        if any(name not in row for name in EVENTS):
            incomplete += 1
            continue
        start, first, terminal, readback = (row[name] for name in EVENTS)
        if not start <= first <= terminal <= readback:
            raise ValueError("sample timestamps are out of order; use one monotonic clock")
        metrics["ttft"].append(first - start)
        metrics["stream_total"].append(terminal - start)
        metrics["persistence_after_terminal"].append(readback - terminal)
        metrics["end_to_s03_readback"].append(readback - start)

    complete = len(metrics["ttft"])
    if complete == 0:
        raise ValueError("no complete samples; each needs all four timing events")
    return {
        "schema": OUTPUT_SCHEMA,
        "trace_sha256": hashlib.sha256(raw).hexdigest(),
        "scenario_id": header["scenario_id"],
        "route_id": header["route_id"],
        "served_sha256": header["served_sha256"],
        "sample_count": complete,
        "incomplete_sample_count": incomplete,
        "percentile_method": "nearest_rank",
        "percentile_quality": "DESCRIPTIVE_ONLY_LT_20_SAMPLES" if complete < 20 else "20_PLUS_SAMPLES",
        "metrics": {name: _metric(values) for name, values in metrics.items()},
        "live_request_sent_by_harness": False,
        "model_or_cache_touched_by_harness": False,
        "raw_dialogue_or_tokens_exported": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="UTF-8 JSONL timing trace exported by an acceptance run")
    parser.add_argument("--output", type=Path, help="write summary JSON here; stdout if omitted")
    args = parser.parse_args(argv)
    try:
        report = summarize(args.trace)
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if args.output:
            args.output.write_text(encoded, encoding="utf-8")
        else:
            sys.stdout.write(encoded)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"HOLD_TRACE_INVALID: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
