#!/usr/bin/env python3
"""Install shared current facts and the existing media queue into owner chat.

Only an idle proxy is restarted. Training, model, controller, S03 sources and
WEB29 assets are observed dynamically and are never stopped or rewritten.
Native acceptance uses one public inventory question; it does not enqueue a
GPU job while the trainer's first admitted steps are in progress.
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
PATCH_SHA = 'b67dbf89b6e6c397784326b14678b2105b03559cb465649eb74ca28ffa62c95d'
NEW = {'owner_chat_evidence.py': 'ea66e05f30472b066444058ac18d0c7af74def410bde760396d1e2431161e8b2',
       'owner_chat_stream.py': '5b7bafde0c25fa26d6b8f98dfbb4958f0faa42ee77292da561834a63097a2e8e'}
STATUS_SHA = '574bd91bb072a626b32fc557299e245b61a8798204fffd690099ffd78fc09eda'
RUNTIME_SHA = 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5'
PREVIOUS_REQUEST = '6904832882'
PREVIOUS_SOURCE = '2253e6d24458e992b49dd2051ad17f24c497971a'
SCHEMA = 'NOX_OWNER_CHAT_EVIDENCE_DEPLOY_V1'


def fail(code):
    raise RuntimeError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bundle(name, expected):
    raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
    if not raw or len(raw) > 1_000_000 or digest(raw) != expected:
        fail('HOLD_CHAT_EVIDENCE_BUNDLE')
    return raw


def module(name, raw):
    value = types.ModuleType(name)
    exec(compile(raw, '<'+name+'>', 'exec'), value.__dict__)
    return value


def dependencies():
    deploy = module('chat_evidence_install_primitives', bundle('owner_download_status_entry.py', DEPLOY_SHA))
    deploy.BUNDLE = BUNDLE
    patcher = module('chat_evidence_source_hooks', bundle('owner_chat_evidence_patch.py', PATCH_SHA))
    return deploy, patcher, deploy.helper_module()


def sources(deploy, patcher):
    rows = []
    for name, pin in NEW.items():
        path = deploy.plain(deploy.SCRIPTS/name)
        old = deploy.read(path) if path.exists() else None
        before = patcher.STREAM_BEFORE if name == 'owner_chat_stream.py' else None
        if (digest(old) if old is not None else None) not in (before, pin) or (before and old is None):
            fail('HOLD_CHAT_EVIDENCE_UNKNOWN_PREIMAGE')
        new = bundle(name, pin)
        compile(new, str(path), 'exec')
        rows.append({'path': path, 'old': old, 'new': new, 'changed': new != old})
    for name, transform in (('chat_proxy.py', patcher.patch_proxy),
                            ('nox_v137_owner_self_observation.py', patcher.patch_self_observation)):
        path = deploy.SCRIPTS/name; old = deploy.read(path); new = transform(old)
        rows.append({'path': path, 'old': old, 'new': new, 'changed': new != old})
    return rows


def guards(deploy):
    # Static sources are compared with the actual post-training-admission
    # preimages, not obsolete TASK_BOOST or TRAIN_HOLD pins. Mutable training
    # progress/optimizer files/STOP flags are never rewritten by this entry.
    required = ('config/owner_download_manifest.json', 'config/owner_task_lifecycle.json',
        'scripts/nox_v29_chat_bridge.py', 'scripts/agent_loop.py', 'scripts/slim_chat_t885u.py',
        'scripts/owner_chat_ui.py', 'scripts/owner_download_status.py', 'scripts/owner_media_runtime.py',
        'scripts/nox_dispatcher_t855u.py', 'scripts/owner_task_lifecycle.py', 'scripts/owner_event_outbox.py',
        'scripts/nox_autoscale_t877u.py', 'scripts/nox_priority_scheduler.py',
        'scripts/run_train_volta_t866u.sh', 'scripts/hybrid_training_entry.py',
        'scripts/train_qlora_35b_t866u.py', 'scripts/nox_tools.py')
    optional = ('scripts/owner_task_plans.py', 'scripts/owner_plan_native_actions.py',
        'scripts/owner_dispatcher_mentor.py', 'scripts/owner_s03_gateway.py', 'scripts/s03_memory.py',
        'scripts/owner_senior_gateway.py', 'config/owner_senior_gateway.json')
    result = {}
    for relative in required+optional:
        path = deploy.plain(deploy.ROOT/relative)
        result[str(path)] = digest(deploy.read(path)) if relative in required or path.exists() else None
    for path in (Path('/root/nox_selfheal.py'), Path('/etc/supervisor/conf.d/nox-train-volta-t866u.conf')):
        result[str(path)] = digest(deploy.read(path))
    for name in ('pc/resonance.html', 'pc/v24/nox-v24.css', 'pc/v25/nox-shell-v25.css',
                 'pc/v25/nox-shell-v25.js', 'pc/vendor/nox-liquid-glass/liquid-glass.css',
                 'nox-v135-resonance-owner-bridge.js', 'nox-v137-owner-self-status.js',
                 'owner-chat-ui.js', 'owner-presence.js'):
        path = deploy.SITE/name; result[str(path)] = digest(deploy.read(path))
    if result[str(deploy.SCRIPTS/'owner_download_status.py')] != STATUS_SHA or result[str(deploy.SCRIPTS/'owner_media_runtime.py')] != RUNTIME_SHA:
        fail('HOLD_CHAT_EVIDENCE_SHARED_RUNTIME_PIN')
    return result


def training_observation(helper):
    value = helper.service_state('nox-train-volta-t866u')
    pid = value.get('pid'); process = helper.process(pid) if type(pid) is int and pid > 0 else None
    owned = bool(process and process.get('service') == 'nox-train-volta-t866u')
    return {'state': value.get('state', 'UNKNOWN'), 'pid': pid,
            'starttime': process.get('starttime') if owned else None,
            'service_identity_observed': owned, 'control_action_performed': False}


REGISTRY_PROBE = r'''
import contextlib,hashlib,json,os,sys
with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
 sys.path.insert(0,'/root/nox/scripts')
 import nox_tools
 if nox_tools.__file__!='/root/nox/scripts/nox_tools.py':raise RuntimeError('HOLD_NATIVE_TOOLS_ORIGIN')
 payload=json.loads(sys.stdin.buffer.read(100001))
 raw=__import__('base64').b64decode(payload['source'],validate=True)
 if hashlib.sha256(raw).hexdigest()!=sys.argv[1]:raise RuntimeError('HOLD_NATIVE_REGISTRY_PROJECTOR')
 namespace={'__name__':'reviewed_registry_projection'};exec(compile(raw,'<registry-projector>','exec'),namespace)
 result=namespace['tool_registry_projection'](nox_tools.TOOLS)
print(json.dumps(result,sort_keys=True))
'''


def child_json(deploy, code, arguments=(), data=None, timeout=50):
    value = subprocess.run([deploy.PYTHON, '-B', '-c', code, *arguments], input=data,
        capture_output=True, timeout=timeout, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    # Exceptions/import logs may contain private configuration. They are never
    # returned or interpolated into the public maintenance receipt.
    if value.returncode or len(value.stdout) > 25000:
        fail('HOLD_CHAT_EVIDENCE_PRIVATE_CHILD_FAILED')
    try:
        proof = json.loads(value.stdout)
    except (ValueError, UnicodeError):
        fail('HOLD_CHAT_EVIDENCE_CHILD_SCHEMA')
    if not isinstance(proof, dict):
        fail('HOLD_CHAT_EVIDENCE_CHILD_SCHEMA')
    return proof


def registry(deploy, patcher):
    raw = bundle('owner_chat_evidence_patch.py', PATCH_SHA)
    proof = child_json(deploy, REGISTRY_PROBE, [PATCH_SHA],
        json.dumps({'source': base64.b64encode(raw).decode()}).encode(), timeout=25)
    names = proof.get('names')
    if not isinstance(names, list):
        fail('HOLD_CHAT_EVIDENCE_NATIVE_REGISTRY')
    checked = patcher.tool_registry_projection([{'function': {'name': name}} for name in names])
    if proof != checked or checked['reserved_names_free'] is not True:
        fail('HOLD_CHAT_EVIDENCE_NATIVE_REGISTRY_COLLISION')
    return checked


HTTP_PROBE = r'''
import contextlib,fcntl,hashlib,http.cookiejar,ipaddress,json,os,re,socket,struct,sys,time,urllib.request,urllib.error
with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
 sys.path.insert(0,'/root/nox/scripts')
 import chat_proxy,agent_loop,owner_chat_evidence as facts,owner_media_runtime as media,nox_v137_owner_self_observation as observer
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
 def request(opener,path,data=None,maximum=262144,stream=False):
  req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data,ensure_ascii=False).encode(),
    headers={'Content-Type':'application/json','Origin':base})
  try:response=opener.open(req,timeout=25)
  except urllib.error.HTTPError as exc:response=exc
  if stream:return response
  with response:
   raw=response.read(maximum+1)
   if len(raw)>maximum:raise RuntimeError('HOLD_RESPONSE_SIZE')
   return response.status,raw
 anon_download,_=request(anonymous,'/api/ui/downloads')
 anon_stream,_=request(anonymous,'/api/nox/chat/stream',{'message':'Что уже скачано?','history':[]})
 login,_=request(client,'/chat/login',{'password':password});password=None
 if login!=200 or not list(jar) or anon_download!=401 or anon_stream!=401:raise RuntimeError('HOLD_OFFICIAL_OWNER_AUTH')
 status,raw=request(client,'/api/ui/downloads');inventory=json.loads(raw)
 projected=facts.project(inventory)
 if status!=200 or projected['media']['verified_files']!=4 or projected['drive_adapters']['verified_files']!=3:
  raise RuntimeError('HOLD_LIVE_CURRENT_INVENTORY')
 observation_code,raw=request(client,'/api/nox/self/observations');observation=json.loads(raw)
 current=observation.get('download_observation',{})
 if observation_code!=200 or current.get('schema')!=facts.SCHEMA or current.get('media')!=projected['media'] or current.get('drive_adapters')!=projected['drive_adapters']:
  raise RuntimeError('HOLD_LIVE_SELF_OBSERVATION')
 prompt='Что уже скачано?';expected=facts.inventory_reply()
 create_code,raw=request(client,'/api/ui/memory/dialogs/create',{'title':'NOX current file evidence QA '+sys.argv[1],'confirmed':True})
 dialog=json.loads(raw).get('dialog_id')
 if create_code!=200 or not isinstance(dialog,str) or not re.fullmatch('[a-f0-9]{32}',dialog):raise RuntimeError('HOLD_SYNTHETIC_DIALOG')
 started=time.monotonic();first=None;answer='';done=None
 with request(client,'/api/nox/chat/stream',{'message':prompt,'history':[],'dialog_id':dialog},stream=True) as response:
  if response.status!=200:raise RuntimeError('HOLD_LIVE_STREAM_HTTP')
  for index,line in enumerate(response):
   if index>250 or len(line)>20000 or time.monotonic()-started>30:raise RuntimeError('HOLD_LIVE_STREAM_BOUND')
   row=json.loads(line);kind=row.get('type')
   if kind=='delta':
    part=row.get('text')
    if not isinstance(part,str):raise RuntimeError('HOLD_LIVE_DELTA_TYPE')
    answer+=part
    if len(answer)>10000:raise RuntimeError('HOLD_LIVE_ANSWER_SIZE')
    if part.strip() and first is None:first=round((time.monotonic()-started)*1000)
   elif kind=='error':raise RuntimeError('HOLD_LIVE_STREAM_ERROR')
   elif kind=='done':done=row;break
 total=round((time.monotonic()-started)*1000)
 if (answer!=expected or '4/4' not in answer or '3/3' not in answer or first is None or not isinstance(done,dict)
     or done.get('saved') is not True or done.get('owner_dialog_saved') is not True
     or done.get('s03_integrated') is not False or done.get('canonical_s03_write_verified') is not False
     or done.get('writer')!='V112_OWNER_DIALOG_WRITER' or done.get('dialog_id')!=dialog
     or any(not isinstance(done.get(k),str) or not re.fullmatch(r'[a-f0-9]{32}',done[k])
            for k in ('turn_id','receipt_id','lease_epoch'))
     or not isinstance(done.get('exchange_id'),str) or not 6<=len(done['exchange_id'])<=160
     or not isinstance(done.get('receipt_sha256'),str)
     or not re.fullmatch(r'[a-f0-9]{64}',done['receipt_sha256'])):
  raise RuntimeError('HOLD_LIVE_OWNER_DIALOG_RECEIPT')
 history_code,raw=request(client,'/api/ui/memory/dialogs/history?dialog_id='+dialog+'&limit=4')
 history=json.loads(raw);pair=history.get('messages',[])
 if (history_code!=200 or history.get('status')!='READY' or history.get('dialog_id')!=dialog
     or history.get('store_scope')!='OWNER_DIALOG_TABLES_ONLY'
     or history.get('canonical_s03_readback_verified') is not False
     or len(pair)!=2 or [(row.get('role'),row.get('content')) for row in pair]!=[('user',prompt),('assistant',answer)]):
  raise RuntimeError('HOLD_LIVE_OWNER_DIALOG_HISTORY_READBACK')
 runtime=facts._module('owner_media_runtime')
 binding=(runtime is media and callable(runtime.create_job) and callable(runtime.load_job)
  and agent_loop.owner_completion.__module__=='owner_chat_stream'
  and getattr(observer,'_owner_current_evidence_bound',False) is True
  and facts.explicit_media_request('Нарисуй синий круг на белом фоне')=={'kind':'image','prompt':'синий круг на белом фоне'}
  and facts.explicit_media_request('Создай видео: цветок на ветру')=={'kind':'video','prompt':'цветок на ветру'}
  and facts.explicit_media_request('Не создавай видео цветка') is None)
 if not binding:raise RuntimeError('HOLD_LIVE_MEDIA_QUEUE_BINDING')
 result={'schema':'NOX_OWNER_CHAT_EVIDENCE_ACCEPTANCE_V1','nonloopback_peer':True,
  'anonymous_download_http':anon_download,'anonymous_stream_http':anon_stream,'owner_http':200,
  'media_verified_files':4,'media_verified_bytes':projected['media']['verified_bytes'],
  'drive_verified_files':3,'drive_verified_bytes':projected['drive_adapters']['verified_bytes'],
  'generation_tests_verified':projected['media']['generation_test_verified'],
  'inventory_answer_sha256':hashlib.sha256(answer.encode()).hexdigest(),'inventory_answer_bytes':len(answer.encode()),
  'first_actual_delta_ms':first,'total_ms':total,'synthetic_owner_dialog_history_readback':True,
  'owner_dialog_store_scope':'OWNER_DIALOG_TABLES_ONLY','canonical_s03_readback_verified':False,
  'onehost_1a01_acceptance_state':'HOLD_CANONICAL_S03_WRITER_AND_READBACK_NOT_BOUND',
  'self_observation_shared_evidence':True,'model_prompt_evidence_hook_installed':True,
  'existing_media_queue_binding_verified':binding,'media_queue_proof_scope':'SOURCE_AND_IMPORTED_RUNTIME_BINDING_NO_NEW_JOB',
  'media_generation_requested':False,'training_or_gpu_control_performed':False,'private_content_exported':False}
print(json.dumps(result,sort_keys=True))
'''


def live_probe(deploy, request):
    proof = child_json(deploy, HTTP_PROBE, [request], timeout=75)
    if (proof.get('schema') != 'NOX_OWNER_CHAT_EVIDENCE_ACCEPTANCE_V1'
            or proof.get('nonloopback_peer') is not True or proof.get('private_content_exported') is not False
            or proof.get('synthetic_owner_dialog_history_readback') is not True
            or proof.get('owner_dialog_store_scope')!='OWNER_DIALOG_TABLES_ONLY'
            or proof.get('canonical_s03_readback_verified') is not False
            or proof.get('onehost_1a01_acceptance_state')!='HOLD_CANONICAL_S03_WRITER_AND_READBACK_NOT_BOUND'
            or proof.get('media_generation_requested') is not False
            or proof.get('existing_media_queue_binding_verified') is not True
            or proof.get('media_verified_files') != 4 or proof.get('drive_verified_files') != 3):
        fail('HOLD_CHAT_EVIDENCE_HTTP_ACCEPTANCE')
    return proof


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch('[0-9]{1,24}', request) or not re.fullmatch('[a-f0-9]{40}', source):
        fail('HOLD_CHAT_EVIDENCE_OWNER_CONTEXT')
    deploy, patcher, helper = dependencies()
    sources(deploy, patcher)
    prior = json.loads(deploy.read(deploy.STATE/('owner_download_status_'+PREVIOUS_REQUEST+'.json')))
    if (prior.get('request') != PREVIOUS_REQUEST or prior.get('source_sha') != PREVIOUS_SOURCE
            or prior.get('state') != 'LIVE_CURRENT_DOWNLOAD_INVENTORY_VERIFIED' or prior.get('rollback') is not False):
        fail('HOLD_CHAT_EVIDENCE_CURRENT_UI_RECEIPT')
    receipt = deploy.plain(deploy.STATE/('owner_chat_evidence_'+request+'.json'))
    if receipt.exists():
        fail('HOLD_CHAT_EVIDENCE_REQUEST_ALREADY_RECORDED')
    record = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'state': 'STARTING',
              'started_at': time.time(), 'proxy_restarted': False, 'model_restarted': False,
              'training_control_performed': False, 'gpu_job_requested': False, 'rollback': False,
              'immutable_manifest_modified': False, 'private_content_exported': False, 'installed': []}
    changed = []; stopped = False; success = False
    def save():
        helper.atomic(receipt, json.dumps(record, sort_keys=True).encode())
    with ExitStack() as leases:
        leases.enter_context(deploy.lock(deploy.STATE/'media/controller.lock'))
        leases.enter_context(deploy.lock(deploy.STATE/'owner_maintenance.lock'))
        before = guards(deploy); model = deploy.model_identity(helper); proxy = deploy.proxy_identity(helper)
        record['training_before'] = training_observation(helper)
        record['preserved_sources_before'] = before; record['model_identity'] = model
        try:
            if deploy.stopped_by_owner():
                fail('HOLD_CHAT_EVIDENCE_GLOBAL_STOP')
            save(); record['native_tool_registry'] = registry(deploy, patcher); rows = sources(deploy, patcher)
            if guards(deploy) != before or deploy.model_identity(helper) != model:
                fail('HOLD_CHAT_EVIDENCE_PREINSTALL_SOURCE_CHANGED')
            for row in rows:
                if row['changed'] and row['old'] is not None:
                    helper.atomic(deploy.plain(deploy.ROOT/'backup/owner_chat_evidence'/request/row['path'].name), row['old'])
            if any(row['changed'] for row in rows):
                deploy.stop_proxy(helper, proxy); stopped = True
            for row in rows:
                if not row['changed']:
                    continue
                helper.atomic(row['path'], row['new']); changed.append(row)
                # Proxy source may contain existing private configuration.
                # Preserve private mode for every Python source in this change.
                os.chmod(row['path'], 0o600)
                if deploy.read(row['path']) != row['new']:
                    fail('HOLD_CHAT_EVIDENCE_INSTALL_READBACK')
                record['installed'].append({'name': row['path'].name, 'sha256': digest(row['new'])}); save()
            if stopped:
                deploy.start_proxy(helper); stopped = False; record['proxy_restarted'] = True
            record['acceptance'] = live_probe(deploy, request)
            if guards(deploy) != before or deploy.model_identity(helper) != model:
                fail('HOLD_CHAT_EVIDENCE_PRESERVATION')
            record['training_after'] = training_observation(helper)
            record.update(state='LIVE_OWNER_FACTS_AND_MEDIA_QUEUE_BINDING_VERIFIED', preservation_verified=True)
            success = True
        except Exception as exc:
            code = str(exc)
            record.update(state='HOLD_CHAT_EVIDENCE_DEPLOY', reason=code if re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]+', code)
                          else 'HOLD_CHAT_EVIDENCE_'+type(exc).__name__.upper())
            try:
                if changed:
                    current = helper.service_state('nox-proxy')['state']
                    if current == 'RUNNING':
                        deploy.stop_proxy(helper, deploy.proxy_identity(helper)); stopped = True
                    elif current in ('STOPPED', 'EXITED', 'FATAL'):
                        stopped = True
                    else:
                        fail('HOLD_CHAT_EVIDENCE_ROLLBACK_PROXY_STATE')
                    for row in reversed(changed):
                        if deploy.read(row['path']) != row['new']:
                            fail('HOLD_CHAT_EVIDENCE_ROLLBACK_TARGET_CHANGED')
                        if row['old'] is not None:
                            helper.atomic(row['path'], row['old'])
                        else:
                            # Only this invocation's exact newly installed
                            # source file can be removed during its rollback.
                            row['path'].unlink()
                    record['rollback'] = True
                if stopped:
                    deploy.start_proxy(helper); stopped = False
                if changed:
                    record['rollback_verified'] = (guards(deploy) == before and deploy.model_identity(helper) == model
                        and all((not row['path'].exists()) if row['old'] is None else deploy.read(row['path']) == row['old'] for row in changed))
            except Exception:
                record['rollback_verified'] = False
        finally:
            record['finished_at'] = time.time(); save()
    print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'chat_current_evidence', 'data': record}, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        code = str(exc)
        safe = code if re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]+', code) else 'HOLD_CHAT_EVIDENCE_'+type(exc).__name__.upper()
        print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'chat_current_evidence_failure', 'data': safe}), flush=True)
        raise SystemExit(2)
