"""Read the two exact small saved AMP state files on CPU without changing them."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess

CHECKPOINT=Path('/root/nox/lora/qlora_t866u/runs_owner_hybrid/checkpoint-5')
FILES={'adapter_model.safetensors','adapter_config.json','optimizer.pt','scheduler.pt',
       'rng_state.pth','scaler.pt','trainer_state.json'}
STATE='SAVED_ZERO_UPDATE_OPTIMIZER_AND_SCALER_VERIFIED'
SCHEMA='NOX_OWNER_SAVED_AMP_STATE_V1'


def fail(code):raise RuntimeError(code)


CHILD=r'''
import contextlib,hashlib,io,json,math,os,stat,sys
from pathlib import Path

REASONS={'optimizer state':'OPTIMIZER_STATE_SCHEMA','optimizer groups':'OPTIMIZER_GROUP_SCHEMA',
 'optimizer parameters':'INVALID_PARAMETER_GROUP','optimizer ids':'INVALID_PARAMETER_IDENTIFIERS',
 'scaler schema':'SCALER_SCHEMA','scaler number':'SCALER_NONFINITE_OR_TYPE','scaler range':'SCALER_RANGE',
 'path':'STATE_FILE_PATH','size':'STATE_FILE_SIZE','hash or identity':'STATE_FILE_HASH_OR_IDENTITY',
 'unexpected CUDA initialization':'CUDA_INITIALIZED'}

def inspect_numeric(optimizer,scaler):
 out={'optimizer_is_dict':isinstance(optimizer,dict),'scaler_is_dict':isinstance(scaler,dict)}
 if isinstance(optimizer,dict):
  state=optimizer.get('state');groups=optimizer.get('param_groups')
  out['optimizer_state_entries']=len(state) if isinstance(state,dict) else None
  out['parameter_group_count']=len(groups) if isinstance(groups,list) else None
  if isinstance(groups,list) and len(groups)<=100:
   counts=[];ids=[];invalid=0
   for group in groups:
    params=group.get('params') if isinstance(group,dict) else None
    counts.append(len(params) if isinstance(params,list) else None)
    if isinstance(params,list):
     for value in params:
      if type(value) is int and value>=0:ids.append(value)
      else:invalid+=1
   out.update(parameter_counts=counts,empty_parameter_groups=counts.count(0),
    valid_parameter_count=len(ids),invalid_parameter_id_count=invalid,
    duplicate_parameter_id_count=len(ids)-len(set(ids)))
 if isinstance(scaler,dict):
  values={}
  for key in ('scale','growth_factor','backoff_factor','growth_interval','_growth_tracker'):
   value=scaler.get(key)
   values[key.lstrip('_')]=(value if type(value) in (int,float) and math.isfinite(value)
      else 'MISSING' if key not in scaler else 'NONFINITE_OR_WRONG_TYPE')
  out['scaler_numeric']=values
 return out

def project(optimizer,scaler):
 if not isinstance(optimizer,dict) or set(optimizer)!={'state','param_groups'} or optimizer['state']!={}:raise ValueError('optimizer state')
 groups=optimizer['param_groups']
 if not isinstance(groups,list) or not 1<=len(groups)<=100:raise ValueError('optimizer groups')
 identifiers=[]
 for group in groups:
  if not isinstance(group,dict) or not isinstance(group.get('params'),list):raise ValueError('optimizer parameters')
  identifiers+=group['params']
 if (not 1<=len(identifiers)<=100000 or any(type(x) is not int or x<0 for x in identifiers)
     or len(set(identifiers))!=len(identifiers)):raise ValueError('optimizer ids')
 if not isinstance(scaler,dict) or set(scaler)!={'scale','growth_factor','backoff_factor','growth_interval','_growth_tracker'}:raise ValueError('scaler schema')
 for key in ('scale','growth_factor','backoff_factor'):
  if type(scaler[key]) not in (int,float) or not math.isfinite(scaler[key]):raise ValueError('scaler number')
 if (scaler['scale']<=0 or scaler['growth_factor']<=1 or not 0<scaler['backoff_factor']<1
     or type(scaler['growth_interval']) is not int or scaler['growth_interval']<1
     or type(scaler['_growth_tracker']) is not int or not 0<=scaler['_growth_tracker']<scaler['growth_interval']):raise ValueError('scaler range')
 return {'optimizer_state_entries':0,'optimizer_parameter_groups':len(groups),
  'optimizer_parameter_count':len(identifiers),
  'optimizer_parameter_counts':[len(group['params']) for group in groups],
  'optimizer_empty_parameter_groups':sum(not group['params'] for group in groups),'scaler':{
   'scale':scaler['scale'],'growth_factor':scaler['growth_factor'],'backoff_factor':scaler['backoff_factor'],
   'growth_interval':scaler['growth_interval'],'growth_tracker':scaler['_growth_tracker']}}

def state_file(name,pin,torch):
 path=Path('/root/nox/lora/qlora_t866u/runs_owner_hybrid/checkpoint-5')/name
 if any(p.is_symlink() for p in (*path.parents,path)):raise ValueError('path')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as stream:
  before=os.fstat(stream.fileno())
  if not stat.S_ISREG(before.st_mode) or not 1<=before.st_size<=131072:raise ValueError('size')
  raw=stream.read(131073);after=os.fstat(stream.fileno());named=path.stat(follow_symlinks=False)
  if (len(raw)!=before.st_size or hashlib.sha256(raw).hexdigest()!=pin
      or any(getattr(before,key)!=getattr(after,key) or getattr(after,key)!=getattr(named,key)
             for key in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns'))):raise ValueError('hash or identity')
 return torch.load(io.BytesIO(raw),map_location='cpu',weights_only=True)

result={'state':'HOLD_SAVED_AMP_STATE_PREFLIGHT'};stage='INPUT';observations={}
try:
 hashes=json.loads(sys.stdin.buffer.read(16385))
 with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
  stage='IMPORT_TORCH'
  import torch
  stage='LOAD_OPTIMIZER'
  optimizer=state_file('optimizer.pt',hashes['optimizer.pt'],torch)
  stage='LOAD_SCALER'
  scaler=state_file('scaler.pt',hashes['scaler.pt'],torch)
  stage='NUMERIC_PROJECTION';observations=inspect_numeric(optimizer,scaler)
  stage='VALIDATE_SAVED_STATE'
  values=project(optimizer,scaler)
  stage='CHECK_CUDA'
  if torch.cuda.is_initialized():raise ValueError('unexpected CUDA initialization')
 result={'schema':'NOX_OWNER_SAVED_AMP_STATE_V1','state':'SAVED_ZERO_UPDATE_OPTIMIZER_AND_SCALER_VERIFIED',
  'checkpoint_global_step':5,'files_sha256':hashes,'cuda_initialized':False,'files_modified':False,**values}
except Exception as exc:
 result={'state':'HOLD_SAVED_AMP_STATE_PREFLIGHT','exception_class':type(exc).__name__,
  'failed_stage':stage,'reason_code':REASONS.get(str(exc),'UNCLASSIFIED_EXCEPTION'),'numeric_observations':observations}
print(json.dumps(result,sort_keys=True,allow_nan=False))
raise SystemExit(0 if result['state']=='SAVED_ZERO_UPDATE_OPTIMIZER_AND_SCALER_VERIFIED' else 2)
'''


def safe_failure(value):
    if (not isinstance(value,dict) or set(value)!={'state','exception_class','failed_stage','reason_code','numeric_observations'}
            or value.get('state')!='HOLD_SAVED_AMP_STATE_PREFLIGHT'
            or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,95}',str(value.get('exception_class','')))
            or value.get('failed_stage') not in ('INPUT','IMPORT_TORCH','LOAD_OPTIMIZER','LOAD_SCALER',
                'NUMERIC_PROJECTION','VALIDATE_SAVED_STATE','CHECK_CUDA')
            or value.get('reason_code') not in ('OPTIMIZER_STATE_SCHEMA','OPTIMIZER_GROUP_SCHEMA','INVALID_PARAMETER_GROUP',
                'INVALID_PARAMETER_IDENTIFIERS','SCALER_SCHEMA','SCALER_NONFINITE_OR_TYPE','SCALER_RANGE',
                'STATE_FILE_PATH','STATE_FILE_SIZE','STATE_FILE_HASH_OR_IDENTITY','CUDA_INITIALIZED','UNCLASSIFIED_EXCEPTION')):
        fail('HOLD_SAVED_AMP_STATE_OUTPUT')
    numeric=value['numeric_observations']
    allowed={'optimizer_is_dict','scaler_is_dict','optimizer_state_entries','parameter_group_count','parameter_counts',
             'empty_parameter_groups','valid_parameter_count','invalid_parameter_id_count','duplicate_parameter_id_count','scaler_numeric'}
    if not isinstance(numeric,dict) or set(numeric)-allowed:fail('HOLD_SAVED_AMP_STATE_OUTPUT')
    for key,item in numeric.items():
        if key in ('optimizer_is_dict','scaler_is_dict'):
            valid=type(item) is bool
        elif key=='parameter_counts':
            valid=isinstance(item,list) and len(item)<=100 and all(x is None or type(x) is int and 0<=x<=100000 for x in item)
        elif key=='scaler_numeric':
            valid=(isinstance(item,dict) and set(item)=={'scale','growth_factor','backoff_factor','growth_interval','growth_tracker'}
                and all(x in ('MISSING','NONFINITE_OR_WRONG_TYPE') if type(x) is str else type(x) in (int,float) and math.isfinite(x)
                        for x in item.values()))
        else:valid=item is None or type(item) is int and 0<=item<=100000
        if not valid:fail('HOLD_SAVED_AMP_STATE_OUTPUT')
    return value


def run_probe(checkpoint,files_sha256,python='/root/venv_volta/bin/python'):
    if (Path(checkpoint)!=CHECKPOINT or not isinstance(files_sha256,dict) or set(files_sha256)!=FILES
            or any(not re.fullmatch('[a-f0-9]{64}',str(value)) for value in files_sha256.values())
            or python!='/root/venv_volta/bin/python'):
        fail('HOLD_SAVED_AMP_STATE_SCOPE')
    selected={name:files_sha256[name] for name in ('optimizer.pt','scaler.pt')}
    environment=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
                     TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1')
    try:
        child=subprocess.run([python,'-I','-B','-c',CHILD],input=json.dumps(selected).encode(),
            capture_output=True,timeout=45,env=environment)
    except subprocess.TimeoutExpired:fail('HOLD_SAVED_AMP_STATE_TIMEOUT')
    if child.returncode not in (0,2) or len(child.stdout)>16384:fail('HOLD_SAVED_AMP_STATE_NATIVE_CHECK_FAILED')
    try:value=json.loads(child.stdout)
    except ValueError:fail('HOLD_SAVED_AMP_STATE_OUTPUT')
    if child.returncode==2:
        diagnostic=safe_failure(value)
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'saved_amp_state_preflight_hold','data':diagnostic},
            separators=(',',':'),allow_nan=False),flush=True)
        fail('HOLD_SAVED_AMP_STATE_'+diagnostic['failed_stage']+'_'+diagnostic['reason_code'])
    if (not isinstance(value,dict) or set(value)!={'schema','state','checkpoint_global_step','files_sha256',
            'cuda_initialized','files_modified','optimizer_state_entries','optimizer_parameter_groups',
            'optimizer_parameter_count','optimizer_parameter_counts','optimizer_empty_parameter_groups','scaler'}
            or value.get('schema')!=SCHEMA or value.get('state')!=STATE
            or value.get('checkpoint_global_step')!=5 or value.get('files_sha256')!=selected
            or value.get('cuda_initialized') is not False or value.get('files_modified') is not False
            or value.get('optimizer_state_entries')!=0):fail('HOLD_SAVED_AMP_STATE_OUTPUT')
    counts=value['optimizer_parameter_counts']
    if (not isinstance(counts,list) or not 1<=len(counts)<=100
            or any(type(item) is not int or not 0<=item<=100000 for item in counts)
            or not 1<=sum(counts)<=100000 or value['optimizer_parameter_groups']!=len(counts)
            or value['optimizer_parameter_count']!=sum(counts) or value['optimizer_empty_parameter_groups']!=counts.count(0)):
        fail('HOLD_SAVED_AMP_STATE_OUTPUT')
    return value
