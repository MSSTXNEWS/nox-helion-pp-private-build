#!/usr/bin/env python3
"""Read-only browser startup and media progress audit; raw logs stay private.

No package installation, backend/login request, service restart or media job
launch occurs. Only the diagnostic's own finite browser child may be stopped.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import time

ROOT=Path('/root/nox')
AREA=ROOT/'browser_qa'
STATE=ROOT/'state/owner_browser_diagnostic'
PYTHON=AREA/'venv/bin/python'
PLAYWRIGHT_PIN='1.65.2'
ASSETS={'sdxl_lightning_4step.safetensors':('checkpoints',6938040682),
        'wan2.1_t2v_1.3B_fp16.safetensors':('diffusion_models',2838303560),
        'umt5_xxl_fp8_e4m3fn_scaled.safetensors':('text_encoders',6735906897),
        'wan_2.1_vae.safetensors':('vae',253815318)}
SHA=re.compile(r'^[0-9a-f]{64}$')
LIB=re.compile(r'^lib[A-Za-z0-9_+.-]{1,90}\.so(?:\.[0-9]{1,5}){0,4}$')


def emit(kind,value):
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},separators=(',',':'),allow_nan=False),flush=True)


def plain(path):
    path=Path(path)
    if any(p.is_symlink() for p in (*path.parents,path)):
        raise RuntimeError('HOLD_DIAGNOSTIC_SYMLINK')
    return path


def read(path,limit=65536,tail=False):
    path=plain(path)
    fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):raise RuntimeError('HOLD_DIAGNOSTIC_FILE_TYPE')
        if info.st_size>limit:
            if not tail:raise RuntimeError('HOLD_DIAGNOSTIC_FILE_SIZE')
            stream.seek(info.st_size-limit)
            stream.readline(limit+1)
        return stream.read(limit+1)[:limit]


def read_json(path,limit=65536):
    value=json.loads(read(path,limit))
    if not isinstance(value,dict):raise RuntimeError('HOLD_DIAGNOSTIC_JSON_SCHEMA')
    return value


def private(path,data):
    path=plain(path)
    if len(data)>262144:raise RuntimeError('HOLD_DIAGNOSTIC_OUTPUT_SIZE')
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())


def bounded_command(argv,env,timeout=35,limit=196608):
    process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             env=env,start_new_session=True,close_fds=True)
    selector=selectors.DefaultSelector();parts={'stdout':bytearray(),'stderr':bytearray()}
    for label,stream in (('stdout',process.stdout),('stderr',process.stderr)):
        os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,label)
    deadline=time.monotonic()+timeout;reason=None
    try:
        while selector.get_map():
            if time.monotonic()>=deadline:reason='TIMEOUT';break
            for key,_ in selector.select(min(0.2,max(0,deadline-time.monotonic()))):
                block=os.read(key.fileobj.fileno(),16384)
                if not block:selector.unregister(key.fileobj);continue
                if sum(map(len,parts.values()))+len(block)>limit:reason='OUTPUT_LIMIT';break
                parts[key.data].extend(block)
            if reason:break
        if reason and process.poll() is None:
            # Still our unreaped direct child: this PID cannot have been reused.
            os.killpg(process.pid,signal.SIGKILL)
        process.wait(timeout=3)
    finally:
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=3)
        selector.close();process.stdout.close();process.stderr.close()
    return {'returncode':process.returncode,'bounded_stop':reason,
            'stdout':bytes(parts['stdout']),'stderr':bytes(parts['stderr'])}


def missing_libraries(raw):
    text=raw.decode(errors='replace') if isinstance(raw,bytes) else str(raw)
    found=set()
    for pattern in (r'^\s*(lib[^\s/:]{1,110})\s+=>\s+not found\s*$',
                    r'\b(lib[^\s/:]{1,110}):\s+cannot open shared object file'):
        for value in re.findall(pattern,text,re.M):
            if LIB.fullmatch(value):found.add(value)
    return sorted(found)[:32]


def failure_tags(raw):
    text=raw.decode(errors='replace') if isinstance(raw,bytes) else str(raw)
    checks={'MISSING_SHARED_LIBRARY':r'error while loading shared libraries|=> not found|cannot open shared object file',
            'MISSING_EXECUTABLE':r"Executable doesn't exist|ENOENT",
            'SANDBOX_FAILURE':r'No usable sandbox|Running as root without --no-sandbox',
            'PROCESS_OR_THREAD_LIMIT':r'pthread_create.*Resource temporarily unavailable|fork.*Resource temporarily unavailable',
            'FILESYSTEM_SPACE':r'No space left on device',
            'DISPLAY_REQUIRED':r'Missing X server|cannot open display',
            'LOADER_VERSION_MISMATCH':r"version [`']GLIBC[^\n]+not found",
            'PROCESS_CRASH':r'SIGSEGV|SIGILL|signal=SIG'}
    return sorted(name for name,pattern in checks.items() if re.search(pattern,text,re.I))


def resources():
    result={}
    for name in ('memory.current','memory.max','pids.current','pids.max'):
        try:
            value=read(Path('/sys/fs/cgroup')/name,256).decode().strip()
            result[name]=int(value) if value.isdigit() else None
        except (OSError,ValueError,RuntimeError):result[name]=None
    try:
        result['memory_events']={k:int(v) for k,v in (line.split() for line in read('/sys/fs/cgroup/memory.events',4096).decode().splitlines())
                                 if k in ('oom','oom_kill','max','high') and v.isdigit()}
    except (OSError,ValueError,RuntimeError):pass
    for name,path in (('disk',ROOT),('shm',Path('/dev/shm')),('tmp',Path('/tmp'))):
        result[name+'_free_bytes']=shutil.disk_usage(path).free
    try:
        os_release=Path('/etc/os-release')
        if os_release.is_symlink():os_release=Path('/usr/lib/os-release')
        source=read(os_release,8192).decode()
        for key in ('ID','VERSION_ID'):
            match=re.search('^'+key+r'=["\']?([A-Za-z0-9._-]{1,50})',source,re.M)
            if match:result['os_'+key.lower()]=match[1]
    except (OSError,ValueError,RuntimeError):pass
    return result


CHILD = r'''
import asyncio,importlib.metadata,json,os,re,shutil,sys
os.environ.pop('DEBUG',None);os.environ.pop('PWDEBUG',None)
os.nice(10)
if hasattr(os,'sched_getaffinity'):
 cpus=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,set(cpus[:2]))
def emit(value):print('NOX_BROWSER_DIAG='+json.dumps(value,separators=(',',':')),flush=True)
version=importlib.metadata.version('playwright')
emit({'phase':'package','version':version,'python':sys.version.split()[0]})
if version!='1.65.2':raise SystemExit(3)
async def run():
 from playwright.async_api import async_playwright
 async with async_playwright() as runtime:
  arguments=['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader',
             '--enable-unsafe-swiftshader','--disable-background-networking','--disable-extensions']
  child_env={key:os.environ[key] for key in ('PATH','LANG','LC_ALL','LD_LIBRARY_PATH') if key in os.environ}
  child_env['CUDA_VISIBLE_DEVICES']=''
  launch={'headless':True,'args':arguments,'env':child_env,'timeout':20000}
  candidates=[shutil.which(name) for name in ('chromium','chromium-browser','google-chrome','google-chrome-stable')]
  candidates=[path for path in candidates if path]
  if candidates:launch['executable_path']=candidates[0]
  emit({'phase':'launch','system_browser_selected':bool(candidates),'backend_accessed':False})
  try:
   browser=await runtime.chromium.launch(**launch)
  except Exception as exc:
   sys.stderr.write(str(exc)[:100000]);sys.stderr.flush()
   emit({'phase':'result','state':'LAUNCH_FAILED','exception_type':type(exc).__name__})
   return 2
  try:
   context=await browser.new_context(accept_downloads=False,service_workers='block')
   try:
    await context.route('**/*',lambda route:route.abort())
    page=await context.new_page()
    await page.goto('about:blank',timeout=5000)
    value=await page.evaluate("() => {const c=document.createElement('canvas');const g=c.getContext('webgl2')||c.getContext('webgl');return {webgl:!!g};}")
    emit({'phase':'result','state':'BLANK_BROWSER_STARTED','webgl':value.get('webgl') is True,'backend_accessed':False})
   finally:await context.close()
  finally:await browser.close()
 return 0
try:raise SystemExit(asyncio.run(asyncio.wait_for(run(),30)))
except Exception as exc:
 sys.stderr.write(str(exc)[:100000]);emit({'phase':'result','state':'DIAGNOSTIC_FAILED','exception_type':type(exc).__name__});raise SystemExit(2)
'''


def media_progress():
    result={'state':'UNKNOWN','restarted':False,'raw_log_exported':False,'files':[]}
    try:
        job=read_json(ROOT/'state/owner_media/prepare_job.json',16000)
        request=job.get('request')
        if not isinstance(request,str) or not re.fullmatch(r'[0-9]{1,24}',request):return result
        result.update(state='JOB_OBSERVED',request=request)
        for key in ('installer_sha256','runtime_sha256','worker_sha256'):
            if isinstance(job.get(key),str) and SHA.fullmatch(job[key]):result[key]=job[key]
        pid=job.get('pid');alive=False
        if type(pid) is int and pid>0:
            try:
                folder=Path('/proc')/str(pid)
                fields=read(folder/'stat',8192).decode().split(') ',1)[1].split()
                argv=[part.decode(errors='replace') for part in read(folder/'cmdline',16384).split(b'\0') if part]
                alive=(fields[0]!='Z' and fields[19]==str(job.get('start_ticks')) and argv==job.get('argv')
                       and read('/proc/sys/kernel/random/boot_id',128).decode().strip()==job.get('boot_id'))
            except (OSError,ValueError,IndexError,RuntimeError):pass
        result.update(pid=pid if type(pid) is int and pid>0 else None,process_identity_verified_alive=alive)
        try:
            terminal=read_json(ROOT/'state/owner_media'/('prepare_result_'+request+'.json'),16000)
            if terminal.get('request')==request and terminal.get('source_sha')==job.get('source_sha'):
                allowed={'HOLD_MEDIA_PREPARE','FILES_VERIFIED_ENGINE_START_PENDING','FILES_VERIFIED_ENGINE_START_DEFERRED',
                         'ENGINE_AND_FILES_READY_GENERATION_ACCEPTANCE_PENDING'}
                result['terminal_state']=terminal.get('state') if terminal.get('state') in allowed else 'UNKNOWN'
                code=terminal.get('error')
                if isinstance(code,str) and re.fullmatch('HOLD_[A-Z0-9_]{1,100}',code):result['terminal_error']=code
                for key in ('started','finished'):
                    value=terminal.get(key)
                    if type(value) in (int,float) and math.isfinite(value):result[key]=value
        except (OSError,ValueError,RuntimeError):pass
        events=[]
        log=read(ROOT/'logs'/('owner_media_prepare_'+request+'.log'),65536,tail=True).decode(errors='replace')
        for line in log.splitlines()[-100:]:
            if not line.startswith('NOX_MEDIA_INSTALL=') or len(line)>16384:continue
            try:value=json.loads(line.split('=',1)[1])
            except ValueError:continue
            if not isinstance(value,dict):continue
            phase=value.get('phase')
            if phase in ('download','asset_sha_verified'):
                name=value.get('filename',value.get('file'))
                if not isinstance(name,str) or name not in ASSETS:continue
                row={'phase':phase,'filename':name}
                for key in ('bytes','total'):
                    if type(value.get(key)) is int and 0<=value[key]<=ASSETS[name][1]:row[key]=value[key]
                if isinstance(value.get('sha256'),str) and SHA.fullmatch(value['sha256']):row['sha256']=value['sha256']
                events.append(row)
            elif phase=='isolated_dependency_closure':
                issues=value.get('issues') or []
                if not isinstance(issues,list):continue
                clean=[{'package':x['package'],'reason':x['reason']} for x in issues[:64]
                       if isinstance(x,dict) and isinstance(x.get('package'),str)
                       and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',x['package'])
                       and x.get('reason') in ('MISSING','VERSION_MISMATCH')]
                events.append({'phase':phase,'ok':value.get('ok') is True,'issues':clean})
            elif phase in ('admitted','additive_dependency_migration','isolated_environment_installing',
                            'isolated_environment_verified','parallel_downloads_admitted','prepared'):
                events.append({'phase':phase})
        result['events']=events[-24:]
    except (OSError,ValueError,TypeError,RuntimeError):pass
    for name,(subdirectory,size) in ASSETS.items():
        for location,base in (('ram',Path('/dev/shm/nox_media/models')),('disk',ROOT/'media/weights/models')):
            for suffix in ('','.partial'):
                path=base/subdirectory/(name+suffix)
                try:
                    info=plain(path).stat()
                    if stat.S_ISREG(info.st_mode):result['files'].append({'filename':name,'location':location,
                        'partial':bool(suffix),'bytes':info.st_size,'expected_bytes':size,'sha256_reverified':False})
                except (OSError,RuntimeError):pass
    return result


def executable_candidates():
    output=[];scanned=0
    cache=plain(AREA/'browsers')
    if cache.is_dir():
        for folder,dirs,files in os.walk(cache,followlinks=False):
            relative=Path(folder).relative_to(cache)
            dirs[:]=sorted(name for name in dirs if not (Path(folder)/name).is_symlink()) if len(relative.parts)<4 else []
            scanned+=len(dirs)+len(files)
            if scanned>3000:break
            for name in files:
                if name not in ('headless_shell','chrome-headless-shell','chrome'):continue
                path=plain(Path(folder)/name)
                fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW)
                try:
                    info=os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or not info.st_mode&0o111:continue
                    header=os.read(fd,64)
                    if header[:4]==b'\x7fELF':output.append(path)
                finally:os.close(fd)
    return output[:4]


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not re.fullmatch(r'[0-9]{1,24}',request) or not re.fullmatch('[0-9a-f]{40}',source):raise RuntimeError('HOLD_OWNER_CONTEXT')
    if any((ROOT/name).exists() or (ROOT/name).is_symlink() for name in ('STOP','STOP.flag','stop.flag','.stop','program/STOP','state/STOP')):
        raise RuntimeError('HOLD_OWNER_STOP')
    plain(STATE).mkdir(mode=0o700,parents=True,exist_ok=True)
    directory=plain(STATE/request);directory.mkdir(mode=0o700)
    report={'schema':'NOX_OWNER_BROWSER_DIAGNOSTIC_V1','request':request,'source_sha':source,
            'started':time.time(),'before':resources(),'package_or_service_changes':False,'backend_accessed':False,
            'private_stderr_exported':False,'media':media_progress()}
    env={k:v for k,v in os.environ.items() if k not in ('DEBUG','PWDEBUG','LD_PRELOAD')}
    env.update(CUDA_VISIBLE_DEVICES='',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
               PLAYWRIGHT_BROWSERS_PATH=str(AREA/'browsers'))
    marker=read_json(AREA/'owner-environment.json',8192)
    if marker!={'schema':'NOX_OWNER_BROWSER_ENV_V1','playwright':PLAYWRIGHT_PIN,
                'base_python':'/root/nox/venv/bin/python','torch_modified':False}:
        raise RuntimeError('HOLD_BROWSER_ENV_SCOPE')
    if report['before'].get('memory.max') is None or report['before']['memory.max']-report['before']['memory.current']<3*1024**3:
        raise RuntimeError('HOLD_BROWSER_RAM_RESERVE')
    linked=[]
    for number,path in enumerate(executable_candidates()):
        observed=bounded_command(['/usr/bin/ldd',str(path)],env,10,65536)
        raw=observed['stdout']+b'\n'+observed['stderr']
        private(directory/('linker_'+str(number)+'.log'),raw)
        linked.append({'binary':str(path.relative_to(AREA)),'returncode':observed['returncode'],
                       'missing_libraries':missing_libraries(raw),'failure_tags':failure_tags(raw)})
    report['linker']=linked
    child=directory/'launch_probe.py';private(child,CHILD.encode())
    observed=bounded_command([str(PYTHON),str(child)],env,38)
    private(directory/'launch.stderr.log',observed['stderr'])
    private(directory/'launch.stdout.log',observed['stdout'])
    report['launch']={'returncode':observed['returncode'],'bounded_stop':observed['bounded_stop'],
                      'missing_libraries':missing_libraries(observed['stderr']),
                      'failure_tags':failure_tags(observed['stderr']),'observations':[]}
    for line in observed['stdout'].decode(errors='replace').splitlines():
        if not line.startswith('NOX_BROWSER_DIAG=') or len(line)>4096:continue
        try:row=json.loads(line.split('=',1)[1])
        except ValueError:continue
        safe={k:v for k,v in row.items() if (k in ('backend_accessed','system_browser_selected','webgl') and type(v) is bool)
              or (k in ('phase','state','exception_type','version','python') and isinstance(v,str)
                  and re.fullmatch('[A-Za-z0-9_.-]{1,80}',v))}
        report['launch']['observations'].append(safe)
    report.update(after=resources(),finished=time.time(),media=media_progress())
    private(directory/'receipt.json',json.dumps(report,separators=(',',':'),allow_nan=False).encode())
    emit('browser_startup_diagnostic',report)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        reason=str(exc)
        emit('browser_diagnostic_hold',{'reason':reason if re.fullmatch('HOLD_[A-Z0-9_]{1,100}',reason) else type(exc).__name__})
        raise SystemExit(2)
