#!/usr/bin/env python3
"""One owner-authenticated, bounded cgroup-v2 clean-file-cache reclaim.

No process signals, model/service restarts, drop_caches, rm, DB writes, or
training changes. Only the kernel's memory.reclaim interface is requested once.
Fail closed unless strict owner, STOP, cgroup, PSI/OOM and cold-cache gates pass.
This must remain an ephemeral exact-source OWNER_REPAIR, never a default route.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

ROOT=Path('/root/nox')
CGROUP=Path('/sys/fs/cgroup')
MIB=1024**2
GIB=1024**3
MIN_RAW=512*MIB
TARGET_RAW=4*GIB
COLD_MIN=6*GIB
MAX_ONESHOT=4*GIB
SERVICES=('nox-ds41-8098','nox-proxy','nox-web29-18775','nox-dispatcher-t855u')
STOP_FILES=('STOP','STOP.flag','stop.flag','.stop','program/STOP','state/STOP',
            'state/STOP.flag','state/OWNER_MAINTENANCE.flag')
REQ=re.compile(r'[0-9]{1,24}\Z')
SRC=re.compile(r'[a-f0-9]{40}\Z')


def hold(reason):
    raise RuntimeError('HOLD_SAFE_CGROUP_'+reason)


def read_text(path, limit=8192):
    if path.is_symlink():
        hold('SYMLINK')
    with path.open('rb') as f:
        raw=f.read(limit+1)
    if len(raw)>limit:
        hold('FILE_BOUND')
    return raw.decode('ascii',errors='strict')


def cgroup_memory():
    current=read_text(CGROUP/'memory.current',40).strip()
    maximum=read_text(CGROUP/'memory.max',40).strip()
    if not current.isdigit() or not maximum.isdigit():
        hold('LIMIT')
    current,maximum=int(current),int(maximum)
    if not 0<current<maximum<2**64:
        hold('LIMIT')
    stats={}
    for line in read_text(CGROUP/'memory.stat',12000).splitlines():
        row=line.split()
        if len(row)!=2 or not row[1].isdigit() or row[0] in stats:
            hold('STATS')
        stats[row[0]]=int(row[1])
    if not all(x in stats for x in ('file','inactive_file','shmem','anon')):
        hold('STATS')
    events={}
    for line in read_text(CGROUP/'memory.events',2000).splitlines():
        row=line.split()
        if len(row)!=2 or not row[1].isdigit() or row[0] in events:
            hold('EVENTS')
        events[row[0]]=int(row[1])
    if not all(x in events for x in ('oom','oom_kill')):
        hold('EVENTS')
    pressure=read_text(CGROUP/'memory.pressure',2000)
    try:
        psi={row.split()[0]:float(re.fullmatch(r'avg10=([0-9]+\.[0-9]+)',row.split()[1]).group(1))
             for row in pressure.splitlines() if row.split()}
    except (AttributeError,IndexError,ValueError):
        hold('PSI')
    if set(psi)!={'some','full'}:
        hold('PSI')
    # Conservative lower bound: subtract shmem from inactive_file even on
    # kernels that already account shmem on the anonymous LRU.
    cold=max(0,min(stats['inactive_file'], max(0,stats['file']-stats['shmem']))-stats['shmem'])
    return {'raw':maximum-current,'max':maximum,'current':current,
            'cold_lower_bound':cold,'psi':psi,'events':events}


def stopped():
    paths=[ROOT/p for p in STOP_FILES]+[Path('/workspace/NOX_STOP')]
    return any(p.exists() or p.is_symlink() for p in paths)


def services():
    result={}
    for name in SERVICES:
        try:
            p=subprocess.run(['supervisorctl','status',name],text=True,
                             capture_output=True,timeout=10)
        except (OSError,subprocess.TimeoutExpired):
            hold('SERVICE_UNAVAILABLE')
        match=re.match(r'^'+re.escape(name)+r'\s+RUNNING\s+pid\s+([0-9]+),',p.stdout.strip())
        if p.returncode!=0 or not match:
            hold('SERVICE_NOT_RUNNING')
        pid=int(match.group(1))
        raw=read_text(Path('/proc')/str(pid)/'stat',2048)
        try:
            columns=raw.rsplit(') ',1)[1].split()
            start_ticks=int(columns[19])
            if columns[0]=='Z' or start_ticks<=0:hold('SERVICE_PID_STATE')
        except (IndexError,ValueError):
            hold('SERVICE_PID_STATE')
        result[name]={'pid':pid,'start_ticks':start_ticks}
    return result


def check(before):
    if before['raw']<MIN_RAW or before['cold_lower_bound']<COLD_MIN:
        hold('MEMORY_ADMISSION')
    if before['psi']['some']>0.05 or before['psi']['full']>0.05:
        hold('PRESSURE')
    if before['events']['oom'] or before['events']['oom_kill']:
        hold('OOM')
    if stopped():
        hold('STOP')
    if not (CGROUP/'memory.reclaim').exists():
        hold('RECLAIM_UNAVAILABLE')


def execute():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','')
    source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not REQ.fullmatch(request) or not SRC.fullmatch(source):
        hold('OWNER_CONTEXT')
    lock_path=ROOT/'state/owner_maintenance.lock'
    if lock_path.is_symlink():
        hold('LOCK_SYMLINK')
    lock=os.open(lock_path,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:hold('LOCK_BUSY')
        original_services=services()
        before=cgroup_memory()
        check(before)
        if before['raw']>=TARGET_RAW:
            print('NOX_MAINT_SAFE_RECLAIM='+json.dumps({
                'request':request,'state':'ALREADY_ENOUGH_RAW_RAM',
                'raw_before':before['raw'],'raw_after':before['raw'],
                'kernel_reclaim_requested':False,'model_restarted':False,
                'data_deleted':False,'source_sha':source},sort_keys=True),flush=True)
            print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
            return
        reclaim_bytes=min(MAX_ONESHOT,max(GIB,TARGET_RAW-before['raw']+GIB))
        require_cold=reclaim_bytes+2*GIB
        if before['cold_lower_bound']<require_cold:
            hold('COLD_CACHE_RESERVE')
        path=CGROUP/'memory.reclaim'
        if path.is_symlink():
            hold('RECLAIM_SYMLINK')
        info=path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            hold('RECLAIM_TYPE')
        # The file is scoped to this cgroup, not the host's global drop_caches.
        fd=os.open(path,os.O_WRONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            payload=str(reclaim_bytes).encode('ascii')
            if os.write(fd,payload)!=len(payload):
                hold('RECLAIM_SHORT_WRITE')
        except OSError as exc:
            hold('KERNEL_RECLAIM_DENIED_'+type(exc).__name__.upper())
        finally:
            os.close(fd)
        time.sleep(0.5)
        after=cgroup_memory()
        if after['max']!=before['max'] or stopped() or services()!=original_services:
            hold('POST_IDENTITY')
        if after['events']['oom']!=before['events']['oom'] or (
                after['events']['oom_kill']!=before['events']['oom_kill']):
            hold('POST_OOM')
        if after['raw']<TARGET_RAW:
            hold('POST_INSUFFICIENT_RAW')
        print('NOX_MAINT_SAFE_RECLAIM='+json.dumps({
            'request':request,'state':'RECLAIMED_CGROUP_FILE_CACHE',
            'raw_before':before['raw'],'raw_after':after['raw'],
            'cold_lower_bound_before':before['cold_lower_bound'],
            'kernel_reclaim_requested':True,'requested_bytes':reclaim_bytes,
            'model_restarted':False,'data_deleted':False,'source_sha':source
        },sort_keys=True,separators=(',',':')),flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    finally:
        fcntl.flock(lock,fcntl.LOCK_UN)
        os.close(lock)


if __name__=='__main__':
    try:
        execute()
    except Exception as exc:
        code=str(exc)
        if not re.fullmatch(r'HOLD_SAFE_CGROUP_[A-Z0-9_]{1,100}',code):
            code='HOLD_SAFE_CGROUP_INTERNAL'
        print('NOX_MAINT_SAFE_RECLAIM='+json.dumps({
            'state':'HOLD','reason':code,'model_restarted':False,
            'data_deleted':False,'kernel_reclaim_completed':False},sort_keys=True),flush=True)
        raise SystemExit(2)
