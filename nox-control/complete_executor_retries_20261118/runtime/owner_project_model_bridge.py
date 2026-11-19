#!/usr/bin/env python3
"""Trusted bridge from a pinned native task contract to a prepared project edit.

It reads only the approved source snapshot, sends bounded data to the existing
local model, and delegates every candidate test to the confined executor. Only
the dispatcher parent may integrate the resulting exact plan. This module does
not create queue rows, run model-selected commands or accept original tasks.
"""
from __future__ import annotations

import json
from pathlib import Path
import time

import owner_project_executor as executor
from owner_project_model_client import LocalModelClient
from owner_project_planner import (PlannerHold, canonical, plan_task, relative_path,
                                   require, sha, validate_contract)

SOURCE_FILES = ('owner_project_planner.py', 'owner_project_model_client.py',
                'owner_project_model_bridge.py')


def load_contract(reference, config):
    executor.validate_config(config)
    require(isinstance(reference, dict) and set(reference) == {'contract_sha256'}
            and executor.SHA.fullmatch(str(reference.get('contract_sha256'))),
            'CONTRACT_REFERENCE')
    digest = reference['contract_sha256']
    raw = executor.read(Path(config['package_root']) / 'contracts' / (digest + '.json'))
    require(sha(raw) == digest, 'CONTRACT_CONTENT_ADDRESS')
    try:
        contract = json.loads(raw)
    except ValueError as exc:
        raise PlannerHold('HOLD_PROJECT_PLANNER_CONTRACT_JSON') from exc
    require(isinstance(contract, dict) and canonical(contract) == raw,
            'CONTRACT_CANONICAL_ENCODING')
    require(contract.get('root_id') in config['roots'], 'CONTRACT_ROOT')
    root = config['roots'][contract['root_id']]
    require(isinstance(contract.get('context'), list), 'CONTRACT_CONTEXT')
    snapshot = {}
    with executor.tree(root['path']) as handle:
        for row in contract['context']:
            require(isinstance(row, dict) and set(row) == {'path', 'sha256'},
                    'CONTRACT_CONTEXT_ROW')
            path = relative_path(row['path'])
            require(executor._allowed(path, root['allowed_paths'])
                    and not executor._allowed(path, root.get('deny_paths', [])),
                    'CONTRACT_ROOT_PATH_POLICY')
            raw, _mode = handle.get(path)
            require(raw is not None and sha(raw) == row['sha256'], 'CONTRACT_SOURCE_CHANGED')
            snapshot[path] = raw
        handle.assert_current()
    validate_contract(contract, snapshot)
    return contract, snapshot


def _check_pins(config):
    model = config.get('model')
    require(isinstance(model, dict) and set(model) <= {
        'expected_model_id', 'max_tokens', 'lock_path', 'source_pins'}, 'MODEL_CONFIG')
    pins = model.get('source_pins')
    require(isinstance(pins, dict) and set(pins) == set(SOURCE_FILES), 'BRIDGE_SOURCE_PINS')
    for name in SOURCE_FILES:
        require(sha(executor.read(Path(__file__).parent / name)) == pins[name],
                'BRIDGE_SOURCE_CHANGED')
    return model


def execute(item, *, cancelled=lambda: False, heartbeat=lambda: None):
    context = item.get('_native_project_context')
    require(isinstance(context, dict) and set(context) == {'reference', 'config', 'claim'}
            and executor.CLAIM.fullmatch(str(context.get('claim', ''))), 'WORKER_CONTEXT')
    config, claim, reference = context['config'], context['claim'], context['reference']
    started = time.time()
    prepared = {}
    try:
        require(cancelled() is False, 'OWNER_STOP_OR_CLAIM_LOST')
        contract, snapshot = load_contract(reference, config)
        require(item.get('id') == contract['task_id'], 'WORKER_TASK_IDENTITY')
        model = _check_pins(config)
        client = LocalModelClient(expected_model_id=model['expected_model_id'],
            max_tokens=model.get('max_tokens', 900), stop_check=cancelled,
            heartbeat=heartbeat, lock_path=model['lock_path'])

        def verify(plan, payloads):
            result = executor.verify_candidate(plan, payloads, config, claim,
                approved_contract_sha256=reference['contract_sha256'],
                stop_check=cancelled, heartbeat=heartbeat)
            digest = sha(canonical(plan))
            prepared[digest] = result
            test = result.get('project_evidence', {}).get('tests', {})
            return {**result, **{key: test[key] for key in
                ('failures', 'errors', 'output') if key in test}}

        planned = plan_task(contract, snapshot, client, verify, cancelled, heartbeat)
        if planned.get('state') != 'PLAN_READY':
            return {**planned, 'passed': False, 'reference': reference,
                    'prepared_claim': claim, 'project_source_changed': False,
                    'planner_receipt': {'schema': 'NOX_PROJECT_PLANNER_RECEIPT_V1',
                        'task_id': item['id'], 'contract_sha256': reference['contract_sha256'],
                        'state': planned['state'], 'trace': planned.get('trace', []),
                        'reason': planned.get('reason'), 'started_at': started,
                        'finished_at': time.time(), 'original_task_accepted': False}}
        digest = sha(canonical(planned['plan']))
        result = prepared.get(digest)
        require(isinstance(result, dict) and result.get('passed') is True
                and result.get('state') == 'PREPARED', 'FINAL_PREPARED_REFERENCE')
        require(cancelled() is False, 'OWNER_STOP_OR_CLAIM_LOST')
        heartbeat()
        return {**result, 'reference': {'plan_sha256': digest,
                    'contract_sha256': reference['contract_sha256']},
                'prepared_claim': claim, 'planner_receipt': planned['planner_receipt'],
                'original_task_accepted': False}
    except (PlannerHold, executor.ProjectHold, OSError, ValueError, KeyError, TypeError) as exc:
        reason = str(exc) if isinstance(exc, (PlannerHold, executor.ProjectHold)) else (
            'HOLD_PROJECT_MODEL_BRIDGE_' + type(exc).__name__)
        return {'state': reason, 'passed': False, 'reference': reference,
                'prepared_claim': claim, 'original_task_accepted': False,
                'project_source_changed': False,
                'planner_receipt': getattr(exc, 'partial_receipt', None) or {
                    'schema': 'NOX_PROJECT_PLANNER_RECEIPT_V1',
                    'task_id': item.get('id'), 'contract_sha256': reference.get('contract_sha256'),
                    'state': reason, 'started_at': started, 'finished_at': time.time(),
                    'original_task_accepted': False}}
