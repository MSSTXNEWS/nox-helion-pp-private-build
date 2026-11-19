#!/usr/bin/env python3
"""Two independent, pinned read-only probes; no native source or state writes.

The browser probe observes a held runtime gate successfully. Its false gate
remains visible and is never converted into a claim that browser QA can run.
Child completion markers are consumed; one final marker covers both processes.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

SCHEMA = 'NOX_OWNER_LOG_BROWSER_READONLY_BATCH_V1'
PINS = {
    'owner_log_selected_size_probe.py': '41ee4517a8000feb03af5aaf5a57df4e6a889e63f6fd29d2712d4ba719efab57',
    'owner_log_space_probe.py': '92367db1f1f010a5eba2cfd1e69ed34ed5332711b62f60b2b974d60a484c680a',
    'owner_builder_proc_probe.py': '1743c8587dac72f412400be9059d1fe01ef73a1955af2056ff77a550e53af3ff',
    'owner_browser_runtime_inspect.py': '54cb27fbbfbfe25e8129d88a43b4975b5b4b3a64b0ed7eaa5d651c98fae1d280',
}
PHASES = (
    {'name': 'selected_logs', 'entry': 'owner_log_selected_size_probe.py',
     'dependencies': ('owner_log_space_probe.py', 'owner_builder_proc_probe.py'), 'timeout': 32,
     'kinds': ('selected_log_size_probe',), 'schema': 'NOX_OWNER_SELECTED_LOG_SIZE_PROBE_V1',
     'success_state': 'READ_ONLY_SELECTED_LOG_ESTIMATES'},
    {'name': 'browser_runtime', 'entry': 'owner_browser_runtime_inspect.py', 'dependencies': (), 'timeout': 12,
     'kinds': ('browser_runtime_inspect', 'browser_runtime_inspect_hold'),
     'schema': 'NOX_BROWSER_RUNTIME_METADATA_V1', 'success_state': 'RUNTIME_METADATA_OBSERVED'},
)
OUTPUT_LIMIT = 65536
TOTAL_SECONDS = 50

# The split namespace key also survives the operator's single bundle-token
# substitution. Each probe gets its own interpreter and SIGALRM namespace.
CHILD = r'''
import base64,json,re,sys
try:
    raw=sys.stdin.buffer.read(262145)
    if len(raw)>262144: raise ValueError('input bound')
    value=json.loads(raw)
    scope={'__name__':'__main__','__file__':'<pinned-readonly-probe>'}
    scope['__NOX_'+'BUNDLE_JSON__']=value['bundle']
    exec(compile(base64.b64decode(value['source'],validate=True),'<pinned-readonly-probe>','exec'),scope)
except SystemExit as exc:
    raise SystemExit(exc.code if type(exc.code) is int else 2)
except BaseException as exc:
    name=type(exc).__name__
    if not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,79}',name): name='UNCLASSIFIED'
    print('NOX_BATCH_CHILD_FAILURE='+json.dumps({'error_class':name}),flush=True)
    raise SystemExit(2)
'''


class Hold(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise Hold('HOLD_READONLY_BATCH_' + code)


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()


def safe(exc):
    value = str(exc)
    return value if re.fullmatch('HOLD_[A-Z0-9_]{1,100}', value) else 'HOLD_READONLY_BATCH_' + type(exc).__name__.upper()


def payload(phase):
    selected = {}
    for name in (phase['entry'], *phase['dependencies']):
        raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
        require(0 < len(raw) <= 65536 and hashlib.sha256(raw).hexdigest() == PINS[name], 'SOURCE_PIN')
        selected[name] = base64.b64encode(raw).decode()
    value = {'source': selected.pop(phase['entry']), 'bundle': selected}
    raw = encoded(value)
    require(len(raw) <= 262144, 'INPUT_BOUND')
    return raw


def parse_output(raw, phase, code):
    require(len(raw) <= OUTPUT_LIMIT, 'OUTPUT_BOUND')
    records, markers = [], []
    protocol_ok = True
    child_error = None
    for line in raw.decode('utf-8', errors='strict').splitlines():
        if not line:
            continue
        if line.startswith('NOX_MAINT_REPAIR='):
            value = json.loads(line.partition('=')[2], parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict) or set(value) != {'kind', 'data'} or value['kind'] not in phase['kinds'] or not isinstance(value['data'], dict):
                protocol_ok = False
                continue
            records.append(value)
        elif line in ('NOX_MAINT_REPAIR_COMPLETE=true', 'NOX_MAINT_REPAIR_COMPLETE=false'):
            markers.append(line.endswith('=true'))
        elif line.startswith('NOX_BATCH_CHILD_FAILURE='):
            value = json.loads(line.partition('=')[2])
            name = value.get('error_class') if isinstance(value, dict) else None
            child_error = name if isinstance(name, str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,79}', name) else 'UNCLASSIFIED'
            protocol_ok = False
        else:
            # Unexpected stdout is never echoed: it can contain private errors.
            protocol_ok = False
    success_rows = [row for row in records if row['kind'] == phase['kinds'][0]
                    and row['data'].get('schema') == phase['schema']
                    and row['data'].get('state') == phase['success_state']]
    success = code == 0 and protocol_ok and markers == [True] and len(records) == len(success_rows) == 1
    return records, {'success': success, 'child_exit_code': code, 'completion_markers': markers,
                     'protocol_valid': protocol_ok, 'child_error_class': child_error,
                     'record_count': len(records)}


def run_phase(phase, context, deadline):
    start = time.monotonic()
    result = {'phase': phase['name'], 'success': False, 'source_sha256': PINS[phase['entry']],
              'temporary_source_files_written': 0, 'raw_stderr_exported': False}
    records = []
    try:
        raw = payload(phase)
        remaining = deadline - time.monotonic()
        require(remaining > 1, 'TOTAL_DEADLINE')
        env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
               'NOX_OWNER_REQUEST_ID': context['request'], 'NOX_OWNER_SOURCE_SHA': context['source_sha']}
        proc = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', CHILD], input=raw,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              env=env, timeout=min(phase['timeout'], remaining))
        records, detail = parse_output(proc.stdout, phase, proc.returncode)
        result.update(detail)
        if not result['success']:
            result['state'] = 'PROBE_HELD_OR_FAILED'
        else:
            result['state'] = 'READ_ONLY_PROBE_FINISHED'
    except subprocess.TimeoutExpired:
        # subprocess.run terminates and reaps only this batch-owned child.
        # Partial bytes are unverified and are not relayed as a result.
        result.update(state='PROBE_TIMED_OUT', reason='HOLD_READONLY_BATCH_CHILD_TIMEOUT')
    except Exception as exc:
        result.update(state='PROBE_HELD_OR_FAILED', reason=safe(exc))
    result['elapsed_seconds'] = round(time.monotonic() - start, 3)
    return records, result


def execute(context):
    started = time.monotonic(); deadline = started + TOTAL_SECONDS
    records, phases = [], []
    for phase in PHASES:
        observed, result = run_phase(phase, context, deadline)
        records.extend(observed); phases.append(result)
    browser = next((r['data'] for r in records if r['kind'] == 'browser_runtime_inspect'), {})
    logs = next((r['data'] for r in records if r['kind'] == 'selected_log_size_probe'), {})
    success = len(phases) == 2 and all(p['success'] for p in phases)
    observed_holds = []
    if browser.get('original_runtime_gate_passes') is False:
        observed_holds.append('ORIGINAL_BROWSER_RUNTIME_GATE_HELD')
    count, measured = logs.get('selected_count'), logs.get('full_stable_estimate_count')
    if type(count) is int and type(measured) is int and measured < count:
        observed_holds.append('SOME_SELECTED_LOG_ESTIMATES_HELD_OR_PARTIAL')
    result = {'schema': SCHEMA, **context, 'success': success,
        'state': ('READ_ONLY_PROBES_COMPLETED_WITH_OBSERVED_HOLDS' if observed_holds else 'READ_ONLY_PROBES_COMPLETED')
                 if success else 'READ_ONLY_PROBES_PARTIAL_OR_HELD',
        'phases': phases, 'successful_probe_count': sum(p['success'] for p in phases),
        'observed_holds': observed_holds, 'completion_is_probe_execution_not_runtime_readiness': True,
        'original_browser_runtime_gate_passes': browser.get('original_runtime_gate_passes'),
        'browser_gate_false_is_observation_not_runtime_readiness': True,
        'selected_log_full_stable_estimate_count': logs.get('full_stable_estimate_count'),
        'selected_log_count': logs.get('selected_count'), 'actual_freed_bytes': 0,
        'services_or_training_flags_changed': False, 'browser_started': False,
        'native_chat_posts': 0, 'source_or_state_files_written': 0,
        'elapsed_seconds': round(time.monotonic() - started, 3), 'source_pins': PINS}
    return records, result


def main():
    context = {'request': os.environ.get('NOX_OWNER_REQUEST_ID', ''), 'source_sha': os.environ.get('NOX_OWNER_SOURCE_SHA', '')}
    require(re.fullmatch('[0-9]{1,24}', context['request']) and re.fullmatch('[a-f0-9]{40}', context['source_sha']), 'OWNER_CONTEXT')
    records, result = execute(context)
    for row in records:
        print('NOX_MAINT_REPAIR=' + encoded(row).decode(), flush=True)
    print('NOX_MAINT_REPAIR=' + encoded({'kind': 'log_browser_readonly_batch', 'data': result}).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(result['success']).lower(), flush=True)
    return 0 if result['success'] else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + encoded({'kind': 'log_browser_readonly_batch', 'data': {
            'schema': SCHEMA, 'state': 'READ_ONLY_BATCH_PREFLIGHT_HELD', 'reason': safe(exc),
            'success': False, 'source_or_state_files_written': 0}}).decode(), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
