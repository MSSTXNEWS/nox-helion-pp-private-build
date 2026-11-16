#!/usr/bin/env python3
"""Activate prepared S03 retrieval in the existing dispatcher and chat proxy.

The llama8081 process stays alive. Only identified NOX control services and the
idle proxy are briefly reloaded. Rollback is permitted only while the exclusive
maintenance lease still prevents new task claims. Memory/history is never
rolled back or deleted; this operation changes inspected source/config bytes.
"""
from __future__ import annotations

import ast
import base64
import fcntl
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import time
import types
import urllib.parse

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}

ROOT=Path('/root/nox');SCRIPTS=ROOT/'scripts';STATE=ROOT/'state'
HELPER_SHA='b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0'
PREPARE_GATEWAY_SHA='40caff3109111d971ff2d37cb81c0c2050ead08ae42d1f631a245778dd1a7a4d'
GATEWAY_SHA='1f1e3799aad2d74d5ce34cce98267bc1e2ce9e2f4fd9fcf6464e0166c6ef1127'
S03_BEFORE='82c592ea5a59281fb5fc1061d133ac4e149b8e95a6d0947a254882715cba7f91'
S03_AFTER='3ebdc3585f32bafbd0e1210ceee286b174a657c37696e16fce9fcafb57c43e10'
DISPATCHER_BEFORE='d4e665915ae2a9f0be8ae4603be3768467e0f88be876e408465c3a7cc156c243'
DISPATCHER_AFTER='934193bf4df6fef73293628793eaac1c10e923e15aea4b7a36c82335ad3795b8'
CONFIG_BEFORE='70d600e861a1e9908d06691790e54e2abcd814b460144ece2af3d2b6a54e0e80'
LIFECYCLE_BEFORE='020fcee6d1267189811c51da031761aa9ae681a3a2bcd567fbbc150c33db8605'
OUTBOX_BEFORE='af4edd2c34e4d46902ccf914b5be9c845a95d682d34f92a08cd69357c4b69c00'
LIFECYCLE_AFTER='909502a75799096e094a622639fe959ecfa835cc70db705a4062541940cea27e'
OUTBOX_AFTER='e15d458f9d1f03b23fcbf0267206621769ff92f2bfe00d3baf79217e2ab74a02'
SENIOR_SHA='1fd1556009ce62fa806bdee0a9a34577d276344e728fe9d94b33f44eb151346e'
OLD_SOURCE_PINS={
 'owner_mentor':'12211a29f77de8e5181d4dd78c35d5da2ed5de0dc6ea529149d32f0896809292',
 'owner_event_outbox':OUTBOX_BEFORE,
 'owner_media_runtime':'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5',
 'owner_task_plans':'7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773',
 'owner_senior_gateway':SENIOR_SHA,
}
NEW_SOURCE_PINS={**OLD_SOURCE_PINS,'owner_event_outbox':OUTBOX_AFTER,'owner_s03_gateway':GATEWAY_SHA}
MARKER='NOX_OWNER_S03_DISPATCHER_BIND_V1'
CONTROLLERS={
 'nox-dispatcher-t855u':(SCRIPTS/'nox_dispatcher_t855u.py',DISPATCHER_BEFORE),
 'nox-priority-scheduler':(SCRIPTS/'nox_priority_scheduler.py','5decaeba7bc1d329abbb627861cd03d99b8150136e98d0e2facd8fcb8e29f45a'),
 'nox-selfheal':(Path('/root/nox_selfheal.py'),'84a841854e25e94a91d1582106ce2825287e631c068775529790f9843add3538'),
}
PROXY=SCRIPTS/'chat_proxy.py'
PYTHON='/root/nox/venv/bin/python'
PUBLIC_QUERY='Как NOX сохраняет историю разговоров и воспоминания?'


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def safe(exc):
    value=str(exc);return value if re.fullmatch('HOLD_[A-Z0-9_]+',value) else type(exc).__name__
def emit(kind,value):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},separators=(',',':')),flush=True)


def read(path,limit=1024*1024):
    path=Path(path)
    if any(item.is_symlink() for item in (*path.parents,path)):fail('HOLD_S03_ACTIVATION_SYMLINK')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>limit:fail('HOLD_S03_ACTIVATION_FILE_SCOPE')
        raw=stream.read(limit+1)
        if len(raw)>limit:fail('HOLD_S03_ACTIVATION_FILE_SCOPE')
        return raw


def document(path,limit=1024*1024):
    value=json.loads(read(path,limit))
    if not isinstance(value,dict):fail('HOLD_S03_ACTIVATION_JSON')
    return value


def bundle(name,pin):
    raw=base64.b64decode(BUNDLE.get(name,''),validate=True)
    if digest(raw)!=pin:fail('HOLD_S03_ACTIVATION_BUNDLE_PIN')
    compile(raw,name,'exec');return raw


def module(name,raw,path=None):
    value=types.ModuleType(name);value.__file__=str(path or SCRIPTS/(name+'.py'))
    sys.modules[name]=value;exec(compile(raw,value.__file__,'exec'),value.__dict__);return value


def transform_dispatcher(source,expected_sha=DISPATCHER_BEFORE):
    if digest(source.encode())!=expected_sha or MARKER in source:fail('HOLD_S03_DISPATCHER_PREIMAGE')
    calls=[node for node in ast.walk(ast.parse(source)) if isinstance(node,ast.Call)
           and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name)
           and node.func.value.id=='owner_task_lifecycle' and node.func.attr=='bind_dispatcher']
    if len(calls)!=1 or len(calls[0].args)!=2 or ast.literal_eval(calls[0].args[1])!=OLD_SOURCE_PINS:
        fail('HOLD_S03_OLD_LIFECYCLE_BINDING')
    old=ast.get_source_segment(source,calls[0])
    if source.count(old)!=1:fail('HOLD_S03_LIFECYCLE_CALL_COUNT')
    source=source.replace(old,'owner_task_lifecycle.bind_dispatcher(globals(), '+repr(NEW_SOURCE_PINS)+')',1)
    anchor='# NOX_OWNER_TASK_LIFECYCLE_BIND_V1\n'
    if source.count(anchor)!=1:fail('HOLD_S03_DISPATCHER_ANCHOR')
    addition=('# '+MARKER+'\nimport owner_s03_gateway\n'
              "LOCKS['shared_memory_index'] = threading.Lock()\n"
              'owner_s03_gateway.bind_dispatcher(globals())\n\n')
    result=source.replace(anchor,addition+anchor,1)
    compile(result,'nox_dispatcher_t855u.py','exec')
    if expected_sha==DISPATCHER_BEFORE and digest(result.encode())!=DISPATCHER_AFTER:fail('HOLD_S03_DISPATCHER_TRANSFORM_CHANGED')
    return result


def verify_prepare(path,expected_sha,gateway):
    raw=read(path,512*1024)
    if digest(raw)!=expected_sha:fail('HOLD_S03_PREPARE_RECEIPT_PIN')
    value=json.loads(raw)
    if (not isinstance(value,dict) or value.get('schema')!='NOX_OWNER_S03_PREPARE_V1'
            or value.get('state')!='HISTORY_AND_INDEX_PREPARED' or value.get('gateway_sha256')!=PREPARE_GATEWAY_SHA
            or value.get('s03_before_sha256')!=S03_BEFORE or value.get('s03_source_changed') is not False
            or value.get('private_text_exported') is not False
            or value.get('training_examples_accepted')!=0
            or not isinstance(value.get('status'),dict) or value['status'].get('stale_embeddings')!=0
            or type(value['status'].get('current_embeddings')) is not int or value['status']['current_embeddings']<1
            or (value.get('synthetic_retrieval_acceptance') or {}).get('state')!='SYNTHETIC_SEMANTIC_FIXTURES_VERIFIED'):
        fail('HOLD_S03_PREPARE_NOT_VERIFIED')
    source=read(SCRIPTS/'s03_memory.py')
    if digest(source)!=S03_BEFORE:fail('HOLD_S03_SOURCE_CHANGED')
    updated=gateway.patch_s03(source.decode())
    if digest(updated.encode())!=value.get('s03_after_activation_sha256') or digest(updated.encode())!=S03_AFTER:
        fail('HOLD_S03_PREDICTED_SOURCE_MISMATCH')
    return value,updated.encode()


def local_json(port,path,timeout=5,limit=256000):
    client=http.client.HTTPConnection('127.0.0.1',port,timeout=timeout)
    try:
        client.request('GET',path,headers={'Connection':'close'})
        response=client.getresponse()
        if response.status!=200:fail('HOLD_S03_LOCAL_HTTP')
        raw=response.read(limit+1)
        if len(raw)>limit:fail('HOLD_S03_LOCAL_HTTP_BUDGET')
        return json.loads(raw)
    finally:client.close()


def slots_idle():
    rows=local_json(8081,'/slots')
    return isinstance(rows,list) and len(rows)==6 and all(isinstance(row,dict) and not row.get('is_processing',row.get('processing',False)) for row in rows)


def model_process(helper):
    found=[]
    for row in helper.process_table().values():
        argv=row['argv']
        if any(arg=='--port' and index+1<len(argv) and argv[index+1]=='8081' for index,arg in enumerate(argv)):
            if '/root/nox/models/current.gguf' in argv and row.get('state')!='Z':found.append(row)
    if len(found)!=1:fail('HOLD_S03_MODEL_IDENTITY')
    return {key:found[0][key] for key in ('pid','starttime','pgrp')}


def service_identity(helper,name,path):
    observed=helper.service_state(name);config=helper.program_config(name)
    argv=shlex.split(config.get('command',''));bound=str(path) in argv
    for arg in argv:
        launcher=Path(arg)
        if (not bound and launcher.parent==Path('/opt/supervisor-scripts') and launcher.suffix=='.sh'
                and launcher.is_file() and str(path) in read(launcher,32000).decode()):bound=True
    if not bound:fail('HOLD_S03_OWNED_SERVICE_COMMAND')
    if observed['state']!='RUNNING':fail('HOLD_S03_OWNED_SERVICE_NOT_RUNNING')
    proc=helper.process(observed['pid'])
    if not proc or proc['service']!=name or str(path) not in proc['argv']:fail('HOLD_S03_OWNED_SERVICE_IDENTITY')
    if config.get('stopasgroup','').lower()=='true' or config.get('killasgroup','').lower()=='true':
        if any(row['service']!=name for row in helper.process_table().values() if row['pgrp']==proc['pgrp'] and row['state']!='Z'):
            fail('HOLD_S03_FOREIGN_SERVICE_GROUP')
    return observed


def queue_state():
    value=document(STATE/'dispatcher/state.json',16*1024*1024)
    if not isinstance(value.get('tasks'),dict):fail('HOLD_S03_QUEUE_SCHEMA')
    return value


def active_claims():return sum(isinstance(task,dict) and task.get('status')=='running' for task in queue_state()['tasks'].values())


def recall_projection(rows):
    if not isinstance(rows,list) or not 1<=len(rows)<=20:fail('HOLD_S03_LIVE_RECALL_SCHEMA')
    methods={name:sum(isinstance(row,dict) and row.get('how')==name for row in rows) for name in ('semantic','hybrid','fts','like','pin','recent')}
    if methods['pin']>2 or methods['semantic']+methods['hybrid']<1:fail('HOLD_S03_LIVE_SEMANTIC_RECALL')
    return {'state':'SEMANTIC_LEXICAL_BOUNDED_PINS','rows':len(rows),'methods':methods,
            'private_text_exported':False,'scope':'LIVE_EXISTING_S03_RECALL_ROUTE'}


SMOKE=r'''
import contextlib,hashlib,json,os,pathlib,sys
sys.path.insert(0,'/root/nox/scripts')
with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
    import chat_proxy
    assert chat_proxy.s03_recall.__module__=='owner_s03_gateway'
    assert chat_proxy.s03_fmt.__module__=='owner_s03_gateway'
    rows=chat_proxy.s03_recall('Как NOX сохраняет историю разговоров и воспоминания?',k=6)
print(json.dumps({'chat_alias_bound':True,'rows':len(rows),'semantic_matches':sum(row.get('how') in ('semantic','hybrid') for row in rows),'pin_count':sum(row.get('how')=='pin' for row in rows),'private_text_exported':False}))
'''


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    prepare_request=os.environ.get('NOX_S03_PREPARE_REQUEST','');prepare_sha=os.environ.get('NOX_S03_PREPARE_SHA256','')
    if (not request.isdigit() or not prepare_request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source)
            or not re.fullmatch('[a-f0-9]{64}',prepare_sha)):fail('HOLD_S03_ACTIVATION_CONTEXT')
    helper=module('owner_s03_activation_helper',bundle('owner_native_repair.py',HELPER_SHA))
    if digest(read(SCRIPTS/'owner_s03_gateway.py'))!=PREPARE_GATEWAY_SHA:fail('HOLD_S03_GATEWAY_SOURCE_PIN')
    raw_gateway=bundle('owner_s03_gateway.py',GATEWAY_SHA)
    gateway=module('owner_s03_gateway',raw_gateway)
    new_outbox=bundle('owner_event_outbox.py',OUTBOX_AFTER)
    new_lifecycle=bundle('owner_task_lifecycle.py',LIFECYCLE_AFTER)
    outbox=module('owner_event_outbox',new_outbox)
    lifecycle=module('owner_task_lifecycle',new_lifecycle)
    prepare,updated_s03=verify_prepare(STATE/'owner_s03'/('prepare_'+prepare_request+'.json'),prepare_sha,gateway)
    receipt=STATE/'owner_s03'/('activation_'+request+'.json')
    if receipt.exists():fail('HOLD_S03_ACTIVATION_REQUEST_REUSED')
    fd=os.open(gateway.plain(STATE/'owner_maintenance.lock'),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True
    backup=ROOT/'backup/owner_s03_activation'/request
    record={'schema':'NOX_OWNER_S03_ACTIVATION_V1','request':request,'source_sha':source,'started_at':time.time(),
            'prepare_request':prepare_request,'prepare_receipt_sha256':prepare_sha,'state':'ADMITTING',
            'installed_sources':[],'steps':[],'weights_deleted':0,'memory_records_deleted':0,
            'llama_restarted':False,'training_started':False,'private_text_exported':False,'rollback':False}
    installed=[];paused=[];queue_backup={};success=False;proxy_stopped=False
    def save():helper.atomic(receipt,json.dumps(record,indent=2).encode())
    def event(kind,value):record['steps'].append({'kind':kind,'data':value});save();emit(kind,value)
    def install(path,raw,before):
        previous=read(path,16*1024*1024)
        if digest(previous)!=before:fail('HOLD_S03_ACTIVATION_PREIMAGE_CHANGED')
        mode=path.stat().st_mode&0o777
        helper.atomic(backup/str(path).lstrip('/'),previous)
        helper.atomic(path,raw);os.chmod(path,mode);installed.append((path,previous,digest(raw),mode))
        if digest(read(path,16*1024*1024))!=digest(raw):fail('HOLD_S03_ACTIVATION_READBACK')
        record['installed_sources'].append({'name':path.name,'before':before,'after':digest(raw)})
        save()
    def stop(name):
        rc=helper.command(['supervisorctl','stop',name],45)[0]
        if helper.service_state(name)['state'] in ('STOPPED','EXITED'):paused.append(name)
        if rc or name not in paused:fail('HOLD_S03_SERVICE_STOP')
        event('s03_owned_service_paused',{'service':name})
    def start(name):
        rc=helper.command(['supervisorctl','start',name],35)[0]
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            if helper.service_state(name)['state']=='RUNNING':return
            time.sleep(.5)
        fail('HOLD_S03_SERVICE_RESTART')
    task_id='owner.memory.index.'+request
    try:
        save()
        if gateway.stop_active():fail('HOLD_S03_OWNER_STOP')
        if helper.health().get('8081')!=200:fail('HOLD_S03_CHAT_MODEL_UNHEALTHY')
        record['model_process_before']=model_process(helper)
        hold=read(STATE/'TRAIN_HOLD.flag',4096);record['training_hold_sha256']=digest(hold)
        if not hold.startswith(b'OWNER_REQUESTED_TRAINING_HALT request=6902883046 source=df3a6005ca711ce44b606b864db154c396cbeb92'):
            fail('HOLD_S03_TRAINING_STATE_CHANGED')
        for name,(path,pin) in CONTROLLERS.items():
            if digest(read(path))!=pin:fail('HOLD_S03_CONTROLLER_SOURCE_CHANGED')
            service_identity(helper,name,path)
        proxy_before=service_identity(helper,'nox-proxy',PROXY)
        record['proxy_source_sha256']=digest(read(PROXY))
        for name,pin in OLD_SOURCE_PINS.items():
            filename='owner_dispatcher_mentor.py' if name=='owner_mentor' else name+'.py'
            if digest(read(SCRIPTS/filename))!=pin:fail('HOLD_S03_EXISTING_BINDING_SOURCE_CHANGED')
        if digest(read(SCRIPTS/'owner_task_lifecycle.py'))!=LIFECYCLE_BEFORE:fail('HOLD_S03_LIFECYCLE_PREIMAGE')
        config_path=ROOT/'config/owner_task_lifecycle.json';config_raw=read(config_path,16000)
        if digest(config_raw)!=CONFIG_BEFORE:fail('HOLD_S03_LIFECYCLE_CONFIG_PREIMAGE')
        config=lifecycle.configure_shared_recall(json.loads(config_raw),digest(updated_s03),GATEWAY_SHA)
        dispatcher=transform_dispatcher(read(SCRIPTS/'nox_dispatcher_t855u.py').decode()).encode()
        # The senior module's strict config validator excludes credentials from
        # this file. Only one reviewed handler ID is appended, under its lock.
        senior=module('owner_senior_gateway',read(SCRIPTS/'owner_senior_gateway.py'))
        senior_path=ROOT/'config/owner_senior_gateway.json'
        senior_before=read(senior_path,16000);senior_config=senior._config()
        if not isinstance(senior_config,dict):fail('HOLD_S03_SENIOR_CONFIG_MISSING')
        if 'owner_memory_sync' not in senior_config['allowed_handlers']:
            senior_config['allowed_handlers'].append('owner_memory_sync')
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            if active_claims()==0 and slots_idle():break
            time.sleep(1)
        if active_claims() or not slots_idle():fail('HOLD_S03_ACTIVE_OWNER_WORK')
        for name in CONTROLLERS:stop(name)
        if active_claims():fail('HOLD_S03_QUEUE_CHANGED_DURING_PAUSE')
        # Retain the live proxy until all non-proxy source bytes are ready.
        # Explicit approved utility revision: same-descriptor hashing and
        # WAL-aware destination reserve. PREPARE provenance remains40caff.
        install(SCRIPTS/'owner_s03_gateway.py',raw_gateway,PREPARE_GATEWAY_SHA)
        install(SCRIPTS/'owner_event_outbox.py',new_outbox,OUTBOX_BEFORE)
        install(SCRIPTS/'owner_task_lifecycle.py',new_lifecycle,LIFECYCLE_BEFORE)
        install(SCRIPTS/'s03_memory.py',updated_s03,S03_BEFORE)
        install(config_path,json.dumps(config,indent=2).encode(),CONFIG_BEFORE)
        install(SCRIPTS/'nox_dispatcher_t855u.py',dispatcher,DISPATCHER_BEFORE)
        senior_lock=senior._lock()
        if senior_lock is None:fail('HOLD_S03_SENIOR_CONFIG_BUSY')
        try:install(senior_path,json.dumps(senior_config,indent=2).encode(),digest(senior_before))
        finally:senior._unlock(senior_lock)
        check=subprocess.run([PYTHON,'-I','-c',SMOKE],capture_output=True,timeout=15)
        if check.returncode or len(check.stdout)>16000:fail('HOLD_S03_PROXY_IMPORT_SMOKE')
        smoke=json.loads(check.stdout)
        if smoke.get('chat_alias_bound') is not True or smoke.get('semantic_matches',0)<1 or smoke.get('pin_count',99)>2:
            fail('HOLD_S03_PROXY_MEMORY_ALIAS')
        event('s03_proxy_source_smoke',smoke)
        if not slots_idle():fail('HOLD_S03_NEW_OWNER_GENERATION')
        stop('nox-proxy');proxy_stopped=True
        start('nox-proxy');proxy_stopped=False;record['proxy_restarted']=True
        if digest(read(PROXY))!=record['proxy_source_sha256']:fail('HOLD_S03_PROXY_SOURCE_RACE')
        live=local_json(8080,'/nox/s03/recall?q='+urllib.parse.quote(PUBLIC_QUERY)+'&k=6',timeout=8)
        event('s03_live_proxy_recall',recall_projection(live.get('items') if isinstance(live,dict) else None))
        memory=lifecycle.semantic_recall({'handler':'owner_memory_sync'})
        if memory.get('retrieval_kind')!='SEMANTIC_LEXICAL_BOUNDED_PINS' or memory.get('gateway_source_sha256')!=GATEWAY_SHA:
            fail('HOLD_S03_LIFECYCLE_MEMORY_ACCEPTANCE')
        event('s03_lifecycle_recall',{key:memory.get(key) for key in ('state','retrieval_kind','lexical_matches','semantic_matches','content_exported','source_sha256','gateway_source_sha256')})
        state_path=STATE/'dispatcher/state.json';queue_path=STATE/'dispatcher/queue.jsonl'
        queue_backup[state_path]=read(state_path,16*1024*1024)
        queue_backup[queue_path]=read(queue_path,16*1024*1024) if queue_path.exists() else b''
        queue=json.loads(queue_backup[state_path])
        if task_id in queue['tasks']:fail('HOLD_S03_ACTIVATION_TASK_EXISTS')
        task={'id':task_id,'handler':'owner_memory_sync','class':'background','lane':'background','priority':4,
              'title':'Verify shared semantic memory index','status':'pending','deps':[],'locks':['shared_memory_index'],
              'retries':0,'max_retries':3,'timeout_sec':45,'source':'NOX_OWNER_S03_ACTIVATION_V1',
              'owner_plan_id':'owner.memory.index','owner_system_task':True}
        queue['tasks'][task_id]=task
        for path,raw in queue_backup.items():helper.atomic(backup/str(path).lstrip('/'),raw)
        helper.atomic(state_path,json.dumps(queue,ensure_ascii=False,indent=2).encode())
        old=queue_backup[queue_path]
        if old and not old.endswith(b'\n'):old+=b'\n'
        helper.atomic(queue_path,old+(json.dumps(task,ensure_ascii=False)+'\n').encode())
        started=time.time()
        for name in CONTROLLERS:start(name)
        if model_process(helper)!=record['model_process_before'] or helper.health().get('8081')!=200:
            fail('HOLD_S03_LIVE_MODEL_CHANGED')
        if digest(read(STATE/'TRAIN_HOLD.flag',4096))!=record['training_hold_sha256']:fail('HOLD_S03_TRAINING_HOLD_CHANGED')
        record.update(state='ACTIVATED_BEFORE_LIVE_CLAIMS',source_pins=NEW_SOURCE_PINS,
                      lifecycle_config_sha256=digest(read(config_path,16000)),dispatcher_after_sha256=digest(dispatcher),
                      s03_after_sha256=digest(updated_s03),proxy_pid_before=proxy_before['pid'])
        save();fcntl.flock(fd,fcntl.LOCK_UN);locked=False
        # From here retain genuine task history; no automatic source rollback.
        deadline=time.monotonic()+55;proof=None;workers=None
        while time.monotonic()<deadline:
            task=queue_state()['tasks'].get(task_id,{})
            if task.get('status')=='done':proof=gateway.verify_success(task,task.get('result'))
            try:
                status_path=ROOT/'status/agents_t856u.json'
                status=document(status_path,262144);rows=status.get('workers',[])
                if status_path.stat().st_mtime>=started and len(rows)==6 and len({row.get('id') for row in rows})==6:
                    claims=[row['current_task']['id'] for row in rows if isinstance(row.get('current_task'),dict)]
                    if len(claims)!=len(set(claims)):fail('HOLD_S03_DUPLICATE_NATIVE_CLAIM')
                    workers={'configured':6,'observed':6,'unique_active_claims':len(claims)}
            except FileNotFoundError:pass
            if proof and workers:break
            time.sleep(1)
        record.update(native_index_proof=proof,workers=workers,model_process_after=model_process(helper))
        if not proof or not workers:fail('HOLD_S03_NATIVE_INDEX_ACCEPTANCE_PENDING')
        if record['model_process_after']!=record['model_process_before']:fail('HOLD_S03_MODEL_RESTARTED_EXTERNALLY')
        record['state']='LIVE_SHARED_SEMANTIC_MEMORY_AND_NATIVE_INDEX_VERIFIED';success=True
    except Exception as exc:
        record['reason']=safe(exc)
        if locked:
            # Only identified services are stopped; no generated shell, broad
            # signal, model stop or restoration of the live memory database.
            for name in paused:
                if helper.service_state(name)['state'] in ('RUNNING','STARTING'):
                    helper.command(['supervisorctl','stop',name],45)
            for path,raw in queue_backup.items():helper.atomic(path,raw)
            for path,raw,after,mode in reversed(installed):
                if digest(read(path,16*1024*1024))!=after:
                    record['rollback_source_conflict']=True;continue
                helper.atomic(path,raw);os.chmod(path,mode)
            if not record.get('rollback_source_conflict'):
                for name in dict.fromkeys(paused):
                    try:start(name)
                    except Exception:record['rollback_service_failure']=True
            record['rollback']=bool(installed)
            record['state']='HOLD_BEFORE_LIVE_CLAIMS'
        else:record['state']='ACTIVATED_NATIVE_ACCEPTANCE_PENDING'
    finally:
        record.update(finished_at=time.time(),health_after=helper.health(),
                      dispatcher_service=helper.service_state('nox-dispatcher-t855u'),
                      proxy_service=helper.service_state('nox-proxy'))
        save();emit('s03_activation_receipt',record);os.close(fd)
    if success:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:emit('s03_activation_hold',{'reason':safe(exc)});raise SystemExit(2)
