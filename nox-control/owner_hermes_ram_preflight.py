#!/usr/bin/env python3
"""Read-only identity/resource evidence for one public Hermes SSD original.

No allocation, relocation, source/flag write, model load, download or service
action. RAM feasibility is a projection, not admission or a new peak measure.
"""
from __future__ import annotations
import base64
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
SHM = Path('/dev/shm')
CGROUP = Path('/sys/fs/cgroup')
NAME = 'Hermes-3-Llama-3.1-8B.Q4_K_M.gguf'
SSD = ROOT / 'offload_shm_t888u/teachers' / NAME
WARM = SHM / 'nox_t802u/teachers' / NAME
TEACHER = ROOT / 'models/teachers' / NAME
SIZE = 4920733824
SHA = 'd4403ce5a6e930f4c2509456388c20d633a15ff08dd52ef3b142ff1810ec3553'
PUBLIC_REPO = 'NousResearch/Hermes-3-Llama-3.1-8B-GGUF'
PUBLIC_REVISION = 'ad1d6b27c4ebc45cdb43e10871324742d771e1c4'
PROC_NAME = 'owner_builder_proc_probe.py'
PROC_SHA = '1743c8587dac72f412400be9059d1fe01ef73a1955af2056ff77a550e53af3ff'
PROFILE_PINS = {
    'qwen_student_training_entry.py': '259ac097f3ceec5be217748667a421ab5c39ebb56b9b2817fd1368d278f99cb0',
    'owner_qwen_memfd.py': '938335009efe691a9cef7b41daa7c55f3c8d3d8618a10a5eb5db125fd45afa82',
    'qwen35_9b_manifest.json': '2275fc88370ca8ba409a791819e13c8ab7d4e38cce4576a13170b05bcb8b839b',
}
ROLE_PINS = {
    'download_t802u.sh': '6a8781f2253818dd9c57e02d8d13e6ec0c1f5b587b64514d0946a36f0a83f049',
    'teacher_serve_t811u.sh': '177fecab38073252466669280b9c41add3ec08b4f5ffe90e8f973c46aea1cde0',
}
SERVICES = ('nox-teacher-serve-t811u', 'nox-downloads-t802u', 'nox-offload-t850u',
            'nox-watch-swap-t845u', 'nox-train-volta-t866u')
SCHEMA = 'NOX_HERMES_RAM_PREFLIGHT_V1'
GIB = 1024 ** 3
QWEN_BASE_BYTES = 19329393661
RATE = 64 * 1024 ** 2
SECONDS = 175
FIELDS = ('st_dev', 'st_ino', 'st_size', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_mtime_ns', 'st_ctime_ns')


class Hold(RuntimeError): pass


def require(ok, code):
    if not ok: raise Hold('HOLD_HERMES_PREFLIGHT_' + code)


def digest(raw): return hashlib.sha256(raw).hexdigest()
def identity(info): return {k: getattr(info, k) for k in FIELDS}
def encoded(value): return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
def safe(exc):
    value = str(exc)
    return value if re.fullmatch('HOLD_[A-Z0-9_]{1,110}', value) else 'HOLD_HERMES_PREFLIGHT_' + type(exc).__name__.upper()


def tick(deadline):
    require(time.monotonic() < deadline, 'DEADLINE')
    require(not any(p.exists() or p.is_symlink() for p in
        tuple(ROOT / s for s in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'state/STOP', 'program/STOP'))
        + (Path('/workspace/NOX_STOP'),)), 'OWNER_STOP')


def open_plain(path):
    path = Path(path); require(path.is_absolute() and '..' not in path.parts, 'PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for i, part in enumerate(path.parts[1:]):
            flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
            flags |= os.O_DIRECTORY if i < len(path.parts) - 2 else getattr(os, 'O_NOATIME', 0)
            child = os.open(part, flags, dir_fd=fd); os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd); raise


def read_small(path, maximum=65536, pseudo=False):
    fd = open_plain(path)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and (pseudo or 0 <= before.st_size <= maximum), 'SMALL_SCOPE')
        raw = os.read(fd, maximum + 1); require(len(raw) <= maximum, 'SMALL_BOUND')
        if not pseudo:
            require(len(raw) == before.st_size and identity(os.fstat(fd)) == identity(before), 'SMALL_CHANGED')
            again = open_plain(path)
            try: require(identity(os.fstat(again)) == identity(before), 'SMALL_NAME_CHANGED')
            finally: os.close(again)
        return raw
    finally: os.close(fd)


def budget():
    values = {}
    for name in ('memory.current', 'memory.max', 'memory.peak'):
        raw = read_small(CGROUP / name, 128, True).strip()
        require(raw.isdigit(), 'CGROUP_NUMERIC'); values[name] = int(raw)
    require(0 <= values['memory.current'] <= values['memory.max'] and values['memory.peak'] >= 0, 'CGROUP_RANGE')
    memory = {}
    for line in read_small(CGROUP / 'memory.stat', 16384, True).splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in (b'anon', b'file', b'shmem', b'inactive_file', b'active_file') and parts[1].isdigit():
            memory[parts[0].decode()] = int(parts[1])
    mount = read_small(Path('/proc') / str(os.getpid()) / 'mountinfo', 262144, True)
    mounts = [line.split(b' - ', 1)[1].split()[0].decode() for line in mount.splitlines()
              if b' - ' in line and len(line.split(b' - ', 1)[0].split()) >= 5
              and line.split(b' - ', 1)[0].split()[4] == b'/dev/shm']
    fs = os.statvfs(SHM); disk = os.statvfs(ROOT)
    return {'at': time.time(), 'cgroup_current_bytes': values['memory.current'],
        'cgroup_limit_bytes': values['memory.max'], 'cgroup_peak_bytes': values['memory.peak'],
        'cgroup_headroom_bytes': values['memory.max'] - values['memory.current'], 'memory_stat': memory,
        'tmpfs_total_bytes': fs.f_blocks * fs.f_frsize, 'tmpfs_free_bytes': fs.f_bavail * fs.f_frsize,
        'dev_shm_is_tmpfs': mounts == ['tmpfs'], 'ssd_free_bytes': disk.f_bavail * disk.f_frsize}


def projections(row, profile_verified):
    current = row['cgroup_headroom_bytes']; peak_head = row['cgroup_limit_bytes'] - row['cgroup_peak_bytes']
    tmp = row['tmpfs_free_bytes'] - 3 * GIB
    old = max(0, min(tmp, current - 16 * GIB, peak_head - 16 * GIB))
    after_hermes = current - SIZE
    stage = 48 * GIB + QWEN_BASE_BYTES
    return {'hermes_additional_bytes': SIZE, 'tmpfs_reserve_bytes': 3 * GIB,
        'tmpfs_after_copy_bytes': row['tmpfs_free_bytes'] - SIZE,
        'tmpfs_reserve_fits': row['dev_shm_is_tmpfs'] and tmp >= SIZE,
        'conservative_lifetime_peak_budget_bytes': old, 'conservative_lifetime_peak_fits': old >= SIZE,
        'lifetime_peak_is_not_current_qwen_profile_peak': True,
        'installed_qwen_gate_sources_verified': profile_verified,
        'qwen_full_source_bytes': QWEN_BASE_BYTES, 'qwen_initial_stage_required_headroom_bytes': stage,
        'projected_headroom_after_hermes_bytes': after_hermes,
        'projected_qwen_initial_stage_gate_fits': profile_verified and after_hermes >= stage,
        'qwen_post_base_required_headroom_bytes': 40 * GIB,
        'projected_post_base_headroom_bytes': after_hermes - QWEN_BASE_BYTES,
        'projected_qwen_post_base_gate_fits': profile_verified and after_hermes - QWEN_BASE_BYTES >= 40 * GIB,
        'future_complete_model_load_peak_measured': False, 'current_page_cache_not_assumed_freeable': True,
        'migration_or_training_start_authorized': False}


def aliases(target):
    rows = {}
    roots = (SSD.parent, WARM.parent, TEACHER.parent)
    for label, path in (('RAM_WARM_ALIAS', WARM), ('LEGACY_TEACHER_ALIAS', TEACHER)):
        try:
            current = Path('/'); pending = list(path.parts[1:]); hops = steps = 0; links = []
            while pending:
                steps += 1; require(steps <= 128, 'ALIAS_STEPS')
                current /= pending.pop(0); info = current.lstat()
                if stat.S_ISLNK(info.st_mode):
                    hops += 1; require(hops <= 8, 'ALIAS_HOPS')
                    text = os.readlink(current); require(len(text) <= 4096, 'ALIAS_BOUND')
                    dest = Path(os.path.normpath(text if os.path.isabs(text) else str(current.parent / text)))
                    require(any(dest == root or dest.is_relative_to(root) for root in roots), 'ALIAS_TARGET_SCOPE')
                    links.append({'identity': identity(info), 'source_path_sha256': digest(str(current).encode()),
                                  'target_path_sha256': digest(str(dest).encode())})
                    pending = list(dest.parts[1:]) + pending; current = Path('/')
            rows[label] = {'state': 'KNOWN_SCOPE_METADATA', 'symlink_hops': hops, 'resolved_to_ssd_path': current == SSD,
                'regular': stat.S_ISREG(info.st_mode), 'same_ssd_inode': (info.st_dev, info.st_ino) == (target['st_dev'], target['st_ino']),
                'identity': identity(info), 'link_metadata': links,
                'independent_full_copy_verified': False, 'unknown_target_paths_exported': False}
        except Exception as exc:
            rows[label] = {'state': 'ALIAS_UNVERIFIED', 'reason': safe(exc), 'unknown_target_paths_exported': False}
    return rows


def source_roles():
    result = {}
    for name, expected in {**PROFILE_PINS, **ROLE_PINS}.items():
        try:
            raw = read_small(ROOT / 'scripts' / name)
            row = {'sha256': digest(raw), 'expected_sha256': expected, 'source_matches': digest(raw) == expected}
            if name in ROLE_PINS:
                row.update(hermes_filename_referenced=NAME.encode() in raw,
                           public_repository_referenced=PUBLIC_REPO.encode() in raw)
            result[name] = row
        except Exception as exc:
            result[name] = {'source_matches': False, 'reason': safe(exc)}
    return result


def services():
    result = {name: {'state': 'UNKNOWN', 'pid': None} for name in SERVICES}
    try:
        proc = subprocess.run(['supervisorctl', 'status'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, timeout=3, env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        require(len(proc.stdout) <= 32768, 'SERVICE_OUTPUT_BOUND')
        for line in proc.stdout.decode(errors='replace').splitlines():
            match = re.match(r'^([a-zA-Z0-9_-]+)\s+(RUNNING|STOPPED|EXITED|FATAL|STARTING|STOPPING|BACKOFF|UNKNOWN)(?:\s+pid\s+(\d+),)?', line)
            if match and match[1] in result:
                result[match[1]] = {'state': match[2], 'pid': int(match[3]) if match[3] else None}
    except Exception:
        pass
    return result


def proc_helper():
    raw = base64.b64decode(BUNDLE.get(PROC_NAME, ''), validate=True)
    require(0 < len(raw) <= 65536 and digest(raw) == PROC_SHA, 'PROC_SOURCE_PIN')
    helper = types.ModuleType('_nox_hermes_readonly_proc')
    exec(compile(raw, '<pinned-proc>', 'exec'), helper.__dict__)
    return helper


def process_refs(helper, before, fd, deadline):
    ns, counters, refs, errors = {}, Counter(), [], []
    for name in helper.NAMESPACES:
        try:
            info = (helper.PROC / 'self/ns' / name).stat(); ns[name] = [info.st_dev, info.st_ino]
        except OSError: ns[name] = None
    pids = sorted(int(p.name) for p in helper.PROC.iterdir() if p.name.isdigit())
    complete = len(pids) <= helper.MAX_PIDS; inspected = ignored = 0; critical = {}
    try:
        for pid in pids[:helper.MAX_PIDS]:
            tick(deadline)
            row = helper.probe_process(pid, {(before['st_dev'], before['st_ino']): ['FIXED_HERMES']}, ns, deadline, counters, {})
            inspected += 1
            complete &= row.get('candidate_fd_maps_complete') is True and not row.get('references_truncated', False)
            if pid in (7637, 746485): critical[str(pid)] = row.get('stat_after', row.get('stat_before'))
            for ref in row['references']:
                if pid == os.getpid() and ref.get('kind') == 'FD' and ref.get('fd') == fd and ref.get('access') == 'READ_ONLY':
                    ignored += 1
                else: refs.append({'pid': pid, **ref})
            if row['errors'] and len(errors) < 12:
                errors.append({'pid': pid, 'errors': row['errors']})
    except helper.ProbeBudget: complete = False
    except Hold as exc:
        if str(exc).endswith('_OWNER_STOP'): raise
        complete = False
    return {'scope': 'CURRENT_PROC_MOUNT_VISIBLE_PROCESSES', 'complete': bool(complete), 'pids_seen': len(pids),
        'processes_inspected': inspected, 'known_reference_count': len(refs), 'references': refs[:64],
        'references_truncated': len(refs) > 64, 'access_errors': errors, 'own_readonly_fd_ignored': ignored,
        'known_process_metadata': critical, 'partial_visibility_is_not_inactivity_proof': True}


def full_hash(fd, deadline, result):
    before = os.fstat(fd); require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and before.st_size == SIZE, 'SSD_SCOPE')
    value = hashlib.sha256(); offset = 0; start = time.monotonic()
    while offset < SIZE:
        tick(deadline)
        raw = os.pread(fd, min(1024 ** 2, SIZE - offset), offset)
        require(bool(raw), 'SSD_EOF'); value.update(raw); offset += len(raw); result['ssd_bytes_read'] = offset
        target = start + offset / RATE
        while time.monotonic() < target:
            tick(deadline); time.sleep(min(.02, max(0, target - time.monotonic())))
    require(identity(os.fstat(fd)) == identity(before) and value.hexdigest() == SHA, 'SSD_FULL_SHA_OR_IDENTITY')
    again = open_plain(SSD)
    try: require(identity(os.fstat(again)) == identity(before), 'SSD_NAME_CHANGED')
    finally: os.close(again)
    return identity(before)


def inspect():
    deadline = time.monotonic() + SECONDS - 3; fd = None
    result = {'schema': SCHEMA, 'state': 'READ_ONLY_HERMES_PREFLIGHT_HELD', 'started_at': time.time(),
        'public_repository': PUBLIC_REPO, 'public_revision': PUBLIC_REVISION, 'public_filename': NAME,
        'expected_bytes': SIZE, 'expected_sha256': SHA, 'native_remote_download_or_metadata_check': False,
        'full_current_ssd_sha_verified': False, 'ssd_bytes_read': 0, 'files_written': 0, 'files_deleted': 0,
        'services_changed': False, 'training_flags_changed': False, 'models_loaded': False,
        'memory_allocated_for_weight_copy_bytes': 0, 'migration_authorized': False, 'source_contents_exported': False}
    try:
        helper = proc_helper(); tick(deadline)
        result['budget_before'] = budget(); result['source_roles'] = source_roles(); result['services_before'] = services()
        fd = open_plain(SSD); initial = identity(os.fstat(fd)); result['ssd_identity_before'] = initial
        require(stat.S_ISREG(initial['st_mode']) and initial['st_size'] == SIZE, 'SSD_SCOPE')
        result['aliases_before'] = aliases(initial)
        result['process_scan_before'] = process_refs(helper, initial, fd, min(deadline, time.monotonic() + 5))
        observed = full_hash(fd, deadline, result); result['full_current_ssd_sha_verified'] = True
        result['ssd_sha256'] = SHA; result['ssd_identity_after_hash'] = observed
        result['process_scan_after'] = process_refs(helper, observed, fd, min(deadline, time.monotonic() + 5))
        result['aliases_after'] = aliases(observed); result['services_after'] = services()
        result['budget_after'] = budget()
        tick(deadline)
        require(identity(os.fstat(fd)) == observed, 'SSD_CHANGED_AFTER_HASH')
        again = open_plain(SSD)
        try: require(identity(os.fstat(again)) == observed, 'SSD_FINAL_NAME_CHANGED')
        finally: os.close(again)
        verified = all(result['source_roles'][name]['source_matches'] for name in PROFILE_PINS)
        result['ram_projection_before'] = projections(result['budget_before'], verified)
        result['ram_projection_after'] = projections(result['budget_after'], verified)
        result['aliases_unchanged_during_probe'] = result['aliases_before'] == result['aliases_after']
        result['state'] = 'HERMES_IDENTITY_AND_RESOURCES_OBSERVED'
    except Exception as exc:
        result['reason'] = safe(exc)
    finally:
        if fd is not None: os.close(fd)
        result['finished_at'] = time.time()
    return result


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', ''); source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'EXISTING_TIMER')
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_): raise Hold('HOLD_HERMES_PREFLIGHT_WALL_TIME')
    signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, SECONDS)
    try: result = inspect()
    finally: signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
    result.update(request=request, source_sha=source)
    require(len(encoded(result)) <= 65536, 'OUTPUT_BOUND')
    ok = result['state'] == 'HERMES_IDENTITY_AND_RESOURCES_OBSERVED'
    print('NOX_MAINT_REPAIR=' + encoded({'kind': 'hermes_ram_preflight', 'data': result}).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(ok).lower(), flush=True)
    return 0 if ok else 2


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + encoded({'kind': 'hermes_ram_preflight', 'data': {
            'schema': SCHEMA, 'state': 'READ_ONLY_HERMES_PREFLIGHT_HELD', 'reason': safe(exc),
            'files_written': 0, 'files_deleted': 0, 'migration_authorized': False}}).decode(), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
