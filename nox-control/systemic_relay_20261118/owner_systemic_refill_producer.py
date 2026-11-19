#!/usr/bin/env python3
"""Emit a fail-closed eligibility and predicate-diff report for REFILL_REQUIRED.

This source-only diagnostic never repairs a proposal, creates a task/status,
claims an original acceptance, writes a native package, or performs publication.
Use owner_systemic_taskpack.py only after all exact reviewed inputs pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from owner_systemic_taskpack import (read_document,
    read_identical_duplicate_document, _validate_refill_request,
    _validate_proposal_request, immutable_verifier_sha256)
from owner_systemic_refill_eligibility import (strict_parent_registry,
    eligibility_ledger, proposal_predicate_diff, special_candidate_gaps)
from runtime.owner_systemic_refill import SHA


def _check(name, expected, actual, passed, missing_field=None):
    result = {'predicate':name,'expected':expected,'actual':actual,'passed':passed is True}
    if missing_field:
        result['actionable_missing_field'] = missing_field
    return result


def _input_docs(source_root):
    docs, pins = {}, {}
    for key,name in (('tasks','work_tasks.json'),('ideas','work_ideas.json'),
                     ('routing_rules','routing_rules.json'),
                     ('routing_overlay','NOX_FOUR_QUEUE_ROUTING_20261118.json')):
        docs[key],pins[key] = read_document(source_root/name)
    docs['receipts'],pins['receipts'] = read_identical_duplicate_document(
        source_root/'work_receipts.json')
    return docs,pins


def build_report(previous, previous_sha, refill_request, refill_sha, proposal,
                 proposal_sha, census, census_sha, disposition, disposition_sha,
                 review, review_sha, source_documents, source_raw_sha256):
    registry = strict_parent_registry(disposition,source_documents,source_raw_sha256)
    ledger = eligibility_ledger(registry,previous,refill_request)
    missions = proposal.get('missions') if isinstance(proposal, dict) else None
    reviewed_ids_expected = None
    if isinstance(missions, list) and all(
            isinstance(m, dict) and type(m.get('mission_id')) is str for m in missions):
        reviewed_ids_expected = sorted(m['mission_id'] for m in missions)
        diffs = proposal_predicate_diff(missions,registry,
            census.get('roots',{}),refill_request,previous)
    else:
        # Malformed proposals must produce HOLD evidence, never crash the reviewer.
        diffs = [{'parent_task_id': None, 'all_passed': False,
                  'predicates': [_check('mission_ids_well_formed', True, False, False,
                                        'proposal.missions[].mission_id')],
                  'native_publish_performed': False, 'original_task_accepted': False}]
    request_validation = []
    try:
        _validate_refill_request(refill_request,previous,previous_sha)
        request_validation.append(_check('refill_request_binding',True,True,True))
    except (ValueError,KeyError,TypeError) as exc:
        request_validation.append(_check('refill_request_binding',
            'exact current REFILL_REQUIRED request with original_task_states',str(exc),False,
            'fresh REFILL_REQUIRED request with original_task_states and its SHA-bound request_id'))
    try:
        _validate_proposal_request(proposal,previous_sha,refill_request)
        request_validation.append(_check('proposal_request_binding',
            refill_request.get('request_id'),proposal.get('request_id'),True))
    except (ValueError,KeyError,TypeError) as exc:
        request_validation.append(_check('proposal_request_binding',
            refill_request.get('request_id'),proposal.get('request_id'),False,
            'proposal.request_id matching the validated 64-hex REFILL_REQUIRED ID'))

    review_checks = [
        _check('review_origin','OWNER_REVIEWED',review.get('review_origin'),
               review.get('review_origin') == 'OWNER_REVIEWED','owner review of exact proposal/census/request bytes'),
        _check('proposal_sha256',proposal_sha,review.get('proposal_sha256'),
               review.get('proposal_sha256') == proposal_sha,'reviewed proposal_sha256'),
        _check('source_census_sha256',census_sha,review.get('source_census_sha256'),
               review.get('source_census_sha256') == census_sha,'reviewed source_census_sha256'),
        _check('refill_request_sha256',refill_sha,review.get('refill_request_sha256'),
               review.get('refill_request_sha256') == refill_sha,'reviewed exact refill_request_sha256'),
        _check('registry_sha256',disposition_sha,review.get('registry_sha256'),
               review.get('registry_sha256') == disposition_sha,'reviewed exact registry SHA'),
        _check('previous_manifest_sha256',previous_sha,review.get('previous_manifest_sha256'),
               review.get('previous_manifest_sha256') == previous_sha,'owner readback of exact predecessor'),
        _check('original_task_accepted',False,review.get('original_task_accepted'),
               review.get('original_task_accepted') is False),
        _check('previous_claims_settled',True,review.get('previous_claims_settled'),
               review.get('previous_claims_settled') is True,'fresh owner readback after claims settle'),
        _check('native_readback_sha256','64-hex',review.get('native_readback_sha256'),
               type(review.get('native_readback_sha256')) is str
               and SHA.fullmatch(review['native_readback_sha256']),
               'fresh owner-authenticated native readback SHA'),
        _check('reviewed_mission_ids',reviewed_ids_expected,
               review.get('reviewed_mission_ids'),
               reviewed_ids_expected is not None
               and type(review.get('reviewed_mission_ids')) is list
               and review.get('reviewed_mission_ids') == reviewed_ids_expected,
               'reviewed_mission_ids must match sorted string mission IDs exactly'),
    ]
    try:
        existing_verifier = immutable_verifier_sha256(proposal.get('missions',[]),
                                                       census.get('roots',{}))
        verifier_ok = review.get('immutable_verifier_sha256') == existing_verifier
    except (KeyError,TypeError,AttributeError):
        existing_verifier,verifier_ok = None,False
    review_checks.append(_check('immutable_verifier_sha256',existing_verifier,
        review.get('immutable_verifier_sha256'),verifier_ok,
        'reviewed immutable verifier contract and exact module hashes'))
    all_passed = (all(row['passed'] for row in request_validation)
                  and all(row['passed'] for row in review_checks)
                  and all(row['all_passed'] for row in diffs))
    structural = [row for row in ledger if row['structural_source_candidate']]
    return {'schema':'NOX_SYSTEMIC_REFILL_ELIGIBILITY_AUDIT_V1',
        'audit_basis':{'previous_manifest_sha256':previous_sha,
            'refill_request_sha256':refill_sha,'proposal_sha256':proposal_sha,
            'source_census_sha256':census_sha,'registry_file_sha256':disposition_sha,
            'review_sha256':review_sha,
            'original_registry_source_pins':registry['source_registry_sha256'],
            'original_task_count':registry['total_original_ids'],
            'raw_receipt_duplicate_projection_ids':sorted(task_id for task_id,parent in registry['parents'].items()
                if parent.get('prior_receipt_projection_ambiguous'))},
        'state':'REVIEWED_TASKPACK_INPUTS_VALID' if all_passed else 'HOLD_NO_REVIEWED_TASKPACK',
        'refill_request_predicates':request_validation,
        'review_predicates':review_checks,
        'prepublisher_predicate_diff':diffs,
        'structural_source_candidate_count':len(structural),
        'structural_source_candidates':[row['task_id'] for row in structural],
        'task_eligibility_ledger':ledger,
        'highlighted_candidate_gaps':special_candidate_gaps(registry,census,census_sha),
        'publisher_requirements':['OWNER_REVIEWED_EXACT_REQUEST_AND_PROPOSAL',
            'EXACT_CURRENT_CONFIG_CAS','EXISTING_NATIVE_OWNER_LEASE',
            'CURRENT_ORIGINAL_TASK_STATE_READBACK_MATCH','ALL_OLD_TASKS_AND_CLAIMS_PRESERVED',
            'NO_OWNER_STOP_OVERRIDE','SOURCE_CONTEXT_AND_IMMUTABLE_TEST_PINS','PUBLISH_READBACK'],
        'native_publish_performed':False,'native_jobs_created':0,
        'original_task_acceptance_added':0,'original_tasks_accepted':False,
        'executable_taskpack_emitted':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('previous-manifest','refill-request','proposal','source-census','registry','review'):
        parser.add_argument('--'+option,required=True)
    default_sources = Path(__file__).parent.parent/'four_queue_20261118'
    parser.add_argument('--source-root',default=str(default_sources))
    args = parser.parse_args()
    previous,previous_sha = read_document(args.previous_manifest)
    request,request_sha = read_document(args.refill_request)
    proposal,proposal_sha = read_document(args.proposal)
    census,census_sha = read_document(args.source_census)
    disposition,disposition_sha = read_document(args.registry)
    review,review_sha = read_document(args.review)
    docs,source_pins = _input_docs(Path(args.source_root))
    report = build_report(previous,previous_sha,request,request_sha,proposal,proposal_sha,
        census,census_sha,disposition,disposition_sha,review,review_sha,docs,source_pins)
    print(json.dumps(report,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    return 0 if report['state'] == 'REVIEWED_TASKPACK_INPUTS_VALID' else 2


if __name__ == '__main__':
    raise SystemExit(main())
