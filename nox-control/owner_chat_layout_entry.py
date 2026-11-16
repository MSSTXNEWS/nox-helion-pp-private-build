#!/usr/bin/env python3
"""Narrow owner UI transition; preserved WEB29 assets and model stay unchanged.

This installer proves source/HTTP delivery only. Real pointer, streaming and
history acceptance remains the separate unchanged-purpose browser QA.
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

DEPLOY_HELPER_SHA = 'f17e8f5337f84ea5a3466053e08a8625c31d9b4b31e3963feecec874f145db36'
OLD = {'owner_chat_ui.py': '68db1c1ac73bb828f8041a7aaaf56f7df856084463ca05f3e852b4bd508ab08e',
       'owner-chat-ui.js': '83a28efd953f4e18e143f47d6c3987c63c18d04f3286e05dbd2b278ad1f13c70'}
NEW = {'owner_chat_ui.py': 'da2cea21d21d3c1129bcb6621cd5293469a085ad861924a8c5cc63981577a866',
       'owner-chat-ui.js': '728e458b54f7d7a606a85c7eeaec5c0b677324f688d62fcb90f2c0922a00dd47'}
PREVIOUS_REQUEST = '6904832882'
PREVIOUS_SOURCE = '2253e6d24458e992b49dd2051ad17f24c497971a'


def fail(code):
    raise RuntimeError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bundle(name, expected):
    raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
    if not raw or digest(raw) != expected:
        fail('HOLD_CHAT_LAYOUT_BUNDLE')
    return raw


def deploy_helper():
    raw = bundle('owner_download_status_entry.py', DEPLOY_HELPER_SHA)
    module = types.ModuleType('owner_layout_reviewed_deploy_helper')
    exec(compile(raw, '<reviewed-source-install-primitives>', 'exec'), module.__dict__)
    module.BUNDLE = BUNDLE
    return module


def sources(deploy):
    rows = []
    for name, pin in NEW.items():
        path = (deploy.SITE if name.endswith('.js') else deploy.SCRIPTS)/name
        old = deploy.read(path)
        observed = digest(old)
        if observed not in (OLD[name], pin):
            fail('HOLD_CHAT_LAYOUT_UNKNOWN_PREIMAGE')
        raw = bundle(name, pin)
        if name.endswith('.py'):
            compile(raw, str(path), 'exec')
        rows.append({'path': path, 'old': old, 'new': raw, 'changed': observed != pin})
    return rows


def guards(deploy):
    value = deploy.guards()
    for relative in ('pc/v24/nox-v24.css', 'pc/v25/nox-shell-v25.css',
                     'pc/v25/nox-shell-v25.js', 'pc/vendor/nox-liquid-glass/liquid-glass.css'):
        path = deploy.SITE/relative
        value[str(path)] = digest(deploy.read(path))
    for relative in ('scripts/owner_download_status.py', 'config/owner_task_lifecycle.json'):
        path = deploy.ROOT/relative
        value[str(path)] = digest(deploy.read(path))
    return value


HTTP_PROBE = r'''
import contextlib,fcntl,hashlib,html.parser,http.cookiejar,ipaddress,json,os,socket,struct,sys,urllib.request,urllib.error
class Links(html.parser.HTMLParser):
 def __init__(self):super().__init__();self.links=[];self.return_bar=False
 def handle_starttag(self,tag,attrs):
  item=dict(attrs)
  if tag=='link':self.links.append(item)
  if tag=='div' and 'nox-v28-pc-return' in item.get('class','').split():self.return_bar=True
with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
 sys.path.insert(0,'/root/nox/scripts')
 import chat_proxy
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
  try:response=opener.open(req,timeout=10)
  except urllib.error.HTTPError as exc:response=exc
  with response:
   raw=response.read(262145)
   if len(raw)>262144:raise RuntimeError('HOLD_RESPONSE_SIZE')
   return response.status,raw
 anon,_=request(anonymous,'/api/ui/downloads')
 login,_=request(client,'/chat/login',{'password':password});password=None
 if login!=200 or not list(jar):raise RuntimeError('HOLD_OFFICIAL_LOGIN')
 page_code,page=request(client,'/nox-web-v29/pc/resonance.html')
 asset_code,asset=request(client,'/nox-web-v29/owner-chat-ui.js')
 css_code,css=request(client,'/nox-web-v29/pc/v25/nox-shell-v25.css')
 parser=Links();parser.feed(page.decode('utf-8'))
 shell=[row for row in parser.links if row.get('href','').split('?',1)[0]=='/nox-web-v29/pc/v25/nox-shell-v25.css']
 marker=len(shell)==1 and shell[0].get('data-n25-css')=='1'
 if (anon!=401 or page_code!=200 or asset_code!=200 or css_code!=200 or not marker or not parser.return_bar
     or hashlib.sha256(asset).hexdigest()!=sys.argv[1]
     or hashlib.sha256(css).hexdigest()!=sys.argv[2]
     or b'RETURN_BANNER_INSET_V1' not in asset):raise RuntimeError('HOLD_LIVE_LAYOUT_DELIVERY')
 result={'anonymous_http':anon,'owner_page_http':page_code,'owner_script_http':asset_code,'shell_css_http':css_code,
  'nonloopback_peer':True,'existing_return_bar_preserved':True,'single_marked_shell_stylesheet':True,
  'ui_script_sha256':hashlib.sha256(asset).hexdigest(),'shell_css_sha256':hashlib.sha256(css).hexdigest(),
  'private_content_exported':False,'physical_browser_acceptance':False}
print(json.dumps(result,sort_keys=True))
'''


def live_probe(deploy):
    css = digest(deploy.read(deploy.SITE/'pc/v25/nox-shell-v25.css'))
    value = subprocess.run([deploy.PYTHON, '-c', HTTP_PROBE, NEW['owner-chat-ui.js'], css],
                           capture_output=True, timeout=65, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    if value.returncode or len(value.stdout) > 10000:
        fail('HOLD_CHAT_LAYOUT_HTTP_ACCEPTANCE')
    proof = json.loads(value.stdout)
    if not isinstance(proof, dict) or proof.get('nonloopback_peer') is not True or proof.get('single_marked_shell_stylesheet') is not True:
        fail('HOLD_CHAT_LAYOUT_HTTP_ACCEPTANCE')
    return proof


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'[0-9]{1,24}', request) or not re.fullmatch(r'[a-f0-9]{40}', source):
        fail('HOLD_CHAT_LAYOUT_OWNER_CONTEXT')
    deploy = deploy_helper(); helper = deploy.helper_module()
    sources(deploy)
    previous = json.loads(deploy.read(deploy.STATE/('owner_download_status_'+PREVIOUS_REQUEST+'.json')))
    if (previous.get('request') != PREVIOUS_REQUEST or previous.get('source_sha') != PREVIOUS_SOURCE
            or previous.get('state') != 'LIVE_CURRENT_DOWNLOAD_INVENTORY_VERIFIED'
            or previous.get('rollback') is not False):
        fail('HOLD_CHAT_LAYOUT_PREVIOUS_RECEIPT')
    receipt = deploy.plain(deploy.STATE/('owner_chat_layout_'+request+'.json'))
    if receipt.exists():
        fail('HOLD_CHAT_LAYOUT_REQUEST_ALREADY_RECORDED')
    record = {'schema': 'NOX_OWNER_CHAT_LAYOUT_DEPLOY_V1', 'request': request, 'source_sha': source,
              'started_at': time.time(), 'state': 'STARTING', 'model_restarted': False,
              'proxy_restarted': False, 'protected_web29_modified': False, 'rollback': False,
              'private_content_exported': False, 'installed': [], 'physical_browser_acceptance': False,
              'previous_request': PREVIOUS_REQUEST, 'previous_source': PREVIOUS_SOURCE}
    changed = []; proxy_stopped = False; success = False
    def save():
        helper.atomic(receipt, json.dumps(record, sort_keys=True).encode())
    with ExitStack() as leases:
        leases.enter_context(deploy.lock(deploy.STATE/'media/controller.lock'))
        leases.enter_context(deploy.lock(deploy.STATE/'owner_maintenance.lock'))
        before = guards(deploy); model = deploy.model_identity(helper); proxy = deploy.proxy_identity(helper)
        record['model_identity'] = model
        try:
            if deploy.stopped_by_owner():
                fail('HOLD_CHAT_LAYOUT_OWNER_STOP')
            if not deploy.read(deploy.STATE/'TRAIN_HOLD.flag', 4096).startswith(deploy.HOLD_PREFIX):
                fail('HOLD_CHAT_LAYOUT_ORIGINAL_TRAINING_HOLD')
            save(); rows = sources(deploy)
            restart = any(row['changed'] and row['path'].suffix == '.py' for row in rows)
            for row in rows:
                if row['changed']:
                    helper.atomic(deploy.plain(deploy.ROOT/'backup/owner_chat_layout'/request/row['path'].name), row['old'])
            if restart:
                deploy.stop_proxy(helper, proxy); proxy_stopped = True
            for row in rows:
                if not row['changed']:
                    continue
                helper.atomic(row['path'], row['new']); changed.append(row); os.chmod(row['path'], 0o644)
                if digest(deploy.read(row['path'])) != NEW[row['path'].name]:
                    fail('HOLD_CHAT_LAYOUT_INSTALL_READBACK')
                record['installed'].append({'name': row['path'].name, 'sha256': NEW[row['path'].name]}); save()
            if restart:
                deploy.start_proxy(helper); proxy_stopped = False; record['proxy_restarted'] = True
            record['acceptance'] = live_probe(deploy)
            if guards(deploy) != before or deploy.model_identity(helper) != model:
                fail('HOLD_CHAT_LAYOUT_PRESERVATION')
            record['state'] = 'LAYOUT_SOURCE_AND_HTTP_VERIFIED_BROWSER_PENDING'; success = True
        except Exception as exc:
            code = str(exc)
            record.update(state='HOLD_CHAT_LAYOUT_DEPLOY', reason=code if re.fullmatch(r'(?:HOLD|WAIT)_[A-Z0-9_]+', code)
                          else 'HOLD_CHAT_LAYOUT_'+type(exc).__name__.upper())
            try:
                if changed:
                    if any(row['path'].suffix == '.py' for row in changed):
                        current = helper.service_state('nox-proxy')['state']
                        if current == 'RUNNING':
                            deploy.stop_proxy(helper, deploy.proxy_identity(helper)); proxy_stopped = True
                        elif current in ('STOPPED', 'EXITED', 'FATAL'):
                            proxy_stopped = True
                        else:
                            fail('HOLD_CHAT_LAYOUT_ROLLBACK_PROXY_STATE')
                    for row in reversed(changed):
                        if digest(deploy.read(row['path'])) != NEW[row['path'].name]:
                            fail('HOLD_CHAT_LAYOUT_ROLLBACK_TARGET_CHANGED')
                        helper.atomic(row['path'], row['old']); os.chmod(row['path'], 0o644)
                    record['rollback'] = True
                if proxy_stopped:
                    deploy.start_proxy(helper); proxy_stopped = False
                if changed:
                    record['rollback_verified'] = (guards(deploy) == before and deploy.model_identity(helper) == model
                        and all(deploy.read(row['path']) == row['old'] for row in changed))
            except Exception:
                record['rollback_verified'] = False
        finally:
            record['finished_at'] = time.time(); save()
    print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'chat_layout_deploy', 'data': record}, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        code = str(exc)
        safe = code if re.fullmatch(r'(?:HOLD|WAIT)_[A-Z0-9_]+', code) else 'HOLD_CHAT_LAYOUT_'+type(exc).__name__.upper()
        print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'chat_layout_failure', 'data': safe}), flush=True)
        raise SystemExit(2)
