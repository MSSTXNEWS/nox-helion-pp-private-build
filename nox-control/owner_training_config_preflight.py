#!/usr/bin/env python3
"""Check the installed training configuration before any model is loaded.

The caller verifies its hybrid source pin and owns maintenance + GPU1 leases.
Only two reviewed function ASTs execute in an isolated child. SFTConfig and its
serialization are real; model, dataset, optimizer and SFTTrainer are sentinels.
No corpus, weights, optimizer state or native training output is opened.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess

NATIVE_SHA = '703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a'
SCHEMA = 'NOX_TRAINING_CONFIG_PREFLIGHT_V1'
MAX_SOURCE_BYTES = 262144
TIMEOUT_SECONDS = 50
EXPECTED = {
    'per_device_train_batch_size': 1, 'gradient_accumulation_steps': 1,
    'max_length': 256, 'max_steps': 1000, 'fp16': True, 'bf16': False,
    'packing': False, 'gradient_checkpointing': True,
    'gradient_checkpointing_kwargs': {'use_reentrant': False},
    'dataloader_num_workers': 0, 'logging_steps': 1, 'save_steps': 1000,
    'save_total_limit': None, 'warmup_steps': 3, 'learning_rate': 0.0001,
    'optim': 'paged_adamw_8bit', 'lr_scheduler_type': 'cosine', 'report_to': [],
}


def fail(code):
    raise RuntimeError(code)


def function_source(raw, name):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_SOURCE_BYTES:
        fail('HOLD_CONFIG_PREFLIGHT_SOURCE_SIZE')
    try:
        tree = ast.parse(raw.decode('utf8'))
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
        if len(functions) != 1 or functions[0].decorator_list:
            fail('HOLD_CONFIG_PREFLIGHT_FUNCTION')
        return ast.unparse(functions[0])
    except (SyntaxError, UnicodeError, ValueError):
        fail('HOLD_CONFIG_PREFLIGHT_SOURCE_SYNTAX')


# stdout and stderr are redirected at descriptor level before package imports.
# The sole result channel is a duplicated stdout descriptor with an allowlist.
CHILD = r'''
import io,json,os,sys,tempfile,types
from pathlib import Path
from importlib.metadata import version
result_fd=os.dup(1)
sink=os.open(os.devnull,os.O_WRONLY)
os.dup2(sink,1);os.dup2(sink,2);os.close(sink)
result={'schema':'NOX_TRAINING_CONFIG_PREFLIGHT_V1','state':'HOLD_CONFIG_PREFLIGHT_CHILD'}
try:
 payload=json.loads(sys.stdin.buffer.read(800001))
 import torch,trl,transformers
 import trl.trainer.sft_trainer as sft_module
 from trl.trainer.sft_config import SFTConfig as RealConfig
 original_config=trl.SFTConfig
 original_trainer=trl.SFTTrainer
 original_internal_trainer=sft_module.SFTTrainer
 if original_config is not RealConfig or sft_module.SFTConfig is not RealConfig:
  raise RuntimeError('HOLD_CONFIG_PREFLIGHT_CONFIG_ALIAS')
 events=[];calls={'trainer':0,'adapter_boundary':0,'optimizer':0,'loss':0}
 class FakeSFTTrainer:
  def __init__(self,*,model,args,train_dataset,processing_class):
   calls['trainer']+=1;self.model=model;self.args=args;self.optimizer=None
  def create_optimizer(self):
   calls['optimizer']+=1;raise RuntimeError('HOLD_CONFIG_PREFLIGHT_OPTIMIZER_CALLED')
  def compute_loss(self,*args,**kwargs):
   calls['loss']+=1;raise RuntimeError('HOLD_CONFIG_PREFLIGHT_LOSS_CALLED')
 def capture_log(value):
  if value=='trainer api sftconfig ok':events.append('sftconfig_ok')
  elif value=='trainer api legacy ok':events.append('legacy_ok')
  elif value.startswith('trainer api sftconfig TypeError:'):events.append('sftconfig_typeerror')
  elif value.startswith('trainer api sftconfig FAIL:'):events.append('sftconfig_error')
  else:events.append('other_native_log')
 def adapter_boundary(*args,**kwargs):
  calls['adapter_boundary']+=1
 def forbidden_optimizer(*args,**kwargs):
  calls['optimizer']+=1;raise RuntimeError('HOLD_CONFIG_PREFLIGHT_OPTIMIZER_CALLED')
 with tempfile.TemporaryDirectory(prefix='nox-config-preflight-') as temporary:
  root=Path(temporary);out=root/'hybrid'
  native_ns={'Path':Path,'OUT':root/'native','log':capture_log}
  hybrid_ns={'Path':Path,'OUTPUT':out,'types':types,'fp32_adapters':adapter_boundary,
             'optimizer_fp32':forbidden_optimizer}
  exec(compile(payload['native_function'],'<pinned-native-builder>','exec'),native_ns)
  exec(compile(payload['hybrid_function'],'<pinned-hybrid-builder>','exec'),hybrid_ns)
  trl.SFTTrainer=FakeSFTTrainer;sft_module.SFTTrainer=FakeSFTTrainer
  try:
   trainer=hybrid_ns['build_existing_trainer'](
    types.SimpleNamespace(build_trainer=native_ns['build_trainer']),object(),object(),object(),1000,torch)
  finally:
   trl.SFTTrainer=original_trainer;sft_module.SFTTrainer=original_internal_trainer
  args=trainer.args
  observed={key:getattr(args,key,None) for key in payload['expected']}
  # Enum configuration values inherit str; converting through JSON matches the
  # public stable values without exporting any other TrainingArguments fields.
  observed=json.loads(json.dumps(observed,allow_nan=False))
  if observed!=payload['expected'] or Path(args.output_dir)!=out:
   raise RuntimeError('HOLD_CONFIG_PREFLIGHT_ARGUMENT_MISMATCH')
  if type(args) is not RealConfig or trl.SFTConfig is not original_config:
   raise RuntimeError('HOLD_CONFIG_PREFLIGHT_NONSTANDARD_CONFIG_CLASS')
  if events!=['sftconfig_ok'] or calls!={'trainer':1,'adapter_boundary':1,'optimizer':0,'loss':0}:
   raise RuntimeError('HOLD_CONFIG_PREFLIGHT_LEGACY_OR_EXECUTION')
  memory=io.BytesIO();torch.save(args,memory);serialized_bytes=memory.tell()
  if not 1<=serialized_bytes<=1048576:
   raise RuntimeError('HOLD_CONFIG_PREFLIGHT_SERIALIZATION_SIZE')
  result={'schema':'NOX_TRAINING_CONFIG_PREFLIGHT_V1','state':'INSTALLED_CONFIG_AND_SERIALIZATION_VERIFIED',
   'configuration':observed,'output_dir_match':True,'constructor_branch':'sftconfig',
   'config_class_module':type(args).__module__,'config_class_name':type(args).__name__,
   'config_alias_restored':True,'serialized_bytes':serialized_bytes,'model_loaded':False,
   'dataset_loaded':False,'optimizer_created':False,'real_trainer_created':False,
   'cuda_visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES'),
   'package_versions':{name:version(name) for name in ('torch','transformers','trl','accelerate','peft')}}
except BaseException as exc:
 code=str(exc)
 if not __import__('re').fullmatch(r'HOLD_CONFIG_PREFLIGHT_[A-Z0-9_]+',code):
  code='HOLD_CONFIG_PREFLIGHT_'+type(exc).__name__.upper()
 result={'schema':'NOX_TRAINING_CONFIG_PREFLIGHT_V1','state':'HOLD_CONFIG_PREFLIGHT_CHILD','reason':code}
raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
os.write(result_fd,raw);os.close(result_fd)
raise SystemExit(0 if result['state']=='INSTALLED_CONFIG_AND_SERIALIZATION_VERIFIED' else 2)
'''


def validate_result(value):
    fields = {'schema','state','configuration','output_dir_match','constructor_branch',
              'config_class_module','config_class_name','config_alias_restored',
              'serialized_bytes','model_loaded','dataset_loaded','optimizer_created',
              'real_trainer_created','cuda_visible_devices','package_versions'}
    if not isinstance(value, dict) or set(value) != fields:
        fail('HOLD_CONFIG_PREFLIGHT_RESULT_SCHEMA')
    if (value['schema'] != SCHEMA or value['state'] != 'INSTALLED_CONFIG_AND_SERIALIZATION_VERIFIED'
            or json.dumps(value['configuration'],sort_keys=True) != json.dumps(EXPECTED,sort_keys=True)
            or value['output_dir_match'] is not True
            or value['constructor_branch'] != 'sftconfig'
            or value['config_class_module'] != 'trl.trainer.sft_config'
            or value['config_class_name'] != 'SFTConfig' or value['config_alias_restored'] is not True
            or value['cuda_visible_devices'] != '1'
            or any(value[key] is not False for key in ('model_loaded','dataset_loaded','optimizer_created','real_trainer_created'))
            or type(value['serialized_bytes']) is not int or not 1 <= value['serialized_bytes'] <= 1048576):
        fail('HOLD_CONFIG_PREFLIGHT_RESULT_REJECTED')
    versions = value['package_versions']
    if (not isinstance(versions, dict) or set(versions) != {'torch','transformers','trl','accelerate','peft'}
            or any(not isinstance(v,str) or not re.fullmatch(r'[a-zA-Z0-9.+_-]{1,64}',v) for v in versions.values())):
        fail('HOLD_CONFIG_PREFLIGHT_VERSION_SCHEMA')
    return value


def run_preflight(hybrid_raw: bytes, native_raw: bytes, python='/root/venv_volta/bin/python') -> dict:
    """Caller holds maintenance+forge leases; no model/training work is admitted."""
    if not isinstance(native_raw, bytes) or hashlib.sha256(native_raw).hexdigest() != NATIVE_SHA:
        fail('HOLD_CONFIG_PREFLIGHT_NATIVE_PIN')
    payload = {'hybrid_function':function_source(hybrid_raw,'build_existing_trainer'),
               'native_function':function_source(native_raw,'build_trainer'), 'expected':EXPECTED}
    if not isinstance(python,str) or not python.startswith('/') or '\x00' in python:
        fail('HOLD_CONFIG_PREFLIGHT_PYTHON_PATH')
    env = {key:os.environ[key] for key in ('PATH','LD_LIBRARY_PATH') if key in os.environ}
    env.update(CUDA_VISIBLE_DEVICES='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',HF_HUB_OFFLINE='1',
               HF_DATASETS_OFFLINE='1',TRANSFORMERS_OFFLINE='1',WANDB_DISABLED='true',
               PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    try:
        result = subprocess.run([python,'-I','-c',CHILD],input=json.dumps(payload).encode(),
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,timeout=TIMEOUT_SECONDS,check=False)
    except subprocess.TimeoutExpired:
        fail('HOLD_CONFIG_PREFLIGHT_TIMEOUT')
    except OSError:
        fail('HOLD_CONFIG_PREFLIGHT_CHILD_START')
    if len(result.stdout) > 16384:
        fail('HOLD_CONFIG_PREFLIGHT_OUTPUT_SIZE')
    try:
        value = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        fail('HOLD_CONFIG_PREFLIGHT_OUTPUT_JSON')
    if result.returncode != 0:
        reason = value.get('reason') if isinstance(value,dict) else None
        fail(reason if isinstance(reason,str) and re.fullmatch(r'HOLD_CONFIG_PREFLIGHT_[A-Z0-9_]+',reason)
             else 'HOLD_CONFIG_PREFLIGHT_CHILD_FAILED')
    safe = validate_result(value)
    safe.update(hybrid_sha256=hashlib.sha256(hybrid_raw).hexdigest(),native_sha256=NATIVE_SHA)
    return safe
