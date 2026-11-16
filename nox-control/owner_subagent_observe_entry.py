#!/usr/bin/env python3
"""Read-only diagnosis of the already installed native NOX worker binding.

No POST, install, service change, queue mutation or second worker launch.
Only this operation's technical S03 rows and public source are exported.
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time
import types
import urllib.request

ROOT = Path('/root/nox')
INITIAL_REQUEST = '6906985850'
INITIAL_SOURCE = '41fbe63b5e57b1172956f8264c403aefa338aa6d'
POLICY_SHA = '84780aaf911a229a654995f38972cdad5d99c72ab38842f76f787ec280acb46f'
PINS = {
    'owner_subagent_processes.py': '117842bc8f0f9adf825213403ebcd2139f80db692d4589ac05b3359381551164',
    'owner_autonomy_pool.py': '8e14f7f7909cefb38686420638621ebf0903e337070ad95d733d86632064ef95',
    'owner_subagent_dispatcher.py': '28f2e21786cef4fb4a2627ac810789dc1b5b65c8196712c19eb5d8398d70b800',
    'nox_dispatcher_t855u.py': '66afe5e6aa5e3a333c21a86c6aee942c3afd0bf9be007d14f9288a4740281e32',
    's03_memory.py': '3ebdc3585f32bafbd0e1210ceee286b174a657c37696e16fce9fcafb57c43e10',
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def read(path, maximum=262144):
    path = Path(path)
    if any(p.is_symlink() for p in (*path.parents, path)):
        raise RuntimeError('HOLD_OBSERVER_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise RuntimeError('HOLD_OBSERVER_SOURCE_SIZE')
        raw = stream.read(maximum+1)
    if len(raw) > maximum:
        raise RuntimeError('HOLD_OBSERVER_SOURCE_SIZE')
    return raw


def record_diagnostic(receipt, row):
    """Hashes and exact receipt equality only; never return row text/meta."""
    item_id, segment, text, provenance, stored_sha, meta = row
    expected_text = ('NOX native job '+receipt['job_id']+' '+receipt['phase']+
                     ' receipt_sha256 '+digest(encoded(receipt)))
    try:
        metadata = json.loads(meta)
    except (ValueError, TypeError):
        metadata = {}
    plain_sha = digest(text.encode())
    segment_sha = digest((segment+'|'+text).encode())
    return {'s03_item_id': item_id, 'task_id': receipt['task_id'], 'job_id': receipt['job_id'],
            'phase': receipt['phase'], 'segment': segment, 'stored_sha256': stored_sha,
            'computed_text_sha256': plain_sha, 'computed_segment_text_sha256': segment_sha,
            'plain_hash_matches': stored_sha == plain_sha, 'segment_hash_matches': stored_sha == segment_sha,
            'expected_text_matches': text == expected_text,
            'provenance_matches': provenance == 'owner_native_subagents',
            'meta_receipt_matches': isinstance(metadata, dict) and metadata.get('receipt') == receipt,
            'text_or_private_meta_exported': False}


def collect():
    result = {'schema': 'NOX_NATIVE_SUBAGENT_READBACK_V1', 'read_only': True,
              'initial_request': INITIAL_REQUEST, 'initial_source': INITIAL_SOURCE,
              'observed_at': time.time(), 'state': 'OBSERVED_NOT_RUNTIME_ACCEPTED'}
    sources = {name: read(ROOT/'scripts'/name) for name in PINS}
    result['source_pins'] = {name: {'sha256': digest(raw), 'expected': PINS[name],
                                   'matches': digest(raw) == PINS[name]} for name, raw in sources.items()}
    if not all(row['matches'] for row in result['source_pins'].values()):
        return {**result, 'state': 'HOLD_OBSERVER_NATIVE_SOURCE_CHANGED'}
    source = sources['s03_memory.py'].decode()
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'remember')
    excerpt = ast.get_source_segment(source, function)
    if len(excerpt.encode()) > 10000:
        raise RuntimeError('HOLD_OBSERVER_FUNCTION_BUDGET')
    result['remember_function_source'] = excerpt
    raw_config = read(ROOT/'config/owner_native_subagents.json')
    config = json.loads(raw_config)
    if (config.get('owner_request') != INITIAL_REQUEST or config.get('owner_source_sha') != INITIAL_SOURCE
            or config.get('policy', {}).get('sha256') != POLICY_SHA
            or config.get('catalog_sha256') != digest(encoded(config.get('catalog')))):
        raise RuntimeError('HOLD_OBSERVER_INSTALL_IDENTITY')
    result['config_sha256'] = digest(raw_config)
    result['policy_sha256'] = digest(read(ROOT/'state/dispatcher/policies/NOX_WEB_WEIGHTS_V06.md'))
    expected = {row['id'] for row in config['catalog']['tasks']}
    if expected != {'owner.native.v06.'+role+'.'+POLICY_SHA[:12] for role in ('runtime', 'memory', 'weights')}:
        raise RuntimeError('HOLD_OBSERVER_TASK_SCOPE')
    state = json.loads(read(ROOT/'state/dispatcher/state.json', 16*1024*1024))
    db = ROOT/'kb/knowledge.sqlite'
    if any(p.is_symlink() for p in (*db.parents, db)):
        raise RuntimeError('HOLD_OBSERVER_DATABASE_SYMLINK')
    conn = sqlite3.connect(db.as_uri()+'?mode=ro', uri=True, timeout=.2)
    tasks = []
    try:
        conn.execute('PRAGMA query_only=ON')
        deadline = time.monotonic()+3
        conn.set_progress_handler(lambda: int(time.monotonic()>deadline), 1000)
        for task_id in sorted(expected):
            task = state.get('tasks', {}).get(task_id, {})
            note = task.get('note')
            projected = {'id': task_id, 'status': task.get('status'), 'claim': task.get('owner_claim'),
                         'note': note if isinstance(note, str) and re.fullmatch('[A-Z0-9_ .:-]{1,160}', note) else None,
                         's03_records': []}
            for receipt in (task.get('native_admission'), (task.get('result') or {}).get('receipt')):
                if not isinstance(receipt, dict) or receipt.get('task_id') != task_id:
                    continue
                text = 'NOX native job '+receipt['job_id']+' '+receipt['phase']+' receipt_sha256 '+digest(encoded(receipt))
                rows = conn.execute('SELECT id,segment,text,provenance,sha256,meta FROM s03_items WHERE text=? LIMIT 3', (text,)).fetchall()
                projected['s03_records'].extend(record_diagnostic(receipt, row) for row in rows)
                if not rows:
                    projected['s03_records'].append({'phase': receipt['phase'], 'matching_rows': 0})
            tasks.append(projected)
    finally:
        conn.close()
    result['tasks'] = tasks
    result['all_tasks_done'] = all(row['status'] == 'done' for row in tasks)
    status = json.loads(read(ROOT/'status/agents_t856u.json', 750000))
    result['native_subexecutors'] = status.get('native_subexecutors')
    result['legacy_thread_runner_count'] = status.get('n')
    prior = json.loads(read(ROOT/'state'/('owner_native_subagents_install_'+INITIAL_REQUEST+'.json')))
    result['install_receipt'] = {key: prior.get(key) for key in ('state', 'error', 'source_installed',
        'dispatcher_after_sha256', 'active_model_before', 'legacy_training_hold_after')}
    result['health'] = {}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for port in (8080, 8081, 8082):
        try:
            with opener.open('http://127.0.0.1:%d/health' % port, timeout=2) as response:
                result['health'][str(port)] = response.status
        except OSError:
            result['health'][str(port)] = None
    return result


def main():
    try:
        value = collect()
        print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'native_subagent_readback', 'data': value}, separators=(',', ':')), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
        return 0
    except Exception as exc:
        code = str(exc)
        print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'native_subagent_readback', 'data': {
            'read_only': True, 'state': 'HOLD', 'error': code if re.fullmatch('HOLD_[A-Z0-9_]+', code) else type(exc).__name__}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
