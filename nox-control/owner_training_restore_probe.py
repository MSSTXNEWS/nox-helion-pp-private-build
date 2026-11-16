#!/usr/bin/env python3
"""Read installed restore ordering and the exact saved LoRA header, without import.

The child never imports torch/transformers/peft, instantiates a model, unpickles a
checkpoint, changes a pointer, or writes a file. Public source bytes and private
tensor names are represented only by hashes and fixed structural observations.
"""
import base64
import hashlib
import json
import os
import re
import subprocess

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
PINS={
 'owner_media_fixture_transport':'5208f16465410140ab38da1c1e44a0711667bd34e3a4fc5f17237df11693230f',
 'owner_checkpoint_backup_transport':'9b7106f82428e47e6b79d1a79a3536519daeeb5b203b104ec25bb0342e6fc8aa',
}

PROBE_BODY=r'''
import ast,importlib.metadata,io,math,struct,zipfile

PUBLIC={
 'trainer':('transformers','5.23.0','transformers/trainer.py','da5a792ffed97570b8d936f19b7090cbac4ff699b5e29b620a67ba1033d20c7d'),
 'peft_model':('peft','0.21.3','peft/peft_model.py','d22a1c50dea7a046ce28e71a79dfc20b1d96a2d238a9b457be6a88b6068e04d5'),
 'peft_state':('peft','0.21.3','peft/utils/save_and_load.py','eb764515dce074bc5b7655a90e945af906e924eb8305b1ec265fc79ca52a8438'),
}

def named(tree,name,kind):
 found=[node for node in ast.walk(tree) if isinstance(node,kind) and node.name==name]
 if len(found)!=1:raise RuntimeError('HOLD_RESTORE_PROBE_SOURCE_FUNCTION_SCOPE')
 return found[0]

def calls(node,name):
 return sorted(n.lineno for n in ast.walk(node) if isinstance(n,ast.Call)
  and ((isinstance(n.func,ast.Attribute) and n.func.attr==name)
       or (isinstance(n.func,ast.Name) and n.func.id==name)))

def before(node,left,right):
 a,b=calls(node,left),calls(node,right)
 return bool(a and b and min(a)<min(b))

def order_projection(sources):
 trainer=ast.parse(sources['trainer']);peft=ast.parse(sources['peft_model']);state=ast.parse(sources['peft_state'])
 klass=named(trainer,'Trainer',ast.ClassDef)
 methods={name:named(klass,name,ast.FunctionDef) for name in
  ('train','_inner_training_loop','_prepare_for_training','_load_from_checkpoint')}
 load=named(peft,'load_adapter',ast.FunctionDef)
 set_state=named(state,'set_peft_model_state_dict',ast.FunctionDef)
 load_text=ast.get_source_segment(sources['peft_model'],load)
 return {
  'model_restore_before_inner_loop_dispatch':before(methods['train'],'_load_from_checkpoint','find_executable_batch_size'),
  'preparation_before_train_begin_callback':before(methods['_inner_training_loop'],'_prepare_for_training','on_train_begin'),
  'create_optimizer_before_optimizer_restore':before(methods['_prepare_for_training'],'create_optimizer','_load_optimizer_and_scheduler'),
  'optimizer_restore_before_scaler_restore':before(methods['_prepare_for_training'],'_load_optimizer_and_scheduler','_load_scaler'),
  'model_restore_does_not_load_optimizer_scaler_rng':not any(calls(methods['_load_from_checkpoint'],x) for x in
    ('_load_optimizer_and_scheduler','_load_scaler','_load_rng_state')),
  'trainer_peft_branch_calls_load_adapter':bool(calls(methods['_load_from_checkpoint'],'load_adapter')),
  'peft_weight_load_before_dispatch':before(load,'set_peft_model_state_dict','dispatch_model'),
  'peft_auto_device_map_before_dispatch':before(load,'infer_auto_device_map','dispatch_model'),
  'peft_cpu_disk_single_adapter_dispatch_guard_present':all(x in load_text for x in
    ('hf_device_map','intersection({"cpu", "disk"})','len(self.peft_config) == 1')),
  'peft_assign_true_branch_present':any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
    and n.func.attr=='load_state_dict' and any(k.arg=='assign' and isinstance(k.value,ast.Constant)
    and k.value.value is True for k in n.keywords) for n in ast.walk(set_state)),
 }

def installed_sources(core):
 source,rows={},{}
 for label,(package,version,relative,expected) in PUBLIC.items():
  distribution=importlib.metadata.distribution(package)
  path=distribution.locate_file(relative)
  raw=core.primitives.read_regular(path,1024**2)
  source[label]=raw.decode('utf-8')
  rows[label]={'package':package,'version':distribution.version,'required_version':version,
   'version_matches':distribution.version==version,'source_sha256':core.digest(raw),
   'public_source_sha256':expected,'public_source_matches':core.digest(raw)==expected}
 return source,rows

def header_projection(core,files):
 tensor=files['adapter_model.safetensors']
 if len(tensor)<8:raise RuntimeError('HOLD_RESTORE_PROBE_HEADER_BOUND')
 size=struct.unpack('<Q',tensor[:8])[0]
 if not 2<=size<=min(1024**2,len(tensor)-8):raise RuntimeError('HOLD_RESTORE_PROBE_HEADER_BOUND')
 header=core.decode_json(tensor[8:8+size],1024**2)
 if not isinstance(header,dict) or len(header)>1000:raise RuntimeError('HOLD_RESTORE_PROBE_HEADER_SCHEMA')
 mapped=[];source=[];ranges=[];counts={'lora_A':0,'lora_B':0};parameters=0
 for key,row in header.items():
  if key=='__metadata__':continue
  match=re.fullmatch(r'(.+)\.(lora_A|lora_B)\.weight',key) if isinstance(key,str) else None
  if not match or not isinstance(row,dict) or set(row)!={'dtype','shape','data_offsets'} or row['dtype']!='F32':
   raise RuntimeError('HOLD_RESTORE_PROBE_LORA_HEADER_SCOPE')
  shape=row['shape'];offsets=row['data_offsets']
  if (not isinstance(shape,list) or len(shape)!=2 or any(type(n) is not int or n<=0 or n>1000000 for n in shape)
      or not isinstance(offsets,list) or len(offsets)!=2 or any(type(n) is not int for n in offsets)
      or not 0<=offsets[0]<offsets[1]<=len(tensor)-8-size
      or offsets[1]-offsets[0]!=math.prod(shape)*4):
   raise RuntimeError('HOLD_RESTORE_PROBE_LORA_SHAPES_OR_OFFSETS')
  mapped.append((match[1]+'.'+match[2]+'.default.weight',shape));source.append((key,shape))
  ranges.append(tuple(offsets));counts[match[2]]+=1;parameters+=math.prod(shape)
 if len(mapped)!=66 or counts!={'lora_A':33,'lora_B':33} or len({name for name,_ in mapped})!=66:
  raise RuntimeError('HOLD_RESTORE_PROBE_LORA_COUNT_OR_MAP')
 previous=0
 for begin,end in sorted(ranges):
  if begin!=previous:raise RuntimeError('HOLD_RESTORE_PROBE_TENSOR_COVERAGE')
  previous=end
 if previous!=len(tensor)-8-size:raise RuntimeError('HOLD_RESTORE_PROBE_TENSOR_COVERAGE')
 lineage=core.decode_json(files['owner_lineage.json']);targets=lineage.get('targets') or {}
 if (targets.get('trainable_tensors')!=66 or targets.get('trainable_parameters')!=parameters
     or targets.get('trainable_dtype')!='float32' or not core.sha(targets.get('target_schema_sha256'))):
  raise RuntimeError('HOLD_RESTORE_PROBE_LINEAGE_TARGET_COUNTS')
 return {'tensor_count':66,'lora_A_count':33,'lora_B_count':33,'dtype':'F32','parameter_count':parameters,
  'header_sha256':core.digest(tensor[8:8+size]),'source_key_shape_sha256':core.digest(core.canonical(sorted(source))),
  'mapped_default_key_shape_sha256':core.digest(core.canonical(sorted(mapped))),
  'lineage_target_schema_sha256':targets['target_schema_sha256'],
  'default_name_mapping_unique':True,'lineage_counts_match':True,'tensor_offsets_exact':True,
  'runtime_model_mapping_verified':False,'tensor_names_shapes_or_values_exported':False}

def perform(core):
 if any(name=='torch' or name.startswith(('torch.','transformers.','peft.')) or name in ('transformers','peft') for name in sys.modules):
  raise RuntimeError('HOLD_RESTORE_PROBE_TRAINING_IMPORT')
 sources,versions=installed_sources(core);ordering=order_projection(sources)
 archive,manifest=core.read_native_archive()
 with zipfile.ZipFile(io.BytesIO(archive)) as z:
  if z.namelist()!=list(core.NAMES):raise RuntimeError('HOLD_RESTORE_PROBE_CHECKPOINT_FILES')
  files={name:z.read(name) for name in core.NAMES}
 if core.validate_payload(files)!=manifest['files']:raise RuntimeError('HOLD_RESTORE_PROBE_BASELINE_PROOF')
 header=header_projection(core,files)
 imported=any(name=='torch' or name.startswith(('torch.','transformers.','peft.')) or name in ('transformers','peft') for name in sys.modules)
 accepted=all(row['version_matches'] and row['public_source_matches'] for row in versions.values()) and all(ordering.values()) and not imported
 return {'schema':'NOX_OWNER_TRAINING_RESTORE_PROBE_V1',
  'state':'INSTALLED_RESTORE_ORDER_AND_BASELINE_HEADER_VERIFIED' if accepted else 'HOLD_RESTORE_PROBE_INSTALLED_SOURCE_OR_ORDER',
  'installed_sources':versions,'ordering':ordering,'checkpoint_header':header,
  'checkpoint_receipt_sha256':core.RECEIPT_SHA,'lineage_sha256':core.LINEAGE_SHA,
  'checkpoint_global_step':5,'successful_optimizer_steps':0,'all_seven_checkpoint_sha_verified':True,
  'checkpoint_file_count':7,'baseline_records_verified':2,
  'training_packages_imported':imported,'gpu_or_model_initialized':False,'files_written':0,
  'current_training_pointer_read':False,'training_control_performed':False,
  'raw_package_source_or_private_tensor_content_exported':False}
'''


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not re.fullmatch('[0-9]{1,24}',request) or not re.fullmatch('[a-f0-9]{40}',source):
        raise RuntimeError('HOLD_RESTORE_PROBE_OWNER_CONTEXT')
    modules={}
    for name,pin in PINS.items():
        raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
        if not raw or len(raw)>100000 or hashlib.sha256(raw).hexdigest()!=pin:
            raise RuntimeError('HOLD_RESTORE_PROBE_BUNDLE_PIN')
        modules[name]={'bytes':base64.b64encode(raw).decode(),'sha256':pin}
    child="""
import sys
sys.dont_write_bytecode=True
import base64,hashlib,json,re,types
try:
 raw=sys.stdin.buffer.read(262145)
 if len(raw)>262144:raise RuntimeError('HOLD_RESTORE_PROBE_INPUT_BOUND')
 value=json.loads(raw);blobs={}
 for name,row in value['modules'].items():
  code=base64.b64decode(row['bytes'],validate=True)
  if hashlib.sha256(code).hexdigest()!=row['sha256']:raise RuntimeError('HOLD_RESTORE_PROBE_CHILD_PIN')
  blobs[name]=code
 for name,code in blobs.items():
  module=types.ModuleType(name);sys.modules[name]=module
  exec(compile(code,'<reviewed-baseline-proof-module>','exec'),module.__dict__)
 exec(compile(value['probe'],'<reviewed-restore-probe>','exec'),globals())
 result=perform(sys.modules['owner_checkpoint_backup_transport']);result.update(request=value['request'],source_sha=value['source_sha'])
 print('NOX_MAINT_REPAIR='+json.dumps({'kind':'training_restore_probe','data':result},separators=(',',':'),allow_nan=False),flush=True)
 if result['state']!='INSTALLED_RESTORE_ORDER_AND_BASELINE_HEADER_VERIFIED':raise RuntimeError(result['state'])
 print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
except Exception as exc:
 code=str(exc)
 if not re.fullmatch('HOLD_[A-Z0-9_]{1,120}',code):code='HOLD_RESTORE_PROBE_'+type(exc).__name__.upper()
 print('NOX_MAINT_REPAIR='+json.dumps({'kind':'training_restore_probe_hold','data':{'reason':code}}),flush=True)
 raise SystemExit(2)
"""
    result=subprocess.run(['/root/venv_volta/bin/python','-I','-B','-c',child],
        input=json.dumps({'modules':modules,'probe':PROBE_BODY,'request':request,'source_sha':source}).encode(),
        capture_output=True,timeout=45,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8',
            'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':'',
            'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
    if len(result.stdout)>16000:raise RuntimeError('HOLD_RESTORE_PROBE_OUTPUT_BOUND')
    lines=result.stdout.decode('ascii').splitlines()
    if any(not line.startswith('NOX_MAINT_REPAIR=') and line!='NOX_MAINT_REPAIR_COMPLETE=true' for line in lines):
        raise RuntimeError('HOLD_RESTORE_PROBE_OUTPUT_SCOPE')
    for line in lines:print(line,flush=True)
    if result.returncode:raise RuntimeError('HOLD_RESTORE_PROBE_NATIVE_FAILED')
    if not lines or lines[-1]!='NOX_MAINT_REPAIR_COMPLETE=true':raise RuntimeError('HOLD_RESTORE_PROBE_INCOMPLETE')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'training_restore_probe_hold',
            'data':{'reason':'HOLD_RESTORE_PROBE_ENTRY'}}),flush=True)
        raise SystemExit(2)
