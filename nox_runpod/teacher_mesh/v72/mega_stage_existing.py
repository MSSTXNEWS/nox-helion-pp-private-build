"""NOX V72: stage ONLY matching SHA-verified MEGA Drive donors already on Vast.

Never downloads unauthenticated files, executes archives, mutates production,
restarts models, or removes checkpoints. OneHost deployment is a separate gate.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
import contextlib
import io
_api=ssh.api
def delay(method,path,key,data=None):
    v=_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(15)
    return v

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,hashlib,json,shutil,zipfile,tempfile
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V72_MEGA_SHA_STAGING_V1')
EXPECTED={
 'NOX_FUNCTIONAL_SOURCE_20261103.zip':'fa346bc06998a1a2b6e8fc96674355aa4d2705141205b7a6fe427058267db309',
 'NOX_HELION_AI_SOUL_MEGA16_ONEBLOCK_20261023.zip':'8755f132a78ade664bbceea8e02103b867ef6b72f9695d43a27b2ed00d9f5594',
 'NOX_AI_WEIGHTS_PHYSICAL_UNIFIED_V1_20261023.zip':'bb210f9f131d12dafd6cf0ff5ced1ac42f8bde9048df32d094aa8f946d1fef57',
 'NOX_SOUL_EMOTION_PERSONA_WEIGHTS_LOCAL_CANDIDATE_V1_20261022.zip':'ef726288e494c505f6990bd883bade34d200269d438aceca5fb11fe7f9575598',
}
ROOTS=('/root/nox/incoming','/root/nox/archives','/workspace/nox/incoming',
       '/workspace/nox/archives','/workspace/nox_sources','/workspace/nox')
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
      '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
DEST=Path('/workspace/nox_mega_full_staging_20261114')
def emit(**value):
    print('NATIVE_MEGA_STAGING='+json.dumps(value,sort_keys=True,separators=(',',':')))
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for buf in iter(lambda:stream.read(1024*1024),b''):
            h.update(buf)
    return h.hexdigest()
found={}
scanned=0
for root in ROOTS:
    base=Path(root)
    if not base.is_dir() or base.is_symlink():continue
    for parent,dirs,files in os.walk(base,followlinks=False):
        rel=Path(parent).relative_to(base)
        dirs[:]=sorted(d for d in dirs if not (Path(parent)/d).is_symlink()) if len(rel.parts)<3 else []
        for name in files:
            if name not in EXPECTED or name in found:continue
            file=Path(parent)/name
            try:
                stat=file.lstat()
                if file.is_symlink() or not file.is_file() or stat.st_size>65_000_000:
                    continue
                if digest(file)!=EXPECTED[name]:continue
                with zipfile.ZipFile(file) as zip:
                    if zip.testzip() is not None:continue
                    if any(p.filename.startswith(('/','../')) or '..' in Path(p.filename).parts
                           for p in zip.infolist()):continue
                found[name]=file
            except (OSError,zipfile.BadZipFile,ValueError):continue
            scanned+=1
        if len(found)==len(EXPECTED):break
        if scanned>5000:break
missing=sorted(set(EXPECTED)-set(found))
if any(Path(p).exists() for p in STOP):
    emit(state='HOLD_GLOBAL_STOP',found=len(found),missing=missing,installed=False)
elif missing:
    emit(state='HOLD_DRIVE_DONOR_ARCHIVES_NOT_ON_VAST',found=len(found),
         missing=missing,installed=False,need_authorized_transfer=True)
else:
    free=shutil.disk_usage('/workspace').free
    total=sum(v.stat().st_size for v in found.values())
    if free<total*3+100_000_000:
        emit(state='HOLD_STAGING_DISK',found=4,installed=False)
    elif DEST.exists() and (DEST.is_symlink() or not DEST.is_dir()):
        emit(state='HOLD_STAGING_CONFLICT',found=4,installed=False)
    else:
        DEST.mkdir(mode=0o700,parents=True,exist_ok=True)
        staged={}
        for filename,source in sorted(found.items()):
            dest=DEST/filename
            if dest.exists():
                if dest.is_symlink() or digest(dest)!=EXPECTED[filename]:
                    raise RuntimeError('HOLD_STAGE_HASH_CONFLICT')
            else:
                temp=DEST/(filename+'.tmp-'+str(os.getpid()))
                with source.open('rb') as inf,temp.open('xb') as outf:
                    shutil.copyfileobj(inf,outf,1024*1024)
                    outf.flush();os.fsync(outf.fileno())
                if digest(temp)!=EXPECTED[filename]:
                    temp.unlink(missing_ok=True)
                    raise RuntimeError('HOLD_STAGE_HASH_MISMATCH')
                os.replace(temp,dest)
            staged[filename]=EXPECTED[filename]
        manifest={'schema':'NOX_V72_MEGA_STAGE_V1','files':staged,
                  'installed':False,'production_mutated':False,'model_weights_changed':False}
        name=DEST/'SHA256_MANIFEST.json'
        temp=DEST/'SHA256_MANIFEST.json.tmp'
        temp.write_text(json.dumps(manifest,sort_keys=True))
        os.replace(temp,name)
        emit(state='SHA_VERIFIED_STAGE_COMPLETE',found=4,staged=4,
             stage_manifest_sha256=digest(name),installed=False,production_changed=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    ssh.REMOTE=REMOTE;ssh.api=delay
    log=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(log):ok=ssh.probe()
    except Exception as exc:
        name=str(exc)
        print('NOX_V72='+name if name.startswith('HOLD_') else 'NOX_V72=HOLD_SSH_OR_RUNTIME')
    finally:
        try:
            with contextlib.redirect_stdout(log):
                if not ssh.cleanup():ok=False
        except Exception:ok=False
    for row in log.getvalue().splitlines():
        if row.startswith(('NATIVE_MEGA_STAGING=','TEMP_SSH_CLEANUP=')) and len(row)<1400:
            print(row)
    return 0 if ok else 2

if __name__=='__main__':
    raise SystemExit(main())
