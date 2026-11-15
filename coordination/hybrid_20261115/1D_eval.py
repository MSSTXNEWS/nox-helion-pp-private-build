#!/usr/bin/env python3
"""NOX AUTO 1D offline comparison gate. Never executes models or untrusted code.

Input files are owner-generated evidence. Passing source consistency does NOT
authenticate their claims, establish native training, or authorize promotion.
"""
import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

REQUIRED_CATEGORIES = {'ru_dialogue', 'es_dialogue', 'code', 'memory', 'identity', 'emotion', 'forgetting'}
REQUIRED_CHECKS = {
    'ru_dialogue': {'relevance', 'accuracy'},
    'es_dialogue': {'relevance', 'accuracy'},
    'code': {'sandbox_pass'},
    'memory': {'owner_acl', 's03_retrieval', 's03_retention'},
    'identity': {'origin_grounded', 'limits_honest'},
    'emotion': {'appropriate', 'non_manipulative'},
    'forgetting': {'retention'},
}
POLICY_KEYS = {'max_quality_drop_pp', 'max_ttft_p95_increase_pct', 'min_tps_ratio', 'max_vram_bytes', 'max_logit_abs_delta'}
HEX = set('0123456789abcdef')


def digest_ok(x):
    return isinstance(x, str) and len(x) == 64 and set(x.lower()) <= HEX


def finite(x, positive=False):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and (x > 0 if positive else x >= 0)


def load(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate_run(run, label):
    require(isinstance(run, dict), f'{label}: JSON object required')
    meta = run.get('run')
    cases = run.get('cases')
    require(isinstance(meta, dict) and isinstance(cases, list) and cases, f'{label}: run/cases missing')
    for key in ('base_sha256', 'tokenizer_sha256', 'generation_sha256', 'dataset_sha256'):
        require(digest_ok(meta.get(key)), f'{label}: missing or invalid {key}')
    for key in ('variant', 'hardware_id', 'engine_build', 'evidence_origin'):
        require(isinstance(meta.get(key), str) and meta[key].strip(), f'{label}: missing {key}')
    require(meta['evidence_origin'] == 'native_measurement', f'{label}: native measurement provenance not supplied')
    unique = {}
    fingerprints = set()
    for case in cases:
        require(isinstance(case, dict), f'{label}: case must be object')
        cid = case.get('case_id')
        require(isinstance(cid, str) and cid and cid not in unique, f'{label}: duplicate/missing case ID')
        require(case.get('split') == 'holdout', f'{label}/{cid}: not independent holdout')
        cat = case.get('category')
        require(cat in REQUIRED_CATEGORIES, f'{label}/{cid}: unrecognized category')
        locale = case.get('locale')
        require(locale in ('ru', 'es'), f'{label}/{cid}: missing locale')
        if cat == 'ru_dialogue':
            require(locale == 'ru', f'{label}/{cid}: wrong RU locale')
        if cat == 'es_dialogue':
            require(locale == 'es', f'{label}/{cid}: wrong ES locale')
        for key in ('prompt_sha256', 'answer_sha256', 'evaluation_sha256'):
            require(digest_ok(case.get(key)), f'{label}/{cid}: missing {key}')
        fingerprint = case['prompt_sha256'].lower()
        require(fingerprint not in fingerprints, f'{label}/{cid}: duplicated prompt fingerprint')
        fingerprints.add(fingerprint)
        checks = case.get('checks')
        require(isinstance(checks, dict) and REQUIRED_CHECKS[cat] <= checks.keys(), f'{label}/{cid}: checks incomplete')
        require(all(type(checks[key]) is bool for key in REQUIRED_CHECKS[cat]), f'{label}/{cid}: non-boolean check')
        require(isinstance(case.get('reviewer_receipt'), str) and case['reviewer_receipt'], f'{label}/{cid}: missing independent review reference')
        for metric in ('ttft_ms', 'decode_tps', 'peak_vram_bytes'):
            require(finite(case.get(metric), positive=(metric != 'peak_vram_bytes')), f'{label}/{cid}: missing real {metric}')
        if cat == 'code':
            sandbox = case.get('sandbox') or {}
            require(isinstance(sandbox, dict) and sandbox.get('network_disabled') is True
                    and isinstance(sandbox.get('run_id'), str) and sandbox['run_id'],
                    f'{label}/{cid}: isolated no-network code execution receipt missing')
        if cat == 'memory':
            require(digest_ok(case.get('s03_receipt_sha256')), f'{label}/{cid}: durable S03 receipt missing')
        unique[cid] = case
    require({c['category'] for c in cases} >= REQUIRED_CATEGORIES, f'{label}: RU/ES/code/memory/identity/emotion/forgetting coverage incomplete')
    return meta, unique


def percentile95(vals):
    v = sorted(vals)
    return v[math.ceil(len(v) * .95) - 1]


def evaluate(reference, candidate, train_manifest, policy):
    ref, r = validate_run(reference, 'reference')
    cand, c = validate_run(candidate, 'candidate')
    require(isinstance(train_manifest, dict) and isinstance(train_manifest.get('prompt_sha256'), list), 'train manifest fingerprints missing')
    raw_train = train_manifest['prompt_sha256']
    require(all(digest_ok(x) for x in raw_train), 'train manifest malformed fingerprints')
    require(bool(raw_train), 'empty train manifest cannot establish holdout separation')
    train = [value.lower() for value in raw_train]
    require(len(set(train)) == len(train), 'duplicate train fingerprints')
    holdout = {v['prompt_sha256'].lower() for v in r.values()}
    require(not (set(train) & holdout), 'TRAIN_HOLDOUT_LEAKAGE')
    require(set(r) == set(c), 'case_id coverage drift')
    for key in ('base_sha256', 'tokenizer_sha256', 'generation_sha256', 'dataset_sha256', 'hardware_id', 'engine_build'):
        a_value = ref[key].lower() if key.endswith('_sha256') else ref[key]
        b_value = cand[key].lower() if key.endswith('_sha256') else cand[key]
        require(a_value == b_value, f'UNPAIRED_COMPARISON:{key}')
    require(ref['variant'] != cand['variant'], 'same variant: comparison not meaningful')
    for cid in r:
        for k in ('prompt_sha256', 'category', 'locale', 'split'):
            a_value = r[cid][k].lower() if k == 'prompt_sha256' else r[cid][k]
            b_value = c[cid][k].lower() if k == 'prompt_sha256' else c[cid][k]
            require(a_value == b_value, f'{cid}: mismatched {k}')
    require(isinstance(policy, dict) and POLICY_KEYS <= policy.keys(), 'owner-approved numerical policy missing')
    require(all(finite(policy[k]) for k in POLICY_KEYS), 'invalid numerical policy')
    require(policy['min_tps_ratio'] > 0, 'min_tps_ratio must be positive')
    require(policy['max_vram_bytes'] > 0, 'max_vram_bytes must be positive')
    ref_pass = sum(all(x['checks'][k] for k in REQUIRED_CHECKS[x['category']]) for x in r.values())
    can_pass = sum(all(x['checks'][k] for k in REQUIRED_CHECKS[x['category']]) for x in c.values())
    quality_drop_pp = 100 * (ref_pass - can_pass) / len(r)
    regressions = sorted(cid for cid in r if
                         all(r[cid]['checks'][k] for k in REQUIRED_CHECKS[r[cid]['category']]) and
                         not all(c[cid]['checks'][k] for k in REQUIRED_CHECKS[c[cid]['category']]))
    p95_ref = percentile95([x['ttft_ms'] for x in r.values()])
    p95_can = percentile95([x['ttft_ms'] for x in c.values()])
    tps_ratio = statistics.median(x['decode_tps'] for x in c.values()) / statistics.median(x['decode_tps'] for x in r.values())
    vram_max = max(x['peak_vram_bytes'] for x in c.values())
    deltas = [x.get('max_logit_abs_delta') for x in c.values()]
    require(all(finite(x) for x in deltas), 'candidate measured logit delta missing')
    tests = {
        'quality': quality_drop_pp <= policy['max_quality_drop_pp'],
        'critical_regression': not regressions,
        'ttft_p95': (p95_can / p95_ref - 1) * 100 <= policy['max_ttft_p95_increase_pct'],
        'tokens_per_sec': tps_ratio >= policy['min_tps_ratio'],
        'vram': vram_max <= policy['max_vram_bytes'],
        'logit_max_abs_delta': max(deltas) <= policy['max_logit_abs_delta'],
    }
    return {
        'schema': 'NOX_1D_SOURCE_EVIDENCE_GATE_V1',
        'source_consistency': 'PASS' if all(tests.values()) else 'FAIL',
        'native_verified': False,
        'live_promoted': False,
        'rollback_tested': False,
        'note': 'External owner-signed native receipt, independent evaluator provenance and live rollback readback require separate verification. No promotion by this script.',
        'reference_variant': ref['variant'], 'candidate_variant': cand['variant'],
        'case_count': len(r), 'reference_passed': ref_pass, 'candidate_passed': can_pass,
        'regression_case_ids': regressions,
        'quality_drop_pp': quality_drop_pp,
        'ttft_p95_reference_ms': p95_ref, 'ttft_p95_candidate_ms': p95_can,
        'median_tps_ratio': tps_ratio, 'candidate_max_vram_bytes': vram_max,
        'candidate_max_logit_abs_delta': max(deltas), 'policy_checks': tests,
    }


def selftest():
    h = lambda value: hashlib.sha256(value.encode()).hexdigest()
    def make_run(variant):
        cases = []
        for i, cat in enumerate(sorted(REQUIRED_CATEGORIES)):
            checks = {k: True for k in REQUIRED_CHECKS[cat]}
            row = dict(case_id=f't{i}', split='holdout', category=cat,
                       locale='es' if cat == 'es_dialogue' else 'ru',
                       prompt_sha256=h('prompt'+str(i)), answer_sha256=h(variant+str(i)),
                       evaluation_sha256=h('review'+str(i)), checks=checks,
                       reviewer_receipt='isolated-fixture-only', ttft_ms=100,
                       decode_tps=25, peak_vram_bytes=1000, max_logit_abs_delta=0.01)
            if cat == 'code': row['sandbox'] = {'network_disabled': True, 'run_id': 'synthetic'}
            if cat == 'memory': row['s03_receipt_sha256'] = h('synthetic S03')
            cases.append(row)
        meta = dict(variant=variant, base_sha256=h('base'), tokenizer_sha256=h('tokenizer'),
                    generation_sha256=h('generation'), dataset_sha256=h('dataset'),
                    hardware_id='fixture-v100', engine_build='synthetic', evidence_origin='native_measurement')
        return {'run': meta, 'cases': cases}
    a, b = make_run('adapter'), make_run('merged')
    pol = dict(max_quality_drop_pp=0, max_ttft_p95_increase_pct=0,
               min_tps_ratio=1, max_vram_bytes=1000, max_logit_abs_delta=.02)
    result = evaluate(a, b, {'prompt_sha256': [h('train')]}, pol)
    assert result['source_consistency'] == 'PASS' and result['native_verified'] is False
    # Empty train evidence must never pass as proof of separation.
    try: evaluate(a, b, {'prompt_sha256': []}, pol)
    except ValueError as exc: assert 'empty train manifest' in str(exc)
    else: raise AssertionError('empty training provenance accepted')
    # SHA-256 hex is case-insensitive; mixed-case hashes must never bypass holdout separation.
    try: evaluate(a, b, {'prompt_sha256': [a['cases'][0]['prompt_sha256'].upper()]}, pol)
    except ValueError as exc: assert 'LEAKAGE' in str(exc)
    else: raise AssertionError('uppercase train fingerprint bypassed holdout')
    try: evaluate(a, b, {'prompt_sha256': [h('train'), h('train').upper()]}, pol)
    except ValueError as exc: assert 'duplicate train' in str(exc)
    else: raise AssertionError('mixed-case train duplicate accepted')
    duplicate_run = make_run('duplicate')
    duplicate_run['cases'].append(dict(duplicate_run['cases'][0],
                                      case_id='duplicate-shadow',
                                      prompt_sha256=duplicate_run['cases'][0]['prompt_sha256'].upper()))
    try: validate_run(duplicate_run, 'duplicate')
    except ValueError as exc: assert 'duplicated prompt fingerprint' in str(exc)
    else: raise AssertionError('mixed-case holdout duplicate accepted')
    upper_candidate = make_run('merged')
    upper_candidate['cases'][0]['prompt_sha256'] = upper_candidate['cases'][0]['prompt_sha256'].upper()
    upper_candidate['run']['base_sha256'] = upper_candidate['run']['base_sha256'].upper()
    assert evaluate(a, upper_candidate, {'prompt_sha256': [h('train')]}, pol)['source_consistency'] == 'PASS'
    try: evaluate(a, b, {'prompt_sha256': [a['cases'][0]['prompt_sha256']]}, pol)
    except ValueError as exc: assert 'LEAKAGE' in str(exc)
    else: raise AssertionError('leakage not detected')
    b['cases'][0]['checks'][next(iter(b['cases'][0]['checks']))] = False
    assert evaluate(a, b, {'prompt_sha256': [h('train')]}, pol)['source_consistency'] == 'FAIL'
    b['cases'][0]['checks'] = a['cases'][0]['checks'].copy()
    del b['cases'][-1]['max_logit_abs_delta']
    try: evaluate(a, b, {'prompt_sha256': [h('train')]}, pol)
    except ValueError as exc: assert 'logit delta' in str(exc)
    else: raise AssertionError('missing logit metric not detected')
    print('SELFTEST 9/9 PASS (synthetic fixtures only; native HOLD)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference')
    parser.add_argument('--candidate')
    parser.add_argument('--train-manifest')
    parser.add_argument('--policy')
    parser.add_argument('--out')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest(); return 0
    try:
        require(all((args.reference, args.candidate, args.train_manifest, args.policy, args.out)), 'input paths required')
        result = evaluate(load(args.reference), load(args.candidate), load(args.train_manifest), load(args.policy))
        status = result['source_consistency']
        code = 0 if status == 'PASS' else 2
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        result = {'schema': 'NOX_1D_SOURCE_EVIDENCE_GATE_V1', 'source_consistency': 'HOLD',
                  'native_verified': False, 'live_promoted': False, 'reason': str(exc)}
        code = 2
    Path(args.out or '1D_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'source_consistency': result['source_consistency'], 'native_verified': False, 'result': args.out}, ensure_ascii=False))
    return code


if __name__ == '__main__':
    sys.exit(main())
