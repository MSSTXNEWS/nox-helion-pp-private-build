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
from pathlib import Path

MAX_ROWS = 2048
EXPECTED_ROUTE_TARGET = 92
STAGES = {"baseline", "lora", "qlora", "merged_fp16", "full_distill", "quantized", "live_promoted"}


def _number(value, *, strictly_positive=False):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (value > 0 if strictly_positive else value >= 0))


def _hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value.lower())


def _p95(values):
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def training_status(raw):
    """Explicit unknown/defaults: never promote a self-declared status to verified native."""
    row = raw if isinstance(raw, dict) else {}
    stage = row.get('stage') if row.get('stage') in STAGES else 'UNKNOWN'
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
    """TTFT is first actual delta onset; SSE chunk count is never token count."""
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError('INVALID_STREAM_RECEIPTS')
    accepted = []
    rejected = 0
    tps_samples = []
    for row in rows:
        if not isinstance(row, dict):
            rejected += 1
            continue
        if (row.get('owner_authenticated') is not True or
            row.get('completed') is not True or
            row.get('s03_saved') is not True or
            row.get('s03_integrated') is not True or
            row.get('terminal_event') != 'done' or
            not _number(row.get('ttft_ms'), strictly_positive=True)):
            rejected += 1
            continue
        accepted.append(row['ttft_ms'])
        n = row.get('native_completion_tokens')
        duration = row.get('decode_elapsed_ms')
        if (row.get('native_usage_source') == 'ORIGINAL_ENGINE_COMPLETION_TOKENS' and
            isinstance(n, int) and not isinstance(n, bool) and n > 0 and
            _number(duration, strictly_positive=True)):
            tps_samples.append(1000 * n / duration)
    return {
        'measured_source_receipts': len(accepted),
        'rejected_or_incomplete_receipts': rejected,
        'ttft_p50_ms': statistics.median(accepted) if accepted else None,
        'ttft_p95_ms': _p95(accepted) if accepted else None,
        'decode_tps_median': statistics.median(tps_samples) if tps_samples else None,
        'decode_tps_samples': len(tps_samples),
        'warning': 'SOURCE_RECEIPT_CONSISTENCY_ONLY_NOT_NATIVE_ATTESTATION',
    }


def route_coverage(rows):
    """Only observed owner-scoped successful HTTP responses count; never 92 by assumption."""
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError('INVALID_ROUTE_RECEIPTS')
    unique = set()
    rejected = 0
    for row in rows:
        if not isinstance(row, dict):
            rejected += 1
            continue
        path = row.get('path')
        if (not isinstance(path, str) or not path.startswith('/') or
            len(path) > 256 or '://' in path or '?' in path or '#' in path or '..' in path or
            row.get('owner_authenticated') is not True or
            row.get('http_status') != 200 or
            row.get('schema_checked') is not True):
            rejected += 1
            continue
        unique.add(path)
    return {
        'expected_route_inventory_target_not_live_claim': EXPECTED_ROUTE_TARGET,
        'owner_schema_200_source_receipts': len(unique),
        'rejected_route_receipts': rejected,
        'full_live_92_route_e2e_verified': False,
        'note': 'Some routes require POST or additional state; a source receipt is not a signed live E2E.'
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
        'routes': route_coverage(payload.get('routes', [])),
        'lesson': 'Never count SSE deltas as tokens; do not enable STOP/RESUME or promote models from unsigned status or source-only route receipts.',
    }


def selftest():
    h = 'a' * 64
    s = {'owner_authenticated': True, 'completed': True, 's03_saved': True,
         's03_integrated': True, 'terminal_event': 'done', 'ttft_ms': 150.0}
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
    route={'path':'/api/nox/status','http_status':200,'owner_authenticated':True,'schema_checked':True}
    assert route_coverage([route,route])['owner_schema_200_source_receipts']==1
    assert route_coverage([dict(route,owner_authenticated=False)])['owner_schema_200_source_receipts']==0
    assert route_coverage([dict(route,path='/api/../admin')])['owner_schema_200_source_receipts']==0
    assert audit({})['native_verified'] is False
    print('SELFTEST 17/17 PASS - synthesized fixtures; native/live UNKNOWN')


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
    a.out.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print('NOX_2C_SOURCE_AUDIT_WRITTEN; native_verified=false; web_deployed=false')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
