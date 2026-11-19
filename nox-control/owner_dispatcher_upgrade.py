#!/usr/bin/env python3
"""Install reviewed native task plans, shared preflight, media and owner reports.

The exact existing dispatcher is updated under the established maintenance
lease. Its six worker threads, claim logic and task history remain authoritative.
Only known controller services are briefly restarted; the chat model, proxy,
training HOLD, weights and S03 data remain available and unchanged.
"""
from __future__ import annotations
import base64,fcntl,hashlib,importlib.util,json,os,re,shlex,stat,subprocess,sys,time,types
from pathlib import Path

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
ROOT=Path('/root/nox');SCRIPTS=ROOT/'scripts';STATE=ROOT/'state'
DISPATCHER=SCRIPTS/'nox_dispatcher_t855u.py'
OLD_DISPATCHER='31fafe9501a81684ab3476acb940e1a8ea439067a610164c9057a647f0990fa2'
NEW_DISPATCHER='d4e665915ae2a9f0be8ae4603be3768467e0f88be876e408465c3a7cc156c243'
HELPER='b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0'
PINS={
 'owner_event_outbox.py':'af4edd2c34e4d46902ccf914b5be9c845a95d682d34f92a08cd69357c4b69c00',
 'owner_media_runtime.py':'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5',
 'owner_task_plans.py':'7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773',
 'owner_task_lifecycle.py':'020fcee6d1267189811c51da031761aa9ae681a3a2bcd567fbbc150c33db8605',
 'owner_senior_gateway.py':'1fd1556009ce62fa806bdee0a9a34577d276344e728fe9d94b33f44eb151346e',
 'owner_s03_diagnostic.py':'a06e45cfe58b6350f5d67787ab13b834a168f78f910574db51af7635e8c969f1',
 'owner_task_lifecycle.json':'70d600e861a1e9908d06691790e54e2abcd814b460144ece2af3d2b6a54e0e80',
 'download_manifest.json':'7ce1b32c3e007fefa5b8c96aca34bd8ca10d97cce15968100e40b29685c091f9',
}
SOURCE_PINS={
 'owner_mentor':'12211a29f77de8e5181d4dd78c35d5da2ed5de0dc6ea529149d32f0896809292',
 'owner_event_outbox':PINS['owner_event_outbox.py'],
 'owner_media_runtime':PINS['owner_media_runtime.py'],
 'owner_task_plans':PINS['owner_task_plans.py'],
 'owner_senior_gateway':PINS['owner_senior_gateway.py'],
}
CONTROLLERS={
 'nox-dispatcher-t855u':(DISPATCHER,OLD_DISPATCHER),
 'nox-priority-scheduler':(SCRIPTS/'nox_priority_scheduler.py','5decaeba7bc1d329abbb627861cd03d99b8150136e98d0e2facd8fcb8e29f45a'),
 'nox-selfheal':(Path('/root/nox_selfheal.py'),'84a841854e25e94a91d1582106ce2825287e631c068775529790f9843add3538'),
}
OLD_MANIFEST='c770a43ddcdeb08483cd90a733b5fc9899d8b1e119e576d6163cbc0b2d66e7ff'

def digest(raw):return hashlib.sha256(raw).hexdigest()
def emit(kind,data):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)
def fail(code):raise RuntimeError(code)
def safe(exc):
 value=str(exc)
 return value if re.fullmatch('HOLD_[A-Z0-9_]+',value) else type(exc).__name__
def raw_file(path,limit=1024*1024):
 path=Path(path)
 if any(p.is_symlink() for p in (*path.parents,path)):fail('HOLD_UPGRADE_PATH_SYMLINK')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as stream:
  meta=os.fstat(stream.fileno())
  if not stat.S_ISREG(meta.st_mode) or meta.st_size>limit:fail('HOLD_UPGRADE_FILE_SCOPE')
  raw=stream.read(limit+1)
  if len(raw)>limit:fail('HOLD_UPGRADE_FILE_SCOPE')
  return raw
def document(path,limit=1024*1024):
 value=json.loads(raw_file(path,limit))
 if not isinstance(value,dict):fail('HOLD_UPGRADE_JSON_SCHEMA')
 return value
def bundle(name,pin):
 raw=base64.b64decode(BUNDLE.get(name,''),validate=True)
 if digest(raw)!=pin:fail('HOLD_UPGRADE_BUNDLE_PIN')
 if name.endswith('.py'):compile(raw,name,'exec')
 else:json.loads(raw)
 return raw
def load_helper():
 raw=bundle('owner_native_repair.py',HELPER)
 module=types.ModuleType('owner_upgrade_reviewed_helper');sys.modules[module.__name__]=module
 exec(compile(raw,'<reviewed-helper>','exec'),module.__dict__)
 return module
def load_installed(name):
 path=SCRIPTS/(name+'.py');raw=raw_file(path)
 if digest(raw)!=PINS[path.name]:fail('HOLD_UPGRADE_MODULE_PIN')
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec)
 sys.modules[name]=mod;exec(compile(raw,str(path),'exec'),mod.__dict__)
 return mod
def pending_claims():
 value=document(STATE/'dispatcher/state.json',16*1024*1024)
 if not isinstance(value.get('tasks'),dict):fail('HOLD_UPGRADE_QUEUE_SCHEMA')
 return sum(isinstance(t,dict) and t.get('status')=='running' for t in value['tasks'].values())
def check_service(helper,name,path):
 observed=helper.service_state(name);config=helper.program_config(name)
 argv=shlex.split(config.get('command',''));bound=str(path) in argv
 for arg in argv:
  launcher=Path(arg)
  if (not bound and launcher.parent==Path('/opt/supervisor-scripts') and launcher.suffix=='.sh'
      and launcher.is_file() and str(path) in raw_file(launcher,32000).decode()):bound=True
 if not bound:fail('HOLD_UPGRADE_SERVICE_COMMAND')
 if observed['state']=='RUNNING':
  process=helper.process(observed['pid'])
  if not process or process['service']!=name or str(path) not in process['argv']:fail('HOLD_UPGRADE_SERVICE_IDENTITY')
  if config.get('stopasgroup','').lower()=='true' or config.get('killasgroup','').lower()=='true':
   if any(row['service']!=name for row in helper.process_table().values() if row['pgrp']==process['pgrp'] and row['state']!='Z'):
    fail('HOLD_UPGRADE_SERVICE_GROUP')
 elif observed['state'] not in ('STOPPED','EXITED','FATAL'):fail('HOLD_UPGRADE_SERVICE_STATE')
 return observed
def queue_task(request):
 return {'id':'owner.autonomy.audit.'+request,'handler':'owner_order','class':'owner_order',
  'priority':0,'status':'pending','deps':[],'locks':[],'retries':0,'max_retries':1,'timeout_sec':120,
  'title':'Verify shared NOX task lifecycle','source':'NOX_OWNER_DISPATCHER_UPGRADE_V1',
  'params':{'plan':{'schema':'NOX_OWNER_PLAN_REQUEST_V1','intent':'audit'}}}
def event_projection(row):
 return {'sequence':row.get('sequence'),'kind':row.get('kind'),'task_id':(row.get('task') or {}).get('id'),
  'claim':(row.get('task') or {}).get('claim'),'learning':row.get('learning'),
  'verification':row.get('verification'),'journal_sha256':row.get('journal_sha256')}
def verify_plan(request,started,outbox):
 value=document(STATE/'dispatcher/state.json',16*1024*1024);tasks=value['tasks']
 parent=tasks.get('owner.autonomy.audit.'+request,{})
 result={'parent_status':parent.get('status'),'children':[],'verified':False}
 ids=parent.get('owner_plan_children') or []
 if len(ids)!=6 or len(set(ids))!=6:return result
 all_claims=set();task_ids=set(ids+[parent['id']]);proofs=[]
 for tid in ids+[parent['id']]:
  task=tasks.get(tid) or {};evidence=task.get('result') or {};claim=task.get('owner_claim') or {}
  public={'id':tid,'status':task.get('status'),'scope':evidence.get('scope'),'blockers':evidence.get('blockers',[])}
  if tid!=parent['id']:result['children'].append(public)
  nonce=claim.get('nonce');path=Path(str(evidence.get('receipt_path','')))
  if (task.get('status')!='done' or not isinstance(nonce,str) or not re.fullmatch('[a-f0-9]{24}',nonce)
      or nonce in all_claims or evidence.get('verified') is not True
      or not path.is_relative_to(STATE/'owner_plans')):return result
  all_claims.add(nonce);raw=raw_file(path,262144);record=json.loads(raw)
  if (digest(raw)!=evidence.get('receipt_sha256') or record.get('verified') is not True
      or record.get('task_id')!=tid or record.get('claim')!=claim or record.get('pid')!=claim.get('pid')
      or record.get('source_sha256')!=PINS['owner_task_plans.py'] or record.get('started_at',0)<started
      or record.get('finished_at',0)<record.get('started_at',0)):return result
  proofs.append({'id':tid,'receipt_sha256':digest(raw),'scope':record['scope']})
 events=outbox.events_after(None,50)['events']
 matching=[row for row in events if (row.get('task') or {}).get('id') in task_ids and row.get('kind')=='task_verified']
 if {row['task']['id'] for row in matching}!=task_ids:return result
 result.update(verified=True,plan_id=parent.get('owner_plan_id'),proofs=proofs,
               owner_reports=[event_projection(row) for row in matching],unique_claims=len(all_claims),
               training_optimizer_update_proven=False,scope='BOUNDED_COMPONENT_AUDIT')
 return result

def main():
 request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
 if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_OWNER_CONTEXT')
 helper=load_helper();assets={name:bundle(name,pin) for name,pin in PINS.items()}
 target_receipt=STATE/('owner_dispatcher_upgrade_'+request+'.json')
 if target_receipt.exists():fail('HOLD_UPGRADE_REQUEST_ALREADY_EXECUTED')
 fd=os.open(STATE/'owner_maintenance.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True
 backup=ROOT/'backup/owner_dispatcher_upgrade'/request
 result={'schema':'NOX_OWNER_DISPATCHER_UPGRADE_V1','request':request,'source_sha':source,'started':time.time(),
  'state':'ADMITTING','source_pins':SOURCE_PINS,'dispatcher_before':OLD_DISPATCHER,'dispatcher_after':NEW_DISPATCHER,
  'steps':[],'weights_deleted':0,'training_started':False,'chat_restarted':False,'rollback':False}
 installed=[];controllers={};paused=[];queue_backup={};restarted_at=None;success=False
 def save():helper.atomic(target_receipt,json.dumps(result,indent=2).encode())
 def step(kind,value):result['steps'].append({'kind':kind,'data':value});save();emit(kind,value)
 def install(path,raw,allowed):
  previous=raw_file(path,16*1024*1024) if path.exists() or path.is_symlink() else None
  old=digest(previous) if previous is not None else None
  if old not in allowed:fail('HOLD_UPGRADE_EXISTING_ASSET_CHANGED')
  if previous==raw:return
  if previous is not None:helper.atomic(backup/str(path).lstrip('/'),previous)
  helper.atomic(path,raw);installed.append((path,previous,digest(raw)))
  if digest(raw_file(path,16*1024*1024))!=digest(raw):fail('HOLD_UPGRADE_READBACK')
  step('dispatcher_asset_installed',{'name':path.name,'before':old,'after':digest(raw)})
 try:
  if any((ROOT/name).exists() or (ROOT/name).is_symlink() for name in ('STOP','STOP.flag','stop.flag','.stop','state/STOP','program/STOP')):fail('HOLD_OWNER_STOP')
  if helper.health().get('8081')!=200:fail('HOLD_UPGRADE_CHAT_UNHEALTHY')
  policy=document(STATE/'task_boost_mode.json',16000)
  if policy.get('mode')!='TASK_BOOST' or policy.get('enabled') is not True or policy.get('training_allowed') is not False:fail('HOLD_UPGRADE_MODE_CHANGED')
  hold=raw_file(STATE/'TRAIN_HOLD.flag',4096)
  if not hold.startswith(b'OWNER_REQUESTED_TRAINING_HALT request=6902883046 source=df3a6005ca711ce44b606b864db154c396cbeb92'):fail('HOLD_UPGRADE_TRAINING_HOLD_CHANGED')
  result['training_hold_sha256']=digest(hold)
  for name,(path,pin) in CONTROLLERS.items():
   if digest(raw_file(path))!=pin:fail('HOLD_UPGRADE_NATIVE_CONTROL_CHANGED')
   controllers[name]=check_service(helper,name,path)
  if digest(raw_file(SCRIPTS/'owner_dispatcher_mentor.py'))!=SOURCE_PINS['owner_mentor']:fail('HOLD_UPGRADE_NATIVE_MENTOR_CHANGED')
  deadline=time.monotonic()+35
  while pending_claims() and time.monotonic()<deadline:time.sleep(1)
  if pending_claims():fail('HOLD_UPGRADE_ACTIVE_TASKS')
  for name,observed in controllers.items():
   if observed['state']=='RUNNING':
    rc=helper.command(['supervisorctl','stop',name],60)[0]
    stopped=helper.service_state(name)['state'] in ('STOPPED','EXITED')
    if stopped:paused.append(name)
    if rc or not stopped:fail('HOLD_UPGRADE_CONTROLLER_STOP')
    step('owned_controller_paused',{'service':name})
  if pending_claims():fail('HOLD_UPGRADE_QUEUE_RACE')
  for name,raw in assets.items():
   if name.endswith('.py'):install(SCRIPTS/name,raw,{None,PINS[name]})
   elif name=='download_manifest.json':install(ROOT/'config/owner_download_manifest.json',raw,{OLD_MANIFEST,PINS[name]})
   else:install(ROOT/'config'/name,raw,{None,PINS[name]})
  sys.path.insert(0,str(SCRIPTS))
  outbox=load_installed('owner_event_outbox');media=load_installed('owner_media_runtime')
  plans=load_installed('owner_task_plans');lifecycle=load_installed('owner_task_lifecycle');gateway=load_installed('owner_senior_gateway')
  original=raw_file(DISPATCHER);changed=media.patch_dispatcher_media(original.decode(),digest(original))
  changed=plans.patch_dispatcher(changed,digest(changed.encode()))
  changed=lifecycle.patch_dispatcher(changed,digest(changed.encode()),SOURCE_PINS)
  if digest(changed.encode())!=NEW_DISPATCHER:fail('HOLD_UPGRADE_TRANSFORM_CHANGED')
  install(DISPATCHER,changed.encode(),{OLD_DISPATCHER})
  status=gateway.initialize()
  step('senior_gateway_installed',{k:status[k] for k in ('state','models_consulted','research_state','providers','min_verified_providers') if k in status})
  # Do not execute the dispatcher in this installer: its real service owns all
  # callbacks, thread claims and task outcomes after the controlled restart.
  task=queue_task(request);state_path=STATE/'dispatcher/state.json';queue_path=STATE/'dispatcher/queue.jsonl'
  queue_backup[state_path]=raw_file(state_path,16*1024*1024)
  queue_backup[queue_path]=raw_file(queue_path,16*1024*1024) if queue_path.exists() else b''
  state=json.loads(queue_backup[state_path])
  if task['id'] in state['tasks']:fail('HOLD_UPGRADE_TASK_ID_COLLISION')
  state['tasks'][task['id']]=task
  for path,old in queue_backup.items():helper.atomic(backup/str(path).lstrip('/'),old)
  helper.atomic(state_path,json.dumps(state,ensure_ascii=False,indent=2).encode())
  before=queue_backup[queue_path]
  if before and not before.endswith(b'\n'):before+=b'\n'
  helper.atomic(queue_path,before+(json.dumps(task,ensure_ascii=False)+'\n').encode())
  step('native_autonomy_plan_queued',{'id':task['id'],'planned_branches':6,'global_worker_cap':6})
  restarted_at=time.time()
  for name,observed in controllers.items():
   if observed['state']=='RUNNING':
    rc=helper.command(['supervisorctl','start',name],40)[0]
    observed_state=helper.service_state(name)['state']
    step('controller_start_attempt',{'service':name,'returncode':rc,'state':observed_state})
    if rc or observed_state not in ('STARTING','RUNNING'):fail('HOLD_UPGRADE_CONTROLLER_START')
  if helper.service_state('nox-dispatcher-t855u')['state']!='RUNNING':fail('HOLD_UPGRADE_DISPATCHER_NOT_RUNNING')
  if helper.health().get('8081')!=200:fail('HOLD_UPGRADE_CHAT_HEALTH')
  result['state']='INSTALLED_NATIVE_ACCEPTANCE_PENDING';save()
  fcntl.flock(fd,fcntl.LOCK_UN);locked=False
  deadline=time.monotonic()+100;workers=None;proof=None
  while time.monotonic()<deadline:
   status_path=ROOT/'status/agents_t856u.json'
   try:
    current=document(status_path,262144);rows=current.get('workers') or []
    ids=[row.get('id') for row in rows]
    if status_path.stat().st_mtime>=restarted_at and len(rows)==6 and len(set(ids))==6:
     claims=[row['current_task']['id'] for row in rows if isinstance(row.get('current_task'),dict)]
     if len(claims)!=len(set(claims)):fail('HOLD_UPGRADE_DUPLICATE_TASK_CLAIM')
     workers={'ids':ids,'busy':len(claims),'mtime':status_path.stat().st_mtime}
    proof=verify_plan(request,restarted_at,outbox)
    if workers and proof['verified']:break
   except (FileNotFoundError,ValueError):pass
   if helper.service_state('nox-dispatcher-t855u')['state']!='RUNNING':fail('HOLD_UPGRADE_DISPATCHER_EXITED')
   time.sleep(2)
  result['workers']=workers;result['native_plan']=proof
  try:step('shared_memory_diagnostic',load_installed('owner_s03_diagnostic').run())
  except Exception as exc:step('shared_memory_diagnostic',{'state':'DIAGNOSTIC_PENDING','reason':safe(exc)})
  if not workers or not proof or not proof['verified']:fail('HOLD_UPGRADE_NATIVE_ACCEPTANCE_PENDING')
  if digest(raw_file(STATE/'TRAIN_HOLD.flag',4096))!=result['training_hold_sha256']:fail('HOLD_UPGRADE_HOLD_CHANGED')
  result['state']='SIX_WORKER_LIFECYCLE_MEDIA_PLANS_REPORTS_VERIFIED';success=True
 except Exception as exc:
  result['error']=safe(exc)
  if locked:
   # Roll back only before live claims are admitted. After release retain the
   # real task history and report the actual incomplete acceptance for repair.
   for name in paused:
    if helper.service_state(name)['state'] in ('RUNNING','STARTING'):helper.command(['supervisorctl','stop',name],60)
   for path,old in queue_backup.items():helper.atomic(path,old)
   for path,old,after in reversed(installed):
    if digest(raw_file(path,16*1024*1024))!=after:continue
    if old is None:path.unlink()
    else:helper.atomic(path,old)
   for name in paused:helper.command(['supervisorctl','start',name],40)
   result['rollback']=bool(installed);result['state']='HOLD_BEFORE_LIVE_CLAIMS'
  else:result['state']='INSTALLED_NATIVE_ACCEPTANCE_PENDING'
 finally:
  result['finished']=time.time();result['chat_after']=helper.health()
  result['dispatcher_service']=helper.service_state('nox-dispatcher-t855u')
  save();emit('native_dispatcher_upgrade_receipt',result);os.close(fd)
 if success:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
 return 0 if success else 2
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as exc:emit('dispatcher_upgrade_hold',{'reason':safe(exc)});raise SystemExit(2)
