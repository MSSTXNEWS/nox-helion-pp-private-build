#!/usr/bin/env python3
"""Bounded static S03 writer/AttachedNOX contract. No runtime import, database, data or weights access.
Projection narrows existing v129/read_native_s03_write_contract.py to AST-only metadata.
"""
import sys
sys.dont_write_bytecode=True
import ast, fcntl, hashlib, importlib.machinery, json, os, re, selectors, shutil, signal, stat, subprocess, time
from pathlib import Path
ROOT=Path('/root/nox');STATE=ROOT/'state'
FLAGS=(ROOT/'STOP',STATE/'OWNER_MAINTENANCE.flag',STATE/'TRAIN_HOLD.flag',STATE/'TRAIN_PAUSE_REQUEST.flag')
SAFE_PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
DEADLINE=None
KNOWN_NOX_SERVICES=('nox-agent-architect-t859u', 'nox-agent-integrator-t859u', 'nox-agent-tuner-t858u', 'nox-chat-8081', 'nox-checklist-worker', 'nox-cores', 'nox-dialog-miner', 'nox-dispatcher-t855u', 'nox-distill-worm-t811u', 'nox-downloads-t802u', 'nox-embed', 'nox-gpu-watchdog-t865u', 'nox-hidden-router', 'nox-lifeline-guard', 'nox-media-comfyui', 'nox-offload-t850u', 'nox-priority-scheduler', 'nox-proxy', 'nox-report-heartbeat-t811u', 'nox-self-improve-t846u', 'nox-self-learning-loop', 'nox-selfheal', 'nox-teacher-bringup', 'nox-teacher-serve-t811u', 'nox-train-volta-t866u', 'nox-train-worm-t811u', 'nox-vram-guard-t829u', 'nox-watch-swap-t845u')
OBSERVATION={}
AST_READ_STARTED=False
class Hold(RuntimeError): pass

def require(value, code):
    if not value: raise Hold('HOLD_CAPABILITY_'+code)

def remaining(limit):
    left = limit if DEADLINE is None else DEADLINE-time.monotonic()
    require(left > 0, 'DEADLINE')
    return max(.1,min(limit,left))

def identity(s): return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)

def plain(path):
    path=Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'PATH')
    require(not any(p.is_symlink() for p in (path,*path.parents)), 'SYMLINK')
    return path

def read_regular(path, private=False, maximum=131072):
    path=plain(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid==os.geteuid() and before.st_size<=maximum, 'FILE_SCOPE')
        require(stat.S_IMODE(before.st_mode)==0o600 if private else not before.st_mode&0o022, 'FILE_MODE')
        data=os.read(fd,maximum+1)
        require(len(data)==before.st_size and identity(before)==identity(os.fstat(fd))==identity(path.lstat()), 'FILE_CHANGED')
        return data
    finally: os.close(fd)

def flags():
    require(all(p.is_file() for p in FLAGS), 'FOUR_STOP_FLAGS_REQUIRED')
    return [hashlib.sha256(read_regular(p)).hexdigest() for p in FLAGS]

def execute(argv, seconds=12, pass_fds=(), collect=False):
    # Bounded pipe, no provider diagnostics or filenames reach logs; kill whole subprocess group.
    env={'PATH':SAFE_PATH,'LC_ALL':'C','HOME':'/root'}
    end=time.monotonic()+remaining(seconds)
    p=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE if collect else subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,env=env,pass_fds=pass_fds,start_new_session=True)
    out=bytearray();sel=selectors.DefaultSelector()
    if collect: sel.register(p.stdout,selectors.EVENT_READ)
    try:
        while p.poll() is None or collect and sel.get_map():
            require(time.monotonic()<end,'COMMAND_TIMEOUT')
            if collect:
                for key,_ in sel.select(.05):
                    chunk=os.read(key.fd,8192)
                    if not chunk:sel.unregister(key.fileobj)
                    else:out.extend(chunk);require(len(out)<=131072,'OUTPUT_BOUND')
            else:time.sleep(.03)
        return p.returncode,bytes(out)
    finally:
        sel.close()
        if p.poll() is None:
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        p.wait(timeout=3)
        if p.stdout:p.stdout.close()

def binary(name):
    p=shutil.which(name,path=SAFE_PATH);require(p is not None,'EXECUTABLE_UNAVAILABLE');return p

def service_status():
    rc,raw=execute([binary('supervisorctl'),'status'],12,collect=True)
    allowed_states={'STOPPED','STARTING','RUNNING','BACKOFF','STOPPING','EXITED','FATAL','UNKNOWN'}
    rows=[]
    for line in raw.decode('utf8','replace').splitlines():
        parts=line.split()
        if not parts or not parts[0].startswith('nox-'):continue
        require(len(rows)<64 and len(parts)>1 and re.fullmatch(r'nox-[A-Za-z0-9_.:-]{1,90}',parts[0]),'SERVICE_OUTPUT_SCOPE')
        rows.append({'name':parts[0],'state':parts[1] if parts[1] in allowed_states else 'UNKNOWN'})
    OBSERVATION['supervisor_status']=rows
    OBSERVATION['supervisor_exit_code']=rc
    require(rc in (0,3) and bool(rows),'SUPERVISOR_STATUS_UNAVAILABLE')
    return rows

def stopped():
    rows=service_status()
    require(all(x['state'] in ('STOPPED','EXITED','FATAL') for x in rows),'SERVICES_NOT_STOPPED')
    return len(rows)

def flag_presence():
    result={p.name:bool(p.is_file() and not p.is_symlink()) for p in FLAGS}
    OBSERVATION['stop_flag_presence']=result
    return result

TRAINER_FILES={'train_full_base_zero3.py','qwen_student_training_entry.py','qwen_student_training_entry_revision.py','qwen_student_training_entry_successor.py','qwen_student_training_entry_transport.py','hybrid_training_entry.py'}
def active_training(rows):
    services=[r['name'] for r in rows if r['state'] in ('RUNNING','STARTING','STOPPING') and re.search(r'train|distill|self-learning|self-improve',r['name'])]
    count=0;scanned=0
    for entry in os.scandir('/proc'):
        if not entry.name.isdigit():continue
        scanned+=1;require(scanned<=4096,'PROCESS_SCAN_BOUND')
        try:
            fd=os.open('/proc/'+entry.name+'/cmdline',os.O_RDONLY|os.O_NOFOLLOW)
            try:raw=os.read(fd,8193)
            finally:os.close(fd)
            if len(raw)>8192:continue
            args=raw.split(b'\0')
            if any(os.path.basename(a.decode('utf8','ignore')) in TRAINER_FILES for a in args):count+=1
        except (FileNotFoundError,ProcessLookupError):continue
        except PermissionError:raise Hold('HOLD_CAPABILITY_PROCESS_VISIBILITY') from None
    OBSERVATION['active_training_services']=services
    OBSERVATION['known_trainer_process_count']=count
    OBSERVATION['trainer_match_count']=count
    return bool(services or count)

def ensure_stop_flags():
    created=[]
    for path in FLAGS:
        plain(path)
        if path.exists():read_regular(path);continue
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            os.write(fd,b'OWNER_FULL_STOP_NOX_49_20261117\n');os.fsync(fd)
        finally:os.close(fd)
        created.append(path.name)
        OBSERVATION['stop_flags_created']=list(created)
    flag_presence()
    return created

def full_stop():
    flag_presence();rows=service_status();OBSERVATION['supervisor_before']=rows
    require(not active_training(rows),'ACTIVE_TRAINER_NO_VERIFIED_SAFEPOINT')
    # Existing deployed trainer throws on STOP before save. Never touch active training here.
    require(all(r['name'] in KNOWN_NOX_SERVICES for r in rows),'UNREVIEWED_NOX_SERVICE')
    ensure_stop_flags();baseline=flags()
    # Check again immediately before supervisor control, while the owner lease is held.
    rows=service_status();require(not active_training(rows),'ACTIVE_TRAINER_NO_VERIFIED_SAFEPOINT')
    targets=[r['name'] for r in rows if r['state'] not in ('STOPPED','EXITED','FATAL')]
    OBSERVATION['stop_targets']=targets;OBSERVATION['supervisor_stop_attempted']=bool(targets)
    if targets:
        rc,_=execute([binary('supervisorctl'),'stop',*targets],150,collect=False)
        OBSERVATION['supervisor_stop_exit_code']=rc
    count=stopped();require(flags()==baseline,'FLAGS_CHANGED')
    OBSERVATION['stop_flags_unchanged_after_control']=True
    OBSERVATION['supervisor_after']=OBSERVATION['supervisor_status']
    OBSERVATION['all_noX_services_quiescent']=True
    OBSERVATION['all_states_literal_STOPPED']=all(r['state']=='STOPPED' for r in OBSERVATION['supervisor_status'])
    return count,baseline

SCRIPT_NAMES=('nox_v29_chat_bridge.py','nox_dispatcher_t855u.py','owner_dispatcher_mentor.py','owner_task_plans.py','owner_s03_gateway.py','owner_task_lifecycle.py')
MODULE_ROOTS={
    's03_memory':(ROOT/'scripts',ROOT),
    'native_bridge_v38':(ROOT/'nox_runpod/teacher_mesh/v38',ROOT/'scripts/nox_runpod/teacher_mesh/v38'),
    'durable_runtime':(ROOT/'nox_runpod/teacher_mesh/v38',ROOT/'scripts/nox_runpod/teacher_mesh/v38'),
    'synaptic_brain':(ROOT/'nox_runpod/teacher_mesh/v38',ROOT/'scripts/nox_runpod/teacher_mesh/v38')}
ALLOWED_PATHS={ROOT/'scripts'/n for n in SCRIPT_NAMES}|{root/(module+'.py') for module,roots in MODULE_ROOTS.items() for root in roots}
IDENT=re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,79}\Z')
SENSITIVE=re.compile(r'^(?:sk_|ghp_|github_pat_)|password|credential|secret|api_key|bearer',re.I)
INTEREST=re.compile(r's03|append|remember|persist|revision|readback|lease|writer|attach|bind|register|open_turn|_db|_proxy_completion|_save_exchange|_readback|recall|commit',re.I)
CONSTRUCTORS={'AttachedNOX','HostBindings','NativePorts','OwnerBrainHooks'}
MAX_FILE=1024*1024
MAX_NODES=60000
MAX_OUTPUT=98304

def safe_name(value):
    return value if isinstance(value,str) and IDENT.fullmatch(value) and not SENSITIVE.search(value) else None
def symbol(node):
    if isinstance(node,ast.Name):return safe_name(node.id)
    if isinstance(node,ast.Attribute):
        left=symbol(node.value);right=safe_name(node.attr)
        return left+'.'+right if left and right and left.count('.')<4 else None
    return None
def signature(node,owner=None):
    args=node.args
    return {'name':safe_name(node.name),'owner':owner,'line':node.lineno,'end_line':node.end_lineno,
            'async':isinstance(node,ast.AsyncFunctionDef),
            'positional_only':[safe_name(a.arg) for a in args.posonlyargs],
            'positional':[safe_name(a.arg) for a in args.args],
            'keyword_only':[safe_name(a.arg) for a in args.kwonlyargs],
            'vararg':safe_name(args.vararg.arg) if args.vararg else None,
            'varkw':safe_name(args.kwarg.arg) if args.kwarg else None,
            'default_count':len(args.defaults)+sum(v is not None for v in args.kw_defaults),
            'calls':sorted({v for n in ast.walk(node) if isinstance(n,ast.Call) and (v:=symbol(n.func))})[:24]}
def project(raw):
    require(len(raw)<=MAX_FILE,'SOURCE_BOUND')
    tree=ast.parse(raw.decode('utf8'));nodes=list(ast.walk(tree));require(len(nodes)<=MAX_NODES,'AST_BOUND')
    imports=[];classes=[];functions=[];bindings=[];slots=[]
    def visit(body,owner=None):
        for node in body:
            if isinstance(node,ast.ClassDef):
                name=safe_name(node.name)
                if name and (name in CONSTRUCTORS or INTEREST.search(name)):
                    classes.append({'name':name,'line':node.lineno,'bases':[symbol(b) for b in node.bases]})
                visit(node.body,name)
            elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                if safe_name(node.name) and (INTEREST.search(node.name) or owner in CONSTRUCTORS):functions.append(signature(node,owner))
            elif isinstance(node,(ast.Try,ast.If,ast.With)):
                visit(node.body,owner)
                for name in ('orelse','finalbody'):visit(getattr(node,name,[]),owner)
                for handler in getattr(node,'handlers',[]):visit(handler.body,owner)
    visit(tree.body)
    for node in nodes:
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            module=node.module if isinstance(node,ast.ImportFrom) else None
            module='.'.join(module.split('.')) if module and all(safe_name(x) for x in module.split('.')) else None
            imports.append({'module':module,'level':getattr(node,'level',0),'symbols':[{'name':a.name,'alias':safe_name(a.asname)} for a in node.names if all(safe_name(x) for x in a.name.split('.'))]})
        elif isinstance(node,ast.Call) and (callee:=symbol(node.func)) and callee.split('.')[-1] in CONSTRUCTORS:
            bindings.append({'callee':callee,'line':node.lineno,'keyword_symbols':{k.arg:symbol(k.value) for k in node.keywords if safe_name(k.arg)},'positional_symbols':[symbol(a) for a in node.args[:12]]})
        elif isinstance(node,(ast.Assign,ast.AnnAssign)):
            for target in node.targets if isinstance(node,ast.Assign) else [node.target]:
                name=symbol(target)
                if name and INTEREST.search(name):slots.append({'target':name,'bound_symbol':symbol(node.value),'line':node.lineno})
    return {'classes':classes[:16],'functions':functions[:32],'imports':imports[:48],
            'constructor_bindings':bindings[:24],'contract_slots':slots[:24],
            'truncated':len(classes)>16 or len(functions)>32 or len(imports)>48 or len(bindings)>24 or len(slots)>24,
            'ast_nodes':len(nodes),'literal_values_exported':False,'runtime_binding_verified':False}
def inspect_source(path):
    require(path in ALLOWED_PATHS and path.suffix=='.py','SOURCE_ALLOWLIST')
    row={'path':str(path),'state':'ABSENT','runtime_imported':False}
    try:
        raw=read_regular(path,maximum=MAX_FILE)
        row.update(state='AST_CONTRACT_OBSERVED',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),contract=project(raw))
    except FileNotFoundError:pass
    except (OSError,Hold,UnicodeError,SyntaxError,RecursionError):row['state']='HOLD_SOURCE_UNREADABLE_OR_INVALID'
    return row
def sources():
    paths=[ROOT/'scripts'/n for n in SCRIPT_NAMES];resolution=[]
    for module,roots in MODULE_ROOTS.items():
        origins=[]
        for root in roots:
            try:
                plain(root)
                spec=importlib.machinery.PathFinder.find_spec(module,[str(root)])
                if spec and spec.origin and Path(spec.origin) in ALLOWED_PATHS and Path(spec.origin).suffix=='.py':
                    path=Path(spec.origin);plain(path);origins.append(path)
            except (OSError,Hold,ImportError,ValueError):continue
        resolution.append({'module':module,'origins':[str(p) for p in origins],'resolution_only_no_import':True})
        paths.extend(origins)
    paths=list(dict.fromkeys(paths));require(len(paths)<=14,'SOURCE_COUNT')
    return [inspect_source(p) for p in paths],resolution
def main():
    global DEADLINE,AST_READ_STARTED
    DEADLINE=time.monotonic()+240;AST_READ_STARTED=False;OBSERVATION.clear()
    source=os.environ.get('NOX_OWNER_SOURCE_SHA','');request=os.environ.get('NOX_OWNER_REQUEST_ID','')
    require(re.fullmatch('[a-f0-9]{40}',source) and re.fullmatch('[0-9]{1,24}',request),'OWNER_CONTEXT')
    flag_presence()
    lockpath=plain(STATE/'owner_maintenance.lock')
    lock=os.open(lockpath,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(lock);require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid(),'LEASE_FILE')
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Hold('HOLD_CAPABILITY_LEASE_BUSY') from None
        count,before=full_stop()
        AST_READ_STARTED=True;rows,resolution=sources()
        require(flags()==before,'FLAGS_CHANGED');stopped()
        result={'schema':'NOX_STOP_AND_S03_AST_V1','run_id':'NOX-49-20261117','instance':60509551,
                'source_sha':source,'request':request,'sources':rows,'module_resolution':resolution,
                'state':'OLD_NOX_QUIESCENT_AND_AST_INSPECTION_COMPLETE','stopped_services':count,'stop_flags_unchanged':True,
                'database_opened':False,'weights_opened':False,'runtime_modules_imported':False,
                'source_writes':len(OBSERVATION.get('stop_flags_created',[])),
                'private_literals_exported':False,'runtime_bindings_verified':False,'stop_observation':OBSERVATION,
                'training_resume':False,'checkpoint_created_claim':False,'source_deleted':False,'ast_read_started':True}
        require(len(json.dumps(result).encode())<=MAX_OUTPUT,'TOTAL_OUTPUT_BOUND')
        return result
    finally:os.close(lock)
def failure_record(exc):
    return {'schema':'NOX_STOP_AND_S03_AST_V1','run_id':'NOX-49-20261117','instance':60509551,
            'state':str(exc) if isinstance(exc,Hold) else 'HOLD_CAPABILITY_UNEXPECTED',
            'source_writes':len(OBSERVATION.get('stop_flags_created',[])), 'database_opened':False,'weights_opened':False,
            'stop_observation':OBSERVATION,'ast_read_started':AST_READ_STARTED,'training_resume':False,'source_deleted':False}
if __name__=='__main__':
    def deadline(*args):raise Hold('HOLD_CAPABILITY_DEADLINE')
    signal.signal(signal.SIGALRM,deadline);signal.alarm(250)
    try:
        print('NOX_MAINT_S03_CONTRACT='+json.dumps(main(),sort_keys=True),flush=True)
        print('NOX_MAINT_DEPLOY_COMPLETE=true',flush=True)
    except Exception as exc:
        print('NOX_MAINT_S03_CONTRACT='+json.dumps(failure_record(exc),sort_keys=True),flush=True)
        raise SystemExit(2)
    finally:signal.alarm(0)
