#!/usr/bin/env python3
"""NOX AUTO 2C: bounded, read-only hybrid WEB evidence contract.

This is a source-level auditor for sanitized ORIGINAL OneHost receipts, not a
replacement route, web UI, model, S03, controller or native attestation verifier.
It NEVER executes commands, updates S03, sends HTTP, or enables STOP/RESUME.
"""
from __future__ import annotations
import argparse
import json
import math
import statistics
import tempfile
from pathlib import Path

MAX_ROWS = 2048
# Guard source-only timing samples against extreme finite numbers that can
# overflow aggregation into non-standard JSON Infinity/NaN.
MAX_OBSERVATION_MS = 86_400_000  # 24h, upper bound for one timing sample
EXPECTED_ROUTE_TARGET = 92
STAGES = {"baseline", "lora", "qlora", "merged_fp16", "full_distill", "quantized", "live_promoted"}


def _number(value, *, strictly_positive=False, max_value=None):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        numeric = float(value)
    except (OverflowError, ValueError, TypeError):
        return False
    return (math.isfinite(numeric) and
            (numeric > 0 if strictly_positive else numeric >= 0) and
            (max_value is None or numeric <= max_value))


def _hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value.lower())


def _p95(values):
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def _canonical_route_inventory():
    """Original V29.3 frozen route matrix; no caller-supplied pseudo-92 paths."""
    path = Path(__file__).resolve().parents[1] / 'NOX_V98_WEB_FULL_REAL_API_MATRIX.json'
    if path.is_symlink():
        raise ValueError('HOLD_CANONICAL_92_ROUTE_INVENTORY')
    try:
        rows = json.loads(path.read_text(encoding='utf-8'))['functions']
        routes = [row['route'] for row in rows]
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ValueError('HOLD_CANONICAL_92_ROUTE_INVENTORY') from exc
    if (len(routes) != EXPECTED_ROUTE_TARGET or len(set(routes)) != EXPECTED_ROUTE_TARGET or
        any(not isinstance(x, str) or not x.startswith('/') for x in routes)):
        raise ValueError('HOLD_CANONICAL_92_ROUTE_INVENTORY')
    return frozenset(routes)


def training_status(raw):
    """Explicit unknown/defaults: never promote a self-declared status to verified native."""
    row = raw if isinstance(raw, dict) else {}
    raw_stage = row.get('stage')
    stage = raw_stage if isinstance(raw_stage, str) and raw_stage in STAGES else 'UNKNOWN'
    lineage = (row.get('base_sha256') if _hex64(row.get('base_sha256')) else None)
    tokenizer = (row.get('tokenizer_sha256') if _hex64(row.get('tokenizer_sha256')) else None)
    step = row.get('global_step')
    if not (isinstance(step, int) and not isinstance(step, bool) and step >= 0):
        step = None
    stop = row.get('manual_stop_latched')
    stop = stop if type(stop) is bool else None
    if not (lineage and tokenizer):
        stage = 'UNKNOWN'
    return {
        'stage_reported_unverified': stage,
        'base_sha256_reported_unverified': lineage,
        'tokenizer_sha256_reported_unverified': tokenizer,
        'global_step_reported_unverified': step,
        'manual_stop_latched_reported_unverified': stop,
        'native_training_verified': False,
        'live_promoted_verified': False,
        'stop_resume_controls': 'DISABLED_NEEDS_OWNER_FENCED_NATIVE_CALLBACKS',
        'readback_state': 'HOLD_NO_AUTHENTICATED_NATIVE_SIGNED_EVIDENCE',
    }


def stream_stats(rows):
    """Source-only metric consistency; replay cannot increase unique TTFT samples."""
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError('INVALID_STREAM_RECEIPTS')
    unique, conflicted, s03_owners = {}, set(), {}
    rejected = 0
    for row in rows:
        if not isinstance(row, dict):
            rejected += 1
            continue
        req, s03 = row.get('request_sha256'), row.get('s03_receipt_sha256')
        if not _hex64(req) or not _hex64(s03):
            rejected += 1
            continue
        req, s03 = req.lower(), s03.lower()
        signature = (s03, row.get('owner_authenticated'), row.get('completed'),
                     row.get('s03_saved'), row.get('s03_integrated'),
                     row.get('terminal_event'), row.get('ttft_ms'),
                     row.get('native_completion_tokens'), row.get('decode_elapsed_ms'),
                     row.get('native_usage_source'))
        if req in unique:
            rejected += 1
            if unique[req][1] != signature:
                conflicted.add(req)
        else:
            unique[req] = (row, signature)
        if s03 in s03_owners and s03_owners[s03] != req:
            conflicted.update((req, s03_owners[s03]))
        else:
            s03_owners[s03] = req
    accepted, tps_samples = [], []
    for req, (row, signature) in unique.items():
        if req in conflicted:
            rejected += 1
            continue
        if (row.get('owner_authenticated') is not True or
            row.get('completed') is not True or
            row.get('s03_saved') is not True or
            row.get('s03_integrated') is not True or
            row.get('terminal_event') != 'done' or
            not _number(row.get('ttft_ms'), strictly_positive=True,
                        max_value=MAX_OBSERVATION_MS)):
            rejected += 1
            continue
        accepted.append(row['ttft_ms'])
        n, duration = row.get('native_completion_tokens'), row.get('decode_elapsed_ms')
        if (row.get('native_usage_source') == 'ORIGINAL_ENGINE_COMPLETION_TOKENS' and
            isinstance(n, int) and not isinstance(n, bool) and n > 0 and
            _number(duration, strictly_positive=True,
                    max_value=MAX_OBSERVATION_MS)):
            try:
                measured_tps = 1000 * n / duration
            except (OverflowError, ZeroDivisionError):
                measured_tps = None
            if _number(measured_tps, strictly_positive=True):
                tps_samples.append(measured_tps)
    return {
        'measured_source_receipts': len(accepted),
        'rejected_or_incomplete_receipts': rejected,
        'conflicted_request_receipts': len(conflicted),
        'ttft_p50_ms': statistics.median(accepted) if accepted else None,
        'ttft_p95_ms': _p95(accepted) if accepted else None,
        'decode_tps_median': statistics.median(tps_samples) if tps_samples else None,
        'decode_tps_samples': len(tps_samples),
        'warning': 'SOURCE_RECEIPT_CONSISTENCY_ONLY_NOT_NATIVE_ATTESTATION',
    }


def route_coverage(rows, inventory):
    """Count consistent source-only successes from exact original routes.

    A successful route receipt contradicted by a failed / unauthenticated /
    schema-invalid receipt for the same exact path is quarantined rather than
    spuriously reported as a passing original route.
    """
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError('INVALID_ROUTE_RECEIPTS')
    if (not isinstance(inventory, (set, frozenset)) or len(inventory) != EXPECTED_ROUTE_TARGET or
        any(not isinstance(p, str) or not p.startswith('/') for p in inventory)):
        raise ValueError('HOLD_CANONICAL_92_ROUTE_INVENTORY')
    passed, contradicted = set(), set()
    rejected = 0
    unmapped = 0
    for row in rows:
        if not isinstance(row, dict):
            rejected += 1
            continue
        path = row.get('path')
        if (not isinstance(path, str) or not path.startswith('/') or
            len(path) > 256 or '://' in path or '?' in path or '#' in path or '..' in path):
            rejected += 1
            continue
        source_pass = (row.get('owner_authenticated') is True and
                       row.get('http_status') == 200 and
                       row.get('schema_checked') is True)
        if path not in inventory:
            if source_pass:
                unmapped += 1
            else:
                rejected += 1
            continue
        if not source_pass:
            contradicted.add(path)
            rejected += 1
            continue
        passed.add(path)
    return {
        'expected_route_inventory_target_not_live_claim': EXPECTED_ROUTE_TARGET,
        'owner_schema_200_source_receipts': len(passed - contradicted),
        'contradictory_route_source_paths': len(passed & contradicted),
        'owner_schema_200_outside_original_inventory': unmapped,
        'rejected_route_receipts': rejected,
        'full_live_92_route_e2e_verified': False,
        'note': 'Conflicting same-path outcomes held; source checks only, not live 92-route E2E.',
    }


def audit(payload):
    if not isinstance(payload, dict):
        raise ValueError('INVALID_AUDIT_PAYLOAD')
    return {
        'schema': 'NOX_HYBRID_2C_SOURCE_WEB_AUDIT_V1',
        'native_verified': False,
        'web_deployed': False,
        'onehost_modified': False,
        'training': training_status(payload.get('training')),
        'stream': stream_stats(payload.get('streams', [])),
        'routes': route_coverage(payload.get('routes', []), _canonical_route_inventory()),
        'lesson': 'Never count SSE deltas as tokens; do not enable STOP/RESUME or promote models from unsigned status or source-only route receipts.',
    }


def selftest():
    h = 'a' * 64
    s = {'owner_authenticated': True, 'completed': True, 's03_saved': True,
         's03_integrated': True, 'terminal_event': 'done', 'ttft_ms': 150.0,
         'request_sha256': h, 's03_receipt_sha256': '1' * 64}
    assert stream_stats([])['ttft_p95_ms'] is None
    assert stream_stats([s])['ttft_p50_ms'] == 150
    assert stream_stats([s])['decode_tps_median'] is None
    assert stream_stats([dict(s, delta_count=99)])['decode_tps_median'] is None
    assert stream_stats([dict(s, native_completion_tokens=20, decode_elapsed_ms=1000,
                              native_usage_source='ORIGINAL_ENGINE_COMPLETION_TOKENS')])['decode_tps_median'] == 20
    assert stream_stats([dict(s, owner_authenticated=False)])['measured_source_receipts'] == 0
    assert stream_stats([dict(s, s03_saved=False)])['measured_source_receipts'] == 0
    assert stream_stats([dict(s, terminal_event='error')])['measured_source_receipts'] == 0
    assert stream_stats([dict(s, ttft_ms=float('nan'))])['measured_source_receipts'] == 0
    assert training_status({'stage':'lora','base_sha256':h,'tokenizer_sha256':h,
                             'global_step':5})['global_step_reported_unverified'] == 5
    assert training_status({'stage':'live_promoted','base_sha256':h,'tokenizer_sha256':h,
                             'global_step':100,'native_verified':True})['live_promoted_verified'] is False
    assert training_status({'stage':'lora','global_step':True})['global_step_reported_unverified'] is None
    assert training_status({})['stop_resume_controls'].startswith('DISABLED_')
    inventory = _canonical_route_inventory()
    route={'path':sorted(inventory)[0],'http_status':200,'owner_authenticated':True,'schema_checked':True}
    assert route_coverage([route,route], inventory)['owner_schema_200_source_receipts']==1
    # Mixed positive/negative source outcomes on the same route must fail closed.
    assert route_coverage([route,dict(route,http_status=503)],inventory)['owner_schema_200_source_receipts']==0
    assert route_coverage([dict(route,http_status=503),route],inventory)['owner_schema_200_source_receipts']==0
    assert route_coverage([route,dict(route,schema_checked=False)],inventory)['owner_schema_200_source_receipts']==0
    assert route_coverage([route,dict(route,owner_authenticated=False)],inventory)['owner_schema_200_source_receipts']==0
    assert route_coverage([dict(route,http_status=503)],inventory)['owner_schema_200_source_receipts']==0
    assert route_coverage([route,dict(route,http_status=503)],inventory)['contradictory_route_source_paths']==1
    assert route_coverage([dict(route,owner_authenticated=False)], inventory)['owner_schema_200_source_receipts']==0
    assert route_coverage([dict(route,path='/api/../admin')], inventory)['owner_schema_200_source_receipts']==0
    assert stream_stats([s,s])['measured_source_receipts']==1
    assert stream_stats([s,s])['rejected_or_incomplete_receipts']==1
    assert stream_stats([s,dict(s,ttft_ms=300)])['measured_source_receipts']==0
    assert stream_stats([s,dict(s,owner_authenticated=False)])['measured_source_receipts']==0
    assert stream_stats([s,dict(s,s03_saved=False)])['measured_source_receipts']==0
    assert stream_stats([s,dict(s,request_sha256='b'*64)])['measured_source_receipts']==0
    assert stream_stats([dict(s,request_sha256=None)])['measured_source_receipts']==0
    assert route_coverage([dict(route,path='/not-in-original-inventory')], inventory)['owner_schema_200_source_receipts']==0
    assert audit({})['native_verified'] is False
    assert training_status({'stage': []})['stage_reported_unverified'] == 'UNKNOWN'
    assert training_status({'stage': {}})['stage_reported_unverified'] == 'UNKNOWN'
    assert stream_stats([dict(s, ttft_ms=10**400)])['measured_source_receipts'] == 0
    assert stream_stats([dict(s, native_completion_tokens=10**400, decode_elapsed_ms=1000,
                              native_usage_source='ORIGINAL_ENGINE_COMPLETION_TOKENS')])['decode_tps_samples'] == 0
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / 'existing.json'
        output.write_text('PRESERVE_ORIGINAL', encoding='utf-8')
        try:
            _write_report_exclusive(output, audit({}))
        except ValueError as exc:
            assert str(exc) == 'HOLD_OUTPUT_PATH_EXISTS'
        else:
            raise AssertionError('OUTPUT_OVERWRITE_NOT_BLOCKED')
        assert output.read_text(encoding='utf-8') == 'PRESERVE_ORIGINAL'
        fresh = Path(tmp) / 'new.json'
        _write_report_exclusive(fresh, audit({}))
        assert json.loads(fresh.read_text(encoding='utf-8'))['native_verified'] is False
    # A syntactically finite but absurd TTFT can overflow statistics.median
    # (1e308 + 1e308) / 2 into inf. It must not become a source metric.
    extreme = dict(s, ttft_ms=1e308)
    other_extreme = dict(extreme, request_sha256='b' * 64, s03_receipt_sha256='2' * 64)
    extreme_result = stream_stats([extreme, other_extreme])
    assert extreme_result['measured_source_receipts'] == 0
    assert extreme_result['ttft_p50_ms'] is None
    assert extreme_result['ttft_p95_ms'] is None
    assert stream_stats([dict(s, ttft_ms=MAX_OBSERVATION_MS + 1)])['measured_source_receipts'] == 0
    assert stream_stats([dict(s, native_completion_tokens=20, decode_elapsed_ms=1e308,
                              native_usage_source='ORIGINAL_ENGINE_COMPLETION_TOKENS')])['decode_tps_samples'] == 0
    # Source report must be valid strict JSON rather than Python-specific Infinity.
    json.dumps(audit({'streams': [extreme, other_extreme]}), allow_nan=False)
    print('SELFTEST 44/44 PASS - synthesized fixtures; native/live UNKNOWN')


def _write_report_exclusive(path: Path, report: dict) -> None:
    """Never clobber an existing receipt, S03 path or symlink from --out."""
    try:
        with path.open('x', encoding='utf-8') as handle:
            handle.write(json.dumps(report, ensure_ascii=False, sort_keys=True,
                                        indent=2, allow_nan=False) + '\n')
    except FileExistsError as exc:
        raise ValueError('HOLD_OUTPUT_PATH_EXISTS') from exc


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selftest',action='store_true')
    p.add_argument('--input',type=Path)
    p.add_argument('--out',type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
        return 0
    if not a.input or not a.out:
        p.error('--input and --out are required for source audit')
    data = json.loads(a.input.read_text(encoding='utf-8'))
    report = audit(data)
    # Do not serialize input: even a malformed user-provided field could contain credentials.
    try:
        _write_report_exclusive(a.out, report)
    except ValueError as exc:
        p.error(str(exc))
    print('NOX_2C_SOURCE_AUDIT_WRITTEN; native_verified=false; web_deployed=false')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
