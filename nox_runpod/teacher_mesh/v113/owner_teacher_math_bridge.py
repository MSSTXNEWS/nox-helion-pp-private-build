"""V113: opt-in, locally verified arithmetic teacher in existing OneHost.
Only sanitized public integers are sent to local Vikhr (never raw user message,
chat history, S03, secrets, or an external service). No second backend.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r'''
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,hashlib,json,os,stat,subprocess,time,urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
P=Path('/root/nox/scripts/chat_proxy.py')
OLD='07c9feb7f5a192f61b0c64b192c466e2995688b5a14429841da1b308a12076e5'
BACKUP=P.with_name('chat_proxy.py.nox-v113-backup-'+OLD[:12])
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(v):return hashlib.sha256(v).hexdigest()
def stopped():return any(Path(p).exists() for p in STOP)
def emit(**v):print('NATIVE_V113='+json.dumps(v,sort_keys=True,separators=(',',':')))
def health(port):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=4) as r:return r.status
 except Exception:return None
def status():
 try:
  r=subprocess.run(['supervisorctl','status','nox-proxy'],text=True,capture_output=True,timeout=7)
  a=r.stdout.split();return a[1] if r.returncode==0 and len(a)>1 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as r:a=json.loads(r.read(28000))
  return isinstance(a,list) and len(a)==6 and not any(
    x.get('is_processing',x.get('processing',False)) for x in a if isinstance(x,dict))
 except Exception:return False
def atomic(data,meta,temp):
 if temp.exists():raise RuntimeError('HOLD_TEMP_EXISTS')
 with temp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.chmod(temp,stat.S_IMODE(meta.st_mode));os.chown(temp,meta.st_uid,meta.st_gid)
 if sha(temp.read_bytes())!=sha(data):raise RuntimeError('HOLD_TEMP_SHA')
 os.replace(temp,P)
def rollback(old,meta):
 try:
  atomic(old,meta,P.with_name('.nox-v113-rollback.tmp'))
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=35,check=True)
  for _ in range(18):
   if status()=='RUNNING' and health(8080)==200 and health(8081)==200:return sha(P.read_bytes())==OLD
   time.sleep(1)
 except Exception:return False
 return False

HELPER="""from threading import BoundedSemaphore as _NoxTeacherSemaphore
_NOX_V113_GATE = _NoxTeacherSemaphore(1)
def _nox_v113_public_math_teacher(query):
    # Explicit owner opt-in: only decimal public numbers go to a local model.
    import re as _re
    if not isinstance(query,str) or len(query)>75:return ''
    match=_re.fullmatch(r'\\s*@(?:учитель|teacher)\\s*:\\s*([0-9]{1,4})\\s*([*x×])\\s*([0-9]{1,4})\\s*\\??\\s*',query,flags=_re.I)
    if not match:return ''
    a,b=int(match.group(1)),int(match.group(3))
    product=a*b
    if any(Path(p).exists() for p in ('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')):
        return ''
    if not _NOX_V113_GATE.acquire(blocking=False):return ''
    try:
        import json as _json
        import urllib.request as _req
        with _req.urlopen('http://127.0.0.1:8084/v1/models',timeout=0.7) as r:
            models=_json.loads(r.read(12000)).get('data') or []
        model_id=str((models[0] or {}).get('id') or '') if len(models)==1 else ''
        if 'vikhr-nemo-12b' not in model_id.lower():return ''
        # Never pass query string, history, S03, identity or tool instructions.
        public_question='Сколько будет '+str(a)+' умножить на '+str(b)+'? Ответь только числом.'
        blob=_json.dumps({'model':model_id,'messages':[{'role':'user','content':public_question}],
                         'temperature':0.0,'max_tokens':42,'stream':False},ensure_ascii=False).encode()
        req=_req.Request('http://127.0.0.1:8084/v1/chat/completions',data=blob,
                         method='POST',headers={'Content-Type':'application/json'})
        with _req.urlopen(req,timeout=2.6) as r:
            raw=r.read(20000)
        result=_json.loads(raw)
        choices=result.get('choices') or []
        answer=str((choices[0].get('message') or {}).get('content') or '') if choices else ''
        if not _re.search(r'(?<!\\d)'+str(product)+r'(?!\\d)',answer):return ''
        if any(Path(p).exists() for p in ('/root/nox/STOP','/root/nox/STOP.flag','/workspace/NOX_STOP')):
            return ''
        return ('Проверенный локальный учитель Vikhr: '+str(a)+'×'+str(b)+'='+str(product)+
                ' (независимо проверено Python). Используй только как справочный результат.')
    except Exception:return ''
    finally:_NOX_V113_GATE.release()
"""
INJECT="""    if _owner and isinstance(_utext,str):
        try:
            import asyncio as _nox_v113_asyncio
            _v113_hint=await _nox_v113_asyncio.wait_for(
                _nox_v113_asyncio.to_thread(_nox_v113_public_math_teacher,_utext),timeout=3.2)
            if (_v113_hint and isinstance(payload.get('messages'),list) and payload['messages']
                    and payload['messages'][0].get('role')=='system'):
                payload['messages'][0]['content']=str(payload['messages'][0].get('content') or '')+'\\n'+_v113_hint
                log_line(LOGS / 'proxy.log','nox_v113_verified_local_teacher_hint_applied=1')
        except Exception:pass
"""
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 if not P.is_file() or P.is_symlink():raise RuntimeError('HOLD_PROXY_NOT_REGULAR')
 old=P.read_bytes();meta=P.stat()
 if sha(old)!=OLD or meta.st_uid!=0 or len(old)>150000:raise RuntimeError('HOLD_SOURCE_SHA_DRIFT')
 if status()!='RUNNING' or health(8080)!=200 or health(8081)!=200 or health(8084)!=200 or not idle():
  raise RuntimeError('HOLD_BUSY_OR_UNHEALTHY')
 source=old.decode('utf8')
 anchor="async def _proxy_completion(body: dict):\n"
 after="    payload['messages'] = _trim_ctx(_build_messages(body))\n"
 if source.count(anchor)!=1 or 'nox_v113_verified_local_teacher' in source:
  raise RuntimeError('HOLD_OWNER_FUNCTION_ANCHOR')
 original_ast=ast.parse(source)
 original_proxy=next(n for n in original_ast.body
                     if isinstance(n,ast.AsyncFunctionDef) and n.name=='_proxy_completion')
 assignments=[]
 for n in ast.walk(original_proxy):
  if not isinstance(n,ast.Assign) or len(n.targets)!=1:continue
  t=n.targets[0]
  if (isinstance(t,ast.Subscript) and isinstance(t.value,ast.Name)
      and t.value.id=='payload' and isinstance(t.slice,ast.Constant)
      and t.slice.value=='messages' and isinstance(n.value,ast.Call)
      and isinstance(n.value.func,ast.Name) and n.value.func.id=='_trim_ctx'):
   assignments.append(n)
 if len(assignments)!=1:
  emit(state='HOLD_AST_PAYLOAD_MESSAGES_ASSIGN',matches=len(assignments))
  raise RuntimeError('HOLD_AST_PAYLOAD_MESSAGES_ASSIGN')
 assign=assignments[0]
 lines=source.splitlines(keepends=True)
 original_line=lines[assign.lineno-1]
 if not original_line.startswith('    ') or original_line.startswith('        '):
  raise RuntimeError('HOLD_AST_INSERT_INDENT')
 lines.insert(assign.end_lineno,INJECT)
 updated=''.join(lines)
 updated=updated.replace(anchor,HELPER+anchor,1)
 compile(updated,str(P),'exec')
 tree=ast.parse(updated)
 proxy=next(x for x in tree.body if isinstance(x,ast.AsyncFunctionDef) and x.name=='_proxy_completion')
 if not any(isinstance(x,ast.Name) and x.id=='_nox_v113_public_math_teacher' for x in ast.walk(proxy)):
  raise RuntimeError('HOLD_TEACHER_HOOK_MISSING')
 if updated.count('_s03_augment(retrieve_text)')!=1 or updated.count('register_native_v29_chat(app, globals())')!=1:
  raise RuntimeError('HOLD_EXISTING_NOX_INTEGRATION_CHANGED')
 new=updated.encode('utf8')
 if len(new)>165000:raise RuntimeError('HOLD_PATCH_TOO_LARGE')
 if stopped() or not idle():raise RuntimeError('HOLD_CHAT_BECAME_BUSY')
 if BACKUP.exists():
  if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=OLD:raise RuntimeError('HOLD_BACKUP_CONFLICT')
 else:
  with BACKUP.open('xb') as f:f.write(old);f.flush();os.fsync(f.fileno())
  os.chmod(BACKUP,stat.S_IMODE(meta.st_mode));os.chown(BACKUP,meta.st_uid,meta.st_gid)
 atomic(new,meta,P.with_name('.nox-v113-stage.tmp'))
 try:
  subprocess.run(['supervisorctl','restart','nox-proxy'],timeout=35,capture_output=True,check=True)
  good=False
  for _ in range(18):
   if status()=='RUNNING' and health(8080)==200 and health(8081)==200 and health(8084)==200:
    good=True;break
   time.sleep(1)
  if not good or sha(P.read_bytes())!=sha(new) or stopped():raise RuntimeError('HOLD_POST_DEPLOY')
  emit(state='NATIVE_OWNER_OPTIN_PUBLIC_MATH_TEACHER_BOUND',new_sha256=sha(new),
       backup_verified=sha(BACKUP.read_bytes())==OLD,
       native_onehost_only=True,existing_s03_unchanged=True,
       owner_cookie_endpoint_preserved=True,
       weights_changed=False,teacher_e2e_http_tested=False,
       private_data_ever_forwarded=False)
 except Exception as ex:
  did=rollback(old,meta)
  emit(state='HOLD_ROLLED_BACK' if did else 'HOLD_ROLLBACK_UNVERIFIED',rollback=did,
       failing_gate=str(ex)[:90] if str(ex).startswith('HOLD_') else type(ex).__name__)
except Exception as ex:
 x=str(ex)
 emit(state=x if x.startswith('HOLD_') and len(x)<80 else 'HOLD_PRECHECK',live_source_changed=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
    ssh.REMOTE=REMOTE;original=ssh.api
    def gate(method,path,key,data=None):
        for i in range(4):
            try:
                v=original(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return v
            except RuntimeError as e:
                if method!='GET' or str(e)!='HOLD_VAST_API_HTTP_429' or i==3:raise
                time.sleep((10,20,40)[i])
    ssh.api=gate
    out=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(out):ok=ssh.probe()
    except Exception as e:
        s=str(e);print('NOX_V113_HOLD='+(s if s.startswith('HOLD_') else 'SSH'))
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if ssh.cleanup() is not True:ok=False
        except Exception:ok=False
    lines=[]
    for x in out.getvalue().splitlines():
        if x.startswith(('NATIVE_V113=','TEMP_SSH_CLEANUP=')):
            lines.append(x);print(x[:2000])
    passed=bool(ok and any('NATIVE_OWNER_OPTIN_PUBLIC_MATH_TEACHER_BOUND' in x for x in lines))
    print('NOX_V113_OWNER_TEACHER_PATCH_ACCEPTED='+str(passed).lower())
    return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
