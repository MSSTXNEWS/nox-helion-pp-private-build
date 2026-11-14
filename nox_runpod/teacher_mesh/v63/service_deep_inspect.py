"""Deep but read-only supervisor config/exit/log diagnosis on existing NOX.

Inspect only exact five named service configs, no raw log text or credentials
leave host. This is not a restart agent and does not change any process.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as connection

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,shlex,configparser,subprocess,json,re,hashlib
from pathlib import Path
SERVICES=(
 'nox-agent-tuner-t858u','nox-downloads-t802u','nox-teacher-bringup',
 'nox-teacher-serve-t811u','nox-train-worm-t811u'
)
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V63_DEEP_SERVICE_CAUSE_V1')
CONFIGS=('/etc/supervisor/conf.d/nox-t855u.conf',
         '/etc/supervisor/conf.d/nox-t802u.conf',
         '/etc/supervisor/conf.d/nox-t811u.conf')
LOGROOTS=('/root/nox/logs','/root/nox/var/log','/var/log/supervisor','/root/nox')
def run(args,secs=7):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=secs,check=False)
        return p.returncode,p.stdout[-35000:],p.stderr[-5000:]
    except (OSError,subprocess.TimeoutExpired):
        return -1,'',''

def cfg_for(service):
    for name in CONFIGS:
        p=Path(name)
        if not p.is_file():continue
        conf=configparser.ConfigParser(interpolation=None,strict=False)
        try: conf.read(name)
        except (OSError,configparser.Error):continue
        for section in conf.sections():
            if section.startswith(('program:','group:')):
                actual=section.split(':',1)[1]
                if actual==service:
                    return p,dict(conf.items(section))
    return None,{}

def safe_path(p):
    try:
        path=Path(p)
        if not path.is_absolute():return None
        resolved=path.resolve(strict=False)
        if any(resolved.is_relative_to(Path(parent)) for parent in LOGROOTS):
            return resolved
    except (OSError,ValueError):pass
    return None

def safe_module(log):
    names=[]
    for m in re.finditer(r"no module named ['\"]([a-zA-Z0-9_\.]{1,80})['\"]",log,re.I):
        if m.group(1) not in names:names.append(m.group(1))
    return names[:5]

def error_classes(log):
    s=log.lower()
    probes={
        'ImportError':r'modulenotfounderror|importerror|no module named',
        'MissingExecutable':r'command not found|executable not found|cannot find command',
        'MissingPath':r'filenotfounderror|no such file or directory',
        'NoSpace':r'no space left on device|enospc|quota exceeded',
        'GpuOOM':r'cuda out of memory|outofmemoryerror',
        'RamOOM':r'killed process|memoryerror|oom-kill',
        'CudaMismatch':r'no kernel image|unsupported architecture|sm_70.*unsupported',
        'AuthFailure':r'401 unauthorized|403 forbidden|authentication failed|permission denied',
        'PortConflict':r'address already in use|eaddrinuse',
        'Network':r'connection refused|connection reset|network is unreachable',
        'CleanStop':r'graceful shutdown|exit code 0|finished successfully|completed successfully',
        'PreflightHold':r'hold_|preflight failed|insufficient disk|reserve',
        'Failure':r'traceback|error:|exception|failed',
        'Killed':r'sigterm|sigkill|stopped by user',
    }
    return [key for key,pattern in probes.items() if re.search(pattern,s,re.I)]

def read_log(service,opts):
    entries=[]
    for channel in ('stderr','stdout'):
        rc,out,err=run(['supervisorctl','tail','-5000',service,channel])
        if rc==0 and out:
            entries.append((channel,out))
        else:
            rc,out,err=run(['supervisorctl','tail',service,channel])
            if rc==0 and out:entries.append((channel,out))
    for k in ('stderr_logfile','stdout_logfile'):
        raw=opts.get(k)
        if not raw:continue
        candidate=safe_path(raw)
        if candidate is None:continue
        try:
            if not candidate.is_file() or candidate.stat().st_size>100000000:continue
            with candidate.open('rb') as fd:
                fd.seek(max(0,candidate.stat().st_size-16000))
                data=fd.read(16000).decode('utf-8',errors='replace')
            entries.append((k,data))
        except (OSError,ValueError):continue
    if not entries:return None,[],[]
    merged='\n'.join(x[1][-7500:] for x in entries)[-24000:]
    return hashlib.sha256(merged.encode()).hexdigest(),error_classes(merged),safe_module(merged)

def cmd_info(command,dir_):
    if not command:return {'present':False}
    try:parts=shlex.split(command)
    except ValueError:return {'present':True,'parseable':False}
    if not parts:return {'present':False}
    exe=Path(parts[0]).name
    result={'present':True,'executable':exe,'executable_resolved':bool(
       os.path.isfile(parts[0]) or __import__('shutil').which(parts[0]))}
    # Only inspect program file, never command arguments/environment.
    scripts=[x for x in parts[1:7] if x.lower().endswith(('.py','.sh')) and not x.startswith('-')]
    if scripts:
        p=Path(scripts[0])
        if not p.is_absolute() and dir_:p=Path(dir_)/p
        try:
            result['script_basename']=p.name[:75]
            result['script_exists']=p.is_file()
            if p.is_file() and p.stat().st_size<1200000 and not p.is_symlink():
                result['script_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:result['script_exists']=False
    return result

def proc_supervisor(service):
    # Status is read, not used to mutate any process.
    rc,out,err=run(['supervisorctl','status',service])
    line=out.strip().splitlines()[0] if out.strip() else ''
    cols=line.split()
    return {
        'status_rc':rc,
        'state':cols[1] if len(cols)>1 else 'UNKNOWN',
        'pid':int(cols[3].rstrip(',')) if len(cols)>3 and cols[2]=='pid' and cols[3].rstrip(',').isdigit() else None,
    }

for service in SERVICES:
    cfg,opts=cfg_for(service)
    log_sha,log_class,missing_modules=read_log(service,opts)
    command=cmd_info(opts.get('command',''),opts.get('directory',''))
    state=proc_supervisor(service)
    report={
        'name':service,'state':state['state'],'pid':state['pid'],
        'config_found':cfg is not None,'config_sha256':hashlib.sha256(cfg.read_bytes()).hexdigest() if cfg else None,
        'autostart':opts.get('autostart','unknown'),
        'autorestart':opts.get('autorestart','unknown'),
        'startsecs':opts.get('startsecs','unknown'),
        'exitcodes':opts.get('exitcodes','unknown'),
        'command':command,
        'log_sha256':log_sha,
        'failure_classes':log_class,
        'missing_modules':missing_modules,
        'log_text_exported':False,
    }
    print('NATIVE_SERVICE_DEEP='+json.dumps(report,ensure_ascii=False,separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main()->int:
    connection.REMOTE=REMOTE
    ok=False
    try:ok=connection.probe()
    except Exception as e:
        # Do not export hostnames, keys, stdout or exception internals.
        msg=str(e)
        if msg.startswith("HOLD_") and len(msg)<100 and all(ch.isupper() or ch.isdigit() or ch=="_" for ch in msg):
            print("NOX_V63_DEEP="+msg)
        else:
            print("NOX_V63_DEEP=HOLD_NATIVE_"+type(e).__name__)
    finally:
        try:
            if not connection.cleanup():ok=False
        except Exception:
            print("NOX_V63_DEEP=HOLD_TEMP_SSH_KEY")
            ok=False
    return 0 if ok else 2

if __name__=="__main__":raise SystemExit(main())
