#!/usr/bin/env python3
"""Bind the reviewed relay to one fresh owner snapshot; never contact the host."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--snapshot', required=True)
    args = args.parse_args()
    base = Path(__file__).resolve().parent
    repo = base.parents[1]
    snapshot = json.loads(Path(args.snapshot).read_bytes())
    census = snapshot['NOX_MAINT_SCOPE_PROJECT_SOURCE_WORKSPACE_CENSUS'][0]
    worker_views = snapshot['NOX_MAINT_SCOPE_POST_WORKERS']
    assert len(worker_views) == 2 and census['two_reads_match'] is True
    assert not census['unattributed_changed_paths']
    first, latest = worker_views
    assert all(row['verified'] for row in latest['workers']) and len(latest['workers']) == 3
    assert first['observed_director'] == latest['observed_director']
    for a, b in zip(first['workers'], latest['workers']):
        assert a['observed']['pid'] == b['observed']['pid']
        assert a['observed']['start_ticks'] == b['observed']['start_ticks']
        assert b['claimed']['heartbeat_at'] > a['claimed']['heartbeat_at']
        assert b['claimed']['current_task'] is None
    batch = json.loads((base/'mission_pack_v1/batch.json').read_bytes())
    assert batch['source_files_sha256'] == census['files_sha256']
    runtime = base/'runtime'
    callback = sha((runtime/'owner_subagent_dispatcher.py').read_bytes())
    truth = (repo/'nox-control/continuous_executor_20261118/assets/continuous_truth.py').read_text()
    truth, count = re.subn(r"(?m)^CALLBACK_SHA = '[a-f0-9]{64}'$", "CALLBACK_SHA = '" + callback + "'", truth)
    assert count == 1
    (runtime/'owner_subagent_instruction_truth.py').write_text(truth)
    assets = base/'assets'
    assets.mkdir(exist_ok=True)
    runtime_paths, package_paths, pins, asset_sources = {}, {}, {}, {}
    for name in ('owner_subagent_dispatcher.py','owner_subagent_processes.py',
                 'owner_project_native.py','owner_project_planner.py',
                 'owner_subagent_instruction_truth.py','owner_systemic_refill.py'):
        raw = (runtime/name).read_bytes()
        compile(raw,name,'exec')
        asset = 'systemic_' + name
        (assets/asset).write_bytes(raw)
        runtime_paths[asset] = 'scripts/' + name
        pins[asset] = sha(raw)
        asset_sources[asset] = str((assets/asset).relative_to(repo))
    helper = repo/'nox-control/continuous_executor_20261118/assets/continuous_transaction_helpers.py'
    assert sha(helper.read_bytes()) == '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
    helper_asset = 'systemic_transaction_helpers.py'
    (assets/helper_asset).write_bytes(helper.read_bytes())
    pins[helper_asset] = sha(helper.read_bytes())
    asset_sources[helper_asset] = str((assets/helper_asset).relative_to(repo))
    for old_name, source in batch['asset_sources'].items():
        raw = (base/'mission_pack_v1'/source).read_bytes()
        asset = 'systemic_' + old_name
        (assets/asset).write_bytes(raw)
        pins[asset] = sha(raw)
        package_paths[asset] = batch['package_paths'][old_name]
        asset_sources[asset] = str((assets/asset).relative_to(repo))
    previous = json.loads((repo/'nox-control/c02_memory_progress_20261118/recovery_install_spec.json').read_bytes())
    expected = previous['expected_native']
    expected['config/owner_native_subagents.json'] = census['config_sha256']
    for row in snapshot['NOX_MAINT_SCOPE_PROJECT_RUNTIME_SOURCE']:
        assert row['matches_module_pin'] is True
        expected['scripts/' + row['name']] = row['sha256']
    services = snapshot['NOX_MAINT_SCOPE_SNAPSHOT_B'][0]['services']
    def service(name):
        matches = [row['identity'] for row in services if row['service'] == name and row['state'] == 'RUNNING']
        assert len(matches) == 1
        return {key:matches[0][key] for key in ('pid','ppid','pgrp','start_ticks')}
    spec = {'schema':'NOX_SYSTEMIC_RELAY_INSTALL_SPEC_V1', 'assets':pins,
        'helper_asset':helper_asset, 'runtime_paths':runtime_paths, 'package_paths':package_paths,
        'manifest_sha256':batch['manifest_sha256'], 'batch_task_ids':sorted(batch['contracts']),
        'expected_native':expected, 'expected_bootstrap_sha256':census['bootstrap']['sha256'],
        'expected_source_files_sha256':census['files_sha256'],
        'expected_director':{key:latest['observed_director'][key] for key in ('pid','start_ticks')},
        'expected_workers':[{key:row['observed'][key] for key in ('pid','start_ticks')} for row in latest['workers']],
        'protected_processes':{'chat':service('nox-ds41-8098'),'proxy':service('nox-proxy'),'web':service('nox-web29-18775')}}
    (base/'install_spec.json').write_bytes(encoded(spec))
    (base/'asset_sources.json').write_bytes(encoded(asset_sources))
    template = (base/'owner_systemic_relay_install.py').read_text()
    marker = 'SPEC = {}  # The packager embeds the exact reviewed installation specification.'
    assert template.count(marker) == 1
    entry = template.replace(marker,'SPEC = ' + repr(spec))
    compile(entry,'owner_systemic_relay_entry.py','exec')
    (base/'owner_systemic_relay_entry.py').write_text(entry)
    # The operator selects the exact reviewed entry and only its named bundle.
    operator = repo/'nox-control/owner_native_operator.py'
    text = operator.read_text()
    source = text.splitlines(keepends=True)
    entry_path = str((base/'owner_systemic_relay_entry.py').relative_to(repo))
    changes = {}
    for node in ast.parse(text).body:
        if not isinstance(node,ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0],ast.Name):
            continue
        name = node.targets[0].id
        if name not in ('FILES','SCOPED_REPAIR_BUNDLES','SCOPED_REPAIR_EXTRA_PATHS'):
            continue
        value = ast.literal_eval(node.value)
        if name == 'FILES':
            value['repair'] = entry_path
            value['inspect'] = str((base/'owner_systemic_relay_observe.py').relative_to(repo))
        elif name == 'SCOPED_REPAIR_BUNDLES':
            value[entry_path] = tuple(asset_sources)
        else:
            value[entry_path] = tuple(asset_sources.values())
        changes[node.lineno - 1] = (node.end_lineno, name + '=' + repr(value) + '\n')
    assert len(changes) == 3
    for first_line,(last_line,replacement) in sorted(changes.items(),reverse=True):
        source[first_line:last_line] = [replacement]
    result = ''.join(source)
    compile(result,str(operator),'exec')
    operator.write_text(result)
    print(json.dumps({'entry':entry_path, 'manifest_sha256':batch['manifest_sha256'],
        'runtime_files':len(runtime_paths),'package_files':len(package_paths),
        'source_workspace_writes':0,'tasks':spec['batch_task_ids'],'native_operation_performed':False}))


if __name__ == '__main__':
    main()
