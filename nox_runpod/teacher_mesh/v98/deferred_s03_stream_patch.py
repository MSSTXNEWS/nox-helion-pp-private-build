"""V98: one bounded native hotfix for streamed owner answer persistence.
Existing OneHost/S03 only. No second DB, LLM, model downloads or training.
Pinned prior SHA + idle slots + backup SHA + automatic rollback.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

_OLD_API=ssh.api
def _api(method,path,key,data=None):
    for attempt in range(4):
        try:
            result=_OLD_API(method,path,key,data)
            if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
            return result
        except RuntimeError as exc:
            if method!="GET" or str(exc)!="HOLD_VAST_API_HTTP_429" or attempt==3:raise
            time.sleep((10,20,40)[attempt])

REMOTE=r'''
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,os,hashlib,json,stat,subprocess,time,urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V98_DEFERRED_OWNER_STREAM_S03_V1')
FILE=Path('/root/nox/scripts/chat_proxy.py')
EXPECTED='68a559781a46f02ea09eddfab6aa425025938d1c447550d18e54511fa1aed017'
BACKUP=FILE.with_name('chat_proxy.py.nox-v98-backup-'+EXPECTED[:12])
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(x):return hashlib.sha256(x).hexdigest()
def stopped():return any(Path(p).exists() for p in STOP)
def emit(**value):print('NATIVE_V98_RECEIPT='+json.dumps(value,separators=(',',':'),sort_keys=True))
def state():
 try:
  p=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=6)
  x=p.stdout.split();return x[1] if p.returncode==0 and len(x)>1 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def health(port):
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=3) as r:return r.status
 except Exception:return None
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:a=json.loads(r.read(20000))
  return isinstance(a,list) and len(a)==6 and not any(item.get('is_processing',item.get('processing',False)) for item in a if isinstance(item,dict))
 except Exception:return False
def atomic(data,meta,temp):
 if temp.exists() or temp.is_symlink():raise RuntimeError('HOLD_TEMP_EXISTS')
 with temp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.chmod(temp,stat.S_IMODE(meta.st_mode));os.chown(temp,meta.st_uid,meta.st_gid)
 if sha(temp.read_bytes())!=sha(data):raise RuntimeError('HOLD_WRITE_VERIFY')
 os.replace(temp,FILE)
def rollback(original,meta):
 try:
  atomic(original,meta,FILE.with_name('.nox-v98-rollback.tmp'))
  subprocess.run(['supervisorctl','restart','nox-proxy'],timeout=30,capture_output=True,check=True)
  for _ in range(18):
   if state()=='RUNNING' and health(8080)==200 and health(8081)==200:
    return sha(FILE.read_bytes())==EXPECTED
   time.sleep(1)
 except Exception:return False
 return False

PATCH="""            if stream and hasattr(resp, 'body_iterator'):
                _nox_owner_original_stream = resp.body_iterator
                async def _nox_owner_s03_after_stream():
                    _nox_finished_normally = False
                    try:
                        async for _nox_sse_chunk in _nox_owner_original_stream:
                            yield _nox_sse_chunk
                        _nox_finished_normally = True
                    finally:
                        if _nox_finished_normally:
                            _nox_answer = payload.get('_agent_final') or ''
                            if isinstance(_nox_answer, str) and _nox_answer.strip():
                                try:
                                    _s03_persist_pair(_s03_user_from_payload(payload) or _last_user_text(body), _nox_answer)
                                    log_line(LOGS / 'proxy.log', 's03_owner_stream_postflight=attempted')
                                except Exception as _nox_memory_error:
                                    try:
                                        log_line(LOGS / 'proxy.log', f's03_owner_stream_postflight_error {type(_nox_memory_error).__name__}')
                                    except Exception:
                                        pass
                resp.body_iterator = _nox_owner_s03_after_stream()
"""
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 if not FILE.is_file() or FILE.is_symlink():raise RuntimeError('HOLD_NATIVE_SOURCE')
 meta=FILE.stat();original=FILE.read_bytes()
 if meta.st_uid!=0 or len(original)>150000 or sha(original)!=EXPECTED:raise RuntimeError('HOLD_UNEXPECTED_SOURCE_SHA')
 if state()!='RUNNING' or health(8080)!=200 or health(8081)!=200 or not idle():raise RuntimeError('HOLD_ACTIVE_OR_UNHEALTHY_CHAT')
 source=original.decode('utf8')
 anchor="            resp = await owner_completion(url, payload, _last_user_text(body), stream)\n            resp = _wrap_ttft(resp, t_gate, _utext)\n"
 # The current native owner answer expression varies; do not rewrite it.
 # V99 physically confirmed exactly one owner+wrap anchor and no existing hook.
 if source.count(anchor)!=1 or '_nox_owner_s03_after_stream' in source:
  raise RuntimeError('HOLD_OWNER_S03_ANCHOR_A'+str(source.count(anchor)))
 # Preserve nonstream (synchronous) S03 persistence. Streaming response receives
 # final text only after body_iterator is fully consumed, not at response creation.
 updated=source.replace(anchor,anchor+PATCH,1)
 tree=ast.parse(updated);compile(updated,str(FILE),'exec')
 proxy=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='_proxy_completion')
 if sum(1 for x in ast.walk(proxy) if isinstance(x,ast.AsyncFunctionDef) and x.name=='_nox_owner_s03_after_stream')!=1:
  raise RuntimeError('HOLD_AST_PATCH_MISSING')
 if updated.count('_s03_augment(retrieve_text)')!=1 or updated.count('NOX_MEM.extra_context(')!=1:
  raise RuntimeError('HOLD_MANDATORY_MEMORY_CHANGED')
 new=updated.encode('utf8')
 if len(new)>155000:raise RuntimeError('HOLD_PATCH_TOO_LARGE')
 if not idle() or stopped():raise RuntimeError('HOLD_CHAT_BECAME_BUSY')
 if BACKUP.exists():
  if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=EXPECTED:raise RuntimeError('HOLD_BACKUP_CONFLICT')
 else:
  with BACKUP.open('xb') as f:f.write(original);f.flush();os.fsync(f.fileno())
  os.chmod(BACKUP,stat.S_IMODE(meta.st_mode));os.chown(BACKUP,meta.st_uid,meta.st_gid)
 if sha(BACKUP.read_bytes())!=EXPECTED:raise RuntimeError('HOLD_BACKUP_SHA')
 atomic(new,meta,FILE.with_name('.nox-v98-patch.tmp'))
 try:
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=30,check=True)
  accepted=False
  for _ in range(18):
   if state()=='RUNNING' and health(8080)==200 and health(8081)==200:
    accepted=True;break
   time.sleep(1)
  if not accepted or sha(FILE.read_bytes())!=sha(new) or stopped():raise RuntimeError('HOLD_POSTFLIGHT')
  emit(state='NATIVE_DEFERRED_OWNER_STREAM_S03_SOURCE_INSTALLED',source_sha256=sha(new),
       backup_sha_verified=True,chat_health=200,model_health=200,no_second_backend=True,
       weights_changed=False,s03_readback_verified=False,
       stream_e2e_verified=False,training_started=False,rollback_source_sha256=EXPECTED)
 except Exception:
  restored=rollback(original,meta)
  emit(state='HOLD_ROLLED_BACK' if restored else 'HOLD_ROLLBACK_UNVERIFIED',rollback=restored)
except Exception as exc:
 x=str(exc)
 emit(state=x if x.startswith('HOLD_') and len(x)<100 else 'HOLD_NATIVE_GATES',
      source_changed=False,weights_changed=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''

def main():
    ssh.api=_api
    ssh.REMOTE=REMOTE
    out=io.StringIO()
    ok=False
    try:
        with contextlib.redirect_stdout(out):ok=ssh.probe()
    except Exception as exc:
        x=str(exc)
        print("NOX_V98_HOLD="+(x if x.startswith("HOLD_") and len(x)<100 else "REMOTE"))
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if ssh.cleanup() is not True:ok=False
        except Exception:ok=False
    receipts=[]
    for line in out.getvalue().splitlines():
        if line.startswith("NATIVE_V98_RECEIPT="):
            receipts.append(line)
            print(line[:1800])
        elif line.startswith("TEMP_SSH_CLEANUP="):print(line[:100])
    accepted=bool(ok and len(receipts)==1 and '"state":"NATIVE_DEFERRED_OWNER_STREAM_S03_SOURCE_INSTALLED"' in receipts[0])
    print("NOX_V98_NATIVE_SOURCE_ACCEPTED="+str(accepted).lower())
    return 0 if accepted else 2
if __name__=="__main__":raise SystemExit(main())
