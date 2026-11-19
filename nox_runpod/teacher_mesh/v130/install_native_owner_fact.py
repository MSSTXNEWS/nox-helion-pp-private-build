"""V130: one SHA-pinned native install of owner-confirmed M2 S03 fact POST.

Existing OneHost only, original S03 and owner cookie, no new service/database.
Atomic preimage backups + reversible proxy/bridge patch and real HTTP/SQLite E2E.
"""
from __future__ import annotations
import ast,base64,contextlib,hashlib,io,time
from pathlib import Path
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

MODULE=Path('nox_runpod/teacher_mesh/v130/owner_s03_fact_write.py')
BRIDGE_SHA='2c714c7f952be64a2b278c993da9d59014a43a32075281b5aa755ada02c6fb8e'
PROXY_SHA='e79aa0747511cf010f79f72150fc4e64b36b9c9ccea3b09d788a6306c63c0c95'
S03_SOURCE_SHA='82c592ea5a59281fb5fc1061d133ac4e149b8e95a6d0947a254882715cba7f91'
ANCHOR='    directory=Path(site_dir) if site_dir is not None else SITE\n'
SNIPPET=("    from nox_v130_owner_s03_fact_write import register_nox_v130_owner_fact_write\n"
         "    register_nox_v130_owner_fact_write(app,trusted)\n")
PROXY_OLD_GUARD="if (request.url.path.startswith(('/api/ui/', '/nox-web-v29/')) or request.url.path in ('/api/health','/api/nox/activity','/api/nox/model','/api/nox/memory','/api/nox/history','/api/nox/experience','/api/training/status','/api/status','/api/nox/system/processes','/api/nox/premium/status','/api/nox/premium/capabilities','/api/nox/training/status')) and _session_ok(request):"
PROXY_NEW_GUARD=PROXY_OLD_GUARD.replace(
    "'/api/nox/training/status'", "'/api/nox/training/status','/api/nox/memory/facts'")
assert PROXY_NEW_GUARD!=PROXY_OLD_GUARD

REMOTE_TEMPLATE=r'''
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import ast,base64,hashlib,http.cookiejar as cookiejar,json,os,secrets,sqlite3,stat,subprocess,time,urllib.error,urllib.request
from datetime import datetime,timezone
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V130_AUTH_OWNER_NATIVE_S03_FACT_PATCH_V1')
P=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
PX=Path('/root/nox/scripts/chat_proxy.py')
M=Path('/root/nox/scripts/nox_v130_owner_s03_fact_write.py')
S03=Path('/root/nox/scripts/s03_memory.py')
OLD_BRIDGE='___OLD_BRIDGE___'
OLD_PROXY='___OLD_PROXY___'
OLD_S03='___OLD_S03___'
NEW_MODULE=base64.b64decode('___MODULE_B64___',validate=True)
MODULE_SHA='___MODULE_SHA___'
ANCHOR=base64.b64decode('___ANCHOR_B64___').decode('utf8')
SNIPPET=base64.b64decode('___SNIPPET_B64___').decode('utf8')
GUARD_BEFORE=base64.b64decode('___GUARD_BEFORE_B64___').decode('utf8')
GUARD_AFTER=base64.b64decode('___GUARD_AFTER_B64___').decode('utf8')
BACK=P.with_name(P.name+'.nox-v130-'+OLD_BRIDGE[:12]+'.bak')
PXBACK=PX.with_name(PX.name+'.nox-v130-'+OLD_PROXY[:12]+'.bak')
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def digest(data):return hashlib.sha256(data).hexdigest()
def sha(path):return digest(path.read_bytes()) if path.is_file() and not path.is_symlink() else None
def stop():return any(Path(name).exists() for name in STOPS)
def health(port):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as r:return r.status==200
 except Exception:return False
def supervisor():
 try:
  r=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=5)
  words=r.stdout.split()
  return words[1] if r.returncode==0 and len(words)>1 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as r:rows=json.loads(r.read(25000))
  return isinstance(rows,list) and len(rows)==6 and all(
   isinstance(row,dict) and row.get('is_processing',row.get('processing',None)) is False for row in rows)
 except Exception:return False
def s03_ok():
 try:
  import s03_memory
  db=Path(s03_memory.DB)
  if not db.is_file() or db.is_symlink():return False
  with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=3) as con:
   con.execute('PRAGMA query_only=ON')
   return con.execute('PRAGMA quick_check').fetchone()[0]=='ok'
 except Exception:return False
def atomic(path,raw,meta,tmpname):
 temp=path.with_name(tmpname)
 if temp.exists() or temp.is_symlink():raise RuntimeError('HOLD_V130_TEMP_COLLISION')
 with temp.open('xb') as w:w.write(raw);w.flush();os.fsync(w.fileno())
 os.chmod(temp,stat.S_IMODE(meta.st_mode));os.chown(temp,meta.st_uid,meta.st_gid)
 if sha(temp)!=digest(raw):raise RuntimeError('HOLD_V130_ATOMIC_SHA')
 os.replace(temp,path)
def restart():
 try:r=subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=18)
 except Exception:return False
 if r.returncode!=0:return False
 for _ in range(22):
  if supervisor()=='RUNNING' and health(8080) and health(8081):return True
  time.sleep(.5)
 return False
def response(op,path,method='GET',data=None):
 req=urllib.request.Request('http://127.0.0.1:8080'+path,
  data=None if data is None else json.dumps(data).encode('utf8'),
  method=method,headers={'Content-Type':'application/json'})
 try:return op.open(req,timeout=7)
 except urllib.error.HTTPError as e:return e
def owner_acceptance():
 from chat_proxy import _read_chat_password
 secret=_read_chat_password()
 if not isinstance(secret,str) or len(secret)<6:raise RuntimeError('HOLD_V130_OWNER_SECRET')
 jar=cookiejar.CookieJar()
 owner=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
 with response(owner,'/chat/login','POST',{'password':secret}) as auth:
  if auth.status!=200:raise RuntimeError('HOLD_V130_OWNER_LOGIN')
 secret=None
 with response(owner,'/chat/session') as session:
  if session.status!=200 or json.loads(session.read(2000)).get('ok') is not True:
   raise RuntimeError('HOLD_V130_OWNER_SESSION')
 anonymous=urllib.request.build_opener()
 with response(anonymous,'/api/nox/memory/facts','POST',{'content':'NOX-QA'}) as denied:
  if denied.status!=401:raise RuntimeError('HOLD_V130_OWNER_ONLY')
 marker='NOX_V130_QA_'+secrets.token_hex(7)
 content='NOX V130 synthetic QA original S03 memory '+marker
 evidence={'fact_key':'OWNER-'+marker,'content':content,
  'source_ref':'OWNER-QA-V130','valid_from':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
  'source_sha256':digest(content.encode('utf8'))}
 try:
  if stop():raise RuntimeError('HOLD_V130_STOP_REVOKED')
  with response(owner,'/api/nox/memory/facts','POST',evidence) as proof:
   if proof.status!=200:raise RuntimeError('HOLD_V130_WRITE_HTTP_'+str(proof.status))
   body=json.loads(proof.read(3500))
  if (body.get('status')!='READY' or body.get('committed') is not True
      or body.get('readback_verified') is not True or body.get('duplicate') is not False
      or not isinstance(body.get('event_id'),str) or len(body['event_id'])<6
      or body.get('source_sha256')!=evidence['source_sha256']):
   raise RuntimeError('HOLD_V130_WRITE_RECEIPT')
  with response(owner,'/api/nox/memory/facts','POST',evidence) as again:
   second=json.loads(again.read(3500)) if again.status==200 else {}
  if second.get('duplicate') is not True or second.get('event_id')!=body['event_id']:
   raise RuntimeError('HOLD_V130_IDEMPOTENT_REPLAY')
  with response(owner,'/api/nox/experience?q='+marker) as history:
   data=json.loads(history.read(35000)) if history.status==200 else {}
  rows=data.get('results')
  if not isinstance(rows,list) or not any(
    r.get('content')==content and r.get('source_sha256')==evidence['source_sha256'] for r in rows if isinstance(r,dict)):
   raise RuntimeError('HOLD_V130_EXISTING_S03_READ_VIEW')
  with response(owner,'/api/nox/status') as status:
   if status.status!=200:raise RuntimeError('HOLD_V130_CHAT_STATUS')
  return {'event_id_sha256':digest(body['event_id'].encode('utf8')),
          'real_s03_note_readback':True,'idempotent':True,'anon_401':True}
 finally:
  try:
   with response(owner,'/chat/logout','POST',{}):pass
  except Exception:pass
def emit(**obj):print('NATIVE_V130_RESULT='+json.dumps(obj,sort_keys=True,separators=(',',':')))
patch_bridge=False;patch_proxy=False;previous=None;pxprevious=None;meta=None;pxmeta=None
try:
 if stop():raise RuntimeError('HOLD_STOP')
 if os.getuid()!=0 or sha(P)!=OLD_BRIDGE or sha(PX)!=OLD_PROXY or sha(S03)!=OLD_S03:
  raise RuntimeError('HOLD_V130_CONCURRENT_SHA_DRIFT')
 if not 3000<len(NEW_MODULE)<16000 or digest(NEW_MODULE)!=MODULE_SHA:
  raise RuntimeError('HOLD_V130_MODULE_SHA')
 compile(NEW_MODULE,str(M),'exec')
 tree=ast.parse(NEW_MODULE)
 if not any(isinstance(n,ast.FunctionDef) and n.name=='register_nox_v130_owner_fact_write' for n in tree.body):
  raise RuntimeError('HOLD_V130_SOURCE_CONTRACT')
 if supervisor()!='RUNNING' or not health(8080) or not health(8081) or not s03_ok() or not idle():
  raise RuntimeError('HOLD_V130_IDLE_HEALTH')
 statv=os.statvfs('/root/nox')
 if statv.f_bavail*statv.f_frsize<512*1024*1024:raise RuntimeError('HOLD_V130_DISK_HEADROOM')
 previous=P.read_bytes();meta=P.stat();bridge=previous.decode('utf8')
 pxprevious=PX.read_bytes();pxmeta=PX.stat();proxy=pxprevious.decode('utf8')
 if (meta.st_uid!=0 or pxmeta.st_uid!=0 or len(bridge)>180000 or len(proxy)>200000 or
     bridge.count(ANCHOR)!=1 or 'register_nox_v130_owner_fact_write(' in bridge or
     proxy.count(GUARD_BEFORE)!=1 or '/api/nox/memory/facts' in proxy):
  raise RuntimeError('HOLD_V130_SOURCE_ANCHORS')
 changed_bridge=bridge.replace(ANCHOR,SNIPPET+ANCHOR,1).encode('utf8')
 changed_proxy=proxy.replace(GUARD_BEFORE,GUARD_AFTER,1).encode('utf8')
 compile(changed_bridge,str(P),'exec');compile(changed_proxy,str(PX),'exec')
 if M.exists():
  if sha(M)!=MODULE_SHA:raise RuntimeError('HOLD_V130_EXISTING_MODULE_DRIFT')
 else:
  atomic(M,NEW_MODULE,meta,'.nox-v130-module.tmp')
 with Path(M).open('rb') as f:
  if digest(f.read())!=MODULE_SHA:raise RuntimeError('HOLD_V130_MODULE_STAGE')
 test=subprocess.run(['/root/nox/venv/bin/python','-c',
  'from nox_v130_owner_s03_fact_write import register_nox_v130_owner_fact_write; assert callable(register_nox_v130_owner_fact_write)'],
  cwd='/root/nox/scripts',capture_output=True,timeout=10)
 if test.returncode!=0:raise RuntimeError('HOLD_V130_NATIVE_IMPORT')
 if stop() or not idle() or sha(P)!=OLD_BRIDGE or sha(PX)!=OLD_PROXY:
  raise RuntimeError('HOLD_V130_BUSY_OR_CONCURRENT')
 for dst,src,st,original_sha in ((BACK,previous,meta,OLD_BRIDGE),(PXBACK,pxprevious,pxmeta,OLD_PROXY)):
  if dst.exists():
   if dst.is_symlink() or sha(dst)!=original_sha:raise RuntimeError('HOLD_V130_BACKUP_CONFLICT')
  else:
   with dst.open('xb') as file:file.write(src);file.flush();os.fsync(file.fileno())
   os.chmod(dst,stat.S_IMODE(st.st_mode));os.chown(dst,st.st_uid,st.st_gid)
  if sha(dst)!=original_sha:raise RuntimeError('HOLD_V130_BACKUP_SHA')
 if stop() or not idle() or sha(P)!=OLD_BRIDGE or sha(PX)!=OLD_PROXY:
  raise RuntimeError('HOLD_V130_BEFORE_WRITE_CHANGED')
 atomic(PX,changed_proxy,pxmeta,'.nox-v130-proxy.tmp');patch_proxy=True
 atomic(P,changed_bridge,meta,'.nox-v130-bridge.tmp');patch_bridge=True
 if not restart() or sha(P)!=digest(changed_bridge) or sha(PX)!=digest(changed_proxy) or not s03_ok():
  raise RuntimeError('HOLD_V130_POST_RESTART')
 proof=owner_acceptance()
 if not s03_ok() or stop():raise RuntimeError('HOLD_V130_POST_NOTE_S03')
 emit(state='V130_NATIVE_S03_OWNER_FACT_PERSISTED',
      owner_http200=True,anonymous_http401=proof['anon_401'],
      native_remember_and_s03_readback=proof['real_s03_note_readback'],
      idempotent_second_post=proof['idempotent'],
      owner_note_id_sha256=proof['event_id_sha256'],
      bridge_sha256=sha(P),proxy_sha256=sha(PX),module_sha256=MODULE_SHA,
      backup_sha_verified=True,s03_quick_check=True,weights_changed=False,
      model_restarted=False,proxy_restarted=True)
except Exception as exc:
 msg=str(exc)
 reason=msg if msg.startswith('HOLD_') and len(msg)<110 else 'HOLD_V130_'+type(exc).__name__
 if patch_bridge or patch_proxy:
  try:
   if patch_bridge:atomic(P,previous,meta,'.nox-v130-bridge-rollback.tmp')
   if patch_proxy:atomic(PX,pxprevious,pxmeta,'.nox-v130-proxy-rollback.tmp')
   reverted=restart() and sha(P)==OLD_BRIDGE and sha(PX)==OLD_PROXY and s03_ok()
  except Exception:reverted=False
  emit(state='HOLD_ROLLED_BACK' if reverted else 'HOLD_ROLLBACK_UNVERIFIED',
       reason=reason,rollback_verified=reverted,
       synthetic_qa_record_may_remain=True,weights_changed=False)
 else:
  emit(state=reason,live_code_changed=False,weights_changed=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''

def main():
    raw=MODULE.read_bytes()
    if not 3000<len(raw)<16000:raise RuntimeError('HOLD_V130_LOCAL_MODULE_SIZE')
    compile(raw,str(MODULE),'exec')
    ssh.REMOTE=REMOTE_TEMPLATE
    substitutions={
      '___OLD_BRIDGE___':BRIDGE_SHA,'___OLD_PROXY___':PROXY_SHA,
      '___OLD_S03___':S03_SOURCE_SHA,
      '___MODULE_SHA___':hashlib.sha256(raw).hexdigest(),
      '___MODULE_B64___':base64.b64encode(raw).decode('ascii'),
      '___ANCHOR_B64___':base64.b64encode(ANCHOR.encode()).decode('ascii'),
      '___SNIPPET_B64___':base64.b64encode(SNIPPET.encode()).decode('ascii'),
      '___GUARD_BEFORE_B64___':base64.b64encode(PROXY_OLD_GUARD.encode()).decode('ascii'),
      '___GUARD_AFTER_B64___':base64.b64encode(PROXY_NEW_GUARD.encode()).decode('ascii')}
    for before,after in substitutions.items():
        if ssh.REMOTE.count(before)!=1:raise RuntimeError('HOLD_V130_REMOTE_TEMPLATE_DRIFT')
        ssh.REMOTE=ssh.REMOTE.replace(before,after,1)
    original=ssh.api
    def safe(method,path,key,data=None):
        for i in range(4):
            try:
                out=original(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return out
            except RuntimeError as ex:
                if method!='GET' or str(ex)!='HOLD_VAST_API_HTTP_429' or i==3:raise
                time.sleep((10,20,40)[i])
    ssh.api=safe
    output=io.StringIO();connected=False;clean=False
    try:
        with contextlib.redirect_stdout(output):connected=ssh.probe()
    except Exception as exc:
        msg=str(exc)
        print('NOX_V130_TRANSPORT_HOLD='+(msg if msg.startswith('HOLD_') and len(msg)<90 else 'HOLD_NATIVE_SSH'))
    finally:
        try:
            with contextlib.redirect_stdout(output):clean=ssh.cleanup()
        except Exception:clean=False
    lines=output.getvalue().splitlines()
    proofs=[x for x in lines if x.startswith('NATIVE_V130_RESULT=')]
    for line in lines:
        if line.startswith(('NATIVE_V130_RESULT=','TEMP_SSH_CLEANUP=')) and len(line)<800:
            print(line)
    try:payload=json.loads(proofs[0].split('=',1)[1]) if len(proofs)==1 else {}
    except (ValueError,TypeError):payload={}
    ok=bool(connected and clean and payload.get('state')=='V130_NATIVE_S03_OWNER_FACT_PERSISTED'
       and 'NATIVE_READ_ONLY_COMPLETE=true' in lines)
    print('NOX_V130_NATIVE_S03_OWNER_FACT_ACCEPTED='+str(ok).lower())
    return 0 if ok else 2

if __name__=='__main__':raise SystemExit(main())
