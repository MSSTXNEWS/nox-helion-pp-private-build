#!/usr/bin/env python3
"""NOX V40 evidence-only 3-axis learning meter; never manufactures intelligence percentages.

Read-only, pure computation unless --out is explicitly provided. Inputs must
come from native trusted OneHost/S03/FORGE receipts, not assistant prose.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

HEX = re.compile(r"^[0-9a-f]{64}$")
WEIGHTS = {'knowledge': 0.30, 'skills': 0.35, 'weights': 0.35}
SCHEMA = 'nox-learning-3axes-evidence-v1'
OUTPUT = 'nox-learning-3axes-dashboard-v1'


def _hold(reason: str):
    return {'state': 'HOLD', 'percent': None, 'reason': reason}


def _positive_int(v):
    return type(v) is int and v > 0


def _count_int(v):
    return type(v) is int and v >= 0


def _sha(v):
    return isinstance(v, str) and bool(HEX.fullmatch(v.lower()))


def _proof_meta(v):
    return isinstance(v, dict) and v.get('native_verified') is True and _sha(v.get('receipt_sha256')) and isinstance(v.get('source_uri'), str) and v['source_uri'].startswith(('s03://', 'nox-checkpoint://', 'https://'))


def _assess_axis(kind, v):
    if not _proof_meta(v):
        return _hold('NO_NATIVE_PROOF')
    if kind in ('knowledge', 'skills'):
        # Proof of a fixed, source-disjoint evaluation suite, not a raw memory size.
        if not (_positive_int(v.get('total_tests')) and _count_int(v.get('passed_tests')) and v['passed_tests'] <= v['total_tests']):
            return _hold('INVALID_BENCHMARK_COUNTS')
        if not (_sha(v.get('suite_sha256')) and v.get('independent_evaluator') is True and v.get('source_disjoint') is True):
            return _hold('NO_INDEPENDENT_BENCHMARK')
        if kind == 'knowledge' and v.get('s03_recall_verified') is not True:
            return _hold('S03_RECALL_UNVERIFIED')
        if kind == 'skills' and v.get('regression_suite_passed') is not True:
            return _hold('NO_SKILL_RETENTION_PROOF')
        count = v['passed_tests']; total = v['total_tests']
        return {'state':'VERIFIED','percent': round(100 * count / total, 1),
                'passed':count,'total':total,'receipt':v['receipt_sha256'], 'source':v['source_uri']}
    if kind == 'weights':
        if not (_positive_int(v.get('target_optimizer_steps')) and _count_int(v.get('checkpointed_optimizer_steps')) and v['checkpointed_optimizer_steps'] <= v['target_optimizer_steps']):
            return _hold('INVALID_OPTIMIZER_COUNTS')
        if not all(_sha(v.get(k)) for k in ('baseline_model_sha256', 'student_weights_sha256', 'checkpoint_sha256', 'optimizer_receipt_sha256')):
            return _hold('WEIGHT_FINGERPRINT_MISSING')
        if v['baseline_model_sha256'] == v['student_weights_sha256']:
            return _hold('NO_STUDENT_WEIGHT_DELTA')
        if v.get('real_optimizer_verified') is not True or v.get('checkpoint_reload_verified') is not True:
            return _hold('NO_OPTIMIZER_OR_RELOAD_PROOF')
        count = v['checkpointed_optimizer_steps']; total = v['target_optimizer_steps']
        return {'state':'VERIFIED','percent':round(100 * count / total, 1),
                'passed':count,'total':total,'receipt':v['receipt_sha256'], 'source':v['source_uri'],
                'quality_gate_passed':v.get('independent_holdout_passed') is True}
    return _hold('INVALID_AXIS')


def assess(document: dict) -> dict:
    state = {'schema':OUTPUT,'at_utc':datetime.now(timezone.utc).isoformat(),
             'axes':{k:_hold('NO_EVIDENCE') for k in WEIGHTS},
             'overall':_hold('INCOMPLETE_VERIFIED_AXES'),
             'overall_release_accepted':False,
             'gpu_target_compute_percent':85,
             'note':'Progress of fixed, versioned checks. NOT a measure of consciousness or all possible intelligence.'}
    if not isinstance(document, dict) or document.get('schema') != SCHEMA:
        state['source_state']='HOLD_SCHEMA';return state
    src = document.get('axes', {})
    if not isinstance(src,dict):
        state['source_state']='HOLD_AXES_TYPE';return state
    for k in WEIGHTS:state['axes'][k]=_assess_axis(k,src.get(k))
    state['source_state']='SOURCE_READ'
    if all(state['axes'][k]['state']=='VERIFIED' for k in WEIGHTS):
        score = sum(state['axes'][k]['percent']*WEIGHTS[k] for k in WEIGHTS)
        state['overall']={'state':'VERIFIED','percent':round(score,1), 'formula':'30% knowledge + 35% skills + 35% weights'}
        # 100% is an acceptance of a bounded version, never 'perfect intelligence'.
        accepted=bool(all(state['axes'][k]['percent'] == 100 for k in WEIGHTS)
                      and src['weights'].get('independent_holdout_passed') is True
                      and document.get('native_onehost_stop_test_passed') is True
                      and document.get('s03_restart_restore_test_passed') is True
                      and document.get('production_e2e_passed') is True)
        state['overall_release_accepted']=accepted
        if state['overall']['percent']==100 and not accepted:
            state['overall']['state']='HOLD_RELEASE_GATE';state['overall']['percent']=None
    return state


def main():
    a=argparse.ArgumentParser()
    a.add_argument('--evidence',required=True,help='Owner-approved read-only JSON from native OneHost')
    a.add_argument('--out',help='Staged dashboard JSON only; no server deployment')
    args=a.parse_args()
    path=Path(args.evidence)
    if path.stat().st_size>2*1024*1024:raise SystemExit('HOLD_EVIDENCE_OVERSIZE')
    result=assess(json.loads(path.read_text('utf-8')))
    content=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.out:
        dest=Path(args.out)
        if not dest.parent.exists():raise SystemExit('HOLD_OUTPUT_PARENT_MISSING')
        if dest.exists():raise SystemExit('HOLD_NO_OVERWRITE_OF_EXISTING_RECEIPT')
        dest.write_text(content,encoding='utf-8')
    else:print(content,end='')

if __name__=='__main__':main()
