#!/usr/bin/env python3
"""Generate two small owner samples through the existing authenticated queue.

This is a bounded acceptance operation, not another worker or media backend.
It does not start training, change controller sources, or kill any process.
Real output files stay private; only technical evidence is emitted.
"""
from __future__ import annotations

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
import sys
import tempfile
import time
import types

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SCRIPTS = ROOT / 'scripts'
PROXY_PYTHON = '/root/nox/venv/bin/python'
RUNTIME_SHA = 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5'
SOURCE_GROUPS = {
    'BEFORE_S03_ACTIVATION': {
        'nox_dispatcher_t855u.py': 'd4e665915ae2a9f0be8ae4603be3768467e0f88be876e408465c3a7cc156c243',
        'owner_task_lifecycle.py': '020fcee6d1267189811c51da031761aa9ae681a3a2bcd567fbbc150c33db8605',
        'owner_event_outbox.py': 'af4edd2c34e4d46902ccf914b5be9c845a95d682d34f92a08cd69357c4b69c00',
    },
    'AFTER_S03_ACTIVATION': {
        'nox_dispatcher_t855u.py': '934193bf4df6fef73293628793eaac1c10e923e15aea4b7a36c82335ad3795b8',
        'owner_task_lifecycle.py': '909502a75799096e094a622639fe959ecfa835cc70db705a4062541940cea27e',
        'owner_event_outbox.py': 'e15d458f9d1f03b23fcbf0267206621769ff92f2bfe00d3baf79217e2ab74a02',
    },
}
HALT_PREFIX = b'OWNER_REQUESTED_TRAINING_HALT request=6902883046 source=df3a6005ca711ce44b606b864db154c396cbeb92'
CASES = (
    {'kind': 'image', 'prompt': 'A realistic photograph of a red ceramic teacup on a wooden table beside a window, soft natural morning light, detailed ceramic surface, no text.',
     'negative_prompt': '', 'width': 512, 'height': 512, 'frames': 1, 'fps': 8, 'seed': 160011},
    {'kind': 'video', 'prompt': 'A small yellow flower gently moving in a light breeze, a close camera view, soft natural daylight, smooth continuous motion, no text.',
     'negative_prompt': 'static image, text, watermark', 'width': 256, 'height': 256, 'frames': 9, 'fps': 8, 'seed': 160012},
)
MAX_OUTPUT = 64 * 1024 * 1024
JOB_RE = re.compile(r'[a-f0-9]{32}')
CODE_RE = re.compile(r'(?:HOLD|WAIT|INVALID)_[A-Z0-9_]{1,100}')


def fail(code):
    raise RuntimeError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_error(exc):
    value = str(exc)
    return value if CODE_RE.fullmatch(value) else 'HOLD_MEDIA_ACCEPTANCE_' + type(exc).__name__.upper()


def emit(kind, value):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': value}, separators=(',', ':'), allow_nan=False), flush=True)


def checked_path(path):
    path = Path(path)
    if not path.is_absolute() or any(item.is_symlink() for item in (path, *path.parents)):
        fail('HOLD_MEDIA_ACCEPTANCE_PATH')
    return path


@contextmanager
def regular_fd(path, limit):
    path = checked_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            fail('HOLD_MEDIA_ACCEPTANCE_FILE_SCOPE')
        yield fd, before
        after = os.fstat(fd)
        current = path.stat(follow_symlinks=False)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if any(getattr(before, key) != getattr(after, key) or getattr(before, key) != getattr(current, key) for key in fields):
            fail('HOLD_MEDIA_ACCEPTANCE_FILE_CHANGED')
    finally:
        os.close(fd)


def read(path, limit=1024 * 1024):
    with regular_fd(path, limit) as (fd, _):
        parts = []; count = 0
        while True:
            chunk = os.read(fd, min(65536, limit + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            if count > limit:
                fail('HOLD_MEDIA_ACCEPTANCE_FILE_SCOPE')
            parts.append(chunk)
        return b''.join(parts)


def document(path, limit=1024 * 1024):
    value = json.loads(read(path, limit))
    if not isinstance(value, dict):
        fail('HOLD_MEDIA_ACCEPTANCE_JSON')
    return value


def write_record(path, value, immutable=False):
    path = checked_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = (json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')) + '\n').encode()
    if immutable:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    else:
        fd, temporary = tempfile.mkstemp(prefix='.acceptance-', dir=path.parent)
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
def lease(path, shared=False):
    path = checked_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            fail('HOLD_MEDIA_ACCEPTANCE_LEASE_TYPE')
        try:
            fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError:
            fail('WAIT_MEDIA_ACCEPTANCE_LEASE')
        yield fd
    finally:
        os.close(fd)


def sources():
    observed = {name: digest(read(SCRIPTS / name)) for name in next(iter(SOURCE_GROUPS.values()))}
    group = next((name for name, pins in SOURCE_GROUPS.items() if observed == pins), None)
    runtime = read(SCRIPTS / 'owner_media_runtime.py')
    if group is None or digest(runtime) != RUNTIME_SHA:
        fail('HOLD_MEDIA_ACCEPTANCE_SOURCE_PINS')
    return {'group': group, 'pins': observed, 'runtime_sha256': RUNTIME_SHA}, runtime


def load_runtime(raw):
    if digest(raw) != RUNTIME_SHA:
        fail('HOLD_MEDIA_ACCEPTANCE_RUNTIME_PIN')
    module = types.ModuleType('owner_media_acceptance_runtime')
    module.__file__ = str(SCRIPTS / 'owner_media_runtime.py')
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def dispatcher_identity():
    result = subprocess.run(['supervisorctl', 'status', 'nox-dispatcher-t855u'], capture_output=True, timeout=6, text=True)
    match = re.fullmatch(r'nox-dispatcher-t855u\s+RUNNING\s+pid\s+(\d+),[^\n]*\n?', result.stdout)
    if result.returncode or not match:
        fail('HOLD_MEDIA_ACCEPTANCE_DISPATCHER_NOT_RUNNING')
    pid = int(match[1]); proc = Path('/proc') / str(pid)
    argv = (proc / 'cmdline').read_bytes().split(b'\0')
    fields = (proc / 'stat').read_text().split(') ', 1)[1].split()
    if str(SCRIPTS / 'nox_dispatcher_t855u.py').encode() not in argv or fields[0] in ('Z', 'X'):
        fail('HOLD_MEDIA_ACCEPTANCE_DISPATCHER_IDENTITY')
    return {'pid': pid, 'start_ticks': fields[19]}


def training_guard(runtime, expected=None):
    hold = read(STATE / 'TRAIN_HOLD.flag', 4096)
    if not hold.startswith(HALT_PREFIX):
        fail('HOLD_MEDIA_ACCEPTANCE_ORIGINAL_TRAINING_HOLD')
    pause_path = STATE / 'TRAIN_PAUSE_REQUEST.flag'
    pause_sha = digest(read(pause_path, 4096)) if pause_path.exists() or pause_path.is_symlink() else None
    value = {'hold_sha256': digest(hold), 'pause_sha256': pause_sha}
    if expected is not None and value != expected:
        fail('HOLD_MEDIA_ACCEPTANCE_TRAINING_FLAGS_CHANGED')
    status = runtime.service_state(runtime.TRAIN_SERVICE)
    if status['state'] not in ('STOPPED', 'EXITED', 'FATAL') or status.get('pid'):
        fail('HOLD_MEDIA_ACCEPTANCE_TRAINER_NOT_STOPPED')
    yielded_path = STATE / 'media/training_yield.json'
    if yielded_path.exists() and document(yielded_path).get('active') is True:
        fail('HOLD_MEDIA_ACCEPTANCE_OTHER_TRAINING_YIELD')
    return value, status


AUTH = r'''
import contextlib,http.client,http.cookies,json,os,sys
sys.path.insert(0,'/root/nox/scripts')
with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
    import chat_proxy
    password=chat_proxy._read_chat_password()
if not isinstance(password,str) or len(password)<6:raise RuntimeError('HOLD_OWNER_CREDENTIAL_UNAVAILABLE')
c=http.client.HTTPConnection('127.0.0.1',8080,timeout=8)
try:
    c.request('POST','/chat/login',json.dumps({'password':password}).encode(),{'Content-Type':'application/json','Connection':'close'})
    password=None;r=c.getresponse()
    if r.status!=200:raise RuntimeError('HOLD_OFFICIAL_LOGIN')
    cookies=http.cookies.SimpleCookie()
    for key,value in r.getheaders():
        if key.lower()=='set-cookie':cookies.load(value)
    if 'nox_chat' not in cookies:raise RuntimeError('HOLD_OFFICIAL_COOKIE')
    print(json.dumps({'cookie':cookies['nox_chat'].value}))
finally:c.close()
'''


class OwnerClient:
    def __init__(self, cookie=None):
        self.cookie = cookie

    @classmethod
    def authenticate(cls):
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='')
        result = subprocess.run([PROXY_PYTHON, '-c', AUTH], capture_output=True, timeout=25, env=environment)
        if result.returncode or len(result.stdout) > 2000:
            fail('HOLD_MEDIA_ACCEPTANCE_OFFICIAL_LOGIN')
        try:
            cookie = json.loads(result.stdout)['cookie']
        except (ValueError, TypeError, KeyError):
            fail('HOLD_MEDIA_ACCEPTANCE_OFFICIAL_COOKIE')
        if not isinstance(cookie, str) or not re.fullmatch(r'\d{8,14}\.[A-Za-z0-9_-]{8,100}\.[a-f0-9]{64}', cookie):
            fail('HOLD_MEDIA_ACCEPTANCE_OFFICIAL_COOKIE')
        client = cls(cookie)
        if client.json('/chat/session').get('ok') is not True:
            fail('HOLD_MEDIA_ACCEPTANCE_SIGNED_SESSION')
        return client

    def connection(self, path, method='GET', data=None):
        if not re.fullmatch(r'/(?:chat/(?:session|logout)|api/ui/media(?:/jobs(?:/[a-f0-9]{32}(?:/outputs/0)?)?)?)', path):
            fail('HOLD_MEDIA_ACCEPTANCE_API_SCOPE')
        headers = {'Connection': 'close', 'Content-Type': 'application/json', 'Accept-Encoding': 'identity'}
        if self.cookie is not None:
            headers['Cookie'] = 'nox_chat=' + self.cookie
        client = http.client.HTTPConnection('127.0.0.1', 8080, timeout=8)
        try:
            client.request(method, path, None if data is None else json.dumps(data).encode(), headers)
            return client, client.getresponse()
        except Exception:
            client.close()
            raise

    def json(self, path, method='GET', data=None, status=200):
        client, response = self.connection(path, method, data)
        try:
            raw = response.read(256001)
            if response.status != status:
                fail('HOLD_MEDIA_ACCEPTANCE_HTTP_' + str(response.status))
            if len(raw) > 256000:
                fail('HOLD_MEDIA_ACCEPTANCE_HTTP_SIZE')
            result = json.loads(raw)
            if not isinstance(result, dict):
                fail('HOLD_MEDIA_ACCEPTANCE_HTTP_SCHEMA')
            return result
        finally:
            client.close()

    def output_hash(self, path, expected_type):
        client, response = self.connection(path)
        try:
            if response.status != 200 or response.getheader('Content-Type', '').split(';')[0] != expected_type:
                fail('HOLD_MEDIA_ACCEPTANCE_OUTPUT_HTTP')
            if response.getheader('Content-Encoding', 'identity') != 'identity':
                fail('HOLD_MEDIA_ACCEPTANCE_OUTPUT_ENCODING')
            length = response.getheader('Content-Length', '')
            if not length.isdigit() or not 0 < int(length) <= MAX_OUTPUT:
                fail('HOLD_MEDIA_ACCEPTANCE_OUTPUT_HTTP_SIZE')
            result = hashlib.sha256(); count = 0; deadline = time.monotonic() + 40
            while True:
                chunk = response.read(262144)
                if not chunk:
                    break
                count += len(chunk)
                if count > MAX_OUTPUT or time.monotonic() > deadline:
                    fail('HOLD_MEDIA_ACCEPTANCE_OUTPUT_HTTP_BUDGET')
                result.update(chunk)
            if count != int(length):
                fail('HOLD_MEDIA_ACCEPTANCE_OUTPUT_HTTP_TRUNCATED')
            return {'bytes': count, 'sha256': result.hexdigest(), 'authenticated_http_verified': True}
        finally:
            client.close()

    def close(self):
        try:
            self.json('/chat/logout', method='POST', data={})
        finally:
            self.cookie = None


def no_other_jobs(runtime, own_ids=()):
    directory = checked_path(STATE / 'media/jobs')
    if not directory.exists():
        return
    count = 0
    for path in directory.iterdir():
        count += 1
        if count > 450:
            fail('HOLD_MEDIA_ACCEPTANCE_JOB_SCAN_BUDGET')
        if path.suffix != '.json':
            continue
        if not JOB_RE.fullmatch(path.stem):
            fail('HOLD_MEDIA_ACCEPTANCE_JOB_INVENTORY')
        value = document(path, 262144)
        if value.get('id') != path.stem:
            fail('HOLD_MEDIA_ACCEPTANCE_JOB_IDENTITY')
        if value.get('state') in runtime.ACTIVE and path.stem not in own_ids:
            fail('WAIT_MEDIA_ACCEPTANCE_OWNER_WORK')


def queue_task(job_id):
    value = document(STATE / 'dispatcher/state.json', 16 * 1024 * 1024)
    tasks = value.get('tasks')
    if not isinstance(tasks, dict):
        fail('HOLD_MEDIA_ACCEPTANCE_NATIVE_QUEUE_SCHEMA')
    return tasks.get('owner.media.' + job_id)


def claim_projection(task, job_id, dispatcher_pid, require_done=False):
    if not isinstance(task, dict):
        return None
    if (task.get('id') != 'owner.media.' + job_id or task.get('handler') != 'owner_media'
            or (task.get('params') or {}).get('job_id') != job_id or task.get('locks') != ['gpu1']
            or task.get('class') != 'owner_order'):
        fail('HOLD_MEDIA_ACCEPTANCE_NATIVE_TASK_IDENTITY')
    claim = task.get('owner_claim') or {}
    if task.get('status') not in ('running', 'done'):
        return None
    if (type(claim.get('pid')) is not int or claim['pid'] != dispatcher_pid
            or not isinstance(claim.get('worker'), str) or not re.fullmatch(r'nox-agent-0[1-6]', claim['worker'])
            or not isinstance(claim.get('nonce'), str) or not re.fullmatch(r'[a-f0-9]{24}', claim['nonce'])):
        fail('HOLD_MEDIA_ACCEPTANCE_NATIVE_CLAIM')
    if require_done:
        result = task.get('result')
        if (task.get('status') != 'done' or not isinstance(result, dict) or result.get('id') != job_id
                or result.get('state') != 'COMPLETED' or result.get('generation_verified') is not True):
            return None
    return {'task_id': task['id'], 'handler': 'owner_media', 'status': task['status'],
            'worker': claim['worker'], 'pid': claim['pid'], 'nonce': claim['nonce']}


def forge_holder(dispatcher_pid):
    path = checked_path(STATE / 'forge_training.lock')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            fail('HOLD_MEDIA_ACCEPTANCE_FORGE_TYPE')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            pass
        # /proc/locks has zero st_size, so a bounded direct read is required.
        with open('/proc/locks', 'rb', buffering=0) as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            fail('HOLD_MEDIA_ACCEPTANCE_LOCK_SCAN_BUDGET')
        for line in raw.decode('ascii').splitlines():
            if '->' in line:
                continue
            found = re.fullmatch(r'\d+:\s+FLOCK\s+ADVISORY\s+WRITE\s+(\d+)\s+([a-fA-F0-9]+):([a-fA-F0-9]+):(\d+)\s+0\s+EOF', line)
            if (found and int(found[1]) == dispatcher_pid and int(found[2], 16) == os.major(info.st_dev)
                    and int(found[3], 16) == os.minor(info.st_dev) and int(found[4]) == info.st_ino):
                return True
        return False
    finally:
        os.close(fd)


DECODE = r'''
import hashlib,json,sys
from PIL import Image,ImageStat
path=sys.argv[1];expected=json.loads(sys.argv[2]);kind=expected['kind']
if kind=='image':
    im=Image.open(path)
    if im.format!='PNG':raise RuntimeError('FORMAT')
    im.verify();im=Image.open(path);im.load();rgb=im.convert('RGB')
    ranges=[high-low for low,high in rgb.getextrema()]
    proof={'width':im.width,'height':im.height,'frames':getattr(im,'n_frames',1),'codec':'png',
           'max_channel_range':max(ranges),'max_channel_variance':max(ImageStat.Stat(rgb).var)}
else:
    import av
    with av.open(path) as container:
        if len(container.streams.video)!=1:raise RuntimeError('STREAM_COUNT')
        stream=container.streams.video[0];stamps=[];hashes=set();ranges=[]
        count=0
        for frame in container.decode(stream):
            count+=1
            if count>expected['frames']:raise RuntimeError('FRAME_BUDGET')
            if frame.width!=expected['width'] or frame.height!=expected['height']:raise RuntimeError('FRAME_DIMENSIONS')
            if frame.pts is None or frame.time_base is None:raise RuntimeError('TIMESTAMPS')
            stamps.append(float(frame.pts*frame.time_base))
            rgb=frame.to_image().convert('RGB');hashes.add(hashlib.sha256(rgb.tobytes()).hexdigest())
            ranges.append(max(high-low for low,high in rgb.getextrema()))
        span=stamps[-1]-stamps[0] if len(stamps)>1 else 0
        proof={'width':stream.width,'height':stream.height,'frames':count,'codec':stream.codec_context.name,
               'metadata_fps':float(stream.average_rate) if stream.average_rate else None,
               'decoded_fps':(count-1)/span if span>0 else 0,'distinct_decoded_frames':len(hashes),
               'max_channel_range':max(ranges,default=0),'timestamps_strictly_increasing':len(stamps)>1 and all(b>a for a,b in zip(stamps,stamps[1:])),
               'timestamp_span_seconds':span,
               'max_frame_interval_error_seconds':max((abs((b-a)-1/expected['fps']) for a,b in zip(stamps,stamps[1:])),default=999)}
print(json.dumps(proof,allow_nan=False))
'''


def validate_decode(proof, request):
    if not isinstance(proof, dict) or any(type(proof.get(key)) is not int or proof[key] != request[key] for key in ('width', 'height', 'frames')):
        fail('HOLD_MEDIA_ACCEPTANCE_DECODE_DIMENSIONS')
    if any(type(value) is float and not math.isfinite(value) for value in proof.values()):
        fail('HOLD_MEDIA_ACCEPTANCE_DECODE_NONFINITE')
    if type(proof.get('max_channel_range')) not in (int, float) or proof['max_channel_range'] < 4:
        fail('HOLD_MEDIA_ACCEPTANCE_BLANK_OUTPUT')
    if request['kind'] == 'image':
        if proof.get('codec') != 'png' or type(proof.get('max_channel_variance')) not in (int, float) or proof['max_channel_variance'] < 1:
            fail('HOLD_MEDIA_ACCEPTANCE_IMAGE_DECODE')
    elif (proof.get('codec') != 'vp9' or type(proof.get('decoded_fps')) not in (int, float) or abs(proof['decoded_fps'] - request['fps']) > 0.01
            or type(proof.get('distinct_decoded_frames')) is not int or proof['distinct_decoded_frames'] < 2
            or proof.get('timestamps_strictly_increasing') is not True
            or type(proof.get('max_frame_interval_error_seconds')) not in (int, float) or proof['max_frame_interval_error_seconds'] > 0.002
            or abs(proof.get('timestamp_span_seconds', 0) - (request['frames'] - 1) / request['fps']) > 0.025):
        fail('HOLD_MEDIA_ACCEPTANCE_VIDEO_DECODE')
    return proof


def verify_artifact(runtime, config, job, client):
    outputs = job.get('outputs')
    if not isinstance(outputs, list) or len(outputs) != 1:
        fail('HOLD_MEDIA_ACCEPTANCE_OUTPUT_COUNT')
    item = outputs[0]; path = runtime.output_path(config, job['id'], item)
    expected_type = 'image/png' if job['request']['kind'] == 'image' else 'video/webm'
    if path.suffix != ('.png' if job['request']['kind'] == 'image' else '.webm') or item.get('media_type') != expected_type:
        fail('HOLD_MEDIA_ACCEPTANCE_OUTPUT_FORMAT')
    with regular_fd(path, MAX_OUTPUT) as (fd, info):
        value = hashlib.sha256()
        for chunk in iter(lambda: os.read(fd, 1024 * 1024), b''):
            value.update(chunk)
        actual_sha = value.hexdigest()
        if info.st_size <= 0 or info.st_size != item.get('bytes') or actual_sha != item.get('sha256'):
            fail('HOLD_MEDIA_ACCEPTANCE_OUTPUT_HASH')
        os.lseek(fd, 0, os.SEEK_SET)
        expected = {key: job['request'][key] for key in ('kind', 'width', 'height', 'frames', 'fps')}
        result = subprocess.run([config['python'], '-c', DECODE, '/proc/self/fd/' + str(fd), json.dumps(expected)],
                                pass_fds=(fd,), capture_output=True, timeout=35,
                                env=dict(os.environ, CUDA_VISIBLE_DEVICES='', PYTHONDONTWRITEBYTECODE='1'))
        if result.returncode or len(result.stdout) > 5000:
            fail('HOLD_MEDIA_ACCEPTANCE_OUTPUT_DECODE')
        proof = validate_decode(json.loads(result.stdout), job['request'])
        url = '/api/ui/media/jobs/' + job['id'] + '/outputs/0'
        served = client.output_hash(url, expected_type)
        if served['bytes'] != info.st_size or served['sha256'] != actual_sha:
            fail('HOLD_MEDIA_ACCEPTANCE_SERVED_HASH_MISMATCH')
    return {'kind': job['request']['kind'], 'job_id': job['id'], 'path': str(path), 'url': url,
            'bytes': info.st_size, 'sha256': actual_sha, 'media_type': expected_type,
            'decode': proof, 'decode_verified': True, 'authenticated_http_verified': True, 'pixels_exported': False,
            'scope': 'GENERATED_FILE_DECODE_AND_AUTHENTICATED_DELIVERY'}


def wait_job(runtime, client, job_id, expected, dispatcher, flags, deadline, journal, journal_path):
    observed_state = None; observed_lease = False; observed_engine = False
    while time.monotonic() < deadline:
        value = client.json('/api/ui/media/jobs/' + job_id)
        job = document(runtime.job_path(job_id), 262144)
        if value.get('id') != job_id or job.get('id') != job_id or value.get('request') != expected or job.get('request') != expected:
            fail('HOLD_MEDIA_ACCEPTANCE_JOB_CHANGED')
        state = value.get('state')
        if not isinstance(state, str) or state not in runtime.ACTIVE | runtime.TERMINAL:
            fail('HOLD_MEDIA_ACCEPTANCE_JOB_STATE')
        if state != observed_state:
            observed_state = state
            emit('media_acceptance_job', {'kind': expected['kind'], 'job_id': job_id, 'state': state})
        task = queue_task(job_id)
        claim = claim_projection(task, job_id, dispatcher['pid'])
        if state == 'RUNNING' and claim:
            training_guard(runtime, flags)
            prompt_id = job.get('prompt_id'); queue = runtime.queue_ids()
            own_prompt = isinstance(prompt_id, str) and prompt_id in queue['queue_running']
            observed_engine = observed_engine or own_prompt
            observed_lease = observed_lease or (own_prompt and forge_holder(dispatcher['pid']))
        journal['jobs'][expected['kind']].update(state=state, forge_lease_observed=observed_lease, engine_execution_observed=observed_engine)
        if state in ('FAILED', 'CANCELLED', 'BLOCKED'):
            reason = job.get('reason')
            journal['jobs'][expected['kind']]['reason'] = reason if isinstance(reason, str) and CODE_RE.fullmatch(reason) else 'HOLD_MEDIA_ACCEPTANCE_JOB_TERMINAL'
            write_record(journal_path, journal)
            fail('HOLD_MEDIA_ACCEPTANCE_GENERATION_' + state)
        if state == 'COMPLETED' and job.get('generation_verified') is True and job.get('gpu1_released') is True:
            final = claim_projection(task, job_id, dispatcher['pid'], require_done=True)
            if final:
                if not observed_lease or not observed_engine:
                    fail('HOLD_MEDIA_ACCEPTANCE_EXECUTION_NOT_OBSERVED')
                if job.get('training_resume') != 'TRAINING_PREVIOUSLY_HELD':
                    fail('HOLD_MEDIA_ACCEPTANCE_TRAINING_RESUME_STATE')
                journal['jobs'][expected['kind']].update(claim=final, state='COMPLETED', generation_verified=True,
                    workflow_sha256=job.get('workflow_sha256'), generation_seconds=round(job['finished_at']-job['generation_started_at'], 3))
                write_record(journal_path, journal)
                return job
        write_record(journal_path, journal)
        time.sleep(1)
    fail('WAIT_MEDIA_ACCEPTANCE_GENERATION_PENDING')


def final_unload(runtime, config, flags, engine_before):
    result = {'forge_lease_reacquired': False, 'forge_lease_released': False, 'training_started': False}
    with lease(STATE / 'owner_maintenance.lock', shared=True), lease(STATE / 'media/controller.lock'), lease(STATE / 'forge_training.lock'):
        result['forge_lease_reacquired'] = True
        training_guard(runtime, flags)
        if runtime.engine_identity(config) != engine_before:
            fail('HOLD_MEDIA_ACCEPTANCE_ENGINE_CHANGED')
        no_other_jobs(runtime)
        queue = runtime.queue_ids()
        if queue['queue_running'] or queue['queue_pending']:
            fail('WAIT_MEDIA_ACCEPTANCE_ENGINE_OTHER_WORK')
        runtime.engine('/free', {'unload_models': True, 'free_memory': True})
        deadline = time.monotonic() + 25
        while True:
            gpu = runtime.gpu1()
            if gpu['free_mib'] >= 30000:
                break
            if time.monotonic() >= deadline:
                fail('HOLD_MEDIA_ACCEPTANCE_GPU_NOT_RELEASED')
            time.sleep(1)
        _, trainer = training_guard(runtime, flags)
        result.update(gpu1=gpu, trainer=trainer, original_flags_preserved=True, **flags)
    result['forge_lease_released'] = True
    return result


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'\d{6,20}', request) or not re.fullmatch(r'[a-f0-9]{40}', source):
        fail('HOLD_MEDIA_ACCEPTANCE_OWNER_CONTEXT')
    directory = STATE / 'owner_media_acceptance'
    journal_path = directory / ('run_' + request + '.json')
    record = {'schema': 'NOX_OWNER_MEDIA_ACCEPTANCE_V1', 'request': request, 'source': source,
              'state': 'STARTING', 'started_at': time.time(), 'jobs': {}, 'artifacts': [],
              'private_text_exported': False, 'pixels_exported': False, 'training_started': False,
              'scope': 'TWO_SYNTHETIC_OWNER_MEDIA_JOBS'}
    client = None; runtime = None; config = None; flags = None; engine_before = None
    with lease(directory / 'acceptance.lock'):
        # A repeated request must inspect the recorded job IDs, never enqueue duplicates.
        write_record(journal_path, record, immutable=True)
        try:
            admitted, raw = sources(); runtime = load_runtime(raw)
            if runtime.media_stop():
                fail('WAIT_MEDIA_ACCEPTANCE_OWNER_STOP_OR_MAINTENANCE')
            config = runtime.configuration(); engine_before = runtime.engine_identity(config)
            flags, trainer = training_guard(runtime)
            dispatcher = dispatcher_identity()
            no_other_jobs(runtime)
            queue = runtime.queue_ids()
            if queue['queue_running'] or queue['queue_pending']:
                fail('WAIT_MEDIA_ACCEPTANCE_ENGINE_OTHER_WORK')
            for case in CASES:
                runtime.assets_for(config, case['kind']); runtime.resource_gate(config, case['kind'])
            anonymous = OwnerClient()
            connection, response = anonymous.connection('/api/ui/media')
            try:
                if response.status != 401:
                    fail('HOLD_MEDIA_ACCEPTANCE_ANONYMOUS_OWNER_ACCESS')
            finally:
                connection.close()
            client = OwnerClient.authenticate()
            capabilities = client.json('/api/ui/media')
            if capabilities.get('schema') != 'NOX_OWNER_MEDIA_V1' or any(capabilities.get(kind) is not True for kind in ('image', 'video')):
                fail('HOLD_MEDIA_ACCEPTANCE_CAPABILITIES')
            record.update(state='AUTHENTICATED_QUEUE_READY', source_pins=admitted, engine=engine_before,
                          dispatcher=dispatcher, original_flags=flags, trainer_before=trainer,
                          anonymous_http=401, signed_owner_session=True)
            write_record(journal_path, record)
            emit('media_acceptance_started', {'request': request, 'state': record['state'], 'runtime_sha256': RUNTIME_SHA})
            for case in CASES:
                if sources()[0] != admitted or dispatcher_identity() != dispatcher:
                    fail('HOLD_MEDIA_ACCEPTANCE_CONTROLLERS_CHANGED')
                training_guard(runtime, flags); no_other_jobs(runtime)
                runtime.resource_gate(config, case['kind'])
                expected = runtime.validate_request(case)
                created = client.json('/api/ui/media/jobs', 'POST', case, status=202)
                job_id = created.get('id')
                if not isinstance(job_id, str) or not JOB_RE.fullmatch(job_id) or created.get('request') != expected:
                    fail('HOLD_MEDIA_ACCEPTANCE_QUEUE_RESPONSE')
                record['jobs'][case['kind']] = {'id': job_id, 'state': created.get('state'), 'request_sha256': digest(json.dumps(expected, sort_keys=True).encode())}
                write_record(journal_path, record)
                deadline = time.monotonic() + (240 if case['kind'] == 'image' else 420)
                job = wait_job(runtime, client, job_id, expected, dispatcher, flags, deadline, record, journal_path)
                artifact = verify_artifact(runtime, config, job, client)
                record['artifacts'].append(artifact)
                write_record(journal_path, record)
                emit('media_acceptance_artifact', artifact)
            record['release'] = final_unload(runtime, config, flags, engine_before)
            if sources()[0] != admitted or dispatcher_identity() != dispatcher:
                fail('HOLD_MEDIA_ACCEPTANCE_CONTROLLERS_CHANGED')
            record.update(state='GENERATED_DECODED_AND_GPU_RELEASED', finished_at=time.time(), generation_verified=True)
            path = directory / ('accepted_' + request + '.json')
            sha = write_record(path, record, immutable=True)
            write_record(journal_path, record)
            emit('media_acceptance', {'state': record['state'], 'schema': record['schema'], 'receipt': str(path),
                 'receipt_sha256': sha, 'request': request, 'source': source, 'artifacts': record['artifacts'],
                 'release': record['release'], 'pixels_exported': False})
            return 0
        except Exception as exc:
            record.update(state='MEDIA_ACCEPTANCE_PENDING_OR_FAILED', reason=safe_error(exc), finished_at=time.time(), generation_verified=False)
            # Only idle engines can be unloaded. Pending owner work is allowed to drain.
            if runtime is not None and config is not None and flags is not None and engine_before is not None:
                try:
                    record['release_after_failure'] = final_unload(runtime, config, flags, engine_before)
                except Exception as cleanup:
                    record['release_after_failure'] = {'state': safe_error(cleanup), 'gpu_release_verified': False}
            write_record(journal_path, record)
            path = directory / ('pending_' + request + '.json')
            sha = write_record(path, record, immutable=True)
            emit('media_acceptance', {'state': record['state'], 'reason': record['reason'], 'receipt': str(path),
                 'receipt_sha256': sha, 'request': request, 'source': source,
                 'jobs': {kind: {'id': value['id'], 'state': value.get('state')} for kind, value in record['jobs'].items()},
                 'artifacts_verified': len(record['artifacts']), 'training_started': False})
            return 1
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    client.cookie = None


if __name__ == '__main__':
    try:
        exit_code = main()
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
        raise SystemExit(exit_code)
    except Exception as exc:
        emit('media_acceptance', {'state': 'BLOCKED', 'reason': safe_error(exc), 'training_started': False})
        raise SystemExit(1)
