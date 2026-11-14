"""V115 isolated native teacher callback proof on live NOX, synthetic arithmetic only.
No user login secrets, no cookies, no private memory and no service changes.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r'''
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import hashlib,json,time,urllib.request,re
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V115_ISOLATED_LOCAL_TEACHER_HOOK_V1')
def emit(**v):print('NATIVE_V115='+json.dumps(v,sort_keys=True,separators=(',',':')))
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
try:
 if any(Path(p).exists() for p in STOPS):raise RuntimeError('HOLD_STOP')
 p=Path('/root/nox/scripts/chat_proxy.py')
 sha=hashlib.sha256(p.read_bytes()).hexdigest()
 if sha!='b7ba15d061fc6e518c2798ed42513c1113a115bc314d8cbaa3096a152d206d7f':
  raise RuntimeError('HOLD_SOURCE_SHA')
 with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=5) as r:
  slots=json.loads(r.read(26000))
 if not isinstance(slots,list) or len(slots)!=6 or any(
        s.get('is_processing',s.get('processing',False)) for s in slots if isinstance(s,dict)):
  raise RuntimeError('HOLD_MAIN_BUSY')
 with urllib.request.urlopen('http://127.0.0.1:8084/health',timeout=4) as r:
  if r.status!=200:raise RuntimeError('HOLD_TEACHER_UNHEALTHY')
 import chat_proxy
 fn=getattr(chat_proxy,'_nox_v113_public_math_teacher',None)
 if not callable(fn):raise RuntimeError('HOLD_OWNER_TEACHER_NOT_IMPORTED')
 # Public non-mathematical input must be rejected before remote model inference.
 rejects=(fn('Привет')=='') and (fn('@учитель: абв')=='') and (fn('@teacher: 123 + 17')=='')
 if not rejects:raise RuntimeError('HOLD_NON_PUBLIC_REJECT')
 start=time.monotonic()
 hint=fn('@учитель: 17*19')
 elapsed=int((time.monotonic()-start)*1000)
 valid=bool(isinstance(hint,str) and '323' in hint and '17' in hint and '19' in hint)
 emit(state='LIVE_LOCAL_TEACHER_SAFE_HINT_PASS' if valid else 'HOLD_TEACHER_HINT_EMPTY_OR_INVALID',
      source_sha256=sha,invalid_commands_rejected=rejects,
      verified_math_hint=valid,elapsed_ms=elapsed,
      independent_python_arithmetic=(17*19==323),
      only_local_public_prompt=True,user_records_exported=False,
      s03_modified=False,weights_changed=False)
 if valid:print('NATIVE_V115_LIVE_TEACHER_HINT_ACCEPTED=true')
except Exception as ex:
 x=str(ex)
 emit(state=x if x.startswith('HOLD_') and len(x)<90 else 'HOLD_NATIVE_TEACHER',
      exception_type=type(ex).__name__,user_records_exported=False,weights_changed=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
    ssh.REMOTE=REMOTE
    orig=ssh.api
    def gate(method,path,key,data=None):
        for i in range(4):
            try:
                r=orig(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return r
            except RuntimeError as e:
                if method!='GET' or str(e)!='HOLD_VAST_API_HTTP_429' or i==3:raise
                time.sleep((10,20,40)[i])
    ssh.api=gate
    out=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(out):ok=ssh.probe()
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if ssh.cleanup() is not True:ok=False
        except Exception:ok=False
    lines=out.getvalue().splitlines()
    for l in lines:
        if l.startswith(('NATIVE_V115=','NATIVE_V115_LIVE_TEACHER_HINT_ACCEPTED=','TEMP_SSH_CLEANUP=')):
            print(l[:1500])
    passed=bool(ok and 'NATIVE_V115_LIVE_TEACHER_HINT_ACCEPTED=true' in lines)
    print('NOX_V115_HOOK_PASS='+str(passed).lower())
    return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
