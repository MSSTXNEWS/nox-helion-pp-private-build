"""NOX V95: bound OPTIONAL CEDR/live-registry enrichment before first token.

Preserves S03 retrieval, actual model streaming and existing OneHost. A single
bounded worker prevents queuing new slow CEDR work while previous work remains
in-flight. Changes only one SHA-pinned native proxy with rollback.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import contextlib,io,time
_api=ssh.api
def settle(method,path,key,data=None):
 x=_api(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return x
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,os,hashlib,json,stat,subprocess,urllib.request,time
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V95_TTFT_OPTIONAL_ENRICH_BOUND_V1')
FILE=Path('/root/nox/scripts/chat_proxy.py')
EXPECTED='cca063f9bb31d1023d753f3adce5226a99dceed88ebd97fad08ebf6478609d18'
BACKUP=FILE.with_name('chat_proxy.py.nox-v95-backup-'+EXPECTED[:12])
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(blob):return hashlib.sha256(blob).hexdigest()
def emit(**r):print('NATIVE_V95_RESULT='+json.dumps(r,sort_keys=True,separators=(',',':')))
def healthy(port):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as r:return r.status
 except Exception:return None
def service():
 try:
  p=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=7)
  tokens=p.stdout.split()
  return tokens[1] if p.returncode==0 and len(tokens)>1 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def slots_idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:x=json.loads(r.read(25000))
  return isinstance(x,list) and len(x)==6 and not any(k.get('is_processing',k.get('processing',False)) for k in x if isinstance(k,dict))
 except Exception:return False
def revert(raw,meta):
 try:
  tmp=FILE.with_name('.nox-v95-revert.tmp')
  with tmp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  os.chmod(tmp,stat.S_IMODE(meta.st_mode));os.chown(tmp,meta.st_uid,meta.st_gid)
  os.replace(tmp,FILE)
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=30,check=True)
  for i in range(15):
   if service()=='RUNNING' and healthy(8080)==200 and healthy(8081)==200:
    return sha(FILE.read_bytes())==EXPECTED
   time.sleep(1)
 except Exception:pass
 return False
helper='''from concurrent.futures import ThreadPoolExecutor as _NoxPool, TimeoutError as _NoxOptionalTimeout
from threading import BoundedSemaphore as _NoxSemaphore
_NOX_OPTIONAL_ENRICH_POOL = _NoxPool(max_workers=1,thread_name_prefix='nox-optional-emotion')
_NOX_OPTIONAL_ENRICH_GATE = _NoxSemaphore(1)

def _nox_bounded_optional_enrich(fn, prompt):
    # Bounded optional context; never bind essential S03 to this timer.
    if any(Path(p).exists() for p in ('/root/nox/STOP','/root/nox/STOP.flag','/workspace/NOX_STOP')):
        return []
    if not _NOX_OPTIONAL_ENRICH_GATE.acquire(blocking=False):
        return []
    try:
        future = _NOX_OPTIONAL_ENRICH_POOL.submit(fn,prompt)
    except Exception:
        _NOX_OPTIONAL_ENRICH_GATE.release()
        return []
    future.add_done_callback(lambda _f: _NOX_OPTIONAL_ENRICH_GATE.release())
    try:
        raw = future.result(timeout=0.25)
    except _NoxOptionalTimeout:
        return []
    except Exception:
        return []
    if not isinstance(raw,list):
        return []
    if any(Path(p).exists() for p in ('/root/nox/STOP','/root/nox/STOP.flag','/workspace/NOX_STOP')):
        return []
    return [text[:500] for text in raw[:8] if isinstance(text,str)]

'''
try:
 if any(Path(s).exists() for s in STOPS):raise RuntimeError('HOLD_STOP')
 if not FILE.is_file() or FILE.is_symlink():raise RuntimeError('HOLD_NO_SOURCE')
 meta=FILE.stat();original=FILE.read_bytes()
 if meta.st_uid!=0 or len(original)>145000 or sha(original)!=EXPECTED:
  raise RuntimeError('HOLD_SOURCE_CHANGED')
 if service()!='RUNNING' or healthy(8080)!=200 or healthy(8081)!=200 or not slots_idle():
  raise RuntimeError('HOLD_ACTIVE_OR_UNHEALTHY_CHAT')
 text=original.decode('utf8')
 header='def _augment(user_text: str, dialog_msgs=None) -> str:'
 old='        parts.extend(extra_parts(user_text) or [])'
 new='        parts.extend(_nox_bounded_optional_enrich(extra_parts,user_text))'
 if text.count(header)!=1 or text.count(old)!=1 or '_NOX_OPTIONAL_ENRICH_POOL' in text:
  raise RuntimeError('HOLD_EXACT_ENRICH_ANCHORS')
 text=text.replace(header,helper+header,1).replace(old,new,1)
 updated=text.encode('utf8')
 if len(updated)>150000:raise RuntimeError('HOLD_PATCH_SIZE')
 tree=ast.parse(updated.decode());compile(updated,str(FILE),'exec')
 m=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='_augment')
 if not any(isinstance(x,ast.Call) and isinstance(x.func,ast.Name)
            and x.func.id=='_nox_bounded_optional_enrich' for x in ast.walk(m)):
  raise RuntimeError('HOLD_NO_TIMEBOX_AST')
 if text.count('_s03_augment(retrieve_text)')!=1 or text.count('NOX_MEM.extra_context(')!=1:
  raise RuntimeError('HOLD_MANDATORY_MEMORY_CHANGED')
 if not slots_idle() or any(Path(s).exists() for s in STOPS):raise RuntimeError('HOLD_CHAT_BECAME_BUSY')
 if BACKUP.exists():
  if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=EXPECTED:raise RuntimeError('HOLD_BACKUP_SHA')
 else:
  with BACKUP.open('xb') as f:f.write(original);f.flush();os.fsync(f.fileno())
  os.chmod(BACKUP,stat.S_IMODE(meta.st_mode));os.chown(BACKUP,meta.st_uid,meta.st_gid)
 temp=FILE.with_name('.nox-v95-patch.tmp')
 if temp.exists():raise RuntimeError('HOLD_TEMP_EXISTS')
 with temp.open('xb') as f:f.write(updated);f.flush();os.fsync(f.fileno())
 os.chmod(temp,stat.S_IMODE(meta.st_mode));os.chown(temp,meta.st_uid,meta.st_gid)
 if sha(temp.read_bytes())!=sha(updated):raise RuntimeError('HOLD_TEMP_SHA')
 os.replace(temp,FILE)
 try:
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=30,check=True)
  okay=False
  for _ in range(16):
   if service()=='RUNNING' and healthy(8080)==200 and healthy(8081)==200:
    okay=True;break
   time.sleep(1)
  if not okay or sha(FILE.read_bytes())!=sha(updated) or any(Path(s).exists() for s in STOPS):
   raise RuntimeError('HOLD_POST_DEPLOY')
  emit(state='NATIVE_OPTIONAL_ENRICH_TTFT_BOUNDED',new_sha256=sha(updated),
       backup_verified=sha(BACKUP.read_bytes())==EXPECTED,owner_chat_health=200,
       main_model_health=200,optional_enrich_timeout_ms=250,
       single_background_worker=True,s03_retrieval_unchanged=True,
       memory_dialog_scope_preserved=True,onehost_only=True,
       weights_changed=False,trained_steps_claimed=0,
       precise_ttft_gain_measured=False)
 except Exception:
  restored=revert(original,meta)
  emit(state='HOLD_AUTOMATIC_ROLLBACK' if restored else 'HOLD_ROLLBACK_UNVERIFIED',rollback=restored)
except Exception as e:
 value=str(e)
 emit(state=value if value.startswith('HOLD_') and len(value)<100 else 'HOLD_NATIVE_PRECHECK',
      weights_changed=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 ssh.REMOTE=REMOTE;ssh.api=settle;buffer=io.StringIO();ok=False
 try:
  with contextlib.redirect_stdout(buffer):ok=ssh.probe()
 except Exception as e:
  x=str(e);print('NOX_V95='+x if x.startswith('HOLD_') else 'NOX_V95=HOLD_REMOTE')
 finally:
  try:
   with contextlib.redirect_stdout(buffer):
    if not ssh.cleanup():ok=False
  except Exception:ok=False
 found=[]
 for line in buffer.getvalue().splitlines():
  if line.startswith('NATIVE_V95_RESULT=') and len(line)<1800:
   print(line);found.append(line)
  elif line.startswith('TEMP_SSH_CLEANUP='):print(line[:120])
 good=bool(ok and len(found)==1 and 'NATIVE_OPTIONAL_ENRICH_TTFT_BOUNDED' in found[0])
 print('NOX_V95_NATIVE_ACCEPTED='+str(good).lower())
 return 0 if good else 2
if __name__=='__main__':raise SystemExit(main())
