#!/usr/bin/env python3
"""Bounded, isolated Maya build. No inference, install, service or training action."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import shutil
import signal
import stat
import subprocess
import tarfile
import time
import urllib.request
import zipfile

ROOT = Path('/root/nox')
GIB = 1024 ** 3
MAYA = 'c81fab6c9d63cf69b928f92460e0a662b28aa9ec'
LLAMA = '3cf03257f219afbe7334045ff7c6a06ac68c627d'
SOURCE_MANIFEST_SHA = 'efa83e0bc417da78d9b774eb799a4858f5a45bd2113b710920ae6fc0603a0496'
CUDA = Path('/usr/local/cuda-12.4')
KEY = 'maya-c81fab6c9d63-cu124-sm70-v1'
DISK_RESERVE, DISK_MAX = 8 * GIB, 4 * GIB
RAM_RESERVE, BUILD_RSS_MAX, PROCESS_AS_MAX = 20 * GIB, 8 * GIB, 6 * GIB
WALL_SECONDS = 780
SAFE_PATH = str(CUDA / 'bin') + ':/usr/local/bin:/usr/bin:/bin'
ARTIFACTS = {
    'llama.tar.gz': {'url': 'https://codeload.github.com/ggml-org/llama.cpp/tar.gz/' + LLAMA,
        'bytes': 37513049, 'sha256': 'c076d7534afa0e5d0ec2a0d425b11e791c16f3de0d727221aea071cef156a280',
        'expanded_max': 200 * 1024 ** 2, 'members_max': 4500},
    'cmake.whl': {'url': 'https://files.pythonhosted.org/packages/61/e3/0d24bb452ebc819ab03bbc01b1f4d92863e5c106a93755a4eb38761495da/cmake-4.4.5-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl',
        'bytes': 30246479, 'sha256': '85625a9b6d5e88ff99c7eb79123d85570844e77ac076366cf75c609cc0b1b579',
        'expanded_max': 100 * 1024 ** 2, 'members_max': 4500},
}
PLAN = {'schema': 'NOX_MAYA_BUILD_OWNER_V1', 'maya': MAYA, 'llama': LLAMA, 'cuda': str(CUDA),
        'cmake': '4.4.5', 'arch': '70', 'target': 'maya-ds4', 'jobs': 2, 'portable': True,
        'tests': False, 'source_manifest_sha256': SOURCE_MANIFEST_SHA, 'artifacts': ARTIFACTS}


class Hold(RuntimeError):
    pass


def need(value, code):
    if not value:
        raise Hold(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def plain(path):
    p = Path(os.path.abspath(path))
    need(not any(x.is_symlink() for x in (*p.parents, p)), 'HOLD_BUILD_SYMLINK_PATH')
    return p


def read(path, maximum):
    fd = os.open(plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        s = os.fstat(f.fileno())
        need(stat.S_ISREG(s.st_mode) and s.st_size <= maximum, 'HOLD_BUILD_INPUT_SIZE_TYPE')
        raw = f.read(maximum + 1)
        after = os.fstat(f.fileno())
    need(len(raw) <= maximum and (s.st_ino, s.st_size, s.st_mtime_ns) ==
         (after.st_ino, after.st_size, after.st_mtime_ns), 'HOLD_BUILD_INPUT_CHANGED')
    return raw


def write(path, data, mode=0o600):
    path = plain(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Preserve timestamps of verified inputs: a bounded continuation must keep
    # Ninja's completed objects useful instead of recompiling the whole tree.
    if path.exists() and path.stat().st_size == len(data) and read(path, len(data)) == data:
        if stat.S_IMODE(path.stat().st_mode) != mode:
            path.chmod(mode)
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as f:
        os.fchmod(f.fileno(), mode)
        f.write(data)


def stop(root=ROOT):
    flags = [root / x for x in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')]
    flags.append(Path('/workspace/NOX_STOP'))
    need(not any(p.exists() or p.is_symlink() for p in flags), 'HOLD_OWNER_STOP')


def resource_snapshot(root=ROOT):
    cg = Path('/sys/fs/cgroup')
    cap, used = read(cg / 'memory.max', 128).strip(), int(read(cg / 'memory.current', 128))
    need(cap.isdigit(), 'HOLD_BUILD_CGROUP_LIMIT_UNKNOWN')
    fields = dict(x.split(':', 1) for x in read(Path('/proc/meminfo'), 65536).decode().splitlines() if ':' in x)
    available = int(fields['MemAvailable'].split()[0]) * 1024
    return {'disk_free_bytes': shutil.disk_usage(root).free, 'memory_max_bytes': int(cap),
            'memory_current_bytes': used, 'memory_headroom_bytes': min(available, max(0, int(cap) - used))}


def admit(snapshot):
    need(snapshot['disk_free_bytes'] >= DISK_RESERVE + DISK_MAX, 'HOLD_BUILD_DISK_ADMISSION')
    need(snapshot['memory_headroom_bytes'] >= RAM_RESERVE + BUILD_RSS_MAX, 'HOLD_BUILD_RAM_ADMISSION')


def usage(path):
    total = 0
    if path.exists():
        for base, dirs, files in os.walk(path, followlinks=False):
            for name in dirs + files:
                try:
                    s = (Path(base) / name).lstat()
                except FileNotFoundError:
                    continue
                if stat.S_ISREG(s.st_mode):
                    total += max(s.st_size, s.st_blocks * 512)
    return total


class Guard:
    def __init__(self, root, base):
        self.root, self.base = root, base
        self.deadline = time.monotonic() + WALL_SECONDS
        self.last_scan = 0.0
        self.peak_rss = 0

    def check(self, rss=0, full=False):
        stop(self.root)
        need(time.monotonic() < self.deadline, 'HOLD_BUILD_TIME_BUDGET_RESUMABLE')
        self.peak_rss = max(self.peak_rss, rss)
        need(rss <= BUILD_RSS_MAX, 'HOLD_BUILD_RSS_BUDGET')
        snap = resource_snapshot(self.root)
        need(snap['memory_headroom_bytes'] >= RAM_RESERVE, 'HOLD_BUILD_RAM_RESERVE')
        need(snap['disk_free_bytes'] >= DISK_RESERVE, 'HOLD_BUILD_DISK_RESERVE')
        if full or time.monotonic() - self.last_scan > 5:
            need(usage(self.base) <= DISK_MAX, 'HOLD_BUILD_DIRECTORY_BUDGET')
            self.last_scan = time.monotonic()


def owned_base(root):
    base = plain(root / 'engine_builds' / KEY)
    if base.exists():
        need(json.loads(read(base / '.owner.json', 16384)) == PLAN, 'HOLD_BUILD_UNOWNED_DIRECTORY')
    else:
        base.mkdir(mode=0o700, parents=True)
        write(base / '.owner.json', canonical(PLAN))
    s = base.stat()
    need(s.st_uid == os.geteuid() and stat.S_IMODE(s.st_mode) == 0o700, 'HOLD_BUILD_DIRECTORY_OWNER_MODE')
    return base


def relative(name):
    p = PurePosixPath(name)
    need(not p.is_absolute() and name and '\\' not in name and
         all(x not in ('', '.', '..', '.git') for x in name.split('/')) and
         not any(ord(x) < 32 for x in name), 'HOLD_BUILD_ARCHIVE_PATH')
    return p


def copy_source(root, base, guard):
    source = plain(root / 'engine_candidates/maya' / MAYA)
    raw = read(source / '.nox-tracked-sha256.json', 2 * 1024 ** 2)
    need(hashlib.sha256(raw).hexdigest() == SOURCE_MANIFEST_SHA, 'HOLD_BUILD_SOURCE_MANIFEST_PIN')
    manifest = json.loads(raw)
    need(manifest.get('commit') == MAYA and len(manifest.get('files', [])) == 1713 and
         not manifest.get('unfetched_submodules') and not manifest.get('lfs_pointer_files') and
         not manifest.get('symlinks_as_text'), 'HOLD_BUILD_SOURCE_FORMAT')
    total = 0
    for row in manifest['files']:
        guard.check()
        name = relative(row['path'])
        data = read(source / name, row['bytes'])
        need(len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'], 'HOLD_BUILD_SOURCE_BYTES')
        need(hashlib.sha1(('blob ' + str(len(data)) + '\0').encode() + data).hexdigest() == row['blob'],
             'HOLD_BUILD_SOURCE_BLOB_ID')
        total += len(data)
        need(total <= 64 * 1024 ** 2, 'HOLD_BUILD_SOURCE_BUDGET')
        dest = base / 'source' / name
        if not dest.exists() or read(dest, len(data)) != data:
            write(dest, data)
    return base / 'source'


class FixedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        need(newurl in {a['url'] for a in ARTIFACTS.values()}, 'HOLD_BUILD_UNPINNED_REDIRECT')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(base, name, guard):
    need(name in ARTIFACTS, 'HOLD_BUILD_ARTIFACT_ALLOWLIST')
    spec = ARTIFACTS[name]
    path = base / name
    if path.exists():
        data = read(path, spec['bytes'])
        if len(data) == spec['bytes'] and hashlib.sha256(data).hexdigest() == spec['sha256']:
            return path
    temp = plain(base / (name + '.part'))
    opener = urllib.request.build_opener(FixedRedirect())
    digest, count = hashlib.sha256(), 0
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as target, opener.open(spec['url'], timeout=10) as response:
        need(response.geturl() == spec['url'], 'HOLD_BUILD_ARTIFACT_URL')
        while True:
            guard.check()
            chunk = response.read(1024 ** 2)
            if not chunk:
                break
            count += len(chunk)
            need(count <= spec['bytes'], 'HOLD_BUILD_DOWNLOAD_BUDGET')
            target.write(chunk); digest.update(chunk)
    need(count == spec['bytes'] and digest.hexdigest() == spec['sha256'], 'HOLD_BUILD_ARTIFACT_SHA256')
    os.replace(temp, path)
    return path


def extract(base, name, archive, guard):
    spec = ARTIFACTS[name]
    target = base / ('llama' if name == 'llama.tar.gz' else 'cmake')
    total = 0
    if name == 'llama.tar.gz':
        with tarfile.open(archive, 'r:gz') as source:
            members = source.getmembers()
            need(len(members) <= spec['members_max'], 'HOLD_BUILD_ARCHIVE_MEMBERS')
            for item in members:
                guard.check()
                path = relative(item.name.rstrip('/'))
                need(path.parts[0] == 'llama.cpp-' + LLAMA and (item.isdir() or item.isfile()),
                     'HOLD_BUILD_TAR_TYPE_OR_ROOT')
                if item.isdir():
                    continue
                total += item.size
                need(total <= spec['expanded_max'], 'HOLD_BUILD_ARCHIVE_EXPANSION')
                dest = target.joinpath(*path.parts[1:])
                write(dest, source.extractfile(item).read(item.size + 1))
    else:
        with zipfile.ZipFile(archive) as source:
            members = source.infolist()
            need(len(members) <= spec['members_max'], 'HOLD_BUILD_ARCHIVE_MEMBERS')
            for item in members:
                guard.check()
                path = relative(item.filename.rstrip('/'))
                need(not stat.S_ISLNK(item.external_attr >> 16), 'HOLD_BUILD_ZIP_LINK')
                total += item.file_size
                need(total <= spec['expanded_max'], 'HOLD_BUILD_ARCHIVE_EXPANSION')
                if item.is_dir() or path.parts[:2] != ('cmake', 'data'):
                    continue
                write(target.joinpath(*path.parts[2:]), source.read(item),
                      0o700 if path.parts[2:3] == ('bin',) else 0o600)
    return target


def environment(base):
    return {'PATH': SAFE_PATH, 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'CUDA_VISIBLE_DEVICES': '',
            'CMAKE_BUILD_PARALLEL_LEVEL': '2', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
            'MKL_NUM_THREADS': '1', 'TMPDIR': str(base / 'tmp'), 'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_CONFIG_SYSTEM': '/dev/null', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0'}


def limits():
    os.nice(19)
    resource.setrlimit(resource.RLIMIT_AS, (PROCESS_AS_MAX, PROCESS_AS_MAX))
    resource.setrlimit(resource.RLIMIT_FSIZE, (GIB, GIB))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def session_rss(session):
    rss = 0
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            fields = (p / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[3]) == session:
                rss += int(fields[21]) * os.sysconf('SC_PAGE_SIZE')
        except (OSError, ValueError, IndexError):
            continue
    return rss


def run(argv, phase, base, guard):
    log = plain(base / (phase + '.log'))
    started = time.monotonic()
    with log.open('wb') as output:
        p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                             cwd=base, env=environment(base), start_new_session=True, preexec_fn=limits)
        try:
            while p.poll() is None:
                guard.check(session_rss(p.pid))
                need(log.stat().st_size <= 4 * 1024 ** 2, 'HOLD_BUILD_LOG_BUDGET')
                time.sleep(0.25)
        finally:
            # This Popen owns a new session. Also clean its remaining compiler children if
            # cmake/ninja exited first; no pre-existing service belongs to this session.
            if p.poll() is None or session_rss(p.pid):
                try:
                    os.killpg(p.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                if p.poll() is None or session_rss(p.pid):
                    try:
                        os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    p.wait(timeout=2)
    guard.check(full=True)
    raw = read(log, 4 * 1024 ** 2)
    need(p.returncode == 0, 'HOLD_BUILD_' + phase.upper() + '_FAILED')
    return {'phase': phase, 'returncode': p.returncode, 'seconds': round(time.monotonic() - started, 3),
            'log_sha256': hashlib.sha256(raw).hexdigest(), 'log_path': str(log)}


def commands(base):
    cmake = str(base / 'cmake/bin/cmake')
    configure = [cmake, '-S', str(base / 'source'), '-B', str(base / 'build'), '-G', 'Ninja',
        '-DCMAKE_MAKE_PROGRAM=/usr/bin/ninja', '-DCMAKE_BUILD_TYPE=Release', '-DSTRATA_ENABLE_CUDA=ON',
        '-DSTRATA_PORTABLE=ON', '-DSTRATA_BUILD_TESTS=OFF', '-DCMAKE_CUDA_ARCHITECTURES=70',
        '-DCMAKE_CUDA_COMPILER=' + str(CUDA / 'bin/nvcc'), '-DCUDAToolkit_ROOT=' + str(CUDA),
        '-DCMAKE_CXX_COMPILER=/usr/bin/g++', '-DCMAKE_C_COMPILER=/usr/bin/gcc',
        '-DCMAKE_CUDA_FLAGS=--threads=1', '-DSTRATA_GGML_DIR=' + str(base / 'llama'),
        '-DSTRATA_NATIVE_EXPERTS=ON', '-DFETCHCONTENT_FULLY_DISCONNECTED=ON', '-DMAYA_BUILD_ID=' + MAYA,
        '-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF', '-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF']
    return configure, [cmake, '--build', str(base / 'build'), '--target', 'maya-ds4', '--parallel', '2']


def binary_identity(path, guard):
    digest, count, prefix = hashlib.sha256(), 0, b''
    fd = os.open(plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        before = os.fstat(f.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_size <= GIB, 'HOLD_BUILD_BINARY_SIZE_TYPE')
        while True:
            guard.check()
            block = f.read(1024 ** 2)
            if not block:
                break
            if not prefix:
                prefix = block[:4]
            count += len(block); digest.update(block)
        after = os.fstat(f.fileno())
    need((before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)
         and count == before.st_size and prefix == b'\x7fELF' and count > 100000, 'HOLD_BUILD_BINARY_FORMAT')
    return {'binary': str(path), 'binary_bytes': count, 'binary_sha256': digest.hexdigest()}


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source_sha = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    need(re.fullmatch('[0-9]{1,20}', request) and re.fullmatch('[0-9a-f]{40}', source_sha), 'HOLD_OWNER_CONTEXT')
    stop()
    before = resource_snapshot(); admit(before)
    for p in (CUDA / 'bin/nvcc', CUDA / 'include/cuda_runtime.h', CUDA / 'include/cublas_v2.h',
              Path('/usr/bin/ninja'), Path('/usr/bin/g++'), Path('/usr/bin/gcc'), Path('/usr/bin/git')):
        need(p.is_file(), 'HOLD_BUILD_REQUIRED_TOOLCHAIN_FILE')
    cpu = read(Path('/proc/cpuinfo'), 2 * 1024 ** 2).decode()
    flags = set(next(x.split(':', 1)[1].split() for x in cpu.splitlines() if x.startswith('flags')))
    need({'avx2', 'fma', 'f16c', 'bmi2'} <= flags, 'HOLD_BUILD_PORTABLE_CPU_BASELINE')
    os.umask(0o077)
    base = owned_base(ROOT)
    lock = os.open(plain(base / '.build.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        guard = Guard(ROOT, base)
        result = {'schema': 'NOX_MAYA_BUILD_RECEIPT_V1', 'request': request, 'source_sha': source_sha,
                  'state': 'BUILDING', 'plan': PLAN, 'before': before, 'phases': [], 'inference_executed': False,
                  'installed': False, 'services_changed': False, 'training_changed': False, 'base': str(base),
                  'wall_limit_seconds': WALL_SECONDS, 'disk_max_bytes': DISK_MAX, 'disk_reserve_bytes': DISK_RESERVE,
                  'rss_watchdog_limit_bytes': BUILD_RSS_MAX, 'resource_poll_seconds': 0.25,
                  'per_process_address_space_limit_bytes': PROCESS_AS_MAX,
                  'memory_reserve_bytes': RAM_RESERVE, 'gpu_visible_to_build': False}
        try:
            copy_source(ROOT, base, guard)
            for name in ARTIFACTS:
                extract(base, name, download(base, name, guard), guard)
            (base / 'tmp').mkdir(mode=0o700, exist_ok=True)
            result['phases'].append(run([str(CUDA / 'bin/nvcc'), '--version'], 'nvcc-version', base, guard))
            result['phases'].append(run([str(base / 'cmake/bin/cmake'), '--version'], 'cmake-version', base, guard))
            for phase, argv in zip(('configure', 'compile'), commands(base)):
                result['active_phase'] = phase
                print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'maya_build_phase', 'data': {'phase': phase, 'request': request}}), flush=True)
                result['phases'].append(run(argv, phase, base, guard))
            binary = base / 'build/maya-ds4'
            result.update(state='BUILT_NOT_LOADED_OR_RUNTIME_VALIDATED', **binary_identity(binary, guard))
        except Exception as exc:
            result.update(state=str(exc) if isinstance(exc, Hold) else 'HOLD_BUILD_' + type(exc).__name__,
                          resumable_owned_directory=True)
            phase = result.get('active_phase')
            if phase in ('configure', 'compile'):
                log = plain(base / (phase + '.log'))
                if log.is_file():
                    with log.open('rb') as f:
                        f.seek(max(0, log.stat().st_size - 8192))
                        result['failure_log_tail'] = f.read(8192).decode('utf-8', 'replace')
        result.update(peak_build_rss_bytes=guard.peak_rss, directory_bytes=usage(base), finished_at_epoch=time.time())
        receipt = base / ('receipt-' + request + '.json')
        write(receipt, canonical(result))
        result['receipt_path'] = str(receipt)
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'maya_build_receipt', 'data': result}, separators=(',', ':')), flush=True)
        good = result['state'] == 'BUILT_NOT_LOADED_OR_RUNTIME_VALIDATED'
        if good:
            print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
        return 0 if good else 2
    finally:
        os.close(lock)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'maya_build_hold', 'data': {
            'state': str(exc) if isinstance(exc, Hold) else 'HOLD_BUILD_' + type(exc).__name__}}), flush=True)
        raise SystemExit(2)
