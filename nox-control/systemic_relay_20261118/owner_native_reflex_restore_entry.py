#!/usr/bin/env python3
"""Restore the exact 6995658656 NOX dispatcher preimages after BACKOFF.

One-shot owner-authorized recovery only. No weights, S03, workspace, model,
proxy, web, other services, source branch or task history are changed.
"""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

ROOT = Path('/root/nox')
SERVICE = 'nox-dispatcher-t855u'
BACKUP = ROOT/'state/dispatcher/reflex_upgrade_backups/6995658656'
BEFORE = {
    'scripts/owner_subagent_dispatcher.py':'0193c511168489637b6df041bee2daf79bd42bd338c4ff5f9a6b129652dc4a13',
    'scripts/owner_systemic_refill.py':'4f0ea3f44ded11d40245de7573c5f48efc2e2f7424f979cec2da3e140a6d1197',
    'config/owner_native_subagents.json':'30effffe3c8a20c0df4dee936beb2f8183347fb2a5fd51d4543dfbde50efb919',
}
AFTER = {
    'scripts/owner_subagent_dispatcher.py':'eac3ce9e2d8c862d1a7917ec447ea72e84454b7775a4260ad1e72e59de96fe11',
    'scripts/owner_systemic_refill.py':'f6ef891912634dbfdb17937b5da900d305c9d77aeaac34a0dbb759e2db2ae422',
    'config/owner_native_subagents.json':'01892aed8879c8225232c8ebfca36bc4bafbe4e9d5ac4ff4639d07e02d8baaa2',
}

def require(valid,reason):
    if not valid: raise RuntimeError('HOLD_NATIVE_REFLEX_RESTORE_'+reason)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def regular(path,limit=2*1024*1024):
    path=Path(path)
    require(not any(x.is_symlink() for x in (path,*path.parents)),'SYMLINK')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as h:
        pre=os.fstat(h.fileno())
        require(stat.S_ISREG(pre.st_mode) and pre.st_size<=limit,'REGULAR')
        raw=h.read(limit+1)
        post=os.fstat(h.fileno())
    require(len(raw)<=limit and (pre.st_dev,pre.st_ino,pre.st_size,pre.st_mtime_ns)==
            (post.st_dev,post.st_ino,post.st_size,post.st_mtime_ns),'READ_CHANGED')
    return raw

def atomic(path,raw,mode):
    require(not any(p.is_symlink() for p in (path,*path.parents)),'TARGET_SYMLINK')
    fd,temp=tempfile.mkstemp(prefix='.nox-reflex-restore-',dir=path.parent)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'wb') as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
        d=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(d)
        finally:os.close(d)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def status():
    p=subprocess.run(['supervisorctl','status',SERVICE],capture_output=True,text=True,timeout=10)
    m=re.match(re.escape(SERVICE)+r'\s+(RUNNING|STARTING|STOPPED|FATAL|BACKOFF|EXITED)\b(?:\s+pid\s+([0-9]+))?',p.stdout)
    require(m is not None,'SUPERVISOR_UNREADABLE')
    return {'state':m[1],'pid':int(m[2]) if m[2] else None}

def run():
    rid=os.environ.get('NOX_OWNER_REQUEST_ID','')
    source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    require(re.fullmatch('[0-9]{1,24}',rid) and re.fullmatch('[a-f0-9]{40}',source),'OWNER_CONTEXT')
    receipt={'schema':'NOX_NATIVE_REFLEX_RESTORE_RECEIPT_V1','request':rid,
             'source_sha':source,'previous_request':'6995658656',
             'started_at':time.time(),'state':'PREFLIGHT','written':[],
             'model_restarted':False,'weights_changed':False,
             's03_changed':False,'web_or_proxy_restarted':False}
    lock=ROOT/'state/owner_maintenance.lock'
    fd=os.open(lock,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('HOLD_NATIVE_REFLEX_RESTORE_OWNER_LEASE_BUSY')
        info=os.fstat(fd);named=lock.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and
                info.st_nlink==1 and not(info.st_mode & 0o022) and
                (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'OWNER_LOCK')
        require(not any(p.exists() or p.is_symlink() for p in
                 [ROOT/'STOP',ROOT/'state/STOP',ROOT/'state/OWNER_MAINTENANCE.flag',Path('/workspace/NOX_STOP')]),'STOP')
        old={};current={}
        for rel,wanted in BEFORE.items():
            raw=regular(BACKUP/Path(rel).name)
            require(sha(raw)==wanted,'BACKUP_SHA_'+Path(rel).name)
            old[rel]=raw
            live=regular(ROOT/rel)
            require(sha(live) in (AFTER[rel],wanted),'UNRECOGNIZED_LIVE_SHA_'+Path(rel).name)
            current[rel]=live
        require(len({sha(value) for value in current.values()})==3,'CURRENT_DATA')
        sup=status()
        require(sup['state'] in ('STOPPED','BACKOFF','FATAL','EXITED') and sup['pid'] is None,
                'DIRECTOR_NOT_QUIESCENT')
        queue=json.loads(regular(ROOT/'state/dispatcher/state.json',32*1024*1024))
        require(isinstance(queue.get('tasks'),dict) and not any(
            isinstance(t,dict) and t.get('status')=='running' for t in queue['tasks'].values()),'QUEUE_NOT_IDLE')
        order=['scripts/owner_systemic_refill.py','scripts/owner_subagent_dispatcher.py','config/owner_native_subagents.json']
        for rel in order:
            now=regular(ROOT/rel)
            require(now==current[rel],'CURRENT_FILE_CHANGED')
            if now!=old[rel]:
                atomic(ROOT/rel,old[rel],0o600 if rel.startswith('config/') else 0o644)
                receipt['written'].append(rel)
            require(regular(ROOT/rel)==old[rel],'RESTORE_READBACK')
        require(all(sha(regular(ROOT/rel))==BEFORE[rel] for rel in BEFORE),'POSTIMAGES')
        receipt['state']='PREIMAGES_RESTORED'
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)

    # Original dispatcher requires the shared lock; don't hold EX while booting.
    sup=status()
    require(sup['state'] in ('STOPPED','BACKOFF','FATAL','EXITED'),'START_STATE')
    res=subprocess.run(['supervisorctl','start',SERVICE],capture_output=True,text=True,timeout=28)
    deadline=time.monotonic()+35
    observed=None
    while time.monotonic()<deadline:
        state=status()
        if state['state']=='RUNNING' and state['pid']:
            try:
                data=json.loads(regular(ROOT/'status/agents_t856u.json',2*1024*1024))
                native=data.get('native_subexecutors',{})
                workers=native.get('workers',[])
                director=native.get('director',{})
                if (director.get('pid')==state['pid'] and len(workers)==3
                    and all(row.get('state')=='RUNNING' or row.get('verified') is True
                            for row in workers if isinstance(row,dict))):
                    observed={'pid':state['pid'],'workers':len(workers)}
                    break
            except (OSError,ValueError,TypeError,KeyError,RuntimeError): pass
        if state['state'] in ('BACKOFF','FATAL') and time.monotonic()>deadline-18:
            break
        time.sleep(1)
    receipt['finished_at']=time.time()
    if observed:
        receipt['state']='ORIGINAL_DIRECTOR_THREE_WORKERS_RESTORED'
        receipt['director']=observed
    else:
        receipt['state']='HOLD_NATIVE_REFLEX_RESTORE_BOOT_NOT_VERIFIED'
        receipt['supervisor']=status()
    print('NOX_MAINT_REFLEX_RESTORE='+json.dumps(receipt,sort_keys=True,separators=(',',':')),flush=True)
    require(observed,'BOOT_NOT_VERIFIED')
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return receipt

if __name__=='__main__':
    run()
