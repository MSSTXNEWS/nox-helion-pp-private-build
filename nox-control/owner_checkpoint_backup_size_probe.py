#!/usr/bin/env python3
"""Small read-only checkpoint5 compression/transport projection; no ciphertext.

The exact original admission and nine baseline files are verified by the frozen
backup core. A changed current training pointer is deliberately not consulted.
Only temporary in-process archives are built; no native file is written.
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
import io,math,struct,zipfile

def perform(core):
 stored,manifest=core.read_native_archive()
 files={}
 with zipfile.ZipFile(io.BytesIO(stored)) as archive:
  if archive.namelist()!=list(core.NAMES):raise RuntimeError('HOLD_CHECKPOINT_PROBE_FILE_SCOPE')
  for name in core.NAMES:files[name]=archive.read(name)
 if core.validate_payload(files)!=manifest['files']:raise RuntimeError('HOLD_CHECKPOINT_PROBE_SOURCE_PROOF')
 output=io.BytesIO()
 with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=False) as archive:
  for name in core.NAMES:
   info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.create_system=3
   info.external_attr=0o100600<<16;info.compress_type=zipfile.ZIP_DEFLATED
   archive.writestr(info,files[name],compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
 packed=output.getvalue()
 if len(packed)>core.MAX_ARCHIVE:raise RuntimeError('HOLD_CHECKPOINT_PROBE_ARCHIVE_BOUND')
 with zipfile.ZipFile(io.BytesIO(packed)) as archive:
  restored={name:archive.read(name) for name in core.NAMES}
 if core.validate_payload(restored)!=manifest['files']:raise RuntimeError('HOLD_CHECKPOINT_PROBE_COMPRESSED_READBACK')
 partition={'lora_A':{'tensors':0,'bytes':0,'all_zero_bytes':0},
            'lora_B':{'tensors':0,'bytes':0,'all_zero_bytes':0},
            'other':{'tensors':0,'bytes':0,'all_zero_bytes':0}}
 tensor=files['adapter_model.safetensors']
 if len(tensor)<8:raise RuntimeError('HOLD_CHECKPOINT_PROBE_SAFETENSORS')
 header_size=struct.unpack('<Q',tensor[:8])[0]
 if not 2<=header_size<=min(1024**2,len(tensor)-8):raise RuntimeError('HOLD_CHECKPOINT_PROBE_SAFETENSORS')
 header=core.decode_json(tensor[8:8+header_size],1024**2)
 if not isinstance(header,dict) or len(header)>10000:raise RuntimeError('HOLD_CHECKPOINT_PROBE_TENSOR_HEADER')
 data=memoryview(tensor)[8+header_size:];spans=[]
 for name,row in header.items():
  if name=='__metadata__':continue
  offsets=row.get('data_offsets') if isinstance(row,dict) else None
  if (not isinstance(name,str) or not isinstance(offsets,list) or len(offsets)!=2
      or any(type(x) is not int for x in offsets) or not 0<=offsets[0]<offsets[1]<=len(data)):
   raise RuntimeError('HOLD_CHECKPOINT_PROBE_TENSOR_OFFSETS')
  begin,end=offsets;spans.append((begin,end))
  category='lora_A' if '.lora_A.' in name else 'lora_B' if '.lora_B.' in name else 'other'
  partition[category]['tensors']+=1;partition[category]['bytes']+=end-begin
  if not any(data[begin:end]):partition[category]['all_zero_bytes']+=end-begin
 previous=0
 for begin,end in sorted(spans):
  if begin!=previous:raise RuntimeError('HOLD_CHECKPOINT_PROBE_TENSOR_COVERAGE')
  previous=end
 if previous!=len(data):raise RuntimeError('HOLD_CHECKPOINT_PROBE_TENSOR_COVERAGE')
 def sizes(length):
  chars=((length+16+2)//3)*4;chunks=(chars+core.CHUNK_CHARS-1)//core.CHUNK_CHARS
  return {'archive_bytes':length,'ciphertext_base64_characters':chars,
          'chunks_60000_characters':chunks,'pages_at_six_chunks':(chunks+5)//6,
          'maximum_page_ciphertext_characters':min(chunks,6)*core.CHUNK_CHARS}
 return {'schema':'NOX_CHECKPOINT_BACKUP_SIZE_PROBE_V1',
  'state':'EXACT_BASELINE_AND_COMPRESSED_READBACK_VERIFIED',
  'scope_sha256':core.scope_sha(),'checkpoint_receipt_sha256':core.RECEIPT_SHA,
  'lineage_canonical_sha256':core.LINEAGE_SHA,'file_count':len(core.NAMES),
  'files_bytes':sum(len(value) for value in files.values()),
  'zip_stored':sizes(len(stored)),'zip_deflated_level6':sizes(len(packed)),
  'deflated_to_stored_ratio':round(len(packed)/len(stored),6),
  'all_nine_file_hashes_preserved':True,'tensor_byte_partition':partition,
  'successful_optimizer_steps':0,'full_model_backup':False,'current_training_pointer_read':False,
  'files_written':0,'ciphertext_exported':False,'raw_tensor_or_metadata_content_exported':False}
'''


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not re.fullmatch('[0-9]{1,24}',request) or not re.fullmatch('[a-f0-9]{40}',source):
        raise RuntimeError('HOLD_CHECKPOINT_PROBE_OWNER_CONTEXT')
    modules={}
    for name,pin in PINS.items():
        raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
        if not raw or len(raw)>100000 or hashlib.sha256(raw).hexdigest()!=pin:
            raise RuntimeError('HOLD_CHECKPOINT_PROBE_SOURCE_PIN')
        modules[name]={'bytes':base64.b64encode(raw).decode(),'sha256':pin}
    child="""
import sys
sys.dont_write_bytecode=True
import base64,hashlib,json,re,types
try:
 raw=sys.stdin.buffer.read(262145)
 if len(raw)>262144:raise RuntimeError('HOLD_CHECKPOINT_PROBE_INPUT_BOUND')
 value=json.loads(raw)
 for name,row in value['modules'].items():
  code=base64.b64decode(row['bytes'],validate=True)
  if hashlib.sha256(code).hexdigest()!=row['sha256']:raise RuntimeError('HOLD_CHECKPOINT_PROBE_CHILD_PIN')
  module=types.ModuleType(name);sys.modules[name]=module
  exec(compile(code,'<reviewed-checkpoint-module>','exec'),module.__dict__)
 exec(compile(value['probe'],'<reviewed-checkpoint-size-probe>','exec'),globals())
 result=perform(sys.modules['owner_checkpoint_backup_transport'])
 result.update(request=value['request'],source_sha=value['source_sha'])
 print('NOX_MAINT_REPAIR='+json.dumps({'kind':'checkpoint_backup_size_probe','data':result},separators=(',',':'),allow_nan=False),flush=True)
 print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
except Exception as exc:
 code=str(exc)
 if not re.fullmatch('HOLD_[A-Z0-9_]{1,120}',code):code='HOLD_CHECKPOINT_PROBE_'+type(exc).__name__.upper()
 print('NOX_MAINT_REPAIR='+json.dumps({'kind':'checkpoint_backup_size_probe_hold','data':{'reason':code}}),flush=True)
 raise SystemExit(2)
"""
    payload={'modules':modules,'probe':PROBE_BODY,'request':request,'source_sha':source}
    result=subprocess.run(['/usr/bin/python3','-I','-B','-c',child],input=json.dumps(payload).encode(),
        capture_output=True,timeout=45,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8',
        'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':'',
        'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
    if len(result.stdout)>16000:raise RuntimeError('HOLD_CHECKPOINT_PROBE_OUTPUT_BOUND')
    lines=result.stdout.decode('ascii').splitlines()
    if any(not line.startswith('NOX_MAINT_REPAIR=') and line!='NOX_MAINT_REPAIR_COMPLETE=true' for line in lines):
        raise RuntimeError('HOLD_CHECKPOINT_PROBE_OUTPUT_SCOPE')
    for line in lines:print(line,flush=True)
    if result.returncode:raise RuntimeError('HOLD_CHECKPOINT_PROBE_NATIVE_FAILED')
    if not lines or lines[-1]!='NOX_MAINT_REPAIR_COMPLETE=true':raise RuntimeError('HOLD_CHECKPOINT_PROBE_INCOMPLETE')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'checkpoint_backup_size_probe_hold',
            'data':{'reason':'HOLD_CHECKPOINT_PROBE_ENTRY'}}),flush=True)
        raise SystemExit(2)
