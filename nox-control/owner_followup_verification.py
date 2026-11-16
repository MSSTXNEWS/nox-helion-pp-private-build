#!/usr/bin/env python3
"""One native connection: exact RAM duplicate, UI diagnostics, media progress."""
import base64,hashlib,json,os,re,stat,sys,time,types
from pathlib import Path
try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
ROOT=Path('/root/nox')
PINS={'owner_ram_duplicate_reclaim.py':'8698f9ab2e5b0870c6c6a76123792bf673b35b9d8f0e267376da7595538ba71e',
      'owner_browser_qa_entry.py':'0b1d1104d23369ebd6855ef06dac662461d608971eca9eb68b9c95d55e92a00c',
      'owner_s03_prepare_entry.py':'b303d295f27cbe423b8f8d3abc74f0e0cce6d845ad3e4f8d1f5da224cd726c35'}
MEDIA_SHA='e66a5b743deb0dfaa7e1e846e11b2d06190962d9ba0ba4abb67abeca54c02ca5'
def emit(kind,data):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)
def error(exc):
 text=str(exc)
 return text if re.fullmatch('HOLD_[A-Z0-9_]+',text) else type(exc).__name__
def load(name,raw,pin):
 if hashlib.sha256(raw).hexdigest()!=pin:raise RuntimeError('HOLD_FOLLOWUP_SOURCE_PIN')
 module=types.ModuleType('nox_followup_'+name[:-3]);module.__file__=str(ROOT/'scripts'/name)
 module.__dict__['__NOX_'+'BUNDLE_JSON__']=BUNDLE;sys.modules[module.__name__]=module
 exec(compile(raw,module.__file__,'exec'),module.__dict__)
 return module
def bundle(name):return load(name,base64.b64decode(BUNDLE.get(name,''),validate=True),PINS[name])
def private_read(path,limit=262144,tail=False):
 path=Path(path)
 if any(part.is_symlink() for part in (*path.parents,path)):raise RuntimeError('HOLD_FOLLOWUP_PATH')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as stream:
  info=os.fstat(stream.fileno())
  if not stat.S_ISREG(info.st_mode):raise RuntimeError('HOLD_FOLLOWUP_TYPE')
  if info.st_size>limit:
   if not tail:raise RuntimeError('HOLD_FOLLOWUP_SIZE')
   stream.seek(info.st_size-limit);stream.readline(limit+1)
  return stream.read(limit)
def media_progress():
 module=load('owner_media_install.py',private_read(ROOT/'scripts/owner_media_install.py'),MEDIA_SHA)
 state=ROOT/'state/owner_media';job_path=state/'prepare_job.json'
 result={'schema':'NOX_MEDIA_READONLY_PROGRESS_V1','resources':module.resources(),'assets':[],
         'generation_acceptance_verified':False,'worker':None}
 if job_path.exists():
  job=json.loads(private_read(job_path,16000));pid=job.get('pid')
  if type(pid) is not int or pid<=0:raise RuntimeError('HOLD_MEDIA_PROGRESS_PID')
  alive=False
  try:
   fields=Path('/proc',str(pid),'stat').read_text().split(') ',1)[1].split()
   alive=fields[0]!='Z' and fields[19]==job.get('start_ticks') and Path('/proc/sys/kernel/random/boot_id').read_text().strip()==job.get('boot_id')
  except FileNotFoundError:pass
  result['worker']={'alive':alive,'request':job.get('request'),'source_sha':job.get('source_sha'),'pid':pid}
  request=str(job.get('request',''))
  if not request.isdigit():raise RuntimeError('HOLD_MEDIA_PROGRESS_REQUEST')
  terminal=state/('prepare_result_'+request+'.json')
  if terminal.exists():
   value=json.loads(private_read(terminal,16000))
   result['worker_result']={k:value.get(k) for k in ('state','error','started','finished','mode')}
  path=ROOT/'logs'/('owner_media_prepare_'+request+'.log')
  if path.exists():
   events=[]
   for line in private_read(path,65536,True).decode(errors='replace').splitlines():
    if not line.startswith('NOX_MEDIA_INSTALL='):continue
    try:value=json.loads(line.split('=',1)[1])
    except ValueError:continue
    public={k:value[k] for k in ('phase','file','filename','bytes','total','component','error','code','maximum_transfers','pending_bytes','packages','missing','extra','mismatches') if k in value}
    # Lists/dicts of dependencies are allowed only if composed of bounded package identifiers.
    for key in ('packages','missing','extra','mismatches'):
     if key in public:public[key]=len(public[key]) if isinstance(public[key],(list,dict)) else public[key] if isinstance(public[key],(int,bool)) else '[REDACTED]'
    if any(isinstance(v,str) and (len(v)>160 or 'http' in v or '/' in v or '?' in v) for v in public.values()):continue
    events.append(public)
   result['recent_events']=events[-18:]
 for asset in module.ASSETS:
  rows=[]
  for tier in ('ram','disk'):
   path=module.asset_path(asset,tier)
   for final,target in ((True,path),(False,path.with_name(path.name+'.partial'))):
    if target.exists():
     info=target.stat()
     rows.append({'storage':tier,'bytes':info.st_size,'final_filename':final,
                  'full_sha_verified_now':bool(final and module.validate_file(target,asset))})
  result['assets'].append({'filename':asset['filename'],'expected_bytes':asset['bytes'],'copies':rows})
 result['selected_bytes']=sum(row['expected_bytes'] for row in result['assets'])
 result['downloaded_bytes']=sum(max((copy['bytes'] for copy in row['copies']),default=0) for row in result['assets'])
 result['all_asset_sha_verified_now']=all(any(copy['full_sha_verified_now'] for copy in row['copies']) for row in result['assets'])
 return result
def main():
 failed=[]
 for kind,call in (('media_progress_before',lambda:emit('media_progress_before',media_progress())),
                   ('ram_duplicate_alias',lambda:bundle('owner_ram_duplicate_reclaim.py').main()),
                   ('native_browser_qa',lambda:bundle('owner_browser_qa_entry.py').main()),
                   ('shared_memory_prepare',lambda:bundle('owner_s03_prepare_entry.py').main()),
                   ('media_progress_after',lambda:emit('media_progress_after',media_progress()))):
  try:
   code=call()
   if type(code) is int and code!=0:
    failed.append(kind);emit('followup_component_hold',{'component':kind,'returncode':code})
  except Exception as exc:failed.append(kind);emit('followup_component_hold',{'component':kind,'reason':error(exc)})
 emit('followup_complete',{'components_failed':failed,'each_component_result_is_separate':True})
 if not failed:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
 return 2 if failed else 0
if __name__=='__main__':raise SystemExit(main())
