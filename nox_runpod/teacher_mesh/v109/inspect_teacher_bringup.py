"""NOX V109: inspect safety gates of existing teacher launcher without execution."""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,re,json,hashlib,stat,subprocess
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V109_ONDEMAND_LOCAL_TEACHER_GATE_V1')
def emit(label,rec):
 x=json.dumps(rec,sort_keys=True,separators=(',',':'))
 if len(x)<1200:print('NATIVE_V109_'+label+'='+x)
script=Path('/root/nox/scripts/teacher_serve_t811u.sh')
try:
 raw=script.read_text(encoding='utf8',errors='replace')
 emit('LAUNCHER',{'basename':script.name,'sha256':hashlib.sha256(raw.encode()).hexdigest(),
   'lines':len(raw.splitlines()),'has_stop':bool(re.search('STOP|stop.flag',raw,re.I)),
   'uses_gpu_scheduler':bool(re.search('nvidia-smi|GPU|VRAM',raw,re.I)),
   'uses_llama_server':'llama-server' in raw,'available_mode_flags':sorted(set(re.findall(r'(?:TEACHER|T811U|NOX)_[A-Z0-9_]{3,}',raw)))[:20]})
 for i,line in enumerate(raw.splitlines(),1):
  if re.search(r'(--port|PORT_|=81[0-9][0-9]|llama-server|OFFLOAD|ENABLE|PRELOAD|GATED|TEACHER.*STOP)',line,re.I):
   # Never echo any line source: only parsed booleans/port numbers and relevant flags.
   ports=sorted(set(int(x) for x in re.findall(r'(?<!\d)8[0-9]{3}(?!\d)',line)))[:10]
   flags=sorted(set(re.findall(r'(?:TEACHER|T811U|NOX)_[A-Z0-9_]{3,}',line)))[:12]
   emit('CODE_INDEX',{'line':i,'mentions_port':ports,'flags':flags,
      'mentions_server':'llama-server' in line,'mentions_stop':bool(re.search('STOP|stop.flag',line,re.I))})
except Exception as e:emit('LAUNCHER',{'state':'HOLD_READ','error_type':type(e).__name__})
base=Path('/root/nox/models')
known=['nox36-mix_final_pref-Q4_K_M.gguf',
'NousResearch_DeepHermes-3-Llama-3-8B-Preview-Q4_K_M.gguf',
'Hermes-3-Llama-3.1-8B.Q4_K_M.gguf',
'Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf',
'Dolphin3.0-Llama3.1-8B-Q4_K_M.gguf']
for name in known:
 files=[]
 for root,dirs,items in os.walk(base,followlinks=False):
  depth=len(Path(root).relative_to(base).parts)
  dirs[:]=[x for x in dirs if depth<4 and not (Path(root)/x).is_symlink()][:50]
  if name in items:
   p=Path(root)/name
   try:
    st=p.stat()
    if stat.S_ISREG(st.st_mode):files.append({'basename':name,'bytes':st.st_size})
   except OSError:pass
 emit('MODEL_FILE',{'basename':name,'present_count':len(files),'size_bytes':files[0]['bytes'] if len(files)==1 else None})
print('NATIVE_V109_NO_MODEL_LOADED=true')
print('NATIVE_V109_NO_PRIVATE_REQUESTS=true')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 out=io.StringIO();ok=False;ssh.REMOTE=REMOTE
 orig=ssh.api
 def gate(method,path,key,data=None):
  for i in range(4):
   try:
    r=orig(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r
   except RuntimeError as e:
    if method!="GET" or str(e)!="HOLD_VAST_API_HTTP_429" or i==3:raise
    time.sleep((10,20,40)[i])
 ssh.api=gate
 try:
  with contextlib.redirect_stdout(out):ok=ssh.probe()
 except Exception as e:
  x=str(e);print('NOX_V109_HOLD='+(x if x.startswith('HOLD_') and len(x)<90 else 'NATIVE_TRANSPORT'))
 finally:
  try:
   with contextlib.redirect_stdout(out):
    if ssh.cleanup() is not True:ok=False
  except Exception:ok=False
 rows=[]
 for line in out.getvalue().splitlines():
  if line.startswith(("NATIVE_V109_","TEMP_SSH_CLEANUP=")):
   print(line[:1200]);rows.append(line)
 passed=bool(ok and any(x.startswith('NATIVE_V109_LAUNCHER=') for x in rows) and
             sum(x.startswith('NATIVE_V109_MODEL_FILE=') for x in rows)==5 and
             'NATIVE_READ_ONLY_COMPLETE=true' in out.getvalue())
 print('NOX_V109_NATIVE_TEACHER_GATE_INSPECTED='+str(passed).lower())
 return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
