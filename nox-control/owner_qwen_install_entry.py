#!/usr/bin/env python3
"""Install one pinned Qwen student window into the EXISTING trainer slot.

The public base streams to same-process sealed RAM. Approved corpus text stays
on this server. The old automatic failure HOLD is archived by exact identity;
manual STOP/pause is never cleared. No chat cutover, new service or model merge.
"""
from __future__ import annotations
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
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
STATE = ROOT/'state'
SCRIPTS = ROOT/'scripts'
SERVICE = 'nox-train-volta-t866u'
WRAPPER = SCRIPTS/'run_train_volta_t866u.sh'
WRAPPER_SHA = '3487daffe672f443c43444cd5934c6e65bd45628d9907d5dc43de1ffe9397cb3'
SUPERVISOR = Path('/etc/supervisor/conf.d/nox-train-volta-t866u.conf')
SUPERVISOR_SHA = '6f9562bf9a159b380875c35731b9ae5b8161bd4fa803ceccaec59be8f697f3e4'
NATIVE_TRAINER_SHA = '703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a'
HOLD = STATE/'TRAIN_HOLD.flag'
OLD_HOLD = b'OWNER_HYBRID_FAILED request=6906626126\n'
OLD_HOLD_SHA = '5e42cb8f5e86562ce338a0791a2332f0e86c28672cdf239b0adff17e9c559cd7'
ADMISSION = STATE/'owner_training_admission.json'
PINS = {
 'qwen_student_training_entry.py': '259ac097f3ceec5be217748667a421ab5c39ebb56b9b2817fd1368d278f99cb0',
 'owner_qwen_training_contract.py': '7108da4d4949887414f33f5693fe901e3eb5fc63eb97f2b98d1371fed912f50a',
 'owner_qwen_memfd.py': '938335009efe691a9cef7b41daa7c55f3c8d3d8618a10a5eb5db125fd45afa82',
 'owner_qwen_corpus.py': '1509c31789c2c39507d726515ca1c24a5de5545d8c305c7de0ddbba82058b7eb',
 'qwen35_9b_manifest.json': '2275fc88370ca8ba409a791819e13c8ab7d4e38cce4576a13170b05bcb8b839b',
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2).encode()+b'\n'


def fail(code):
    raise RuntimeError(code)


def plain(path):
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (*path.parents, path)):
        fail('HOLD_QWEN_INSTALL_PATH')
    return path


def read(path, maximum=1024*1024):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            fail('HOLD_QWEN_INSTALL_FILE_SIZE')
        raw = stream.read(maximum+1)
    if len(raw) > maximum:
        fail('HOLD_QWEN_INSTALL_FILE_SIZE')
    return raw


def atomic(path, raw, *, mode=0o600):
    path = plain(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.qwen-owner-', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY|os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def owner_stop():
    return any(p.exists() or p.is_symlink() for p in (
        ROOT/'STOP', ROOT/'STOP.flag', ROOT/'stop.flag', ROOT/'.stop', ROOT/'program/STOP',
        STATE/'STOP', STATE/'TRAIN_PAUSE_REQUEST.flag', Path('/workspace/NOX_STOP')))


def command(args, timeout=10):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def service():
    p = command(['supervisorctl', 'status', SERVICE])
    m = re.match('^'+re.escape(SERVICE)+r'\s+(\w+)(?:\s+pid\s+(\d+))?', p.stdout.strip())
    return {'state': m[1] if m else 'UNKNOWN', 'pid': int(m[2]) if m and m[2] else None,
            'rc': p.returncode}


def model_identity():
    rows = []
    for folder in Path('/proc').iterdir():
        if not folder.name.isdigit():
            continue
        try:
            args = (folder/'cmdline').read_bytes().split(b'\0')
            if (folder/'comm').read_text().strip() != 'llama-server' or b'--port' not in args:
                continue
            if args[args.index(b'--port')+1] != b'8081':
                continue
            fields = (folder/'stat').read_text().split(') ', 1)[1].split()
            rows.append({'pid': int(folder.name), 'start_ticks': fields[19]})
        except (OSError, ValueError, IndexError):
            continue
    if len(rows) != 1:
        fail('HOLD_CURRENT_CHAT_MODEL_IDENTITY')
    return rows[0]


def resource_check():
    if owner_stop():
        fail('HOLD_OWNER_STOP_OR_TRAINING_PAUSE')
    current = int(Path('/sys/fs/cgroup/memory.current').read_text())
    maximum = int(Path('/sys/fs/cgroup/memory.max').read_text())
    disk = os.statvfs(str(ROOT))
    if maximum-current < 72*1024**3 or disk.f_bavail*disk.f_frsize < 10*1024**3:
        fail('HOLD_QWEN_INITIAL_RAM_OR_CHECKPOINT_RESERVE')
    p = command(['nvidia-smi', '--query-gpu=index,memory.free,utilization.gpu', '--format=csv,noheader,nounits'])
    rows = [line.split(',') for line in p.stdout.splitlines() if line.split(',')[0].strip() == '1']
    if p.returncode or len(rows) != 1 or int(rows[0][1]) < 28*1024:
        fail('HOLD_QWEN_GPU1_RESERVE')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:8188/queue', timeout=3) as response:
        queue = json.loads(response.read(65537))
    if (not isinstance(queue, dict) or queue.get('queue_running') != []
            or queue.get('queue_pending') != []):
        fail('HOLD_EXISTING_MEDIA_JOB_ACTIVE')
    return {'cgroup_free_bytes': maximum-current, 'disk_free_bytes': disk.f_bavail*disk.f_frsize,
            'gpu1_free_mib': int(rows[0][1]), 'gpu1_utilization': int(rows[0][2]),
            'comfy_queue_empty': True}


def sources():
    if digest(read(WRAPPER)) != WRAPPER_SHA or digest(read(SUPERVISOR)) != SUPERVISOR_SHA:
        fail('HOLD_EXISTING_TRAINER_WRAPPER_OR_SUPERVISOR_CHANGED')
    if digest(read(SCRIPTS/'train_qlora_35b_t866u.py')) != NATIVE_TRAINER_SHA:
        fail('HOLD_EXISTING_TRAINING_CORPUS_LOADER_CHANGED')
    if read(HOLD, 256) != OLD_HOLD or digest(OLD_HOLD) != OLD_HOLD_SHA:
        fail('HOLD_OLD_AUTOMATIC_TRAINER_FAILURE_CHANGED')
    proof = json.loads(read(STATE/'owner_qwen_runtime_smoke_6906939827.json'))
    if (proof.get('state') != 'NATIVE_RUNTIME_SMOKE_PASSED'
            or proof.get('source_sha') != 'f6e8173b3f11e156e7a661470353d8f8fd38780e'
            or proof.get('hold_unchanged') is not True):
        fail('HOLD_NATIVE_QWEN_RUNTIME_PROOF_REQUIRED')
    policy = json.loads(read(STATE/'task_boost_mode.json', 16000))
    if (policy.get('enabled') is not True or policy.get('mode') != 'TASK_BOOST'
            or policy.get('training_allowed') is not True
            or policy.get('training_service') != SERVICE or policy.get('training_gpu') != 1):
        fail('HOLD_EXISTING_SINGLE_TRAINER_POLICY')
    return proof, policy


def assets():
    result = {}
    for name, pin in PINS.items():
        raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
        if digest(raw) != pin:
            fail('HOLD_QWEN_SOURCE_BUNDLE_PIN')
        if name.endswith('.py'):
            compile(raw, name, 'exec')
        result[name] = raw
    return result


def wrapper(args, request):
    # O_EXCL creates only this run's automatic outcome flag; an owner's flag wins.
    latch = "import os,sys\np=sys.argv[1]\ntry:\n fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)\nexcept FileExistsError:\n raise SystemExit(0)\nwith os.fdopen(fd,'w') as f:\n f.write('OWNER_QWEN_WINDOW_'+('COMPLETE' if sys.argv[2]=='0' else 'FAILED')+' request='+sys.argv[3]+' goal=5\\n');f.flush();os.fsync(f.fileno())\n"
    return ('#!/bin/bash\nset -u\nunset BNB_CUDA_VERSION\nexport CUDA_VISIBLE_DEVICES=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false\n'
            'for flag in /root/nox/STOP /root/nox/STOP.flag /root/nox/stop.flag /root/nox/.stop /root/nox/program/STOP /root/nox/state/STOP /workspace/NOX_STOP /root/nox/state/TRAIN_HOLD.flag /root/nox/state/TRAIN_PAUSE_REQUEST.flag; do\n'
            '  [ ! -e "$flag" ] && [ ! -L "$flag" ] || exit 0\ndone\n'
            +'child_pid=\nforward_stop() { if [ -n "$child_pid" ]; then kill -TERM "$child_pid" 2>/dev/null || true; fi; }\n'
            +'trap forward_stop TERM INT\n'+shlex.join(args)+' &\nchild_pid=$!\n'
            +'while true; do\n  wait "$child_pid"\n  rc=$?\n  kill -0 "$child_pid" 2>/dev/null || break\ndone\n'
            +'/root/venv_volta/bin/python - /root/nox/state/TRAIN_HOLD.flag "$rc" '+shlex.quote(request)+" <<'NOX_QWEN_LATCH'\n"
            +latch+'NOX_QWEN_LATCH\nexit "$rc"\n').encode()


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'\d{1,24}', request) or not re.fullmatch('[a-f0-9]{40}', source):
        fail('HOLD_OWNER_REQUEST_IDENTITY')
    receipt_path = STATE/('owner_qwen_install_'+request+'.json')
    if receipt_path.exists() or receipt_path.is_symlink():
        fail('HOLD_QWEN_INSTALL_ALREADY_STARTED')
    bundle = assets()
    smoke, policy = sources()
    if service()['state'] not in ('STOPPED', 'FATAL', 'EXITED'):
        fail('HOLD_EXISTING_TRAINER_STILL_ACTIVE')
    before_model = model_identity()
    before_resources = resource_check()
    for name in PINS:
        if (SCRIPTS/name).exists() or (SCRIPTS/name).is_symlink():
            fail('HOLD_QWEN_SOURCE_ALREADY_PRESENT')
    lease = os.open(plain(STATE/'owner_maintenance.lock'), os.O_RDWR|os.O_NOFOLLOW)
    fcntl.flock(lease, fcntl.LOCK_EX|fcntl.LOCK_NB)
    training_lease = os.open(plain(STATE/'forge_training.lock'), os.O_RDWR|os.O_NOFOLLOW)
    fcntl.flock(training_lease, fcntl.LOCK_EX|fcntl.LOCK_NB)
    flag = STATE/'OWNER_MAINTENANCE.flag'
    if flag.exists() or flag.is_symlink():
        fail('HOLD_EXISTING_OWNER_MAINTENANCE')
    note = ('NOX_QWEN_INITIAL_INSTALL '+request+' '+source+'\n').encode()
    original_wrapper = read(WRAPPER)
    original_admission = read(ADMISSION)
    backup = ROOT/'backup/owner_qwen_student'/request
    corpus_dir = STATE/'qwen_corpus'/request
    output = ROOT/'lora/qwen35_9b'/request
    hold_archive = backup/'legacy_TRAIN_HOLD.flag'
    for fresh in (backup, corpus_dir, output):
        plain(fresh)
        if fresh.exists() or fresh.is_symlink():
            fail('HOLD_QWEN_FRESH_RUN_PATH_ALREADY_EXISTS')
    installed = []
    released = False
    started = False
    result = {'schema': 'NOX_QWEN_INITIAL_OWNER_INSTALL_V1', 'request': request, 'source_sha': source,
              'started_at': time.time(), 'state': 'PREFLIGHT', 'source_pins': PINS,
              'original_wrapper_sha256': WRAPPER_SHA, 'original_admission_sha256': digest(original_admission),
              'runtime_smoke_request': '6906939827', 'initial_resources': before_resources,
              'active_chat_before': before_model, 'training_service': SERVICE,
              'new_service_created': False, 'main_chat_changed': False, 'old_weights_deleted': 0}
    try:
        atomic(flag, note)
        atomic(receipt_path, encode(result))
        sources(); resource_check()
        if service()['state'] not in ('STOPPED', 'FATAL', 'EXITED'):
            fail('HOLD_TRAINER_CHANGED_BEFORE_INSTALL')
        atomic(backup/'run_train_volta_t866u.sh', original_wrapper)
        atomic(backup/'owner_training_admission.json', original_admission)
        for name, raw in bundle.items():
            target = SCRIPTS/name
            if target.exists() or target.is_symlink():
                fail('HOLD_QWEN_SOURCE_CHANGED_BEFORE_INSTALL')
            atomic(target, raw)
            installed.append(target)
            if digest(read(target)) != PINS[name]:
                fail('HOLD_QWEN_INSTALLED_SOURCE_READBACK')
        for name in ('owner_qwen_training_contract', 'owner_qwen_memfd', 'owner_qwen_corpus'):
            mod = types.ModuleType(name)
            mod.__file__ = str(SCRIPTS/(name+'.py'))
            sys.modules[name] = mod
            exec(compile(bundle[name+'.py'], mod.__file__, 'exec'), mod.__dict__)
        manifest = json.loads(bundle['qwen35_9b_manifest.json'])
        config_row = next(row for row in manifest['files'] if row['path'] == 'config.json')
        transport = sys.modules['owner_qwen_memfd']
        transport.allowed_public_url(config_row['immutable_url'])
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), transport.PublicHFRedirect())
        with opener.open(urllib.request.Request(config_row['immutable_url'],
                         headers={'Accept-Encoding': 'identity'}), timeout=15) as response:
            transport.allowed_public_url(response.geturl())
            small_config = response.read(config_row['bytes']+1)
        if len(small_config) != config_row['bytes'] or digest(small_config) != config_row['sha256']:
            fail('HOLD_NATIVE_PUBLIC_MODEL_CONFIG_READBACK')
        result['native_public_hf_probe'] = {'file': 'config.json', 'bytes': len(small_config),
                                         'sha256': digest(small_config), 'verified': True}
        def guard():
            if owner_stop() or read(flag, 256) != note or read(HOLD, 256) != OLD_HOLD:
                fail('HOLD_OWNER_CHANGED_DURING_CORPUS_SNAPSHOT')
        corpus = sys.modules['owner_qwen_corpus'].snapshot(ROOT, corpus_dir, guard=guard)
        contract = sys.modules['owner_qwen_training_contract']
        runtime = smoke['native_proof']['runtime']
        profile = {'schema': 'NOX_QWEN35_9B_SINGLE_TRAINER_V1', 'model_id': contract.MODEL_ID,
            'revision': contract.REVISION, 'base_manifest_sha256': contract.MANIFEST_SHA,
            'base_directory': str(STATE/'qwen_memfd'), 'base_transport': 'sealed-memfd',
            'output_directory': str(output), 'train_sha256': corpus['train_sha256'],
            'holdout_sha256': corpus['holdout_sha256'], 'dataset_manifest_sha256': corpus['manifest_sha256'],
            'physical_gpu': 1, 'training_service': SERVICE, 'successful_updates_goal': 5,
            'runtime_versions': {'python': runtime['python_version'], 'torch': runtime['torch_version'],
                'cuda': runtime['torch_cuda'], 'packages': runtime['packages']}}
        admission = {'schema': 'NOX_OWNER_TRAINING_ADMISSION_V1', 'request': request, 'source_sha': source,
                     'sources': {str(SCRIPTS/name): pin for name,pin in PINS.items() if name.endswith('.py')},
                     'student_profile': profile, 'initial_request': request, 'created_at': time.time()}
        raw_admission = encode(admission)
        args = ['/root/venv_volta/bin/python', '-u', str(SCRIPTS/'qwen_student_training_entry.py'),
            '--request', request, '--admission-sha256', digest(raw_admission),
            '--base-directory', profile['base_directory'], '--base-transport', 'sealed-memfd',
            '--manifest', str(SCRIPTS/'qwen35_9b_manifest.json'), '--output-directory', str(output),
            '--train-jsonl', str(corpus_dir/'train.jsonl'), '--train-sha256', corpus['train_sha256'],
            '--holdout-jsonl', str(corpus_dir/'holdout.jsonl'), '--holdout-sha256', corpus['holdout_sha256'],
            '--dataset-manifest', str(corpus_dir/'corpus_manifest.json'),
            '--dataset-manifest-sha256', corpus['manifest_sha256'], '--successful-updates', '5']
        new_wrapper = wrapper(args, request)
        subprocess.run(['bash', '-n'], input=new_wrapper, check=True, capture_output=True, timeout=5)
        guard(); resource_check(); sources()
        if digest(read(ADMISSION)) != digest(original_admission):
            fail('HOLD_PREVIOUS_TRAINING_ADMISSION_CHANGED')
        atomic(ADMISSION, raw_admission)
        atomic(WRAPPER, new_wrapper, mode=0o700)
        if digest(read(ADMISSION)) != digest(raw_admission) or digest(read(WRAPPER)) != digest(new_wrapper):
            fail('HOLD_QWEN_ADMISSION_WRAPPER_READBACK')
        if read(HOLD, 256) != OLD_HOLD:
            fail('HOLD_AUTOMATIC_HOLD_CHANGED_BEFORE_HANDOFF')
        if hold_archive.exists() or hold_archive.is_symlink():
            fail('HOLD_LEGACY_HOLD_ARCHIVE_ALREADY_EXISTS')
        os.rename(HOLD, hold_archive)
        if read(hold_archive, 256) != OLD_HOLD:
            fail('HOLD_LEGACY_HOLD_ARCHIVE_READBACK')
        result.update(state='INSTALLED_BEFORE_START', student_profile=profile,
                      admission_sha256=digest(raw_admission), wrapper_sha256=digest(new_wrapper),
                      corpus_snapshot=corpus, output_directory=str(output), corpus_directory=str(corpus_dir),
                      old_hold_archived=str(hold_archive))
        atomic(receipt_path, encode(result))
        os.close(training_lease); training_lease = None
        released = True
        p = command(['supervisorctl', 'start', SERVICE], 30)
        observed = service()
        if p.returncode != 0 or observed['state'] != 'RUNNING' or not observed['pid']:
            fail('HOLD_NEW_STUDENT_SUPERVISOR_START_UNVERIFIED')
        started = True
        if model_identity() != before_model:
            fail('HOLD_CURRENT_CHAT_MODEL_IDENTITY_CHANGED')
        result.update(state='NEW_STUDENT_STARTED_ACCEPTANCE_PENDING', service_after=observed,
                      active_chat_after=model_identity(), successful_optimizer_steps_verified=False,
                      full_model_loaded_verified=False, training_process_started=True)
    except Exception as exc:
        message = str(exc)
        result.update(state='HOLD', error=message if re.fullmatch('HOLD_[A-Z0-9_]+', message) else type(exc).__name__)
        if released:
            try:
                failure_fd = os.open(HOLD, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                result['failure_hold'] = 'EXISTING_FLAG_PRESERVED'
            else:
                with os.fdopen(failure_fd, 'w') as stream:
                    stream.write('OWNER_QWEN_INSTALL_FAILED request='+request+'\n')
                    stream.flush(); os.fsync(stream.fileno())
                result['failure_hold'] = 'OWNED_FAILURE_FLAG_CREATED'
        if not released:
            try:
                if WRAPPER.exists() and digest(read(WRAPPER)) != WRAPPER_SHA:
                    if 'new_wrapper' in locals() and digest(read(WRAPPER)) == digest(new_wrapper):
                        atomic(WRAPPER, original_wrapper, mode=0o700)
                if 'raw_admission' in locals() and digest(read(ADMISSION)) == digest(raw_admission):
                    atomic(ADMISSION, original_admission)
                if not HOLD.exists() and hold_archive.exists() and read(hold_archive, 256) == OLD_HOLD:
                    os.rename(hold_archive, HOLD)
                for target in reversed(installed):
                    if digest(read(target)) == PINS[target.name]:
                        target.unlink()
                result['prestart_rollback_completed'] = True
            except Exception as rollback:
                result['rollback_error'] = type(rollback).__name__
    finally:
        if training_lease is not None:
            os.close(training_lease)
        if flag.exists() and read(flag, 256) == note:
            flag.unlink()
        os.close(lease)
        result['finished_at'] = time.time()
        result['source_installed'] = released
        result['training_process_started'] = started
        atomic(receipt_path, encode(result))
        print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'qwen_initial_install', 'data': result}), flush=True)
    success = started and result['state'] == 'NEW_STUDENT_STARTED_ACCEPTANCE_PENDING'
    print('NOX_MAINT_REPAIR_COMPLETE='+str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        message = str(exc)
        code = message if re.fullmatch('HOLD_[A-Z0-9_]+', message) else 'HOLD_'+type(exc).__name__.upper()
        print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'qwen_install_preflight', 'state': code}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
