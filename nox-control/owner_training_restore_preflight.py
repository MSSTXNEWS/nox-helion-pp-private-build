"""Bounded tiny-GPU check of the pinned in-place restore before real model load.

The caller owns maintenance/forge leases and resource admission. This child uses
only its own two FP32 LoRA tensors and temporary synthetic files; it never reads
the real corpus/checkpoint or changes existing model, training, or service state.
"""
import base64
import hashlib
import json
import math
import os
import re
import subprocess

HYBRID_SHA='c576e63b4b8f63bf12b4f1453de5b8e1763d42685991af96ec765bce35264a75'
SCHEMA='NOX_OWNER_TINY_GPU_RESTORE_PREFLIGHT_V1'
STATE='PINNED_INPLACE_RESTORE_ON_TINY_GPU_MODEL_VERIFIED'
PYTHON='/root/venv_volta/bin/python'

CHILD=r'''
import base64,contextlib,hashlib,importlib.metadata,json,math,os,re,stat,sys,tempfile,types
from pathlib import Path
HYBRID_SHA='c576e63b4b8f63bf12b4f1453de5b8e1763d42685991af96ec765bce35264a75'
SOURCES={
 'trainer':('transformers','5.23.0','transformers/trainer.py','da5a792ffed97570b8d936f19b7090cbac4ff699b5e29b620a67ba1033d20c7d'),
 'peft_model':('peft','0.21.3','peft/peft_model.py','d22a1c50dea7a046ce28e71a79dfc20b1d96a2d238a9b457be6a88b6068e04d5'),
 'peft_state':('peft','0.21.3','peft/utils/save_and_load.py','eb764515dce074bc5b7655a90e945af906e924eb8305b1ec265fc79ca52a8438'),
}
STOP=tuple(Path('/root/nox')/p for p in ('STOP','STOP.flag','stop.flag','.stop','program/STOP','state/STOP','state/TRAIN_PAUSE_REQUEST.flag'))+(Path('/workspace/NOX_STOP'),)
def fail(code):raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stopped():
 if any(p.exists() or p.is_symlink() for p in STOP):fail('HOLD_RESTORE_PREFLIGHT_OWNER_STOP')
def read_source(path):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as stream:
  before=os.fstat(stream.fileno())
  if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=1024**2:fail('HOLD_RESTORE_PREFLIGHT_PACKAGE_SIZE')
  raw=stream.read(1024**2+1);after=os.fstat(stream.fileno());named=path.stat(follow_symlinks=False)
  if len(raw)!=before.st_size or any(getattr(before,k)!=getattr(after,k) or getattr(after,k)!=getattr(named,k)
      for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')):fail('HOLD_RESTORE_PREFLIGHT_PACKAGE_CHANGED')
 return raw
def installed_sources():
 rows={}
 for label,(package,version,relative,pin) in SOURCES.items():
  dist=importlib.metadata.distribution(package);raw=read_source(dist.locate_file(relative))
  if dist.version!=version or sha(raw)!=pin:fail('HOLD_RESTORE_PREFLIGHT_INSTALLED_SOURCE_CHANGED')
  rows[label]=pin
 return rows
def tensor_bytes(tensor):return tensor.detach().cpu().contiguous().numpy().tobytes()

stage='INPUT';result={}
try:
 raw=sys.stdin.buffer.read(262145)
 if len(raw)>262144:fail('HOLD_RESTORE_PREFLIGHT_INPUT_BOUND')
 payload=json.loads(raw);hybrid=base64.b64decode(payload['hybrid_source'],validate=True)
 if payload.get('hybrid_sha256')!=HYBRID_SHA or sha(hybrid)!=HYBRID_SHA:fail('HOLD_RESTORE_PREFLIGHT_HYBRID_PIN')
 with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
  stopped();stage='INSTALLED_SOURCE';pins=installed_sources()
  if any(name in sys.modules for name in ('torch','transformers','peft')):fail('HOLD_RESTORE_PREFLIGHT_EARLY_TRAINING_IMPORT')
  stage='IMPORT_TORCH'
  import torch
  from safetensors.torch import save_file
  torch.set_num_threads(1);stopped();stage='CUDA_ADMISSION'
  if os.environ.get('CUDA_VISIBLE_DEVICES')!='1' or not torch.cuda.is_available() or torch.cuda.device_count()!=1:
   fail('HOLD_RESTORE_PREFLIGHT_GPU_SCOPE')
  torch.cuda.set_device(0)
  if torch.cuda.mem_get_info(0)[0]<256*1024**2:fail('HOLD_RESTORE_PREFLIGHT_GPU_HEADROOM')
  torch.cuda.reset_peak_memory_stats(0)
  if Path('/dev/shm').is_symlink() or not Path('/dev/shm').is_dir():fail('HOLD_RESTORE_PREFLIGHT_TEMP_SCOPE')
  stage='SYNTHETIC_SETUP';module=types.ModuleType('_nox_synthetic_pinned_hybrid')
  exec(compile(hybrid,'<reviewed-hybrid-restore>','exec'),module.__dict__)
  class Block(torch.nn.Module):
   def __init__(self):
    super().__init__()
    self.lora_A=torch.nn.ModuleDict({'default':torch.nn.Linear(2,2,bias=False,device='cuda:0',dtype=torch.float32)})
    self.lora_B=torch.nn.ModuleDict({'default':torch.nn.Linear(2,2,bias=False,device='cuda:0',dtype=torch.float32)})
  class Toy(torch.nn.Module):
   def __init__(self):
    super().__init__();self.block=Block()
    self.frozen_base=torch.nn.Parameter(torch.tensor([13.0],device='cpu',dtype=torch.float32),requires_grad=False)
    self.active_adapters=['default'];self.peft_config={'default':object()};self.hf_device_map={'frozen_base':'cpu','block':0}
  model=Toy();parameters=dict(model.named_parameters());ids={k:id(v) for k,v in parameters.items()}
  base_before=tensor_bytes(model.frozen_base);map_before=dict(model.hf_device_map)
  with torch.no_grad():
   model.block.lora_A['default'].weight.fill_(3);model.block.lora_B['default'].weight.fill_(5)
  expected_hash=module.tensor_sha(model,torch)
  tensors={re.sub(r'\.(lora_[AB])\.default\.weight$',r'.\1.weight',name):p.detach().cpu().contiguous()
   for name,p in model.named_parameters() if p.requires_grad}
  with tempfile.TemporaryDirectory(prefix='nox-restore-preflight-',dir='/dev/shm') as directory:
   os.chmod(directory,0o700);module.OUTPUT=Path(directory);checkpoint=module.OUTPUT/'checkpoint-5';checkpoint.mkdir(mode=0o700)
   save_file(tensors,str(checkpoint/'adapter_model.safetensors'))
   files={'trainer_state.json':b'{"global_step":5}', 'adapter_config.json':b'{"peft_type":"LORA"}',
          'optimizer.pt':b'SYNTHETIC_OPTIMIZER_SENTINEL','scheduler.pt':b'SYNTHETIC_SCHEDULER_SENTINEL',
          'scaler.pt':b'SYNTHETIC_SCALER_SENTINEL','rng_state.pth':b'SYNTHETIC_RNG_SENTINEL'}
   for name,value in files.items():(checkpoint/name).write_bytes(value)
   for path in checkpoint.iterdir():os.chmod(path,0o600)
   lineage={'schema':module.SCHEMA,'native_sha256':'0'*64,'targets':module.fp32_adapters(model,torch,convert=False),'synthetic_only':True}
   record=module.checkpoint_record(checkpoint)
   receipt={'schema':module.SCHEMA,'native_sha256':lineage['native_sha256'],'lineage_sha256':module.json_sha(lineage),
    'global_step':5,'checkpoint':record,'after_tensor_sha256':expected_hash}
   receipt_path=module.OUTPUT/'owner_receipt_step_5.json';receipt_path.write_text(json.dumps(receipt));os.chmod(receipt_path,0o600)
   with torch.no_grad():
    for parameter in model.parameters():
     if parameter.requires_grad:parameter.zero_()
   if module.tensor_sha(model,torch)==expected_hash:fail('HOLD_RESTORE_PREFLIGHT_FIXTURE_NOT_DISTINCT')
   scheduler=object();scaler=object();trainer=types.SimpleNamespace(model=model,optimizer=None,
    lr_scheduler=scheduler,accelerator=types.SimpleNamespace(scaler=scaler))
   rng_cpu=torch.random.get_rng_state().clone();rng_cuda=torch.cuda.get_rng_state(0).clone()
   stopped();stage='INPLACE_RESTORE';proof=module.bind_checkpoint_restore(trainer,checkpoint,torch,lineage)
   if proof.get('restored') is not False:fail('HOLD_RESTORE_PREFLIGHT_EARLY_RESTORE')
   trainer._load_from_checkpoint(str(checkpoint));torch.cuda.synchronize(0);stage='READBACK'
   checks={
    'real_safetensors_restore_verified':module.tensor_sha(model,torch)==expected_hash,
    'parameter_objects_preserved':ids=={k:id(v) for k,v in model.named_parameters()},
    'trainable_device_and_dtype_preserved':all(p.device==torch.device('cuda:0') and p.dtype==torch.float32 for p in model.parameters() if p.requires_grad),
    'frozen_cpu_base_preserved':model.frozen_base.device.type=='cpu' and tensor_bytes(model.frozen_base)==base_before,
    'base_device_map_preserved':model.hf_device_map==map_before,
    'optimizer_not_created':trainer.optimizer is None,
    'scheduler_and_scaler_sentinels_preserved':trainer.lr_scheduler is scheduler and trainer.accelerator.scaler is scaler,
    'rng_state_preserved':torch.equal(torch.random.get_rng_state(),rng_cpu) and torch.equal(torch.cuda.get_rng_state(0),rng_cuda),
    'seven_synthetic_files_unchanged':module.checkpoint_record(checkpoint)==record,
    'restore_hook_positive_proof':proof.get('restored') is True and proof.get('parameter_objects_preserved') is True
      and proof.get('base_placement_preserved') is True and proof.get('trainable_tensors')==2}
   peak=torch.cuda.max_memory_allocated(0)
   if not all(checks.values()) or peak>1024**2:fail('HOLD_RESTORE_PREFLIGHT_INVARIANT')
   result={'schema':'NOX_OWNER_TINY_GPU_RESTORE_PREFLIGHT_V1','state':'PINNED_INPLACE_RESTORE_ON_TINY_GPU_MODEL_VERIFIED',
    'hybrid_sha256':HYBRID_SHA,'installed_source_sha256':pins,'checks':checks,
    'trainable_tensors':2,'trainable_parameters':8,'peak_tensor_allocation_bytes':peak,
    'temporary_checkpoint_files':7,'synthetic_checkpoint_only':True,'real_checkpoint_read':False,
    'base_model_loaded':False,'training_step_performed':False,'optimizer_step_performed':False,
    'service_or_training_flags_changed':False,'private_tensor_or_source_content_exported':False}
  stage='CLEANUP';stopped();result['temporary_directory_removed']=not Path(directory).exists()
  if not result['temporary_directory_removed']:fail('HOLD_RESTORE_PREFLIGHT_TEMP_CLEANUP')
 print(json.dumps(result,sort_keys=True,allow_nan=False))
except Exception as exc:
 code=str(exc)
 if not re.fullmatch('HOLD_[A-Z0-9_]{1,120}',code):code='HOLD_RESTORE_PREFLIGHT_'+stage+'_'+type(exc).__name__.upper()
 print(json.dumps({'state':'HOLD_TINY_GPU_RESTORE_PREFLIGHT','stage':stage,'reason':code,'raw_exception_exported':False}))
 raise SystemExit(2)
'''


def validate_result(value):
    checks=('real_safetensors_restore_verified','parameter_objects_preserved','trainable_device_and_dtype_preserved',
        'frozen_cpu_base_preserved','base_device_map_preserved','optimizer_not_created','scheduler_and_scaler_sentinels_preserved',
        'rng_state_preserved','seven_synthetic_files_unchanged','restore_hook_positive_proof')
    if (not isinstance(value,dict) or value.get('schema')!=SCHEMA or value.get('state')!=STATE
            or value.get('hybrid_sha256')!=HYBRID_SHA or value.get('trainable_tensors')!=2
            or value.get('trainable_parameters')!=8 or value.get('temporary_checkpoint_files')!=7
            or value.get('temporary_directory_removed') is not True or value.get('synthetic_checkpoint_only') is not True
            or not isinstance(value.get('checks'),dict) or set(value['checks'])!=set(checks)
            or not all(v is True for v in value['checks'].values())
            or type(value.get('peak_tensor_allocation_bytes')) is not int or not 0<value['peak_tensor_allocation_bytes']<=1024**2
            or any(value.get(k) is not False for k in ('real_checkpoint_read','base_model_loaded','training_step_performed',
                'optimizer_step_performed','service_or_training_flags_changed','private_tensor_or_source_content_exported'))):
        raise RuntimeError('HOLD_RESTORE_PREFLIGHT_RESULT_SCHEMA')
    expected={'trainer':'da5a792ffed97570b8d936f19b7090cbac4ff699b5e29b620a67ba1033d20c7d',
        'peft_model':'d22a1c50dea7a046ce28e71a79dfc20b1d96a2d238a9b457be6a88b6068e04d5',
        'peft_state':'eb764515dce074bc5b7655a90e945af906e924eb8305b1ec265fc79ca52a8438'}
    if value.get('installed_source_sha256')!=expected:raise RuntimeError('HOLD_RESTORE_PREFLIGHT_RESULT_SOURCE')
    allowed={'schema','state','hybrid_sha256','installed_source_sha256','checks','trainable_tensors','trainable_parameters',
        'peak_tensor_allocation_bytes','temporary_checkpoint_files','synthetic_checkpoint_only','real_checkpoint_read',
        'base_model_loaded','training_step_performed','optimizer_step_performed','service_or_training_flags_changed',
        'private_tensor_or_source_content_exported','temporary_directory_removed'}
    if set(value)!=allowed:raise RuntimeError('HOLD_RESTORE_PREFLIGHT_RESULT_SCOPE')
    return value


def run_preflight(hybrid_raw:bytes):
    if not isinstance(hybrid_raw,bytes) or len(hybrid_raw)>150000 or hashlib.sha256(hybrid_raw).hexdigest()!=HYBRID_SHA:
        raise RuntimeError('HOLD_RESTORE_PREFLIGHT_HYBRID_PIN')
    payload={'hybrid_source':base64.b64encode(hybrid_raw).decode(),'hybrid_sha256':HYBRID_SHA}
    environment=dict(os.environ,CUDA_VISIBLE_DEVICES='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
        TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1')
    try:
        child=subprocess.run([PYTHON,'-I','-B','-c',CHILD],input=json.dumps(payload).encode(),
                             capture_output=True,timeout=50,env=environment)
    except subprocess.TimeoutExpired:
        raise RuntimeError('HOLD_RESTORE_PREFLIGHT_TIMEOUT') from None
    if len(child.stdout)>16384 or child.returncode not in (0,2):raise RuntimeError('HOLD_RESTORE_PREFLIGHT_CHILD')
    try:value=json.loads(child.stdout,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
    except (ValueError,UnicodeError):raise RuntimeError('HOLD_RESTORE_PREFLIGHT_OUTPUT') from None
    if child.returncode==2:
        if (not isinstance(value,dict) or set(value)!={'state','stage','reason','raw_exception_exported'}
                or value.get('state')!='HOLD_TINY_GPU_RESTORE_PREFLIGHT' or value.get('raw_exception_exported') is not False
                or value.get('stage') not in ('INPUT','INSTALLED_SOURCE','IMPORT_TORCH','CUDA_ADMISSION',
                    'SYNTHETIC_SETUP','INPLACE_RESTORE','READBACK','CLEANUP')
                or not re.fullmatch('HOLD_[A-Z0-9_]{1,120}',str(value.get('reason','')))):
            raise RuntimeError('HOLD_RESTORE_PREFLIGHT_FAILURE_SCHEMA')
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'tiny_gpu_restore_preflight_hold','data':value},separators=(',',':')),flush=True)
        raise RuntimeError(value['reason'])
    return validate_result(value)
