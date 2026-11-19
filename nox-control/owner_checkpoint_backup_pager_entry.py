#!/usr/bin/env python3
"""Finite prepare/inspect/page action; never starts training or prints plaintext."""
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
 'owner_checkpoint_backup_pager':'899e0fcc857ca9897349f90b9b416c51be0262959c40e82c69e9a2ddd26946f5',
}
# Root sets only this public-metadata pin immediately before prepare.
# No private key is generated, accepted or installed on the server.
PUBLIC_METADATA_SHA='UNPREPARED'

CHILD=r'''
import sys
sys.dont_write_bytecode=True
import base64,hashlib,json,re,types
try:
 raw=sys.stdin.buffer.read(300001)
 if len(raw)>300000:raise RuntimeError('HOLD_CHECKPOINT_PAGER_INPUT_BOUND')
 value=json.loads(raw)
 for name,item in value['modules'].items():
  code=base64.b64decode(item['bytes'],validate=True)
  if hashlib.sha256(code).hexdigest()!=item['sha256']:raise RuntimeError('HOLD_CHECKPOINT_PAGER_CHILD_PIN')
  module=types.ModuleType(name);sys.modules[name]=module
  exec(compile(code,'<reviewed-checkpoint-pager>','exec'),module.__dict__)
 pager=sys.modules['owner_checkpoint_backup_pager'];action=value['action']
 if action=='prepare':
  metadata=base64.b64decode(value['metadata'],validate=True)
  if hashlib.sha256(metadata).hexdigest()!=value['metadata_sha256']:raise RuntimeError('HOLD_CHECKPOINT_PAGER_PUBLIC_PIN')
  rows=pager.prepare(pager.core.decode_json(metadata),value['request'],value['source_sha'])
 elif action=='page':
  rows=pager.page(value['transfer_id'],value['manifest_sha256'],value['page_index'],value['request'],value['source_sha'])
 elif action=='inspect':rows=pager.inspect(value['transfer_id'],value['manifest_sha256'])
 else:raise RuntimeError('HOLD_CHECKPOINT_PAGER_ACTION')
 for row in rows:
  text=json.dumps(row,separators=(',',':'),allow_nan=False)
  if len(text.encode())>=79000:raise RuntimeError('HOLD_CHECKPOINT_PAGER_LINE_BOUND')
  print('NOX_MAINT_REPAIR='+text,flush=True)
 print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
except Exception as exc:
 code=str(exc)
 if not re.fullmatch('HOLD_[A-Z0-9_]{1,120}',code):code='HOLD_CHECKPOINT_PAGER_'+type(exc).__name__.upper()
 print('NOX_MAINT_REPAIR='+json.dumps({'kind':'checkpoint_backup_pager_hold','data':{'reason':code}}),flush=True)
 raise SystemExit(2)
'''


def bundle(name,pin,maximum=100000):
    raw=base64.b64decode(BUNDLE.get(name,''),validate=True)
    if (not re.fullmatch('[a-f0-9]{64}',pin) or not raw or len(raw)>maximum
            or hashlib.sha256(raw).hexdigest()!=pin):raise RuntimeError('HOLD_CHECKPOINT_PAGER_BUNDLE_PIN')
    return raw


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    action=os.environ.get('NOX_CHECKPOINT_PAGER_ACTION','inspect')
    if (not re.fullmatch('[0-9]{1,24}',request) or not re.fullmatch('[a-f0-9]{40}',source)
            or action not in ('prepare','page','inspect')):raise RuntimeError('HOLD_CHECKPOINT_PAGER_OWNER_CONTEXT')
    payload={'request':request,'source_sha':source,'action':action,'modules':{}}
    for name,pin in PINS.items():
        payload['modules'][name]={'bytes':base64.b64encode(bundle(name+'.py',pin)).decode(),'sha256':pin}
    if action=='prepare':
        payload.update(metadata=base64.b64encode(bundle('owner_checkpoint_backup_public_key.json',PUBLIC_METADATA_SHA,8192)).decode(),
                       metadata_sha256=PUBLIC_METADATA_SHA)
    else:
        transfer=os.environ.get('NOX_CHECKPOINT_PAGER_TRANSFER_ID','')
        manifest=os.environ.get('NOX_CHECKPOINT_PAGER_MANIFEST_SHA256','')
        if not re.fullmatch('[a-f0-9]{32}',transfer) or not re.fullmatch('[a-f0-9]{64}',manifest):
            raise RuntimeError('HOLD_CHECKPOINT_PAGER_SEALED_TRANSFER')
        payload.update(transfer_id=transfer,manifest_sha256=manifest)
        if action=='page':
            index=os.environ.get('NOX_CHECKPOINT_PAGER_PAGE_INDEX','')
            if not re.fullmatch('[0-9]{1,3}',index) or int(index)>199:raise RuntimeError('HOLD_CHECKPOINT_PAGER_PAGE_INDEX')
            payload['page_index']=int(index)
    result=subprocess.run(['/usr/bin/python3','-I','-B','-c',CHILD],input=json.dumps(payload).encode(),
        capture_output=True,timeout=60 if action=='prepare' else 15,
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1',
             'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
    if len(result.stdout)>400000 or any(len(line)>=80000 for line in result.stdout.splitlines()):
        raise RuntimeError('HOLD_CHECKPOINT_PAGER_OUTPUT_BOUND')
    lines=result.stdout.decode('ascii').splitlines()
    allowed={'checkpoint_backup_page_summary','checkpoint_backup_ciphertext_header','checkpoint_backup_ciphertext_chunk',
             'checkpoint_backup_page_receipt','checkpoint_backup_pager_hold'}
    if not lines or len(lines)>9:raise RuntimeError('HOLD_CHECKPOINT_PAGER_OUTPUT_PROTOCOL')
    for line in lines:
        if line=='NOX_MAINT_REPAIR_COMPLETE=true':continue
        if not line.startswith('NOX_MAINT_REPAIR='):raise RuntimeError('HOLD_CHECKPOINT_PAGER_OUTPUT_PROTOCOL')
        row=json.loads(line.split('=',1)[1])
        if not isinstance(row,dict) or set(row)!={'kind','data'} or row['kind'] not in allowed:
            raise RuntimeError('HOLD_CHECKPOINT_PAGER_OUTPUT_PROTOCOL')
    for line in lines:print(line,flush=True)
    if result.returncode:raise RuntimeError('HOLD_CHECKPOINT_PAGER_NATIVE_FAILED')
    if lines[-1]!='NOX_MAINT_REPAIR_COMPLETE=true':raise RuntimeError('HOLD_CHECKPOINT_PAGER_INCOMPLETE')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'checkpoint_backup_pager_hold',
            'data':{'reason':'HOLD_CHECKPOINT_PAGER_ENTRY'}}),flush=True)
        raise SystemExit(2)
