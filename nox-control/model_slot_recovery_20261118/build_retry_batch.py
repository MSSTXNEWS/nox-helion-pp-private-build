#!/usr/bin/env python3
"""Prepare two exact model retries after observed zero-turn slot starvation.

Local builder only. It preserves the previous immutable task instructions and
tests. A native installer must independently recheck the predecessor receipts,
current source pins, idle claims and changed model-slot runtime before append.
No prepared source solution or replacement for a historical claim is emitted.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[1]
sys.path.insert(0, str(REPO / 'nox-control/complete_executor_retries_20261118/runtime'))
import owner_project_planner as planner

CALLBACK_SHA = '84c08283fc3e0e0714704b8bf540eaacb979ec6618f8c1920eb5d75062561c6b'
FAILURE_REASON = 'HOLD_PROJECT_PLANNER_MODEL_SLOT_BUSY'
TASKS = (
    '6V14-12.project.readonly_transient_retry.20261118',
    '4A02.project.bilingual_task_matrix.20261118',
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def require(value, code):
    if not value:
        raise ValueError(code)


def build(inspect_path, current_source):
    inspected = json.loads(inspect_path.read_bytes())
    census = inspected['NOX_MAINT_SCOPE_PROJECT_SOURCE_WORKSPACE_CENSUS'][-1]
    require(census.get('two_reads_match') is True
            and census.get('complete_allowed_files_read') is True
            and census.get('config_unchanged_during_census') is True
            and census.get('bootstrap_unchanged_during_census') is True
            and not census.get('read_errors')
            and not census.get('unattributed_changed_paths'),
            'CURRENT_SOURCE_CENSUS_NOT_VERIFIED')
    pins = {path: row['sha256'] for path, row in census['files'].items()}
    require(len(pins) == 31, 'EXPECTED_CURRENT_SOURCE_FILESET')
    # Every context byte used below must match the independently observed source
    # workspace. Unrelated files are retained as install-time CAS preconditions.
    catalog = json.loads((REPO / 'nox-control/continuous_executor_20261118/batch.json').read_bytes())
    prior_rows = {row['id']: row for row in catalog['catalog_append']}
    executions = {row['id']: row for row in inspected['NOX_MAINT_SCOPE_PROJECT_EXECUTION']}
    package_paths, asset_sources, asset_pins, rows, recovery = {}, {}, {}, [], []
    predecessors = []
    for task_id in TASKS:
        previous = executions[task_id]
        owner_claim = previous['owner_claim']
        receipt = previous['receipt']
        evidence = previous['project_evidence']
        plan_receipt = previous['planner_receipt']
        old_row = prior_rows[task_id]
        previous_contract = old_row['params']['contract_sha256']
        require(previous.get('status') == 'blocked'
                and previous.get('original_task_accepted') is False
                and previous.get('receipt_sha_matches') is True
                and previous.get('receipt_claim_matches') is True
                and previous.get('project_evidence_sha_matches') is True
                and previous['result'].get('verified') is True,
                'PREDECESSOR_NOT_NATIVE_VERIFIED_BLOCKED')
        require(receipt.get('phase') == 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED'
                and receipt.get('task_id') == task_id
                and receipt.get('source_sha256') == CALLBACK_SHA
                and receipt.get('project_source_changed') is False
                and receipt.get('live_service_deployed') is False
                and receipt.get('original_task_accepted') is False,
                'PREDECESSOR_RECEIPT_SCOPE')
        require(evidence.get('state') == 'BLOCKED_PLANNER'
                and evidence.get('task_id') == task_id
                and evidence.get('claim') == owner_claim['nonce']
                and evidence.get('reason') == FAILURE_REASON
                and evidence.get('project_source_changed') is False
                and evidence.get('postimages') is None
                and evidence.get('plan_sha256') is None,
                'PREDECESSOR_SOURCE_NOT_UNCHANGED')
        require(plan_receipt.get('state') == FAILURE_REASON
                and plan_receipt.get('task_id') == task_id
                and plan_receipt.get('contract_sha256') == previous_contract
                and type(plan_receipt.get('completed_model_turns')) is int
                and plan_receipt['completed_model_turns'] == 0
                and plan_receipt.get('changed_candidate_paths') == []
                and plan_receipt.get('trace') == []
                and plan_receipt.get('original_task_accepted') is False,
                'PREDECESSOR_NOT_ZERO_TURN_SLOT_FAILURE')
        receipt_pin = previous['result']['receipt_sha256']
        require(previous['s03'].get('verified') is True
                and previous['s03'].get('receipt_sha256') == receipt_pin
                and previous['s03'].get('scope') == 'EXACT_READ_ONLY_SQLITE_RECEIPT_MATCH',
                'PREDECESSOR_EXACT_S03_READBACK_REQUIRED')
        contract_path = REPO / 'nox-control/continuous_work_20261118/package/contracts' / (previous_contract + '.json')
        old_raw = contract_path.read_bytes()
        old_contract = json.loads(old_raw)
        require(sha(old_raw) == previous_contract and old_raw == encoded(old_contract)
                and old_contract.get('task_id') == task_id,
                'PREVIOUS_CONTRACT_PIN')
        snapshot = {}
        for context in old_contract['context']:
            path, pin = context['path'], context['sha256']
            require(pins.get(path) == pin, 'CURRENT_CONTEXT_CHANGED:' + path)
            raw = (current_source / path).read_bytes()
            require(sha(raw) == pin, 'LOCAL_CONTEXT_PIN:' + path)
            snapshot[path] = raw
        contract = copy.deepcopy(old_contract)
        retry_id = task_id.removesuffix('.20261118') + '.slot_retry.20261118'
        contract['task_id'] = retry_id
        planner.validate_contract(contract, snapshot)
        # Retry identity is the sole change to the approved model contract.
        require({k: v for k, v in contract.items() if k != 'task_id'}
                == {k: v for k, v in old_contract.items() if k != 'task_id'},
                'RETRY_CHANGED_APPROVED_CONTRACT')
        raw = encoded(contract)
        contract_pin = sha(raw)
        relative = 'package/contracts/' + contract_pin + '.json'
        target = BASE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        asset_name = 'slot_contract_' + contract_pin[:20] + '.json'
        package_paths[asset_name] = 'state/dispatcher/project_executor/' + relative
        asset_sources[asset_name] = str(target.relative_to(REPO))
        asset_pins[asset_name] = contract_pin
        row = copy.deepcopy(old_row)
        row['id'] = retry_id
        row['params']['contract_sha256'] = contract_pin
        require(row.get('deps') == [] and row.get('source_sha256') == CALLBACK_SHA,
                'RETRY_CATALOG_SCOPE')
        rows.append(row)
        recovery.append({
            'retry_task_id': retry_id,
            'parent_task_id': old_contract['parent_task_id'],
            'predecessor_task_id': task_id,
            'predecessor_status': 'blocked',
            'predecessor_owner_claim': owner_claim,
            'predecessor_claim_nonce': owner_claim['nonce'],
            'predecessor_job_id': receipt['job_id'],
            'predecessor_receipt_sha256': receipt_pin,
            'predecessor_receipt_phase': receipt['phase'],
            'predecessor_contract_sha256': previous_contract,
            'predecessor_planner_receipt_sha256': sha(encoded(plan_receipt)),
            'predecessor_reason': FAILURE_REASON,
            'predecessor_completed_model_turns': 0,
            'predecessor_changed_candidate_paths': [],
            'predecessor_project_source_changed': False,
            'predecessor_plan_sha256': None,
            'predecessor_s03_item_id': previous['s03']['s03_item_id'],
            'source_context_pins': {context['path']: context['sha256']
                                    for context in contract['context']},
            'old_task_mutation_allowed': False,
            'original_task_accepted': False,
        })
        predecessors.append({key: previous[key] for key in (
            'id', 'parent_task_id', 'queue_id', 'status', 'owner_claim', 'result',
            'receipt', 'receipt_sha_matches', 'receipt_claim_matches', 's03',
            'receipt_source', 'worker_event', 'project_evidence',
            'project_evidence_sha_matches', 'planner_receipt')})
    manifest = {
        'schema': 'NOX_MODEL_SLOT_RECOVERY_BATCH_V1',
        'source_test_paths': {},
        'package_paths': package_paths,
        'asset_sources': asset_sources,
        'asset_sha256': asset_pins,
        'catalog_append': rows,
        'recovery_requirements': recovery,
        'source_context_pins': pins,
        'source_census_sha256': census['files_sha256'],
        'source_census_file_count': len(pins),
        'source_census_started_at': census['started_at'],
        'source_census_finished_at': census['finished_at'],
        'source_census_atomic_snapshot': False,
        'source_census_two_reads_match': True,
        'observed_config_sha256': census['config_sha256'],
        'observed_bootstrap_sha256': census['bootstrap']['sha256'],
        'observed_bootstrap_manifest_sha256': census['bootstrap']['manifest_sha256'],
        'observed_queue_snapshot_sha256': census['receipt_queue_snapshot_sha256'],
        'inspection_payload_sha256': sha(inspect_path.read_bytes()),
        'current_cas_recheck_required': True,
        'changed_model_slot_runtime_required': True,
        'callback_sha256': CALLBACK_SHA,
        'historical_claim_replacement_allowed': False,
        'automatic_replay_allowed': False,
        'prepared_solution_payloads': [],
        'source_only': True,
        'original_acceptance_added': 0,
    }
    (BASE / 'observed_predecessors.json').write_bytes(encoded({
        'schema': 'NOX_MODEL_SLOT_RECOVERY_OBSERVATIONS_V1',
        'inspection_payload_sha256': manifest['inspection_payload_sha256'],
        'native_recheck_required': True,
        'predecessors': predecessors}) + b'\n')
    (BASE / 'batch.json').write_bytes(encoded(manifest) + b'\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect-json', type=Path, required=True)
    parser.add_argument('--current-source', type=Path, required=True)
    args = parser.parse_args()
    manifest = build(args.inspect_json, args.current_source)
    print(json.dumps({'contracts': len(manifest['catalog_append']),
        'source_files': manifest['source_census_file_count'],
        'retry_ids': [row['id'] for row in manifest['catalog_append']],
        'new_source_tests': 0, 'prepared_solutions': 0,
        'original_acceptance_added': 0}))


if __name__ == '__main__':
    main()
