#!/usr/bin/env python3
"""Repair retained-inbox starvation by reloading only the idle dispatcher.

The admitted live1000 trainer, chat, runtimeca8, reviewer179e, guard, handoff,
configuration, job records and existing claims are preserved. The standard
planner admits the already queued target after the in-memory overlay binds.
"""
import base64
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
SCHEMA = 'NOX_MEDIA_INBOX_FAIR_INSTALL_V1'
HELPERS = 'owner_qwen_guard_install_entry.py'
FAIR = 'owner_media_inbox_fair.py'
TRUTH = 'owner_subagent_instruction_truth.py'
DISPATCHER_BEFORE = '439f669487e965b3a9709078674c1fbff6ceff332b0ad2089dad1f218c2e57cf'
RUNTIME_SHA = 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5'
PLANS_SHA = '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773'
WINDOW_CONTEXT = {'request': '6908281920', 'source_sha': '35931438c591a9bb5a649e851f155c4313f28562',
                  'receipt_sha256': 'fa0ed9dd2088a247b2ccc94ad60f9962c0d502121c12bf00e31436c9cf487662'}
ADMISSION_SHA = '9116c9ffbca959ba7afe80dbb66c36a356a922b87ecd839469d17413bb450499'
WRAPPER_SHA = '5bef568fd965f17151b252d8b8d25f00c9b67dd756feef9e30c54cd5b419cd96'
CONFIG_PINS = {
    'owner_qwen_training_guard.json': 'ae4a37af04152e09b88f07882c2fd2825ae3a56769b611d7c3b8ad5441a8bf2a',
    'owner_qwen_media_handoff.json': 'c3760b6f7d2f4af6546c32b730c457c562692026344a1e948298c72fe3445f0a',
    'owner_media_runtime.json': 'd76d900d6898a7a33a5cacfc1f4fd334e8fa4a5c72160a9b6ea900fa02beb560',
}
TARGET = '943c960553eb5f6cf13702455d06a5d8'
PINS = {
    HELPERS: '8eb645c63a132b690cbd25220241fef86c43070a531327881aed4e486ee422e5',
    FAIR: '590ef7db87d0f0a0769e02223169ff99464aaba7512f9a297288aa1e3b7ab700', TRUTH: 'daccac22beaa5f76a5fc0dcad780eb1a19e8fbf8df66df1d653656852c0173d9',
    'owner_qwen_media_handoff_entry.py': '4ffcc8b4296ad35bb0bafb8454a77047a2c446caa2031d00c81c8da4fb9cff25',
    'owner_qwen_training_guard.py': '2a6f6ade1a913bf42bc921d997b83109323adf3227570cf29a0ffc61a7b2614c',
    'owner_qwen_media_guard.py': 'acd1ec157ba171e979f82b7e058b4a5054a81fae3884ee1cb8ba8fd33c419450',
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
MARKER = 'NOX_MEDIA_INBOX_FAIR_BIND_V1'
BINDING = ('# ' + MARKER + '\nimport owner_media_inbox_fair\n'
           'owner_media_inbox_fair.bind_dispatcher(globals(), owner_media_runtime)\n'
           'import owner_subagent_dispatcher\nimport owner_subagent_instruction_truth\n'
           'owner_subagent_instruction_truth.bind(owner_subagent_dispatcher, owner_media_inbox_fair.source_bytes)\n\n')


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_MEDIA_INBOX_INSTALL_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()


def safe(exc):
    text = str(exc)
    return text if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', text) else type(exc).__name__


def emit(kind, value):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': value}, allow_nan=False,
          ensure_ascii=False, separators=(',', ':')), flush=True)


def module(name, raw):
    value = types.ModuleType('_nox_inbox_install_' + name.removesuffix('.py'))
    value.__file__ = str(SCRIPTS / name); sys.modules[value.__name__] = value
    exec(compile(raw, value.__file__, 'exec'), value.__dict__); value.BUNDLE = BUNDLE
    return value


def prepared():
    assets = {}
    for name, pin in PINS.items():
        value = BUNDLE.get(name)
        require(isinstance(value, str) and 0 < len(value) <= 3 * 1024 ** 2, 'BUNDLE_BOUND')
        raw = base64.b64decode(value, validate=True)
        require(0 < len(raw) <= 2 * 1024 ** 2 and digest(raw) == pin, 'BUNDLE_PIN')
        compile(raw, name, 'exec'); assets[name] = raw
    installer = module(HELPERS, assets[HELPERS])
    installer.bundle()
    base, fresh, h, recovery = installer.helpers(assets)
    guard = module('owner_qwen_training_guard.py', assets['owner_qwen_training_guard.py'])
    return assets, installer, base, fresh, h, recovery, guard


def patch_dispatcher(raw):
    require(digest(raw) == DISPATCHER_BEFORE, 'DISPATCHER_PREIMAGE')
    anchor = '# NOX_OWNER_TASK_LIFECYCLE_BIND_V1\n'
    text = raw.decode()
    require(text.count(anchor) == 1 and MARKER not in text
            and text.count('# NOX_QWEN_MEDIA_GUARD_BIND_V1') == 1
            and text.index('# NOX_QWEN_MEDIA_GUARD_BIND_V1') < text.index(anchor), 'BINDING_ANCHOR')
    after = text.replace(anchor, BINDING + anchor, 1).encode()
    require(after.replace(BINDING.encode(), b'', 1) == raw, 'BINDING_SCOPE')
    compile(after, '<inbox-fair-dispatcher>', 'exec'); return after


def current_sources(h, base, fresh, expected_dispatcher):
    base.check_fresh(h, fresh, base.FRESH_CONTEXT, expected_dispatcher)
    for name in ('owner_qwen_training_guard.py', 'owner_qwen_media_guard.py',
                 'owner_qwen_media_handoff.py', 'owner_media_training_handoff.py',
                 'owner_qwen_window_entry.py', 'owner_qwen_install_entry.py', 'owner_qwen_training_observe.py'):
        require(digest(h.read(SCRIPTS / name)) == PINS[name], 'PROTECTED_SOURCE')
    require(digest(h.read(SCRIPTS / 'owner_media_runtime.py')) == RUNTIME_SHA
            and digest(h.read(SCRIPTS / 'owner_task_plans.py')) == PLANS_SHA, 'MEDIA_OR_PLANNER_SOURCE')
    for name, pin in CONFIG_PINS.items():
        require(digest(h.read(ROOT / 'config' / name)) == pin, 'CURRENT_CONFIG_CHANGED')
    require(digest(h.read(STATE / 'owner_training_admission.json')) == ADMISSION_SHA
            and digest(h.read(SCRIPTS / 'run_train_volta_t866u.sh')) == WRAPPER_SHA, 'CURRENT_TRAINING_CHANGED')


def live_training(guard, h, fresh, ctx):
    snapshot = fresh.training_snapshot(h)
    require(snapshot['service']['state'] == 'RUNNING' and snapshot['process']
            and not any(row['present'] for row in snapshot['flags'].values()), 'LIVE_UNPAUSED_TRAINER_REQUIRED')
    window = guard.module('owner_qwen_window_entry.py'); helper = guard.module('owner_qwen_install_entry.py')
    obs = ctx['observer']
    args = window.arguments(helper, ctx['profile'], WINDOW_CONTEXT['request'], ADMISSION_SHA, 1000, resume=True)
    service = obs.service(); children = obs.trainers(args, service)
    require(service['state'] == 'RUNNING' and service['pid'] == snapshot['service']['pid']
            and len(children) == 1 and all(children[0].get(k) is True for k in
                ('exact_admitted_argv', 'cuda_visible_devices_1', 'supervisor_ancestry_verified'))
            and children[0].get('state') != 'Z', 'CURRENT_CHILD_IDENTITY')
    snapshot['student'] = {key: children[0][key] for key in ('pid', 'ppid', 'start_ticks')}
    return snapshot


def preserve_training(fresh, before, after):
    fresh.preserve_training(before, after)
    require(before['service'] == after['service'] and before['process'] == after['process']
            and before['student'] == after['student'], 'TRAINING_PROCESS_CHANGED')


def historical_tasks(h):
    rows = h.queue_state()['tasks']
    require(not any(row.get('status') == 'running' for row in rows.values()), 'RUNNING_CLAIMS')
    # All prior claims/results remain authoritative. Unclaimed pending jobs
    # may receive the existing planner's DAG, which is the intended repair.
    return {key: digest(encoded(row)) for key, row in rows.items()
            if row.get('owner_claim') or row.get('status') in ('done', 'failed', 'blocked', 'cancelled')}


def preserved_history(h, previous):
    current = h.queue_state()['tasks']
    require(all(key in current and digest(encoded(current[key])) == pin for key, pin in previous.items()),
            'HISTORICAL_CLAIM_OR_RESULT_CHANGED')


def job_history(h):
    folder = STATE / 'media/jobs'; result = {}
    require(not any(p.is_symlink() for p in (*folder.parents, folder)), 'MEDIA_HISTORY_PATH')
    with os.scandir(folder) as entries:
        for count, entry in enumerate(entries, 1):
            require(count <= 200, 'MEDIA_HISTORY_BOUND')
            if re.fullmatch('[a-f0-9]{32}\\.json', entry.name):
                require(entry.is_file(follow_symlinks=False), 'MEDIA_HISTORY_FILE')
                result[entry.name] = digest(h.read(Path(entry.path), 262144))
    return result


def target_plan(h):
    tasks = h.queue_state()['tasks']; task = tasks.get('owner.media.' + TARGET)
    if not isinstance(task, dict):
        return {'job_id': TARGET, 'normal_dag_observed': False, 'generation_completed_verified': False}
    plan = task.get('owner_plan_id')
    require(isinstance(plan, str) and re.fullmatch('[a-f0-9]{24}', plan), 'TARGET_PLAN_ID')
    parent_id = 'owner.plan.media.' + TARGET
    engine, budget = ('owner.branch.' + plan + '.' + suffix for suffix in ('engine', 'budget'))
    parent = tasks.get(parent_id, {})
    manifest_raw = h.read(STATE / 'owner_plans' / plan / 'manifest.json', 65536)
    manifest = json.loads(manifest_raw)
    expected_nodes = [
        {'id': engine, 'step': 'engine', 'operation': 'media_readiness', 'deps': [], 'handler': 'owner_plan_step'},
        {'id': budget, 'step': 'budget', 'operation': 'resource_budget', 'deps': [], 'handler': 'owner_plan_step'},
        {'id': task['id'], 'step': 'generation', 'operation': 'media_native', 'deps': [engine, budget], 'handler': 'owner_media'},
    ]
    require(task.get('handler') == 'owner_media' and task.get('params', {}).get('job_id') == TARGET
            and task.get('owner_parent_id') == parent_id and task.get('deps') == [engine, budget]
            and task.get('locks') == ['gpu1'] and not task.get('owner_claim')
            and parent.get('handler') == 'owner_plan_join' and parent.get('owner_plan_id') == plan
            and manifest.get('source_sha256') == PLANS_SHA and manifest.get('plan_id') == plan
            and manifest.get('parent_id') == parent_id and manifest.get('intent') == 'media'
            and manifest.get('nodes') == expected_nodes and manifest.get('parameters') == {'job_id': TARGET}
            and all(tasks.get(key, {}).get('owner_plan_id') == plan for key in (engine, budget)), 'TARGET_NORMAL_DAG')
    return {'job_id': TARGET, 'normal_dag_observed': True, 'plan_id': plan,
            'manifest_sha256': digest(manifest_raw), 'branches': 3, 'generation_completed_verified': False,
            'state': 'ADMITTED_TO_EXISTING_PLANNER_NOT_GENERATED'}


SMOKE = r'''
import hashlib,json,multiprocessing,os,runpy,sys
out=os.dup(1);sink=os.open(os.devnull,os.O_WRONLY);os.dup2(sink,1);os.dup2(sink,2);os.close(sink)
result={"state":"HOLD_MEDIA_INBOX_FAIR_SMOKE"}
try:
 sys.path.insert(0,"/root/nox/scripts")
 ns=runpy.run_path("/root/nox/scripts/nox_dispatcher_t855u.py",run_name="inbox_fair_smoke")
 fair=sys.modules["owner_media_inbox_fair"];truth=sys.modules["owner_subagent_instruction_truth"]
 assert ns["WORKERS"]==6 and all(ns.get(k) for k in ("_owner_media_bound","_owner_plans_bound","_owner_lifecycle_bound","_owner_media_inbox_fair_bound","_owner_qwen_media_guard_bound"))
 assert fair.BOUND["runtime"].ingest_media_tasks is fair.BOUND["replacement"]
 assert truth.BOUND["callback"].model_instruction is truth.BOUND["replacement"]
 fixture="1C: runtime\n2B: memory\n2D: weights\n"
 for role in ("runtime","memory","weights"):
  prompt=truth.BOUND["callback"].model_instruction(fixture,role)
  assert truth.OLD not in prompt and truth.NEW in prompt
 # The existing Subagents uses spawn. Reproduce its real dispatcher main-path
 # import, then inspect the callback imported in that independent child.
 sys.modules["__main__"].__file__="/root/nox/scripts/nox_dispatcher_t855u.py"
 sys.modules["__main__"].__spec__=None
 ctx=multiprocessing.get_context("spawn");parent,child=ctx.Pipe(duplex=False)
 p=ctx.Process(target=truth.spawn_prompt_probe,args=(child,));p.start();child.close()
 try:
  assert parent.poll(6);childproof=parent.recv();p.join(3)
  assert p.exitcode==0 and childproof=={"bound_in_spawned_child":True,"all_roles_truthful":True}
 finally:
  parent.close()
  if p.is_alive():p.terminate();p.join(2)
 result={"state":"MEDIA_INBOX_AND_TRUTH_OVERLAYS_BOUND","workers":6,"native_source_files_modified":False,"guard_tick_called":False,"model_requested":False,"spawn_reimport_prompt_verified":True}
except Exception as exc:
 result={"state":"HOLD_MEDIA_INBOX_FAIR_SMOKE","exception_class":type(exc).__name__}
os.write(out,json.dumps(result,separators=(",",":")).encode());os.close(out)
raise SystemExit(0 if result["state"]=="MEDIA_INBOX_AND_TRUTH_OVERLAYS_BOUND" else 2)
'''


def smoke(python):
    require(isinstance(python, str) and python.startswith('/')
            and re.fullmatch(r'python(?:[0-9]+(?:\.[0-9]+)?)?', Path(python).name), 'PYTHON_IDENTITY')
    child = subprocess.run([python, '-I', '-B', '-c', SMOKE], capture_output=True, timeout=15)
    require(len(child.stdout) <= 4096, 'SMOKE_OUTPUT_BOUND')
    result = json.loads(child.stdout)
    require(child.returncode == 0 and result.get('state') == 'MEDIA_INBOX_AND_TRUTH_OVERLAYS_BOUND', 'SMOKE_FAILED')
    return result


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    assets, installer, base, fresh, h, recovery, guard = prepared()
    before = h.read(DISPATCHER); after = patch_dispatcher(before)
    current_sources(h, base, fresh, DISPATCHER_BEFORE)
    cfg, config_sha = guard.checked_config(WINDOW_CONTEXT, PINS['owner_qwen_training_guard.py'])
    require(config_sha == CONFIG_PINS['owner_qwen_training_guard.json'], 'GUARD_CONTEXT')
    ctx = guard.context_evidence(cfg)
    require(ctx['context'] == WINDOW_CONTEXT and ctx['admission_sha256'] == ADMISSION_SHA
            and ctx['wrapper_sha256'] == WRAPPER_SHA, 'CURRENT_WINDOW_CONTEXT')
    require(h.active_model() == fresh.CHAT and h.health() == {'8080': 200, '8081': 200, '8082': 200}
            and not h.global_stop(), 'CORE_HEALTH_OR_STOP')
    for name in (FAIR, TRUTH):
        path = SCRIPTS / name
        require(not path.exists() and not path.is_symlink() or h.read(path) == assets[name], 'FOREIGN_OVERLAY')
    receipt = STATE / ('owner_media_inbox_fair_' + request + '.json')
    backup = ROOT / 'backup/owner_media_inbox_fair' / request
    require(not receipt.exists() and not receipt.is_symlink() and not backup.exists() and not backup.is_symlink(),
            'REQUEST_ALREADY_USED')
    controller = maintenance = None
    try:
        controller = installer.acquire(h, STATE / 'media/controller.lock')
        maintenance = installer.acquire(h, STATE / 'owner_maintenance.lock')
    except BaseException:
        if controller is not None:
            os.close(controller)
        raise
    acquired_at = time.time(); flag = STATE / 'OWNER_MAINTENANCE.flag'
    note = ('NOX_MEDIA_INBOX_FAIR ' + request + ' ' + source + '\n').encode()
    result = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'started_at': acquired_at,
              'state': 'PREFLIGHT', 'window_admission': WINDOW_CONTEXT,
              'dispatcher_before_sha256': digest(before), 'dispatcher_after_sha256': digest(after),
              'source_pins': {FAIR: PINS[FAIR], TRUTH: PINS[TRUTH]}, 'protected_config_pins': CONFIG_PINS,
              'max_inbox_history': 200, 'max_new_tasks_per_tick': 3,
              'trainer_service_actions': 0, 'training_flags_written': False, 'checkpoints_written': False,
              'protected_source_files_modified': False, 'configuration_changed': False, 'jobs_created': 0,
              'jobs_retried': 0, 'queue_file_edited_by_installer': False, 'claims_replayed': 0,
              'installed': [], 'rollback': False, 'generation_completed_verified': False}
    saved, written, modes = {}, {}, {}
    stop_attempted = owned_flag = success = False

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
        result['installed'].append({'name': path.name, 'before': digest(saved[path]) if saved[path] else None,
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
        fd = os.open(installer.plain(flag), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(note); stream.flush(); os.fsync(stream.fileno())
        owned_flag = True
        current_sources(h, base, fresh, DISPATCHER_BEFORE)
        training_before = live_training(guard, h, fresh, ctx); result['training_before'] = training_before
        save(); result['idle_before'] = base.drain(h, acquired_at, timeout=20)
        history_before, jobs_before = historical_tasks(h), job_history(h)
        require('owner.media.' + TARGET not in h.queue_state()['tasks'], 'TARGET_ALREADY_PLANNED')
        target = json.loads(h.read(STATE / 'media/jobs' / (TARGET + '.json'), 262144))
        require(target.get('id') == TARGET and target.get('state') == 'QUEUED', 'TARGET_NO_LONGER_QUEUED')
        current_sources(h, base, fresh, DISPATCHER_BEFORE)
        preserve_training(fresh, training_before, live_training(guard, h, fresh, ctx))
        result['owned_dispatcher_group'] = fresh.dispatcher_group(h, recovery, training_before)
        current = h.service(); python = h.process(current['pid'])['argv'][0]
        base.workers(h, acquired_at)
        require(not h.global_stop(), 'STOP_BEFORE_DISPATCHER')
        stop_attempted = True
        rc = h.command(['supervisorctl', 'stop', h.SERVICE], 30)[0]
        require(rc == 0 and h.service()['state'] == 'STOPPED', 'DISPATCHER_STOP')
        current_sources(h, base, fresh, DISPATCHER_BEFORE)
        preserve_training(fresh, training_before, live_training(guard, h, fresh, ctx))
        for name in (FAIR, TRUTH):
            path = SCRIPTS / name
            if path.exists() or path.is_symlink():
                require(h.read(path) == assets[name], 'FOREIGN_OVERLAY_AFTER_DRAIN')
            else:
                install(path, assets[name], 0o644)
        install(DISPATCHER, after, stat.S_IMODE(DISPATCHER.stat().st_mode))
        result['binding_smoke'] = smoke(python)
        start(); result['idle_after'] = base.drain(h, time.time(), timeout=20)
        deadline = time.monotonic() + 10
        while True:
            result['target_plan'] = target_plan(h)
            if result['target_plan']['normal_dag_observed']:
                break
            require(time.monotonic() < deadline and not h.global_stop(), 'TARGET_DAG_NOT_OBSERVED')
            time.sleep(.5)
        current_sources(h, base, fresh, digest(after))
        result['training_after'] = live_training(guard, h, fresh, ctx)
        preserve_training(fresh, training_before, result['training_after'])
        preserved_history(h, history_before)
        require(job_history(h) == jobs_before, 'MEDIA_JOB_HISTORY_CHANGED')
        require(h.active_model() == fresh.CHAT and h.health() == {'8080': 200, '8081': 200, '8082': 200}
                and h.read(flag, 4096) == note and not h.global_stop(), 'CORE_OR_MAINTENANCE_CHANGED')
        result.update(state='MEDIA_INBOX_FAIR_AND_REVIEWER_TRUTH_BOUND',
                      training_identity_preserved=True, current_student_process_preserved=True,
                      historical_claims_preserved=True, prior_claim_or_terminal_count=len(history_before),
                      prior_claim_or_terminal_sha256=digest(encoded(history_before)),
                      media_job_history_preserved=True, media_job_count=len(jobs_before),
                      media_job_history_sha256=digest(encoded(jobs_before)),
                      chat_identity_preserved=True, dispatcher_only_restarted=True,
                      prompt_identity_assertions_removed=True, native_runtime_and_callback_files_unchanged=True)
        save(); flag.unlink(); owned_flag = False; success = True
    except Exception as exc:
        result.update(state='HOLD_MEDIA_INBOX_FAIR_INSTALL', reason=safe(exc))
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
                base.restore(h, saved, written, backup, modes); result['rollback'] = bool(written)
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
                      dispatcher_service_after=h.service(), health_after=h.health())
        save(); raw = h.read(receipt)
        require(raw == encoded(result), 'RECEIPT_EXACT_READBACK')
        emit('media_inbox_fair_install', result)
        emit('media_inbox_fair_context', {'request': request, 'source_sha': source,
             'receipt_sha256': digest(raw), 'receipt_bytes': len(raw), 'state': result['state']})
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit('media_inbox_fair_preflight', {'state': 'HOLD', 'reason': safe(exc)})
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
