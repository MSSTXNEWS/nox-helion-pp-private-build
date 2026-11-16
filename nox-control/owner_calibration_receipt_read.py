#!/usr/bin/env python3
"""Read the exact completed calibration attempt without exporting its ciphertext.

This diagnostic loads pinned read-only helpers, reads three fixed receipt files,
and projects current training evidence only after checking the actual admission.
It never installs sources, changes services, starts an observer, or writes files.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

PINS = {
    'owner_native_repair': 'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0',
    'owner_training_status': '1688fc70b8663434beed02b6d4488ca8e5f636af71aa8e5498e5606f2b69751a',
}
TARGET_REQUEST = '6906626126'
TARGET_SOURCE = 'c88d33ed8fbacaf58238921f600ec7641782b516'
ORIGIN = {'request': '6905764817', 'source_sha': 'e4549616aa13295febc44dc78a3a033870f9071d',
          'receipt_sha256': '960e96fba9d24bb0835df1a46bf9971f770aaab78c0587e20a897b53fd6aeb46'}
RECEIPTS = (
    ('batch', 'owner_checkpoint_calibration_', 'NOX_OWNER_CHECKPOINT_CALIBRATION_BATCH_V1'),
    ('calibration', 'owner_maintenance_', 'NOX_OWNER_TRAINING_RESUME_V1'),
    ('status_binding', 'owner_training_status_binding_', 'NOX_OWNER_TRAINING_STATUS_BINDING_DEPLOY_V1'),
)
BOOLS = frozenset(('training_started', 'optimizer_steps_verified', 'continuation_to_1000_started',
    'continuation_to_1000_admitted', 'weights_merged', 'scaler_reset', 'optimizer_reset',
    'hold_retained', 'pause_retained', 'chat_health_regression', 'proxy_restarted', 'model_restarted',
    'training_control_performed', 'preservation_verified', 'rollback', 'rollback_verified',
    'positive_optimizer_steps_verified', 'tensor_delta_verified', 'checkpoint_saved_verified',
    'checkpoint_restore_verified', 'cuda_initialized', 'files_modified', 'read_only',
    'current_checkpoint_files_verified', 'metadata_used_as_optimizer_evidence', 'history_text_exported'))
NUMBERS = frozenset(('started', 'started_at', 'finished', 'finished_at', 'observed_at',
    'global_step', 'start_step', 'successful_optimizer_steps', 'skipped_optimizer_steps',
    'optimizer_steps', 'checkpoint_file_count', 'checkpoint_global_step', 'weights_deleted',
    'checkpoints_deleted', 'optimizer_state_entries', 'optimizer_parameter_groups',
    'optimizer_parameter_count', 'optimizer_empty_parameter_groups', 'target_step',
    'planned_steps', 'max_steps', 'return_code', 'checkpoint_bytes_hashed', 'step',
    'scale', 'growth_factor', 'backoff_factor', 'growth_interval', 'growth_tracker',
    'segments', 'pid', 'ppid', 'start_ticks', 'target_global_step', 'inferred_run_start_step',
    'nonfinite_grad_norm_count', 'owner_http', 'anonymous_http', 'media_verified_files',
    'drive_verified_files'))
CODES = frozenset(('schema', 'state', 'verification_state', 'reason', 'error', 'failure_cause',
    'counter_chain_state', 'current_model_merge_inclusion', 'scope'))


def fail(code):
    raise RuntimeError(code)


def safe(exc):
    value = str(exc)
    return value if re.fullmatch(r'(?:HOLD|WAIT)_[A-Z0-9_]{1,150}', value) else 'HOLD_CALIBRATION_RECEIPT_READ_'+type(exc).__name__.upper()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def dependencies():
    # Validate both injected byte strings before executing either module.
    blobs = {}
    for name, pin in PINS.items():
        try:
            raw = base64.b64decode(BUNDLE.get(name+'.py', ''), validate=True)
        except (ValueError, TypeError):
            fail('HOLD_CALIBRATION_RECEIPT_READ_BUNDLE')
        if not raw or len(raw) > 1_000_000 or digest(raw) != pin:
            fail('HOLD_CALIBRATION_RECEIPT_READ_BUNDLE')
        blobs[name] = raw
    modules = {}
    for name, raw in blobs.items():
        module = types.ModuleType(name+'_receipt_read')
        module.__file__ = '<'+name+'_receipt_read>'
        sys.modules[module.__name__] = module
        exec(compile(raw, module.__file__, 'exec'), module.__dict__)
        modules[name] = module
    return modules['owner_training_status'], modules['owner_native_repair']


def scalars(value):
    """No arbitrary strings, paths, source text, logs, or ciphertext are copied."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, item in value.items():
        if key in BOOLS and type(item) is bool:
            result[key] = item
        elif key in NUMBERS and (item is None or type(item) in (int, float) and math.isfinite(item)):
            result[key] = item
        elif key in CODES and isinstance(item, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,160}', item):
            result[key] = item
    return result


def service(value):
    if not isinstance(value, dict):
        return {'state': 'UNAVAILABLE'}
    result = {k: value[k] for k in ('rc', 'pid') if type(value.get(k)) is int}
    if value.get('pid') is None:
        result['pid'] = None
    result['state'] = value.get('state') if value.get('state') in (
        'STOPPED', 'STARTING', 'RUNNING', 'BACKOFF', 'STOPPING', 'EXITED', 'FATAL', 'UNKNOWN') else 'UNKNOWN'
    return result


def context_projection(status, value):
    try:
        context = status.context_value(value)
        if context == ORIGIN or (context['request'] == TARGET_REQUEST and context['source_sha'] == TARGET_SOURCE):
            return context
    except Exception:
        pass
    return None


def training_projection(value):
    result = scalars(value)
    for name in ('verified_counter_chain', 'historical_verified_checkpoint', 'latest_verified_checkpoint'):
        if isinstance(value.get(name), dict):
            result[name] = scalars(value[name])
            metadata = value[name].get('trainer_state_metadata')
            if isinstance(metadata, dict):
                result[name]['trainer_state_metadata'] = scalars(metadata)
    flags = value.get('flags')
    if isinstance(flags, dict):
        result['flags'] = {k: flags[k] for k in ('hold_present', 'pause_present', 'owned_failure', 'owned_complete')
                           if type(flags.get(k)) is bool}
    run = value.get('current_run')
    if isinstance(run, dict):
        result['current_run'] = {k: scalars(run[k]) for k in ('process', 'telemetry') if isinstance(run.get(k), dict)}
        phase = (run.get('telemetry') or {}).get('phase')
        if phase in ('loading_owner_hybrid', 'train_owner_hybrid', 'VERIFIED_BOUNDED_ADAPTER_UPDATE', 'CHECKPOINTED_OWNER_STOP'):
            result['current_run'].setdefault('telemetry', {})['phase'] = phase
        resume = (run.get('process') or {}).get('resume_argument')
        if type(resume) is bool:
            result['current_run'].setdefault('process', {})['resume_argument'] = resume
    return result


def receipt_projection(status, label, value):
    result = scalars(value)
    for key in ('service_after',):
        if isinstance(value.get(key), dict):
            result[key] = service(value[key])
    for key in ('baseline_saved_state', 'bounded_optimizer_proof', 'bounded_update_receipt', 'progress_after'):
        if isinstance(value.get(key), dict):
            result[key] = scalars(value[key])
    if label == 'batch':
        result['stages'] = []
        for row in value.get('stages', [])[:3]:
            if isinstance(row, dict) and row.get('stage') in (
                'checkpoint5_encrypted_export', 'bounded_amp_calibration', 'training_status_binding'):
                result['stages'].append({'stage': row['stage'], **scalars(row)})
    elif label == 'calibration':
        result['saved_scaler_numeric_proof'] = None
        for row in value.get('steps', [])[:256]:
            if isinstance(row, dict) and row.get('kind') == 'saved_optimizer_and_scaler_numeric_projection':
                data = row.get('data', {})
                if not isinstance(data, dict):
                    continue
                proof = scalars(data)
                proof['scaler'] = scalars(data.get('scaler'))
                counts = data.get('optimizer_parameter_counts')
                if isinstance(counts, list) and len(counts) <= 100 and all(type(x) is int and 0 <= x <= 100000 for x in counts):
                    proof['optimizer_parameter_counts'] = counts
                result['saved_scaler_numeric_proof'] = proof
        pointer = value.get('admission')
        if isinstance(pointer, dict):
            result['admission'] = {'matches_target_context': pointer.get('request') == TARGET_REQUEST and pointer.get('source_sha') == TARGET_SOURCE,
                                   **scalars(pointer)}
            if type(pointer.get('resume')) is bool:
                result['admission']['resume'] = pointer['resume']
    elif label == 'status_binding':
        result['training_admission'] = context_projection(status, value.get('training_admission'))
        acceptance = value.get('acceptance')
        if isinstance(acceptance, dict):
            result['acceptance'] = scalars(acceptance)
            if isinstance(acceptance.get('training_projection'), dict):
                result['acceptance']['training_projection'] = training_projection(acceptance['training_projection'])
        result['installed'] = [{'name': row['name'], 'sha256': row['sha256']} for row in value.get('installed', [])[:5]
            if isinstance(row, dict) and row.get('name') in ('owner_training_status.py', 'owner_training_status_binding.py',
                'chat_proxy.py', 'nox_v137_owner_self_observation.py', 'owner_training_status.json')
            and isinstance(row.get('sha256'), str) and re.fullmatch('[a-f0-9]{64}', row['sha256'])]
    return result


def read_receipts(status):
    public, private = {}, {}
    for label, prefix, schema in RECEIPTS:
        row = {'filename': prefix+TARGET_REQUEST+'.json', 'read_state': 'UNAVAILABLE', 'sha256': None}
        public[label] = row
        try:
            value, sha = status.document(status.ROOT/'state'/row['filename'], 2*1024**2)
            row['sha256'] = sha
            if value.get('schema') != schema or value.get('request') != TARGET_REQUEST or value.get('source_sha') != TARGET_SOURCE:
                fail('HOLD_CALIBRATION_RECEIPT_READ_SCOPE')
            private[label] = (value, sha)
            row.update(read_state='VERIFIED_EXACT_RECEIPT', projection=receipt_projection(status, label, value))
        except FileNotFoundError:
            row.update(read_state='MISSING', reason='HOLD_CALIBRATION_RECEIPT_NOT_PRESENT')
        except Exception as exc:
            row.update(read_state='HOLD', reason=safe(exc))
    return public, private


def current_training(status, receipts):
    result = {'state': 'UNVERIFIED_CURRENT_CONTEXT', 'continuation_admitted_by_reader': False,
              'global_process_coverage_verified': False}
    try:
        pointer, pointer_sha = status.document(status.ROOT/'state/owner_training_admission.json')
        result['pointer_sha256'] = pointer_sha
        if pointer.get('request') == ORIGIN['request'] and pointer.get('source_sha') == ORIGIN['source_sha']:
            context = status.context_value(ORIGIN)
        elif (pointer.get('request') == TARGET_REQUEST and pointer.get('source_sha') == TARGET_SOURCE
              and type(pointer.get('max_steps')) is int and pointer['max_steps'] == 20):
            value, sha = receipts.get('calibration', (None, None))
            if not isinstance(value, dict) or value.get('admission') != pointer:
                fail('HOLD_CALIBRATION_RECEIPT_CURRENT_ADMISSION')
            context = status.context_value({'request': TARGET_REQUEST, 'source_sha': TARGET_SOURCE, 'receipt_sha256': sha})
        else:
            fail('HOLD_CALIBRATION_RECEIPT_CURRENT_POINTER')
        # A current failed attempt may be observed, never promoted to a pending
        # or positive continuation merely because its pointer was installed.
        status.admission(context)
        observed = status.snapshot(context)
        status.admission(context)
        _, after_sha = status.document(status.ROOT/'state/owner_training_admission.json')
        if after_sha != pointer_sha:
            fail('HOLD_CALIBRATION_RECEIPT_POINTER_CHANGED')
        result.update(state='VERIFIED_CURRENT_CONTEXT_READ_ONLY', context=context,
                      training=training_projection(observed))
    except Exception as exc:
        result['reason'] = safe(exc)
    return result


def resources(helper):
    """Only bounded status/nvidia-smi reads; never helper mutation functions."""
    original = helper.command
    def bounded(args, timeout=12):
        allowed = (args == ['supervisorctl', 'status', helper.SERVICE] or args == [
            'nvidia-smi', '--query-gpu=index,memory.used,memory.free,utilization.gpu', '--format=csv,noheader,nounits'])
        if not allowed:
            fail('HOLD_CALIBRATION_RECEIPT_COMMAND_SCOPE')
        return original(args, min(timeout, 4))
    helper.command = bounded
    result = {'training_service': service(helper.service_state()), 'gpu': helper.gpu(), 'cgroup': {}}
    for name in ('memory.current', 'memory.max', 'memory.high', 'cpu.max', 'memory.events'):
        try:
            with (Path('/sys/fs/cgroup')/name).open('r') as stream:
                raw = stream.read(4097)
            if len(raw) > 4096:
                continue
            fields = raw.split()
            if name in ('memory.current', 'memory.max', 'memory.high') and len(fields) == 1:
                if fields[0].isdigit(): result['cgroup'][name] = int(fields[0])
                elif fields[0] == 'max': result['cgroup'][name] = None
            elif name == 'cpu.max' and len(fields) == 2 and all(x.isdigit() for x in fields) and int(fields[1]) > 0:
                result['cgroup']['cpu_quota_cores'] = int(fields[0])/int(fields[1])
            elif name == 'memory.events':
                result['cgroup']['memory_events'] = {line.split()[0]: int(line.split()[1]) for line in raw.splitlines()
                    if len(line.split()) == 2 and line.split()[0] in ('low','high','max','oom','oom_kill','oom_group_kill') and line.split()[1].isdigit()}
        except OSError:
            continue
    return result


def main():
    status, helper = dependencies()
    receipts, private = read_receipts(status)
    result = {'schema': 'NOX_OWNER_CALIBRATION_RECEIPT_READ_V1', 'observed_at': time.time(),
        'target_request': TARGET_REQUEST, 'target_source_sha': TARGET_SOURCE, 'source_pins': PINS,
        'read_only': True, 'training_control_performed': False, 'files_written': 0,
        'ciphertext_exported': False, 'raw_logs_or_private_content_exported': False,
        'receipts': receipts, 'current_training': current_training(status, private)}
    try:
        result['resources_now'] = resources(helper)
    except Exception as exc:
        result['resources_now'] = {'state': 'HOLD', 'reason': safe(exc)}
    result['state'] = 'READ_ONLY_OBSERVATION_COMPLETE'
    result['all_three_receipts_verified'] = all(row['read_state'] == 'VERIFIED_EXACT_RECEIPT' for row in receipts.values())
    raw = json.dumps({'kind': 'calibration_receipt_read', 'data': result}, separators=(',', ':'), allow_nan=False)
    if len(raw.encode()) > 60_000:
        fail('HOLD_CALIBRATION_RECEIPT_OUTPUT_BOUND')
    print('NOX_MAINT_REPAIR='+raw, flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'calibration_receipt_read_hold', 'data': {'reason': safe(exc)}}), flush=True)
        raise SystemExit(2)
