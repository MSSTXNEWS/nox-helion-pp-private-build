"""NOX V76: exact live owner proxy source hash and safe reload admission."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,hashlib,json,subprocess,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V76_PROXY_CHANGE_ADMISSION_V1')
pid=198698
try:
 args=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
 candidates=[Path(a.decode('utf-8','replace')) for a in args if a.endswith(b'chat_proxy.py')]
 source=next((q for q in candidates if q.is_file()),None)
 if source is None:
  raise RuntimeError()
 blob=source.read_bytes()
 if len(blob)>600_000:raise RuntimeError()
 print('NATIVE_PROXY_SOURCE_META='+json.dumps({'path':str(source),'bytes':len(blob),
    'sha256':hashlib.sha256(blob).hexdigest(),'symlink':source.is_symlink(),
    'owner_uid':source.stat().st_uid},separators=(',',':')))
 marks=(b'_understanding_http(_utext, stream, body)',b'if _und is not None:',
        b'def _build_messages(',b'rag_relevant(user_text)')
 print('NATIVE_PROXY_SOURCE_ANCHORS='+json.dumps([blob.count(s) for s in marks]))
except Exception:
 print('NATIVE_PROXY_SOURCE_META=HOLD_SOURCE_PATH')
try:
 s=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=7)
 print('NATIVE_PROXY_SUPERVISOR='+json.dumps({'state':s.stdout.split()[1] if len(s.stdout.split())>1 else 'UNKNOWN','pid_exact':('pid '+str(pid)+',') in s.stdout},separators=(',',':')))
except Exception:print('NATIVE_PROXY_SUPERVISOR=HOLD')
try:
 with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as r:
  obj=json.loads(r.read(16000))
 slots=obj if isinstance(obj,list) else []
 print('NATIVE_MAIN_MODEL_SLOT_STATUS='+json.dumps({'reported_slots':len(slots),'busy_count':sum(bool(x.get('is_processing',x.get('processing',False))) for x in slots if isinstance(x,dict))},separators=(',',':')))
except Exception:print('NATIVE_MAIN_MODEL_SLOT_STATUS=UNKNOWN')
print('NATIVE_PROXY_NOT_RESTARTED=true')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
 conn.REMOTE=REMOTE;ok=False
 try:ok=conn.probe()
 except Exception as e:
  s=str(e);print('NOX_V76='+s if s.startswith('HOLD_') else 'NOX_V76=HOLD')
 finally:
  try:
   if not conn.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
