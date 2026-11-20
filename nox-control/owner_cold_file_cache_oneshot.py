#!/usr/bin/env python3
"""Owner-scoped bounded cold-file cache hints. No files, weights, S03 or services changed."""
from __future__ import annotations
import fcntl, json, os, re, stat, subprocess
from pathlib import Path

ROOT=Path('/root/nox')
CGROUP=Path('/sys/fs/cgroup')
GIB=1024**3
MIB=1024**2
FLOOR=2*GIB
GOAL=4*GIB
COLD_MIN=12*GIB
EXT=('.safetensors','.gguf','.ggml','.pt','.pth','.ckpt','.zip','.bin','.tar','.tar.gz','.zst')
ROOTS=('/root/nox','/workspace','/models','/root/.cache/huggingface','/root/.cache/torch')
SERVICES=('nox-ds41-8098','nox-proxy','nox-web29-18775','nox-dispatcher-t855u')
STOPS=('STOP','STOP.flag','stop.flag','.stop','program/STOP','state/STOP','state/STOP.flag','state/OWNER_MAINTENANCE.flag')
STAGE='START'

class Hold(RuntimeError): pass

def require(ok,reason):
    if not ok:raise Hold('HOLD_NOX_COLD_FILE_'+reason)

def read(path,cap=16000):
    path=Path(path)
    require(not path.is_symlink(),'SYMLINK')
    with path.open('rb') as f:raw=f.read(cap+1)
    require(len(raw)<=cap,'INPUT_SIZE')
    return raw.decode('ascii')

def snapshot():
    current=read(CGROUP/'memory.current',40).strip()
    maximum=read(CGROUP/'memory.max',40).strip()
    require(current.isdecimal() and maximum.isdecimal(),'MEMORY_LIMIT')
    current,maximum=int(current),int(maximum)
    require(0<current<maximum,'MEMORY_RANGE')
    stats={}
    for line in read(CGROUP/'memory.stat').splitlines():
        parts=line.split()
        require(len(parts)==2 and parts[1].isdecimal() and parts[0] not in stats,'MEMORY_STAT')
        stats[parts[0]]=int(parts[1])
    require({'file','shmem','inactive_file'}<=stats.keys(),'MEMORY_STAT')
    cold=max(0,min(stats['inactive_file'],max(0,stats['file']-stats['shmem']))-stats['shmem'])
    ev={}
    for line in read(CGROUP/'memory.events',2048).splitlines():
        p=line.split()
        require(len(p)==2 and p[1].isdecimal(),'MEMORY_EVENTS')
        ev[p[0]]=int(p[1])
    require({'oom','oom_kill'}<=ev.keys(),'MEMORY_EVENTS')
    psi={}
    for line in read(CGROUP/'memory.pressure',2048).splitlines():
        p=line.split()
        require(len(p)>=2,'MEMORY_PSI')
        m=re.fullmatch(r'avg10=([0-9]+\.[0-9]+)',p[1])
        require(m is not None,'MEMORY_PSI')
        psi[p[0]]=float(m[1])
    require(set(psi)=={'some','full'},'MEMORY_PSI')
    return {'free':maximum-current,'cold':cold,'max':maximum,'oom':ev['oom'],
            'oom_kill':ev['oom_kill'],'psi':psi}

def stopped():
    return any((ROOT/p).exists() or (ROOT/p).is_symlink() for p in STOPS) or Path('/workspace/NOX_STOP').exists()

def processes():
    pins={}
    for name in SERVICES:
        p=subprocess.run(['supervisorctl','status',name],text=True,capture_output=True,timeout=8)
        m=re.match('^'+re.escape(name)+r'\s+RUNNING\s+pid\s+(\d+),',p.stdout.strip())
        require(p.returncode==0 and m is not None,'SERVICE_STATE')
        pid=int(m[1]);data=read(Path('/proc')/str(pid)/'stat',4096)
        tick=int(data.rsplit(') ',1)[1].split()[19])
        require(tick>0,'SERVICE_PID')
        pins[name]=(pid,tick)
    return pins

def guard(m,origin=None):
    require(m['free']>=32*MIB and m['cold']>=COLD_MIN,'RESOURCE')
    require(m['psi']['some']<=0.05 and m['psi']['full']<=0.05,'PRESSURE')
    require(m['oom']==0 and m['oom_kill']==0,'OOM')
    require(not stopped(),'STOP')
    if origin is not None:require(m['max']==origin['max'],'CGROUP_LIMIT_DRIFT')

def opened_paths(pins):
    used=set()
    for pid,_ in pins.values():
        for fd in (Path('/proc')/str(pid)/'fd').iterdir():
            try:
                path=os.readlink(fd)
                if path.startswith('/'):used.add(path.removesuffix(' (deleted)'))
            except OSError:pass
        with (Path('/proc')/str(pid)/'maps').open('r',errors='replace') as f:
            for line in f:
                p=line.rstrip().split(None,5)
                if len(p)==6 and p[5].startswith('/'):used.add(p[5].removesuffix(' (deleted)'))
    return used

def cold_files(used):
    found=[];seen=set();walked=0
    for root in ROOTS:
        r=Path(root)
        if not r.is_dir() or r.is_symlink():continue
        for dirname,dirs,names in os.walk(r,followlinks=False):
            dirs[:]=[d for d in dirs if d not in {'state','s03','memory','tmp','proc','sys','dev','node_modules','.git'}
                     and not (Path(dirname)/d).is_symlink()]
            for name in names:
                walked+=1
                require(walked<=25000,'WALK_BOUND')
                path=Path(dirname)/name
                if not name.lower().endswith(EXT) or path.is_symlink() or str(path) in used:continue
                if any(word in name.lower() for word in ('engram','active','current','live-model')):continue
                try:s=path.stat(follow_symlinks=False)
                except OSError:continue
                inode=(s.st_dev,s.st_ino)
                if not stat.S_ISREG(s.st_mode) or s.st_size<256*MIB or inode in seen:continue
                found.append((s.st_size,str(path),inode));seen.add(inode)
    found.sort(reverse=True)
    return found[:80],walked

def perform():
    global STAGE
    require(re.fullmatch(r'[0-9]{1,24}',os.getenv('NOX_OWNER_REQUEST_ID','')) is not None,'OWNER_ID')
    require(re.fullmatch(r'[a-f0-9]{40}',os.getenv('NOX_OWNER_SOURCE_SHA','')) is not None,'OWNER_SHA')
    # Existing immutable owner-comment transport binds repair action and Vast instance.
    # The remote payload receives only the exact verified request ID and source SHA.
    STAGE='OWNER_LOCK'
    lock=ROOT/'state/owner_maintenance.lock'
    require(not lock.is_symlink(),'OWNER_LOCK_SYMLINK')
    fd=os.open(lock,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Hold('HOLD_NOX_COLD_FILE_OWNER_BUSY') from None
        STAGE='PRECONDITIONS'
        pins=processes();initial=snapshot();guard(initial)
        if initial['free']>=GOAL:
            return {'status':'ALREADY_ENOUGH','raw_before':initial['free'],
                    'raw_after':initial['free'],'files_advised':0,'data_deleted':False,
                    'model_restarted':False,'s03_modified':False}
        STAGE='SEARCH'
        files,walked=cold_files(opened_paths(pins))
        STAGE='HINT'
        advised=0;total=0;errors=0
        for size,path,inode in files:
            if total>=72*GIB:break
            current=snapshot()
            if current['free']>=FLOOR and current['cold']<COLD_MIN:break
            guard(current,initial)
            try:
                f=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
                try:
                    info=os.fstat(f)
                    require(stat.S_ISREG(info.st_mode) and
                            (info.st_dev,info.st_ino)==inode and
                            info.st_size==size,'INODE_CHANGED')
                    os.posix_fadvise(f,0,0,os.POSIX_FADV_DONTNEED)
                    advised+=1;total+=size
                finally:os.close(f)
            except OSError:errors+=1
            if snapshot()['free']>=GOAL:break
        STAGE='POSTCONDITIONS'
        after=snapshot()
        require(not stopped() and processes()==pins,'SERVICES_CHANGED')
        require(after['max']==initial['max'] and after['oom']==initial['oom'] and
                after['oom_kill']==initial['oom_kill'],'POST_RESOURCE')
        return {'status':'ADMISSION_RECOVERED' if after['free']>=FLOOR else 'INSUFFICIENT_CACHE_FREED',
                'raw_before':initial['free'],'raw_after':after['free'],
                'files_advised':advised,'logical_bytes_advised':total,'file_errors':errors,
                'files_scanned':walked,'candidates':len(files),
                'data_deleted':False,'model_restarted':False,'s03_modified':False,
                'native_task_published':False}
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)

if __name__=='__main__':
    try:
        result=perform()
        print('NOX_MAINT_COLD_FILE='+json.dumps(result,sort_keys=True,separators=(',',':')),flush=True)
        if result['status'] in ('ADMISSION_RECOVERED','ALREADY_ENOUGH'):
            print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
        else:raise SystemExit(2)
    except Exception as exc:
        reason=str(exc)
        if not re.fullmatch(r'HOLD_NOX_COLD_FILE_[A-Z0-9_]{1,100}',reason):
            reason='HOLD_NOX_COLD_FILE_INTERNAL_'+STAGE+'_'+type(exc).__name__.upper()
        print('NOX_MAINT_COLD_FILE='+json.dumps({'status':'HOLD','reason':reason,
            'data_deleted':False,'model_restarted':False},sort_keys=True),flush=True)
        raise SystemExit(2)
