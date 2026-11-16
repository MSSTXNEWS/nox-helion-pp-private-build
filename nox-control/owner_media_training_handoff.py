#!/usr/bin/env python3
"""Return a media-owned GPU yield through the existing six-worker dispatcher.

The immutable media runtime/configuration are preserved. This binder replaces
only its in-process resume callback with a durable request; a typed native task
then rechecks the separately sealed 5-to-1000 training admission. It cannot
admit initial training, merge weights, stop a process, or clear an owner pause.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time

ROOT = Path('/root/nox')
CONFIG = 'config/owner_media_training_handoff.json'
SCHEMA = 'NOX_OWNER_MEDIA_TRAINING_HANDOFF_V1'
CONFIG_SCHEMA = 'NOX_OWNER_MEDIA_TRAINING_HANDOFF_CONFIG_V1'
TASK_HANDLER = 'owner_media_resume'
TASK_SOURCE = 'owner_media_training_handoff'
SERVICE = 'nox-train-volta-t866u'
MEDIA_SHA = 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5'
INSTALLER_SHA = 'e66a5b743deb0dfaa7e1e846e11b2d06190962d9ba0ba4abb67abeca54c02ca5'
SCOPE = 'MEDIA_YIELD_TRAINER_ADMISSION_ONLY'
BLOCKERS = ['FRESH_OPTIMIZER_CHECKPOINT_REQUIRED', 'HOLDOUT_AND_MERGE_PROMOTION_SEPARATE']
SHA = re.compile(r'^[a-f0-9]{64}$')
JOB_ID = re.compile(r'^[a-f0-9]{32}$')
NONCE = re.compile(r'^[a-f0-9]{24}$')
TERMINAL = {'COMPLETED', 'FAILED', 'CANCELLED', 'BLOCKED'}
ACTIVE = {'QUEUED', 'YIELDING_TRAINING', 'WAITING_RESOURCES', 'RUNNING', 'SUBMITTING', 'CANCEL_REQUESTED'}
CHECKPOINT_NAMES = {'adapter_model.safetensors', 'adapter_config.json', 'optimizer.pt',
                    'scheduler.pt', 'rng_state.pth', 'scaler.pt', 'trainer_state.json'}
_BOUND = None


class HandoffHold(RuntimeError):
    pass


def hold(code):
    raise HandoffHold(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def plain(path):
    path = Path(path)
    if any(item.is_symlink() for item in (*path.parents, path)):
        hold('HOLD_MEDIA_HANDBACK_SYMLINK')
    return path


def read(path, maximum=262144):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= maximum:
            hold('HOLD_MEDIA_HANDBACK_FILE_SCOPE')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    if len(raw) != before.st_size or identity(before) != identity(after) or identity(path.stat()) != identity(after):
        hold('HOLD_MEDIA_HANDBACK_FILE_CHANGED')
    return raw


def document(path, maximum=262144):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                hold('HOLD_MEDIA_HANDBACK_DUPLICATE_KEY')
            result[key] = value
        return result
    value = json.loads(read(path, maximum), object_pairs_hook=unique,
                       parse_constant=lambda _: hold('HOLD_MEDIA_HANDBACK_NONFINITE'))
    if not isinstance(value, dict):
        hold('HOLD_MEDIA_HANDBACK_JSON')
    return value


def atomic(path, value, create=False):
    path = plain(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.handback-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded(value)); stream.flush(); os.fsync(stream.fileno())
        if create:
            os.link(temporary, path, follow_symlinks=False)
        else:
            os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def exclusive(path, code):
    path = plain(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            hold('HOLD_MEDIA_HANDBACK_LOCK_TYPE')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            hold(code)
        yield
    finally:
        os.close(fd)


def stopped():
    paths = [ROOT / name for name in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
                                      'state/STOP', 'state/OWNER_MAINTENANCE.flag')]
    paths.append(Path('/workspace/NOX_STOP'))
    return any(path.exists() or path.is_symlink() for path in paths)


def safe_code(exc):
    code = str(exc)
    return code if re.fullmatch(r'(?:HOLD|WAIT)_[A-Z0-9_]{1,120}', code) else 'HOLD_MEDIA_HANDBACK_VALIDATION'


def job_id(value):
    if not isinstance(value, str) or not JOB_ID.fullmatch(value):
        hold('HOLD_MEDIA_HANDBACK_JOB_ID')
    return value


def task_shape(task):
    if not isinstance(task, dict):
        return False
    params = task.get('params')
    jid = params.get('job_id') if isinstance(params, dict) else None
    return (isinstance(jid, str) and bool(JOB_ID.fullmatch(jid)) and set(params) == {'job_id'}
            and task.get('id') == 'owner.media.resume.' + jid and task.get('handler') == TASK_HANDLER
            and task.get('source') == TASK_SOURCE and task.get('class') == 'training'
            and task.get('locks') == ['gpu1'] and task.get('deps') == [])


def finite_time(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 < value <= time.time() + 1


class Handback:
    def __init__(self, namespace, runtime, actions, checkpoint_proof):
        self.ns, self.runtime, self.actions, self.proof = namespace, runtime, actions, checkpoint_proof
        self.source_pin = digest(read(__file__, 2 * 1024 * 1024))
        self.original_resume = runtime.resume_training
        self.original_ingest = namespace['ingest_owner_orders']
        self.original_admitted = namespace['_nox_owner_task_admitted']
        self.original_verify = namespace['owner_mentor'].verify_success

    def configuration(self):
        path = plain(ROOT / CONFIG)
        info = path.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            hold('HOLD_MEDIA_HANDBACK_CONFIG_PERMISSIONS')
        config = document(path)
        expected = {'schema', 'enabled', 'resume_training_after_media', 'source_sha256',
                    'runtime_sha256', 'installer_sha256', 'media_config_sha256', 'initial_admission'}
        if (set(config) != expected or config.get('schema') != CONFIG_SCHEMA
                or config.get('enabled') is not True or config.get('resume_training_after_media') is not True):
            hold('WAIT_MEDIA_HANDBACK_NOT_ENABLED')
        if (config.get('source_sha256') != self.source_pin or config.get('runtime_sha256') != MEDIA_SHA
                or config.get('installer_sha256') != INSTALLER_SHA or self.actions.admission is None
                or config.get('initial_admission') != self.actions.admission):
            hold('HOLD_MEDIA_HANDBACK_ADMISSION_CONFIG')
        for path, expected_sha in ((Path(__file__), self.source_pin),
                (ROOT / 'scripts/owner_media_runtime.py', MEDIA_SHA),
                (ROOT / 'scripts/owner_media_install.py', INSTALLER_SHA),
                (ROOT / 'config/owner_media_runtime.json', config.get('media_config_sha256'))):
            if not isinstance(expected_sha, str) or not SHA.fullmatch(expected_sha) or digest(read(path, 2 * 1024 * 1024)) != expected_sha:
                hold('HOLD_MEDIA_HANDBACK_SOURCE_OR_MEDIA_CONFIG_CHANGED')
        return config

    def directory(self, jid):
        return ROOT / 'state/media/training_handback' / job_id(jid)

    def yielded(self, jid, allow_resumed=False):
        value = document(ROOT / 'state/media/training_yield.json')
        resumed = (allow_resumed and value.get('active') is False and value.get('resume') is False
                   and value.get('handback_source_sha256') == self.source_pin
                   and value.get('resume_state') == 'ADMITTED_EXISTING_TRAINER_RESUMED')
        if (value.get('job_id') != jid or not (value.get('resume') is True or resumed)
                or not finite_time(value.get('requested_at'))
                or value.get('pause_token') != 'NOX_MEDIA_CHECKPOINT_YIELD ' + jid + '\n'
                or not isinstance(value.get('wrapper_sha256'), str) or not SHA.fullmatch(value['wrapper_sha256'])):
            hold('HOLD_MEDIA_HANDBACK_YIELD_IDENTITY')
        before = value.get('trainer_before') or {}
        if before.get('state') != 'RUNNING' or type(before.get('pid')) is not int or before['pid'] <= 1:
            hold('HOLD_MEDIA_HANDBACK_PREVIOUS_TRAINER')
        return value

    @staticmethod
    def yield_binding(yielded):
        return {key: yielded[key] for key in ('job_id', 'requested_at', 'pause_token', 'wrapper_sha256', 'trainer_before')}

    def request(self, jid):
        config = self.configuration()
        yielded = self.yielded(jid)
        if yielded.get('active') is not True:
            hold('WAIT_MEDIA_HANDBACK_NO_ACTIVE_YIELD')
        path = self.directory(jid) / 'request.json'
        expected = {'schema': SCHEMA, 'job_id': jid, 'yield_sha256': digest(encoded(self.yield_binding(yielded))),
                    'config_sha256': digest(encoded(config)), 'source_sha256': self.source_pin,
                    'initial_admission': self.actions.admission}
        if not path.exists():
            try:
                atomic(path, {**expected, 'stage': 'QUEUED', 'created_at': time.time()}, create=True)
            except FileExistsError:
                pass
        current = document(path)
        if any(current.get(key) != value for key, value in expected.items()):
            hold('HOLD_MEDIA_HANDBACK_REQUEST_CHANGED')
        return current, yielded

    def idle_media(self, required_job):
        paths = list((ROOT / 'state/media/jobs').glob('*.json'))
        if len(paths) > 200:
            hold('HOLD_MEDIA_HANDBACK_JOB_BOUND')
        found = False
        for path in paths:
            value = document(path)
            if (path.stem != value.get('id') or not JOB_ID.fullmatch(path.stem)
                    or value.get('schema') != 'NOX_OWNER_MEDIA_JOB_V1'
                    or value.get('state') not in TERMINAL | ACTIVE):
                hold('HOLD_MEDIA_HANDBACK_JOB_STATE')
            if value['state'] in ACTIVE:
                hold('WAIT_MEDIA_QUEUE_DRAIN')
            found = found or value['id'] == required_job
        if not found:
            hold('HOLD_MEDIA_HANDBACK_ORIGINAL_JOB_MISSING')

    def callback(self, job, config, yielded):
        if not yielded.get('active') or not yielded.get('resume'):
            return self.original_resume(job, config, yielded)
        # Completion of a generated artifact cannot be undone by a resume wait.
        try:
            self.request(job_id(yielded.get('job_id')))
            return 'TRAINING_RESUME_QUEUED'
        except Exception as exc:
            return safe_code(exc)

    def ingest(self, state):
        self.original_ingest(state)
        try:
            if stopped() or self.ns['owner_mentor'].stop_active():
                return
            value = document(ROOT / 'state/media/training_yield.json')
            jid = job_id(value.get('job_id'))
            if value.get('active') is not True or value.get('resume') is not True:
                return
            self.idle_media(jid)
            self.request(jid)
            tid = 'owner.media.resume.' + jid
            tasks = state.setdefault('tasks', {})
            if tid not in tasks:
                tasks[tid] = {'id': tid, 'handler': TASK_HANDLER, 'source': TASK_SOURCE,
                    'class': 'training', 'priority': 0, 'status': 'pending', 'deps': [], 'locks': ['gpu1'],
                    'params': {'job_id': jid}, 'title': 'Return admitted trainer after media',
                    'retries': 0, 'max_retries': 1, 'timeout_sec': 180}
        except Exception:
            # This hook runs under the native queue lock; it never starts a
            # process, hashes checkpoint payloads, or resets a previous claim.
            return

    def admitted(self, task):
        if task.get('handler') != TASK_HANDLER:
            return self.original_admitted(task)
        try:
            if not task_shape(task) or stopped() or self.ns['owner_mentor'].stop_active():
                return False
            self.configuration()
            record = document(self.directory(task['params']['job_id']) / 'request.json')
            return (record.get('schema') == SCHEMA and record.get('source_sha256') == self.source_pin
                    and record.get('initial_admission') == self.actions.admission
                    and record.get('stage') in {'QUEUED', 'START_INTENT', 'RESUMED'})
        except Exception:
            return False

    def claim(self, task, completed=False):
        claim = task.get('owner_claim') or {}
        if (not task_shape(task) or set(claim) != {'worker', 'pid', 'nonce', 'at'}
                or claim.get('pid') != os.getpid() or not isinstance(claim.get('worker'), str)
                or not re.fullmatch(r'nox-agent-0[1-6]', claim['worker'])
                or not isinstance(claim.get('nonce'), str) or not NONCE.fullmatch(claim['nonce'])
                or not isinstance(claim.get('at'), str) or not 1 <= len(claim['at']) <= 64
                or not finite_time(task.get('owner_claim_epoch'))
                or task.get('claimed_by') != claim['worker']
                or task.get('status') not in ({'running', 'done'} if completed else {'running'})):
            hold('HOLD_MEDIA_HANDBACK_CLAIM')
        if Path(self.ns.get('STATE', '')) != ROOT / 'state/dispatcher/state.json':
            hold('HOLD_MEDIA_HANDBACK_QUEUE_PATH')
        row = (document(self.ns['STATE'], 16 * 1024 * 1024).get('tasks') or {}).get(task['id'])
        if (not isinstance(row, dict) or not task_shape(row) or row.get('owner_claim') != claim
                or row.get('owner_claim_epoch') != task['owner_claim_epoch']
                or row.get('claimed_by') != task['claimed_by']
                or row.get('status') not in ({'running', 'done'} if completed else {'running'})):
            hold('HOLD_MEDIA_HANDBACK_PERSISTED_CLAIM')
        return claim

    def checkpoint(self, yielded, lineage):
        output = ROOT / 'lora/qlora_t866u/runs_owner_hybrid'
        path = output / 'owner_last_result.json'
        before = identity(plain(path).stat())
        terminal = document(path)
        if (terminal.get('state') != 'CHECKPOINTED_OWNER_STOP'
                or path.stat().st_mtime < yielded['requested_at']):
            hold('HOLD_MEDIA_HANDBACK_FRESH_CHECKPOINT')
        ack = yielded.get('checkpoint') or {}
        if (ack.get('receipt_sha256') != digest(read(path)) or ack.get('step') != terminal.get('global_step')
                or ack.get('checkpoint') != str(output / ('checkpoint-' + str(ack.get('step'))))):
            hold('HOLD_MEDIA_HANDBACK_CHECKPOINT_ACKNOWLEDGEMENT')
        total = 0
        for name in CHECKPOINT_NAMES:
            info = plain(output / ('checkpoint-' + str(ack['step'])) / name).stat()
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 8 * 1024 ** 3:
                hold('HOLD_MEDIA_HANDBACK_CHECKPOINT_SIZE_BOUND')
            total += info.st_size
        if total > 8 * 1024 ** 3:
            hold('HOLD_MEDIA_HANDBACK_CHECKPOINT_SIZE_BOUND')
        proof = self.proof(path, lineage=lineage)
        if (proof.get('step') != ack['step'] or proof.get('receipt_sha256') != ack['receipt_sha256']
                or proof.get('lineage_sha256') != lineage or proof.get('adapter_delta_verified') is not True
                or type(proof.get('successful_optimizer_steps')) is not int or proof['successful_optimizer_steps'] < 1
                or len(proof.get('files', [])) != 7
                or {Path(row.get('path', '')).name for row in proof['files']} != CHECKPOINT_NAMES
                or any(row.get('full_sha256_verified') is not True for row in proof['files'])
                or identity(path.stat()) != before):
            hold('HOLD_MEDIA_HANDBACK_FULL_CHECKPOINT_PROOF')
        if proof['step'] >= 1000:
            hold('HOLD_ADMITTED_TRAINING_TARGET_ALREADY_REACHED')
        return proof

    def no_trainer(self):
        scripts = {str(ROOT / 'scripts' / name) for name in
                   ('hybrid_training_entry.py', 'run_train_volta_t866u.sh', 'train_qlora_35b_t866u.py')}
        if any(row.get('state') != 'Z' and scripts.intersection(row.get('argv', []))
               for row in self.actions.helper.process_table().values()):
            hold('WAIT_MEDIA_HANDBACK_EXISTING_TRAINER_PROCESS')

    def resource_gate(self):
        helper = self.actions.helper
        if stopped():
            hold('WAIT_OWNER_STOP')
        if not plain(ROOT / 'state/train_wants_gpu1').is_file():
            hold('WAIT_TEACHER_RESERVATION')
        if any(helper.service_state(name).get('state') not in ('STOPPED', 'EXITED', 'FATAL') for name in helper.HEAVY_SERVICES):
            hold('WAIT_LEGACY_HEAVY_SERVICE_ACTIVE')
        _, lineage, first = self.actions.disk_guard.admission(self.actions.admission)
        budget = self.actions.disk_guard.checkpoint_budget(lineage, first)
        space = os.statvfs(plain(ROOT / 'lora/qlora_t866u/runs_owner_hybrid'))
        if space.f_bavail * space.f_frsize < budget['required_free_bytes']:
            hold('WAIT_TRAINING_CHECKPOINT_DISK_RESERVE')
        gpu = self.runtime.gpu1()
        if gpu['free_mib'] < 30000:
            hold('WAIT_TRAINING_GPU1_HEADROOM')
        memory_limit = int(Path('/sys/fs/cgroup/memory.max').read_text())
        memory_used = int(Path('/sys/fs/cgroup/memory.current').read_text())
        caps = re.findall(r'^TRAIN_CPU_MAX=([0-9]+)GiB$', read(ROOT / 'state/train_cpu_max.env').decode(), re.MULTILINE)
        if len(caps) != 1 or not 56 <= int(caps[0]) <= 64 or memory_limit - memory_used < (int(caps[0]) + 16) * 1024 ** 3:
            hold('WAIT_TRAINING_RAM_HEADROOM')
        if helper.health().get('8081') != 200:
            hold('WAIT_CHAT_HEALTH')
        queue = self.runtime.queue_ids()
        if set(queue) != {'queue_running', 'queue_pending'} or any(queue.values()):
            hold('WAIT_MEDIA_ENGINE_QUEUE_DRAIN')
        return {'gpu1_free_mib': gpu['free_mib'], 'cgroup_available_bytes': memory_limit - memory_used,
                'disk_free_bytes': space.f_bavail * space.f_frsize, 'disk_required_bytes': budget['required_free_bytes']}

    def flags(self, yielded, pointer):
        pause = yielded['pause_token'].encode()
        acknowledgement = ('OWNER_HYBRID_BOUNDED_COMPLETE request=' + pointer['wrapper_request'] + '\n').encode()
        if yielded.get('hold_sha256') != digest(acknowledgement):
            hold('HOLD_MEDIA_HANDBACK_HOLD_ACKNOWLEDGEMENT')
        if digest(read(ROOT / 'scripts/run_train_volta_t866u.sh')) != yielded['wrapper_sha256']:
            hold('HOLD_MEDIA_HANDBACK_WRAPPER_CHANGED')
        return {'TRAIN_PAUSE_REQUEST.flag': pause, 'TRAIN_HOLD.flag': acknowledgement}

    def release_flags(self, jid, flags):
        # Keep the original flag inodes as private evidence. Hard-link creation
        # cannot overwrite another writer; unlink only an unchanged owned name.
        for name, expected in flags.items():
            target = self.directory(jid) / ('released-' + name)
            current = ROOT / 'state' / name
            if target.exists():
                if read(target, 4096) != expected:
                    hold('HOLD_MEDIA_HANDBACK_FLAG_ARCHIVE')
            else:
                if read(current, 4096) != expected:
                    hold('WAIT_UNOWNED_TRAINING_HOLD_OR_PAUSE')
                os.link(current, target, follow_symlinks=False)
            if current.exists() or current.is_symlink():
                before = plain(current).stat()
                if read(current, 4096) != expected or (before.st_dev, before.st_ino) != (target.stat().st_dev, target.stat().st_ino):
                    hold('HOLD_MEDIA_HANDBACK_FLAG_CHANGED')
                if identity(current.stat()) != identity(before):
                    hold('HOLD_MEDIA_HANDBACK_FLAG_CHANGED')
                current.unlink()

    def restore_flags(self, jid, flags):
        # Never overwrite a newly created owner/disk/failed-wrapper flag.
        for name, expected in flags.items():
            archived = self.directory(jid) / ('released-' + name)
            target = ROOT / 'state' / name
            if archived.exists() and read(archived, 4096) == expected:
                try:
                    os.link(archived, target, follow_symlinks=False)
                except FileExistsError:
                    pass

    def attached_process(self, record):
        process = self.actions.trainer_process()
        service = self.actions.helper.service_state(SERVICE)
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if (service.get('state') not in ('RUNNING', 'STARTING') or service.get('pid') != process.get('ppid')
                or process.get('cuda') != '1' or process.get('service') != SERVICE
                or boot != record.get('boot_id') or int(process.get('starttime', 0)) < record['start_not_before_ticks']
                or process.get('pid') == record.get('previous_trainer_pid')):
            hold('WAIT_MEDIA_HANDBACK_STARTED_PROCESS_IDENTITY')
        previous = record.get('process')
        if previous and any(previous.get(key) != process.get(key) for key in ('pid', 'starttime', 'ppid', 'cuda', 'service')):
            hold('HOLD_MEDIA_HANDBACK_PROCESS_REPLACED')
        return process

    def receipt(self, task, record, process):
        claim = self.claim(task)
        path = self.directory(task['params']['job_id']) / ('claim-' + claim['nonce'] + '.json')
        row = {'schema': SCHEMA, 'state': 'ADMITTED_EXISTING_TRAINER_RESUMED', 'verified': True,
               'scope': SCOPE, 'blockers': BLOCKERS, 'task_id': task['id'], 'claim': claim,
               'claim_epoch': task['owner_claim_epoch'], 'observed_at': time.time(),
               'source_sha256': self.source_pin, 'initial_admission': self.actions.admission,
               'job_id': task['params']['job_id'], 'yield_sha256': record['yield_sha256'],
               'baseline_step': record['baseline_step'], 'baseline_receipt_sha256': record['baseline_receipt_sha256'],
               'lineage_sha256': record['lineage_sha256'], 'service': SERVICE, 'process': process,
               'optimizer_progress_since_resume_verified': False, 'weights_promoted': False}
        atomic(path, row, create=True)
        return {'schema': SCHEMA, 'state': row['state'], 'verified': True, 'scope': SCOPE, 'blockers': BLOCKERS,
                'receipt_path': str(path), 'receipt_sha256': digest(read(path)), 'source_sha256': self.source_pin}

    def execute(self, task):
        jid = task['params']['job_id']
        self.claim(task)
        self.configuration()
        if stopped():
            hold('WAIT_OWNER_STOP')
        pointer, lineage = self.actions.training_context()
        record = document(self.directory(jid) / 'request.json')
        yielded = self.yielded(jid, allow_resumed=record.get('stage') == 'RESUMED')
        if (record.get('yield_sha256') != digest(encoded(self.yield_binding(yielded)))
                or record.get('source_sha256') != self.source_pin
                or record.get('initial_admission') != self.actions.admission
                or record.get('config_sha256') != digest(encoded(self.configuration()))):
            hold('HOLD_MEDIA_HANDBACK_REQUEST_CHANGED')
        service = self.actions.helper.service_state(SERVICE)
        if record.get('stage') in ('START_INTENT', 'RESUMED') and record.get('start_command_issued') is True:
            if service.get('state') not in ('RUNNING', 'STARTING'):
                hold('HOLD_MEDIA_HANDBACK_PREVIOUS_START_UNVERIFIED')
            process = self.attached_process(record)
        else:
            if yielded.get('active') is not True or record.get('stage') not in ('QUEUED', 'START_INTENT'):
                hold('HOLD_MEDIA_HANDBACK_REQUEST_STATE')
            self.idle_media(jid)
            if service.get('state') not in ('STOPPED', 'EXITED', 'FATAL'):
                hold('WAIT_TRAINER_TRANSITION')
            self.no_trainer()
            flags = self.flags(yielded, pointer)
            # Before releasing either flag, prove ownership of both. Partial
            # archive recovery is permitted only for this same durable request.
            for name, expected in flags.items():
                current = ROOT / 'state' / name
                archived = self.directory(jid) / ('released-' + name)
                candidate = current if current.exists() or current.is_symlink() else archived
                if read(candidate, 4096) != expected:
                    hold('WAIT_UNOWNED_TRAINING_HOLD_OR_PAUSE')
            proof = self.checkpoint(yielded, lineage)
            with exclusive(ROOT / 'state/forge_training.lock', 'WAIT_SHARED_GPU1_LEASE'):
                budget = self.resource_gate()
                self.no_trainer()
                if self.actions.helper.service_state(SERVICE).get('state') not in ('STOPPED', 'EXITED', 'FATAL'):
                    hold('WAIT_TRAINING_SERVICE_CHANGED')
                self.claim(task)
                if self.actions.training_context() != (pointer, lineage):
                    hold('HOLD_MEDIA_HANDBACK_ADMISSION_CHANGED')
                record.update(stage='START_INTENT', start_command_issued=False,
                    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                    start_not_before_ticks=max(0, int(time.clock_gettime(time.CLOCK_BOOTTIME) * os.sysconf('SC_CLK_TCK')) - 1),
                    previous_trainer_pid=yielded['trainer_before']['pid'], baseline_step=proof['step'],
                    baseline_receipt_sha256=proof['receipt_sha256'], lineage_sha256=lineage, budget=budget)
                atomic(self.directory(jid) / 'request.json', record)
            # Runtime is still serialized by controller.lock and native gpu1;
            # maintenance excludes other controllers. The trainer itself must
            # acquire forge_training.lock before its Torch import.
            try:
                self.release_flags(jid, flags)
                self.idle_media(jid)
                if stopped():
                    hold('WAIT_OWNER_STOP')
                record.update(start_command_issued=True, start_requested_at=time.time())
                atomic(self.directory(jid) / 'request.json', record)
                self.actions.helper.command(['supervisorctl', 'start', SERVICE], 35)
                process = self.attached_process(record)
            except Exception:
                self.restore_flags(jid, flags)
                if record.get('start_command_issued') is True:
                    record.update(stage='START_UNVERIFIED', reason='HOLD_MEDIA_HANDBACK_START_NOT_VERIFIED')
                    atomic(self.directory(jid) / 'request.json', record)
                    hold('HOLD_MEDIA_HANDBACK_START_NOT_VERIFIED')
                raise
        if stopped():
            hold('WAIT_OWNER_STOP')
        record.update(stage='RESUMED', process=process, resumed_at=time.time())
        atomic(self.directory(jid) / 'request.json', record)
        yielded.update(active=False, resume=False, resumed_at=record['resumed_at'],
                       resume_state='ADMITTED_EXISTING_TRAINER_RESUMED', handback_source_sha256=self.source_pin)
        atomic(ROOT / 'state/media/training_yield.json', yielded)
        return self.receipt(task, record, process)

    def run(self, task):
        try:
            if not self.admitted(task):
                hold('WAIT_MEDIA_HANDBACK_ADMISSION')
            # Never wait for maintenance while holding the media controller:
            # owner operations take maintenance first, then this controller.
            with exclusive(ROOT / 'state/media/controller.lock', 'WAIT_MEDIA_CONTROLLER'):
                with exclusive(ROOT / 'state/owner_maintenance.lock', 'WAIT_OWNER_MAINTENANCE'):
                    result = self.execute(task)
            return True, result
        except Exception as exc:
            reason = safe_code(exc)
            return ('wait' if reason.startswith('WAIT_') else False), {
                'schema': SCHEMA, 'state': reason, 'verified': False, 'scope': SCOPE,
                'optimizer_progress_since_resume_verified': False}

    def verify(self, task, evidence=None):
        if task.get('handler') != TASK_HANDLER:
            return self.original_verify(task, evidence)
        try:
            claim = self.claim(task, completed=True)
            jid = task['params']['job_id']
            path = self.directory(jid) / ('claim-' + claim['nonce'] + '.json')
            value = document(path)
            if (not isinstance(evidence, dict) or evidence.get('schema') != SCHEMA
                    or evidence.get('receipt_path') != str(path) or evidence.get('receipt_sha256') != digest(read(path))
                    or value.get('schema') != SCHEMA or value.get('state') != 'ADMITTED_EXISTING_TRAINER_RESUMED'
                    or value.get('verified') is not True or value.get('task_id') != task['id']
                    or value.get('claim') != claim or value.get('claim_epoch') != task['owner_claim_epoch']
                    or value.get('initial_admission') != self.actions.admission
                    or value.get('source_sha256') != self.source_pin or digest(read(__file__, 2 * 1024 * 1024)) != self.source_pin
                    or value.get('scope') != SCOPE or value.get('blockers') != BLOCKERS
                    or value.get('optimizer_progress_since_resume_verified') is not False
                    or value.get('weights_promoted') is not False or not finite_time(value.get('observed_at'))
                    or value['observed_at'] < task['owner_claim_epoch'] or time.time() - value['observed_at'] > 300):
                return None
            return {'kind': 'bounded_native_component_check', 'task_id': task['id'],
                    'receipt_sha256': evidence['receipt_sha256'], 'scope': SCOPE,
                    'blockers': BLOCKERS, 'source_sha256': self.source_pin}
        except Exception:
            return None


def bind_dispatcher(namespace, runtime, actions, checkpoint_proof):
    """Called by the separately pinned native-actions binder before lifecycle."""
    global _BOUND
    if namespace.get('_owner_media_training_handoff_bound'):
        return
    if (not namespace.get('_owner_media_bound') or not namespace.get('_owner_plans_bound')
            or namespace.get('_owner_lifecycle_bound') or namespace.get('WORKERS') != 6
            or Path(getattr(runtime, '__file__', '')) != ROOT / 'scripts/owner_media_runtime.py'
            or digest(read(runtime.__file__, 2 * 1024 * 1024)) != MEDIA_SHA
            or not callable(checkpoint_proof) or not callable(getattr(actions, 'training_context', None))
            or actions.ns is not namespace or actions.disk_guard is None or actions.admission is None
            or TASK_HANDLER in namespace.get('HANDLERS', {})):
        hold('HOLD_MEDIA_HANDBACK_BINDING')
    _BOUND = Handback(namespace, runtime, actions, checkpoint_proof)
    # Missing/disabled private config does not break chat/media startup. Every
    # mutating handback operation requires it plus real sealed1000 admission.
    runtime.resume_training = _BOUND.callback
    namespace['ingest_owner_orders'] = _BOUND.ingest
    namespace['_nox_owner_task_admitted'] = _BOUND.admitted
    namespace['HANDLERS'][TASK_HANDLER] = _BOUND.run
    namespace['owner_mentor'].verify_success = _BOUND.verify
    namespace['_owner_media_training_handoff_bound'] = True
