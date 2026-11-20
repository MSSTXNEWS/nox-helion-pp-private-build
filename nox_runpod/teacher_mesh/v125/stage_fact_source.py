"""Safe V125 source staging on existing NOX OneHost. No service restart.

Copies the SHA-verified source-only fact adapter into original /root/nox/scripts.
It is NOT installed or imported into production in this step.
"""
from __future__ import annotations
import base64
import contextlib
import hashlib
import io
from pathlib import Path
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

MODULE=Path("nox_runpod/teacher_mesh/v125/owner_fact_write.py")
ORIGINAL_API=ssh.api

REMOTE_TEMPLATE=r'''
set -euo pipefail
/root/nox/venv/bin/python - <<'PYREMOTE'
import ast
import base64
import hashlib
import json
import os
import subprocess
import urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V125_STAGE_SCHEMA=EXISTING_ONEHOST_FACT_API_SOURCE_V1')
PROXY=Path('/root/nox/scripts/chat_proxy.py')
BRIDGE=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
DEST=Path('/root/nox/scripts/nox_v125_owner_fact_write.py')
PROXY_SHA='e79aa0747511cf010f79f72150fc4e64b36b9c9ccea3b09d788a6306c63c0c95'
BRIDGE_SHA='2c714c7f952be64a2b278c993da9d59014a43a32075281b5aa755ada02c6fb8e'
CODE=base64.b64decode('___SOURCE64___',validate=True)
EXPECTED='___SOURCE_SHA___'
PREVIOUS='38997324053456fdfa5339f1eaed66485657fe2c795711accaa24b706dfbc490'
BACKUP=DEST.with_name(DEST.name+'.original-'+PREVIOUS[:12]+'.bak')
def sha(blob):return hashlib.sha256(blob).hexdigest()
def emit(state,**kw):
    receipt={'state':state,'service_restarted':False,'fact_api_activated':False,
             'weights_changed':False,'s03_changed':False,**kw}
    print('NATIVE_V125_STAGE_RESULT='+json.dumps(receipt,separators=(',',':'),sort_keys=True)[:720])
def stopped():
    return any(Path(p).exists() for p in (
        '/root/nox/STOP','/root/nox/STOP.flag',
        '/root/nox/.stop','/workspace/NOX_STOP'))
try:
    if stopped():raise RuntimeError('HOLD_STOP')
    if len(CODE)<4000 or len(CODE)>15000 or sha(CODE)!=EXPECTED:
        raise RuntimeError('HOLD_MODULE_BYTES_OR_SHA')
    ast.parse(CODE.decode('utf8'));compile(CODE,str(DEST),'exec')
    if b'def register_nox_v125_owner_fact_write' not in CODE or b's03_memory.remember(' not in CODE:
        raise RuntimeError('HOLD_MISSING_NATIVE_REMEMBER_ENTRYPOINT')
    if not PROXY.is_file() or PROXY.is_symlink() or not BRIDGE.is_file() or BRIDGE.is_symlink():
        raise RuntimeError('HOLD_NO_ORIGINAL_ONEHOST')
    if sha(PROXY.read_bytes())!=PROXY_SHA or sha(BRIDGE.read_bytes())!=BRIDGE_SHA:
        raise RuntimeError('HOLD_EXISTING_ONEHOST_DRIFT')
    for port in (8080,8081):
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as r:
            if r.status!=200:raise RuntimeError('HOLD_NATIVE_HEALTH')
    if DEST.exists() or DEST.is_symlink():
        if DEST.is_symlink():raise RuntimeError('HOLD_EXISTING_FACT_MODULE_SYMLINK')
        previous=DEST.read_bytes()
        if sha(previous)==EXPECTED:
            emit('EXISTING_SOURCE_SHA_VERIFIED',module_sha256=EXPECTED)
        elif sha(previous)==PREVIOUS:
            # Old module is staged, NOT imported by active proxy. Preserve every byte.
            if BACKUP.exists() or BACKUP.is_symlink():
                if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=PREVIOUS:
                    raise RuntimeError('HOLD_FACT_BACKUP_COLLISION')
            else:
                with BACKUP.open('xb') as f:
                    f.write(previous);f.flush();os.fsync(f.fileno())
                os.chmod(BACKUP,0o600)
            temp=DEST.with_name('.nox-v125-safe-stage-v2.tmp')
            if temp.exists() or temp.is_symlink():
                raise RuntimeError('HOLD_FACT_STAGE_TEMP_CONFLICT')
            with temp.open('xb') as f:
                f.write(CODE);f.flush();os.fsync(f.fileno())
            os.chmod(temp,0o600)
            if sha(temp.read_bytes())!=EXPECTED:
                raise RuntimeError('HOLD_FACT_NEW_DIGEST')
            if stopped() or sha(DEST.read_bytes())!=PREVIOUS:
                raise RuntimeError('HOLD_FACT_STAGE_CHANGED_CONCURRENTLY')
            os.replace(temp,DEST)
            if sha(DEST.read_bytes())!=EXPECTED:
                raise RuntimeError('HOLD_STAGE_READBACK_SHA')
            emit('UPDATED_SOURCE_STAGED_BACKUP_VERIFIED',module_sha256=EXPECTED,
                 old_module_backup_sha256=PREVIOUS,staged_bytes=len(CODE))
        else:
            raise RuntimeError('HOLD_EXISTING_FACT_MODULE_CONFLICT')
    else:
        with DEST.open('xb') as f:
            f.write(CODE);f.flush();os.fsync(f.fileno())
        os.chmod(DEST,0o600)
        if sha(DEST.read_bytes())!=EXPECTED:
            raise RuntimeError('HOLD_STAGE_READBACK_SHA')
        emit('NEW_SOURCE_STAGED_SHA_VERIFIED',module_sha256=EXPECTED,
             staged_bytes=len(CODE))
except Exception as exc:
    desc=str(exc)
    emit(desc if desc.startswith('HOLD_') and len(desc)<90 else 'HOLD_STAGE_RUNTIME')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''

def main():
    blob=MODULE.read_bytes()
    sha=hashlib.sha256(blob).hexdigest()
    ssh.REMOTE=REMOTE_TEMPLATE.replace('___SOURCE64___',base64.b64encode(blob).decode()).replace(
        '___SOURCE_SHA___',sha)
    initial=ssh.api
    def settled(method,path,key,data=None):
        value=initial(method,path,key,data)
        if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
        return value
    ssh.api=settled
    out=io.StringIO()
    connected=False
    detached=False
    try:
        with contextlib.redirect_stdout(out):connected=ssh.probe()
    except Exception:
        print('NOX_V125_STAGE=HOLD_SSH')
    finally:
        try:
            with contextlib.redirect_stdout(out):detached=ssh.cleanup()
        except Exception:detached=False
    status=[]
    for line in out.getvalue().splitlines():
        if line.startswith('NATIVE_V125_STAGE_RESULT=') and len(line)<800:
            print(line);status.append(line)
        elif line.startswith('TEMP_SSH_CLEANUP='):
            print(line[:120])
    okay=(connected and detached and len(status)==1 and
          any(name in status[0] for name in (
              '"state":"NEW_SOURCE_STAGED_SHA_VERIFIED"',
              '"state":"EXISTING_SOURCE_SHA_VERIFIED"',
              '"state":"UPDATED_SOURCE_STAGED_BACKUP_VERIFIED"')))
    print('NOX_V125_EXISTING_HOST_SOURCE_STAGING='+('PASS' if okay else 'HOLD'))
    return 0 if okay else 2

if __name__=="__main__":
    raise SystemExit(main())
