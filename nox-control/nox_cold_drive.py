#!/usr/bin/env python3
"""NOX cold storage: copy, streaming SHA readback, receipt, optional exact eviction.
Uses only an existing rclone remote. No daemon, credentials, GPU or trainer changes.
Batch transfers use at most six OS processes. Deletion is serial and opt-in.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import time

GIB = 1024 ** 3
BLOCKED_PARTS = {'s03', 'checkpoint', 'checkpoints', 'optimizer', 'training', 'sqlite', 'database', 'db', 'genesis'}
ALLOWED_SUFFIX = {'.safetensors', '.gguf', '.bin', '.pt', '.pth'}
SHA = re.compile(r'^[0-9a-f]{64}$')


def plain_path(value, must_exist=True):
    p = Path(os.path.abspath(value))
    for part in [*reversed(p.parents), p]:
        if part.is_symlink():
            raise ValueError('HOLD_SYMLINK_PATH')
    if must_exist:
        p.stat()
    return p


def assert_model(value):
    p = plain_path(value)
    s = p.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_size <= 0 or p.suffix.lower() not in ALLOWED_SUFFIX:
        raise ValueError('HOLD_NOT_REGULAR_MODEL')
    if any(x.lower() in BLOCKED_PARTS or x.lower().startswith('checkpoint-') for x in p.parts):
        raise ValueError('HOLD_PROTECTED_PATH')
    if re.match(r'^(optimizer|scheduler|scaler|rng_state|training_args)([._-]|$)', p.name.lower()):
        raise ValueError('HOLD_PROTECTED_TRAINING_STATE')
    if s.st_nlink != 1:
        raise ValueError('HOLD_HARDLINK_MODEL')
    return p


def identity(p):
    s = p.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def assert_remote(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}:[^\x00-\x1f\x7f]+', value):
        raise ValueError('HOLD_CONFIGURED_REMOTE_REQUIRED')
    if '..' in value.split(':', 1)[1].split('/') or '?' in value or '#' in value:
        raise ValueError('HOLD_REMOTE_PATH')
    return value.rstrip('/')


def command(args, timeout=3600):
    # Suppress provider stderr; it can contain signed URLs or credentials.
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError('HOLD_TRANSFER_TIMEOUT') from None
    if p.returncode:
        raise RuntimeError('HOLD_RCLONE_EXIT_' + str(p.returncode))
    return p.stdout


def stream_sha256(remote, size, timeout=3600):
    """Hash the full remote stream with bounded memory, no model-sized SSD copy."""
    digest, count = hashlib.sha256(), 0
    deadline = time.monotonic() + timeout
    p = subprocess.Popen(['rclone', 'cat', remote, '--retries', '2', '--low-level-retries', '2'],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(p.stdout, selectors.EVENT_READ, True)
            sel.register(p.stderr, selectors.EVENT_READ, False)
            while sel.get_map():
                left = deadline - time.monotonic()
                if left <= 0:
                    raise RuntimeError('HOLD_READBACK_TIMEOUT')
                for key, _ in sel.select(min(left, 1.0)):
                    chunk = os.read(key.fd, 1024 * 1024)
                    if not chunk:
                        sel.unregister(key.fileobj)
                    elif key.data:
                        count += len(chunk)
                        if count > size:
                            raise RuntimeError('HOLD_READBACK_OVERSIZE')
                        digest.update(chunk)
        if p.wait(timeout=max(0.1, deadline-time.monotonic())) != 0 or count != size:
            raise RuntimeError('HOLD_READBACK_INCOMPLETE')
        return digest.hexdigest()
    finally:
        if p.poll() is None:
            p.kill()
        p.wait()
        p.stdout.close()
        p.stderr.close()


def atomic_json(path, obj):
    path = plain_path(path, False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.nox-receipt-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
        d = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(d)
        finally:
            os.close(d)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def maintenance_lock(root):
    import fcntl
    root = plain_path(root, False)
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(root/'.cold-storage.lock', os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('HOLD_STORAGE_WRITER_BUSY') from None
        yield
    finally:
        os.close(fd)


def copy_verified(job):
    src = assert_model(job['source'])
    before, digest = identity(src), sha256(src)
    expected = job.get('sha256')
    if expected is not None and (not SHA.fullmatch(expected) or digest != expected):
        raise ValueError('HOLD_SOURCE_SHA_MISMATCH')
    dest = assert_remote(job['remote']) + '/' + digest + '/' + src.name
    command(['rclone','copyto',str(src),dest,'--immutable','--retries','3',
             '--transfers','1','--checkers','1','--multi-thread-streams','1'], job['timeout'])
    if stream_sha256(dest, before[2], job['timeout']) != digest:
        raise RuntimeError('HOLD_REMOTE_SHA_MISMATCH')
    if assert_model(src) != src or identity(src) != before:
        raise RuntimeError('HOLD_SOURCE_CHANGED_DURING_TRANSFER')
    rid = hashlib.sha256(str(src).encode()).hexdigest()[:16] + '-' + digest
    dest_receipt = Path(job['receipt_dir'])/(rid+'.json')
    row = {'schema_version':2,'source':str(src),'destination':dest,'size':before[2],
           'sha256':digest,'identity':before,'readback_verified':True,
           'verified_at':time.time(),'source_deleted':False,'worker_pid':os.getpid()}
    atomic_json(dest_receipt, row)
    return {'receipt':str(dest_receipt), **row}


def fresh_manifest(path, source):
    p = plain_path(path)
    if p.stat().st_size > 1024*1024:
        raise ValueError('HOLD_ACTIVE_MANIFEST_TOO_LARGE')
    obj = json.loads(p.read_text())
    ts = obj.get('generated_at')
    if type(ts) not in (int,float) or not math.isfinite(ts) or not -5 <= time.time()-ts <= 300:
        raise ValueError('HOLD_ACTIVE_MANIFEST_STALE')
    for name in ('active_paths','protected_paths','evict_paths'):
        if not isinstance(obj.get(name),list) or any(not isinstance(v,str) for v in obj[name]):
            raise ValueError('HOLD_ACTIVE_MANIFEST_SCHEMA')
    src = source.resolve()
    for value in obj['active_paths'] + obj['protected_paths']:
        p = Path(value).resolve()
        if src == p or p in src.parents:
            raise ValueError('HOLD_ACTIVE_OR_PROTECTED_MODEL')
    if str(src) not in {str(Path(v).resolve()) for v in obj['evict_paths']}:
        raise ValueError('HOLD_NOT_EXPLICITLY_EVICTABLE')


def assert_not_open(source):
    target, proc = str(source), Path('/proc')
    if not proc.is_dir():
        raise RuntimeError('HOLD_NATIVE_PROCESS_INSPECTION_UNAVAILABLE')
    for pid in proc.iterdir():
        if not pid.name.isdigit():
            continue
        try:
            for link in (pid/'fd').iterdir():
                try:
                    if os.readlink(link).removesuffix(' (deleted)') == target:
                        raise RuntimeError('HOLD_MODEL_OPEN_BY_PROCESS')
                except FileNotFoundError:
                    pass
            for line in (pid/'maps').read_text(errors='replace').splitlines():
                fields = line.split(maxsplit=5)
                if len(fields)==6 and fields[-1].removesuffix(' (deleted)')==target:
                    raise RuntimeError('HOLD_MODEL_MEMORY_MAPPED')
        except (FileNotFoundError,ProcessLookupError):
            continue
        except PermissionError:
            raise RuntimeError('HOLD_PROCESS_SCAN_PERMISSION') from None


def evict_verified(row, active_manifest):
    if not active_manifest:
        raise ValueError('HOLD_ACTIVE_MANIFEST_REQUIRED')
    src = assert_model(row['source'])
    fresh_manifest(active_manifest, src)
    if identity(src)!=row['identity'] or sha256(src)!=row['sha256']:
        raise RuntimeError('HOLD_SOURCE_CHANGED_BEFORE_EVICTION')
    assert_not_open(src)
    fresh_manifest(active_manifest, src)
    if identity(src)!=row['identity']:
        raise RuntimeError('HOLD_SOURCE_CHANGED_BEFORE_UNLINK')
    before, allocated = shutil.disk_usage(src.parent).free, src.stat().st_blocks*512
    src.unlink()  # One exact verified regular file; never recursive deletion.
    row.update(source_deleted=True, source_logical_bytes_removed=row['size'],
               source_allocated_bytes=allocated,
               observed_free_bytes_delta=shutil.disk_usage(src.parent).free-before)
    atomic_json(Path(row['receipt']), {k:v for k,v in row.items() if k!='receipt'})
    return row


def upload(a):
    if a.evict and not a.active_manifest:
        raise ValueError('HOLD_ACTIVE_MANIFEST_REQUIRED')
    with maintenance_lock(a.receipt_dir):
        row=copy_verified({'source':a.file,'remote':a.remote,'receipt_dir':a.receipt_dir,
                           'timeout':a.timeout,'sha256':a.sha256})
        if a.evict:
            evict_verified(row,a.active_manifest)
        print(json.dumps(row,ensure_ascii=False))


def batch(a):
    p=plain_path(a.manifest)
    if p.stat().st_size > 1024*1024:
        raise ValueError('HOLD_BATCH_TOO_LARGE')
    rows=json.loads(p.read_text()).get('files')
    if not isinstance(rows,list) or not 1<=len(rows)<=4096:
        raise ValueError('HOLD_BATCH_SCHEMA')
    jobs=[]
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'path','sha256'} or not SHA.fullmatch(str(row['sha256'])):
            raise ValueError('HOLD_BATCH_FILE_SCHEMA')
        jobs.append({'source':str(assert_model(row['path'])),'sha256':row['sha256'],
                     'remote':assert_remote(a.remote),'receipt_dir':a.receipt_dir,'timeout':a.timeout})
    if len({j['source'] for j in jobs}) != len(jobs):
        raise ValueError('HOLD_DUPLICATE_BATCH_SOURCE')
    if a.evict and not a.active_manifest:
        raise ValueError('HOLD_ACTIVE_MANIFEST_REQUIRED')
    with maintenance_lock(a.receipt_dir):
        done, errors = [], []
        with ProcessPoolExecutor(max_workers=a.workers) as pool:
            pending={pool.submit(copy_verified,j):j for j in jobs}
            for future in as_completed(pending):
                try:
                    done.append(future.result())
                except Exception as ex:
                    errors.append({'source':pending[future]['source'],'error':type(ex).__name__})
        summary={'requested':len(jobs),'copies_verified':len(done),'errors':errors,
                 'sources_deleted':0,'receipts':[r['receipt'] for r in done]}
        atomic_json(Path(a.receipt_dir)/'last-batch.json',summary)
        if errors:
            raise RuntimeError('HOLD_BATCH_INCOMPLETE_SOURCES_RETAINED')
        if a.evict:
            for row in done:
                evict_verified(row,a.active_manifest)
                summary['sources_deleted']+=1
                atomic_json(Path(a.receipt_dir)/'last-batch.json',summary)
        print(json.dumps(summary,ensure_ascii=False))


def memory_budget(dest_dir, reserve_gib):
    fields=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    available=int(fields['MemAvailable'].split()[0])*1024
    root=Path('/sys/fs/cgroup')
    if (root/'memory.max').is_file():
        cap=(root/'memory.max').read_text().strip()
        used=int((root/'memory.current').read_text())
        if cap!='max':
            available=min(available,max(0,int(cap)-used))
    elif (root/'memory/memory.limit_in_bytes').is_file():
        cap=int((root/'memory/memory.limit_in_bytes').read_text())
        used=int((root/'memory/memory.usage_in_bytes').read_text())
        available=min(available,max(0,cap-used))
    else:
        raise RuntimeError('HOLD_CGROUP_MEMORY_LIMIT_UNKNOWN')
    return min(available,shutil.disk_usage(dest_dir).free)-reserve_gib*GIB


def load(a):
    remote=assert_remote(a.remote)
    if not SHA.fullmatch(a.sha256):
        raise ValueError('HOLD_EXPECTED_SHA_REQUIRED')
    dest_dir=plain_path(a.ram_dir)
    if not dest_dir.is_dir() or not dest_dir.is_relative_to(Path('/dev/shm')):
        raise ValueError('HOLD_RAM_PATH_REQUIRED')
    name=remote.rsplit('/',1)[-1]
    if '/' not in remote.split(':',1)[1] or Path(name).suffix.lower() not in ALLOWED_SUFFIX:
        raise ValueError('HOLD_REMOTE_MODEL_FILE_REQUIRED')
    meta=json.loads(command(['rclone','size','--json',remote],a.timeout))
    size=meta.get('bytes',0)
    if type(size) is not int or size<=0 or meta.get('count')!=1:
        raise ValueError('HOLD_REMOTE_NOT_ONE_FILE')
    with maintenance_lock(dest_dir):
        if memory_budget(dest_dir,a.reserve_gib)<size:
            raise RuntimeError('HOLD_RAM_RESERVE')
        dest=dest_dir/name
        if os.path.lexists(dest):
            raise FileExistsError('HOLD_RAM_DESTINATION_EXISTS')
        fd,tmp=tempfile.mkstemp(prefix='.nox-load-',dir=dest_dir)
        os.close(fd); temp=Path(tmp)
        try:
            command(['rclone','copyto',remote,str(temp),'--transfers','1','--multi-thread-streams','1'],a.timeout)
            if temp.stat().st_size!=size or sha256(temp)!=a.sha256:
                raise RuntimeError('HOLD_RAM_SHA_MISMATCH')
            with temp.open('rb') as f:
                os.fsync(f.fileno())
            os.link(temp,dest)  # Atomic no-replace publication, not destructive rename.
            print(json.dumps({'ram_model':str(dest),'bytes':size,'sha256':a.sha256}))
        finally:
            temp.unlink(missing_ok=True)


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    sp=p.add_subparsers(dest='action',required=True)
    for name in ('upload','batch'):
        q=sp.add_parser(name)
        q.add_argument('--file' if name=='upload' else '--manifest',required=True)
        q.add_argument('--remote',required=True)
        q.add_argument('--receipt-dir',default='./cold_receipts')
        q.add_argument('--active-manifest'); q.add_argument('--evict',action='store_true')
        q.add_argument('--timeout',type=int,default=3600)
        if name=='upload':
            q.add_argument('--sha256')
        else:
            q.add_argument('--workers',type=int,choices=range(1,7),default=6)
    q=sp.add_parser('load'); q.add_argument('--remote',required=True)
    q.add_argument('--ram-dir',default='/dev/shm/nox_models'); q.add_argument('--sha256',required=True)
    q.add_argument('--reserve-gib',type=int,default=12); q.add_argument('--timeout',type=int,default=3600)
    return p


def main(argv=None):
    p=parser(); a=p.parse_args(argv)
    if a.action=='load' and a.reserve_gib<1:
        p.error('RAM reserve must be positive')
    if a.timeout<1:
        p.error('Timeout must be positive')
    try:
        {'upload':upload,'batch':batch,'load':load}[a.action](a)
    except Exception as ex:
        msg=str(ex)
        code=msg if re.fullmatch(r'HOLD_[A-Z0-9_]+',msg) else 'HOLD_'+type(ex).__name__.upper()
        print('NOX COLD: '+code,file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':
    raise SystemExit(main())
