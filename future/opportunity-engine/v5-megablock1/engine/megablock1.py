"""NOX OIE V5 · MEGA-BLOCK 1: reproducible, offline opportunity analysis.

A read-only evidence/selection pipeline. It NEVER interprets internet links or LLM
text as evidence of market demand. No grants, no deployment, no paid actions.
Only a future NOX owner-approved runtime can perform external pilot work.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from .pipeline import run_mission
from .discovery import load_seeds
from .gates import audit

CONTRACT = 'nox.oie.megablock1.v1'
ROLES = ('SCOUT', 'INVENTOR', 'SKEPTIC', 'PRODUCT_ARCHITECT', 'EVIDENCE_QA')
CORE_STAGES = ('DISCOVER', 'DIVERSIFY', 'CRITIQUE', 'PASSPORT', 'EVIDENCE_GATE', 'RECEIPT')

def stable_hash(value):
    """Portable SHA of a JSON value with exact UTF-8 canonical serialization."""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode('utf-8')
    return sha256(raw).hexdigest()

def _keywords(s):
    return set(re.findall(r'[^\W_]+', str(s).casefold(), flags=re.UNICODE)) - {
        'nox', 'ai', 'ии', 'the', 'and', 'with', 'для', 'это', 'продукт', 'сервис'}

def _similarity(a, b):
    a, b = _keywords(a), _keywords(b)
    return round(len(a & b) / len(a | b), 4) if a and b else 0.0

def _passport(item, original_titles):
    c = item['candidate']
    problem = c.get('problem', c.get('content', {}).get('problem', 'UNKNOWN'))
    benefit = c.get('first_5min_value', c.get('content', {}).get('first_value', 'UNKNOWN'))
    buyer = c.get('payer_hypothesis', c.get('content', {}).get('payer_hypothesis', 'UNKNOWN'))
    alternatives = item['critic']['alternatives_to_research']
    if not isinstance(alternatives, list): alternatives = []
    closest = sorted(((_similarity(c['name'], title), title)
                      for title in original_titles), reverse=True)[:3]
    closest = [{'title': title, 'internal_title_similarity': score}
               for score, title in closest if score > 0]
    blockers = ['MARKET_DEMAND_NOT_VERIFIED', 'PRIOR_ART_NOT_REVIEWED',
                'OWNER_PERMISSION_NOT_VERIFIED', 'PILOT_NOT_RUN']
    return {
        'idea_id': c['candidate_id'], 'name': c['name'],
        'stream': c.get('stream', 'UNCLASSIFIED'),
        'problem_hypothesis': problem, 'beneficiary': c.get('beneficiary', 'UNKNOWN'),
        'buyer_hypothesis': buyer, 'first_five_minutes': benefit,
        'technical_reuse_hypothesis': c.get('technical_reuse_hypothesis', []),
        'existing_alternative_to_check': alternatives,
        'falsification_test': c.get('first_falsification_test', c.get('content', {}).get('pilot_to_falsify', 'UNKNOWN')),
        'internal_catalog_nearest_titles_not_market_prior_art': closest,
        'risk_review': 'PENDING', 'external_demand_evidence': [],
        'independent_review': 'NOT_RUN', 'market_demand': 'UNKNOWN',
        'pilot_execution': 'NOT_AUTHORIZED', 'pilot_result': 'NOT_RUN',
        'status': 'IDEA_UNVERIFIED', 'decision': 'RESEARCH_REQUIRED',
        'missing_evidence': blockers,
    }

def _check_manifest(payload):
    """Check integrity, semantics, and honesty of one computed offline result."""
    errors = []
    if payload.get('contract') != CONTRACT: errors.append('CONTRACT_MISMATCH')
    if payload.get('status') != 'SOURCE_PREVIEW_ONLY': errors.append('UNSUPPORTED_STATUS')
    records = payload.get('passports')
    if not isinstance(records, list) or not records: return ['NO_PASSPORTS']
    ids = [x.get('idea_id') for x in records]
    if len(ids) != len(set(ids)):errors.append('DUPLICATE_CANDIDATE')
    if payload.get('counts', {}).get('proposals') != len(records):errors.append('COUNT_MISMATCH')
    if payload.get('verified_market_cases') != 0 or payload.get('pilots_started') != 0:
        errors.append('UNSUPPORTED_EXTERNAL_SUCCESS')
    if payload.get('r1_touched') is not False: errors.append('R1_BOUNDARY')
    for p in records:
        if p.get('status') != 'IDEA_UNVERIFIED' or p.get('pilot_execution') != 'NOT_AUTHORIZED':
            errors.append('ILLEGAL_PROMOTION:'+str(p.get('idea_id')))
        if p.get('market_demand') != 'UNKNOWN' or p.get('independent_review') != 'NOT_RUN':
            errors.append('UNSUPPORTED_EVIDENCE:'+str(p.get('idea_id')))
    receipts = payload.get('receipts', {})
    if receipts.get('passports_sha256') != stable_hash(records):errors.append('PASSPORTS_HASH_MISMATCH')
    if receipts.get('qa_sha256') != stable_hash({k: v for k, v in payload.items() if k != 'receipts'}):
        errors.append('FULL_RECEIPT_MISMATCH')
    return errors

def run_megablock1(catalog, *, count=3, seed=0, theme=''):
    """One real bounded offline mission, not a simulated customer/market study."""
    if not isinstance(catalog, list) or len(catalog) < 1: raise ValueError('EMPTY_CATALOG')
    if type(count) is not int or not 1 <= count <= 12: raise ValueError('INVALID_COUNT')
    if type(seed) is not int or not -1000000 <= seed <= 1000000: raise ValueError('INVALID_SEED')
    if not isinstance(theme, str) or len(theme) > 240: raise ValueError('INVALID_THEME')
    original = [i.get('name', '') for i in catalog]
    mission = run_mission(catalog, count=count, seed=seed, theme=theme.strip(),
                          provider='offline', research='none', network=False)
    passports = [_passport(item, original) for item in mission['results']]
    if not passports:raise ValueError('NO_MATCHING_CURATED_SEEDS')
    streams = Counter(p['stream'] for p in passports)
    inp = {'catalog_sha256': stable_hash(catalog),
           'problem_seeds_sha256': stable_hash(load_seeds()),
           'args_sha256': stable_hash({'count': count, 'seed': seed, 'theme': theme.strip()})}
    payload = {
        'contract': CONTRACT, 'source_revision': 'V5_MEGA1',
        'scope': 'OFFLINE_READ_ONLY', 'status': 'SOURCE_PREVIEW_ONLY',
        'stages': list(CORE_STAGES), 'agent_roles_are_specs_not_running_workers': list(ROLES),
        'input': inp, 'counts': {'requested': count, 'proposals': len(passports),
                                'distinct_streams': len(streams), 'catalog_ideas': len(catalog)},
        'stream_distribution': dict(sorted(streams.items())),
        'passports': passports, 'qa': {'market_demand_verification': 'NOT_RUN',
                                    'competitor_readback': 'NOT_RUN',
                                    'owner_grant': 'NOT_PRESENT',
                                    'independent_person_review': 'NOT_RUN',
                                    'recommendation': 'RESEARCH_BUT_DO_NOT_EXECUTE'},
        'verified_market_cases': 0, 'pilots_started': 0,
        'commercial_revenue_verified': 0, 'r1_touched': False,
        'negative_control': 'DO_NOT_TREAT_INTERNAL_TITLE_DISTANCE_AS_EXTERNAL_NOVELTY',
    }
    payload['receipts'] = {'passports_sha256': stable_hash(passports),
                           'qa_sha256': stable_hash(payload)}
    errors = _check_manifest(payload)
    if errors: raise AssertionError('MEGABLOCK1_QA_FAILED:'+','.join(errors))
    return payload

def verify_megablock1(payload, catalog=None):
    """Read-only local receipt verification; no claim of cryptographic authenticity."""
    errors = _check_manifest(payload) if isinstance(payload,dict) else ['INVALID_MANIFEST']
    if isinstance(payload, dict) and catalog is not None:
        hashes = payload.get('input', {})
        if hashes.get('catalog_sha256') != stable_hash(catalog):errors.append('CATALOG_CHANGED')
        if hashes.get('problem_seeds_sha256') != stable_hash(load_seeds()):errors.append('SEEDS_CHANGED')
    return {'valid': not errors, 'errors': errors,
            'proof_type': 'UNSIGNED_CONTENT_HASH_NOT_EXTERNAL_ATTESTATION'}
