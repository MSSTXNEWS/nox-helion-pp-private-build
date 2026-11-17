#!/usr/bin/env python3
"""Bounded delivery into a private GGUF staging directory, then atomic publish.

Uses the existing role2 immutable-manifest and file verifier. No service, GPU,
training, promotion, deletion of old weights or implicit server admission.
"""
from __future__ import annotations
import argparse
import ctypes
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
from urllib.request import Request, urlopen

CHUNK = 4 * 1024 * 1024
MAX_CALL = 1024 ** 3


def verifier():
    path = Path(__file__).resolve().parents[1]/'role2/verify_deepseek_pack.py'
    spec = importlib.util.spec_from_file_location('nox_existing_gguf_verifier', path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def require(test, code):
    if not test: raise RuntimeError(code)


def plain(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'HOLD_DELIVERY_SYMLINK')
    return path


def sha_file(path, limit=None):
    digest=hashlib.sha256();count=0
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno());require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==os.geteuid(),'HOLD_NOT_PRIVATE_REGULAR')
        while True:
            chunk=stream.read(CHUNK if limit is None else min(CHUNK,limit-count))
            if not chunk:break
            digest.update(chunk);count+=len(chunk)
            if limit is not None and count==limit:break
        after=os.fstat(stream.fileno())
        named=os.stat(path,follow_symlinks=False)
        identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        require(identity(before)==identity(after)==identity(named),'HOLD_DELIVERY_CHANGED')
    return count,digest,identity(before)


def atomic_json(path, body):
    temporary=path.with_name(path.name+'.next')
    # This is our own replaceable cursor only, never a model artifact.
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError('HOLD_UNCOMMITTED_CURSOR')
    with temporary.open('x',encoding='utf8') as f:
        os.chmod(temporary,0o600);json.dump(body,f,sort_keys=True,allow_nan=False)
        f.write('\n');f.flush();os.fsync(f.fileno())
    require(not path.is_symlink(),'HOLD_CURSOR_SYMLINK')
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def no_replace(source, target):
    # Linux OneHost: kernel-atomic publication, including destination races.
    libc=ctypes.CDLL(None,use_errno=True)
    rename=libc.renameat2;rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    rename.restype=ctypes.c_int
    if rename(-100,os.fsencode(source),-100,os.fsencode(target),1):
        code=ctypes.get_errno()
        raise OSError(code,os.strerror(code))


def open_range(url, start, end):
    return urlopen(Request(url,headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity'}),timeout=30)


def deliver(stage, drive, git, *, byte_budget, reserve_bytes, publish_to=None, transport=open_range, verify=None):
    v=verify or verifier()
    require(type(byte_budget) is int and 0<byte_budget<=MAX_CALL,'HOLD_BOUNDED_BYTE_BUDGET')
    require(type(reserve_bytes) is int and reserve_bytes>=0,'HOLD_STORAGE_RESERVE')
    expected,alias,total=v.compare_manifests(drive,git)
    stage=plain(stage);require(stage.is_dir(),'HOLD_EXISTING_ADMITTED_STAGE_REQUIRED')
    info=stage.stat()
    require(info.st_uid==os.geteuid() and info.st_mode&0o077==0,'HOLD_PRIVATE_STAGE_REQUIRED')
    if publish_to is not None:
        publish_to=plain(publish_to)
        require(publish_to.parent==stage.parent and publish_to!=stage,'HOLD_SAME_PARENT_ATOMIC_PUBLISH')
        require(not publish_to.exists(),'HOLD_PUBLICATION_EXISTS')
    lock_fd=os.open(stage/'.delivery.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
    try:
        lock_info=os.fstat(lock_fd)
        require(stat.S_ISREG(lock_info.st_mode) and lock_info.st_uid==os.geteuid() and lock_info.st_nlink==1,'HOLD_DELIVERY_LOCK_TYPE')
        fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fd=os.open(stage,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW)
        try:
            # Preserve every mismatched existing artifact; only missing names
            # can be downloaded. Completed good files are never redownloaded.
            initial={name:v.verify_file(fd,name,pin) for name,pin in expected.items()}
            require(all(s in ('MISSING','SHA256_MATCH') for s in initial.values()),'HOLD_EXISTING_ARTIFACT_MISMATCH')
            used=0;urls={r['path']:r['url'] for r in drive['files']}
            for name,(size,digest) in expected.items():
                if initial[name]=='SHA256_MATCH':continue
                part=stage/(name+'.part');cursor=stage/(name+'.cursor.json')
                pin=dict(schema='NOX_GGUF_CURSOR_V1',revision=git['revision'],name=name,bytes=size,sha256=digest)
                if not part.exists() and not part.is_symlink():
                    require(not cursor.exists() and not cursor.is_symlink(),'HOLD_ORPHAN_CURSOR')
                    with part.open('xb') as f:os.chmod(part,0o600);f.flush();os.fsync(f.fileno())
                    atomic_json(cursor,{**pin,'offset':0,'prefix_sha256':hashlib.sha256(b'').hexdigest()})
                part=plain(part);cursor=plain(cursor)
                require(cursor.is_file() and cursor.stat().st_size<8192,'HOLD_CURSOR_MISSING')
                state=v.load_manifest(cursor)
                require(all(state.get(k)==value for k,value in pin.items()),'HOLD_CURSOR_IDENTITY')
                count,hash_state,part_identity=sha_file(part)
                require(type(state.get('offset')) is int and count==state['offset'] and count<=size
                    and hash_state.hexdigest()==state.get('prefix_sha256'),'HOLD_CURSOR_PREFIX_MISMATCH')
                if count<size and used<byte_budget:
                    amount=min(byte_budget-used,size-count)
                    fs=os.fstatvfs(fd)
                    require(fs.f_bavail*fs.f_frsize>=amount+reserve_bytes,'HOLD_MEASURED_DISK_BUDGET')
                    with transport(urls[name],count,count+amount-1) as response:
                        require(response.status==206,'HOLD_RANGE_REQUIRED')
                        require(response.headers.get('Content-Range')==f'bytes {count}-{count+amount-1}/{size}','HOLD_CONTENT_RANGE')
                        require(response.headers.get('Content-Encoding','identity')=='identity','HOLD_ENCODED_RANGE')
                        require(response.headers.get('Content-Length')==str(amount),'HOLD_RANGE_LENGTH')
                        output_fd=os.open(part,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW)
                        with os.fdopen(output_fd,'ab') as output:
                            current=os.fstat(output.fileno())
                            require((current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns,current.st_ctime_ns)==part_identity,'HOLD_PART_CHANGED')
                            remaining=amount
                            while remaining:
                                chunk=response.read(min(CHUNK,remaining))
                                require(bool(chunk) and len(chunk)<=remaining,'HOLD_RANGE_TRUNCATED')
                                output.write(chunk);output.flush();os.fsync(output.fileno())
                                hash_state.update(chunk);count+=len(chunk);used+=len(chunk);remaining-=len(chunk)
                                atomic_json(cursor,{**pin,'offset':count,'prefix_sha256':hash_state.hexdigest()})
                            require(not response.read(1),'HOLD_RANGE_OVERRUN')
                if count==size:
                    require(hash_state.hexdigest()==digest,'HOLD_COMPLETE_SHA_MISMATCH')
                    require(v.verify_file(fd,part.name,(size,digest))=='SHA256_MATCH','HOLD_GGUF_COMPLETION')
                    no_replace(part,stage/name)
                if used>=byte_budget:break
            final={name:v.verify_file(fd,name,pin) for name,pin in expected.items()}
            complete=all(s=='SHA256_MATCH' for s in final.values())
            if complete:
                alias_path=stage/alias[0]
                if not alias_path.exists() and not alias_path.is_symlink():os.symlink(alias[1],alias_path)
                require(v.verify_alias(fd,alias) in ('RELATIVE_SYMLINK_MATCH','HARDLINK_MATCH'),'HOLD_ENGRAM_ALIAS')
            report=dict(schema='NOX_GGUF_BOUNDED_DELIVERY_V1',revision=git['revision'],
                transferred_bytes=used,byte_budget=byte_budget,files=final,complete=complete,
                published=False,native_onehost_acceptance=False,training_started=False)
            if complete and publish_to is not None:
                atomic_json(stage/'GGUF_VERIFIED_RECEIPT.json',report)
                os.fsync(fd);no_replace(stage,publish_to)
                parent_fd=os.open(publish_to.parent,os.O_DIRECTORY|os.O_RDONLY)
                try:os.fsync(parent_fd)
                finally:os.close(parent_fd)
                report['published']=True
            return report
        finally:os.close(fd)
    finally:os.close(lock_fd)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',required=True);p.add_argument('--publish-to')
    p.add_argument('--byte-budget',type=int,required=True);p.add_argument('--reserve-bytes',type=int,required=True)
    p.add_argument('--execute',action='store_true')
    args=p.parse_args()
    if not args.execute:p.error('--execute requires the existing owner storage admission and lease')
    v=verifier()
    try:result=deliver(args.stage,v.load_manifest(v.HERE/'drive-publisher-manifest.json'),
        v.load_manifest(v.HERE/'git-immutable-weights.json'),byte_budget=args.byte_budget,
        reserve_bytes=args.reserve_bytes,publish_to=args.publish_to,verify=v)
    except (RuntimeError,OSError,ValueError) as exc:
        print(json.dumps({'state':'HOLD_DELIVERY','reason':str(exc),'native_onehost_acceptance':False}));return 2
    print(json.dumps(result,sort_keys=True));return 0 if result['complete'] else 3


if __name__=='__main__':raise SystemExit(main())
