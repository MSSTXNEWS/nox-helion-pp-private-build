#!/usr/bin/env python3
"""Image/video jobs in the existing NOX dispatcher and authenticated chat app.

Only two fixed, locally validated ComfyUI graphs are admitted. This module does
not install models, accept arbitrary workflows, start another NOX backend, or
kill processes. GPU1 shares the hybrid trainer's actual flock lease.
"""
from __future__ import annotations
import asyncio
from contextlib import contextmanager
from owner_media_idempotency import create_or_resume, repair_queued_inbox, IdempotencyHold
import fcntl
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request

ROOT = Path('/root/nox')
CONFIG = 'config/owner_media_runtime.json'
BASE = 'http://127.0.0.1:8188'
SERVICE = 'nox-media-comfyui'
TRAIN_SERVICE = 'nox-train-volta-t866u'
PATCH_MARKER = 'NOX_OWNER_MEDIA_BIND_V1'
JOB_ID = re.compile(r'^[0-9a-f]{32}$')
SHA = re.compile(r'^[0-9a-f]{64}$')
TERMINAL = {'COMPLETED', 'FAILED', 'CANCELLED', 'BLOCKED'}
ACTIVE = {'QUEUED', 'YIELDING_TRAINING', 'WAITING_RESOURCES', 'RUNNING', 'SUBMITTING', 'CANCEL_REQUESTED'}
_LOCK = threading.RLock()
WORKFLOW_SOURCES = {
    'image': 'https://huggingface.co/ByteDance/SDXL-Lightning/blob/main/comfyui/sdxl_lightning_workflow_full.json',
    'video': 'https://comfyanonymous.github.io/ComfyUI_examples/wan/text_to_video_wan.json',
}


class MediaHold(RuntimeError):
    pass


def now():
    return time.time()


def read_json(path, limit=262144):
    path = Path(path)
    try:
        if path.is_symlink() or path.stat().st_size > limit:
            return None
        return json.loads(path.read_text())
    except (OSError, ValueError, UnicodeError):
        return None


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.parent.is_symlink():
        raise MediaHold('HOLD_MEDIA_STATE_SYMLINK')
    fd, temporary = tempfile.mkstemp(prefix='.media-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def file_sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def job_path(job_id):
    if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
        raise MediaHold('INVALID_JOB_ID')
    return ROOT / 'state/media/jobs' / (job_id + '.json')


def load_job(job_id):
    value = read_json(job_path(job_id))
    if not isinstance(value, dict) or value.get('id') != job_id:
        raise MediaHold('MEDIA_JOB_NOT_FOUND')
    return value


def update_job(job, **fields):
    lockpath = job_path(job['id']).with_suffix('.lock')
    lockpath.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lockpath, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        # Never reconstruct a missing/corrupt durable job from stale worker RAM.
        # The prior `or job` fallback silently replaced S03 evidence on errors.
        current = read_json(job_path(job['id']))
        if not isinstance(current, dict) or current.get('id') != job['id']:
            raise MediaHold('HOLD_MEDIA_JOB_STATE_UNREADABLE')
        current.update(fields, updated_at=now())
        if job.get('cancel_requested'):
            current['cancel_requested'] = True
        atomic(job_path(job['id']), current)
        job.clear(); job.update(current)
    finally:
        os.close(fd)
    return job


def command(args, timeout=5):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout[:16000]
    except (OSError, subprocess.TimeoutExpired):
        return 99, ''


def service_state(name):
    if name not in (SERVICE, TRAIN_SERVICE):
        raise MediaHold('HOLD_SERVICE_NOT_ALLOWLISTED')
    rc, output = command(['supervisorctl', 'status', name])
    match = re.match(r'^' + re.escape(name) + r'\s+([A-Z]+)(?:\s+pid\s+(\d+))?', output.strip())
    return {'state': match[1] if match else 'UNKNOWN', 'pid': int(match[2]) if match and match[2] else None, 'rc': rc}


def maintenance_busy():
    try:
        fd = os.open(ROOT / 'state/owner_maintenance.lock', os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
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


def media_stop():
    flags = [ROOT / name for name in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')]
    flags.append(Path('/workspace/NOX_STOP'))
    return maintenance_busy() or any(path.exists() or path.is_symlink() for path in flags)


@contextmanager
def exclusive(path, *, wait_seconds=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        # The default is unchanged: nonblocking for other exclusive leases.
        # Media jobs alone may wait briefly for another request's short commit.
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MediaHold('WAIT_RESOURCE_LEASE') from None
                time.sleep(min(0.02, remaining))
        yield fd
    finally:
        os.close(fd)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise MediaHold('HOLD_ENGINE_REDIRECT')


def engine(path, data=None, limit=4 * 1024 * 1024):
    if not path.startswith('/') or '://' in path:
        raise MediaHold('HOLD_ENGINE_PATH')
    request = urllib.request.Request(BASE + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type': 'application/json'}, method='POST' if data is not None else 'GET')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=8) as response:
            raw = response.read(limit + 1)
        if len(raw) > limit:
            raise MediaHold('HOLD_ENGINE_RESPONSE_SIZE')
        return json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError):
        raise MediaHold('HOLD_MEDIA_ENGINE_UNAVAILABLE') from None


def configuration():
    config = read_json(ROOT / CONFIG)
    if not isinstance(config, dict) or config.get('enabled') is not True:
        raise MediaHold('HOLD_MEDIA_NOT_INSTALLED')
    if config.get('engine_service') != SERVICE:
        raise MediaHold('HOLD_MEDIA_SERVICE_UNVERIFIED')
    for key in ('engine_root', 'output_root', 'python'):
        value = config.get(key)
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise MediaHold('HOLD_MEDIA_CONFIG_PATH')
    output = Path(config['output_root']).resolve()
    if output == ROOT or ROOT not in output.parents:
        raise MediaHold('HOLD_MEDIA_OUTPUT_ROOT')
    if not isinstance(config.get('assets'), list):
        raise MediaHold('HOLD_MEDIA_ASSETS_UNVERIFIED')
    return config


def engine_identity(config):
    state = service_state(SERVICE)
    if state['state'] != 'RUNNING' or not state['pid']:
        raise MediaHold('HOLD_MEDIA_ENGINE_NOT_RUNNING')
    proc = Path('/proc') / str(state['pid'])
    try:
        argv = proc.joinpath('cmdline').read_bytes().decode().strip('\0').split('\0')
        environment = proc.joinpath('environ').read_bytes().decode().split('\0')
        cuda = next((item.partition('=')[2] for item in environment if item.startswith('CUDA_VISIBLE_DEVICES=')), None)
        cwd = proc.joinpath('cwd').resolve()
        script = Path(config['engine_root']) / 'main.py'
        has_script = str(script) in argv or ('main.py' in argv and cwd == Path(config['engine_root']).resolve())
        stat = proc.joinpath('stat').read_text().split(') ', 1)[1].split()
        if cuda != '1' or not has_script or stat[0] in ('Z', 'X'):
            raise MediaHold('HOLD_MEDIA_GPU_IDENTITY')
        return {'pid': state['pid'], 'start_ticks': stat[19], 'physical_gpu': 1}
    except (OSError, ValueError, IndexError):
        raise MediaHold('HOLD_MEDIA_PROCESS_UNVERIFIED') from None


def assets_for(config, kind):
    required = {'checkpoint'} if kind == 'image' else {'unet', 'clip', 'vae'}
    assets = {}
    for row in config['assets']:
        if not isinstance(row, dict) or row.get('kind') != kind or row.get('role') not in required:
            continue
        name = row.get('filename')
        path = Path(row.get('path') or '')
        try:
            stat = path.stat()
            valid = (row.get('verified') is True and isinstance(name, str) and Path(name).name == name
                     and isinstance(row.get('sha256'), str) and SHA.fullmatch(row['sha256'])
                     and type(row.get('bytes')) is int and stat.st_size == row['bytes']
                     and type(row.get('stat_mtime_ns')) is int and stat.st_mtime_ns == row['stat_mtime_ns']
                     and stat.st_size > 100_000_000)
        except OSError:
            valid = False
        if valid:
            assets[row['role']] = row
    if set(assets) != required:
        raise MediaHold('HOLD_' + kind.upper() + '_WEIGHTS_NOT_VERIFIED')
    return assets


def validate_request(data):
    if not isinstance(data, dict) or set(data) - {'kind', 'prompt', 'negative_prompt', 'width', 'height', 'frames', 'fps', 'seed'}:
        raise MediaHold('INVALID_MEDIA_REQUEST')
    kind = data.get('kind')
    if kind not in ('image', 'video'):
        raise MediaHold('INVALID_MEDIA_KIND')
    prompt = data.get('prompt')
    negative = data.get('negative_prompt', '')
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2000 or not isinstance(negative, str) or len(negative) > 1000:
        raise MediaHold('INVALID_MEDIA_PROMPT')
    defaults = {'width': 1024, 'height': 1024} if kind == 'image' else {'width': 512, 'height': 320}
    result = {'kind': kind, 'prompt': prompt.strip(), 'negative_prompt': negative, **defaults,
              'frames': 1 if kind == 'image' else 17, 'fps': 8, 'seed': secrets.randbelow(2 ** 32)}
    for key in ('width', 'height', 'frames', 'fps', 'seed'):
        if key in data:
            if type(data[key]) is not int:
                raise MediaHold('INVALID_MEDIA_' + key.upper())
            result[key] = data[key]
    alignment = 64 if kind == 'image' else 16
    if not (256 <= result['width'] <= 1024 and 256 <= result['height'] <= 1024 and result['width'] % alignment == result['height'] % alignment == 0):
        raise MediaHold('INVALID_MEDIA_DIMENSIONS')
    if not 0 <= result['seed'] < 2 ** 53 or not 4 <= result['fps'] <= 16:
        raise MediaHold('INVALID_MEDIA_SEED_OR_FPS')
    if kind == 'image' and result['frames'] != 1:
        raise MediaHold('INVALID_IMAGE_BATCH')
    if kind == 'video' and (result['width'] > 832 or result['height'] > 512 or result['width'] * result['height'] > 832 * 480 or result['frames'] not in (9, 17, 25, 33)):
        raise MediaHold('INVALID_VIDEO_BUDGET')
    return result


def workflow(job, assets):
    settings = job['request']
    prefix = 'nox/' + job['id'] + '/' + settings['kind']
    positive = settings['prompt']
    negative = settings['negative_prompt']
    def node(kind, **inputs):
        return {'class_type': kind, 'inputs': inputs}
    graph = {
        '6': node('CLIPTextEncode', clip=['4', 1], text=positive),
        '7': node('CLIPTextEncode', clip=['4', 1], text=negative),
        '8': node('VAEDecode', samples=['3', 0], vae=['4', 2]),
    }
    if settings['kind'] == 'image':
        graph.update({
            '4': node('CheckpointLoaderSimple', ckpt_name=assets['checkpoint']['filename']),
            '5': node('EmptyLatentImage', width=settings['width'], height=settings['height'], batch_size=1),
            '3': node('KSampler', model=['4', 0], positive=['6', 0], negative=['7', 0], latent_image=['5', 0],
                      seed=settings['seed'], steps=4, cfg=1.0, sampler_name='euler', scheduler='sgm_uniform', denoise=1.0),
            '9': node('SaveImage', images=['8', 0], filename_prefix=prefix),
        })
    else:
        graph['6']['inputs']['clip'] = ['38', 0]
        graph['7']['inputs']['clip'] = ['38', 0]
        graph['8']['inputs']['vae'] = ['39', 0]
        graph.update({
            '37': node('UNETLoader', unet_name=assets['unet']['filename'], weight_dtype='default'),
            '38': node('CLIPLoader', clip_name=assets['clip']['filename'], type='wan', device='default'),
            '39': node('VAELoader', vae_name=assets['vae']['filename']),
            '40': node('EmptyHunyuanLatentVideo', width=settings['width'], height=settings['height'], length=settings['frames'], batch_size=1),
            '48': node('ModelSamplingSD3', model=['37', 0], shift=8.0),
            '3': node('KSampler', model=['48', 0], positive=['6', 0], negative=['7', 0], latent_image=['40', 0],
                      seed=settings['seed'], steps=30, cfg=6.0, sampler_name='uni_pc', scheduler='simple', denoise=1.0),
            '47': node('SaveWEBM', images=['8', 0], filename_prefix=prefix, codec='vp9', fps=float(settings['fps']), crf=32.0),
        })
    return graph


def validate_graph(graph, objects):
    if not isinstance(objects, dict):
        raise MediaHold('HOLD_ENGINE_NODE_INVENTORY')
    for item in graph.values():
        definition = objects.get(item['class_type'])
        if not isinstance(definition, dict):
            raise MediaHold('HOLD_ENGINE_NODE_MISSING_' + item['class_type'])
        allowed = (definition.get('input') or {}).get('required', {})
        allowed = {**allowed, **(definition.get('input') or {}).get('optional', {})}
        required = (definition.get('input') or {}).get('required', {})
        if set(required) - set(item['inputs']):
            raise MediaHold('HOLD_ENGINE_REQUIRED_INPUT_CHANGED')
        for key, value in item['inputs'].items():
            spec = allowed.get(key)
            if not isinstance(spec, list) or not spec:
                raise MediaHold('HOLD_ENGINE_INPUT_CHANGED')
            if isinstance(spec[0], list) and value not in spec[0]:
                raise MediaHold('HOLD_ENGINE_OPTION_OR_MODEL_MISSING')


def queue_ids():
    data = engine('/queue', limit=1024 * 1024)
    if not isinstance(data, dict) or any(not isinstance(data.get(key), list) for key in ('queue_running', 'queue_pending')):
        raise MediaHold('HOLD_ENGINE_QUEUE_UNVERIFIED')
    result = {}
    for key in ('queue_running', 'queue_pending'):
        ids = []
        for item in data[key]:
            if not isinstance(item, list) or len(item) < 2 or not isinstance(item[1], str):
                raise MediaHold('HOLD_ENGINE_QUEUE_UNVERIFIED')
            ids.append(item[1])
        result[key] = ids
    return result


def gpu1():
    rc, output = command(['nvidia-smi', '--id=1', '--query-gpu=memory.total,memory.used,memory.free', '--format=csv,noheader,nounits'])
    fields = [part.strip() for part in output.strip().split(',')]
    if rc or len(fields) != 3 or not all(value.isdigit() for value in fields):
        raise MediaHold('HOLD_GPU1_TELEMETRY')
    return dict(zip(('total_mib', 'used_mib', 'free_mib'), map(int, fields)))


def resource_gate(config, kind):
    if media_stop():
        raise MediaHold('WAIT_OWNER_STOP_OR_MAINTENANCE')
    try:
        memory = int(Path('/sys/fs/cgroup/memory.current').read_text())
        limit = int(Path('/sys/fs/cgroup/memory.max').read_text())
    except (OSError, ValueError):
        raise MediaHold('HOLD_CGROUP_UNVERIFIED') from None
    reserve = max(16 * 1024 ** 3, int(config.get('cgroup_reserve_bytes', 16 * 1024 ** 3)),
                  (16 if kind == 'image' else 24) * 1024 ** 3)
    if limit - memory < reserve:
        raise MediaHold('WAIT_SYSTEM_RAM_HEADROOM')
    disk_reserve = max(6 * 1024 ** 3, int(config.get('disk_reserve_bytes', 6 * 1024 ** 3)))
    if shutil.disk_usage(config['output_root']).free < disk_reserve:
        raise MediaHold('WAIT_OUTPUT_DISK_HEADROOM')
    gpu = gpu1()
    if gpu['free_mib'] < 30000:
        raise MediaHold('WAIT_GPU1_HEADROOM')
    return {'gpu1': gpu, 'memory_current': memory, 'memory_max': limit}


def checkpoint_after(stamp):
    output = ROOT / 'lora/qlora_t866u/runs_owner_hybrid'
    path = output / 'owner_last_result.json'
    receipt = read_json(path)
    if not isinstance(receipt, dict) or receipt.get('state') != 'CHECKPOINTED_OWNER_STOP' or receipt.get('adapter_delta_verified') is not True:
        raise MediaHold('HOLD_FRESH_TRAINING_CHECKPOINT_REQUIRED')
    step = receipt.get('global_step')
    if type(step) is not int or step < 1 or path.stat().st_mtime < stamp:
        raise MediaHold('HOLD_FRESH_TRAINING_CHECKPOINT_REQUIRED')
    checkpoint = output / ('checkpoint-' + str(step))
    required = ('trainer_state.json', 'optimizer.pt', 'scheduler.pt', 'rng_state.pth', 'scaler.pt', 'adapter_config.json', 'adapter_model.safetensors')
    if any(not (checkpoint / name).is_file() or (checkpoint / name).is_symlink() or (checkpoint / name).stat().st_size == 0 for name in required):
        raise MediaHold('HOLD_INCOMPLETE_TRAINING_CHECKPOINT')
    state = read_json(checkpoint / 'trainer_state.json')
    if not isinstance(state, dict) or state.get('global_step') != step:
        raise MediaHold('HOLD_CHECKPOINT_STEP_MISMATCH')
    return {'step': step, 'receipt_sha256': file_sha(path), 'checkpoint': str(checkpoint)}


def prepare_training(job):
    state = service_state(TRAIN_SERVICE)
    yield_path = ROOT / 'state/media/training_yield.json'
    existing = read_json(yield_path)
    if isinstance(existing, dict) and existing.get('active') is True:
        return existing
    if state['state'] in ('STOPPED', 'EXITED', 'FATAL'):
        hold = ROOT / 'state/TRAIN_HOLD.flag'
        record = {'active': False, 'resume': False}
        if not hold.exists() and not hold.is_symlink():
            token = 'OWNER_MEDIA_HOLD ' + job['id'] + '\n'
            fd = os.open(hold, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(fd, 'w') as stream:
                stream.write(token); stream.flush(); os.fsync(stream.fileno())
            record['media_hold_token'] = token
        return record
    if state['state'] != 'RUNNING':
        raise MediaHold('WAIT_TRAINER_TRANSITION')
    wrapper = ROOT / 'scripts/run_train_volta_t866u.sh'
    if wrapper.is_symlink() or '--resume' not in wrapper.read_text():
        raise MediaHold('HOLD_RESUMABLE_TRAINER_WRAPPER_REQUIRED')
    pause = ROOT / 'state/TRAIN_PAUSE_REQUEST.flag'
    hold = ROOT / 'state/TRAIN_HOLD.flag'
    if pause.exists() or pause.is_symlink() or hold.exists() or hold.is_symlink():
        raise MediaHold('WAIT_OWNER_TRAINING_PAUSE')
    token = 'NOX_MEDIA_CHECKPOINT_YIELD ' + job['id'] + '\n'
    requested_at = now()
    fd = os.open(pause, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(token); stream.flush(); os.fsync(stream.fileno())
    record = {'active': True, 'resume': True, 'job_id': job['id'], 'requested_at': requested_at,
              'pause_token': token, 'wrapper_sha256': file_sha(wrapper), 'trainer_before': state}
    atomic(yield_path, record)
    return record


def wait_training(job, yielded):
    deadline = now() + 180
    while True:
        if media_stop():
            raise MediaHold('WAIT_OWNER_STOP_OR_MAINTENANCE')
        state = service_state(TRAIN_SERVICE)
        if state['state'] in ('STOPPED', 'EXITED', 'FATAL'):
            if yielded.get('active'):
                proof = checkpoint_after(yielded['requested_at'])
                hold = ROOT / 'state/TRAIN_HOLD.flag'
                try:
                    content = hold.read_text()
                except OSError:
                    raise MediaHold('HOLD_TRAINING_STOP_ACKNOWLEDGEMENT') from None
                if not content.startswith('OWNER_HYBRID_BOUNDED_COMPLETE request='):
                    raise MediaHold('HOLD_TRAINING_STOP_ACKNOWLEDGEMENT')
                yielded.update(checkpoint=proof, hold_sha256=hashlib.sha256(content.encode()).hexdigest())
                atomic(ROOT / 'state/media/training_yield.json', yielded)
            return
        if now() > deadline:
            raise MediaHold('WAIT_CHECKPOINT_TIMEOUT')
        update_job(job, state='YIELDING_TRAINING')
        time.sleep(2)


def any_other_pending(job_id):
    for path in (ROOT / 'state/media/jobs').glob('*.json'):
        value = read_json(path)
        if isinstance(value, dict) and value.get('id') != job_id and value.get('state') in ACTIVE:
            return True
    return False


def resume_training(job, config, yielded):
    if not yielded.get('active') or not yielded.get('resume'):
        if yielded.get('media_hold_token'):
            hold = ROOT / 'state/TRAIN_HOLD.flag'
            if not hold.is_symlink() and hold.read_text() == yielded['media_hold_token']:
                hold.unlink()
        return 'TRAINING_PREVIOUSLY_HELD'
    if config.get('resume_training_after_media') is not True or media_stop() or any_other_pending(job['id']):
        return 'TRAINING_REMAINS_CHECKPOINTED'
    pause = ROOT / 'state/TRAIN_PAUSE_REQUEST.flag'
    hold = ROOT / 'state/TRAIN_HOLD.flag'
    wrapper = ROOT / 'scripts/run_train_volta_t866u.sh'
    if (pause.is_symlink() or hold.is_symlink() or wrapper.is_symlink()
            or pause.read_text() != yielded['pause_token'] or file_sha(hold) != yielded.get('hold_sha256')
            or file_sha(wrapper) != yielded['wrapper_sha256']):
        raise MediaHold('HOLD_TRAINING_OWNER_FLAGS_CHANGED')
    checkpoint_after(yielded['requested_at'])
    if gpu1()['free_mib'] < 30000:
        raise MediaHold('HOLD_GPU1_NOT_RELEASED_FOR_TRAINING')
    # Only our pause request and its matching fresh wrapper acknowledgement go.
    pause.unlink(); hold.unlink()
    rc, _ = command(['supervisorctl', 'start', TRAIN_SERVICE], timeout=15)
    after = service_state(TRAIN_SERVICE)
    yielded.update(active=False, resumed_at=now(), resume_state=after['state'], resume_rc=rc)
    atomic(ROOT / 'state/media/training_yield.json', yielded)
    if rc or after['state'] not in ('RUNNING', 'STARTING'):
        raise MediaHold('HOLD_TRAINING_RESUME_NOT_RUNNING')
    return 'TRAINING_RESUME_REQUESTED'


def output_path(config, job_id, item):
    if not isinstance(item, dict) or item.get('type') != 'output':
        raise MediaHold('HOLD_OUTPUT_KIND')
    filename = item.get('filename')
    subfolder = item.get('subfolder', '')
    if not isinstance(filename, str) or Path(filename).name != filename or not isinstance(subfolder, str):
        raise MediaHold('HOLD_OUTPUT_PATH')
    expected = Path(config['output_root']).resolve() / 'nox' / job_id
    candidate = Path(config['output_root']) / subfolder / filename
    if candidate.is_symlink() or candidate.resolve().parent != expected or not candidate.is_file():
        raise MediaHold('HOLD_OUTPUT_SCOPE')
    if candidate.stat().st_size <= 0 or candidate.stat().st_size > 256 * 1024 ** 2:
        raise MediaHold('HOLD_OUTPUT_SIZE')
    return candidate


def validate_output(config, job, path):
    kind = job['request']['kind']
    if kind == 'image':
        if path.suffix.lower() != '.png':
            raise MediaHold('HOLD_IMAGE_FORMAT')
        with path.open('rb') as handle:
            if handle.read(8) != b'\x89PNG\r\n\x1a\n':
                raise MediaHold('HOLD_IMAGE_HEADER')
        code = "from PIL import Image;import sys,json;im=Image.open(sys.argv[1]);im.verify();im=Image.open(sys.argv[1]);print(json.dumps({'width':im.width,'height':im.height,'frames':getattr(im,'n_frames',1)}))"
    else:
        if path.suffix.lower() != '.webm':
            raise MediaHold('HOLD_VIDEO_FORMAT')
        code = "import av,sys,json;c=av.open(sys.argv[1]);s=c.streams.video[0];n=sum(1 for f in c.decode(s));print(json.dumps({'width':s.width,'height':s.height,'frames':n}));c.close()"
    rc, output = command([config['python'], '-c', code, str(path)], timeout=30)
    try:
        proof = json.loads(output)
    except ValueError:
        proof = None
    expected = job['request']
    if rc or not isinstance(proof, dict) or any(proof.get(key) != expected[key] for key in ('width', 'height', 'frames')):
        raise MediaHold('HOLD_OUTPUT_DECODE_VERIFICATION')
    return {'filename': path.name, 'subfolder': 'nox/' + job['id'], 'type': 'output',
            'bytes': path.stat().st_size, 'sha256': file_sha(path), **proof,
            'media_type': 'image/png' if kind == 'image' else 'video/webm'}


def extract_outputs(config, job, history):
    if not isinstance(history, dict):
        raise MediaHold('HOLD_ENGINE_HISTORY_SCHEMA')
    status = history.get('status') or {}
    if status.get('completed') is not True or status.get('status_str') != 'success':
        raise MediaHold('HOLD_GENERATION_NOT_SUCCESSFUL')
    outputs = history.get('outputs')
    if not isinstance(outputs, dict):
        raise MediaHold('HOLD_ENGINE_OUTPUT_SCHEMA')
    items = []
    for value in outputs.values():
        if isinstance(value, dict):
            for key in ('images', 'gifs', 'videos'):
                if isinstance(value.get(key), list):
                    items.extend(value[key])
    if not 1 <= len(items) <= 4:
        raise MediaHold('HOLD_OUTPUT_COUNT')
    return [validate_output(config, job, output_path(config, job['id'], item)) for item in items]


def poll_generation(config, job):
    deadline = now() + (600 if job['request']['kind'] == 'image' else 1800)
    prompt_id = job['prompt_id']
    while True:
        latest = load_job(job['id'])
        cancelled = latest.get('cancel_requested') is True or media_stop()
        if cancelled:
            update_job(job, state='CANCEL_REQUESTED', cancel_requested=True)
            queue = queue_ids()
            if prompt_id in queue['queue_pending']:
                engine('/queue', {'delete': [prompt_id]})
                return 'CANCELLED', []
            # This pinned engine has a global interrupt. Never hit another job.
            # Running work drains naturally; no process kill or global cancel.
        history = engine('/history/' + urllib.parse.quote(prompt_id, safe=''), limit=1024 * 1024)
        entry = history.get(prompt_id) if isinstance(history, dict) else None
        if isinstance(entry, dict):
            outputs = extract_outputs(config, job, entry)
            return ('CANCELLED' if cancelled else 'COMPLETED'), outputs
        if now() >= deadline:
            raise MediaHold('HOLD_GENERATION_DEADLINE_UNRESOLVED')
        time.sleep(2)


def run_media_task(task):
    job_id = (task.get('params') or {}).get('job_id')
    try:
        job = load_job(job_id)
        if job['state'] in TERMINAL:
            return (True if job['state'] in ('COMPLETED', 'CANCELLED') else False), public_job(job)
        if job.get('cancel_requested') is True and not job.get('prompt_id'):
            update_job(job, state='CANCELLED')
            return True, public_job(job)
        config = configuration()
        engine_identity(config)
        assets = assets_for(config, job['request']['kind'])
        graph = workflow(job, assets)
        validate_graph(graph, engine('/object_info'))
        yielded = {'active': False}
        released = False
        with exclusive(ROOT / 'state/media/controller.lock'):
            if media_stop():
                raise MediaHold('WAIT_OWNER_STOP_OR_MAINTENANCE')
            yielded = prepare_training(job)
            wait_training(job, yielded)
            with exclusive(ROOT / 'state/forge_training.lock'):
                budget = resource_gate(config, job['request']['kind'])
                engine_identity(config)
                queue = queue_ids()
                known = job.get('prompt_id')
                active = queue['queue_running'] + queue['queue_pending']
                if any(value != known for value in active):
                    raise MediaHold('WAIT_ENGINE_HAS_OTHER_WORK')
                if not known and load_job(job['id']).get('cancel_requested'):
                    final_state, outputs = 'CANCELLED', []
                else:
                    if not known:
                        update_job(job, state='SUBMITTING', budget=budget, workflow_sha256=hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest())
                        response = engine('/prompt', {'prompt': graph, 'client_id': job['id']})
                        prompt_id = response.get('prompt_id') if isinstance(response, dict) else None
                        if not isinstance(prompt_id, str) or not re.fullmatch(r'[A-Za-z0-9-]{16,80}', prompt_id) or response.get('node_errors'):
                            raise MediaHold('HOLD_ENGINE_PROMPT_REJECTED')
                        update_job(job, state='RUNNING', prompt_id=prompt_id, generation_started_at=now())
                    final_state, outputs = poll_generation(config, job)
                update_job(job, state=final_state, outputs=outputs, finished_at=now(),
                           generation_verified=final_state == 'COMPLETED', workflow_source=WORKFLOW_SOURCES[job['request']['kind']])
                try:
                    queue = queue_ids()
                    if not queue['queue_running'] and not queue['queue_pending']:
                        engine('/free', {'unload_models': True, 'free_memory': True})
                        for attempt in range(15):
                            if gpu1()['free_mib'] >= 30000:
                                released = True
                                break
                            time.sleep(1)
                except MediaHold as exc:
                    update_job(job, resource_release_reason=str(exc))
            # The shared forge lease must be released before starting a trainer.
            if released:
                try:
                    resume = resume_training(job, config, yielded)
                except (MediaHold, OSError) as exc:
                    resume = str(exc) if isinstance(exc, MediaHold) else 'HOLD_TRAINING_RESUME_IO'
                update_job(job, training_resume=resume, gpu1_released=True)
            else:
                update_job(job, training_resume='HOLD_GPU1_RELEASE_NOT_VERIFIED', gpu1_released=False)
        return True, public_job(job)
    except MediaHold as exc:
        reason = str(exc)
        if 'job' in locals():
            state = 'WAITING_RESOURCES' if reason.startswith('WAIT_') else 'BLOCKED'
            update_job(job, state=state, reason=reason)
        return ('wait' if reason.startswith('WAIT_') else False), {'state': reason, 'job_id': job_id, 'generation_verified': False}
    except Exception as exc:
        if 'job' in locals():
            update_job(job, state='BLOCKED', reason='HOLD_MEDIA_' + type(exc).__name__)
        return False, {'state': 'HOLD_MEDIA_' + type(exc).__name__, 'job_id': job_id, 'generation_verified': False}


def public_job(job):
    public = {key: job[key] for key in ('id', 'state', 'created_at', 'updated_at', 'reason', 'generation_verified', 'training_resume', 'gpu1_released', 'cancel_requested') if key in job}
    public['kind'] = job['request']['kind']
    public['request'] = job['request']
    public['outputs'] = [{key: value for key, value in item.items() if key != 'subfolder'} |
                         {'url': '/api/ui/media/jobs/' + job['id'] + '/outputs/' + str(index)} for index, item in enumerate(job.get('outputs', []))]
    return public


def capabilities():
    result = {'schema': 'NOX_OWNER_MEDIA_V1', 'image': False, 'video': False, 'generation_verified': {},
              'queue_limit': 3, 'concurrent_gpu_jobs': 1, 'idempotency_v1': True, 'backend': 'EXISTING_NOX_DISPATCHER_COMFYUI'}
    try:
        config = configuration()
        engine_identity(config)
        objects = engine('/object_info')
        for kind in ('image', 'video'):
            try:
                assets = assets_for(config, kind)
                fixture = {'id': '0' * 32, 'request': validate_request({'kind': kind, 'prompt': 'availability check only'})}
                validate_graph(workflow(fixture, assets), objects)
                result[kind] = True
            except MediaHold as exc:
                result[kind + '_reason'] = str(exc)
        result['state'] = 'AVAILABLE_FOR_GENERATION' if result['image'] or result['video'] else 'BLOCKED'
    except MediaHold as exc:
        result.update(state='BLOCKED', reason=str(exc))
    return result



@contextmanager
def _media_jobs_lock():
    # Reuse the only existing inter-process media.jobs lock, never a second ledger.
    with _LOCK, exclusive(ROOT / 'state/media/jobs.lock', wait_seconds=0.25):
        yield


def _new_media_record(request, owner):
    # Invoked only inside _media_jobs_lock by keyed or legacy create.
    # Commit-time STOP fence: a service can enter STOP after remote preflight.
    # Recovery/replay of an already-durable keyed job remains read-only and allowed.
    if media_stop():
        raise MediaHold('HOLD_MEDIA_STOP')
    jobs = [read_json(path) for path in (ROOT / 'state/media/jobs').glob('*.json')]
    if any(not isinstance(value, dict) for value in jobs):
        raise MediaHold('HOLD_MEDIA_JOB_INDEX_UNREADABLE')
    if sum(value.get('state') in ACTIVE for value in jobs) >= 3:
        raise MediaHold('WAIT_MEDIA_QUEUE_FULL')
    if len(jobs) >= 200:
        raise MediaHold('HOLD_MEDIA_JOB_HISTORY_QUOTA')
    total = sum(item.get('bytes', 0) for value in jobs
                for item in value.get('outputs', []) if isinstance(item, dict))
    if total >= 2 * 1024 ** 3:
        raise MediaHold('HOLD_MEDIA_OUTPUT_QUOTA')
    return {'schema': 'NOX_OWNER_MEDIA_JOB_V1', 'id': secrets.token_hex(16),
            'owner': owner, 'request': request, 'state': 'QUEUED',
            'created_at': now(), 'updated_at': now(),
            'generation_verified': False, 'outputs': []}


def _media_preflight(data):
    request = validate_request(data)
    status = capabilities()
    if not status.get(request['kind']):
        raise MediaHold(status.get(request['kind'] + '_reason',
                                   status.get('reason', 'HOLD_MEDIA_NOT_READY')))
    return request


def create_job(data, owner='native-owner'):
    if not isinstance(data, dict):
        raise MediaHold('INVALID_MEDIA_REQUEST')
    if 'client_request_id' in data:
        # The submitted payload is pinned before validate_request creates a random seed.
        try:
            record = create_or_resume(
                data, owner, lock=_media_jobs_lock,
                jobs_dir=ROOT / 'state/media/jobs',
                inbox_dir=ROOT / 'state/media/inbox', read_json=read_json,
                atomic=atomic, preflight=_media_preflight,
                new_job=lambda payload: _new_media_record(validate_request(payload), owner))
        except IdempotencyHold as exc:
            raise MediaHold(str(exc)) from None
        return public_job(record)

    # Preserve the legacy unkeyed caller until the same-origin browser is upgraded.
    request = _media_preflight(data)
    with _media_jobs_lock():
        record = _new_media_record(request, owner)
        atomic(job_path(record['id']), record)
        atomic(ROOT / 'state/media/inbox' / (record['id'] + '.json'), {'job_id': record['id']})
        return public_job(record)


def lookup_media_request(owner, client_request_id):
    if (type(client_request_id) is not str or not JOB_ID.fullmatch(client_request_id)
            or type(owner) is not str or not owner or len(owner) > 256):
        raise MediaHold('INVALID_MEDIA_CLIENT_REQUEST_ID')
    with _media_jobs_lock():
        found = None
        for path in sorted((ROOT / 'state/media/jobs').glob('*.json')):
            item = read_json(path)
            if (path.is_symlink() or not isinstance(item, dict) or
                    item.get('id') != path.stem or not JOB_ID.fullmatch(path.stem)):
                raise MediaHold('HOLD_MEDIA_JOB_INDEX_UNREADABLE')
            if item.get('owner') == owner and item.get('client_request_id') == client_request_id:
                if found is not None:
                    raise MediaHold('HOLD_MEDIA_DUPLICATE_REQUEST_ID')
                found = item
        if found is None:
            raise MediaHold('MEDIA_JOB_NOT_FOUND')
        if found.get('state') == 'QUEUED':
            try:
                repair_queued_inbox(ROOT / 'state/media/inbox', found['id'],
                                    read_json, atomic)
            except IdempotencyHold as exc:
                raise MediaHold(str(exc)) from None
        return public_job(found)


def ingest_media_tasks(state):
    count = 0
    # Scan past durable inbox receipts for already-ingested or terminal jobs.
    # Cap only NEW admissions; limiting the candidate scan to three starves
    # later requests after three older inbox records survive in S03.
    for path in sorted((ROOT / 'state/media/inbox').glob('*.json')):
        if count >= 3:
            break
        value = read_json(path)
        job_id = value.get('job_id') if isinstance(value, dict) else None
        if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id) or path.stem != job_id:
            continue
        try:
            job = load_job(job_id)
        except MediaHold as exc:
            if str(exc) != 'MEDIA_JOB_NOT_FOUND':
                raise
            # An orphan inbox receipt cannot be executed, but must not
            # starve unrelated queued jobs. Preserve it for reconciliation.
            # Only a genuinely absent job file is skippable: corrupted or
            # symlinked state must retain the existing fail-closed behavior.
            try:
                os.lstat(job_path(job_id))
            except FileNotFoundError:
                continue
            raise
        task_id = 'owner.media.' + job_id
        if task_id in state.setdefault('tasks', {}) or job.get('state') != 'QUEUED':
            continue
        state['tasks'][task_id] = {'id': task_id, 'handler': 'owner_media', 'class': 'owner_order', 'priority': 0,
            'status': 'pending', 'deps': [], 'locks': ['gpu1'], 'params': {'job_id': job_id},
            'title': 'Owner ' + job['request']['kind'] + ' generation', 'retries': 0, 'max_retries': 1,
            'timeout_sec': 2100, 'source': 'authenticated_owner_media'}
        count += 1
    return count


def media_task_admitted(task):
    job_id = (task.get('params') or {}).get('job_id')
    return (isinstance(job_id, str) and bool(JOB_ID.fullmatch(job_id)) and task.get('id') == 'owner.media.' + job_id
            and task.get('class') == 'owner_order' and task.get('locks') == ['gpu1'] and not media_stop())


def bind_dispatcher(namespace):
    if namespace.get('_owner_media_bound'):
        return
    for name in ('HANDLERS', 'ingest_owner_orders', '_nox_owner_task_admitted'):
        if name not in namespace:
            raise MediaHold('HOLD_MEDIA_DISPATCHER_CALLBACK_' + name)
    original_ingest = namespace['ingest_owner_orders']
    original_admission = namespace['_nox_owner_task_admitted']
    def ingest(state):
        original_ingest(state)
        ingest_media_tasks(state)
    def admission(task):
        if task.get('handler') == 'owner_media':
            return media_task_admitted(task)
        return original_admission(task)
    namespace['HANDLERS']['owner_media'] = run_media_task
    namespace['ingest_owner_orders'] = ingest
    namespace['_nox_owner_task_admitted'] = admission
    namespace['_owner_media_bound'] = True


def patch_dispatcher_media(source, expected_sha256):
    if PATCH_MARKER in source:
        compile(source, '<dispatcher-media>', 'exec')
        return source
    if not SHA.fullmatch(expected_sha256) or hashlib.sha256(source.encode()).hexdigest() != expected_sha256:
        raise MediaHold('HOLD_NATIVE_DISPATCHER_SOURCE_CHANGED')
    anchor = 'if __name__ == "__main__":'
    if source.count(anchor) != 1:
        raise MediaHold('HOLD_MEDIA_DISPATCHER_ANCHOR')
    addition = '# ' + PATCH_MARKER + '\nimport owner_media_runtime\nowner_media_runtime.bind_dispatcher(globals())\n\n'
    updated = source.replace(anchor, addition + anchor, 1)
    compile(updated, '<dispatcher-media>', 'exec')
    return updated


def verified_export_path(config, job, item):
    """Bind a served asset to its completed job's recorded bytes and MIME."""
    expected = {'image': ('image/png', '.png'), 'video': ('video/webm', '.webm')}.get(
        (job.get('request') or {}).get('kind'))
    if (job.get('generation_verified') is not True or expected is None
            or not isinstance(item, dict) or item.get('media_type') != expected[0]
            or not isinstance(item.get('sha256'), str) or not SHA.fullmatch(item['sha256'])
            or type(item.get('bytes')) is not int):
        raise MediaHold('HOLD_OUTPUT_VERIFICATION_MISSING')
    try:
        path = output_path(config, job['id'], item)
        if (path.suffix.lower() != expected[1] or path.stat().st_size != item['bytes']
                or file_sha(path) != item['sha256']):
            raise MediaHold('HOLD_OUTPUT_CHANGED')
        return path
    except OSError:
        raise MediaHold('HOLD_OUTPUT_CHANGED') from None


def register_media(app, trusted):
    """Mount inside the existing owner-authenticated FastAPI application only."""
    from starlette.requests import Request
    from starlette.responses import JSONResponse, FileResponse
    globals()['Request'] = Request
    if not callable(trusted.get('_session_ok')) or not callable(trusted.get('_unauthorized')):
        raise MediaHold('HOLD_MEDIA_OWNER_AUTH_CALLBACK')
    if any(getattr(route, 'path', '').startswith('/api/ui/media') for route in app.routes):
        raise MediaHold('HOLD_MEDIA_ROUTES_ALREADY_REGISTERED')
    def authorized(request):
        return bool(trusted['_session_ok'](request))
    def same_origin(request):
        origin = request.headers.get('origin')
        return request.headers.get('sec-fetch-site') != 'cross-site' and (
            origin is None or urllib.parse.urlparse(origin).netloc.lower() == request.headers.get('host', '').lower())
    def owner(request):
        callback = trusted.get('_media_owner_id')
        return str(callback(request)) if callable(callback) else 'native-owner'
    def scoped(request, job_id):
        job = load_job(job_id)
        if job.get('owner') != owner(request):
            raise MediaHold('MEDIA_JOB_NOT_FOUND')
        return job
    def error(exc):
        code = str(exc)
        status = (404 if code == 'MEDIA_JOB_NOT_FOUND' else 409 if code == 'HOLD_MEDIA_IDEMPOTENCY_CONFLICT' else 422 if code.startswith('INVALID_') else 503)
        return JSONResponse({'state': 'BLOCKED', 'reason': code}, status_code=status, headers={'Cache-Control': 'no-store'})
    @app.get('/api/ui/media')
    async def media_status(request: Request):
        if not authorized(request):
            return trusted['_unauthorized']()
        return await asyncio.to_thread(capabilities)
    @app.post('/api/ui/media/jobs')
    async def media_create(request: Request):
        if not authorized(request):
            return trusted['_unauthorized']()
        if not same_origin(request):
            return JSONResponse({'error': 'SAME_ORIGIN_REQUIRED'}, status_code=403)
        if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
            return JSONResponse({'error': 'JSON_CONTENT_TYPE_REQUIRED'}, status_code=415)
        try:
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 12000:
                    raise MediaHold('INVALID_MEDIA_REQUEST_SIZE')
            data = json.loads(raw)
            return JSONResponse(await asyncio.to_thread(create_job, data, owner(request)), status_code=202)
        except (ValueError, UnicodeError):
            return JSONResponse({'error': 'INVALID_JSON'}, status_code=400)
        except MediaHold as exc:
            return error(exc)
    @app.get('/api/ui/media/requests/{client_request_id}')
    async def media_request_status(request: Request, client_request_id: str):
        if not authorized(request):
            return trusted['_unauthorized']()
        try:
            return await asyncio.to_thread(lookup_media_request, owner(request), client_request_id)
        except MediaHold as exc:
            return error(exc)
    @app.get('/api/ui/media/jobs/{job_id}')
    async def media_job(request: Request, job_id: str):
        if not authorized(request):
            return trusted['_unauthorized']()
        try:
            return public_job(await asyncio.to_thread(scoped, request, job_id))
        except MediaHold as exc:
            return error(exc)
    @app.post('/api/ui/media/jobs/{job_id}/cancel')
    async def media_cancel(request: Request, job_id: str):
        if not authorized(request):
            return trusted['_unauthorized']()
        if not same_origin(request):
            return JSONResponse({'error': 'SAME_ORIGIN_REQUIRED'}, status_code=403)
        try:
            job = await asyncio.to_thread(scoped, request, job_id)
            if job['state'] not in TERMINAL:
                await asyncio.to_thread(update_job, job, cancel_requested=True)
            return public_job(job)
        except MediaHold as exc:
            return error(exc)
    @app.get('/api/ui/media/jobs/{job_id}/outputs/{index}')
    async def media_output(request: Request, job_id: str, index: int):
        if not authorized(request):
            return trusted['_unauthorized']()
        try:
            job = await asyncio.to_thread(scoped, request, job_id)
            if job['state'] != 'COMPLETED' or not 0 <= index < len(job.get('outputs', [])):
                raise MediaHold('MEDIA_JOB_NOT_FOUND')
            item = job['outputs'][index]
            path = await asyncio.to_thread(verified_export_path, configuration(), job, item)
            return FileResponse(path, media_type=item['media_type'], filename=path.name,
                content_disposition_type='inline', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
        except MediaHold as exc:
            return error(exc)
    return {'prefix': '/api/ui/media', 'owner_auth': 'EXISTING_NATIVE_SESSION', 'backend_created': False}
