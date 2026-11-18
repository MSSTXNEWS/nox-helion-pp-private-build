#!/usr/bin/env python3
"""Install only the reviewed per-submit resource gate in the existing callback.

Historical review jobs stay done. No task is posted, requeued, or executed for
acceptance. Only the owned dispatcher group reloads; the current Qwen training
configuration and flags are observed dynamically and never written here.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

OLD_CALLBACK = 'b60c14db2b3dbef526daf45843aa96f11f70060c90b071a24f8b61ea7c9e1866'
NEW_CALLBACK = 'f091f6e3097feb6cae561f33948ca27a4bd5639481c0f15516fd0318617e08ee'
OLD_CONFIG = '52e9252ac363679f52ef52c63f27253a4abcca56eca2c30c9c40a68e901bd490'
NEW_CONFIG = 'daf4ac2525906c49958061c7a345f0ece35262c540f4919de0de364b54d10d27'
DISPATCHER_SHA = '66afe5e6aa5e3a333c21a86c6aee942c3afd0bf9be007d14f9288a4740281e32'
POLICY_SHA = '84780aaf911a229a654995f38972cdad5d99c72ab38842f76f787ec280acb46f'
PRIOR_REQUEST = '6907376498'
PRIOR_SOURCE = '6c2d82701ead34c50311b14a48c4b01278ba2879'
PRIOR_RECEIPT_SHA = '772d335786caf3cd4f824e63167186e5cbc1dc00a1c1e2cecb6b61b054a6f050'
CHAT = {'pid': 7637, 'starttime': 149189867}
TRAIN_SERVICE = 'nox-train-volta-t866u'
OLD_DEPENDENCIES = {
    'owner_subagent_processes.py': '117842bc8f0f9adf825213403ebcd2139f80db692d4589ac05b3359381551164',
    'owner_autonomy_pool.py': '8e14f7f7909cefb38686420638621ebf0903e337070ad95d733d86632064ef95',
    'owner_subagent_dispatcher.py': OLD_CALLBACK,
}
NEW_DEPENDENCIES = {
    'owner_subagent_processes.py': '8805da8d99c7d5fe38db6c9a100fb86cc052e1c795418fd78284a5cb7a84d276',
    'owner_autonomy_pool.py': 'c4f0a178d22f47c1e1b2575f6b9c3280165eb0cf13920053c7b427ada3d8f8a9',
    'owner_subagent_dispatcher.py': NEW_CALLBACK,
}
ASSETS = {
    'owner_subagent_hash_recovery_entry.py': 'de2371d0f5c92063c122b65ff08d15c43015ca599cff8299f9dcb7886bc95659',
    'owner_subagent_install_entry.py': 'a210182012d8872390b27a1f0fa8a5668016f06cd94d5557aad2b242d67eb806',
    'owner_subagent_dispatcher_fresh.py': NEW_CALLBACK,
    'owner_subagent_processes.py': NEW_DEPENDENCIES['owner_subagent_processes.py'],
    'owner_autonomy_pool.py': NEW_DEPENDENCIES['owner_autonomy_pool.py'],
}
HANDLER = 'owner_native_subagent_review'
TASKS = {'owner.native.v06.' + role + '.84780aaf911a' for role in ('runtime', 'memory', 'weights')}


def require(value, code):
    if not value:
        raise RuntimeError('HOLD_SUBAGENT_FRESH_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def load_helpers():
    assets = {}
    for name, pin in ASSETS.items():
        value = BUNDLE.get(name)
        require(isinstance(value, str) and 0 < len(value) <= 400000, 'BUNDLE_BOUND')
        raw = base64.b64decode(value, validate=True)
        require(digest(raw) == pin, 'BUNDLE_PIN')
        compile(raw, name, 'exec')
        assets[name] = raw
    recovery = types.ModuleType('owner_fresh_reviewed_recovery_helpers')
    sys.modules[recovery.__name__] = recovery
    exec(compile(assets['owner_subagent_hash_recovery_entry.py'], '<recovery-helpers>', 'exec'), recovery.__dict__)
    # Assignment AFTER exec deliberately avoids the operator's global macro.
    recovery.BUNDLE = BUNDLE
    helper = recovery.helper()
    # Neither recovery.main nor helper.main is called by this operation.
    return helper, recovery, assets


def checked_config(raw):
    require(digest(raw) == OLD_CONFIG, 'CONFIG_PREIMAGE')
    value = json.loads(raw)
    require(value.get('module_pins') == OLD_DEPENDENCIES, 'CONFIG_MODULE_PINS')
    value['module_pins'] = dict(NEW_DEPENDENCIES)
    result = encoded(value)
    require(digest(result) == NEW_CONFIG, 'CONFIG_POSTIMAGE')
    return result


def check_sources(h, callback_sha=OLD_CALLBACK, config_sha=OLD_CONFIG,
                  module_pins=OLD_DEPENDENCIES):
    require(digest(h.read(h.DISPATCHER)) == DISPATCHER_SHA, 'DISPATCHER_PREIMAGE')
    require(digest(h.read(h.SUPERVISOR_CONFIG, 32768)) == h.SUPERVISOR_SHA, 'SUPERVISOR_PREIMAGE')
    for name, pin in {**h.DEPENDENCY_PINS, **module_pins}.items():
        expected = callback_sha if name == 'owner_subagent_dispatcher.py' else pin
        require(digest(h.read(h.SCRIPTS/name)) == expected, 'NATIVE_SOURCE_PIN')
    require(digest(h.read(h.ROOT/'config/owner_native_subagents.json')) == config_sha, 'CONFIG_PREIMAGE')
    require(digest(h.read(h.STATE/'dispatcher/policies/NOX_WEB_WEIGHTS_V06.md', 65536)) == POLICY_SHA,
            'POLICY_PREIMAGE')


def old_callback(h):
    """Import only pinned definitions for read-only S03 receipt verification."""
    for filename, pin in OLD_DEPENDENCIES.items():
        raw = h.read(h.SCRIPTS/filename)
        require(digest(raw) == pin, 'CALLBACK_READBACK_SOURCE')
        name = filename[:-3]
        value = types.ModuleType(name)
        value.__file__ = str(h.SCRIPTS/filename)
        sys.modules[name] = value
        exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    return sys.modules['owner_subagent_dispatcher']


def prior_receipt(h):
    raw = h.read(h.STATE/('owner_native_subagents_recovery_' + PRIOR_REQUEST + '.json'), 262144)
    require(digest(raw) == PRIOR_RECEIPT_SHA, 'PRIOR_RECEIPT_SHA')
    value = json.loads(raw)
    require(value.get('schema') == 'NOX_NATIVE_SUBAGENT_HASH_RECOVERY_V1'
            and value.get('request') == PRIOR_REQUEST and value.get('source_sha') == PRIOR_SOURCE
            and value.get('state') == 'LIVE_NATIVE_REVIEWS_AND_S03_VERIFIED'
            and value.get('new_callback_loaded') is True
            and value.get('config_after_sha256') == OLD_CONFIG
            and value.get('module_after_sha256') == OLD_CALLBACK, 'PRIOR_RECEIPT_SCOPE')
    require({row.get('task_id') for row in value.get('jobs', [])} == TASKS, 'PRIOR_TASK_SET')
    return value


def completed_proofs(h, callback, prior):
    state = h.queue_state()
    rows = state['tasks']
    require({key for key, row in rows.items() if row.get('handler') == HANDLER} == TASKS,
            'UNREVIEWED_CATALOG_TASKS')
    previous = {row['task_id']: row for row in prior['jobs']}
    proofs = {}
    for task_id in sorted(TASKS):
        row = rows.get(task_id, {})
        record = (row.get('result') or {}).get('receipt')
        require(row.get('status') == 'done' and isinstance(record, dict)
                and record.get('source_sha256') == OLD_CALLBACK
                and row.get('owner_claim') == previous[task_id]['claim']
                and record.get('claim') == row.get('owner_claim'), 'HISTORICAL_DONE_TASK')
        proof = callback.s03_readback(record)
        admission = callback.s03_readback(row.get('native_admission'))
        require(proof == previous[task_id]['s03']
                and admission == prior['admission_records_before'][task_id]
                and proof['receipt_sha256'] == row['result'].get('receipt_sha256'), 'HISTORICAL_S03_READBACK')
        proofs[task_id] = {'task_sha256': digest(encoded(row)),
                          'result_receipt_sha256': proof['receipt_sha256'],
                          'admission_receipt_sha256': admission['receipt_sha256'],
                          's03_result_id': proof['s03_item_id'], 'status': 'done'}
    return proofs


def file_identity(h, path, optional=False):
    try:
        before = path.lstat()
    except FileNotFoundError:
        require(optional, 'TRAINING_FILE_MISSING')
        return {'present': False}
    require(stat.S_ISREG(before.st_mode) and before.st_size <= 1048576, 'TRAINING_FILE_TYPE')
    raw = h.read(path)
    after = path.lstat()
    keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode', 'st_uid')
    require(all(getattr(before, key) == getattr(after, key) for key in keys), 'TRAINING_FILE_RACE')
    return {'present': True, 'sha256': digest(raw), 'identity': [getattr(after, key) for key in keys]}


def training_snapshot(h):
    # Read the CURRENT authorized Qwen generation. A later resume may replace
    # admission/wrapper before this lease is acquired; no old c82/9bc pin is used.
    paths = {'admission': h.STATE/'owner_training_admission.json',
             'wrapper': h.SCRIPTS/'run_train_volta_t866u.sh',
             'supervisor': Path('/etc/supervisor/conf.d/nox-train-volta-t866u.conf'),
             'task_boost_policy': h.STATE/'task_boost_mode.json'}
    for name in ('qwen_student_training_entry.py', 'owner_qwen_training_contract.py',
                 'owner_qwen_memfd.py', 'owner_qwen_corpus.py'):
        paths[name] = h.SCRIPTS/name
    files = {key: file_identity(h, path) for key, path in paths.items()}
    admission = json.loads(h.read(paths['admission']))
    require(digest(h.read(paths['admission'])) == files['admission']['sha256'], 'TRAINING_ADMISSION_RACE')
    profile = admission.get('student_profile', {})
    require(admission.get('schema') == 'NOX_OWNER_TRAINING_ADMISSION_V1'
            and profile.get('model_id') == 'Qwen/Qwen3.5-9B'
            and profile.get('training_service') == TRAIN_SERVICE
            and profile.get('physical_gpu') == 1, 'CURRENT_QWEN_SCOPE')
    flags = {name: file_identity(h, h.STATE/name, optional=True)
             for name in ('TRAIN_HOLD.flag', 'TRAIN_PAUSE_REQUEST.flag')}
    rc, output = h.command(['supervisorctl', 'status', TRAIN_SERVICE], 5)
    match = re.fullmatch(re.escape(TRAIN_SERVICE) + r'\s+(RUNNING|STOPPED|STARTING|STOPPING|BACKOFF|FATAL|EXITED)\b(?:\s+pid\s+(\d+))?.*', output.strip())
    require(match is not None, 'TRAINING_SERVICE_STATUS')
    pid = int(match[2]) if match[2] else None
    process = h.process(pid) if pid else None
    require(pid is None or process is not None, 'TRAINING_PROCESS_IDENTITY')
    identity = {key: process[key] for key in ('pid', 'starttime', 'pgrp', 'ppid')} if process else None
    return {'files': files, 'flags': flags, 'service': {'state': match[1], 'pid': pid, 'rc': rc},
            'process': identity, 'student_profile_sha256': digest(encoded(profile))}


def preserve_training(before, after):
    require(before['files'] == after['files'] and before['flags'] == after['flags']
            and before['student_profile_sha256'] == after['student_profile_sha256'], 'TRAINING_IDENTITY_CHANGED')


def dispatcher_group(h, recovery, training):
    observed = h.service()
    owner = h.process(observed['pid']) if observed.get('pid') else None
    require(observed['state'] == 'RUNNING' and owner and str(h.DISPATCHER) in owner['argv'], 'DIRECTOR_IDENTITY')
    require(owner['pgrp'] == owner['pid'] and owner['pgrp'] != os.getpgrp(), 'DIRECTOR_GROUP')
    group = recovery.owned_group(owner['pid'])
    protected = {CHAT['pid']}
    if training.get('process'):
        protected.add(training['process']['pid'])
        require(training['process']['pgrp'] != owner['pgrp'], 'TRAINER_IN_DIRECTOR_GROUP')
    require(not protected & {row['pid'] for row in group}, 'PROTECTED_PROCESS_GROUP')
    # A trainer child is excluded even if its supervisor wrapper has exited.
    for row in group:
        process = h.process(row['pid'])
        require(process is not None and not any('qwen_student_training_entry.py' in arg
                    or 'run_train_volta_t866u.sh' in arg for arg in process['argv']), 'TRAINER_CHILD_IN_GROUP')
    return group


def loaded_status(h):
    state = json.loads(h.read(h.ROOT/'status/agents_t856u.json', 750000))
    native = state.get('native_subexecutors') or {}
    view = native.get('review_status') or {}
    expected_counts = {key: 3 if key == 'done' else 0 for key in
                       ('not_admitted', 'pending', 'running', 'done', 'blocked', 'failed', 'unknown')}
    director = native.get('director') or {}
    current = h.service()
    process = h.process(current['pid']) if current.get('pid') else None
    require(state.get('n') == 6 and native.get('thread_runner_count') == 6
            and native.get('target') == 3 and native.get('workers') == []
            and current['state'] == 'RUNNING' and director.get('pid') == current.get('pid')
            and process and director.get('process_starttime') == process['starttime']
            and 0 <= time.time() - native.get('observed_at', 0) <= 15
            and view.get('queue_counts') == expected_counts and view.get('catalog_tasks') == 3
            and view.get('owned_model_requests_active') == 0
            and view.get('fresh_resource_check') == 'BEFORE_EVERY_SUBMIT'
            and all(view.get(key) is False for key in ('model_answers_authoritative',
                'candidate_actions_applied', 'training_updates_verified', 'capacity_maximum_measured')),
            'LOADED_CALLBACK_STATUS')
    return {'thread_runners': 6, 'completed_reviews': 3, 'reviewer_target': 3,
            'reviewer_pool_actual': 0, 'pool_state': 'WAITING_READY_TASK',
            'director_pid': current['pid'], 'fresh_resource_check': 'BEFORE_EVERY_SUBMIT'}


def rollback_files(h, file_transitions):
    current = {path: h.read(path) for path in file_transitions}
    require(all(raw in file_transitions[path] for path, raw in current.items()),
            'ROLLBACK_FOREIGN_CHANGE')
    for path, (preimage, replacement) in file_transitions.items():
        if current[path] != preimage:
            h.atomic(path, preimage)
    require(all(h.read(path) == pair[0] for path, pair in file_transitions.items()),
            'ROLLBACK_READBACK')


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'\d{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    h, recovery, assets = load_helpers()
    candidate = assets['owner_subagent_dispatcher_fresh.py']
    receipt_path = h.STATE/('owner_subagent_fresh_gate_' + request + '.json')
    require(not receipt_path.exists() and not receipt_path.is_symlink(), 'ALREADY_STARTED_READ_RECEIPT')
    check_sources(h)
    prior = prior_receipt(h)
    callback = old_callback(h)
    before_proofs = completed_proofs(h, callback, prior)
    target, config = h.SCRIPTS/'owner_subagent_dispatcher.py', h.ROOT/'config/owner_native_subagents.json'
    pool_target = h.SCRIPTS/'owner_autonomy_pool.py'
    process_target = h.SCRIPTS/'owner_subagent_processes.py'
    before_module, before_config = h.read(target), h.read(config)
    before_pool, before_process = h.read(pool_target), h.read(process_target)
    updated_config = checked_config(before_config)
    file_transitions = {
        pool_target: (before_pool, assets['owner_autonomy_pool.py']),
        process_target: (before_process, assets['owner_subagent_processes.py']),
        target: (before_module, candidate),
        config: (before_config, updated_config),
    }
    require(not h.global_stop() and h.active_model() == CHAT, 'STOP_OR_CHAT_IDENTITY')
    health = h.health()
    require(health == {'8080': 200, '8081': 200, '8082': 200}, 'CORE_HEALTH')
    lease = os.open(h.STATE/'owner_maintenance.lock', os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(lease)
        raise
    flag = h.STATE/'OWNER_MAINTENANCE.flag'
    if flag.exists() or flag.is_symlink():
        os.close(lease)
        raise RuntimeError('HOLD_SUBAGENT_FRESH_EXISTING_MAINTENANCE')
    note = ('NOX_SUBAGENT_FRESH_GATE ' + request + ' ' + source + '\n').encode()
    result = {'schema': 'NOX_NATIVE_SUBAGENT_FRESH_GATE_INSTALL_V1', 'request': request,
              'source_sha': source, 'state': 'PREFLIGHT', 'started_at': time.time(),
              'callback_before_sha256': OLD_CALLBACK, 'callback_after_sha256': NEW_CALLBACK,
              'config_before_sha256': OLD_CONFIG, 'config_after_sha256': NEW_CONFIG,
              'module_preimages_sha256': {path.name: digest(pair[0]) for path, pair in file_transitions.items()},
              'module_postimages_sha256': {path.name: digest(pair[1]) for path, pair in file_transitions.items()},
              'dispatcher_sha256': DISPATCHER_SHA, 'prior_receipt_sha256': PRIOR_RECEIPT_SHA,
              'completed_reviews_before': before_proofs, 'training_control_performed': False,
              'queue_file_edited': False, 'tasks_posted': 0, 'tasks_requeued': 0,
              'weights_changed': False, 'training_flags_written': False}
    backup = h.ROOT/'backup/owner_subagent_fresh_gate'/request
    stopped = stop_attempted = writes_attempted = released = success = False
    cleanup_flag = True
    training_before = None
    def save():
        h.atomic(receipt_path, encoded(result))
    try:
        h.atomic(flag, note)
        training_before = training_snapshot(h)
        result['training_before'] = training_before
        save()
        deadline = time.monotonic() + 25
        while any(row.get('status') == 'running' for row in h.queue_state()['tasks'].values()):
            require(time.monotonic() < deadline and not h.global_stop(), 'ACTIVE_CLAIMS_OR_STOP')
            time.sleep(.5)
        check_sources(h)
        preserve_training(training_before, training_snapshot(h))
        require(completed_proofs(h, callback, prior) == before_proofs and not h.global_stop(), 'DONE_TASKS_OR_STOP')
        result['owned_group_before'] = dispatcher_group(h, recovery, training_before)
        for path, (preimage, _) in file_transitions.items():
            backup_path = backup/path.name
            require(not backup_path.exists() and not backup_path.is_symlink(), 'BACKUP_ALREADY_EXISTS')
            h.atomic(backup_path, preimage)
            require(h.read(backup_path) == preimage
                    and stat.S_IMODE(backup_path.stat().st_mode) == 0o600,
                    'BACKUP_READBACK')
        stop_attempted = True
        rc = h.command(['supervisorctl', 'stop', h.SERVICE], 25)[0]
        stopped = h.service()['state'] == 'STOPPED'
        require(rc == 0 and stopped, 'DIRECTOR_STOP')
        require(completed_proofs(h, callback, prior) == before_proofs, 'DONE_TASKS_AFTER_STOP')
        check_sources(h)
        writes_attempted = True
        for path, (_, replacement) in file_transitions.items():
            h.atomic(path, replacement)
            require(digest(h.read(path)) == digest(replacement), 'INSTALL_READBACK')
        check_sources(h, NEW_CALLBACK, NEW_CONFIG, NEW_DEPENDENCIES)
        rc = h.command(['supervisorctl', 'start', h.SERVICE], 30)[0]
        stopped = h.service()['state'] == 'STOPPED'
        require(rc == 0 and h.service()['state'] == 'RUNNING', 'DIRECTOR_START')
        deadline = time.monotonic() + 15
        while True:
            try:
                status = loaded_status(h)
                break
            except (RuntimeError, OSError, ValueError, TypeError):
                require(time.monotonic() < deadline and not h.global_stop(), 'CALLBACK_STATUS_TIMEOUT')
                time.sleep(.5)
        after_proofs = completed_proofs(h, callback, prior)
        require(after_proofs == before_proofs, 'HISTORICAL_TASKS_CHANGED')
        training_after = training_snapshot(h)
        preserve_training(training_before, training_after)
        require(h.active_model() == CHAT and h.health() == health and not h.global_stop(), 'CORE_CHANGED_OR_STOP')
        check_sources(h, NEW_CALLBACK, NEW_CONFIG, NEW_DEPENDENCIES)
        require(h.read(flag, 4096) == note, 'MAINTENANCE_OWNERSHIP')
        result.update(state='FRESH_GATE_INSTALLED_HISTORY_PRESERVED', acceptance=status,
                      completed_reviews_after=after_proofs, training_after=training_after,
                      training_configuration_and_flags_preserved=True,
                      training_process_identity_same=training_before['process'] == training_after['process'],
                      active_chat_after=CHAT, chat_health_after=health, finished_at=time.time())
        save()
        flag.unlink()
        os.close(lease)
        lease = None
        released = success = True
    except Exception as exc:
        reason = str(exc)
        result.update(state='HOLD', error=reason if re.fullmatch('HOLD_[A-Z0-9_]+', reason) else type(exc).__name__)
        if not released and (writes_attempted or stop_attempted):
            try:
                # Reject foreign file changes BEFORE any rollback control call.
                require(all(h.read(path) in pair for path, pair in file_transitions.items()),
                        'ROLLBACK_FOREIGN_CHANGE')
                current_state = h.service()['state']
                require(current_state in ('RUNNING', 'STOPPED', 'EXITED', 'FATAL', 'BACKOFF'),
                        'ROLLBACK_SERVICE_UNSETTLED')
                if current_state == 'RUNNING' and writes_attempted:
                    dispatcher_group(h, recovery, training_snapshot(h))
                    require(h.command(['supervisorctl', 'stop', h.SERVICE], 25)[0] == 0
                            and h.service()['state'] == 'STOPPED', 'ROLLBACK_STOP')
                rollback_files(h, file_transitions)
                if current_state != 'RUNNING' or writes_attempted:
                    require(h.command(['supervisorctl', 'start', h.SERVICE], 30)[0] == 0
                            and h.service()['state'] == 'RUNNING', 'ROLLBACK_START')
                result['rollback_verified'] = True
            except Exception as rollback_error:
                code = str(rollback_error)
                result['rollback_error'] = code if re.fullmatch('HOLD_[A-Z0-9_]+', code) else type(rollback_error).__name__
                cleanup_flag = False
    finally:
        if lease is not None:
            try:
                if cleanup_flag and flag.exists() and h.read(flag, 4096) == note:
                    flag.unlink()
                    released = True
            finally:
                os.close(lease)
        result['admissions_reopened'] = released
        result['maintenance_flag_retained'] = not cleanup_flag
        try:
            result['native_callback_sha256'] = digest(h.read(target))
            result['native_config_sha256'] = digest(h.read(config))
            result['native_module_sha256'] = {
                pool_target.name: digest(h.read(pool_target)),
                process_target.name: digest(h.read(process_target)),
            }
            result['source_installed'] = (
                result['native_callback_sha256'] == NEW_CALLBACK
                and result['native_config_sha256'] == NEW_CONFIG
                and result['native_module_sha256'] == {
                    'owner_autonomy_pool.py': NEW_DEPENDENCIES['owner_autonomy_pool.py'],
                    'owner_subagent_processes.py': NEW_DEPENDENCIES['owner_subagent_processes.py'],
                })
        except (OSError, RuntimeError):
            result['source_installed'] = None
        result['receipt_path'] = str(receipt_path)
        save()
        h.emit('native_subagent_fresh_gate', result)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:
        reason = str(exc)
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'native_subagent_fresh_gate_preflight',
              'data': {'state': 'HOLD', 'reason': reason if re.fullmatch('HOLD_[A-Z0-9_]+', reason) else type(exc).__name__}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        code = 2
    raise SystemExit(code)
