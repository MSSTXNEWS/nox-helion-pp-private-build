#!/usr/bin/env python3
"""Bounded, read-only successor observation; metadata is not tensor proof.

Only exact native source definitions are loaded. No issuer main/finalizer,
training/status full checkpoint hash, service control, flag or config write,
model request or media request is performed. Public staging logs remain
uncorrelated telemetry; current progress needs the actual admitted PID/binding.
"""
import configparser
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import time
import types
import urllib.request

ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
INSTALLER = SCRIPTS / 'owner_qwen_revision_install.py'
INSTALLER_SHA = 'd562ff23fcf21fb0873a93e6e68b23f0dffa87db07e3fe309bed3e750d0080e6'
SHARED_SHA = 'd3b2905c568d088cde2d8267f02f9e913f9fe1d3e46f590992c3a7fcb138ae14'
SCHEMA = 'NOX_QWEN_SUCCESSOR_METADATA_OBSERVATION_V1'
KIND = 'qwen_successor_metadata_observation'
PREFIX = 'NOX_MAINT_REPAIR='
OWNER_UID = 0
PROC = Path('/proc')
CHAT_PID = 7637
CHAT_START = 149189867
JOURNALS = {
    'watcher_ready.json': 'NOX_QWEN_SUCCESSOR_WATCHER_READY_V1',
    'start_receipt.json': 'NOX_QWEN_SUCCESSOR_START_RECEIPT_V1',
    'watcher_result.json': 'NOX_QWEN_SUCCESSOR_WATCHER_RESULT_V1',
}


class Hold(RuntimeError):
    pass


class Deadline(BaseException):
    pass


def require(ok, code):
    if not ok: raise Hold('HOLD_QWEN_SUCCESSOR_OBSERVE_' + code)


def safe(exc):
    if isinstance(exc, Deadline): return 'HOLD_QWEN_SUCCESSOR_OBSERVE_DEADLINE'
    text = str(exc)
    return text if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,160}', text) else 'HOLD_QWEN_SUCCESSOR_OBSERVE_UNVERIFIED'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def integer(value):
    return type(value) is int and 0 <= value <= 10**12


def state_code(value):
    return value if isinstance(value, str) and re.fullmatch('[A-Z0-9_]{1,160}', value) else None


def source(path, pin):
    require(isinstance(pin, str) and re.fullmatch('[a-f0-9]{64}', pin), 'SOURCE_NOT_PREPARED')
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (*path.parents,path)), 'SOURCE_PATH')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid==OWNER_UID and before.st_nlink==1
                and not before.st_mode & 0o022 and 0<before.st_size<=262144,'SOURCE_METADATA')
        raw=stream.read(262145)
        identity=lambda s:tuple(getattr(s,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))
        require(len(raw)==before.st_size and identity(before)==identity(os.fstat(stream.fileno()))
                ==identity(path.stat(follow_symlinks=False)) and digest(raw)==pin,'SOURCE_CHANGED')
    return raw


def load(name, raw):
    value=types.ModuleType('_nox_successor_observe_'+name.removesuffix('.py'))
    value.__file__=str(SCRIPTS/name)
    exec(compile(raw,value.__file__,'exec'),value.__dict__)
    return value


def optional(function):
    try: return function()
    except Exception as exc: return {'state':'UNVERIFIED','reason':safe(exc)}


def ready_metadata_binding(shared,ctx,row):
    desc=ctx['execution']['descriptor']
    require(row.get('schema')==JOURNALS['watcher_ready.json'] and row.get('execution_revision')==ctx['context']
            and row.get('watcher_source_sha256')==desc['activation_watcher_sha256']
            and row.get('verifier_sha256')==SHARED_SHA and row.get('issuer_source_sha256')==INSTALLER_SHA
            and row.get('start_capability') is False and shared.process_identity_valid(row.get('process_identity'))
            and finite(row.get('armed_at')) and desc['created_at']<=row['armed_at']<=time.time()+2,'READY_SOURCE')


def journal_metadata(shared, ctx, name):
    require(name in JOURNALS,'JOURNAL_SCOPE')
    path=ctx['execution']['directory']/name
    if not path.exists() and not path.is_symlink(): return {'present':False,'state':'ABSENT'}
    row,raw=shared.document(path,16384,private=True)
    require(row.get('schema')==JOURNALS[name] and row.get('execution_revision')==ctx['context'],'JOURNAL_CONTEXT')
    out={'present':True,'sha256':digest(raw),'bytes':len(raw),'schema':row['schema']}
    for key in ('state','activation_observation'):
        if key in row:
            require(state_code(row[key]) is not None,'JOURNAL_STATE');out[key]=row[key]
    for key in ('active','optimizer_permission_issued','ordinary_guard_verified','read_only',
                'start_capability','start_command_issued','finalizer_called_once','flags_changed_by_watcher'):
        if key in row:
            require(type(row[key]) is bool or key in {'active','optimizer_permission_issued'} and row[key] is None,
                    'JOURNAL_BOOLEAN');out[key]=row[key]
    for key in ('armed_at','finished_at','started_at','sampled_at'):
        if key in row:
            require(finite(row[key]),'JOURNAL_TIME');out[key]=row[key]
    for key in ('watcher_source_sha256','verifier_sha256','issuer_source_sha256','watcher_ready_sha256','start_receipt_sha256'):
        if key in row:
            require(shared.sha(row[key]),'JOURNAL_SHA');out[key]=row[key]
    who=row.get('process_identity')
    if name=='start_receipt.json':
        trainer=row.get('trainer') or {};who=trainer.get('process_identity')
        service=trainer.get('service') or {}
        require(row.get('start_command_issued') is True and type(row.get('start_command_returncode')) is int
                and row['start_command_returncode']==0 and service.get('state')=='RUNNING'
                and integer(service.get('pid')) and service['pid']>1,'START_RECEIPT')
        out['service_at_start']={'state':'RUNNING','pid':service['pid']}
        ready,ready_raw=shared.document(ctx['execution']['directory']/'watcher_ready.json',16384,private=True)
        ready_metadata_binding(shared,ctx,ready)
        require(row.get('watcher_ready_sha256')==digest(ready_raw) and finite(row.get('started_at'))
                and finite(row.get('sampled_at')) and ready['armed_at']<=row['started_at']<=row['sampled_at']<=time.time()+2,
                'START_READY_LINK')
    require(shared.process_identity_valid(who),'JOURNAL_PROCESS')
    out['process_identity']=who
    desc=ctx['execution']['descriptor']
    if name!='start_receipt.json':
        require(row.get('watcher_source_sha256')==desc['activation_watcher_sha256'],'JOURNAL_WATCHER_SOURCE')
    if name=='watcher_ready.json':
        ready_metadata_binding(shared,ctx,row)
    if 'start_receipt_sha256' in row:
        _,start_raw=shared.document(ctx['execution']['directory']/'start_receipt.json',16384,private=True)
        require(row['start_receipt_sha256']==digest(start_raw),'RESULT_START_LINK')
    return out


def checkpoint_metadata(shared,ctx):
    pointer,raw=shared.document(ctx['output']/'latest_checkpoint.json',16384)
    name=pointer.get('directory');pin=pointer.get('manifest_sha256')
    require(isinstance(name,str) and shared.NAME.fullmatch(name) and shared.sha(pin),'CHECKPOINT_POINTER')
    directory=ctx['output']/name
    manifest,_=shared.document(directory/'checkpoint_manifest.json',65536,expected=pin)
    require(manifest.get('directory')==name,'CHECKPOINT_DIRECTORY')
    saved,_=shared.document(directory/'student_state.json',expected=manifest.get('files_sha256',{}).get('student_state.json'))
    proof=shared.checkpoint_binding(ctx,manifest,saved,allow_initial_anchor=True)
    total=0
    for filename in manifest['files_sha256']:
        path=shared.plain(directory/filename);info=path.stat(follow_symlinks=False)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and 0<=info.st_size<=2*1024**3,'CHECKPOINT_FILE_METADATA')
        total+=info.st_size
    require(total<=2*1024**3 and shared.read(ctx['output']/'latest_checkpoint.json',16384)==raw,'CHECKPOINT_CHANGED')
    witness=proof['witness']
    who=manifest.get('process_identity')
    require(shared.process_identity_valid(who),'CHECKPOINT_PROCESS_METADATA')
    return {'state':'CHECKPOINT_METADATA_OBSERVED','scope':'HASH_BOUND_METADATA_ONLY',
        'directory':name,'pointer_sha256':digest(raw),'manifest_sha256':pin,'student_state_sha256':proof['student_state_sha256'],
        'recorded_files':len(manifest['files_sha256']),'observed_file_bytes':total,
        'metadata_hashes_verified':True,'full_checkpoint_files_verified':False,
        'initial_anchor':proof['initial_anchor'],'current_execution':proof['current_execution'],
        'checkpoint_process_identity':who,
        'successful_total':saved['successful_total'],'attempted_total':saved['attempted_total'],'skipped_total':saved['skipped_total'],
        'evaluated_at_update':saved['holdout_evaluated_successful_total'],
        'holdout_loss':saved['last_holdout_loss'],
        'new_saved_updates_recorded':max(0,saved['successful_total']-25) if proof['current_execution'] else 0,
        'new_optimizer_updates_full_verified':False,
        'evaluation_witness':{'kind':witness['kind'],'process_identity':witness['process_identity'],
            'finished_at':witness['finished_at'],'evaluated_at_update':witness['evaluated_successful_total'],
            'holdout_examples':witness['holdout_examples'],'state_unchanged_during_evaluation':witness['before']==witness['after']}}


def progress_metadata(shared,ctx,live):
    path=ctx['output']/'owner_progress.json'
    if not path.exists() and not path.is_symlink():return {'present':False,'state':'ABSENT'}
    row,raw=shared.document(path,65536)
    require(row.get('state') in {'NATIVE_EXECUTION_EVALUATION_CHECKPOINTED','NATIVE_STUDENT_UPDATE_OBSERVED'},'PROGRESS_STATE')
    keys=('successful_optimizer_steps','attempted_steps','skipped_steps','holdout_evaluated_successful_total')
    require(all(integer(row.get(k)) for k in keys) and row['successful_optimizer_steps']<=1000
            and row['attempted_steps']==row['successful_optimizer_steps']+row['skipped_steps']
            and row['holdout_evaluated_successful_total']<=row['successful_optimizer_steps']
            and finite(row.get('time')) and 0<row['time']<=time.time()+2 and finite(row.get('loss')) and shared.sha(row.get('adapter_tensor_sha256'))
            and shared.process_identity_valid(row.get('process_identity'))
            and row.get('pid')==row['process_identity']['pid'] and type(row.get('optimizer_permission_verified')) is bool,
            'PROGRESS_FIELDS')
    binding=row.get('execution_binding');current=binding==shared.execution_binding(ctx)
    require(current or binding==shared.predecessor_binding(),'PROGRESS_EXECUTION')
    require(not current or row['time']>=ctx['execution']['descriptor']['created_at'],'PROGRESS_ATTEMPT_TIME')
    process_bound=(current and live['service']['state']=='RUNNING' and row['process_identity']==live['process_identity'])
    permission=(process_bound and row['state']=='NATIVE_STUDENT_UPDATE_OBSERVED'
                and row['optimizer_permission_verified'] is True and row['successful_optimizer_steps']>25)
    return {'present':True,'state':row['state'],'sha256':digest(raw),'bytes':len(raw),'sampled_at':row['time'],
        'age_seconds':max(0,time.time()-row['time']),'process_identity':row['process_identity'],
        'current_execution':current,'historical_predecessor':not current,'current_process_bound':process_bound,
        **{k:row[k] for k in keys},'loss':row['loss'],
        'current_process_optimizer_permission_reported':permission,
        'new_current_process_updates_reported':max(0,row['successful_optimizer_steps']-25) if permission else 0,
        'full_checkpoint_files_verified':False}


def guard_metadata(shared,ctx):
    name='owner_qwen_training_guard.py';pin=ctx['execution']['descriptor']['consumer_sources'][name]
    guard=load(name,source(SCRIPTS/name,pin))
    cfg,cfg_sha=guard.checked_config(ctx['context'],pin)
    row,raw=shared.document(guard.STATUS,65536,private=True)
    require(row.get('bindings')==guard.bindings(cfg,cfg_sha,ctx) and finite(row.get('sampled_at')),'GUARD_BINDING')
    age=time.time()-row['sampled_at'];policy=row.get('policy_state') or {};safe_policy={}
    for key in ('inhibit','complete','floor_already_crossed'):
        if key in policy:require(type(policy[key]) is bool,'GUARD_BOOLEAN');safe_policy[key]=policy[key]
    for key in ('reason',):
        if key in policy:require(policy[key] is None or state_code(policy[key]) is not None,'GUARD_REASON');safe_policy[key]=policy[key]
    for key in ('last_successful_updates','last_evaluation_update','evaluation_age_updates','best_holdout_loss',
                'regression_streak','observed_distinct_evaluations','latched_at','last_free_bytes','disk_early_threshold_bytes'):
        if key in policy:require(policy[key] is None or finite(policy[key]),'GUARD_NUMBER');safe_policy[key]=policy[key]
    require(state_code(row.get('state')) is not None,'GUARD_STATE')
    cp=row.get('checkpoint') or {}
    return {'state':row['state'],'sha256':digest(raw),'age_seconds':age,'fresh':0<=age<=30,'policy_state':safe_policy,
            'checkpoint_manifest_sha256':cp.get('manifest_sha256') if shared.sha(cp.get('manifest_sha256')) else None}


def chat_identity():
    path=PROC/str(CHAT_PID)
    try:
        with (path/'stat').open('rb') as stream: raw=stream.read(8193)
        require(len(raw)<=8192,'CHAT_STAT_BOUND')
        fields=raw[raw.rfind(b')')+2:].split();start=int(fields[19])
        with (path/'cmdline').open('rb') as stream:args=stream.read(32769).split(b'\0')
        require(sum(map(len,args))<=32768,'CHAT_ARGV_BOUND')
        port=args.index(b'--port');actual_port=args[port+1]
        with (path/'comm').open('rb') as stream:comm=stream.read(64).strip()
        return {'pid':CHAT_PID,'start_ticks':start,'same_original':start==CHAT_START and comm==b'llama-server'
                and actual_port==b'8081' and fields[0]!=b'Z'}
    except Exception:return {'pid':CHAT_PID,'same_original':False,'state':'UNVERIFIED'}


def health():
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect());out={}
    for port in (8080,8081,8082):
        try:
            with opener.open('http://127.0.0.1:'+str(port)+'/health',timeout=2) as response:out[str(port)]=response.status
        except Exception:out[str(port)]=None
    return out


def observed_state(live,activation,progress):
    running=live['service']['state']=='RUNNING' and live['process_identity'] is not None
    if not running:return 'TRAINER_NOT_RUNNING_METADATA_OBSERVED'
    if activation.get('active') is True and progress.get('current_process_optimizer_permission_reported') is True:
        return 'RUNNING_CURRENT_PROCESS_UPDATE_PROGRESS_RECORDED'
    if activation.get('active') is True:return 'ACTIVATION_PRESENT_CURRENT_UPDATE_PROGRESS_PENDING'
    return 'RUNNING_BOOTSTRAP_OR_PERMISSION_PENDING'


def observe():
    shared=load('owner_qwen_execution_revision.py',source(SCRIPTS/'owner_qwen_execution_revision.py',SHARED_SHA))
    ctx=shared.current_context()
    require(ctx['execution']['descriptor']['activation_issuer_sha256']==INSTALLER_SHA,'ISSUER_DESCRIPTOR_PIN')
    core=load(INSTALLER.name,source(INSTALLER,INSTALLER_SHA));core.protected()
    live=core.trainer(ctx)
    activation=shared.activation_status(ctx)
    journals={name.removesuffix('.json'):optional(lambda n=name:journal_metadata(shared,ctx,n)) for name in JOURNALS}
    cp=optional(lambda:checkpoint_metadata(shared,ctx))
    progress=optional(lambda:progress_metadata(shared,ctx,live))
    guard=optional(lambda:guard_metadata(shared,ctx))
    flags={}
    for name in ('TRAIN_HOLD.flag','TRAIN_PAUSE_REQUEST.flag','OWNER_MAINTENANCE.flag','STOP'):
        path=shared.STATE/name
        if not path.exists() and not path.is_symlink():flags[name]={'present':False};continue
        def flag(p=path):
            raw=shared.read(p,4096);return {'present':True,'sha256':digest(raw),'bytes':len(raw)}
        flags[name]=optional(flag)
    logs=transport_telemetry(core,ctx)
    chat=chat_identity();chat_health=health()
    after=core.trainer(ctx);shared.current_context(ctx['context'])
    activation=shared.activation_status(ctx)
    consistent=after==live
    if not consistent:
        progress.update(current_process_bound=False,current_process_optimizer_permission_reported=False,
                        new_current_process_updates_reported=0)
    return {'schema':SCHEMA,'state':observed_state(after,activation,progress) if consistent else 'TRAINER_CHANGED_DURING_OBSERVATION',
        'observed_at':time.time(),'read_only':True,'execution_revision':ctx['context'],
        'execution_binding':shared.execution_binding(ctx),'source_pins':{'shared':SHARED_SHA,'issuer':INSTALLER_SHA},
        'trainer':after,'trainer_consistent':consistent,'checkpoint':cp,'progress':progress,'guard':guard,'journals':journals,
        'activation':{k:activation.get(k) for k in ('active','bootstrap_pending','deadline','permit_sha256','initial_process_identity')},
        'flags':flags,'transport_telemetry':logs,'chat_model_identity':chat,'chat_health':chat_health,
        'full_checkpoint_files_verified':False,'new_optimizer_updates_full_verified':False,
        'general_intelligence_improvement_proven':False,'services_or_flags_modified':False}


def deadline(*_):raise Deadline()


def main():
    prior=signal.getsignal(signal.SIGALRM);signal.signal(signal.SIGALRM,deadline)
    timer=signal.setitimer(signal.ITIMER_REAL,40)
    try:
        result=observe();encoded=json.dumps({'kind':KIND,'data':result},sort_keys=True,allow_nan=False,separators=(',',':'))
        require(len(encoded.encode())<=131072,'OUTPUT_BOUND')
        print(PREFIX+encoded,flush=True);print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True);return 0
    except (Exception,Deadline) as exc:
        print(PREFIX+json.dumps({'kind':KIND,'data':{'schema':SCHEMA,'state':'UNVERIFIED','reason':safe(exc),
            'read_only':True,'full_checkpoint_files_verified':False,'services_or_flags_modified':False}},separators=(',',':')),flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false',flush=True);return 2
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,prior)
        if timer[0]:signal.setitimer(signal.ITIMER_REAL,*timer)




def transport_events(raw):
    """Project bounded public transport fields; never associate logs with a PID."""
    events = []
    allowed_types = {'TimeoutError', 'ConnectionResetError', 'URLError', 'HTTPError',
                     'IncompleteRead', 'RemoteDisconnected', 'SSLEOFError', 'SSLZeroReturnError',
                     'SSLCertVerificationError', 'gaierror', 'OSError', 'BrokenPipeError',
                     'ConnectionAbortedError', 'ConnectionRefusedError', 'BlockingIOError',
                     'InterruptedError', 'SSLError', 'OTHER_EXCEPTION'}
    def unique(pairs):
        row = {}
        for key, value in pairs:
            if key in row:
                raise ValueError('duplicate')
            row[key] = value
        return row
    for line in raw[-65536:].split(b'\n'):
        if not 1 <= len(line) <= 4096:
            continue
        try:
            row = json.loads(line, object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
        except (ValueError, UnicodeError):
            continue
        if (not isinstance(row, dict) or row.get('state') != 'PINNED_PUBLIC_BASE_STAGING'
                or row.get('transport_version') != 'NOX_QWEN_PUBLIC_TRANSPORT_V1'):
            continue
        stage = row.get('stage', 'PROGRESS')
        offset, total = row.get('bytes'), row.get('total')
        committed = row.get('committed_offset', offset)
        if (not isinstance(stage, str) or stage not in {'OPEN', 'READ', 'WRITE', 'CLOSE', 'VERIFIED', 'PROGRESS'}
                or type(offset) is not int or type(total) is not int
                or not 0 <= offset <= total <= 20 * 1024 ** 3
                or type(committed) is not int or committed != offset):
            continue
        attempt = row.get('attempt')
        if stage != 'PROGRESS' and (type(attempt) is not int or not 1 <= attempt <= 6):
            continue
        event = {'stage': stage, 'attempt': attempt if type(attempt) is int and 1 <= attempt <= 6 else None,
                 'committed_offset': offset, 'total_bytes': total}
        for key, low, high in (('http_status', 100, 599), ('errno', -65535, 65535)):
            value = row.get(key)
            event[key] = value if type(value) is int and low <= value <= high else None
        for key in ('staging_elapsed_seconds', 'io_elapsed_seconds'):
            value = row.get(key)
            event[key] = value if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 7200 else None
        value = row.get('exception_type')
        event['exception_type'] = value if isinstance(value, str) and value in allowed_types else ('OTHER_EXCEPTION' if value is not None else None)
        events.append(event)
    return events[-24:]


def transport_telemetry(core, ctx):
    """Use the exact pinned window's supervisor/stdout scope, at most 64KiB."""
    result = {'transport_version': 'NOX_QWEN_PUBLIC_TRANSPORT_V1', 'may_include_prior_runs': True,
              'current_process_bound': False, 'full_weights_integrity_proven': False,
              'raw_text_exported': False, 'events': []}
    try:
        helper = ctx['helper']
        raw_config = helper.read(helper.SUPERVISOR)
        core.require(helper.digest(raw_config) == helper.SUPERVISOR_SHA, 'TRANSPORT_SUPERVISOR_PIN')
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(raw_config.decode())
        name = config.get('program:' + helper.SERVICE, 'stdout_logfile', fallback='')
        core.require(name and name.upper() not in {'AUTO', 'NONE'}, 'TRANSPORT_NO_EXPLICIT_LOG_PATH')
        path = Path(name)
        core.require(path.is_absolute() and path.resolve() == path
                     and path.is_relative_to(helper.ROOT / 'logs'), 'TRANSPORT_LOG_SCOPE')
        fd = os.open(helper.plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            core.require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid(), 'TRANSPORT_LOG_TYPE')
            offset = max(0, before.st_size - 65536)
            stream.seek(offset); raw = stream.read(min(65536, before.st_size))
            after, named = os.fstat(stream.fileno()), path.stat(follow_symlinks=False)
            core.require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
                         == (named.st_dev, named.st_ino) and after.st_size >= before.st_size
                         and named.st_size >= before.st_size and len(raw) == before.st_size - offset,
                         'TRANSPORT_LOG_CHANGED')
        result.update(status='BOUNDED_LOG_TELEMETRY', log_bytes=before.st_size, mtime_ns=before.st_mtime_ns,
                      tail_bytes_read=len(raw), events=transport_events(raw))
    except Exception as exc:
        value = str(exc)
        result.update(status='UNAVAILABLE', reason=value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,160}', value)
                      else 'HOLD_TRANSPORT_LOG_' + type(exc).__name__.upper())
    return result

if __name__=='__main__':raise SystemExit(main())
