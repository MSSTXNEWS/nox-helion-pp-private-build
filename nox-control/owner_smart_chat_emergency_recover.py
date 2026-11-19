#!/usr/bin/env python3
"""Emergency owner repair: restore exact verified preimage bytes; never touch S03.

The prior two-source install changed both native files but proxy start and
rollback failed. Use its private immutable native backups and current checksums.
Only the original nox-proxy Supervisor unit may be stopped/started, not model.
"""
from __future__ import annotations
import ctypes
import fcntl
import hashlib
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time

ROOT=Path('/root/nox')
STATE=ROOT/'state'
BACKUPS=STATE/'owner_smart_chat_backups'/'6996280040'
LOCK=STATE/'owner_maintenance.lock'
PAIRS={
 'stream':(ROOT/'scripts/owner_chat_stream.py',
   '38f4dc2995dd2c31f1f4d6a816d485721267d7add1c789cc4693aca54233fe09',
   'a26ec83aadac240d7284959b53cf7e59575e8e487d27c962cec7236892ccc7af'),
 'bridge':(ROOT/'scripts/nox_v29_chat_bridge.py',
   '9d7475428ad8c553c756ca50280ac2363e7c03854abab285de560ae066d4586a',
   '2d7145293fa5566fee38a61e772780b4b0dd0e2d1bcad71b5ceedf77974a75a7'),
}
STOPS=tuple(ROOT/x for x in ('STOP','STOP.flag','stop.flag','.stop','program/STOP','state/STOP'))
SAFE_ENV={'PATH':'/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'}
SCHEMA='NOX_SMART_CHAT_OWNER_RECOVERY_V1'


def require(ok, reason):
    if not ok:
        raise RuntimeError('HOLD_SMART_CHAT_RECOVERY_'+reason)


def check_stop():
    require(not any(os.path.lexists(x) for x in STOPS), 'OWNER_STOP')


def private_read(path):
    path=Path(path)
    require(path.is_absolute(), 'PATH')
    fd=os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        meta=os.fstat(fd)
        require(stat.S_ISREG(meta.st_mode) and meta.st_uid==os.geteuid() and meta.st_nlink==1
                and not (meta.st_mode & 0o022) and meta.st_size<=1024*1024, 'SOURCE_SCOPE')
        raw=os.read(fd, 1024*1024+1)
        require(len(raw)==meta.st_size, 'SOURCE_SIZE')
        return hashlib.sha256(raw).hexdigest()
    finally:
        os.close(fd)


def service(name='nox-proxy'):
    run=subprocess.run(['supervisorctl','status',name],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        timeout=8,env=SAFE_ENV)
    rows=run.stdout.decode('utf-8','replace').strip().splitlines()
    require(len(rows)==1 and rows[0].startswith(name+' '), 'SERVICE_IDENTITY')
    parts=rows[0].split()
    require(len(parts)>=2, 'SERVICE_SCHEMA')
    state=parts[1]
    require(state in ('RUNNING','STOPPED','EXITED','FATAL','BACKOFF','STARTING','STOPPING'), 'SERVICE_STATE')
    pid=None
    match=re.search(r'\bpid ([0-9]+),',rows[0])
    if match: pid=int(match.group(1))
    if state=='RUNNING':
        require(run.returncode==0 and pid is not None, 'SERVICE_RUNNING_PID')
        if name=='nox-proxy':
            args=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
            require(b'/root/nox/scripts/chat_proxy.py' in args, 'FOREIGN_PROXY_PROCESS')
    return {'state':state,'pid':pid}


def http_health(port):
    c=HTTPConnection('127.0.0.1',port,timeout=5)
    try:
        c.request('GET','/health',headers={'Connection':'close'})
        r=c.getresponse()
        return r.status==200
    except OSError:
        return False
    finally:
        c.close()


def call_supervisor(action):
    r=subprocess.run(['supervisorctl',action,'nox-proxy'],stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=45,env=SAFE_ENV)
    return r.returncode


def no_active_model():
    import urllib.request
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                'http://127.0.0.1:8098/slots',timeout=4) as response:
            rows=json.loads(response.read(100001))
        if not isinstance(rows,list) or len(rows)!=2:
            return False
        for row in rows:
            values=[row[k] for k in ('is_processing','processing') if k in row]
            if not values or any(type(x) is not bool for x in values) or any(values):
                return False
        return True
    except (OSError,ValueError,KeyError):
        return False


def exchange(first, second):
    first,second=Path(first),Path(second)
    a=os.open(first.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    b=os.open(second.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        require(os.fstat(a).st_dev==os.fstat(b).st_dev,'FILESYSTEM_MISMATCH')
        f=getattr(ctypes.CDLL(None,use_errno=True),'renameat2',None)
        require(f is not None,'ATOMIC_EXCHANGE_UNAVAILABLE')
        f.argtypes=(ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint)
        f.restype=ctypes.c_int
        if f(a,os.fsencode(first.name),b,os.fsencode(second.name),2):
            raise OSError(ctypes.get_errno(),'atomic exchange failed')
        os.fsync(a);os.fsync(b)
    finally:
        os.close(b);os.close(a)


def main():
    request_id=os.environ.get('NOX_OWNER_REQUEST_ID','')
    commit=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    require(re.fullmatch(r'[0-9]{1,24}',request_id) and re.fullmatch(r'[a-f0-9]{40}',commit), 'OWNER_CONTEXT')
    result={'schema':SCHEMA,'request':request_id,'source_sha':commit,
        'old_backup_request':'6996280040','source_reverted':[],'model_or_training_restarted':False,
        's03_modified':False,'stop_flags_modified':False,'credentials_exported':False,
        'private_source_exported':False,'started_at':time.time()}
    lockfd=None; success=False
    try:
        check_stop()
        result['peer_services'] = {}
        for name in ('nox-ds41-8098','nox-web29-18775','nox-dispatcher-t855u'):
            try:
                result['peer_services'][name] = service(name)['state']
            except Exception:
                result['peer_services'][name] = 'UNKNOWN'
        result['model_health_before'] = http_health(8098)
        # Recovery of original chat files is independent of a halted dispatcher.
        lockfd=os.open(LOCK,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        for _ in range(90):
            try:
                fcntl.flock(lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                check_stop();time.sleep(.5)
        else:
            require(False,'OWNER_LEASE_BUSY')
        check_stop()
        current=service()
        result['proxy_before']=current
        hashes={}
        for label,(target,old,new) in PAIRS.items():
            source=private_read(target)
            backup=private_read(BACKUPS/(label+'.original'))
            stage=private_read(BACKUPS/(label+'.exchange'))
            require(backup==old,'PRIVATE_BACKUP_SHA_'+label.upper())
            require(source in (old,new),'FOREIGN_TARGET_'+label.upper())
            require(stage in (old,new),'FOREIGN_STAGED_'+label.upper())
            hashes[label]=(source,stage)
        if all(t[0]==PAIRS[k][1] for k,t in hashes.items()) and current['state']=='RUNNING' and http_health(8080):
            result['state']='ALREADY_RESTORED_AND_HEALTHY'
            success=True
        else:
            if current['state']=='RUNNING':
                require(not result['model_health_before'] or all(no_active_model() for _ in range(3)), 'MODEL_BUSY_FOR_PROXY_STOP')
                # Exactly the owner-scoped proxy; its argv was pinned in service().
                require(call_supervisor('stop')==0,'PROXY_STOP_COMMAND')
                current=service()
            elif current['state'] in ('STARTING','BACKOFF','STOPPING'):
                call_supervisor('stop')
                current=service()
            require(current['state'] in ('STOPPED','EXITED','FATAL'),'PROXY_NOT_QUIESCENT')
            for label,(target,old,new) in PAIRS.items():
                state,stage=hashes[label]
                if state==new:
                    require(stage==old,'ORIGINAL_STAGE_MISMATCH_'+label.upper())
                    check_stop();exchange(target,BACKUPS/(label+'.exchange'))
                    require(private_read(target)==old,'RESTORE_TARGET_'+label.upper())
                    require(private_read(BACKUPS/(label+'.exchange'))==new,
                            'RESTORE_STAGE_'+label.upper())
                    result['source_reverted'].append(label)
                else:
                    require(private_read(target)==old,'ALREADY_OLD_CHANGED_'+label.upper())
            result['original_sources_verified']=all(
                private_read(target)==old for target,old,_ in PAIRS.values())
            require(result['original_sources_verified'],'POSTRESTORE_HASH')
            check_stop()
            rc=call_supervisor('start')
            result['proxy_start_command_rc']=rc
            deadline=time.monotonic()+35
            while time.monotonic()<deadline:
                state=service()
                if state['state']=='RUNNING' and http_health(8080):
                    result['proxy_after']=state
                    break
                time.sleep(.5)
            else:
                require(False,'PROXY_HEALTH_AFTER_ROLLBACK')
            result['model_health_after'] = http_health(8098)
            result['state']='ORIGINAL_SOURCES_AND_PROXY_HEALTH_VERIFIED'
            success=True
    except Exception as exc:
        value=str(exc)
        result['state']='HOLD_RECOVERY'
        result['reason']=value if re.fullmatch(r'HOLD_SMART_CHAT_RECOVERY_[A-Z0-9_]{1,120}',value) else type(exc).__name__
    finally:
        if lockfd is not None:
            os.close(lockfd)
        result['finished_at']=time.time()
        try:
            result['proxy_status_after'] = service()
        except Exception:
            result['proxy_status_after'] = {'state':'UNKNOWN'}
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'smart_chat_emergency_recovery','data':result},
            separators=(',',':'),sort_keys=True),flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE='+str(success).lower(),flush=True)
    return 0 if success else 2


if __name__=='__main__':
    raise SystemExit(main())
