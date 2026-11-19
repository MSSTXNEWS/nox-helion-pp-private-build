"""NOX V87 physical memory read-through smoke, no user data export.
Import staged V84 module and query REAL existing S03 with a deny-all record ACL.
Never treat this as authorization to show any record or train on it.
"""
from __future__ import annotations
import contextlib, io, time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as bridge
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import importlib.util, json, os, sqlite3, hashlib
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V87_DENY_ALL_S03_READTHROUGH_V1')
STAGE=Path('/root/nox/staging/nox_v84_memory_native.py')
EXPECTED='c311394ffa9e95c6784e132db3bb4e3bde44fc01e17704a282a76dd50c5e2289'
SEED='/root/nox/kb/pc_safe70/nox_seed_memory.sqlite3'
INFINITE='/root/nox/memory/infinite/nox_infinite_memory.sqlite3'
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def emit(label,value):
 print(label+'='+json.dumps(value,sort_keys=True,separators=(',',':')))
try:
 if any(Path(x).exists() for x in STOP):raise RuntimeError('HOLD_STOP')
 if not STAGE.is_file() or STAGE.is_symlink() or hashlib.sha256(STAGE.read_bytes()).hexdigest()!=EXPECTED:
  raise RuntimeError('HOLD_STAGED_MODULE_SHA')
 spec=importlib.util.spec_from_file_location('nox_stage_v84',STAGE)
 module=importlib.util.module_from_spec(spec)
 import sys
 sys.modules[spec.name]=module
 spec.loader.exec_module(module)
 paths={'seed':SEED,'infinite':INFINITE}
 # Run against real databases with authoritative deny-all per-record ACL.
 # No private memory content or hashes are emitted.
 counts={'seen':0}
 def deny_record(scope,kind,record):
  counts['seen']+=1
  return False
 native=module.NativeMemoryAccess(lambda scope,action:scope=='nox-v87-smoke' and action=='s03.recall',deny_record,lambda:False)
 result=module.retrieve('NOX',scope='nox-v87-smoke',paths=paths,native=native,limit=5)
 safe={'state':result.get('state'),'returned':result.get('returned'),'result_count':len(result.get('results',[])),
       'records_rejected_by_native_acl':counts['seen']}
 emit('NATIVE_V87_REAL_DB_QUERY',safe)
 if safe['state']!='NATIVE_LOCAL_MEMORY_RETRIEVED' or safe['result_count']!=0 or not counts['seen']:
  raise RuntimeError('HOLD_REAL_DB_QUERY_OR_DENY_ACL')
 if any(Path(x).exists() for x in STOP):raise RuntimeError('HOLD_STOP_REVOKED')
 print('NATIVE_V87_REAL_S03_QUERY_WITH_DENY_ALL_ACL=PASS')
except Exception as exc:
 print('NATIVE_V87_HOLD='+(str(exc) if str(exc).startswith('HOLD_') else 'LIVE_QUERY_OR_RUNTIME'))
print('NATIVE_V87_MEMORY_TEXT_EXPORTED=false')
print('NATIVE_V87_S03_WRITES=false')
print('NATIVE_V87_TRAINING_STARTED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    out=io.StringIO();ok=False
    original=bridge.api
    def settle(method,path,key,data=None):
        r=original(method,path,key,data)
        if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
        return r
    bridge.REMOTE=REMOTE;bridge.api=settle
    try:
        with contextlib.redirect_stdout(out):ok=bridge.probe()
    except Exception as exc:
        val=str(exc)
        print("NOX_V87_HOLD="+(val if val.startswith('HOLD_') and len(val)<70 else 'NATIVE_BRIDGE'))
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if bridge.cleanup() is not True:ok=False
        except Exception:ok=False
    raw=out.getvalue()
    for line in raw.splitlines():
        if line.startswith(('NATIVE_V87_','TEMP_SSH_CLEANUP=')) and len(line)<1200:
            print(line)
    passed=bool(ok and 'NATIVE_V87_REAL_S03_QUERY_WITH_DENY_ALL_ACL=PASS' in raw)
    print('NOX_V87_PHYSICAL_READTHROUGH_ACCEPTED='+str(passed).lower())
    return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
