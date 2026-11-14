"""V110 read-only physical inventory for existing NOX OneHost, no model or S03 writes.

Uses the existing V51 temporary SSH key mechanism and guarantees cleanup.
This is diagnosis, not trainer/bridge activation, checkpoint proof or promotion.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

BASE_API = ssh.api


def settled_api(method, path, key, data=None):
    answer = BASE_API(method, path, key, data)
    if method == "POST" and path.endswith("/ssh/"):
        time.sleep(12)
    return answer


REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V110_SCHEMA=NOX_EXISTING_ONEHOST_READONLY_ADMISSION_INVENTORY_V1')

def emit(label, **data):
    line = 'NATIVE_V110_' + label + '=' + json.dumps(
        data, sort_keys=True, ensure_ascii=True, separators=(',', ':'))
    if len(line) < 780:
        print(line)

def command(args, timeout=5):
    try:
        p = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=timeout)
        return p.returncode, p.stdout[:1500]
    except (OSError, subprocess.TimeoutExpired):
        return 99, ''

def get_status(path, timeout=2):
    try:
        with urllib.request.urlopen('http://127.0.0.1:' + path,
                                    timeout=timeout) as r:
            return r.status, r.read(150000)
    except urllib.error.HTTPError as exc:
        return exc.code, b''
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, b''

stops = ('/root/nox/STOP', '/root/nox/STOP.flag', '/root/nox/stop.flag',
         '/root/nox/.stop', '/workspace/NOX_STOP', '/root/nox/program/STOP')
emit('STOP', active=any(Path(x).exists() for x in stops))
for port in (8080, 8081):
    code, _ = get_status(str(port) + '/health')
    emit('HEALTH_' + str(port), http=code, healthy=(code == 200))
code, payload = get_status('8081/slots')
info = {'http': code, 'shape': 'UNKNOWN', 'idle_proven': False}
if code == 200:
    try:
        obj = json.loads(payload)
        info['shape'] = ('list' if isinstance(obj, list)
                         else 'dict' if isinstance(obj, dict) else 'other')
        if isinstance(obj, list):
            info['count'] = len(obj)
            if all(isinstance(s, dict) for s in obj):
                flags = [(s.get('is_processing') if 'is_processing' in s
                          else s.get('processing')) for s in obj]
                info['known_flags'] = sum(isinstance(flag, bool) for flag in flags)
                info['busy'] = sum(flag is True for flag in flags)
                info['idle_proven'] = (len(obj) == 6 and
                                       all(flag is False for flag in flags))
        elif isinstance(obj, dict):
            info['has_slots_list'] = isinstance(obj.get('slots'), list)
    except (TypeError, ValueError):
        info['shape'] = 'INVALID_JSON'
emit('SLOTS', **info)

rc, state = command(['supervisorctl', 'status', 'nox-proxy'])
words = state.split()
emit('PROXY', status=(words[1] if rc == 0 and len(words) > 1
                     and words[0].startswith('nox-proxy') else 'UNKNOWN'),
     query_ok=(rc == 0))
rc, state = command(['supervisorctl', 'status'])
if rc == 0:
    statuses = {}
    for line in state.splitlines()[:80]:
        bits = line.split()
        if len(bits) >= 2 and re.fullmatch(r'[a-zA-Z0-9_.:@-]{1,64}', bits[0]):
            if any(key in bits[0].casefold() for key in ('forge','train','proxy','s03','onehost')):
                statuses[bits[0]] = bits[1][:32]
    emit('SERVICES', states=statuses)

for label, path in (('NOX', '/root/nox'), ('WORKSPACE', '/workspace')):
    if os.path.isdir(path):
        disk = shutil.disk_usage(path)
        emit('DISK_' + label, total_bytes=disk.total,
             used_bytes=disk.used, free_bytes=disk.free)
    else:
        emit('DISK_' + label, exists=False)

rc, raw = command(['nvidia-smi', '--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu',
                   '--format=csv,noheader,nounits'], 6)
gpu_count = 0
if rc == 0:
    for row in raw.splitlines()[:4]:
        fields = [f.strip() for f in row.split(',')]
        if len(fields) >= 6 and all(re.fullmatch(r'[0-9]+', fields[k]) for k in (0,2,3,4,5)):
            gpu_count += 1
            emit('GPU_' + fields[0], v100=('V100' in fields[1]),
                 mem_total_mib=int(fields[2]), used_mib=int(fields[3]),
                 free_mib=int(fields[4]), utilization_pct=int(fields[5]))
emit('GPU_QUERY', success=(rc == 0), valid_rows=gpu_count)

proxy = Path('/root/nox/scripts/chat_proxy.py')
bridge = Path('/root/nox/scripts/nox_v29_chat_bridge.py')
if proxy.is_file() and not proxy.is_symlink() and proxy.stat().st_size < 500000:
    b = proxy.read_bytes()
    bridge_ok = bridge.is_file() and not bridge.is_symlink() and bridge.stat().st_size < 500000
    emit('WEB_SOURCE', source_sha256=hashlib.sha256(b).hexdigest(),
         registration_marker=(b'register_native_v29_chat(app, globals())' in b),
         bridge_module_exists=bridge_ok,
         bridge_sha256=(hashlib.sha256(bridge.read_bytes()).hexdigest() if bridge_ok else None))
else:
    emit('WEB_SOURCE', valid_proxy_source=False)

# Send only unauthenticated negative security probes, never chat prompts.
# An active route must reject both calls before any STOP or model code runs.
for label, endpoint in (('STREAM', '/api/nox/chat/stream'), ('STOP', '/api/nox/stop')):
    try:
        request = urllib.request.Request(
            'http://127.0.0.1:8080' + endpoint,
            data=b'{}', method='POST',
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=3) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        status = 0
    emit('AUTH_' + label, http=status, rejects_anonymous=(status == 401))

private = Path('/root/nox/forge/base_train_input_v108')
manifest = private / 'manifest.json'
if (manifest.is_file() and not manifest.is_symlink()
        and manifest.stat().st_size < 100000):
    try:
        obj = json.loads(manifest.read_text(encoding='utf-8'))
        emit('CORPUS', schema_ok=(obj.get('schema') == 'NOX_V108_V47_BASE_INPUT_V1'),
             train_rows=obj.get('train_rows'), holdout_rows=obj.get('holdout_rows'),
             private_only=True, converted_not_trained=True)
    except (OSError, ValueError):
        emit('CORPUS', status='MANIFEST_UNREADABLE')
else:
    emit('CORPUS', status='NOT_FOUND')

roots = ('/root/nox/models', '/root/nox/forge', '/root/nox/checkpoints',
         '/workspace/nox/models', '/workspace/nox/forge')
dirs_scanned = 0
hf_candidates = 0
hf_shard_bytes = 0
hf_architectures = []
optimizer_files = 0
optimizer_bytes = 0
for root in roots:
    if not os.path.isdir(root) or os.path.islink(root):
        continue
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs_scanned += 1
        depth = len(Path(current).relative_to(root).parts)
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(current,d))
                   and d not in ('cache','.cache','node_modules','.git')][:50] if depth < 3 else []
        has_hf = 'config.json' in files and any(
            name.endswith('.safetensors') or
            (name.startswith('pytorch_model') and name.endswith('.bin'))
            for name in files)
        if has_hf:
            hf_candidates += 1
            for name in files:
                if name.endswith('.safetensors') or (name.startswith('pytorch_model')
                                                      and name.endswith('.bin')):
                    try:
                        hf_shard_bytes += (Path(current) / name).stat().st_size
                    except OSError:
                        pass
            try:
                conf = Path(current) / 'config.json'
                if conf.stat().st_size < 250000:
                    cfg = json.loads(conf.read_text(encoding='utf-8'))
                    mt = cfg.get('model_type')
                    if isinstance(mt, str) and re.fullmatch(r'[a-zA-Z0-9_.-]{1,50}', mt):
                        hf_architectures.append(mt)
            except (OSError, ValueError):
                pass
        for name in files:
            if (name == 'optimizer_state.pt' or name.startswith('optimizer_state.')
                    or name == 'optimizer.pt'):
                try:
                    obj = Path(current) / name
                    if not obj.is_symlink():
                        optimizer_files += 1
                        optimizer_bytes += obj.stat().st_size
                except OSError:
                    pass
        if dirs_scanned >= 650:
            dirs[:] = []
            break
    if dirs_scanned >= 650:
        break
emit('TRAINABLE', scanned_directories=dirs_scanned,
     partial_scan=True, local_hf_candidates=hf_candidates,
     hf_shard_bytes=hf_shard_bytes, model_types=hf_architectures[:3],
     optimizer_file_candidates=optimizer_files,
     optimizer_file_bytes=optimizer_bytes,
     restore_verified=False, owner_lease_verified=False)
print('NATIVE_V110_NO_CHANGES=true')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""


def main():
    ssh.REMOTE = REMOTE
    ssh.api = settled_api
    log = io.StringIO()
    success = False
    try:
        with contextlib.redirect_stdout(log):
            success = ssh.probe()
    except Exception:
        print('NOX_V110=HOLD_NATIVE_SSH')
    finally:
        try:
            with contextlib.redirect_stdout(log):
                if not ssh.cleanup():
                    success = False
        except Exception:
            success = False
    observed = 0
    cleanup = False
    for line in log.getvalue().splitlines():
        if line.startswith('NATIVE_V110_') and len(line) < 780:
            print(line)
            observed += 1
        elif line.startswith('TEMP_SSH_CLEANUP='):
            print(line[:120])
            if 'DETACHED_AND_VERIFIED' in line or 'ALREADY_ABSENT' in line:
                cleanup = True
    accepted = success and observed >= 8 and cleanup
    print('NOX_V110_READONLY_INVENTORY=' + ('PASS' if accepted else 'HOLD'))
    print('NOX_V110_TRAINING_OR_DEPLOYMENT_PERFORMED=false')
    return 0 if accepted else 2


if __name__ == '__main__':
    raise SystemExit(main())
