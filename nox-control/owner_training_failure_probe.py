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
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
ROOT=Path('/root/nox');STATE=ROOT/'state';OUTPUT=ROOT/'lora/qlora_t866u/runs_owner_hybrid'
SERVICE='nox-train-volta-t866u'
HELPER_SHA='b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0'
FAILED_REQUEST='6905113544';FAILED_SOURCE='4c1de82ab1e3307de63a7b60639497841cda6d41'
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
 'TRAINER_CONSTRUCTED':r'trainer api \d+ ok',
 'DISK_FULL':r'No space left on device|Disk quota exceeded',
 'CUDA_KERNEL_UNAVAILABLE':r'no kernel image|invalid device function|CUDA error',
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
        if marker and (marker[1] in CLASSES or re.fullmatch('HOLD_[A-Z0-9_]+',marker[1])):
            row['hybrid_failure']=marker[1]
        reasons=[name for name,pattern in PATTERNS.items() if re.search(pattern,line,re.I)]
        if reasons:row['technical_patterns']=reasons
        exceptions=[name for name in CLASSES if re.search(r'\b'+name+r'\b',line)]
        if exceptions:row['exception_classes']=sorted(exceptions)
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


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_TRAIN_PROBE_CONTEXT')
    raw=base64.b64decode(BUNDLE.get('owner_native_repair.py',''),validate=True)
    if digest(raw)!=HELPER_SHA:fail('HOLD_TRAIN_PROBE_HELPER_PIN')
    helper=types.ModuleType('owner_train_probe_helper');exec(compile(raw,'<pinned-native-helper>','exec'),helper.__dict__)
    previous=json.loads(read(STATE/('owner_maintenance_'+FAILED_REQUEST+'.json'),2*1024*1024))
    if (previous.get('source_sha')!=FAILED_SOURCE or previous.get('state')!='HOLD_TRAINING_RESUME'
            or previous.get('error')!='HOLD_TRAINER_EXITED_WITHOUT_OPTIMIZER_PROOF'):
        fail('HOLD_TRAIN_PROBE_FAILED_RECEIPT_CHANGED')
    result={'schema':'NOX_OWNER_TRAINING_FAILURE_PROBE_V1','request':request,'source_sha':source,
            'failed_request':FAILED_REQUEST,'mutations':False,'private_training_text_exported':False,
            'service':helper.service_state(SERVICE),'progress':helper.progress(),'gpu':helper.gpu(),'health':helper.health(),
            'logs':[],'output_files':[],'cgroup':{}}
    for channel in ('stdout','stderr'):
        rc,text=helper.command(['supervisorctl','tail',SERVICE,channel],15)
        result['logs'].append({'source':'supervisorctl:'+channel,'rc':rc,**project_log(text[-131072:])})
    for path in log_paths():
        try:result['logs'].append({'source':str(path),**project_log(read(path,131072,tail=True))})
        except FileNotFoundError:result['logs'].append({'source':str(path),'present':False})
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
    emit('training_failure_diagnostic',result)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True);return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        reason=str(exc);emit('training_failure_probe_hold',{'reason':reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else type(exc).__name__})
        raise SystemExit(2)
