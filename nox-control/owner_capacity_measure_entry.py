#!/usr/bin/env python3
"""Measure short useful NOX inference bursts with one foreground slot reserved.

Loads the reviewed probe in this private process only. No native service, model,
training flag or worker configuration changes. Results distinguish queue workers,
model slots, logical coordination and the external temporary ChatGPT team.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import threading
import time
import types
import urllib.error
import urllib.request

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SCRIPTS = ROOT / 'scripts'
CGROUP = Path('/sys/fs/cgroup')
PROC = Path('/proc')
PROBE_SHA = '36e18d2f37dc8eb39195659e3a1082711bead921eb15150158ef883928a6c4f0'
HYBRID_SHA = '54e1707dd25a7128690e90722ced5885a3fcb347b50126e69e3cac216cf6c557'
ACTION_SHA = 'a72922c610f92c837f1d4fcaa4bc88590e6d472595f71b95cf3f607a52e157da'
NATIVE_SHA = '703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a'
TRAINER = 'nox-train-volta-t866u'
OUTPUT = ROOT / 'lora/qlora_t866u/runs_owner_hybrid'
HEAVY = ('nox-distill-worm-t811u', 'nox-self-improve-t846u', 'nox-self-learning-loop',
         'nox-teacher-serve-t811u', 'nox-offload-t850u', 'nox-downloads-t802u',
         'nox-watch-swap-t845u', 'nox-agent-architect-t859u', 'nox-agent-tuner-t858u')
OPTIONAL_HEAVY = ('nox-teacher-bringup', 'nox-train-worm-t811u')
HEAVY_SCRIPTS = {'distill_worm_t811u.py', 'self_improve_worm_t846u.py', 'self_learning_loop.py',
                 'offload_worm_t850u.py', 'nox_agent_architect_t859u.py', 'nox_agent_tuner_t858u.py',
                 'train_qlora_35b_t866u.py', 'hybrid_training_entry.py', 'owner_hybrid_training_entry.py'}
STOPPED = {'STOPPED', 'EXITED', 'FATAL'}
STOP_RELATIVE = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')
ACTIVE_MEDIA = {'QUEUED', 'YIELDING_TRAINING', 'WAITING_RESOURCES', 'RUNNING', 'SUBMITTING', 'CANCEL_REQUESTED'}
WORKER_IDS = {'nox-agent-%02d' % i for i in range(1, 7)}
REQUESTED = (1, 2, 4, 5)
MAX_SECONDS = 100
_CHECKPOINT_HELPER = None


def fail(code):
    raise RuntimeError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def safe_error(exc):
    text = str(exc)
    return text if re.fullmatch(r'(?:HOLD|WAIT)_[A-Z0-9_]{1,100}', text) else 'HOLD_CAPACITY_' + type(exc).__name__.upper()


def emit(kind, value):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': value}, separators=(',', ':'), allow_nan=False), flush=True)


def checked(path):
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        fail('HOLD_CAPACITY_PATH')
    return path


def read(path, limit=65536):
    path = checked(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            fail('HOLD_CAPACITY_FILE_SCOPE')
        raw = bytearray()
        while True:
            part = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
            if len(raw) > limit:
                fail('HOLD_CAPACITY_FILE_SCOPE')
        after = os.fstat(fd)
        current = path.stat(follow_symlinks=False)
        if any(getattr(before, key) != getattr(after, key) or getattr(before, key) != getattr(current, key)
               for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
            fail('HOLD_CAPACITY_FILE_CHANGED')
        return bytes(raw)
    finally:
        os.close(fd)


def document(path, limit=65536):
    value = json.loads(read(path, limit))
    if not isinstance(value, dict):
        fail('HOLD_CAPACITY_JSON')
    return value


def record(path, value, immutable=False):
    path = checked(path); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = encoded(value) + b'\n'
    if immutable:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    else:
        fd, temporary = tempfile.mkstemp(prefix='.capacity-', dir=path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return digest(raw)


@contextmanager
def measurement_lock():
    path = checked(STATE / 'owner_capacity/measure.lock')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            fail('HOLD_CAPACITY_LOCK_TYPE')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail('WAIT_CAPACITY_PROBE_ALREADY_RUNNING')
        yield
    finally:
        os.close(fd)


def stop_active():
    if any((ROOT / name).exists() or (ROOT / name).is_symlink() for name in STOP_RELATIVE) or Path('/workspace/NOX_STOP').exists():
        return True
    try:
        fd = os.open(STATE / 'owner_maintenance.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True
    finally:
        os.close(fd)


def http_json(port, path, limit=1048576):
    client = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        client.request('GET', path, headers={'Connection': 'close'})
        response = client.getresponse()
        if response.status != 200:
            fail('HOLD_CAPACITY_LOCAL_HTTP_' + str(response.status))
        raw = response.read(limit + 1)
        if len(raw) > limit:
            fail('HOLD_CAPACITY_LOCAL_HTTP_BUDGET')
        return json.loads(raw)
    finally:
        client.close()


def services():
    result = subprocess.run(['supervisorctl', 'status'], capture_output=True, text=True, timeout=5)
    if result.returncode not in (0, 3) or len(result.stdout) > 65536:
        fail('HOLD_CAPACITY_SUPERVISOR')
    values = {}
    for line in result.stdout.splitlines():
        match = re.fullmatch(r'([A-Za-z0-9_.:-]+)\s+([A-Z]+)(?:\s+pid\s+(\d+),[^\n]*)?(?:\s+[^\n]*)?', line)
        if match:
            values[match[1]] = {'state': match[2], 'pid': int(match[3]) if match[3] else None}
    if not values:
        fail('HOLD_CAPACITY_SUPERVISOR_SCHEMA')
    return values


def process_inventory():
    result = {}; count = 0; deadline = time.monotonic() + 5
    for entry in PROC.iterdir():
        if not entry.name.isdigit():
            continue
        count += 1
        if count > 4096 or time.monotonic() > deadline:
            fail('HOLD_CAPACITY_PROCESS_SCAN_BUDGET')
        try:
            fields = read(entry / 'stat', 8192).decode().split(') ', 1)[1].split()
            argv = read(entry / 'cmdline', 65536).decode(errors='replace').strip('\0').split('\0')
            if not argv[0] or fields[0] in ('Z', 'X'):
                continue
            names = {Path(arg).name for arg in argv[1:5] if arg.endswith('.py')}
            options = {arg: argv[index + 1] for index, arg in enumerate(argv[:-1]) if arg in ('--port', '-m', '--model', '-np', '--parallel')}
            result[int(entry.name)] = {'pid': int(entry.name), 'ppid': int(fields[1]), 'start_ticks': int(fields[19]),
                'script_names': names, 'llama': Path(argv[0]).name == 'llama-server', 'port': options.get('--port'),
                'model': options.get('-m', options.get('--model')), 'parallel': options.get('-np', options.get('--parallel')),
                'training_arguments': argv if 'hybrid_training_entry.py' in names else None}
        except FileNotFoundError:
            continue
        except (OSError, ValueError, IndexError):
            fail('HOLD_CAPACITY_PROCESS_IDENTITY_UNREADABLE')
    return result


def public_process(row):
    return {key: row[key] for key in ('pid', 'ppid', 'start_ticks')}


def descends(pid, parent, processes):
    seen = set()
    for _ in range(12):
        if pid == parent:
            return True
        if pid in seen or pid not in processes:
            return False
        seen.add(pid); pid = processes[pid]['ppid']
    return False


def process_started(row):
    match = re.search(r'^btime (\d+)$', read(PROC / 'stat', 65536).decode(), re.M)
    if not match:
        fail('HOLD_CAPACITY_PROCESS_START_CLOCK')
    return int(match[1]) + row['start_ticks'] / os.sysconf('SC_CLK_TCK')


def media_idle(service_states):
    directory = checked(STATE / 'media/jobs')
    if directory.exists():
        count = 0
        for path in directory.iterdir():
            count += 1
            if count > 450:
                fail('HOLD_CAPACITY_MEDIA_SCAN_BUDGET')
            if path.suffix == '.json' and document(path, 262144).get('state') in ACTIVE_MEDIA:
                fail('WAIT_CAPACITY_MEDIA_ACTIVE')
    if service_states.get('nox-media-comfyui', {}).get('state') == 'RUNNING':
        queue = http_json(8188, '/queue')
        if not isinstance(queue, dict) or any(not isinstance(queue.get(key), list) for key in ('queue_running', 'queue_pending')):
            fail('HOLD_CAPACITY_MEDIA_QUEUE')
        if queue['queue_running'] or queue['queue_pending']:
            fail('WAIT_CAPACITY_MEDIA_ACTIVE')


def worker_evidence(service_states, processes):
    config_path = ROOT / 'config/dispatcher_agents_t868u.json'
    config = document(config_path)
    if any(type(config.get(key)) is not int or config[key] != 6 for key in ('workers', 'min_workers', 'max_workers')):
        fail('HOLD_CAPACITY_SIX_WORKER_CONFIGURATION')
    dispatcher = service_states.get('nox-dispatcher-t855u') or {}
    pid = dispatcher.get('pid'); proc = processes.get(pid)
    if dispatcher.get('state') != 'RUNNING' or not proc or 'nox_dispatcher_t855u.py' not in proc['script_names']:
        fail('HOLD_CAPACITY_DISPATCHER_IDENTITY')
    path = ROOT / 'status/agents_t856u.json'; status = document(path, 512 * 1024)
    rows = status.get('workers'); info = path.stat()
    if (not isinstance(rows, list) or len(rows) != 6 or status.get('n') != 6
            or {row.get('id') for row in rows if isinstance(row, dict)} != WORKER_IDS
            or info.st_mtime < max(process_started(proc), time.time() - 90)):
        fail('HOLD_CAPACITY_FRESH_SIX_WORKER_STATUS')
    claims = [(row.get('current_task') or {}).get('id') for row in rows if isinstance(row.get('current_task'), dict)]
    if any(not isinstance(value, str) for value in claims) or len(claims) != len(set(claims)):
        fail('HOLD_CAPACITY_WORKER_CLAIM_COLLISION')
    return {'configured': 6, 'fresh_status_workers': 6, 'worker_ids': sorted(WORKER_IDS), 'busy_count': len(claims),
            'claimed_task_id_hashes': [digest(value.encode()) for value in claims],
            'dispatcher': public_process(proc), 'config_sha256': digest(read(config_path)),
            'scope': 'CONFIGURATION_AND_FRESH_STATUS_NOT_WORKER_THROUGHPUT_MAXIMUM'}


def training_evidence(service_states, processes):
    status = service_states.get(TRAINER) or {}
    candidates = [row for row in processes.values() if 'hybrid_training_entry.py' in row['script_names']]
    if status.get('state') != 'RUNNING' or len(candidates) != 1 or not descends(candidates[0]['pid'], status.get('pid'), processes):
        fail('HOLD_CAPACITY_REAL_TRAINER_PROCESS')
    process = candidates[0]
    if digest(read(SCRIPTS / 'hybrid_training_entry.py', 262144)) != HYBRID_SHA:
        fail('HOLD_CAPACITY_TRAINER_SOURCE')
    if any((STATE / name).exists() or (STATE / name).is_symlink() for name in ('TRAIN_HOLD.flag', 'TRAIN_PAUSE_REQUEST.flag')):
        fail('HOLD_CAPACITY_TRAINING_NOT_ADMITTED')
    admission_path = STATE / 'owner_training_admission.json'; admission = document(admission_path)
    admission_sha = os.environ.get('NOX_CAPACITY_TRAINING_ADMISSION_SHA256', '')
    if (admission.get('schema') != 'NOX_OWNER_TRAINING_ADMISSION_V1'
            or not re.fullmatch(r'\d{6,20}', admission.get('request', ''))
            or not re.fullmatch(r'[a-f0-9]{40}', admission.get('source_sha', ''))
            or not re.fullmatch(r'[a-f0-9]{64}', admission_sha)):
        fail('WAIT_CAPACITY_SEALED_TRAINING_ADMISSION')
    sealed_raw = read(STATE / ('owner_maintenance_' + admission['request'] + '.json'), 2 * 1024 * 1024)
    sealed = json.loads(sealed_raw)
    if (digest(sealed_raw) != admission_sha or sealed.get('schema') != 'NOX_OWNER_TRAINING_RESUME_V1'
            or sealed.get('source_sha') != admission['source_sha'] or sealed.get('request') != admission['request']
            or sealed.get('admission') != admission or sealed.get('state') != 'FIVE_STEPS_VERIFIED_CONTINUATION_STARTED'
            or sealed.get('optimizer_steps_verified') is not True or admission.get('max_steps') != 1000 or admission.get('resume') is not True):
        fail('HOLD_CAPACITY_SEALED_TRAINING_RECEIPT')
    source_pins = admission.get('sources') or {}
    for path in (SCRIPTS / 'hybrid_training_entry.py', SCRIPTS / 'run_train_volta_t866u.sh', STATE / 'train_cpu_max.env'):
        expected = source_pins.get(str(path))
        if not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected) or digest(read(path, 262144)) != expected:
            fail('HOLD_CAPACITY_TRAINING_ADMISSION_SOURCE')
    argv = process['training_arguments']
    options = {arg: argv[index + 1] for index, arg in enumerate(argv[:-1]) if arg in ('--native-sha', '--max-steps', '--planned-steps')}
    if (str(SCRIPTS / 'hybrid_training_entry.py') not in argv or options != {'--native-sha': NATIVE_SHA, '--max-steps': '1000', '--planned-steps': '1000'}
            or '--resume' not in argv):
        fail('HOLD_CAPACITY_TRAINER_ARGUMENT_IDENTITY')
    environment = read(PROC / str(process['pid']) / 'environ', 262144).split(b'\0')
    cuda = [item.partition(b'=')[2] for item in environment if item.startswith(b'CUDA_VISIBLE_DEVICES=')]
    if cuda != [b'1']:
        fail('HOLD_CAPACITY_TRAINER_GPU_IDENTITY')
    del environment
    path = ROOT / 'status/train_volta_t866u.json'; heartbeat = document(path)
    current = time.time(); started = process_started(process)
    if (heartbeat.get('phase') != 'train_owner_hybrid' or heartbeat.get('program') != TRAINER
            or heartbeat.get('output') != str(OUTPUT)
            or type(heartbeat.get('step')) is not int or heartbeat['step'] < 1
            or type(heartbeat.get('successful_optimizer_steps')) is not int or heartbeat['successful_optimizer_steps'] < 1
            or type(heartbeat.get('skipped_optimizer_steps')) is not int or heartbeat['skipped_optimizer_steps'] < 0
            or type(heartbeat.get('loss')) not in (int, float) or not math.isfinite(heartbeat['loss'])
            or type(heartbeat.get('ts')) not in (int, float) or not started <= heartbeat['ts'] <= current + 2
            or current - heartbeat['ts'] > 300 or path.stat().st_mtime < started):
        fail('HOLD_CAPACITY_FRESH_SUCCESSFUL_OPTIMIZER_HEARTBEAT')
    lineage = document(OUTPUT / 'owner_lineage.json', 262144)
    lineage_sha = digest(encoded(lineage)); proof = None
    paths = list(OUTPUT.glob('owner_receipt_step_*.json'))
    if len(paths) > 1024:
        fail('HOLD_CAPACITY_OPTIMIZER_RECEIPT_BUDGET')
    paths = sorted((p for p in paths if re.fullmatch(r'owner_receipt_step_\d+\.json', p.name)),
                   key=lambda p: int(re.search(r'\d+', p.name)[0]), reverse=True)
    if not paths:
        fail('HOLD_CAPACITY_VERIFIED_OPTIMIZER_DELTA_REQUIRED')
    # Reuse the reviewed seven-artifact proof. It hashes each unchanged file only
    # once in this probe process; no checkpoint tensors are imported or executed.
    helper = checkpoint_helper()
    row = document(paths[0], 262144); step = row.get('global_step')
    if type(step) is not int or not 0 < step <= heartbeat['step']:
        fail('HOLD_CAPACITY_CHECKPOINT_STEP')
    names = helper.CHECKPOINT_NAMES
    checkpoint = OUTPUT / ('checkpoint-' + str(step))
    size = 0
    for name in names:
        info = checked(checkpoint / name).stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 2 * 1024 ** 3:
            fail('HOLD_CAPACITY_CHECKPOINT_BYTE_BUDGET')
        size += info.st_size
    if size > 4 * 1024 ** 3:
        fail('HOLD_CAPACITY_CHECKPOINT_BYTE_BUDGET')
    deadline = time.monotonic() + 40
    helper.global_stop = lambda: stop_active() or time.monotonic() >= deadline
    full = helper.checkpoint_proof(paths[0], 0, lineage_sha)
    proof = {'global_step': full['step'], 'receipt_sha256': full['receipt_sha256'],
             'verified_artifacts': len(full['files']), 'full_hashes_verified': True, 'artifact_bytes': size,
             'proof_source_sha256': ACTION_SHA}
    return {'process': public_process(process), 'global_step': heartbeat['step'],
            'successful_optimizer_steps': heartbeat['successful_optimizer_steps'], 'skipped_optimizer_steps': heartbeat['skipped_optimizer_steps'],
            'heartbeat_age_sec': round(current - heartbeat['ts'], 3), 'lineage_sha256': lineage_sha,
            'checkpoint_delta_proof': proof, 'source_sha256': HYBRID_SHA, 'physical_gpu': 1,
            'admission_receipt_sha256': admission_sha, 'admission_pointer_sha256': digest(read(admission_path))}


def checkpoint_helper():
    global _CHECKPOINT_HELPER
    if _CHECKPOINT_HELPER is None:
        blob = BUNDLE.get('owner_plan_native_actions.py')
        raw = base64.b64decode(blob, validate=True) if blob else read(SCRIPTS / 'owner_plan_native_actions.py', 262144)
        if digest(raw) != ACTION_SHA:
            fail('HOLD_CAPACITY_CHECKPOINT_HELPER_PIN')
        module = types.ModuleType('owner_capacity_checkpoint_proofs')
        module.__file__ = str(SCRIPTS / 'owner_plan_native_actions.py')
        exec(compile(raw, module.__file__, 'exec'), module.__dict__)
        _CHECKPOINT_HELPER = module
    return _CHECKPOINT_HELPER


def native_profile(mode):
    if stop_active():
        fail('WAIT_CAPACITY_OWNER_STOP_OR_MAINTENANCE')
    policy_path = STATE / 'task_boost_mode.json'; policy = document(policy_path)
    if policy.get('schema') != 'NOX_OWNER_TASK_BOOST_V1' or policy.get('enabled') is not True or policy.get('mode') != 'TASK_BOOST':
        fail('HOLD_CAPACITY_OPERATIONAL_POLICY_UNVERIFIED')
    status = services(); processes = process_inventory()
    for name in HEAVY:
        if status.get(name, {}).get('state') not in STOPPED:
            fail('HOLD_CAPACITY_HEAVY_SERVICE_ACTIVE_OR_UNKNOWN')
    if any(status[name]['state'] not in STOPPED for name in OPTIONAL_HEAVY if name in status):
        fail('HOLD_CAPACITY_HEAVY_SERVICE_ACTIVE_OR_UNKNOWN')
    models = [row for row in processes.values() if row['llama']]
    if any(row['port'] not in ('8081', '8082') for row in models):
        fail('HOLD_CAPACITY_OTHER_MODEL_PROCESS')
    active = [row for row in models if row['port'] == '8081']
    if len(active) != 1 or active[0]['model'] != str(ROOT / 'models/current.gguf') or active[0]['parallel'] != '6':
        fail('HOLD_CAPACITY_SIX_SLOT_MODEL_PROCESS')
    allowed_training = {'hybrid_training_entry.py'} if mode == 'NORMAL' else set()
    if any(row['script_names'] & (HEAVY_SCRIPTS - allowed_training) for row in processes.values()):
        fail('HOLD_CAPACITY_ORPHAN_HEAVY_PROCESS')
    media_idle(status)
    worker = worker_evidence(status, processes)
    if mode == 'TASK_BOOST':
        if policy.get('training_allowed') is not False or status.get(TRAINER, {}).get('state') not in STOPPED:
            fail('HOLD_CAPACITY_BOOST_TRAINER_NOT_PAUSED')
        hold = read(STATE / 'TRAIN_HOLD.flag', 4096)
        if not hold.strip():
            fail('HOLD_CAPACITY_TRAINING_HOLD_UNVERIFIED')
        training = {'state': status[TRAINER]['state'], 'hold_sha256': digest(hold), 'optimizer_active': False}
    else:
        if policy.get('training_allowed') is not True or policy.get('training_service') != TRAINER:
            fail('HOLD_CAPACITY_NORMAL_TRAINING_PERMISSION')
        training = training_evidence(status, processes)
    source_pins = {name: digest(read(SCRIPTS / name, 262144)) for name in (
        'nox_dispatcher_t855u.py', 'owner_task_lifecycle.py', 'owner_event_outbox.py')}
    return {'requested_mode': mode, 'verified': True, 'policy_mode': 'TASK_BOOST',
            'training_allowed': policy['training_allowed'], 'policy_sha256': digest(read(policy_path)),
            'workers': worker, 'model': public_process(active[0]), 'training': training, 'source_pins': source_pins,
            'heavy_services_paused': list(HEAVY), 'media_idle': True,
            'media_engine_state': status.get('nox-media-comfyui', {}).get('state', 'NOT_OBSERVED'),
            'additional_duties': {name: status.get(name, {'state': 'NOT_OBSERVED'}) for name in ('nox-agent-integrator-t859u', 'nox-autoscale-t877u')},
            'scope': 'OBSERVED_TRAINING_AND_DUTY_PROFILE_LEGACY_HEAVY_WRITERS_REMAIN_PAUSED'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fail('HOLD_CAPACITY_HTTP_REDIRECT')


def load_probe():
    raw = base64.b64decode(BUNDLE.get('owner_capacity_probe.py', ''), validate=True)
    if digest(raw) != PROBE_SHA:
        fail('HOLD_CAPACITY_PROBE_BUNDLE_PIN')
    module = types.ModuleType('owner_capacity_probe_bounded')
    module.__file__ = str(SCRIPTS / 'owner_capacity_probe.py')
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    module.urllib = types.SimpleNamespace(request=types.SimpleNamespace(Request=urllib.request.Request, urlopen=opener.open), error=urllib.error)
    module.stop_active = stop_active
    infer = module.infer
    def private_infer(*args, **kwargs):
        row = infer(*args, **kwargs)
        response = row.pop('public_fixture_response', None)
        if response is not None:
            row.update(withheld_response_sample_sha256=digest(response.encode()), response_sample_characters=len(response), raw_response_exported=False)
        return row
    module.infer = private_infer
    return module


def monitor_media(probe, profile):
    """The main burst monitor cancels this probe if owner media work arrives."""
    original_resources, original_gate = probe.resources, probe.resource_gate
    observed = {'until': 0.0, 'reason': None}
    states = {'nox-media-comfyui': {'state': profile['media_engine_state']}}
    def resources():
        value = original_resources()
        if time.monotonic() >= observed['until']:
            observed['until'] = time.monotonic() + 1
            try:
                media_idle(states)
            except Exception as exc:
                observed['reason'] = safe_error(exc)
        value['owner_media_gate'] = observed['reason']
        return value
    def gate(current, baseline=None):
        original_gate(current, baseline)
        if current.get('owner_media_gate'):
            raise probe.Hold('OWNER_MEDIA_ARRIVED_OR_UNVERIFIED')
    probe.resources, probe.resource_gate = resources, gate


def hardware_gate(gpu, mode):
    rows = gpu.get('gpus')
    if (gpu.get('query_rc') != 0 or not isinstance(rows, list) or len(rows) != 2
            or {row.get('index') for row in rows} != {0, 1}
            or any(type(row.get('total_mib')) is not int or not 31000 <= row['total_mib'] <= 33000 for row in rows)):
        fail('HOLD_CAPACITY_TWO_V100_MEMORY_TELEMETRY')
    if mode == 'TASK_BOOST' and next(row for row in rows if row['index'] == 1)['free_mib'] < 30000:
        fail('WAIT_CAPACITY_GPU1_NOT_RELEASED')


def comparison(before, after, mode):
    stable = (before['model'] == after['model'] and before['workers']['dispatcher'] == after['workers']['dispatcher']
              and before['workers']['config_sha256'] == after['workers']['config_sha256']
              and before['policy_sha256'] == after['policy_sha256'] and before['source_pins'] == after['source_pins'])
    if mode == 'TASK_BOOST':
        stable = stable and before['training'] == after['training']
        return {'profile_stable': stable, 'optimizer_advanced': False}
    first, last = before['training'], after['training']
    same_run = (first['process'] == last['process'] and first['lineage_sha256'] == last['lineage_sha256']
                and first['admission_receipt_sha256'] == last['admission_receipt_sha256']
                and first['admission_pointer_sha256'] == last['admission_pointer_sha256'])
    advanced = (same_run and last['global_step'] > first['global_step']
                and last['successful_optimizer_steps'] > first['successful_optimizer_steps'])
    return {'profile_stable': stable and same_run, 'optimizer_advanced': advanced,
            'optimizer_step_delta': last['successful_optimizer_steps'] - first['successful_optimizer_steps'] if same_run else None,
            'skipped_optimizer_step_delta': last['skipped_optimizer_steps'] - first['skipped_optimizer_steps'] if same_run else None}


def summarize(probe, rows, mode_verified):
    partial_usable = bool(mode_verified and rows)
    sweep_complete = ([row['concurrency'] for row in rows] == list(REQUESTED)
                      and all(row['state'] in ('PASSED', 'QUALITY_FAILED') and not row.get('hold_reason') for row in rows))
    mode_verified = bool(mode_verified and sweep_complete)
    quality = probe.recommend(rows, 3000, 12000)
    transport = [row for row in rows if row['state'] in ('PASSED', 'QUALITY_FAILED')
                 and row.get('native_streams_completed') == row.get('samples') and not row.get('hold_reason')
                 and row.get('p95_ttft_ms') is not None and row['p95_ttft_ms'] <= 3000
                 and row.get('p95_total_ms') is not None and row['p95_total_ms'] <= 12000]
    return {'quality_gated': quality, 'largest_latency_passing_transport_concurrency': max((row['concurrency'] for row in transport), default=None),
            'tested_concurrency': [row['concurrency'] for row in rows],
            'sweep_complete': sweep_complete, 'partial_case_evidence_usable': partial_usable,
            'quality_gate_passed': bool(quality.get('recommended_concurrency')), 'mode_measurement_valid': mode_verified,
            'recommended_background_inferences': quality.get('recommended_concurrency') if mode_verified else None,
            'global_maximum_proven': False, 'sustained_capacity_proven': False,
            'scope': 'BEST_AND_LARGEST_PASSING_TESTED_CONCURRENCIES_ON_SHORT_PUBLIC_FIXTURES'}


def save_modes(receipt_path, receipt_sha, result):
    path = STATE / 'owner_capacity/modes.json'
    value = document(path, 262144) if path.exists() else {
        'schema': 'NOX_OWNER_EXECUTOR_CAPACITY_MODES_V1',
        'modes': {
            'TASK_BOOST': {'definition': 'Owner tasks with training and heavy legacy improvement services paused; core duties remain.', 'state': 'UNMEASURED'},
            'NORMAL': {'definition': 'The admitted optimizer advances concurrently with owner work and core duties; legacy heavy writers remain paused.', 'state': 'AWAITING_RUNNING_OPTIMIZER_MEASUREMENT'},
        },
    }
    if value.get('schema') != 'NOX_OWNER_EXECUTOR_CAPACITY_MODES_V1' or set(value.get('modes', {})) != {'TASK_BOOST', 'NORMAL'}:
        fail('HOLD_CAPACITY_MODE_RECORD_SCHEMA')
    mode = value['modes'][result['requested_mode']]
    proof = {'receipt_path': str(receipt_path), 'receipt_sha256': receipt_sha, 'request': result['request'], 'source': result['source'],
             'state': result['state'], 'measured': result.get('measured'), 'finished_at': result['finished_at']}
    mode['last_attempt'] = proof
    if (result.get('measured') or {}).get('mode_measurement_valid'):
        mode['last_verified_measurement'] = proof
        mode['state'] = 'MEASURED_SHORT_FIXTURES'
    layers = result.get('layers') or {}
    value.update(configured_dispatcher_workers=layers.get('configured_native_workers') or value.get('configured_dispatcher_workers'),
                 model_slots=layers.get('model_slots') or value.get('model_slots'), foreground_slot_reserve=1,
                 background_inference_admission_ceiling=5, control_settings_changed=False)
    return {'path': str(path), 'sha256': record(path, value)}


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', ''); source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    mode = os.environ.get('NOX_CAPACITY_MODE', 'TASK_BOOST')
    if not re.fullmatch(r'\d{6,20}', request) or not re.fullmatch(r'[a-f0-9]{40}', source) or mode not in ('TASK_BOOST', 'NORMAL'):
        fail('HOLD_CAPACITY_OWNER_CONTEXT')
    result = {'schema': 'NOX_OWNER_CAPACITY_MEASUREMENT_V2', 'request': request, 'source': source, 'requested_mode': mode,
              'started_at': time.time(), 'cases': [], 'private_text_exported': False, 'service_changes': False,
              'model_changes': False, 'global_maximum_proven': False,
              'layers': {'configured_native_workers': None, 'model_slots': None, 'foreground_slot_reserve': 1,
                         'background_inference_admission_ceiling': 5,
                         'nox_coordinator': {'logical_role_count': 1, 'extra_model_or_worker_claim': False},
                         'temporary_chatgpt_team': {'session_declared_agents': 4, 'runs_on_nox_server': False,
                                                   'counts_toward_server_capacity': False}},
              'caveats': ['Only short finite fixtures are measured; tool, CPU and long-context maxima are not established.',
                          'A foreground slot is reserved by the five-request ceiling, not an exclusive engine reservation.',
                          'Small-sample p95 is an order statistic; quality failures remain failures even if transport succeeds.']}
    with measurement_lock():
        directory = STATE / 'owner_capacity'
        start_path = directory / ('started_' + request + '.json')
        record(start_path, {'request': request, 'source': source, 'mode': mode}, immutable=True)
        probe = None; before = None
        try:
            probe = load_probe(); before = native_profile(mode); result['profile_before'] = before
            monitor_media(probe, before)
            resource = probe.resources(); probe.resource_gate(resource)
            if abs((resource.get('cpu_quota_cores') or 0) - 19.2) > .001 or resource.get('memory_max') != 194065203200:
                fail('HOLD_CAPACITY_HARDWARE_PROFILE_CHANGED')
            slots = probe.idle_gate()
            if slots['slots'] != 6:
                fail('HOLD_CAPACITY_SIX_MODEL_SLOTS')
            result['layers'].update(configured_native_workers=before['workers']['configured'],
                                    fresh_status_workers=before['workers']['fresh_status_workers'], model_slots=slots['slots'])
            model = http_json(8081, '/v1/models', 16384)
            entries = model.get('data') if isinstance(model, dict) else None
            if not isinstance(entries, list) or len(entries) != 1 or entries[0].get('id') != str(ROOT / 'models/current.gguf'):
                fail('HOLD_CAPACITY_EXISTING_MODEL_ID')
            model_id = entries[0]['id']; deadline = time.monotonic() + MAX_SECONDS
            gpu = probe.gpu_snapshot(); hardware_gate(gpu, mode)
            result.update(resources_before=resource, gpu_before=gpu, model_slots=6,
                          probe_sha256=PROBE_SHA, samples_per_case=12, candidate_concurrency=list(REQUESTED))
            usage = True
            warmup = probe.infer(model_id, 0, threading.Event(), deadline, usage)
            if warmup['state'] == 'HTTP_400':
                probe.idle_gate(); usage = False; warmup = probe.infer(model_id, 0, threading.Event(), deadline, usage)
            result['warmup_excluded'] = warmup
            if not warmup.get('stream_done') or warmup.get('finish_reason') not in ('stop', 'eos_token'):
                fail('HOLD_CAPACITY_WARMUP_TRANSPORT')
            for concurrency in REQUESTED:
                if deadline - time.monotonic() < 15:
                    fail('WAIT_CAPACITY_TIME_BUDGET')
                current = native_profile(mode)
                if not comparison(before, current, mode)['profile_stable']:
                    fail('HOLD_CAPACITY_PROFILE_CHANGED')
                case = probe.burst(model_id, concurrency, 12, deadline, usage)
                result['cases'].append(case)
                emit('capacity_case', case)
                if case['state'] == 'FAILED':
                    fail('HOLD_CAPACITY_TRANSPORT_OR_RESOURCE_FAILURE')
            result['state'] = 'BOUNDED_MEASUREMENTS_COMPLETED'
        except Exception as exc:
            result.update(state='MEASUREMENT_PENDING_OR_HELD', reason=safe_error(exc))
        finally:
            verified = False
            if probe is not None:
                result['resources_after'] = probe.resources(); result['gpu_after'] = probe.gpu_snapshot()
                try:
                    hardware_gate(result['gpu_after'], mode)
                    after = native_profile(mode); result['profile_after'] = after
                    if before is not None:
                        check = comparison(before, after, mode); result['mode_comparison'] = check
                        verified = check['profile_stable'] and (mode == 'TASK_BOOST' or check['optimizer_advanced'])
                    probe.resource_gate(result['resources_after'], result.get('resources_before'))
                except Exception as exc:
                    result['profile_after_reason'] = safe_error(exc); verified = False
                result['measured'] = summarize(probe, result['cases'], verified)
            result['finished_at'] = time.time()
            path = directory / ('measurement_' + request + '.json')
            receipt_sha = record(path, result, immutable=True)
            modes = save_modes(path, receipt_sha, result)
            emit('capacity_measurement', {'schema': result['schema'], 'state': result['state'], 'reason': result.get('reason'),
                 'mode': mode, 'receipt': str(path), 'receipt_sha256': receipt_sha, 'modes': modes,
                 'layers': result['layers'], 'measured': result.get('measured'), 'request': request, 'source': source})
        return 0 if result.get('measured', {}).get('mode_measurement_valid') and result['cases'] else 1


if __name__ == '__main__':
    try:
        exit_code = main()
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
        raise SystemExit(exit_code)
    except Exception as exc:
        emit('capacity_measurement', {'state': 'BLOCKED', 'reason': safe_error(exc), 'service_changes': False})
        raise SystemExit(1)
