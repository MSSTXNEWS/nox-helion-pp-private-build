"""Native audit of immutable live chat HTML and exact streaming patch anchors."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
prev=ssh.api
def safe(method,path,key,data=None):
 r=prev(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import re,os,hashlib,json,urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V84_EXACT_STATIC_CHAT_SOURCE_V1')
with urllib.request.urlopen('http://127.0.0.1:8080/chat',timeout=5) as r:
 live=r.read(150000)
sha=hashlib.sha256(live).hexdigest()
print('NATIVE_LIVE_HTML_SHA256='+sha)
root=Path('/root/nox')
found=[]
files_seen=0
for parent,dirs,files in os.walk(root,followlinks=False):
 depth=len(Path(parent).relative_to(root).parts)
 dirs[:]=[d for d in dirs if not (Path(parent)/d).is_symlink()] if depth<5 else []
 for file in files:
  if not file.endswith(('.html','.htm','.txt')):continue
  p=Path(parent)/file
  try:
   st=p.lstat()
   if p.is_symlink() or st.st_size!=len(live):continue
   files_seen+=1
   if hashlib.sha256(p.read_bytes()).hexdigest()==sha:
    found.append(str(p))
  except OSError:pass
 if len(found)>5:break
print('NATIVE_LIVE_HTML_SOURCE_MATCH='+json.dumps(found[:5],separators=(',',':')))
txt=live.decode('utf8','replace')
blocks=re.findall(r'<script\b[^>]*>(.*?)</script>',txt,re.I|re.S)
js='\n'.join(blocks)
for i,line in enumerate(js.splitlines()):
 if 412 <= i+1 <= 467:
  # Static script content only. No cookie or network response bodies.
  print('NATIVE_STREAM_JS_'+str(i+1)+'='+line[:400].replace('\x1b',''))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
 ssh.REMOTE=REMOTE;ssh.api=safe;ok=False
 try:ok=ssh.probe()
 except Exception as e:
  x=str(e);print('NOX_V84='+x if x.startswith('HOLD_') else 'NOX_V84=HOLD_SSH')
 finally:
  try:
   if not ssh.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
