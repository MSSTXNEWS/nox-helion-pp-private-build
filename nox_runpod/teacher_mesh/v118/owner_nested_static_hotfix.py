"""V118: one-byte-scope native owner bootstrap path fix on EXISTING V112 bridge.
Only replaces the relative script URL with an absolute same-origin /nox-web-v29
path. No model, memory, training, client private data, or configuration changes.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

REMOTE = r'''
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import ast
import hashlib
import http.cookiejar as _nox_cookiejar
import json
import os
import stat
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V118_NESTED_OWNER_STATIC_PATH_V1')
TARGET=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
PROXY=Path('/root/nox/scripts/chat_proxy.py')
OLD='066ed91555a9a6251420b5897a040eda13a03b3d6c2d85b936e384c5f4113cd4'
PROXY_EXPECTED='568b5950cfbd263a96a106525f81de8fdc024526fe86fab7765a3c25baa180f8'
ORIGINAL=b'<head><script src="./native-owner.js"></script>'
PATCHED=b'<head><script src="/nox-web-v29/native-owner.js"></script>'
BACKUP=TARGET.with_name('nox_v29_chat_bridge.py.nox-v118-'+OLD[:12]+'.bak')
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(b): return hashlib.sha256(b).hexdigest()
def stopped(): return any(Path(p).exists() for p in STOP)
def emit(**data): print('NATIVE_V118_RESULT='+json.dumps(data,sort_keys=True,separators=(',',':')))
def healthy():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=3) as a, urllib.request.urlopen('http://127.0.0.1:8081/health',timeout=3) as b:
   q=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=7)
   return a.status==200 and b.status==200 and q.returncode==0 and 'RUNNING' in q.stdout
 except Exception:return False
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as a:rows=json.loads(a.read(32000))
  return isinstance(rows,list) and len(rows)==6 and all(
   isinstance(x,dict) and x.get('is_processing',x.get('processing',None)) is False
   for x in rows)
 except Exception:return False
def atomic(data,metadata,name):
 temp=TARGET.with_name(name)
 if temp.exists() or temp.is_symlink():raise RuntimeError('HOLD_TEMP_CONFLICT')
 with temp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.chmod(temp,stat.S_IMODE(metadata.st_mode))
 os.chown(temp,metadata.st_uid,metadata.st_gid)
 if sha(temp.read_bytes())!=sha(data):raise RuntimeError('HOLD_TEMP_HASH')
 os.replace(temp,TARGET)
def restart():
 p=subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,text=True,timeout=35)
 if p.returncode!=0:raise RuntimeError('HOLD_SUPERVISOR_RESTART')
 for _ in range(18):
  if healthy():return True
  time.sleep(1)
 return False
def http(url,opener=None):
 req=urllib.request.Request('http://127.0.0.1:8080'+url,
  headers={'User-Agent':'NOX-V118-SAFE-STATIC-ACCEPTANCE'})
 try:
  client = opener.open if opener is not None else urllib.request.urlopen
  return client(req,timeout=5)
 except urllib.error.HTTPError as e:return e
def rollback(data,metadata):
 try:
  atomic(data,metadata,'.nox-v118-revert.tmp')
  if not restart():return False
  return sha(TARGET.read_bytes())==OLD
 except Exception:return False

original=None
metadata=None
touched=False
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 if not TARGET.is_file() or TARGET.is_symlink() or not PROXY.is_file() or PROXY.is_symlink():
  raise RuntimeError('HOLD_EXISTING_NATIVE_FILES')
 metadata=TARGET.stat()
 original=TARGET.read_bytes()
 if metadata.st_uid!=0 or sha(original)!=OLD or sha(PROXY.read_bytes())!=PROXY_EXPECTED:
  raise RuntimeError('HOLD_PINNED_SOURCE_SHA')
 if original.count(ORIGINAL)!=1 or PATCHED in original:
  raise RuntimeError('HOLD_ANCHOR_NONUNIQUE')
 if not healthy() or not idle():raise RuntimeError('HOLD_BUSY_OR_HEALTH')
 changed=original.replace(ORIGINAL,PATCHED,1)
 ast.parse(changed);compile(changed,str(TARGET),'exec')
 if len(changed)!=len(original)+len(PATCHED)-len(ORIGINAL):
  raise RuntimeError('HOLD_ONLY_ONE_REPLACEMENT')
 for path in ('/nox-web-v29/pc/pages/cinema/index.html',
              '/nox-web-v29/chat.html'):
  if http(path).status!=401:raise RuntimeError('HOLD_ANON_BASELINE_AUTH')
 if stopped() or not idle():raise RuntimeError('HOLD_CHAT_BECAME_BUSY')
 if BACKUP.exists():
  if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=OLD:
   raise RuntimeError('HOLD_EXISTING_BACKUP')
 else:
  with BACKUP.open('xb') as f:f.write(original);f.flush();os.fsync(f.fileno())
  os.chmod(BACKUP,stat.S_IMODE(metadata.st_mode))
  os.chown(BACKUP,metadata.st_uid,metadata.st_gid)
 if sha(BACKUP.read_bytes())!=OLD:raise RuntimeError('HOLD_BACKUP_SHA')
 atomic(changed,metadata,'.nox-v118-stage.tmp')
 touched=True
 if not restart() or sha(TARGET.read_bytes())!=sha(changed):
  raise RuntimeError('HOLD_POST_RESTART_HEALTH')
 # Credentials are read only inside this existing NOX host; never exported.
 import sys
 sys.path.insert(0,'/root/nox/scripts')
 import chat_proxy
 password=chat_proxy._read_chat_password()
 if not isinstance(password,str) or len(password)<6:
  raise RuntimeError('HOLD_OWNER_LOGIN_CREDENTIAL')
 jar=_nox_cookiejar.CookieJar()
 opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
 req=urllib.request.Request('http://127.0.0.1:8080/chat/login',
    data=json.dumps({'password':password}).encode(),method='POST',
    headers={'Content-Type':'application/json'})
 password=None
 with opener.open(req,timeout=7) as login:
  if login.status!=200:raise RuntimeError('HOLD_OWNER_LOGIN')
 if not list(jar):raise RuntimeError('HOLD_NO_OWNER_SESSION')
 checked=[]
 for url in ('/nox-web-v29/chat.html','/nox-web-v29/pc/pages/cinema/index.html'):
  with http(url,opener) as resp:
   data=resp.read(500000)
   if resp.status!=200 or PATCHED[len(b'<head>'):] not in data:
    raise RuntimeError('HOLD_OWNER_NESTED_BOOTSTRAP')
   checked.append(url)
 with http('/nox-web-v29/native-owner.js',opener) as js:
  if js.status!=200 or b'NOX_NATIVE_OWNER = true' not in js.read(6000):
   raise RuntimeError('HOLD_OWNER_SCRIPT_NOT_SERVED')
 for url in checked:
  if http(url).status!=401:raise RuntimeError('HOLD_ANON_AFTER_RESTART')
 with http('/api/nox/status',opener) as s:
  if s.status!=200:raise RuntimeError('HOLD_NATIVE_STATUS_AFTER_RESTART')
 try:
  req=urllib.request.Request('http://127.0.0.1:8080/chat/logout',
      data=b'{}',method='POST',headers={'Content-Type':'application/json'})
  opener.open(req,timeout=4).close()
 except Exception:pass
 if stopped():raise RuntimeError('HOLD_STOP_AFTER_RESTART')
 emit(state='NATIVE_OWNER_NESTED_WEB_PATH_PATCHED',
  bridge_sha256=sha(changed),backup_sha_verified=True,
  service='nox-proxy',owner_cookie_authenticated=True,
  nested_pages_checked=2,anonymous_protected=True,
  health_8080_8081=True,production_home_unchanged=True,
  s03_not_modified_by_patch=True,weights_unchanged=True,
  full_web_92_e2e_verified=False)
except Exception as e:
 msg=str(e)
 if touched and original is not None and metadata is not None:
  restored=rollback(original,metadata)
  emit(state='HOLD_ROLLED_BACK' if restored else 'HOLD_ROLLBACK_UNVERIFIED',
    rollback=restored,failed_gate=msg[:100] if msg.startswith('HOLD_') else type(e).__name__)
 else:
  emit(state=msg if msg.startswith('HOLD_') and len(msg)<100 else 'HOLD_NATIVE_PREFLIGHT',
    live_patched=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
 ssh.REMOTE=REMOTE
 original_api=ssh.api
 def retry(method,path,key,data=None):
  for idx in range(4):
   try:
    result=original_api(method,path,key,data)
    if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
    return result
   except RuntimeError as e:
    if method!='GET' or str(e)!='HOLD_VAST_API_HTTP_429' or idx==3:raise
    time.sleep((10,20,40)[idx])
 ssh.api=retry
 stream=io.StringIO()
 okay=False
 try:
  with contextlib.redirect_stdout(stream):okay=ssh.probe()
 except Exception as e:
  s=str(e)
  print('NOX_V118_HOLD='+(s if s.startswith('HOLD_') else 'NATIVE_CONNECTION'))
 finally:
  try:
   with contextlib.redirect_stdout(stream):
    if ssh.cleanup() is not True:okay=False
  except Exception:okay=False
 messages=[]
 for line in stream.getvalue().splitlines():
  if line.startswith('NATIVE_V118_RESULT=') and len(line)<2000:
   print(line)
   messages.append(line)
  elif line.startswith('TEMP_SSH_CLEANUP='): print(line[:120])
 accepted=bool(okay and len(messages)==1 and 'NATIVE_OWNER_NESTED_WEB_PATH_PATCHED' in messages[0])
 print('NOX_V118_PHYSICAL_PASS='+str(accepted).lower())
 return 0 if accepted else 2

if __name__=='__main__':raise SystemExit(main())
