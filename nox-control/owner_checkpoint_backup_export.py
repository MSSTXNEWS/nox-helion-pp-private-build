#!/usr/bin/env python3
"""Memory-only native checkpoint5 exporter. An unprepared key pin blocks use."""
import sys
sys.dont_write_bytecode=True
import base64
import hashlib
import json
import os
import re
import subprocess

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
PRIMITIVES_SHA='5208f16465410140ab38da1c1e44a0711667bd34e3a4fc5f17237df11693230f'
TRANSPORT_SHA='9b7106f82428e47e6b79d1a79a3536519daeeb5b203b104ec25bb0342e6fc8aa'
# Set to the exact freshly prepared public metadata bytes immediately before
# the owner action. No private key is accepted in the bundle or native child.
PUBLIC_METADATA_SHA='cb5d6044f397fcb23cafa424412c2a490eb1996ba2a0cc7d970d5cc9d8fa9b8e'
MAX_OUTPUT=73_294_336
CHILD_STAGES={'INPUT','MODULES','KEY_METADATA','COLLECT_AND_SEAL','EMIT_CIPHERTEXT'}
CHILD_REASONS={'HOLD_CHECKPOINT_BACKUP_'+suffix for suffix in (
    'CHILD_BUDGET','CHILD_SOURCE_PIN','CHILD_KEY_PIN','JSON_SIZE','JSON_NUMBER',
    'KEY_SCHEMA','KEY_CONTEXT','PUBLIC_KEY','KEY_ID','RAM_HEADROOM','ORIGIN_ADMISSION',
    'TOTAL_SIZE','FILES','RECEIPT_SHA','LINEAGE','ZERO_UPDATE_PROOF','CHECKPOINT_SCOPE',
    'FILE_SHA','TRAINER_STEP','TRAINER_DIAGNOSTIC_SCOPE','TRAINER_METADATA_BUDGET',
    'ARCHIVE_SIZE','CHUNK_BUDGET','LOG_LINE_SIZE','SCOPE',
    'CRYPTO_VALUEERROR','CRYPTO_JSONDECODEERROR','CRYPTO_KEYERROR','CRYPTO_TYPEERROR',
    'CRYPTO_OSERROR','CRYPTO_FILENOTFOUNDERROR','CRYPTO_PERMISSIONERROR',
    'CRYPTO_MEMORYERROR','CRYPTO_RECURSIONERROR','CRYPTO_UNICODEDECODEERROR')}
CHILD_REASONS.update('HOLD_MEDIA_FIXTURE_'+suffix for suffix in (
    'DUPLICATE_JSON_KEY','PATH','FILE_SCOPE','FILE_SIZE','FILE_CHANGED','OWNER_CONTEXT'))


def fail(code):raise RuntimeError(code)
def bundle(name,pin,maximum=100000):
    raw=base64.b64decode(BUNDLE.get(name,''),validate=True)
    if (not re.fullmatch('[a-f0-9]{64}',pin) or not raw or len(raw)>maximum
            or hashlib.sha256(raw).hexdigest()!=pin):fail('HOLD_CHECKPOINT_BACKUP_BUNDLE_PIN')
    return raw


def child_failure_projection(raw):
    """Only fixed categorical child output may cross the public log boundary."""
    fallback={'stage':'UNVERIFIED_CHILD_RESULT','reason':'HOLD_CHECKPOINT_BACKUP_NATIVE_EXPORT_FAILED'}
    if not isinstance(raw,bytes) or len(raw)>4096:return fallback
    try:
        lines=raw.decode('ascii').splitlines()
        if len(lines)!=1 or not lines[0].startswith('NOX_MAINT_REPAIR='):return fallback
        value=json.loads(lines[0].split('=',1)[1]);data=value.get('data')
        if (set(value)!={'kind','data'} or value['kind']!='checkpoint_backup_export_failure'
                or not isinstance(data,dict) or set(data)!={'stage','reason'}
                or data['stage'] not in CHILD_STAGES or data['reason'] not in CHILD_REASONS):return fallback
        return {'stage':data['stage'],'reason':data['reason']}
    except (ValueError,TypeError,AttributeError,UnicodeError):return fallback


CHILD=r'''
import sys
sys.dont_write_bytecode=True
import base64,hashlib,json,re,types
stage='INPUT'
try:
 raw=sys.stdin.buffer.read(262145)
 if len(raw)>262144:raise RuntimeError('HOLD_CHECKPOINT_BACKUP_CHILD_BUDGET')
 value=json.loads(raw)
 stage='MODULES'
 for name in ('owner_media_fixture_transport','owner_checkpoint_backup_transport'):
  item=value['modules'][name];source=base64.b64decode(item['bytes'],validate=True)
  if hashlib.sha256(source).hexdigest()!=item['sha256']:raise RuntimeError('HOLD_CHECKPOINT_BACKUP_CHILD_SOURCE_PIN')
  module=types.ModuleType(name);sys.modules[name]=module
  exec(compile(source,'<reviewed-checkpoint-backup>','exec'),module.__dict__)
 core=sys.modules['owner_checkpoint_backup_transport']
 stage='KEY_METADATA'
 metadata=base64.b64decode(value['metadata'],validate=True)
 if hashlib.sha256(metadata).hexdigest()!=value['metadata_sha256']:raise RuntimeError('HOLD_CHECKPOINT_BACKUP_CHILD_KEY_PIN')
 stage='COLLECT_AND_SEAL'
 rows=core.seal(core.decode_json(metadata),value['request'],value['source_sha'])
 stage='EMIT_CIPHERTEXT'
 for row in rows:print('NOX_MAINT_REPAIR='+json.dumps(row,separators=(',',':')),flush=True)
 print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
except Exception as exc:
 code=str(exc)
 if not re.fullmatch('HOLD_[A-Z0-9_]+',code):code='HOLD_CHECKPOINT_BACKUP_CRYPTO_'+type(exc).__name__.upper()
 print('NOX_MAINT_REPAIR='+json.dumps({'kind':'checkpoint_backup_export_failure',
       'data':{'stage':stage,'reason':code}}),flush=True)
 raise SystemExit(2)
'''


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not re.fullmatch('[0-9]{1,24}',request) or not re.fullmatch('[a-f0-9]{40}',source):
        fail('HOLD_CHECKPOINT_BACKUP_OWNER_CONTEXT')
    metadata=bundle('owner_checkpoint_backup_public_key.json',PUBLIC_METADATA_SHA,8192)
    modules={}
    for name,pin in (('owner_media_fixture_transport',PRIMITIVES_SHA),('owner_checkpoint_backup_transport',TRANSPORT_SHA)):
        modules[name]={'bytes':base64.b64encode(bundle(name+'.py',pin)).decode(),'sha256':pin}
    payload={'modules':modules,'metadata':base64.b64encode(metadata).decode(),
        'metadata_sha256':PUBLIC_METADATA_SHA,'request':request,'source_sha':source}
    result=subprocess.run(['/usr/bin/python3','-I','-B','-c',CHILD],input=json.dumps(payload).encode(),
        capture_output=True,timeout=60,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONNOUSERSITE':'1',
        'PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
    if len(result.stdout)>MAX_OUTPUT or any(len(line)>=80000 for line in result.stdout.splitlines()):
        fail('HOLD_CHECKPOINT_BACKUP_NATIVE_OUTPUT_BUDGET')
    if result.returncode:
        projection=child_failure_projection(result.stdout)
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'checkpoint_backup_export_failure','data':projection}),flush=True)
        fail('HOLD_CHECKPOINT_BACKUP_NATIVE_EXPORT_FAILED')
    lines=result.stdout.decode('ascii').splitlines()
    if (not lines or lines[-1]!='NOX_MAINT_REPAIR_COMPLETE=true' or len(lines)>1202
            or any(not line.startswith('NOX_MAINT_REPAIR=') for line in lines[:-1])):
        fail('HOLD_CHECKPOINT_BACKUP_NATIVE_PROTOCOL')
    for line in lines:print(line,flush=True)
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        value=str(exc);code=value if re.fullmatch('HOLD_[A-Z0-9_]+',value) else 'HOLD_CHECKPOINT_BACKUP_'+type(exc).__name__.upper()
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'checkpoint_backup_export_failure','data':code}),flush=True)
        raise SystemExit(2)
