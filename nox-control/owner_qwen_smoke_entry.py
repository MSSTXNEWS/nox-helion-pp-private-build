#!/usr/bin/env python3
"""Run a tiny Qwen/Volta diagnostic through the existing owner transport.

This changes neither services, model weights nor any owner STOP/HOLD flag.
An observed automatic old-trainer failure flag is passed unchanged by hash.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SMOKE_NAME = 'owner_qwen_runtime_smoke.py'
SMOKE_SHA = '3d92e3dd0a50bf928dbd2f10f562a65ad2e590915d0e3d564a748cabadc950c1'
PYTHON = '/root/venv_volta/bin/python'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def hold(code):
    raise RuntimeError(code)


def observed_automatic_hold():
    path = STATE / 'TRAIN_HOLD.flag'
    if path.is_symlink():
        hold('HOLD_TRAIN_FLAG_SYMLINK')
    if not path.exists():
        return {'present': False}
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 256:
            hold('HOLD_TRAIN_FLAG_SCOPE')
        raw = stream.read(257)
    match = re.fullmatch(rb'OWNER_HYBRID_FAILED request=(\d{1,24})\n', raw)
    if not match:
        hold('HOLD_UNCLASSIFIED_TRAIN_FLAG')
    return {'present': True, 'kind': 'OWNER_HYBRID_FAILED',
            'request': match[1].decode(), 'sha256': digest(raw),
            'bytes': len(raw), 'mtime_ns': info.st_mtime_ns,
            'preserved': True}


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}', source):
        hold('HOLD_OWNER_CONTEXT')
    if any(p.is_symlink() for p in (ROOT, STATE)) or not STATE.is_dir():
        hold('HOLD_NATIVE_STATE_PATH')
    receipt = STATE / ('owner_qwen_runtime_smoke_' + request + '.json')
    if receipt.exists() or receipt.is_symlink():
        hold('HOLD_SMOKE_REQUEST_ALREADY_EXECUTED')
    raw = base64.b64decode(BUNDLE.get(SMOKE_NAME, ''), validate=True)
    if digest(raw) != SMOKE_SHA:
        hold('HOLD_SMOKE_SOURCE_BUNDLE')
    compile(raw, SMOKE_NAME, 'exec')
    initial_hold = observed_automatic_hold()
    result = {'schema': 'NOX_QWEN_RUNTIME_SMOKE_OWNER_RECEIPT_V1',
              'request': request, 'source_sha': source,
              'smoke_source_sha256': SMOKE_SHA, 'started_at': time.time(),
              'initial_hold': initial_hold, 'training_started': False,
              'weights_changed': False, 'services_modified': False}
    success = False
    try:
        with tempfile.TemporaryDirectory(prefix='qwen-runtime-smoke-', dir=STATE) as parent:
            script = Path(parent) / SMOKE_NAME
            script.write_bytes(raw)
            script.chmod(0o600)
            args = [PYTHON, str(script)]
            if initial_hold['present']:
                args.extend(['--expected-auto-hold-sha256', initial_hold['sha256'],
                             '--expected-auto-hold-request', initial_hold['request']])
            env = dict(os.environ)
            env.update(CUDA_VISIBLE_DEVICES='1', PYTHONDONTWRITEBYTECODE='1',
                       OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', TOKENIZERS_PARALLELISM='false')
            child = subprocess.run(args, env=env, capture_output=True, text=True, timeout=150)
            result['exit_code'] = child.returncode
            if len(child.stdout) > 65536 or len(child.stderr) > 65536:
                hold('HOLD_SMOKE_OUTPUT_BUDGET')
            records = []
            for line in child.stdout.splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and 'state' in row:
                    records.append(row)
            if len(records) != 1:
                result['stderr_present'] = bool(child.stderr)
                hold('HOLD_SMOKE_RESULT_SCHEMA')
            result['native_proof'] = records[0]
            final_hold = observed_automatic_hold()
            result['hold_unchanged'] = final_hold == initial_hold
            success = (child.returncode == 0 and result['hold_unchanged']
                       and records[0].get('state') == 'NATIVE_RUNTIME_SMOKE_PASSED'
                       and records[0].get('source_sha256') == SMOKE_SHA
                       and records[0].get('fp16_matmul_backward') is True
                       and records[0].get('nf4_input_backward') is True
                       and records[0].get('memfd', {}).get('tensor_exact') is True)
            result['state'] = 'NATIVE_RUNTIME_SMOKE_PASSED' if success else 'HOLD_NATIVE_RUNTIME_SMOKE'
    except Exception as exc:
        message = str(exc)
        result['state'] = message if re.fullmatch('HOLD_[A-Z0-9_]+', message) else 'HOLD_' + type(exc).__name__.upper()
    result['finished_at'] = time.time()
    blob = json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False).encode() + b'\n'
    fd = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(blob)
        stream.flush()
        os.fsync(stream.fileno())
    if digest(receipt.read_bytes()) != digest(blob):
        hold('HOLD_SMOKE_RECEIPT_READBACK')
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_runtime_smoke', 'data': result}), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        message = str(exc)
        code = message if re.fullmatch('HOLD_[A-Z0-9_]+', message) else 'HOLD_' + type(exc).__name__.upper()
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_runtime_smoke', 'state': code}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
