#!/usr/bin/env python3
"""One bounded namespace probe with exact process/source guards; no host policy changes."""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import selectors
import signal
import stat
import subprocess
import time


ROOT=Path('/root/nox')


EXPECTED_CONFIG='085fa4e3c8c96ae4ffb952dee53bb0d8bda0a1c50416a4d8a365017d043e95be'


EXPECTED_SOURCE_CENSUS='f9d914745e8b42bc7d8f45bc5dd0804291a86eacab4edd1cd2dc42d4c17f583f'


DIRECTOR={'pid':3760381,'start_ticks':176197984}


WORKERS=[{'pid':pid,'start_ticks':176199997} for pid in (3760595,3760596,3760597)]


class DiagnosticHold(RuntimeError):pass


def require(value,code):
    if not value:raise DiagnosticHold('HOLD_NAMESPACE_INSPECT_'+code)


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def digest(raw):return hashlib.sha256(raw).hexdigest()


def safe_text(value,limit=8192):
    value=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',str(value))
    value=re.sub(r'[\x00-\x08\x0b-\x1f\x7f]','',value)
    value=re.sub(r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)',
                 '[REDACTED_PRIVATE_KEY]',value)
    value=re.sub(r'(?i)(https?://)[^\s/:@]+:[^\s/@]+@',r'\1[REDACTED]@',value)
    value=re.sub(r'(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9+/_.~=-]{8,}','[REDACTED_AUTH]',value)
    value=re.sub(r'(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\s*[=:]\s*[\"\']?[^\s\"\',}]{4,}',
                 '[REDACTED_CREDENTIAL]',value)
    value=re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{16,}|xox[baprs]-[A-Za-z0-9-]{12,}|AKIA[A-Z0-9]{16})\b',
                 '[REDACTED_TOKEN]',value)
    return value[:limit]


def plain(path):
    path=Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (path,*path.parents)),'PATH_SYMLINK')
    return path


def read_file(path,limit=1024*1024):
    path=plain(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        before=os.fstat(f.fileno());require(stat.S_ISREG(before.st_mode) and before.st_size<=limit,'FILE_BOUND')
        raw=f.read(limit+1);after=os.fstat(f.fileno())
    require(len(raw)<=limit and (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'FILE_CHANGED')
    return raw,after


def proc_read(path,limit=65536):
    # Call sites use only fixed /proc paths or the explicitly pinned process ids.
    require(str(path).startswith('/proc/'),'PROC_SCOPE')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:raw=f.read(limit+1)
    require(len(raw)<=limit,'PROC_BOUND')
    return raw.decode('utf-8','replace')


def process(pid):
    try:
        fields=proc_read('/proc/'+str(pid)+'/stat',16384).rsplit(') ',1)[1].split()
        return {'pid':pid,'ppid':int(fields[1]),'start_ticks':int(fields[19]),'state':fields[0]}
    except (OSError,ValueError,IndexError,DiagnosticHold):return None


def current_processes():
    director=process(DIRECTOR['pid'])
    require(director and director['start_ticks']==DIRECTOR['start_ticks'] and director['state'] in ('R','S','D','I'),'DIRECTOR_CHANGED')
    rows=[]
    for expected in WORKERS:
        found=process(expected['pid'])
        require(found and found['start_ticks']==expected['start_ticks'] and found['ppid']==director['pid']
                and found['state'] in ('R','S','D','I'),'WORKER_CHANGED')
        rows.append(found)
    return {'director':director,'workers':rows,'same_three_pid_start_ticks':True}


def source_census(root,config):
    policy=config['project_executor']['roots']['NOX_PROJECT_SOURCE'];path=Path(policy['path'])
    require(path==root/'projects/owner_executor/source_workspace','SOURCE_ROOT')
    names=policy['allowed_paths'];require(isinstance(names,list) and len(names)==len(set(names))==28,'SOURCE_ALLOWED_SET')
    files={}
    for name in sorted(names):
        require(isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_./-]+',name) and not name.startswith('/')
                and all(part and part not in ('.','..') and not part.startswith('.') for part in name.split('/')),'SOURCE_NAME')
        raw,info=read_file(path/name,2*1024*1024)
        files[name]={'sha256':digest(raw),'size':len(raw),'mode':stat.S_IMODE(info.st_mode)}
    pin=digest(encoded(files));require(pin==EXPECTED_SOURCE_CENSUS,'SOURCE_CENSUS_CHANGED')
    return {'count':len(files),'files_sha256':pin,'matches_expected':True}


UNSHARE=Path('/usr/bin/unshare')
UNSHARE_SHA='9f41a192393e7a05b843ae51bd187a76e09482392d37275d796f8881db97dde6'
PYTHON=Path('/usr/bin/python3.12')
PYTHON_SHA='1396795801a792fc4a0faa7a47762751e85c76293b4fd925f32c49e27c0f978a'
PREFIX='NOX_OWN_NAMESPACE_PROBE_V1:'
CHILD_CODE=r'''
import hashlib,json,os,re
from pathlib import Path
pid=os.getpid()
raw=Path('/proc/self/stat').read_bytes()
if len(raw)>16384:raise RuntimeError('OWN_STAT_BOUND')
line=raw.decode('utf-8','strict');fields=line.rsplit(') ',1)[1].split()
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot):raise RuntimeError('BOOT_ID_SHAPE')
result={'schema':'NOX_OWN_NAMESPACE_PROBE_V1','pid':pid,'ppid':os.getppid(),
        'uid':os.getuid(),'euid':os.geteuid(),'stat_pid':int(line.split(' ',1)[0]),
        'stat_start_ticks':int(fields[19]),'real_boot_id_read':True,
        'boot_id_sha256':hashlib.sha256(boot.encode()).hexdigest(),
        'namespace_ids':{name:os.readlink('/proc/self/ns/'+name) for name in ('user','pid','mnt')}}
print('NOX_OWN_NAMESPACE_PROBE_V1:'+json.dumps(result,sort_keys=True,separators=(',',':')),flush=True)
'''


def own_namespaces():
    return {name:os.readlink('/proc/'+str(os.getpid())+'/ns/'+name) for name in ('user','pid','mnt')}

def pinned_executable(path,pin):
    raw,info=read_file(path,16*1024*1024)
    require(digest(raw)==pin and stat.S_IMODE(info.st_mode)==0o755
            and not info.st_mode&(stat.S_ISUID|stat.S_ISGID),'EXECUTABLE_PIN_OR_MODE')
    return {'path':str(path),'sha256':pin,'mode':'0o755','setuid':False,'setgid':False}

def probe():
    binaries={'unshare':pinned_executable(UNSHARE,UNSHARE_SHA),'python':pinned_executable(PYTHON,PYTHON_SHA)}
    before_ns=own_namespaces();parent_pid=os.getpid()
    # Unshare must create a fresh mount namespace before mounting a fresh proc.
    # No host proc bind and no /usr/bin/mount (which is SUID on this host).
    argv=[str(UNSHARE),'--user','--map-root-user','--mount','--pid','--fork',
          '--kill-child=KILL','--propagation','private','--mount-proc=/proc','--',
          str(PYTHON),'-I','-S','-B','-c',CHILD_CODE]
    def child_limits():
        resource.setrlimit(resource.RLIMIT_CPU,(2,2))
        resource.setrlimit(resource.RLIMIT_AS,(128*1024*1024,128*1024*1024))
        resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
        libc=ctypes.CDLL(None,use_errno=True)
        if libc.prctl(1,signal.SIGKILL,0,0,0)!=0 or os.getppid()!=parent_pid:os._exit(91)
    started=time.monotonic();output=bytearray();reason=None;cleanup='OWN_PROCESS_EXITED'
    child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        close_fds=True,start_new_session=True,preexec_fn=child_limits,
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'})
    own=None;selector=selectors.DefaultSelector()
    deadline=started+6.0
    try:
        own=process(child.pid)
        require(own and own['ppid']==parent_pid,'OWN_CHILD_IDENTITY')
        selector.register(child.stdout,selectors.EVENT_READ)
        while True:
            if time.monotonic()>=deadline:reason='BOUNDED_PROBE_TIMEOUT';break
            for key,_ in selector.select(.05):
                chunk=os.read(key.fileobj.fileno(),4096)
                if chunk:
                    output.extend(chunk)
                    if len(output)>16384:reason='BOUNDED_PROBE_OUTPUT_LIMIT';break
                else:selector.unregister(key.fileobj)
            if reason or (child.poll() is not None and not selector.get_map()):break
    finally:
        if child.poll() is None:
            current=process(child.pid)
            if own is None and current and current['ppid']==parent_pid:own=current
            require(current and current['start_ticks']==own['start_ticks'] and current['ppid']==parent_pid
                    and os.getpgid(child.pid)==child.pid,'OWN_CHILD_CLEANUP_IDENTITY')
            os.killpg(child.pid,signal.SIGKILL);cleanup='ONLY_OWN_VERIFIED_PROCESS_GROUP_KILLED'
        child.wait(timeout=1.0);selector.close();child.stdout.close()
    elapsed=time.monotonic()-started
    require(elapsed<=8.0,'PROBE_BOUND_EXCEEDED')
    require(own_namespaces()==before_ns,'PARENT_NAMESPACE_CHANGED')
    text=bytes(output[:16384]).decode('utf-8','replace')
    records=[]
    for line in text.splitlines():
        if line.startswith(PREFIX):
            try:records.append(json.loads(line[len(PREFIX):]))
            except ValueError:reason='MALFORMED_PROBE_RECORD'
    child_record=records[0] if len(records)==1 else None
    supported=(reason is None and child.returncode==0 and isinstance(child_record,dict)
        and child_record.get('schema')=='NOX_OWN_NAMESPACE_PROBE_V1'
        and child_record.get('pid')==child_record.get('stat_pid')==1
        and type(child_record.get('stat_start_ticks')) is int and child_record['stat_start_ticks']>0
        and child_record.get('real_boot_id_read') is True
        and re.fullmatch(r'[0-9a-f]{64}',str(child_record.get('boot_id_sha256')))
        and all(isinstance(child_record.get('namespace_ids',{}).get(name),str)
                and child_record['namespace_ids'][name]!=before_ns[name] for name in before_ns))
    denied=child.returncode!=0 and bool(re.search(r'(?i)operation not permitted|permission denied|EPERM|EACCES',text))
    state='ISOLATED_USER_MOUNT_PID_PROC_PROVEN' if supported else ('NAMESPACE_DENIED_NO_ESCALATION' if denied else (reason or 'NAMESPACE_PROBE_NOT_PROVEN'))
    return {'schema':'NOX_BOUNDED_USERNS_PROBE_V1','state':state,'namespace_support_proven':bool(supported),
            'returncode':child.returncode,'elapsed_seconds':round(elapsed,3),'output_bytes':len(output),
            'output_sha256':digest(bytes(output)),'sanitized_output':safe_text(text,16384),
            'child_record':child_record,'owned_process':own,'owned_process_group':child.pid,'cleanup':cleanup,
            'parent_namespaces_before':before_ns,'parent_namespaces_after':own_namespaces(),
            'binaries':binaries,'private_propagation_requested':True,'fresh_proc_mount_requested':True,
            'host_proc_bound':False,'suid_mount_executed':False,'host_policy_changes':0,
            'fixed_environment_without_inherited_credentials':True,'attempt_count':1,
            'followup_or_escalation_attempted':False,'native_code_sandbox_acceptance_proven':False}

def run(root=ROOT):
    root=plain(root);started=time.time();raw,_=read_file(root/'config/owner_native_subagents.json')
    require(digest(raw)==EXPECTED_CONFIG,'CONFIG_CHANGED');config=json.loads(raw)
    require(config['project_executor']['sandbox']['python']==str(PYTHON)
            and config['project_executor']['sandbox']['python_sha256']==PYTHON_SHA,'PYTHON_CONFIG_PIN')
    before=current_processes();census=source_census(root,config)
    result=probe()
    require(read_file(root/'config/owner_native_subagents.json')[0]==raw,'CONFIG_CHANGED_DURING_PROBE')
    require(source_census(root,config)==census,'SOURCE_CHANGED_DURING_PROBE')
    after=current_processes()
    return {'schema':'NOX_PROJECT_USERNS_CAPABILITY_INSPECT_V1','state':'BOUNDED_PROBE_COMPLETE',
            'started_at':started,'finished_at':time.time(),'config_sha256':EXPECTED_CONFIG,'source_census':census,
            'processes_before':before,'processes_after':after,'probe':result,
            'source_writes':0,'config_writes':0,'queue_writes':0,'service_changes':0}

def main():
    try:result=run()
    except Exception as exc:
        result={'schema':'NOX_PROJECT_USERNS_CAPABILITY_INSPECT_V1',
                'state':str(exc) if isinstance(exc,DiagnosticHold) else 'HOLD_USERNS_PROBE_'+type(exc).__name__,
                'source_writes':0,'config_writes':0,'queue_writes':0,'service_changes':0}
        print('NOX_MAINT_SCOPE_PROJECT_USERNS_PROBE='+encoded(result).decode(),flush=True)
        raise SystemExit(2)
    print('NOX_MAINT_SCOPE_PROJECT_USERNS_PROBE='+encoded(result).decode(),flush=True)
    print('NOX_MAINT_INSPECT_COMPLETE=true',flush=True)

if __name__=='__main__':main()
