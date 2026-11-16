#!/usr/bin/env python3
"""Stage pinned public engine sources; never install, build, or start them."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time

ROOT = Path('/root/nox')
MANIFEST = 'coordination/NOX_ENGINE_STACK_20261116/engine_sources.json'
GIB = 1024 ** 3
RESERVE = 8 * GIB
MAX_WORKERS = 6
SAFE_PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
OWNER_FILE = '.nox-download-owner.json'
HASH_FILE = '.nox-tracked-sha256.json'
ATTRIBUTES = b'* -text -eol -ident -filter -working-tree-encoding\n'
CONFIG = b'[core]\n repositoryformatversion = 0\n bare = false\n filemode = true\n symlinks = false\n logallrefupdates = false\n hooksPath = /dev/null\n[gc]\n auto = 0\n[maintenance]\n auto = false\n'
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}
PRINT_LOCK = threading.Lock()


class Hold(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Hold(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def emit(kind, data):
    with PRINT_LOCK:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': data}, separators=(',', ':')), flush=True)


def check_stop(root=ROOT):
    flags = [root / name for name in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')]
    flags.append(Path('/workspace/NOX_STOP'))
    require(not any(p.exists() or p.is_symlink() for p in flags), 'HOLD_OWNER_STOP')


def plain(path):
    path = Path(os.path.abspath(path))
    require(not any(p.is_symlink() for p in (*path.parents, path)), 'HOLD_ENGINE_SYMLINK_PATH')
    return path


def directory(path):
    path = plain(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o077,
            'HOLD_ENGINE_PRIVATE_DIRECTORY')
    return path


def read_regular(path, limit):
    fd = os.open(plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and before.st_size <= limit,
                'HOLD_ENGINE_FILE')
        value = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    require(len(value) <= limit and (before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_ino, after.st_size, after.st_mtime_ns), 'HOLD_ENGINE_FILE_CHANGED')
    return value


def hash_regular(path, size, root, blob):
    """Hash tracked bytes with bounded RAM, checking STOP between chunks."""
    fd = os.open(plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    digest, count, prefix = hashlib.sha256(), 0, b''
    git_digest = hashlib.sha1(('blob ' + str(size) + '\0').encode())
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and before.st_size == size,
                'HOLD_ENGINE_TRACKED_SIZE_CHANGED')
        while True:
            check_stop(root)
            chunk = stream.read(1024 ** 2)
            if not chunk:
                break
            if not prefix:
                prefix = chunk[:64]
            count += len(chunk)
            require(count <= size, 'HOLD_ENGINE_TRACKED_SIZE_CHANGED')
            digest.update(chunk)
            git_digest.update(chunk)
        after = os.fstat(stream.fileno())
    require(count == size and (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'HOLD_ENGINE_FILE_CHANGED')
    require(git_digest.hexdigest() == blob, 'HOLD_ENGINE_BLOB_ID_MISMATCH')
    return digest.hexdigest(), prefix.startswith(b'version https://git-lfs.github.com/spec/v1\n')


def atomic(path, value):
    path = plain(path)
    if path.exists():
        read_regular(path, 16 * 1024 ** 2)
    fd, temp = tempfile.mkstemp(prefix='.nox-write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        require(read_regular(path, len(value)) == value, 'HOLD_ENGINE_WRITE_READBACK')
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def validate_manifest(raw):
    require(len(raw) <= 131072, 'HOLD_ENGINE_MANIFEST_SIZE')
    value = json.loads(raw)
    require(isinstance(value, dict) and set(value) == {'schema', 'sources'} and
            value['schema'] == 'NOX_ENGINE_SOURCES_V1', 'HOLD_ENGINE_MANIFEST_SCHEMA')
    sources = value['sources']
    require(isinstance(sources, list) and 1 <= len(sources) <= 24, 'HOLD_ENGINE_SOURCE_COUNT')
    seen = set()
    for row in sources:
        require(isinstance(row, dict) and set(row) == {'name', 'repo', 'commit', 'source_max_bytes', 'git_max_bytes'},
                'HOLD_ENGINE_SOURCE_FIELDS')
        require(isinstance(row['name'], str) and len(row['name']) <= 48 and
                re.fullmatch(r'[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)?', row['name']) and row['name'] not in seen,
                'HOLD_ENGINE_NAME')
        seen.add(row['name'])
        require(isinstance(row['repo'], str) and
                re.fullmatch(r'https://github\.com/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\.git', row['repo']) and
                '..' not in row['repo'], 'HOLD_ENGINE_REPOSITORY_ALLOWLIST')
        require(isinstance(row['commit'], str) and re.fullmatch('[0-9a-f]{40}', row['commit']) and
                row['commit'] != '0' * 40, 'HOLD_ENGINE_COMMIT_PIN')
        for key in ('source_max_bytes', 'git_max_bytes'):
            require(type(row[key]) is int and 1 <= row[key] <= GIB, 'HOLD_ENGINE_SOURCE_BUDGET')
    return sources


def load_manifest():
    if 'engine_sources.json' in BUNDLE:
        raw = base64.b64decode(BUNDLE['engine_sources.json'], validate=True)
    else:
        raw = read_regular(Path(__file__).resolve().parents[1] / MANIFEST, 131072)
    return raw, validate_manifest(raw)


def usage(path):
    logical = allocated = 0
    if not path.exists():
        return logical, allocated
    for base, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            item = Path(base) / name
            try:
                info = item.lstat()
            except FileNotFoundError:
                continue  # Git atomically renames temporary pack/index files; check again after exit.
            require(not stat.S_ISLNK(info.st_mode), 'HOLD_ENGINE_TREE_SYMLINK')
            require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), 'HOLD_ENGINE_TREE_TYPE')
            allocated += info.st_blocks * 512
            if stat.S_ISREG(info.st_mode):
                logical += info.st_size
    return logical, allocated


class Budget:
    def __init__(self, base):
        self.base = base
        self.lock = threading.Lock()
        self.reserved = {}

    def acquire(self, row):
        amount = row['source_max_bytes'] + row['git_max_bytes'] + 16 * 1024 ** 2
        with self.lock:
            require(shutil.disk_usage(self.base).free >= RESERVE + sum(self.reserved.values()) + amount,
                    'HOLD_ENGINE_DISK_ADMISSION')
            self.reserved[row['name']] = amount

    def release(self, row):
        with self.lock:
            self.reserved.pop(row['name'], None)

    def check(self, path, row):
        require(shutil.disk_usage(self.base).free >= RESERVE, 'HOLD_ENGINE_DISK_RESERVE')
        git_bytes, _ = usage(path / '.git')
        require(git_bytes <= row['git_max_bytes'], 'HOLD_ENGINE_GIT_BUDGET')
        total, _ = usage(path)
        require(total - git_bytes <= row['source_max_bytes'] + 16 * 1024 ** 2,
                'HOLD_ENGINE_SOURCE_BUDGET')


def environment():
    return {'PATH': SAFE_PATH, 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_SYSTEM': '/dev/null', 'GIT_CONFIG_GLOBAL': '/dev/null',
            'GIT_TERMINAL_PROMPT': '0', 'GIT_LFS_SKIP_SMUDGE': '1', 'GIT_NO_REPLACE_OBJECTS': '1',
            'GIT_ALLOW_PROTOCOL': 'https', 'GIT_OPTIONAL_LOCKS': '0', 'OMP_NUM_THREADS': '1'}


def git_argv(path, args):
    require(args and args[0] in {'init', 'fetch', 'checkout', 'rev-parse', 'fsck', 'ls-tree', 'diff'},
            'HOLD_ENGINE_GIT_COMMAND')
    git = shutil.which('git', path=SAFE_PATH)
    require(git is not None, 'HOLD_ENGINE_GIT_UNAVAILABLE')
    settings = ('core.hooksPath=/dev/null', 'core.symlinks=false', 'credential.helper=',
                'http.followRedirects=false', 'protocol.allow=never', 'protocol.https.allow=always',
                'submodule.recurse=false', 'filter.lfs.required=false', 'filter.lfs.process=',
                'filter.lfs.smudge=', 'filter.lfs.clean=', 'gc.auto=0', 'maintenance.auto=false',
                'pack.threads=1', 'index.threads=1', 'http.lowSpeedLimit=1', 'http.lowSpeedTime=45')
    return [git, *[item for setting in settings for item in ('-c', setting)], '-C', str(path), *args]


def run_git(path, args, row, budget, root=ROOT, timeout=240):
    check_stop(root)
    budget.check(path, row)
    started = time.monotonic()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(git_argv(path, args), stdout=out, stderr=err,
                                stdin=subprocess.DEVNULL, env=environment(), start_new_session=True)
        try:
            last_check = 0
            while proc.poll() is None:
                check_stop(root)
                now = time.monotonic()
                require(now - started < timeout, 'HOLD_ENGINE_GIT_TIMEOUT')
                require(os.fstat(out.fileno()).st_size <= 16 * 1024 ** 2 and
                        os.fstat(err.fileno()).st_size <= 1024 ** 2, 'HOLD_ENGINE_GIT_OUTPUT_LIMIT')
                if now - last_check >= 0.4:
                    budget.check(path, row)
                    last_check = now
                time.sleep(0.1)
            require(proc.returncode == 0, 'HOLD_ENGINE_GIT_' + args[0].replace('-', '_').upper())
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=2)
        check_stop(root)
        budget.check(path, row)
        out.seek(0)
        value = out.read(16 * 1024 ** 2 + 1)
        require(len(value) <= 16 * 1024 ** 2, 'HOLD_ENGINE_GIT_OUTPUT_LIMIT')
        return value


def source_tree(raw, row):
    entries, total = [], 0
    for record in raw.split(b'\0'):
        if not record:
            continue
        meta, name = record.split(b'\t', 1)
        mode, kind, blob, size = meta.split()
        path = name.decode('utf-8')
        parts = path.split('/')
        require(parts and not PurePosixPath(path).is_absolute() and len(path) <= 2048 and
                all(p not in ('', '..', '.', '.git') for p in parts) and path not in (OWNER_FILE, HASH_FILE),
                'HOLD_ENGINE_TRACKED_PATH')
        require(mode in (b'100644', b'100755', b'120000', b'160000'), 'HOLD_ENGINE_TRACKED_MODE')
        require(kind == (b'commit' if mode == b'160000' else b'blob') and re.fullmatch(b'[0-9a-f]{40}', blob),
                'HOLD_ENGINE_TRACKED_OBJECT')
        length = 0 if mode == b'160000' else int(size)
        require(length >= 0, 'HOLD_ENGINE_TRACKED_SIZE')
        total += length
        require(total <= row['source_max_bytes'] and len(entries) < 100000, 'HOLD_ENGINE_SOURCE_BUDGET')
        entries.append({'path': path, 'mode': mode.decode(), 'blob': blob.decode(), 'bytes': length})
    require(entries, 'HOLD_ENGINE_EMPTY_TREE')
    return entries


def owner_matches(path, row):
    marker = json.loads(read_regular(path / OWNER_FILE, 16384))
    require(marker.get('schema') == 'NOX_ENGINE_DOWNLOAD_OWNER_V1' and
            all(marker.get(k) == row[k] for k in ('name', 'repo', 'commit')), 'HOLD_ENGINE_UNOWNED_PATH')
    return marker


def quarantine_partial(path, row, request):
    plain(path)
    owner_matches(path, row)
    target = plain(path.with_name(path.name + '.quarantine.' + request))
    require(not target.exists(), 'HOLD_ENGINE_QUARANTINE_EXISTS')
    path.rename(target)
    return str(target)


def verify_source(path, row, budget, root):
    owner_matches(path, row)
    require(read_regular(path / '.git/config', 16384) == CONFIG, 'HOLD_ENGINE_GIT_CONFIG')
    attributes = path / '.git/info/attributes'
    if attributes.exists() or attributes.is_symlink():
        require(read_regular(attributes, 1024) == ATTRIBUTES, 'HOLD_ENGINE_GIT_ATTRIBUTES')
    for forbidden in ('objects/info/alternates', 'info/grafts', 'config.worktree'):
        require(not (path / '.git' / forbidden).exists(), 'HOLD_ENGINE_GIT_EXTERNAL_STATE')
    head = run_git(path, ['rev-parse', 'HEAD'], row, budget, root).decode().strip()
    require(head == row['commit'], 'HOLD_ENGINE_HEAD_MISMATCH')
    run_git(path, ['fsck', '--full', '--no-dangling'], row, budget, root)
    entries = source_tree(run_git(path, ['ls-tree', '-r', '-z', '-l', 'HEAD'], row, budget, root), row)
    run_git(path, ['diff', '--quiet', '--no-ext-diff', '--no-textconv', '--ignore-submodules=all', 'HEAD', '--'], row, budget, root)
    hashes, submodules, links, lfs = [], [], 0, 0
    for entry in entries:
        check_stop(root)
        if entry['mode'] == '160000':
            submodules.append({'path': entry['path'], 'commit': entry['blob']})
            continue
        digest, is_lfs = hash_regular(path / entry['path'], entry['bytes'], root, entry['blob'])
        item = dict(entry, sha256=digest)
        if entry['mode'] == '120000':
            links += 1  # core.symlinks=false stores link target as inert text.
        lfs += int(is_lfs)
        hashes.append(item)
    raw = canonical({'schema': 'NOX_ENGINE_TRACKED_SHA256_V1', 'commit': head, 'files': hashes,
                     'unfetched_submodules': submodules, 'symlinks_as_text': links, 'lfs_pointer_files': lfs})
    return raw, {'head': head, 'git_fsck_passed': True, 'tracked_files': len(hashes),
                 'canonical_git_blob_ids_verified': True,
                 'tracked_source_bytes': sum(x['bytes'] for x in hashes), 'submodules_fetched': False,
                 'unfetched_submodules': submodules, 'symlinks_as_text': links, 'lfs_pointer_files': lfs,
                 'tracked_manifest_sha256': hashlib.sha256(raw).hexdigest()}


def stage_one(row, request, manifest_sha, budget, root=ROOT):
    started = time.monotonic()
    check_stop(root)
    parent = directory(root / 'engine_candidates' / row['name'])
    target, partial = parent / row['commit'], parent / (row['commit'] + '.partial')
    budget.acquire(row)
    quarantined = None
    try:
        if target.exists() or target.is_symlink():
            plain(target)
            raw, evidence = verify_source(target, row, budget, root)
            require(read_regular(target / HASH_FILE, 16 * 1024 ** 2) == raw, 'HOLD_ENGINE_EXISTING_MANIFEST_CHANGED')
            state = 'REUSED_AND_SHA_VERIFIED'
        else:
            if partial.exists() or partial.is_symlink():
                quarantined = quarantine_partial(partial, row, request)
            directory(partial)
            atomic(partial / OWNER_FILE, canonical(dict(schema='NOX_ENGINE_DOWNLOAD_OWNER_V1', request=request,
                   manifest_sha256=manifest_sha, **{k: row[k] for k in ('name', 'repo', 'commit')})))
            run_git(partial, ['init', '--quiet', '--template='], row, budget, root)
            atomic(partial / '.git/config', CONFIG)
            directory(partial / '.git/info')
            atomic(partial / '.git/info/attributes', ATTRIBUTES)  # Stage canonical blob bytes, without checkout conversion.
            run_git(partial, ['fetch', '--depth=1', '--no-tags', '--no-recurse-submodules', '--no-write-fetch-head',
                             row['repo'], row['commit']], row, budget, root)
            source_tree(run_git(partial, ['ls-tree', '-r', '-z', '-l', row['commit']], row, budget, root), row)
            run_git(partial, ['checkout', '--quiet', '--detach', '--no-recurse-submodules', row['commit']], row, budget, root)
            raw, evidence = verify_source(partial, row, budget, root)
            atomic(partial / HASH_FILE, raw)
            check_stop(root)
            require(not target.exists(), 'HOLD_ENGINE_DESTINATION_RACE')
            partial.rename(target)
            require(read_regular(target / HASH_FILE, len(raw)) == raw, 'HOLD_ENGINE_FINAL_READBACK')
            state = 'DOWNLOADED_AND_SHA_VERIFIED'
        logical, allocated = usage(target)
        return dict(name=row['name'], repo=row['repo'], commit=row['commit'], path=str(target), state=state,
                    seconds=round(time.monotonic()-started, 3), du_allocated_bytes=allocated,
                    logical_checkout_and_git_bytes=logical, quarantined_partial=quarantined,
                    installed=False, built=False, executed=False, **evidence)
    finally:
        budget.release(row)


def native_metadata(root=ROOT):
    commands = {'gpus': ('nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader,nounits'),
                'cuda_compiler': ('nvcc', '--version'), 'rclone': ('rclone', 'version')}
    result = {'free_ssd_bytes': shutil.disk_usage(root).free, 'dev_fuse_exists': Path('/dev/fuse').exists()}
    for key in ('memory.max', 'memory.current'):
        path = Path('/sys/fs/cgroup') / key
        try:
            result[key] = path.read_text()[:128].strip()
        except OSError:
            result[key] = None
    for name, argv in commands.items():
        executable = shutil.which(argv[0], path=SAFE_PATH)
        row = {'path': executable, 'available': bool(executable)}
        if executable:
            try:
                proc = subprocess.run([executable, *argv[1:]], stdin=subprocess.DEVNULL, capture_output=True,
                                      timeout=8, env=environment())
                row.update(returncode=proc.returncode, output=proc.stdout.decode('utf-8', 'replace')[:4096])
            except subprocess.TimeoutExpired:
                row['state'] = 'READ_ONLY_PROBE_TIMEOUT'
        result[name] = row
    return result


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,20}', request) and re.fullmatch('[0-9a-f]{40}', source), 'HOLD_OWNER_CONTEXT')
    raw, rows = load_manifest()
    check_stop(ROOT)
    os.umask(0o077)
    base = directory(ROOT / 'engine_candidates')
    state = directory(ROOT / 'state/owner_engine_download')
    fd = os.open(plain(state / 'download.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt = state / (request + '.json')
        require(not receipt.exists(), 'HOLD_ENGINE_REQUEST_ALREADY_RECORDED')
        result = {'schema': 'NOX_ENGINE_DOWNLOAD_RECEIPT_V1', 'request': request, 'source_sha': source,
                  'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'started_at': time.time(),
                  'state': 'DOWNLOADING_SOURCES', 'maximum_parallel_downloads': MAX_WORKERS, 'results': [],
                  'services_changed': False, 'model_restarted': False, 'training_started': False,
                  'installed': False, 'built': False, 'submodules_fetched': False, 'lfs_downloaded': False,
                  'native_before': native_metadata(ROOT)}
        atomic(receipt, canonical(result))
        budget = Budget(base)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix='nox-engine-download') as pool:
            futures = {pool.submit(stage_one, row, request, result['manifest_sha256'], budget, ROOT): row for row in rows}
            for future in as_completed(futures):
                row = futures[future]
                try:
                    item = future.result()
                except Exception as exc:
                    item = {'name': row['name'], 'commit': row['commit'], 'state': 'HOLD',
                            'reason': str(exc) if isinstance(exc, Hold) else type(exc).__name__}
                result['results'].append(item)
                atomic(receipt, canonical(result))
                emit('engine_source_result', item)
        success = len(result['results']) == len(rows) and all(x['state'] in
                  ('DOWNLOADED_AND_SHA_VERIFIED', 'REUSED_AND_SHA_VERIFIED') for x in result['results'])
        try:
            check_stop(ROOT)
        except Hold:
            success = False
            result['stop_observed_at_completion'] = True
        result.update(state='SOURCES_STAGED_NOT_INSTALLED' if success else 'HOLD_PARTIAL_DOWNLOAD',
                      finished_at=time.time(), free_ssd_after_bytes=shutil.disk_usage(ROOT).free)
        atomic(receipt, canonical(result))
        emit('engine_download_receipt', dict(result, receipt_path=str(receipt),
             receipt_sha256=hashlib.sha256(read_regular(receipt, 16 * 1024 ** 2)).hexdigest()))
        if success:
            print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
        return 0 if success else 2
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit('engine_download_hold', {'reason': str(exc) if isinstance(exc, Hold) else type(exc).__name__})
        raise SystemExit(2)
