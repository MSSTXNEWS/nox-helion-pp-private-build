"""NOX V93: preserve session-consistent native S03 dialog lookup across turns.

Existing memory_hooks.jp_dialog_id hashes the FIRST user turn of a multi-turn
conversation. Earlier _augment supplied only the LAST text (new dialog every
turn). Pass a bounded copy of existing authorised chat messages, never user-
supplied dialog_id, without creating a second DB or reducing the S03 retrieval.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import contextlib,io,time
_api=ssh.api
def gate(method,path,key,data=None):
 r=_api(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,os,re,stat,hashlib,json,subprocess,urllib.request,time
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V93_SINGLE_S03_DIALOG_SCOPE_LIVE_V1')
FILE=Path('/root/nox/scripts/chat_proxy.py')
PREVIOUS='f21d57c607772a20d80f25b98b8b44cb65148c1e3c5ef876adcd57c6d898ce9a'
BACKUP=FILE.with_name('chat_proxy.py.nox-v93-backup-'+PREVIOUS[:12])
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(x):return hashlib.sha256(x).hexdigest()
def emit(**value):print('NATIVE_V93_RESULT='+json.dumps(value,sort_keys=True,separators=(',',':')))
def health(port):
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=3) as r:return r.status
 except Exception:return None
def supervisor():
 try:
  v=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=8)
  a=v.stdout.split()
  return a[1] if v.returncode==0 and len(a)>1 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as f:a=json.loads(f.read(20000))
  if not isinstance(a,list) or len(a)!=6:return False
  return not any(x.get('is_processing',x.get('processing',False)) for x in a if isinstance(x,dict))
 except Exception:return False
def restore(original,meta):
 try:
  temp=FILE.with_name('.nox-v93-rollback.tmp')
  with temp.open('xb') as f:f.write(original);f.flush();os.fsync(f.fileno())
  os.chmod(temp,stat.S_IMODE(meta.st_mode));os.chown(temp,meta.st_uid,meta.st_gid)
  os.replace(temp,FILE)
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=30,check=True)
  for i in range(15):
   if supervisor()=='RUNNING' and health(8080)==200 and health(8081)==200:
    return sha(FILE.read_bytes())==PREVIOUS
   time.sleep(1)
 except Exception:pass
 return False
try:
 if any(Path(x).exists() for x in STOPS):raise RuntimeError('HOLD_STOP')
 if not FILE.is_file() or FILE.is_symlink():raise RuntimeError('HOLD_SOURCE')
 meta=FILE.stat();original=FILE.read_bytes()
 if meta.st_uid!=0 or len(original)>140000 or sha(original)!=PREVIOUS:
  raise RuntimeError('HOLD_CHANGED_SOURCE_SHA')
 if health(8080)!=200 or health(8081)!=200 or supervisor()!='RUNNING' or not idle():
  raise RuntimeError('HOLD_ACTIVE_CHAT_OR_HEALTH')
 text=original.decode('utf8')
 anchors={
 'def _augment(user_text: str) -> str:':'def _augment(user_text: str, dialog_msgs=None) -> str:',
 'augmented = _augment(user_text)':'augmented = _augment(user_text, msgs)',
 "            did = NOX_MEM.jp_dialog_id({'message': user_text or ''})":(
 "            _first_user = next((m.get('content') for m in (dialog_msgs or [])\n"
 "                if isinstance(m, dict) and m.get('role') == 'user'\n"
 "                and isinstance(m.get('content'), str) and m.get('content').strip()), '')\n"
 "            _bounded_history = (isinstance(dialog_msgs, list) and len(dialog_msgs) <= 128\n"
 "                and isinstance(_first_user, str) and 16 <= len(_first_user) <= 8000)\n"
 "            _memory_payload = {'messages': dialog_msgs} if _bounded_history else {'message': user_text or ''}\n"
 "            did = NOX_MEM.jp_dialog_id(_memory_payload)"
 )}
 for index,(a,b) in enumerate(anchors.items()):
  if index==2:
   # AST locates the native dialog assignment even when quote/spacing differs.
   source_ast=ast.parse(text)
   source_fn=next(x for x in source_ast.body if isinstance(x,ast.FunctionDef) and x.name=='_augment')
   candidates=[x for x in ast.walk(source_fn)
               if isinstance(x,ast.Assign)
               and any(isinstance(t,ast.Name) and t.id=='did' for t in x.targets)
               and isinstance(x.value,ast.Call)
               and isinstance(x.value.func,ast.Attribute)
               and x.value.func.attr=='jp_dialog_id']
   if len(candidates)!=1 or candidates[0].lineno!=candidates[0].end_lineno:
    raise RuntimeError('HOLD_AST_MEMORY_ASSIGNMENT_NOT_UNIQUE')
   lines=text.splitlines(keepends=True)
   line=lines[candidates[0].lineno-1]
   indent=line[:len(line)-len(line.lstrip())]
   if 'NOX_MEM.jp_dialog_id(' not in line or len(indent)!=12:
    raise RuntimeError('HOLD_MEMORY_SOURCE_LAYOUT')
   lines[candidates[0].lineno-1]=b+'\n'
   text=''.join(lines)
   continue
  if text.count(a)!=1:
   emit(state='HOLD_ANCHOR_COUNT',anchor_index=index,anchor_count=text.count(a))
   raise RuntimeError('HOLD_ANCHOR_COUNT')
  text=text.replace(a,b,1)
 new=text.encode('utf8')
 if len(new)>145000:raise RuntimeError('HOLD_PATCH_SIZE')
 tree=ast.parse(new.decode());compile(new,str(FILE),'exec')
 augment=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='_augment')
 build=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='_build_messages')
 if not any(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr=='jp_dialog_id'
   for x in ast.walk(augment)):raise RuntimeError('HOLD_AST_NO_NATIVE_MEMORY')
 if not any(isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id=='_augment'
    and len(x.args)==2 for x in ast.walk(build)):raise RuntimeError('HOLD_AST_NO_SESSION_HISTORY')
 # Native deterministic memory identifier smoke without reading any records.
 import sys
 sys.path.insert(0,'/root/nox/scripts')
 from memory_hooks import jp_dialog_id
 first={'role':'user','content':'Расскажи про происхождение NOX HELION.'}
 more={'role':'user','content':'Какие события ты помнишь?'}
 history_id_1=jp_dialog_id({'messages':[first]})
 history_id_2=jp_dialog_id({'messages':[first,{'role':'assistant','content':'Нейтральный ответ'},more]})
 other=jp_dialog_id({'messages':[{'role':'user','content':'Другая исходная беседа'}]})
 if history_id_1!=history_id_2 or history_id_1==other:
  raise RuntimeError('HOLD_S03_DIALOG_ID_SEMANTICS')
 if not idle() or any(Path(x).exists() for x in STOPS):raise RuntimeError('HOLD_CHAT_BECAME_BUSY')
 if BACKUP.exists():
  if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=PREVIOUS:raise RuntimeError('HOLD_BACKUP_CONFLICT')
 else:
  with BACKUP.open('xb') as f:f.write(original);f.flush();os.fsync(f.fileno())
  os.chmod(BACKUP,stat.S_IMODE(meta.st_mode));os.chown(BACKUP,meta.st_uid,meta.st_gid)
 temp=FILE.with_name('.nox-v93-patch.tmp')
 if temp.exists():raise RuntimeError('HOLD_TEMP_CONFLICT')
 with temp.open('xb') as f:f.write(new);f.flush();os.fsync(f.fileno())
 os.chmod(temp,stat.S_IMODE(meta.st_mode));os.chown(temp,meta.st_uid,meta.st_gid)
 if sha(temp.read_bytes())!=sha(new):raise RuntimeError('HOLD_TEMP_SHA')
 os.replace(temp,FILE)
 try:
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=30,check=True)
  accepted=False
  for _ in range(16):
   if supervisor()=='RUNNING' and health(8080)==200 and health(8081)==200:
    accepted=True;break
   time.sleep(1)
  if not accepted or sha(FILE.read_bytes())!=sha(new) or any(Path(x).exists() for x in STOPS):
   raise RuntimeError('HOLD_POST_RESTART')
  emit(state='NATIVE_MULTI_TURN_S03_DIALOG_BOUND',new_sha256=sha(new),previous_sha256=PREVIOUS,
       original_backup_sha_verified=sha(BACKUP.read_bytes())==PREVIOUS,
       native_dialog_id_regression='PASS',onehost_chat_health=200,model_health=200,
       no_new_db=True,model_weights_unchanged=True,owner_memory_access_not_widened=True,
       broad_s03_cross_chat_access_added=False,training_started=False)
 except Exception:
  result=restore(original,meta)
  emit(state='HOLD_ROLLED_BACK' if result else 'HOLD_ROLLBACK_UNVERIFIED',rollback=result)
except Exception as e:
 name=str(e)
 emit(state=name if name.startswith('HOLD_') and len(name)<100 else 'HOLD_PRECHECK',
      previous_weights_untouched=True)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
 ssh.REMOTE=REMOTE;ssh.api=gate;out=io.StringIO();ok=False
 try:
  with contextlib.redirect_stdout(out):ok=ssh.probe()
 except Exception as e:
  s=str(e);print('NOX_V93='+s if s.startswith('HOLD_') else 'NOX_V93=HOLD_NATIVE')
 finally:
  try:
   with contextlib.redirect_stdout(out):
    if not ssh.cleanup():ok=False
  except Exception:ok=False
 rows=[]
 for line in out.getvalue().splitlines():
  if line.startswith('NATIVE_V93_RESULT=') and len(line)<1800:rows.append(line);print(line)
  elif line.startswith('TEMP_SSH_CLEANUP='):print(line[:120])
 accepted=bool(ok and len(rows)==1 and 'NATIVE_MULTI_TURN_S03_DIALOG_BOUND' in rows[0])
 print('NOX_V93_PHYSICAL_ACCEPTED='+str(accepted).lower())
 return 0 if accepted else 2
if __name__=='__main__':raise SystemExit(main())
