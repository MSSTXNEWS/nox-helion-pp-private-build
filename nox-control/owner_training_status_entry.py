#!/usr/bin/env python3
"""Install verified training facts into the current owner chat and V137 route.

Only an idle, identity-checked nox-proxy is reloaded. The current training
admission is an explicit sealed argument, never an invented success. All model,
training, dispatcher, memory and media sources are preserved dynamically.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

DEPLOY_SHA = 'f17e8f5337f84ea5a3466053e08a8625c31d9b4b31e3963feecec874f145db36'
EVIDENCE_ENTRY_SHA = '39b397bd07ca870a8b0ebb433c2eea7ee91738c99dcdd296f334340ec7dd660a'
STATUS_SHA = '1688fc70b8663434beed02b6d4488ca8e5f636af71aa8e5498e5606f2b69751a'
PREVIOUS_STATUS_SHA = 'feda14757700e4d0b10d7dcace3d1ff007539c2be2bd51d6a86f0ecde7f8c828'
LAST_INSTALLED_STATUS_SHA = '72732887e7bf4e4032cb99289b7620301ba48d04d583200464942ebffbd4ff2e'
BINDING_SHA = '91df0894f52e07ae36f6f05bcb17c846c1b06da88427f45bfe52faf8e50fc1fa'
STREAM_SHA = '5b7bafde0c25fa26d6b8f98dfbb4958f0faa42ee77292da561834a63097a2e8e'
EVIDENCE_SHA = 'ea66e05f30472b066444058ac18d0c7af74def410bde760396d1e2431161e8b2'
SCHEMA = 'NOX_OWNER_TRAINING_STATUS_BINDING_DEPLOY_V1'


def fail(code):
    raise RuntimeError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe(exc):
    code = str(exc)
    return code if re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]+', code) else 'HOLD_TRAINING_STATUS_INSTALL_'+type(exc).__name__.upper()


def bundle(name, pin):
    raw = base64.b64decode(BUNDLE.get(name+'.py', ''), validate=True)
    if not raw or len(raw) > 1_000_000 or digest(raw) != pin:
        fail('HOLD_TRAINING_STATUS_INSTALL_BUNDLE')
    return raw


def module(name, pin):
    raw = bundle(name, pin); value = types.ModuleType(name+'_install_reviewed')
    exec(compile(raw, '<'+name+'>', 'exec'), value.__dict__); value.BUNDLE = BUNDLE
    return value


def dependencies():
    deploy = module('owner_download_status_entry', DEPLOY_SHA)
    evidence = module('owner_chat_evidence_entry', EVIDENCE_ENTRY_SHA)
    status = module('owner_training_status', STATUS_SHA)
    binding = module('owner_training_status_binding', BINDING_SHA)
    return deploy, evidence, status, binding, deploy.helper_module()


def read_context(status):
    try:
        value = json.loads(os.environ.get('NOX_TRAINING_RECOVERY_CONTEXT', ''))
    except (ValueError, TypeError):
        fail('HOLD_TRAINING_STATUS_INSTALL_CONTEXT_REQUIRED')
    context = status.context_value(value)
    status.admission(context)
    return context


def sources(deploy, status, binding, context):
    rows = []
    for name, pin in (('owner_training_status.py', STATUS_SHA),
                      ('owner_training_status_binding.py', BINDING_SHA)):
        path = deploy.plain(deploy.SCRIPTS/name)
        old = deploy.read(path) if path.exists() else None
        allowed = {pin,PREVIOUS_STATUS_SHA,LAST_INSTALLED_STATUS_SHA} if name == 'owner_training_status.py' else {pin}
        if old is not None and digest(old) not in allowed:
            fail('HOLD_TRAINING_STATUS_INSTALL_MODULE_PREIMAGE')
        new = bundle(name[:-3], pin); compile(new, str(path), 'exec')
        rows.append({'path':path, 'old':old, 'new':new, 'changed':old != new})
    for name, transform in (('chat_proxy.py', binding.patch_proxy),
                            ('nox_v137_owner_self_observation.py', binding.patch_self_observation)):
        path = deploy.plain(deploy.SCRIPTS/name); old = deploy.read(path); new = transform(old)
        rows.append({'path':path, 'old':old, 'new':new, 'changed':old != new})
    path = deploy.plain(deploy.ROOT/'config/owner_training_status.json')
    old = deploy.read(path, 16384) if path.exists() else None
    if old is not None:
        prior = json.loads(old)
        if not isinstance(prior, dict) or set(prior) != {'schema','admission'} or prior['schema'] != status.CONFIG_SCHEMA:
            fail('HOLD_TRAINING_STATUS_INSTALL_CONFIG_PREIMAGE')
        status.context_value(prior['admission'])
    new = json.dumps({'schema':status.CONFIG_SCHEMA,'admission':context}, sort_keys=True, indent=2).encode()
    rows.append({'path':path, 'old':old, 'new':new, 'changed':old != new})
    return rows


def guards(deploy, evidence):
    value = evidence.guards(deploy)
    for name in ('owner_chat_stream.py','owner_chat_evidence.py','owner_training_disk_guard.py',
                 'owner_plan_native_actions.py','owner_media_training_handoff.py'):
        path = deploy.plain(deploy.SCRIPTS/name)
        value[str(path)] = digest(deploy.read(path)) if path.exists() else None
    for name in ('owner_media_training_handoff.json','owner_media_runtime.json'):
        path = deploy.plain(deploy.ROOT/'config'/name)
        value[str(path)] = digest(deploy.read(path)) if path.exists() else None
    if value[str(deploy.SCRIPTS/'owner_chat_stream.py')] != STREAM_SHA or value[str(deploy.SCRIPTS/'owner_chat_evidence.py')] != EVIDENCE_SHA:
        fail('HOLD_TRAINING_STATUS_INSTALL_SHARED_PIN')
    return value


def wait_idle(deploy, seconds=15):
    deadline = time.monotonic()+seconds
    while True:
        if deploy.stopped_by_owner():
            fail('HOLD_TRAINING_STATUS_INSTALL_GLOBAL_STOP')
        if deploy.slots_idle():
            return
        if time.monotonic() >= deadline:
            fail('WAIT_TRAINING_STATUS_INSTALL_OWNER_CHAT_ACTIVE')
        time.sleep(.5)


HTTP_PROBE = r'''
import contextlib,fcntl,http.cookiejar,ipaddress,json,os,socket,struct,sys,time,urllib.request,urllib.error
with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
 sys.path.insert(0,'/root/nox/scripts')
 import chat_proxy,owner_training_status as status,owner_training_status_binding as binding,nox_v137_owner_self_observation as observer
 context=json.loads(sys.stdin.buffer.read(16385))
 if status.context_value()!=context:raise RuntimeError('HOLD_TRAINING_STATUS_LIVE_CONTEXT')
 status.admission(context)
 if not getattr(observer,'_owner_training_status_bound',False) or not getattr(observer,'_owner_current_evidence_bound',False):
  raise RuntimeError('HOLD_TRAINING_STATUS_LIVE_OBSERVER_BINDING')
 ordinary=[{'role':'user','content':'17 * 19'}]
 if binding.augment_messages(ordinary,'17 * 19') is not ordinary:raise RuntimeError('HOLD_TRAINING_STATUS_ORDINARY_TURN')
 sample=binding.augment_messages([{'role':'system','content':'fixture'}],'Сколько подтверждённых обновлений optimizer сейчас у NOX?')
 if binding.MARKER not in sample[0]['content']:raise RuntimeError('HOLD_TRAINING_STATUS_MODEL_CONTEXT')
 password=chat_proxy._read_chat_password()
 if not isinstance(password,str) or len(password)<6:raise RuntimeError('HOLD_OWNER_SESSION')
 address=None
 for _,name in socket.if_nameindex():
  if name=='lo':continue
  try:
   with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
    info=fcntl.ioctl(sock.fileno(),0x8915,struct.pack('256s',name.encode()[:15]))
   candidate=socket.inet_ntoa(info[20:24])
   if not ipaddress.ip_address(candidate).is_loopback:address=candidate;break
  except OSError:pass
 if address is None:raise RuntimeError('HOLD_NONLOOPBACK')
 base='http://'+address+':8080';jar=http.cookiejar.CookieJar()
 client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
 anonymous=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 def request(opener,path,data=None):
  req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json','Origin':base})
  try:response=opener.open(req,timeout=15)
  except urllib.error.HTTPError as exc:response=exc
  with response:
   raw=response.read(262145)
   if len(raw)>262144:raise RuntimeError('HOLD_TRAINING_STATUS_LIVE_SIZE')
   return response.status,dict(response.headers),raw
 anonymous_code,_,_=request(anonymous,'/api/nox/self/observations')
 login,_,_=request(client,'/chat/login',{'password':password});password=None
 if login!=200 or not list(jar) or anonymous_code!=401:raise RuntimeError('HOLD_TRAINING_STATUS_LIVE_AUTH')
 code,headers,raw=request(client,'/api/nox/self/observations');value=json.loads(raw);training=value.get('training',{})
 if (code!=200 or value.get('read_only') is not True or not isinstance(training,dict)
     or type(training.get('positive_optimizer_steps_verified')) is not bool
     or training.get('current_model_merge_inclusion')!='NOT_VERIFIED'
     or 'verification_state' not in training or training.get('state')=='UNVERIFIED_ADMISSION'
     or not isinstance(training.get('observed_at'),(int,float)) or not -5 <= time.time()-training['observed_at'] <= 30
     or 'no-store' not in next((v for k,v in headers.items() if k.lower()=='cache-control'),'')):
  raise RuntimeError('HOLD_TRAINING_STATUS_LIVE_PROJECTION')
 inventory_code,_,raw=request(client,'/api/ui/downloads');inventory=json.loads(raw)
 if inventory_code!=200 or inventory.get('media',{}).get('verified_files')!=4 or inventory.get('drive_adapters',{}).get('verified_files')!=3:
  raise RuntimeError('HOLD_TRAINING_STATUS_INVENTORY_PRESERVATION')
 status.admission(context)
 result={'schema':'NOX_OWNER_TRAINING_STATUS_BINDING_ACCEPTANCE_V1','owner_http':code,'anonymous_http':anonymous_code,
  'nonloopback_peer':True,'training_projection':{k:training.get(k) for k in ('state','verification_state','positive_optimizer_steps_verified','optimizer_steps','global_step','failure_cause','reason')},
  'current_training_context_bound':True,'ordinary_turn_training_io':False,'v137_training_bound':True,'inventory_evidence_bound':True,
  'media_verified_files':4,'drive_verified_files':3,'model_message_context_verified':True,
  'new_model_generation_requested':False,'private_content_exported':False}
print(json.dumps(result,sort_keys=True))
'''


def live_probe(deploy, context):
    child = subprocess.run([deploy.PYTHON,'-B','-c',HTTP_PROBE], input=json.dumps(context).encode(),
        capture_output=True, timeout=65, env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    if child.returncode or len(child.stdout) > 16000:
        fail('HOLD_TRAINING_STATUS_INSTALL_PRIVATE_ACCEPTANCE_FAILED')
    try:
        value = json.loads(child.stdout)
    except (ValueError, UnicodeError):
        fail('HOLD_TRAINING_STATUS_INSTALL_ACCEPTANCE_SCHEMA')
    if not isinstance(value,dict) or value.get('schema') != 'NOX_OWNER_TRAINING_STATUS_BINDING_ACCEPTANCE_V1' or value.get('nonloopback_peer') is not True:
        fail('HOLD_TRAINING_STATUS_INSTALL_ACCEPTANCE_SCHEMA')
    return value


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID',''); source = os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not re.fullmatch('[0-9]{1,24}',request) or not re.fullmatch('[a-f0-9]{40}',source):
        fail('HOLD_TRAINING_STATUS_INSTALL_OWNER_CONTEXT')
    deploy,evidence,status,binding,helper = dependencies(); context = read_context(status)
    receipt = deploy.plain(deploy.STATE/('owner_training_status_binding_'+request+'.json'))
    if receipt.exists():
        fail('HOLD_TRAINING_STATUS_INSTALL_REQUEST_USED')
    record = {'schema':SCHEMA,'request':request,'source_sha':source,'started_at':time.time(),
        'state':'PREFLIGHT','training_admission':context,'proxy_restarted':False,'model_restarted':False,
        'training_control_performed':False,'weights_deleted':0,'private_content_exported':False,
        'installed':[],'rollback':False}
    changed = []; stopped = False; success = False
    def save():
        helper.atomic(receipt,json.dumps(record,sort_keys=True).encode())
    with ExitStack() as leases:
        leases.enter_context(deploy.lock(deploy.STATE/'media/controller.lock'))
        leases.enter_context(deploy.lock(deploy.STATE/'owner_maintenance.lock'))
        before = guards(deploy,evidence); model = deploy.model_identity(helper); proxy = deploy.proxy_identity(helper)
        record.update(preserved_sources_before=before,model_identity=model,training_before=evidence.training_observation(helper))
        try:
            if deploy.stopped_by_owner():
                fail('HOLD_TRAINING_STATUS_INSTALL_GLOBAL_STOP')
            rows = sources(deploy,status,binding,context); save()
            status.admission(context)
            if guards(deploy,evidence)!=before or deploy.model_identity(helper)!=model:
                fail('HOLD_TRAINING_STATUS_INSTALL_PREIMAGE_RACE')
            for row in rows:
                if row['changed'] and row['old'] is not None:
                    helper.atomic(deploy.plain(deploy.ROOT/'backup/owner_training_status_binding'/request/row['path'].name),row['old'])
            if any(row['changed'] for row in rows):
                wait_idle(deploy);status.admission(context)
                deploy.stop_proxy(helper,proxy);stopped=True
            for row in rows:
                if not row['changed']:
                    continue
                now=deploy.read(row['path']) if row['path'].exists() else None
                if now != row['old']:
                    fail('HOLD_TRAINING_STATUS_INSTALL_TARGET_CHANGED')
                helper.atomic(row['path'],row['new']);changed.append(row);os.chmod(row['path'],0o600)
                if deploy.read(row['path']) != row['new'] or row['path'].stat().st_mode & 0o777 != 0o600:
                    fail('HOLD_TRAINING_STATUS_INSTALL_READBACK')
                record['installed'].append({'name':row['path'].name,'sha256':digest(row['new'])});save()
            if stopped:
                deploy.start_proxy(helper);stopped=False;record['proxy_restarted']=True
            record['acceptance']=live_probe(deploy,context);status.admission(context)
            if guards(deploy,evidence)!=before or deploy.model_identity(helper)!=model:
                fail('HOLD_TRAINING_STATUS_INSTALL_PRESERVATION')
            record.update(state='LIVE_OWNER_TRAINING_EVIDENCE_BOUND',preservation_verified=True,
                          training_after=evidence.training_observation(helper));success=True
        except Exception as exc:
            record.update(state='HOLD_TRAINING_STATUS_BINDING_DEPLOY',reason=safe(exc))
            try:
                if changed:
                    # Detect a foreign edit before interrupting a healthy
                    # proxy for a rollback we can no longer perform safely.
                    if any(deploy.read(row['path']) != row['new'] for row in changed):
                        fail('HOLD_TRAINING_STATUS_INSTALL_ROLLBACK_TARGET_CHANGED')
                    current=helper.service_state('nox-proxy')['state']
                    if current=='RUNNING':
                        deploy.stop_proxy(helper,deploy.proxy_identity(helper));stopped=True
                    elif current in ('STOPPED','EXITED','FATAL'):
                        stopped=True
                    else:
                        fail('HOLD_TRAINING_STATUS_INSTALL_ROLLBACK_PROXY_STATE')
                    for row in reversed(changed):
                        if deploy.read(row['path']) != row['new']:
                            fail('HOLD_TRAINING_STATUS_INSTALL_ROLLBACK_TARGET_CHANGED')
                        if row['old'] is None:
                            row['path'].unlink()
                        else:
                            helper.atomic(row['path'],row['old'])
                    record['rollback']=True
                if stopped:
                    deploy.start_proxy(helper);stopped=False
                if changed:
                    record['rollback_verified']=(guards(deploy,evidence)==before and deploy.model_identity(helper)==model
                        and all((not row['path'].exists()) if row['old'] is None else deploy.read(row['path'])==row['old'] for row in changed))
            except Exception as rollback_exc:
                record.update(rollback_verified=False,rollback_reason=safe(rollback_exc))
        finally:
            record['finished_at']=time.time();save()
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':'training_status_binding','data':record},separators=(',',':')),flush=True)
    if success:
        print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'training_status_binding_hold','data':{'reason':safe(exc)}}),flush=True)
        raise SystemExit(2)
