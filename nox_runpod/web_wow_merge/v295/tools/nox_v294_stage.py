#!/usr/bin/env python3
"""NOX V29.4 one-source source-lock installer/STAGER (not a product release).

Uses the already SHA-pinned V29.3 WEB and updated existing V25 PC backend/voice.
Does not promote a live web root, edit user memory, start/stop services, or train.
"""
from __future__ import annotations
import argparse,hashlib,json,os,pathlib,re,shutil,sqlite3,sys,tempfile,time,urllib.request,urllib.error,zipfile
from pathlib import Path, PurePosixPath

WEB_SHA='166becb90fce63e2db3f9a74281d756995844552cddb7b67a0ac4bd67a190aa0'
WEB_BYTES=85218272
D02_SHA='f3fc804d238146ffe42c50103d3e04c9736b8b587c6572987f59b61a6112eb17'
EXPECTED_MANIFEST=1085
ORIGINAL_SERVER_SHA='4d5766cdd98333c9bfdfd394029debc07224d08b59ac54bdc60565130cd6143a'
ORIGINAL_VOICE_SHA='dd34f8427001fdc0163b66f2d825f6ea487bb38435dc89d8acdc799ed4a82fea'
PATCHED_SERVER_SHA='3ec3e4a8a6fcc53ea5a1cc102556451107fcfa7c8d110965f843e4febd7a9cb5'
PATCHED_VOICE_SHA='f3e437a053fe53955c9df95d607e12aa22ad2b0cdd49da3fd02349bb3c683139'
SENSITIVE_DRIVE_PARTS={'CON','PRN','AUX','NUL'} | {f'COM{i}' for i in range(1,10)} | {f'LPT{i}' for i in range(1,10)}

def sha_file(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def check_name(name:str)->str:
 if not name or '\\' in name or ':' in name or '\x00' in name or name.startswith('/'):
  raise ValueError('NOX_UNSAFE_ZIP_NAME: '+repr(name))
 bits=name.split('/')
 if len(bits)>30 or any(not x or x in ('.','..') or x.endswith((' ','.')) or x.split('.')[0].upper() in SENSITIVE_DRIVE_PARTS for x in bits):
  raise ValueError('NOX_UNSAFE_WINDOWS_FILENAME: '+repr(name))
 return '/'.join(bits)

def validate_web(archive:Path):
 if not archive.is_file() or archive.stat().st_size!=WEB_BYTES or sha_file(archive)!=WEB_SHA:
  raise ValueError('NOX_V293_EXACT_ORIGINAL_SHA_SIZE_MISMATCH')
 with zipfile.ZipFile(archive) as z:
  if z.testzip() is not None: raise ValueError('NOX_INNER_WEB_CRC_FAILED')
  names=[x.filename for x in z.infolist() if not x.is_dir()]
  if len(names)!=1089 or len({x.casefold() for x in names})!=1089:raise ValueError('NOX_INNER_WEB_ENTRY_COLLISION')
  if any(not n.startswith('site/') for n in names):raise ValueError('NOX_UNEXPECTED_INNER_MEMBER')
  manifest=json.loads(z.read('site/SOURCE_MANIFEST_V29.json'))
  if len(manifest)!=EXPECTED_MANIFEST:raise ValueError('NOX_INNER_LOCK_COUNT_DRIFT')
  for n,rec in manifest.items():
   f='site/'+check_name(n)
   item=z.getinfo(f)
   if item.file_size!=rec['bytes']:raise ValueError('NOX_INNER_FILE_SIZE_DRIFT: '+n)
   with z.open(item) as fh:
    h=hashlib.sha256()
    for piece in iter(lambda:fh.read(1<<20),b''):h.update(piece)
    if h.hexdigest()!=rec['sha256']:raise ValueError('NOX_INNER_FILE_SHA_DRIFT: '+n)
  with z.open('site/index.html') as f:
   h=hashlib.sha256()
   for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
   if h.hexdigest()!=D02_SHA:raise ValueError('NOX_ORIGINAL_D02_CHANGED')
 return {'sha256':WEB_SHA,'entries':len(names),'source_lock':len(manifest),'crc':'PASS','d02_sha256':D02_SHA}

def local_api_probe(port:int):
 """Read-only existing loopback endpoints; never invent voice/GPU pass."""
 endpoints=[('/api/nox/status','status'),('/api/nox/memory','memory'),('/api/nox/history','history'),('/api/nox/progress','progress'),('/api/nox/safe70','safe70'),('/api/nox/pc-load','pc_load'),('/api/nox/voice/status?lang=ru','voice_ru'),('/api/nox/voice/status?lang=es','voice_es')]
 status={}
 for path,name in endpoints:
  uri=f'http://127.0.0.1:{port}'+path
  try:
   with urllib.request.urlopen(urllib.request.Request(uri,headers={'Accept':'application/json'}),timeout=4) as r:
    if r.status!=200 or int(r.headers.get('Content-Length') or 0)>250000:raise ValueError('bad_response')
    raw=r.read(250001)
   if len(raw)>250000:raise ValueError('too_large')
   data=json.loads(raw)
   status[name]={'http':200,'status':data.get('status'),'schema_matched':False}
   if name=='status':status[name]['schema_matched']=data.get('host')=='NOX_CHAT_V24.1' or (data.get('backend')=='EXISTING_NATIVE_ONEHOST' and data.get('native_p02_bound') is True)
   elif name=='memory':status[name]['schema_matched']=data.get('status')=='READY' and isinstance(data.get('stats'),dict) and isinstance(data.get('segments'),dict)
   elif name=='history':status[name]['schema_matched']=data.get('status')=='READY' and isinstance(data.get('dialogs'),list)
   elif name.startswith('voice_'):status[name]['schema_matched']=data.get('language')==name[-2:] and data.get('status') in ('READY','HOLD')
   else:status[name]['schema_matched']=isinstance(data,dict)
   if name.startswith('voice_'):status[name]['voice_output_ready']=bool(data.get('status')=='READY' and data.get('tts_available') is True)
   if name=='pc_load':
    x=data.get('gpu_hot_spot_c');status[name]['hotspot_present']=isinstance(x,(int,float)) and 0<x<130
  except Exception as e:status[name]={'http':'HOLD','error':type(e).__name__,'schema_matched':False}
 return status

def safe_stage(bundle:Path,out:Path,port:int):
 if out.exists():
  receipt=out/'NOX_V294_STAGE_RECEIPT.json'
  if not receipt.is_file():raise ValueError('NOX_STAGE_EXISTS_NO_VERIFIED_RECEIPT')
  data=json.loads(receipt.read_text(encoding='utf8'))
  if data.get('bundle_sha256')!=sha_file(bundle) or data.get('web_sha256')!=WEB_SHA:
   raise ValueError('NOX_STAGING_PREEXISTS_DIFFERENT_SHA')
  if sha_file(out/'site/index.html')!=D02_SHA:raise ValueError('NOX_EXISTING_STAGE_D02_DRIFT')
  return {**data,'staging_reused':True}
 if out.is_symlink() or out.parent.is_symlink():raise ValueError('NOX_STAGING_SYMLINK_DENIED')
 # Reject non-isolated roots and software directories: staging only under builds.
 if not any(p.lower()=='builds' for p in out.parts):raise ValueError('NOX_STAGE_MUST_BE_UNDER_BUILDS')
 if not bundle.is_file():raise ValueError('NOX_BUNDLE_ABSENT')
 with zipfile.ZipFile(bundle) as z:
  if z.testzip() is not None:raise ValueError('NOX_BUNDLE_BAD_CRC')
  names=[i.filename for i in z.infolist() if not i.is_dir()]
  if len(names)!=len({x.casefold() for x in names}):raise ValueError('NOX_BUNDLE_CASE_COLLISION')
  for n in names: check_name(n)
  needed=('web/NOX_HELION_WEB_V29_3_FROZEN_20261113.zip','native_source/nox_chat_server.py','native_source/nox_voice.py')
  for n in needed:
   if n not in names:raise ValueError('NOX_REQUIRED_BUNDLE_MEMBER_MISSING: '+n)
  if hashlib.sha256(z.read(needed[1])).hexdigest()!=PATCHED_SERVER_SHA or hashlib.sha256(z.read(needed[2])).hexdigest()!=PATCHED_VOICE_SHA:
   raise ValueError('NOX_NATIVE_PATCH_SHA_DRIFT')
  out.parent.mkdir(parents=True,exist_ok=True)
  tmp=out.parent/(out.name+'.tmp_'+str(os.getpid()))
  if tmp.exists():raise ValueError('NOX_TEMP_DIR_PREEXISTS')
  tmp.mkdir()
  try:
   for n in names:
    if not n.startswith(('native_source/','tools/','qa/','docs/','web/')):continue
    dest=tmp/n;dest.parent.mkdir(parents=True,exist_ok=True)
    with z.open(n) as src,dest.open('xb') as fp:
     shutil.copyfileobj(src,fp,1<<20)
   source=tmp/needed[0]
   stat=validate_web(source)
   with zipfile.ZipFile(source) as webzip:
    total=0
    for entry in webzip.infolist():
     if entry.is_dir():continue
     rel=check_name(entry.filename)[5:]
     if not rel:raise ValueError('NOX_EMPTY_INNER_SITE_NAME')
     target=tmp/'site'/rel;target.parent.mkdir(parents=True,exist_ok=True)
     total+=entry.file_size
     if total>1_000_000_000:raise ValueError('NOX_INNER_ZIP_BOMB_HOLD')
     with webzip.open(entry) as rd,target.open('xb') as wr:shutil.copyfileobj(rd,wr,1<<20)
   status=local_api_probe(port)
   receipt={'schema':'NOX-V29.4-ISOLATED-WINDOWS-STAGE-v1',
            'bundle_sha256':sha_file(bundle),'web_sha256':stat['sha256'],
            'web_entries':stat['entries'],'web_source_lock':stat['source_lock'],
            'backend_patched_sha256':PATCHED_SERVER_SHA,'voice_patched_sha256':PATCHED_VOICE_SHA,
            'original_d02_sha256':D02_SHA,'local_pc_diagnostics':status,
            'installed_into_live_PC':False,'production_modified':False,
            's03_restart_on_user_machine':False,'ollama_inference_tested':False,
            'inflight_stop_on_user_machine':False,'sapi_ru_es_generated_wav_on_user_machine':False,
            'gpu_safe70_trip_on_user_machine':False,'independent_e07_WPF':False,
            'model_weights_trained':False,'release_accepted':False,
            'stage_path':str(out)}
   (tmp/'NOX_V294_STAGE_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
   os.replace(tmp,out)
  except BaseException:
   shutil.rmtree(tmp,ignore_errors=True)
   raise
 return receipt

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--bundle',type=Path,required=True)
 p.add_argument('--stage',type=Path,default=Path(r'C:\NOX\builds\NOX_V29_4_VERIFIED_STAGE'))
 p.add_argument('--port',type=int,default=8766)
 args=p.parse_args()
 result=safe_stage(args.bundle,args.stage,args.port)
 print(json.dumps(result,ensure_ascii=False,indent=2))
 if result['release_accepted']:raise ValueError('NOX_FALSE_PRODUCT_RELEASE_PASS')

if __name__=='__main__':
 try:main()
 except Exception as e:
  print('NOX_V294_HOLD',type(e).__name__,str(e),file=sys.stderr)
  raise SystemExit(2)
