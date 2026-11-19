"""One-shot SHA-pinned source staging on Vast; NO live chat swap without E2E.

Copies only audited GitHub code into a separate area, never second server.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as probe
import contextlib,io,time
original=probe.api
def delayed(method,path,key,data=None):
    v=original(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(15)
    return v
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,urllib.request,subprocess,json,tempfile,hashlib,shutil
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V74_SHA_PINNED_COGNITIVE_STAGE_V1')
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
files={
 'synaptic_brain.py':'8340a74469d9242a94a16d611b5980ac084808de',
 'durable_runtime.py':'17aca9d60aa2d11c4f6eeef47982963a4a5946e6',
 'native_bridge_v38.py':'dc58cbd4344802027eaf2a11a7f65f82e06c1a14',
}
base='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/feature/nox-v38-synaptic-brain-20261114/nox_runpod/teacher_mesh/v38/'
dest=Path('/workspace/nox_mega_stage_verified/v38')
def emit(data):
 print('NATIVE_STAGE_RECEIPT='+json.dumps(data,sort_keys=True,separators=(',',':')))
if any(Path(p).exists() for p in STOP):
 emit({'state':'HOLD_GLOBAL_STOP','staged':0,'live_deployed':False})
else:
 free=shutil.disk_usage('/workspace').free
 if free<8_000_000_000:
  emit({'state':'HOLD_DISK_HEADROOM','staged':0,'live_deployed':False})
 else:
  payload={}
  for name,sha in sorted(files.items()):
   with urllib.request.urlopen(urllib.request.Request(base+name,headers={'User-Agent':'NOX-V74-Verified/1.0'}),timeout=15) as r:
    value=r.read(100000)
   git_hash=hashlib.sha1(b'blob '+str(len(value)).encode()+b'\x00'+value).hexdigest()
   if git_hash!=sha or not value or b'__import__("os").system' in value:
    raise RuntimeError('HOLD_BLOB_SHA_MISMATCH')
   code=compile(value,'<source:'+name+'>','exec')
   payload[name]=value
  if dest.exists() and (dest.is_symlink() or not dest.is_dir()):
   raise RuntimeError('HOLD_STAGE_CONFLICT')
  dest.mkdir(parents=True,exist_ok=True,mode=0o700)
  for name,value in payload.items():
   current=dest/name
   if current.exists():
    if current.is_symlink() or current.read_bytes()!=value:raise RuntimeError('HOLD_OLD_STAGE_CONFLICT')
    continue
   temp=dest/(name+'.tmp')
   with temp.open('xb') as out:out.write(value);out.flush();os.fsync(out.fileno())
   os.replace(temp,current)
  manifest={'schema':'NOX_V74_STAGE_V1','module_blobs':files,'live_deployed':False,
            'onehost_callbacks_connected':False,'main_gguf_modified':False}
  m=dest/'MANIFEST.json'
  m.write_text(json.dumps(manifest,sort_keys=True))
  emit({'state':'VERIFIED_MODULES_STAGED','staged':len(payload),'manifest_sha256':hashlib.sha256(m.read_bytes()).hexdigest(),
       'live_deployed':False,'s03_changed':False,'weights_changed':False,
       'stage_folder':'/workspace/nox_mega_stage_verified/v38'})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    probe.REMOTE=REMOTE;probe.api=delayed
    stream=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(stream):
            ok=probe.probe()
    except Exception as exc:
        value=str(exc);print("NOX_V74="+value if value.startswith("HOLD_") else "NOX_V74=HOLD_EXECUTION")
    finally:
        try:
            with contextlib.redirect_stdout(stream):
                if not probe.cleanup():ok=False
        except Exception:ok=False
    for line in stream.getvalue().splitlines():
        if line.startswith(('NATIVE_STAGE_RECEIPT=','TEMP_SSH_CLEANUP=')) and len(line)<1200:
            print(line)
    if "VERIFIED_MODULES_STAGED" not in stream.getvalue():ok=False
    return 0 if ok else 2
if __name__=="__main__":raise SystemExit(main())
