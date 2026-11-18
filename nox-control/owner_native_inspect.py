#!/usr/bin/env python3
"""Exact dependency, template/tokenizer and PID readback; no inference or writes."""
from __future__ import annotations
import ast, hashlib, json, os, re, stat, subprocess, time, urllib.request
from pathlib import Path
ROOT=Path('/root/nox')
SCRIPTS=ROOT/'scripts'
IDENTIFIER=re.compile(r'^[A-Za-z0-9_.:/@ -]{1,250}$')
SHA=re.compile(r'^[0-9a-f]{40,64}$')
FLAGS=tuple(Path(x) for x in ('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/root/nox/program/STOP','/root/nox/state/STOP','/root/nox/state/STOP.flag','/workspace/NOX_STOP','/root/nox/state/OWNER_MAINTENANCE.flag','/root/nox/state/TRAIN_HOLD.flag','/root/nox/state/TRAIN_PAUSE_REQUEST.flag'))
LOCK_PATHS=(ROOT/'state/owner_maintenance.lock',ROOT/'state/dispatcher/native_subagents.lock')
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

def native_status():
    data,raw,_=obj(ROOT/'status/agents_t856u.json',2*1024*1024)
    native=data.get('native_subexecutors') or {}
    row={'status_sha256':hashlib.sha256(raw).hexdigest(),'keys':sorted(native),'observed_at':native.get('observed_at'),
         'details':scalar_projection(native,('mode','target','close_reason','last_close_reason','thread_runner_count','declared_worker_contract_slots')),
         'last_admission':scalar_projection(native.get('last_admission') or {},('state','reason','close_reason','error','jobs_started','pending')),
         'director':native.get('director'),'workers':[]}
    for worker in native.get('workers',[])[:8]:
        claim=scalar_projection(worker,('pid','ppid','process_starttime','role','state','heartbeat_at','current_task'))
        row['workers'].append({'claimed':claim,'observed':process(claim['pid']) if type(claim.get('pid')) is int else None})
    for name in ('pool','pool_status','close_status'):
        if isinstance(native.get(name),dict):row[name]=scalar_projection(native[name],('state','reason','close_reason','closed_at'))
    emit('NATIVE_STATUS',row)

KNOWN_CALLBACK='5f134b8b1915851de15318e23885951885ca84d6515ca1e48c56286862830db5'
CORE=('nox_dispatcher_t855u.py','owner_subagent_dispatcher.py','owner_subagent_processes.py',
      'owner_autonomy_pool.py','owner_subagent_instruction_truth.py','owner_task_plans.py',
      'owner_component_tasks.py','owner_resource_policy.py')

def exact_current_config():
    path=ROOT/'config/owner_native_subagents.json'
    try:
        data,raw,info=obj(path,20000)
        row={'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
             'schema':data.get('schema'),'owner_request':data.get('owner_request')}
        allowed={'schema','instance_id','owner_authorized','mode','target','policy_id','policy','module_pins',
                 'catalog','catalog_sha256','owner_request','owner_source_sha','execution_mode','global_worker_cap',
                 'project_pins','global_cap','normal_mode','stop_policy','max_workers',
                 'historical_leaf_source_sha256','project_handoff'}
        clean=redact_source(raw.decode());unknown=sorted(set(data)-allowed)
        row['unknown_top_level_keys']=unknown
        def sensitive(value):
            if isinstance(value,dict):return any(re.search(r'secret|password|token|credential|authorization|api_key|access_key',str(k),re.I) or sensitive(v) for k,v in value.items())
            if isinstance(value,list):return any(sensitive(v) for v in value)
            return False
        row['redacted']=clean!=raw.decode() or sensitive(data)
        if data.get('schema')=='NOX_NATIVE_SUBAGENT_BINDING_V1' and not row['redacted']:
            # Known owner binding/catalog configuration, explicitly requested.
            row['content']=raw.decode()
        else:row['content']='OMITTED_UNRECOGNIZED_OR_REDACTED_CONFIG'
        emit('EXACT_CONFIG',row)
        return data
    except (OSError,ValueError,TypeError) as exc:
        emit('EXACT_CONFIG',{'state':'UNAVAILABLE','error':type(exc).__name__});return {}

def descendants(snapshot):
    director=next((x['identity'] for x in snapshot['services'] if x['service']=='nox-dispatcher-t855u'),None)
    if not director:emit('DESCENDANTS',{'state':'NO_DIRECTOR'});return
    pending=[director['pid']];seen=set();rows={}
    try:
        while pending:
            parent=pending.pop(0)
            if parent in seen:continue
            seen.add(parent)
            if len(seen)>24:raise ValueError('CHILD_BOUND')
            try:threads=list((Path('/proc')/str(parent)/'task').iterdir())
            except FileNotFoundError:continue
            if len(threads)>128:raise ValueError('THREAD_BOUND')
            for thread in threads:
                if not thread.name.isdigit():continue
                try:raw=(thread/'children').read_text()
                except FileNotFoundError:continue
                if len(raw)>4096:raise ValueError('CENSUS_BOUND')
                for child in raw.split():
                    if not child.isdigit():raise ValueError('CENSUS_SCHEMA')
                    identity=process(int(child))
                    if identity.get('ppid')==parent:
                        rows[int(child)]=identity;pending.append(int(child))
        emit('DESCENDANTS',{'director':director,'rows':[rows[x] for x in sorted(rows)],
                            'scope':'CHILD_IDENTITIES_NOT_ALL_CLASSIFIED_AS_WORKERS'})
    except (OSError,ValueError) as exc:emit('DESCENDANTS',{'state':'UNKNOWN','error':type(exc).__name__})

def recovery_receipts(config):
    request=str(config.get('owner_request',''))
    if not re.fullmatch(r'[0-9]{1,24}',request):return
    directory=ROOT/'state'/('four_queue_recovery_'+request)
    try:
        entries=sorted(p for p in directory.iterdir() if re.fullmatch(r'\d{2}_[A-Z_]+\.json',p.name))
        if len(entries)>64:raise ValueError('RECEIPT_BOUND')
        for path in entries[-8:]:
            data,raw,_=obj(path,100000)
            # Installer phase/identity/source metadata only, never queue snapshots.
            projection={key:data.get(key) for key in ('schema','request','source_sha','phase','reason','status',
                'lifetime','restored_original_sources','release_intent','state') if key in data}
            emit('FOREIGN_RECOVERY_PHASE',{'file':path.name,'sha256':hashlib.sha256(raw).hexdigest(),
                                         'fields':projection})
    except (OSError,ValueError,TypeError) as exc:emit('FOREIGN_RECOVERY_PHASE',{'state':'UNAVAILABLE','error':type(exc).__name__})

def dispatcher_errors():
    try:
        result=subprocess.run(['supervisorctl','tail','nox-dispatcher-t855u','stderr'],capture_output=True,
                              text=True,timeout=5,check=False)
        lines=[]
        for line in result.stdout[-12000:].splitlines():
            if re.search(r'Traceback|File ".*(?:owner_|nox_dispatcher)|(?:GateError|RuntimeError|ValueError|NameError|ImportError|ModuleNotFoundError|TypeError|AttributeError|SyntaxError):|\bHOLD_[A-Z0-9_]+',line):
                lines.append(redact_source(line)[:700])
        emit('DISPATCHER_ERROR_LINES',{'returncode':result.returncode,'filtered_lines':lines[-40:],
                                     'scope':'SUPERVISOR_BOUNDED_STDERR_EXCEPTION_LINES_ONLY'})
    except (OSError,subprocess.SubprocessError) as exc:emit('DISPATCHER_ERROR_LINES',{'state':'UNAVAILABLE','error':type(exc).__name__})

def main():
    first=runtime_snapshot();emit('SNAPSHOT_A',first);descendants(first)
    config=exact_current_config();configuration();emit('LOCKS',locks())
    for name in CORE:
        include=name=='owner_subagent_instruction_truth.py'
        if name=='owner_subagent_dispatcher.py':
            try:raw,_=safe_read(SCRIPTS/name,180000);include=hashlib.sha256(raw).hexdigest()!=KNOWN_CALLBACK
            except (OSError,ValueError):include=False
        source_metadata(SCRIPTS/name,include,'CURRENT_CORE_SOURCE')
    for turn in range(2):
        try:native_status()
        except (OSError,ValueError,TypeError) as exc:emit('NATIVE_STATUS',{'state':'UNAVAILABLE','error':type(exc).__name__})
        if turn==0:time.sleep(1)
    queue_capabilities();recovery_receipts(config);dispatcher_errors()
    final=runtime_snapshot();emit('SNAPSHOT_B',final);descendants(final)
    print('NOX_MAINT_INSPECT_COMPLETE=true',flush=True)

if __name__=='__main__':main()
