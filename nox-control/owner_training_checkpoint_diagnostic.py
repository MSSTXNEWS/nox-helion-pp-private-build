#!/usr/bin/env python3
"""Read-only technical diagnosis of the exact first-five training exit."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
ROOT=Path('/root/nox');STATE=ROOT/'state';OUTPUT=ROOT/'lora/qlora_t866u/runs_owner_hybrid'
CONTEXT={'request':'6905764817','source_sha':'e4549616aa13295febc44dc78a3a033870f9071d',
 'receipt_sha256':'960e96fba9d24bb0835df1a46bf9971f770aaab78c0587e20a897b53fd6aeb46'}
PINS={
 'owner_training_failure_probe':'01530e3adc7652bd7355be2ff0e92d409d979f209d6604e22bc2e9c1b0cd5c5b',
 'owner_native_repair':'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0',
 'owner_training_status':'feda14757700e4d0b10d7dcace3d1ff007539c2be2bd51d6a86f0ecde7f8c828',
 'owner_builder_proc_probe':'1743c8587dac72f412400be9059d1fe01ef73a1955af2056ff77a550e53af3ff',
}

def fail(code):raise RuntimeError(code)
def emit(kind,data):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)
def load(name):
 raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
 if hashlib.sha256(raw).hexdigest()!=PINS[name]:fail('HOLD_CHECKPOINT_DIAGNOSTIC_BUNDLE_PIN')
 module=types.ModuleType(name);module.__file__=str(ROOT/'scripts'/(name+'.py'));sys.modules[name]=module
 exec(compile(raw,module.__file__,'exec'),module.__dict__);module.BUNDLE=BUNDLE
 return module

def main():
 request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
 if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_CHECKPOINT_DIAGNOSTIC_OWNER_CONTEXT')
 probe=load('owner_training_failure_probe');helper=load('owner_native_repair');status=load('owner_training_status')
 original=probe.read(STATE/('owner_maintenance_'+CONTEXT['request']+'.json'),2*1024**2)
 if hashlib.sha256(original).hexdigest()!=CONTEXT['receipt_sha256']:fail('HOLD_CHECKPOINT_DIAGNOSTIC_INITIAL_RECEIPT')
 sealed=json.loads(original);pointer=json.loads(probe.read(STATE/'owner_training_admission.json'))
 if pointer!=sealed.get('admission') or pointer.get('request')!=CONTEXT['request'] or pointer.get('max_steps')!=5:
  fail('HOLD_CHECKPOINT_DIAGNOSTIC_ADMISSION_CHANGED')
 observed=probe.read(STATE/'owner_maintenance_6905989441.json',2*1024**2)
 if hashlib.sha256(observed).hexdigest()!='242bd58ab4f99f04aeff1ee6905d3200a0381b9fd140b2c7820f92fffc63b782':
  fail('HOLD_CHECKPOINT_DIAGNOSTIC_OBSERVATION_RECEIPT')
 result={'request':request,'source_sha':source,'state':'READ_ONLY_CHECKPOINT_EXIT_DIAGNOSTIC',
  'initial_admission':CONTEXT,'service':helper.service_state(),'progress':helper.progress(),
  'health':helper.health(),'gpu':helper.gpu(),'mutations':0,'private_training_text_exported':False,
  'training_restarted':False,'logs':[],'checkpoints':[],'step_receipts':[]}
 for channel in ('stdout','stderr'):
  rc,text=helper.command(['supervisorctl','tail',probe.SERVICE,channel],15)
  result['logs'].append({'channel':channel,'rc':rc,**probe.project_log(text[-131072:])})
 for path in probe.log_paths():
  try:result['logs'].append({'source':path.name,**probe.project_log(probe.read(path,131072,tail=True))})
  except FileNotFoundError:pass
 allowed=('adapter_model.safetensors','adapter_config.json','optimizer.pt','scheduler.pt',
          'rng_state.pth','scaler.pt','trainer_state.json','training_args.bin')
 for path in sorted(OUTPUT.iterdir()):
  if re.fullmatch(r'checkpoint-[0-9]{1,4}',path.name):
   if path.is_symlink() or not path.is_dir():fail('HOLD_CHECKPOINT_DIAGNOSTIC_DIRECTORY')
   row={'step':int(path.name.split('-')[1]),'files':[]}
   for name in allowed:
    file=path/name
    try:
     info=file.lstat();row['files'].append({'name':name,'present':True,'regular':stat.S_ISREG(info.st_mode),
      'bytes':info.st_size,'mode':format(stat.S_IMODE(info.st_mode),'04o')})
    except FileNotFoundError:row['files'].append({'name':name,'present':False})
   result['checkpoints'].append(row)
  elif re.fullmatch(r'owner_receipt_step_[0-9]{1,4}\.json',path.name) or path.name=='owner_last_result.json':
   raw=probe.read(path);value=json.loads(raw)
   keys=('schema','native_sha256','lineage_sha256','start_step','global_step','loss',
    'successful_optimizer_steps','skipped_optimizer_steps','before_tensor_sha256','after_tensor_sha256',
    'adapter_delta_verified','merged','live_promoted','state','requested_step')
   result['step_receipts'].append({'name':path.name,'sha256':hashlib.sha256(raw).hexdigest(),
     'data':{key:value[key] for key in keys if key in value}})
 if len(result['checkpoints'])>1000 or len(result['step_receipts'])>1001:fail('HOLD_CHECKPOINT_DIAGNOSTIC_INVENTORY_BOUND')
 result['training_evidence']=status.snapshot(CONTEXT)
 fs=os.statvfs(OUTPUT);result['disk_free_bytes']=fs.f_bavail*fs.f_frsize
 flag=STATE/'TRAIN_HOLD.flag'
 if flag.exists():
  raw=probe.read(flag,4096);result['hold']={'sha256':hashlib.sha256(raw).hexdigest(),
   'matches_initial_failure':raw==('OWNER_HYBRID_FAILED request='+CONTEXT['request']+'\n').encode(),
   'matches_initial_complete':raw==('OWNER_HYBRID_BOUNDED_COMPLETE request='+CONTEXT['request']+'\n').encode()}
 emit('training_checkpoint_exit_diagnostic',result)
 load('owner_builder_proc_probe').main()
 print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
 return 0

if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as exc:
  reason=str(exc);emit('training_checkpoint_diagnostic_hold',{'reason':reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else type(exc).__name__})
  raise SystemExit(2)
