#!/usr/bin/env python3
"""Freeze three reviewed corrections against the actual settled native receipts."""
from __future__ import annotations
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', required=True)
    args = parser.parse_args()
    base = Path(__file__).resolve().parent
    repo = base.parents[1]
    out = base / 'reviewed_recovery'
    assets = out / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    snapshot = json.loads(Path(args.snapshot).read_bytes())
    census = snapshot['NOX_MAINT_SCOPE_PROJECT_SOURCE_WORKSPACE_CENSUS'][0]
    first, latest = snapshot['NOX_MAINT_SCOPE_POST_WORKERS']
    assert snapshot['NOX_MAINT_REMOTE_EXIT_CODE'] == [0]
    assert census['two_reads_match'] is True and census['complete_allowed_files_read'] is True
    assert not census['unattributed_changed_paths'] and not census['read_errors']
    assert first['observed_director'] == latest['observed_director']
    assert len(latest['workers']) == 3
    for a, b in zip(first['workers'], latest['workers']):
        assert a['verified'] is True and b['verified'] is True
        assert a['observed']['pid'] == b['observed']['pid']
        assert a['observed']['start_ticks'] == b['observed']['start_ticks']
        assert b['claimed']['heartbeat_at'] > a['claimed']['heartbeat_at']
        assert a['claimed']['current_task'] is None and b['claimed']['current_task'] is None
    callback = sha((base / 'runtime/owner_subagent_dispatcher.py').read_bytes())
    entry_rows = {x['id']: x for x in snapshot['NOX_MAINT_SCOPE_PROJECT_EXECUTION']}
    batch_v1 = json.loads((base / 'mission_pack_v1/batch.json').read_bytes())
    manifest_path = base / 'mission_pack_v1/package/relay' / (batch_v1['manifest_sha256'] + '.json')
    manifest = json.loads(manifest_path.read_bytes())
    descriptions = {
        'cache_fill_ttl': ('nox_runpod/teacher_mesh/v38/durable_runtime.py', '3A03', 'cache_ttl',
                           'Apply reviewed insertion-time cache TTL after the stalled model attempt'),
        'forge_read_budget': ('forge_split_guard.py', '4A02', 'forge_budget',
                             'Complete bounded split reads and pre-parse row enforcement'),
        'skill_journal_budget': ('owner_dispatcher_mentor.py', '3B05', 'skill_budget',
                               'Complete bounded skill journal and marker identity reads'),
    }
    helper = repo / 'nox-control/continuous_executor_20261118/assets/continuous_transaction_helpers.py'
    helper_asset = 'reviewed_systemic_transaction_helpers.py'
    assert sha(helper.read_bytes()) == '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
    (assets / helper_asset).write_bytes(helper.read_bytes())
    pins = {helper_asset: sha(helper.read_bytes())}
    asset_sources = {helper_asset: str((assets / helper_asset).relative_to(repo))}
    batches, predecessors = [], []
    for mission in manifest['missions']:
        path, parent, key, title = descriptions[mission['mission_id']]
        choices = [r for r in entry_rows.values() if r.get('parent_task_id') == parent
                   and r['id'].startswith(parent + '.relay.' + mission['mission_id'] + '.')]
        assert len(choices) == 1
        observed = choices[0]
        assert observed['status'] in ('blocked', 'done')
        assert observed['receipt_sha_matches'] is True and observed['receipt_claim_matches'] is True
        assert observed['native_worker_lease']['phase'] == 'SETTLED'
        predecessor = {'task_id': observed['id'], 'parent_task_id': parent,
                       'status': observed['status'], 'receipt_sha256': observed['result']['receipt_sha256'],
                       'contract_sha256': batch_v1['contracts'][observed['id']]}
        if observed['status'] == 'blocked':
            predecessor['reason'] = observed['project_evidence']['reason']
            assert predecessor['reason'] == 'PLANNER_REPEATED_ACTION_NO_PROGRESS'
            assert observed['project_evidence']['project_source_changed'] is False
        else:
            predecessor['postimages'] = observed['project_evidence']['postimages']
            assert observed['project_evidence']['integration_verified'] is True
            assert predecessor['postimages'] == {path: census['files'][path]['sha256']}
        contract_path = base / 'mission_pack_v1/package/contracts' / (predecessor['contract_sha256'] + '.json')
        contract = json.loads(contract_path.read_bytes())
        assert sha(contract_path.read_bytes()) == predecessor['contract_sha256']
        payload = (out / 'source' / path).read_bytes()
        compile(payload, path, 'exec')
        after, before = sha(payload), census['files'][path]['sha256']
        assert after != before
        task_id = parent + '.project.systemic_reviewed_' + key + '.20261118'
        plan = {'schema': 'NOX_PROJECT_WORK_PLAN_V1', 'task_id': task_id,
                'parent_task_id': parent, 'queue_id': mission['queue_id'], 'root_id': 'NOX_PROJECT_SOURCE',
                'operation': 'apply_reviewed_files', 'review_origin': 'OWNER_REVIEWED',
                'spec_sha256': manifest['registry']['parents'][parent]['spec_sha256'],
                'context': [{'path': r['path'], 'sha256': census['files'][r['path']]['sha256']}
                            for r in contract['context']],
                'files': [{'path': path, 'before_sha256': before,
                           'after_sha256': after, 'payload_sha256': after}],
                'verification': contract['verification'], 'acceptance_scope': 'SOURCE_PATCH_TESTED',
                'original_task_accepted': False}
        raw = encoded(plan)
        pin = sha(raw)
        plan_asset = 'reviewed_' + key + '_plan.json'
        payload_asset = 'reviewed_' + key + '_payload.source'
        for name, data in ((plan_asset, raw), (payload_asset, payload)):
            (assets / name).write_bytes(data)
            pins[name] = sha(data)
            asset_sources[name] = str((assets / name).relative_to(repo))
        row = {'id': task_id, 'handler': 'owner_native_project_work', 'queue_id': plan['queue_id'],
               'resource': 'CPU_LIGHT', 'priority': 'P1', 'deps': [], 'estimated_cost': 2,
               'source_sha256': callback, 'params': {'parent_task_id': parent, 'plan_sha256': pin},
               'title': title}
        batches.append({'title': title, 'plan_asset': plan_asset, 'payload_assets': {after: payload_asset},
                        'catalog_row': row})
        predecessors.append(predecessor)
    services = snapshot['NOX_MAINT_SCOPE_SNAPSHOT_B'][0]['services']
    def service(name):
        rows = [r['identity'] for r in services if r['service'] == name and r['state'] == 'RUNNING']
        assert len(rows) == 1
        return {k: rows[0][k] for k in ('pid', 'ppid', 'pgrp', 'start_ticks')}
    spec = {'schema': 'NOX_SYSTEMIC_REVIEWED_PUBLISH_SPEC_V1', 'assets': pins,
            'helper_asset': helper_asset, 'batches': batches, 'predecessors': predecessors,
            'expected_callback_sha256': callback, 'expected_config_sha256': census['config_sha256'],
            'expected_source_files_sha256': census['files_sha256'],
            'expected_director': {k: latest['observed_director'][k] for k in ('pid', 'start_ticks')},
            'expected_workers': [{k: r['observed'][k] for k in ('pid', 'start_ticks')} for r in latest['workers']],
            'protected_processes': {'chat': service('nox-ds41-8098'), 'proxy': service('nox-proxy'),
                                    'web': service('nox-web29-18775')}}
    (out / 'publish_spec.json').write_bytes(encoded(spec))
    (out / 'asset_sources.json').write_bytes(encoded(asset_sources))
    template = (base / 'owner_systemic_reviewed_publish.py').read_text()
    assert template.count('SPEC = {}') == 1
    entry = template.replace('SPEC = {}', 'SPEC = ' + repr(spec))
    compile(entry, 'owner_systemic_reviewed_entry.py', 'exec')
    entry_path = base / 'owner_systemic_reviewed_entry.py'
    entry_path.write_text(entry)
    operator = repo / 'nox-control/owner_native_operator.py'
    text = operator.read_text()
    lines = text.splitlines(keepends=True)
    changes = {}
    for node in ast.parse(text).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name not in ('FILES', 'SCOPED_REPAIR_BUNDLES', 'SCOPED_REPAIR_EXTRA_PATHS'):
            continue
        value = ast.literal_eval(node.value)
        key = str(entry_path.relative_to(repo))
        if name == 'FILES':
            value['repair'] = key
        elif name == 'SCOPED_REPAIR_BUNDLES':
            value[key] = tuple(asset_sources)
        else:
            value[key] = tuple(asset_sources.values())
        changes[node.lineno - 1] = (node.end_lineno, name + '=' + repr(value) + '\n')
    assert len(changes) == 3
    for start, (end, replacement) in sorted(changes.items(), reverse=True):
        lines[start:end] = [replacement]
    result = ''.join(lines)
    compile(result, str(operator), 'exec')
    operator.write_text(result)
    print(json.dumps({'entry': str(entry_path.relative_to(repo)), 'assets': len(pins),
        'tasks': [b['catalog_row']['id'] for b in batches], 'expected_config': census['config_sha256'],
        'source_census': census['files_sha256'], 'model_calls_required': 0, 'native_operation_performed': False}))


if __name__ == '__main__':
    main()
