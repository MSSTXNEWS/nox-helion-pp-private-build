#!/usr/bin/env python3
"""Publish exact host-reviewed source plans to the existing three native workers.

Only immutable package metadata and the existing catalog are written. The native
executor still owns admission, immutable verification, source CAS, and S03.
No worker restart, model generation, source edit, or test is performed here.
"""
from __future__ import annotations

import base64
import contextlib
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time
import types

ROOT = Path('/root/nox')
CONFIG = ROOT / 'config/owner_native_subagents.json'
PACKAGE = ROOT / 'state/dispatcher/project_executor/package'
HELPER_SHA = '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
SHA = re.compile(r'[a-f0-9]{64}')
ID = re.compile(r'[A-Za-z0-9_.:-]{1,128}')
SPEC = {'schema': 'NOX_SYSTEMIC_REVIEWED_PUBLISH_SPEC_V1', 'assets': {'reviewed_systemic_transaction_helpers.py': '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609', 'reviewed_cache_ttl_plan.json': '7993b7ec58f6bfaafcef97c80d27b78c8c292d5ba2eaf76eafbc06e10148025f', 'reviewed_cache_ttl_payload.source': '449a3c57baff26e5f4251b88ed0f21ba8cf7320cea65813cc80bc854d3095afc', 'reviewed_forge_budget_plan.json': '86c1f916da8194f49231a32b0e2899f6bfbea9a7d7622561280ac130352795ce', 'reviewed_forge_budget_payload.source': '82969cfb2b02939cfe60c6fbd62ab921754e5f61ff96183ccea53ddcc40cc9fb', 'reviewed_skill_budget_plan.json': '63f108342e5366c053233141ca01cbf2c39caca8aa17413c1b362d32b7850b31', 'reviewed_skill_budget_payload.source': 'fdab96a2861f49efa8471347ed315dac748ee81207f0f9e347fe8b37a05e47cb'}, 'helper_asset': 'reviewed_systemic_transaction_helpers.py', 'batches': [{'title': 'Apply reviewed insertion-time cache TTL after the stalled model attempt', 'plan_asset': 'reviewed_cache_ttl_plan.json', 'payload_assets': {'449a3c57baff26e5f4251b88ed0f21ba8cf7320cea65813cc80bc854d3095afc': 'reviewed_cache_ttl_payload.source'}, 'catalog_row': {'id': '3A03.project.systemic_reviewed_cache_ttl.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q2_MEMORY_KNOWLEDGE', 'resource': 'CPU_LIGHT', 'priority': 'P1', 'deps': [], 'estimated_cost': 2, 'source_sha256': '0193c511168489637b6df041bee2daf79bd42bd338c4ff5f9a6b129652dc4a13', 'params': {'parent_task_id': '3A03', 'plan_sha256': '7993b7ec58f6bfaafcef97c80d27b78c8c292d5ba2eaf76eafbc06e10148025f'}, 'title': 'Apply reviewed insertion-time cache TTL after the stalled model attempt'}}, {'title': 'Complete bounded split reads and pre-parse row enforcement', 'plan_asset': 'reviewed_forge_budget_plan.json', 'payload_assets': {'82969cfb2b02939cfe60c6fbd62ab921754e5f61ff96183ccea53ddcc40cc9fb': 'reviewed_forge_budget_payload.source'}, 'catalog_row': {'id': '4A02.project.systemic_reviewed_forge_budget.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q3_TRAINING_WEIGHTS', 'resource': 'CPU_LIGHT', 'priority': 'P1', 'deps': [], 'estimated_cost': 2, 'source_sha256': '0193c511168489637b6df041bee2daf79bd42bd338c4ff5f9a6b129652dc4a13', 'params': {'parent_task_id': '4A02', 'plan_sha256': '86c1f916da8194f49231a32b0e2899f6bfbea9a7d7622561280ac130352795ce'}, 'title': 'Complete bounded split reads and pre-parse row enforcement'}}, {'title': 'Complete bounded skill journal and marker identity reads', 'plan_asset': 'reviewed_skill_budget_plan.json', 'payload_assets': {'fdab96a2861f49efa8471347ed315dac748ee81207f0f9e347fe8b37a05e47cb': 'reviewed_skill_budget_payload.source'}, 'catalog_row': {'id': '3B05.project.systemic_reviewed_skill_budget.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q2_MEMORY_KNOWLEDGE', 'resource': 'CPU_LIGHT', 'priority': 'P1', 'deps': [], 'estimated_cost': 2, 'source_sha256': '0193c511168489637b6df041bee2daf79bd42bd338c4ff5f9a6b129652dc4a13', 'params': {'parent_task_id': '3B05', 'plan_sha256': '63f108342e5366c053233141ca01cbf2c39caca8aa17413c1b362d32b7850b31'}, 'title': 'Complete bounded skill journal and marker identity reads'}}], 'predecessors': [{'task_id': '3A03.relay.cache_fill_ttl.27ce42904d0e73af', 'parent_task_id': '3A03', 'status': 'blocked', 'receipt_sha256': 'd4ab4ab519cbf54dd75d2dc9fe61830b1cd90cb2c97ced6567da3b2392f5b195', 'contract_sha256': '9f3d8444c2159dd38a62bd065ce309f9d3bd100fc51f27e9a47a6ef7dd286903', 'reason': 'PLANNER_REPEATED_ACTION_NO_PROGRESS'}, {'task_id': '4A02.relay.forge_read_budget.f7f4408ebf5b4ce4', 'parent_task_id': '4A02', 'status': 'done', 'receipt_sha256': '2831b552f41d1a475c3a60ed41a0127ced88a8ad9192d38421b50efa68228955', 'contract_sha256': 'ff08b3bb9270e2683468fb67fbaef05b3da837bc9f31c44d822588a9535eb7e8', 'postimages': {'forge_split_guard.py': '30677e7012b3d266cc98425d89df25814e6b38f4d840e6fd0f883b77f6703f35'}}, {'task_id': '3B05.relay.skill_journal_budget.68bb42827d53bab9', 'parent_task_id': '3B05', 'status': 'done', 'receipt_sha256': '605101f1f952e2056aaefb27cd85598624e6f3897972235012954e2c7dc92393', 'contract_sha256': '98ebd2d81f2d875b78842c3b91743e46e7e87d8b16575b0b792f9fe120735413', 'postimages': {'owner_dispatcher_mentor.py': '8b8328c731357d37d5c5eb1265704e2abba8f7d3e649e902a09124f6a85abb4a'}}], 'expected_callback_sha256': '0193c511168489637b6df041bee2daf79bd42bd338c4ff5f9a6b129652dc4a13', 'expected_config_sha256': 'ad7a2ba87ab184c1ea0871932cf9686d3dce7813cb469fd2f1a5c2bf18ac9366', 'expected_source_files_sha256': '90b291b41b69c8dbf0f159275de7b8f5d0c28502c5a1d623641f6ddfe70f36cd', 'expected_director': {'pid': 106058, 'start_ticks': 181620214}, 'expected_workers': [{'pid': 106174, 'start_ticks': 181621423}, {'pid': 106175, 'start_ticks': 181621423}, {'pid': 106176, 'start_ticks': 181621423}], 'protected_processes': {'chat': {'pid': 3266857, 'ppid': 114, 'pgrp': 3266857, 'start_ticks': 172046662}, 'proxy': {'pid': 3703386, 'ppid': 114, 'pgrp': 3703386, 'start_ticks': 175609570}, 'web': {'pid': 3505392, 'ppid': 114, 'pgrp': 3505392, 'start_ticks': 173653097}}}
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}


def require(value, code):
    if not value:
        raise RuntimeError('HOLD_SYSTEMIC_REVIEWED_' + code)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def wait_settled_queue(helper, guard, expected, receipt):
    """Allow an already-running task to settle without resetting any claim."""
    deadline = time.monotonic() + 8
    while True:
        require(guard() == expected, 'PROCESS_IDENTITY_CHANGED')
        state, active = helper.queue_idle(ROOT)
        busy = set(active)
        for task_id, row in state['tasks'].items():
            if (isinstance(row, dict) and row.get('handler') == 'owner_native_project_work'
                    and (row.get('status') == 'pending'
                         or (row.get('native_worker_lease') or {}).get('phase') in ('ACTIVE', 'RETIRING'))):
                busy.add(task_id)
        receipt['busy_count'] = len(busy)
        receipt['busy_tasks'] = []
        for task_id in sorted(busy)[:12]:
            row = state['tasks'][task_id]
            lease = row.get('native_worker_lease') or {}
            receipt['busy_tasks'].append({
                'id': str(task_id)[:128],
                'status': row.get('status')[:64] if isinstance(row.get('status'), str) else None,
                'handler': row.get('handler')[:128] if isinstance(row.get('handler'), str) else None,
                'lease_phase': lease.get('phase')[:64] if isinstance(lease.get('phase'), str) else None,
            })
        if not busy:
            return state
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'WAIT_ACTIVE_CLAIMS_SETTLE')
        time.sleep(min(.05, remaining))


def exact_s03(receipt, helper):
    path = ROOT / 'kb/knowledge.sqlite'
    require(not any(p.is_symlink() for p in (path, *path.parents))
            and stat.S_ISREG(path.stat().st_mode), 'S03_PATH')
    pin = digest(encoded(receipt))
    text = 'NOX native job ' + receipt['job_id'] + ' ' + receipt['phase'] + ' receipt_sha256 ' + pin
    with contextlib.closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.2)) as conn:
        conn.execute('PRAGMA query_only=ON')
        deadline = time.monotonic() + 2
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        rows = conn.execute("SELECT id,meta,sha256 FROM s03_items WHERE segment='M2' AND text=? AND provenance=? LIMIT 2",
                            (text, 'owner_native_subagents')).fetchall()
    require(len(rows) == 1 and rows[0][2] == digest(('M2|' + text).encode())
            and json.loads(rows[0][1]).get('receipt') == receipt, 'S03_EXACT_RECEIPT')
    return {'s03_item_id': rows[0][0], 'receipt_sha256': pin}


def predecessors(state, spec, helper):
    proofs = []
    expected_workers = {(w['pid'], w['start_ticks']) for w in spec['expected_workers']}
    for expected in spec['predecessors']:
        row = state['tasks'].get(expected['task_id'])
        require(isinstance(row, dict) and row.get('status') == expected['status']
                and row.get('handler') == 'owner_native_project_work'
                and row.get('parent_task_id') == expected['parent_task_id'], 'PREDECESSOR_STATUS')
        result = row.get('result') or {}
        receipt = result.get('receipt') or {}
        claim = row.get('owner_claim') or {}
        lease = row.get('native_worker_lease') or {}
        require(result.get('verified') is True
                and result.get('receipt_sha256') == expected['receipt_sha256']
                and digest(encoded(receipt)) == expected['receipt_sha256']
                and receipt.get('task_id') == expected['task_id']
                and receipt.get('parent_task_id') == expected['parent_task_id']
                and receipt.get('claim') == claim
                and claim.get('pid') == spec['expected_director']['pid']
                and re.fullmatch(r'[a-f0-9]{24}', str(claim.get('nonce')))
                and receipt.get('execution_claim') == claim['nonce']
                and receipt.get('source_sha256') == spec['expected_callback_sha256']
                and receipt.get('scope') == 'SOURCE_PATCH_TESTED'
                and receipt.get('original_task_accepted') is False
                and receipt.get('live_service_deployed') is False
                and lease.get('phase') == 'SETTLED'
                and lease.get('claim') == claim['nonce']
                and lease.get('receipt_sha256') == expected['receipt_sha256'], 'PREDECESSOR_RECEIPT')
        event = receipt.get('worker_result') or {}
        evidence = event.get('project_evidence') or {}
        worker = evidence.get('worker') or {}
        require(digest(encoded(evidence)) == event.get('project_evidence_sha256')
                and evidence.get('task_id') == expected['task_id']
                and evidence.get('claim') == claim['nonce']
                and (worker.get('pid'), worker.get('process_starttime')) in expected_workers
                and worker.get('ppid') == spec['expected_director']['pid']
                and evidence.get('root_id') == 'NOX_PROJECT_SOURCE', 'PREDECESSOR_EVIDENCE')
        if expected['status'] == 'blocked':
            require(receipt.get('phase') == 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED'
                    and evidence.get('state') == 'BLOCKED_PLANNER'
                    and evidence.get('reason') == expected['reason']
                    and evidence.get('project_source_changed') is False
                    and receipt.get('project_source_changed') is False
                    and receipt.get('plan_sha256') is None, 'FAILED_ATTEMPT_CHANGED_SOURCE')
        else:
            require(expected['status'] == 'done'
                    and receipt.get('phase') == 'PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED'
                    and evidence.get('state') == 'INTEGRATED'
                    and evidence.get('integration_verified') is True
                    and evidence.get('postimages') == expected['postimages']
                    and evidence.get('trusted_tests_unchanged') is True, 'PREDECESSOR_INTEGRATION')
        proofs.append({'task_id': expected['task_id'], **exact_s03(receipt, helper)})
    return proofs


def registry(config, helper):
    reference = config['systemic_relay']
    require(reference['path'] == str(PACKAGE / 'relay' / (reference['sha256'] + '.json')),
            'MANIFEST_PATH')
    raw = helper.read_regular(Path(reference['path']), 2 * 1024 * 1024)
    require(digest(raw) == reference['sha256'], 'MANIFEST_PIN')
    manifest = json.loads(raw)
    docs = {}
    for key, name in {'tasks': 'project_work_tasks.json', 'ideas': 'project_work_ideas.json',
                      'receipts': 'project_work_receipts_source.json', 'routing': 'project_routing_4q.json'}.items():
        raw = helper.read_regular(ROOT / 'state/dispatcher' / name, 16 * 1024 * 1024)
        require(digest(raw) == manifest['registry']['source_registry_sha256'][key], 'REGISTRY_PIN')
        docs[key] = json.loads(raw)
    specs = [*docs['tasks']['tasks'], *docs['ideas']['ideas']]
    parents = {row['id']: row for row in specs}
    routing = {row['task_id']: row['queue_id'] for row in docs['routing']['tasks']}
    require(len(specs) == len(parents) == len(routing) == 295 and set(parents) == set(routing),
            'REGISTRY_DENOMINATOR')
    return parents, routing


def run(bundle, spec):
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'[0-9]{1,24}', request) and re.fullmatch(r'[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    require(spec.get('schema') == 'NOX_SYSTEMIC_REVIEWED_PUBLISH_SPEC_V1', 'SPEC_SCHEMA')
    pins = spec.get('assets')
    require(isinstance(pins, dict) and set(pins) == set(bundle) and 3 <= len(pins) <= 32, 'ASSETS')
    assets, total = {}, 0
    for name, pin in pins.items():
        require(re.fullmatch(r'[A-Za-z0-9_.-]{1,180}', name) and SHA.fullmatch(str(pin))
                and isinstance(bundle[name], str) and len(bundle[name]) <= 2800000, 'ASSET_BOUND')
        raw = base64.b64decode(bundle[name], validate=True)
        total += len(raw)
        require(len(raw) <= 2 * 1024 * 1024 and total <= 8 * 1024 * 1024 and digest(raw) == pin, 'ASSET_PIN')
        assets[name] = raw
    require(digest(assets[spec['helper_asset']]) == HELPER_SHA, 'HELPER_PIN')
    helper = types.ModuleType('_nox_systemic_reviewed_helper')
    helper.__file__ = '<reviewed-helper>'
    exec(compile(assets[spec['helper_asset']], helper.__file__, 'exec'), helper.__dict__)
    batches = spec.get('batches')
    require(isinstance(batches, list) and 1 <= len(batches) <= 3
            and len(spec.get('predecessors', [])) == len(batches), 'BATCH_BOUND')
    lock = ROOT / 'state/owner_maintenance.lock'
    require(not any(p.is_symlink() for p in (lock, *lock.parents)), 'LEASE_PATH')
    fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    old_raw = new_raw = None
    changed = False
    receipt = {'schema': 'NOX_SYSTEMIC_REVIEWED_PUBLISH_RECEIPT_V1', 'request': request,
               'source_sha': source, 'state': 'PREFLIGHT', 'started_at': time.time(),
               'workers_restarted': 0, 'queue_writes': 0, 'source_writes': 0, 'test_writes': 0,
               'model_calls': 0, 'original_tasks_accepted': 0, 'review_origin': 'OWNER_REVIEWED'}
    try:
        deadline = time.monotonic() + 8
        while True:
            require(helper.stop_clear(ROOT), 'OWNER_STOP')
            waiting, named = os.fstat(fd), lock.stat()
            require(stat.S_ISREG(waiting.st_mode) and waiting.st_nlink == 1
                    and (waiting.st_dev, waiting.st_ino) == (named.st_dev, named.st_ino), 'LEASE_IDENTITY')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < deadline, 'MAINTENANCE_BUSY')
                time.sleep(.05)
        def guard():
            info, named = os.fstat(fd), lock.stat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1
                    and not info.st_mode & 0o022 and (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino),
                    'LEASE_IDENTITY')
            require(helper.stop_clear(ROOT), 'OWNER_STOP')
            return helper.expected_processes(spec), helper.protected_snapshot(spec)
        processes, protected = guard()
        baseline = wait_settled_queue(helper, guard, (processes, protected), receipt)
        old_raw = helper.read_regular(CONFIG, 2 * 1024 * 1024)
        require(digest(old_raw) == spec['expected_config_sha256'], 'CONFIG_PREDECESSOR')
        old = json.loads(old_raw)
        require(old.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1' and old.get('owner_authorized') is True
                and old.get('instance_id') == 60509551 and old.get('mode') == 'NORMAL'
                and old.get('target') == old.get('global_worker_cap') == 3
                and old.get('execution_mode') == 'NATIVE_PROJECT_V1', 'OWNER_SCOPE')
        for name, pin in old['module_pins'].items():
            require(re.fullmatch(r'owner_[a-z0-9_]+\.py', name) and SHA.fullmatch(pin)
                    and digest(helper.read_regular(ROOT / 'scripts' / name, 1024 * 1024)) == pin, 'RUNTIME_PIN')
        require(old['module_pins']['owner_subagent_dispatcher.py'] == spec['expected_callback_sha256'], 'CALLBACK_PIN')
        loader = importlib.util.spec_from_file_location('_nox_systemic_reviewed_executor', ROOT / 'scripts/owner_project_executor.py')
        require(loader is not None and loader.loader is not None, 'EXECUTOR_LOADER')
        sys.dont_write_bytecode = True
        executor = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(executor)
        project = old['project_executor']
        executor.validate_config(project)
        require(project['package_root'] == str(PACKAGE)
                and project['roots']['NOX_PROJECT_SOURCE']['path'] == str(ROOT / 'projects/owner_executor/source_workspace')
                and project['roots']['NOX_PROJECT_SOURCE']['integration_kind'] == 'SOURCE_WORKSPACE', 'PROJECT_ROOT')
        snapshot = helper.source_snapshot(ROOT, old)
        require(snapshot['files_sha256'] == spec['expected_source_files_sha256'], 'SOURCE_PREIMAGE')
        proof = predecessors(baseline, spec, helper)
        parent_specs, routing = registry(old, helper)
        require(old['catalog'].get('schema') == 'NOX_AUTONOMY_PROCESS_POOL_V1'
                and digest(encoded(old['catalog'])) == old['catalog_sha256'], 'CATALOG_PIN')
        new = copy.deepcopy(old)
        known = {row['id'] for row in old['catalog']['tasks']}
        require(len(known) == len(old['catalog']['tasks']), 'CATALOG_IDS')
        used_assets = {spec['helper_asset']}
        seen_paths = set()
        admitted = []
        with executor.tree(project['roots']['NOX_PROJECT_SOURCE']['path']) as handle:
            for batch, predecessor in zip(batches, spec['predecessors']):
                raw = assets[batch['plan_asset']]
                plan = json.loads(raw)
                pin = digest(raw)
                require(encoded(plan) == raw, 'PLAN_CANONICAL')
                executor.validate_plan(plan, project)
                parent = plan['parent_task_id']
                require(parent == predecessor['parent_task_id'] and parent in parent_specs
                        and plan['spec_sha256'] == digest(encoded(parent_specs[parent]))
                        and plan['queue_id'] == routing[parent] and plan['review_origin'] == 'OWNER_REVIEWED'
                        and plan['root_id'] == 'NOX_PROJECT_SOURCE' and plan['acceptance_scope'] == 'SOURCE_PATCH_TESTED'
                        and plan['original_task_accepted'] is False and 'contract_sha256' not in plan, 'PLAN_SCOPE')
                contract = executor.load_contract_metadata({'contract_sha256': predecessor['contract_sha256']}, project)
                require(plan['verification'] == contract['verification']
                        and {row['path'] for row in plan['context']} == {row['path'] for row in contract['context']},
                        'TRUSTED_VERIFIER_CHANGED')
                paths = {row['path'] for row in plan['files']}
                require(paths == set(contract['editable_paths']) and not (paths & seen_paths)
                        and not any(p.startswith('source_tests/') or Path(p).name.startswith('test_') for p in paths)
                        and all(row['before_sha256'] is not None for row in plan['files']), 'EDIT_SCOPE')
                seen_paths.update(paths)
                require(all(snapshot['files'][row['path']]['sha256'] == row['sha256'] for row in plan['context']), 'CONTEXT_PREIMAGE')
                row = batch['catalog_row']
                expected_row = {'id': plan['task_id'], 'handler': 'owner_native_project_work',
                    'queue_id': plan['queue_id'], 'resource': 'CPU_LIGHT', 'priority': 'P1',
                    'deps': [], 'estimated_cost': 2, 'source_sha256': spec['expected_callback_sha256'],
                    'params': {'parent_task_id': parent, 'plan_sha256': pin}, 'title': batch['title']}
                require(row == expected_row and ID.fullmatch(row['id']) and row['id'] not in known
                        and row['id'] not in baseline['tasks'] and isinstance(batch['title'], str)
                        and 1 <= len(batch['title']) <= 180, 'CATALOG_ROW')
                payloads = {p: assets[name] for p, name in batch['payload_assets'].items()}
                used_assets.add(batch['plan_asset'])
                used_assets.update(batch['payload_assets'].values())
                executor._check_source(handle, plan)
                require(executor.materialize_plan(plan, payloads, project) == {'plan_sha256': pin}, 'PLAN_MATERIALIZATION')
                executor._check_source(handle, plan)
                known.add(row['id'])
                new['catalog']['tasks'].append(copy.deepcopy(row))
                admitted.append({'task_id': row['id'], 'plan_sha256': pin,
                                 'postimages': {r['path']: r['after_sha256'] for r in plan['files']}})
            require(used_assets == set(assets), 'UNUSED_ASSETS')
            new['catalog_sha256'] = digest(encoded(new['catalog']))
            require({k: v for k, v in new.items() if k not in ('catalog', 'catalog_sha256')}
                    == {k: v for k, v in old.items() if k not in ('catalog', 'catalog_sha256')}, 'UNRELATED_CONFIG_CHANGE')
            require(guard() == (processes, protected) and helper.read_regular(CONFIG) == old_raw
                    and helper.source_snapshot(ROOT, old) == snapshot, 'FINAL_CAS_CHANGED')
            final_state, active = helper.queue_idle(ROOT)
            require(not active and helper.preserve_terminal_history(baseline, final_state)['verified']
                    and predecessors(final_state, spec, helper) == proof, 'PREDECESSORS_CHANGED')
            backup = ROOT / 'state/dispatcher/systemic_reviewed_publish_rollback' / request
            require(not backup.exists() and not backup.is_symlink(), 'BACKUP_EXISTS')
            helper.atomic(backup / 'config.json', old_raw)
            new_raw = encoded(new)
            changed = True
            helper.atomic(CONFIG, new_raw)
            require(helper.read_regular(CONFIG) == new_raw and guard() == (processes, protected), 'CONFIG_READBACK')
        receipt.update(state='CATALOG_APPENDED_NATIVE_EXECUTION_PENDING', batches=admitted,
            predecessors=proof, config_sha256=digest(new_raw), previous_config_sha256=digest(old_raw),
            old_catalog_rows=len(old['catalog']['tasks']), new_catalog_rows=len(new['catalog']['tasks']),
            preserved_terminal_tasks=len(baseline['tasks']), processes=processes)
    except BaseException as exc:
        receipt['state'] = str(exc) if re.fullmatch(r'HOLD_[A-Z0-9_]{1,200}', str(exc)) else 'HOLD_SYSTEMIC_REVIEWED_' + type(exc).__name__
        if changed and old_raw is not None and new_raw is not None:
            try:
                if helper.read_regular(CONFIG) == new_raw:
                    helper.atomic(CONFIG, old_raw)
                    receipt['config_restored'] = helper.read_regular(CONFIG) == old_raw
            except Exception:
                receipt['config_restored'] = False
        raise
    finally:
        os.close(fd)
        receipt['finished_at'] = time.time()
        helper.atomic(ROOT / 'state/dispatcher' / ('systemic_reviewed_publish_' + request + '.json'), encoded(receipt))
        print('NOX_MAINT_SYSTEMIC_REVIEWED_PUBLISH=' + encoded(receipt).decode(), flush=True)
    return receipt


if __name__ == '__main__':
    run(BUNDLE, SPEC)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
