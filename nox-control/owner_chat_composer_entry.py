#!/usr/bin/env python3
"""Exact static UI fix for report overflow; no service or training restart.

HTTP/source acceptance is separate from the real browser geometry, stream,
history and active Stop proof in owner_chat_browser_qa.py.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

PRIMITIVES_SHA = 'f17e8f5337f84ea5a3466053e08a8625c31d9b4b31e3963feecec874f145db36'
GUARDS_SHA = '39b397bd07ca870a8b0ebb433c2eea7ee91738c99dcdd296f334340ec7dd660a'
OLD_JS = '728e458b54f7d7a606a85c7eeaec5c0b677324f688d62fcb90f2c0922a00dd47'
NEW_JS = 'dcb413249a8bc99b6acf5d701047fe44ee7a3d65f8c1efe7f7e108a981f9e043'
UI_PY_SHA = 'da2cea21d21d3c1129bcb6621cd5293469a085ad861924a8c5cc63981577a866'
PREVIOUS_REQUEST = '6905063285'
PREVIOUS_SOURCE = '432b6195e7a8e3e56b32b9abcfd258dfc21465ec'


def fail(code):
    raise RuntimeError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bundle(name, expected):
    raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
    if not raw or len(raw)>1_000_000 or digest(raw)!=expected:
        fail('HOLD_COMPOSER_BUNDLE_PIN')
    return raw


def dependencies():
    modules = []
    for name, pin in (('owner_download_status_entry.py', PRIMITIVES_SHA),
                      ('owner_chat_evidence_entry.py', GUARDS_SHA)):
        value = types.ModuleType('reviewed_'+name.removesuffix('.py'))
        exec(compile(bundle(name, pin), '<reviewed-composer-primitives>', 'exec'), value.__dict__)
        value.BUNDLE = BUNDLE
        modules.append(value)
    deploy, evidence = modules
    return deploy, evidence, deploy.helper_module()


def sources(deploy):
    path = deploy.plain(deploy.SITE/'owner-chat-ui.js')
    before = deploy.read(path)
    if digest(before) not in (OLD_JS, NEW_JS):
        fail('HOLD_COMPOSER_UNKNOWN_UI_PREIMAGE')
    after = bundle('owner-chat-ui.js', NEW_JS)
    return path, before, after


def guards(deploy, evidence):
    result = evidence.guards(deploy)
    result.pop(str(deploy.SITE/'owner-chat-ui.js'))
    if result.get(str(deploy.SCRIPTS/'owner_chat_ui.py')) != UI_PY_SHA:
        fail('HOLD_COMPOSER_UI_RENDERER_PIN')
    for name in ('chat_proxy.py', 'owner_chat_stream.py', 'owner_chat_evidence.py',
                 'nox_v137_owner_self_observation.py'):
        path = deploy.plain(deploy.SCRIPTS/name)
        result[str(path)] = digest(deploy.read(path))
    return result


HTTP_PROBE = r'''
import contextlib,fcntl,hashlib,http.cookiejar,ipaddress,json,os,socket,struct,sys,urllib.request,urllib.error
with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
 sys.path.insert(0,'/root/nox/scripts');import chat_proxy
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
  req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
  try:response=opener.open(req,timeout=12)
  except urllib.error.HTTPError as exc:response=exc
  with response:
   raw=response.read(262145)
   if len(raw)>262144:raise RuntimeError('HOLD_RESPONSE_SIZE')
   return response.status,raw
 anon,_=request(anonymous,'/api/ui/downloads')
 login,_=request(client,'/chat/login',{'password':password});password=None
 if login!=200 or not list(jar) or anon!=401:raise RuntimeError('HOLD_OFFICIAL_OWNER_SESSION')
 page_code,page=request(client,'/nox-web-v29/pc/resonance.html')
 asset_code,asset=request(client,'/nox-web-v29/owner-chat-ui.js')
 if (page_code!=200 or asset_code!=200 or hashlib.sha256(asset).hexdigest()!=sys.argv[1]
     or b'BOUNDED_REPORTS_SCROLL_V1' not in asset or b'RETURN_BANNER_INSET_V1' not in asset
     or b'/nox-web-v29/owner-chat-ui.js' not in page):raise RuntimeError('HOLD_COMPOSER_LIVE_DELIVERY')
 result={'nonloopback_peer':True,'anonymous_http':anon,'owner_page_http':page_code,'owner_script_http':asset_code,
   'ui_script_sha256':hashlib.sha256(asset).hexdigest(),'private_content_exported':False,
   'actual_browser_acceptance':False,'training_or_gpu_control_performed':False}
print(json.dumps(result,sort_keys=True))
'''


def live_probe(deploy, evidence):
    proof = evidence.child_json(deploy, HTTP_PROBE, [NEW_JS], timeout=65)
    if (proof.get('nonloopback_peer') is not True or proof.get('private_content_exported') is not False
            or proof.get('owner_page_http')!=200 or proof.get('owner_script_http')!=200
            or proof.get('ui_script_sha256')!=NEW_JS or proof.get('actual_browser_acceptance') is not False):
        fail('HOLD_COMPOSER_HTTP_ACCEPTANCE')
    return proof


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch('[0-9]{1,24}', request) or not re.fullmatch('[a-f0-9]{40}', source):
        fail('HOLD_COMPOSER_OWNER_CONTEXT')
    deploy, evidence, helper = dependencies()
    path, old, new = sources(deploy)
    prior = json.loads(deploy.read(deploy.STATE/('owner_chat_layout_'+PREVIOUS_REQUEST+'.json')))
    if (prior.get('request')!=PREVIOUS_REQUEST or prior.get('source_sha')!=PREVIOUS_SOURCE
            or prior.get('state')!='LAYOUT_SOURCE_AND_HTTP_VERIFIED_BROWSER_PENDING' or prior.get('rollback') is not False):
        fail('HOLD_COMPOSER_LAYOUT_RECEIPT')
    receipt = deploy.plain(deploy.STATE/('owner_chat_composer_'+request+'.json'))
    if receipt.exists():
        fail('HOLD_COMPOSER_REQUEST_ALREADY_RECORDED')
    record = {'schema':'NOX_OWNER_CHAT_COMPOSER_DEPLOY_V1','request':request,'source_sha':source,
        'started_at':time.time(),'state':'STARTING','proxy_restarted':False,'model_restarted':False,
        'training_control_performed':False,'protected_web29_modified':False,'rollback':False,
        'private_content_exported':False,'actual_browser_acceptance':False}
    changed = False; success = False
    def save():
        helper.atomic(receipt, json.dumps(record,sort_keys=True).encode())
    with ExitStack() as leases:
        leases.enter_context(deploy.lock(deploy.STATE/'media/controller.lock'))
        leases.enter_context(deploy.lock(deploy.STATE/'owner_maintenance.lock'))
        before = guards(deploy,evidence); model = deploy.model_identity(helper); proxy = deploy.proxy_identity(helper)
        record.update(preserved_sources=before,model_identity=model,proxy_identity=proxy,
                      training_before=evidence.training_observation(helper))
        try:
            if deploy.stopped_by_owner():fail('HOLD_COMPOSER_GLOBAL_STOP')
            save(); path,old,new = sources(deploy)
            if guards(deploy,evidence)!=before or deploy.model_identity(helper)!=model:
                fail('HOLD_COMPOSER_PREINSTALL_SOURCE_CHANGED')
            if old!=new:
                helper.atomic(deploy.plain(deploy.ROOT/'backup/owner_chat_composer'/request/path.name),old)
                helper.atomic(path,new);changed=True;os.chmod(path,0o644)
                if deploy.read(path)!=new:fail('HOLD_COMPOSER_INSTALL_READBACK')
            record['installed_js_sha256']=NEW_JS;save()
            record['http_acceptance']=live_probe(deploy,evidence)
            if (guards(deploy,evidence)!=before or deploy.model_identity(helper)!=model
                    or deploy.proxy_identity(helper)!=proxy):
                fail('HOLD_COMPOSER_PRESERVATION')
            record['training_after']=evidence.training_observation(helper)
            record.update(state='BOUNDED_REPORTS_SOURCE_AND_HTTP_VERIFIED_BROWSER_PENDING',preservation_verified=True)
            success=True
        except Exception as exc:
            code=str(exc)
            record.update(state='HOLD_COMPOSER_DEPLOY',reason=code if re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]+',code)
                          else 'HOLD_COMPOSER_'+type(exc).__name__.upper())
            if changed:
                try:
                    if deploy.read(path)!=new:fail('HOLD_COMPOSER_ROLLBACK_TARGET_CHANGED')
                    helper.atomic(path,old);os.chmod(path,0o644)
                    record.update(rollback=True,rollback_verified=deploy.read(path)==old)
                except Exception:
                    record['rollback_verified']=False
        finally:
            record['finished_at']=time.time();save()
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':'chat_composer_layout','data':record},separators=(',',':')),flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        code=str(exc)
        safe=code if re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]+',code) else 'HOLD_COMPOSER_'+type(exc).__name__.upper()
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'chat_composer_layout_failure','data':safe}),flush=True)
        raise SystemExit(2)
