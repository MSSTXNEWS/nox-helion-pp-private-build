#!/usr/bin/env python3
"""Bounded original NOX source/runtime inspection, no mutation or secret dump."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import configparser, glob, hashlib, json, os, re, subprocess, time

SECRET=re.compile(r'(?i)(?:\b(?:password|secret|api_key|access_key|authorization|token)\s*[:=]\s*[\"\']?[^\s,]+|Bearer\s+\S+|(?:hf_|ghp_|github_pat_)[A-Za-z0-9_]{12,}|BEGIN [A-Z ]*PRIVATE KEY)')
def run(a,t=15):
 try:
  p=subprocess.run(a,capture_output=True,text=True,timeout=t);return p.returncode,p.stdout
 except Exception as e:return 99,type(e).__name__
def emit(k,d):print('NOX_MAINT_INSPECT='+json.dumps({'section':k,'result':d},separators=(',',':')),flush=True)
def scrub(s):return SECRET.sub('[REDACTED]',s)

def configs():
 paths=set(glob.glob('/etc/supervisor/**/*.conf',recursive=True)+glob.glob('/etc/supervisord.conf'))
 rows=[]
 for path in sorted(paths):
  if Path(path).stat().st_size>500000:continue
  c=configparser.RawConfigParser(strict=False)
  try:c.read(path)
  except Exception:continue
  for sec in c.sections():
   if not sec.startswith('program:nox'):continue
   d={'file':path,'section':sec}
   for key in ('command','directory','autostart','autorestart','startsecs','stopwaitsecs','stdout_logfile','stderr_logfile'):
    if c.has_option(sec,key):d[key]=scrub(c.get(sec,key))[:1000]
   rows.append(d)
 return rows

def interpreters():
 paths={'/opt/venv/bin/python','/opt/venv/bin/python3','/usr/local/bin/python','/usr/local/bin/python3','/usr/bin/python3'}
 proc=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   argv=(p/'cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
   if not argv:continue
   if 'python' in argv[0]:
    if argv[0].startswith('/'):paths.add(argv[0])
    exe=os.readlink(p/'exe');paths.add(exe)
    if any('/root/nox/' in a for a in argv):
     env=dict(x.split('=',1) for x in (p/'environ').read_bytes().decode(errors='replace').split('\0') if '=' in x)
     proc.append({'pid':int(p.name),'executable':exe,'argv0':argv[0],'venv':env.get('VIRTUAL_ENV'),'pythonpath':env.get('PYTHONPATH')})
  except (OSError,ValueError):pass
 code="import importlib.metadata as m,json,sys; d={'python':sys.executable,'version':sys.version.split()[0]};\nfor n in ['torch','transformers','accelerate','deepspeed','peft','bitsandbytes','trl','psutil','nvidia-ml-py']:\n try:d[n]=m.version(n)\n except m.PackageNotFoundError:d[n]=None\nprint(json.dumps(d))"
 out=[]
 for p in sorted(paths):
  if not Path(p).is_file():continue
  rc,s=run([p,'-c',code])
  try:d=json.loads(s) if rc==0 else {'error':'IMPORT_FAILED'}
  except ValueError:d={'error':'INVALID_OUTPUT'}
  out.append({'path':p,'result':d})
 return {'interpreters':out,'nox_processes':proc[:40],'opt_dirs':[p.name for p in Path('/opt').iterdir()]}

def sources():
 rows=[]
 for pattern in ('*train*volta*','*train*worm*','*train*t866*','*teacher_serve*t811*','*priority_scheduler*','*offload_worm*t850*','*watch_swap*t845*'):
  for p in Path('/root/nox/scripts').glob(pattern):
   if not p.is_file() or p.is_symlink() or p.stat().st_size>55000:continue
   s=p.read_text(errors='replace')
   row={'path':str(p),'sha256':hashlib.sha256(s.encode()).hexdigest(),'bytes':len(s)}
   if SECRET.search(s):row['source_omitted']='POTENTIAL_CREDENTIAL_MATERIAL'
   else:row['source']=s
   rows.append(row)
 return rows

def errors():
 result=[]
 dirs=('/var/log/supervisor','/root/nox/logs','/root/nox/state','/tmp')
 for directory in dirs:
  for pattern in ('*volta*','*train*866*','*train*811*'):
   for p in Path(directory).glob(pattern):
    if not p.is_file() or p.is_symlink():continue
    try:
     with p.open('rb') as f:f.seek(max(0,p.stat().st_size-16000));s=f.read(16000).decode(errors='replace')
     lines=[scrub(x)[:800] for x in s.splitlines() if re.search(r'Error|Exception|Traceback|CUDA|memory|not found|step|loss|peft|bitsandbytes|ModuleNotFound',x)]
     result.append({'path':str(p),'bytes':p.stat().st_size,'tail':lines[-25:]})
    except OSError:pass
 return result[:20]

def models():
 result=[]
 for path in ('/root/nox/models/current.gguf','/root/nox/base_nf4','/workspace/base36','/dev/shm/base36','/root/nox/train','/root/nox/training','/root/nox/data','/root/nox/knowledge'):
  p=Path(path);d={'path':path,'exists':p.exists(),'symlink':p.is_symlink()}
  if p.exists():
   d['resolved']=str(p.resolve())
   if p.is_dir():d['entries']=[x.name for x in list(p.iterdir())[:35]]
  result.append(d)
 return result

def checkpoint_logs():
 rows=[]
 for d in ('/root/nox/state','/root/nox/logs','/root/nox_learn'):
  for p in Path(d).glob('*'):
   if p.is_file() and p.suffix in ('.json','.jsonl') and re.search(r'train|volta|distill|progress',p.name):
    rows.append({'path':str(p),'bytes':p.stat().st_size,'mtime':int(p.stat().st_mtime)})
 return rows[:40]

def work(n):
 f=(configs,interpreters,sources,errors,models,checkpoint_logs)[n]
 try:return f.__name__,{'worker_pid':os.getpid(),'data':f()}
 except Exception as e:return f.__name__,{'error':type(e).__name__}
if __name__=='__main__':
 with ProcessPoolExecutor(max_workers=6) as pool:
  for k,d in pool.map(work,range(6)):emit(k,d)
 print('NOX_MAINT_INSPECT_COMPLETE=true')
