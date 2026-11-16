#!/usr/bin/env python3
"""Bind the Qwen media adapter after the actual accepted six-update window.

Only an idle, exact dispatcher reloads. Training, media configuration, prior
plans, reviewer history and the accepted checkpoint are preserved. Blocked-job
inspection is metadata-only; this installer never changes queue task states.
"""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
STATE = ROOT / 'state'
DISPATCHER = SCRIPTS / 'nox_dispatcher_t855u.py'
CONFIG = ROOT / 'config/owner_qwen_media_handoff.json'
SCHEMA = 'NOX_QWEN_MEDIA_HANDOFF_INSTALL_V1'
ADAPTER = 'owner_qwen_media_handoff.py'
ADAPTER_SHA = '312966b352348f0ae0f403cbe84bbfa2e26f89826f285a0a865965650c7931dc'
DISPATCHER_BEFORE = '66afe5e6aa5e3a333c21a86c6aee942c3afd0bf9be007d14f9288a4740281e32'
FRESH_SHA = '670cad05144157a4a2294dbdb07fee7504346587120275c8c85649c5253f2fd4'
WINDOW_REQUEST = '6907513913'
WINDOW_SOURCE = '4d5f0b065309f3524dc4d5d08d3924a4d0223931'
WINDOW_CONTEXT = {'request': WINDOW_REQUEST, 'source_sha': WINDOW_SOURCE,
                  'receipt_sha256': '4547158a490e9c367a6f59f0936f6c0ae3836d40a797fe47b1f303dae38f4308'}
FRESH_CONTEXT = {'request': '6907862216', 'source_sha': 'cf7e49136f3b29644d2346641b90359d717aa98a',
                 'receipt_sha256': '5e39c36179c1d177fe5984fdddfb46ba5264c3975631c3137e1a612ed3e58d73'}
DEPS = {
    'owner_media_training_handoff.py': '36db3c363ffddfc144c6127e1a9407132bbe39d38996233bf3dd64e5b3cb6ec8',
    'owner_qwen_window_entry.py': 'fb9b9dd403f7b1e5d94b8192ce7ad63394ba8a6b3988cc298fc90a195aa191a7',
    'owner_qwen_install_entry.py': '864fe6b0e1567931f94d0b0be55651227ee00fd9106abc4c82e09c13601975d7',
    'owner_qwen_training_observe.py': 'f2dc6c155b682bdeb663bc383f1aa1db70895f815939099690d898262a3d986a',
}
CONTROLS = {
    'owner_subagent_fresh_install_entry.py': FRESH_SHA,
    'owner_subagent_hash_recovery_entry.py': 'de2371d0f5c92063c122b65ff08d15c43015ca599cff8299f9dcb7886bc95659',
    'owner_subagent_install_entry.py': 'a210182012d8872390b27a1f0fa8a5668016f06cd94d5557aad2b242d67eb806',
    'owner_subagent_dispatcher_fresh.py': '179e50b71377e007d32a39d0558ff77dbe02267f43045a4c14763b3d4abd6114',
}
JOBS = ('5eb826584f059b8dd8eeffe8b4f6cb3a', '72c5ab9b719d0b9a5a191f863db42b1f')
MARKER = 'NOX_QWEN_MEDIA_HANDOFF_BIND_V1'
BINDING = ('# ' + MARKER + '\nimport owner_qwen_media_handoff\n'
           'owner_qwen_media_handoff.bind_dispatcher(globals(), owner_media_runtime)\n\n')


def require(value, code):
    if not value:
        raise RuntimeError('HOLD_QWEN_MEDIA_INSTALL_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + '\n').encode()


def safe(exc):
    value = str(exc)
    return value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', value) else type(exc).__name__


def emit(kind, data):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': data}, separators=(',', ':')), flush=True)


def context(value):
    require(isinstance(value, dict) and set(value) == {'request', 'source_sha', 'receipt_sha256'}
            and isinstance(value['request'], str) and re.fullmatch('[0-9]{1,24}', value['request'])
            and re.fullmatch('[a-f0-9]{40}', str(value['source_sha']))
            and re.fullmatch('[a-f0-9]{64}', str(value['receipt_sha256'])), 'SEALED_CONTEXT')
    return dict(value)


def bundle():
    result = {}
    for name, pin in {ADAPTER: ADAPTER_SHA, **DEPS, **CONTROLS}.items():
        raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
        require(0 < len(raw) <= 2 * 1024 ** 2 and digest(raw) == pin, 'BUNDLE_PIN')
        compile(raw, name, 'exec')
        result[name] = raw
    return result


def module(name, raw, alias_file=None):
    value = types.ModuleType('_nox_qwen_media_install_' + name.removesuffix('.py'))
    value.__file__ = str(alias_file or SCRIPTS / name)
    sys.modules[value.__name__] = value
    exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    value.BUNDLE = BUNDLE
    return value


def patch_dispatcher(raw):
    require(digest(raw) == DISPATCHER_BEFORE, 'DISPATCHER_PREIMAGE')
    source = raw.decode()
    anchor = '# NOX_OWNER_TASK_LIFECYCLE_BIND_V1\n'
    require(source.count(anchor) == 1 and MARKER not in source, 'DISPATCHER_ANCHOR')
    result = source.replace(anchor, BINDING + anchor, 1).encode()
    compile(result, '<qwen-handoff-dispatcher>', 'exec')
    return result


def configuration(window_context, media_config_sha, *, resume_training_after_media=False):
    context(window_context)
    require(type(resume_training_after_media) is bool
            and re.fullmatch('[a-f0-9]{64}', str(media_config_sha)), 'CONFIG_SCOPE')
    return {'schema': 'NOX_QWEN_MEDIA_HANDOFF_CONFIG_V1', 'enabled': True,
        'resume_training_after_media': resume_training_after_media, 'source_sha256': ADAPTER_SHA,
        'dependencies': DEPS, 'runtime_sha256': 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5',
        'installer_sha256': 'e66a5b743deb0dfaa7e1e846e11b2d06190962d9ba0ba4abb67abeca54c02ca5',
        'media_config_sha256': media_config_sha, 'window_admission': dict(window_context)}


def check_fresh(h, fresh, expected, dispatcher_sha=DISPATCHER_BEFORE):
    context(expected)
    raw = h.read(STATE / ('owner_subagent_fresh_gate_' + expected['request'] + '.json'))
    require(digest(raw) == expected['receipt_sha256'], 'FRESH_RECEIPT_SHA')
    value = json.loads(raw)
    require(value.get('schema') == 'NOX_NATIVE_SUBAGENT_FRESH_GATE_INSTALL_V1'
            and value.get('request') == expected['request'] and value.get('source_sha') == expected['source_sha']
            and value.get('state') == 'FRESH_GATE_INSTALLED_HISTORY_PRESERVED'
            and value.get('source_installed') is True and value.get('rollback_verified') is not True
            and value.get('callback_after_sha256') == fresh.NEW_CALLBACK
            and value.get('config_after_sha256') == fresh.NEW_CONFIG, 'FRESH_RECEIPT_STATE')
    # This check is read-only. The freshly installed callback and its config
    # are never candidates for replacement or rollback by this installer.
    require(digest(h.read(DISPATCHER)) == dispatcher_sha, 'DISPATCHER_DRIFT')
    require(digest(h.read(h.SUPERVISOR_CONFIG)) == h.SUPERVISOR_SHA, 'SUPERVISOR_DRIFT')
    for name, pin in {**h.DEPENDENCY_PINS, **fresh.DEPENDENCIES}.items():
        expected_pin = fresh.NEW_CALLBACK if name == 'owner_subagent_dispatcher.py' else pin
        require(digest(h.read(SCRIPTS / name)) == expected_pin, 'PROTECTED_DEPENDENCY_DRIFT')
    require(digest(h.read(ROOT / 'config/owner_native_subagents.json')) == fresh.NEW_CONFIG, 'FRESH_CONFIG_DRIFT')


def candidate_actions(assets, window_context):
    adapter = module(ADAPTER, assets[ADAPTER])
    original_read = adapter.read
    def candidate_read(path, limit=2 * 1024 ** 2):
        path = Path(path)
        if path.parent == SCRIPTS and path.name in DEPS:
            return assets[path.name]
        return original_read(path, limit)
    adapter.read = candidate_read
    adapter.load = lambda name, alias_file=None: module(name, assets[name], alias_file)
    runtime_raw = original_read(SCRIPTS / 'owner_media_runtime.py')
    require(digest(runtime_raw) == adapter.MEDIA_SHA, 'MEDIA_RUNTIME_PIN')
    runtime = module('owner_media_runtime.py', runtime_raw)
    actions = adapter.Admission({}, runtime)
    actions.admission, actions.resume_after_media = dict(window_context), False
    return adapter, actions


def workers(h, fresh_after):
    path = ROOT / 'status/agents_t856u.json'
    before = path.stat()
    value = json.loads(h.read(path, 750000))
    rows = value.get('workers') or []
    service = h.service()
    native = value.get('native_subexecutors') or {}
    director = native.get('director') or {}
    process = h.process(service.get('pid')) if service.get('pid') else None
    require(before.st_mtime >= fresh_after and 0 <= time.time() - before.st_mtime <= 15
            and value.get('n') == 6 and len(rows) == 6
            and {row.get('id') for row in rows} == {'nox-agent-%02d' % i for i in range(1, 7)}
            and all(row.get('current_task') is None and row.get('status') == 'idle' for row in rows)
            and process and service['state'] == 'RUNNING' and director.get('pid') == service['pid']
            and director.get('process_starttime') == process['starttime'], 'FRESH_IDLE_WORKERS')
    return {'count': 6, 'busy': 0, 'director_pid': service['pid'], 'heartbeat_mtime': before.st_mtime}


def drain(h, fresh_after, timeout=30):
    deadline = time.monotonic() + timeout
    while True:
        require(not h.global_stop(), 'OWNER_STOP')
        try:
            row = workers(h, fresh_after)
            require(not any(task.get('status') == 'running' for task in h.queue_state()['tasks'].values()), 'RUNNING_CLAIMS')
            return row
        except (RuntimeError, OSError, ValueError, TypeError):
            require(time.monotonic() < deadline, 'IDLE_DRAIN_TIMEOUT')
            time.sleep(.5)


def blocked_projection(h):
    tasks = h.queue_state()['tasks']; rows = []
    allowed = lambda v: v if isinstance(v, str) and re.fullmatch('[A-Z][A-Z0-9_]{0,120}', v) else None
    for jid in JOBS:
        row = {'job_id': jid, 'tasks': []}
        for tid in ('owner.media.' + jid, 'owner.plan.media.' + jid):
            task = tasks.get(tid, {})
            result = task.get('result') if isinstance(task.get('result'), dict) else {}
            row['tasks'].append({'id': tid, 'status': task.get('status') if task.get('status') in
                {'pending', 'running', 'wait', 'retry', 'done', 'failed', 'blocked', 'cancelled'} else 'UNKNOWN',
                'plan_id': task.get('owner_plan_id') if re.fullmatch('[a-f0-9]{24}', str(task.get('owner_plan_id'))) else None,
                'result_state': allowed(result.get('state')), 'plan_wait': allowed(task.get('owner_plan_wait')),
                'claim_present': isinstance(task.get('owner_claim'), dict)})
        path = STATE / 'media/jobs' / (jid + '.json')
        if path.exists() or path.is_symlink():
            raw = h.read(path, 128000); value = json.loads(raw)
            row['media_job'] = {'sha256': digest(raw), 'schema_valid': value.get('schema') == 'NOX_OWNER_MEDIA_JOB_V1',
                'identity_valid': value.get('id') == jid, 'state': allowed(value.get('state')),
                'failure_reason': allowed(value.get('reason')), 'generation_verified': value.get('generation_verified') is True,
                'output_count': len(value.get('outputs', [])) if isinstance(value.get('outputs'), list) else 0}
        else:
            row['media_job'] = {'present': False}
        rows.append(row)
    return {'jobs': rows, 'queue_file_edited': False, 'tasks_requeued': 0, 'private_prompts_exported': False}


SMOKE = r'''
import json,os,runpy,sys
out=os.dup(1);sink=os.open(os.devnull,os.O_WRONLY);os.dup2(sink,1);os.dup2(sink,2);os.close(sink)
result={"state":"HOLD_QWEN_HANDOFF_NATIVE_IMPORT"}
try:
 sys.path.insert(0,"/root/nox/scripts")
 ns=runpy.run_path("/root/nox/scripts/nox_dispatcher_t855u.py",run_name="qwen_media_handoff_smoke")
 assert ns["WORKERS"]==6 and all(ns.get(k) for k in ("_owner_media_bound","_owner_plans_bound","_owner_qwen_media_handoff_bound","_owner_lifecycle_bound"))
 h=sys.modules["owner_qwen_media_handoff"].BOUND
 cfg=h.configuration();ctx=h.actions.context()
 assert cfg["enabled"] is True and cfg["resume_training_after_media"] is False and ctx["mode"]=="COMPLETED_WINDOW6"
 assert callable(ns["HANDLERS"].get("owner_media_resume"))
 result={"state":"QWEN_COMPLETED_SIX_MEDIA_BINDING_VERIFIED","workers":6,"training_started":False}
except Exception as exc:
 text=str(exc);result={"state":"HOLD_QWEN_HANDOFF_NATIVE_IMPORT","exception_class":type(exc).__name__,"code":text if text.startswith(("HOLD_","WAIT_")) and len(text)<160 and all(c.isupper() or c.isdigit() or c=="_" for c in text) else None}
os.write(out,json.dumps(result,separators=(",",":")).encode());os.close(out)
raise SystemExit(0 if result["state"]=="QWEN_COMPLETED_SIX_MEDIA_BINDING_VERIFIED" else 2)
'''


def smoke(python):
    require(isinstance(python, str) and python.startswith('/')
            and re.fullmatch(r'python(?:[0-9]+(?:\.[0-9]+)?)?', Path(python).name), 'PYTHON_IDENTITY')
    row = subprocess.run([python, '-I', '-B', '-c', SMOKE], capture_output=True, timeout=45)
    require(len(row.stdout) <= 4096, 'SMOKE_OUTPUT_BOUND')
    try:
        value = json.loads(row.stdout)
    except ValueError:
        require(False, 'SMOKE_JSON')
    if row.returncode or value.get('state') != 'QWEN_COMPLETED_SIX_MEDIA_BINDING_VERIFIED':
        emit('qwen_media_handoff_smoke', value)
        require(False, 'SMOKE_FAILED')
    return value


def current_or_missing(h, path):
    try:
        return h.read(path)
    except FileNotFoundError:
        return None


def restore(h, saved, written, backup, modes=None):
    # Check every target before any file is restored. Fresh callback/config and
    # training files are deliberately absent from this write set.
    for path, pin in written.items():
        current = current_or_missing(h, path)
        require(current == saved[path] or current is not None and digest(current) == pin, 'ROLLBACK_FOREIGN_WRITE')
    for path in reversed(written):
        current = current_or_missing(h, path)
        if current == saved[path]:
            continue
        require(current is not None and digest(current) == written[path], 'ROLLBACK_RACE')
        if saved[path] is None:
            target = backup / 'failed_new' / str(path).lstrip('/')
            target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            require(not target.exists(), 'ROLLBACK_ARCHIVE_COLLISION')
            path.rename(target)
        else:
            h.atomic(path, saved[path])
            if modes is not None:
                os.chmod(path, modes[path])


def rollback_controller_plan(state, has_writes):
    require(state in ('RUNNING', 'STOPPED', 'EXITED', 'FATAL', 'BACKOFF'), 'ROLLBACK_CONTROLLER_UNSETTLED')
    return {'stop_first': state == 'RUNNING' and has_writes,
            'restart': state != 'RUNNING' or has_writes}


def main(window_context=None, fresh_context=None):
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    window_context = context(WINDOW_CONTEXT if window_context is None else window_context)
    fresh_context = context(FRESH_CONTEXT if fresh_context is None else fresh_context)
    require(window_context == WINDOW_CONTEXT and fresh_context == FRESH_CONTEXT, 'EXACT_NATIVE_CONTEXTS')
    assets = bundle(); fresh = module('owner_subagent_fresh_install_entry.py', assets['owner_subagent_fresh_install_entry.py'])
    h, recovery, _ = fresh.load_helpers()
    adapter, actions = candidate_actions(assets, window_context)
    receipt_path = STATE / ('owner_qwen_media_handoff_' + request + '.json')
    require(not receipt_path.exists() and not receipt_path.is_symlink(), 'REQUEST_ALREADY_USED')
    before = h.read(DISPATCHER); updated = patch_dispatcher(before)
    check_fresh(h, fresh, fresh_context)
    media_path = ROOT / 'config/owner_media_runtime.json'; media_sha = digest(h.read(media_path))
    cfg = configuration(window_context, media_sha); cfg_raw = encoded(cfg)
    require(not CONFIG.exists() and not CONFIG.is_symlink(), 'EXISTING_CONFIG')
    package = {ADAPTER: assets[ADAPTER], **{name: assets[name] for name in DEPS}}
    for name, raw in package.items():
        path = SCRIPTS / name
        require(not path.exists() or h.read(path) == raw, 'EXISTING_DEPENDENCY_CHANGED')
    require(h.active_model() == fresh.CHAT and h.health() == {'8080': 200, '8081': 200, '8082': 200}
            and not h.global_stop(), 'CORE_HEALTH_OR_STOP')
    fd = os.open(STATE / 'owner_maintenance.lock', os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd); raise
    locked_at = time.time(); flag = STATE / 'OWNER_MAINTENANCE.flag'
    note = ('NOX_QWEN_MEDIA_HANDOFF ' + request + ' ' + source + '\n').encode()
    if flag.exists() or flag.is_symlink():
        os.close(fd)
        require(False, 'EXISTING_MAINTENANCE')
    backup = ROOT / 'backup/owner_qwen_media_handoff' / request
    result = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'started_at': locked_at,
        'state': 'PREFLIGHT', 'window_admission': window_context, 'fresh_reviewer_context': fresh_context,
        'source_pins': {ADAPTER: ADAPTER_SHA, **DEPS}, 'dispatcher_before_sha256': digest(before),
        'dispatcher_after_sha256': digest(updated), 'completed_six': None,
        'training_started': False, 'training_flags_written': False, 'weights_changed': False,
        'media_main_configuration_changed': False, 'planner_overwritten': False, 'queue_file_edited': False,
        'tasks_posted': 0, 'tasks_requeued': 0, 'rollback': False, 'installed': []}
    saved, written, modes = {}, {}, {}; stopped = stop_attempted = live = owned_flag = success = False; python = None
    def save():
        h.atomic(receipt_path, encoded(result))
    def install(path, raw, mode):
        require(not h.global_stop(), 'STOP_BEFORE_INSTALL')
        saved[path] = h.read(path) if path.exists() else None
        modes[path] = stat.S_IMODE(path.stat().st_mode) if path.exists() else mode
        if saved[path] is not None:
            h.atomic(backup / str(path).lstrip('/'), saved[path])
        written[path] = digest(raw)
        h.atomic(path, raw); os.chmod(path, mode)
        require(h.read(path) == raw, 'INSTALL_READBACK')
        result['installed'].append({'path': str(path), 'before': digest(saved[path]) if saved[path] is not None else None,
                                     'after': digest(raw)})
        save()
    def start():
        require(not h.global_stop(), 'STOP_BEFORE_START')
        require(h.command(['supervisorctl', 'start', h.SERVICE], 30)[0] == 0, 'DIRECTOR_START')
        deadline = time.monotonic() + 15
        while h.service()['state'] != 'RUNNING':
            require(time.monotonic() < deadline and not h.global_stop(), 'DIRECTOR_START_TIMEOUT')
            time.sleep(.5)
    try:
        flagfd = os.open(flag, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(flagfd, 'wb') as stream:
            stream.write(note); stream.flush(); os.fsync(stream.fileno())
        owned_flag = True
        require(not backup.exists(), 'BACKUP_COLLISION')
        result['blocked_media_before'] = blocked_projection(h)
        training_before = fresh.training_snapshot(h); result['training_before'] = training_before
        result['completed_six'] = adapter.completed_six(actions)
        save(); result['idle_before'] = drain(h, locked_at)
        check_fresh(h, fresh, fresh_context)
        fresh.preserve_training(training_before, fresh.training_snapshot(h))
        group = fresh.dispatcher_group(h, recovery, training_before)
        result['owned_dispatcher_group'] = group
        current = h.service(); owner = h.process(current['pid']); python = owner['argv'][0]
        workers(h, locked_at)
        require(not h.global_stop(), 'STOP_BEFORE_CONTROLLER')
        stop_attempted = True
        try:
            rc = h.command(['supervisorctl', 'stop', h.SERVICE], 30)[0]
        finally:
            stopped = h.service()['state'] == 'STOPPED'
        require(rc == 0 and stopped, 'DIRECTOR_STOP')
        check_fresh(h, fresh, fresh_context)
        fresh.preserve_training(training_before, fresh.training_snapshot(h))
        for name, raw in package.items():
            if (SCRIPTS / name).exists():
                require(h.read(SCRIPTS / name) == raw, 'DEPENDENCY_CHANGED_DURING_DRAIN')
            else:
                install(SCRIPTS / name, raw, 0o644)
        install(CONFIG, cfg_raw, 0o600); install(DISPATCHER, updated, 0o644)
        result['binding_smoke'] = smoke(python)
        start(); stopped = False
        result['workers'] = drain(h, time.time())
        check_fresh(h, fresh, fresh_context, digest(updated))
        require(digest(h.read(media_path)) == media_sha and h.read(CONFIG) == cfg_raw, 'MEDIA_CONFIG_CHANGED')
        result['training_after'] = fresh.training_snapshot(h)
        fresh.preserve_training(training_before, result['training_after'])
        require(h.active_model() == fresh.CHAT and h.health() == {'8080': 200, '8081': 200, '8082': 200}
                and not h.global_stop(), 'CORE_AFTER')
        result['blocked_media_after'] = blocked_projection(h)
        require(h.read(flag, 4096) == note, 'MAINTENANCE_OWNERSHIP')
        result.update(state='COMPLETED_SIX_MEDIA_HANDOFF_BOUND', handoff_config_sha256=digest(cfg_raw),
                      media_config_sha256=media_sha, completed_six_hold_preserved=True,
                      resume_training_after_media=False, finished_at=time.time())
        save(); flag.unlink(); owned_flag = False; live = success = True
    except Exception as exc:
        result.update(state='HOLD_QWEN_MEDIA_HANDOFF_INSTALL', reason=safe(exc))
        if not live and (written or stop_attempted):
            try:
                # Reject a foreign edit before stopping anything for rollback.
                for path, pin in written.items():
                    raw = current_or_missing(h, path)
                    require(raw == saved[path] or raw is not None and digest(raw) == pin, 'ROLLBACK_FOREIGN_WRITE')
                recovery_plan = rollback_controller_plan(h.service()['state'], bool(written))
                if recovery_plan['stop_first']:
                    fresh.dispatcher_group(h, recovery, fresh.training_snapshot(h))
                    require(h.command(['supervisorctl', 'stop', h.SERVICE], 30)[0] == 0
                            and h.service()['state'] == 'STOPPED', 'ROLLBACK_STOP')
                    stopped = True
                restore(h, saved, written, backup, modes); result['rollback'] = bool(written)
                if recovery_plan['restart']:
                    start(); stopped = False
            except Exception as rollback_error:
                result['rollback_error'] = safe(rollback_error)
    finally:
        try:
            if owned_flag and 'rollback_error' not in result and flag.exists() and h.read(flag, 4096) == note:
                flag.unlink(); owned_flag = False
        except Exception as cleanup_error:
            result['maintenance_cleanup_error'] = safe(cleanup_error)
        finally:
            os.close(fd)
        result.update(finished_at=time.time(), maintenance_flag_retained=owned_flag,
                      service_after=h.service(), health_after=h.health())
        save(); emit('qwen_media_handoff_install', result)
        emit('qwen_media_handoff_context', {'request': request, 'source_sha': source,
             'receipt_sha256': digest(h.read(receipt_path)), 'state': result['state'], 'window_admission': window_context})
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit('qwen_media_handoff_preflight', {'state': 'HOLD', 'reason': safe(exc)})
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
