#!/usr/bin/env python3
"""Bounded read-only diagnosis of the exact admitted training source set."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

ROOT=Path('/root/nox');STATE=ROOT/'state';SCRIPTS=ROOT/'scripts'
OUTPUT=ROOT/'lora/qlora_t866u/runs_owner_hybrid'
CONTEXT={'request':'6906626126','source_sha':'c88d33ed8fbacaf58238921f600ec7641782b516',
 'receipt_sha256':'8981703e8b6e65a23b4556d2eac06a851561a3cc8159716d6d740c32bcf10d2c'}
POINTER_SHA='7f5267361133b8c128418619429c3fb5b174622df4556abb3dc62c0ea6c29c26'
ATTEMPT_REQUEST='6907119210'
ATTEMPT_SHA='dd500c463108b33765820d7ef3b9033c42f4eac6f4ebd622626b2c5825b4b9bc'
BASELINE_SHA='ba19160382025630d41f8187122bc1f51c7aa3abe2c2a8608e9b8804eeac72fe'
NATIVE_SHA='703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a'
FILES={'adapter_model.safetensors','adapter_config.json','optimizer.pt','scheduler.pt',
 'rng_state.pth','scaler.pt','trainer_state.json'}
SHA=re.compile('[a-f0-9]{64}')


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def identity(info):return tuple(getattr(info,key) for key in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns'))
def read(path,maximum=2*1024**2):
    path=Path(path)
    if any(p.is_symlink() for p in (*path.parents,path)):fail('HOLD_SOURCE_DELTA_SYMLINK')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0<=before.st_size<=maximum:fail('HOLD_SOURCE_DELTA_FILE_SCOPE')
        raw=stream.read(maximum+1);after=os.fstat(stream.fileno());named=path.stat(follow_symlinks=False)
        if len(raw)!=before.st_size or identity(before)!=identity(after) or identity(after)!=identity(named):
            fail('HOLD_SOURCE_DELTA_READ_RACE')
    return raw,{'bytes':before.st_size,'mtime_ns':before.st_mtime_ns,'sha256':digest(raw)}
def document(path,expected=None):
    raw,meta=read(path)
    if expected is not None and meta['sha256']!=expected:fail('HOLD_SOURCE_DELTA_SEALED_RECEIPT')
    value=json.loads(raw)
    if not isinstance(value,dict):fail('HOLD_SOURCE_DELTA_DOCUMENT')
    return value,meta
def error_code(exc):
    value=str(exc)
    return value if re.fullmatch('HOLD_[A-Z0-9_]+',value) else type(exc).__name__
def label(path):
    path=Path(path)
    if path==Path('/root/nox_selfheal.py'):return 'nox_selfheal.py'
    if path.is_relative_to(ROOT) and '..' not in path.parts:
        value=str(path.relative_to(ROOT))
        if re.fullmatch('[A-Za-z0-9_./-]{1,180}',value):return value
    fail('HOLD_SOURCE_DELTA_PATH_SCOPE')
def file_row(path,expected,maximum=2*1024**2):
    row={'filename':label(path),'expected_sha256':expected}
    try:
        _,meta=read(path,maximum);row.update(meta)
        row['matches_expected']=meta['sha256']==expected
        row['state']='MATCH' if row['matches_expected'] else 'SOURCE_CHANGED'
    except Exception as exc:row.update(state='READ_UNAVAILABLE',reason=error_code(exc),matches_expected=False)
    return row
def service():
    try:
        child=subprocess.run(['supervisorctl','status','nox-train-volta-t866u'],capture_output=True,timeout=8)
        if len(child.stdout)>4096:fail('HOLD_SOURCE_DELTA_SERVICE_OUTPUT')
        match=re.fullmatch(rb'nox-train-volta-t866u\s+(RUNNING|STARTING|STOPPED|EXITED|FATAL|BACKOFF|STOPPING|UNKNOWN)(?:\s+[^\r\n]*)?\s*',child.stdout)
        return {'state':match[1].decode() if match else 'UNKNOWN','returncode':child.returncode}
    except Exception as exc:return {'state':'UNKNOWN','reason':error_code(exc)}
def flags():
    result={}
    for name in ('TRAIN_HOLD.flag','TRAIN_PAUSE_REQUEST.flag','train_wants_gpu1'):
        path=STATE/name;row={'present':path.exists() or path.is_symlink()}
        if row['present']:
            try:
                raw,meta=read(path,4096);row.update(meta)
                if name=='TRAIN_HOLD.flag':
                    row['owned_failed_admission']=raw==('OWNER_HYBRID_FAILED request='+CONTEXT['request']+'\n').encode()
            except Exception as exc:row['reason']=error_code(exc)
        result[name]=row
    result['global_stop']={name:(path.exists() or path.is_symlink()) for name,path in
        [('STOP',ROOT/'STOP'),('STOP.flag',ROOT/'STOP.flag'),('stop.flag',ROOT/'stop.flag'),
         ('.stop',ROOT/'.stop'),('program/STOP',ROOT/'program/STOP'),('state/STOP',STATE/'STOP'),
         ('workspace/NOX_STOP',Path('/workspace/NOX_STOP'))]}
    return result


def snapshot():
    result={'schema':'NOX_OWNER_TRAINING_SOURCE_DELTA_V1','observed_at':time.time(),
        'read_only':True,'files_written':0,'training_started':False,'source_content_exported':False,
        'expected_context':dict(CONTEXT),'source_rows':[]}
    old,old_meta=document(STATE/('owner_maintenance_'+CONTEXT['request']+'.json'),CONTEXT['receipt_sha256'])
    if (old.get('schema')!='NOX_OWNER_TRAINING_RESUME_V1' or old.get('request')!=CONTEXT['request']
        or old.get('source_sha')!=CONTEXT['source_sha']):fail('HOLD_SOURCE_DELTA_ADMISSION_SCOPE')
    admitted=old.get('admission') or {};pins=admitted.get('sources') or {}
    if len(pins)!=20 or any(not isinstance(pin,str) or not SHA.fullmatch(pin) for pin in pins.values()):
        fail('HOLD_SOURCE_DELTA_SOURCE_SET')
    pointer,pointer_meta=document(STATE/'owner_training_admission.json')
    result['current_pointer']={**pointer_meta,'matches_expected_sha256':pointer_meta['sha256']==POINTER_SHA,
        'matches_sealed_admission':pointer==admitted,'expected_sha256':POINTER_SHA}
    for name,pin in sorted(pins.items()):result['source_rows'].append(file_row(Path(name),pin))
    result['mismatched_source_count']=sum(not row['matches_expected'] for row in result['source_rows'])
    result['native_trainer']=file_row(SCRIPTS/'train_qlora_35b_t866u.py',NATIVE_SHA)
    try:
        attempt,meta=document(STATE/('owner_maintenance_'+ATTEMPT_REQUEST+'.json'),ATTEMPT_SHA)
        projection={key:attempt[key] for key in ('training_started','optimizer_steps_verified') if type(attempt.get(key)) is bool}
        for key in ('state','error'):
            value=attempt.get(key)
            if isinstance(value,str) and re.fullmatch('[A-Z][A-Z0-9_]{0,100}',value):projection[key]=value
        result['latest_attempt']={'request':ATTEMPT_REQUEST,**meta,**projection}
    except Exception as exc:result['latest_attempt']={'state':'UNAVAILABLE','reason':error_code(exc)}
    try:
        baseline,meta=document(OUTPUT/'owner_receipt_step_5.json',BASELINE_SHA)
        cp=baseline.get('checkpoint') or {};hashes=cp.get('files_sha256') or {}
        if (set(hashes)!=FILES or cp.get('global_step')!=5 or cp.get('path')!=str(OUTPUT/'checkpoint-5')
            or any(not isinstance(pin,str) or not SHA.fullmatch(pin) for pin in hashes.values())):
            fail('HOLD_SOURCE_DELTA_BASELINE_SCOPE')
        rows=[file_row(OUTPUT/'checkpoint-5'/name,hashes[name],64*1024**2) for name in sorted(FILES)]
        result['baseline_checkpoint']={'receipt_sha256':meta['sha256'],'global_step':5,
            'seven_files_match':all(row['matches_expected'] for row in rows),'files':rows}
    except Exception as exc:result['baseline_checkpoint']={'state':'UNAVAILABLE','reason':error_code(exc)}
    result['service']=service();result['flags']=flags()
    _,after=read(STATE/'owner_training_admission.json')
    result['pointer_unchanged_during_snapshot']=after['sha256']==pointer_meta['sha256']
    result['state']='READ_ONLY_SOURCE_COMPARISON_COMPLETE'
    return result


def main():
    try:
        value=snapshot();print('NOX_MAINT_REPAIR='+json.dumps({'kind':'training_source_delta','data':value},separators=(',',':')),flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True);return 0
    except Exception as exc:
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'training_source_delta_hold','data':{'reason':error_code(exc)}}),flush=True)
        return 2


if __name__=='__main__':raise SystemExit(main())
