"""Diagnose single cold ZIP full SHA via existing Vast V51 native bridge.

Bounded private error classification; no raw archive data is sent to GitHub.
Stop/active NOX inference, memory and weights not touched. No second backend.
"""
from __future__ import annotations
import contextlib
import io
import json
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c

_original_api=c.api
def _delayed_api(method,path,key,data=None):
    answer=_original_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):
        time.sleep(20)
    return answer

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,stat,hashlib,json,traceback
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V69_ONE_COLD_FULL_SHA_V1')
result={'state':'HOLD_NO_CANDIDATE','candidates_count':0}
try:
    root=Path('/root/nox/incoming_t800u')
    target_size=85218466
    matches=[]
    for parent,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(parent)/d).is_symlink()][:60]
        for name in files:
            path=Path(parent)/name
            if path.suffix!='.zip':continue
            meta=path.lstat()
            if stat.S_ISREG(meta.st_mode) and meta.st_size==target_size:
                matches.append((path,meta))
                if len(matches)>2:break
        if len(matches)>2:break
    result['candidates_count']=len(matches)
    if len(matches)==1:
        path,meta=matches[0]
        h=hashlib.sha256()
        with path.open('rb') as fd:
            for block in iter(lambda:fd.read(2*1024*1024),b''):
                h.update(block)
        after=path.stat()
        if after.st_size!=meta.st_size or after.st_mtime_ns!=meta.st_mtime_ns:
            result['state']='HOLD_ARCHIVE_CHANGED'
        else:
            result['state']='PASS_FULL_SHA'
            result['bytes']=meta.st_size
            result['sha256']=h.hexdigest()
            result['name_sha16']=hashlib.sha256(path.name.encode()).hexdigest()[:16]
    elif len(matches)>1:
        result['state']='HOLD_AMBIGUOUS_SIZE'
except Exception as ex:
    result['state']='HOLD_EXCEPTION'
    result['exception_class']=type(ex).__name__[:70]
    tb=traceback.extract_tb(ex.__traceback__)
    result['remote_source_line']=tb[-1].lineno if tb else None
print('NATIVE_COLD_SHA_DIAGNOSTIC='+json.dumps(result,separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main()->int:
    c.REMOTE=REMOTE
    c.api=_delayed_api
    stdout=io.StringIO()
    done=False
    revoked=False
    try:
        with contextlib.redirect_stdout(stdout):
            done=c.probe()
    except Exception:
        print("NOX_V69_DIAG=HOLD_SSH_EXCEPTION")
    finally:
        try:
            with contextlib.redirect_stdout(stdout):
                revoked=c.cleanup()
        except Exception:
            print("NOX_V69_DIAG=HOLD_TEMP_KEY_REVOKE")
    entries=[]
    for line in stdout.getvalue().splitlines():
        if line.startswith('NATIVE_COLD_SHA_DIAGNOSTIC='):
            try:
                item=json.loads(line.split('=',1)[1])
                if isinstance(item,dict):entries.append(item);print(line)
            except (ValueError,TypeError):
                pass
        elif line.startswith("TEMP_SSH_CLEANUP=") and len(line)<100:
            print(line)
    state=entries[0].get('state') if len(entries)==1 else "HOLD_NO_RECEIPT"
    print("NOX_V69_FULL_SHA_RESULT="+state)
    return 0 if done and revoked and state=="PASS_FULL_SHA" else 2

if __name__=="__main__":
    raise SystemExit(main())
