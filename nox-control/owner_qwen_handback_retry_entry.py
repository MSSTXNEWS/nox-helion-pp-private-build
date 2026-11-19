#!/usr/bin/env python3
"""Bind bounded handback waits and requeue one archived failed resume task.

Only the dispatcher is restarted. The installer cannot release training flags,
call the handback handler, start the trainer, or change its sealed admission.
"""
import base64
import copy
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
QUEUE_STATE = STATE / 'dispatcher/state.json'
QUEUE_LINES = STATE / 'dispatcher/queue.jsonl'
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
HELPER = 'owner_media_inbox_fair_entry.py'
OVERLAY = 'owner_qwen_handback_retry.py'
STATUS = 'owner_qwen_training_status.py'
PINS = {
    HELPER: 'bd3f93d01db07806f1696ec5320930ab49b1fab4da53930f864c51d27caa1e4c',
    OVERLAY: '9711fa34c31a4e1f6633fe20998e693eaa2668c7024ac96de6bae6c9a2ac9055',
    STATUS: '56ac00ee986932524fe61b996b6edde651419dcc0da028d8b6a56f342be58ae8',
}
BEFORE = '89b359b49fe37e219629574eed5ae7ee3d8e756fa5feb64f5274d68b1eccb2bb'
JOB = '943c960553eb5f6cf13702455d06a5d8'
TASK = 'owner.media.resume.' + JOB
CLAIM_SHA = '7715a84b52b7e90e2490ec66e960295f460f7769a1171902f5df67521bad11d1'
HANDOFF_DIR = STATE / 'media/training_handback' / JOB
MANIFEST8 = '107f26c33c62b7e9ee4326013bafd75ed2cc3ad03de14f5da24bcd99c57f78b2'
SIX_SHA = '2076f7050169692e0333747d07abb5c290b429c1b30d56fd55928fc215edfc00'
FIXED = {
    HANDOFF_DIR / 'request.json': 'ba59daf72634948e351a734e6f5cfdd7bc579c6dbcd8e1612d425b65ffa45c8e',
    STATE / 'media/training_yield.json': 'ed8f23607ae2ee0b5be5db9d1437fca95a93a872a491cffb803c5d864922b8c3',
    STATE / 'TRAIN_HOLD.flag': '2e104be136236c5ce7a9a6327904bc8c5c091c959085192e9b6c1c1152417ae4',
    STATE / 'TRAIN_PAUSE_REQUEST.flag': 'f57c65d2f2a1cf7214fef5f83545f2e901a7065c82ef07ebad75a7236bb4ff38',
    STATE / 'media/jobs' / (JOB + '.json'): '40cfaf570dc3d02a9e862fc7cd25660bdf45d36840d6aba8ef262525f7ee4780',
    OUTPUT / 'owner_last_result.json': '8cda027082b101cd14474edf5ef8432dc2263d5b29314a4563805c4af0a3665e',
    OUTPUT / 'latest_checkpoint.json': '0ebfab068527bd8a91a70e4c19fb6041003d6288b3aeb4fee42f1d6cc9ff4659',
    OUTPUT / 'owner_acceptance.json': SIX_SHA,
}
EXECUTION_FIELDS = frozenset(('owner_claim', 'owner_claim_epoch', 'claimed_by', 'started_at', 'finished_at',
                             'result', 'note', 'mentor', 'mentor_incident', 'next_try'))
MARKER = 'NOX_QWEN_HANDBACK_RETRY_BIND_V1'
BINDING = ('# ' + MARKER + '\nimport owner_qwen_handback_retry\n'
           'owner_qwen_handback_retry.bind_dispatcher(globals(), owner_qwen_media_handoff, owner_qwen_media_guard)\n\n')


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_QWEN_HANDBACK_REPAIR_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + '\n').encode()


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode()


def safe(exc):
    text = str(exc)
    return text if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', text) else type(exc).__name__


def emit(kind, value):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': value}, ensure_ascii=False,
          allow_nan=False, separators=(',', ':')), flush=True)


def module(name, raw):
    value = types.ModuleType('_nox_handback_repair_' + name.removesuffix('.py'))
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
    fair = module(HELPER, assets[HELPER])
    original_assets, installer, base, fresh, h, recovery, guard = fair.prepared()
    assets.update(original_assets)
    status = module(STATUS, assets[STATUS])
    return assets, fair, installer, base, fresh, h, recovery, guard, status


def patch_dispatcher(raw):
    require(digest(raw) == BEFORE, 'DISPATCHER_PREIMAGE')
    text = raw.decode(); anchor = '# NOX_OWNER_TASK_LIFECYCLE_BIND_V1\n'
    require(text.count(anchor) == 1 and MARKER not in text
            and text.count('# NOX_MEDIA_INBOX_FAIR_BIND_V1') == 1
            and text.index('# NOX_MEDIA_INBOX_FAIR_BIND_V1') < text.index(anchor)
            and text.count('# NOX_QWEN_MEDIA_GUARD_BIND_V1') == 1, 'BINDING_ANCHOR')
    updated = text.replace(anchor, BINDING + anchor, 1).encode()
    require(updated.replace(BINDING.encode(), b'', 1) == raw, 'BINDING_SCOPE')
    compile(updated, '<handback-retry-dispatcher>', 'exec'); return updated


def strict(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, 'DUPLICATE_JSON_KEY'); out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: require(False, 'NONFINITE_JSON'))


def queue(h):
    raw = h.read(QUEUE_STATE, 16 * 1024 ** 2); value = strict(raw)
    require(isinstance(value, dict) and isinstance(value.get('tasks'), dict)
            and 0 < len(value['tasks']) <= 20000
            and all(isinstance(row, dict) and row.get('id') == key for key, row in value['tasks'].items()), 'QUEUE_SCHEMA')
    return value, raw


def queue_lines(value):
    return ('\n'.join(json.dumps(row, ensure_ascii=False, allow_nan=False)
                      for row in value['tasks'].values()) + '\n').encode()


def pending_task(row, request, source, archive_sha):
    require(isinstance(row, dict) and row.get('id') == TASK and row.get('handler') == 'owner_media_resume'
            and row.get('source') == 'owner_qwen_media_handoff' and row.get('class') == 'training'
            and row.get('params') == {'job_id': JOB} and row.get('deps') == [] and row.get('locks') == ['gpu1']
            and row.get('status') == 'blocked' and type(row.get('retries')) is int and row['retries'] == 1
            and isinstance(row.get('result'), dict)
            and row['result'].get('state') == 'HOLD_MEDIA_HANDBACK_FILE_CHANGED'
            and row['result'].get('verified') is False and row.get('owner_claim', {}).get('pid') == 724331
            and digest(canonical(row['owner_claim'])) == CLAIM_SHA
            and 'owner_handback_repair' not in row and not any(k.startswith('_') for k in row), 'TARGET_SCOPE')
    updated = {key: copy.deepcopy(value) for key, value in row.items() if key not in EXECUTION_FIELDS}
    updated['status'] = 'pending'
    updated['owner_handback_repair'] = {'schema': 'NOX_HANDOFF_SINGLE_TASK_RETRY_V1', 'request': request,
        'source_sha': source, 'archived_task_sha256': archive_sha, 'previous_retries': 1,
        'reason': 'BOUNDED_QUEUE_READ_AND_GUARD_FRESHNESS_REPAIR', 'claim_must_be_reissued': True}
    require(updated['retries'] == 1 and not EXECUTION_FIELDS & updated.keys(), 'RETRY_SCOPE')
    return updated


def fixed_evidence(h, fresh, guard, ctx, fair):
    snapshot = fresh.training_snapshot(h)
    require(snapshot['service']['state'] == 'FATAL' and snapshot['service']['pid'] is None
            and snapshot['process'] is None, 'PAUSED_FATAL_SERVICE_REQUIRED')
    window = guard.module('owner_qwen_window_entry.py'); helper = guard.module('owner_qwen_install_entry.py')
    argv = window.arguments(helper, ctx['profile'], fair.WINDOW_CONTEXT['request'], fair.ADMISSION_SHA, 1000, resume=True)
    require(not ctx['observer'].trainers(argv, ctx['observer'].service()), 'LIVE_TRAINER_CHILD')
    rows = {}
    for path, pin in FIXED.items():
        before = path.lstat(); raw = h.read(path, 2 * 1024 ** 2); after = path.lstat()
        ident = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode, s.st_uid)
        require(stat.S_ISREG(before.st_mode) and ident(before) == ident(after)
                and digest(raw) == pin, 'FIXED_EVIDENCE_CHANGED')
        rows[str(path.relative_to(ROOT))] = {'sha256': pin, 'identity': list(ident(after))}
    for name in ('TRAIN_HOLD.flag', 'TRAIN_PAUSE_REQUEST.flag'):
        path = HANDOFF_DIR / ('released-' + name)
        require(not path.exists() and not path.is_symlink(), 'PREVIOUS_FLAG_RELEASE')
    request = strict(h.read(HANDOFF_DIR / 'request.json'))
    yielded = strict(h.read(STATE / 'media/training_yield.json'))
    job = strict(h.read(STATE / 'media/jobs' / (JOB + '.json')))
    terminal = strict(h.read(OUTPUT / 'owner_last_result.json'))
    require(request.get('job_id') == JOB and request.get('stage') == 'QUEUED'
            and request.get('initial_admission') == fair.WINDOW_CONTEXT
            and 'start_command_issued' not in request and 'start_requested_at' not in request
            and 'process' not in request and 'resumed_at' not in request
            and yielded.get('active') is True and yielded.get('resume') is True
            and yielded.get('job_id') == JOB and yielded.get('qwen_admission_sha256') == fair.ADMISSION_SHA
            and yielded.get('wrapper_sha256') == fair.WRAPPER_SHA
            and yielded.get('checkpoint', {}).get('receipt_sha256') == FIXED[OUTPUT / 'owner_last_result.json']
            and yielded.get('checkpoint', {}).get('manifest_sha256') == MANIFEST8
            and yielded.get('checkpoint', {}).get('step') == 8
            and job.get('state') == 'COMPLETED' and job.get('generation_verified') is True
            and job.get('gpu1_released') is True
            and terminal.get('state') == 'EXISTING_TRAINER_HOLD_OR_PAUSE'
            and terminal.get('reload_verified') is True and terminal.get('successful_optimizer_steps') == 8,
            'FIXED_HANDOFF_SCOPE')
    return {'training': snapshot, 'evidence': rows}


def checkpoint_identities(ctx, manifest):
    directory = ctx['output'] / manifest['directory']; result = {}
    require(set(p.name for p in directory.iterdir()) == set(manifest['files_sha256']) | {'checkpoint_manifest.json'}, 'CHECKPOINT_FILES')
    for name in (*manifest['files_sha256'], 'checkpoint_manifest.json'):
        path = directory / name; info = path.lstat()
        require(not any(p.is_symlink() for p in (*path.parents, path)) and stat.S_ISREG(info.st_mode), 'CHECKPOINT_FILE_SCOPE')
        result[name] = [getattr(info, key) for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode', 'st_uid')]
    return result


def full_checkpoints(ctx, status):
    obs = ctx['observer']; deadline = time.monotonic() + 90
    latest, metadata = obs.document(ctx['output'] / 'latest_checkpoint.json')
    require(metadata['sha256'] == FIXED[OUTPUT / 'latest_checkpoint.json'] and latest['manifest_sha256'] == MANIFEST8,
            'LATEST_CHECKPOINT_CHANGED')
    rows = []; manifests = []; identities = []
    for goal, name, pin in ((6, Path(ctx['certificate']['checkpoint']).name, ctx['certificate']['checkpoint_manifest_sha256']),
                            (8, latest['directory'], MANIFEST8)):
        manifest, _ = obs.document(ctx['output'] / name / 'checkpoint_manifest.json', pin)
        before = checkpoint_identities(ctx, manifest)
        proof, manifest, saved = status.checkpoint(obs, ctx['contract'], ctx['lineage'], name, pin, deadline)
        require(before == checkpoint_identities(ctx, manifest)
                and proof['successful_optimizer_steps'] == proof['attempted_steps'] == goal
                and proof['skipped_steps'] == 0 and proof['checkpoint_file_count'] == 10
                and proof['verified_bytes'] == {6: 519882866, 8: 519884896}[goal]
                and saved['update_evidence'][:6] == ctx['certificate']['update_evidence'], 'FULL_CHECKPOINT_SCOPE')
        terminal = obs.terminal_proof(ctx['output'] / ('owner_acceptance.json' if goal == 6 else 'owner_last_result.json'),
                                      ctx['contract'], ctx['lineage'], manifest, saved, acceptance=goal == 6)
        require(terminal['receipt_sha256'] == (SIX_SHA if goal == 6 else FIXED[OUTPUT / 'owner_last_result.json']), 'TERMINAL_PIN')
        rows.append({'step': goal, 'manifest_sha256': pin, 'verified_files': 10, 'verified_bytes': proof['verified_bytes'],
                     'all_checkpoint_file_sha256_verified': True, 'terminal_sha256': terminal['receipt_sha256']})
        manifests.append(manifest); identities.append(before)
    require(obs.read(ctx['output'] / 'latest_checkpoint.json')[1]['sha256'] == metadata['sha256'], 'CHECKPOINT_POINTER_RACE')
    return rows, manifests, identities


def preserve_checkpoints(ctx, manifests, identities):
    require(all(checkpoint_identities(ctx, manifest) == identity for manifest, identity in zip(manifests, identities)),
            'CHECKPOINT_IDENTITY_CHANGED')


SMOKE = r'''
import json,os,runpy,sys
out=os.dup(1);sink=os.open(os.devnull,os.O_WRONLY);os.dup2(sink,1);os.dup2(sink,2);os.close(sink)
result={"state":"HOLD_QWEN_HANDBACK_RETRY_SMOKE"}
try:
 sys.path.insert(0,"/root/nox/scripts")
 ns=runpy.run_path("/root/nox/scripts/nox_dispatcher_t855u.py",run_name="handback_retry_smoke")
 mod=sys.modules["owner_qwen_handback_retry"];bound=mod.BOUND
 assert ns["WORKERS"]==6 and all(ns.get(k) for k in ("_owner_media_inbox_fair_bound","_owner_qwen_media_guard_bound","_owner_qwen_handback_retry_bound","_owner_lifecycle_bound"))
 assert bound["base"]["read"] is bound["read"] and bound["reader"].admission is bound["admission"]
 assert sys.modules["owner_qwen_media_handoff"].BOUND.run.__func__.__globals__ is bound["base"]
 assert callable(ns["HANDLERS"]["owner_media_resume"])
 result={"state":"HANDOFF_RETRY_BINDING_VERIFIED","queue_snapshot_attempts":3,"guard_freshness_codes":3,"handler_called":False,"guard_tick_called":False,"training_started":False}
except Exception as exc:result["exception_class"]=type(exc).__name__
os.write(out,json.dumps(result,separators=(",",":")).encode());os.close(out)
raise SystemExit(0 if result["state"]=="HANDOFF_RETRY_BINDING_VERIFIED" else 2)
'''


def smoke(python):
    require(isinstance(python, str) and python.startswith('/') and re.fullmatch(r'python(?:[0-9]+(?:\.[0-9]+)?)?', Path(python).name), 'PYTHON_IDENTITY')
    result = subprocess.run([python, '-I', '-B', '-c', SMOKE], capture_output=True, timeout=15)
    require(len(result.stdout) <= 4096, 'SMOKE_BOUND'); value = strict(result.stdout)
    require(result.returncode == 0 and value.get('state') == 'HANDOFF_RETRY_BINDING_VERIFIED', 'SMOKE_FAILED')
    return value


def observation(h, old_claim):
    state, _ = queue(h); row = state['tasks'].get(TASK, {})
    record = strict(h.read(HANDOFF_DIR / 'request.json'))
    claim = row.get('owner_claim') or {}
    fresh = bool(claim and claim != old_claim and claim.get('pid') == h.service().get('pid')
                 and re.fullmatch('[a-f0-9]{24}', str(claim.get('nonce'))))
    rc, text = h.command(['supervisorctl', 'status', 'nox-train-volta-t866u'], 5)
    match = re.match(r'nox-train-volta-t866u\s+(RUNNING|STARTING|FATAL|STOPPED|EXITED|BACKOFF|STOPPING)\b(?:.*?pid\s+(\d+))?', text)
    require(match is not None, 'OBSERVATION_SERVICE')
    return {'task_state': row.get('status'), 'fresh_native_claim_observed': fresh,
            'claim_sha256': digest(canonical(claim)) if claim else None,
            'request_stage': record.get('stage'), 'start_command_issued': record.get('start_command_issued') is True,
            'trainer_service_state': match[1], 'resumed_record_observed': record.get('stage') == 'RESUMED',
            'new_optimizer_updates_verified': False,
            'handler_result_verified_recorded': (row.get('result') or {}).get('verified') is True}


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    assets, fair, installer, base, fresh, h, recovery, guard, status = prepared()
    before = h.read(DISPATCHER); after = patch_dispatcher(before)
    def sources(pin):
        fair.current_sources(h, base, fresh, pin)
        for name in (fair.FAIR, fair.TRUTH):
            require(digest(h.read(SCRIPTS / name)) == fair.PINS[name], 'EXISTING_OVERLAY_CHANGED')
        require(digest(h.read(SCRIPTS / 'owner_training_status.py')) == PINS[STATUS], 'STATUS_SOURCE_CHANGED')
    sources(BEFORE)
    config, config_sha = guard.checked_config(fair.WINDOW_CONTEXT, fair.PINS['owner_qwen_training_guard.py'])
    require(config_sha == fair.CONFIG_PINS['owner_qwen_training_guard.json'], 'GUARD_CONFIG')
    ctx = guard.context_evidence(config)
    fixed_before = fixed_evidence(h, fresh, guard, ctx, fair)
    checkpoint_proof, manifests, identities = full_checkpoints(ctx, status)
    require(fixed_evidence(h, fresh, guard, ctx, fair) == fixed_before, 'PREFLIGHT_EVIDENCE_CHANGED')
    guard_reason = guard.resume_block_reason(fair.WINDOW_CONTEXT)
    if guard_reason is not None:
        raise RuntimeError(guard_reason)
    require(h.active_model() == fresh.CHAT and h.health() == {'8080': 200, '8081': 200, '8082': 200}
            and not h.global_stop(), 'CORE_HEALTH_OR_STOP')
    overlay_path = SCRIPTS / OVERLAY
    require(not overlay_path.exists() and not overlay_path.is_symlink() or h.read(overlay_path) == assets[OVERLAY], 'FOREIGN_OVERLAY')
    receipt = STATE / ('owner_qwen_handback_retry_' + request + '.json')
    backup = ROOT / 'backup/owner_qwen_handback_retry' / request
    require(not receipt.exists() and not receipt.is_symlink() and not backup.exists() and not backup.is_symlink(), 'REQUEST_ALREADY_USED')
    controller = maintenance = None
    try:
        controller = installer.acquire(h, STATE / 'media/controller.lock')
        maintenance = installer.acquire(h, STATE / 'owner_maintenance.lock')
    except BaseException:
        if controller is not None: os.close(controller)
        raise
    flag = STATE / 'OWNER_MAINTENANCE.flag'; note = ('NOX_QWEN_HANDBACK_RETRY ' + request + ' ' + source + '\n').encode()
    started = time.time(); owned_flag = success = stop_attempted = queue_written = released = False
    saved, written, modes = {}, {}, {}
    old_task = new_task = None; others = {}
    result = {'schema': 'NOX_QWEN_HANDBACK_RETRY_INSTALL_V1', 'request': request, 'source_sha': source,
              'started_at': started, 'state': 'PREFLIGHT', 'window_admission': fair.WINDOW_CONTEXT,
              'dispatcher_before_sha256': BEFORE, 'dispatcher_after_sha256': digest(after),
              'overlay_sha256': PINS[OVERLAY], 'checkpoint_proofs': checkpoint_proof,
              'guard_preflight': {'state': 'FRESH_GUARD_ADMITS_RESUME', 'read_only': True, 'guard_tick_called': False},
              'training_flags_written_by_installer': False, 'trainer_service_actions_by_installer': 0,
              'handback_handler_called_by_installer': False, 'admission_or_wrapper_changed': False,
              'media_jobs_created_or_retried': 0, 'target_task': TASK, 'tasks_requeued': 0,
              'historical_claims_replayed': False, 'private_prompts_exported': False, 'rollback': False}
    def save(): h.atomic(receipt, encoded(result))
    def install(path, raw, mode):
        require(not h.global_stop(), 'STOP_BEFORE_WRITE')
        saved[path] = h.read(path) if path.exists() else None
        modes[path] = stat.S_IMODE(path.stat().st_mode) if path.exists() else mode
        if saved[path] is not None: h.atomic(backup / str(path.relative_to(ROOT)), saved[path])
        written[path] = digest(raw); h.atomic(path, raw); os.chmod(path, mode)
        require(h.read(path) == raw, 'INSTALL_READBACK')
    def start():
        require(not h.global_stop(), 'STOP_BEFORE_DISPATCHER_START')
        require(h.command(['supervisorctl', 'start', h.SERVICE], 30)[0] == 0, 'DISPATCHER_START')
        until = time.monotonic() + 15
        while h.service()['state'] != 'RUNNING':
            require(time.monotonic() < until and not h.global_stop(), 'DISPATCHER_START_TIMEOUT'); time.sleep(.5)
    def compare_others(value):
        require(all(key in value['tasks'] and digest(encoded(value['tasks'][key])) == pin for key, pin in others.items()), 'OTHER_TASK_CHANGED')
    def write_queue(value):
        require(not h.global_stop(), 'STOP_BEFORE_QUEUE_WRITE')
        h.atomic(QUEUE_STATE, encoded(value)); h.atomic(QUEUE_LINES, queue_lines(value))
        require(strict(h.read(QUEUE_STATE, 16 * 1024 ** 2)) == value
                and h.read(QUEUE_LINES, 16 * 1024 ** 2) == queue_lines(value), 'QUEUE_READBACK')
    try:
        require(not flag.exists() and not flag.is_symlink(), 'EXISTING_MAINTENANCE')
        fd = os.open(installer.plain(flag), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream: stream.write(note); stream.flush(); os.fsync(stream.fileno())
        owned_flag = True; save(); result['idle_before'] = base.drain(h, started, timeout=20)
        sources(BEFORE); require(fixed_evidence(h, fresh, guard, ctx, fair) == fixed_before, 'PRESTOP_EVIDENCE_CHANGED')
        preserve_checkpoints(ctx, manifests, identities)
        jobs_before = fair.job_history(h)
        result['dispatcher_group'] = fresh.dispatcher_group(h, recovery, fixed_before['training'])
        python = h.process(h.service()['pid'])['argv'][0]
        stop_attempted = True
        require(h.command(['supervisorctl', 'stop', h.SERVICE], 30)[0] == 0 and h.service()['state'] == 'STOPPED', 'DISPATCHER_STOP')
        sources(BEFORE); require(fixed_evidence(h, fresh, guard, ctx, fair) == fixed_before, 'POSTSTOP_EVIDENCE_CHANGED')
        state, raw_state = queue(h); raw_lines = h.read(QUEUE_LINES, 16 * 1024 ** 2)
        lines = [strict(line) for line in raw_lines.splitlines() if line.strip()]
        require(len(lines) == len(state['tasks']) and {row['id']: row for row in lines} == state['tasks']
                and not any(row.get('status') == 'running' for row in state['tasks'].values()), 'QUEUE_SYNC_OR_RUNNING')
        old_task = copy.deepcopy(state['tasks'].get(TASK)); archive_raw = encoded(old_task)
        new_task = pending_task(old_task, request, source, digest(archive_raw))
        others = {key: digest(encoded(row)) for key, row in state['tasks'].items() if key != TASK}
        archive = {'target_task.json': archive_raw, 'target_claim.json': encoded(old_task['owner_claim']),
                   'target_result.json': encoded(old_task['result']), 'queue_before.json': raw_state, 'queue_before.jsonl': raw_lines}
        for name, raw in archive.items():
            path = backup / name; h.atomic(path, raw)
            require(h.read(path, 16 * 1024 ** 2) == raw and stat.S_IMODE(path.stat().st_mode) == 0o600, 'PRIVATE_ARCHIVE_READBACK')
        result['archive'] = {name: {'sha256': digest(raw), 'bytes': len(raw)} for name, raw in archive.items()}
        if not overlay_path.exists(): install(overlay_path, assets[OVERLAY], 0o644)
        install(DISPATCHER, after, modes.get(DISPATCHER, stat.S_IMODE(DISPATCHER.stat().st_mode)))
        result['binding_smoke'] = smoke(python)
        preserve_checkpoints(ctx, manifests, identities)
        require(fixed_evidence(h, fresh, guard, ctx, fair) == fixed_before, 'BEFORE_RETRY_EVIDENCE_CHANGED')
        state['tasks'][TASK] = new_task; queue_written = True; write_queue(state)
        start(); result['idle_after'] = base.drain(h, time.time(), timeout=20)
        current, _ = queue(h); compare_others(current)
        require(current['tasks'].get(TASK) == new_task and new_task['status'] == 'pending'
                and not new_task.get('owner_claim') and not any(t.get('status') == 'running' for t in current['tasks'].values()),
                'PENDING_RETRY_NOT_VERIFIED')
        sources(digest(after)); preserve_checkpoints(ctx, manifests, identities)
        require(fixed_evidence(h, fresh, guard, ctx, fair) == fixed_before and fair.job_history(h) == jobs_before,
                'PRE_RELEASE_STATE_CHANGED')
        require(h.active_model() == fresh.CHAT and h.health() == {'8080': 200, '8081': 200, '8082': 200}
                and h.read(flag, 4096) == note and not h.global_stop(), 'HEALTH_OR_MAINTENANCE_CHANGED')
        result.update(state='HANDOFF_RETRY_BOUND_AND_PENDING_VERIFIED', tasks_requeued=1,
                      original_retry_counter_preserved=True, old_claim_and_result_archived=True,
                      other_tasks_preserved=len(others), media_job_history_preserved=True,
                      training_flags_preserved_until_release=True, dispatcher_only_restarted=True)
        save(); flag.unlink(); owned_flag = False; released = True; success = True
    except Exception as exc:
        result.update(state='HOLD_QWEN_HANDBACK_RETRY_INSTALL', reason=safe(exc))
        if not released and (written or stop_attempted or queue_written):
            try:
                for path, pin in written.items():
                    raw = base.current_or_missing(h, path)
                    require(raw == saved[path] or raw is not None and digest(raw) == pin, 'ROLLBACK_FOREIGN_SOURCE')
                rollback_plan = base.rollback_controller_plan(h.service()['state'], bool(written or queue_written))
                if rollback_plan['stop_first']:
                    fresh.dispatcher_group(h, recovery, fresh.training_snapshot(h))
                    require(h.command(['supervisorctl', 'stop', h.SERVICE], 30)[0] == 0 and h.service()['state'] == 'STOPPED', 'ROLLBACK_STOP')
                if queue_written:
                    current, _ = queue(h); compare_others(current)
                    require(current['tasks'].get(TASK) in (old_task, new_task), 'ROLLBACK_FOREIGN_CLAIM')
                    current['tasks'][TASK] = old_task; write_queue(current); result['queue_rollback_verified'] = True
                base.restore(h, saved, written, backup, modes); result['rollback'] = bool(written or queue_written)
                if rollback_plan['restart']:
                    start()
            except Exception as rollback_error: result['rollback_error'] = safe(rollback_error)
    finally:
        try:
            if owned_flag and 'rollback_error' not in result and flag.exists() and h.read(flag, 4096) == note:
                flag.unlink(); owned_flag = False
        except Exception as cleanup_error: result['maintenance_cleanup_error'] = safe(cleanup_error)
        finally:
            os.close(maintenance); os.close(controller)
    if success:
        until = time.monotonic() + 45
        while True:
            try:
                result['handback_observation'] = observation(h, old_task['owner_claim'])
                row = result['handback_observation']
                if row['task_state'] in ('done', 'blocked', 'failed') or time.monotonic() >= until: break
            except Exception as exc:
                result['handback_observation'] = {'state': 'OBSERVATION_HELD', 'reason': safe(exc)}
                if time.monotonic() >= until: break
            time.sleep(2)
    result.update(finished_at=time.time(), maintenance_flag_retained=owned_flag,
                  dispatcher_service_after=h.service(), health_after=h.health())
    save(); raw = h.read(receipt, 262144); require(raw == encoded(result), 'RECEIPT_READBACK')
    emit('qwen_handback_retry_install', result)
    emit('qwen_handback_retry_context', {'request': request, 'source_sha': source,
         'receipt_sha256': digest(raw), 'receipt_bytes': len(raw), 'state': result['state']})
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit('qwen_handback_retry_preflight', {'state': 'HOLD', 'reason': safe(exc)})
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
