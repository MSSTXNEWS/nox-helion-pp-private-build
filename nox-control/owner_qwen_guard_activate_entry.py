#!/usr/bin/env python3
"""Advance accepted Qwen6 once, then bind its sealed1000 window to the guard.

The exact reviewed window entry performs the sole start. This wrapper changes
only two existing private configurations and its own receipt/backup. It never
calls Guard.tick, restarts the dispatcher, clears a pause, or rolls back a
started window. Failure after a matching1000 admission requests its own
checkpoint-aware pause. Counter observations are not an in-memory optimizer
barrier: that remaining visibility limit is stated in the receipt.
"""
import base64
import contextlib
import fcntl
import hashlib
import io
import json
import math
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

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SCRIPTS = ROOT / 'scripts'
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
GUARD_CONFIG = ROOT / 'config/owner_qwen_training_guard.json'
MEDIA_CONFIG = ROOT / 'config/owner_qwen_media_handoff.json'
GUARD_STATE = STATE / 'owner_qwen_training_guard.json'
SCHEMA = 'NOX_QWEN_GUARDED_WINDOW_ACTIVATION_V1'
WINDOW = 'owner_qwen_window_entry.py'
HELPER = 'owner_qwen_install_entry.py'
GUARD = 'owner_qwen_training_guard.py'
HANDOFF = 'owner_qwen_media_handoff.py'
OBSERVER = 'owner_qwen_training_observe.py'
PINS = {
    WINDOW: 'fb9b9dd403f7b1e5d94b8192ce7ad63394ba8a6b3988cc298fc90a195aa191a7',
    HELPER: '864fe6b0e1567931f94d0b0be55651227ee00fd9106abc4c82e09c13601975d7',
    GUARD: '2a6f6ade1a913bf42bc921d997b83109323adf3227570cf29a0ffc61a7b2614c',
    HANDOFF: '312966b352348f0ae0f403cbe84bbfa2e26f89826f285a0a865965650c7931dc',
    OBSERVER: 'f2dc6c155b682bdeb663bc383f1aa1db70895f815939099690d898262a3d986a',
    'owner_qwen_media_guard.py': 'acd1ec157ba171e979f82b7e058b4a5054a81fae3884ee1cb8ba8fd33c419450',
    'owner_media_training_handoff.py': '36db3c363ffddfc144c6127e1a9407132bbe39d38996233bf3dd64e5b3cb6ec8',
    'owner_media_runtime.py': 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5',
    'owner_media_install.py': 'e66a5b743deb0dfaa7e1e846e11b2d06190962d9ba0ba4abb67abeca54c02ca5',
}
DISPATCHER_SHA = '439f669487e965b3a9709078674c1fbff6ceff332b0ad2089dad1f218c2e57cf'
DISABLED_CONFIG_SHA = '9335aac28edf0c60389ac6976ae599009ddb83a22a61b0c1b112557f0a30e423'
MEDIA_CONFIG_SHA = '6ecf2239cb300a44c1601063bafe2de855c1c083f44852bb4421910ba304c2f2'
RUNTIME_CONFIG_SHA = 'd76d900d6898a7a33a5cacfc1f4fd334e8fa4a5c72160a9b6ea900fa02beb560'
MEDIA_INSTALL = {'request': '6907909296', 'source_sha': '32f527a55808684e5cfd4c4a9f58d9f4cce68bde',
                 'receipt_sha256': '18498798d36bb4cea7ac3f8c274c9cd443f82986eb7c1821d8e0844a9081be35'}
SIX = {'request': '6907513913', 'source_sha': '4d5f0b065309f3524dc4d5d08d3924a4d0223931',
       'receipt_sha256': '4547158a490e9c367a6f59f0936f6c0ae3836d40a797fe47b1f303dae38f4308'}
SIX_ACCEPTANCE = '2076f7050169692e0333747d07abb5c290b429c1b30d56fd55928fc215edfc00'
SIX_MANIFEST = 'bbe6ff24861fdcf33d28eba089edba583406ffbb9184c68e5a43d305a619b293'


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_QWEN_ACTIVATE_' + code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + '\n').encode()


def plain(path):
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (*path.parents, path)), 'SYMLINK')
    return path


def read(path, maximum=2 * 1024 ** 2):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        first = os.fstat(stream.fileno())
        require(stat.S_ISREG(first.st_mode) and 0 <= first.st_size <= maximum, 'FILE_BOUND')
        raw = stream.read(maximum + 1)
        identity = lambda v: (v.st_dev, v.st_ino, v.st_size, v.st_mtime_ns, v.st_ctime_ns)
        require(len(raw) == first.st_size and identity(first) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)), 'FILE_CHANGED')
    return raw


def pairs(rows):
    result = {}
    for key, value in rows:
        require(key not in result, 'JSON_DUPLICATE'); result[key] = value
    return result


def document(path, maximum=2 * 1024 ** 2):
    raw = read(path, maximum)
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
    require(isinstance(value, dict), 'JSON_OBJECT')
    return value, raw


def private(path):
    info = plain(path).stat(follow_symlinks=False)
    require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600, 'CONFIG_PERMISSIONS')


def context(value):
    require(isinstance(value, dict) and set(value) == {'request', 'source_sha', 'receipt_sha256'}
            and type(value['request']) is str and re.fullmatch('[0-9]{1,24}', value['request'])
            and type(value['source_sha']) is str and re.fullmatch('[a-f0-9]{40}', value['source_sha'])
            and type(value['receipt_sha256']) is str and re.fullmatch('[a-f0-9]{64}', value['receipt_sha256']),
            'SEALED_CONTEXT')
    return dict(value)


def load(name, raw=None):
    raw = read(SCRIPTS / name) if raw is None else raw
    require(sha(raw) == PINS[name], 'SOURCE_PIN')
    value = types.ModuleType('_nox_guard_activate_' + name.removesuffix('.py'))
    value.__file__ = str(SCRIPTS / name); sys.modules[value.__name__] = value
    exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    return value


def transform_window(raw):
    require(sha(raw) == PINS[WINDOW], 'WINDOW_PREIMAGE')
    before = b'MODE = "ADVANCE6"  # Reviewed transition after native first-five observation.'
    after = b'MODE = "ADVANCE1000"  # Reviewed transition after native first-five observation.'
    require(raw.count(before) == 1, 'WINDOW_MODE_ANCHOR')
    changed = raw.replace(before, after, 1)
    require(changed.replace(after, before, 1) == raw, 'WINDOW_CHANGE_SCOPE')
    compile(changed, '<qwen-window1000>', 'exec')
    return changed


def window_module():
    assets = {}
    for name in (WINDOW, HELPER):
        value = BUNDLE.get(name)
        require(isinstance(value, str) and len(value) <= 3 * 1024 ** 2, 'BUNDLE_BOUND')
        raw = base64.b64decode(value, validate=True)
        require(sha(raw) == PINS[name] and read(SCRIPTS / name) == raw, 'BUNDLE_NATIVE_PIN')
        assets[name] = raw
    raw = transform_window(assets[WINDOW])
    module = types.ModuleType('_nox_guarded_advance1000'); module.__file__ = str(SCRIPTS / WINDOW)
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    module.BUNDLE = {HELPER: base64.b64encode(assets[HELPER]).decode()}
    return module, module.helper(), sha(raw)


def sources():
    for name, pin in PINS.items():
        require(sha(read(SCRIPTS / name)) == pin, 'INSTALLED_SOURCE_CHANGED')
    require(sha(read(SCRIPTS / 'nox_dispatcher_t855u.py')) == DISPATCHER_SHA
            and sha(read(ROOT / 'config/owner_media_runtime.json')) == RUNTIME_CONFIG_SHA, 'DISPATCHER_OR_RUNTIME_CONFIG')


def installed_guard_proof(sealed):
    sealed = context(sealed)
    row, raw = document(STATE / ('owner_qwen_guard_install_' + sealed['request'] + '.json'), 128000)
    require(sha(raw) == sealed['receipt_sha256'] and row.get('request') == sealed['request']
            and row.get('source_sha') == sealed['source_sha']
            and row.get('schema') == 'NOX_QWEN_INACTIVE_GUARD_INSTALL_V1'
            and row.get('state') == 'INACTIVE_QWEN_GUARD_AND_MEDIA_READER_INSTALLED'
            and row.get('prior_handoff') == MEDIA_INSTALL and row.get('window_admission') == SIX
            and row.get('dispatcher_after_sha256') == DISPATCHER_SHA
            and row.get('guard_config_sha256') == DISABLED_CONFIG_SHA
            and row.get('existing_handoff_config_sha256') == MEDIA_CONFIG_SHA
            and row.get('existing_media_config_sha256') == RUNTIME_CONFIG_SHA
            and row.get('source_pins') == {GUARD: PINS[GUARD], 'owner_qwen_media_guard.py': PINS['owner_qwen_media_guard.py']},
            'GUARD_INSTALL_RECEIPT')
    require(all(row.get(key) is True for key in ('completed_six_preserved', 'training_flags_preserved',
                'historical_reviews_preserved', 'chat_identity_preserved'))
            and all(row.get(key) is False for key in ('guard_enabled', 'window1000_admitted', 'training_started',
                'rollback', 'maintenance_flag_retained')), 'GUARD_INSTALL_PRESERVATION')
    smoke = row.get('binding_smoke', {})
    require(smoke.get('state') == 'INACTIVE_QWEN_GUARD_AND_MEDIA_READER_VERIFIED'
            and smoke.get('guard_tick_no_action') is True
            and smoke.get('flags_and_guard_state_unchanged') is True, 'GUARD_INSTALL_SMOKE')
    prior, raw = document(STATE / ('owner_qwen_media_handoff_' + MEDIA_INSTALL['request'] + '.json'), 128000)
    require(sha(raw) == MEDIA_INSTALL['receipt_sha256']
            and prior.get('state') == 'COMPLETED_SIX_MEDIA_HANDOFF_BOUND', 'MEDIA_INSTALL_RECEIPT')
    window, raw = document(STATE / ('owner_qwen_window_' + SIX['request'] + '.json'), 128000)
    require(sha(raw) == SIX['receipt_sha256'] and window.get('target_goal') == 6, 'SIX_WINDOW_RECEIPT')
    return row


def acquire(path):
    fd = os.open(plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid(), 'LEASE_FILE')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        after = path.stat(follow_symlinks=False)
        require((info.st_dev, info.st_ino) == (after.st_dev, after.st_ino), 'LEASE_CHANGED')
        return fd
    except BaseException:
        os.close(fd); raise


def acquire_after_start(path):
    """Let the existing <=4s guard reader finish; never bypass other errors."""
    deadline = time.monotonic() + 6
    while True:
        try:
            return acquire(path)
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'MAINTENANCE_REACQUIRE_TIMEOUT')
            time.sleep(min(.2, remaining))


def controller(h, obs):
    row = h.command(['supervisorctl', 'status', 'nox-dispatcher-t855u'], 5)
    match = re.match(r'^nox-dispatcher-t855u\s+RUNNING\s+pid\s+([0-9]+),', row.stdout[:4096])
    require(row.returncode == 0 and match, 'DISPATCHER_NOT_RUNNING')
    pid = int(match[1]); process = obs.process(pid)
    argv = obs.proc_bytes(Path('/proc') / str(pid) / 'cmdline').rstrip(b'\0').split(b'\0')
    require(process and process['state'] != 'Z' and str(SCRIPTS / 'nox_dispatcher_t855u.py').encode() in argv,
            'DISPATCHER_PROCESS_IDENTITY')
    return {'pid': pid, 'start_ticks': process['start_ticks']}


def trainer_snapshot(window, h, obs, ctx, *, required=False):
    service = h.service()
    args = window.arguments(h, ctx['profile'], ctx['admission']['request'], sha(ctx['raw']),
                            ctx['profile']['successful_updates_goal'], resume=True)
    rows = obs.trainers(args, service)
    require(len(rows) <= 1 and all(all(row.get(key) is True for key in
            ('exact_admitted_argv', 'cuda_visible_devices_1', 'supervisor_ancestry_verified')) for row in rows),
            'TRAINER_PROCESS_IDENTITY')
    require(not required or service['state'] == 'RUNNING' and len(rows) == 1, 'TRAINER_NOT_RUNNING')
    return {'service': service, 'process': {key: rows[0][key] for key in ('pid', 'ppid', 'start_ticks')}
            if rows else None}


def counters(obs, contract):
    pointer, pointer_raw = document(OUTPUT / 'latest_checkpoint.json', 16384)
    name = pointer.get('directory')
    require(isinstance(name, str) and re.fullmatch('checkpoint-u[0-9]{8}-a[0-9]{8}-g[0-9]{20}', name), 'CHECKPOINT_PATH')
    manifest, manifest_raw = document(OUTPUT / name / 'checkpoint_manifest.json', 65536)
    require(sha(manifest_raw) == pointer.get('manifest_sha256'), 'CHECKPOINT_MANIFEST')
    state, state_raw = document(OUTPUT / name / 'student_state.json')
    require(sha(state_raw) == (manifest.get('files_sha256') or {}).get('student_state.json'), 'CHECKPOINT_COUNTER_SHA')
    proof = obs.update_chain(state, contract)
    result = {'successful_optimizer_steps': proof['successful_optimizer_steps'],
              'attempted_steps': proof['attempted_steps'], 'skipped_steps': proof['skipped_steps'],
              'pointer_sha256': sha(pointer_raw), 'manifest_sha256': sha(manifest_raw),
              'student_state_sha256': sha(state_raw), 'progress': None}
    progress_path = OUTPUT / 'owner_progress.json'
    if progress_path.exists() or progress_path.is_symlink():
        progress, raw = document(progress_path, 16384)
        good, attempted, skipped = (progress.get(key) for key in ('successful_optimizer_steps', 'attempted_steps', 'skipped_steps'))
        require(progress.get('state') == 'NATIVE_STUDENT_UPDATE_OBSERVED'
                and all(type(v) is int and 0 <= v <= 10 ** 8 for v in (good, attempted, skipped))
                and attempted == good + skipped and type(progress.get('pid')) is int
                and type(progress.get('time')) in (int, float) and math.isfinite(progress['time']), 'PROGRESS_COUNTERS')
        result['progress'] = {'sha256': sha(raw), 'successful_optimizer_steps': good, 'attempted_steps': attempted,
                              'skipped_steps': skipped, 'pid': progress['pid'], 'time': progress['time']}
    require(read(OUTPUT / 'latest_checkpoint.json', 16384) == pointer_raw, 'COUNTER_POINTER_RACE')
    return result


def no_observed_advance(before, after):
    require(all(after.get(key) == before.get(key) for key in ('successful_optimizer_steps', 'attempted_steps',
            'skipped_steps', 'pointer_sha256', 'manifest_sha256', 'student_state_sha256'))
            and before['successful_optimizer_steps'] == before['attempted_steps'] == 6 and before['skipped_steps'] == 0,
            'UPDATES_BEFORE_GUARD')
    progress = after.get('progress')
    require(progress is None or progress['successful_optimizer_steps'] <= 6 and progress['attempted_steps'] <= 6
            and progress['skipped_steps'] == 0, 'PROGRESS_BEFORE_GUARD')


def commit_configurations(h, previous, new_guard, new_media):
    """Two atomic files under the caller's EX lease; partial commit never rolls back."""
    for path, value in ((GUARD_CONFIG, new_guard), (MEDIA_CONFIG, new_media)):
        require(read(path, 32768) == previous[path] and not h.owner_stop(), 'CONFIG_CHANGED_BEFORE_WRITE')
        h.atomic(path, encode(value)); private(path)
        require(read(path, 32768) == encode(value), 'CONFIG_READBACK')


def new_window(window, h, request, source):
    row, raw = document(STATE / ('owner_qwen_window_' + request + '.json'), 128000)
    require(row.get('schema') == 'NOX_QWEN_WINDOW_ADVANCE_V1'
            and row.get('state') == 'WINDOW_STARTED_ACCEPTANCE_PENDING'
            and row.get('request') == request and row.get('source_sha') == source and row.get('target_goal') == 1000
            and row.get('previous_request') == SIX['request'], 'WINDOW_START_RECEIPT')
    accepted = row.get('acceptance', {})
    require(accepted.get('previous_goal') == 6 and accepted.get('target_goal') == 1000
            and accepted.get('acceptance_sha256') == accepted.get('terminal_receipt_sha256') == SIX_ACCEPTANCE
            and accepted.get('checkpoint', {}).get('manifest_sha256') == SIX_MANIFEST
            and accepted.get('checkpoint', {}).get('all_checkpoint_file_sha256_verified') is True, 'WINDOW_SIX_ACCEPTANCE')
    ctx = window.context(h)
    require(ctx['admission']['request'] == request and ctx['admission']['source_sha'] == source
            and ctx['profile']['successful_updates_goal'] == 1000
            and row.get('new_admission_sha256') == sha(ctx['raw'])
            and row.get('wrapper_sha256') == sha(ctx['wrapper']), 'NEW_ADMISSION_WRAPPER')
    return {'request': request, 'source_sha': source, 'receipt_sha256': sha(raw)}, row, ctx


def own_pause(h, window, request, source, reason):
    """Pause only this exact new admission, without replacing anyone's flag."""
    pointer, raw = document(h.ADMISSION, 64000)
    require(pointer.get('request') == request and pointer.get('source_sha') == source
            and pointer.get('initial_request') == '6907283384'
            and pointer.get('previous_request') == SIX['request']
            and pointer.get('sources') == {str(SCRIPTS / n): p for n, p in h.PINS.items() if n.endswith('.py')}
            and pointer.get('student_profile', {}).get('successful_updates_goal') == 1000, 'PAUSE_SCOPE_CHANGED')
    args = window.arguments(h, pointer['student_profile'], request, sha(raw), 1000, resume=True)
    require(read(h.WRAPPER) == window.wrapper(h, args, request, 1000), 'PAUSE_WRAPPER_CHANGED')
    path = STATE / 'TRAIN_PAUSE_REQUEST.flag'
    token = ('NOX_QWEN_ACTIVATION_PAUSE_V1 request=' + request + ' source=' + source + ' reason=' + reason + '\n').encode()
    try:
        fd = os.open(plain(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    except FileExistsError:
        return {'state': 'EXISTING_PAUSE_PRESERVED', 'checkpoint_after_pause_verified': False}
    with os.fdopen(fd, 'wb') as stream:
        stream.write(token); stream.flush(); os.fsync(stream.fileno())
    directory = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    require(read(path, 4096) == token, 'PAUSE_READBACK')
    return {'state': 'OWN_ACTIVATION_CHECKPOINT_PAUSE_REQUESTED', 'sha256': sha(token),
            'checkpoint_after_pause_verified': False, 'service_killed': False}


def safe(exc):
    value = str(exc)
    return value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', value) else 'HOLD_QWEN_ACTIVATE_UNVERIFIED'


def emit(kind, data):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': data}, ensure_ascii=False,
          allow_nan=False, separators=(',', ':')), flush=True)


def main(guard_install_context=None):
    install_context = context(guard_install_context)
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source)
            and request not in (SIX['request'], MEDIA_INSTALL['request'], install_context['request']), 'OWNER_CONTEXT')
    window, h, transformed_sha = window_module()
    guard, media, runtime, obs = (load(name) for name in (GUARD, HANDOFF, 'owner_media_runtime.py', OBSERVER))
    receipt = STATE / ('owner_qwen_guard_activate_' + request + '.json')
    backup = ROOT / 'backup/owner_qwen_guard_activate' / request
    require(all(not plain(p).exists() and not p.is_symlink() for p in (receipt, backup,
            STATE / ('owner_qwen_window_' + request + '.json'))), 'REQUEST_ALREADY_USED')
    result = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'guard_installation': install_context,
              'state': 'PREFLIGHT', 'started_at': time.time(), 'original_window': SIX,
              'window_source_sha256': PINS[WINDOW], 'in_memory_window_mode_sha256': transformed_sha,
              'source_pins': dict(PINS), 'training_started': False, 'window_start_attempted': False,
              'configuration_committed': False,
              'dispatcher_restarted': False, 'manual_guard_tick_called': False, 'flags_cleared_by_activation': False,
              'in_memory_optimizer_absence_proven': False,
              'counter_observation_scope': 'COMMITTED_CHECKPOINT_AND_NATIVE_PROGRESS_NOT_IN_FLIGHT_OPTIMIZER'}
    controller_lease = maintenance = None; started_attempt = False; success = False
    old_configs = {}; new_context = None
    def save():
        h.atomic(receipt, encode(result))
    def pause_after_failure():
        nonlocal maintenance
        try:
            if maintenance is None:
                maintenance = acquire_after_start(STATE / 'owner_maintenance.lock')
            return own_pause(h, window, request, source, result['reason'])
        except Exception as pause_error:
            return {'state': 'PAUSE_NOT_CONFIRMED', 'reason': safe(pause_error), 'foreign_state_preserved': True}
    try:
        controller_lease = acquire(STATE / 'media/controller.lock')
        maintenance = acquire(STATE / 'owner_maintenance.lock')
        sources(); installed_guard_proof(install_context)
        require(not h.owner_stop() and not (STATE / 'OWNER_MAINTENANCE.flag').exists()
                and not (STATE / 'OWNER_MAINTENANCE.flag').is_symlink(), 'OWNER_STOP_OR_MAINTENANCE')
        actions = media.Admission({}, runtime); old_media = actions.configuration(PINS[HANDOFF])
        result['completed_six'] = media.completed_six(actions)
        require(result['completed_six']['acceptance_sha256'] == SIX_ACCEPTANCE
                and result['completed_six']['checkpoint_manifest_sha256'] == SIX_MANIFEST, 'COMPLETED_SIX')
        ctx = window.context(h); result['trainer_before'] = trainer_snapshot(window, h, obs, ctx)
        baseline = counters(obs, ctx['contract']); no_observed_advance(baseline, baseline)
        result['counters_before'] = baseline; result['dispatcher_before'] = controller(h, obs)
        for path, pin in ((GUARD_CONFIG, DISABLED_CONFIG_SHA), (MEDIA_CONFIG, MEDIA_CONFIG_SHA)):
            private(path); old_configs[path] = read(path, 32768)
            require(sha(old_configs[path]) == pin, 'CONFIG_PREIMAGE')
            h.atomic(backup / path.name, old_configs[path])
        require(json.loads(old_configs[GUARD_CONFIG]) == guard.configuration(None, PINS[GUARD], enabled=False)
                and old_media['resume_training_after_media'] is False and old_media['window_admission'] == SIX
                and not GUARD_STATE.exists() and not GUARD_STATE.is_symlink(), 'INACTIVE_CONFIG_REQUIRED')
        result.update(state='SIX_ACCEPTED_GUARD_INSTALLED_START_READY', backup_config_sha256={p.name: sha(v) for p,v in old_configs.items()})
        save(); os.close(maintenance); maintenance = None
        started_attempt = True
        result.update(state='NORMAL_WINDOW_ADVANCE_INVOKED', window_start_attempted=True)
        save()
        # Invoke the unchanged normal entry. Capture its intermediate completion
        # marker so only this wrapper reports the combined action's outcome.
        with contextlib.redirect_stdout(io.StringIO()):
            code = window.main()
        require(code == 0, 'NORMAL_WINDOW_ADVANCE_FAILED')
        new_context, started_receipt, ctx = new_window(window, h, request, source)
        result.update(state='WINDOW_STARTED_GUARD_ACTIVATION_PENDING', training_started=True,
                      window_admission=new_context, new_admission_sha256=sha(ctx['raw']),
                      new_wrapper_sha256=sha(ctx['wrapper']), trainer_after_start=trainer_snapshot(window, h, obs, ctx))
        result['base_stage_observation'] = window.process_chain(h, result['trainer_after_start']['service'].get('pid'))
        save()
        maintenance = acquire_after_start(STATE / 'owner_maintenance.lock')
        sources(); installed_guard_proof(install_context)
        require(not h.owner_stop() and not h.HOLD.exists() and not h.HOLD.is_symlink()
                and not (STATE / 'OWNER_MAINTENANCE.flag').exists()
                and not (STATE / 'OWNER_MAINTENANCE.flag').is_symlink(), 'STOP_AFTER_START')
        observed = counters(obs, ctx['contract']); no_observed_advance(baseline, observed)
        result['counters_before_configuration'] = observed
        new_guard = guard.configuration(new_context, PINS[GUARD], enabled=True)
        new_media = dict(old_media); new_media.update(resume_training_after_media=True, window_admission=new_context)
        result['configuration_plan'] = {GUARD_CONFIG.name: sha(encode(new_guard)), MEDIA_CONFIG.name: sha(encode(new_media))}
        save()
        commit_configurations(h, old_configs, new_guard, new_media)
        require(read(h.ADMISSION, 64000) == ctx['raw'] and read(h.WRAPPER) == ctx['wrapper'], 'ADMISSION_CHANGED')
        actions.configuration(PINS[HANDOFF]); admitted = actions.context()
        require(admitted['mode'] == 'RUNNING_WINDOW1000' and actions.admission == new_context, 'MEDIA_ADMISSION_READBACK')
        config, config_sha = guard.checked_config(new_context, PINS[GUARD]); guard.context_evidence(config)
        result.update(state='CONFIGURATIONS_COMMITTED_GUARD_SAMPLE_PENDING', configuration_committed=True,
                      configuration_committed_at=time.time(), guard_config_sha256=config_sha,
                      handoff_config_sha256=sha(encode(new_media)))
        save(); os.close(maintenance); maintenance = None
        deadline = time.monotonic() + 45
        while True:
            require(not h.owner_stop() and not h.HOLD.exists() and not h.HOLD.is_symlink(), 'STOP_WHILE_WAITING_GUARD')
            require(controller(h, obs) == result['dispatcher_before'], 'DISPATCHER_CHANGED')
            observed = counters(obs, ctx['contract']); no_observed_advance(baseline, observed)
            current_trainer = trainer_snapshot(window, h, obs, ctx)
            require(current_trainer['service']['state'] in ('RUNNING', 'STARTING'), 'TRAINER_EXITED_BEFORE_GUARD')
            if GUARD_STATE.exists() or GUARD_STATE.is_symlink():
                row, raw = document(GUARD_STATE, 65536); private(GUARD_STATE)
                sampled = row.get('sampled_at')
                require(type(sampled) in (int, float) and math.isfinite(sampled)
                        and sampled >= result['configuration_committed_at'], 'GUARD_SAMPLE_PREDATES_CONFIGURATION')
                reason = guard.resume_block_reason(new_context)
                require(reason is None, 'GUARD_NOT_PERMISSIVE')
                current_trainer = trainer_snapshot(window, h, obs, ctx, required=True)
                final = counters(obs, ctx['contract']); no_observed_advance(baseline, final)
                require(controller(h, obs) == result['dispatcher_before'], 'DISPATCHER_CHANGED')
                result.update(state='WINDOW1000_GUARD_AND_MEDIA_HANDBACK_ACTIVE', trainer_after_activation=current_trainer,
                              counters_after_activation=final, no_new_optimizer_updates_observed_before_guard=True,
                              guard_state={'sha256': sha(raw), 'sampled_at': sampled, 'state': row['state'],
                                           'bindings': row['bindings'], 'checkpoint': row['checkpoint'],
                                           'policy_state': row['policy_state']},
                              new_optimizer_updates_verified=False, requested_window_complete=False)
                success = True; break
            require(time.monotonic() < deadline, 'FRESH_GUARD_TIMEOUT')
            time.sleep(.5)
        final_trainer = trainer_snapshot(window, h, obs, ctx, required=True)
        require(final_trainer['process'] == result['trainer_after_activation']['process'], 'TRAINER_CHANGED_AFTER_ACTIVATION')
        result['trainer_after_activation'] = final_trainer
    except Exception as exc:
        success = False
        result.update(state='HOLD_QWEN_GUARDED_WINDOW_ACTIVATION', reason=safe(exc))
        if started_attempt:
            if result['training_started'] is not True:
                result['training_started'] = None
            result['checkpoint_pause'] = pause_after_failure()
    finally:
        try:
            final_service = h.service()
        except Exception as service_error:
            final_service = {'state': 'UNKNOWN', 'reason': safe(service_error)}
        result['trainer_service_after'] = final_service
        if success and (final_service.get('state') != 'RUNNING'
                        or final_service.get('pid') != result['trainer_after_activation']['service']['pid']):
            success = False
            result.update(state='HOLD_QWEN_GUARDED_WINDOW_ACTIVATION', reason='HOLD_QWEN_ACTIVATE_FINAL_TRAINER_EXIT')
            result['checkpoint_pause'] = pause_after_failure()
        if maintenance is not None:
            os.close(maintenance)
        if controller_lease is not None:
            os.close(controller_lease)
        result['finished_at'] = time.time()
        result['configuration_after'] = {}
        for path in (GUARD_CONFIG, MEDIA_CONFIG):
            try:
                result['configuration_after'][path.name] = {'sha256': sha(read(path, 32768))}
            except Exception as config_error:
                result['configuration_after'][path.name] = {'reason': safe(config_error)}
        save()
        raw = read(receipt)
        require(raw == encode(result), 'FINAL_RECEIPT_READBACK')
        emit('qwen_guarded_window_activation', result)
        emit('qwen_guarded_window_activation_context', {'request': request, 'source_sha': source,
             'receipt_sha256': sha(raw), 'state': result['state'], 'window_admission': new_context})
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit('qwen_guarded_window_preflight', {'state': 'HOLD', 'reason': safe(exc)})
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
