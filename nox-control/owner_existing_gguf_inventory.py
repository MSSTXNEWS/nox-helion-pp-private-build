#!/usr/bin/env python3
"""Read-only exact on-disk GGUF inventory for NOX resource recovery.
Does not hash full weights, download, delete, move, stop or activate anything.
"""
from __future__ import annotations
import json,os,re,stat,subprocess
from pathlib import Path

ROOT=Path('/root/nox')
SCOPED=(
 ROOT/'models',
 ROOT/'models/teachers',
 ROOT/'models/teachers_ondisk',
 ROOT/'gguf',
 ROOT/'progress_pull_t784u/gguf',
 ROOT/'models/nox_lean_fallback',
 Path('/workspace/models'),
)
ALIASES=(ROOT/'models/current.gguf',ROOT/'models/teachers_ondisk/current.gguf')
STAGE='INIT'
class Hold(RuntimeError):pass
def need(c,r):
 if not c:raise Hold('HOLD_NOX_GGUF_INVENTORY_'+r)
def raw(path,limit):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
 with os.fdopen(fd,'rb') as f:
  info=os.fstat(f.fileno())
  need(stat.S_ISREG(info.st_mode),'FILE_TYPE')
  data=f.read(limit+1)
 need(len(data)<=limit,'FILE_BOUND')
 return data
def protected():
 result={}
 for svc in ('nox-ds41-8098','nox-proxy','nox-web29-18775','nox-dispatcher-t855u'):
  p=subprocess.run(['supervisorctl','status',svc],capture_output=True,text=True,timeout=8)
  m=re.match('^'+re.escape(svc)+r'\s+RUNNING\s+pid ([1-9][0-9]*),',p.stdout.strip())
  need(p.returncode==0 and m,'PROTECTED_SERVICE')
  pid=int(m[1])
  tail=raw(Path('/proc')/str(pid)/'stat',4096).decode('ascii').rsplit(') ',1)
  need(len(tail)==2 and len(tail[1].split())>19,'PROTECTED_PID')
  result[svc]={'pid':pid,'start_ticks':int(tail[1].split()[19])}
 return result
def choose_dir(path):
 if path.is_symlink():return None
 if not path.exists() or not path.is_dir():return None
 return path
def run():
 global STAGE
 need(re.fullmatch('[0-9]{1,24}',os.getenv('NOX_OWNER_REQUEST_ID','')) is not None,'OWNER_ID')
 need(re.fullmatch('[a-f0-9]{40}',os.getenv('NOX_OWNER_SOURCE_SHA','')) is not None,'OWNER_SOURCE')
 STAGE='SERVICES'
 services=protected()
 STAGE='ALIAS'
 aliases={}
 for a in ALIASES:
  if not a.is_symlink():continue
  try:
   dest=a.resolve(strict=True)
   need(dest.is_relative_to(ROOT),'ALIAS_SCOPE')
   info=dest.stat()
   if stat.S_ISREG(info.st_mode):
    aliases[str(a.relative_to(ROOT))]={'target_basename':dest.name,
        'bytes':info.st_size,'dev':info.st_dev,'ino':info.st_ino}
  except (OSError,ValueError):pass
 STAGE='FILES'
 files=[];seen=set();count=0
 for base in SCOPED:
  folder=choose_dir(base)
  if not folder:continue
  for e in folder.iterdir():
   count+=1;need(count<=15000,'ENTRY_BOUND')
   if e.is_symlink() or not e.name.lower().endswith(('.gguf','.safetensors')):continue
   if not re.fullmatch(r'[A-Za-z0-9._()+ -]{1,200}',e.name):continue
   try:
    st=e.stat(follow_symlinks=False)
    if not stat.S_ISREG(st.st_mode) or st.st_size<512*1024**2:continue
    marker=(st.st_dev,st.st_ino)
    if marker in seen:continue
    seen.add(marker)
    fd=os.open(e,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:head=os.read(fd,8)
    finally:os.close(fd)
    aliases_for=[a for a,x in aliases.items() if (x['dev'],x['ino'])==marker]
    files.append({'subdir':str(base.relative_to(ROOT)) if base.is_relative_to(ROOT) else 'WORKSPACE',
        'name':e.name,'bytes':st.st_size,'gguf_header':head.startswith(b'GGUF'),
        'is_current_alias':bool(aliases_for),'alias_names':aliases_for})
   except OSError:pass
 files.sort(key=lambda x:(-x['bytes'],x['name']))
 files=files[:75]
 STAGE='AFTER'
 need(protected()==services,'PROTECTED_CHANGED')
 free=os.statvfs(ROOT).f_bavail*os.statvfs(ROOT).f_frsize
 return {'schema':'NOX_OWNER_GGUF_INVENTORY_V1','read_only':True,
  'disk_free_bytes':free,'models_found':len(files),'files':files,
  'current_aliases':{a:{'target_basename':x['target_basename'],'bytes':x['bytes']}
                     for a,x in aliases.items()},
  'no_s03_model_or_queue_write':True,'no_files_modified':True}
if __name__=='__main__':
 try:
  result=run()
  print('NOX_MAINT_GGUF_INVENTORY='+json.dumps(result,sort_keys=True,separators=(',',':')),flush=True)
  print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
 except Exception as e:
  reason=str(e)
  if not re.fullmatch('HOLD_NOX_GGUF_INVENTORY_[A-Z0-9_]{1,100}',reason):
   reason='HOLD_NOX_GGUF_INVENTORY_INTERNAL_'+STAGE+'_'+type(e).__name__.upper()
  print('NOX_MAINT_GGUF_INVENTORY='+json.dumps({'status':'HOLD','reason':reason},sort_keys=True),flush=True)
  raise SystemExit(2)
