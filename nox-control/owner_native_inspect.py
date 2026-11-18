#!/usr/bin/env python3
"""Fixed read-only NOX queue/pool inspection. No model calls or native writes."""
from __future__ import annotations

import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
SOURCE_NAMES = (
    'owner_subagent_dispatcher.py', 'owner_subagent_processes.py',
    'owner_autonomy_pool.py', 'owner_task_plans.py',
    'owner_component_tasks.py', 'nox_auto_architect.py', 'owner_dispatcher_mentor.py',
)
FLAGS = (
    ROOT/'STOP', ROOT/'STOP.flag', ROOT/'stop.flag', ROOT/'.stop',
    ROOT/'program/STOP', ROOT/'state/STOP', ROOT/'state/STOP.flag',
    Path('/workspace/NOX_STOP'), ROOT/'state/OWNER_MAINTENANCE.flag',
    ROOT/'state/TRAIN_HOLD.flag', ROOT/'state/TRAIN_PAUSE_REQUEST.flag',
)
LOCK_PATHS = (ROOT/'state/owner_maintenance.lock', ROOT/'state/dispatcher/native_subagents.lock')
IDENTIFIER = re.compile(r'^[A-Za-z0-9_.:/@ -]{1,250}$')
SHA = re.compile(r'^[0-9a-f]{40,64}$')

def emit(name, value):
    print('NOX_MAINT_SCOPE_' + name + '=' + json.dumps(value, ensure_ascii=True,
          separators=(',', ':'), allow_nan=False), flush=True)

def safe_read(path, limit):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('ABSOLUTE_PATH_REQUIRED')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise ValueError('UNSAFE_TYPE_OR_SIZE')
            chunks = []
            total = 0
            while total <= limit:
                b = os.read(fd, min(65536, limit + 1 - total))
                if not b:
                    break
                chunks.append(b)
                total += len(b)
            after = os.fstat(fd)
            if total > limit or any(getattr(before, k) != getattr(after, k) for k in
                    ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
                raise ValueError('CHANGED_OR_OVERSIZED')
            return b''.join(chunks), after
        finally:
            os.close(fd)
    finally:
        os.close(parent)

def obj(path, limit=2000000):
    raw, info = safe_read(path, limit)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError('OBJECT_REQUIRED')
    return data, raw, info

def redact_source(value):
    out = re.sub(r'-----BEGIN [^-\n]*PRIVATE KEY-----[\s\S]*?-----END [^-\n]*PRIVATE KEY-----', '[REDACTED_PRIVATE_KEY]', value)
    out = re.sub(r'(?i)(https?://)[^/\s@]+:[^/\s@]+@', r'\1[REDACTED]@', out)
    out = re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9_.~+/=-]{12,}', r'\1[REDACTED]', out)
    out = re.sub(r'\b(?:hf_|ghp_|github_pat_|sk-)[A-Za-z0-9_-]{8,}', '[REDACTED_TOKEN]', out)
    out = re.sub(r'''(?i)((?:password|secret|api_key|access_key|authorization|token)\s*[:=]\s*["'])([^"'\n]{12,})(["'])''', r'\1[REDACTED]\3', out)
    out = re.sub(r'(?i)([?&](?:token|key|password|signature|secret)=)[^\s&"\']+', r'\1[REDACTED]', out)
    return out

def identifier(value):
    return value if isinstance(value, str) and IDENTIFIER.fullmatch(value) else None

def scalar_projection(data, names):
    result = {}
    for name in names:
        value = data.get(name)
        if value is None or isinstance(value, (bool, int)) or isinstance(value, float) and __import__('math').isfinite(value):
            result[name] = value
        elif isinstance(value, str) and len(value) <= 300:
            result[name] = redact_source(value)
    return result

def process(pid):
    try:
        p = Path('/proc')/str(int(pid))
        raw = (p/'stat').read_text()
        fields = raw.rsplit(') ', 1)[1].split()
        result = {'pid':int(pid), 'ppid':int(fields[1]), 'pgrp':int(fields[2]),
                  'start_ticks':int(fields[19]), 'state':fields[0]}
        ns = re.search(r'^NSpid:\s*(.*)$', (p/'status').read_text(), re.M)
        result['namespace_pids'] = [int(x) for x in ns[1].split()] if ns else []
        # Export two non-secret dispatcher controls, never an environment dump.
        result['dispatcher_env'] = {}
        for entry in (p/'environ').read_bytes().split(b'\0'):
            if b'=' not in entry:
                continue
            key, value = entry.split(b'=', 1)
            if key in (b'NOX_DISPATCHER_SAFE', b'NOX_DISPATCHER_WORKERS') and re.fullmatch(rb'[0-9]{1,2}', value):
                result['dispatcher_env'][key.decode()] = value.decode()
        again = (p/'stat').read_text().rsplit(') ', 1)[1].split()
        if int(again[19]) != result['start_ticks']:
            raise ValueError('PID_CHANGED')
        return result
    except (OSError, ValueError, IndexError):
        return {'pid':pid, 'status':'UNKNOWN_OR_CHANGED'}

def runtime_snapshot():
    rows = []
    cp = subprocess.run(['supervisorctl', 'status'], capture_output=True, text=True,
                        timeout=10, check=False)
    keep = {'nox-dispatcher-t855u', 'nox-ds41-8098', 'nox-proxy', 'nox-web29-18775',
            'nox-agent-architect-t859u', 'nox-agent-integrator-t859u', 'nox-agent-tuner-t858u'}
    for line in cp.stdout.splitlines():
        m = re.match(r'^([A-Za-z0-9_.:-]+)\s+([A-Z]+)(?:\s+pid\s+(\d+))?', line)
        if m and m[1] in keep:
            rows.append({'service':m[1], 'state':m[2],
                         'identity':process(int(m[3])) if m[3] else None})
    flags = {}
    for path in FLAGS:
        try:
            mode = path.lstat().st_mode
            flags[str(path)] = 'PRESENT' if stat.S_ISREG(mode) else 'UNSAFE_TYPE'
        except FileNotFoundError:
            flags[str(path)] = 'ABSENT'
        except OSError:
            flags[str(path)] = 'UNKNOWN'
    resources = {}
    for name in ('memory.current','memory.max','memory.stat','memory.events',
                 'memory.pressure','cpu.pressure','cpu.stat','cpu.max','io.pressure'):
        try:
            resources[name] = (Path('/sys/fs/cgroup')/name).read_text()[:10000]
        except OSError:
            resources[name] = None
    return {'time_unix':time.time(), 'supervisor_rc':cp.returncode, 'services':rows,
            'flags':flags, 'resources':resources}

def locks():
    try:
        lines = Path('/proc/locks').read_text().splitlines()
    except OSError:
        lines = []
    rows = []
    for path in LOCK_PATHS:
        row = {'path':str(path), 'scope':'PROC_LOCKS_OBSERVATION_NOT_LEASE_ACQUISITION'}
        try:
            s = path.lstat()
            row.update({'present':True, 'inode':s.st_ino, 'device_major':os.major(s.st_dev),
                        'device_minor':os.minor(s.st_dev), 'type_regular':stat.S_ISREG(s.st_mode)})
            matches = []
            for line in lines:
                m = re.search(r'\b([0-9a-f]+):([0-9a-f]+):(\d+)\b', line)
                if m and (int(m[1],16),int(m[2],16),int(m[3])) == (os.major(s.st_dev),os.minor(s.st_dev),s.st_ino):
                    matches.append(line[:250])
            row['matching_kernel_locks'] = matches[:10]
        except FileNotFoundError:
            row['present'] = False
        except OSError:
            row['status'] = 'UNKNOWN'
        rows.append(row)
    return rows


def configuration():
    path = ROOT/'config/owner_native_subagents.json'
    try:
        data, raw, info = obj(path, 1000000)
        row = scalar_projection(data, ('schema','mode','target','owner_authorized','instance_id','policy_id','catalog_sha256','owner_request','owner_source_sha','execution_mode','global_worker_cap'))
        row.update({'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),
                    'owner_uid':info.st_uid,'mode_bits':oct(stat.S_IMODE(info.st_mode))})
        row['module_pins'] = {k:v for k,v in data.get('module_pins',{}).items()
                              if identifier(k) and isinstance(v,str) and SHA.fullmatch(v)}
        policy = data.get('policy',{})
        row['policy'] = scalar_projection(policy, ('path','sha256')) if isinstance(policy,dict) else None
        catalog = data.get('catalog')
        row['catalog_shape'] = {'type':type(catalog).__name__}
        if isinstance(catalog,dict):
            pages = catalog.get('pages',[])
            row['catalog_shape']['schema'] = identifier(catalog.get('schema'))
            row['catalog_shape']['pages'] = len(pages) if isinstance(pages,list) else None
            tasks = []
            if isinstance(pages,list):
                for page in pages[:32]:
                    if isinstance(page,dict) and isinstance(page.get('tasks'),list):
                        tasks.extend(page['tasks'][:100])
            if isinstance(catalog.get('tasks'),list):
                tasks.extend(catalog['tasks'][:100])
            row['catalog_shape']['tasks'] = [
                {k:identifier(task.get(k)) for k in ('id','task_id','handler','subagent','status')}
                for task in tasks[:512] if isinstance(task,dict)]
        emit('CONFIG', row)
    except (OSError, ValueError, TypeError) as exc:
        emit('CONFIG', {'path':str(path),'status':'UNKNOWN','error':type(exc).__name__})




# Exact technical capabilities only. No installs, model POSTs, tests, namespaces,
# permissions changes, source writes or credential reads occur in this probe.
import ast
import pwd
import shutil
import urllib.request

CORE = (
    'nox_dispatcher_t855u.py','owner_subagent_dispatcher.py','owner_subagent_processes.py',
    'owner_autonomy_pool.py','owner_subagent_instruction_truth.py','owner_task_plans.py',
    'owner_component_tasks.py','owner_resource_policy.py',
)
BACKEND = ('native_v29_full_bridge.py','owner_chat_request_ledger.py',
           's03_existing_readback.py','durable_runtime.py','work_progress.py',
           'owner_dispatcher_mentor.py')
KNOWN = {
 'owner_subagent_dispatcher.py':'88af9c11d54e084ccb868c474d17c2a85511600a0ff6578bfe5490b437fe554e',
 'owner_subagent_processes.py':'c1d5adfcc83300d749b42f66d50f41d5c62c4df52215e43cfc0b891e7c91101b',
 'owner_autonomy_pool.py':'2c4735938dacd2a062ed2ee0b20477a6191d39b0fcf2b6c49686c10133047102',
}

PROBE_DEADLINE = time.monotonic()+100

def bounded_run(argv, timeout=6):
    remaining=PROBE_DEADLINE-time.monotonic()
    if remaining<1:return {'state':'BUDGET_EXHAUSTED'}
    timeout=min(timeout,remaining)
    env={'PATH':'/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
         'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','GIT_OPTIONAL_LOCKS':'0',
         'GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_SYSTEM':'/dev/null'}
    try:
        r=subprocess.run(argv,capture_output=True,text=True,timeout=timeout,check=False,env=env)
        return {'returncode':r.returncode,'stdout':r.stdout[:262144],
                'stderr':redact_source(r.stderr[:1000]),'truncated':len(r.stdout)>262144}
    except (OSError,subprocess.SubprocessError) as exc:
        return {'state':'UNAVAILABLE','error':type(exc).__name__}

def process_details(pid):
    row=process(pid)
    try:
        p=Path('/proc')/str(pid)
        row['cwd']=str((p/'cwd').resolve(strict=True))
        row['exe']=str((p/'exe').resolve(strict=True))
        status=(p/'status').read_text()
        for key in ('Uid','Gid','Seccomp','NoNewPrivs','CapEff'):
            found=re.search(r'^'+key+r':\s*([^\n]+)',status,re.M)
            row[key]=found[1] if found else None
        argv=(p/'cmdline').read_bytes().decode('utf-8','replace').split('\0')
        row['python_entries']=[x for x in argv if x.startswith('/root/nox/') and x.endswith('.py')][:10]
        flags={}
        safe_values={'-np','--parallel','-c','--ctx-size','-n','--predict','-t','--threads','--port'}
        for i,arg in enumerate(argv):
            if arg in safe_values and i+1<len(argv) and re.fullmatch(r'[0-9]{1,7}',argv[i+1]):flags[arg]=int(argv[i+1])
            if arg in ('--jinja','--no-webui','--slots','--no-slots','--no-mmap','--mlock'):flags[arg]=True
        row['safe_runtime_flags']=flags
    except (OSError,ValueError):
        row['details_state']='UNKNOWN'
    return row

def native_processes():
    data,_,_=obj(ROOT/'status/agents_t856u.json',2*1024*1024)
    native=data.get('native_subexecutors')
    if not isinstance(native,dict):
        emit('CAP_WORKERS',{'state':'NO_NATIVE_STATUS'})
        return
    director=native.get('director') or {};observed=process_details(director.get('pid')) if type(director.get('pid')) is int else None
    rows=[]
    for w in native.get('workers',[])[:8]:
        if not isinstance(w,dict) or type(w.get('pid')) is not int:continue
        found=process_details(w['pid'])
        rows.append({'claimed':scalar_projection(w,('pid','ppid','process_starttime','role','state','current_task','heartbeat_at')),
                     'observed':found,'identity_verified':found.get('start_ticks')==w.get('process_starttime') and found.get('ppid')==director.get('pid')})
    emit('CAP_WORKERS',{'at':time.time(),'observed_at':native.get('observed_at'),
                       'director_claim':scalar_projection(director,('pid','ppid','process_starttime')),
                       'director_observed':observed,'workers':rows,
                       'last_admission':scalar_projection(native.get('last_admission') or {},('state','jobs_started'))})

def source_metadata(path, include_source=False, category='SOURCE'):
    try:
        raw,info=safe_read(path,180000);text=raw.decode('utf-8');h=hashlib.sha256(raw).hexdigest()
        row={'path':str(path),'bytes':len(raw),'sha256':h,'mtime_ns':info.st_mtime_ns,'scope':'ON_DISK_SOURCE_NOT_LIVE_FRAME_INSPECTION'}
        try:
            tree=ast.parse(text)
            row['functions']=[node.name for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))][:70]
            row['imports']=sorted(set(node.module or '' for node in ast.walk(tree) if isinstance(node,ast.ImportFrom))|set(alias.name for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names))[:70]
            routes=[];callbacks=[];danger=[]
            for node in ast.walk(tree):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                    if node.func.attr in ('get','post','put','delete','route','add_api_route','add_route') and node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str):
                        value=node.args[0].value
                        if value.startswith('/') and re.search(r'tool|exec|code|agent|chat|s03|work|project|model',value,re.I):routes.append(value[:180])
                    if node.func.attr in ('run','Popen','system','write_text','write_bytes'):danger.append({'name':node.func.attr,'line':node.lineno})
                if isinstance(node,ast.Subscript) and isinstance(node.value,ast.Name) and node.value.id=='HANDLERS' and isinstance(node.slice,ast.Constant):callbacks.append(str(node.slice.value)[:80])
            row.update(technical_routes=sorted(set(routes))[:60],handler_names=sorted(set(callbacks))[:80],execution_write_calls=danger[:30])
        except SyntaxError:row['ast']='UNPARSEABLE'
        if include_source:
            clean=redact_source(text);row['source_redacted']=clean!=text
            if len(json.dumps(clean,ensure_ascii=True))<150000:row['source']=clean
            else:row['source']='OMITTED_OUTPUT_BOUND'
        emit(category,row)
        return row
    except (OSError,ValueError,UnicodeError) as exc:
        emit(category,{'path':str(path),'state':'UNAVAILABLE','error':type(exc).__name__})
        return None

def source_capabilities():
    for name in CORE:
        p=SCRIPTS/name
        try:raw,_=safe_read(p,180000);changed=KNOWN.get(name) is not None and hashlib.sha256(raw).hexdigest()!=KNOWN[name]
        except (OSError,ValueError):changed=False
        source_metadata(p,include_source=changed,category='CAP_CORE_SOURCE')
    for name in BACKEND:
        source_metadata(SCRIPTS/name,include_source=name!='owner_dispatcher_mentor.py',category='CAP_BACKEND_SOURCE')
    candidates=[]
    for directory in (ROOT/'scripts',ROOT/'program',ROOT/'agent',ROOT/'web29',ROOT/'web'):
        try:
            entries=sorted(directory.iterdir(),key=lambda p:p.name)
        except OSError:continue
        for p in entries:
            if len(candidates)>=40:break
            if p.suffix=='.py' and not p.is_symlink() and p.name not in CORE+BACKEND and re.search(r'executor|sandbox|tool|bridge|gateway|request_ledger|warm.?cache|router',p.name,re.I) and not re.search(r'credential|password|secret',p.name,re.I):
                candidates.append(p)
    exported=0
    for p in candidates:
        if time.monotonic()>PROBE_DEADLINE:break
        include=exported<3 and re.search(r'executor|sandbox|native_tools|agent_tools|code_tools',p.name,re.I) is not None
        source_metadata(p,include,'CAP_TOOL_MODULE')
        if include:exported+=1
    # Trace only currently serving technical entry files discovered in /proc.
    snapshot=runtime_snapshot()
    for service in snapshot['services']:
        if service['service'] not in ('nox-proxy','nox-web29-18775','nox-ds41-8098') or not service.get('identity'):continue
        detail=process_details(service['identity']['pid']);emit('CAP_SERVING_PROCESS',{'service':service['service'],**detail})
        for entry in detail.get('python_entries',[])[:3]:
            source_metadata(Path(entry),False,'CAP_SERVING_SOURCE')

def executables():
    names=('git','python3','node','npm','pytest','bwrap','unshare','docker','podman','nsjail','firejail','setpriv','prlimit','timeout')
    found={name:shutil.which(name) for name in names}
    versions={}
    for name in ('git','python3','node','bwrap','unshare','setpriv'):
        if found[name]:
            result=bounded_run([found[name],'--version'],3)
            versions[name]={k:v for k,v in result.items() if k!='stdout'}
            versions[name]['version']=redact_source(result.get('stdout','').splitlines()[0])[:180] if result.get('stdout') else None
    sysctls={}
    for name in ('/proc/sys/kernel/unprivileged_userns_clone','/proc/sys/user/max_user_namespaces','/proc/sys/kernel/apparmor_restrict_unprivileged_userns'):
        try:sysctls[name]=Path(name).read_text()[:200].strip()
        except OSError:sysctls[name]=None
    users=[]
    for entry in pwd.getpwall():
        if entry.pw_uid!=0 and entry.pw_name in ('nox','nobody','runner','worker','sandbox','www-data'):
            users.append({'name':entry.pw_name,'uid':entry.pw_uid,'gid':entry.pw_gid,'shell':entry.pw_shell})
    sockets={}
    for path in ('/var/run/docker.sock','/run/podman/podman.sock'):
        try:mode=Path(path).lstat();sockets[path]={'present':True,'socket':stat.S_ISSOCK(mode.st_mode),'uid':mode.st_uid,'gid':mode.st_gid,'mode':oct(stat.S_IMODE(mode.st_mode))}
        except OSError:sockets[path]={'present':False}
    try:seccomp=[str(p) for p in Path('/usr/lib/x86_64-linux-gnu').glob('libseccomp.so*')][:5]
    except OSError:seccomp=[]
    interpreters=[]
    for path in ('/usr/bin/python3','/usr/local/bin/python3','/root/venv_volta/bin/python','/root/nox/venv/bin/python','/usr/bin/node','/usr/local/bin/node'):
        p=Path(path)
        if p.exists():interpreters.append({'path':path,'resolved':str(p.resolve()),'executable':os.access(p,os.X_OK)})
    emit('CAP_EXECUTION_FACILITIES',{'programs':found,'versions':versions,'process':process_details(os.getpid()),
         'non_root_candidates':users,'userns_sysctls':sysctls,'container_sockets':sockets,'libseccomp':seccomp,
         'interpreters':interpreters,'actual_isolation_tested':False,
         'scope':'AVAILABILITY_ONLY_NO_SANDBOX_OR_TEST_CREATED'})

def repository_locations():
    candidates=[]
    for root in (Path('/root'),Path('/workspace'),Path('/opt')):
        try:entries=list(root.iterdir())
        except OSError:continue
        for p in entries:
            if p.is_dir() and not p.is_symlink() and re.search(r'nox|helion|repo|code|work|app|src',p.name,re.I):candidates.append((p,0))
    candidates.insert(0,(ROOT,0));seen=set();repos=[];project_roots=[]
    skip={'models','model','data','datasets','downloads','lora','memory','kb','venv','node_modules','cache','backups','snapshots','site-packages','__pycache__'}
    while candidates and len(seen)<160:
        p,depth=candidates.pop(0)
        if str(p) in seen:continue
        seen.add(str(p))
        if (p/'.git').exists():
            repos.append(p)
            if len(repos)>=12:break
            continue
        markers=[name for name in ('pyproject.toml','package.json','pytest.ini','requirements.txt','AGENTS.md') if (p/name).is_file()]
        if markers:project_roots.append({'path':str(p),'markers':markers})
        if depth>=2:continue
        try:children=sorted(p.iterdir(),key=lambda v:v.name)
        except OSError:continue
        for child in children:
            if child.name.startswith('.') or child.name.casefold() in skip or child.is_symlink():continue
            if child.is_dir() and (depth>0 or re.search(r'nox|helion|repo|code|work|app|src|project|server|web|script',child.name,re.I)):
                candidates.append((child,depth+1))
    emit('CAP_PROJECT_LOCATIONS',{'scan_scope':'FILTERED_PROJECT_DIRECTORIES_DEPTH_2_NO_MODEL_OR_PRIVATE_DATA_WALK',
         'visited_directory_count':len(seen),'repository_count':len(repos),'project_roots':project_roots[:25]})
    git=shutil.which('git')
    for p in repos:
        if time.monotonic()>PROBE_DEADLINE:break
        row={'path':str(p),'owner_uid':p.stat().st_uid}
        if git:
            prefix=[git,'-c','core.fsmonitor=false','-C',str(p)]
            for name,argv in (('head',['rev-parse','HEAD']),('branch',['symbolic-ref','--short','HEAD']),('worktrees',['worktree','list','--porcelain'])):
                result=bounded_run(prefix+argv,5)
                value=result.get('stdout','').strip()
                row[name]={'rc':result.get('returncode'),'value':redact_source(value[:5000]),'truncated':result.get('truncated')}
            state=bounded_run(prefix+['status','--porcelain','--untracked-files=no'],7)
            row['tracked_working_changes']={'rc':state.get('returncode'),'line_count':len(state.get('stdout','').splitlines()),'truncated':state.get('truncated')}
        emit('CAP_REPOSITORY',row)

def model_api_metadata():
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise ValueError('REDIRECT_REJECTED')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    for path in ('/health','/v1/models','/props','/slots'):
        row={'port':8098,'path':path,'method':'GET','model_inference_called':False}
        try:
            with opener.open('http://127.0.0.1:8098'+path,timeout=2) as response:
                raw=response.read(262145);row['http_status']=response.status
            if len(raw)>262144:raise ValueError('RESPONSE_BOUND')
            data=json.loads(raw)
            if path=='/slots' and isinstance(data,list):
                row['slot_count']=len(data);row['slots']=[scalar_projection(item,('id','id_task','is_processing','processing','n_ctx','n_predict')) for item in data[:16] if isinstance(item,dict)]
            elif path=='/v1/models' and isinstance(data,dict):
                row['models']=[{'id':redact_source(str(item.get('id','')))[:200],'object':identifier(item.get('object'))} for item in data.get('data',[])[:10] if isinstance(item,dict)]
            elif path=='/props' and isinstance(data,dict):
                row['keys']=sorted(data)[:70]
                row['values']=scalar_projection(data,('total_slots','n_ctx_train','n_ctx','n_predict','model_path','build_info'))
                default=data.get('default_generation_settings')
                if isinstance(default,dict):row['default_numeric_settings']={k:v for k,v in default.items() if type(v) in (int,float,bool) and re.search(r'ctx|predict|token|parallel|batch|temp|repeat',k,re.I)}
                template=data.get('chat_template')
                row['chat_template']={'present':isinstance(template,str),'bytes':len(template.encode()) if isinstance(template,str) else None,'has_tool_markers':bool(re.search(r'tool_calls|function|tool_response',template)) if isinstance(template,str) else None}
            elif isinstance(data,dict):row['health']=scalar_projection(data,('status','error','code'))
        except (OSError,ValueError,TypeError) as exc:row.update(state='UNAVAILABLE',error=type(exc).__name__)
        emit('CAP_MODEL_API',row)

def queue_capabilities():
    data,raw,_=obj(ROOT/'state/dispatcher/state.json',16*1024*1024);tasks=data.get('tasks')
    if not isinstance(tasks,dict) or len(tasks)>10000:raise ValueError('QUEUE_SHAPE')
    counts={};handlers={};selected=[]
    for key,t in tasks.items():
        if not isinstance(t,dict):continue
        state=identifier(t.get('status')) or 'UNKNOWN';handler=identifier(t.get('handler')) or 'UNKNOWN'
        counts[state]=counts.get(state,0)+1;handlers[handler]=handlers.get(handler,0)+1
        if state=='running' or handler in ('owner_native_typed_leaf','owner_native_subagent_review'):
            row={k:identifier(t.get(k)) for k in ('id','handler','status','queue_id','parent_task_id')}
            row['claim_present']=bool(t.get('owner_claim'))
            row['params_keys']=sorted((t.get('params') or {}).keys())[:20] if isinstance(t.get('params'),dict) else []
            selected.append(row)
    emit('CAP_QUEUE',{'count':len(tasks),'counts':counts,'handler_counts':handlers,'sha256':hashlib.sha256(raw).hexdigest(),'selected':selected[:30]})
    disk=os.statvfs(ROOT);emit('CAP_DISK',{'path':str(ROOT),'available_bytes':disk.f_bavail*disk.f_frsize})

def main():
    emit('SNAPSHOT_A',runtime_snapshot())
    native_processes()
    configuration()
    queue_capabilities()
    emit('LOCKS',locks())
    executables()
    repository_locations()
    model_api_metadata()
    source_capabilities()
    native_processes()
    emit('SNAPSHOT_B',runtime_snapshot())
    print('NOX_MAINT_INSPECT_COMPLETE=true',flush=True)

if __name__=='__main__':
    main()
