#!/usr/bin/env python3
"""Owner-approved one-shot integration on existing NOX; preserves GPU0 chat/S03.
Only known source revisions are patched. No blind process sweep or weight deletion.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import base64, configparser, fcntl, hashlib, json, os, py_compile, re, shutil, signal, stat, subprocess, tempfile, time, urllib.request
BUNDLE=__NOX_BUNDLE_JSON__
ROOT=Path('/root/nox');STATE=ROOT/'state';SCRIPTS=ROOT/'scripts'
SHA=os.environ['NOX_OWNER_SOURCE_SHA'];REQUEST=os.environ['NOX_OWNER_REQUEST_ID']
BACKUP=ROOT/'backup'/'owner_maintenance'/REQUEST
PROTECTED_PORTS={8080,8081,8082,8083}

def emit(kind,data):print('NOX_MAINT_STAGE='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)
def digest(b):return hashlib.sha256(b).hexdigest()
def atomic(p,b,mode=0o600):
 p=Path(p)
 if p.is_symlink():raise RuntimeError('HOLD_TARGET_SYMLINK')
 p.parent.mkdir(parents=True,exist_ok=True)
 fd,t=tempfile.mkstemp(prefix='.owner-',dir=p.parent)
 try:
  os.fchmod(fd,mode)
  with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
  os.replace(t,p)
 finally:
  if os.path.exists(t):os.unlink(t)

def backup(p):
 p=Path(p)
 if not p.is_file() or p.is_symlink():raise RuntimeError('HOLD_SOURCE_PATH')
 b=p.read_bytes();dest=BACKUP/str(p).lstrip('/')
 if not dest.exists():atomic(dest,b)
 elif dest.read_bytes()!=b:raise RuntimeError('HOLD_BACKUP_COLLISION')
 return b

def command(argv,timeout=30):
 try:
  p=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
  return p.returncode,p.stdout,p.stderr
 except subprocess.TimeoutExpired:return 124,'',''

def status(name):
 rc,out,_=command(['supervisorctl','status',name],10)
 parts=out.split();return parts[1] if len(parts)>1 else 'UNKNOWN'

def write_change(p,expected,transform):
 old=backup(p)
 if digest(old)!=expected:raise RuntimeError('HOLD_SOURCE_CHANGED_'+Path(p).name.replace('.','_'))
 text=transform(old.decode());compile(text,str(p),'exec') if str(p).endswith('.py') else None
 atomic(p,text.encode(),0o755)
 emit('source_installed',{'path':str(p),'before':expected,'after':digest(text.encode()),'backup':str(BACKUP)})

def package_smoke():
 py='/root/venv_volta/bin/python'
 if not Path(py).is_file():return {'error':'MISSING_EXISTING_VOLTA_ENV'}
 code='''import json,importlib.metadata as m,torch,bitsandbytes as bnb
from peft import LoraConfig,get_peft_model
out={'torch':torch.__version__,'cuda':torch.version.cuda,'capability':list(torch.cuda.get_device_capability()),'arch':torch.cuda.get_arch_list()}
for n in ('peft','bitsandbytes','trl','transformers','accelerate','deepspeed','nvidia-ml-py'):
 try:out[n]=m.version(n)
 except m.PackageNotFoundError:out[n]=None
a=torch.randn(64,64,device='cuda',dtype=torch.float16);b=a@a;torch.cuda.synchronize()
out['fp16_cuda_matmul']=bool(torch.isfinite(b).all().item())
q,state=bnb.functional.quantize_4bit(a,quant_type='nf4',compress_statistics=True)
x=bnb.functional.dequantize_4bit(q,state);torch.cuda.synchronize()
out['nf4_cuda_smoke']=bool(torch.isfinite(x).all().item())
print(json.dumps(out))
'''
 env={**os.environ,'CUDA_VISIBLE_DEVICES':'1','OMP_NUM_THREADS':'2','TOKENIZERS_PARALLELISM':'false'}
 p=subprocess.run([py,'-c',code],env=env,capture_output=True,text=True,timeout=90)
 if p.returncode:return {'error':'GPU_LIBRARY_SMOKE_FAILED','rc':p.returncode,'error_class':next((x.split(':',1)[0] for x in reversed(p.stderr.splitlines()) if 'Error:' in x),'UNKNOWN')}
 return json.loads(p.stdout.strip().splitlines()[-1])

def teacher_candidates():
 rows=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   argv=(p/'cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
   if not argv or 'llama-server' not in Path(argv[0]).name:continue
   def value(k):return argv[argv.index(k)+1] if k in argv and argv.index(k)+1<len(argv) else None
   model=value('-m') or value('--model');port=value('--port')
   env=dict(x.split('=',1) for x in (p/'environ').read_bytes().decode(errors='replace').split('\0') if '=' in x)
   dev=env.get('CUDA_VISIBLE_DEVICES','')
   if port and port.isdigit():port=int(port)
   rows.append({'pid':int(p.name),'model':model,'port':port,'cuda_visible':dev,
                'starttime':(p/'stat').read_text().split(') ',1)[1].split()[19]})
  except (OSError,ValueError):continue
 return rows

def gpu1():
 rc,out,_=command(['nvidia-smi','-i','1','--query-gpu=memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'],10)
 if rc:return None
 a=[int(float(x.strip())) for x in out.strip().split(',')];return {'used_mib':a[0],'free_mib':a[1],'utilization':a[2]}

def health():
 result={}
 for port in (8080,8081):
  try:
   with urllib.request.urlopen('http://127.0.0.1:%s/health'%port,timeout=5) as r:result[str(port)]=r.status
  except Exception as e:result[str(port)]=type(e).__name__
 return result

WORKSPACE_STOP = Path('/workspace/NOX_STOP')
STOP_PATHS = (ROOT/'STOP',ROOT/'STOP.flag',ROOT/'stop.flag',ROOT/'.stop',
              ROOT/'program/STOP',STATE/'STOP',STATE/'STOP.flag',WORKSPACE_STOP)
OWNER_MAINTENANCE_FLAG = STATE/'OWNER_MAINTENANCE.flag'
OWNER_WRITER_LEASE_STATE = 'UNKNOWN_NO_OWNER_CAS_READBACK'


def _native_flag_state(path):
 try:
  info=Path(path).lstat()
 except FileNotFoundError:
  return 'ABSENT'
 except OSError:
  return 'UNKNOWN'
 return 'PRESENT' if stat.S_ISREG(info.st_mode) else 'UNSAFE'


def stage_gate(stop_paths, maintenance_flag, lease_state):
 # Match owner_native_inspect.owner_safety_snapshot. Existing STOP aliases and
 # the separate OWNER_MODEL_UPDATE maintenance flag block all stage writes.
 for path in stop_paths:
  state=_native_flag_state(path)
  if state=='PRESENT':
   raise RuntimeError('HOLD_OWNER_STOP_ACTIVE')
  if state!='ABSENT':
   raise RuntimeError('HOLD_OWNER_STOP_EVIDENCE_UNKNOWN')
 maintenance=_native_flag_state(maintenance_flag)
 if maintenance=='PRESENT':
  raise RuntimeError('HOLD_OWNER_MODEL_UPDATE_ACTIVE')
 if maintenance!='ABSENT':
  raise RuntimeError('HOLD_OWNER_MODEL_UPDATE_EVIDENCE_UNKNOWN')
 if lease_state!='OWNER_CAS_VERIFIED':
  raise RuntimeError('HOLD_OWNER_LEASE_UNKNOWN')


def require_stage_admission():
 # owner_native_inspect reports UNKNOWN_NO_OWNER_CAS_READBACK. A flock is not
 # a native owner lease, so production stage remains blocked until proof exists.
 stage_gate(STOP_PATHS,OWNER_MAINTENANCE_FLAG,OWNER_WRITER_LEASE_STATE)


def _same_hold_preimage(path, identity, sha):
 try:
  info=path.lstat()
  if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
   return False
  current=(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)
  return current==identity and digest(path.read_bytes())==sha
 except OSError:
  return False


def _restore_train_hold(hold, archived, identity, sha):
 if archived is None or not archived.exists():
  return
 if not _same_hold_preimage(archived,identity,sha):
  raise RuntimeError('HOLD_TRAIN_HOLD_PREIMAGE_CHANGED')
 if hold.exists() or hold.is_symlink():
  raise RuntimeError('HOLD_TRAIN_HOLD_RESTORE_COLLISION')
 archived.rename(hold)


def release_hold_and_start_trainer():
 hold=STATE/'TRAIN_HOLD.flag'
 archived=None
 hold_identity=None
 hold_sha=None
 attempts=STATE/'train_volta_t866u.attempts'
 prior_attempts=None
 attempts_written=False
 require_stage_admission()  # immediately before TRAIN_HOLD can be released
 try:
  if hold.is_file() and not hold.is_symlink():
   before=hold.lstat()
   prior=backup(hold)
   after=hold.lstat()
   if ((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=
       (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) or digest(hold.read_bytes())!=digest(prior)):
    raise RuntimeError('HOLD_TRAIN_HOLD_PREIMAGE_CHANGED')
   hold_identity=(before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)
   hold_sha=digest(prior)
   archived=STATE/('TRAIN_HOLD.resumed_by_owner_'+REQUEST)
   if archived.exists() or archived.is_symlink():raise RuntimeError('HOLD_TRAIN_HOLD_ARCHIVE_COLLISION')
   require_stage_admission()  # immediately before archiving TRAIN_HOLD
   hold.rename(archived)
  if attempts.exists():
   prior_attempts=backup(attempts)
  require_stage_admission()
  atomic(attempts,b'0\\n')
  attempts_written=True
  require_stage_admission()  # last fence immediately before supervisor start
 except BaseException:
  if attempts_written:
   if prior_attempts is None:
    try:
     if attempts.is_symlink() or attempts.is_file():attempts.unlink()
    except FileNotFoundError:
     pass
   else:
    atomic(attempts,prior_attempts)
  _restore_train_hold(hold,archived,hold_identity,hold_sha)
  raise
 return command(['supervisorctl','start','nox-train-volta-t866u'],40)


def main():
 require_stage_admission()  # before mkdir, receipt, backup, or service actions
 STATE.mkdir(parents=True,exist_ok=True)
 lock=os.open(STATE/'owner_maintenance.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 receipt=STATE/('owner_maintenance_'+REQUEST+'.json')
 if receipt.exists():raise RuntimeError('HOLD_REQUEST_ALREADY_STARTED_INSPECT_RECEIPT')
 BACKUP.mkdir(parents=True,exist_ok=True,mode=0o700)
 result={'request':REQUEST,'source_sha':SHA,'started':time.time(),'steps':[],'chat_before':health(),'weight_deletions':0,'unique_data_deleted':0}
 atomic(receipt,json.dumps(result).encode())
 if result['chat_before'].get('8081')!=200:raise RuntimeError('HOLD_CHAT_NOT_HEALTHY_BEFORE_MAINTENANCE')
 # Preserve original active training; do not terminate an optimizer mid-step.
 state=status('nox-train-volta-t866u')
 if state in ('RUNNING','STARTING'):
  emit('trainer_busy_no_change',{'state':state});raise RuntimeError('HOLD_ACTIVE_TRAINER')
 # Actual native deployment of the tested existing storage utility.
 for name in ('nox_cold_drive.py','owner_native_audit.py','owner_native_inspect.py'):
  data=base64.b64decode(BUNDLE[name]);compile(data,name,'exec')
  dst=SCRIPTS/name
  if dst.exists():backup(dst)
  atomic(dst,data,0o755)
  py_compile.compile(str(dst),doraise=True)
  result['steps'].append({'installed':str(dst),'sha256':digest(data)})
 emit('installed_native_helpers',result['steps'])
 # Missing telemetry library only; no torch/transformers upgrades or duplicate env.
 py='/root/venv_volta/bin/python'
 if not Path(py).is_file():raise RuntimeError('HOLD_VOLTA_ENV_MISSING')
 rc,_,_=command([py,'-c','import pynvml'],15)
 if rc:
  rc,_,_=command([py,'-m','pip','install','--disable-pip-version-check','--no-cache-dir','--no-deps','nvidia-ml-py>=12,<14'],120)
  emit('nvml_dependency_install',{'rc':rc})
  if rc:raise RuntimeError('HOLD_NVML_INSTALL')
 smoke=package_smoke();emit('native_gpu_library_smoke',smoke)
 if not smoke.get('fp16_cuda_matmul') or not smoke.get('nf4_cuda_smoke'):raise RuntimeError('HOLD_GPU_STACK_SMOKE')
 teacher=SCRIPTS/'teacher_serve_t811u.sh'
 def patch_teacher(s):
  anchor='gpu1_training_busy(){\n'
  if anchor not in s:raise RuntimeError('HOLD_TEACHER_ANCHOR')
  s=s.replace(anchor,anchor+'  [ -f /root/nox/state/train_wants_gpu1 ] && return 0\n',1)
  s=s.replace('start_cpu_judge 8092 8 4 8192','start_cpu_judge 8092 2 2 4096').replace('start_cpu_judge 8093 8 4 8192','start_cpu_judge 8093 2 2 4096')
  s=s.replace('8087 14 4 8192','8087 3 2 4096').replace('8088 14 4 8192','8088 3 2 4096')
  return s
 write_change(teacher,'f5c71f1ff51f2a67d0ea57f464e2c510d775bdc36676922a161fb25eeefca15e',patch_teacher)
 rc,_,_=command(['bash','-n',str(teacher)])
 if rc:raise RuntimeError('HOLD_TEACHER_BASH_SYNTAX')
 # Reserve GPU1 before controller restart. Only GPU1 auxiliary inference yields.
 flag=STATE/'train_wants_gpu1'
 if flag.exists():backup(flag)
 atomic(flag,('owner maintenance '+REQUEST+'\n').encode())
 rc,_,_=command(['supervisorctl','restart','nox-teacher-serve-t811u'],35)
 emit('teacher_controller_reload',{'rc':rc,'state':status('nox-teacher-serve-t811u')})
 rows=teacher_candidates();emit('llama_roles_before',rows)
 stopped=[]
 for row in rows:
  if row['cuda_visible']!='1' or row['port'] in PROTECTED_PORTS or not isinstance(row['port'],int):continue
  model=row.get('model') or ''
  if not model.startswith(('/root/nox/judge/','/root/nox/models/teachers/','/root/nox/models/judge/')):continue
  p=Path('/proc')/str(row['pid'])
  try:
   if (p/'stat').read_text().split(') ',1)[1].split()[19]!=row['starttime']:continue
   os.kill(row['pid'],signal.SIGTERM);stopped.append(row)
  except ProcessLookupError:pass
 emit('owned_gpu1_inference_yielded',stopped)
 for _ in range(20):
  g=gpu1()
  if g and g['free_mib']>=27000:break
  time.sleep(2)
 emit('gpu1_after_yield',gpu1())
 if not gpu1() or gpu1()['free_mib']<27000:raise RuntimeError('HOLD_GPU1_NOT_FREE_NO_BLIND_KILL')
 # Existing trainer remains the sole training entry. Limit CPU work by actual cgroup quota.
 oldenv=STATE/'train_cpu_max.env'
 if oldenv.exists():backup(oldenv)
 atomic(oldenv,b'TRAIN_CPU_MAX=64GiB\nOMP_NUM_THREADS=4\nMKL_NUM_THREADS=4\nOPENBLAS_NUM_THREADS=1\nTOKENIZERS_PARALLELISM=false\n',0o600)
  # HOLD, attempt counter, and trainer start share repeated owner admission gates.
 had_hold=(STATE/'TRAIN_HOLD.flag').is_file()
 rc,out,_=release_hold_and_start_trainer()
 if had_hold:emit('manual_hold_released_by_explicit_owner_request',True)
 emit('existing_trainer_start',{'rc':rc,'state':status('nox-train-volta-t866u')})
 result.update(steps=result['steps'],gpu1_after=gpu1(),stopped_teacher_pids=[x['pid'] for x in stopped],
               trainer_status=status('nox-train-volta-t866u'),chat_after=health(),finished=time.time(),
               training_steps_verified=False,storage_remote_configured=False)
 atomic(receipt,json.dumps(result,indent=2).encode())
 emit('native_receipt',result)
 if result['chat_after'].get('8081')!=200:raise RuntimeError('HOLD_CHAT_HEALTH_REGRESSION')
 if result['trainer_status'] not in ('RUNNING','STARTING'):raise RuntimeError('HOLD_TRAINER_START_FAILED')
 print('NOX_MAINT_STAGE_COMPLETE=true',flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:
  code=str(e);emit('failure',code if re.fullmatch('HOLD_[A-Za-z0-9_]+',code) else type(e).__name__)
  raise SystemExit(2)
