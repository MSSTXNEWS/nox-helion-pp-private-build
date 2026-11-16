#!/usr/bin/env python3
"""Read the exact checkpoint8/media943c handback; never resume or clear flags.

The frozen observer supplies bounded regular-file readers and Supervisor status.
Only categorical projections leave this process. No model/checkpoint payload,
private prompt, graph, corpus, traceback, config body or flag content is emitted.
"""
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

OBSERVER = 'owner_qwen_media_retry_observe.py'
OBSERVER_SHA = 'fce01bca74751ee01a993eba7aa8874b4fc58cb2a8b9656212d0d17923ad4018'
ROOT = Path('/root/nox')
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
JOB = '943c960553eb5f6cf13702455d06a5d8'
RESUME_ID = 'owner.media.resume.' + JOB
WINDOW = {'request': '6908281920', 'source_sha': '35931438c591a9bb5a649e851f155c4313f28562',
          'receipt_sha256': 'fa0ed9dd2088a247b2ccc94ad60f9962c0d502121c12bf00e31436c9cf487662'}
SOURCE_PINS = {
    'nox_dispatcher_t855u.py': '89b359b49fe37e219629574eed5ae7ee3d8e756fa5feb64f5274d68b1eccb2bb',
    'owner_qwen_media_handoff.py': '312966b352348f0ae0f403cbe84bbfa2e26f89826f285a0a865965650c7931dc',
    'owner_media_training_handoff.py': '36db3c363ffddfc144c6127e1a9407132bbe39d38996233bf3dd64e5b3cb6ec8',
    'owner_media_runtime.py': 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5',
    'owner_qwen_media_guard.py': 'acd1ec157ba171e979f82b7e058b4a5054a81fae3884ee1cb8ba8fd33c419450',
    'owner_qwen_training_guard.py': '2a6f6ade1a913bf42bc921d997b83109323adf3227570cf29a0ffc61a7b2614c',
}
WRAPPER_SHA = '5bef568fd965f17151b252d8b8d25f00c9b67dd756feef9e30c54cd5b419cd96'
ADMISSION_SHA = '9116c9ffbca959ba7afe80dbb66c36a356a922b87ecd839469d17413bb450499'
CONFIG_SHA = 'c3760b6f7d2f4af6546c32b730c457c562692026344a1e948298c72fe3445f0a'
CHECKPOINT8 = 'checkpoint-u00000008-a00000008-g01794808441026361842'
MANIFEST8 = '107f26c33c62b7e9ee4326013bafd75ed2cc3ad03de14f5da24bcd99c57f78b2'
TERMINAL8 = '8cda027082b101cd14474edf5ef8432dc2263d5b29314a4563805c4af0a3665e'
SERVICE = 'nox-train-volta-t866u'
STATES = {'QUEUED', 'START_INTENT', 'START_UNVERIFIED', 'RESUMED', 'RUNNING', 'STARTING', 'STOPPED',
          'EXITED', 'FATAL', 'BACKOFF', 'STOPPING', 'UNKNOWN', 'COMPLETED', 'CANCELLED', 'BLOCKED',
          'WAITING_RESOURCES', 'YIELDING_TRAINING', 'MONITORING', 'INHIBITED',
          'EXISTING_TRAINER_HOLD_OR_PAUSE', 'TRAINING_RESUME_QUEUED', 'TRAINING_PREVIOUSLY_HELD',
          'TRAINING_REMAINS_CHECKPOINTED', 'ADMITTED_EXISTING_TRAINER_RESUMED',
          'NATIVE_STUDENT_UPDATE_OBSERVED'}
SHA = re.compile('[a-f0-9]{64}')


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_QWEN_HANDBACK_DIAGNOSTIC_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_code(value):
    return value if isinstance(value, str) and (value in STATES or
        re.fullmatch('(HOLD|WAIT|NEEDS)_[A-Z0-9_]{1,120}', value)) else None


def sha(value):
    return value if isinstance(value, str) and SHA.fullmatch(value) else None


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def process(value):
    if not isinstance(value, dict):
        return None
    result = {k: number(value.get(k)) for k in ('pid', 'ppid')}
    for key in ('starttime', 'start_ticks'):
        raw = value.get(key)
        result[key] = raw if type(raw) is int or isinstance(raw, str) and re.fullmatch('[0-9]{1,24}', raw) else None
    result['state'] = safe_code(value.get('state'))
    return result


def observer():
    raw = base64.b64decode(BUNDLE.get(OBSERVER, ''), validate=True)
    require(0 < len(raw) <= 131072 and digest(raw) == OBSERVER_SHA, 'BUNDLE_PIN')
    module = types.ModuleType('_nox_handback_readonly_observer')
    module.__file__ = str(ROOT / 'scripts' / OBSERVER)
    sys.modules[module.__name__] = module
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    module.DEADLINE = time.monotonic() + 25
    return module


def attempt(function):
    try:
        return function()
    except FileNotFoundError:
        return {'present': False}
    except Exception as exc:
        return {'observation': 'HELD', 'reason': safe_code(str(exc)) or 'HOLD_DIAGNOSTIC_READ_UNVERIFIED'}


def json_projection(reader, path, projector, maximum=262144):
    value, meta = reader.document(path, maximum)
    return {'present': True, 'file': meta, **projector(value)}


def checkpoint(value):
    if not isinstance(value, dict):
        return None
    directory = value.get('directory')
    path = value.get('checkpoint')
    return {**{key: number(value.get(key)) for key in ('step', 'successful_optimizer_steps', 'attempted_steps',
            'skipped_steps', 'new_successful_optimizer_steps_in_window', 'verified_bytes', 'files_verified')},
            'manifest_sha256': sha(value.get('manifest_sha256') or value.get('checkpoint_manifest_sha256')),
            'receipt_sha256': sha(value.get('receipt_sha256')), 'lineage_sha256': sha(value.get('lineage_sha256')),
            'full_checkpoint_files_verified_recorded': value.get('full_checkpoint_files_verified') is True,
            'names_observed_checkpoint8': directory == CHECKPOINT8 or path == str(OUTPUT / CHECKPOINT8)}


def yield_projection(value):
    pause = 'NOX_MEDIA_CHECKPOINT_YIELD ' + JOB + '\n'
    return {'job_matches': value.get('job_id') == JOB, 'active': value.get('active') is True,
            'resume': value.get('resume') is True, 'requested_at': number(value.get('requested_at')),
            'pause_token_matches': value.get('pause_token') == pause,
            'wrapper_sha256': sha(value.get('wrapper_sha256')), 'hold_sha256': sha(value.get('hold_sha256')),
            'qwen_admission_sha256': sha(value.get('qwen_admission_sha256')),
            'qwen_student': process(value.get('qwen_student')), 'trainer_before': process(value.get('trainer_before')),
            'checkpoint': checkpoint(value.get('checkpoint')),
            'resume_state': safe_code(value.get('resume_state')), 'resumed_at': number(value.get('resumed_at'))}


def request_projection(value):
    return {'job_matches': value.get('job_id') == JOB, 'stage': safe_code(value.get('stage')),
            'reason': safe_code(value.get('reason')), 'initial_admission_matches': value.get('initial_admission') == WINDOW,
            'source_sha256': sha(value.get('source_sha256')), 'yield_sha256': sha(value.get('yield_sha256')),
            'config_sha256': sha(value.get('config_sha256')), 'created_at': number(value.get('created_at')),
            'start_command_issued': value.get('start_command_issued') if type(value.get('start_command_issued')) is bool else None,
            'start_requested_at': number(value.get('start_requested_at')), 'resumed_at': number(value.get('resumed_at')),
            'baseline_step': number(value.get('baseline_step')), 'process': process(value.get('process'))}


def task_projection(value):
    tasks = value.get('tasks')
    require(isinstance(tasks, dict) and len(tasks) <= 20000, 'QUEUE_BOUND')
    task = tasks.get(RESUME_ID)
    if task is None:
        return {'resume_task_present': False, 'total_tasks': len(tasks)}
    require(isinstance(task, dict), 'TASK_OBJECT')
    result = task.get('result') if isinstance(task.get('result'), dict) else {}
    mentor = task.get('mentor') if isinstance(task.get('mentor'), dict) else {}
    note = task.get('note')
    note_code = safe_code(note)
    if note_code is None and isinstance(note, str):
        match = re.search(r"['\"]state['\"]\s*:\s*['\"]((?:HOLD|WAIT|NEEDS)_[A-Z0-9_]{1,120})['\"]", note[:1000])
        note_code = match[1] if match else None
    claim = task.get('owner_claim') or {}
    return {'resume_task_present': True, 'total_tasks': len(tasks), 'task_id_matches': task.get('id') == RESUME_ID,
            'handler_matches': task.get('handler') == 'owner_media_resume',
            'state': task.get('status') if task.get('status') in ('pending', 'wait', 'retry', 'running', 'done', 'blocked', 'failed') else None,
            'retries': number(task.get('retries')), 'next_try': number(task.get('next_try')),
            'note_present': bool(note), 'note_code': note_code, 'result_state': safe_code(result.get('state')),
            'result_verified_recorded': result.get('verified') is True, 'mentor_state': safe_code(mentor.get('state')),
            'claim_pid': number(claim.get('pid')), 'claim_sha256': digest(json.dumps(claim, sort_keys=True, allow_nan=False).encode())}


def terminal_projection(value):
    return {'state': safe_code(value.get('state')), 'reload_verified': value.get('reload_verified') is True,
            **{k: number(value.get(k)) for k in ('successful_optimizer_steps', 'new_successful_optimizer_steps',
               'attempted_steps', 'skipped_steps', 'evaluated_at_update', 'holdout_loss')},
            'process_identity': process(value.get('process_identity')), 'checkpoint': checkpoint(value),
            'final_adapter_tensor_sha256': sha(value.get('final_adapter_tensor_sha256')),
            'update_evidence_count': len(value['update_evidence']) if isinstance(value.get('update_evidence'), list) else None}


def flag(reader, name, expected):
    raw, meta = reader.read(ROOT / 'state' / name, 4096)
    return {'present': True, 'file': meta, 'matches_exact_owned_value': raw == expected}


def snapshot(reader):
    start = time.time()
    state = ROOT / 'state'
    directory = state / 'media/training_handback' / JOB
    result = {'schema': 'NOX_QWEN_HANDBACK_DIAGNOSTIC_V1', 'started_at': start, 'job_id': JOB,
              'read_only': True, 'files_written': 0, 'service_actions': 0, 'flags_changed': False,
              'checkpoint_payload_bytes_read': 0, 'private_prompts_exported': False,
              'window_admission': WINDOW}
    result['services'] = attempt(reader.services)
    result['sources'] = {name: attempt(lambda name=name, pin=pin: {
        'matches_expected': digest(reader.read(ROOT / 'scripts' / name)[0]) == pin}) for name, pin in SOURCE_PINS.items()}
    controls = {'wrapper': (ROOT / 'scripts/run_train_volta_t866u.sh', WRAPPER_SHA),
                'admission': (state / 'owner_training_admission.json', ADMISSION_SHA),
                'handoff_configuration': (ROOT / 'config/owner_qwen_media_handoff.json', CONFIG_SHA)}
    raw_before = {}
    def control(name, path, expected):
        raw, meta = reader.read(path); raw_before[name] = raw
        return {'file': meta, 'matches_expected': digest(raw) == expected}
    result['controls'] = {key: attempt(lambda key=key, pair=pair: control(key, *pair)) for key, pair in controls.items()}
    result['yield'] = attempt(lambda: json_projection(reader, state / 'media/training_yield.json', yield_projection))
    result['handback_request'] = attempt(lambda: json_projection(reader, directory / 'request.json', request_projection))
    result['resume_task'] = attempt(lambda: json_projection(reader, ROOT / 'state/dispatcher/state.json', task_projection, 8 * 1024 ** 2))
    result['terminal'] = attempt(lambda: json_projection(reader, OUTPUT / 'owner_last_result.json', terminal_projection))
    result['terminal']['matches_observed_checkpoint8_receipt'] = (result['terminal'].get('file') or {}).get('sha256') == TERMINAL8
    result['latest_checkpoint'] = attempt(lambda: json_projection(reader, OUTPUT / 'latest_checkpoint.json', checkpoint))
    result['media_job'] = attempt(lambda: json_projection(reader, state / 'media/jobs' / (JOB + '.json'), lambda value: {
        'job_matches': value.get('id') == JOB, 'state': safe_code(value.get('state')),
        'generation_verified_recorded': value.get('generation_verified') is True,
        'gpu1_released_recorded': value.get('gpu1_released') is True,
        'training_resume': safe_code(value.get('training_resume')), 'reason': safe_code(value.get('reason'))}))
    owned = {'TRAIN_HOLD.flag': ('OWNER_QWEN_WINDOW_FAILED request=' + WINDOW['request'] + ' goal=1000\n').encode(),
             'TRAIN_PAUSE_REQUEST.flag': ('NOX_MEDIA_CHECKPOINT_YIELD ' + JOB + '\n').encode()}
    result['flags'] = {name: attempt(lambda name=name, raw=raw: flag(reader, name, raw)) for name, raw in owned.items()}
    result['released_flags'] = {name: attempt(lambda name=name, raw=raw: {
        'present': True, 'matches_exact_owned_value': reader.read(directory / ('released-' + name), 4096)[0] == raw})
        for name, raw in owned.items()}
    result['guard'] = attempt(lambda: json_projection(reader, state / 'owner_qwen_training_guard.json', lambda value: {
        'state': safe_code(value.get('state')), 'sampled_at': number(value.get('sampled_at')),
        'inhibit': (value.get('policy_state') or {}).get('inhibit') is True,
        'reason': safe_code((value.get('policy_state') or {}).get('reason')),
        'guard_tick_called': False}))
    result['controls_unchanged_during_read'] = {key: attempt(lambda key=key, pair=pair: {
        'unchanged': key in raw_before and reader.read(pair[0])[0] == raw_before[key]}) for key, pair in controls.items()}
    result['finished_at'] = time.time()
    result['state'] = 'READ_ONLY_HANDBACK_STATE_OBSERVED'
    result['resume_admitted'] = False
    return result


def main():
    code = 0
    try:
        result = snapshot(observer())
    except Exception as exc:
        code = 2
        result = {'schema': 'NOX_QWEN_HANDBACK_DIAGNOSTIC_V1', 'state': 'OBSERVATION_HELD',
                  'reason': safe_code(str(exc)) or 'HOLD_DIAGNOSTIC_READ_UNVERIFIED', 'files_written': 0}
    raw = json.dumps({'kind': 'qwen_handback_diagnostic', 'data': result}, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    require(len(raw.encode()) <= 48000, 'OUTPUT_BOUND')
    print('NOX_MAINT_REPAIR=' + raw, flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + ('true' if code == 0 else 'false'), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
