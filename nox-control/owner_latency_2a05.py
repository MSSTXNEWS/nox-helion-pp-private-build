#!/usr/bin/env python3
"""Privacy-safe 2A05 latency baseline from existing owner-authenticated receipts.

No network, host commands, token data, or inference. Does not claim native
acceptance: comparison requires verified model+route pins and >=20 distinct runs.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

SCHEMA = 'NOX_2A05_LATENCY_BASELINE_V1'
SHA = re.compile(r'[0-9a-f]{64}\Z')
MIN_RUNS = 20
FIELDS = ('ttft_ms', 'ui_first_ms', 'first_turn_ms', 'second_turn_ms')


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError('HOLD_2A05_' + reason)


def milliseconds(value: object) -> float:
    require(type(value) in (int, float) and math.isfinite(value)
            and 0 <= value <= 300_000, 'BAD_LATENCY')
    return float(value)


def pct(values: list[float], percentage: float) -> float:
    """Nearest-rank p50/p95: conservative empirical quantile, no interpolation."""
    require(values and percentage in (50, 95), 'PERCENTILE_INPUT')
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(percentage * len(ordered) / 100) - 1)], 3)


def summarize(receipts: list[dict], *, model_sha256: str, route_sha256: str) -> dict:
    require(bool(SHA.fullmatch(model_sha256)) and bool(SHA.fullmatch(route_sha256)),
            'PIN_REQUIRED')
    require(type(receipts) is list and len(receipts) <= 1000, 'RECEIPT_COUNT')
    seen: set[str] = set()
    values = {name: [] for name in FIELDS}
    source_sha: str | None = None
    asset_sha: str | None = None
    for row in receipts:
        require(isinstance(row, dict), 'RECEIPT_TYPE')
        require(row.get('schema') == 'NOX_OWNER_BROWSER_STREAM_ONLY_QA_V2'
                and row.get('state') == 'STREAM_ONLY_ACCEPTED'
                and row.get('native_posts_admitted') == 2
                and row.get('both_terminal_sse_done_records_saved_s03_integrated') is True
                and row.get('authenticated_s03_history_readback_verified') is True
                and row.get('first_turn_terminal_sse_verified') is True,
                'NONTERMINAL_SAMPLE')
        # External model pin must be verified by the owner separately. Never
        # infer model identity from the QA tool SHA or served JS asset SHA.
        require(row.get('verified_model_sha256') == model_sha256
                and row.get('verified_route_sha256') == route_sha256,
                'MODEL_OR_ROUTE_MISMATCH')
        sid = row.get('request')
        src = row.get('source_sha')
        asset = row.get('served_asset_sha256')
        require(type(sid) is str and 1 <= len(sid) <= 64 and sid not in seen,
                'REPLAYED_OR_MISSING_REQUEST')
        require(type(src) is str and bool(SHA.fullmatch(src))
                and type(asset) is str and bool(SHA.fullmatch(asset)), 'SOURCE_PIN')
        require((source_sha is None or source_sha == src)
                and (asset_sha is None or asset_sha == asset), 'MIXED_QA_BUILD')
        source_sha, asset_sha = src, asset
        seen.add(sid)
        stream = row.get('stream')
        require(isinstance(stream, dict), 'STREAM_MISSING')
        sample = {'ttft_ms': stream.get('native_first_ms'),
                  'ui_first_ms': stream.get('ui_first_ms'),
                  'first_turn_ms': row.get('elapsed_turn_ms'),
                  'second_turn_ms': row.get('multiturn_second_elapsed_ms')}
        for name, value in sample.items():
            values[name].append(milliseconds(value))
    n = len(receipts)
    # Do not emit any raw receipt fields, IDs, prompts or private paths.
    return {'schema': SCHEMA, 'task_id': '2A05', 'samples': n,
            'state': 'SOURCE_BASELINE_READY_NOT_NATIVE_ACCEPTED' if n >= MIN_RUNS
                     else 'HOLD_2A05_INSUFFICIENT_IDENTICAL_SAMPLES',
            'minimum_runs': MIN_RUNS, 'identity_verified_by_owner_required': True,
            'canonical_s03_acceptance_claimed': False,
            'original295_accepted_increment': 0,
            'latency_ms': {name: ({'p50': pct(series, 50), 'p95': pct(series, 95)}
                                  if n >= MIN_RUNS else None)
                           for name, series in values.items()}}


def main() -> int:
    ap = argparse.ArgumentParser(description='Compute bounded owner-pinned NOX latency baseline')
    ap.add_argument('json_file', type=Path, help='private JSON array of QA receipts')
    ap.add_argument('--model-sha256', required=True)
    ap.add_argument('--route-sha256', required=True)
    args = ap.parse_args()
    require(args.json_file.is_file() and args.json_file.stat().st_size <= 5_000_000,
            'INPUT_SIZE')
    raw = args.json_file.read_text(encoding='utf-8')
    result = summarize(json.loads(raw), model_sha256=args.model_sha256,
                       route_sha256=args.route_sha256)
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0 if result['state'] == 'SOURCE_BASELINE_READY_NOT_NATIVE_ACCEPTED' else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        # Preserve fail-closed cause, never print user-supplied content.
        reason = str(exc) if str(exc).startswith('HOLD_2A05_') else 'HOLD_2A05_INPUT_ERROR'
        print(json.dumps({'schema': SCHEMA, 'state': reason, 'original295_accepted_increment': 0}))
        raise SystemExit(2)
