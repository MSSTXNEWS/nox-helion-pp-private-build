"""NOX V51: one-time temporary per-instance SSH access using EXISTING NOX2.

This does not create an SSH account key, API key, service, scheduler, or backend.
It uses Vast's documented per-instance POST /instances/<id>/ssh and cleans up
that exact temporary public key through DELETE /instances/<id>/ssh/<key_id>.
Run only in ephemeral GitHub Actions environment; never embed NOX2 in code.
"""
from __future__ import annotations
import json
import ipaddress
import socket
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import email.utils
from datetime import datetime, timezone
import urllib.error
import urllib.request

INSTANCE = 60509551
API = "https://console.vast.ai/api/v0"  # Per-instance SSH key operations remain v0
LIST_API = "https://console.vast.ai/api/v1/instances/?owner=me"  # v0 account listing deprecated
RUNNER = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "nox-v51-ephemeral"
KEY = RUNNER / "identity"
TRACK = RUNNER / "cleanup.json"
HOST_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]{1,253}$")

# Trust-boundary: data returned by the native command is heavily bounded,
# independently of what untrusted code might be present on the remote host.
REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,subprocess,re,json,shutil
def call(args,seconds=12):
    try:
        r=subprocess.run(args,capture_output=True,text=True,timeout=seconds)
        return r.returncode,r.stdout[:10000]
    except (OSError,subprocess.TimeoutExpired):
        return 99,''
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_CONTAINER_UID='+str(os.getuid()))
rc,out=call(['nvidia-smi','--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'])
if rc==0:
    rows=[v.strip() for v in out.splitlines() if v.strip() and len(v)<200][:4]
    print('NATIVE_GPU_QUERY=PASS')
    for row in rows:
        # No commands or untrusted process arguments are printed.
        if re.fullmatch(r'[\w, .+/-]{10,200}',row):
            print('NATIVE_GPU='+row)
else: print('NATIVE_GPU_QUERY=HOLD')
rc,out=call(['free','-b'])
if rc==0:
    for row in out.splitlines():
        if row.startswith('Mem:'):
            fields=row.split()
            if len(fields)>3:
                print('NATIVE_RAM_TOTAL_BYTES='+fields[1])
                print('NATIVE_RAM_USED_BYTES='+fields[2])
                break
rc,out=call(['df','-B1','/workspace'])
if rc==0:
    for line in out.splitlines()[1:2]:
        fields=line.split()
        if len(fields)>=4:
            print('NATIVE_WORKSPACE_DISK_TOTAL_BYTES='+fields[1])
            print('NATIVE_WORKSPACE_DISK_USED_BYTES='+fields[2])
            print('NATIVE_WORKSPACE_DISK_FREE_BYTES='+fields[3])
rc,out=call(['ps','-eo','comm='])
if rc==0:
    names=[x.strip().lower() for x in out.splitlines()]
    patterns={'python':'python','llama':'llama','ollama':'ollama','supervisor':'supervis','node':'node','jupyter':'jupyter'}
    for label,pattern in patterns.items():
        print('NATIVE_PROCESS_COUNT_'+label.upper()+'='+str(sum(pattern in name for name in names)))

# P0 compatibility inventory: metadata only; no GPU allocations or package installs.
from pathlib import Path
print('NATIVE_P0_DEEP_INVENTORY_STARTED=true')
print('NATIVE_CPU_LOGICAL_COUNT='+str(os.cpu_count()))
for path,label in (
    ('/sys/fs/cgroup/memory.max','CGROUP_MEMORY_MAX'),
    ('/sys/fs/cgroup/memory.current','CGROUP_MEMORY_CURRENT')):
    try:
        value=Path(path).read_text().strip()
        if re.fullmatch(r'(?:[0-9]{1,20}|max)',value):
            print('NATIVE_'+label+'='+value)
    except OSError:pass
rc,out=call(['nvidia-smi','--query-gpu=index,driver_version,compute_cap','--format=csv,noheader,nounits'])
if rc==0:
    print('NATIVE_DRIVER_CCAP_QUERY=PASS')
    for item in out.splitlines()[:2]:
        if re.fullmatch(r'[0-9., ]{5,100}',item.strip()):
            print('NATIVE_DRIVER_CCAP='+item.strip())
else:print('NATIVE_DRIVER_CCAP_QUERY=HOLD')
rc,out=call(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader,nounits'])
if rc==0:
    print('NATIVE_COMPUTE_APPS_QUERY=PASS')
    for item in out.splitlines()[:16]:
        cols=[c.strip() for c in item.split(',')]
        if len(cols)>=3 and cols[1].isdigit() and re.fullmatch(r'[0-9]+',cols[2]):
            pid=cols[1]
            try: process=Path('/proc',pid,'comm').read_text().strip()
            except OSError:process='UNKNOWN'
            if not re.fullmatch('[A-Za-z0-9_.:-]{1,40}',process):
                process='UNKNOWN'
            print('NATIVE_COMPUTE_APP_PID='+pid+',MEM_MIB='+cols[2]+',PROC='+process)
else:print('NATIVE_COMPUTE_APPS_QUERY=HOLD')
for root,label in (('/workspace','WORKSPACE'),('/root','ROOT')):
    try:
        items=[x.name for x in os.scandir(root)
                if x.is_dir(follow_symlinks=False) and
                   ('nox' in x.name.lower() or 'onehost' in x.name.lower())]
        items=[x for x in items if re.fullmatch('[A-Za-z0-9_.-]{1,70}',x)]
        print('NATIVE_NOX_DIR_NAMES_'+label+'='+json.dumps(items[:15]))
    except OSError:pass
for path,label in (
    ('/usr/local/cuda/version.json','CUDA_VERSION_JSON_EXISTS'),
    ('/usr/local/cuda/bin/nvcc','NVCC_EXISTS'),
    ('/root/nox/STOP','STOP_ROOT_NOX'),
    ('/workspace/NOX_STOP','STOP_WORKSPACE')):
    print('NATIVE_'+label+'='+str(Path(path).exists()).lower())
PY_META = '''
import json,sys
from importlib import metadata as m
d={"python":sys.version.split()[0],"packages":{}}
for name in ("torch","transformers","accelerate","datasets",
             "safetensors","deepspeed","triton","llama-cpp-python"):
    try:d["packages"][name]=m.version(name)
    except m.PackageNotFoundError:pass
if "torch" in d["packages"]:
    try:
        import torch
        d["torch_cuda_build"]=str(torch.version.cuda)
        d["torch_compiled_arch_list"]=torch.cuda.get_arch_list()
        d["cudnn_version"]=torch.backends.cudnn.version()
    except Exception as e:d["torch_probe_error_type"]=type(e).__name__
print(json.dumps(d,sort_keys=True))
'''
candidates=[shutil.which('python3'),'/opt/venv/bin/python',
            '/workspace/venv/bin/python','/root/nox/venv/bin/python']
checked=set()
for exe in candidates:
    if not exe or exe in checked or not os.path.isfile(exe) or not os.access(exe,os.X_OK):
        continue
    checked.add(exe)
    rc,out=call([exe,'-c',PY_META],seconds=20)
    if rc==0:
        try:
            record=json.loads(out)
            if isinstance(record,dict):
                print('NATIVE_PYENV_'+str(len(checked))+'='+json.dumps(record,sort_keys=True)[:1900])
        except ValueError:pass
    else:
        print('NATIVE_PYENV_'+str(len(checked))+'=HOLD_PACKAGE_INSPECT')
    if len(checked)>=3:break
print('NATIVE_P0_DEEP_INVENTORY_COMPLETE=true')

def supervisor_projection(rc, output):
    # Bounded read-only critical NOX status, including Supervisor exit code 3.
    if rc not in (0, 3):
        return {'state':'HOLD_SUPERVISOR_COMMAND','services':[]}
    lines=output.splitlines()
    if not 1 <= len(lines) <= 40:
        return {'state':'HOLD_SUPERVISOR_BOUNDS','services':[]}
    wanted={'nox-train-volta-t866u','nox-chat-8081','nox-dispatcher-t855u',
            'nox-priority-scheduler','nox-selfheal'}
    services=[]
    seen=set()
    for line in lines:
        if len(line)>512:
            return {'state':'HOLD_SUPERVISOR_ROW_BOUNDS','services':[]}
        match=re.match(r'^([A-Za-z0-9_.:@-]{1,80})\s+(RUNNING|STARTING|STOPPED|FATAL|BACKOFF|EXITED|STOPPING|UNKNOWN)(?:\s|$)',line)
        if match is None:
            return {'state':'HOLD_SUPERVISOR_SCHEMA','services':[]}
        name,status=match.group(1),match.group(2)
        if name not in wanted:
            continue
        if name in seen:
            return {'state':'HOLD_SUPERVISOR_DUPLICATE','services':[]}
        seen.add(name)
        pid=None
        if status=='RUNNING':
            m=re.search(r'\bpid\s+([1-9][0-9]{0,9})(?:,|\s|$)',line[match.end():])
            if m is None:
                return {'state':'HOLD_SUPERVISOR_PID','services':[]}
            pid=int(m.group(1))
        services.append({'service':name,'status':status,'pid':pid})
    if not services:
        return {'state':'HOLD_SUPERVISOR_NO_CORE','services':[]}
    # rc=0 and a single RUNNING row do not prove all five NOX services exist.
    healthy=(rc==0 and seen==wanted and all(x['status']=='RUNNING' for x in services))
    return {'state':'OBSERVED_ALL_RUNNING' if healthy else 'OBSERVED_PARTIAL',
            'supervisor_rc':rc,'all_running_verified':healthy,'services':services}
rc,out=call(['supervisorctl','status'])
projection=json.dumps(supervisor_projection(rc,out),sort_keys=True,separators=(',',':'))
# V51 manual owner workflow already forwards NATIVE_P0_*; never expose raw command/args.
print('NATIVE_P0_SUPERVISOR_STATUS='+projection if len(projection)<=730
      else 'NATIVE_P0_SUPERVISOR_STATUS=HOLD_OUTPUT_BUDGET')
# Detect project artifacts by count only; never copy secrets, content or paths.
for label,root in [('workspace', '/workspace'),('nox_home', '/root')]:
    dirs=0
    if os.path.isdir(root):
        try:
            for item in os.scandir(root):
                if item.is_dir(follow_symlinks=False) and ('nox' in item.name.lower() or 'onehost' in item.name.lower()):
                    dirs+=1
        except OSError:pass
    print('NATIVE_NOX_TOPLEVEL_DIRS_'+label.upper()+'='+str(dirs))

# P0 read-only ownership forensics: GPU PID belongs to GPU index, NOT a writer lease.
def gpu_pid_map(call,procroot):
    rc,gpu=call(['nvidia-smi','--query-gpu=index,uuid','--format=csv,noheader,nounits'])
    if rc:return {'status':'HOLD_GPU_UUID_QUERY'}
    ids={}
    for line in gpu.splitlines():
        cols=[x.strip() for x in line.split(',')]
        if len(cols)!=2 or cols[0] not in ('0','1') or not re.fullmatch(r'GPU-[A-Za-z0-9-]{15,80}',cols[1]):
            return {'status':'HOLD_GPU_UUID_SCHEMA'}
        if cols[1] in ids:return {'status':'HOLD_GPU_UUID_DUPLICATE'}
        ids[cols[1]]=int(cols[0])
    if set(ids.values())!={0,1}:return {'status':'HOLD_GPU_COUNT_UNVERIFIED'}
    rc,apps=call(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader,nounits'])
    if rc:return {'status':'HOLD_GPU_APP_QUERY'}
    rows=[]
    for item in apps.splitlines():
        if not item.strip() or item.strip()=='No running processes found':continue
        x=[v.strip() for v in item.split(',')]
        if len(x)!=3 or x[0] not in ids or not x[1].isdigit() or not x[2].isdigit():
            return {'status':'HOLD_GPU_APP_BINDING'}
        pid=int(x[1]);vram=int(x[2])
        if not (1<=pid<=9999999 and 0<=vram<=32768):
            return {'status':'HOLD_GPU_APP_RANGE'}
        try:comm=(procroot/str(pid)/'comm').read_text().strip()
        except OSError:comm='UNKNOWN'
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,40}',comm):comm='UNKNOWN'
        rows.append({'gpu':ids[x[0]],'pid':pid,'vram_mib':vram,'comm':comm})
        if len(rows)>12:return {'status':'HOLD_TOO_MANY_GPU_APPS'}
    return {'status':'PID_ONLY_NO_OWNER_LEASE','processes':rows,'gpu1_owner_lease_verified':False}

def cgroup_oom_pair(path,pause):
    def read():
        try:lines=path.read_text().splitlines()
        except OSError:return None
        values={}
        for line in lines:
            x=line.split()
            if len(x)!=2 or not re.fullmatch(r'[a-z_]+',x[0]) or x[0] in values or not x[1].isdigit():
                return None
            values[x[0]]=int(x[1])
        return values if {'oom','oom_kill'}<=set(values) else None
    a=read()
    if a is None:return {'verified':False,'reason':'HOLD_CGROUP_OOM_BEFORE'}
    pause(1.0)
    b=read()
    if b is None or any(b[k]<a[k] for k in ('oom','oom_kill')):
        return {'verified':False,'reason':'HOLD_CGROUP_OOM_AFTER_OR_RESET'}
    return {'verified':True,'oom_delta':b['oom']-a['oom'],'oom_kill_delta':b['oom_kill']-a['oom_kill']}

# Preserve a complete, parseable receipt; a clipped JSON string is not evidence.
def bounded_native_json(value,max_chars,hold_status):
    payload=json.dumps(value,sort_keys=True,separators=(',',':'))
    return (payload if len(payload)<=max_chars else
            json.dumps({'status':hold_status},sort_keys=True,separators=(',',':')))


def pinned_owner_stop_snapshot(paths, lstat):
    # Observation only: eight canonical known paths do not prove every STOP gate.
    if len(paths) != 8 or len(set(paths)) != 8:
        return {'status': 'HOLD_STOP_SCOPE'}
    def scan():
        present = []
        for idx, path in enumerate(paths):
            try:
                lstat(path)  # Counts even dangling STOP symlinks.
            except FileNotFoundError:
                continue
            except OSError:
                return None
            present.append(idx)
        return present
    first = scan()
    second = scan()
    if first is None or second is None:
        return {'status': 'HOLD_STOP_IO'}
    if first != second:
        return {'status': 'HOLD_STOP_CHANGED_DURING_READ'}
    return {'status': 'STOP_PRESENT' if first else 'NO_STOP_IN_EIGHT_PINNED_PATHS',
            'checked_count': 8, 'present_ids': first,
            'manual_stop_clear_verified': False}

# Exactly the eight owner STOP paths already guarded by nox_cold_drive.
# This is a read-only observation, never a write lease or authorisation.
pinned_stop_paths = (
    '/root/nox/STOP', '/root/nox/STOP.flag',
    '/root/nox/stop.flag', '/root/nox/.stop',
    '/root/nox/program/STOP', '/root/nox/state/STOP',
    '/root/nox/state/STOP.flag', '/workspace/NOX_STOP')
print('NATIVE_P0_OWNER_STOP='+bounded_native_json(
    pinned_owner_stop_snapshot(pinned_stop_paths, os.lstat),
    300,'HOLD_STOP_JSON_BUDGET'))


def chat_listener_projection(supervisor, call, procroot):
    # A listening PID is observed process evidence, never a writer lease.
    services = supervisor.get('services', []) if isinstance(supervisor, dict) else []
    chat = next((x for x in services if x.get('service') == 'nox-chat-8081'), None)
    if chat is None:
        return {'status': 'HOLD_CHAT_SUPERVISOR_NOT_OBSERVED'}
    rc, output = call(['ss', '-H', '-ltnp'])
    if rc or len(output) >= 10000:
        return {'status': 'HOLD_CHAT_LISTENER_QUERY'}
    owners = set()
    found_listener = False
    for line in output.splitlines():
        fields = line.split(None, 5)
        if len(fields) < 5 or fields[0] != 'LISTEN' or not fields[3].endswith(':8081'):
            continue
        found_listener = True
        pids = re.findall(r'\bpid=([1-9][0-9]{0,8})\b', line)
        if not pids:
            return {'status': 'HOLD_CHAT_LISTENER_PID_UNREADABLE'}
        owners.update(map(int, pids))
        if len(owners) > 5:
            return {'status': 'HOLD_CHAT_LISTENER_AMBIGUOUS'}
    if not found_listener:
        return {'status': 'NO_CHAT_LISTENER_ON_8081',
                'supervisor_status': chat['status'], 'restart_authorized': False}
    pins = []
    for pid in sorted(owners):
        try:
            p = procroot / str(pid)
            raw = (p / 'stat').read_text()
            stat = raw.rsplit(') ', 1)[1].split()
            start = stat[19]
            comm = (p / 'comm').read_text().strip()
        except (OSError, IndexError, ValueError):
            return {'status': 'HOLD_CHAT_PID_IDENTITY_UNREADABLE'}
        if not start.isdigit() or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,40}', comm):
            return {'status': 'HOLD_CHAT_PID_IDENTITY_SCHEMA'}
        pins.append({'pid': pid, 'start_ticks': int(start), 'comm': comm})
    status = ('CHAT_UNMANAGED_LISTENER_OBSERVED' if chat['status'] != 'RUNNING'
              else 'CHAT_LISTENER_OBSERVED')
    return {'status': status, 'supervisor_status': chat['status'],
            'listener_pids': pins, 'restart_authorized': False}

print('NATIVE_P0_CHAT_LISTENER='+bounded_native_json(
    chat_listener_projection(supervisor_projection(rc,out),call,Path('/proc')),
    680,'HOLD_CHAT_LISTENER_OUTPUT_BUDGET'))

print('NATIVE_P0_GPU_PID_MAP='+bounded_native_json(
    gpu_pid_map(call,Path('/proc')),740,'HOLD_GPU_PID_LOG_BUDGET'))
print('NATIVE_P0_CGROUP_OOM='+bounded_native_json(
    cgroup_oom_pair(Path('/sys/fs/cgroup/memory.events'),__import__('time').sleep),
    260,'HOLD_CGROUP_OOM_LOG_BUDGET'))
print('NATIVE_P0_WRITER_LEASE=HOLD_NOT_PROVEN_BY_PID_INVENTORY')
print('NATIVE_P0_OFFSITE_RESTORE=HOLD_NOT_PROVEN_BY_READ_ONLY_PROBE')

print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""


_MAX_RETRY_AFTER_SECONDS = 30

def _retry_after_seconds(exc: urllib.error.HTTPError, retry_index: int) -> float:
    """Return a bounded delay; an invalid/too-long server delay fails closed."""
    headers = getattr(exc, "headers", None)
    value = headers.get("Retry-After") if headers is not None else None
    if value is None:
        return float(2 ** retry_index)
    raw = str(value).strip()
    try:
        delay = float(raw)
    except (TypeError, ValueError):
        try:
            when = email.utils.parsedate_to_datetime(raw)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            delay = (when - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            raise RuntimeError("HOLD_VAST_API_HTTP_429_RETRY_AFTER_INVALID") from None
    if delay < 0:
        delay = 0.0
    if delay > _MAX_RETRY_AFTER_SECONDS:
        raise RuntimeError("HOLD_VAST_API_HTTP_429_RETRY_AFTER_TOO_LONG") from None
    return delay


def _retryable_read_only_metadata(method: str, path: str, data: dict | None) -> bool:
    # Exact allowlist: account instance listing and this instance's SSH-key metadata.
    return (method == "GET" and data is None and
            (path == "/instances/" or
             path == f"/instances/{INSTANCE}/ssh/"))


def api(method: str, path: str, key: str, data: dict | None = None):
    if not key:
        raise RuntimeError("HOLD_NOX2_MISSING")
    headers = {"Authorization": "Bearer " + key, "Accept": "application/json"}
    raw = None
    if data is not None:
        raw = json.dumps(data, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    endpoint = LIST_API if method == "GET" and path == "/instances/" else API + path
    retryable = _retryable_read_only_metadata(method, path, data)
    for retry_index in range(3):
        request = urllib.request.Request(endpoint, headers=headers, data=raw, method=method)
        try:
            with urllib.request.urlopen(request, timeout=22) as response:
                body = response.read(250000)
            value = json.loads(body)
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and retryable and retry_index < 2:
                time.sleep(_retry_after_seconds(exc, retry_index))
                continue
            raise RuntimeError("HOLD_VAST_API_HTTP_" + str(exc.code)) from None
    if isinstance(value, dict) and value.get("success") is False:
        raise RuntimeError("HOLD_VAST_API_REJECTED_" + method)
    return value



def attach_ephemeral_key(key: str, public: str) -> list[int]:
    """Issue one POST; on ambiguous 429, use only one safe GET reconciliation."""
    try:
        api("POST", f"/instances/{INSTANCE}/ssh/", key, {"ssh_key": public})
        TRACK.write_text(json.dumps({
            "public": public, "key_id": None,
            "attach_state": "ATTACH_ACCEPTED_UNVERIFIED"}))
        print("VAST_EPHEMERAL_PUBLIC_KEY_ATTACH_ACCEPTED=true")
        return []
    except RuntimeError as exc:
        if str(exc) != "HOLD_VAST_API_HTTP_429":
            raise
        TRACK.write_text(json.dumps({
            "public": public, "key_id": None,
            "attach_state": "ATTACH_AMBIGUOUS_HTTP_429"}))
        key_id = reconcile_attach_after_429(key, public)
        TRACK.write_text(json.dumps({
            "public": public, "key_id": key_id,
            "attach_state": "ATTACHED_VERIFIED"}))
        print("VAST_EPHEMERAL_ATTACH_429_RECONCILED_BY_READ=true")
        return [key_id]


def reconcile_attach_after_429(key: str, public: str) -> int:
    """Read-only confirmation after an ambiguous attach; never repeats POST."""
    try:
        ids = match(key, public)
    except RuntimeError as exc:
        # Keep the precise HTTP status and the fixed GET resource in a safe code.
        status = re.fullmatch(r"HOLD_VAST_API_HTTP_([0-9]{3})", str(exc))
        if status:
            raise RuntimeError(
                "HOLD_VAST_API_GET_INSTANCE_SSH_HTTP_" + status.group(1)
            ) from None
        raise RuntimeError(
            "HOLD_VAST_API_GET_INSTANCE_SSH_RECONCILE_FAILED"
        ) from None
    if not ids:
        raise RuntimeError(
            "HOLD_VAST_API_POST_INSTANCE_SSH_HTTP_429_RECONCILE_ABSENT"
        )
    if len(ids) != 1:
        raise RuntimeError(
            "HOLD_VAST_API_POST_INSTANCE_SSH_HTTP_429_RECONCILE_AMBIGUOUS"
        )
    return ids[0]


def keys(key: str) -> list[dict]:
    data = api("GET", f"/instances/{INSTANCE}/ssh/", key)
    entries = data.get("ssh_keys", data.get("keys", [])) if isinstance(data, dict) else data
    if isinstance(entries, str):
        entries = json.loads(entries)
    if not isinstance(entries, list) or any(not isinstance(v, dict) for v in entries):
        raise RuntimeError("HOLD_VAST_INSTANCE_KEY_LIST")
    return entries


def match(key: str, public: str) -> list[int]:
    identity = public.strip().split()[:2]
    found = []
    for obj in keys(key):
        candidate = str(obj.get("public_key", obj.get("ssh_key", obj.get("key", ""))))
        if candidate.strip().split()[:2] == identity and len(identity) == 2:
            value = obj.get("id")
            if str(value).isdigit():
                found.append(int(value))
    return found


def cleanup() -> bool:
    key = os.environ.get("NOX2", "")
    if not TRACK.exists():
        print("TEMP_SSH_CLEANUP=NOT_ATTACHED")
        return True
    record = json.loads(TRACK.read_text())
    pub = record.get("public", "")
    if not pub.startswith("ssh-ed25519 "):
        print("TEMP_SSH_CLEANUP=HOLD_BAD_RECORD")
        return False
    ids = match(key, pub)
    # A 429 POST has an ambiguous outcome; absence from one read is not proof
    # that a delayed attach cannot appear. Keep its receipt for later recovery.
    if not ids:
        if record.get("attach_state") in (
                "ATTACH_AMBIGUOUS_HTTP_429", "ATTACH_ACCEPTED_UNVERIFIED"):
            print("TEMP_SSH_CLEANUP=HOLD_ATTACH_STATE_UNRESOLVED")
            return False
        print("TEMP_SSH_CLEANUP=ALREADY_ABSENT")
        TRACK.unlink(missing_ok=True)
        return True
    if len(ids) != 1:
        print("TEMP_SSH_CLEANUP=HOLD_AMBIGUOUS_KEY_ID")
        return False
    expected = record.get("key_id")
    if expected is not None and int(expected) != ids[0]:
        print("TEMP_SSH_CLEANUP=HOLD_KEY_ID_CHANGED")
        return False
    api("DELETE", f"/instances/{INSTANCE}/ssh/{ids[0]}/", key)
    for attempt in range(4):
        if not match(key, pub):
            print("TEMP_SSH_CLEANUP=DETACHED_AND_VERIFIED")
            TRACK.unlink(missing_ok=True)
            return True
        time.sleep(1.5)
    print("TEMP_SSH_CLEANUP=HOLD_STILL_ATTACHED")
    return False


def probe() -> bool:
    key = os.environ.get("NOX2", "")
    d = api("GET", "/instances/", key)
    d = d.get("instances", d) if isinstance(d, dict) else None
    if isinstance(d, list):
        d = next((row for row in d if str(row.get("id")) == str(INSTANCE)), None)
    if not isinstance(d, dict) or str(d.get("id")) != str(INSTANCE):
        raise RuntimeError("HOLD_WRONG_INSTANCE")
    if d.get("actual_status") != "running":
        raise RuntimeError("HOLD_INSTANCE_NOT_RUNNING")
    if str(d.get("num_gpus")) != "2":
        raise RuntimeError("HOLD_GPU_COUNT_CHANGED")
    # Vast proxy route sometimes accepts TCP but does not emit an SSH banner.
    # Prefer the direct, authenticated API-provided 22/tcp mapping, requiring
    # a genuine SSH-2.0 banner BEFORE generating or attaching any key.
    ip = d.get("public_ipaddr")
    try:
        if not ipaddress.ip_address(ip).is_global:
            raise ValueError("private")
    except (TypeError,ValueError):
        raise RuntimeError("HOLD_DIRECT_SSH_IP_NOT_GLOBAL")
    ports = d.get("ports")
    if not isinstance(ports,dict):
        raise RuntimeError("HOLD_DIRECT_SSH_PORT_MAP")
    mappings = ports.get("22/tcp")
    if not isinstance(mappings,list):
        raise RuntimeError("HOLD_DIRECT_SSH_MAPPINGS")
    host,port = None,None
    for row in mappings:
        if not isinstance(row,dict):
            continue
        raw = row.get("HostPort")
        if not str(raw).isdigit() or not (1<=int(raw)<=65535):
            continue
        try:
            with socket.create_connection((ip,int(raw)),timeout=7) as sock:
                sock.settimeout(5)
                banner = sock.recv(128)
                if banner.startswith(b"SSH-2.0"):
                    host,port = ip,int(raw)
                    break
        except (OSError,TimeoutError):
            continue
    if host is None:
        raise RuntimeError("HOLD_DIRECT_SSH_BANNER_UNAVAILABLE")
    print("SSH_ROUTE=VAST_API_DIRECT_MAPPED_22_WITH_BANNER")
    RUNNER.mkdir(mode=0o700,parents=True,exist_ok=True)
    # Existing owner-pinned Ed25519 fingerprint, verified BEFORE any SSH key
    # is attached to the live instance. TCP banner alone does not authenticate.
    known = RUNNER / "known_hosts"
    try:
        scanned = subprocess.run(
            ["ssh-keyscan", "-T", "8", "-t", "ed25519", "-p", str(port), host],
            capture_output=True, text=True, timeout=11, check=False)
        known.write_text(scanned.stdout[:8000])
        known.chmod(0o600)
        fingerprint = subprocess.run(
            ["ssh-keygen", "-lf", str(known), "-E", "sha256"],
            capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("HOLD_UNVERIFIED_REMOTE_HOST_KEY") from None
    if (scanned.returncode != 0 or fingerprint.returncode != 0
            or "SHA256:G4hmMllaT4uSfx+Gup9vjSySLXJT1cSc/9XePr7XmGc"
            not in fingerprint.stdout):
        raise RuntimeError("HOLD_UNVERIFIED_REMOTE_HOST_KEY")
    print("SSH_HOST_FINGERPRINT=OWNER_PIN_MATCH_BEFORE_ATTACH")
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C",
         "nox-v51-github-action-" + os.environ.get("GITHUB_RUN_ID", "ephemeral"),
         "-f", str(KEY)],stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,check=True,timeout=12)
    KEY.chmod(0o600)
    public = KEY.with_suffix(".pub").read_text().strip()
    if len(public) > 700 or not public.startswith("ssh-ed25519 "):
        raise RuntimeError("HOLD_EPHEMERAL_KEY_FORMAT")
    before_ids = set(match(key, public))
    if before_ids:
        raise RuntimeError("HOLD_EPHEMERAL_KEY_COLLISION")
    # Record BEFORE the attach attempt so cleanup can recover an uncertain POST.
    TRACK.write_text(json.dumps({"public": public, "key_id": None}))
    TRACK.chmod(0o600)
    # 429 can be ambiguous: reconcile exactly once through GET; never retry POST.
    found = attach_ephemeral_key(key, public)
    for attempt in range(6):
        if found:
            break
        found = match(key, public)
        if found:
            break
        time.sleep(1.5)
    if len(found) != 1:
        raise RuntimeError("HOLD_EPHEMERAL_ATTACHED_KEY_ID_NOT_DISCOVERED")
    TRACK.write_text(json.dumps({
        "public": public, "key_id": found[0],
        "attach_state": "ATTACHED_VERIFIED"}))
    print("VAST_EPHEMERAL_KEY_MATCHED_BY_EXACT_PUBLIC_KEY=true")
    print("VAST_INSTANCE_RUNNING_PRESERVED=true")
    cmd = ["ssh","-vv","-T","-i",str(KEY),"-p",str(port),
           "-o","BatchMode=yes","-o","IdentitiesOnly=yes",
           "-o","ConnectTimeout=12","-o","NumberOfPasswordPrompts=0",
           "-o","StrictHostKeyChecking=yes",
           "-o","UserKnownHostsFile="+str(known),
           "root@"+host,"bash","-se"]
    for attempt in range(4):
        try:
            result = subprocess.run(cmd,input=REMOTE,encoding="utf-8",
                                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                    timeout=95)
        except subprocess.TimeoutExpired:
            print("SSH_ATTEMPT_"+str(attempt+1)+"=TIMEOUT")
            continue
        if result.returncode == 0 and "NATIVE_READ_ONLY_COMPLETE=true" in result.stdout and "NOX_NATIVE_V51_SSH_EXECUTED=true" in result.stdout:
            for line in result.stdout.splitlines():
                if len(line)<800 and line.startswith(("NOX_NATIVE_","NATIVE_")):
                    print(line)
            print("SSH_READONLY_REMOTE_EXIT_CODE=0")
            print("SSH_HOST_IDENTITY_POLICY=OWNER_PINNED_ED25519_READ_ONLY")
            return True
        stderr = result.stderr.lower()
        checks = [
            ("permission denied", "AUTH_PERMISSION_DENIED"),
            ("host key verification failed", "HOST_KEY_VALIDATION"),
            ("connection refused", "NETWORK_REFUSED"),
            ("connection timed out", "NETWORK_TIMEOUT"),
            ("operation timed out", "NETWORK_TIMEOUT"),
            ("connection closed", "CONNECTION_CLOSED"),
            ("connection reset", "CONNECTION_RESET"),
            ("could not resolve hostname", "DNS_FAILURE"),
            ("kex_exchange_identification", "SSH_KEX_FAILURE"),
            ("no matching host key type", "HOST_KEY_ALGORITHM"),
            ("no route to host", "NETWORK_NO_ROUTE"),
            ("server accepts key", "KEY_ACCEPTED_REMOTE_FAILURE"),
        ]
        reason = next((name for needle,name in checks if needle in stderr),
                      "UNCLASSIFIED")
        print("SSH_ATTEMPT_"+str(attempt+1)+"=FAILED_RC_"+str(result.returncode))
        print("SSH_FAILURE_CLASS="+reason)
        time.sleep(4)
    raise RuntimeError("HOLD_EPHEMERAL_SSH_CONNECT_OR_EXECUTION")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if mode not in ("probe","cleanup"):
        raise SystemExit("HOLD_MODE")
    good = False
    if mode == "probe":
        try:
            good = probe()
        except Exception as exc:
            # Do not print exception text, which could include remote details.
            print("PROBE_RESULT="+str(exc) if str(exc).startswith("HOLD_") else "PROBE_RESULT=HOLD_NATIVE_PROBE_EXCEPTION")
        finally:
            try:
                if not cleanup():
                    good = False
            except Exception:
                print("TEMP_SSH_CLEANUP=HOLD_UNEXPECTED_FAILURE")
                good = False
    else:
        try:
            good = cleanup()
        except Exception:
            print("TEMP_SSH_CLEANUP=HOLD_UNEXPECTED_FAILURE")
    raise SystemExit(0 if good else 2)
