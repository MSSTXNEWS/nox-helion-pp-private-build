#!/usr/bin/env python3
"""Stage the original WEB29 archive + approved 3D Motion/accessibility assets.

Source-only; never installs to OneHost. Refuses unknown preimages and overwrites.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

PRIMARY_SHA = '611a3cf21b37ff79dbaece57f4c65c5efb70e0c302b5fc4b4f64dbfa060f15bc'
THREE_A_SHA = '48fa3a189b100242a3ff965e15da3ef83e426c443e275df03bdaae76dfaf413a'
LOCKED = {
 'site/nox-engines/nox-world-shaders.mjs':'124a5d341059eb1070adcf58640657aa471ea4888e4409101503ecaa9337f952',
 'site/nox-orbit-14.js':'3aced1774354b6212b665ef40514e78fb7660a3319fd346c4b12bbf277a39d38',
 'site/pc/nox-engines/nox-world-shaders.mjs':'124a5d341059eb1070adcf58640657aa471ea4888e4409101503ecaa9337f952',
 'site/pc/nox-orbit-14.js':'3aced1774354b6212b665ef40514e78fb7660a3319fd346c4b12bbf277a39d38',
}
REPLACE = {
 'site/chat.html': (
  b'<script defer src="vendor/fx/motion.js"></script>',
  b'<script defer src="nox-motion-idle-loader.js" data-nox-3d-idle="true"></script>'
 ),
 'site/nox-chat.js': (
  b'    run.stopping=true;\n    if(nativeOwner)state.nativeReplayHold=true;',
  b'    run.stopping=true;\n    activity(\'nox-stop-requested\',{request_id:run.rid,source:\'chat\'});\n    if(nativeOwner)state.nativeReplayHold=true;'
 ),
}
ASSETS = ('site/nox-motion-idle-loader.js','site/nox-cinematic-accessibility-3d.css')

def sha(data: bytes) -> str:
 return hashlib.sha256(data).hexdigest()

def stage(src: Path, overlay: Path, dest: Path):
 if dest.exists(): raise RuntimeError('HOLD_OUTPUT_EXISTS')
 if sha(src.read_bytes()) not in (PRIMARY_SHA, THREE_A_SHA): raise RuntimeError('HOLD_UNREVIEWED_WEB_PREIMAGE')
 if not src.is_file() or not overlay.is_dir():raise RuntimeError('HOLD_INPUT')
 with zipfile.ZipFile(src) as old:
  names=old.namelist()
  if len(names)!=len(set(names)) or any(name.startswith('/') or '..' in Path(name).parts for name in names):
   raise RuntimeError('HOLD_UNSAFE_ARCHIVE')
  if old.testzip() is not None:raise RuntimeError('HOLD_ZIP_CRC')
  for path,digest in LOCKED.items():
   if sha(old.read(path))!=digest:raise RuntimeError('HOLD_D02_14_WORLD_SOURCE_LOCK_'+path)
  if any(path in names for path in ASSETS):raise RuntimeError('HOLD_PREEXISTING_3D_ASSET')
  changes={}
  for path,(before,after) in REPLACE.items():
   data=old.read(path)
   if data.count(before)!=1:raise RuntimeError('HOLD_HTML_OR_STOP_PREIMAGE_'+path)
   data=data.replace(before,after,1)
   if path=='site/chat.html':
    closing=b'</head>'
    if data.count(closing)!=1:raise RuntimeError('HOLD_CHAT_HEAD_PREIMAGE')
    data=data.replace(closing,b'<link rel="stylesheet" href="nox-cinematic-accessibility-3d.css" data-nox-3d-a11y="true">'+closing,1)
   changes[path]=data
  for path in ASSETS:
   source=overlay / Path(path).name
   if not source.is_file():raise RuntimeError('HOLD_MISSING_3D_ASSET_'+str(source))
   changes[path]=source.read_bytes()
  expected={'site/nox-motion-idle-loader.js':'7d5b31162ae1e62e23cc85a5bf5e552850a40678','site/nox-cinematic-accessibility-3d.css':'3c60c6f4499cb0095291297f3e5fb628de6e1fc8'}
  for path,digest in expected.items():
   data=changes[path]
   git_blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
   if git_blob!=digest:raise RuntimeError('HOLD_ASSET_NOT_GITHUB_VERIFIED_'+path)
  dest.parent.mkdir(parents=True,exist_ok=True)
  fd,tmp=tempfile.mkstemp(prefix='.nox3d_stage_',suffix='.zip',dir=dest.parent)
  os.close(fd)
  try:
   with zipfile.ZipFile(tmp,'w') as output:
    for info in old.infolist():
     output.writestr(copy.copy(info),changes.get(info.filename,old.read(info.filename)))
    for path in ASSETS:output.writestr(path,changes[path],compress_type=zipfile.ZIP_DEFLATED)
   with zipfile.ZipFile(tmp) as check:
    if check.testzip() is not None:raise RuntimeError('HOLD_RESULT_CRC')
    for name in names:
     if name not in REPLACE and check.read(name)!=old.read(name):raise RuntimeError('HOLD_UNRELATED_PATH_CHANGED_'+name)
    for path,digest in LOCKED.items():
     if sha(check.read(path))!=digest:raise RuntimeError('HOLD_LOCK_CHANGED_'+path)
   os.replace(tmp,dest)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
 return {'schema':'NOX_WEB29_3D_SOURCE_STAGE_V1','status':'SOURCE_ONLY_NOT_ONEHOST_DEPLOY','input_sha256':sha(src.read_bytes()),'output_sha256':sha(dest.read_bytes()),'output_bytes':dest.stat().st_size,'original_members':len(names),'output_members':len(names)+2,'modified_original_paths':list(REPLACE),'modified_original_paths_scope':'relative to selected approved source preimage; not necessarily primary WEB29 MAIN','added_assets':list(ASSETS),'all_unrelated_original_bytes_identical':True,'D02_14_worlds_sha_verified':True,'native_browser_test':'HOLD_ADMIN_BLOCK','native_SSE_STOP_S03':'HOLD_NOT_CONNECTED'}

if __name__=='__main__':
 parser=argparse.ArgumentParser()
 parser.add_argument('--source',type=Path,required=True)
 parser.add_argument('--overlay',type=Path,required=True)
 parser.add_argument('--out',type=Path,required=True)
 p=parser.parse_args()
 print(json.dumps(stage(p.source,p.overlay,p.out),ensure_ascii=False,indent=2))
