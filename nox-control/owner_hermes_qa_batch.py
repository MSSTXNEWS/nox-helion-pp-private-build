#!/usr/bin/env python3
"""One connection, two independent pinned processes: Hermes evidence and QA.

Only the unchanged scoped QA repair may alter its two directory modes, private
receipts and one public test conversation. This wrapper never controls services,
training flags or model files. A permissions receipt alone cannot pass QA.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

SCHEMA = 'NOX_OWNER_HERMES_QA_BATCH_V1'
PINS = {
    'owner_hermes_ram_preflight.py': '6b1b0393101d485a12c2b0019095f2aa655c931385645ac655b88f916e154a10',
    'owner_builder_proc_probe.py': '1743c8587dac72f412400be9059d1fe01ef73a1955af2056ff77a550e53af3ff',
    'owner_browser_runtime_repair_entry.py': 'f2a10aa6b5ee6a0f4f293d3efd2f20e188ad0852b14573d37a8f4cbaec0f16e8',
    'owner_browser_runtime_inspect.py': '54cb27fbbfbfe25e8129d88a43b4975b5b4b3a64b0ed7eaa5d651c98fae1d280',
    'owner_browser_stream_only_entry.py': '8866e963acd01f5b5775e079b8d6b85753d8e34ad1d636fcca04f1a6c841d6de',
    'owner_chat_browser_qa.py': 'b76198d8117c3912fb7e1a1ef19c01abc41aa3ac87f4ad919612342edf593587',
    'owner_chat_browser_transport_qa.py': 'e8d256f4ab4de1d53859c1da74237622871354b5d84442bdff1171631f9f05f0',
    'owner_chat_browser_release_qa.py': '42abf7b769b4103f9f3799048fe68da5c93937dbef9b56a8e4a2b5aac2072bc7',
    'owner_chat_stream_only_qa.py': 'd2a426c113f09fb033105d4949ef4e40892a89fbbde43b12f1f804152158779a',
}
PHASES = (
    {'name': 'hermes', 'entry': 'owner_hermes_ram_preflight.py',
     'dependencies': ('owner_builder_proc_probe.py',), 'timeout': 180,
     'kinds': ('hermes_ram_preflight',), 'final_kind': 'hermes_ram_preflight',
     'schema': 'NOX_HERMES_RAM_PREFLIGHT_V1', 'success_state': 'HERMES_IDENTITY_AND_RESOURCES_OBSERVED'},
    {'name': 'browser_qa', 'entry': 'owner_browser_runtime_repair_entry.py', 'timeout': 200,
     'dependencies': ('owner_browser_runtime_inspect.py', 'owner_browser_stream_only_entry.py',
                      'owner_chat_browser_qa.py', 'owner_chat_browser_transport_qa.py',
                      'owner_chat_browser_release_qa.py', 'owner_chat_stream_only_qa.py'),
     'kinds': ('browser_runtime_permissions', 'browser_stream_only_sources', 'browser_stream_only_receipt',
               'browser_stream_only_hold', 'browser_stream_only_entry_hold',
               'browser_runtime_repair', 'browser_runtime_repair_preflight'),
     'final_kind': 'browser_runtime_repair', 'schema': 'NOX_BROWSER_RUNTIME_SCOPED_PERMISSION_REPAIR_V1',
     'success_state': 'RUNTIME_PERMISSIONS_AND_STREAM_ONLY_VERIFIED'},
)
OUTPUT_LIMIT = 500 * 1024
TOTAL_SECONDS = 420
STOP_PATHS = tuple(Path('/root/nox') / name for name in
                  ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')) + (Path('/workspace/NOX_STOP'),)

# Track only Popen instances created in this disposable interpreter. No global
# process search. On interruption, a separate QA session is terminated only
# while its unreaped leader still has its recorded start/session identity.
CHILD = r'''
import base64,json,os,re,signal,subprocess,sys,time
tracked=[]; interrupted=False
OriginalPopen=subprocess.Popen
def identity(pid):
    with open('/proc/'+str(pid)+'/stat','rb') as f: raw=f.read(8193)
    if len(raw)>8192: raise ValueError('stat bound')
    fields=raw[raw.rfind(b')')+2:].split()
    return (int(fields[1]),int(fields[2]),int(fields[3]),int(fields[19]))
class OwnedPopen(OriginalPopen):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        try: self.owned_identity=identity(self.pid)
        except (OSError,ValueError,IndexError): self.owned_identity=None
        self.owned_session=kwargs.get('start_new_session') is True
        tracked.append(self)
subprocess.Popen=OwnedPopen
class Interrupted(BaseException): pass
def stop(*_):
    global interrupted
    interrupted=True
    raise Interrupted()
signal.signal(signal.SIGTERM,stop)
def cleanup():
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    checked=[]; refused=0
    for p in reversed(tracked):
        if p.poll() is not None: continue
        try:
            now=identity(p.pid)
            if p.owned_identity is None or now!=p.owned_identity or now[0]!=os.getpid():
                refused+=1; continue
            group=p.owned_session and now[1]==p.pid and now[2]==p.pid
            if group: os.killpg(p.pid,signal.SIGTERM)
            else: p.terminate()
            checked.append((p,group))
        except ProcessLookupError: pass
        except (OSError,ValueError,IndexError): refused+=1
    # Keep a group leader unreaped until final group KILL: a leader can exit
    # on TERM while a Chromium descendant ignores TERM. Its zombie retains
    # the PID/start/session identity, preventing group-ID reuse here.
    if checked: time.sleep(2)
    for p,group in checked:
        try:
            if identity(p.pid)!=p.owned_identity: refused+=1; continue
            if group: os.killpg(p.pid,signal.SIGKILL)
            else: os.kill(p.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        except (OSError,ValueError,IndexError): refused+=1
    deadline=time.monotonic()+1
    for p,group in checked:
        try: p.wait(timeout=max(0.001,deadline-time.monotonic()))
        except subprocess.TimeoutExpired: refused+=1
    print('NOX_BATCH_CHILD_CONTROL='+json.dumps({'interrupted':True,'tracked_children':len(tracked),
        'cleanup_targets':len(checked),'cleanup_unverified':refused}),flush=True)
try:
    raw=sys.stdin.buffer.read(262145)
    if len(raw)>262144: raise ValueError('input bound')
    value=json.loads(raw)
    scope={'__name__':'__main__','__file__':'<pinned-hermes-qa-phase>'}
    scope['__NOX_'+'BUNDLE_JSON__']=value['bundle']
    exec(compile(base64.b64decode(value['source'],validate=True),'<pinned-hermes-qa-phase>','exec'),scope)
except SystemExit as exc:
    raise SystemExit(exc.code if type(exc.code) is int else 2)
except BaseException as exc:
    name=type(exc).__name__
    if not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,79}',name): name='UNCLASSIFIED'
    print('NOX_BATCH_CHILD_FAILURE='+json.dumps({'error_class':name}),flush=True)
    raise SystemExit(2)
finally:
    if interrupted: cleanup()
'''


class Hold(RuntimeError): pass


def require(ok, code):
    if not ok: raise Hold('HOLD_HERMES_QA_BATCH_' + code)


def encoded(value): return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
def stop_present(): return any(path.exists() or path.is_symlink() for path in STOP_PATHS)
def safe(exc):
    value = str(exc)
    return value if re.fullmatch('HOLD_[A-Z0-9_]{1,120}', value) else 'HOLD_HERMES_QA_BATCH_' + type(exc).__name__.upper()


def payload(phase):
    selected = {}
    for name in (phase['entry'], *phase['dependencies']):
        raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
        require(0 < len(raw) <= 65536 and hashlib.sha256(raw).hexdigest() == PINS[name], 'SOURCE_PIN')
        selected[name] = base64.b64encode(raw).decode()
    raw = encoded({'source': selected.pop(phase['entry']), 'bundle': selected})
    require(len(raw) <= 262144, 'INPUT_BOUND')
    return raw


def parse_output(raw, phase, code, context):
    require(len(raw) <= OUTPUT_LIMIT, 'OUTPUT_BOUND')
    records, markers = [], []; protocol_ok = True; control = None; error = None
    for line in raw.decode('utf-8', errors='strict').splitlines():
        if not line: continue
        if line.startswith('NOX_MAINT_REPAIR='):
            value = json.loads(line.partition('=')[2], parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if (not isinstance(value, dict) or set(value) != {'kind', 'data'}
                    or value['kind'] not in phase['kinds'] or not isinstance(value['data'], dict)):
                protocol_ok = False; continue
            records.append(value)
        elif line in ('NOX_MAINT_REPAIR_COMPLETE=true', 'NOX_MAINT_REPAIR_COMPLETE=false'):
            markers.append(line.endswith('=true'))
        elif line.startswith('NOX_BATCH_CHILD_FAILURE='):
            value = json.loads(line.partition('=')[2]); name = value.get('error_class') if isinstance(value, dict) else None
            error = name if isinstance(name, str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,79}', name) else 'UNCLASSIFIED'
            protocol_ok = False
        elif line.startswith('NOX_BATCH_CHILD_CONTROL='):
            value = json.loads(line.partition('=')[2])
            keys = {'interrupted', 'tracked_children', 'cleanup_targets', 'cleanup_unverified'}
            if (isinstance(value, dict) and set(value) == keys and value['interrupted'] is True
                    and all(type(value[k]) is int and 0 <= value[k] <= 128 for k in keys - {'interrupted'})):
                control = value
            else: protocol_ok = False
        else:
            protocol_ok = False  # Never echo unknown stdout or private errors.
    final = records[-1]['data'] if records and records[-1]['kind'] == phase['final_kind'] else {}
    bound = final.get('request') == context['request'] and final.get('source_sha') == context['source_sha']
    success = (code == 0 and protocol_ok and control is None and bool(markers) and all(markers)
               and bound and final.get('schema') == phase['schema'] and final.get('state') == phase['success_state'])
    if phase['name'] == 'hermes':
        success = success and len(records) == 1 and markers == [True] and final.get('full_current_ssd_sha_verified') is True
    else:
        receipts = [r['data'] for r in records if r['kind'] == 'browser_stream_only_receipt']
        success = (success and markers == [True, True] and len(receipts) == 1
            and receipts[0].get('request') == context['request'] and receipts[0].get('source_sha') == context['source_sha']
            and receipts[0].get('state') == 'STREAM_ONLY_ACCEPTED' and receipts[0].get('stream_only_acceptance_verified') is True
            and final.get('permissions_verified') is True and final.get('qa_acceptance_verified') is True
            and final.get('post_qa_runtime_identity_verified') is True and final.get('qa_returncode') == 0)
    return records, {'success': bool(success), 'child_exit_code': code, 'completion_markers': markers,
        'protocol_valid': protocol_ok, 'child_error_class': error, 'child_cleanup': control, 'record_count': len(records)}


def run_phase(phase, context, deadline, output_remaining):
    started = time.monotonic(); records = []; proc = None
    result = {'phase': phase['name'], 'success': False, 'source_sha256': PINS[phase['entry']],
              'temporary_source_files_written': 0, 'raw_stderr_exported': False}
    try:
        require(not stop_present(), 'OWNER_STOP')
        raw = payload(phase); timeout = min(phase['timeout'], deadline - time.monotonic())
        require(timeout > .05, 'TOTAL_DEADLINE')
        grace = min(5.0, timeout / 4); soft_deadline = time.monotonic() + timeout - grace
        env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
               'NOX_OWNER_REQUEST_ID': context['request'], 'NOX_OWNER_SOURCE_SHA': context['source_sha']}
        proc = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', CHILD], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, start_new_session=True)
        data = raw; interrupted = None
        while True:
            try:
                output, _ = proc.communicate(input=data, timeout=max(.01, min(1, soft_deadline - time.monotonic())))
                break
            except subprocess.TimeoutExpired as exc:
                data = None
                if len(exc.output or b'') > output_remaining: interrupted = 'OUTPUT_BOUND'
                elif stop_present(): interrupted = 'OWNER_STOP'
                elif time.monotonic() >= soft_deadline: interrupted = 'CHILD_TIMEOUT'
                if interrupted:
                    proc.terminate()  # CHILD handles TERM and cleans only its tracked children.
                    try: output, _ = proc.communicate(timeout=grace)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL); output, _ = proc.communicate(timeout=1)
                        result['outer_child_forced_termination'] = True
                    break
        require(len(output) <= output_remaining, 'OUTPUT_BOUND')
        records, detail = parse_output(output, phase, proc.returncode, context); result.update(detail)
        result['captured_stdout_bytes'] = len(output)
        if interrupted: result.update(success=False, reason='HOLD_HERMES_QA_BATCH_' + interrupted)
        result['state'] = 'PHASE_VERIFIED' if result['success'] else 'PHASE_HELD_OR_FAILED'
    except Exception as exc:
        result.update(state='PHASE_HELD_OR_FAILED', reason=safe(exc))
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try: proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL); proc.communicate(timeout=1)
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    return records, result


def execute(context):
    started = time.monotonic(); deadline = started + TOTAL_SECONDS
    records, phases = [], []; stop_latched = False; used = 0
    for phase in PHASES:
        if stop_latched or stop_present():
            phases.append({'phase': phase['name'], 'success': False, 'state': 'SKIPPED_OWNER_STOP'})
            stop_latched = True; continue
        observed, result = run_phase(phase, context, deadline, OUTPUT_LIMIT - 32768 - used)
        records.extend(observed); phases.append(result); used += result.get('captured_stdout_bytes', 0)
        stop_latched = (str(result.get('reason', '')).endswith('_OWNER_STOP') or any(
            str(row['data'].get('reason', '')).endswith('_OWNER_STOP') for row in observed))
    success = len(phases) == 2 and all(row['success'] for row in phases)
    return records, {'schema': SCHEMA, **context, 'success': success,
        'state': 'HERMES_OBSERVED_AND_STREAM_ONLY_VERIFIED' if success else 'HERMES_QA_PARTIAL_OR_HELD',
        'phases': phases, 'verified_phase_count': sum(row['success'] for row in phases),
        'owner_stop_latched': stop_latched, 'source_pins': PINS,
        'maximum_authorized_native_posts': 1, 'full_browser_qa_promoted': False,
        'hermes_migration_authorized': False, 'services_or_training_flags_changed': False,
        'allowed_mutations': 'ONLY_FROZEN_SCOPED_QA_REPAIR_RECEIPTS_AND_ONE_PUBLIC_TEST_DIALOG',
        'elapsed_seconds': round(time.monotonic() - started, 3)}


def main():
    context = {'request': os.environ.get('NOX_OWNER_REQUEST_ID', ''), 'source_sha': os.environ.get('NOX_OWNER_SOURCE_SHA', '')}
    require(re.fullmatch('[0-9]{1,24}', context['request']) and re.fullmatch('[a-f0-9]{40}', context['source_sha']), 'OWNER_CONTEXT')
    records, result = execute(context)
    for row in records: print('NOX_MAINT_REPAIR=' + encoded(row).decode(), flush=True)
    print('NOX_MAINT_REPAIR=' + encoded({'kind': 'hermes_qa_batch', 'data': result}).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(result['success']).lower(), flush=True)
    return 0 if result['success'] else 2


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + encoded({'kind': 'hermes_qa_batch', 'data': {
            'schema': SCHEMA, 'state': 'BATCH_PREFLIGHT_HELD', 'reason': safe(exc), 'success': False}}).decode(), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
