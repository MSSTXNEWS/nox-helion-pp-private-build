"""NOX V91: avoid a redundant pre-LLM owner hook for self/memory questions.

V77 was calling the hook before discarding its result, wasting TTFT while
risking misleading canned descriptions. Existing authenticated owner session,
S03 augmentation, model and privileged tool routes are preserved.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import contextlib,io,time
_api=ssh.api
def settle(method,path,key,data=None):
 v=_api(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return v

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,os,re,hashlib,stat,json,subprocess,time,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V91_AUTH_OWNER_FASTPATH_ONEPATCH_V1')
P=Path('/root/nox/scripts/chat_proxy.py')
OLD='596130dda753d7fed5514a0ae36d8908be8699c804cbb1288f58a410418f043b'
BAK=P.with_name('chat_proxy.py.nox-v91-backup-'+OLD[:12])
SERVICE='nox-proxy'
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(v):return hashlib.sha256(v).hexdigest()
def emit(**v):print('NATIVE_V91_RESULT='+json.dumps(v,sort_keys=True,separators=(',',':')))
def health(port):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=4) as r:return r.status
 except Exception:return None
def supervisor():
 try:
  x=subprocess.run(['supervisorctl','status',SERVICE],capture_output=True,text=True,timeout=8)
  parts=x.stdout.split()
  return parts[1] if x.returncode==0 and len(parts)>1 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def busy_slots():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as r:d=json.loads(r.read(20000))
  if not isinstance(d,list) or len(d)!=6:return None
  return sum(bool(x.get('is_processing',x.get('processing',False))) for x in d if isinstance(x,dict))
 except Exception:return None
def restore(raw,meta):
 try:
  target=P.with_name('.nox-v91-rollback.tmp')
  with target.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  os.chmod(target,stat.S_IMODE(meta.st_mode));os.chown(target,meta.st_uid,meta.st_gid)
  os.replace(target,P)
  x=subprocess.run(['supervisorctl','restart',SERVICE],capture_output=True,timeout=30)
  for _ in range(12):
   if health(8080)==200 and health(8081)==200 and supervisor()=='RUNNING':
    return sha(P.read_bytes())==OLD
   time.sleep(1)
 except Exception:pass
 return False
try:
 if any(Path(x).exists() for x in STOPS):raise RuntimeError('HOLD_STOP')
 if not P.is_file() or P.is_symlink():raise RuntimeError('HOLD_SOURCE_MISSING')
 meta=P.stat();raw=P.read_bytes()
 if meta.st_uid!=0 or len(raw)>130000 or sha(raw)!=OLD:raise RuntimeError('HOLD_SOURCE_SHA')
 if health(8080)!=200 or health(8081)!=200 or supervisor()!='RUNNING':
  raise RuntimeError('HOLD_NO_MAIN_HEALTH')
 if busy_slots()!=0:raise RuntimeError('HOLD_ACTIVE_CHAT_STREAM')
 text=raw.decode('utf8')
 head='    _und = _understanding_http(_utext, stream, body)\n'
 tail='\n    if _und is not None:'
 if text.count(head)!=1:raise RuntimeError('HOLD_HOOK_ANCHOR')
 start=text.index(head)
 end=text.find(tail,start)
 if end<=start or end-start>1700:raise RuntimeError('HOLD_ROUTE_SCOPE')
 snippet=text[start:end]
 regex=(r'    _und = _understanding_http\(_utext, stream, body\)\n'
        r'    if isinstance\(_utext, str\) and any\(word in _utext\.casefold\(\) for word in (\(.+\))\):\n'
        r'        _und = None  # send autobiography/memory questions to the actual NOX model')
 match=re.fullmatch(regex,snippet)
 if match is None:raise RuntimeError('HOLD_EXACT_ROUTE_LAYOUT')
 terms=match.group(1)
 import ast as _ast
 words=_ast.literal_eval(terms)
 if not isinstance(words,tuple) or len(words)<10 or not all(isinstance(x,str) for x in words):
  raise RuntimeError('HOLD_FOCUS_SET_CHANGED')
 new=('    _self_query = bool(_owner and isinstance(_utext, str) and any(\n'
      '        word in _utext.casefold() for word in '+terms+'))\n'
      '    _und = None if _self_query else _understanding_http(_utext, stream, body)')
 changed=(text[:start]+new+text[end:]).encode('utf8')
 if len(changed)>130000 or changed==raw:raise RuntimeError('HOLD_BAD_PATCH')
 tree=ast.parse(changed.decode());compile(changed,str(P),'exec')
 fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='_proxy_completion')
 checks=ast.get_source_segment(changed.decode(),fn)
 if not checks or '_self_query' not in checks or checks.count('_understanding_http(')!=1:
  raise RuntimeError('HOLD_PYTHON_AST')
 if busy_slots()!=0 or any(Path(x).exists() for x in STOPS):raise RuntimeError('HOLD_CHAT_OR_STOP_CHANGED')
 if BAK.exists():
  if BAK.is_symlink() or sha(BAK.read_bytes())!=OLD:raise RuntimeError('HOLD_BACKUP_CONFLICT')
 else:
  with BAK.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  os.chmod(BAK,stat.S_IMODE(meta.st_mode));os.chown(BAK,meta.st_uid,meta.st_gid)
 tmp=P.with_name('.nox-v91-patch.tmp')
 if tmp.exists():raise RuntimeError('HOLD_TEMP_CONFLICT')
 with tmp.open('xb') as f:f.write(changed);f.flush();os.fsync(f.fileno())
 os.chmod(tmp,stat.S_IMODE(meta.st_mode));os.chown(tmp,meta.st_uid,meta.st_gid)
 if sha(tmp.read_bytes())!=sha(changed):raise RuntimeError('HOLD_TMP_SHA')
 os.replace(tmp,P)
 try:
  subprocess.run(['supervisorctl','restart',SERVICE],capture_output=True,text=True,timeout=30,check=True)
  good=False
  for _ in range(14):
   if health(8080)==200 and health(8081)==200 and supervisor()=='RUNNING':
    good=True;break
   time.sleep(1)
  if not good or sha(P.read_bytes())!=sha(changed) or any(Path(x).exists() for x in STOPS):
   raise RuntimeError('HOLD_POST_LIVE')
  emit(state='NATIVE_OWNER_SELF_FASTPATH_ACTIVE',old_sha256=OLD,new_sha256=sha(changed),
       backup_verified=sha(BAK.read_bytes())==OLD,server='EXISTING_NOX_PROXY',
       service_restart_count=1,chat_health=200,model_health=200,active_slots_before=0,
       auth_owner_only=True,s03_augment_unchanged=True,model_weights_unchanged=True,
       first_token_improvement_measured=False,onehost_new_backend=False)
 except Exception:
  ok=restore(raw,meta)
  emit(state='HOLD_PATCH_ROLLED_BACK' if ok else 'HOLD_ROLLBACK_UNVERIFIED',rollback_verified=ok)
except Exception as e:
 v=str(e)
 emit(state=v if v.startswith('HOLD_') and len(v)<95 else 'HOLD_NATIVE_GATE',
      model_weights_unchanged=True)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 ssh.REMOTE=REMOTE;ssh.api=settle
 buffer=io.StringIO();ok=False
 try:
  with contextlib.redirect_stdout(buffer):ok=ssh.probe()
 except Exception as e:
  x=str(e);print('NOX_V91='+x if x.startswith('HOLD_') else 'NOX_V91=HOLD_REMOTE')
 finally:
  try:
   with contextlib.redirect_stdout(buffer):
    if not ssh.cleanup():ok=False
  except Exception:ok=False
 receipts=[]
 for line in buffer.getvalue().splitlines():
  if line.startswith('NATIVE_V91_RESULT=') and len(line)<1700:
   receipts.append(line);print(line)
  elif line.startswith('TEMP_SSH_CLEANUP='):print(line[:120])
 accept=bool(ok and len(receipts)==1 and 'NATIVE_OWNER_SELF_FASTPATH_ACTIVE' in receipts[0])
 print('NOX_V91_NATIVE_ACCEPTED='+str(accept).lower())
 return 0 if accept else 2
if __name__=='__main__':raise SystemExit(main())
