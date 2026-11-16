#!/usr/bin/env python3
"""Read-only, bounded technical projection of the failed initial hybrid load."""
import base64
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
ROOT=Path('/root/nox');STATE=ROOT/'state';OUTPUT=ROOT/'lora/qlora_t866u/runs_owner_hybrid'
SERVICE='nox-train-volta-t866u'
HELPER_SHA='b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0'
FAILED_REQUEST='6905505383';FAILED_SOURCE='e5ff890d7424eb2abaa2e8d6188ca03759d4dc68'
FAILED_RECEIPT_SHA='250ad99af3269cf8bd7856a63696cbd410a7caf2a5a7a451106bc44f8fe7cd5b'
CLASSES={'RuntimeError','ValueError','TypeError','ImportError','ModuleNotFoundError','AttributeError',
         'KeyError','IndexError','OSError','MemoryError','OutOfMemoryError','NotImplementedError','AssertionError'}
PATTERNS={
 'CUDA_OUT_OF_MEMORY':r'CUDA out of memory|torch\.OutOfMemoryError',
 'HOST_PROCESS_KILLED':r'\bKilled\b|SIGKILL|signal 9',
 'CPU_OFFLOAD_DISPATCH':r'Some modules are dispatched on the CPU|offload.*(?:error|fail)|dispatch.*(?:error|fail)',
 'META_TENSOR_COPY':r'Cannot copy out of meta tensor|meta tensor|meta device',
 'MIXED_DEVICE':r'Expected all tensors.*same device|expected device .* got',
 'BF16_UNSCALE':r'unscale.*BFloat16|_amp_foreach_non_finite_check_and_unscale_cuda',
 'FP16_GRADIENT_UNSCALE':r'Attempting to unscale FP16 gradients',
 'CHECKPOINT_LOAD_PROGRESS':r'Loading checkpoint shards',
 'NATIVE_BASE_LOAD_BEGAN':r'load 4bit .*max_memory=',
 'DEVICE_MAP_COMPUTED':r'device_map placement',
 'DEVICE_DISPATCH_BEGAN':r'dispatch devices=',
 'ADAPTER_TARGETS_SELECTED':r'lora target modules=',
 'TRAINER_CONSTRUCTED':r'trainer api (?:\d+|sftconfig|legacy) ok',
 'ISINSTANCE_CLASS_ARGUMENT':r'isinstance\(\) arg 2 must be a type',
 'ISSUBCLASS_CLASS_ARGUMENT':r'issubclass\(\) arg [12] must be a class',
 'NONE_NOT_ITERABLE':r'argument of type .NoneType. is not iterable',
 'NONE_NO_LENGTH':r'object of type .NoneType. has no len',
 'CONFIG_OUTPUT_TYPE':r'args.*SFTConfig|SFTConfig.*instance',
 'GRADSCALER_MISSING':r'HOLD_FP16_GRADSCALER_NOT_PRESENT',
 'TOKENIZER_PAD_MISSING':r'pad_token.*(?:not set|None|missing)',
 'CUDA_ASSERT':r'device-side assert triggered',
 'DISK_FULL':r'No space left on device|Disk quota exceeded',
 'CUDA_KERNEL_UNAVAILABLE':r'no kernel image|invalid device function|CUDA error',
 'NATIVE_ABORT':r'Aborted|SIGABRT|terminate called|Fatal Python error',
 'NATIVE_SEGFAULT':r'Segmentation fault|SIGSEGV',
 'THREAD_RESOURCE_EXHAUSTED':r'pthread_create|can.t start new thread|Resource temporarily unavailable|ThreadPoolBuildError|thread pool',
 'RUST_PANIC':r'PanicException|panicked at|pyo3_runtime',
 'CPP_ALLOCATION_FAILURE':r'std::bad_alloc|std::system_error|bad allocation',
 'PYTHON_EXIT':r'SystemExit|KeyboardInterrupt',
}


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def emit(kind,data):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)
def read(path,limit=262144,tail=False):
    path=Path(path)
    if any(p.is_symlink() for p in (*path.parents,path)):fail('HOLD_TRAIN_PROBE_SYMLINK')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):fail('HOLD_TRAIN_PROBE_FILE_TYPE')
        if tail:stream.seek(max(0,info.st_size-limit))
        elif info.st_size>limit:fail('HOLD_TRAIN_PROBE_FILE_SIZE')
        return stream.read(limit)


def project_log(raw):
    text=raw.decode(errors='replace') if isinstance(raw,bytes) else str(raw)
    events=[]
    for line in text.splitlines()[-4000:]:
        row={}
        marker=re.search(r'NOX_HYBRID_FAILURE=([A-Za-z0-9_]+)',line)
        if marker and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,95}',marker[1]):
            row['hybrid_failure']=marker[1]
        reasons=[name for name,pattern in PATTERNS.items() if re.search(pattern,line,re.I)]
        if reasons:row['technical_patterns']=reasons
        exceptions=[name for name in CLASSES if re.search(r'\b'+name+r'\b',line)]
        if exceptions:row['exception_classes']=sorted(exceptions)
        terminal=re.match(r'^(?:[A-Za-z_][A-Za-z0-9_]*\.)*([A-Za-z_][A-Za-z0-9_]{0,63}(?:Error|Exception)):',line.strip())
        if terminal:row['terminal_exception_class']=terminal[1]
        frame=re.search(r'File "([^"\n]+\.py)", line (\d+), in ([A-Za-z_][A-Za-z0-9_]{0,63}|<module>)',line)
        if frame:
            known={'hybrid_training_entry.py','train_qlora_35b_t866u.py','sft_trainer.py','sft_config.py',
                   'trainer.py','training_args.py','arrow_dataset.py','arrow_writer.py','tokenization_utils_base.py'}
            basename=Path(frame[1]).name
            if basename in known:row['known_code_frame']={'file':basename,'line':int(frame[2]),'function':frame[3]}
        if re.search(r'trainer api (?:sftconfig|legacy) (?:TypeError|FAIL):',line):
            for pattern,kind in (
                (r"unexpected keyword argument ['\"]([A-Za-z_][A-Za-z0-9_]{0,63})['\"]",'UNEXPECTED_KEYWORD'),
                (r"missing .* required .* argument: ['\"]([A-Za-z_][A-Za-z0-9_]{0,63})['\"]",'MISSING_ARGUMENT'),
                (r"has no attribute ['\"]([A-Za-z_][A-Za-z0-9_]{0,63})['\"]",'MISSING_ATTRIBUTE')):
                match=re.search(pattern,line)
                if match:row['constructor_error']={'kind':kind,'identifier':match[1]}
        counts=re.search(r'lora target modules=(\d+) skipped_offloaded=(\d+)',line)
        if counts:row.update(adapter_target_modules=int(counts[1]),skipped_offloaded=int(counts[2]))
        load=re.search(r'Loading checkpoint shards.*?(\d+)/(\d+)',line)
        if load:row['loaded_shards']=[int(load[1]),int(load[2])]
        if row:events.append(row)
    return {'scanned_bytes':len(text.encode()),'technical_events':events[-50:],
            'raw_lines_exported':False,'private_training_text_exported':False}


def log_paths():
    paths={ROOT/'logs/train_volta_t866u.log',ROOT/'logs/train_volta_t866u.supervisor.err'}
    config=configparser.RawConfigParser(interpolation=None)
    config.read_string(read('/etc/supervisor/conf.d/nox-train-volta-t866u.conf',64000).decode())
    section='program:'+SERVICE
    for key in ('stdout_logfile','stderr_logfile'):
        candidate=Path(config.get(section,key,fallback=''))
        if candidate.parent==ROOT/'logs' and re.fullmatch(r'[A-Za-z0-9_.-]*t866u[A-Za-z0-9_.-]*',candidate.name):
            paths.add(candidate)
    return sorted(paths)


def corpus_projection():
    path=OUTPUT/'training_text.jsonl'
    if any(p.is_symlink() for p in (*path.parents,path)):fail('HOLD_CORPUS_PROBE_SYMLINK')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    result={'raw_text_exported':False,'mutations':False,'physical_lines':0,'valid_text_records':0,
            'unicode_splitline_records':0,'old_reader_failure_reproduced':False}
    h=hashlib.sha256();deadline=time.monotonic()+35
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size!=305243573:fail('HOLD_CORPUS_PROBE_SCOPE')
        while True:
            if time.monotonic()>deadline:fail('HOLD_CORPUS_PROBE_TIME_BUDGET')
            raw=stream.readline(8*1024*1024+1)
            if not raw:break
            if len(raw)>8*1024*1024:fail('HOLD_CORPUS_PROBE_ROW_BUDGET')
            h.update(raw);result['physical_lines']+=1
            try:
                line=raw.decode('utf8');value=json.loads(line)
            except (UnicodeError,json.JSONDecodeError) as exc:
                result['physical_line_failure_class']=type(exc).__name__;break
            if not isinstance(value,dict) or set(value)!={'text'} or not isinstance(value['text'],str):
                result['physical_line_schema_verified']=False;break
            result['valid_text_records']+=1
            pieces=line.splitlines()
            if len(pieces)>1:
                result['unicode_splitline_records']+=1
                if not result['old_reader_failure_reproduced']:
                    for piece in pieces:
                        try:json.loads(piece)
                        except json.JSONDecodeError:
                            result['old_reader_failure_reproduced']=True
                            result['old_reader_failure_class']='JSONDecodeError';break
        after=os.fstat(stream.fileno());named=path.stat(follow_symlinks=False)
        fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
        if any(getattr(before,k)!=getattr(after,k) or getattr(after,k)!=getattr(named,k) for k in fields):
            fail('HOLD_CORPUS_PROBE_IDENTITY_CHANGED')
        result.update(bytes=before.st_size,full_sha256=h.hexdigest(),
            full_corpus_sha_verified=h.hexdigest()=='31b0d6983d6bb6e40d05ffca505b4b1d68c9e9212648cd9cd270dedafd79fc1d')
    return result


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_TRAIN_PROBE_CONTEXT')
    raw=base64.b64decode(BUNDLE.get('owner_native_repair.py',''),validate=True)
    if digest(raw)!=HELPER_SHA:fail('HOLD_TRAIN_PROBE_HELPER_PIN')
    helper=types.ModuleType('owner_train_probe_helper');exec(compile(raw,'<pinned-native-helper>','exec'),helper.__dict__)
    previous_raw=read(STATE/('owner_maintenance_'+FAILED_REQUEST+'.json'),2*1024*1024)
    previous=json.loads(previous_raw)
    if (digest(previous_raw)!=FAILED_RECEIPT_SHA or previous.get('source_sha')!=FAILED_SOURCE
            or previous.get('state')!='HOLD_TRAINING_CONFIG_RECOVERY'
            or previous.get('error')!='HOLD_RECOVERY_TRAINER_EXITED_WITHOUT_PROOF'):
        fail('HOLD_TRAIN_PROBE_FAILED_RECEIPT_CHANGED')
    result={'schema':'NOX_OWNER_TRAINING_FAILURE_PROBE_V1','request':request,'source_sha':source,
            'failed_request':FAILED_REQUEST,'mutations':False,'private_training_text_exported':False,
            'service':helper.service_state(SERVICE),'progress':helper.progress(),'gpu':helper.gpu(),'health':helper.health(),
            'logs':[],'output_files':[],'cgroup':{},'supervisor_exits':[]}
    for channel in ('stdout','stderr'):
        rc,text=helper.command(['supervisorctl','tail',SERVICE,channel],15)
        result['logs'].append({'source':'supervisorctl:'+channel,'rc':rc,**project_log(text[-131072:])})
    for path in log_paths():
        try:result['logs'].append({'source':str(path),**project_log(read(path,131072,tail=True))})
        except FileNotFoundError:result['logs'].append({'source':str(path),'present':False})
    for path in ('/var/log/supervisor/supervisord.log','/var/log/supervisord.log','/tmp/supervisord.log'):
        try:
            tail=read(path,262144,tail=True).decode(errors='replace')
            rows=[]
            for line in tail.splitlines():
                if SERVICE not in line:continue
                stamp=re.match(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d',line)
                status=re.search(r'exit status (\d{1,3})',line)
                signal=re.search(r'(?:terminated by|signal) (SIG[A-Z0-9]{2,12})',line)
                if status or signal:rows.append({'timestamp':stamp[0] if stamp else None,
                    'exit_status':int(status[1]) if status else None,'signal':signal[1] if signal else None})
            result['supervisor_exits'].append({'source':path,'events':rows[-16:]})
        except FileNotFoundError:pass
        except (OSError,RuntimeError):result['supervisor_exits'].append({'source':path,'events':[],'state':'UNAVAILABLE_SAFE_READ'})
    for name in ('memory.current','memory.max','memory.peak','memory.events','cpu.max'):
        try:
            value=Path('/sys/fs/cgroup',name).read_text().strip()
            if re.fullmatch(r'[a-zA-Z0-9_ \n]+',value):result['cgroup'][name]=value
        except FileNotFoundError:pass
    for name in ('owner_preparation.json','owner_lineage.json','training_text.jsonl','owner_last_result.json'):
        path=OUTPUT/name;row={'name':name,'present':path.is_file() and not path.is_symlink()}
        if row['present']:
            row['bytes']=path.stat().st_size
            if name!='training_text.jsonl':row['sha256']=digest(read(path))
        result['output_files'].append(row)
    if OUTPUT.is_dir():
        checkpoints=[p for p in OUTPUT.iterdir() if re.fullmatch(r'checkpoint-\d{1,5}',p.name)]
        result['checkpoint_count']=len(checkpoints)
        result['checkpoint_steps']=sorted(int(p.name.split('-')[1]) for p in checkpoints)[:1000]
    flag=STATE/'TRAIN_HOLD.flag'
    if flag.is_file():
        data=read(flag,4096)
        result['failure_hold']={'sha256':digest(data),'matches_failed_owner':
            data==('OWNER_HYBRID_FAILED request='+FAILED_REQUEST+'\n').encode()}
    fs=os.statvfs(OUTPUT if OUTPUT.is_dir() else ROOT)
    result['output_disk_free_bytes']=fs.f_bavail*fs.f_frsize
    try:result['frozen_corpus_projection']=corpus_projection()
    except Exception as exc:
        reason=str(exc);result['frozen_corpus_projection']={'state':'UNKNOWN',
            'reason':reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else type(exc).__name__}
    emit('training_failure_diagnostic',result)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True);return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        reason=str(exc);emit('training_failure_probe_hold',{'reason':reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else type(exc).__name__})
        raise SystemExit(2)
