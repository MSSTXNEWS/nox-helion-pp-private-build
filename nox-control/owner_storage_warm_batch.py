#!/usr/bin/env python3
"""One owner connection: verified builder cold storage, then conditional Hermes.

The unchanged scoped entries own their mutations and rollback.  This driver
never starts training, clears a flag, calls guard.tick, or writes a source.
Hermes is admitted only after durable builder acceptance and a new sample from
the existing dispatcher after the builder's maintenance lease was released.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
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
SCHEMA = 'NOX_OWNER_STORAGE_WARM_BATCH_V1'
TRANSPORT = 'owner_hermes_qa_batch.py'
PINS = {
    TRANSPORT: '84a4d402ae3d86000fc65018660cf906b9952560430ae73a979a11ecaa08ed3d',
    'owner_builder_cold_storage_entry.py': '77199afa4b08feda5e3734255c7899d00194cbda23458792cc26c02657bf9df6',
    'owner_builder_archive_reclaim.py': '804ea161e91c52df57964ca450c3da07a860a0ff428bb95993d5c94ecc4541f6',
    'owner_builder_proc_probe.py': '1743c8587dac72f412400be9059d1fe01ef73a1955af2056ff77a550e53af3ff',
    'owner_builder_drive_public_proof.json': '46888f4bd3dfdf5d89fbe3ff8c24afd07918091e5867c8be663ccb82b76b112e',
    'owner_qwen_disk_rearm_entry.py': 'd7017fecab20dab1dc833b2509b14850d4a65151682031143c23e5596c9b8f38',
    'owner_download_status_entry.py': 'f17e8f5337f84ea5a3466053e08a8625c31d9b4b31e3963feecec874f145db36',
    'owner_native_repair.py': 'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0',
    'owner_training_status_binding.py': '91df0894f52e07ae36f6f05bcb17c846c1b06da88427f45bfe52faf8e50fc1fa',
    'owner_builder_cold_location.py': 'f573a7c5509786139b80768bc009fcbbae89c1a088e3d81361aa0d9eb7dbd965',
    'owner_drive_storage_bridge.py': 'b9e73d96e7ae48dedd7aa1a168d1caa09337d0f58fecca00af527d2347ba8d81',
    'owner_builder_cold_chat_binding.py': 'a9ff754639495d50e0cc67fa2bf49d592f7c16934f8efd63da1815fc9baa0689',
    'owner_hermes_warm_move.py': '42e217bf22f773edcac13e3c9f1c974369ae58a9fca34e3928cab0c8bb911303',
    'owner_hermes_hydrate.py': 'd58ffd95fa5c3d572468d08f3ccbf14e6a2021c21c4468e1c69eab859ca0c327',
    'owner_hermes_ram_preflight.py': '6b1b0393101d485a12c2b0019095f2aa655c931385645ac655b88f916e154a10',
}
BUILDER = {
    'name': 'builder', 'entry': 'owner_builder_cold_storage_entry.py', 'soft_seconds': 225, 'grace_seconds': 105,
    'dependencies': ('owner_builder_archive_reclaim.py', 'owner_builder_proc_probe.py',
        'owner_builder_drive_public_proof.json', 'owner_qwen_disk_rearm_entry.py',
        'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_training_status_binding.py',
        'owner_builder_cold_location.py', 'owner_drive_storage_bridge.py', 'owner_builder_cold_chat_binding.py'),
    'kinds': ('builder_cold_storage', 'builder_cold_storage_context'),
    'final_kind': 'builder_cold_storage', 'schema': 'NOX_BUILDER_COLD_STORAGE_TRANSITION_V1',
    'state': 'BUILDER_COLD_ON_SSD_AND_CONSUMERS_VERIFIED',
}
HERMES = {
    'name': 'hermes', 'entry': 'owner_hermes_warm_move.py', 'soft_seconds': 400, 'grace_seconds': 20,
    'dependencies': ('owner_hermes_hydrate.py', 'owner_hermes_ram_preflight.py',
                     'owner_builder_proc_probe.py', 'owner_qwen_disk_rearm_entry.py'),
    'kinds': ('hermes_warm_move',), 'final_kind': 'hermes_warm_move',
    'schema': 'NOX_HERMES_STORAGE_WARM_MOVE_V1', 'state': 'HERMES_RAM_SHA_ALIASES_AND_PINNED_HYDRATION_VERIFIED',
}
INPUT_LIMIT = 512 * 1024
SOURCE_LIMIT = 256 * 1024
OUTPUT_LIMIT = 500 * 1024
TOTAL_SECONDS = 780
GUARD_WAIT_SECONDS = 20
GUARD_SHA = '2a6f6ade1a913bf42bc921d997b83109323adf3227570cf29a0ffc61a7b2614c'
GUARD_CONFIG_SHA = 'ae4a37af04152e09b88f07882c2fd2825ae3a56769b611d7c3b8ad5441a8bf2a'
WINDOW = {'request': '6908281920', 'source_sha': '35931438c591a9bb5a649e851f155c4313f28562',
          'receipt_sha256': 'fa0ed9dd2088a247b2ccc94ad60f9962c0d502121c12bf00e31436c9cf487662'}
TEN_POINTER = '31acfad8ba1e8dbc7f6abf4f6e95c5bccd57eadcd3c6071d58aaefd9f14b1049'
STOP_PATHS = tuple(ROOT / p for p in ('STOP', 'STOP.flag', 'stop.flag', '.stop',
                   'program/STOP', 'state/STOP', 'state/DRIVE_STOP.flag')) + (Path('/workspace/NOX_STOP'),)
INTERRUPTED = False


class Hold(RuntimeError): pass


def require(ok, code):
    if not ok: raise Hold('HOLD_STORAGE_WARM_BATCH_' + code)


def digest(raw): return hashlib.sha256(raw).hexdigest()
def encoded(value): return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
def safe(exc):
    code = str(exc)
    return code if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', code) else 'HOLD_STORAGE_WARM_BATCH_' + type(exc).__name__.upper()
def stop_present(): return INTERRUPTED or any(p.exists() or p.is_symlink() for p in STOP_PATHS)


def interrupted(*_):
    global INTERRUPTED
    INTERRUPTED = True  # The polling driver gives its own child rollback time.


def document(raw):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_JSON_KEY'); result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
    require(isinstance(value, dict), 'JSON_OBJECT')
    return value


def read_regular(path, maximum=262144, *, private=False):
    require(path.is_absolute() and not any(p.is_symlink() for p in (path, *path.parents)), 'READ_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and before.st_nlink == 1 and not before.st_mode & 0o022 and 0 < before.st_size <= maximum
                and (not private or stat.S_IMODE(before.st_mode) == 0o600), 'READ_SCOPE')
        raw = os.read(fd, maximum + 1)
        identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mode, x.st_uid, x.st_gid,
                              x.st_nlink, x.st_mtime_ns, x.st_ctime_ns)
        require(len(raw) == before.st_size and identity(before) == identity(os.fstat(fd))
                == identity(path.lstat()), 'READ_CHANGED')
        return raw
    finally: os.close(fd)


def sources():
    result = {}
    for name, expected in PINS.items():
        value = BUNDLE.get(name)
        require(isinstance(value, str) and 0 < len(value) <= (SOURCE_LIMIT + 2) // 3 * 4, 'BUNDLE_BOUND')
        raw = base64.b64decode(value, validate=True)
        require(0 < len(raw) <= SOURCE_LIMIT and digest(raw) == expected, 'BUNDLE_PIN')
        if name.endswith('.py'): compile(raw, '<pinned-' + name + '>', 'exec')
        else: document(raw)
        result[name] = raw
    return result


def child_bootstrap(blobs):
    """Re-use reviewed owned-child cleanup; TERM must enter entry rollback."""
    require(digest(blobs[TRANSPORT]) == PINS[TRANSPORT], 'TRANSPORT_PIN')
    module = types.ModuleType('_pinned_storage_transport')
    exec(compile(blobs[TRANSPORT], '<pinned-storage-transport>', 'exec'), module.__dict__)
    source = module.CHILD
    edits = (
        ('class Interrupted(BaseException): pass', 'class Interrupted(RuntimeError): pass'),
        ('    interrupted=True\n    raise Interrupted()',
         "    interrupted=True\n    signal.signal(signal.SIGTERM,signal.SIG_IGN)\n    raise Interrupted('HOLD_STORAGE_WARM_BATCH_INTERRUPTED')"),
        ('raw=sys.stdin.buffer.read(262145)', 'raw=sys.stdin.buffer.read(524289)'),
        ("if len(raw)>262144: raise ValueError('input bound')", "if len(raw)>524288: raise ValueError('input bound')"),
        ('<pinned-hermes-qa-phase>', '<pinned-storage-warm-phase>'),
    )
    for old, new in edits:
        count = 2 if old == '<pinned-hermes-qa-phase>' else 1
        require(source.count(old) == count, 'TRANSPORT_ANCHOR')
        source = source.replace(old, new)
    compile(source, '<storage-child-bootstrap>', 'exec')
    return source


def payload(phase, blobs):
    raw = encoded({'source': base64.b64encode(blobs[phase['entry']]).decode(),
        'bundle': {name: base64.b64encode(blobs[name]).decode() for name in phase['dependencies']}})
    require(len(raw) <= INPUT_LIMIT, 'INPUT_BOUND')
    return raw


def acceptance(records, phase, code, markers, protocol_ok, context):
    finals = [r['data'] for r in records if r['kind'] == phase['final_kind']]
    if not (code == 0 and protocol_ok and markers == [True] and len(finals) == 1): return False
    final = finals[0]
    if not (final.get('schema') == phase['schema'] and final.get('state') == phase['state']
            and all(final.get(k) == context[k] for k in ('request', 'source_sha'))): return False
    if phase['name'] == 'builder':
        contexts = [r['data'] for r in records if r['kind'] == 'builder_cold_storage_context']
        a = final.get('acceptance') or {}
        return (len(records) == 2 and len(contexts) == 1
            and all(contexts[0].get(k) == context[k] for k in ('request', 'source_sha'))
            and bool(re.fullmatch('[a-f0-9]{64}', str(contexts[0].get('receipt_sha256', ''))))
            and type(contexts[0].get('receipt_bytes')) is int and 0 < contexts[0]['receipt_bytes'] <= 262144
            and a.get('anonymous_http') == 401 and a.get('owner_http') == 200
            and a.get('storage_counts') == {'RAM': 2, 'SSD': 1}
            and final.get('ram_duplicate_unlinked_bytes') == 306787336
            and final.get('canonical_permission_after') == 0o644
            and all(final.get(k) is True for k in ('canonical_full_sha256_verified',
                'previous_ram_full_sha256_verified', 'old_ram_receipt_unchanged', 'all_sidecars_preserved'))
            and all(final.get(k) is False for k in ('weights_merged', 'training_flags_modified',
                'new_model_loaded', 'unique_weight_content_removed')) and final.get('training_actions') == 0)
    return (len(records) == 1 and all(final.get(k) is True for k in ('full_ram_sha_verified',
        'checkpoints_and_admission_unchanged', 'own_ssd_payload_descriptors_closed', 'ssd_original_unlinked'))
        and final.get('ram_is_durable_backup') is False and final.get('training_or_service_actions') == 0
        and final.get('checkpoint_or_ledger_changes') == 0
        and bool(re.fullmatch('[a-f0-9]{64}', str(final.get('final_receipt_sha256', '')))))


def parse_output(raw, phase, code, context):
    require(len(raw) <= OUTPUT_LIMIT, 'OUTPUT_BOUND')
    records, markers = [], []; valid = True; control = None; error_class = None
    for line in raw.decode('utf-8', 'strict').splitlines():
        if not line: continue
        if line.startswith('NOX_MAINT_REPAIR='):
            row = document(line.partition('=')[2])
            if set(row) != {'kind', 'data'} or row['kind'] not in phase['kinds'] or not isinstance(row['data'], dict):
                valid = False; continue
            records.append(row)
        elif line in ('NOX_MAINT_REPAIR_COMPLETE=true', 'NOX_MAINT_REPAIR_COMPLETE=false'):
            markers.append(line.endswith('=true'))
        elif line.startswith('NOX_BATCH_CHILD_CONTROL='):
            row = document(line.partition('=')[2]); keys = {'interrupted', 'tracked_children', 'cleanup_targets', 'cleanup_unverified'}
            if (set(row) == keys and row['interrupted'] is True
                    and all(type(row[k]) is int and 0 <= row[k] <= 128 for k in keys - {'interrupted'})):
                control = row
            valid = False
        elif line.startswith('NOX_BATCH_CHILD_FAILURE='):
            name = document(line.partition('=')[2]).get('error_class')
            error_class = name if isinstance(name, str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,79}', name) else 'UNCLASSIFIED'
            valid = False
        else:
            valid = False  # Unknown lines are never relayed.
    return records, {'success': bool(acceptance(records, phase, code, markers, valid, context)),
        'child_exit_code': code, 'completion_markers': markers, 'protocol_valid': valid,
        'child_cleanup': control, 'child_error_class': error_class, 'record_count': len(records)}


def receipt_readback(records, phase, context):
    final = next(r['data'] for r in records if r['kind'] == phase['final_kind'])
    if phase['name'] == 'builder':
        evidence = next(r['data'] for r in records if r['kind'] == 'builder_cold_storage_context')
        path = ROOT / 'state' / ('owner_builder_cold_storage_' + context['request'] + '.json')
        expected = evidence['receipt_sha256']; body = final
    else:
        path = ROOT / 'state/owner_hermes_warm' / context['request'] / 'result.json'
        expected = final['final_receipt_sha256']; body = {k: v for k, v in final.items() if k != 'final_receipt_sha256'}
    raw = read_regular(path, private=True)
    require(digest(raw) == expected and document(raw) == body, 'DURABLE_RECEIPT_READBACK')
    if phase['name'] == 'builder': require(len(raw) == evidence['receipt_bytes'], 'RECEIPT_BYTES')
    return {'durable_receipt_verified': True, 'receipt_sha256': expected, 'receipt_bytes': len(raw)}


def process_identity(pid):
    with open('/proc/' + str(pid) + '/stat', 'rb') as f: raw = f.read(8193)
    require(len(raw) <= 8192, 'CHILD_IDENTITY_BOUND')
    fields = raw[raw.rfind(b')') + 2:].split()
    return tuple(int(fields[i]) for i in (1, 2, 3, 19))


def signal_owned(proc, identity, sig, *, group=False):
    try:
        current = process_identity(proc.pid)
        require(current == identity and current[:3] == (os.getpid(), proc.pid, proc.pid), 'CHILD_IDENTITY_CHANGED')
        if group: os.killpg(proc.pid, sig)
        else: os.kill(proc.pid, sig)
        return True
    except ProcessLookupError: return False
    except FileNotFoundError: return False


def finish_child(proc, identity, grace):
    signal_owned(proc, identity, signal.SIGTERM)
    try: output, _ = proc.communicate(timeout=grace); return output, False
    except subprocess.TimeoutExpired:
        # No poll/wait before this identity check: the unreaped group leader
        # protects against PID reuse even if it exited during rollback.
        signal_owned(proc, identity, signal.SIGKILL, group=True)
        output, _ = proc.communicate(timeout=2)
        return output, True


def run_phase(phase, context, blobs, bootstrap, deadline, output_remaining):
    started = time.monotonic(); proc = None; identity = None; complete = False; records = []
    result = {'phase': phase['name'], 'success': False, 'source_sha256': PINS[phase['entry']],
              'raw_stderr_exported': False, 'temporary_source_files_written': 0,
              'rollback_grace_seconds': phase['grace_seconds']}
    try:
        require(not stop_present(), 'OWNER_STOP')
        raw = payload(phase, blobs)
        require(deadline - time.monotonic() >= phase['soft_seconds'] + phase['grace_seconds'] + 2, 'INSUFFICIENT_PHASE_BUDGET')
        soft_deadline = time.monotonic() + phase['soft_seconds']
        env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
               'NOX_OWNER_REQUEST_ID': context['request'], 'NOX_OWNER_SOURCE_SHA': context['source_sha']}
        proc = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', bootstrap],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, start_new_session=True)
        identity = process_identity(proc.pid)
        data = raw; stopped = None
        while True:
            try:
                output, _ = proc.communicate(input=data, timeout=max(.01, min(1, soft_deadline - time.monotonic())))
                complete = True; break
            except subprocess.TimeoutExpired as exc:
                data = None
                if len(exc.output or b'') > output_remaining: stopped = 'OUTPUT_BOUND'
                elif stop_present(): stopped = 'OWNER_STOP'
                elif time.monotonic() >= soft_deadline: stopped = 'CHILD_TIMEOUT'
                if stopped:
                    output, forced = finish_child(proc, identity, phase['grace_seconds']); complete = True
                    result['forced_termination'] = forced
                    result['rollback_completion_claimed_after_forced_termination'] = False
                    break
        result['released_at'] = time.time()
        require(len(output) <= output_remaining, 'OUTPUT_BOUND')
        records, parsed = parse_output(output, phase, proc.returncode, context); result.update(parsed)
        result['captured_stdout_bytes'] = len(output)
        if stopped: result.update(success=False, reason='HOLD_STORAGE_WARM_BATCH_' + stopped)
        if result['success']: result.update(receipt_readback(records, phase, context))
        result['state'] = 'PHASE_VERIFIED' if result['success'] else 'PHASE_HELD_OR_FAILED'
    except BaseException as exc:
        result.update(success=False, state='PHASE_HELD_OR_FAILED', reason=safe(exc))
    finally:
        if proc is not None and not complete:
            try:
                _, forced = finish_child(proc, identity, phase['grace_seconds'])
                result['forced_termination'] = forced
            except BaseException as exc: result['cleanup_reason'] = safe(exc)
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    return records, result


def load_guard():
    path = ROOT / 'scripts/owner_qwen_training_guard.py'; raw = read_regular(path)
    require(digest(raw) == GUARD_SHA, 'GUARD_SOURCE_PIN')
    module = types.ModuleType('_storage_batch_readonly_guard'); module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def fresh_guard(after, deadline):
    """Read only. The existing dispatcher, not this driver, must write a sample."""
    started = time.monotonic(); until = min(deadline, started + GUARD_WAIT_SECONDS)
    guard = load_guard(); observed = 0
    while time.monotonic() < until:
        require(not stop_present(), 'OWNER_STOP')
        guard._IO_DEADLINE.value = min(until, time.monotonic() + 4)
        try:
            cfg, cfgsha = guard.checked_config(WINDOW, GUARD_SHA)
            require(cfgsha == GUARD_CONFIG_SHA, 'GUARD_CONFIG_CHANGED')
            ctx = guard.context_evidence(cfg)
            row, rowsha = guard.previous_state(guard.bindings(cfg, cfgsha, ctx)); observed += 1
            if row is not None:
                stamp = row.get('sampled_at'); policy = row.get('policy_state') or {}; cp = row.get('checkpoint') or {}
                require(row.get('state') == 'INHIBITED' and policy.get('inhibit') is True
                        and policy.get('reason') == 'DISK_EARLY_MARGIN'
                        and policy.get('last_successful_updates') == 10
                        and cp.get('pointer_sha256') == TEN_POINTER, 'GUARD_PAUSED_CONTEXT_CHANGED')
                require(type(stamp) in (int, float) and math.isfinite(stamp), 'GUARD_TIMESTAMP')
                age = time.time() - stamp
                if stamp > after and 0 <= age <= min(10, cfg['policy']['state_max_age_seconds']):
                    require(cp == guard.checkpoint_metadata(ctx), 'GUARD_CHECKPOINT_CHANGED')
                    require(not stop_present(), 'OWNER_STOP')
                    return {'state': 'NEW_FRESH_PAUSED_GUARD_OBSERVED', 'success': True,
                        'sampled_at': stamp, 'age_seconds': age, 'builder_release_observed_at': after,
                        'state_sha256': rowsha, 'source_sha256': GUARD_SHA, 'config_sha256': cfgsha,
                        'observations': observed, 'guard_tick_called': False, 'training_resume_authorized': False,
                        'elapsed_seconds': round(time.monotonic() - started, 3)}
        finally: guard._IO_DEADLINE.value = None
        time.sleep(min(.5, max(0, until - time.monotonic())))
    raise Hold('WAIT_STORAGE_WARM_BATCH_NEW_GUARD_SAMPLE')


def execute(context):
    started = time.monotonic(); deadline = started + TOTAL_SECONDS
    records, phases = [], []; guard = None; blobs = sources(); bootstrap = child_bootstrap(blobs)
    sizes = {p['name']: len(payload(p, blobs)) for p in (BUILDER, HERMES)}
    rows, first = run_phase(BUILDER, context, blobs, bootstrap, deadline, OUTPUT_LIMIT - 32768)
    records.extend(rows); phases.append(first)
    if first['success'] and not stop_present():
        try: guard = fresh_guard(first['released_at'], deadline)
        except BaseException as exc: guard = {'success': False, 'state': 'GUARD_WAIT_HELD', 'reason': safe(exc), 'guard_tick_called': False}
    if first['success'] and guard and guard['success'] and not stop_present():
        rows, second = run_phase(HERMES, context, blobs, bootstrap, deadline,
                                 OUTPUT_LIMIT - 32768 - first.get('captured_stdout_bytes', 0))
        records.extend(rows); phases.append(second)
    else:
        phases.append({'phase': 'hermes', 'success': False,
            'state': 'SKIPPED_OWNER_STOP' if stop_present() else 'SKIPPED_BUILDER_OR_FRESH_GUARD_NOT_VERIFIED'})
    success = all(p['success'] for p in phases) and bool(guard and guard['success'])
    return records, {'schema': SCHEMA, **context, 'success': success,
        'state': 'BUILDER_COLD_AND_HERMES_WARM_VERIFIED' if success else 'STORAGE_SEQUENCE_PARTIAL_OR_HELD',
        'phases': phases, 'guard': guard, 'source_pins': PINS, 'input_bytes_by_phase': sizes,
        'owner_stop_latched': stop_present(), 'training_rearmed': False, 'trainer_started': False,
        'training_flags_modified_by_driver': False, 'native_guard_tick_called': False,
        'ssd_reclaim_requires_actual_phase_readback': True, 'unique_weight_content_deleted_by_driver': False,
        'raw_stderr_exported': False, 'maximum_seconds': TOTAL_SECONDS,
        'elapsed_seconds': round(time.monotonic() - started, 3)}


def main():
    context = {'request': os.environ.get('NOX_OWNER_REQUEST_ID', ''), 'source_sha': os.environ.get('NOX_OWNER_SOURCE_SHA', '')}
    require(re.fullmatch('[0-9]{1,24}', context['request']) and re.fullmatch('[a-f0-9]{40}', context['source_sha']), 'OWNER_CONTEXT')
    old = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    for sig in old: signal.signal(sig, interrupted)
    try: records, result = execute(context)
    finally:
        for sig, handler in old.items(): signal.signal(sig, handler)
    for row in records: print('NOX_MAINT_REPAIR=' + encoded(row).decode(), flush=True)
    print('NOX_MAINT_REPAIR=' + encoded({'kind': 'storage_warm_batch', 'data': result}).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(result['success']).lower(), flush=True)
    return 0 if result['success'] else 2


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + encoded({'kind': 'storage_warm_batch_hold', 'data': {'reason': safe(exc)}}).decode(), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
