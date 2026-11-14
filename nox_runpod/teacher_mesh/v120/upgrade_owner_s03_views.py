"""V120 safe deployment into existing NOX OneHost with no second S03 or backend."""
from __future__ import annotations
import base64
import contextlib
import hashlib
import io
from pathlib import Path
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

MODULE=Path('nox_runpod/teacher_mesh/v120/s03_owner_memory_views.py')
REMOTE_TEMPLATE=r'''
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,base64,hashlib,json,os,stat,subprocess,time,urllib.error,urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V120_S03_EXISTING_ONEHOST_V1')
P=Path('/root/nox/scripts/chat_proxy.py')
M=Path('/root/nox/scripts/nox_v120_s03_owner_memory_views.py')
EXPECTED='58e7fb20eb87e582a3e52486dcc93899affc34aa7b80f029b09696c545353d16'
B=base64.b64decode('___MODULE_BASE64___',validate=True)
BSHA='___MODULE_SHA___'
BACKUP=P.with_name('chat_proxy.py.nox-v120-'+EXPECTED[:12]+'.bak')
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(x):return hashlib.sha256(x).hexdigest()
def stopped():return any(Path(x).exists() for x in STOPS)
def emit(**d):print('NATIVE_V120_RECEIPT='+json.dumps(d,sort_keys=True,separators=(',',':')))
def health(port):
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=4) as f:return f.status
 except Exception:return None
def state():
 try:
  p=subprocess.run(['supervisorctl','status','nox-proxy'],text=True,capture_output=True,timeout=8)
  fields=p.stdout.split()
  return fields[1] if len(fields)>1 and p.returncode==0 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as f:a=json.loads(f.read(26000))
  return isinstance(a,list) and len(a)==6 and not any(
    x.get('is_processing',x.get('processing',False)) for x in a if isinstance(x,dict))
 except Exception:return False
def atomic(path,blob,meta,tmpname):
 temp=path.with_name(tmpname)
 if temp.exists() or temp.is_symlink():raise RuntimeError('HOLD_TEMP_EXISTS')
 with temp.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
 os.chmod(temp,stat.S_IMODE(meta.st_mode));os.chown(temp,meta.st_uid,meta.st_gid)
 if sha(temp.read_bytes())!=sha(blob):raise RuntimeError('HOLD_TEMP_SHA')
 os.replace(temp,path)
def revert(blob,meta):
 try:
  atomic(P,blob,meta,'.nox-v120-rollback.tmp')
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=35,check=True)
  for _ in range(18):
   if state()=='RUNNING' and health(8080)==200 and health(8081)==200:
    return sha(P.read_bytes())==EXPECTED
   time.sleep(1)
 except Exception:return False
 return False
def anonymous_code(path):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=4) as r:return r.status
 except urllib.error.HTTPError as e:return e.code
 except Exception:return None
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 if not P.is_file() or P.is_symlink() or len(B)<3000 or len(B)>16000 or sha(B)!=BSHA:
  raise RuntimeError('HOLD_SOURCE_OR_MODULE_SHA')
 meta=P.stat();previous=P.read_bytes()
 if meta.st_uid!=0 or sha(previous)!=EXPECTED or len(previous)>195000:
  raise RuntimeError('HOLD_NATIVE_SOURCE_SHA')
 if state()!='RUNNING' or health(8080)!=200 or health(8081)!=200 or not idle():
  raise RuntimeError('HOLD_ACTIVE_CHAT')
 compile(B,str(M),'exec')
 tree=ast.parse(B)
 if not any(isinstance(x,ast.FunctionDef) and x.name=='register_nox_v120_s03_memory_views' for x in tree.body):
  raise RuntimeError('HOLD_NATIVE_MEMORY_REGISTRATION')
 source=previous.decode('utf8')
 anchor='register_nox_v118_real_read_surfaces(app, globals())\n'
 extra='from nox_v120_s03_owner_memory_views import register_nox_v120_s03_memory_views\nregister_nox_v120_s03_memory_views(app, globals())\n'
 oldauth="'/api/nox/model','/api/nox/memory','/api/training/status'"
 newauth="'/api/nox/model','/api/nox/memory','/api/nox/history','/api/nox/experience','/api/training/status'"
 if source.count(anchor)!=1 or source.count(oldauth)!=1 or 'register_nox_v120_s03_memory_views(' in source:
  raise RuntimeError('HOLD_NATIVE_OLD_ANCHORS')
 updated=source.replace(anchor,anchor+extra,1).replace(oldauth,newauth,1)
 compile(updated,str(P),'exec')
 if len(updated)>200000:raise RuntimeError('HOLD_CODE_SIZE')
 if M.exists():
  if M.is_symlink() or sha(M.read_bytes())!=BSHA:raise RuntimeError('HOLD_EXISTING_MODULE_CONFLICT')
 else:
  atomic(M,B,meta,'.nox-v120-module.tmp')
 isolated="""from nox_v120_s03_owner_memory_views import register_nox_v120_s03_memory_views
assert callable(register_nox_v120_s03_memory_views)
print('NOX_V120_MODULE_IMPORT=PASS')
"""
 r=subprocess.run(['/root/nox/venv/bin/python','-c',isolated],cwd='/root/nox/scripts',
                  text=True,capture_output=True,timeout=15)
 if r.returncode!=0 or 'NOX_V120_MODULE_IMPORT=PASS' not in r.stdout:
  raise RuntimeError('HOLD_NATIVE_IMPORT')
 if stopped() or not idle():raise RuntimeError('HOLD_CHAT_BECAME_BUSY')
 if BACKUP.exists():
  if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=EXPECTED:
   raise RuntimeError('HOLD_BACKUP_CONFLICT')
 else:
  with BACKUP.open('xb') as f:f.write(previous);f.flush();os.fsync(f.fileno())
  os.chmod(BACKUP,stat.S_IMODE(meta.st_mode));os.chown(BACKUP,meta.st_uid,meta.st_gid)
 if sha(BACKUP.read_bytes())!=EXPECTED:raise RuntimeError('HOLD_BACKUP_SHA')
 atomic(P,updated.encode('utf8'),meta,'.nox-v120-owner-memory.tmp')
 try:
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=35,check=True)
  ready=False
  for _ in range(18):
   if state()=='RUNNING' and health(8080)==200 and health(8081)==200:
    ready=True;break
   time.sleep(1)
  if not ready or sha(P.read_bytes())!=sha(updated.encode('utf8')) or stopped():
   raise RuntimeError('HOLD_POST_NATIVE_RESTART')
  paths=['/api/nox/history','/api/nox/experience','/api/ui/memory/facts/history']
  codes=[anonymous_code(p) for p in paths]
  if codes!=[401,401,401]:raise RuntimeError('HOLD_ANONYMOUS_ACCESS')
  emit(state='NATIVE_V120_S03_OWNER_MEMORY_ROUTES_INSTALLED',
       proxy_sha256=sha(P.read_bytes()),module_sha256=BSHA,
       prior_backup_verified=True,anonymous_http=codes,
       native_routes=paths,onehost_no_second_db=True,
       original_s03_untouched=True,owner_memory_http_e2e_verified=False,
       private_records_exported=False,weights_changed=False)
 except Exception as ex:
  rollback=revert(previous,meta)
  msg=str(ex)
  emit(state='HOLD_ROLLED_BACK' if rollback else 'HOLD_ROLLBACK_UNVERIFIED',
       rollback=rollback,failed_gate=msg if msg.startswith('HOLD_') and len(msg)<90 else type(ex).__name__)
except Exception as ex:
 msg=str(ex)
 emit(state=msg if msg.startswith('HOLD_') and len(msg)<100 else 'HOLD_PRECHECK',
      weights_changed=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
    module=MODULE.read_bytes()
    compile(module,str(MODULE),'exec')
    ssh.REMOTE=REMOTE_TEMPLATE.replace('___MODULE_BASE64___',base64.b64encode(module).decode())
    ssh.REMOTE=ssh.REMOTE.replace('___MODULE_SHA___',hashlib.sha256(module).hexdigest())
    old=ssh.api
    def settle(method,path,key,data=None):
        for attempt in range(4):
            try:
                val=old(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return val
            except RuntimeError as e:
                if method!='GET' or str(e)!='HOLD_VAST_API_HTTP_429' or attempt==3:raise
                time.sleep((10,20,40)[attempt])
    ssh.api=settle
    out=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(out):ok=ssh.probe()
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if ssh.cleanup() is not True:ok=False
        except Exception:ok=False
    receipts=[]
    for line in out.getvalue().splitlines():
        if line.startswith('NATIVE_V120_RECEIPT=') and len(line)<2500:
            receipts.append(line);print(line)
        elif line.startswith('TEMP_SSH_CLEANUP='):print(line[:130])
    accepted=bool(ok and len(receipts)==1 and 'NATIVE_V120_S03_OWNER_MEMORY_ROUTES_INSTALLED' in receipts[0])
    print('NOX_V120_S03_MEMORY_ROUTES_ACCEPTED='+str(accepted).lower())
    return 0 if accepted else 2
if __name__=='__main__':raise SystemExit(main())
