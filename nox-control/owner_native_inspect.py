#!/usr/bin/env python3
"""Fixed read-only NOX queue/pool inspection. No model calls or native writes."""
from __future__ import annotations

import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
SOURCE_NAMES = (
    'owner_subagent_dispatcher.py', 'owner_subagent_processes.py',
    'owner_autonomy_pool.py', 'owner_task_plans.py',
    'owner_component_tasks.py', 'nox_auto_architect.py', 'owner_dispatcher_mentor.py',
)
FLAGS = (
    ROOT/'STOP', ROOT/'STOP.flag', ROOT/'stop.flag', ROOT/'.stop',
    ROOT/'program/STOP', ROOT/'state/STOP', ROOT/'state/STOP.flag',
    Path('/workspace/NOX_STOP'), ROOT/'state/OWNER_MAINTENANCE.flag',
    ROOT/'state/TRAIN_HOLD.flag', ROOT/'state/TRAIN_PAUSE_REQUEST.flag',
)
LOCK_PATHS = (ROOT/'state/owner_maintenance.lock', ROOT/'state/dispatcher/native_subagents.lock')
IDENTIFIER = re.compile(r'^[A-Za-z0-9_.:/@ -]{1,250}$')
SHA = re.compile(r'^[0-9a-f]{40,64}$')

def emit(name, value):
    print('NOX_MAINT_SCOPE_' + name + '=' + json.dumps(value, ensure_ascii=True,
          separators=(',', ':'), allow_nan=False), flush=True)

def safe_read(path, limit):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('ABSOLUTE_PATH_REQUIRED')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise ValueError('UNSAFE_TYPE_OR_SIZE')
            chunks = []
            total = 0
            while total <= limit:
                b = os.read(fd, min(65536, limit + 1 - total))
                if not b:
                    break
                chunks.append(b)
                total += len(b)
            after = os.fstat(fd)
            if total > limit or any(getattr(before, k) != getattr(after, k) for k in
                    ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
                raise ValueError('CHANGED_OR_OVERSIZED')
            return b''.join(chunks), after
        finally:
            os.close(fd)
    finally:
        os.close(parent)

def obj(path, limit=2000000):
    raw, info = safe_read(path, limit)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError('OBJECT_REQUIRED')
    return data, raw, info

def redact_source(value):
    out = re.sub(r'-----BEGIN [^-\n]*PRIVATE KEY-----[\s\S]*?-----END [^-\n]*PRIVATE KEY-----', '[REDACTED_PRIVATE_KEY]', value)
    out = re.sub(r'(?i)(https?://)[^/\s@]+:[^/\s@]+@', r'\1[REDACTED]@', out)
    out = re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9_.~+/=-]{12,}', r'\1[REDACTED]', out)
    out = re.sub(r'\b(?:hf_|ghp_|github_pat_)[A-Za-z0-9_]{12,}', '[REDACTED_TOKEN]', out)
    out = re.sub(r'''(?i)((?:password|secret|api_key|access_key|authorization|token)\s*[:=]\s*["'])([^"'\n]{12,})(["'])''', r'\1[REDACTED]\3', out)
    out = re.sub(r'(?i)([?&](?:token|key|password|signature|secret)=)[^\s&"\']+', r'\1[REDACTED]', out)
    return out

def identifier(value):
    return value if isinstance(value, str) and IDENTIFIER.fullmatch(value) else None

def scalar_projection(data, names):
    result = {}
    for name in names:
        value = data.get(name)
        if value is None or isinstance(value, (bool, int)) or isinstance(value, float) and __import__('math').isfinite(value):
            result[name] = value
        elif isinstance(value, str) and len(value) <= 300:
            result[name] = redact_source(value)
    return result

def process(pid):
    try:
        p = Path('/proc')/str(int(pid))
        raw = (p/'stat').read_text()
        fields = raw.rsplit(') ', 1)[1].split()
        result = {'pid':int(pid), 'ppid':int(fields[1]), 'pgrp':int(fields[2]),
                  'start_ticks':int(fields[19]), 'state':fields[0]}
        ns = re.search(r'^NSpid:\s*(.*)$', (p/'status').read_text(), re.M)
        result['namespace_pids'] = [int(x) for x in ns[1].split()] if ns else []
        # Export two non-secret dispatcher controls, never an environment dump.
        result['dispatcher_env'] = {}
        for entry in (p/'environ').read_bytes().split(b'\0'):
            if b'=' not in entry:
                continue
            key, value = entry.split(b'=', 1)
            if key in (b'NOX_DISPATCHER_SAFE', b'NOX_DISPATCHER_WORKERS') and re.fullmatch(rb'[0-9]{1,2}', value):
                result['dispatcher_env'][key.decode()] = value.decode()
        again = (p/'stat').read_text().rsplit(') ', 1)[1].split()
        if int(again[19]) != result['start_ticks']:
            raise ValueError('PID_CHANGED')
        return result
    except (OSError, ValueError, IndexError):
        return {'pid':pid, 'status':'UNKNOWN_OR_CHANGED'}

def runtime_snapshot():
    rows = []
    cp = subprocess.run(['supervisorctl', 'status'], capture_output=True, text=True,
                        timeout=10, check=False)
    keep = {'nox-dispatcher-t855u', 'nox-ds41-8098', 'nox-proxy', 'nox-web29-18775',
            'nox-agent-architect-t859u', 'nox-agent-integrator-t859u', 'nox-agent-tuner-t858u'}
    for line in cp.stdout.splitlines():
        m = re.match(r'^([A-Za-z0-9_.:-]+)\s+([A-Z]+)(?:\s+pid\s+(\d+))?', line)
        if m and m[1] in keep:
            rows.append({'service':m[1], 'state':m[2],
                         'identity':process(int(m[3])) if m[3] else None})
    flags = {}
    for path in FLAGS:
        try:
            mode = path.lstat().st_mode
            flags[str(path)] = 'PRESENT' if stat.S_ISREG(mode) else 'UNSAFE_TYPE'
        except FileNotFoundError:
            flags[str(path)] = 'ABSENT'
        except OSError:
            flags[str(path)] = 'UNKNOWN'
    resources = {}
    for name in ('memory.current','memory.max','memory.stat','memory.events',
                 'memory.pressure','cpu.pressure','cpu.stat','cpu.max','io.pressure'):
        try:
            resources[name] = (Path('/sys/fs/cgroup')/name).read_text()[:10000]
        except OSError:
            resources[name] = None
    return {'time_unix':time.time(), 'supervisor_rc':cp.returncode, 'services':rows,
            'flags':flags, 'resources':resources}

def locks():
    try:
        lines = Path('/proc/locks').read_text().splitlines()
    except OSError:
        lines = []
    rows = []
    for path in LOCK_PATHS:
        row = {'path':str(path), 'scope':'PROC_LOCKS_OBSERVATION_NOT_LEASE_ACQUISITION'}
        try:
            s = path.lstat()
            row.update({'present':True, 'inode':s.st_ino, 'device_major':os.major(s.st_dev),
                        'device_minor':os.minor(s.st_dev), 'type_regular':stat.S_ISREG(s.st_mode)})
            matches = []
            for line in lines:
                m = re.search(r'\b([0-9a-f]+):([0-9a-f]+):(\d+)\b', line)
                if m and (int(m[1],16),int(m[2],16),int(m[3])) == (os.major(s.st_dev),os.minor(s.st_dev),s.st_ino):
                    matches.append(line[:250])
            row['matching_kernel_locks'] = matches[:10]
        except FileNotFoundError:
            row['present'] = False
        except OSError:
            row['status'] = 'UNKNOWN'
        rows.append(row)
    return rows


def configuration():
    path = ROOT/'config/owner_native_subagents.json'
    try:
        data, raw, info = obj(path, 1000000)
        row = scalar_projection(data, ('schema','mode','target','owner_authorized','instance_id','policy_id','catalog_sha256'))
        row.update({'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),
                    'owner_uid':info.st_uid,'mode_bits':oct(stat.S_IMODE(info.st_mode))})
        row['module_pins'] = {k:v for k,v in data.get('module_pins',{}).items()
                              if identifier(k) and isinstance(v,str) and SHA.fullmatch(v)}
        policy = data.get('policy',{})
        row['policy'] = scalar_projection(policy, ('path','sha256')) if isinstance(policy,dict) else None
        catalog = data.get('catalog')
        row['catalog_shape'] = {'type':type(catalog).__name__}
        if isinstance(catalog,dict):
            pages = catalog.get('pages',[])
            row['catalog_shape']['schema'] = identifier(catalog.get('schema'))
            row['catalog_shape']['pages'] = len(pages) if isinstance(pages,list) else None
            tasks = []
            if isinstance(pages,list):
                for page in pages[:32]:
                    if isinstance(page,dict) and isinstance(page.get('tasks'),list):
                        tasks.extend(page['tasks'][:100])
            if isinstance(catalog.get('tasks'),list):
                tasks.extend(catalog['tasks'][:100])
            row['catalog_shape']['tasks'] = [
                {k:identifier(task.get(k)) for k in ('id','task_id','handler','subagent','status')}
                for task in tasks[:512] if isinstance(task,dict)]
        emit('CONFIG', row)
    except (OSError, ValueError, TypeError) as exc:
        emit('CONFIG', {'path':str(path),'status':'UNKNOWN','error':type(exc).__name__})




def startup_diagnostics():
    for channel in ('stderr','stdout'):
        result=subprocess.run(['supervisorctl','tail','-24000','nox-dispatcher-t855u',channel],
            capture_output=True,text=True,timeout=12,check=False)
        # Export frames and exception summaries only, never arbitrary task/log text.
        found=[]
        for line in result.stdout.splitlines():
            clean=redact_source(line)
            if clean.startswith('Traceback (most recent call last):'):
                found.append(clean)
            elif re.match(r'^\s*File "[^"\r\n]{1,220}\.py", line [0-9]+, in [A-Za-z_][A-Za-z0-9_<>]*\s*$', clean):
                found.append(clean)
            elif re.match(r'^[A-Za-z_.]*(?:Error|Exception|Hold):',clean):
                found.append(clean[:600])
            elif re.search(r'\bHOLD_[A-Z0-9_]{4,120}\b',clean):
                found.extend(re.findall(r'\bHOLD_[A-Z0-9_]{4,120}\b',clean))
        emit('STARTUP_LOG',{'channel':channel,'command_rc':result.returncode,
            'tail_bound_bytes':24000,'projection':'TRACEBACK_FRAMES_AND_REDACTED_EXCEPTION_SUMMARIES',
            'lines':found[-80:]})
    for name in ('nox_dispatcher_t855u.py','owner_subagent_dispatcher.py','owner_subagent_processes.py',
                 'owner_autonomy_pool.py','owner_resource_policy.py','owner_subagent_instruction_truth.py'):
        try:
            raw,_=safe_read(SCRIPTS/name,130000)
            row={'path':str(SCRIPTS/name),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            if name=='owner_subagent_instruction_truth.py':
                source=raw.decode('utf-8');clean=redact_source(source)
                row.update(source=clean,source_redacted=source!=clean)
            emit('STARTUP_SOURCE',row)
        except (OSError,ValueError,UnicodeError) as exc:
            emit('STARTUP_SOURCE',{'path':str(SCRIPTS/name),'state':'UNAVAILABLE','error':type(exc).__name__})

def main():
    emit('SNAPSHOT_A',runtime_snapshot())
    startup_diagnostics()
    configuration()
    emit('LOCKS',locks())
    time.sleep(1)
    emit('SNAPSHOT_B',runtime_snapshot())
    print('NOX_MAINT_INSPECT_COMPLETE=true',flush=True)

if __name__=='__main__':
    main()
