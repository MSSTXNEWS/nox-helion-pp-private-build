#!/usr/bin/env python3
"""Fixed read-only NOX queue/pool inspection. No model calls or native writes."""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
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
MAX_PROC_LOCKS_BYTES = 1024 * 1024
MAX_LOCK_RECORDS_PER_PATH = 64
PLANNER_MEMORY_TRACE_SHAS = frozenset((
    'fecce4cc6345b6d686f3053753645f97d57f22f68e5de405c66027c19712e15c',
    'aa0dd1c8266106b599ce83b64b7af77c7a4f32377fc09cd545e1f9697bda4420',
    'e7bc83e4dea75f08ecb4e92fedf6ef98e0620f17c7b3b28ccb4728c6ddda68ac',
))
MAX_SOURCE_FILE = 2 * 1024 * 1024
MAX_SOURCE_TOTAL = 16 * 1024 * 1024


def approved_relative(value):
    if (not isinstance(value,str) or not 1<=len(value)<=240
            or any(not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*',part)
                   or part in ('.','..') for part in value.split('/'))):
        raise ValueError('UNAPPROVED_RELATIVE_PATH')
    return value


def project_observation_scope(config):
    project=config.get('project_executor') or {}
    root=(project.get('roots') or {}).get('NOX_PROJECT_SOURCE') or {}
    expected=ROOT/'projects/owner_executor/source_workspace'
    allowed=root.get('allowed_paths')
    if (config.get('schema')!='NOX_NATIVE_SUBAGENT_BINDING_V1'
            or project.get('schema')!='NOX_PROJECT_EXECUTOR_CONFIG_V1'
            or root.get('path')!=str(expected)
            or root.get('integration_kind')!='SOURCE_WORKSPACE'
            or project.get('package_root')!=str(ROOT/'state/dispatcher/project_executor/package')
            or project.get('state_root')!=str(ROOT/'state/dispatcher/project_executor/run')
            or not isinstance(allowed,list) or not 1<=len(allowed)<=256
            or not all(isinstance(path,str) for path in allowed)
            or len(set(allowed))!=len(allowed) or root.get('deny_paths',[])!=[]):
        raise ValueError('PROJECT_OBSERVATION_SCOPE')
    return project,expected,sorted(approved_relative(path) for path in allowed)

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
    host_clock_initial = _host_boot_clock_snapshot()
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
    host_clock_final = _host_boot_clock_snapshot()
    host_clock = _host_clock_pair(host_clock_initial, host_clock_final)
    for row in rows:
        if isinstance(row.get('identity'), dict):
            row['identity'] = _attach_pid_start_epoch(row['identity'], host_clock)
    return {'time_unix':host_clock_final.get('observed_at_unix', time.time()),
            'host_clock_snapshot':host_clock,
            'host_clock_snapshot_status':host_clock['status'],
            'host_clock_snapshot_sha256':host_clock_final.get('snapshot_sha256'),
            'snapshot_complete':host_clock['status'] == 'STABLE',
            'supervisor_rc':cp.returncode, 'services':rows,
            'flags':flags, 'resources':resources}

def _proc_stat_identity(pid, raw):
    """Extract identity fields without splitting a process comm on its ')' chars."""
    prefix = str(pid) + ' ('
    if not raw.startswith(prefix) or ') ' not in raw:
        raise ValueError('PID_STAT_MISMATCH')
    fields = raw.rsplit(') ', 1)[1].split()
    if len(fields) < 20 or not fields[19].isdigit() or not fields[1].isdigit():
        raise ValueError('PID_STAT_SHAPE')
    return {'pid':pid, 'ppid':int(fields[1]), 'state':fields[0],
            'start_ticks':int(fields[19])}


def process_identity(pid, proc_root=Path('/proc')):
    """Resolve a lock PID to one stable PID/start-tick/command observation."""
    if type(pid) is not int or pid < 2:
        return {'pid':pid, 'resolution':'PID_NOT_RESOLVABLE'}
    proc = Path(proc_root) / str(pid)
    try:
        first = _proc_stat_identity(pid, (proc/'stat').read_text())
        comm = (proc/'comm').read_text().strip()[:128]
        argv = (proc/'cmdline').read_bytes()[:4096].decode('utf-8', 'replace').strip('\0').split('\0')
        exe = None
        try:
            exe = os.path.basename(os.readlink(proc/'exe'))[:128]
        except OSError:
            pass
        status_text = (proc/'status').read_text()
        uid_match = re.search(r'^Uid:\s+(\d+)', status_text, re.M)
        argv0 = os.path.basename(argv[0])[:128] if argv and argv[0] else None
        script = next((os.path.basename(value)[:128] for value in argv[1:5]
                       if value.endswith(('.py', '.sh')) and '\n' not in value), None)
        command = ' '.join(value for value in (exe or argv0 or comm, script) if value)
        # The command projection intentionally omits all argument values.
        command = redact_source(command)[:260]
        last = _proc_stat_identity(pid, (proc/'stat').read_text())
        if last['start_ticks'] != first['start_ticks'] or last['ppid'] != first['ppid']:
            raise ValueError('PID_CHANGED_DURING_IDENTITY_READ')
        return {**first, 'comm':redact_source(comm)[:128], 'executable':exe or argv0,
                'script':script, 'command':command,
                'uid':int(uid_match[1]) if uid_match else None,
                'resolution':'VERIFIED_PID_START_TICKS_AND_COMMAND'}
    except (OSError, ValueError, IndexError) as exc:
        return {'pid':pid, 'resolution':'UNKNOWN_OR_CHANGED',
                'reason':type(exc).__name__}


def _host_boot_clock_snapshot(proc_root=Path('/proc')):
    """Capture read-only boot identity and clock basis for PID start ticks."""
    proc_root = Path(proc_root)
    try:
        boot_id = (proc_root/'sys/kernel/random/boot_id').read_text().strip().lower()
        if not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
                            boot_id):
            raise ValueError('BOOT_ID_SHAPE')
        uptime_fields = (proc_root/'uptime').read_text().split()
        uptime_seconds = float(uptime_fields[0])
        if not math.isfinite(uptime_seconds) or uptime_seconds < 0:
            raise ValueError('UPTIME_SHAPE')
        sc_clk_tck = os.sysconf('SC_CLK_TCK')
        if (type(sc_clk_tck) is not int or sc_clk_tck <= 0):
            raise ValueError('SC_CLK_TCK_SHAPE')
        observed_at_unix = time.time()
        if not math.isfinite(observed_at_unix):
            raise ValueError('WALL_CLOCK_SHAPE')
        record = {'boot_id':boot_id, 'uptime_seconds':uptime_seconds,
                  'sc_clk_tck':sc_clk_tck, 'observed_at_unix':observed_at_unix,
                  'boot_epoch_unix_estimate':observed_at_unix-uptime_seconds}
        digest = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':'),
                                             allow_nan=False).encode('utf-8')).hexdigest()
        return {'status':'VERIFIED', **record, 'snapshot_sha256':digest}
    except (OSError, ValueError, TypeError, IndexError, OverflowError) as exc:
        return {'status':'UNAVAILABLE', 'reason':type(exc).__name__}


def _host_boot_clock_pair_status(initial, final):
    if initial.get('status') != 'VERIFIED' or final.get('status') != 'VERIFIED':
        return 'UNAVAILABLE'
    if initial['boot_id'] != final['boot_id']:
        return 'BOOT_ID_CHANGED'
    if initial['sc_clk_tck'] != final['sc_clk_tck']:
        return 'SC_CLK_TCK_CHANGED'
    if final['uptime_seconds'] < initial['uptime_seconds']:
        return 'UPTIME_DECREASED'
    return 'STABLE'


def _host_clock_pair(initial, final):
    return {'status':_host_boot_clock_pair_status(initial, final),
            'initial':initial, 'final':final}


def _pid_start_epoch_binding(pid, start_ticks, host_clock):
    if host_clock.get('status') != 'STABLE':
        return {'host_clock_binding_status':host_clock.get('status', 'UNAVAILABLE')}
    if type(pid) is not int or pid < 1 or type(start_ticks) is not int or start_ticks < 0:
        return {'host_clock_binding_status':'PID_START_TICKS_UNAVAILABLE'}
    final = host_clock.get('final') or {}
    clock_ticks = final.get('sc_clk_tck')
    boot_epoch = final.get('boot_epoch_unix_estimate')
    if (type(clock_ticks) is not int or clock_ticks <= 0
            or not isinstance(boot_epoch, (int, float)) or not math.isfinite(boot_epoch)):
        return {'host_clock_binding_status':'HOST_CLOCK_BASIS_UNAVAILABLE'}
    return {'host_clock_binding_status':'VERIFIED',
            'host_boot_id':final['boot_id'],
            'host_clock_snapshot_sha256':final['snapshot_sha256'],
            'process_start_epoch_unix_estimate':boot_epoch + start_ticks / clock_ticks,
            'process_start_epoch_method':(
                'snapshot_wall_time_minus_proc_uptime_plus_start_ticks_over_SC_CLK_TCK')}


def _attach_pid_start_epoch(identity, host_clock):
    if not isinstance(identity, dict):
        return identity
    result = dict(identity)
    result.update(_pid_start_epoch_binding(identity.get('pid'), identity.get('start_ticks'),
                                           host_clock))
    return result


def _host_clock_chain_status(snapshots):
    pairs = list(snapshots)
    for snapshot in pairs:
        if not isinstance(snapshot, dict) or snapshot.get('status') != 'STABLE':
            return snapshot.get('status', 'UNAVAILABLE') if isinstance(snapshot, dict) else 'UNAVAILABLE'
    finals = [snapshot['final'] for snapshot in pairs]
    for earlier, later in zip(finals, finals[1:]):
        status = _host_boot_clock_pair_status(earlier, later)
        if status != 'STABLE':
            return status
    return 'STABLE'


def _parse_proc_lock(line):
    """Parse a Linux /proc/locks record, including blocked waiter records."""
    fields = line.split()
    if len(fields) < 7:
        return None
    blocked = len(fields) > 1 and fields[1] == '->'
    if blocked:
        fields = [fields[0], *fields[2:]]
    if len(fields) < 7 or not fields[0].endswith(':'):
        return None
    key = re.fullmatch(r'([0-9a-fA-F]+):([0-9a-fA-F]+):(\d+)', fields[5])
    if not key:
        return None
    try:
        lock_pid = int(fields[4])
    except ValueError:
        return None
    return {'lock_id':fields[0][:-1], 'lock_kind':fields[1],
            'lock_scope':fields[2], 'access':fields[3],
            'lock_pid':lock_pid if lock_pid >= 0 else None,
            'pid_kind':'PID' if lock_pid >= 0 else 'OPEN_FILE_DESCRIPTION_OR_UNKNOWN',
            'device_major':int(key[1],16), 'device_minor':int(key[2],16),
            'inode':int(key[3]), 'record_role':'BLOCKED_WAITER' if blocked else 'HELD',
            'raw':line[:250]}


def _kernel_lock_lines_for_identity(lines, identity):
    if identity is None:
        return ()
    expected = (os.major(identity[0]), os.minor(identity[0]), identity[1])
    matched = []
    for line in lines:
        key = re.search(r'\b([0-9a-fA-F]+):([0-9a-fA-F]+):(\d+)\b', line)
        if key and (int(key[1],16), int(key[2],16), int(key[3])) == expected:
            matched.append(line[:250])
    return tuple(sorted(matched))


def _read_proc_locks(path):
    try:
        with open(path, 'r', encoding='ascii', errors='replace') as stream:
            raw = stream.read(MAX_PROC_LOCKS_BYTES + 1)
        truncated = len(raw) > MAX_PROC_LOCKS_BYTES
        raw = raw[:MAX_PROC_LOCKS_BYTES]
        return {'status':'READ_TRUNCATED' if truncated else 'READ_OK',
                'raw':raw, 'lines':raw.splitlines(), 'truncated':truncated,
                'error':None}
    except OSError as exc:
        return {'status':'UNAVAILABLE', 'raw':'', 'lines':[], 'truncated':False,
                'error':type(exc).__name__}


def locks(proc_locks_path=Path('/proc/locks'), lock_paths=None, proc_root=Path('/proc')):
    """Read lock-file inodes and kernel lock holders with explicit completeness.

    This is observation only: it neither acquires nor releases any lease.
    Every PID in a matching proc-lock record is resolved with start_ticks and a
    command projection; PID reuse or unsupported OFD ownership fails closed.
    """
    paths = tuple(LOCK_PATHS if lock_paths is None else lock_paths)
    observed_at = time.time()
    host_clock_initial = _host_boot_clock_snapshot(proc_root)
    before = {}
    rows = []
    for path in paths:
        row = {'path':str(path), 'scope':'PROC_LOCKS_OBSERVATION_NOT_LEASE_ACQUISITION',
               'observation_time_unix':observed_at}
        try:
            info = Path(path).lstat()
            regular = stat.S_ISREG(info.st_mode)
            before[str(path)] = (info.st_dev, info.st_ino, info.st_mode)
            row.update({'present':True, 'inode':info.st_ino,
                'device_major':os.major(info.st_dev), 'device_minor':os.minor(info.st_dev),
                'type_regular':regular,
                'path_identity_status':'STABLE_CANDIDATE' if regular else 'UNSAFE_PATH_TYPE'})
        except FileNotFoundError:
            row.update({'present':False, 'path_identity_status':'NOT_PRESENT'})
        except OSError as exc:
            row.update({'present':None, 'path_identity_status':'UNKNOWN',
                        'path_error':type(exc).__name__})
        rows.append(row)

    first_snapshot = _read_proc_locks(proc_locks_path)
    lines = first_snapshot['lines']
    proc_status = first_snapshot['status']
    proc_error = first_snapshot['error']

    parsed = [_parse_proc_lock(line) for line in lines]
    holder_cache = {}
    holder_pids_by_path = {}
    for row in rows:
        if not row.get('type_regular'):
            row.update({'proc_locks_read_status':proc_status,
                        'proc_locks_error':proc_error,
                        'matching_kernel_locks':[], 'matching_lock_records':[],
                        'lock_observation_complete':False})
            continue
        identity = before.get(row['path'])
        if identity is None:
            row.update({'proc_locks_read_status':proc_status,
                        'proc_locks_error':proc_error,
                        'matching_kernel_locks':[], 'matching_lock_records':[],
                        'lock_observation_complete':False})
            continue
        matching = []
        holder_pids_by_path[row['path']] = set()
        unparsed_matches = 0
        for line, record in zip(lines, parsed):
            if record is None:
                inode_match = re.search(r'\b([0-9a-fA-F]+):([0-9a-fA-F]+):(\d+)\b', line)
                if inode_match and (int(inode_match[1],16), int(inode_match[2],16),
                                    int(inode_match[3])) == (os.major(identity[0]),
                                    os.minor(identity[0]), identity[1]):
                    unparsed_matches += 1
                continue
            if (record['device_major'], record['device_minor'], record['inode']) != (
                    os.major(identity[0]), os.minor(identity[0]), identity[1]):
                continue
            item = dict(record)
            if item['lock_pid'] is None:
                item['holder_identity'] = {'resolution':'PID_NOT_EXPOSED_BY_PROC_LOCKS'}
            else:
                holder_pids_by_path[row['path']].add(item['lock_pid'])
                if item['lock_pid'] not in holder_cache:
                    holder_cache[item['lock_pid']] = process_identity(item['lock_pid'], proc_root)
                item['holder_identity'] = holder_cache[item['lock_pid']]
            matching.append(item)
        try:
            after = Path(row['path']).lstat()
            stable = (after.st_dev, after.st_ino, after.st_mode) == identity
        except OSError:
            stable = False
        unresolved = any(item['holder_identity'].get('resolution') !=
                         'VERIFIED_PID_START_TICKS_AND_COMMAND' for item in matching)
        records_truncated = len(matching) > MAX_LOCK_RECORDS_PER_PATH
        row.update({'path_identity_status':'STABLE' if stable else 'CHANGED_DURING_READ',
            'proc_locks_read_status':proc_status, 'proc_locks_error':proc_error,
            'proc_locks_line_count':len(lines),
            'matching_kernel_locks':[item['raw'] for item in matching[:10]],
            'matching_lock_count':len(matching),
            'matching_lock_records':matching[:MAX_LOCK_RECORDS_PER_PATH],
            'unparsed_matching_lock_count':unparsed_matches,
            'matching_lock_records_truncated':records_truncated,
            'lock_observation_complete':False})

    # Re-read after PID resolution. If a target inode's lock lines or either
    # read status changed during mapping, preserve records but fail closed.
    second_snapshot = (_read_proc_locks(proc_locks_path) if proc_status == 'READ_OK'
                       else {'status':'NOT_ATTEMPTED', 'raw':'', 'lines':[],
                             'truncated':False, 'error':None})
    # Re-resolve every distinct PID observed in matching records only after the
    # final /proc/locks read. Compare the stable identity projection, not the
    # transient process state, so PID reuse or an exec/comm change fails closed.
    identity_fields = ('pid', 'start_ticks', 'comm', 'command')
    def identity_projection(identity):
        if (not isinstance(identity, dict) or identity.get('resolution') !=
                'VERIFIED_PID_START_TICKS_AND_COMMAND'):
            return {'pid':identity.get('pid') if isinstance(identity, dict) else None,
                    'resolution':identity.get('resolution') if isinstance(identity, dict)
                    else 'UNKNOWN_OR_CHANGED'}
        return {key:identity.get(key) for key in identity_fields}

    holder_rechecks = {}
    observed_holder_pids = sorted({pid for values in holder_pids_by_path.values()
                                   for pid in values})
    for pid in observed_holder_pids:
        before_identity = holder_cache.get(pid, {'pid':pid, 'resolution':'UNKNOWN_OR_CHANGED'})
        after_identity = process_identity(pid, proc_root)
        before_projection = identity_projection(before_identity)
        after_projection = identity_projection(after_identity)
        stable = (before_identity.get('resolution') ==
                  'VERIFIED_PID_START_TICKS_AND_COMMAND'
                  and after_identity.get('resolution') ==
                  'VERIFIED_PID_START_TICKS_AND_COMMAND'
                  and all(before_projection.get(key) == after_projection.get(key)
                          for key in identity_fields))
        holder_rechecks[pid] = {'pid':pid, 'status':'STABLE' if stable
                                else 'CHANGED_OR_UNAVAILABLE',
                                'before':before_projection, 'after':after_projection}

    # Read again only after lock and holder identity observations. This binds
    # all reported process start epochs to one verified host boot/clock snapshot.
    host_clock_final = _host_boot_clock_snapshot(proc_root)
    host_clock_snapshot = _host_clock_pair(host_clock_initial, host_clock_final)
    host_clock_status = host_clock_snapshot['status']
    if host_clock_status != 'STABLE':
        for check in holder_rechecks.values():
            check['status'] = 'CHANGED_OR_UNAVAILABLE'
            check['host_clock_status'] = host_clock_status
    else:
        for pid, check in holder_rechecks.items():
            identity = check['after']
            start_ticks = identity.get('start_ticks')
            binding = _pid_start_epoch_binding(pid, start_ticks, host_clock_snapshot)
            check.update(binding)
            check['host_clock_status'] = host_clock_status
            if binding.get('host_clock_binding_status') != 'VERIFIED':
                check['status'] = 'CHANGED_OR_UNAVAILABLE'

    for row in rows:
        row.update({'host_clock_snapshot':host_clock_snapshot,
                    'host_clock_snapshot_status':host_clock_status,
                    'host_clock_snapshot_sha256':host_clock_final.get('snapshot_sha256')})
        if not row.get('type_regular') or row.get('path_identity_status') in (
                'NOT_PRESENT', 'UNKNOWN'):
            continue
        identity = before.get(row['path'])
        first_matches = _kernel_lock_lines_for_identity(first_snapshot['lines'], identity)
        second_matches = _kernel_lock_lines_for_identity(second_snapshot['lines'], identity)
        proc_stability = ('STABLE' if second_snapshot['status'] == 'READ_OK'
                          and second_matches == first_matches else 'CHANGED_OR_UNAVAILABLE')
        first_sha = hashlib.sha256('\n'.join(first_matches).encode('ascii', 'replace')).hexdigest()
        second_sha = hashlib.sha256('\n'.join(second_matches).encode('ascii', 'replace')).hexdigest()
        records = row.get('matching_lock_records', [])
        row_holder_rechecks = [holder_rechecks[pid] for pid in
                               sorted(holder_pids_by_path.get(row['path'], ()))
                               if pid in holder_rechecks]
        holder_recheck_truncated = len(row_holder_rechecks) > MAX_LOCK_RECORDS_PER_PATH
        for item in records:
            if item.get('lock_pid') is not None:
                check = holder_rechecks.get(item['lock_pid'])
                item['holder_identity_recheck'] = (check['status'] if check else
                                                   'NOT_OBSERVED')
                if (check and check.get('status') == 'STABLE'
                        and check.get('host_clock_binding_status') == 'VERIFIED'):
                    item['holder_identity'].update(_pid_start_epoch_binding(
                        item['lock_pid'], check['after'].get('start_ticks'), host_clock_snapshot))
        holder_recheck_stability = (
            'STABLE' if all(item['status'] == 'STABLE' for item in row_holder_rechecks)
            else 'CHANGED_OR_UNAVAILABLE')
        unresolved = any(item['holder_identity'].get('resolution') !=
                         'VERIFIED_PID_START_TICKS_AND_COMMAND' for item in records)
        complete = (proc_status == 'READ_OK' and proc_stability == 'STABLE'
                    and row.get('path_identity_status') == 'STABLE'
                    and not row.get('matching_lock_records_truncated')
                    and not row.get('unparsed_matching_lock_count') and not unresolved
                    and holder_recheck_stability == 'STABLE'
                    and host_clock_status == 'STABLE'
                    and not holder_recheck_truncated)
        row.update({'proc_locks_stability':proc_stability,
                    'proc_locks_recheck_status':second_snapshot['status'],
                    'proc_locks_sha256':first_sha,
                    'proc_locks_recheck_sha256':second_sha,
                    'holder_identity_recheck_status':holder_recheck_stability,
                    'holder_identity_rechecks':row_holder_rechecks[:MAX_LOCK_RECORDS_PER_PATH],
                    'holder_identity_rechecks_truncated':holder_recheck_truncated,
                    'lock_observation_complete':complete})
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




def hash_summary():
    names = SOURCE_NAMES + ('nox_dispatcher_t855u.py', 'owner_resource_policy.py',
                            'test_owner_four_queue.py', 'test_owner_normal3_continuity.py',
                            'owner_subagent_instruction_truth.py')
    for name in names:
        try:
            raw, info = safe_read(SCRIPTS/name, 300000)
            emit('INSTALLED_SOURCE', {'path':str(SCRIPTS/name), 'bytes':len(raw),
                'sha256':hashlib.sha256(raw).hexdigest(), 'mtime_ns':info.st_mtime_ns})
        except (OSError, ValueError) as exc:
            emit('INSTALLED_SOURCE', {'path':str(SCRIPTS/name), 'state':'UNAVAILABLE', 'error':type(exc).__name__})

def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def s03_receipt_check(receipt):
    import sqlite3
    path = ROOT/'kb/knowledge.sqlite'
    try:
        if any(p.is_symlink() for p in (path, *path.parents)) or not stat.S_ISREG(path.stat().st_mode):
            return {'verified':False, 'state':'UNSAFE_DATABASE_PATH'}
        digest = hashlib.sha256(encoded(receipt)).hexdigest()
        text = 'NOX native job '+receipt['job_id']+' '+receipt['phase']+' receipt_sha256 '+digest
        with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=.2)) as conn:
            conn.execute('PRAGMA query_only=ON')
            deadline = time.monotonic()+2
            conn.set_progress_handler(lambda: int(time.monotonic()>deadline), 1000)
            rows = conn.execute("SELECT id,meta,sha256 FROM s03_items WHERE segment='M2' AND text=? AND provenance=? LIMIT 2",
                                (text, 'owner_native_subagents')).fetchall()
        verified = (len(rows)==1 and rows[0][2]==hashlib.sha256(('M2|'+text).encode()).hexdigest()
                    and json.loads(rows[0][1]).get('receipt') == receipt)
        return {'verified':verified, 's03_item_id':rows[0][0] if verified else None,
                'receipt_sha256':digest, 'scope':'EXACT_READ_ONLY_SQLITE_RECEIPT_MATCH'}
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        return {'verified':False, 'state':'UNAVAILABLE', 'error':type(exc).__name__}

def leaf_queue_summary():
    data, raw, _ = obj(ROOT/'state/dispatcher/state.json',16*1024*1024)
    tasks=data.get('tasks')
    if not isinstance(tasks,dict) or len(tasks)>5000:
        raise ValueError('QUEUE_SHAPE')
    counts={}
    for task in tasks.values():
        if isinstance(task,dict):
            state=identifier(task.get('status')) or 'UNKNOWN'
            counts[state]=counts.get(state,0)+1
    emit('POST_QUEUE', {'task_count':len(tasks), 'counts':counts, 'sha256':hashlib.sha256(raw).hexdigest()})
    for key,task in tasks.items():
        if not isinstance(task,dict) or task.get('handler') not in ('owner_native_typed_leaf','owner_native_subagent_review'):
            continue
        row={k:identifier(task.get(k)) for k in ('id','handler','status','queue_id','parent_task_id','scope')}
        row['key']=identifier(key)
        claim=task.get('owner_claim')
        row['claim']=scalar_projection(claim,('pid','worker','nonce','at')) if isinstance(claim,dict) else None
        row.update(scalar_projection(task,('native_queue_sequence','original_task_accepted','retries','note')))
        result=task.get('result')
        if isinstance(result,dict):
            row['result']=scalar_projection(result,('schema','verified','scope','receipt_sha256','original_task_accepted','check_passed'))
            receipt=result.get('receipt')
            if isinstance(receipt,dict):
                row['receipt']=scalar_projection(receipt,('schema','phase','task_id','job_id','source_sha256','parent_task_id','queue_id','original_task_accepted','training_started','service_or_weights_changed','finished_at'))
                row['receipt_sha_matches']=hashlib.sha256(encoded(receipt)).hexdigest()==result.get('receipt_sha256')
                row['receipt_claim_matches']=receipt.get('claim')==claim
                event=receipt.get('worker_result')
                if isinstance(event,dict):
                    row['worker_result']=scalar_projection(event,('kind','role','pid','id','state','elapsed_ms'))
                    leaf=event.get('leaf_evidence')
                    if isinstance(leaf,dict):
                        row['leaf']=scalar_projection(leaf,('operation','queue_id','parent_task_id','original_task_accepted','scope','check_completed','check_passed','claim','started_at','finished_at','source_sha256','model_called'))
                        row['leaf_sha_matches']=hashlib.sha256(encoded(leaf)).hexdigest()==event.get('leaf_evidence_sha256')
                        row['leaf']['blockers']=[identifier(x) for x in leaf.get('blockers',[])[:20]]
                        worker=leaf.get('worker')
                        row['leaf']['worker']=scalar_projection(worker,('pid','ppid','process_starttime')) if isinstance(worker,dict) else None
                row['s03']=s03_receipt_check(receipt)
        emit('POST_TASK',row)

def worker_status_sample():
    host_clock_initial = _host_boot_clock_snapshot()
    data,raw,_=obj(ROOT/'status/agents_t856u.json',2*1024*1024)
    native=data.get('native_subexecutors')
    if not isinstance(native,dict):
        host_clock = _host_clock_pair(host_clock_initial,
                                      _host_boot_clock_snapshot())
        emit('POST_WORKERS', {'state':'NO_NATIVE_STATUS',
            'host_clock_snapshot':host_clock,
            'host_clock_snapshot_status':host_clock['status']})
        return
    director=native.get('director') or {}
    observed_director=process(director.get('pid')) if type(director.get('pid')) is int else None
    row={'time_unix':time.time(), 'observed_at':native.get('observed_at'),
         'claimed_director':scalar_projection(director,('pid','ppid','process_starttime')),
         'observed_director':observed_director,'workers':[]}
    for worker in native.get('workers',[])[:10]:
        if not isinstance(worker,dict):
            continue
        claimed=scalar_projection(worker,('pid','ppid','process_starttime','role','state','heartbeat_at','current_task','native_pid_verified'))
        identity=process(worker['pid']) if type(worker.get('pid')) is int else None
        verified=(isinstance(identity,dict) and identity.get('state') in ('R','S','D','I')
                  and identity.get('start_ticks')==worker.get('process_starttime')
                  and identity.get('ppid')==director.get('pid')
                  and isinstance(observed_director,dict)
                  and observed_director.get('start_ticks')==director.get('process_starttime'))
        row['workers'].append({'claimed':claimed,'observed':identity,'verified':verified})
    project=native.get('project_queues')
    if isinstance(project,dict):
        row['project']=scalar_projection(project,('state','received_unique_tasks','dispatch_cap','bound_leaf_subtasks','bound_project_subtasks','original_task_acceptance_added','scope'))
        for name in ('queues','leaf_status','project_status'):
            row['project'][name]={k:v for k,v in (project.get(name) or {}).items() if identifier(k) and type(v) is int}
        progress=project.get('catalog_progress')
        if isinstance(progress,dict):
            row['project']['catalog_progress']=scalar_projection(progress,tuple(progress))
    admission=native.get('last_admission')
    row['admission']=scalar_projection(admission,('state','jobs_started','process_count','process_target','next_action')) if isinstance(admission,dict) else None
    resource=native.get('resource_admission')
    if isinstance(resource,dict):
        row['resource_admission']=scalar_projection(resource,('native_verified','instance_id',
            'stop_active','source_sha_verified','owner_scope_verified','cgroup_memory_ratio',
            'raw_cgroup_memory_ratio','effective_cgroup_memory_ratio','projected_cgroup_memory_ratio',
            'cpu_pressure','admission_class'))
        for key in ('bounded_cpu_budget','bounded_cpu_decision'):
            value=resource.get(key)
            if isinstance(value,dict):row['resource_admission'][key]=scalar_projection(value,tuple(value))
    row['pool_lifecycle']=scalar_projection(native.get('pool_lifecycle') or {},
        ('last_started_at','last_closed_at','last_close_reason'))
    relay=native.get('systemic_relay')
    if isinstance(relay,dict) and len(encoded(relay)) <= 100000:
        row['systemic_relay']=relay
    roles=(native.get('pool_lifecycle') or {}).get('roles')
    if isinstance(roles,dict) and len(encoded(roles)) <= 10000:
        row['pool_lifecycle']['roles']=roles
    host_clock_final = _host_boot_clock_snapshot()
    host_clock = _host_clock_pair(host_clock_initial, host_clock_final)
    row.update({'time_unix':host_clock_final.get('observed_at_unix', time.time()),
        'host_clock_snapshot':host_clock,
        'host_clock_snapshot_status':host_clock['status'],
        'host_clock_snapshot_sha256':host_clock_final.get('snapshot_sha256')})
    if isinstance(row.get('observed_director'), dict):
        row['observed_director'] = _attach_pid_start_epoch(row['observed_director'], host_clock)
    claimed_director = row.get('claimed_director') or {}
    observed_director = row.get('observed_director') or {}
    claimed_director_ticks = claimed_director.get('process_starttime')
    if (host_clock['status'] == 'STABLE' and isinstance(observed_director, dict)
            and observed_director.get('start_ticks') == claimed_director_ticks):
        claimed_director['start_ticks'] = claimed_director_ticks
        claimed_director.update(_pid_start_epoch_binding(
            claimed_director.get('pid'), claimed_director_ticks, host_clock))
    else:
        claimed_director['host_clock_binding_status'] = (
            host_clock['status'] if host_clock['status'] != 'STABLE'
            else 'CLAIM_IDENTITY_MISMATCH')
    for worker_row in row['workers']:
        if isinstance(worker_row.get('observed'), dict):
            worker_row['observed'] = _attach_pid_start_epoch(worker_row['observed'], host_clock)
        claimed = worker_row.get('claimed') or {}
        observed = worker_row.get('observed') or {}
        claimed_ticks = claimed.get('process_starttime')
        if (host_clock['status'] == 'STABLE' and isinstance(observed, dict)
                and observed.get('start_ticks') == claimed_ticks):
            claimed['start_ticks'] = claimed_ticks
            claimed.update(_pid_start_epoch_binding(claimed.get('pid'), claimed_ticks,
                                                    host_clock))
        else:
            claimed['host_clock_binding_status'] = (
                host_clock['status'] if host_clock['status'] != 'STABLE'
                else 'CLAIM_IDENTITY_MISMATCH')
        worker_row['verified'] = worker_row['verified'] and host_clock['status'] == 'STABLE'
    emit('POST_WORKERS',row)


INSTALL_REQUEST = '6964933277'
INSTALL_SOURCE = '32546b26b03019169c22f440af5c9f6ed5b0e09c'
PROJECT_PINS = {
    'project_work_tasks.json':'5347258ca08500d61173d9b36f69cc0632eff36d3ea1e10fcbbc420de69be000',
    'project_work_ideas.json':'e1c84397506c6e46fdc3ce71b63cc5eba2f5cc0cd290f8d1e32d4840e25972ae',
    'project_work_receipts_source.json':'b40c012a7280889722f446083c4cbe878db15fd6da34ac19855a99a0a099af71',
    'project_routing_4q.json':'f98ab106e16116a88947f6be207f73ec2bf9215ae107d415077b79479e91c671',
}

def project_summary():
    docs={}
    for name,pin in PROJECT_PINS.items():
        path=ROOT/'state/dispatcher'/name
        try:
            data,raw,_=obj(path,16*1024*1024)
            docs[name]=data
            rows=data.get('ideas') if name=='project_work_ideas.json' else data.get('tasks')
            emit('PROJECT_FILE',{'path':str(path),'bytes':len(raw),
                'sha256':hashlib.sha256(raw).hexdigest(),'matches_expected_source':hashlib.sha256(raw).hexdigest()==pin,
                'row_count':len(rows) if isinstance(rows,(dict,list)) else None})
        except (OSError,ValueError,TypeError) as exc:
            emit('PROJECT_FILE',{'path':str(path),'state':'UNAVAILABLE','error':type(exc).__name__})
    if len(docs)==4:
        try:
            original=[row['id'] for row in docs['project_work_tasks.json']['tasks']]
            original += [row['id'] for row in docs['project_work_ideas.json']['ideas']]
            route=docs['project_routing_4q.json'];routed=[row['task_id'] for row in route['tasks']]
            queues={}
            for row in route['tasks']:
                q=identifier(row.get('queue_id')) or 'UNKNOWN'
                queues[q]=queues.get(q,0)+1
            emit('PROJECT_COVERAGE',{'original_count':len(original),'original_unique':len(set(original)),
                'routed_count':len(routed),'routed_unique':len(set(routed)),
                'missing_count':len(set(original)-set(routed)), 'extra_count':len(set(routed)-set(original)),
                'queues':queues,'dispatch_cap':route.get('dispatch_cap'),
                'source_scope':'MANIFEST_HANDOFF_ONLY_NOT_ORIGINAL_TASK_ACCEPTANCE'})
        except (ValueError,TypeError,KeyError):
            emit('PROJECT_COVERAGE',{'state':'UNKNOWN_SCHEMA'})

def old_claim_comparison():
    backup=ROOT/'state/dispatcher/four_queue_rollback'/INSTALL_REQUEST
    try:
        current,_,_=obj(ROOT/'state/dispatcher/state.json',16*1024*1024)
        original,_,_=obj(backup/'original_queue_snapshot.json',16*1024*1024)
        final,_,_=obj(backup/'final_stopped_queue_snapshot.json',16*1024*1024)
        cur=current['tasks'];old=original['tasks'];last=final['tasks']
        if any(not isinstance(x,dict) for x in (cur,old,last)):
            raise ValueError('QUEUE_SCHEMA')
        emit('ORIGINAL_QUEUE_PRESERVATION',{'original_before_stop_count':len(old),
            'original_after_stop_count':len(last),'current_count':len(cur),
            'missing_before_stop_count':len(set(old)-set(cur)),
            'missing_after_stop_count':len(set(last)-set(cur)),
            'new_id_count':len(set(cur)-set(last))})
        for role in ('runtime','memory','weights'):
            tid='owner.native.v06.'+role+'.84780aaf911a'
            a,b,c=old.get(tid),last.get(tid),cur.get(tid)
            complete=all(isinstance(x,dict) for x in (a,b,c))
            row={'task_id':tid,'present_in_all_three':complete,
                 'current_full_row_equals_before_stop':complete and c==a,
                 'current_full_row_equals_final_stop':complete and c==b}
            if complete:
                row.update({'before_stop_row_sha256':hashlib.sha256(encoded(a)).hexdigest(),
                    'final_stop_row_sha256':hashlib.sha256(encoded(b)).hexdigest(),
                    'current_row_sha256':hashlib.sha256(encoded(c)).hexdigest(),
                    'status_before':identifier(a.get('status')),'status_current':identifier(c.get('status')),
                    'claim_equal':c.get('owner_claim')==a.get('owner_claim')==b.get('owner_claim'),
                    'claim_epoch_equal':c.get('owner_claim_epoch')==a.get('owner_claim_epoch')==b.get('owner_claim_epoch'),
                    'result_equal':c.get('result')==a.get('result')==b.get('result')})
            emit('OLD_REVIEW_PRESERVATION',row)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        emit('OLD_REVIEW_PRESERVATION',{'state':'UNAVAILABLE','error':type(exc).__name__})
    try:
        receipt,raw,_=obj(ROOT/'state/dispatcher'/('four_queue_install_'+INSTALL_REQUEST+'.json'),2*1024*1024)
        row=scalar_projection(receipt,('schema','state','request','source_sha','original_tasks_accepted','training_started','model_restarted','same_worker_identities','finished_at'))
        row.update({'sha256':hashlib.sha256(raw).hexdigest(),
                    'matches_install_request':str(receipt.get('request'))==INSTALL_REQUEST,
                    'matches_install_source':receipt.get('source_sha')==INSTALL_SOURCE})
        emit('INSTALL_RECEIPT',row)
    except (OSError,ValueError,TypeError) as exc:
        emit('INSTALL_RECEIPT',{'state':'UNAVAILABLE','error':type(exc).__name__})


def project_receipt_source(task,receipt,config,current_source):
    source=receipt.get('source_sha256')
    current_pin=(config.get('module_pins') or {}).get('owner_subagent_dispatcher.py')
    historical=config.get('historical_project_source_sha256') or []
    matched=(task.get('params') or {}).get('source_sha256')==source
    scope=('CURRENT' if current_source==current_pin==source else
           'HISTORICAL_VERIFY_ONLY' if source in historical and matched
                and task.get('status') in ('done','blocked','failed','cancelled') else 'UNREVIEWED_OR_CHANGED')
    return {'source_sha256':source,'current_callback_sha256':current_source,
            'matches_config_callback_pin':current_source==current_pin,
            'matches_durable_task_source':matched,'scope':scope,
            'source_authorized':scope in ('CURRENT','HISTORICAL_VERIFY_ONLY')}


def export_model_postimages(tid,plan,project,exported,remaining):
    import base64
    files=plan.get('files')
    if not isinstance(files,list) or not 1<=len(files)<=32:
        return {'complete':False,'state':'PLAN_FILES_INVALID','files':[]},0
    root_spec=project['roots'][plan['root_id']];root=Path(root_spec['path'])
    results=[];used=0
    for changed in files:
        row={'path':changed.get('path'),'sha256':changed.get('after_sha256')}
        try:
            path=changed['path'];p=Path(path);expected=changed['after_sha256']
            if (not isinstance(path,str) or p.is_absolute() or str(p)!=path
                    or any(x in ('','..','.') or x.startswith('.') for x in p.parts)
                    or path not in root_spec.get('allowed_paths',[])
                    or not isinstance(expected,str) or not re.fullmatch(r'[a-f0-9]{64}',expected)):
                row['state']='UNAPPROVED_PATH_OR_HASH'
            else:
                source,_=safe_read(root/path,100000);actual=hashlib.sha256(source).hexdigest()
                row.update(bytes=len(source),actual_sha256=actual)
                if actual!=expected:row['state']='POSTIMAGE_CHANGED'
                elif (path,actual) in exported:row['state']='ALREADY_EXPORTED'
                elif used+len(source)>remaining:row['state']='EXPORT_BYTE_LIMIT'
                elif redact_source(source.decode('utf-8'))!=source.decode('utf-8'):
                    row['state']='REDACTION_REQUIRED'
                else:
                    emit('PROJECT_MODEL_POSTIMAGE',{'task_id':tid,'path':path,'bytes':len(source),
                        'sha256':actual,'before_sha256':changed.get('before_sha256'),
                        'base64':base64.b64encode(source).decode()})
                    used+=len(source);exported.add((path,actual));row['state']='EXPORTED'
        except (OSError,ValueError,KeyError,TypeError) as exc:
            row.update(state='UNAVAILABLE',error=type(exc).__name__)
        results.append(row)
    complete=all(row['state'] in ('EXPORTED','ALREADY_EXPORTED') for row in results)
    return {'complete':complete,'state':'COMPLETE' if complete else 'INCOMPLETE',
            'expected_files':len(files),'exported_bytes':used,'files':results},used


def project_plan_reference(task,receipt,event,evidence):
    """Read the actual reviewed-plan binding; worker reference is model-only."""
    params=task.get('params') or {}
    event_ref=event.get('reference') or {}
    if not isinstance(params,dict) or not isinstance(event_ref,dict):
        raise ValueError('PROJECT_REFERENCE_SHAPE')
    if params.get('plan_sha256'):
        reference={key:params[key] for key in ('plan_sha256','contract_sha256') if key in params}
        if event_ref and event_ref!=reference:
            raise ValueError('PROJECT_REFERENCE_CONFLICT')
    else:
        reference=event_ref
        if reference.get('plan_sha256') and (
                reference.get('contract_sha256')!=params.get('contract_sha256')
                or task.get('native_project_generated_reference')!=reference):
            raise ValueError('PROJECT_GENERATED_REFERENCE_CONFLICT')
    if not reference.get('plan_sha256'):
        if receipt.get('plan_sha256') is not None or evidence.get('plan_sha256') is not None:
            raise ValueError('PROJECT_MISSING_DURABLE_REFERENCE')
        return {}
    if (set(reference)-{'plan_sha256','contract_sha256'}
            or any(not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{64}',value)
                   for value in reference.values())
            or receipt.get('plan_sha256')!=reference['plan_sha256']
            or evidence.get('plan_sha256')!=reference['plan_sha256']):
        raise ValueError('PROJECT_REFERENCE_PIN_MISMATCH')
    return reference


def project_plan_binding(plan,raw,reference,task,receipt,evidence,project):
    params=task.get('params') or {}
    expected={'task_id':task.get('id'),'parent_task_id':params.get('parent_task_id'),
              'queue_id':task.get('queue_id'),'root_id':'NOX_PROJECT_SOURCE'}
    return (plan.get('schema')=='NOX_PROJECT_WORK_PLAN_V1'
        and plan.get('operation')=='apply_reviewed_files' and encoded(plan)==raw
        and plan.get('acceptance_scope')=='SOURCE_PATCH_TESTED'
        and plan.get('original_task_accepted') is False
        and expected['parent_task_id']==task.get('parent_task_id')
        and all(isinstance(value,str) and plan.get(key)==value and evidence.get(key)==value
                for key,value in expected.items())
        and all(receipt.get(key)==expected[key] for key in ('task_id','parent_task_id','queue_id'))
        and (plan.get('review_origin')=='OWNER_REVIEWED' and params.get('plan_sha256')==reference['plan_sha256']
             or plan.get('review_origin')=='MODEL_CANDIDATE'
             and plan.get('contract_sha256')==reference.get('contract_sha256')==params.get('contract_sha256'))
        and plan.get('root_id') in project.get('roots',{}))


def project_execution_readback():
    import base64
    config, config_raw, _ = obj(ROOT/'config/owner_native_subagents.json')
    emit('PROJECT_EXECUTOR_CONFIG', {'sha256':hashlib.sha256(config_raw).hexdigest(),
        'mode':config.get('execution_mode'),'worker_cap':config.get('global_worker_cap'),
        'source_pins':config.get('project_executor',{}).get('source_pins'),
        'model_pins':config.get('project_executor',{}).get('model',{}).get('source_pins'),
        'historical_project_source_sha256':config.get('historical_project_source_sha256',[]),
        'historical_leaf_source_sha256':config.get('historical_leaf_source_sha256',[])})
    project=config.get('project_executor') or {}
    if not project:
        return
    current_source=hashlib.sha256(safe_read(SCRIPTS/'owner_subagent_dispatcher.py',500000)[0]).hexdigest()
    for name in ('owner_subagent_dispatcher.py','owner_autonomy_pool.py',
                 'owner_subagent_instruction_truth.py','owner_subagent_processes.py',
                 'owner_project_executor.py','owner_project_test_runner.py','owner_project_native.py',
                 'owner_project_planner.py','owner_project_model_client.py','owner_project_model_bridge.py',
                 'owner_systemic_refill.py'):
        try:
            raw,_=safe_read(SCRIPTS/name,500000)
            pin=config.get('module_pins',{}).get(name)
            source_row={'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                'configured_sha256':pin,'matches_module_pin':hashlib.sha256(raw).hexdigest()==pin if pin else None}
            if name=='owner_subagent_instruction_truth.py':
                match=re.search(rb"^CALLBACK_SHA = '([a-f0-9]{64})'$",raw,re.M)
                source_row['callback_pin']=match[1].decode() if match else None
                source_row['matches_current_callback']=source_row['callback_pin']==current_source
            emit('PROJECT_RUNTIME_SOURCE',source_row)
        except (OSError,ValueError) as exc:
            emit('PROJECT_RUNTIME_SOURCE',{'name':name,'state':'UNAVAILABLE','error':type(exc).__name__})
    state, state_raw, _ = obj(ROOT/'state/dispatcher/state.json',32*1024*1024)
    rows=state.get('tasks',{})
    counts={}
    for task in rows.values():
        key=task.get('status','UNKNOWN');counts[key]=counts.get(key,0)+1
    emit('PROJECT_QUEUE',{'rows':len(rows),'counts':counts,'sha256':hashlib.sha256(state_raw).hexdigest()})
    exported=set();export_bytes=0;verified_postimages={}
    for tid,task in rows.items():
        if not isinstance(task,dict) or task.get('handler')!='owner_native_project_work':continue
        row={key:task.get(key) for key in ('id','parent_task_id','queue_id','status','note','retries',
                                         'native_queue_sequence','original_task_accepted')}
        row['owner_claim']=task.get('owner_claim')
        if isinstance(task.get('systemic_relay'),dict):
            row['systemic_relay']=task['systemic_relay']
        if isinstance(task.get('native_worker_lease'),dict):
            row['native_worker_lease']=task['native_worker_lease']
        result=task.get('result') or {};receipt=result.get('receipt') or {}
        row['result']={key:result.get(key) for key in ('verified','scope','receipt_sha256')}
        if receipt:
            row['receipt']={key:receipt.get(key) for key in ('schema','phase','task_id','parent_task_id',
                'queue_id','job_id','plan_sha256','source_sha256','scope','finished_at',
                'project_source_changed','live_service_deployed','original_task_accepted')}
            row['receipt_sha_matches']=hashlib.sha256(encoded(receipt)).hexdigest()==result.get('receipt_sha256')
            row['receipt_claim_matches']=receipt.get('claim')==task.get('owner_claim')
            row['s03']=s03_receipt_check(receipt)
            row['receipt_source']=project_receipt_source(task,receipt,config,current_source)
            event=receipt.get('worker_result') or {};evidence=event.get('project_evidence') or {}
            row['worker_event']={key:event.get(key) for key in ('kind','role','pid','id','state','elapsed_ms','reason')}
            row['project_evidence']={key:evidence.get(key) for key in ('schema','state','task_id','claim',
                'plan_sha256','root_id','acceptance_scope','worker','project_source_changed',
                'integration_verified','postimages','tests_sha256','reason','trusted_tests_unchanged')}
            if evidence:
                row['project_evidence_sha_matches']=hashlib.sha256(encoded(evidence)).hexdigest()==event.get('project_evidence_sha256')
            tests=evidence.get('tests') or {}
            row['tests']={key:tests.get(key) for key in ('schema','completed','passed','modules','tests_run',
                'failures','errors','skipped','sandbox','log_sha256','log_bytes','elapsed_ms')}
            if tests.get('passed') is not True:
                row['tests']['output_tail']=redact_source(str(tests.get('output',''))[-4000:])
            planner=event.get('planner_receipt') or {}
            row['planner_receipt']=planner
            try:
                reference=project_plan_reference(task,receipt,event,evidence)
            except (ValueError,KeyError,TypeError) as exc:
                reference={};row['plan']={'state':'REFERENCE_UNVERIFIED','error':str(exc)}
            if reference.get('plan_sha256'):
                plan_path=Path(project['package_root'])/'plans'/(reference['plan_sha256']+'.json')
                try:
                    plan,raw,_=obj(plan_path)
                    row['plan']={'sha256':hashlib.sha256(raw).hexdigest(),
                        'matches_reference':hashlib.sha256(raw).hexdigest()==reference['plan_sha256'],
                        'files':plan.get('files'), 'review_origin':plan.get('review_origin'),
                        'contract_sha256':plan.get('contract_sha256'),
                        'binding_verified':project_plan_binding(plan,raw,reference,task,receipt,evidence,project),
                        'reference_source':'DURABLE_TASK_PARAMS' if (task.get('params') or {}).get('plan_sha256')
                                           else 'DURABLE_GENERATED_REFERENCE'}
                    proof_verified=(task.get('status')=='done' and result.get('verified') is True
                        and evidence.get('state')=='INTEGRATED' and evidence.get('integration_verified') is True
                        and tests.get('passed') is True and row['plan']['matches_reference'] and row['plan']['binding_verified']
                        and row['receipt_sha_matches'] and row['receipt_claim_matches']
                        and row['s03'].get('verified') is True and row['receipt_source']['source_authorized']
                        and row['receipt_source']['matches_durable_task_source']
                        and row['receipt_source']['matches_config_callback_pin']
                        and row.get('project_evidence_sha_matches') is True
                        and plan.get('task_id')==tid and plan.get('parent_task_id')==task.get('parent_task_id')
                        and plan.get('root_id')=='NOX_PROJECT_SOURCE')
                    files=plan.get('files')
                    if proof_verified and isinstance(files,list) and 1<=len(files)<=32:
                        postimages={approved_relative(f['path']):f['after_sha256'] for f in files}
                        if (len(postimages)==len(files) and postimages==evidence.get('postimages')
                                and set(postimages)<=set(project['roots']['NOX_PROJECT_SOURCE']['allowed_paths'])
                                and all(isinstance(v,str) and re.fullmatch(r'[a-f0-9]{64}',v)
                                        for v in postimages.values())):
                            for path,sha in postimages.items():
                                verified_postimages.setdefault(path,[]).append({'task_id':tid,
                                    'receipt_sha256':result['receipt_sha256'],'sha256':sha})
                    if evidence.get('state')=='INTEGRATED' and plan.get('review_origin')=='MODEL_CANDIDATE':
                        verified=proof_verified
                        if verified:
                            row['model_export'],used=export_model_postimages(tid,plan,project,exported,262144-export_bytes)
                            export_bytes+=used
                        else:row['model_export']={'complete':False,'state':'PROOF_UNVERIFIED'}
                        emit('PROJECT_MODEL_EXPORT_SUMMARY',{'task_id':tid,**row['model_export']})
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    row['plan']={'state':'UNAVAILABLE','error':type(exc).__name__}
        # The full receipt remains canonical in native state and S03. This
        # bounded readback retains verification facts and exact source hashes.
        emit('PROJECT_EXECUTION',row)
    config_rows=config.get('catalog',{}).get('tasks',[])
    emit('PROJECT_CATALOG',{'rows':len(config_rows),'new_project_rows':[
        {key:t.get(key) for key in ('id','queue_id','deps','params','priority','resource')}
        for t in config_rows if t.get('handler')=='owner_native_project_work']})
    return {'config_sha256':hashlib.sha256(config_raw).hexdigest(),
            'queue_sha256':hashlib.sha256(state_raw).hexdigest(),'postimages':verified_postimages}


def project_workspace_census(proofs):
    """Per-file stable reads, without locking writers or claiming an atomic tree."""
    started=time.time()
    report={'scope':'CONFIG_ALLOWED_FILES_ONLY_NOT_DIRECTORY_INVENTORY',
        'atomic_snapshot':False,'source_payloads_exported':False,
        'repository_commit_verified':False,'live_deployment_verified':False,
        'original_task_accepted':False,'started_at':started}
    try:
        config,raw,_=obj(ROOT/'config/owner_native_subagents.json')
        _,root,allowed=project_observation_scope(config)
        config_sha=hashlib.sha256(raw).hexdigest()
        report.update(root=str(root),config_sha256=config_sha,allowed_file_count=len(allowed))
        owner,marker,_=obj(root/'NOX_EXECUTOR_BOOTSTRAP.json',65536)
        pins=owner.get('file_pins')
        if (owner.get('schema')!='NOX_PROJECT_SOURCE_BOOTSTRAP_RECEIPT_V1'
                or owner.get('root')!=str(root) or not isinstance(pins,dict)
                or set(pins)!=set(allowed) or owner.get('source_file_count')!=len(allowed)
                or any(not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{64}',v)
                       for v in pins.values())):
            raise ValueError('BOOTSTRAP_MANIFEST_SCOPE')
        baseline={'schema':'NOX_PROJECT_SOURCE_BASELINE_V1','files':pins,
                  'source_refs':owner.get('source_refs',[])}
        marker_sha=hashlib.sha256(marker).hexdigest()
        manifest_sha=hashlib.sha256(encoded(baseline)).hexdigest()
        baseline_matches=manifest_sha==owner.get('manifest_sha256')
        report['bootstrap']={'sha256':marker_sha,'manifest_sha256':manifest_sha,
            'recorded_manifest_sha256':owner.get('manifest_sha256'),
            'manifest_digest_matches_marker':baseline_matches,'file_count':len(pins),
            'scope':'RECORDED_INSTALL_BASELINE_NOT_CURRENT_ACCEPTANCE'}
        if not baseline_matches:raise ValueError('BOOTSTRAP_MANIFEST_DIGEST')
        proof_config_matches=isinstance(proofs,dict) and proofs.get('config_sha256')==config_sha
        postimages=proofs.get('postimages',{}) if proof_config_matches else {}
        report['receipt_comparison_config_matches']=proof_config_matches
        report['receipt_queue_snapshot_sha256']=proofs.get('queue_sha256') if isinstance(proofs,dict) else None
        files={};details=[];total=0;errors=[]
        for path in allowed:
            row={'path':path,'bootstrap_sha256':pins[path]}
            try:
                source,info=safe_read(root/path,min(MAX_SOURCE_FILE,MAX_SOURCE_TOTAL-total))
                total+=len(source);sha=hashlib.sha256(source).hexdigest()
                files[path]={'sha256':sha,'size':len(source),'mode':stat.S_IMODE(info.st_mode)}
                references=postimages.get(path,[])[:32]
                row.update(**files[path],matches_bootstrap=sha==pins[path],
                    verified_receipt_postimages=[{**item,'matches_current':item['sha256']==sha}
                                                for item in references])
                matches=any(item['sha256']==sha for item in references)
                row['comparison']=('MATCHES_VERIFIED_RECEIPT_POSTIMAGE' if matches else
                    'MATCHES_BOOTSTRAP_BASELINE' if sha==pins[path] else 'CHANGE_WITHOUT_MATCHING_RECEIPT_IN_SNAPSHOT')
            except (OSError,ValueError) as exc:
                row.update(state='UNAVAILABLE',error=type(exc).__name__);errors.append(path)
            details.append(row)
        # Independent second reads detect observed churn; they do not form a lock
        # and cannot prove that no write occurred between two equal observations.
        changed=[];second_total=0
        for path,first in files.items():
            try:
                source,info=safe_read(root/path,min(MAX_SOURCE_FILE,MAX_SOURCE_TOTAL-second_total))
                second_total+=len(source)
                current={'sha256':hashlib.sha256(source).hexdigest(),'size':len(source),
                         'mode':stat.S_IMODE(info.st_mode)}
                if current!=first:changed.append(path)
            except (OSError,ValueError):changed.append(path)
        config_stable=hashlib.sha256(safe_read(ROOT/'config/owner_native_subagents.json',2000000)[0]).hexdigest()==config_sha
        marker_stable=hashlib.sha256(safe_read(root/'NOX_EXECUTOR_BOOTSTRAP.json',65536)[0]).hexdigest()==marker_sha
        complete=not errors and len(files)==len(allowed)
        report.update(state='CENSUS_OBSERVED',files=files,file_comparisons=details,
            count=len(files),total_bytes=total,files_sha256=hashlib.sha256(encoded(files)).hexdigest(),
            complete_allowed_files_read=complete,read_errors=errors,
            changed_between_reads=changed,two_reads_match=complete and not changed,
            config_unchanged_during_census=config_stable,bootstrap_unchanged_during_census=marker_stable,
            current_cas_recheck_required=True,
            unattributed_changed_paths=[r['path'] for r in details
                if r.get('comparison')=='CHANGE_WITHOUT_MATCHING_RECEIPT_IN_SNAPSHOT'])
    except (OSError,ValueError,KeyError,TypeError) as exc:
        report.update(state='CENSUS_UNAVAILABLE',error=type(exc).__name__)
    report['finished_at']=time.time()
    emit('PROJECT_SOURCE_WORKSPACE_CENSUS',report)


def project_install_preservation():
    config,_,_=obj(ROOT/'config/owner_native_subagents.json')
    request=str(config.get('owner_request',''))
    if not re.fullmatch(r'[0-9]{1,24}',request):return
    base=ROOT/'state/dispatcher/complete_executor_rollback'/request
    try:
        before,_,_=obj(base/'final_stopped_queue_snapshot.json',32*1024*1024)
        after,_,_=obj(ROOT/'state/dispatcher/state.json',32*1024*1024)
        old=before['tasks'];new=after['tasks']
        historic={key:row for key,row in old.items() if row.get('status') in ('done','blocked','failed')}
        changed=[key for key,row in historic.items() if any(row.get(field)!=new.get(key,{}).get(field)
                                                         for field in ('owner_claim','result'))]
        emit('PROJECT_QUEUE_PRESERVATION',{'request':request,'old_count':len(old),'current_count':len(new),
            'missing_original_ids':sorted(set(old)-set(new)),'historical_checked':len(historic),
            'changed_claim_or_result':changed,'verified':not(set(old)-set(new)) and not changed})
        receipt,raw,_=obj(ROOT/'state/dispatcher'/('complete_executor_install_'+request+'.json'),4*1024*1024)
        emit('PROJECT_INSTALL_RECEIPT',{'sha256':hashlib.sha256(raw).hexdigest(),
            **{key:receipt.get(key) for key in ('schema','state','request','source_sha','started_at',
                'finished_at','previous_director','new_director','original_tasks_accepted',
                'protected_processes','training_started','model_restarted','preflight',
                'sandbox_preflight','native_sandbox_preflight','source_bootstrap')}})
    except (OSError,ValueError,KeyError) as exc:
        emit('PROJECT_QUEUE_PRESERVATION',{'request':request,'state':'UNAVAILABLE','error':type(exc).__name__})


def director_child_census():
    host_clock_initial = _host_boot_clock_snapshot()
    data,_,_=obj(ROOT/'status/agents_t856u.json')
    native=data.get('native_subexecutors') or {};pid=(native.get('director') or {}).get('pid')
    director_identity=process(pid) if type(pid) is int else None
    result=[]
    if type(pid) is int:
        for child in Path('/proc').iterdir():
            if not child.name.isdigit():continue
            observed=process(int(child.name))
            if observed.get('ppid')!=pid:continue
            try:
                raw=(child/'cmdline').read_bytes()[:4000]
                kind='MP_WORKER' if b'multiprocessing.spawn' in raw else (
                    'MP_RESOURCE_TRACKER' if b'resource_tracker' in raw else 'OTHER_CHILD')
            except OSError:kind='UNKNOWN'
            result.append({**observed,'kind':kind})
    host_clock_final = _host_boot_clock_snapshot()
    host_clock = _host_clock_pair(host_clock_initial, host_clock_final)
    if isinstance(director_identity, dict):
        director_identity = _attach_pid_start_epoch(director_identity, host_clock)
    result=[_attach_pid_start_epoch(child, host_clock) for child in result]
    emit('PROJECT_DIRECTOR_CHILDREN',{'director_pid':pid,'director_identity':director_identity,
        'host_clock_snapshot':host_clock,'host_clock_snapshot_status':host_clock['status'],
        'host_clock_snapshot_sha256':host_clock_final.get('snapshot_sha256'),'children':result,
        'native_fields':sorted(native),'last_admission':native.get('last_admission'),
        'close_reason':native.get('close_reason'),'state':native.get('state')})


def continuous_install_receipts():
    base=ROOT/'state/dispatcher'
    paths=[path for path in base.glob('continuous_executor_install_*.json')
           if re.fullmatch(r'continuous_executor_install_[0-9]{1,24}\.json',path.name)]
    for path in sorted(paths,key=lambda item:int(item.stem.rsplit('_',1)[1]))[-4:]:
        request=path.stem.rsplit('_',1)[1]
        try:
            receipt,raw,_=obj(path,4*1024*1024)
            if (receipt.get('schema')!='NOX_CONTINUOUS_EXECUTOR_INSTALL_RECEIPT_V1'
                    or receipt.get('request')!=request):
                raise ValueError('CONTINUOUS_RECEIPT_BINDING')
            row=scalar_projection(receipt,('schema','state','request','source_sha','config_sha256',
                'started_at','finished_at','original_tasks_accepted','training_started',
                'model_restarted','queue_writes','old_catalog_rows_preserved','preserved_project_receipts'))
            row['sha256']=hashlib.sha256(raw).hexdigest()
            row['new_director']=scalar_projection(receipt.get('new_director') or {},
                ('pid','ppid','pgrp','start_ticks'))
            row['batch_task_ids']=[identifier(task) for task in (receipt.get('batch_task_ids') or [])[:32]]
            emit('CONTINUOUS_INSTALL_RECEIPT',row)
        except (OSError,ValueError,TypeError) as exc:
            emit('CONTINUOUS_INSTALL_RECEIPT',{'request':request,'state':'UNAVAILABLE','error':type(exc).__name__})


def project_active_progress():
    import urllib.request
    try:
        req=urllib.request.Request('http://127.0.0.1:8098/slots',method='GET')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req,timeout=5) as response:
            raw=response.read(200001)
        if len(raw)>200000:raise ValueError('SLOT_SIZE')
        slots=json.loads(raw)
        if not isinstance(slots,list):raise ValueError('SLOT_SHAPE')
        rows=[]
        keys=('id','id_task','is_processing','n_ctx','n_prompt_tokens','n_decoded','n_predict','n_past','state')
        for slot in slots[:4]:
            row=scalar_projection(slot,keys)
            for field in ('timings','next_token','params'):
                if isinstance(slot.get(field),dict):
                    row[field]=scalar_projection(slot[field],(
                        'n_predict','n_ctx','n_decoded','n_remaining','has_next_token',
                        'prompt_n','prompt_ms','predicted_n','predicted_ms',
                        'predicted_per_token_ms','predicted_per_second'))
            rows.append(row)
        emit('PROJECT_MODEL_SLOT_PROGRESS',{'slots':rows,'scope':'READ_ONLY_NO_PROMPT_OR_COMPLETION_CONTENT'})
    except (OSError,ValueError,TypeError) as exc:
        emit('PROJECT_MODEL_SLOT_PROGRESS',{'state':'UNAVAILABLE','error':type(exc).__name__})
    base=ROOT/'state/dispatcher/project_executor/run/attempts'
    rows=[]
    if base.exists() and not base.is_symlink():
        for path in sorted(base.glob('*/*/*/journal.json'))[-40:]:
            try:
                value,raw,info=obj(path,2000000)
                row=scalar_projection(value,('schema','state','task_id','claim','plan_sha256','reason','started_at','finished_at'))
                row.update({'journal_sha256':hashlib.sha256(raw).hexdigest(),'mtime_ns':info.st_mtime_ns})
                tests=value.get('tests')
                if isinstance(tests,dict):
                    row['tests']=scalar_projection(tests,('schema','completed','passed','tests_run',
                        'failures','errors','skipped','log_sha256','log_bytes','elapsed_ms'))
                    row['tests']['report_sha256']=hashlib.sha256(encoded(tests)).hexdigest()
                    row['tests']['matches_journal_test_pin']=row['tests']['report_sha256']==value.get('tests_sha256')
                rows.append(row)
            except (OSError,ValueError):continue
    try:planner_sha=hashlib.sha256(safe_read(SCRIPTS/'owner_project_planner.py',500000)[0]).hexdigest()
    except (OSError,ValueError):planner_sha=None
    emit('PROJECT_ATTEMPT_PROGRESS',{'attempts':rows,'planner_sha256':planner_sha,
        'interim_trace_unavailable':True,
        'trace_storage':'MEMORY_ONLY_UNTIL_FINAL_RECEIPT' if planner_sha in PLANNER_MEMORY_TRACE_SHAS else 'UNREVIEWED_PLANNER_VERSION',
        'scope':'DURABLE_TEST_ATTEMPTS_ONLY_NOT_IN_MEMORY_EDIT_OR_TURN_PROGRESS',
        'absence_of_attempt_does_not_prove_no_source_edits':True})


def systemic_relay_readback():
    config,raw,_=obj(ROOT/'config/owner_native_subagents.json',2000000)
    reference=config.get('systemic_relay')
    if reference is not None:
        try:
            if (not isinstance(reference,dict) or set(reference)!={'path','sha256'}
                    or not re.fullmatch(r'[a-f0-9]{64}',str(reference.get('sha256','')))):
                raise ValueError('RELAY_REFERENCE')
            expected=ROOT/'state/dispatcher/project_executor/package/relay'/(reference['sha256']+'.json')
            if reference['path']!=str(expected):raise ValueError('RELAY_PATH')
            manifest,body,_=obj(expected,2000000)
            if hashlib.sha256(body).hexdigest()!=reference['sha256']:raise ValueError('RELAY_SHA')
            emit('SYSTEMIC_RELAY_MANIFEST',{'config_sha256':hashlib.sha256(raw).hexdigest(),
                'reference':reference,'schema':manifest.get('schema'),'revision':manifest.get('revision'),
                'previous_manifest_sha256':manifest.get('previous_manifest_sha256'),
                'missions':[{key:row.get(key) for key in ('mission_id','revision','parent_task_id',
                    'queue_id','editable_paths','context','instruction','experience')}
                    for row in manifest.get('missions',[])[:30]],
                'source_scope':'OWNER_PINNED_MISSIONS_NOT_TASK_ACCEPTANCE'})
        except (OSError,ValueError,TypeError) as exc:
            emit('SYSTEMIC_RELAY_MANIFEST',{'state':'UNVERIFIED','error':type(exc).__name__})
    for prefix,schema in (('systemic_relay_install','NOX_SYSTEMIC_RELAY_INSTALL_RECEIPT_V1'),
                          ('systemic_relay_publish','NOX_SYSTEMIC_RELAY_PUBLISH_RECEIPT_V1')):
        base=ROOT/'state/dispatcher'
        paths=[path for path in base.glob(prefix+'_*.json')
               if re.fullmatch(prefix+r'_[0-9]{1,24}\.json',path.name)]
        for path in sorted(paths,key=lambda item:int(item.stem.rsplit('_',1)[1]))[-4:]:
            try:
                value,body,_=obj(path,4*1024*1024)
                if value.get('schema')!=schema:raise ValueError('RELAY_RECEIPT_SCHEMA')
                item=scalar_projection(value,('schema','state','request','source_sha','config_sha256',
                    'manifest_sha256','previous_manifest_sha256','previous_config_sha256','started_at',
                    'finished_at','original_tasks_accepted','model_restarted','training_started',
                    'source_workspace_writes','source_writes','trusted_test_writes','test_writes',
                    'workers_restarted','preserved_project_receipts','old_catalog_rows_preserved'))
                item['sha256']=hashlib.sha256(body).hexdigest()
                for key in ('new_director','director','batch_task_ids','runtime_pins'):
                    if key in value:item[key]=value[key]
                emit('SYSTEMIC_RELAY_RECEIPT',item)
            except (OSError,ValueError,TypeError) as exc:
                emit('SYSTEMIC_RELAY_RECEIPT',{'state':'UNAVAILABLE','error':type(exc).__name__})


def main():
    snapshot_a = runtime_snapshot()
    emit('SNAPSHOT_A',snapshot_a)
    worker_status_sample()
    director_child_census()
    project_summary()
    project_install_preservation()
    continuous_install_receipts()
    systemic_relay_readback()
    proofs=project_execution_readback()
    project_workspace_census(proofs)
    project_active_progress()
    lock_rows = locks()
    time.sleep(6)
    worker_status_sample()
    director_child_census()
    snapshot_b = runtime_snapshot()
    final_guard = _host_boot_clock_snapshot()
    snapshot_b['host_clock_final_guard'] = final_guard
    clock_chain = [snapshot_a.get('host_clock_snapshot'),
                   *[row.get('host_clock_snapshot') for row in lock_rows[:1]],
                   snapshot_b.get('host_clock_snapshot'),
                   _host_clock_pair(snapshot_b.get('host_clock_snapshot', {}).get('final', {}),
                                    final_guard)]
    chain_status = _host_clock_chain_status(clock_chain)
    snapshot_b['host_boot_identity_chain_status'] = chain_status
    snapshot_b['snapshot_complete'] = (snapshot_b.get('snapshot_complete') is True
                                      and chain_status == 'STABLE')
    if chain_status != 'STABLE':
        snapshot_b['host_clock_snapshot_status'] = chain_status
        for service in snapshot_b.get('services', []):
            identity = service.get('identity') if isinstance(service, dict) else None
            if isinstance(identity, dict):
                identity['host_clock_binding_status'] = chain_status
    for row in lock_rows:
        row['host_boot_identity_chain_status'] = chain_status
        if chain_status != 'STABLE':
            row['host_clock_snapshot_status'] = chain_status
            row['lock_observation_complete'] = False
            row['holder_identity_recheck_status'] = 'CHANGED_OR_UNAVAILABLE'
            for check in row.get('holder_identity_rechecks', []):
                check['status'] = 'CHANGED_OR_UNAVAILABLE'
                check['host_clock_binding_status'] = chain_status
            for record in row.get('matching_lock_records', []):
                record['holder_identity_recheck'] = 'CHANGED_OR_UNAVAILABLE'
                if isinstance(record.get('holder_identity'), dict):
                    record['holder_identity']['host_clock_binding_status'] = chain_status
    emit('LOCKS',lock_rows)
    emit('SNAPSHOT_B',snapshot_b)
    print('NOX_MAINT_INSPECT_COMPLETE=true',flush=True)

if __name__=='__main__':main()
