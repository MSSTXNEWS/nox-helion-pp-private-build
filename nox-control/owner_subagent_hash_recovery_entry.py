#!/usr/bin/env python3
"""Correct one observed S03 hash contract and resume the SAME native jobs.

Only the existing dispatcher reloads. Admission records are read back, never
POSTed again. No queue file is edited by this payload; its installed ticker
reconciles the already-owned three staged rows through the normal callbacks.
"""
from __future__ import annotations
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
OLD_MODULE = '28f2e21786cef4fb4a2627ac810789dc1b5b65c8196712c19eb5d8398d70b800'
OLD_CONFIG = '803eb3f0d08f9b139313af00b8d5eea407a85de6422a0dba8c796cb4dbed5eff'
DISPATCHER = '66afe5e6aa5e3a333c21a86c6aee942c3afd0bf9be007d14f9288a4740281e32'
ADMISSIONS = {'memory': 'S03-fdba9601c77541b7', 'runtime': 'S03-571049691ccb4428',
              'weights': 'S03-7301ffbc0df54ae0'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def corrected_source(raw):
    if digest(raw) != OLD_MODULE:
        raise RuntimeError('HOLD_SUBAGENT_REPAIR_SOURCE_CHANGED')
    source = raw.decode()
    changes = (
        ("conn.execute('SELECT id,text,meta,sha256 FROM s03_items WHERE text=? AND provenance=? LIMIT 2',",
         'conn.execute("SELECT id,text,meta,sha256 FROM s03_items WHERE segment=\'M2\' AND text=? AND provenance=? LIMIT 2",'),
        ('rows[0][3] != digest(text.encode())', "rows[0][3] != digest(('M2|'+text).encode())"),
    )
    for old, new in changes:
        if source.count(old) != 1:
            raise RuntimeError('HOLD_SUBAGENT_REPAIR_ANCHOR')
        source = source.replace(old, new)
    compile(source, 'owner_subagent_dispatcher.py', 'exec')
    return source.encode()


def helper():
    raw = base64.b64decode(BUNDLE.get('owner_subagent_install_entry.py', ''), validate=True)
    if not raw or len(raw) > 40000:
        raise RuntimeError('HOLD_SUBAGENT_REPAIR_HELPER')
    value = types.ModuleType('owner_subagent_recovery_helper')
    value.__dict__['__NOX_' + 'BUNDLE_JSON__'] = BUNDLE
    sys.modules[value.__name__] = value
    exec(compile(raw, '<reviewed-subagent-helper>', 'exec'), value.__dict__)
    return value


def metadata(pid):
    try:
        row = Path('/proc', str(pid), 'stat').read_text().split(') ', 1)[1].split()
        return {'pid': int(pid), 'ppid': int(row[1]), 'pgrp': int(row[2]),
                'starttime': int(row[19]), 'state': row[0]}
    except (OSError, ValueError, IndexError):
        return None


def owned_group(pid):
    director = metadata(pid)
    if director is None:
        raise RuntimeError('HOLD_SUBAGENT_DIRECTOR_GONE')
    rows = [row for folder in Path('/proc').iterdir() if folder.name.isdigit()
            and (row := metadata(folder.name)) and row['pgrp'] == director['pgrp'] and row['state'] != 'Z']
    owned = {pid}
    for _ in range(len(rows)):
        owned.update(row['pid'] for row in rows if row['ppid'] in owned)
    if any(row['pid'] not in owned for row in rows):
        raise RuntimeError('HOLD_SUBAGENT_UNRELATED_PROCESS_GROUP')
    return rows


def admissions(state, module):
    result = {}
    for role, item_id in ADMISSIONS.items():
        task_id = 'owner.native.v06.'+role+'.84780aaf911a'
        task = state['tasks'].get(task_id, {})
        receipt = task.get('native_admission')
        if not isinstance(receipt, dict) or receipt.get('source_sha256') != OLD_MODULE:
            raise RuntimeError('HOLD_SUBAGENT_ADMISSION_IDENTITY')
        proof = module.s03_readback(receipt)
        if not proof or proof.get('s03_item_id') != item_id:
            raise RuntimeError('HOLD_SUBAGENT_ORIGINAL_S03_RECEIPT')
        result[task_id] = proof
    return result


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}', source):
        raise RuntimeError('HOLD_SUBAGENT_OWNER_CONTEXT')
    h = helper()
    path = h.STATE/('owner_native_subagents_recovery_'+request+'.json')
    if path.exists() or path.is_symlink():
        raise RuntimeError('HOLD_SUBAGENT_RECOVERY_ALREADY_STARTED_READBACK')
    target = h.SCRIPTS/'owner_subagent_dispatcher.py'
    config_path = ROOT/'config/owner_native_subagents.json'
    before_module, before_config = h.read(target), h.read(config_path)
    corrected = corrected_source(before_module)
    if digest(before_config) != OLD_CONFIG:
        raise RuntimeError('HOLD_SUBAGENT_REPAIR_CONFIG_CHANGED')
    assets, module = h.reviewed_modules()
    if corrected != assets['owner_subagent_dispatcher.py']:
        raise RuntimeError('HOLD_SUBAGENT_REPAIR_NOT_EXACT_TWO_LINE_DELTA')
    config = json.loads(before_config)
    if config['module_pins']['owner_subagent_dispatcher.py'] != OLD_MODULE:
        raise RuntimeError('HOLD_SUBAGENT_OLD_PIN')
    for name, pin in config['module_pins'].items():
        if digest(h.read(h.SCRIPTS/name)) != pin:
            raise RuntimeError('HOLD_SUBAGENT_INSTALLED_DEPENDENCY_CHANGED')
    for name, pin in h.DEPENDENCY_PINS.items():
        if digest(h.read(h.SCRIPTS/name)) != pin:
            raise RuntimeError('HOLD_SUBAGENT_ORIGINAL_DEPENDENCY_CHANGED')
    if digest(h.read(h.DISPATCHER)) != DISPATCHER or digest(h.read(h.SUPERVISOR_CONFIG)) != h.SUPERVISOR_SHA:
        raise RuntimeError('HOLD_SUBAGENT_DIRECTOR_SOURCE_CHANGED')
    before_proofs = admissions(h.queue_state(), module)
    before_model, before_health = h.active_model(), h.health()
    if any(value != 200 for value in before_health.values()) or h.global_stop():
        raise RuntimeError('HOLD_SUBAGENT_CORE_HEALTH_OR_STOP')
    config['module_pins']['owner_subagent_dispatcher.py'] = digest(corrected)
    updated_config = module.encoded(config)
    fd = os.open(h.STATE/'owner_maintenance.lock', os.O_RDWR | os.O_NOFOLLOW)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    flag = h.STATE/'OWNER_MAINTENANCE.flag'
    if flag.exists() or flag.is_symlink():
        os.close(fd)
        raise RuntimeError('HOLD_EXISTING_OWNER_MAINTENANCE')
    note = ('NOX_SUBAGENT_CANONICAL_HASH_REPAIR '+request+' '+source+'\n').encode()
    result = {'schema': 'NOX_NATIVE_SUBAGENT_HASH_RECOVERY_V1', 'request': request, 'source_sha': source,
              'started_at': time.time(), 'state': 'PREFLIGHT', 'admission_records_before': before_proofs,
              'module_before_sha256': OLD_MODULE, 'module_after_sha256': digest(corrected),
              'config_before_sha256': OLD_CONFIG, 'config_after_sha256': digest(updated_config),
              'active_model_before': before_model, 'chat_health_before': before_health,
              'legacy_training_hold_before': h.training_hold_observation(),
              'queue_file_edited_by_payload': False, 'admission_post_repeated': False,
              'training_started': False, 'weights_changed': False, 'stop_cleared': False}
    stopped = changed = released = success = False
    backup = ROOT/'backup/owner_native_subagent_hash_recovery'/request
    def save():
        h.atomic(path, module.encoded(result))
    try:
        h.atomic(flag, note)
        save()
        deadline = time.monotonic()+25
        while any(row.get('status') == 'running' for row in h.queue_state()['tasks'].values()):
            if time.monotonic() >= deadline:
                raise RuntimeError('HOLD_SUBAGENT_ACTIVE_NATIVE_CLAIMS')
            time.sleep(.5)
        if h.global_stop() or digest(h.read(target)) != OLD_MODULE or digest(h.read(config_path)) != OLD_CONFIG:
            raise RuntimeError('HOLD_SUBAGENT_STOP_OR_PREIMAGE_CHANGED')
        observed = h.service()
        owner = h.process(observed['pid']) if observed.get('pid') else None
        if observed['state'] != 'RUNNING' or not owner or str(h.DISPATCHER) not in owner['argv']:
            raise RuntimeError('HOLD_SUBAGENT_DIRECTOR_IDENTITY')
        result['owned_group_before'] = owned_group(owner['pid'])
        if before_model['pid'] in {row['pid'] for row in result['owned_group_before']}:
            raise RuntimeError('HOLD_SUBAGENT_MODEL_IN_DIRECTOR_GROUP')
        h.atomic(backup/'owner_subagent_dispatcher.py', before_module)
        h.atomic(backup/'owner_native_subagents.json', before_config)
        rc = h.command(['supervisorctl', 'stop', h.SERVICE], 25)[0]
        stopped = h.service()['state'] == 'STOPPED'
        if rc != 0 or not stopped:
            raise RuntimeError('HOLD_SUBAGENT_DIRECTOR_STOP_UNVERIFIED')
        if admissions(h.queue_state(), module) != before_proofs:
            raise RuntimeError('HOLD_SUBAGENT_ADMISSION_CHANGED_DURING_DRAIN')
        h.atomic(target, corrected)
        changed = True
        h.atomic(config_path, updated_config)
        if h.read(target) != corrected or h.read(config_path) != updated_config:
            raise RuntimeError('HOLD_SUBAGENT_REPAIR_WRITE_READBACK')
        if h.command(['supervisorctl', 'start', h.SERVICE], 30)[0] != 0 or h.service()['state'] != 'RUNNING':
            raise RuntimeError('HOLD_SUBAGENT_DIRECTOR_START_UNVERIFIED')
        stopped = False
        if h.active_model() != before_model or h.health() != before_health:
            raise RuntimeError('HOLD_SUBAGENT_CORE_IDENTITY_CHANGED')
        if h.read(flag, 4096) != note:
            raise RuntimeError('HOLD_SUBAGENT_MAINTENANCE_OWNER_CHANGED')
        flag.unlink()
        os.close(fd)
        fd = None
        released = True
        expected = set(before_proofs)
        deadline = time.monotonic()+180
        while time.monotonic() < deadline:
            state = h.queue_state()
            tasks = [state['tasks'].get(task_id, {}) for task_id in sorted(expected)]
            if h.global_stop():
                raise RuntimeError('HOLD_OWNER_STOP')
            result['task_states'] = [{key: task.get(key) for key in ('id', 'status', 'note')} for task in tasks]
            failures = [row for row in tasks if row.get('status') in ('blocked', 'failed')
                        and row.get('note') != 'WAIT_S03_ADMISSION_READBACK']
            if failures:
                raise RuntimeError('HOLD_SUBAGENT_REVIEW_FAILED')
            if all(task.get('status') == 'done' for task in tasks):
                proofs = []
                for task in tasks:
                    evidence = task.get('result') or {}
                    receipt = evidence.get('receipt')
                    if (not isinstance(receipt, dict) or receipt.get('source_sha256') != digest(corrected)
                            or receipt.get('phase') != 'NATIVE_REVIEW_COMPLETED_CANDIDATE_NOT_APPLIED'):
                        raise RuntimeError('HOLD_SUBAGENT_NEW_RESULT_SOURCE')
                    proof = module.s03_readback(receipt)
                    if not proof or proof['receipt_sha256'] != evidence.get('receipt_sha256'):
                        raise RuntimeError('HOLD_SUBAGENT_NEW_RESULT_S03')
                    proofs.append({'task_id': task['id'], 'job_id': receipt['job_id'],
                        'claim': task['owner_claim'], 's03': proof, 'worker_result': receipt['worker_result'],
                        'scope': 'NATIVE_TECHNICAL_REVIEW_CANDIDATE_NOT_APPLIED'})
                native = json.loads(h.read(ROOT/'status/agents_t856u.json', 750000)).get('native_subexecutors', {})
                workers = module.autonomy.verify_distinct_native_processes(native.get('workers', []), requested=3)
                if any(module.process_identity(row['pid']) != {key: row[key] for key in ('pid', 'ppid', 'process_starttime')}
                       or not 0 <= time.time()-row.get('heartbeat_at', 0) <= 15 for row in workers):
                    time.sleep(1)
                    continue
                events = h.owner_events(expected)
                if {row['task']['id'] for row in events} != expected:
                    time.sleep(1)
                    continue
                if any(not any(event['task'].get('claim') == proof['claim']['nonce']
                               and event['verification'].get('receipt_sha256') == proof['s03']['receipt_sha256']
                               for event in events if event['task']['id'] == proof['task_id']) for proof in proofs):
                    raise RuntimeError('HOLD_SUBAGENT_OWNER_CALLBACK_IDENTITY')
                if admissions(state, module) != before_proofs:
                    raise RuntimeError('HOLD_SUBAGENT_ADMISSION_REPLACED')
                if {row['worker_result']['pid'] for row in proofs} != {row['pid'] for row in workers}:
                    raise RuntimeError('HOLD_SUBAGENT_RESULT_PID_COUNT')
                result.update(state='LIVE_NATIVE_REVIEWS_AND_S03_VERIFIED', jobs=proofs,
                    owner_task_events=events, native_pool=native, admission_records_reused=True,
                    active_model_after=h.active_model(), chat_health_after=h.health(), finished_at=time.time())
                if result['active_model_after'] != before_model or result['chat_health_after'] != before_health:
                    raise RuntimeError('HOLD_SUBAGENT_CORE_IDENTITY_CHANGED')
                success = True
                break
            time.sleep(2)
        if not success:
            raise RuntimeError('HOLD_SUBAGENT_NATIVE_ACCEPTANCE_TIMEOUT')
    except Exception as exc:
        reason = str(exc)
        result.update(state='HOLD', error=reason if re.fullmatch('HOLD_[A-Z0-9_]+', reason) else type(exc).__name__)
        if not released:
            try:
                if changed and h.service()['state'] == 'RUNNING':
                    h.command(['supervisorctl', 'stop', h.SERVICE], 25)
                    stopped = True
                if changed and h.read(target) == corrected:
                    h.atomic(target, before_module)
                if changed and h.read(config_path) == updated_config:
                    h.atomic(config_path, before_config)
                if stopped:
                    h.command(['supervisorctl', 'start', h.SERVICE], 30)
                result['rollback_service'] = h.service()
            except Exception as rollback:
                result['rollback_error'] = type(rollback).__name__
    finally:
        if fd is not None:
            try:
                if flag.exists() and h.read(flag, 4096) == note:
                    flag.unlink()
            finally:
                os.close(fd)
        result['new_callback_loaded'] = released
        result['legacy_training_hold_after'] = h.training_hold_observation()
        result['receipt_path'] = str(path)
        save()
        h.emit('native_subagent_hash_recovery', result)
    print('NOX_MAINT_REPAIR_COMPLETE='+str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:
        reason = str(exc)
        print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'native_subagent_recovery_preflight', 'data': {
            'state': 'HOLD', 'error': reason if re.fullmatch('HOLD_[A-Z0-9_]+', reason) else type(exc).__name__}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        code = 2
    raise SystemExit(code)
