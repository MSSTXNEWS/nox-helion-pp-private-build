"""NOX V82 read-only live inline HTML and streaming route diagnosis, trainer state.

Never emits prompt contents, credentials, log bodies or SQL rows.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
prev=ssh.api
def gate(method,path,key,data=None):
 r=prev(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,re,json,subprocess,hashlib,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V82_INLINE_CLIENT_STREAM_TRAINING_V1')
def emit(k,d):print(k+'='+json.dumps(d,sort_keys=True,separators=(',',':')))
try:
 with urllib.request.urlopen('http://127.0.0.1:8080/chat',timeout=5) as res:
  html=res.read(120000).decode('utf-8','replace')
 scripts=re.findall(r'<script\b[^>]*>(.*?)</script>',html,re.I|re.S)
 code='\n'.join(scripts)
 names=['getReader(','.read()', 'TextDecoder','EventSource(', 'text/event-stream','/chat/api','/v1/chat/completions','JSON.stringify','response.json()', 'response.text()', 'StreamingResponse','setInterval','requestAnimationFrame','textContent','innerHTML','scrollTop','data:','[DONE]','stream:true','stream: true','stream: false','stream:false','_render','typewriter']
 emit('NATIVE_INLINE_STREAM_DIAG',{'html_bytes':len(html.encode()),'inline_script_blocks':len(scripts),'inline_js_bytes':len(code.encode()),'signals':{k:code.count(k) for k in names}})
 # Lines with stream-related operation, but emit ONLY sanitized operation markers and numeric location.
 for idx,line in enumerate(code.splitlines()):
  if any(tag in line for tag in ('getReader(', '.read()', '/chat/api', 'fetch(', 'stream:', 'response.json()', 'response.text()', 'textContent=', 'textContent +=','innerHTML =','JSON.parse(', 'requestAnimationFrame(')):
   if len(line)>1500:continue
   ops=[tag for tag in names if tag in line]
   emit('NATIVE_INLINE_STREAM_OP',{'line':idx+1,'ops':ops,'line_len':len(line)})
except Exception:emit('NATIVE_INLINE_STREAM_DIAG',{'state':'HOLD_NO_INLINE_HTML'})
try:
 out=subprocess.run(['supervisorctl','status'],capture_output=True,text=True,timeout=8)
 states=[]
 for line in out.stdout.splitlines():
  parts=line.split()
  if len(parts)>1 and any(x in parts[0] for x in ('train','tuner','teacher','distill','download')):
   states.append({'service':parts[0][:80],'state':parts[1]})
 emit('NATIVE_TRAIN_STATE_ALL',{'states':states[:45],'supervisorctl_rc':out.returncode})
except Exception:emit('NATIVE_TRAIN_STATE_ALL',{'state':'HOLD'})
# Named config and log status ONLY: don't print any private values
for path in ('/etc/supervisor/conf.d/nox-t866u.conf','/root/nox/training/status.json',
 '/root/nox/training/train_status.json','/root/nox/train_volta/status.json',
 '/root/nox/forge/status.json'):
 p=Path(path)
 if p.is_file() and p.stat().st_size<120000:
  emit('NATIVE_TRAIN_FILE',{'basename':p.name,'under':p.parent.name,'bytes':p.stat().st_size,
        'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=="__main__":
 ssh.REMOTE=REMOTE;ssh.api=gate;ok=False
 try:ok=ssh.probe()
 except Exception as e:
  print('NOX_V82='+str(e) if str(e).startswith('HOLD_') else 'NOX_V82=HOLD_NATIVE')
 finally:
  try:
   if not ssh.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
