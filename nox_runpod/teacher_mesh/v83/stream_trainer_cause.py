"""NOX V83 read-only diagnostic of browser stream display and Volta EXITED classification."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
_old=ssh.api
def delay(method,path,key,data=None):
  value=_old(method,path,key,data)
  if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
  return value
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import re,json,urllib.request,subprocess,configparser,os,hashlib
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V83_STREAM_TRAIN_ROOTCAUSE_V1')
def output(k,v):print(k+'='+json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')))
try:
 with urllib.request.urlopen('http://127.0.0.1:8080/chat',timeout=4) as r:
  html=r.read(110000).decode('utf8','replace')
 body='\n'.join(re.findall(r'<script\b[^>]*>(.*?)</script>',html,re.I|re.S))
 lines=body.splitlines()
 # Output only individual source lines with string literals and HTTP endpoints redacted.
 for i in range(406,min(520,len(lines))):
  s=lines[i]
  if len(s)>950:continue
  if not any(v in s for v in ('fetch(','.read()','getReader(', 'TextDecoder','stream:', 'requestAnimationFrame(', 'append', 'data:', 'JSON.parse','delta','content','display','flush','message','render','[DONE]','if(')):continue
  s=re.sub(r'\\x22[^\\x22]*\\x22|\\x27[^\\x27]*\\x27','STR',s)
  s=re.sub(r'(?i)(token|password|secret|authorization)\s*[:=]\s*[^,;]+',r'\1=<REDACTED>',s)
  output('NATIVE_STREAM_SOURCE_LINE',{'line':i+1,'code':s[:300]})
except Exception as e:output('NATIVE_STREAM_SOURCE_LINE',{'state':'HOLD_HTTP','kind':type(e).__name__})
# Identify actual Volta script and last failure types without exposing logs.
config=configparser.ConfigParser(interpolation=None,strict=False)
for cf in Path('/etc/supervisor/conf.d').glob('*.conf'):
 try:config.read(cf)
 except Exception:continue
sec='program:nox-train-volta-t866u'
if config.has_section(sec):
 fields={key:config.get(sec,key,fallback='') for key in ('command','directory','stdout_logfile','stderr_logfile','autostart','autorestart','startretries')}
 safe={key:(str(val)[:110] if key not in ('command','stdout_logfile','stderr_logfile') else
              hashlib.sha256(str(val).encode()).hexdigest()[:14]) for key,val in fields.items()}
 output('NATIVE_VOLTA_SUPERVISOR_CONFIG',safe)
 for key in ('stdout_logfile','stderr_logfile'):
  p=Path(fields.get(key,''))
  if not p.is_absolute() or not p.is_file() or p.stat().st_size>100000000:continue
  with p.open('rb') as f:
   f.seek(max(0,p.stat().st_size-120000))
   lines=f.read().decode('utf8','replace').splitlines()[-400:]
  signatures={'CUDA_OOM':r'(?:out of memory|CUDA.*memory|CUBLAS_STATUS_ALLOC_FAILED)',
    'IMPORT_ERROR':r'(?i)(?:ModuleNotFoundError|ImportError)',
    'QUANT_ERROR':r'(?i)(?:bitsandbytes|quantization.*error|nf4.*error)',
    'TRACEBACK':r'Traceback',
    'PROCESS_EXIT':r'(?i)(?:exited|exit code|terminated|killed|SIGKILL)',
    'STEP_0':r'(?i)(?:global_step[= :]0|step[= :]0|phase[= :]init)',
    'TRAIN_STEP_POSITIVE':r'(?i)(?:global_step[= :][1-9][0-9]*|step[= :][1-9][0-9]*)'}
  output('NATIVE_VOLTA_LOG_CLASS',{'label':key,'bytes':p.stat().st_size,'last_n_lines':len(lines),
       'counts':{n:sum(bool(re.search(pattern,line)) for line in lines) for n,pattern in signatures.items()}})
else:output('NATIVE_VOLTA_SUPERVISOR_CONFIG',{'state':'HOLD_NOT_FOUND'})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
 ssh.REMOTE=REMOTE;ssh.api=delay;ok=False
 try:ok=ssh.probe()
 except Exception as e:
  s=str(e);print('NOX_V83='+s if s.startswith('HOLD_') else 'NOX_V83=HOLD_NATIVE')
 finally:
  try:
   if not ssh.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
