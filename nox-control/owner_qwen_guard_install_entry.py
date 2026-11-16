#!/usr/bin/env python3
"""Install an inactive Qwen guard and media handback reader after completed6.

Only an exact idle dispatcher reloads. No trainer, model, media job, flag,
checkpoint, corpus or existing configuration is changed. Window1000 activation
is a different reviewed action requiring its actual immutable start receipt.
"""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
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
STATE = ROOT / 'state'
SCRIPTS = ROOT / 'scripts'
DISPATCHER = SCRIPTS / 'nox_dispatcher_t855u.py'
CONFIG = ROOT / 'config/owner_qwen_training_guard.json'
GUARD_STATE = STATE / 'owner_qwen_training_guard.json'
SCHEMA = 'NOX_QWEN_INACTIVE_GUARD_INSTALL_V1'
BASE_ENTRY = 'owner_qwen_media_handoff_entry.py'
GUARD = 'owner_qwen_training_guard.py'
OVERLAY = 'owner_qwen_media_guard.py'
GUARD_SHA = '2a6f6ade1a913bf42bc921d997b83109323adf3227570cf29a0ffc61a7b2614c'
OVERLAY_SHA = 'acd1ec157ba171e979f82b7e058b4a5054a81fae3884ee1cb8ba8fd33c419450'
DISPATCHER_BEFORE = 'eeacabfc161d28001396a901c2680f58b71a7fcedd6c46893fc6744144bb6e17'
PRIOR = {'request': '6907909296', 'source_sha': '32f527a55808684e5cfd4c4a9f58d9f4cce68bde',
         'receipt_sha256': '18498798d36bb4cea7ac3f8c274c9cd443f82986eb7c1821d8e0844a9081be35'}
PRIOR_CONFIG_SHA = '6ecf2239cb300a44c1601063bafe2de855c1c083f44852bb4421910ba304c2f2'
MEDIA_CONFIG_SHA = 'd76d900d6898a7a33a5cacfc1f4fd334e8fa4a5c72160a9b6ea900fa02beb560'
PINS = {
    BASE_ENTRY: '4ffcc8b4296ad35bb0bafb8454a77047a2c446caa2031d00c81c8da4fb9cff25',
    GUARD: GUARD_SHA,
    OVERLAY: OVERLAY_SHA,
    'owner_qwen_media_handoff.py': '312966b352348f0ae0f403cbe84bbfa2e26f89826f285a0a865965650c7931dc',
    'owner_media_training_handoff.py': '36db3c363ffddfc144c6127e1a9407132bbe39d38996233bf3dd64e5b3cb6ec8',
    'owner_qwen_window_entry.py': 'fb9b9dd403f7b1e5d94b8192ce7ad63394ba8a6b3988cc298fc90a195aa191a7',
    'owner_qwen_install_entry.py': '864fe6b0e1567931f94d0b0be55651227ee00fd9106abc4c82e09c13601975d7',
    'owner_qwen_training_observe.py': 'f2dc6c155b682bdeb663bc383f1aa1db70895f815939099690d898262a3d986a',
    'owner_subagent_fresh_install_entry.py': '670cad05144157a4a2294dbdb07fee7504346587120275c8c85649c5253f2fd4',
    'owner_subagent_hash_recovery_entry.py': 'de2371d0f5c92063c122b65ff08d15c43015ca599cff8299f9dcb7886bc95659',
    'owner_subagent_install_entry.py': 'a210182012d8872390b27a1f0fa8a5668016f06cd94d5557aad2b242d67eb806',
    'owner_subagent_dispatcher_fresh.py': '179e50b71377e007d32a39d0558ff77dbe02267f43045a4c14763b3d4abd6114',
}
MARKER = 'NOX_QWEN_TRAINING_GUARD_BIND_V1'
BINDING = ('# ' + MARKER + '\nimport owner_qwen_training_guard\n'
           'owner_qwen_training_guard.bind_dispatcher(globals(), ' + repr(GUARD_SHA) + ')\n\n'
           '# NOX_QWEN_MEDIA_GUARD_BIND_V1\nimport owner_qwen_media_guard\n'
           'owner_qwen_media_guard.bind_dispatcher(globals(), owner_qwen_media_handoff)\n\n')


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_QWEN_GUARD_INSTALL_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()


def safe(exc):
    text = str(exc)
    return text if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', text) else type(exc).__name__


def emit(kind, value):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': value},
          ensure_ascii=False, allow_nan=False, separators=(',', ':')), flush=True)


def plain(path):
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (*path.parents, path)), 'PATH_OR_SYMLINK')
    return path


def bundle():
    result = {}
    for name, pin in PINS.items():
        value = BUNDLE.get(name)
        require(isinstance(value, str) and len(value) <= 3 * 1024 ** 2, 'BUNDLE_BOUND')
        raw = base64.b64decode(value, validate=True)
        require(0 < len(raw) <= 2 * 1024 ** 2 and digest(raw) == pin, 'BUNDLE_PIN')
        compile(raw, name, 'exec'); result[name] = raw
    return result


def module(name, raw):
    value = types.ModuleType('_nox_guard_install_' + name.removesuffix('.py'))
    value.__file__ = str(SCRIPTS / name)
    sys.modules[value.__name__] = value
    exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    value.BUNDLE = BUNDLE
    return value


def helpers(assets):
    base = module(BASE_ENTRY, assets[BASE_ENTRY])
    # Reuse only pinned definitions; neither installer main is called.
    base.bundle()
    fresh = base.module('owner_subagent_fresh_install_entry.py', assets['owner_subagent_fresh_install_entry.py'])
    helper, recovery, _ = fresh.load_helpers()
    return base, fresh, helper, recovery


def patch_dispatcher(raw, base):
    require(digest(raw) == DISPATCHER_BEFORE, 'DISPATCHER_PREIMAGE')
    anchor = '# NOX_OWNER_TASK_LIFECYCLE_BIND_V1\n'
    text = raw.decode()
    require(text.count(anchor) == 1 and text.count(base.BINDING) == 1
            and text.index(base.BINDING) < text.index(anchor)
            and MARKER not in text and '# NOX_QWEN_MEDIA_GUARD_BIND_V1' not in text, 'BINDING_ANCHOR')
    result = text.replace(anchor, BINDING + anchor, 1).encode()
    require(result.replace(BINDING.encode(), b'', 1) == raw, 'BINDING_SCOPE')
    compile(result, '<inactive-qwen-guard-dispatcher>', 'exec')
    return result


def prior_proof(h, base, fresh, dispatcher_sha):
    raw = h.read(STATE / ('owner_qwen_media_handoff_' + PRIOR['request'] + '.json'), 128000)
    require(digest(raw) == PRIOR['receipt_sha256'], 'PRIOR_RECEIPT_SHA')
    value = json.loads(raw)
    require(value.get('schema') == 'NOX_QWEN_MEDIA_HANDOFF_INSTALL_V1'
            and value.get('request') == PRIOR['request'] and value.get('source_sha') == PRIOR['source_sha']
            and value.get('state') == 'COMPLETED_SIX_MEDIA_HANDOFF_BOUND'
            and value.get('dispatcher_after_sha256') == DISPATCHER_BEFORE
            and value.get('handoff_config_sha256') == PRIOR_CONFIG_SHA
            and value.get('media_config_sha256') == MEDIA_CONFIG_SHA
            and value.get('window_admission') == base.WINDOW_CONTEXT
            and value.get('fresh_reviewer_context') == base.FRESH_CONTEXT
            and value.get('source_pins') == {base.ADAPTER: base.ADAPTER_SHA, **base.DEPS}
            and value.get('rollback') is False and value.get('training_started') is False
            and value.get('completed_six_hold_preserved') is True
            and value.get('resume_training_after_media') is False, 'PRIOR_RECEIPT_SCOPE')
    base.check_fresh(h, fresh, base.FRESH_CONTEXT, dispatcher_sha)
    for name, pin in {base.ADAPTER: base.ADAPTER_SHA, **base.DEPS}.items():
        require(digest(h.read(SCRIPTS / name)) == pin, 'EXISTING_MEDIA_DEPENDENCY')
    require(digest(h.read(base.CONFIG)) == PRIOR_CONFIG_SHA
            and digest(h.read(ROOT / 'config/owner_media_runtime.json')) == MEDIA_CONFIG_SHA, 'EXISTING_CONFIG')
    return value['completed_six']


def history(h, fresh):
    tasks = h.queue_state()['tasks']
    require(all(tasks.get(key, {}).get('status') == 'done' for key in fresh.TASKS), 'HISTORICAL_REVIEWS')
    return {key: digest(encoded(tasks[key])) for key in sorted(fresh.TASKS)}


def acquire(h, path):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid(), 'LEASE_FILE')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        after = path.stat(follow_symlinks=False)
        require((info.st_dev, info.st_ino) == (after.st_dev, after.st_ino), 'LEASE_CHANGED')
        return fd
    except BaseException:
        os.close(fd); raise


SMOKE = r'''
import hashlib,json,os,runpy,stat,sys
out=os.dup(1);sink=os.open(os.devnull,os.O_WRONLY);os.dup2(sink,1);os.dup2(sink,2);os.close(sink)
result={"state":"HOLD_QWEN_INACTIVE_GUARD_SMOKE"}
def snapshot():
 from pathlib import Path
 values={}
 for name in ("TRAIN_HOLD.flag","TRAIN_PAUSE_REQUEST.flag","owner_qwen_training_guard.json"):
  p=Path("/root/nox/state")/name
  if not p.exists() and not p.is_symlink():values[name]=None;continue
  assert not p.is_symlink();s=p.stat();assert stat.S_ISREG(s.st_mode) and s.st_size<=65536
  values[name]=(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,hashlib.sha256(p.read_bytes()).hexdigest())
 return values
try:
 before=snapshot();sys.path.insert(0,"/root/nox/scripts")
 ns=runpy.run_path("/root/nox/scripts/nox_dispatcher_t855u.py",run_name="inactive_qwen_guard_smoke")
 assert ns["WORKERS"]==6 and all(ns.get(k) for k in ("_owner_media_bound","_owner_plans_bound","_owner_qwen_media_handoff_bound","_owner_qwen_media_guard_bound","_owner_lifecycle_bound"))
 guardmod=sys.modules["owner_qwen_training_guard"]
 guard=ns["_owner_qwen_training_guard"]
 config,raw=guardmod.document(guardmod.CONFIG,32768);guardmod.private(guardmod.CONFIG)
 assert config==guardmod.configuration(None,guard.expected_source,enabled=False)
 handback=sys.modules["owner_qwen_media_handoff"].BOUND
 cfg=handback.configuration();ctx=handback.actions.context()
 assert cfg["enabled"] is True and cfg["resume_training_after_media"] is False and ctx["mode"]=="COMPLETED_WINDOW6"
 assert guard.tick()=={"state":"NON_TARGET_WINDOW_NO_ACTION"}
 reader=sys.modules["owner_qwen_media_guard"].BOUND
 assert reader.admission()=={"state":"COMPLETED_SIX_UNAFFECTED","guard_consulted":False}
 assert callable(ns["HANDLERS"].get("owner_media_resume")) and snapshot()==before
 result={"state":"INACTIVE_QWEN_GUARD_AND_MEDIA_READER_VERIFIED","workers":6,"guard_enabled":False,"window1000_admitted":False,"guard_tick_no_action":True,"media_guard_not_consulted":True,"flags_and_guard_state_unchanged":True,"training_started":False}
except Exception as exc:
 text=str(exc);result={"state":"HOLD_QWEN_INACTIVE_GUARD_SMOKE","exception_class":type(exc).__name__,"code":text if text.startswith(("HOLD_","WAIT_")) and len(text)<160 and all(c.isupper() or c.isdigit() or c=="_" for c in text) else None}
os.write(out,json.dumps(result,separators=(",",":")).encode());os.close(out)
raise SystemExit(0 if result["state"]=="INACTIVE_QWEN_GUARD_AND_MEDIA_READER_VERIFIED" else 2)
'''


def smoke(python):
    require(isinstance(python, str) and python.startswith('/')
            and re.fullmatch(r'python(?:[0-9]+(?:\.[0-9]+)?)?', Path(python).name), 'PYTHON_IDENTITY')
    row = subprocess.run([python, '-I', '-B', '-c', SMOKE], capture_output=True, timeout=45)
    require(len(row.stdout) <= 4096, 'SMOKE_OUTPUT_BOUND')
    value = json.loads(row.stdout)
    if row.returncode or value.get('state') != 'INACTIVE_QWEN_GUARD_AND_MEDIA_READER_VERIFIED':
        emit('qwen_inactive_guard_smoke', value)
        require(False, 'SMOKE_FAILED')
    return value


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    assets = bundle(); base, fresh, h, recovery = helpers(assets)
    guard = module(GUARD, assets[GUARD]); cfg_raw = encoded(guard.configuration(None, GUARD_SHA, enabled=False))
    prior_proof(h, base, fresh, DISPATCHER_BEFORE)
    before = h.read(DISPATCHER); after = patch_dispatcher(before, base)
    for path in (CONFIG, GUARD_STATE):
        require(not path.exists() and not path.is_symlink(), 'GUARD_ALREADY_CONFIGURED')
    for name in (GUARD, OVERLAY):
        path = SCRIPTS / name
        require(not path.exists() and not path.is_symlink() or h.read(path) == assets[name], 'FOREIGN_MODULE')
    require(h.active_model() == fresh.CHAT and h.health() == {'8080': 200, '8081': 200, '8082': 200}
            and not h.global_stop(), 'CORE_HEALTH_OR_STOP')
    receipt = STATE / ('owner_qwen_guard_install_' + request + '.json')
    backup = ROOT / 'backup/owner_qwen_guard' / request
    require(not receipt.exists() and not receipt.is_symlink() and not backup.exists() and not backup.is_symlink(),
            'REQUEST_ALREADY_USED')
    controller = maintenance = None
    try:
        # Same order as generation/handback; no GPU/forge lease is touched.
        controller = acquire(h, STATE / 'media/controller.lock')
        maintenance = acquire(h, STATE / 'owner_maintenance.lock')
    except BaseException:
        if controller is not None:
            os.close(controller)
        raise
    acquired_at = time.time(); flag = STATE / 'OWNER_MAINTENANCE.flag'
    note = ('NOX_QWEN_INACTIVE_GUARD ' + request + ' ' + source + '\n').encode()
    result = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'started_at': acquired_at,
              'state': 'PREFLIGHT', 'prior_handoff': PRIOR, 'window_admission': base.WINDOW_CONTEXT,
              'fresh_reviewer_context': base.FRESH_CONTEXT, 'source_pins': {GUARD: GUARD_SHA, OVERLAY: OVERLAY_SHA},
              'dispatcher_before_sha256': digest(before), 'dispatcher_after_sha256': digest(after),
              'guard_enabled': False, 'window1000_admitted': False, 'training_started': False,
              'training_flags_written': False, 'checkpoints_changed': False, 'media_jobs_changed': False,
              'existing_configuration_changed': False, 'queue_file_edited': False, 'tasks_posted': 0,
              'tasks_requeued': 0, 'installed': [], 'rollback': False}
    saved, written, modes = {}, {}, {}
    stop_attempted = owned_flag = success = False
    python = None

    def save():
        h.atomic(receipt, encoded(result))

    def install(path, raw, mode):
        require(not h.global_stop(), 'STOP_BEFORE_INSTALL')
        saved[path] = h.read(path) if path.exists() else None
        modes[path] = stat.S_IMODE(path.stat().st_mode) if path.exists() else mode
        if saved[path] is not None:
            h.atomic(backup / str(path).lstrip('/'), saved[path])
        written[path] = digest(raw)
        h.atomic(path, raw); os.chmod(path, mode)
        require(h.read(path) == raw, 'INSTALL_READBACK')
        result['installed'].append({'path': str(path), 'before': digest(saved[path]) if saved[path] is not None else None,
                                    'after': digest(raw)})
        save()

    def start():
        require(not h.global_stop(), 'STOP_BEFORE_START')
        require(h.command(['supervisorctl', 'start', h.SERVICE], 30)[0] == 0, 'DISPATCHER_START')
        deadline = time.monotonic() + 15
        while h.service()['state'] != 'RUNNING':
            require(time.monotonic() < deadline and not h.global_stop(), 'DISPATCHER_START_TIMEOUT')
            time.sleep(.5)

    try:
        require(not flag.exists() and not flag.is_symlink(), 'EXISTING_MAINTENANCE')
        flagfd = os.open(plain(flag), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(flagfd, 'wb') as stream:
            stream.write(note); stream.flush(); os.fsync(stream.fileno())
        owned_flag = True
        require(not CONFIG.exists() and not CONFIG.is_symlink() and not GUARD_STATE.exists()
                and not GUARD_STATE.is_symlink(), 'GUARD_CREATED_DURING_ADMISSION')
        prior_proof(h, base, fresh, DISPATCHER_BEFORE)
        training_before = fresh.training_snapshot(h); result['training_before'] = training_before
        adapter, actions = base.candidate_actions(assets, base.WINDOW_CONTEXT)
        result['completed_six_before'] = adapter.completed_six(actions)
        result['historical_reviews_before'] = history(h, fresh)
        save(); result['idle_before'] = base.drain(h, acquired_at)
        prior_proof(h, base, fresh, DISPATCHER_BEFORE)
        fresh.preserve_training(training_before, fresh.training_snapshot(h))
        result['owned_dispatcher_group'] = fresh.dispatcher_group(h, recovery, training_before)
        current = h.service(); python = h.process(current['pid'])['argv'][0]
        base.workers(h, acquired_at)
        require(not h.global_stop(), 'STOP_BEFORE_DISPATCHER')
        stop_attempted = True
        try:
            rc = h.command(['supervisorctl', 'stop', h.SERVICE], 30)[0]
        finally:
            stopped = h.service()['state'] == 'STOPPED'
        require(rc == 0 and stopped, 'DISPATCHER_STOP')
        prior_proof(h, base, fresh, DISPATCHER_BEFORE)
        fresh.preserve_training(training_before, fresh.training_snapshot(h))
        for name in (GUARD, OVERLAY):
            path = SCRIPTS / name
            if path.exists() or path.is_symlink():
                require(h.read(path) == assets[name], 'FOREIGN_MODULE_AFTER_DRAIN')
            else:
                install(path, assets[name], 0o644)
        require(not CONFIG.exists() and not CONFIG.is_symlink(), 'FOREIGN_CONFIG_AFTER_DRAIN')
        install(CONFIG, cfg_raw, 0o600)
        install(DISPATCHER, after, stat.S_IMODE(DISPATCHER.stat().st_mode))
        result['binding_smoke'] = smoke(python)
        start(); result['idle_after'] = base.drain(h, time.time())
        prior_proof(h, base, fresh, digest(after))
        result['training_after'] = fresh.training_snapshot(h)
        fresh.preserve_training(training_before, result['training_after'])
        result['completed_six_after'] = adapter.completed_six(actions)
        result['historical_reviews_after'] = history(h, fresh)
        require(result['completed_six_before'] == result['completed_six_after']
                and result['historical_reviews_before'] == result['historical_reviews_after'], 'PRESERVED_PROOFS_CHANGED')
        require(h.read(CONFIG) == cfg_raw and not GUARD_STATE.exists() and not GUARD_STATE.is_symlink(), 'DISABLED_GUARD_CHANGED')
        require(h.active_model() == fresh.CHAT and h.health() == {'8080': 200, '8081': 200, '8082': 200}
                and h.read(flag, 4096) == note and not h.global_stop(), 'CORE_OR_MAINTENANCE_CHANGED')
        result.update(state='INACTIVE_QWEN_GUARD_AND_MEDIA_READER_INSTALLED',
                      guard_config_sha256=digest(cfg_raw), existing_media_config_sha256=MEDIA_CONFIG_SHA,
                      existing_handoff_config_sha256=PRIOR_CONFIG_SHA, completed_six_preserved=True,
                      training_flags_preserved=True, historical_reviews_preserved=True, chat_identity_preserved=True)
        save(); flag.unlink(); owned_flag = False; success = True
    except Exception as exc:
        result.update(state='HOLD_QWEN_INACTIVE_GUARD_INSTALL', reason=safe(exc))
        if written or stop_attempted:
            try:
                for path, pin in written.items():
                    current = base.current_or_missing(h, path)
                    require(current == saved[path] or current is not None and digest(current) == pin, 'ROLLBACK_FOREIGN_WRITE')
                plan = base.rollback_controller_plan(h.service()['state'], bool(written))
                if plan['stop_first']:
                    fresh.dispatcher_group(h, recovery, fresh.training_snapshot(h))
                    require(h.command(['supervisorctl', 'stop', h.SERVICE], 30)[0] == 0
                            and h.service()['state'] == 'STOPPED', 'ROLLBACK_STOP')
                base.restore(h, saved, written, backup, modes)
                result['rollback'] = bool(written)
                if plan['restart']:
                    start()
            except Exception as rollback_error:
                result['rollback_error'] = safe(rollback_error)
    finally:
        try:
            if owned_flag and 'rollback_error' not in result and flag.exists() and h.read(flag, 4096) == note:
                flag.unlink(); owned_flag = False
        except Exception as cleanup_error:
            result['maintenance_cleanup_error'] = safe(cleanup_error)
        finally:
            os.close(maintenance); os.close(controller)
        result.update(finished_at=time.time(), maintenance_flag_retained=owned_flag,
                      service_after=h.service(), health_after=h.health())
        save()
        raw = h.read(receipt)
        require(raw == encoded(result), 'RECEIPT_EXACT_READBACK')
        emit('qwen_inactive_guard_install', result)
        emit('qwen_inactive_guard_context', {'request': request, 'source_sha': source,
             'receipt_sha256': digest(raw), 'receipt_bytes': len(raw), 'state': result['state'],
             'receipt_serialization': 'JSON_SORT_KEYS_INDENT2_UTF8_NEWLINE',
             'guard_enabled': False, 'window1000_admitted': False})
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit('qwen_inactive_guard_preflight', {'state': 'HOLD', 'reason': safe(exc)})
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
