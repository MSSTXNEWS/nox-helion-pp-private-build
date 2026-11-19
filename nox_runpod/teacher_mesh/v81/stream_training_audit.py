"""Native read-only diagnosis: live chat streaming path and Volta optimizer-step evidence.
Never expose prompt values, paths to secrets, tokens or private logs.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
old=ssh.api
def delay(method,path,key,data=None):
 r=old(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return r

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,re,json,hashlib,subprocess,urllib.request,urllib.error,ast
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V81_STREAM_TRAIN_READONLY_V1')
def emit(key,obj):
 print(key+'='+json.dumps(obj,sort_keys=True,separators=(',',':')))
def cmd(cmd):
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=8)
  return p.stdout if p.returncode==0 else ''
 except Exception:return ''
def status(name):
 s=cmd(['supervisorctl','status',name])
 f=s.split()
 return {'service':name,'state':f[1] if len(f)>1 else 'UNKNOWN',
         'pid':int(f[3].rstrip(',')) if len(f)>3 and f[2]=='pid' and f[3].rstrip(',').isdigit() else None}
for name in ('nox-proxy','nox-chat-8081','nox-train-volta-t866u','nox-priority-scheduler','nox-cores','nox-embed','nox-teacher-serve-t811u'):
 emit('NATIVE_SERVICE_READBACK',status(name))
# Identify live HTML route; only emit safe script names and HTTP headers, no content.
for path in ('/chat','/'):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=3) as r:
   raw=r.read(150000)
   emit('NATIVE_LIVE_HTML',{'path':path,'status':r.status,'sha256':hashlib.sha256(raw).hexdigest(),
      'bytes_sampled':len(raw),'javascript_names':sorted(set(re.findall(r'(?:src|href)=["\'][^"\']*?([A-Za-z0-9_.-]+\.(?:js|mjs))',raw.decode('utf8','replace'))))[:20]})
 except urllib.error.HTTPError as e:
  emit('NATIVE_LIVE_HTML',{'path':path,'status':e.code})
 except Exception:emit('NATIVE_LIVE_HTML',{'path':path,'status':'HOLD'})
# Search only installed actual frontend, avoid recording page contents or any private messages.
pathlist=['/root/nox/scripts/chat_proxy.py','/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/nox-chat.js']
for rawpath in pathlist:
 p=Path(rawpath)
 if not p.is_file() or p.stat().st_size>800000:continue
 txt=p.read_text(errors='replace')
 emit('NATIVE_CODE_STREAM_INDICATORS',{'basename':p.name,
  'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
  'reader':txt.count('getReader('),'streaming_response':txt.count('StreamingResponse('),
  'stream_true':txt.count("'stream': True")+txt.count("'stream':True")+txt.count('"stream":true'),
  'stream_false':txt.count("'stream': False")+txt.count("'stream':False"),
  'response_content':txt.count('output.textContent=result'),
  'sse':txt.count('text/event-stream'),'buffered':txt.count('NATIVE_BUFFERED'),
  'routes_nox_stream':txt.count('/api/nox/chat/stream'),
  'routes_chat_api':txt.count('/chat/api'),
  'owner_completion':txt.count('owner_completion(')})
# Training data: selected JSON status files only, never raw logs or paths with secrets.
for name in ('nox-train-volta-t866u','nox-train-worm-t811u','nox-distill-worm-t811u'):
 emit('NATIVE_TRAIN_SUPERVISOR',status(name))
p=status('nox-train-volta-t866u')['pid']
if p:
 try:
  args=(Path('/proc')/str(p)/'cmdline').read_bytes().split(b'\0')
  scripts=[Path(v.decode('utf8','replace')).name for v in args if v.endswith(('.py','.sh'))]
  emit('NATIVE_TRAIN_PROCESS',{'pid':p,'script_basenames':scripts[:5]})
 except Exception:pass
# Last progress from machine-readable files: no private content, no user data.
for root in ('/root/nox','/workspace/nox'):
 base=Path(root)
 if not base.is_dir():continue
 paths=[]
 for name in ('train_status.json','training_status.json','progress.json','trainer_state.json'):
  for sub in ('','training','forge','status','logs','train_volta'):
   f=base/sub/name
   if f.is_file() and not f.is_symlink() and f.stat().st_size<100000:paths.append(f)
 for f in paths[:15]:
  try:
   d=json.loads(f.read_text())
   if not isinstance(d,dict):continue
   keys=('phase','status','global_step','step','loss','train_loss','max_steps','total_steps','last_update','updated_at','method','smoke')
   values={k:d[k] for k in keys if k in d and isinstance(d[k],(str,int,float,bool,type(None)))}
   emit('NATIVE_TRAIN_JSON_META',{'path_label':str(f.relative_to(base)),
       'root':'root_nox' if root=='/root/nox' else 'workspace_nox','fields':values})
  except Exception:pass
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

if __name__=='__main__':
 ssh.REMOTE=REMOTE;ssh.api=delay;ok=False
 try:ok=ssh.probe()
 except Exception as e:
  v=str(e);print('NOX_V81='+v if v.startswith('HOLD_') else 'NOX_V81=HOLD_NATIVE')
 finally:
  try:
   if not ssh.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
