#!/usr/bin/env python3
"""One-shot native audit. Seven bounded OS workers, no daemon, no mutation or credentials output."""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import csv, hashlib, json, os, re, shutil, subprocess, sys, time

SAFE=re.compile(r'^[A-Za-z0-9_./+@:= -]{1,300}$')
ROOTS=('/root/nox','/root/nox_learn','/workspace')

def run(argv, seconds=12):
    try:
        p=subprocess.run(argv,capture_output=True,text=True,timeout=seconds)
        return p.returncode,p.stdout[:200000]
    except Exception as e:return 99,type(e).__name__

def num(path):
    try:
        v=Path(path).read_text().strip()
        return int(v) if v.isdigit() else v[:40]
    except OSError:return None

MAX_GPU_APPS = 128
MAX_PROC_ENTRIES = 8192
MAX_PARENT_DEPTH = 16
GPU_APP_QUERY = ['nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_gpu_memory',
                 '--format=csv,noheader,nounits']
GPU_UUID = re.compile(r'^GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$')
CGROUP_PATH = re.compile(r'^/[A-Za-z0-9_./:@+=-]{0,512}$')
SUPERVISOR_STATUS = re.compile(
    r'^([A-Za-z0-9_.:-]{1,128})\s+([A-Z]+)(?:\s+pid\s+([0-9]+))?(?:[,\s]|$)')


def _read_proc_text(path, limit=16384):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('HOLD_PROC_FILE_SIZE')
    return raw.decode('utf-8', errors='replace')


def _status_identity(proc_dir, expected_pid):
    fields = {}
    for line in _read_proc_text(Path(proc_dir) / 'status').splitlines():
        name, sep, value = line.partition(':')
        if sep and name in ('Name', 'State', 'Tgid', 'Pid', 'PPid', 'Uid', 'NSpid'):
            fields[name] = value.strip()
    try:
        pid, ppid, tgid = int(fields['Pid']), int(fields['PPid']), int(fields['Tgid'])
    except (KeyError, ValueError) as exc:
        raise ValueError('HOLD_PROC_STATUS_IDENTITY') from exc
    if pid != int(expected_pid):
        raise ValueError('HOLD_PROC_STATUS_PID_MISMATCH')
    raw_nspid = fields.get('NSpid', '')
    nspid_parts = raw_nspid.split() if raw_nspid else [str(pid)]
    if not nspid_parts or len(nspid_parts) > 16 or any(not item.isdecimal() for item in nspid_parts):
        raise ValueError('HOLD_PROC_NSPID')
    uid_parts = fields.get('Uid', '').split()
    uid = int(uid_parts[0]) if uid_parts and uid_parts[0].isdecimal() else None
    return {'pid': pid, 'ppid': ppid, 'tgid': tgid, 'uid': uid,
            'name': fields.get('Name', '')[:60],
            'state': fields.get('State', '').split()[0] if fields.get('State') else None,
            'nspid': [int(item) for item in nspid_parts],
            'nspid_available': bool(raw_nspid)}


def _proc_cgroups(proc_dir):
    rows = []
    for line in _read_proc_text(Path(proc_dir) / 'cgroup', 8192).splitlines():
        parts = line.split(':', 2)
        if len(parts) != 3 or not parts[0].isdecimal() or not CGROUP_PATH.fullmatch(parts[2]):
            raise ValueError('HOLD_PROC_CGROUP_FORMAT')
        rows.append({'hierarchy': int(parts[0]), 'controllers': parts[1], 'path': parts[2]})
        if len(rows) > 64:
            raise ValueError('HOLD_PROC_CGROUP_UNBOUNDED')
    return rows


def _ns_link(proc_dir, namespace):
    try:
        value = os.readlink(Path(proc_dir) / 'ns' / namespace)
    except OSError:
        return None
    return value if re.fullmatch(r'[a-z]+:\[[0-9]+\]', value) else None


def read_proc_identity(proc_root, pid):
    """Read PID, NSpid, PID namespace, start ticks and cgroup with race checks."""
    if type(pid) is not int or pid < 1:
        raise ValueError('HOLD_PROC_PID_RANGE')
    proc_dir = Path(proc_root) / str(pid)
    first = _proc_stat(proc_dir, pid)
    status = _status_identity(proc_dir, pid)
    if status['ppid'] != first['ppid']:
        raise ValueError('HOLD_PROC_PARENT_RACE')
    try:
            cgroups, cgroup_state = _proc_cgroups(proc_dir), 'READ'
            if len(cgroups) > 16:
                cgroups, cgroup_state = cgroups[:16], 'TRUNCATED_BOUNDED'
    except (OSError, ValueError):
        cgroups, cgroup_state = [], 'UNAVAILABLE_OR_INVALID'
    try:
        comm = _read_proc_text(proc_dir / 'comm', 1024).strip()[:60]
    except (OSError, ValueError):
        comm = None
    try:
        executable = os.path.basename(os.readlink(proc_dir / 'exe'))[:256]
        if not SAFE.fullmatch(executable):
            executable = '[REDACTED]'
            executable_state = 'REDACTED'
        else:
            executable_state = 'AVAILABLE'
    except FileNotFoundError:
        executable, executable_state = None, 'MISSING'
    except PermissionError:
        executable, executable_state = None, 'UNREADABLE'
    except OSError:
        executable, executable_state = None, 'UNAVAILABLE'
    namespaces = {name: _ns_link(proc_dir, name) for name in ('pid', 'mnt', 'cgroup')}
    last = _proc_stat(proc_dir, pid)
    if first['start_ticks'] != last['start_ticks'] or first['ppid'] != last['ppid']:
        raise ValueError('HOLD_PROC_IDENTITY_CHANGED')
    return {'pid': pid, 'ppid': first['ppid'], 'pgrp': first['pgrp'],
            'start_ticks': first['start_ticks'], 'state': status['state'],
            'comm': comm, 'executable': executable, 'uid': status['uid'],
            'nspid': status['nspid'], 'nspid_available': status['nspid_available'],
            'pid_namespace': namespaces['pid'], 'mnt_namespace': namespaces['mnt'],
            'cgroup_namespace': namespaces['cgroup'],
            'executable_state': executable_state,
            'cgroups': cgroups, 'cgroup_state': cgroup_state,
            'identity_state': 'VERIFIED'}


def parse_gpu_apps(text):
    rows, rejected, unbounded, seen = [], 0, False, set()
    for line in str(text).splitlines():
        if len(line) > 512:
            rejected += 1
            continue
        fields = next(csv.reader([line]), [])
        if not fields or not any(part.strip() for part in fields):
            continue
        if len(fields) != 3:
            rejected += 1
            continue
        pid_text, gpu_uuid, memory = (part.strip() for part in fields)
        if (not pid_text.isdecimal() or int(pid_text) <= 1
                or not GPU_UUID.fullmatch(gpu_uuid)
                or not (memory.isdecimal() or memory.lower() in ('n/a', 'not supported'))):
            rejected += 1
            continue
        key = (int(pid_text), gpu_uuid)
        if key in seen:
            rejected += 1
            continue
        seen.add(key)
        rows.append({'gpu_pid': int(pid_text), 'gpu_uuid': gpu_uuid,
                     'used_gpu_memory': memory})
        if len(rows) > MAX_GPU_APPS:
            rows = rows[:MAX_GPU_APPS]
            rejected += 1
            unbounded = True
            break
    return rows, rejected, unbounded


def _capture_gpu_apps(run_fn, clock):
    started = clock()
    rc, output = run_fn(GPU_APP_QUERY, seconds=12)
    finished = clock()
    rows, rejected, unbounded = parse_gpu_apps(output)
    truncated = len(str(output)) >= 200000
    return {'return_code': rc, 'started_unix_ns': started,
            'finished_unix_ns': finished, 'apps': rows,
            'rejected_rows': rejected, 'unbounded': unbounded,
            'truncated': truncated,
            'complete': type(rc) is int and rc == 0 and not truncated and not rejected and not unbounded,
            'scope': 'NVIDIA_SMI_COMPUTE_APP_SNAPSHOT'}


def _parse_supervisor_status(text):
    services = []
    for line in str(text).splitlines()[:512]:
        match = SUPERVISOR_STATUS.match(line.strip())
        if match:
            services.append({'service': match.group(1), 'state': match.group(2),
                             'pid': int(match.group(3)) if match.group(3) else None})
    return services


def _capture_services(proc_root, run_fn, clock):
    started = clock()
    rc, output = run_fn(['supervisorctl', 'status'], seconds=12)
    finished = clock()
    services = _parse_supervisor_status(output)
    lines = [line for line in str(output).splitlines() if line.strip()]
    truncated = len(str(output)) >= 200000 or len(lines) > 512
    rejected_lines = max(0, len(lines) - len(services))
    names = [service['service'] for service in services]
    duplicate_names = len(names) != len(set(names))
    identities_complete = True
    for service in services:
        service['identity'] = None
        if service['state'] == 'RUNNING':
            if not service['pid']:
                service['identity_state'] = 'RUNNING_PID_MISSING'
                identities_complete = False
                continue
            try:
                identity = read_proc_identity(proc_root, service['pid'])
                if (identity['pid'] != service['pid'] or identity['start_ticks'] <= 0
                        or not identity['nspid_available'] or not identity['pid_namespace']):
                    raise ValueError('HOLD_SUPERVISOR_PID_IDENTITY_INCOMPLETE')
                service['identity'] = identity
                service['identity_state'] = 'VERIFIED'
            except (OSError, ValueError, KeyError, TypeError):
                service['identity_state'] = 'UNAVAILABLE_OR_CHANGED'
                identities_complete = False
    state_counts = {}
    for service in services:
        state = service['state']
        state_counts[state] = state_counts.get(state, 0) + 1
    all_running = bool(services) and all(service['state'] == 'RUNNING' for service in services)
    any_not_running = any(service['state'] != 'RUNNING' for service in services)
    rows_complete = (bool(services) and not truncated and rejected_lines == 0
                     and not duplicate_names and identities_complete)
    status_consistent = ((type(rc) is int and rc == 0 and all_running)
                         or (type(rc) is int and rc == 3 and any_not_running))
    inventory_complete = rows_complete and status_consistent
    command_success = type(rc) is int and rc == 0
    health = ('UNKNOWN' if not services else
              'PARTIAL' if not inventory_complete else
              'HEALTHY' if all_running else 'DEGRADED')
    return {'return_code': rc, 'command_rc': rc, 'command_success': command_success,
            'started_unix_ns': started, 'finished_unix_ns': finished, 'services': services,
            'truncated': truncated, 'rejected_lines': rejected_lines,
            'duplicate_service_names': duplicate_names,
            'identity_complete': identities_complete,
            'rows_complete': rows_complete, 'inventory_complete': inventory_complete,
            'status_consistent': status_consistent,
            'service_health': {'state': health, 'counts': state_counts,
                               'running': state_counts.get('RUNNING', 0),
                               'not_running': sum(count for state, count in state_counts.items()
                                                  if state != 'RUNNING')},
            'complete': command_success and inventory_complete and all_running,
            'scope': 'SUPERVISOR_STATUS_PLUS_PROC_IDENTITY'}


def _nspid_aliases(proc_root, targets):
    aliases = {pid: [] for pid in targets}
    if not targets:
        return aliases, True
    complete = True
    try:
        with os.scandir(proc_root) as entries:
            for number, entry in enumerate(entries, 1):
                if number > MAX_PROC_ENTRIES:
                    complete = False
                    break
                if not entry.name.isdecimal():
                    continue
                local_pid = int(entry.name)
                proc_dir = Path(proc_root) / entry.name
                try:
                    initial = _proc_stat(proc_dir, local_pid)
                    status = _status_identity(proc_dir, local_pid)
                except (OSError, ValueError):
                    complete = False
                    continue
                if not status['nspid_available']:
                    complete = False
                    continue
                for target in targets.intersection(status['nspid']):
                    try:
                        identity = read_proc_identity(proc_root, local_pid)
                        final = _proc_stat(proc_dir, local_pid)
                        if (identity['start_ticks'] != initial['start_ticks']
                                or final['start_ticks'] != initial['start_ticks']
                                or identity['ppid'] != initial['ppid']
                                or final['ppid'] != initial['ppid']
                                or not identity['nspid_available']
                                or not identity.get('pid_namespace')
                                or target not in identity['nspid']):
                            complete = False
                            continue
                        aliases[target].append(identity)
                    except (OSError, ValueError):
                        complete = False
    except OSError:
        complete = False
    return aliases, complete


def _service_relation(identity, service_snapshot, proc_root):
    services = service_snapshot.get('services', [])
    by_pid = {}
    for service in services:
        item = service.get('identity')
        if not isinstance(item, dict):
            continue
        by_pid.setdefault(item['pid'], []).append(service)
    chain, current, seen = [], identity, {identity['pid']}
    for depth in range(MAX_PARENT_DEPTH + 1):
        chain.append({'pid': current['pid'], 'ppid': current['ppid'],
                      'start_ticks': current['start_ticks'], 'comm': current.get('comm'),
                      'pid_namespace': current.get('pid_namespace'),
                      'cgroups': current.get('cgroups', [])[:64]})
        for service in by_pid.get(current['pid'], []):
            item = service['identity']
            if item['start_ticks'] == current['start_ticks']:
                return {'service': service['service'], 'pid': service['pid'],
                        'state': service['state'],
                        'relation': 'DIRECT_PID' if depth == 0 else 'PARENT_CHAIN',
                        'start_ticks': item['start_ticks']}, chain
        parent_pid = current['ppid']
        if depth >= MAX_PARENT_DEPTH or parent_pid <= 1 or parent_pid in seen:
            break
        try:
            parent = read_proc_identity(proc_root, parent_pid)
            child_after = _proc_stat(Path(proc_root) / str(current['pid']), current['pid'])
        except (OSError, ValueError):
            break
        if child_after['start_ticks'] != current['start_ticks'] or child_after['ppid'] != parent_pid:
            break
        seen.add(parent_pid)
        current = parent
    return None, chain


def _capture_proc_targets(proc_root, pids, service_snapshot):
    targets_set = set(pids)
    aliases, alias_scan_complete = _nspid_aliases(proc_root, targets_set)
    targets = {}
    for pid in sorted(targets_set):
        candidates = aliases.get(pid, [])
        identity, visibility = None, 'NOT_VISIBLE'
        if not alias_scan_complete:
            visibility = 'INCOMPLETE_NSPID_SCAN'
        elif len(candidates) > 1:
            visibility = 'AMBIGUOUS_NSPID_ALIAS'
        elif len(candidates) == 1:
            identity = candidates[0]
            visibility = 'DIRECT_PROC' if identity['pid'] == pid else 'NSPID_ALIAS'
        relation, chain = (None, [])
        if identity:
            relation, chain = _service_relation(identity, service_snapshot, proc_root)
        targets[pid] = {'reported_gpu_pid': pid,
                        'local_pid': identity['pid'] if identity else None,
                        'visibility': visibility, 'identity': identity,
                        'service_match': relation, 'parent_chain': chain}
    return {'targets': targets, 'alias_scan_complete': alias_scan_complete,
            'complete': alias_scan_complete}


def _target_signature(target):
    item = target.get('identity') if target else None
    if not isinstance(item, dict):
        return None
    return (target.get('visibility'), item.get('pid'), item.get('start_ticks'),
            tuple(item.get('nspid', ())), item.get('pid_namespace'),
            item.get('mnt_namespace'), item.get('cgroup_namespace'))


def _link_gpu_apps(before_inventory, after_inventory, before_proc, after_proc):
    before, after = before_inventory['apps'], after_inventory['apps']
    def keyed(rows):
        return {(row['gpu_pid'], row['gpu_uuid']): row for row in rows}
    pre, post = keyed(before), keyed(after)
    links = []
    for key in sorted(set(pre) | set(post)):
        pid, gpu_uuid = key
        first, last = pre.get(key), post.get(key)
        presence = 'BOTH' if first and last else 'BEFORE_ONLY' if first else 'AFTER_ONLY'
        pre_target = before_proc['targets'].get(pid)
        post_target = after_proc['targets'].get(pid)
        pre_sig, post_sig = _target_signature(pre_target), _target_signature(post_target)
        stable = bool(pre_sig and pre_sig == post_sig)
        target = post_target if post_sig else pre_target
        evidence_complete = (before_inventory.get('complete') is True
                             and after_inventory.get('complete') is True
                             and before_proc.get('complete') is True
                             and after_proc.get('complete') is True
                             and before_proc.get('supervisor_inventory_complete') is True
                             and after_proc.get('supervisor_inventory_complete') is True)
        if not evidence_complete:
            state = 'NOT_VISIBLE'
        elif presence == 'BEFORE_ONLY' or (presence == 'BOTH' and pre_sig != post_sig):
            state = 'GONE_DURING_SAMPLE'
        elif not target or not target.get('identity'):
            state = 'NOT_VISIBLE'
        elif target['visibility'] == 'NSPID_ALIAS':
            state = 'NAMESPACE_ALIAS'
        elif presence == 'BOTH' and not stable:
            state = 'NOT_VISIBLE'
        else:
            relation = ((post_target or {}).get('service_match')
                        or (pre_target or {}).get('service_match'))
            state = 'MATCHED' if relation else 'NO_SERVICE_ANCESTOR'
        relation = ((post_target or {}).get('service_match')
                    or (pre_target or {}).get('service_match'))
        links.append({
            'gpu_pid': pid, 'gpu_uuid': gpu_uuid,
            'used_gpu_memory_before': first.get('used_gpu_memory') if first else None,
            'used_gpu_memory_after': last.get('used_gpu_memory') if last else None,
            'inventory_presence': presence,
            'identity_stability': 'STABLE_BOTH' if stable else
                'CHANGED' if pre_sig and post_sig else
                'PRE_ONLY' if pre_sig else 'POST_ONLY' if post_sig else 'NOT_VISIBLE',
            'classification': state,
            'evidence_state': 'COMPLETE' if evidence_complete else 'INCOMPLETE',
            'visibility': target.get('visibility') if target else 'NOT_VISIBLE',
            'proc_identity': target.get('identity') if target else None,
            'service_match': relation,
            'parent_chain': target.get('parent_chain', []) if target else [],
            'before_alias_scan_complete': before_proc.get('alias_scan_complete'),
            'after_alias_scan_complete': after_proc.get('alias_scan_complete'),
            'scope': 'READ_ONLY_GPU_PID_TO_PROC_SERVICE'})
    return links


_GPU_CONSUMER_CLASSIFICATIONS = frozenset((
    'MATCHED', 'NAMESPACE_ALIAS', 'NO_SERVICE_ANCESTOR'))
_GPU_IDENTITY_FIELDS = ('pid', 'start_ticks', 'nspid', 'pid_namespace',
                        'mnt_namespace', 'cgroup_namespace')


def _candidate_from_link(link):
    """Return a strict export candidate only for complete, live census evidence."""
    if (link.get('evidence_state') != 'COMPLETE'
            or link.get('classification') not in _GPU_CONSUMER_CLASSIFICATIONS
            or link.get('inventory_presence') not in ('BOTH', 'AFTER_ONLY')
            or link.get('identity_stability') not in ('STABLE_BOTH', 'POST_ONLY')):
        return None
    identity = link.get('proc_identity')
    visibility = link.get('visibility')
    classification = link.get('classification')
    if not isinstance(identity, dict) or not identity.get('nspid_available'):
        return None
    pid, start_ticks, gpu_pid = identity.get('pid'), identity.get('start_ticks'), link.get('gpu_pid')
    nspid = identity.get('nspid')
    namespace_names = ('pid_namespace', 'mnt_namespace', 'cgroup_namespace')
    if (type(pid) is not int or pid <= 1 or type(start_ticks) is not int or start_ticks <= 0
            or type(gpu_pid) is not int or gpu_pid <= 1
            or not isinstance(nspid, list) or not nspid
            or any(type(value) is not int or value <= 0 for value in nspid)
            or gpu_pid not in nspid
            or any(not isinstance(identity.get(name), str)
                   or not re.fullmatch(r'(?:pid|mnt|cgroup):\[[0-9]+\]', identity[name])
                   for name in namespace_names)
            or (classification == 'NAMESPACE_ALIAS' and visibility != 'NSPID_ALIAS')
            or (classification in ('MATCHED', 'NO_SERVICE_ANCESTOR') and visibility != 'DIRECT_PROC')
            or not isinstance(link.get('gpu_uuid'), str)
            or not GPU_UUID.fullmatch(link['gpu_uuid'])):
        return None
    return {
        'gpu_pid': gpu_pid,
        'gpu_uuid': link.get('gpu_uuid'),
        'pid': pid,
        'start_ticks': start_ticks,
        'nspid': list(nspid),
        'pid_namespace': identity['pid_namespace'],
        'mnt_namespace': identity['mnt_namespace'],
        'cgroup_namespace': identity['cgroup_namespace'],
        'classification': classification,
        'visibility': visibility,
        'evidence_state': 'COMPLETE',
        'identity_stability': link['identity_stability'],
    }


def _candidate_matches_identity(candidate, identity):
    """Require exact fresh /proc identity and namespace alias before attribution."""
    if not isinstance(candidate, dict) or not isinstance(identity, dict):
        return False
    if (candidate.get('classification') not in _GPU_CONSUMER_CLASSIFICATIONS
            or candidate.get('evidence_state') != 'COMPLETE'
            or candidate.get('identity_stability') not in ('STABLE_BOTH', 'POST_ONLY')
            or not identity.get('nspid_available')):
        return False
    classification, visibility = candidate.get('classification'), candidate.get('visibility')
    if ((classification == 'NAMESPACE_ALIAS' and visibility != 'NSPID_ALIAS')
            or (classification in ('MATCHED', 'NO_SERVICE_ANCESTOR') and visibility != 'DIRECT_PROC')):
        return False
    gpu_pid = candidate.get('gpu_pid')
    if type(gpu_pid) is not int or gpu_pid <= 1:
        return False
    candidate_nspid = candidate.get('nspid')
    current_nspid = identity.get('nspid')
    if (not isinstance(candidate_nspid, list) or not candidate_nspid
            or any(type(value) is not int or value <= 0 for value in candidate_nspid)
            or not isinstance(current_nspid, list)
            or any(type(value) is not int or value <= 0 for value in current_nspid)):
        return False
    return (all(candidate.get(field) == identity.get(field) for field in _GPU_IDENTITY_FIELDS)
            and gpu_pid in current_nspid)


def _gpu_candidates_by_pid(candidates):
    by_pid = {}
    if not isinstance(candidates, (list, tuple)):
        return by_pid
    for candidate in candidates[:MAX_GPU_APPS * 2]:
        if not isinstance(candidate, dict):
            continue
        pid = candidate.get('pid')
        if type(pid) is int and pid > 1:
            by_pid.setdefault(pid, []).append(candidate)
    return by_pid


def gpu_process_census(proc_root=Path('/proc'), run_fn=run, clock=time.time_ns):
    before = _capture_gpu_apps(run_fn, clock)
    services = _capture_services(proc_root, run_fn, clock)
    before_pids = {row['gpu_pid'] for row in before['apps']}
    before_proc = _capture_proc_targets(proc_root, before_pids, services)
    before_proc['supervisor_complete'] = services.get('complete') is True
    before_proc['supervisor_inventory_complete'] = services.get('inventory_complete') is True
    after = _capture_gpu_apps(run_fn, clock)
    process_inventory = _capture_process_identity_inventory(proc_root, clock)
    after_pids = {row['gpu_pid'] for row in after['apps']}
    after_proc = _capture_proc_targets(proc_root, after_pids, services)
    after_proc['supervisor_complete'] = services.get('complete') is True
    after_proc['supervisor_inventory_complete'] = services.get('inventory_complete') is True
    links = _link_gpu_apps(before, after, before_proc, after_proc)
    visible = sorted({target['local_pid']
                      for snapshot in (before_proc, after_proc)
                      for target in snapshot['targets'].values()
                      if target.get('local_pid')})
    gpu_consumer_identities = []
    for link in links:
        candidate = _candidate_from_link(link)
        if candidate is not None:
            gpu_consumer_identities.append(candidate)
    try:
        reader_pid_namespace = os.readlink(Path(proc_root) / 'self/ns/pid')
    except OSError:
        reader_pid_namespace = None
    return {'gpu_apps_before': before, 'gpu_apps_after': after,
            'supervisor_services': services, 'gpu_process_links': links,
            'visible_proc_pids': visible,
            'gpu_consumer_identities': gpu_consumer_identities,
            'process_identity_inventory': process_inventory,
            'reader_pid_namespace': reader_pid_namespace}


def _format_gpu_app(row):
    return ', '.join((str(row['gpu_pid']), row['gpu_uuid'], str(row['used_gpu_memory'])))


def hardware(census=None):
    rc,g=run(['nvidia-smi','--query-gpu=index,name,uuid,memory.total,memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'])
    census = gpu_process_census() if census is None else census
    return {'gpu_rc':rc,'gpu':[x for x in g.splitlines() if SAFE.fullmatch(x.replace(',',''))][:4],
      'gpu_apps':[ _format_gpu_app(x) for x in census['gpu_apps_before']['apps'][:16] ],
      'gpu_apps_before':census['gpu_apps_before'],
      'gpu_apps_after':census['gpu_apps_after'],
      'gpu_process_links':census['gpu_process_links'],
      'gpu_consumer_identities':census.get('gpu_consumer_identities',[]),
      'supervisor_services':census['supervisor_services'],
      'reader_pid_namespace':census['reader_pid_namespace'],
      'cpus':os.cpu_count(),'load':list(os.getloadavg()),
      'cgroup_max':num('/sys/fs/cgroup/memory.max'),'cgroup_current':num('/sys/fs/cgroup/memory.current'),
      'cpu_max':num('/sys/fs/cgroup/cpu.max'),
      'disk':{r:dict(zip(('total','used','free'),shutil.disk_usage(r))) for r in ROOTS if Path(r).is_dir()}}

def _proc_stat(proc_dir, expected_pid):
    raw = _read_proc_text(Path(proc_dir) / 'stat', 4096).strip()
    prefix = str(expected_pid) + ' ('
    boundary = raw.rfind(') ')
    if not raw.startswith(prefix) or boundary < len(prefix):
        raise ValueError('HOLD_PID_STAT_IDENTITY')
    fields = raw[boundary + 2:].split()
    if len(fields) < 20 or not fields[19].isdigit():
        raise ValueError('HOLD_PID_START_TICKS')
    try:
        return {'pid': int(expected_pid), 'state': fields[0],
                'ppid': int(fields[1]), 'pgrp': int(fields[2]),
                'start_ticks': int(fields[19])}
    except ValueError as exc:
        raise ValueError('HOLD_PID_STAT_FIELDS') from exc


def proc_start_ticks(proc_dir, expected_pid):
    """Read Linux /proc/<pid>/stat field 22; verify PID despite ')' in comm."""
    return _proc_stat(proc_dir, expected_pid)['start_ticks']

def _capture_process_identity_inventory(proc_root=Path('/proc'), clock=time.time_ns):
    """Capture a bounded identity-only row for every numeric /proc entry.

    This inventory deliberately omits argv, cmdline, environment, and cgroup
    paths. Any capped scan, enumeration/read error, unstable PID identity, or
    missing required field makes the snapshot incomplete.
    """
    started = clock()
    rows, failure_pids = [], []
    entries_seen = 0
    read_failures = 0
    truncated = False
    enumeration_error = None
    try:
        with os.scandir(proc_root) as entries:
            for entry in entries:
                if not entry.name.isdecimal():
                    continue
                entries_seen += 1
                if entries_seen > MAX_PROC_ENTRIES:
                    truncated = True
                    break
                pid = int(entry.name)
                try:
                    identity = read_proc_identity(proc_root, pid)
                except (OSError, ValueError, KeyError, TypeError):
                    identity = None
                if identity is None:
                    read_failures += 1
                    if len(failure_pids) < 64:
                        failure_pids.append(pid)
                    rows.append({'pid': pid, 'ppid': None, 'uid': None,
                                 'start_ticks': None, 'nspid': None,
                                 'namespaces': {'pid': None, 'mnt': None, 'cgroup': None},
                                 'comm': None, 'exe': None,
                                 'identity_state': 'UNAVAILABLE_OR_CHANGED'})
                    continue
                namespaces = {'pid': identity.get('pid_namespace'),
                              'mnt': identity.get('mnt_namespace'),
                              'cgroup': identity.get('cgroup_namespace')}
                missing = []
                if identity.get('pid') != pid:
                    missing.append('pid')
                if type(identity.get('ppid')) is not int or identity['ppid'] < 0:
                    missing.append('ppid')
                if type(identity.get('uid')) is not int or identity['uid'] < 0:
                    missing.append('uid')
                if type(identity.get('start_ticks')) is not int or identity['start_ticks'] <= 0:
                    missing.append('start_ticks')
                nspid = identity.get('nspid')
                if (not identity.get('nspid_available') or not isinstance(nspid, list)
                        or not nspid or len(nspid) > 16
                        or any(type(value) is not int or value <= 0 for value in nspid)):
                    missing.append('nspid')
                for name, value in namespaces.items():
                    expected = {'pid': 'pid', 'mnt': 'mnt', 'cgroup': 'cgroup'}[name]
                    if not isinstance(value, str) or not re.fullmatch(
                            rf'{expected}:\[[0-9]+\]', value):
                        missing.append('namespace_' + name)
                if not isinstance(identity.get('comm'), str) or not identity['comm']:
                    missing.append('comm')
                exe = identity.get('executable')
                exe_state = identity.get('executable_state', 'UNAVAILABLE')
                if exe_state not in ('AVAILABLE', 'MISSING'):
                    missing.append('exe_read')
                if exe_state == 'AVAILABLE' and (
                        not isinstance(exe, str) or not exe or exe == '[REDACTED]'):
                    missing.append('exe')
                row = {'pid': pid, 'ppid': identity.get('ppid'),
                       'uid': identity.get('uid'), 'start_ticks': identity.get('start_ticks'),
                       'nspid': nspid if isinstance(nspid, list) else None,
                       'namespaces': namespaces, 'comm': identity.get('comm'), 'exe': exe,
                       'exe_state': exe_state,
                       'identity_state': 'VERIFIED' if not missing else 'IDENTITY_INCOMPLETE'}
                if missing:
                    row['missing_fields'] = sorted(set(missing))
                    read_failures += 1
                    if len(failure_pids) < 64:
                        failure_pids.append(pid)
                rows.append(row)
    except OSError as exc:
        enumeration_error = type(exc).__name__
    finished = clock()
    rows.sort(key=lambda row: row['pid'])
    complete = (not truncated and enumeration_error is None and read_failures == 0
                and entries_seen == len(rows))
    encoded_rows = json.dumps(rows, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return {'scope': 'ALL_NUMERIC_PROC_PIDS_MINIMAL_IDENTITY',
            'started_unix_ns': started, 'finished_unix_ns': finished,
            'entries_seen': entries_seen, 'row_count': len(rows),
            'cap': MAX_PROC_ENTRIES, 'truncated': truncated,
            'enumeration_error': enumeration_error, 'read_failure_count': read_failures,
            'read_failure_pids': failure_pids, 'complete': complete,
            'fields': ['pid', 'ppid', 'uid', 'start_ticks', 'nspid',
                       'namespaces.pid', 'namespaces.mnt', 'namespaces.cgroup', 'comm', 'exe', 'exe_state'],
            'omitted_fields': ['argv', 'cmdline', 'environ', 'cgroup_paths'],
            'rows_sha256': hashlib.sha256(encoded_rows).hexdigest(), 'rows': rows}


def process_rows(proc_root=Path('/proc'), include_gpu_identities=()):
    rows, gpu_rows = [], []
    include = _gpu_candidates_by_pid(include_gpu_identities)
    flags={'-m','--model','--model-path','--model_path','--base-model','--student','--output_dir','--output-dir','--config','-c'}
    for p in Path(proc_root).iterdir():
        if not p.name.isdigit():continue
        try:
            pid=int(p.name)
            initial_ticks=proc_start_ticks(p,pid)
            gpu_candidates = include.get(pid, [])
            fresh_identity = None
            if gpu_candidates:
                try:
                    fresh_identity = read_proc_identity(proc_root, pid)
                except (OSError, ValueError):
                    fresh_identity = None
            valid_gpu_candidates = [candidate for candidate in gpu_candidates
                                    if _candidate_matches_identity(candidate, fresh_identity)]
            gpu_consumer = bool(valid_gpu_candidates)
            try:
                argv=(p/'cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
            except OSError:
                if not gpu_consumer:raise
                argv=[]
            keyword_match = bool(argv) and any(
                k in ' '.join(argv[:3]).lower()
                for k in ('nox','llama','train','python','supervisor','rclone','jupyter'))
            if (not argv or not keyword_match) and not gpu_consumer:continue
            args=[]
            for i,v in enumerate(argv):
                if v in flags and i+1<len(argv) and SAFE.fullmatch(argv[i+1]) and '://' not in argv[i+1]:args.append([v,argv[i+1]])
            try:
                comm=(p/'comm').read_text().strip()[:60]
            except OSError:
                comm=None
            scripts=[v for v in argv[1:5] if v.endswith(('.py','.sh')) and SAFE.fullmatch(v)]
            if proc_start_ticks(p,pid) != initial_ticks:continue
            if gpu_consumer:
                try:
                    export_identity = read_proc_identity(proc_root, pid)
                except (OSError, ValueError):
                    export_identity = None
                valid_gpu_candidates = [candidate for candidate in valid_gpu_candidates
                                        if _candidate_matches_identity(candidate, export_identity)]
                gpu_consumer = bool(valid_gpu_candidates)
            if (not argv or not keyword_match) and not gpu_consumer:continue
            row={'pid':pid,'comm':comm,
                 'executable':os.path.basename(argv[0]) if argv else None,
                 'arguments':args[:12], 'gpu_consumer':gpu_consumer,
                 'start_ticks':initial_ticks}
            if gpu_consumer:
                row['gpu_identity']={key:valid_gpu_candidates[0][key]
                                     for key in ('gpu_pid','start_ticks','nspid',
                                                  'pid_namespace','mnt_namespace',
                                                  'cgroup_namespace','classification','visibility')}
            if scripts:row['scripts']=scripts
            (gpu_rows if gpu_consumer else rows).append(row)
        except (OSError,ValueError):continue
    # Preserve the legacy 100-row keyword-filtered inventory and add only
    # census-linked consumers whose complete PID/start-tick/namespace identity
    # still matches at export, even when their argv has no audit keywords.
    return gpu_rows[:MAX_GPU_APPS * 2] + rows[:100]

def v13_owner_fence_metadata(root=Path('/root/nox'), workspace_stop=Path('/workspace/NOX_STOP'), lstat=os.lstat):
    """READ-ONLY marker presence, not authorization to start, stop, or write.

    Preserve unreadable markers as UNKNOWN; missing flags at one instant are
    never evidence of an owner lease, safe release, or completed shutdown.
    Do not open, follow, hash or export marker contents.
    """
    paths = {
        'STOP': root / 'STOP',
        'STOP_FLAG': root / 'STOP.flag',
        'LOWER_STOP_FLAG': root / 'stop.flag',
        'DOT_STOP': root / '.stop',
        'PROGRAM_STOP': root / 'program/STOP',
        'STATE_STOP': root / 'state/STOP',
        'STATE_STOP_FLAG': root / 'state/STOP.flag',
        'MEDIA_STOP': root / 'state/MEDIA_STOP.flag',
        'OWNER_MAINTENANCE': root / 'state/OWNER_MAINTENANCE.flag',
        'WORKSPACE_STOP': workspace_stop,
        'TRAIN_HOLD': root / 'state/TRAIN_HOLD.flag',
    }
    rows = {}
    for name, path in paths.items():
        try:
            lstat(path)
            rows[name] = 'PRESENT'
        except FileNotFoundError:
            rows[name] = 'NOT_FOUND_AT_SNAPSHOT'
        except OSError:
            rows[name] = 'UNKNOWN_UNREADABLE'
    owner_names = tuple(name for name in rows if name != 'TRAIN_HOLD')
    owner_observed = [rows[name] for name in owner_names]
    status = ('PRESENT' if 'PRESENT' in owner_observed else
              'UNKNOWN' if 'UNKNOWN_UNREADABLE' in owner_observed else
              'NOT_OBSERVED_NOT_AUTHORIZED')
    return {
        'scope': 'READ_ONLY_MARKER_METADATA',
        'owner_stop_state': status,
        'train_hold_state': rows['TRAIN_HOLD'],
        'markers': rows,
        'owner_lease_state': 'NOT_CHECKED',
        'may_clear_stop': False,
        'may_start_nox': False,
        'may_write_native': False,
        'pid_starttime_verified': False,
    }


def supervisor():
    fence=v13_owner_fence_metadata()
    binary=shutil.which('supervisorctl')
    if not binary:
        binary=next((x for x in ('/opt/venv/bin/supervisorctl','/usr/local/bin/supervisorctl') if Path(x).is_file()),None)
    if not binary:return {'available':False,'owner_fence_readonly':fence}
    candidates=[None]+[x for x in ('/etc/supervisor/supervisord.conf','/etc/supervisord.conf','/root/nox/supervisord.conf') if Path(x).is_file()]
    results=[]
    for c in candidates:
        args=[binary]+(['-c',c] if c else [])+['status']
        rc,out=run(args)
        rows=[]
        for line in out.splitlines():
            m=re.match(r'^([A-Za-z0-9_.:-]+)\s+(RUNNING|STARTING|STOPPED|FATAL|BACKOFF|EXITED|STOPPING|UNKNOWN)\b(.*)$',line)
            if m:
                pid=re.search(r'\bpid (\d+)',m.group(3))
                rows.append({'name':m.group(1),'state':m.group(2),'pid':int(pid[1]) if pid else None})
        results.append({'config':c,'rc':rc,'services':rows})
        if rows:break
    return {'available':True,'results':results,'owner_fence_readonly':fence}

def v13_wheelhouse_admission(record):
    """Metadata-only ABI gate for the Drive CP311/cu126 wheelhouse, never an installer.

    A matching wheel tag is not a GPU smoke, driver test, license approval, or
    native installation receipt. Incompatible installed Python environments
    must not be modified to make a source check pass.
    """
    if not isinstance(record, dict) or not isinstance(record.get('_runtime'), dict):
        return 'HOLD_WHEELHOUSE_RUNTIME_ABI_UNKNOWN'
    runtime = record['_runtime']
    if runtime.get('python_abi') != 'cpython-311':
        return 'HOLD_WHEELHOUSE_CP311_PYTHON_ABI_MISMATCH'
    if runtime.get('platform') != 'linux-x86_64':
        return 'HOLD_WHEELHOUSE_LINUX_X86_64_PLATFORM_MISMATCH'
    # A CP311 cache tag alone is not enough: it can disagree with the
    # interpreter's actual version. Reject contradictory or missing evidence
    # rather than labelling a potentially CP312 process a candidate.
    python_version = runtime.get('python_version')
    if not isinstance(python_version, str) or re.fullmatch(r'3\.11\.\d+', python_version) is None:
        return 'HOLD_WHEELHOUSE_CP311_VERSION_MISMATCH'
    version = record.get('torch')
    if not isinstance(version, str) or not version:
        return 'HOLD_WHEELHOUSE_TORCH_BUILD_UNKNOWN'
    # A forged package label such as "unknown+cu126" is not a PyTorch build.
    if re.fullmatch(r'[1-9]\d*\.\d+\.\d+\+cu126', version) is None:
        return 'HOLD_WHEELHOUSE_CU126_TORCH_BUILD_MISMATCH'
    return 'SOURCE_ONLY_WHEELHOUSE_ABI_CANDIDATE_NATIVE_SM70_HOLD'


def packages():
    code="import importlib.metadata as m,json,sys,sysconfig; names=['torch','transformers','accelerate','datasets','deepspeed','safetensors','peft','bitsandbytes','trl','psutil','nvidia-ml-py','diffusers','opencv-python','imageio-ffmpeg']; d={'_runtime':{'python_abi':sys.implementation.cache_tag,'python_version':'.'.join(map(str,sys.version_info[:3])),'platform':sysconfig.get_platform()}};\nfor n in names:\n try:d[n]=m.version(n)\n except m.PackageNotFoundError:d[n]=None\nprint(json.dumps(d))"
    found={}
    for p in ('/root/venv_volta/bin/python','/opt/venv/bin/python','/root/nox/.venv/bin/python','/usr/bin/python3'):
        if Path(p).is_file():
            rc,out=run([p,'-c',code])
            try:
                row=json.loads(out) if rc==0 else {'status':'IMPORT_FAILED'}
                if isinstance(row,dict) and rc==0:
                    row['_wheelhouse_candidate']=v13_wheelhouse_admission(row)
                found[p]=row
            except ValueError:found[p]={'status':'INVALID_OUTPUT'}
    return found

# Exact immutable DeepSeek pins mirrored from v51/hf_range_probe.py.
# The offline source test asserts these rows remain identical to that manifest.
MODEL_ROOT='/root/nox/models'
MODEL_MANIFEST_REVISION='65d53bc8be65123e255ff02f3ded958b6dbf54fd'
PINNED_MODEL_FILES=(
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf',5780704,'f356f198561f56df36f7ab92d7238a926646d76de992c34f15bcb939a5f529b9'),
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00002-of-00006.gguf',39535781184,'25af3785ccf925f54137e1ead4c481a8952315dc0b1af6519a99407f67bce8f3'),
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00003-of-00006.gguf',39736712000,'8168d0998fc494def2e1952d83c131425a108660aae9d29190f5a8670ab62b48'),
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00004-of-00006.gguf',39036908384,'9eb9b4de1968f150dfc207eb31c27be9cd9b5666a9a6246bde8a22b184b4bee0'),
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00005-of-00006.gguf',19923784832,'7e35f6b4e6fc46f6c4b152b593d84d683c5ece695ae6ad734f556198c041bec1'),
 ('DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf',110595290816,'3dac4c54893ad7aa89103c0028500eadc78e74112cef3a2930a97e67dc9fb4f3'),
)

def pinned_model_paths(root=MODEL_ROOT,lstat=os.lstat):
    """Metadata-only, no-follow stat for the six immutable targets under one root."""
    root_path=Path(root)
    if not root_path.is_absolute():
        return {'status':'HOLD_MODEL_ROOT_NOT_ABSOLUTE','root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,'files':[]}
    root_parts=root_path.parts
    ancestors=[]; current=Path(root_path.anchor)
    for part in root_parts[1:]:
        current=current/part
        ancestors.append(current)
    try:
        for ancestor in ancestors:
            mode=lstat(str(ancestor)).st_mode
            if __import__('stat').S_ISLNK(mode):
                return {'status':'HOLD_MODEL_PATH_SYMLINK','root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,
                        'files':[{'path':str(root_path/name),'exists':None,'type':'blocked',
                                  'bytes':None,'expected_bytes':size,'sha_status':'NOT_CHECKED',
                                  'path_status':'HOLD_MODEL_PATH_SYMLINK'}
                                 for name,size,_ in PINNED_MODEL_FILES]}
            if not __import__('stat').S_ISDIR(mode):
                return {'status':'HOLD_MODEL_ROOT_COMPONENT_TYPE','root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,
                        'files':[{'path':str(root_path/name),'exists':None,'type':'blocked',
                                  'bytes':None,'expected_bytes':size,'sha_status':'NOT_CHECKED',
                                  'path_status':'HOLD_MODEL_ROOT_COMPONENT_TYPE'}
                                 for name,size,_ in PINNED_MODEL_FILES]}
    except FileNotFoundError:
        pass
    except OSError as exc:
        status='HOLD_MODEL_PATH_STAT_'+type(exc).__name__.upper()
        return {'status':status,'root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,
                'files':[{'path':str(root_path/name),'exists':None,'type':'unknown',
                          'bytes':None,'expected_bytes':size,'sha_status':'NOT_CHECKED',
                          'path_status':status} for name,size,_ in PINNED_MODEL_FILES]}
    results=[]
    for name,expected_bytes,sha256 in PINNED_MODEL_FILES:
        if (not name or Path(name).name!=name or '/' in name or '\\\\' in name
                or name in ('.','..')):
            return {'status':'HOLD_MODEL_PATH_ESCAPE','files':[]}
        target=root_path/name
        path=str(target)
        row={'path':path,'exists':False,'type':'missing','bytes':None,
             'expected_bytes':expected_bytes,'sha_status':'NOT_CHECKED'}
        try:
            observed=lstat(path)
            mode=observed.st_mode
            statmod=__import__('stat')
            if statmod.S_ISLNK(mode):
                row.update({'type':'symlink','path_status':'HOLD_MODEL_PATH_SYMLINK'})
                results.append(row)
                continue
            if statmod.S_ISREG(mode):
                row.update({'exists':True,'type':'regular','bytes':observed.st_size,
                            'size_status':'MATCH' if observed.st_size==expected_bytes else 'MISMATCH'})
            elif statmod.S_ISDIR(mode):
                row.update({'exists':True,'type':'directory','bytes':None})
            else:
                row.update({'exists':True,'type':'other','bytes':None})
            results.append(row)
        except FileNotFoundError:
            results.append(row)
        except OSError as exc:
            row.update({'type':'unknown','path_status':'HOLD_MODEL_PATH_STAT_'+type(exc).__name__.upper()})
            results.append(row)
    # Overall status must fail closed. The caller must not treat unreadable, bad-sized,
    # or nonregular candidates as a clean model inventory just because other rows passed.
    path_holds=[r['path_status'] for r in results if r.get('path_status')]
    if 'HOLD_MODEL_PATH_SYMLINK' in path_holds:
        status='HOLD_MODEL_PATH_SYMLINK'
    elif path_holds:
        status=path_holds[0]
    elif any(r['type'] not in ('regular','missing') for r in results):
        status='HOLD_MODEL_TARGET_TYPE'
    elif any(r.get('size_status')=='MISMATCH' for r in results):
        status='HOLD_MODEL_FILE_SIZE_MISMATCH'
    elif any(r['type']=='missing' for r in results):
        # Missing GGUF files are not an admitted model, even if every readable
        # pathname was safe. In particular, never report OK for an empty root.
        status='HOLD_MODEL_FILES_MISSING'
    else:
        status='HOLD_MODEL_SHA_UNVERIFIED'  # File sizes match, but full GGUF SHA was NOT checked.
    return {'status':status,'root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,
            'files':results}

def models():
    return {'pinned_model_paths':pinned_model_paths()}

def storage():
    rc=shutil.which('rclone')
    if not rc:return {'rclone_present':False}
    status,out=run([rc,'listremotes'])
    names=[x.strip() for x in out.splitlines() if re.fullmatch(r'[A-Za-z0-9_.-]{1,64}:',x.strip())]
    checks=[]
    for remote in names[:3]:
        code,out=run([rc,'about',remote,'--json'],15)
        try:
            d=json.loads(out);clean={k:d[k] for k in ('total','used','free','trashed') if type(d.get(k)) is int}
        except (ValueError,TypeError):clean={}
        checks.append({'remote':remote,'about_rc':code,'capacity':clean})
    return {'rclone_present':True,'list_rc':status,'remotes':names,'checks':checks,
            'known_config_present':{x:Path(x).is_file() for x in ('/root/.config/rclone/rclone.conf','/root/nox/rclone.conf')}}

# Read only the current Linux mount namespace. Device source strings are intentionally
# omitted because they can contain remote paths or credentials. statvfs reads metadata only.
BLOCK_FILESYSTEMS={'ext2','ext3','ext4','xfs','btrfs','zfs','vfat','exfat','ntfs'}
LOCAL_CAPACITY_FILESYSTEMS=BLOCK_FILESYSTEMS|{'overlay','tmpfs','ramfs'}
def _unescape_mountinfo(value):
    return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m.group(1),8)),value)

def _capacity_row(path,mount_rows,statvfs,path_exists):
    exists=bool(path_exists(path))
    matches=[r for r in mount_rows if path==r['mountpoint'] or path.startswith(r['mountpoint'].rstrip('/')+'/')]
    mount=max(matches,key=lambda r:len(r['mountpoint'])) if matches else None
    try:
        if not exists:raise FileNotFoundError(path)
        if mount is None or mount['filesystem'] not in LOCAL_CAPACITY_FILESYSTEMS:
            raise OSError('filesystem is outside the local capacity allowlist')
        st=statvfs(path); block_size=st.f_frsize or st.f_bsize
        total=int(st.f_blocks)*int(block_size); available=int(st.f_bavail)*int(block_size)
    except (OSError,AttributeError,TypeError,ValueError):
        total=None; available=None
    row={'path':path,'exists':exists,'mountpoint':mount['mountpoint'] if mount else None,
         'filesystem':mount['filesystem'] if mount else None,
         'device_major_minor':mount['device_major_minor'] if mount else None,
         'total_bytes':total,'available_bytes':available}
    return row

def _mount_inventory_from_text(text,statvfs=os.statvfs,path_exists=None):
    rows=[]; mount_by_path={}; type_counts={}
    lines=text.splitlines(); truncated=len(lines)>4096
    for line in lines[:4096]:
        try:
            before,after=line.split(' - ',1)
            left=before.split(); right=after.split()
            if len(left)<6 or len(right)<3:continue
            fstype=right[0]; mountpoint=_unescape_mountinfo(left[4]); dev=left[2]
            if not SAFE.fullmatch(mountpoint) or not re.fullmatch(r'\d+:\d+',dev):continue
            if re.fullmatch(r'[A-Za-z0-9_.+-]{1,64}',fstype):
                type_counts[fstype]=type_counts.get(fstype,0)+1
            entry={'mountpoint':mountpoint,'filesystem':fstype,'device_major_minor':dev}
            mount_by_path[mountpoint]=entry
            if fstype in BLOCK_FILESYSTEMS and not any(r['mountpoint']==mountpoint for r in rows):
                try:
                    st=statvfs(mountpoint); block_size=st.f_frsize or st.f_bsize
                    total=int(st.f_blocks)*int(block_size); available=int(st.f_bavail)*int(block_size)
                except (OSError,AttributeError,TypeError,ValueError):
                    total=None; available=None
                rows.append({**entry,'total_bytes':total,'available_bytes':available})
        except (ValueError,IndexError):continue
    if len(rows)>512:
        rows=rows[:512]; truncated=True
    rows.sort(key=lambda r:(r['mountpoint'],r['filesystem'],r['device_major_minor']))
    if path_exists is None:path_exists=lambda p:Path(p).exists()
    all_mount_rows=list(mount_by_path.values())
    data_entry=mount_by_path.get('/data')
    paths=[_capacity_row(p,all_mount_rows,statvfs,path_exists) for p in ('/','/data','/workspace')]
    return {'scope':'current_process_mount_namespace_only','provider_disk_visibility':'not_established',
            'mountinfo_readable':True,'mountinfo_entry_count':len(lines),'filesystem_type_counts':type_counts,
            'data_mount_present':data_entry is not None,'data_mount_entry':data_entry,
            'storage_paths':paths,'eligible_block_mount_count':len(rows),'truncated':truncated,'mounts':rows}

def mount_inventory():
    try:
        text=Path('/proc/self/mountinfo').read_text()
    except OSError as e:
        return {'scope':'current_process_mount_namespace_only','mountinfo_readable':False,
                'error':type(e).__name__,'mounts':[]}
    return _mount_inventory_from_text(text)

def worker(task):
    try:
        if isinstance(task, tuple):
            i, census = task
        else:
            i, census = task, None
        functions=(hardware,process_rows,supervisor,packages,models,storage,mount_inventory)
        if i == 0:
            result = functions[i](census)
        elif i == 1:
            include = census.get('gpu_consumer_identities', []) if isinstance(census, dict) else []
            result = functions[i](include_gpu_identities=include)
        else:
            result = functions[i]()
        record = {'section':functions[i].__name__,'worker_pid':os.getpid(),'result':result}
        if i == 1 and isinstance(census, dict):
            record['bounded_process_identity_inventory'] = census.get('process_identity_inventory')
        return record
    except Exception as e:return {'section':str(task),'worker_pid':os.getpid(),'error':type(e).__name__}

def main():
    census = gpu_process_census()
    hardware_keys = ('gpu_apps_before', 'gpu_apps_after', 'gpu_process_links',
                     'gpu_consumer_identities', 'supervisor_services', 'reader_pid_namespace')
    hardware_snapshot = {key: census.get(key) for key in hardware_keys}
    process_snapshot = {
        'gpu_consumer_identities': census.get('gpu_consumer_identities', []),
        'process_identity_inventory': census.get('process_identity_inventory')
    }
    tasks = ((0, hardware_snapshot), (1, process_snapshot)) + tuple(
        (i, None) for i in range(2, 7))
    with ProcessPoolExecutor(max_workers=7) as pool:
        for row in pool.map(worker, tasks):
            # One JSON record per bounded result item; never dump env/config secrets.
            print('NOX_MAINT_AUDIT='+json.dumps(row,separators=(',',':')),flush=True)
    print('NOX_MAINT_AUDIT_COMPLETE=true',flush=True)
if __name__=='__main__':main()

