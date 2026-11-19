"""Read-only exact Volta EXITED source admission and GPU processes for safe resume."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
old=ssh.api
def sleep_attach(method,path,key,data=None):
 r=old(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import subprocess,configparser,os,re,hashlib,json,shlex,sys
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V88_VOLTA_OOM_RECOVERY_READONLY_V1')
def emit(k,d):print(k+'='+json.dumps(d,sort_keys=True,separators=(',',':')))
cfg=configparser.ConfigParser(interpolation=None,strict=False)
for file in sorted(Path('/etc/supervisor/conf.d').glob('*.conf')):
 try:cfg.read(str(file))
 except Exception:continue
section='program:nox-train-volta-t866u'
if not cfg.has_section(section):
 emit('NATIVE_VOLTA_CONFIG',{'state':'HOLD_CONFIG_NOT_FOUND'})
else:
 command=cfg.get(section,'command',fallback='')
 try:args=shlex.split(command)
 except ValueError:args=[]
 files=[Path(a) for a in args if a.endswith(('.py','.sh')) and a.startswith('/')]
 out={'exe_basename':Path(args[0]).name if args else None,
      'script_basenames':[f.name for f in files],
      'autostart':cfg.get(section,'autostart',fallback=''),
      'autorestart':cfg.get(section,'autorestart',fallback=''),
      'directory_basename':Path(cfg.get(section,'directory',fallback='/')).name}
 for f in files:
  if f.is_file() and f.stat().st_size<300000:
   body=f.read_text(errors='replace')
   out[f.name]={'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),
                'bytes':len(body),
                'has_optimizer_step':('optimizer.step' in body or 'trainer.train(' in body),
                'has_cpu_offload':any(x in body for x in ('cpu_offload','offload_optimizer','offload_param')),
                'has_gradient_checkpointing':('gradient_checkpointing' in body),
                'has_sm70':('sm70' in body or 'V100' in body or 'Volta' in body),
                'config_hints':{k:len(re.findall(k,body,re.I)) for k in ('micro.batch','batch_size','seq_len','max_length','gradient_accumulation','nf4','int8')}}
 emit('NATIVE_VOLTA_CONFIG',out)
 paths=[(cfg.get(section,k,fallback=''),k) for k in ('stdout_logfile','stderr_logfile')]
 for filename,label in paths:
  file=Path(filename)
  if not file.is_absolute() or not file.is_file():continue
  with file.open('rb') as ff:
   ff.seek(max(0,file.stat().st_size-200000))
   lines=ff.read().decode('utf8','replace').splitlines()[-800:]
  errors=[]
  for line in lines:
   if re.search(r'(?i)(?:out of memory|Tried to allocate|allocated memory|reserved.*memory|cuda.*memory|CUDA_VISIBLE_DEVICES|SIGKILL|Killed process|CUBLAS_STATUS_ALLOC_FAILED)',line):
    sanitized=re.sub(r'(?:/[\w.-]+){2,}','<PATH>',line)
    sanitized=re.sub(r'(?i)(?:token|password|api[_-]?key)\s*[=:]\s*[^\s,;]+','<REDACTED>',sanitized)
    errors.append(sanitized[:230])
  emit('NATIVE_VOLTA_ERROR_EXCERPTS',{'stream':label,'matches':errors[-10:],
    'matched':len(errors),'file_size':file.stat().st_size})
# state/usage with per-GPU memory
try:
 p=subprocess.run(['supervisorctl','status','nox-train-volta-t866u'],capture_output=True,text=True,timeout=8)
 emit('NATIVE_VOLTA_STATUS',{'supervisorctl_rc':p.returncode,'words':p.stdout.split()[1:4]})
except Exception:pass
try:
 p=subprocess.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10)
 rows=[]
 for line in p.stdout.splitlines()[:30]:
  f=[x.strip() for x in line.split(',')]
  if len(f)==3:rows.append({'gpu_uuid_hint':f[0][-12:],'pid':f[1],'used_mib':f[2]})
 emit('NATIVE_GPU_PROCESS_MEM',{'rows':rows,'returncode':p.returncode})
except Exception:pass
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
 ssh.REMOTE=REMOTE;ssh.api=sleep_attach;ok=False
 try:ok=ssh.probe()
 except Exception as e:
  v=str(e);print('NOX_V88='+v if v.startswith('HOLD_') else 'NOX_V88=HOLD_NATIVE')
 finally:
  try:
   if not ssh.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
