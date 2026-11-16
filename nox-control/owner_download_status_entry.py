#!/usr/bin/env python3
"""Install the current download projection into the existing owner UI only."""
from __future__ import annotations

import base64
from contextlib import ExitStack, contextmanager
import fcntl
import hashlib
import http.client
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

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
SCRIPTS = ROOT/'scripts'
STATE = ROOT/'state'
SITE = ROOT/'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
PYTHON = '/root/nox/venv/bin/python'
HELPER_SHA = 'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0'
OLD = {'owner_chat_ui.py': '9726ffedf9bd7976488aecb69b951ce176a202be8508939176602d4480c11204',
       'owner-chat-ui.js': '02640c9bcba484e4160510f1be627bc11fdef3e444b06b10f363f4f926921bb3'}
NEW = {'owner_download_status.py': '574bd91bb072a626b32fc557299e245b61a8798204fffd690099ffd78fc09eda',
       'owner_chat_ui.py': '68db1c1ac73bb828f8041a7aaaf56f7df856084463ca05f3e852b4bd508ab08e',
       'owner-chat-ui.js': '83a28efd953f4e18e143f47d6c3987c63c18d04f3286e05dbd2b278ad1f13c70'}
CHAT_REQUEST = '6903791973'
CHAT_SOURCE = '0432d11f7485644af803bb7a821c0abfab12acb6'
HOLD_PREFIX = b'OWNER_REQUESTED_TRAINING_HALT request=6902883046 source=df3a6005ca711ce44b606b864db154c396cbeb92'


def fail(code):
    raise RuntimeError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def plain(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or any(item.is_symlink() for item in (path, *path.parents)):
        fail('HOLD_DOWNLOAD_STATUS_PATH')
    return path


def read(path, maximum=1024*1024):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum or before.st_uid != os.geteuid() or before.st_mode & 0o022:
            fail('HOLD_DOWNLOAD_STATUS_FILE')
        chunks = []; count = 0
        while True:
            part = os.read(fd, min(65536, maximum+1-count))
            if not part:
                break
            chunks.append(part); count += len(part)
            if count > maximum:
                fail('HOLD_DOWNLOAD_STATUS_FILE_SIZE')
        after = os.fstat(fd); current = path.stat(follow_symlinks=False)
        for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'):
            if getattr(before, key) != getattr(after, key) or getattr(before, key) != getattr(current, key):
                fail('HOLD_DOWNLOAD_STATUS_FILE_CHANGED')
        return b''.join(chunks)
    finally:
        os.close(fd)


@contextmanager
def lock(path):
    path = plain(path)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            fail('HOLD_DOWNLOAD_STATUS_LEASE')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail('WAIT_DOWNLOAD_STATUS_ACTIVE_OWNER_WORK')
        yield fd
    finally:
        os.close(fd)


def bundle(name, expected):
    raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
    if not raw or digest(raw) != expected:
        fail('HOLD_DOWNLOAD_STATUS_BUNDLE')
    return raw


def helper_module():
    raw = bundle('owner_native_repair.py', HELPER_SHA)
    module = types.ModuleType('owner_download_status_deploy_helper')
    exec(compile(raw, '<reviewed-owner-helper>', 'exec'), module.__dict__)
    return module


def sources():
    rows = []
    for name, pin in NEW.items():
        path = (SITE if name.endswith('.js') else SCRIPTS)/name
        raw = bundle(name, pin)
        if name.endswith('.py'):
            compile(raw, str(path), 'exec')
        old = read(path) if plain(path).exists() else None
        observed = digest(old) if old is not None else None
        if observed not in (OLD.get(name), pin) or (name in OLD and old is None):
            fail('HOLD_DOWNLOAD_STATUS_UNKNOWN_PREIMAGE')
        rows.append({'path': path, 'new': raw, 'old': old, 'changed': observed != pin})
    previous = {row['path'].name: row['old'] for row in rows}
    if (previous['owner_chat_ui.py'] is not None and digest(previous['owner_chat_ui.py']) == NEW['owner_chat_ui.py']
            and previous['owner_download_status.py'] is None):
        fail('HOLD_DOWNLOAD_STATUS_PARTIAL_PYTHON_INSTALL')
    return rows


def guards():
    paths = [ROOT/name for name in (
        'config/owner_download_manifest.json', 'state/TRAIN_HOLD.flag',
        'scripts/chat_proxy.py', 'scripts/nox_v29_chat_bridge.py', 'scripts/agent_loop.py',
        'scripts/owner_chat_stream.py', 'scripts/owner_media_runtime.py',
        'scripts/nox_dispatcher_t855u.py', 'scripts/owner_task_lifecycle.py', 'scripts/owner_event_outbox.py')]
    paths += [SITE/name for name in ('pc/resonance.html', 'nox-v135-resonance-owner-bridge.js', 'nox-v137-owner-self-status.js')]
    return {str(path): digest(read(path)) for path in paths}


def stopped_by_owner():
    return any(plain(path).exists() for path in [ROOT/name for name in (
        'STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')]+[Path('/workspace/NOX_STOP')])


def local_json(port, path):
    client = http.client.HTTPConnection('127.0.0.1', port, timeout=4)
    try:
        client.request('GET', path, headers={'Connection': 'close'})
        response = client.getresponse(); raw = response.read(256001)
        if response.status != 200 or len(raw) > 256000:
            fail('HOLD_DOWNLOAD_STATUS_LOCAL_HTTP')
        return json.loads(raw)
    finally:
        client.close()


def slots_idle():
    rows = local_json(8081, '/slots')
    if not isinstance(rows, list) or len(rows) != 6:
        return False
    for row in rows:
        if not isinstance(row, dict):
            return False
        flags = [row[key] for key in ('is_processing', 'processing') if key in row]
        if not flags or any(type(value) is not bool or value for value in flags):
            return False
    return True


def model_identity(helper):
    found = []
    for row in helper.process_table().values():
        argv = row['argv']
        if (row['state'] not in ('Z', 'X') and '/root/nox/models/current.gguf' in argv
                and any(arg == '--port' and i+1 < len(argv) and argv[i+1] == '8081' for i, arg in enumerate(argv))):
            found.append(row)
    if len(found) != 1:
        fail('HOLD_DOWNLOAD_STATUS_MODEL_IDENTITY')
    return {key: found[0][key] for key in ('pid', 'starttime', 'pgrp')}


def proxy_identity(helper):
    service = helper.service_state('nox-proxy')
    row = helper.process(service.get('pid')) if service.get('pid') else None
    config = helper.program_config('nox-proxy')
    if (service['state'] != 'RUNNING' or not row or row['service'] != 'nox-proxy'
            or str(SCRIPTS/'chat_proxy.py') not in row['argv'] or row['state'] in ('Z', 'X')
            or '/opt/supervisor-scripts/nox-proxy.sh' not in shlex.split(config.get('command', ''))):
        fail('HOLD_DOWNLOAD_STATUS_PROXY_IDENTITY')
    if config.get('stopasgroup') == 'true' or config.get('killasgroup') == 'true':
        if any(item['service'] != 'nox-proxy' for item in helper.process_table().values()
               if item['pgrp'] == row['pgrp'] and item['state'] not in ('Z', 'X')):
            fail('HOLD_DOWNLOAD_STATUS_FOREIGN_PROCESS_GROUP')
    return {key: row[key] for key in ('pid', 'starttime', 'pgrp')}


def stop_proxy(helper, expected):
    if proxy_identity(helper) != expected or not slots_idle():
        fail('WAIT_DOWNLOAD_STATUS_OWNER_CHAT_ACTIVE_OR_CHANGED')
    helper.command(['supervisorctl', 'stop', 'nox-proxy'], 35)
    if helper.service_state('nox-proxy')['state'] not in ('STOPPED', 'EXITED'):
        fail('HOLD_DOWNLOAD_STATUS_PROXY_STOP')


def start_proxy(helper):
    helper.command(['supervisorctl', 'start', 'nox-proxy'], 35)
    deadline = time.monotonic()+25
    while time.monotonic() < deadline:
        if helper.service_state('nox-proxy')['state'] == 'RUNNING' and helper.health().get('8080') == 200:
            return proxy_identity(helper)
        time.sleep(.5)
    fail('HOLD_DOWNLOAD_STATUS_PROXY_HEALTH')


API_PROBE = r'''
import contextlib,fcntl,hashlib,http.cookiejar,ipaddress,json,os,socket,struct,sys,urllib.request,urllib.error
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
 base='http://'+address+':8080'
 jar=http.cookiejar.CookieJar()
 client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
 anonymous=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 def request(opener,path,data=None,maximum=262144):
  req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
  try:response=opener.open(req,timeout=10)
  except urllib.error.HTTPError as exc:response=exc
  with response:
   raw=response.read(maximum+1)
   if len(raw)>maximum:raise RuntimeError('HOLD_RESPONSE_SIZE')
   return response.status,dict(response.headers),raw
 anonymous_status,_,_=request(anonymous,'/api/ui/downloads')
 login,_,_=request(client,'/chat/login',{'password':password});password=None
 if login!=200 or not list(jar):raise RuntimeError('HOLD_OFFICIAL_LOGIN')
 code,headers,raw=request(client,'/api/ui/downloads');value=json.loads(raw)
 asset,_,script=request(client,'/nox-web-v29/owner-chat-ui.js')
 if (anonymous_status!=401 or code!=200 or value.get('schema')!='NOX_OWNER_DOWNLOAD_INVENTORY_V1'
     or value.get('read_only') is not True or value.get('large_file_hashes_recomputed') is not False
     or value.get('media',{}).get('verified_files')!=4 or value.get('drive_adapters',{}).get('verified_files')!=3
     or asset!=200 or hashlib.sha256(script).hexdigest()!=sys.argv[1]
     or 'no-store' not in next((v for k,v in headers.items() if k.lower()=='cache-control'),'')):
  raise RuntimeError('HOLD_LIVE_DOWNLOAD_STATUS')
 result={'schema':value['schema'],'anonymous_http':anonymous_status,'owner_http':code,'nonloopback_peer':True,
  'media_verified_files':value['media']['verified_files'],'media_verified_bytes':value['media']['verified_bytes'],
  'drive_verified_files':value['drive_adapters']['verified_files'],'drive_verified_bytes':value['drive_adapters']['verified_bytes'],
  'large_file_hashes_recomputed':False,'selection_manifest_sha256':value['selection_manifest']['sha256'],
  'generation_verified':{k:value['media']['generation_acceptance'][k]['verified'] for k in ('image','video')},
  'private_content_exported':False,'ui_script_sha256':hashlib.sha256(script).hexdigest()}
print(json.dumps(result,sort_keys=True))
'''


def live_probe():
    value = subprocess.run([PYTHON, '-c', API_PROBE, NEW['owner-chat-ui.js']], capture_output=True,
                           timeout=45, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    if value.returncode or len(value.stdout) > 16000:
        fail('HOLD_DOWNLOAD_STATUS_LIVE_ACCEPTANCE')
    proof = json.loads(value.stdout)
    if not isinstance(proof, dict) or proof.get('nonloopback_peer') is not True:
        fail('HOLD_DOWNLOAD_STATUS_LIVE_ACCEPTANCE')
    return proof


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'[0-9]{1,24}', request) or not re.fullmatch(r'[a-f0-9]{40}', source):
        fail('HOLD_DOWNLOAD_STATUS_OWNER_CONTEXT')
    helper = helper_module(); rows = sources()
    old_chat = json.loads(read(STATE/('owner_chat_upgrade_'+CHAT_REQUEST+'.json')))
    if (old_chat.get('request') != CHAT_REQUEST or old_chat.get('source_sha') != CHAT_SOURCE
            or old_chat.get('state') != 'LIVE_RESONANCE_REAL_STREAM_S03_HISTORY_ACCEPTED'):
        fail('HOLD_DOWNLOAD_STATUS_ORIGINAL_CHAT_RECEIPT')
    receipt = plain(STATE/('owner_download_status_'+request+'.json'))
    if receipt.exists():
        fail('HOLD_DOWNLOAD_STATUS_REQUEST_ALREADY_RECORDED')
    record = {'schema': 'NOX_OWNER_DOWNLOAD_STATUS_DEPLOY_V1', 'request': request, 'source_sha': source,
              'started_at': time.time(), 'state': 'STARTING', 'model_restarted': False,
              'proxy_restarted': False, 'immutable_manifest_modified': False, 'rollback': False,
              'large_weights_hashed': False, 'private_content_exported': False, 'installed': []}
    changed = []; proxy_stopped = False; success = False
    def save():
        helper.atomic(receipt, json.dumps(record, sort_keys=True).encode())
    with ExitStack() as leases:
        # Do not interrupt a media generation by acquiring maintenance while it
        # is holding the existing controller lease.
        leases.enter_context(lock(STATE/'media/controller.lock'))
        leases.enter_context(lock(STATE/'owner_maintenance.lock'))
        before = guards(); model = model_identity(helper); proxy = proxy_identity(helper)
        record['model_identity'] = model
        try:
            if stopped_by_owner():
                fail('HOLD_DOWNLOAD_STATUS_OWNER_STOP')
            if not read(STATE/'TRAIN_HOLD.flag', 4096).startswith(HOLD_PREFIX):
                fail('HOLD_DOWNLOAD_STATUS_ORIGINAL_TRAINING_HOLD')
            save()
            # Reread known preimages inside the writer lease.
            rows = sources()
            restart = any(row['changed'] and row['path'].suffix == '.py' for row in rows)
            for row in rows:
                if row['changed'] and row['old'] is not None:
                    backup = plain(ROOT/'backup/owner_download_status'/request/row['path'].name)
                    helper.atomic(backup, row['old'])
            if restart:
                stop_proxy(helper, proxy); proxy_stopped = True
            for row in rows:
                if not row['changed']:
                    continue
                helper.atomic(row['path'], row['new']); os.chmod(row['path'], 0o644)
                changed.append(row)
                if digest(read(row['path'])) != NEW[row['path'].name]:
                    fail('HOLD_DOWNLOAD_STATUS_INSTALL_READBACK')
                record['installed'].append({'name': row['path'].name, 'sha256': NEW[row['path'].name]}); save()
            if restart:
                start_proxy(helper); proxy_stopped = False; record['proxy_restarted'] = True
            record['acceptance'] = live_probe()
            if guards() != before or model_identity(helper) != model:
                fail('HOLD_DOWNLOAD_STATUS_PRESERVATION')
            record['state'] = 'LIVE_CURRENT_DOWNLOAD_INVENTORY_VERIFIED'; success = True
        except Exception as exc:
            code = str(exc)
            record.update(state='HOLD_DOWNLOAD_STATUS_DEPLOY', reason=code if re.fullmatch(r'(?:HOLD|WAIT)_[A-Z0-9_]+', code)
                          else 'HOLD_DOWNLOAD_STATUS_'+type(exc).__name__.upper())
            try:
                if changed:
                    if any(row['path'].suffix == '.py' for row in changed):
                        current = helper.service_state('nox-proxy')['state']
                        if current == 'RUNNING':
                            stop_proxy(helper, proxy_identity(helper)); proxy_stopped = True
                        elif current in ('STOPPED', 'EXITED', 'FATAL'):
                            proxy_stopped = True
                        else:
                            fail('HOLD_DOWNLOAD_STATUS_ROLLBACK_PROXY_STATE')
                    for row in reversed(changed):
                        if digest(read(row['path'])) != NEW[row['path'].name]:
                            fail('HOLD_DOWNLOAD_STATUS_ROLLBACK_TARGET_CHANGED')
                        if row['old'] is not None:
                            helper.atomic(row['path'], row['old']); os.chmod(row['path'], 0o644)
                    record['rollback'] = True
                if proxy_stopped:
                    start_proxy(helper); proxy_stopped = False
                if changed:
                    record['rollback_verified'] = (guards() == before and model_identity(helper) == model
                        and all(row['old'] is None or read(row['path']) == row['old'] for row in changed))
            except Exception:
                record['rollback_verified'] = False
        finally:
            record['finished_at'] = time.time(); save()
    print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'download_status_deploy', 'data': record}, separators=(',', ':')), flush=True)
    if success:
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        code = str(exc)
        safe = code if re.fullmatch(r'(?:HOLD|WAIT)_[A-Z0-9_]+', code) else 'HOLD_DOWNLOAD_STATUS_'+type(exc).__name__.upper()
        print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'download_status_failure', 'data': safe}), flush=True)
        raise SystemExit(2)
