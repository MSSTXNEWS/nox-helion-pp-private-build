#!/usr/bin/env python3
"""Read-only controller failure, S03 metadata and focused storage diagnostics."""
import base64,hashlib,importlib.util,json,os,re,stat,sys,tempfile,time,types
from pathlib import Path
try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
ROOT=Path('/root/nox');HELPER_SHA='b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0'
S03_SHA='a06e45cfe58b6350f5d67787ab13b834a168f78f910574db51af7635e8c969f1'
def emit(kind,data):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)
def read(path,limit=131072,tail=False):
 path=Path(path)
 if any(p.is_symlink() for p in (*path.parents,path)):raise RuntimeError('HOLD_DIAGNOSTIC_LINK')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as stream:
  info=os.fstat(stream.fileno())
  if not stat.S_ISREG(info.st_mode):raise RuntimeError('HOLD_DIAGNOSTIC_TYPE')
  if info.st_size>limit:
   if not tail:raise RuntimeError('HOLD_DIAGNOSTIC_SIZE')
   stream.seek(info.st_size-limit);stream.readline(limit+1)
  return stream.read(limit)
def module(name,pin):
 raw=base64.b64decode(BUNDLE.get(name,''),validate=True)
 if hashlib.sha256(raw).hexdigest()!=pin:raise RuntimeError('HOLD_DIAGNOSTIC_SOURCE')
 mod=types.ModuleType(name[:-3]);mod.__file__=str(ROOT/'scripts'/name)
 sys.modules[mod.__name__]=mod;exec(compile(raw,mod.__file__,'exec'),mod.__dict__)
 return mod
def log_projection(raw):
 text=raw.decode(errors='replace');rows=[]
 for line in text.splitlines():
  error=re.match(r'^(?:[A-Za-z0-9_]+\.)?(ImportError|ModuleNotFoundError|AttributeError|NameError|TypeError|ValueError|RuntimeError|PermissionError|LifecycleHold|OutboxHold|PlanHold|MediaHold):',line.strip())
  if error:
   row={'exception':error[1]}
   codes=re.findall(r'\b(?:HOLD|WAIT)_[A-Za-z0-9_]{1,130}\b',line)
   if codes:row['codes']=codes[:4]
   symbols=re.findall(r"(?:module|attribute|name|named) ['\"]([A-Za-z_][A-Za-z0-9_.]{0,90})['\"]",line)
   if symbols:row['symbols']=symbols[:4]
   rows.append(row)
  trace=re.search(r'File "(/root/nox/scripts/[A-Za-z0-9_.-]+\.py)", line ([0-9]+), in ([A-Za-z0-9_<>]+)',line)
  if trace:rows.append({'file':Path(trace[1]).name,'line':int(trace[2]),'function':trace[3]})
 return rows[-35:]
def controller_state(helper):
 out=[]
 for name in ('nox-dispatcher-t855u','nox-priority-scheduler','nox-selfheal'):
  config=helper.program_config(name);row={'service':name,'status':helper.service_state(name),'logs':[]}
  paths=set()
  for key in ('stdout_logfile','stderr_logfile'):
   value=config.get(key)
   if value and value!='AUTO':paths.add(Path(value))
  if name=='nox-dispatcher-t855u':paths.add(ROOT/'logs/dispatcher_t855u.log')
  for path in paths:
   if not any(path.is_relative_to(base) for base in (ROOT/'logs',Path('/var/log'),Path('/opt/supervisor-scripts'))):continue
   try:row['logs'].append({'channel':path.name,'mtime':path.stat().st_mtime,'diagnostics':log_projection(read(path,131072,True))})
   except Exception as exc:row['logs'].append({'channel':'configured_log','read_error':type(exc).__name__})
  out.append(row)
 return out
def storage_focus(request,helper):
 excluded={'venv','venv_volta','venv_v100','venv_new','node_modules','.git','site-packages','__pycache__','merged_hf'}
 roots=[Path('/dev/shm'),ROOT];pending=[(base,base,0) for base in reversed(roots)]
 deadline=time.monotonic()+18;count=0;seen=set();large=[];groups={};complete=True
 while pending:
  if count>=75000 or time.monotonic()>deadline:complete=False;break
  base,path,depth=pending.pop()
  try:entries=list(os.scandir(path))
  except OSError:continue
  for ent in entries:
   count+=1
   if count>=75000:complete=False;break
   try:
    info=ent.stat(follow_symlinks=False)
    if stat.S_ISLNK(info.st_mode):continue
    p=Path(ent.path)
    if stat.S_ISDIR(info.st_mode):
     if depth<10 and ent.name not in excluded:pending.append((base,p,depth+1))
     continue
    if not stat.S_ISREG(info.st_mode) or (info.st_dev,info.st_ino) in seen:continue
    seen.add((info.st_dev,info.st_ino));relative=p.relative_to(base);group=str(base)+('/'+relative.parts[0] if len(relative.parts)>1 else '')
    groups[group]=groups.get(group,0)+info.st_blocks*512
    if info.st_size>=128*1024**2:
     large.append({'path':str(p),'size':info.st_size,'allocated':info.st_blocks*512,'device':info.st_dev,'inode':info.st_ino,'links':info.st_nlink,'mtime_ns':info.st_mtime_ns})
   except OSError:continue
 large.sort(key=lambda r:r['allocated'],reverse=True);private={'schema':'NOX_OWNER_STORAGE_FOCUS_V1','request':request,'large_files':large[:100],'groups':groups,'complete':complete,'entries':count}
 path=ROOT/'state/owner_storage'/('focus_'+request+'.json');helper.atomic(path,json.dumps(private,indent=2).encode())
 safe_groups=[]
 for name,size in sorted(groups.items(),key=lambda r:r[1],reverse=True)[:25]:
  label=name if re.fullmatch(r'/(?:root/nox|dev/shm)(?:/[A-Za-z0-9_.-]{1,80})?',name) else '[PRIVATE_GROUP]'
  safe_groups.append({'group':label,'allocated_bytes':size})
 public=[]
 for row in large[:30]:
  name=Path(row['path']).name
  known=bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,150}',name) and name.lower().endswith(('.gguf','.safetensors','.tar','.gz','.zip','.7z','.pt','.pth','.bin')))
  public.append({'filename':name if known else '[PRIVATE_FILE]','tier':'RAM' if row['path'].startswith('/dev/shm/') else 'SSD','bytes':row['size'],'allocated':row['allocated'],'path_sha256':hashlib.sha256(row['path'].encode()).hexdigest()})
 return {'schema':private['schema'],'complete':complete,'entries':count,'groups':safe_groups,'large_files':public,'private_receipt':str(path),'receipt_sha256':hashlib.sha256(read(path,262144)).hexdigest(),'files_deleted':0}
def main():
 request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
 if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):raise RuntimeError('HOLD_OWNER_CONTEXT')
 helper=module('owner_native_repair.py',HELPER_SHA)
 for kind,fn in (('controller_startup_diagnostic',lambda:controller_state(helper)),('shared_memory_diagnostic',lambda:module('owner_s03_diagnostic.py',S03_SHA).run()),('storage_focus',lambda:storage_focus(request,helper))):
  try:emit(kind,fn())
  except Exception as exc:emit(kind,{'state':'DIAGNOSTIC_ERROR','class':type(exc).__name__})
 print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
if __name__=='__main__':
 try:main()
 except Exception as exc:emit('controller_diagnostic_hold',{'reason':type(exc).__name__});raise SystemExit(2)
