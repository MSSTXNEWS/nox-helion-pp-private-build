#!/usr/bin/env python3
"""Install a separate, evidence-preserving execution revision for checkpoint25.

The original training entry, scientific lineage and completed-six certificate
remain immutable. A single existing supervisor slot restores checkpoint25,
evaluates the actual holdout, saves that same update counter, and waits for an
immutable issuer receipt AND a fresh ordinary dispatcher guard before update26.
No manual guard tick, new daemon, model cutover or threshold relaxation occurs.
"""
import base64
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import types
import urllib.request

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SCRIPTS = ROOT / 'scripts'
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
SELF = 'owner_qwen_revision_install.py'
SHARED = 'owner_qwen_execution_revision.py'
STUDENT = 'qwen_student_training_entry_revision.py'
GUARD = 'owner_qwen_training_guard.py'
DISPATCHER = 'nox_dispatcher_t855u.py'
SERVICE = 'nox-train-volta-t866u'
DISPATCHER_SERVICE = 'nox-dispatcher-t855u'
PROXY_SERVICE = 'nox-proxy'
SCHEMA = 'NOX_QWEN_EXECUTION_REVISION_INSTALL_V1'
ORIGIN = {'request': '6908281920', 'source_sha': '35931438c591a9bb5a649e851f155c4313f28562',
          'receipt_sha256': 'fa0ed9dd2088a247b2ccc94ad60f9962c0d502121c12bf00e31436c9cf487662'}
ORIGIN_LINEAGE = '14c92849840ed3ef982a4a443656fdc0f9183ec7967106b42ce8d0719bb25190'
ORIGIN_LINEAGE_FILE = '19345f9992a8a4a0537c9b9f84ffb086164e1c898eb0207c53569469645f3cb0'
ACCEPTANCE = '2076f7050169692e0333747d07abb5c290b429c1b30d56fd55928fc215edfc00'
OLD_ADMISSION = '9116c9ffbca959ba7afe80dbb66c36a356a922b87ecd839469d17413bb450499'
OLD_WRAPPER = '5bef568fd965f17151b252d8b8d25f00c9b67dd756feef9e30c54cd5b419cd96'
OLD_ENTRY = '259ac097f3ceec5be217748667a421ab5c39ebb56b9b2817fd1368d278f99cb0'
ANCHOR = {
    'directory': 'checkpoint-u00000025-a00000025-g01794816279192913655',
    'pointer_sha256': '1676132e4716aedec8308e71069bf53746a9363343bc767d241ded9bd80fe714',
    'manifest_sha256': 'ba101a2c7125e352cfd17319d8ff8b228b6b43ef9490c99788928c4275fc2dbf',
    'student_state_sha256': '1051539e76d29ee0f8a035fa8b6b4e60dd141e19c8ecc8fd5f4d2a872ba85258',
    'successful_total': 25, 'attempted_total': 25, 'skipped_total': 0,
    'evaluated_successful_total': 10, 'verified_files': 10, 'verified_bytes': 519902179,
}
FLAGS = {
    'TRAIN_HOLD.flag': '2e104be136236c5ce7a9a6327904bc8c5c091c959085192e9b6c1c1152417ae4',
    'TRAIN_PAUSE_REQUEST.flag': '013cb1ff2dfc3fd8555b51609bcf7a9abe3aa8dbb7a4cac1a229c52a8b89a94e',
}
OLD_SOURCES = {
    'owner_qwen_training_guard.py': '2a6f6ade1a913bf42bc921d997b83109323adf3227570cf29a0ffc61a7b2614c',
    'owner_training_status.py': '56ac00ee986932524fe61b996b6edde651419dcc0da028d8b6a56f342be58ae8',
    'owner_qwen_media_handoff.py': '312966b352348f0ae0f403cbe84bbfa2e26f89826f285a0a865965650c7931dc',
    'owner_qwen_media_guard.py': 'acd1ec157ba171e979f82b7e058b4a5054a81fae3884ee1cb8ba8fd33c419450',
    'owner_qwen_handback_retry.py': '9711fa34c31a4e1f6633fe20998e693eaa2668c7024ac96de6bae6c9a2ac9055',
    'owner_hermes_hydrate.py': 'd58ffd95fa5c3d572468d08f3ccbf14e6a2021c21c4468e1c69eab859ca0c327',
    DISPATCHER: '75fe4346b28c74dd20ebda135e9382d09e4767a403ffe575035cbd139927ad2b',
}
PROTECTED = {
    'qwen_student_training_entry.py': OLD_ENTRY,
    'owner_qwen_training_contract.py': '7108da4d4949887414f33f5693fe901e3eb5fc63eb97f2b98d1371fed912f50a',
    'owner_qwen_memfd.py': '938335009efe691a9cef7b41daa7c55f3c8d3d8618a10a5eb5db125fd45afa82',
    'owner_qwen_corpus.py': '1509c31789c2c39507d726515ca1c24a5de5545d8c305c7de0ddbba82058b7eb',
    'qwen35_9b_manifest.json': '2275fc88370ca8ba409a791819e13c8ab7d4e38cce4576a13170b05bcb8b839b',
    'owner_qwen_install_entry.py': '864fe6b0e1567931f94d0b0be55651227ee00fd9106abc4c82e09c13601975d7',
    'owner_qwen_window_entry.py': 'fb9b9dd403f7b1e5d94b8192ce7ad63394ba8a6b3988cc298fc90a195aa191a7',
    'owner_qwen_training_observe.py': 'f2dc6c155b682bdeb663bc383f1aa1db70895f815939099690d898262a3d986a',
    'owner_media_runtime.py': 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5',
    'owner_media_training_handoff.py': '36db3c363ffddfc144c6127e1a9407132bbe39d38996233bf3dd64e5b3cb6ec8',
    'owner_media_inbox_fair.py': '590ef7db87d0f0a0769e02223169ff99464aaba7512f9a297288aa1e3b7ab700',
    'owner_subagent_instruction_truth.py': 'daccac22beaa5f76a5fc0dcad780eb1a19e8fbf8df66df1d653656852c0173d9',
    'owner_task_plans.py': '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773',
    'chat_proxy.py': 'a427aa68ed7760380880c5d1c9ddb0714bef367ee5162a20602dbe43b6722d90',
}
CONFIG_PINS = {
    'owner_training_status.json': '1d8b94a953f0a4fe3a7869cf628188a147ad5a4d88724cd9b3e76a16abd781c1',
    'owner_qwen_training_guard.json': 'ae4a37af04152e09b88f07882c2fd2825ae3a56769b611d7c3b8ad5441a8bf2a',
    'owner_qwen_media_handoff.json': 'c3760b6f7d2f4af6546c32b730c457c562692026344a1e948298c72fe3445f0a',
    'owner_media_runtime.json': 'd76d900d6898a7a33a5cacfc1f4fd334e8fa4a5c72160a9b6ea900fa02beb560',
    'owner_hermes_warm.json': '0382db9cfff273d2c8c40deb9f2dc1ee4055683ff4daa590d06cbe5b3477457f',
}
CANDIDATES = {
    SHARED: SHARED,
    STUDENT: STUDENT,
    'owner_qwen_revision_guard.py': GUARD,
    'owner_qwen_revision_status.py': 'owner_training_status.py',
    'owner_qwen_revision_media_handoff.py': 'owner_qwen_media_handoff.py',
    'owner_qwen_revision_media_guard.py': 'owner_qwen_media_guard.py',
    'owner_qwen_revision_handback_retry.py': 'owner_qwen_handback_retry.py',
    'owner_hermes_revision_hydrate.py': 'owner_hermes_hydrate.py',
}
PINS = {
    'owner_qwen_execution_revision.py': '0dbb06d3384b3436165056ccf4e35bff937fda4f85d96ab2a97ab16a6619998e',
    'qwen_student_training_entry_revision.py': '8291638636bb03f701802c634cf8b30d077a5176c33d3658fb5cb1c92d50f235',
    'owner_qwen_revision_guard.py': '6f5aaebaf196c6ec5bd2ad434c5633f457019368568d93b7f71efcc0effcf656',
    'owner_qwen_revision_status.py': 'c643fe595e09036302818da8e780269ab2e1b48451025b33cb9b491a911eb879',
    'owner_qwen_revision_media_handoff.py': 'e8fa87f3e84d90fad90030cff9b8e548280b4d3097bde83ba6cedd9f4bef46ce',
    'owner_qwen_revision_media_guard.py': 'c0feb873174e776285563fdb0290a4b1064402d33c3c05c58d847531690d7723',
    'owner_qwen_revision_handback_retry.py': '70784355b8458d67f5de0a15b2cce4aaf225fa2522fe90b09f359372ee95fc39',
    'owner_hermes_revision_hydrate.py': '65daf1acd5dd937e23b9f960dedb720b8259793729115bab153993a282e735a3',
}
UTILITIES = {
    'owner_download_status_entry.py': 'f17e8f5337f84ea5a3466053e08a8625c31d9b4b31e3963feecec874f145db36',
    'owner_native_repair.py': 'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0',
    'owner_qwen_disk_rearm_entry.py': 'd7017fecab20dab1dc833b2509b14850d4a65151682031143c23e5596c9b8f38',
}
GIB = 1024 ** 3


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_QWEN_REVISION_INSTALL_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()


def plain(path):
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (*path.parents, path)), 'PATH')
    return path


def ident(info):
    return tuple(getattr(info, k) for k in ('st_dev', 'st_ino', 'st_size', 'st_mode', 'st_uid', 'st_gid', 'st_mtime_ns', 'st_ctime_ns'))


def read(path, maximum=2 * 1024 ** 2):
    path = plain(path)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC), 'rb') as f:
        first = os.fstat(f.fileno())
        require(stat.S_ISREG(first.st_mode) and 0 <= first.st_size <= maximum, 'FILE_BOUND')
        raw = f.read(maximum + 1)
        require(len(raw) == first.st_size and ident(first) == ident(os.fstat(f.fileno()))
                == ident(path.stat(follow_symlinks=False)), 'FILE_RACE')
    return raw


def document(path, maximum=2 * 1024 ** 2):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'DUPLICATE_JSON_KEY'); out[key] = value
        return out
    raw = read(path, maximum)
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
    require(isinstance(value, dict), 'JSON_OBJECT')
    return value, raw


def sync_dir(path):
    fd = os.open(plain(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_dir(path):
    path = plain(path)
    if not path.exists():
        path.mkdir(mode=0o700); sync_dir(path.parent)
    s = path.stat(follow_symlinks=False)
    require(stat.S_ISDIR(s.st_mode) and s.st_uid == os.geteuid() and stat.S_IMODE(s.st_mode) == 0o700, 'PRIVATE_DIRECTORY')


def create(path, raw, mode=0o600):
    fd = os.open(plain(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    with os.fdopen(fd, 'wb') as f:
        os.fchmod(f.fileno(), mode); f.write(raw); f.flush(); os.fsync(f.fileno())
    sync_dir(path.parent)
    require(read(path, max(len(raw), 1)) == raw and stat.S_IMODE(path.stat().st_mode) == mode, 'CREATE_READBACK')


def replace(path, before, after, mode=0o600):
    require(read(path, max(len(before), 1)) == before, 'REPLACE_PREIMAGE')
    fd, tmp = tempfile.mkstemp(prefix='.revision-', dir=plain(path.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            os.fchmod(f.fileno(), mode); f.write(after); f.flush(); os.fsync(f.fileno())
        require(read(path, max(len(before), 1)) == before, 'REPLACE_RACE')
        os.replace(tmp, plain(path)); sync_dir(path.parent)
        require(read(path, max(len(after), 1)) == after, 'REPLACE_READBACK')
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def acquire(path, seconds=0):
    deadline = time.monotonic() + seconds
    while True:
        fd = os.open(plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            first = os.fstat(fd)
            require(stat.S_ISREG(first.st_mode) and first.st_uid == os.geteuid(), 'LOCK_OWNER')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            require((first.st_dev, first.st_ino) == (path.stat().st_dev, path.stat().st_ino), 'LOCK_RACE')
            return fd
        except BlockingIOError:
            os.close(fd)
            require(time.monotonic() < deadline, 'LOCK_BUSY')
            time.sleep(.2)
        except BaseException:
            os.close(fd); raise


def module(name, raw):
    value = types.ModuleType('_nox_revision_install_' + name.removesuffix('.py'))
    value.__file__ = str(SCRIPTS / name); sys.modules[value.__name__] = value
    exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    return value


def assets():
    require(set(PINS) == set(CANDIDATES) and all(re.fullmatch('[a-f0-9]{64}', p) for p in PINS.values()), 'UNREVIEWED_BUNDLE')
    result = {}
    for name in (*CANDIDATES, *UTILITIES, SELF):
        value = BUNDLE.get(name)
        require(isinstance(value, str) and len(value) <= 3 * 1024 ** 2, 'BUNDLE_SCOPE')
        raw = base64.b64decode(value, validate=True)
        require(name == SELF or digest(raw) == {**PINS, **UTILITIES}[name], 'BUNDLE_PIN')
        compile(raw, name, 'exec'); result[CANDIDATES.get(name, name)] = raw
    return result


def protected():
    for name, pin in PROTECTED.items():
        require(digest(read(SCRIPTS / name)) == pin, 'ORIGIN_SOURCE_CHANGED')
    require(digest(read(OUTPUT / 'owner_acceptance.json')) == ACCEPTANCE, 'ACCEPTED_SIX_CHANGED')
    require(digest(read(OUTPUT / 'owner_lineage.json')) == ORIGIN_LINEAGE_FILE, 'ORIGIN_LINEAGE_CHANGED')


def global_stop():
    paths = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP', 'state/OWNER_MAINTENANCE.flag')
    require(not any((ROOT / n).exists() or (ROOT / n).is_symlink() for n in paths)
            and not Path('/workspace/NOX_STOP').exists() and not Path('/workspace/NOX_STOP').is_symlink(), 'OWNER_STOP')


def no_flags():
    global_stop()
    require(not any((STATE / n).exists() or (STATE / n).is_symlink() for n in FLAGS), 'NEW_HOLD_OR_PAUSE')


def exact_flags():
    global_stop()
    result = {}
    for name, pin in FLAGS.items():
        raw = read(STATE / name, 4096)
        require(digest(raw) == pin, 'OLD_FLAGS_CHANGED'); result[name] = raw
    return result


def full_checkpoint(ctx, *, expected=None, flags_check=no_flags):
    """Finite complete checkpoint verification, never used by the 5s guard."""
    pointer, pointer_raw = document(OUTPUT / 'latest_checkpoint.json', 16384)
    name = pointer.get('directory', '')
    require(isinstance(name, str) and re.fullmatch('checkpoint-u[0-9]{8}-a[0-9]{8}-g[0-9]{20}', name), 'CHECKPOINT_PATH')
    folder = plain(OUTPUT / name)
    manifest, manifest_raw = document(folder / 'checkpoint_manifest.json', 65536)
    require(digest(manifest_raw) == pointer.get('manifest_sha256'), 'CHECKPOINT_MANIFEST_SHA')
    files = manifest.get('files_sha256')
    require(isinstance(files, dict) and len(files) == 10 and ctx['observer'].REQUIRED <= files.keys()
            and all(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', k) and k != 'checkpoint_manifest.json'
                    and isinstance(v, str) and re.fullmatch('[a-f0-9]{64}', v) for k, v in files.items())
            and set(p.name for p in folder.iterdir()) == set(files) | {'checkpoint_manifest.json'}, 'CHECKPOINT_FILE_SET')
    total = 0; deadline = time.monotonic() + 60; identities = {}
    for filename, pin in sorted(files.items()):
        path = plain(folder / filename); value = hashlib.sha256(); count = 0
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), 'rb') as f:
            first = os.fstat(f.fileno())
            require(stat.S_ISREG(first.st_mode) and first.st_uid == os.geteuid()
                    and not stat.S_IMODE(first.st_mode) & 0o022 and 0 <= first.st_size <= GIB, 'CHECKPOINT_FILE_OWNER')
            while True:
                flags_check(); require(time.monotonic() < deadline, 'CHECKPOINT_DEADLINE')
                block = f.read(1024 ** 2)
                if not block:
                    break
                count += len(block); total += len(block)
                require(total <= GIB, 'CHECKPOINT_BYTE_BOUND'); value.update(block)
            require(count == first.st_size and ident(first) == ident(os.fstat(f.fileno()))
                    == ident(path.stat(follow_symlinks=False)) and value.hexdigest() == pin, 'CHECKPOINT_FULL_SHA')
            identities[filename] = ident(first)
    state, state_raw = document(folder / 'student_state.json')
    lineage, lineage_raw = document(folder / 'lineage.json')
    require(digest(state_raw) == files['student_state.json'] and digest(lineage_raw) == files['lineage.json']
            and lineage == ctx['lineage'] and ctx['contract'].canonical_sha(lineage) == ORIGIN_LINEAGE,
            'CHECKPOINT_SCIENTIFIC_LINEAGE')
    chain = ctx['observer'].update_chain(state, ctx['contract'])
    require(state['update_evidence'][:6] == ctx['certificate']['update_evidence']
            and manifest.get('successful_total') == state['successful_total']
            and manifest.get('attempted_total') == state['attempted_total']
            and manifest.get('holdout_evaluated_successful_total') == state['holdout_evaluated_successful_total']
            and manifest.get('holdout_loss') == state['last_holdout_loss']
            and manifest.get('adapter_tensor_sha256') == chain['adapter_tensor_sha256'], 'CHECKPOINT_CHAIN')
    require(read(OUTPUT / 'latest_checkpoint.json', 16384) == pointer_raw
            and read(folder / 'checkpoint_manifest.json', 65536) == manifest_raw
            and all(ident((folder / name).stat(follow_symlinks=False)) == value for name, value in identities.items()), 'CHECKPOINT_FINAL_RACE')
    proof = {'directory': name, 'pointer_sha256': digest(pointer_raw), 'manifest_sha256': digest(manifest_raw),
             'student_state_sha256': digest(state_raw), 'successful_total': state['successful_total'],
             'attempted_total': state['attempted_total'], 'skipped_total': state['skipped_total'],
             'evaluated_successful_total': state['holdout_evaluated_successful_total'],
             'verified_files': len(files), 'verified_bytes': total, 'full_files_sha256_verified': True}
    if expected is not None:
        require(all(proof.get(k) == v for k, v in expected.items()), 'EXACT_ANCHOR_REQUIRED')
    return proof, manifest, state


def archive_flag(name, raw, area):
    path = STATE / name; destination = area / ('released-' + name)
    require(read(path, 4096) == raw and digest(raw) == FLAGS[name], 'FLAG_PREIMAGE')
    # Link creates an exact, no-clobber recovery inode before unlinking.
    os.link(plain(path), plain(destination), follow_symlinks=False); sync_dir(area)
    require(path.stat().st_ino == destination.stat().st_ino and read(destination, 4096) == raw, 'FLAG_ARCHIVE')
    require(read(path, 4096) == raw, 'FLAG_CHANGED_BEFORE_UNLINK')
    path.unlink(); sync_dir(STATE)


def safe(exc):
    value = str(exc)
    return value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,150}', value) else type(exc).__name__


def emit(value):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_execution_revision', 'data': value},
          ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':')), flush=True)


def patch_dispatcher(raw, guard_sha):
    require(digest(raw) == OLD_SOURCES[DISPATCHER] and re.fullmatch('[a-f0-9]{64}', guard_sha), 'DISPATCHER_PREIMAGE')
    before = ('owner_qwen_training_guard.bind_dispatcher(globals(), ' + repr(OLD_SOURCES[GUARD]) + ')').encode()
    after = ('owner_qwen_training_guard.bind_dispatcher(globals(), ' + repr(guard_sha) + ')').encode()
    require(raw.count(before) == 1, 'DISPATCHER_BINDING_ANCHOR')
    updated = raw.replace(before, after, 1)
    require(updated.replace(after, before, 1) == raw, 'DISPATCHER_CHANGE_SCOPE')
    compile(updated, '<revision-dispatcher>', 'exec')
    return updated


def service_identity(helper, name, script):
    service = helper.service_state(name)
    process = helper.process(service.get('pid')) if service.get('pid') else None
    require(service['state'] == 'RUNNING' and process and process['service'] == name
            and str(SCRIPTS / script) in process['argv'] and process['state'] not in ('Z', 'X'), 'SERVICE_IDENTITY')
    cfg = helper.program_config(name)
    if cfg.get('stopasgroup') == 'true' or cfg.get('killasgroup') == 'true':
        require(all(row['service'] == name for row in helper.process_table().values()
                    if row['pgrp'] == process['pgrp'] and row['state'] not in ('Z', 'X')), 'FOREIGN_PROCESS_GROUP')
    return {k: process[k] for k in ('pid', 'starttime', 'pgrp')}


def queue_idle():
    row, _ = document(STATE / 'dispatcher/state.json', 16 * 1024 ** 2)
    tasks = row.get('tasks')
    require(isinstance(tasks, dict) and len(tasks) <= 20000 and all(isinstance(t, dict) for t in tasks.values()), 'QUEUE_SCHEMA')
    require(not any(t.get('status') == 'running' for t in tasks.values()), 'DISPATCHER_TASK_RUNNING')


def stop_dispatcher(helper, identity):
    queue_idle()
    require(service_identity(helper, DISPATCHER_SERVICE, DISPATCHER) == identity, 'DISPATCHER_IDENTITY_CHANGED')
    helper.command(['supervisorctl', 'stop', DISPATCHER_SERVICE], 35)
    require(helper.service_state(DISPATCHER_SERVICE)['state'] in ('STOPPED', 'EXITED'), 'DISPATCHER_STOP')


def start_dispatcher(helper):
    require(helper.service_state(DISPATCHER_SERVICE)['state'] in ('STOPPED', 'EXITED', 'FATAL'), 'DISPATCHER_START_SCOPE')
    row = helper.command(['supervisorctl', 'start', DISPATCHER_SERVICE], 35)
    require(row[0] == 0, 'DISPATCHER_START')
    return service_identity(helper, DISPATCHER_SERVICE, DISPATCHER)


def migration_policy(old_guard, before, cp):
    p = before.get('policy_state') or {}
    require(before.get('state') == 'INHIBITED' and p.get('inhibit') is True
            and p.get('reason') == 'EVALUATION_STALE' and p.get('latched_at') == 1794816284.2044637
            and p.get('last_successful_updates') == 25 and p.get('last_evaluation_update') == 10
            and p.get('evaluation_age_updates') == 15 and p.get('regression_streak') == 0
            and p.get('observed_distinct_evaluations') == 0
            and p.get('best_holdout_loss') == 1.2653611116111279 and before.get('checkpoint') == cp,
            'EXACT_STALE_EVALUATION_LATCH')
    require(cp['successful_updates'] == cp['attempted_updates'] == 25 and cp['skipped_updates'] == 0
            and cp['evaluated_at_update'] == 10 and cp['manifest_sha256'] == ANCHOR['manifest_sha256']
            and cp['student_state_sha256'] == ANCHOR['student_state_sha256'], 'EXACT_STALE_CHECKPOINT')
    return copy.deepcopy(p)


def resumed_policy(guard, original, checkpoint, ctx, config, free, now):
    require(original['inhibit'] is True and original['reason'] == 'EVALUATION_STALE'
            and original['last_successful_updates'] == 25 and original['last_evaluation_update'] == 10
            and checkpoint['successful_updates'] == checkpoint['evaluated_at_update'] == 25,
            'REAL_SAME_COUNTER_EVALUATION_REQUIRED')
    trial = copy.deepcopy(original)
    trial.update(inhibit=False, reason=None, latched_at=None)
    result = guard.policy_step(trial, checkpoint, free, ctx['lineage']['targets']['parameters'], now,
                               config['policy'], ctx['certificate']['final_holdout_loss'])
    require(result['inhibit'] is False and result['reason'] is None and result['evaluation_age_updates'] == 0
            and result['last_evaluation_update'] == 25
            and result['observed_distinct_evaluations'] == original['observed_distinct_evaluations'] + 1
            and result['best_holdout_loss'] == min(original['best_holdout_loss'], checkpoint['holdout_loss']),
            'FRESH_EVALUATION_NOT_PERMISSIVE')
    return result


def trainer(ctx, *, required=False):
    obs = ctx['observer']; service = obs.service()
    rows = obs.trainers(ctx['argv'], service)
    require(len(rows) <= 1 and all(all(row.get(k) is True for k in
        ('exact_admitted_argv', 'cuda_visible_devices_1', 'supervisor_ancestry_verified')) for row in rows), 'TRAINER_IDENTITY')
    require(not required or service['state'] == 'RUNNING' and len(rows) == 1, 'TRAINER_NOT_RUNNING')
    process = None
    if rows:
        process = {k: rows[0][k] for k in ('pid', 'start_ticks')}
        process['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    return {'service': service, 'process_identity': process}


def owned_pause(ctx, reason):
    require(read(STATE / 'owner_training_admission.json', 64000) == ctx['raw']
            and read(SCRIPTS / 'run_train_volta_t866u.sh') == ctx['wrapper'], 'PAUSE_ADMISSION_CHANGED')
    path = STATE / 'TRAIN_PAUSE_REQUEST.flag'
    token = ('NOX_QWEN_EXECUTION_REVISION_PAUSE request=' + ctx['context']['request'] + ' reason=' + reason + '\n').encode()
    if path.exists() or path.is_symlink():
        return {'state': 'EXISTING_FLAG_PRESERVED', 'service_killed': False}
    create(path, token)
    return {'state': 'CHECKPOINT_PAUSE_REQUESTED', 'sha256': digest(token), 'service_killed': False}


def rollback_preflight(modified, archived, area, flags):
    """Classify every owned write before stopping any healthy service."""
    for path, before, after, _mode in modified:
        current = read(path, max(len(after), len(before or b''), 1)) if path.exists() or path.is_symlink() else None
        require(current == before or current == after, 'ROLLBACK_FOREIGN_FILE')
    for name in archived:
        path = STATE / name; saved = area / ('released-' + name)
        if path.exists() or path.is_symlink():
            require(read(path, 4096) == flags[name], 'ROLLBACK_FOREIGN_FLAG')
        else:
            require(digest(read(saved, 4096)) == FLAGS[name], 'ROLLBACK_FLAG_ARCHIVE')
    return True


def wait_bootstrap(shared, ctx, guard, result, save, maximum=600):
    deadline = time.monotonic() + maximum
    while time.monotonic() < deadline:
        no_flags(); protected()
        seen = trainer(ctx)
        require(seen['service']['state'] in ('STARTING', 'RUNNING'), 'BOOTSTRAP_PROCESS_EXITED')
        pointer, _ = document(OUTPUT / 'latest_checkpoint.json', 16384)
        if pointer.get('manifest_sha256') != ANCHOR['manifest_sha256']:
            fresh, manifest, state = full_checkpoint(ctx)
            proof = shared.bootstrap_evaluation_proof(ctx, manifest, state)
            live = trainer(ctx, required=True)
            require(live['process_identity'] == proof['witness']['process_identity'], 'BOOTSTRAP_PROCESS_CHANGED')
            result.update(state='REAL_EVALUATION_SAME_COUNTER_CHECKPOINT_VERIFIED', fresh_checkpoint=fresh,
                          bootstrap_evaluation=proof, trainer=live)
            save()
            return fresh, manifest, state
        time.sleep(2)
    result.update(state='BOOTSTRAP_LOADING_PENDING', optimizer_permission_issued=False, trainer=trainer(ctx))
    save()
    return None


def activate(shared, ctx, guard, config, original_policy, proof, manifest, state, area):
    """Caller holds maintenance EX; the normal guard must sample after release."""
    no_flags(); protected()
    witness_proof = shared.bootstrap_evaluation_proof(ctx, manifest, state)
    witness = witness_proof['witness']
    live = trainer(ctx, required=True)
    require(live['process_identity'] == witness['process_identity']
            and proof['full_files_sha256_verified'] is True and proof['manifest_sha256'] == witness_proof['manifest_sha256'],
            'ACTIVATION_FULL_PROOF')
    pointer, _ = document(OUTPUT / 'latest_checkpoint.json', 16384)
    require(pointer['manifest_sha256'] == proof['manifest_sha256'], 'ACTIVATION_POINTER_CHANGED')
    config_now, config_sha = guard.checked_config(ctx['context'], digest(read(SCRIPTS / GUARD)))
    require(config_now == config and config['policy'] == guard.DEFAULT_POLICY, 'POLICY_CHANGED')
    before, raw = document(guard.STATUS, 65536)
    require(before.get('bindings') == guard.bindings(config, config_sha, ctx), 'ACTIVATION_GUARD_BINDING')
    original_keys = ('inhibit', 'reason', 'latched_at', 'last_successful_updates', 'last_evaluation_update',
                     'best_holdout_loss', 'regression_streak', 'observed_distinct_evaluations')
    require(all(before['policy_state'].get(k) == original_policy[k] for k in original_keys), 'BOOTSTRAP_QUALITY_HISTORY_CHANGED')
    cp = guard.checkpoint_metadata(ctx)
    decision = resumed_policy(guard, original_policy, cp, ctx, config, guard.disk_free(), time.time())
    issued = copy.deepcopy(before)
    # This issuer transition is deliberately not called a fresh monitor sample.
    issued.update(state='EVALUATION_ACCEPTED_GUARD_SAMPLE_PENDING', policy_state=decision, checkpoint=cp,
                  pause_flag='NOT_REQUESTED', sampled_at=time.time(), execution_bootstrap={
                      'state': 'EVALUATION_ACCEPTED_GUARD_SAMPLE_PENDING', 'optimizer_permission': False,
                      'quality_history_preserved': True})
    guard_raw = guard.encode(issued)
    create(area / 'guard_after_evaluation.json', guard_raw)
    replace(guard.STATUS, raw, guard_raw)
    permit = {'schema': 'NOX_QWEN_EXECUTION_ACTIVATION_V1', 'state': 'FRESH_EVALUATION_ACCEPTED_OPTIMIZER_ADMITTED',
              'execution_binding': shared.execution_binding(ctx),
              'issuer_source_sha256': ctx['execution']['descriptor']['activation_issuer_sha256'],
              'issued_at': time.time(), 'initial_process_identity': live['process_identity'],
              'checkpoint': {k: proof[k] for k in ('directory', 'manifest_sha256', 'student_state_sha256',
                  'verified_files', 'verified_bytes', 'full_files_sha256_verified')},
              'evaluation_witness': witness, 'preserved_guard_policy_sha256': digest(encode(original_policy)),
              'guard_state_sha256': digest(guard_raw), 'previous_flags_archived': True}
    for name, pin in FLAGS.items():
        require(digest(read(area / ('released-' + name), 4096)) == pin, 'ACTIVATION_ARCHIVE_MISSING')
    no_flags(); require(trainer(ctx, required=True) == live, 'ACTIVATION_TRAINER_CHANGED')
    create(area / 'activation.json', encode(permit))
    require(shared.activation_status(ctx)['active'] is True, 'PERMIT_READBACK')
    return permit


def verify_fresh_guard(shared, ctx, guard, config, checkpoint, timeout=45):
    deadline = time.monotonic() + timeout
    while True:
        no_flags(); live = trainer(ctx, required=True)
        row, raw = document(guard.STATUS, 65536)
        cfg, cfg_sha = guard.checked_config(ctx['context'], digest(read(SCRIPTS / GUARD)))
        require(cfg == config and row.get('bindings') == guard.bindings(cfg, cfg_sha, ctx), 'POSTACTIVATION_BINDING')
        sampled = row.get('sampled_at')
        permit = shared.activation_status(ctx)
        if (permit['active'] is True and type(sampled) in (int, float)
                and permit['permit']['issued_at'] <= sampled <= time.time()
                and time.time() - sampled <= 30 and row.get('state') == 'MONITORING'
                and row.get('policy_state', {}).get('inhibit') is False):
            require(live['process_identity'] == permit['initial_process_identity'], 'POSTACTIVATION_TRAINER_CHANGED')
            require(row['checkpoint']['successful_updates'] >= 25
                    and row['checkpoint']['evaluated_at_update'] >= 25, 'POSTACTIVATION_CHECKPOINT')
            return {'sha256': digest(raw), 'sampled_at': sampled, 'state': row['state'],
                    'checkpoint': row['checkpoint'], 'policy_state': row['policy_state'],
                    'bindings': row['bindings'], 'trainer': live}
        require(time.monotonic() < deadline, 'FRESH_ORDINARY_GUARD_TIMEOUT')
        time.sleep(.5)


def finalize_current():
    """Bounded continuation of the SAME admitted process; never starts a slot."""
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'FINALIZE_OWNER_CONTEXT')
    shared_raw = read(SCRIPTS / SHARED)
    require(digest(shared_raw) == PINS[SHARED], 'FINALIZE_VERIFIER_PIN')
    shared = module(SHARED, shared_raw); ctx = shared.current_context()
    require(digest(read(SCRIPTS / SELF)) == ctx['execution']['descriptor']['activation_issuer_sha256'], 'FINALIZE_ISSUER_PIN')
    guard_raw = read(SCRIPTS / GUARD)
    require(digest(guard_raw) == PINS['owner_qwen_revision_guard.py'], 'FINALIZE_GUARD_PIN')
    guard = module(GUARD, guard_raw)
    config, _ = guard.checked_config(ctx['context'], digest(guard_raw)); ctx = guard.context_evidence(config)
    area = ctx['execution']['directory']
    previous, _ = document(area / 'operation_result.json')
    require(previous.get('request') == ctx['context']['request'] and previous.get('source_sha') == ctx['context']['source_sha']
            and previous.get('start_command_issued') is True and previous.get('state') == 'BOOTSTRAP_LOADING_PENDING',
            'FINALIZE_SAME_PROCESS_START_RECEIPT')
    original_policy, raw_policy = document(area / 'guard_policy_before.json')
    require(digest(raw_policy) == previous['original_guard_policy_sha256'], 'FINALIZE_POLICY_ARCHIVE')
    result = {'schema': SCHEMA, 'state': 'FINALIZE_PREFLIGHT', 'request': request, 'source_sha': source,
              'execution_revision': ctx['context'], 'start_command_issued': False,
              'continuation_of_existing_start': True, 'started_at': time.time(), 'optimizer_permission_issued': False}
    receipt_path = area / ('finalize-' + request + '.json'); receipt_raw = None
    require(not receipt_path.exists() and not receipt_path.is_symlink(), 'FINALIZE_REQUEST_REUSED')
    controller = maintenance = None; success = False

    def save():
        nonlocal receipt_raw
        raw = encode(result)
        if receipt_raw is None:
            create(receipt_path, raw)
        else:
            replace(receipt_path, receipt_raw, raw)
        receipt_raw = raw

    try:
        controller = acquire(STATE / 'media/controller.lock', 6)
        no_flags(); protected(); live = trainer(ctx, required=True)
        expected = previous.get('trainer', {}).get('process_identity')
        require(expected is not None and live['process_identity'] == expected, 'FINALIZE_REPLACED_PROCESS')
        require(shared.activation_status(ctx)['active'] is False, 'FINALIZE_ALREADY_ACTIVATED')
        result['trainer'] = live; save()
        ready = wait_bootstrap(shared, ctx, guard, result, save, maximum=450)
        if ready is not None:
            proof, manifest, state = ready
            maintenance = acquire(STATE / 'owner_maintenance.lock', 6)
            permit = activate(shared, ctx, guard, config, original_policy, proof, manifest, state, area)
            result.update(optimizer_permission_issued=True, activation_sha256=digest(encode(permit)))
            save(); os.close(maintenance); maintenance = None
            result.update(state='EXECUTION_REVISION_ACTIVE_FRESH_EVALUATION_VERIFIED',
                          guard=verify_fresh_guard(shared, ctx, guard, config, proof))
            success = True
    except Exception as exc:
        result.update(state='HOLD_QWEN_REVISION_FINALIZE', reason=safe(exc))
        try:
            result['checkpoint_pause'] = owned_pause(ctx, result['reason'])
        except Exception as failure:
            result['checkpoint_pause'] = {'state': 'NOT_CONFIRMED', 'reason': safe(failure)}
    finally:
        for fd in (maintenance, controller):
            if fd is not None:
                os.close(fd)
        result['finished_at'] = time.time(); save()
        result['operation_receipt_sha256'] = digest(receipt_raw); emit(result)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    prepared = assets()
    shared = module(SHARED, prepared[SHARED])
    new_guard = module(GUARD, prepared[GUARD])
    new_media = module('owner_qwen_media_handoff.py', prepared['owner_qwen_media_handoff.py'])
    new_status = module('owner_training_status.py', prepared['owner_training_status.py'])
    new_hydrate = module('owner_hermes_hydrate.py', prepared['owner_hermes_hydrate.py'])
    deploy = module('owner_download_status_entry.py', prepared['owner_download_status_entry.py'])
    helper = module('owner_native_repair.py', prepared['owner_native_repair.py'])
    rearm = module('owner_qwen_disk_rearm_entry.py', prepared['owner_qwen_disk_rearm_entry.py'])
    native_guard = read(SCRIPTS / GUARD)
    native_runtime = read(SCRIPTS / 'owner_media_runtime.py')
    require(digest(native_guard) == OLD_SOURCES[GUARD]
            and digest(native_runtime) == PROTECTED['owner_media_runtime.py'], 'PREFLIGHT_HELPER_PINS')
    old_guard = module(GUARD, native_guard)
    runtime = module('owner_media_runtime.py', native_runtime)
    area_parent = STATE / 'owner_qwen_execution_revisions'
    area = area_parent / request
    require(not area.exists() and not area.is_symlink()
            and not shared.CONFIG.exists() and not shared.CONFIG.is_symlink(), 'REVISION_ALREADY_EXISTS')
    result = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'state': 'PREFLIGHT',
              'started_at': time.time(), 'start_command_issued': False, 'optimizer_permission_issued': False,
              'new_optimizer_updates_verified': False, 'manual_guard_tick_called': False,
              'thresholds_changed': False, 'original_sources_changed': False, 'accepted_six_changed': False,
              'checkpoint_deleted': False, 'main_chat_model_restarted': False}
    controller = maintenance = forge = None
    modified = []; archived = []; dispatcher_stopped = proxy_stopped = False
    prior_modes = {}
    dispatcher_stop_attempted = proxy_stop_attempted = False
    original_dispatcher = original_proxy = model = None
    old_configs = {}; receipt_raw = None; ready_area = False; ctx = None; success = False

    def save():
        nonlocal receipt_raw
        require(ready_area, 'RESULT_AREA_MISSING')
        raw = encode(result); path = area / 'operation_result.json'
        if receipt_raw is None:
            create(path, raw)
        else:
            replace(path, receipt_raw, raw)
        receipt_raw = raw

    def commit(path, before, after, mode=0o600):
        if before == after:
            return
        # Intent recorded before filesystem replacement to permit exact rollback.
        if before is not None:
            prior_modes[path] = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
        modified.append((path, before, after, mode))
        if before is None:
            create(path, after, mode)
        else:
            replace(path, before, after, mode)

    try:
        controller = acquire(STATE / 'media/controller.lock', 6)
        maintenance = acquire(STATE / 'owner_maintenance.lock', 6)
        forge = acquire(STATE / 'forge_training.lock', 6)
        global_stop(); protected()
        old_raw = {name: read(SCRIPTS / name) for name in OLD_SOURCES}
        require(all(digest(old_raw[name]) == pin for name, pin in OLD_SOURCES.items()), 'LIVE_SOURCE_PREIMAGE')
        for name, pin in CONFIG_PINS.items():
            raw = read(ROOT / 'config' / name, 32768)
            require(digest(raw) == pin, 'LIVE_CONFIG_PREIMAGE'); old_configs[name] = raw
        previous_admission = read(shared.ADMISSION, 64000)
        previous_wrapper = read(shared.WRAPPER)
        require(digest(previous_admission) == OLD_ADMISSION and digest(previous_wrapper) == OLD_WRAPPER, 'LIVE_ORIGIN_ADMISSION')
        old_cfg, old_cfg_sha = old_guard.checked_config(ORIGIN, OLD_SOURCES[GUARD])
        require(old_cfg['policy'] == old_guard.DEFAULT_POLICY, 'ORIGINAL_POLICY')
        origin_ctx = old_guard.context_evidence(old_cfg)
        window, origin_helper = origin_ctx['window'] if 'window' in origin_ctx else old_guard.module('owner_qwen_window_entry.py'), old_guard.module('owner_qwen_install_entry.py')
        origin_args = window.arguments(origin_helper, origin_ctx['profile'], ORIGIN['request'], OLD_ADMISSION, 1000, resume=True)
        service = origin_ctx['observer'].service()
        require(service['state'] == 'FATAL' and service['pid'] is None
                and not origin_ctx['observer'].trainers(origin_args, service), 'STOPPED_CHECKPOINT25_REQUIRED')
        before, before_raw = document(old_guard.STATUS, 65536)
        require(before.get('bindings') == old_guard.bindings(old_cfg, old_cfg_sha, origin_ctx)
                and type(before.get('sampled_at')) in (int, float) and 0 <= time.time() - before['sampled_at'] <= 30, 'FRESH_OLD_GUARD')
        flags = exact_flags()
        require(flags['TRAIN_PAUSE_REQUEST.flag'] == old_guard.pause_token(before), 'OLD_GUARD_FLAG_BINDING')
        cp = old_guard.checkpoint_metadata(origin_ctx)
        policy = migration_policy(old_guard, before, cp)
        resources = rearm.resource_check(old_guard, runtime, origin_ctx['observer'])
        heavy = rearm.heavy_stopped(origin_helper)
        full, anchor_manifest, anchor_state = full_checkpoint(origin_ctx, expected=ANCHOR, flags_check=exact_flags)
        model = deploy.model_identity(helper)
        require(model == {'pid': 7637, 'starttime': '149189867', 'pgrp': 7059}, 'CHAT_MODEL_IDENTITY')
        require(deploy.slots_idle(), 'CHAT_ACTIVE')
        queue_idle()
        original_dispatcher = service_identity(helper, DISPATCHER_SERVICE, DISPATCHER)
        original_proxy = deploy.proxy_identity(helper)
        private_dir(area_parent); private_dir(area); ready_area = True
        create(area / 'previous_admission.json', previous_admission)
        create(area / 'previous_wrapper.sh', previous_wrapper)
        create(area / 'previous_entry.py', read(SCRIPTS / 'qwen_student_training_entry.py'))
        create(area / 'guard_before.json', before_raw)
        create(area / 'guard_policy_before.json', encode(policy))
        for name, raw in flags.items():
            create(area / ('before-' + name), raw)
        # Full private restore bytes stay native, never included in emitted data.
        private_dir(area / 'source_before')
        private_dir(area / 'config_before')
        for name, raw in old_raw.items():
            create(area / 'source_before' / name, raw)
        for name, raw in old_configs.items():
            create(area / 'config_before' / name, raw)
        updated_dispatcher = patch_dispatcher(old_raw[DISPATCHER], digest(prepared[GUARD]))
        consumers = {name: digest(prepared[name]) for name in OLD_SOURCES if name != DISPATCHER}
        consumers[DISPATCHER] = digest(updated_dispatcher)
        now = time.time()
        descriptor = {'schema': 'NOX_QWEN_EXECUTION_REVISION_DESCRIPTOR_V1', 'request': request, 'source_sha': source,
                      'created_at': now, 'origin': copy.deepcopy(shared.ORIGIN),
                      'runtime_sources': {name: digest(prepared[name]) for name in (SHARED, STUDENT)},
                      'consumer_sources': consumers, 'activation_issuer_sha256': digest(prepared[SELF]),
                      'anchor': dict(ANCHOR), 'scheduler': {'interval_seconds': 300, 'maximum_update_gap': 10, 'guard_update_gap': 15},
                      'bootstrap': {'expires_at': now + 1800, 'hold_sha256': FLAGS['TRAIN_HOLD.flag'],
                                    'pause_sha256': FLAGS['TRAIN_PAUSE_REQUEST.flag']}}
        shared.descriptor(descriptor)
        descriptor_raw = shared.encode(descriptor)
        create(area / 'descriptor.json', descriptor_raw)
        admission = shared.make_admission(json.loads(previous_admission), descriptor, digest(descriptor_raw), now)
        admission_raw = shared.encode(admission)
        wrapper = shared.make_wrapper(admission, digest(admission_raw))
        sealed = {'schema': 'NOX_QWEN_EXECUTION_REVISION_ADMISSION_V1',
                  'state': 'EXECUTION_REVISION_INSTALLED_EVALUATION_REQUIRED', 'request': request, 'source_sha': source,
                  'descriptor_sha256': digest(descriptor_raw), 'previous_admission_sha256': OLD_ADMISSION,
                  'new_admission_sha256': digest(admission_raw), 'wrapper_sha256': digest(wrapper),
                  'origin_window': dict(ORIGIN), 'origin_lineage_sha256': ORIGIN_LINEAGE,
                  'anchor_checkpoint_manifest_sha256': ANCHOR['manifest_sha256'],
                  'runtime_sources': descriptor['runtime_sources']}
        sealed_raw = shared.encode(sealed); create(area / 'admission_receipt.json', sealed_raw)
        ref = {'request': request, 'source_sha': source, 'receipt_sha256': digest(sealed_raw)}
        execution_cfg = {'schema': 'NOX_QWEN_EXECUTION_REVISION_CONFIG_V1', 'enabled': True,
                         'source_sha256': digest(prepared[SHARED]), 'execution_revision': ref}
        config = new_guard.make_revision_guard_config(json.loads(old_configs['owner_qwen_training_guard.json']), ref, digest(prepared[GUARD]))
        media_config = new_media.make_revision_media_config(json.loads(old_configs['owner_qwen_media_handoff.json']),
                           ref, source_sha256=digest(prepared['owner_qwen_media_handoff.py']))
        hydrate_config = new_hydrate.make_revision_hydrate_manifest(json.loads(old_configs['owner_hermes_warm.json']), ref,
                             source_sha256=digest(prepared['owner_hermes_hydrate.py']), runtime_entry_sha256=digest(prepared[STUDENT]))
        status_config = new_status.make_revision_status_config(json.loads(old_configs['owner_training_status.json']), ref)
        result.update(state='PRIVATE_ORIGIN_AND_INSTALLATION_PLAN_VERIFIED', execution_revision=ref,
                      descriptor_sha256=digest(descriptor_raw), source_pins={**descriptor['runtime_sources'], **consumers},
                      anchor_checkpoint=full, resources_before=resources, stopped_heavy_services=heavy,
                      original_guard_policy_sha256=digest(encode(policy)), active_chat=model)
        save()
        protected(); require(exact_flags() == flags and read(old_guard.STATUS, 65536) == before_raw, 'PRECOMMIT_CHANGED')
        require(read(OUTPUT / 'latest_checkpoint.json', 16384) and digest(read(OUTPUT / 'latest_checkpoint.json', 16384)) == ANCHOR['pointer_sha256'], 'ANCHOR_CHANGED')
        dispatcher_stop_attempted = True; result['dispatcher_stop_attempted'] = True; save()
        stop_dispatcher(helper, original_dispatcher); dispatcher_stopped = True
        proxy_stop_attempted = True; result['proxy_stop_attempted'] = True; save()
        deploy.stop_proxy(helper, original_proxy); proxy_stopped = True
        for name in (*CANDIDATES.values(), SELF):
            path = SCRIPTS / name; old = old_raw.get(name)
            require(old is not None or not path.exists() and not path.is_symlink(), 'NEW_SOURCE_COLLISION')
            commit(path, old, prepared[name], 0o644)
        commit(SCRIPTS / DISPATCHER, old_raw[DISPATCHER], updated_dispatcher, 0o644)
        commit(shared.ADMISSION, previous_admission, admission_raw)
        commit(shared.WRAPPER, previous_wrapper, wrapper, 0o700)
        commit(shared.CONFIG, None, shared.encode(execution_cfg))
        for name, value in (('owner_qwen_training_guard.json', config), ('owner_qwen_media_handoff.json', media_config),
                            ('owner_hermes_warm.json', hydrate_config), ('owner_training_status.json', status_config)):
            commit(ROOT / 'config' / name, old_configs[name], encode(value))
        ctx = shared.current_context(ref)
        ctx = new_guard.context_evidence(config)
        bootstrap_row = copy.deepcopy(before)
        bootstrap_row.update(state='BOOTSTRAP_EVALUATION', sampled_at=time.time(),
            bindings=new_guard.bindings(config, digest(read(new_guard.CONFIG, 32768)), ctx),
            pause_flag='NOT_REQUESTED_BOOTSTRAP', execution_bootstrap={'state': 'BOOTSTRAP_EVALUATION',
                'optimizer_permission': False, 'quality_history_preserved': True})
        commit(new_guard.STATUS, before_raw, new_guard.encode(bootstrap_row))
        for name, raw in flags.items():
            archived.append(name); archive_flag(name, raw, area)
        no_flags(); protected()
        result.update(state='REVISION_INSTALLED_BOOTSTRAP_REQUIRED', previous_flags_archived=True,
                      guard_policy_history_preserved=True, installed_at=time.time())
        save()
        result['dispatcher_start_attempted'] = True; save()
        result['dispatcher_after'] = start_dispatcher(helper); dispatcher_stopped = False
        result['proxy_start_attempted'] = True; save()
        result['proxy_after'] = deploy.start_proxy(helper); proxy_stopped = False
        require(deploy.model_identity(helper) == model, 'CHAT_CHANGED_AFTER_RELOAD')
        # Resource proof still uses the unchanged disk/VRAM/RAM/media policy.
        result['resources_before_start'] = rearm.resource_check(new_guard, runtime, ctx['observer'])
        os.close(forge); forge = None
        no_flags(); shared.current_context(ref)
        require(ctx['observer'].service()['state'] in ('FATAL', 'STOPPED', 'EXITED') and not ctx['observer'].trainers(ctx['argv'], ctx['observer'].service()), 'TRAINER_START_COLLISION')
        result.update(state='SINGLE_TRAINER_START_INTENT', start_intent_recorded=True); save()
        no_flags()
        result['start_command_issued'] = True; save()
        started = helper.command(['supervisorctl', 'start', SERVICE], 25)
        result['start_command_returncode'] = started[0]
        require(started[0] == 0, 'TRAINER_START_COMMAND')
        os.close(maintenance); maintenance = None
        # Controller prevents a media handoff while this finite bootstrap runs.
        result.update(state='SAME_COUNTER_EVALUATION_PENDING'); save()
        ready = wait_bootstrap(shared, ctx, new_guard, result, save)
        if ready is None:
            result['continuation_required'] = True
        else:
            proof, manifest, saved = ready
            maintenance = acquire(STATE / 'owner_maintenance.lock', 6)
            permit = activate(shared, ctx, new_guard, config, policy, proof, manifest, saved, area)
            result.update(state='EVALUATION_ACCEPTED_ORDINARY_GUARD_PENDING', optimizer_permission_issued=True,
                          activation_sha256=digest(encode(permit)))
            save(); os.close(maintenance); maintenance = None
            sample = verify_fresh_guard(shared, ctx, new_guard, config, proof)
            require(deploy.model_identity(helper) == model, 'FINAL_CHAT_IDENTITY')
            protected(); no_flags()
            result.update(state='EXECUTION_REVISION_ACTIVE_FRESH_EVALUATION_VERIFIED', guard=sample,
                          active_chat_after=model, chat_health=helper.health(),
                          same_counter_optimizer_continuity_verified=True, original_checkpoint25_retained=True,
                          accepted_six_preserved=True, ordinary_dispatcher_guard_verified=True)
            success = True
    except Exception as exc:
        result.update(state='HOLD_QWEN_EXECUTION_REVISION_INSTALL', reason=safe(exc))
        if result['start_command_issued']:
            try:
                result['checkpoint_pause'] = owned_pause(ctx, result['reason']) if ctx else {'state': 'NO_BOUND_CONTEXT'}
            except Exception as failure:
                result['checkpoint_pause'] = {'state': 'NOT_CONFIRMED', 'reason': safe(failure)}
        elif modified or dispatcher_stop_attempted or proxy_stop_attempted:
            try:
                require(origin_ctx['observer'].service()['state'] in ('FATAL', 'STOPPED', 'EXITED'), 'ROLLBACK_TRAINER_ACTIVE')
                rollback_preflight(modified, archived, area, flags)
                ds = helper.service_state(DISPATCHER_SERVICE)['state']
                require(ds in ('RUNNING', 'STOPPED', 'EXITED')
                        or ds == 'FATAL' and result.get('dispatcher_start_attempted') is True, 'ROLLBACK_DISPATCHER_UNSETTLED')
                if ds == 'RUNNING':
                    current = service_identity(helper, DISPATCHER_SERVICE, DISPATCHER)
                    require(current == original_dispatcher or current == result.get('dispatcher_after'), 'ROLLBACK_FOREIGN_DISPATCHER')
                    stop_dispatcher(helper, current)
                dispatcher_stopped = True
                proxy_needs_reload = bool(modified or proxy_stop_attempted)
                if proxy_needs_reload:
                    ps = helper.service_state(PROXY_SERVICE)['state']
                    require(ps in ('RUNNING', 'STOPPED', 'EXITED')
                            or ps == 'FATAL' and result.get('proxy_start_attempted') is True, 'ROLLBACK_PROXY_UNSETTLED')
                    if ps == 'RUNNING':
                        current = deploy.proxy_identity(helper)
                        require(current == original_proxy or current == result.get('proxy_after'), 'ROLLBACK_FOREIGN_PROXY')
                        deploy.stop_proxy(helper, current)
                    proxy_stopped = True
                for path, before_value, after_value, mode in reversed(modified):
                    current = read(path, max(len(after_value), len(before_value or b''), 1)) if path.exists() or path.is_symlink() else None
                    if current == before_value:
                        continue
                    require(current == after_value, 'ROLLBACK_FOREIGN_FILE')
                    if before_value is None:
                        path.unlink(); sync_dir(path.parent)
                    else:
                        replace(path, after_value, before_value, prior_modes[path])
                for name in archived:
                    path = STATE / name; saved = area / ('released-' + name)
                    if path.exists() or path.is_symlink():
                        require(read(path, 4096) == flags[name], 'ROLLBACK_FOREIGN_FLAG')
                    else:
                        require(digest(read(saved, 4096)) == FLAGS[name], 'ROLLBACK_FLAG_ARCHIVE')
                        os.link(plain(saved), plain(path), follow_symlinks=False); sync_dir(STATE)
                start_dispatcher(helper); dispatcher_stopped = False
                if proxy_needs_reload:
                    deploy.start_proxy(helper); proxy_stopped = False
                result['rollback'] = {'complete': True, 'native_training_started': False}
            except Exception as failure:
                result['rollback'] = {'complete': False, 'reason': safe(failure)}
    finally:
        for fd in (forge, maintenance, controller):
            if fd is not None:
                os.close(fd)
        result['finished_at'] = time.time()
        if ready_area:
            save(); result['operation_receipt_sha256'] = digest(receipt_raw)
        emit(result)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit({'state': 'HOLD_QWEN_REVISION_PREFLIGHT', 'reason': safe(exc), 'start_command_issued': False})
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
