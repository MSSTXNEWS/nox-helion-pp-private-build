#!/usr/bin/env python3
"""Read only one failed source-test attempt and bounded namespace metadata.

No namespace creation, mounts, subprocesses, environment reads, service calls,
queue writes, source writes or package installs are performed by this entry.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import time

ROOT=Path('/root/nox')
EXPECTED_CONFIG='085fa4e3c8c96ae4ffb952dee53bb0d8bda0a1c50416a4d8a365017d043e95be'
EXPECTED_SOURCE_CENSUS='f9d914745e8b42bc7d8f45bc5dd0804291a86eacab4edd1cd2dc42d4c17f583f'
TASK='1A03.project.cursor_admission.owner_rescue.20261118'
CLAIM='3110182475f1ae4523267ca5'
PLAN='379d1c5b50e42fb50165ce1fbe904cf47b1b45b3747878c60f9b1208d6e13e23'
JOURNAL_SHA='0865fada5517404155a31cbc06eebdb332490c699db2a9234dcb5a3fc0bc2c1d'
TESTS_SHA='6c5cb6f1464a827857753d0b63780d3d2a6c4cacc3bd480b40b539af4a2fe533'
FULL_LOG_SHA='cf0c7ec09c9a60990860a4a02cca7633bdc062dd95371ff32f9daab62e4de100'
FULL_LOG_BYTES=26895
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

def optional_text(path,limit=4096):
    try:return {'available':True,'text':safe_text(proc_read(path,limit),limit).strip()}
    except (OSError,DiagnosticHold) as exc:return {'available':False,'error_type':type(exc).__name__}

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

def analyze_journal(raw):
    require(digest(raw)==JOURNAL_SHA,'JOURNAL_PIN')
    journal=json.loads(raw)
    require(journal.get('task_id')==TASK and journal.get('claim')==CLAIM and journal.get('plan_sha256')==PLAN
            and journal.get('state')=='FAILED_TESTS' and journal.get('project_source_changed') is False,'JOURNAL_SCOPE')
    tests=journal.get('tests') or {};require(digest(encoded(tests))==TESTS_SHA==journal.get('tests_sha256'),'TEST_REPORT_PIN')
    require(tests.get('log_sha256')==FULL_LOG_SHA and tests.get('log_bytes')==FULL_LOG_BYTES
            and tests.get('tests_run')==30 and tests.get('failures')==13 and tests.get('errors')==12
            and tests.get('skipped')==0 and tests.get('passed') is False,'FAILED_TEST_FACTS')
    tail=tests.get('output');require(isinstance(tail,str) and len(tail.encode())<=8192,'STORED_TAIL_BOUND')
    raw_tail=tail.encode();sanitized=safe_text(tail)
    full_available=len(raw_tail)==FULL_LOG_BYTES and digest(raw_tail)==FULL_LOG_SHA
    first=sanitized.find('Traceback (most recent call last):')
    exception_lines=re.findall(r'(?m)^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception):[^\n]*)',sanitized)
    return {'journal_sha256':JOURNAL_SHA,'journal_pin_verified':True,'tests_sha256':TESTS_SHA,
            'test_report_pin_verified':True,'task_id':TASK,'claim':CLAIM,'plan_sha256':PLAN,
            'tests_run':30,'failures':13,'errors':12,'skipped':0,'passed':False,
            'full_log_declared_sha256':FULL_LOG_SHA,'full_log_declared_bytes':FULL_LOG_BYTES,
            'full_log_bytes_persisted':full_available,'full_log_bytes_pin_verified':True if full_available else None,
            'stored_output_bytes':len(raw_tail),'stored_output_sha256':digest(raw_tail),
            'output_scope':'PERSISTED_LAST_8192_BYTES_NOT_FULL_LOG',
            'full_log_unavailable_reason':None if full_available else 'INSTALLED_RUNNER_RETURNS_ONLY_TAIL_AND_FULL_STREAM_DIGEST',
            'sanitized_stored_output':sanitized,
            'exception_lines_within_stored_tail':exception_lines[:24],
            'first_persisted_traceback_scope':'FIRST_WITHIN_STORED_TAIL_NOT_FIRST_FULL_LOG_ERROR',
            'first_persisted_traceback':sanitized[first:first+2400] if first>=0 else None,
            'failed_tests':[safe_text(x,240) for x in tests.get('failed_tests',[])[:64]],
            'sandbox':tests.get('sandbox')}

def parse_mountinfo(text):
    allowed={'/','/proc','/proc/sys','/proc/sys/kernel/random','/sys','/sys/fs/cgroup'}
    rows=[]
    for line in text.splitlines():
        parts=line.split();sep=parts.index('-') if '-' in parts else -1
        if len(parts)<10 or sep<6 or parts[4] not in allowed:continue
        rows.append({'mountpoint':parts[4],'filesystem':parts[sep+1],
                     'options':[x for x in parts[5].split(',') if x in ('ro','rw','nosuid','nodev','noexec','relatime','noatime')],
                     'propagation':[x for x in parts[6:sep] if re.fullmatch(r'(?:shared|master|propagate_from):[0-9]+|unbindable',x)]})
    return rows

def system_file(path):
    path=Path(path)
    try:
        resolved=path.resolve(strict=True)
        require(str(resolved).startswith(('/usr/bin/','/usr/sbin/','/usr/lib/','/lib/','/bin/','/sbin/')),'SYSTEM_FILE_SCOPE')
        raw,info=read_file(resolved,16*1024*1024)
        return {'path':str(path),'resolved_path':str(resolved),'available':True,'size':len(raw),'sha256':digest(raw),
                'mode':oct(stat.S_IMODE(info.st_mode)),'setuid':bool(info.st_mode&stat.S_ISUID),
                'setgid':bool(info.st_mode&stat.S_ISGID),'elf':raw.startswith(b'\x7fELF')}
    except (OSError,DiagnosticHold) as exc:return {'path':str(path),'available':False,'error_type':type(exc).__name__}

def capability_metadata():
    pid=os.getpid();prefix='/proc/'+str(pid)
    status={}
    for line in proc_read(prefix+'/status').splitlines():
        key,sep,value=line.partition(':')
        if sep and key in ('Uid','Gid','CapInh','CapPrm','CapEff','CapBnd','CapAmb','NoNewPrivs','Seccomp','Seccomp_filters','NSpid'):
            status[key]=value.strip()
    wanted_caps={'CAP_SETGID':6,'CAP_SETUID':7,'CAP_SYS_CHROOT':18,'CAP_SYS_PTRACE':19,'CAP_SYS_ADMIN':21,'CAP_SYS_RESOURCE':24}
    cap_checks={field:{name:bool(int(status[field],16)&(1<<bit)) for name,bit in wanted_caps.items()}
                for field in ('CapEff','CapBnd') if re.fullmatch(r'[0-9a-fA-F]{1,32}',status.get(field,''))}
    tools={}
    for name in ('bwrap','unshare','mount'):
        path=shutil.which(name,path='/usr/sbin:/usr/bin:/sbin:/bin')
        tools[name]=system_file(path) if path else {'available':False}
    try:libc_version=os.confstr('CS_GNU_LIBC_VERSION')
    except (OSError,ValueError):libc_version=None
    libraries={}
    for name in ('libc.so.6','libselinux.so.1','libcap.so.2','libpcre2-8.so.0'):
        choices=[Path(directory)/name for directory in ('/usr/lib/x86_64-linux-gnu','/lib/x86_64-linux-gnu','/usr/lib64','/lib64')]
        selected=next((p for p in choices if p.exists()),None)
        libraries[name]=system_file(selected) if selected else {'available':False}
    namespaces={}
    for name in ('user','pid','mnt'):
        try:namespaces[name]=os.readlink(prefix+'/ns/'+name)
        except OSError as exc:namespaces[name]={'error_type':type(exc).__name__}
    return {'uid':os.getuid(),'euid':os.geteuid(),'gid':os.getgid(),'egid':os.getegid(),
            'status':status,'selected_capabilities':cap_checks,'namespace_ids':namespaces,
            'uid_map':optional_text(prefix+'/uid_map'),'gid_map':optional_text(prefix+'/gid_map'),
            'userns_sysctls':{path:optional_text(path) for path in (
                '/proc/sys/kernel/unprivileged_userns_clone','/proc/sys/user/max_user_namespaces',
                '/proc/sys/kernel/apparmor_restrict_unprivileged_userns')},
            'security_profile':optional_text(prefix+'/attr/current'),'tools':tools,
            'libc_version':libc_version,'libraries':libraries,
            'relevant_mounts':parse_mountinfo(proc_read(prefix+'/mountinfo',512*1024)),
            'namespace_creation_attempted':False,'namespace_support_proven':False,
            'network_calls':0,'mount_calls':0,'subprocesses_started':0,'environment_read':False}

def run(root=ROOT):
    root=plain(root);started=time.time();config_raw,_=read_file(root/'config/owner_native_subagents.json')
    require(digest(config_raw)==EXPECTED_CONFIG,'CONFIG_CHANGED');config=json.loads(config_raw)
    require(config.get('execution_mode')=='NATIVE_PROJECT_V1','MODE')
    processes=current_processes();census=source_census(root,config)
    state_root=Path(config['project_executor']['state_root'])
    require(state_root==root/'state/dispatcher/project_executor/run','STATE_ROOT')
    attempt=state_root/'attempts'/digest(TASK.encode())/CLAIM/PLAN
    journal_raw,_=read_file(attempt/'journal.json',256*1024);failure=analyze_journal(journal_raw)
    spec_raw,_=read_file(attempt/'test-spec.json',65536);test_spec=json.loads(spec_raw)
    require(test_spec.get('backend')=='chroot_seccomp' and test_spec.get('rootfs')==str(attempt/'rootfs'),'ATTEMPT_SANDBOX_SCOPE')
    attempt_proc=attempt/'rootfs/proc'
    failure.update(journal_path=str(attempt/'journal.json'),test_spec_sha256=digest(spec_raw),
        attempted_sandbox={k:test_spec.get(k) for k in ('backend','uid','gid','memory_mb','worker_pid')},
        isolated_proc_path_exists=os.path.lexists(attempt_proc),isolated_proc_path_is_symlink=attempt_proc.is_symlink())
    runtime={}
    for name in ('owner_project_executor.py','owner_project_test_runner.py'):
        raw,_=read_file(root/'scripts'/name,256*1024);pin=digest(raw)
        require(pin==config['module_pins'][name],'RUNTIME_SOURCE_CHANGED');runtime[name]=pin
    caps=capability_metadata()
    require(read_file(root/'config/owner_native_subagents.json')[0]==config_raw,'CONFIG_CHANGED_DURING_READ')
    require(source_census(root,config)==census,'SOURCE_CHANGED_DURING_READ')
    after=current_processes()
    return {'schema':'NOX_PROJECT_NAMESPACE_DIAGNOSTIC_V1','state':'READ_ONLY_DIAGNOSTIC_COMPLETE',
            'started_at':started,'finished_at':time.time(),'config_sha256':EXPECTED_CONFIG,'source_census':census,
            'processes_before':processes,'processes_after':after,'runtime_pins':runtime,
            'failure':failure,'capability_metadata':caps,'native_writes':0,'service_changes':0,
            'next_namespace_probe_authorized_or_executed':False}

def main():
    try:result=run()
    except Exception as exc:
        result={'schema':'NOX_PROJECT_NAMESPACE_DIAGNOSTIC_V1','state':str(exc) if isinstance(exc,DiagnosticHold)
                else 'HOLD_NAMESPACE_INSPECT_'+type(exc).__name__,'native_writes':0,'service_changes':0}
        print('NOX_MAINT_SCOPE_PROJECT_NAMESPACE_DIAGNOSTIC='+encoded(result).decode(),flush=True)
        raise SystemExit(2)
    print('NOX_MAINT_SCOPE_PROJECT_NAMESPACE_DIAGNOSTIC='+encoded(result).decode(),flush=True)
    print('NOX_MAINT_INSPECT_COMPLETE=true',flush=True)

if __name__=='__main__':main()
