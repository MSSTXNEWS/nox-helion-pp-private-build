#!/usr/bin/env python3
"""One bounded restart of the exact disk-paused Qwen checkpoint10.

This does not reclaim storage or weaken the existing guard. It requires two
additional guard checkpoint budgets above its unchanged early threshold.
Only the known guard state and two exact owned flags can be re-armed; sources,
admission, policy thresholds, checkpoints and memory.peak remain unchanged.
"""
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SCRIPTS = ROOT / 'scripts'
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
SCHEMA = 'NOX_QWEN_EXACT_DISK_REARM_V1'
GUARD_NAME = 'owner_qwen_training_guard.py'
STATUS_NAME = 'owner_training_status.py'
RUNTIME_NAME = 'owner_media_runtime.py'
PINS = {
    GUARD_NAME: '2a6f6ade1a913bf42bc921d997b83109323adf3227570cf29a0ffc61a7b2614c',
    STATUS_NAME: '56ac00ee986932524fe61b996b6edde651419dcc0da028d8b6a56f342be58ae8',
    RUNTIME_NAME: 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5',
    'owner_qwen_media_handoff.py': '312966b352348f0ae0f403cbe84bbfa2e26f89826f285a0a865965650c7931dc',
    'owner_qwen_window_entry.py': 'fb9b9dd403f7b1e5d94b8192ce7ad63394ba8a6b3988cc298fc90a195aa191a7',
    'owner_qwen_install_entry.py': '864fe6b0e1567931f94d0b0be55651227ee00fd9106abc4c82e09c13601975d7',
    'owner_qwen_training_observe.py': 'f2dc6c155b682bdeb663bc383f1aa1db70895f815939099690d898262a3d986a',
}
PROTECTED = {
    'nox_dispatcher_t855u.py': '75fe4346b28c74dd20ebda135e9382d09e4767a403ffe575035cbd139927ad2b',
    'owner_qwen_handback_retry.py': '9711fa34c31a4e1f6633fe20998e693eaa2668c7024ac96de6bae6c9a2ac9055',
    'owner_media_inbox_fair.py': '590ef7db87d0f0a0769e02223169ff99464aaba7512f9a297288aa1e3b7ab700',
    'owner_subagent_instruction_truth.py': 'daccac22beaa5f76a5fc0dcad780eb1a19e8fbf8df66df1d653656852c0173d9',
    'owner_qwen_media_guard.py': 'acd1ec157ba171e979f82b7e058b4a5054a81fae3884ee1cb8ba8fd33c419450',
    'owner_media_training_handoff.py': '36db3c363ffddfc144c6127e1a9407132bbe39d38996233bf3dd64e5b3cb6ec8',
    'owner_task_plans.py': '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773',
}
CONFIG_PINS = {
    'owner_qwen_training_guard.json': 'ae4a37af04152e09b88f07882c2fd2825ae3a56769b611d7c3b8ad5441a8bf2a',
    'owner_qwen_media_handoff.json': 'c3760b6f7d2f4af6546c32b730c457c562692026344a1e948298c72fe3445f0a',
    'owner_media_runtime.json': 'd76d900d6898a7a33a5cacfc1f4fd334e8fa4a5c72160a9b6ea900fa02beb560',
}
CONTEXT = {'request': '6908281920', 'source_sha': '35931438c591a9bb5a649e851f155c4313f28562',
           'receipt_sha256': 'fa0ed9dd2088a247b2ccc94ad60f9962c0d502121c12bf00e31436c9cf487662'}
ADMISSION_SHA = '9116c9ffbca959ba7afe80dbb66c36a356a922b87ecd839469d17413bb450499'
WRAPPER_SHA = '5bef568fd965f17151b252d8b8d25f00c9b67dd756feef9e30c54cd5b419cd96'
SIX_SHA = '2076f7050169692e0333747d07abb5c290b429c1b30d56fd55928fc215edfc00'
TEN_DIRECTORY = 'checkpoint-u00000010-a00000010-g01794810380041616470'
TEN_MANIFEST = '9c3bf7d501771f36e79e48cdb4c8121656724fe9d18c2e3fcedb8485c08bed65'
TEN_POINTER = '31acfad8ba1e8dbc7f6abf4f6e95c5bccd57eadcd3c6071d58aaefd9f14b1049'
TEN_TERMINAL = 'c743b34bb2afe435d6b685d146e662f3269af57c845813e83e732db74f783e56'
TEN_STATE = '3f9b52e6322582526c11a6954518d72e86e452ac7118a50f5d3ec89bca25cb41'
TEN_BYTES = 519_886_929
FLAGS = {
    'TRAIN_PAUSE_REQUEST.flag': '090d92468f4b7a4f418b45b7ef67a6b77e5cf612d919982bb789c65aca1ef683',
    'TRAIN_HOLD.flag': '2e104be136236c5ce7a9a6327904bc8c5c091c959085192e9b6c1c1152417ae4',
}
EARLY = 11_832_524_800
CHECKPOINT_BUDGET = 826_671_104
REARM_FREE = EARLY + 2 * CHECKPOINT_BUDGET
MIN_HEADROOM = 72 * 1024 ** 3
LATCHED_AT = 1794810387.505957
LOSS = 1.2770867235958576
RESET_FIELDS = {'inhibit', 'reason', 'latched_at', 'low_since'}
SAMPLE_FIELDS = {'last_sample_at', 'last_free_bytes', 'floor_already_crossed'}
HEAVY = ('nox-distill-worm-t811u', 'nox-self-improve-t846u', 'nox-self-learning-loop',
         'nox-teacher-serve-t811u', 'nox-offload-t850u', 'nox-downloads-t802u',
         'nox-watch-swap-t845u', 'nox-agent-architect-t859u', 'nox-agent-tuner-t858u')


def require(value, code):
    if not value:
        raise RuntimeError('HOLD_QWEN_DISK_REARM_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')) + '\n').encode()


def safe(exc):
    value = str(exc)
    return value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', value) else type(exc).__name__


def plain(path):
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (*path.parents, path)), 'PATH')
    return path


def ident(info, *, moved=False):
    keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_mode', 'st_uid', 'st_gid')
    return tuple(getattr(info, key) for key in keys + (() if moved else ('st_ctime_ns',)))


def read(path, maximum=2 * 1024 ** 2):
    fd = os.open(plain(path), os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, 'FILE_BOUND')
        raw = stream.read(maximum + 1)
        require(len(raw) == before.st_size and ident(before) == ident(os.fstat(stream.fileno()))
                == ident(path.stat(follow_symlinks=False)), 'FILE_CHANGED')
    return raw


def document(path, maximum=2 * 1024 ** 2):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'JSON_DUPLICATE'); out[key] = value
        return out
    raw = read(path, maximum)
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
    require(isinstance(value, dict), 'JSON_OBJECT'); encode(value)
    return value, raw


def private(path):
    info = plain(path).stat(follow_symlinks=False)
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o600, 'PRIVATE_FILE')
    return info


def sync_dir(path):
    fd = os.open(plain(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def create_private(path, raw):
    fd = os.open(plain(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno()); before = os.fstat(stream.fileno())
    sync_dir(path.parent)
    require(ident(before) == ident(private(path)) and read(path, max(len(raw), 1)) == raw, 'PRIVATE_READBACK')
    return digest(raw)


def publish_private_copy(source, destination, raw):
    info = private(source)
    require(read(source, max(1, len(raw))) == raw, 'PRIVATE_COPY_CHANGED')
    os.link(plain(source), plain(destination), follow_symlinks=False)
    sync_dir(destination.parent)
    require(ident(info, moved=True) == ident(private(source), moved=True)
            == ident(private(destination), moved=True)
            and read(destination, max(1, len(raw))) == raw, 'PRIVATE_PUBLISH_READBACK')


def load(name):
    raw = read(SCRIPTS / name)
    require(digest(raw) == PINS[name], 'NATIVE_MODULE_PIN')
    module = types.ModuleType('_nox_disk_rearm_' + name.removesuffix('.py'))
    module.__file__ = str(SCRIPTS / name); sys.modules[module.__name__] = module
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def sources():
    for name, pin in {**PINS, **PROTECTED}.items():
        require(digest(read(SCRIPTS / name)) == pin, 'PROTECTED_SOURCE_CHANGED')
    for name, pin in CONFIG_PINS.items():
        require(digest(read(ROOT / 'config' / name, 32768)) == pin, 'CONFIG_CHANGED')
    require(digest(read(STATE / 'owner_training_admission.json', 64000)) == ADMISSION_SHA
            and digest(read(SCRIPTS / 'run_train_volta_t866u.sh')) == WRAPPER_SHA, 'CURRENT_WINDOW_CHANGED')
    policy, raw = document(STATE / 'task_boost_mode.json', 16000)
    require(policy.get('enabled') is True and policy.get('mode') == 'TASK_BOOST'
            and policy.get('training_allowed') is True and policy.get('training_gpu') == 1
            and policy.get('training_service') == 'nox-train-volta-t866u', 'TRAINING_POLICY')
    return digest(raw)


def stop_gate(guard):
    require(not guard.owner_stop(), 'GLOBAL_STOP')
    maintenance_flag = STATE / 'OWNER_MAINTENANCE.flag'
    require(not maintenance_flag.exists() and not maintenance_flag.is_symlink(), 'FOREIGN_MAINTENANCE')


def flags(guard, row=None):
    stop_gate(guard)
    result = {}
    for name, pin in FLAGS.items():
        path = STATE / name; info = private(path); raw = read(path, 4096)
        require(digest(raw) == pin and ident(info) == ident(private(path)), 'OWNED_FLAGS_CHANGED')
        result[name] = {'raw': raw, 'identity': ident(info), 'move_identity': ident(info, moved=True)}
    require(result['TRAIN_HOLD.flag']['raw'] ==
            ('OWNER_QWEN_WINDOW_FAILED request=' + CONTEXT['request'] + ' goal=1000\n').encode(), 'WRAPPER_HOLD_SCOPE')
    if row is not None:
        require(result['TRAIN_PAUSE_REQUEST.flag']['raw'] == guard.pause_token(row), 'GUARD_PAUSE_SCOPE')
    return result


def no_flags(guard):
    stop_gate(guard)
    require(not any((STATE / name).exists() or (STATE / name).is_symlink() for name in FLAGS), 'NEW_TRAINING_FLAG')


def acquire(path):
    fd = os.open(plain(path), os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid(), 'LEASE_FILE')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require((info.st_dev, info.st_ino) == (path.stat().st_dev, path.stat().st_ino), 'LEASE_CHANGED')
        return fd
    except BaseException:
        os.close(fd); raise


def stopped(ctx, window, helper):
    obs = ctx['observer']; service = obs.service()
    args = window.arguments(helper, ctx['profile'], CONTEXT['request'], ADMISSION_SHA, 1000, resume=True)
    require(service['state'] == 'FATAL' and service.get('pid') is None
            and not obs.trainers(args, service), 'EXACT_PAUSED_TRAINER_REQUIRED')
    return args


def policy_rearm(guard, previous, cp, free, parameters, now, policy, initial_loss):
    p = previous['policy_state']
    require(previous.get('state') == 'INHIBITED' and p.get('inhibit') is True
            and p.get('reason') == 'DISK_EARLY_MARGIN' and p.get('latched_at') == LATCHED_AT
            and p.get('last_successful_updates') == 10 and p.get('last_evaluation_update') == 8
            and p.get('regression_streak') == 0 and p.get('observed_distinct_evaluations') == 0
            and p.get('best_holdout_loss') == LOSS and p.get('complete') is False
            and p.get('evaluation_age_updates') == 2 and p.get('checkpoint_budget_bytes') == CHECKPOINT_BUDGET
            and p.get('disk_early_threshold_bytes') == EARLY and p.get('disk_floor_bytes') == 10 * 1024 ** 3
            and previous.get('checkpoint') == cp, 'EXACT_DISK_LATCH_REQUIRED')
    require(type(free) is int and free >= REARM_FREE, 'TWO_CHECKPOINT_BUDGETS_REQUIRED')
    trial = copy.deepcopy(p)
    trial.update(inhibit=False, reason=None, latched_at=None, low_since=None)
    checked = guard.policy_step(trial, cp, free, parameters, now, policy, initial_loss)
    require(checked['inhibit'] is False and checked['reason'] is None and checked['latched_at'] is None
            and checked['checkpoint_budget_bytes'] == CHECKPOINT_BUDGET
            and checked['disk_early_threshold_bytes'] == EARLY and checked['complete'] is False
            and all(checked.get(key) == value for key, value in p.items() if key not in RESET_FIELDS | SAMPLE_FIELDS)
            and set(checked) == set(p), 'QUALITY_OR_POLICY_NOT_PERMISSIVE')
    updated = copy.deepcopy(previous)
    updated.update(sampled_at=now, policy_state=checked, state='MONITORING', pause_flag='NOT_REQUESTED')
    require(updated['bindings'] == previous['bindings'] and updated['checkpoint'] == cp, 'REARM_SCOPE')
    return updated


def checkpoint_identities(manifest):
    directory = OUTPUT / TEN_DIRECTORY
    require(set(p.name for p in directory.iterdir()) == set(manifest['files_sha256']) | {'checkpoint_manifest.json'}, 'CHECKPOINT_FILE_SET')
    out = {}
    for name in (*manifest['files_sha256'], 'checkpoint_manifest.json'):
        path = plain(directory / name); info = path.stat(follow_symlinks=False)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and not stat.S_IMODE(info.st_mode) & 0o022, 'CHECKPOINT_FILE_OWNER')
        out[name] = ident(info)
    return out


def checkpoint_anchors():
    for name, pin in (('latest_checkpoint.json', TEN_POINTER), ('owner_last_result.json', TEN_TERMINAL),
                      ('owner_acceptance.json', SIX_SHA)):
        require(digest(read(OUTPUT / name)) == pin, 'CHECKPOINT_ANCHOR_CHANGED')


def full_checkpoint(guard, status, ctx, fixed_flags):
    obs = ctx['observer']; original = obs.read; charged = [0]; deadline = time.monotonic() + 45
    manifest, _ = obs.document(OUTPUT / TEN_DIRECTORY / 'checkpoint_manifest.json', TEN_MANIFEST)
    identities = checkpoint_identities(manifest)
    allowed = {OUTPUT / TEN_DIRECTORY / name for name in (*manifest['files_sha256'], 'checkpoint_manifest.json')}
    allowed |= {OUTPUT / 'owner_last_result.json'}
    def guarded_read(path, maximum=2 * 1024 ** 2, *, expected=None, keep=True, deadline=None):
        path = Path(path); require(path in allowed, 'FULL_HASH_PATH_SCOPE')
        fd = os.open(plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        chunks, h, count = [], hashlib.sha256(), 0
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, 'FULL_HASH_FILE_BOUND')
            while True:
                require(time.monotonic() < hash_deadline and (deadline is None or time.monotonic() < deadline), 'FULL_HASH_DEADLINE')
                require(flags(guard) == fixed_flags, 'FLAGS_CHANGED_DURING_HASH')
                block = stream.read(min(1024 ** 2, maximum + 1 - count))
                if not block:
                    break
                count += len(block); charged[0] += len(block)
                require(count <= maximum and charged[0] <= 1024 ** 3, 'FULL_HASH_BYTE_BOUND')
                h.update(block)
                if keep:
                    chunks.append(block)
            require(count == before.st_size and ident(before) == ident(os.fstat(stream.fileno()))
                    == ident(path.stat(follow_symlinks=False)), 'FULL_HASH_FILE_CHANGED')
        value = h.hexdigest(); require(expected is None or value == expected, 'FULL_HASH_SHA')
        return b''.join(chunks), {'bytes': count, 'sha256': value, 'mtime_ns': before.st_mtime_ns}
    hash_deadline = deadline; obs.read = guarded_read
    try:
        proof, manifest, saved = status.checkpoint(obs, ctx['contract'], ctx['lineage'], TEN_DIRECTORY, TEN_MANIFEST, deadline)
        terminal = status.terminal(obs, ctx['contract'], ctx['lineage'], manifest, saved, deadline)
    finally:
        obs.read = original
    require(proof['successful_optimizer_steps'] == proof['attempted_steps'] == 10 and proof['skipped_steps'] == 0
            and proof['checkpoint_file_count'] == 10 and proof['verified_bytes'] == TEN_BYTES
            and saved['update_evidence'][:6] == ctx['certificate']['update_evidence']
            and terminal['receipt_sha256'] == TEN_TERMINAL and terminal['reload_verified'] is True
            and terminal['state'] == 'EXISTING_TRAINER_HOLD_OR_PAUSE'
            and identities == checkpoint_identities(manifest), 'FULL_CHECKPOINT_CHAIN')
    checkpoint_anchors()
    return {'manifest_sha256': TEN_MANIFEST, 'terminal_sha256': TEN_TERMINAL,
            'successful_updates': 10, 'attempted_updates': 10, 'skipped_updates': 0,
            'full_checkpoint_file_sha256_verified': True, 'verified_files': 10,
            'verified_bytes': proof['verified_bytes'], 'reload_verified': True,
            'acceptance_six_sha256': SIX_SHA, 'total_hash_bytes': charged[0]}, manifest, identities


def heavy_stopped(helper):
    row = helper.command(['supervisorctl', 'status', *HEAVY], 5)
    values = {}
    for line in row.stdout[:16000].splitlines():
        match = re.fullmatch(r'([A-Za-z0-9_-]+)\s+(STOPPED|EXITED|FATAL)\b.*', line)
        require(match and match[1] in HEAVY and match[1] not in values, 'LEGACY_HEAVY_NOT_STOPPED')
        values[match[1]] = match[2]
    require(set(values) == set(HEAVY), 'LEGACY_HEAVY_COVERAGE')
    return values


def resource_check(guard, runtime, obs):
    started = time.monotonic(); stop_gate(guard)
    values = {}
    for name in ('memory.current', 'memory.max'):
        raw = obs.proc_bytes(Path('/sys/fs/cgroup') / name, 128).strip()
        require(raw.isdigit(), 'CGROUP_LIMIT_UNKNOWN'); values[name] = int(raw)
    current, maximum = values['memory.current'], values['memory.max']
    require(0 <= current <= maximum and maximum - current >= MIN_HEADROOM, 'RAM_72_GIB_REQUIRED')
    gpu = runtime.gpu1(); require(gpu['free_mib'] >= 30000, 'GPU1_RESERVE')
    queue = runtime.queue_ids()
    require(set(queue) == {'queue_running', 'queue_pending'} and not any(queue.values()), 'MEDIA_ENGINE_ACTIVE')
    tasks, _ = document(STATE / 'dispatcher/state.json', 16 * 1024 ** 2)
    rows = tasks.get('tasks')
    require(isinstance(rows, dict) and len(rows) <= 20000 and all(isinstance(v, dict) for v in rows.values()), 'DISPATCHER_QUEUE_SCOPE')
    require(not any(v.get('status') in ('pending', 'running') and 'gpu1' in v.get('locks', []) for v in rows.values()), 'GPU1_TASK_PENDING')
    reservation = plain(STATE / 'train_wants_gpu1').stat(follow_symlinks=False)
    require(stat.S_ISREG(reservation.st_mode) and reservation.st_uid == os.geteuid(), 'TRAINING_RESERVATION')
    free = guard.disk_free()
    require(type(free) is int and free >= REARM_FREE, 'TWO_CHECKPOINT_BUDGETS_REQUIRED')
    require(time.monotonic() - started <= 15, 'RESOURCE_SAMPLE_TOO_OLD')
    return {'sampled_at': time.time(), 'cgroup_headroom_bytes': maximum - current,
            'required_cgroup_headroom_bytes': MIN_HEADROOM, 'disk_free_bytes': free,
            'required_disk_free_bytes': REARM_FREE, 'gpu1_free_mib': gpu['free_mib'],
            'comfy_queue_empty': True, 'pending_gpu1_tasks': 0}


def moved_file(window, source, destination, expected, expected_identity):
    require(read(source, max(65536, len(expected))) == expected
            and ident(source.stat(follow_symlinks=False), moved=True) == expected_identity, 'MOVE_PREIMAGE_CHANGED')
    window.rename_noreplace(source, destination)
    # The destination is never overwritten and remains a recovery copy even
    # when a foreign replacement raced the preceding comparison.
    sync_dir(source.parent); sync_dir(destination.parent)
    require(read(destination, max(65536, len(expected))) == expected
            and ident(destination.stat(follow_symlinks=False), moved=True) == expected_identity, 'MOVED_PREIMAGE_CHANGED')


def restore_link(saved, destination):
    # link(2) is no-clobber, and the archived inode is retained for inspection.
    plain(saved.parent); plain(destination.parent)
    try:
        os.link(saved, destination, follow_symlinks=False)
        sync_dir(destination.parent)
        return 'RESTORED_ARCHIVED_INODE'
    except FileExistsError:
        return 'FOREIGN_OR_NEWER_FILE_PRESERVED'


def rollback(window, backup, moved, new_guard_raw):
    result = {'attempted': True, 'flags': {}, 'guard': 'UNCHANGED'}
    status = STATE / 'owner_qwen_training_guard.json'
    if 'guard' in moved:
        original = backup / 'original_guard.json'
        if status.exists() or status.is_symlink():
            try:
                info = private(status)
                raw = read(status, 65536)
                if not original.exists() and not original.is_symlink() and raw == read(backup / 'guard_before.json', 65536):
                    result['guard'] = 'UNCHANGED'
                else:
                    require(raw == new_guard_raw, 'ROLLBACK_GUARD_FOREIGN')
                    moved_file(window, status, backup / 'rearmed_guard_at_rollback.json', new_guard_raw, ident(info, moved=True))
            except Exception as exc:
                result['guard'] = 'FOREIGN_OR_NEWER_FILE_PRESERVED'
                result['guard_reason'] = safe(exc)
        if not status.exists() and not status.is_symlink() and (original.exists() or original.is_symlink()):
            result['guard'] = restore_link(original, status)
    for name in FLAGS:
        archive = backup / ('released-' + name)
        if archive.exists() or archive.is_symlink():
            try:
                result['flags'][name] = restore_link(archive, STATE / name)
            except Exception as exc:
                result['flags'][name] = 'RESTORE_UNVERIFIED'
                result.setdefault('flag_errors', {})[name] = safe(exc)
        elif name in moved:
            try:
                private(STATE / name)
                result['flags'][name] = ('UNCHANGED' if digest(read(STATE / name, 4096)) == FLAGS[name]
                                         else 'FOREIGN_OR_NEWER_FILE_PRESERVED')
            except Exception as exc:
                result['flags'][name] = 'RESTORE_UNVERIFIED'
                result.setdefault('flag_errors', {})[name] = safe(exc)
    result['complete'] = result['guard'] in ('UNCHANGED', 'RESTORED_ARCHIVED_INODE') and all(
        value in ('RESTORED_ARCHIVED_INODE', 'UNCHANGED')
        for value in result['flags'].values())
    return result


def observe_started(ctx, helper, argv):
    deadline = time.monotonic() + 10
    while True:
        service = ctx['observer'].service(); rows = ctx['observer'].trainers(argv, service)
        require(service['state'] in ('RUNNING', 'STARTING'), 'STARTED_TRAINER_TERMINAL')
        if service['state'] == 'RUNNING' and len(rows) == 1 and all(rows[0].get(k) is True for k in
                ('exact_admitted_argv', 'cuda_visible_devices_1', 'supervisor_ancestry_verified')):
            return {'service': service, 'process': {k: rows[0][k] for k in ('pid', 'ppid', 'start_ticks')},
                    'optimizer_restore_verified': False, 'new_optimizer_updates_verified': False,
                    'state': 'RUNNING_RESTAGING_ACCEPTANCE_PENDING'}
        require(time.monotonic() < deadline and len(rows) <= 1, 'STARTED_PROCESS_UNVERIFIED')
        time.sleep(.25)


def issue_start_once(helper, release_forge, final_gate, stop_check, save, result):
    require(not result.get('start_intent_recorded') and not result.get('start_command_issued'), 'START_ALREADY_ATTEMPTED')
    release_forge()
    final_gate()
    # Intent is durable before the sole command, but a STOP between these two
    # operations is still a prestart failure eligible for no-clobber rollback.
    result['start_intent_recorded'] = True
    save()
    stop_check()
    result['start_command_issued'] = True
    return helper.command(['supervisorctl', 'start', helper.SERVICE], 20)


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    guard, status, runtime = load(GUARD_NAME), load(STATUS_NAME), load(RUNTIME_NAME)
    window, helper = guard.module('owner_qwen_window_entry.py'), guard.module('owner_qwen_install_entry.py')
    receipt = STATE / ('owner_qwen_disk_rearm_' + request + '.json')
    backup = ROOT / 'backup/owner_qwen_disk_rearm' / request
    require(not receipt.exists() and not receipt.is_symlink() and not backup.exists() and not backup.is_symlink(), 'REQUEST_ALREADY_USED')
    result = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'window_admission': CONTEXT,
              'state': 'PREFLIGHT', 'started_at': time.time(), 'start_command_issued': False,
              'training_started_verified': False, 'new_optimizer_updates_verified': False,
              'checkpoint_deleted': False, 'sources_changed': False, 'configuration_changed': False,
              'thresholds_changed': False, 'memory_peak_reset': False, 'main_chat_changed': False,
              'requested_window_complete': False, 'required_free_bytes': REARM_FREE}
    maintenance = forge = None; moved = set(); new_guard_raw = None; success = False; prepared = False
    last_receipt_sha = None
    def save():
        nonlocal last_receipt_sha
        if last_receipt_sha is None:
            create_private(receipt, encode(result))
        else:
            # Only this newly reserved receipt is updated; existing requests fail
            # above and no other runtime document is written through this helper.
            require(private(receipt) and digest(read(receipt)) == last_receipt_sha, 'RECEIPT_FOREIGN_EDIT')
            helper.atomic(receipt, encode(result))
            require(private(receipt) and read(receipt) == encode(result), 'RECEIPT_READBACK')
        last_receipt_sha = digest(encode(result))
    try:
        maintenance = acquire(STATE / 'owner_maintenance.lock')
        forge = acquire(STATE / 'forge_training.lock')
        stop_gate(guard); policy_sha = sources()
        cfg, cfg_sha = guard.checked_config(CONTEXT, PINS[GUARD_NAME])
        require(cfg_sha == CONFIG_PINS['owner_qwen_training_guard.json'], 'GUARD_CONFIG')
        ctx = guard.context_evidence(cfg)
        require(ctx['admission_sha256'] == ADMISSION_SHA and ctx['wrapper_sha256'] == WRAPPER_SHA, 'WINDOW_CONTEXT')
        argv = stopped(ctx, window, helper)
        expected_bindings = guard.bindings(cfg, cfg_sha, ctx)
        before, before_sha = guard.previous_state(expected_bindings)
        require(before is not None and guard.finite(before.get('sampled_at'))
                and 0 <= time.time() - before['sampled_at'] <= cfg['policy']['state_max_age_seconds'], 'FRESH_GUARD_REQUIRED')
        before_raw = read(guard.STATUS, 65536); before_info = private(guard.STATUS)
        require(digest(before_raw) == before_sha, 'GUARD_SNAPSHOT_CHANGED')
        fixed_flags = flags(guard, before)
        checkpoint = guard.checkpoint_metadata(ctx)
        require(checkpoint['pointer_sha256'] == TEN_POINTER and checkpoint['manifest_sha256'] == TEN_MANIFEST
                and checkpoint['student_state_sha256'] == TEN_STATE and checkpoint['successful_updates'] == 10
                and checkpoint['attempted_updates'] == 10 and checkpoint['skipped_updates'] == 0
                and checkpoint['evaluated_at_update'] == 8 and checkpoint['holdout_loss'] == LOSS, 'EXACT_CHECKPOINT_TEN')
        initial_resources = resource_check(guard, runtime, ctx['observer'])
        policy_rearm(guard, before, checkpoint, initial_resources['disk_free_bytes'], ctx['lineage']['targets']['parameters'],
                     time.time(), cfg['policy'], ctx['certificate']['final_holdout_loss'])
        heavy = heavy_stopped(helper)
        proof, manifest, checkpoint_before = full_checkpoint(guard, status, ctx, fixed_flags)
        require(sources() == policy_sha and flags(guard, before) == fixed_flags
                and read(guard.STATUS, 65536) == before_raw, 'PREFLIGHT_CHANGED')
        stopped(ctx, window, helper)
        chat_before = helper.model_identity()
        require(chat_before == {'pid': 7637, 'start_ticks': '149189867'}, 'CHAT_IDENTITY_CHANGED')
        # Backup setup creates only new owner-private directories; existing modes
        # are never repaired, broadened, or recursively changed.
        parent = plain(backup.parent)
        if not parent.exists():
            parent.mkdir(mode=0o700); sync_dir(parent.parent)
        require(parent.is_dir() and parent.stat().st_uid == os.geteuid()
                and stat.S_IMODE(parent.stat().st_mode) == 0o700, 'BACKUP_PARENT')
        backup.mkdir(mode=0o700); sync_dir(parent)
        create_private(backup / 'guard_before.json', before_raw)
        for name, value in fixed_flags.items():
            create_private(backup / ('before-' + name), value['raw'])
        restore_map = {'schema': 'NOX_QWEN_DISK_REARM_RESTORE_V1', 'request': request, 'source_sha': source,
                       'window_admission': CONTEXT, 'guard_before_sha256': before_sha,
                       'flag_sha256': FLAGS, 'checkpoint': proof, 'sources': {**PINS, **PROTECTED},
                       'configurations': CONFIG_PINS, 'admission_sha256': ADMISSION_SHA, 'wrapper_sha256': WRAPPER_SHA}
        restore_sha = create_private(backup / 'restore_map.json', encode(restore_map))
        result.update(state='PREPARED_PRIVATE_RESTORE_COPIES_VERIFIED', restore_map_sha256=restore_sha,
                      checkpoint=proof, initial_resources=initial_resources, heavy_services=heavy,
                      guard_before_sha256=before_sha, active_chat_before=chat_before)
        save(); prepared = True
        resources = resource_check(guard, runtime, ctx['observer'])
        updated = policy_rearm(guard, before, checkpoint, resources['disk_free_bytes'], ctx['lineage']['targets']['parameters'],
                               time.time(), cfg['policy'], ctx['certificate']['final_holdout_loss'])
        new_guard_raw = guard.encode(updated)
        create_private(backup / 'rearmed_guard.json', new_guard_raw)
        require(sources() == policy_sha and flags(guard, before) == fixed_flags
                and checkpoint_identities(manifest) == checkpoint_before, 'PREMUTATION_CHANGED')
        checkpoint_anchors()
        stopped(ctx, window, helper)
        # Mark each move intent before rename: even a post-rename fsync failure
        # must preserve and attempt to restore the archived inode.
        moved.add('guard')
        moved_file(window, guard.STATUS, backup / 'original_guard.json', before_raw, ident(before_info, moved=True))
        publish_private_copy(backup / 'rearmed_guard.json', guard.STATUS, new_guard_raw)
        for name in FLAGS:
            stop_gate(guard); moved.add(name)
            moved_file(window, STATE / name, backup / ('released-' + name), fixed_flags[name]['raw'], fixed_flags[name]['move_identity'])
        no_flags(guard)
        require(sources() == policy_sha and checkpoint_identities(manifest) == checkpoint_before
                and read(guard.STATUS, 65536) == new_guard_raw, 'PRESTART_CHANGED')
        checkpoint_anchors()
        stopped(ctx, window, helper)
        require(guard.resume_block_reason(CONTEXT) is None, 'CURRENT_GUARD_NOT_PERMISSIVE')
        final_resources = resource_check(guard, runtime, ctx['observer'])
        require(time.time() - updated['sampled_at'] <= 20, 'REARM_SAMPLE_STALE')
        result.update(state='REARMED_START_INTENT', rearmed_guard_sha256=digest(new_guard_raw),
                      final_resources=final_resources, flags_archived=True,
                      source_and_thresholds_preserved=True, active_chat_after=helper.model_identity())
        require(result['active_chat_after'] == chat_before, 'CHAT_CHANGED_BEFORE_START')
        save()
        def release_forge():
            nonlocal forge
            os.close(forge); forge = None
        def final_gate():
            no_flags(guard)
            require(sources() == policy_sha and guard.resume_block_reason(CONTEXT) is None, 'FINAL_START_GATE')
            checkpoint_anchors()
            stopped(ctx, window, helper)
        started = issue_start_once(helper, release_forge, final_gate, lambda: no_flags(guard), save, result)
        result['start_command_returncode'] = started.returncode
        require(started.returncode == 0, 'START_COMMAND_UNVERIFIED')
        result['trainer_after'] = observe_started(ctx, helper, argv)
        require(helper.model_identity() == chat_before and sources() == policy_sha, 'POSTSTART_IDENTITY_CHANGED')
        no_flags(guard)
        require(ctx['observer'].service() == result['trainer_after']['service'], 'FINAL_TRAINER_CHANGED')
        result.update(state='EXACT_DISK_REARM_STARTED_ACCEPTANCE_PENDING', training_started_verified=True,
                      active_chat_after=chat_before, guard_reset_fields=sorted(RESET_FIELDS))
        success = True
    except Exception as exc:
        result.update(state='HOLD_QWEN_DISK_REARM', reason=safe(exc))
        if moved and not result['start_command_issued']:
            try:
                # Nothing started by us. A foreign trainer prevents even this
                # limited rollback; never race it with flag/state replacement.
                stopped(ctx, window, helper)
                result['rollback'] = rollback(window, backup, moved, new_guard_raw)
            except Exception as failure:
                result['rollback'] = {'complete': False, 'reason': safe(failure)}
        elif result['start_command_issued']:
            result['rollback'] = {'attempted': False, 'reason': 'START_ATTEMPT_REQUIRES_READ_ONLY_OBSERVATION'}
    finally:
        if forge is not None:
            os.close(forge)
        if maintenance is not None:
            os.close(maintenance)
        result['finished_at'] = time.time()
        if prepared:
            save(); result['receipt_sha256'] = digest(read(receipt))
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_disk_rearm', 'data': result},
              sort_keys=True, allow_nan=False, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_disk_rearm_preflight',
              'data': {'state': 'HOLD', 'reason': safe(exc), 'start_command_issued': False}}, separators=(',', ':')), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
