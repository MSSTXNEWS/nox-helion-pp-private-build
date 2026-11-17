#!/usr/bin/env python3
"""Exact-source install only; never runs warm-load, cron, supervisor or a network client."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

ROOT=Path(__file__).resolve().parent
TARGET=Path('/root/nox/ops/nox_teachers_warm.sh')
LOCK=Path('/root/nox/state/owner_maintenance.lock')
BEFORE_SHA='437739550dbdff28380a95302c1cc1e98ceab3f147de898b40dd8ec82ef80389'
AFTER_SHA='14ec1196f61813ff6c88b1854a479660e7ef445fe7f5cb78c6f46e315dbf81e2'


def sha(data):return hashlib.sha256(data).hexdigest()


def read_regular(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>128*1024:raise ValueError('HOLD: file type or size')
        return stream.read(),info


def fsync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


@contextmanager
def maintenance(path,borrowed_fd=None):
    # The existing OneHost maintenance lock is required, never created by this installer.
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode):raise ValueError('HOLD: maintenance lock is not a regular file')
    fd=borrowed_fd if borrowed_fd is not None else os.open(path,os.O_RDWR|os.O_NOFOLLOW)
    try:
        actual=os.fstat(fd)
        if (actual.st_dev,actual.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('HOLD: maintenance lock FD mismatch')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise ValueError('HOLD: maintenance lock busy') from exc
        yield
    finally:
        if borrowed_fd is None:os.close(fd)


def install(*,apply=False,expected_source_sha=None,target=TARGET,lock_path=LOCK,maintenance_lock_fd=None):
    target=Path(target);lock_path=Path(lock_path)
    if target.is_symlink() or target.parent.is_symlink():raise ValueError('HOLD: target path is a symlink')
    patched,_=read_regular(ROOT/'nox_teachers_warm.drive_first.sh')
    if sha(patched)!=AFTER_SHA:raise ValueError('HOLD: packaged patch SHA differs')
    backup=target.with_name(target.name+'.before-drive-first-'+BEFORE_SHA[:16]+'.bak')
    def inspect_and_write():
        current,info=read_regular(target);current_sha=sha(current)
        out={'status':'CHECK_ONLY','target':str(target),'observed_sha256':current_sha,
             'drive_source_sha256':BEFORE_SHA,'patched_sha256':AFTER_SHA,
             'expected_source_sha256':expected_source_sha,'backup':str(backup),
             'download_calls':0,'service_restarts':0,'scheduler_changes':0,
             'models_touched':False,'native_model_ready':False,
             'serialization':'existing owner_maintenance.lock; cooperating writers only'}
        if current_sha not in (BEFORE_SHA,AFTER_SHA):raise ValueError('HOLD: live source differs; rebase exact patch')
        if not apply:return dict(out,source_matches=current_sha==BEFORE_SHA,already_patched=current_sha==AFTER_SHA)
        if not expected_source_sha:raise ValueError('HOLD: fresh native SHA pin required for apply')
        if current_sha==AFTER_SHA:
            if sha(read_regular(backup)[0])!=BEFORE_SHA:raise ValueError('HOLD: applied script has no verified backup')
            return dict(out,status='ALREADY_APPLIED')
        if expected_source_sha!=current_sha:raise ValueError('HOLD: compare-and-swap source mismatch')
        if backup.exists() or backup.is_symlink():
            if sha(read_regular(backup)[0])!=BEFORE_SHA:raise ValueError('HOLD: backup collision')
        else:
            fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as stream:
                stream.write(current);stream.flush();os.fsync(stream.fileno())
            fsync_dir(target.parent)
        if sha(read_regular(backup)[0])!=BEFORE_SHA:raise ValueError('HOLD: backup readback differs')
        # Recheck under the cooperating-writer maintenance lease immediately before publish.
        latest,latest_info=read_regular(target)
        if latest!=current or (latest_info.st_dev,latest_info.st_ino)!=(info.st_dev,info.st_ino):
            raise ValueError('HOLD: target changed before publish')
        fd,tmp=tempfile.mkstemp(prefix='.'+target.name+'.drive-first-',dir=target.parent)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(patched);stream.flush()
                os.fchmod(stream.fileno(),stat.S_IMODE(info.st_mode))
                os.fchown(stream.fileno(),info.st_uid,info.st_gid)
                os.fsync(stream.fileno())
            os.replace(tmp,target);fsync_dir(target.parent)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        if sha(read_regular(target)[0])!=AFTER_SHA:raise ValueError('HOLD: installed SHA readback differs')
        return dict(out,status='PATCH_APPLIED_NOT_EXECUTED',observed_sha256=AFTER_SHA)
    if not apply:return inspect_and_write()
    with maintenance(lock_path,maintenance_lock_fd):return inspect_and_write()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--expected-source-sha')
    parser.add_argument('--maintenance-lock-fd',type=int)
    args=parser.parse_args()
    try:
        out=install(apply=args.apply,expected_source_sha=args.expected_source_sha,
                    maintenance_lock_fd=args.maintenance_lock_fd)
    except (OSError,ValueError) as exc:out={'status':'HOLD','reason':str(exc),'native_model_ready':False}
    print(json.dumps(out,ensure_ascii=False,indent=2))
    return 2 if out['status']=='HOLD' else 0


if __name__=='__main__':raise SystemExit(main())
