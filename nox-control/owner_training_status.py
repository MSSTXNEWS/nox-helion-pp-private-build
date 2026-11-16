"""Read-only, receipt-bound training facts for the existing owner chat.

Global steps, successful optimizer updates and AMP skips are distinct. Saved
checkpoints are hashed once per unchanged file identity; the HF base, dataset,
private examples and tensor values are never loaded. This module does not admit,
start, stop, merge or promote training. Its context is installed only after the
operator has obtained the actual sealed native admission receipt.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
import time

ROOT = Path('/root/nox')
PROC = Path('/proc')
SCHEMA = 'NOX_OWNER_CURRENT_TRAINING_EVIDENCE_V1'
TRAIN_SCHEMA = 'NOX_T866U_FP32_ADAPTER_CONTINUATION_V1'
CONFIG_SCHEMA = 'NOX_OWNER_TRAINING_STATUS_CONFIG_V1'
AMP_CALIBRATION = {
    'schema':'NOX_OWNER_AMP_CALIBRATION_V1',
    'origin_admission':{'request':'6905764817','source_sha':'e4549616aa13295febc44dc78a3a033870f9071d',
                        'receipt_sha256':'960e96fba9d24bb0835df1a46bf9971f770aaab78c0587e20a897b53fd6aeb46'},
    'checkpoint_receipt_sha256':'ba19160382025630d41f8187122bc1f51c7aa3abe2c2a8608e9b8804eeac72fe',
    'lineage_sha256':'b2bc1b3630ba40736acdc309b7aa8ea631a756da4913b425ad2e5efcbd7f74bd',
    'start_step':5,'target_step':20,'planned_steps':1000,
    'hybrid_sha256':'f2ba60d6556ba3662713db0e503773f2361b82b6c83391be4e56a506aad8c0af',
    'optimizer_state_preserved':True,'scaler_state_preserved':True,'rng_state_preserved':True,
    'successful_optimizer_steps_before':0,
}
SERVICE = 'nox-train-volta-t866u'
NATIVE_SHA = '703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a'
HYBRID_SHAS = frozenset({
    '54e1707dd25a7128690e90722ced5885a3fcb347b50126e69e3cac216cf6c557',
    '7a384bbee919bec9b24642cc5f56b930cc986065172d7a334cc682c7ee40e455',
    'f2ba60d6556ba3662713db0e503773f2361b82b6c83391be4e56a506aad8c0af',
})
FILES = ('adapter_config.json', 'trainer_state.json', 'scaler.pt', 'rng_state.pth',
         'scheduler.pt', 'optimizer.pt', 'adapter_model.safetensors')
SHA = re.compile(r'[a-f0-9]{64}')
_HASH_LOCK = threading.Lock()
_HASH_CACHE = {}
_VERIFY_LOCK = threading.Lock()
HASH_SECONDS = 4.0


class StatusHold(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise StatusHold(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def json_sha(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def output():
    return ROOT/'lora/qlora_t866u/runs_owner_hybrid'


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def plain(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts
            and not any(p.is_symlink() for p in (path, *path.parents)), 'HOLD_TRAINING_STATUS_PATH')
    return path


@contextmanager
def opened(path, maximum):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and not before.st_mode & 0o022 and 0 <= before.st_size <= maximum,
                'HOLD_TRAINING_STATUS_FILE')
        yield fd, before
        after = os.fstat(fd); named = path.stat(follow_symlinks=False)
        require(identity(before) == identity(after) == identity(named), 'HOLD_TRAINING_STATUS_FILE_CHANGED')
    finally:
        os.close(fd)


def read(path, maximum=262144, tail=False):
    with opened(path, 1024**3 if tail else maximum) as (fd, info):
        if tail:
            os.lseek(fd, max(0, info.st_size-maximum), os.SEEK_SET)
        raw = os.read(fd, maximum+1)
        require(len(raw) == min(info.st_size,maximum) and len(raw) <= maximum,
                'HOLD_TRAINING_STATUS_READ_BOUND')
        return raw


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'HOLD_TRAINING_STATUS_DUPLICATE_JSON_KEY')
        value[key] = item
    return value


def document(path, maximum=262144):
    raw = read(path, maximum)
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(StatusHold('HOLD_TRAINING_STATUS_NONFINITE_JSON')))
    require(isinstance(value, dict), 'HOLD_TRAINING_STATUS_JSON')
    return value, digest(raw)


def bounded_int(value, low=0, high=1000):
    return type(value) is int and low <= value <= high


def valid_sha(value):
    return isinstance(value, str) and bool(SHA.fullmatch(value))


def trainer_state_projection(raw, expected_step, expected_sha):
    """Project one hash-bound HF state without exporting its private history.

    AMP skips may leave nonfinite grad_norm diagnostics in log_history. Only
    that immediate metadata field is admitted; it is never optimizer evidence.
    All receipts, lineage and other documents retain their strict JSON decoder.
    """
    require(isinstance(raw, bytes) and len(raw) <= 1024**2 and valid_sha(expected_sha)
            and digest(raw) == expected_sha, 'HOLD_TRAINING_STATUS_TRAINER_STATE_HASH')
    diagnostic_number = object()
    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: diagnostic_number)
    except RecursionError:
        raise StatusHold('HOLD_TRAINING_STATUS_TRAINER_METADATA_BUDGET') from None
    require(isinstance(value, dict) and bounded_int(value.get('global_step'),1)
            and value['global_step'] == expected_step, 'HOLD_TRAINING_STATUS_TRAINER_STATE')
    history = value.get('log_history', [])
    require(isinstance(history, list) and len(history) <= 1024
            and all(isinstance(row, dict) for row in history),
            'HOLD_TRAINING_STATUS_TRAINER_DIAGNOSTIC_SCOPE')
    pending = [(value, (), 0)]; visited = nonfinite = 0
    while pending:
        item, path, depth = pending.pop(); visited += 1
        require(depth <= 32 and visited <= 20000, 'HOLD_TRAINING_STATUS_TRAINER_METADATA_BUDGET')
        if item is diagnostic_number or (type(item) is float and not math.isfinite(item)):
            require(len(path) == 3 and path[0] == 'log_history' and type(path[1]) is int
                    and path[2] == 'grad_norm', 'HOLD_TRAINING_STATUS_TRAINER_DIAGNOSTIC_SCOPE')
            nonfinite += 1
        elif isinstance(item, dict):
            pending.extend((child, path+(key,), depth+1) for key,child in item.items())
        elif isinstance(item, list):
            pending.extend((child, path+(index,), depth+1) for index,child in enumerate(item))
    return {'global_step': value['global_step'], 'raw_sha256': expected_sha,
            'nonfinite_grad_norm_diagnostics': nonfinite,
            'nonfinite_metadata_scope': 'HF_LOG_HISTORY_GRAD_NORM_ONLY',
            'metadata_used_as_optimizer_evidence': False, 'history_text_exported': False}


def context_value(context=None):
    if context is None:
        value, _ = document(ROOT/'config/owner_training_status.json', 16384)
        require(value.get('schema') == CONFIG_SCHEMA and set(value) == {'schema','admission'},
                'HOLD_TRAINING_STATUS_CONFIGURATION')
        context = value['admission']
    require(isinstance(context, dict) and set(context) == {'request','source_sha','receipt_sha256'}
            and isinstance(context.get('request'), str) and re.fullmatch(r'[0-9]{1,24}', context['request'])
            and isinstance(context.get('source_sha'), str) and re.fullmatch(r'[a-f0-9]{40}', context['source_sha'])
            and valid_sha(context.get('receipt_sha256')), 'HOLD_TRAINING_STATUS_CONTEXT')
    return dict(context)


def admission(context):
    receipt, receipt_sha = document(ROOT/'state'/('owner_maintenance_'+context['request']+'.json'), 2*1024**2)
    pointer, _ = document(ROOT/'state/owner_training_admission.json')
    require(receipt_sha == context['receipt_sha256'] and receipt.get('schema') == 'NOX_OWNER_TRAINING_RESUME_V1'
            and receipt.get('request') == context['request'] and receipt.get('source_sha') == context['source_sha']
            and pointer == receipt.get('admission') and pointer.get('schema') == 'NOX_OWNER_TRAINING_ADMISSION_V1'
            and pointer.get('request') == context['request'] and pointer.get('source_sha') == context['source_sha']
            and type(pointer.get('max_steps')) is int and pointer['max_steps'] in (5,20,1000)
            and type(pointer.get('resume')) is bool, 'HOLD_TRAINING_STATUS_ADMISSION_CHANGED')
    hybrid = ROOT/'scripts/hybrid_training_entry.py'
    hybrid_sha = (pointer.get('sources') or {}).get(str(hybrid))
    require(hybrid_sha in HYBRID_SHAS and digest(read(hybrid)) == hybrid_sha
            and digest(read(ROOT/'scripts/train_qlora_35b_t866u.py')) == NATIVE_SHA,
            'HOLD_TRAINING_STATUS_SOURCE_CHANGED')
    if pointer['max_steps'] == 20:
        require(pointer['resume'] is True and json_sha(pointer.get('amp_calibration')) == json_sha(AMP_CALIBRATION)
                and json_sha(receipt.get('amp_calibration')) == json_sha(AMP_CALIBRATION)
                and hybrid_sha == AMP_CALIBRATION['hybrid_sha256'],
                'HOLD_TRAINING_STATUS_CALIBRATION_SCOPE')
        origin = AMP_CALIBRATION['origin_admission']
        _,origin_sha = document(ROOT/'state'/('owner_maintenance_'+origin['request']+'.json'),2*1024**2)
        baseline,baseline_sha = document(output()/'owner_receipt_step_5.json')
        baseline_metadata = checkpoint_metadata(baseline,AMP_CALIBRATION['lineage_sha256'])
        require(origin_sha == origin['receipt_sha256'] and baseline_sha == AMP_CALIBRATION['checkpoint_receipt_sha256']
                and baseline_metadata['global_step'] == 5 and baseline_metadata['start_step'] == 0
                and baseline_metadata['successful_optimizer_steps'] == 0,
                'HOLD_TRAINING_STATUS_CALIBRATION_BASELINE')
    return receipt, pointer


def checkpoint_metadata(value, lineage_sha=None):
    require(isinstance(value, dict), 'HOLD_TRAINING_STATUS_CHECKPOINT_SCHEMA')
    step, start = value.get('global_step'), value.get('start_step')
    good, skipped = value.get('successful_optimizer_steps'), value.get('skipped_optimizer_steps')
    before, after = value.get('before_tensor_sha256'), value.get('after_tensor_sha256')
    loss = value.get('loss'); lineage = value.get('lineage_sha256')
    require(value.get('schema') == TRAIN_SCHEMA and value.get('native_sha256') == NATIVE_SHA
            and bounded_int(step,1) and bounded_int(start) and start < step
            and bounded_int(good) and bounded_int(skipped) and good+skipped == step-start
            and type(loss) in (int,float) and math.isfinite(loss)
            and valid_sha(lineage) and (lineage_sha is None or lineage == lineage_sha)
            and valid_sha(before) and valid_sha(after)
            and ((good > 0 and before != after and value.get('adapter_delta_verified') is True)
                 or (good == 0 and before == after and value.get('adapter_delta_verified') is False))
            and value.get('merged') is False and value.get('live_promoted') is False,
            'HOLD_TRAINING_STATUS_OPTIMIZER_COUNTERS_OR_DELTA')
    cp = value.get('checkpoint') or {}; hashes = cp.get('files_sha256') or {}
    require(cp.get('path') == str(output()/('checkpoint-'+str(step))) and cp.get('global_step') == step
            and set(hashes) == set(FILES) and all(valid_sha(v) for v in hashes.values()),
            'HOLD_TRAINING_STATUS_CHECKPOINT_SCOPE')
    return {'global_step':step,'start_step':start,'successful_optimizer_steps':good,
            'skipped_optimizer_steps':skipped,'loss':loss,'lineage_sha256':lineage,
            'before_tensor_sha256':before,'after_tensor_sha256':after,
            'adapter_delta_verified':value['adapter_delta_verified'],
            'positive_optimizer_steps_verified':good > 0}


def verified_file(path, expected, deadline, accounting):
    require(valid_sha(expected), 'HOLD_TRAINING_STATUS_CHECKPOINT_DIGEST')
    with opened(path, 4*1024**3) as (fd, info):
        require(info.st_size > 0, 'HOLD_TRAINING_STATUS_EMPTY_CHECKPOINT_FILE')
        key = (str(path), identity(info), expected)
        with _HASH_LOCK:
            cached = key in _HASH_CACHE
        if not cached:
            require(time.monotonic() < deadline, 'WAIT_TRAINING_STATUS_HASH_BUDGET')
            h = hashlib.sha256()
            while True:
                require(time.monotonic() < deadline, 'WAIT_TRAINING_STATUS_HASH_BUDGET')
                block = os.read(fd, 1024**2)
                if not block:
                    break
                accounting['checkpoint_bytes_hashed'] += len(block); h.update(block)
            require(h.hexdigest() == expected, 'HOLD_TRAINING_STATUS_CHECKPOINT_HASH')
        else:
            accounting['checkpoint_files_from_stat_cache'] += 1
    # opened() verifies descriptor and pathname identity before the cache entry
    # becomes usable. A same-size replacement or restored mtime still changes
    # inode/ctime and cannot reuse an old success.
    with _HASH_LOCK:
        if len(_HASH_CACHE) >= 256:
            _HASH_CACHE.pop(next(iter(_HASH_CACHE)))
        _HASH_CACHE[key] = True


def verify_checkpoint(value, lineage_sha, deadline, accounting):
    record = checkpoint_metadata(value, lineage_sha)
    directory = output()/('checkpoint-'+str(record['global_step']))
    hashes = value['checkpoint']['files_sha256']
    total = 0
    for name in FILES:
        total += plain(directory/name).stat(follow_symlinks=False).st_size
        require(total <= 8*1024**3, 'HOLD_TRAINING_STATUS_CHECKPOINT_TOTAL_BOUND')
        verified_file(directory/name, hashes[name], deadline, accounting)
    record['trainer_state_metadata'] = trainer_state_projection(
        read(directory/'trainer_state.json',1024**2), record['global_step'], hashes['trainer_state.json'])
    return record


def latest_receipt():
    candidates = []
    for count, path in enumerate(plain(output()).iterdir()):
        require(count < 4096, 'HOLD_TRAINING_STATUS_OUTPUT_INVENTORY_BOUND')
        match = re.fullmatch(r'owner_receipt_step_([0-9]{1,4})\.json', path.name)
        if match and 1 <= int(match[1]) <= 1000:
            candidates.append((int(match[1]),path))
    if not candidates:
        return None
    step, path = max(candidates)
    value, receipt_sha = document(path)
    require(value.get('global_step') == step, 'HOLD_TRAINING_STATUS_RECEIPT_STEP')
    return value, receipt_sha


def counter_chain(latest, lineage_sha, deadline, accounting):
    current = latest; total_good = total_skip = 0; segments = 0
    while True:
        record = verify_checkpoint(current,lineage_sha,deadline,accounting)
        total_good += record['successful_optimizer_steps']; total_skip += record['skipped_optimizer_steps']; segments += 1
        require(segments <= 32, 'HOLD_TRAINING_STATUS_RESUME_CHAIN_BOUND')
        if record['start_step'] == 0:
            return {'successful_optimizer_steps':total_good,'skipped_optimizer_steps':total_skip,
                    'verified_run_segments':segments}
        baseline, _ = document(output()/('owner_receipt_step_'+str(record['start_step'])+'.json'))
        previous = checkpoint_metadata(baseline,lineage_sha)
        require(previous['global_step'] == record['start_step']
                and previous['after_tensor_sha256'] == record['before_tensor_sha256'],
                'HOLD_TRAINING_STATUS_RESUME_TENSOR_CHAIN')
        current = baseline


def proc_read(path, maximum):
    # procfs has regular files with st_size=0; its text is never exported.
    with path.open('rb') as stream:
        raw = stream.read(maximum+1)
    require(len(raw) <= maximum, 'HOLD_TRAINING_STATUS_PROC_BOUND')
    return raw


def live_process():
    matches = []; hybrid = str(ROOT/'scripts/hybrid_training_entry.py').encode()
    for count, directory in enumerate(PROC.iterdir()):
        require(count < 8192, 'HOLD_TRAINING_STATUS_PROCESS_BOUND')
        if not directory.name.isdigit():
            continue
        try:
            argv = proc_read(directory/'cmdline',8192).split(b'\0')
            if hybrid not in argv:
                continue
            tail = proc_read(directory/'stat',4096).decode().rsplit(')',1)[1].split()
            if tail[0] == 'Z':
                continue
            fields = proc_read(directory/'environ',131072).split(b'\0')
            selected = {item.partition(b'=')[0]:item.partition(b'=')[2] for item in fields
                        if item.startswith((b'CUDA_VISIBLE_DEVICES=',b'SUPERVISOR_PROCESS_NAME='))}
            require(selected == {b'CUDA_VISIBLE_DEVICES':b'1',b'SUPERVISOR_PROCESS_NAME':SERVICE.encode()},
                    'HOLD_TRAINING_STATUS_PROCESS_ROLE')
            args = [value.decode() for value in argv if value]
            options = {key:args[i+1] for i,key in enumerate(args[:-1])
                       if key in ('--max-steps','--planned-steps','--native-sha')}
            require(options.get('--max-steps') in ('5','20','1000') and options.get('--planned-steps') == '1000'
                    and options.get('--native-sha') == NATIVE_SHA, 'HOLD_TRAINING_STATUS_PROCESS_ARGUMENTS')
            ticks = int(tail[19]); boot = re.search(rb'^btime ([0-9]+)$',proc_read(PROC/'stat',262144),re.M)
            require(boot is not None, 'HOLD_TRAINING_STATUS_PROCESS_TIME')
            after = proc_read(directory/'stat',4096).decode().rsplit(')',1)[1].split()
            require(after[0] != 'Z' and int(after[19]) == ticks, 'HOLD_TRAINING_STATUS_PROCESS_CHANGED')
            matches.append({'pid':int(directory.name),'start_ticks':ticks,
                            'started_at':int(boot[1])+ticks/os.sysconf('SC_CLK_TCK'),
                            'target_global_step':int(options['--max-steps']),'resume_argument': '--resume' in args})
        except (FileNotFoundError,ProcessLookupError,PermissionError):
            continue
    require(len(matches) <= 1, 'HOLD_TRAINING_STATUS_MULTIPLE_TRAINERS')
    return matches[0] if matches else None


def heartbeat(process, now):
    value, _ = document(ROOT/'status/train_volta_t866u.json',16384)
    stamp = value.get('ts')
    require(process is not None and type(stamp) in (int,float) and math.isfinite(stamp)
            and -5 <= now-stamp <= 90 and stamp >= process['started_at']-2
            and value.get('program') == SERVICE and value.get('output') == str(output())
            and value.get('max_steps') == process['target_global_step']
            and bounded_int(value.get('step'),0,process['target_global_step']), 'WAIT_TRAINING_STATUS_FRESH_PROCESS_HEARTBEAT')
    phase = value.get('phase')
    require(phase in ('loading_owner_hybrid','train_owner_hybrid','VERIFIED_BOUNDED_ADAPTER_UPDATE','CHECKPOINTED_OWNER_STOP'),
            'HOLD_TRAINING_STATUS_HEARTBEAT_PHASE')
    result = {'phase':phase,'global_step':value['step'],'observed_at':stamp,
              'successful_optimizer_steps':None,'skipped_optimizer_steps':None,
              'source':'CURRENT_PROCESS_HEARTBEAT','checkpoint_verified_by_heartbeat':False}
    if phase == 'train_owner_hybrid':
        good, skipped = value.get('successful_optimizer_steps'),value.get('skipped_optimizer_steps')
        require(bounded_int(good) and bounded_int(skipped) and good+skipped <= value['step'],
                'HOLD_TRAINING_STATUS_HEARTBEAT_COUNTERS')
        result.update(successful_optimizer_steps=good,skipped_optimizer_steps=skipped,
                      inferred_run_start_step=value['step']-good-skipped)
    return result


def flags(request):
    result = {'hold_present':False,'pause_present':False,'owned_failure':False,'owned_complete':False}
    for name,key in (('TRAIN_HOLD.flag','hold_present'),('TRAIN_PAUSE_REQUEST.flag','pause_present')):
        path = ROOT/'state'/name
        result[key] = path.exists() or path.is_symlink()
    if result['hold_present']:
        raw = read(ROOT/'state/TRAIN_HOLD.flag',4096)
        result['owned_failure'] = raw == ('OWNER_HYBRID_FAILED request='+request+'\n').encode()
        result['owned_complete'] = raw == ('OWNER_HYBRID_BOUNDED_COMPLETE request='+request+'\n').encode()
    return result


def failure_cause(receipt, flag):
    code = receipt.get('error')
    fallback = code if isinstance(code,str) and re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}',code) else None
    if not flag['owned_failure']:
        return fallback
    # Only categorical native markers after a timestamp in this admitted run
    # and before its owned failure latch are eligible. No log line is returned.
    try:
        lower = receipt.get('started'); upper = plain(ROOT/'state/TRAIN_HOLD.flag').stat().st_mtime+2
        require(type(lower) in (int,float) and math.isfinite(lower) and 0 < lower <= upper,
                'HOLD_TRAINING_STATUS_FAILURE_INTERVAL')
        log = read(ROOT/'logs/train_volta_t866u.supervisor.log',65536,tail=True).decode(errors='replace')
        last_time = None; found = None
        for line in log.splitlines():
            date = re.match(r'^\[([0-9-]{10} [0-9:]{8}) Europe/Moscow \(UTC\+3\)\]',line)
            if date:
                last_time = datetime.strptime(date[1],'%Y-%m-%d %H:%M:%S').replace(
                    tzinfo=timezone(timedelta(hours=3))).timestamp()
            marker = re.fullmatch(r'NOX_HYBRID_FAILURE=(HOLD_[A-Z0-9_]{1,100}|[A-Za-z_][A-Za-z0-9_]{0,95})',line.strip())
            if marker and last_time is not None and lower-2 <= last_time <= upper:
                found = marker[1]
        return found or fallback
    except (OSError,ValueError,StatusHold):
        return fallback


def snapshot(context=None):
    now = time.time()
    result = {'schema':SCHEMA,'observed_at':now,'read_only':True,'state':'UNVERIFIED_ADMISSION',
              'positive_optimizer_steps_verified':False,'optimizer_steps':None,'global_step':None,
              'skipped_optimizer_steps':None,'checkpoint_saved_verified':False,
              'historical_verified_checkpoint':None,'latest_verified_checkpoint':None,'current_run':None,
              'checkpoint_restore_verified':False,'current_model_merge_inclusion':'NOT_VERIFIED',
              'base_weights_hashed':False,'private_training_text_exported':False,
              'checkpoint_bytes_hashed':0,'checkpoint_files_from_stat_cache':0}
    try:
        context = context_value(context); sealed,pointer = admission(context)
        result['admission'] = context
        first = sealed.get('five_step_receipt') or sealed.get('checkpointed_result') or sealed.get('bounded_update_receipt')
        if first is not None and (sealed.get('optimizer_steps_verified') is True
                                  or sealed.get('state') in ('TRAINING_CHECKPOINTED_BY_NEW_PAUSE',
                                                            'AMP_CALIBRATION_CHECKPOINTED_BY_PAUSE')):
            prior = checkpoint_metadata(first)
            result['historical_verified_checkpoint'] = {**prior,'scope':'SEALED_NATIVE_ACCEPTANCE',
                                                       'current_checkpoint_files_verified':False}
            result['positive_optimizer_steps_verified'] = prior['positive_optimizer_steps_verified']
            if prior['start_step'] == 0:
                result['optimizer_steps'] = prior['successful_optimizer_steps']
                result['global_step'] = prior['global_step']
                result['skipped_optimizer_steps'] = prior['skipped_optimizer_steps']
        process = live_process(); flag = flags(context['request']); result['flags'] = flag
        if process is not None:
            require(process['target_global_step'] == pointer['max_steps']
                    and process['resume_argument'] is pointer['resume'], 'HOLD_TRAINING_STATUS_PROCESS_ADMISSION')
            result['current_run'] = {'process':process,'telemetry':None}
            try:
                hb = heartbeat(process,now);result['current_run']['telemetry']=hb
                result['state'] = 'LOADING' if hb['phase'] == 'loading_owner_hybrid' else 'RUNNING'
            except (OSError,ValueError,StatusHold):
                result['state'] = 'RUNNING_TELEMETRY_UNVERIFIED'
        elif flag['owned_failure']:
            result['state']='HELD_AFTER_FAILURE';result['failure_cause']=failure_cause(sealed,flag)
        elif flag['hold_present'] or flag['pause_present']:
            result['state']='CHECKPOINTED_OR_PAUSED'
        else:
            result['state']='ADMITTED_TRAINER_NOT_RUNNING'
        latest = latest_receipt()
        if latest is not None:
            lineage, _ = document(output()/'owner_lineage.json')
            require(lineage.get('native_sha256') == NATIVE_SHA and lineage.get('schema') == TRAIN_SCHEMA,
                    'HOLD_TRAINING_STATUS_LINEAGE')
            lineage_sha = json_sha(lineage)
            if first is not None:
                require(lineage_sha == first.get('lineage_sha256'), 'HOLD_TRAINING_STATUS_ACCEPTED_LINEAGE_CHANGED')
            require(_VERIFY_LOCK.acquire(blocking=False), 'WAIT_TRAINING_STATUS_CHECKPOINT_VERIFICATION_BUSY')
            try:
                deadline=time.monotonic()+HASH_SECONDS
                proof=verify_checkpoint(latest[0],lineage_sha,deadline,result)
                result['latest_verified_checkpoint']={**proof,'receipt_sha256':latest[1],
                    'current_checkpoint_files_verified':True,'checkpoint_file_count':7}
                result['checkpoint_saved_verified']=True
                result['positive_optimizer_steps_verified'] = (result['positive_optimizer_steps_verified']
                                                               or proof['positive_optimizer_steps_verified'])
                result['global_step']=proof['global_step']
                try:
                    chain=counter_chain(latest[0],lineage_sha,deadline,result)
                    result['verified_counter_chain']=chain;result['optimizer_steps']=chain['successful_optimizer_steps']
                    result['skipped_optimizer_steps']=chain['skipped_optimizer_steps']
                    result['positive_optimizer_steps_verified'] = chain['successful_optimizer_steps'] > 0
                except (OSError,ValueError,StatusHold):
                    # A local update can be proven while a missing older segment
                    # prevents an honest cumulative count across resumptions.
                    result['optimizer_steps']=None;result['counter_chain_state']='CUMULATIVE_COUNT_UNVERIFIED'
                    result['skipped_optimizer_steps']=None
            finally:
                _VERIFY_LOCK.release()
        result['verification_state'] = ('VERIFIED_OPTIMIZER_CHECKPOINT' if result['positive_optimizer_steps_verified']
            else 'VERIFIED_SAVED_CHECKPOINT_WITHOUT_OPTIMIZER_UPDATE' if result['checkpoint_saved_verified']
            else 'NO_VERIFIED_OPTIMIZER_CHECKPOINT')
    except (OSError,ValueError,TypeError,KeyError,IndexError,StatusHold) as exc:
        code=str(exc)
        result['reason']=code if re.fullmatch(r'(?:HOLD|WAIT)_TRAINING_STATUS_[A-Z0-9_]+',code) else 'HOLD_TRAINING_STATUS_UNAVAILABLE'
        result['verification_state']=('HISTORICAL_CHECKPOINT_ONLY' if result['positive_optimizer_steps_verified']
                                      else 'TRAINING_EVIDENCE_UNVERIFIED')
    return result


def model_projection(value):
    require(isinstance(value,dict) and value.get('schema') == SCHEMA,
            'HOLD_TRAINING_STATUS_PROJECTION')
    fields = ('state','verification_state','positive_optimizer_steps_verified','optimizer_steps','global_step',
              'skipped_optimizer_steps','checkpoint_saved_verified','verified_counter_chain',
              'current_run','historical_verified_checkpoint','latest_verified_checkpoint','failure_cause','flags',
              'counter_chain_state','reason','current_model_merge_inclusion','checkpoint_restore_verified')
    return {key:value[key] for key in fields if key in value}


def bind_self_observation(namespace, context=None):
    """Later reviewed installation only; never trust caller-supplied evidence."""
    if namespace.get('_owner_training_status_bound'):
        return
    original_snapshot=namespace['snapshot'];original_model=namespace['evidence_for_model']
    def observed():
        value=original_snapshot();training=snapshot(context)
        previous=value.get('training') if isinstance(value.get('training'),dict) else {}
        value['training']={**previous,**model_projection(training),'observed_at':training['observed_at']}
        return value
    def evidence(observation,verified_memory):
        value=original_model(observation,verified_memory)
        if value.get('state') not in ('HOLD_UNVERIFIED_SELF_OBSERVATION','HOLD_NATIVE_SERVICES_UNOBSERVED'):
            value['training']=model_projection(snapshot(context))
        return value
    namespace.update(snapshot=observed,evidence_for_model=evidence,_owner_training_status_bound=True)
