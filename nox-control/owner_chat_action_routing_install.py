#!/usr/bin/env python3
"""One exact owner stream source transition; native action acceptance is separate.

No tool, planner, model, training permission or configuration is created here.
The existing agent_loop import installs the replacement after a proxy-only reload.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
STATE = ROOT / 'state'
TARGET = SCRIPTS / 'owner_chat_stream.py'
AREA = ROOT / 'backup/owner_chat_action_routing'
PYTHON = '/root/nox/venv/bin/python'
OLD_SHA = '5b7bafde0c25fa26d6b8f98dfbb4958f0faa42ee77292da561834a63097a2e8e'
NEW_SHA = '79592f94c40cbe329491320487b07cfbb7823812c031f8b2067298cbbbf6c237'
CANDIDATE = 'owner_chat_stream_action_routing.py'
PINS = {
    'owner_download_status_entry.py': 'f17e8f5337f84ea5a3466053e08a8625c31d9b4b31e3963feecec874f145db36',
    'owner_native_repair.py': 'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0',
}
PROTECTED = {
    'chat_proxy.py': 'a427aa68ed7760380880c5d1c9ddb0714bef367ee5162a20602dbe43b6722d90',
    'agent_loop.py': '0ecec93bcf3239b7decc768862d27fbdc60fe2b613103f201406761bb4850aaa',
    'nox_v29_chat_bridge.py': '7669bf1c3158c0f30f0f4ee6302427e540618041c9a8c554320464045973dc6c',
    'owner_chat_evidence.py': 'ea66e05f30472b066444058ac18d0c7af74def410bde760396d1e2431161e8b2',
    'nox_tools.py': '2c17b7684275b532d4cc710322588ce178c9b23866630b11c778d1863bc448aa',
}
PRESERVED = (
    'state/owner_training_admission.json', 'scripts/run_train_volta_t866u.sh',
    'config/owner_training_status.json', 'config/owner_qwen_training_guard.json',
    'config/owner_qwen_media_handoff.json', 'config/owner_media_runtime.json',
    'config/owner_qwen_execution_revision.json', 'config/owner_hermes_warm.json',
    'scripts/qwen_student_training_entry.py', 'scripts/qwen_student_training_entry_revision.py',
    'scripts/owner_qwen_execution_revision.py', 'scripts/owner_training_status.py',
    'scripts/owner_qwen_training_guard.py', 'scripts/owner_qwen_media_handoff.py',
    'scripts/owner_qwen_media_guard.py', 'scripts/owner_qwen_handback_retry.py',
    'scripts/nox_dispatcher_t855u.py', 'scripts/owner_hermes_hydrate.py',
    'scripts/nox_admin.py',
    'state/TRAIN_HOLD.flag', 'state/TRAIN_PAUSE_REQUEST.flag', 'state/OWNER_MAINTENANCE.flag',
)
MODEL = {'pid': 7637, 'starttime': '149189867', 'pgrp': 7059}
SERVICE = 'nox-train-volta-t866u'
SCHEMA = 'NOX_OWNER_CHAT_ACTION_ROUTING_INSTALL_V1'


class InstallHold(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise InstallHold('HOLD_CHAT_ACTION_ROUTING_' + code)


def safe(exc):
    code = str(exc)
    return code if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,160}', code) else 'HOLD_CHAT_ACTION_ROUTING_' + type(exc).__name__.upper()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()


def plain(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and
            not any(p.is_symlink() for p in (path, *path.parents)), 'PATH')
    return path


def identity(info):
    # rename changes ctime. Identity here binds the original inode, bytes,
    # owner and mode; a full SHA is always checked alongside this tuple.
    return tuple(getattr(info, key) for key in
                 ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns'))


def read(path, maximum=1048576, expected=None):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and before.st_nlink == 1 and not stat.S_IMODE(before.st_mode) & 0o022
                and 0 <= before.st_size <= maximum, 'FILE_SCOPE')
        raw = source.read(maximum + 1)
        after = os.fstat(source.fileno()); named = path.stat(follow_symlinks=False)
        require(len(raw) == before.st_size and identity(before) == identity(after) == identity(named)
                and before.st_ctime_ns == after.st_ctime_ns == named.st_ctime_ns, 'FILE_CHANGED')
    require(expected is None or digest(raw) == expected, 'FILE_SHA')
    return raw, identity(before)


def sync_dir(path):
    fd = os.open(plain(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_directory(path):
    path = plain(path)
    if not path.exists():
        path.mkdir(mode=0o700); sync_dir(path.parent)
    row = path.stat(follow_symlinks=False)
    require(stat.S_ISDIR(row.st_mode) and row.st_uid == os.geteuid()
            and stat.S_IMODE(row.st_mode) == 0o700, 'PRIVATE_DIRECTORY')


def create(path, raw, mode=0o600):
    fd = os.open(plain(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), mode); stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        held = identity(os.fstat(stream.fileno()))
    sync_dir(path.parent)
    observed, actual = read(path, max(1, len(raw)))
    require(observed == raw and actual == held, 'PRIVATE_WRITE_READBACK')
    return held


def update_private(path, raw, previous):
    old, own = read(path)
    require(old == previous and stat.S_IMODE(path.stat().st_mode) == 0o600, 'RECEIPT_PREIMAGE')
    stage = path.with_name(path.name + '.next')
    staged = create(stage, raw)
    require(read(path) == (old, own), 'RECEIPT_CHANGED')
    os.replace(stage, path); sync_dir(path.parent)
    require(read(path) == (raw, staged), 'RECEIPT_READBACK')


def exchange(first, second):
    first, second = plain(first), plain(second)
    one = os.open(first.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    two = os.open(second.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        require(os.fstat(one).st_dev == os.fstat(two).st_dev, 'EXCHANGE_FILESYSTEM')
        function = getattr(ctypes.CDLL(None, use_errno=True), 'renameat2', None)
        require(function is not None, 'EXCHANGE_UNAVAILABLE')
        function.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        function.restype = ctypes.c_int
        if function(one, os.fsencode(first.name), two, os.fsencode(second.name), 2):
            raise OSError(ctypes.get_errno(), 'atomic source exchange failed')
    finally:
        os.close(two); os.close(one)


def classify_pair(staged, prepared):
    current, current_id = read(TARGET)
    backup, backup_id = read(staged)
    if (digest(current), current_id, digest(backup), backup_id) == (
            OLD_SHA, tuple(prepared['old_identity']), NEW_SHA, tuple(prepared['new_identity'])):
        return 'ORIGINAL'
    require((digest(current), current_id, digest(backup), backup_id) == (
        NEW_SHA, tuple(prepared['new_identity']), OLD_SHA, tuple(prepared['old_identity'])), 'FOREIGN_SOURCE_PAIR')
    return 'INSTALLED'


def apply_source(staged, prepared, record, save):
    require(classify_pair(staged, prepared) == 'ORIGINAL', 'SOURCE_PREIMAGE')
    record['exchange_attempted'] = True; save()
    exchange(TARGET, staged)
    record['source_changed'] = True
    sync_dir(TARGET.parent); sync_dir(staged.parent)
    require(classify_pair(staged, prepared) == 'INSTALLED', 'SOURCE_POSTIMAGE')
    save()


def restore_source(staged, prepared):
    state = classify_pair(staged, prepared)
    if state == 'INSTALLED':
        exchange(TARGET, staged); sync_dir(TARGET.parent); sync_dir(staged.parent)
    require(classify_pair(staged, prepared) == 'ORIGINAL', 'SOURCE_ROLLBACK')


def load(name, pin):
    encoded = BUNDLE.get(name)
    require(isinstance(encoded, str) and 0 < len(encoded) < 262144, 'BUNDLE')
    raw = base64.b64decode(encoded, validate=True)
    require(digest(raw) == pin, 'BUNDLE_PIN')
    module = types.ModuleType('_nox_action_routing_' + name.removesuffix('.py'))
    module.__file__ = str(SCRIPTS / name)
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def candidate():
    encoded = BUNDLE.get(CANDIDATE)
    require(isinstance(encoded, str) and 0 < len(encoded) < 65536, 'CANDIDATE_BUNDLE')
    raw = base64.b64decode(encoded, validate=True)
    require(digest(raw) == NEW_SHA, 'CANDIDATE_PIN')
    compile(raw, str(TARGET), 'exec')
    return raw


def gate():
    paths = [ROOT / name for name in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')]
    paths.append(Path('/workspace/NOX_STOP'))
    require(not any(os.path.lexists(path) for path in paths), 'GLOBAL_STOP')


def snapshots(helper):
    frozen = {name: digest(read(SCRIPTS / name, expected=pin)[0]) for name, pin in PROTECTED.items()}
    guarded = {}
    for name in PRESERVED:
        path = ROOT / name
        guarded[name] = digest(read(path)[0]) if os.path.lexists(path) else None
    require(all(guarded[name] is not None for name in (
        'state/owner_training_admission.json', 'scripts/run_train_volta_t866u.sh',
        'config/owner_training_status.json', 'scripts/nox_admin.py')), 'REQUIRED_PRESERVED_FILE')
    service = helper.service_state(SERVICE)
    require(service.get('state') in ('RUNNING', 'STOPPED', 'EXITED', 'FATAL'), 'TRAINING_SERVICE_UNSETTLED')
    rows = helper.process_table()
    relevant = [row for row in rows.values() if row.get('service') == SERVICE and row.get('state') not in ('Z', 'X')]
    if service['state'] == 'RUNNING':
        require(service.get('pid') in rows and any(row['pid'] == service['pid'] for row in relevant), 'TRAINING_PROCESS_UNREADABLE')
    else:
        require(not relevant and service.get('pid') is None, 'TRAINING_PROCESS_UNEXPECTED')
    processes = sorted([{'pid': row['pid'], 'ppid': row['ppid'], 'pgrp': row['pgrp'],
        'starttime': row['starttime'], 'cuda': row.get('cuda'), 'service': row.get('service'),
        'argv_sha256': digest(encode(row['argv']))} for row in relevant], key=lambda row: row['pid'])
    return {'fixed_sources': frozen, 'preserved_files': guarded,
            'training': {'state': service['state'], 'pid': service.get('pid'), 'observed_service_processes': processes},
            'process_inventory_scope': 'READABLE_EXISTING_TRAINING_SERVICE_PROCESSES_NOT_GLOBAL_PROCESS_COVERAGE'}


def protected_unchanged(helper, deploy, before):
    require(snapshots(helper) == before, 'PRESERVED_STATE_CHANGED')
    require(deploy.model_identity(helper) == MODEL, 'MAIN_MODEL_CHANGED')


def rollback_plan(helper, deploy, original_proxy, new_proxy, staged, prepared, changed):
    pair = classify_pair(staged, prepared)  # Before any service action.
    service = helper.service_state('nox-proxy')
    require(service['state'] in ('RUNNING', 'STOPPED', 'EXITED', 'FATAL'), 'ROLLBACK_PROXY_UNSETTLED')
    if service['state'] == 'RUNNING':
        current = deploy.proxy_identity(helper)
        require(current == original_proxy or new_proxy is not None and current == new_proxy, 'FOREIGN_PROXY')
        if pair == 'ORIGINAL':
            return {'stop': False, 'start': False, 'restore': False}
        return {'stop': True, 'start': True, 'restore': True, 'proxy': current}
    require(service['state'] != 'FATAL' or changed.get('proxy_start_attempted') is True, 'FOREIGN_FATAL_PROXY')
    return {'stop': False, 'start': True, 'restore': pair == 'INSTALLED'}


PROBE = r'''
import contextlib,fcntl,hashlib,http.cookiejar,ipaddress,json,os,socket,struct,sys,urllib.request,urllib.error
with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
 sys.path.insert(0,'/root/nox/scripts')
 raw=open('/root/nox/scripts/owner_chat_stream.py','rb').read(65537)
 if hashlib.sha256(raw).hexdigest()!=sys.argv[1]:raise RuntimeError('HOLD_ROUTING_IMPORT_PIN')
 import owner_chat_stream as stream
 import agent_loop
 if agent_loop.owner_completion.__module__!='owner_chat_stream':raise RuntimeError('HOLD_ROUTING_IMPORT_BINDING')
 if not stream.action_request('Оптимизируй сервер и GPU, скачай все веса') or stream.action_request('Почему GPU не работает?') or stream.status_needs_model('Статус GPU'):raise RuntimeError('HOLD_ROUTING_PREDICATE_SMOKE')
 import chat_proxy
 password=chat_proxy._read_chat_password()
 if not isinstance(password,str) or len(password)<6:raise RuntimeError('HOLD_OWNER_SESSION')
 address=None
 for _,name in socket.if_nameindex():
  if name=='lo':continue
  try:
   with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
    info=fcntl.ioctl(sock.fileno(),0x8915,struct.pack('256s',name.encode()[:15]))
   value=socket.inet_ntoa(info[20:24])
   if not ipaddress.ip_address(value).is_loopback:address=value;break
  except OSError:pass
 if address is None:raise RuntimeError('HOLD_NONLOOPBACK')
 base='http://'+address+':8080';jar=http.cookiejar.CookieJar()
 owner=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
 anonymous=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 def request(opener,path,data=None):
  req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
  try:r=opener.open(req,timeout=5)
  except urllib.error.HTTPError as exc:r=exc
  with r:
   raw=r.read(262145)
   if len(raw)>262144:raise RuntimeError('HOLD_RESPONSE_SIZE')
   return r.status
 anon=request(anonymous,'/api/ui/downloads');login=request(owner,'/chat/login',{'password':password});password=None
 code=request(owner,'/api/ui/downloads')
 if (anon,login,code)!=(401,200,200) or not list(jar):raise RuntimeError('HOLD_OWNER_AUTH')
 result={'anonymous_http':anon,'login_http':login,'owner_http':code,'nonloopback_peer':True,
  'module_binding_verified':True,'predicate_smoke_verified':True,'generation_posts':0,
  'tool_dispatch_performed':False,'optimization_execution_verified':False,'private_content_exported':False}
print(json.dumps(result,sort_keys=True))
'''


def probe():
    process = subprocess.run([PYTHON, '-B', '-c', PROBE, NEW_SHA], capture_output=True, timeout=25,
                             env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    require(process.returncode == 0 and len(process.stdout) <= 4096, 'IMPORT_AND_AUTH_PROBE')
    result = json.loads(process.stdout)
    require(isinstance(result, dict) and result.get('module_binding_verified') is True
            and result.get('generation_posts') == 0 and result.get('tool_dispatch_performed') is False,
            'PROBE_SCOPE')
    return result


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', ''); source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    record = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'state': 'PREFLIGHT',
              'started_at': time.time(), 'source_changed': False, 'exchange_attempted': False,
              'proxy_stop_attempted': False, 'proxy_start_attempted': False, 'proxy_restarted': False,
              'model_restarted': False, 'training_actions': 0, 'flags_or_admission_modified': False,
              'new_tool_or_permission_added': False, 'generation_posts': 0,
              'action_execution_acceptance_verified': False, 'rollback_verified': False,
              'private_content_exported': False}
    journal = None; previous = None; ready = False; new_proxy = None; success = False
    original_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGALRM, signal.SIGTERM)}
    original_timer = signal.getitimer(signal.ITIMER_REAL); began = time.monotonic()
    def interrupted(*_):
        raise InstallHold('HOLD_CHAT_ACTION_ROUTING_DEADLINE')
    def save():
        nonlocal previous
        if journal is None:
            return
        raw = encode(record); path = journal / 'result.json'
        if previous is None:
            create(path, raw)
        else:
            update_private(path, raw, previous)
        previous = raw
    with ExitStack() as stack:
        try:
            require(bool(re.fullmatch('[0-9]{1,24}', request)) and bool(re.fullmatch('[a-f0-9]{40}', source)), 'OWNER_CONTEXT')
            raw = candidate(); deploy = load('owner_download_status_entry.py', PINS['owner_download_status_entry.py'])
            helper = load('owner_native_repair.py', PINS['owner_native_repair.py'])
            for sig in original_handlers:
                signal.signal(sig, interrupted)
            signal.setitimer(signal.ITIMER_REAL, 150)
            stack.enter_context(deploy.lock(STATE / 'owner_chat_action_routing.lock'))
            stack.enter_context(deploy.lock(STATE / 'owner_maintenance.lock'))
            gate(); require(deploy.slots_idle(), 'OWNER_CHAT_BUSY')
            old, old_identity = read(TARGET, expected=OLD_SHA)
            before = snapshots(helper); require(deploy.model_identity(helper) == MODEL, 'MAIN_MODEL_IDENTITY')
            original_proxy = deploy.proxy_identity(helper)
            health = helper.health()
            require(all(health.get(str(p)) == 200 for p in (8080,8081,8082)), 'INITIAL_HEALTH')
            private_directory(AREA); journal = AREA / request
            require(not os.path.lexists(journal), 'REQUEST_REUSED'); private_directory(journal)
            create(journal / 'original.py', old)
            staged = journal / 'exchanged.py'
            new_identity = create(staged, raw, stat.S_IMODE(TARGET.stat().st_mode))
            prepared = {'old_sha256': OLD_SHA, 'new_sha256': NEW_SHA, 'old_identity': old_identity,
                        'new_identity': new_identity, 'guarded_state': before, 'original_proxy': original_proxy,
                        'active_model': MODEL}
            create(journal / 'prepared.json', encode(prepared))
            record.update(state='PREPARED', old_sha256=OLD_SHA, new_sha256=NEW_SHA,
                          original_proxy=original_proxy, active_model=MODEL, preserved_before=before)
            save(); ready = True
            gate(); protected_unchanged(helper, deploy, before)
            require(classify_pair(staged, prepared) == 'ORIGINAL', 'PRESTOP_SOURCE_CHANGED')
            record['proxy_stop_attempted'] = True; save()
            deploy.stop_proxy(helper, original_proxy)
            gate(); protected_unchanged(helper, deploy, before)
            apply_source(staged, prepared, record, save)
            gate(); record['proxy_start_attempted'] = True; save()
            new_proxy = deploy.start_proxy(helper); record.update(proxy_after=new_proxy, proxy_restarted=True); save()
            result = probe(); record['read_only_acceptance'] = result
            protected_unchanged(helper, deploy, before)
            require(classify_pair(staged, prepared) == 'INSTALLED', 'FINAL_SOURCE_CHANGED')
            health = helper.health()
            require(all(health.get(str(p)) == 200 for p in (8080,8081,8082)), 'FINAL_HEALTH')
            record.update(state='ROUTING_SOURCE_AND_AUTH_VERIFIED_ACTION_ACCEPTANCE_PENDING',
                          source_install_verified=True, preserved_state_verified=True,
                          preserved_after=before, model_identity_unchanged=True,
                          finished_at=time.time(), chat_health=health)
            # Seal the final record inside the transactional try block. A
            # failed final write must take the same bounded compensation path.
            save(); record['receipt_sha256'] = digest(previous); success = True
        except BaseException as exc:
            success = False
            signal.setitimer(signal.ITIMER_REAL, 0)
            record.update(state='HOLD_CHAT_ACTION_ROUTING_INSTALL', reason=safe(exc),
                          source_install_verified=False, preserved_state_verified=False)
            if ready and record['proxy_stop_attempted']:
                try:
                    signal.setitimer(signal.ITIMER_REAL, 90)
                    # All source, training and file-identity checks precede
                    # compensation service actions; never stop a foreign proxy.
                    protected_unchanged(helper, deploy, before)
                    plan = rollback_plan(helper, deploy, original_proxy, new_proxy, staged, prepared, record)
                    if plan['stop']:
                        deploy.stop_proxy(helper, plan['proxy'])
                    if plan['restore']:
                        restore_source(staged, prepared)
                    if plan['start']:
                        gate(); record['rollback_proxy'] = deploy.start_proxy(helper)
                    record['rollback_verified'] = classify_pair(staged, prepared) == 'ORIGINAL'
                    protected_unchanged(helper, deploy, before)
                    record['rollback_scope'] = 'EXACT_ORIGINAL_STREAM_INODE_BYTES_MODE_AND_PRESERVED_STATE'
                    record['current_source_sha256'] = OLD_SHA
                except BaseException as failure:
                    record.update(rollback_verified=False, rollback_reason=safe(failure))
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if not success:
                record['finished_at'] = time.time()
            if journal is not None and not success:
                try:
                    save(); record['receipt_sha256'] = digest(previous)
                except BaseException as failure:
                    success = False; record.update(state='HOLD_CHAT_ACTION_ROUTING_RECEIPT', reason=safe(failure))
            for sig, handler in original_handlers.items():
                signal.signal(sig, handler)
            elapsed = time.monotonic()-began
            signal.setitimer(signal.ITIMER_REAL, max(.001, original_timer[0]-elapsed) if original_timer[0] else 0,
                             original_timer[1])
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind':'chat_action_routing_install','data':record},
          sort_keys=True,separators=(',', ':'),allow_nan=False), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    raise SystemExit(main())
