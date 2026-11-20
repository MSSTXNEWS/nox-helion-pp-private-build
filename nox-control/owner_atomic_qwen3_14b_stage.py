#!/usr/bin/env python3
"""Stage exact official Qwen3-14B Q4_K_M GGUF as a non-live, quality-unverified fallback.

One owner-approved operation to stage a smaller, independently hash-pinned recovery model. Never stops/starts models or queues, rewrites
the active model, modifies S03, or removes any pre-existing file. Download is
bounded, SHA-256 verified and atomically published only after complete success.
"""
from __future__ import annotations
import hashlib,json,os,re,signal,stat,subprocess,time,urllib.request
from pathlib import Path

ROOT=Path('/root/nox')
TARGET_DIR=ROOT/'models/nox_lean_fallback'
FILENAME='Qwen3-14B-Q4_K_M.gguf'
URL='https://huggingface.co/Qwen/Qwen3-14B-GGUF/resolve/main/'+FILENAME
SHA256='500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0'
MAX_FILE=9_500_000_000
MIN_FILE=8_500_000_000
RESERVE_DISK=5*1024**3
MIN_FREE_RAM=32*1024**2
CGROUP=Path('/sys/fs/cgroup')
STOP_NAMES=('STOP','STOP.flag','stop.flag','.stop','program/STOP',
            'state/STOP','state/STOP.flag','state/OWNER_MAINTENANCE.flag')
STAGE='START'

class Hold(RuntimeError):pass
def need(ok,code):
    if not ok:raise Hold('HOLD_NOX_QWEN_STAGE_'+code)
def load(path,cap=16000):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        raw=stream.read(cap+1)
    need(len(raw)<=cap,'INPUT_BOUND')
    return raw.decode('ascii','strict')
def protected():
    proc={}
    for svc in ('nox-ds41-8098','nox-proxy','nox-web29-18775','nox-dispatcher-t855u'):
        p=subprocess.run(['supervisorctl','status',svc],capture_output=True,text=True,timeout=10)
        m=re.match(r'^'+re.escape(svc)+r'\s+RUNNING\s+pid ([1-9][0-9]*),',p.stdout.strip())
        need(p.returncode==0 and m,'SERVICE_DOWN')
        pid=int(m[1])
        fields=load(Path('/proc')/str(pid)/'stat',4096).rsplit(') ',1)
        need(len(fields)==2 and len(fields[1].split())>19,'PROC_IDENTITY')
        proc[svc]=(pid,int(fields[1].split()[19]))
    return proc
def stop_active():
    return any((ROOT/s).exists() or (ROOT/s).is_symlink() for s in STOP_NAMES) or Path('/workspace/NOX_STOP').exists()
def resources():
    current=int(load(CGROUP/'memory.current',40))
    maximum=int(load(CGROUP/'memory.max',40))
    need(0<current<maximum,'MEMORY_LIMIT')
    events={}
    for line in load(CGROUP/'memory.events',2048).splitlines():
        parts=line.split()
        if len(parts)==2 and parts[1].isdigit():events[parts[0]]=int(parts[1])
    need(events.get('oom',1)==0 and events.get('oom_kill',1)==0,'OOM')
    pressure={}
    for line in load(CGROUP/'memory.pressure',2048).splitlines():
        parts=line.split()
        m=re.fullmatch(r'avg10=([0-9]+\.[0-9]+)',parts[1]) if len(parts)>1 else None
        need(m is not None,'PSI_FORMAT')
        pressure[parts[0]]=float(m[1])
    need(pressure.get('some',1)<=0.05 and pressure.get('full',1)<=0.05,'PSI')
    need(maximum-current>=MIN_FREE_RAM,'HEADROOM')
    need(not stop_active(),'STOP')
    return maximum-current
def ensure_path():
    for ancestor in (ROOT,ROOT/'models',TARGET_DIR):
        need(not ancestor.is_symlink(),'DESTINATION_SYMLINK')
        if not ancestor.exists():
            ancestor.mkdir(mode=0o700)
        need(ancestor.is_dir() and not ancestor.is_symlink(),'DESTINATION_DIRECTORY')
    return TARGET_DIR/FILENAME
def existing_ok(path):
    if not path.is_file() or path.is_symlink():return False
    if not MIN_FILE<=path.stat().st_size<=MAX_FILE:return False
    sha=hashlib.sha256()
    with path.open('rb') as f:
        while True:
            chunk=f.read(4*1024*1024)
            if not chunk:break
            sha.update(chunk)
    return sha.hexdigest()==SHA256
def execute():
    global STAGE
    request=os.getenv('NOX_OWNER_REQUEST_ID','')
    pin=os.getenv('NOX_OWNER_SOURCE_SHA','')
    need(re.fullmatch(r'[0-9]{1,24}',request) and re.fullmatch(r'[0-9a-f]{40}',pin),'OWNER_CONTEXT')
    STAGE='PRECHECK'
    saved=protected()
    raw_before=resources()
    destination=ensure_path()
    need(not destination.is_symlink(),'TARGET_SYMLINK')
    if destination.exists():
        need(existing_ok(destination),'EXISTING_MODEL_CONFLICT')
        return {'state':'ALREADY_STAGED_EXACT_SHA','sha256':SHA256,
            'bytes':destination.stat().st_size,'source':URL,'no_active_model_change':True,
            'no_queue_or_s03_write':True,'raw_before':raw_before}
    st=os.statvfs(TARGET_DIR)
    free=st.f_bavail*st.f_frsize
    need(free>=MIN_FILE+RESERVE_DISK,'DISK_RESERVE')
    tmp=TARGET_DIR/(FILENAME+'.part.'+request)
    need(not tmp.exists() and not tmp.is_symlink(),'PART_EXISTS')
    STAGE='TRANSFER'
    count=0;digest=hashlib.sha256();last_check=0
    start=time.monotonic()
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        with os.fdopen(fd,'wb',buffering=0) as output:
            req=urllib.request.Request(URL,headers={'User-Agent':'NOX-HELION-verified-staging/1.0'})
            with urllib.request.urlopen(req,timeout=40) as stream:
                need(stream.status==200,'HTTP_STATUS')
                advertised=stream.headers.get('Content-Length','')
                if advertised.isdecimal():
                    expected=int(advertised)
                    need(MIN_FILE<=expected<=MAX_FILE,'REMOTE_SIZE_BOUND')
                    need(free>=expected+RESERVE_DISK,'DISK_RESERVE')
                while True:
                    need(time.monotonic()-start<820,'TRANSFER_BUDGET')
                    chunk=stream.read(1024*1024)
                    if not chunk:break
                    count+=len(chunk)
                    need(count<=MAX_FILE,'DOWNLOAD_LIMIT')
                    output.write(chunk)
                    digest.update(chunk)
                    if count-last_check>=32*1024*1024:
                        output.flush();os.fsync(output.fileno())
                        os.posix_fadvise(output.fileno(),0,count,os.POSIX_FADV_DONTNEED)
                        last_check=count
                        resources()
                        need(os.statvfs(TARGET_DIR).f_bavail*os.statvfs(TARGET_DIR).f_frsize>=RESERVE_DISK,'STREAM_DISK_RESERVE')
                        if count%(512*1024*1024)<32*1024*1024:
                            need(protected()==saved,'SERVICE_CHANGED')
            output.flush();os.fsync(output.fileno())
            os.posix_fadvise(output.fileno(),0,count,os.POSIX_FADV_DONTNEED)
        STAGE='CHECKSUM'
        need(count>=MIN_FILE and digest.hexdigest()==SHA256,'SHA256_OR_SIZE')
        need(protected()==saved and not stop_active(),'POST_SERVICE')
        need(os.statvfs(TARGET_DIR).f_bavail*os.statvfs(TARGET_DIR).f_frsize>=RESERVE_DISK,'POST_DISK_RESERVE')
        resources()
        STAGE='PUBLISH'
        need(not destination.exists() and not destination.is_symlink(),'TARGET_RACE')
        os.link(tmp,destination,follow_symlinks=False)
        os.unlink(tmp)
        dirfd=os.open(TARGET_DIR,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
        try:os.fsync(dirfd)
        finally:os.close(dirfd)
        need(destination.stat().st_size==count,'POST_PUBLISH_SIZE')
        return {'state':'STAGED_VERIFIED_NOT_ACTIVE','sha256':SHA256,'bytes':count,
                'source':URL,'no_active_model_change':True,
                'no_queue_or_s03_write':True,'model_service_pid':saved['nox-ds41-8098'][0],
                'raw_before':raw_before,'raw_after':resources()}
    except Exception:
        # Only remove the unique temp created by this exact owner request.
        if tmp.exists() and not tmp.is_symlink():
            tmp.unlink(missing_ok=True)
        raise
if __name__=='__main__':
    try:
        result=execute()
        print('NOX_MAINT_QWEN_STAGE='+json.dumps(result,sort_keys=True,separators=(',',':')),flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    except Exception as ex:
        reason=str(ex)
        if not re.fullmatch(r'HOLD_NOX_QWEN_STAGE_[A-Z0-9_]{1,100}',reason):
            reason='HOLD_NOX_QWEN_STAGE_INTERNAL_'+STAGE+'_'+type(ex).__name__.upper()
        print('NOX_MAINT_QWEN_STAGE='+json.dumps({'state':'HOLD','reason':reason,
            'active_model_changed':False,'original_task_accepted':False,
            'disk_free_bytes':os.statvfs(TARGET_DIR).f_bavail*os.statvfs(TARGET_DIR).f_frsize if TARGET_DIR.is_dir() else None},sort_keys=True),flush=True)
        raise SystemExit(2)
