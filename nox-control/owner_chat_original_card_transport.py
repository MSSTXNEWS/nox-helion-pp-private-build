#!/usr/bin/env python3
"""One-shot owner repair transport for the frozen 1A01 browser witness."""

import base64
from contextlib import suppress
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import signal
import subprocess
import tempfile
import time

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

TASK_SPEC_SHA256 = 'e0bc3244e0a176baa7fc02827c364d15b37bd56cdd93223f6d3d869264377b3e'
STATE = Path('/root/nox/state/owner_browser_qa')
RUNTIME_ENTRY = 'owner_browser_stream_only_entry.py'
QA_ENTRY = 'owner_chat_original_card_qa.py'
PINS = {
    RUNTIME_ENTRY: 'af2bc57048899ad419b69ecbf6b7ff649957b577643645158517e716f369d56b',
    'owner_chat_browser_qa.py': '02f4d4acdb0d47afc6404d613e5f2cffe912ad079684034c24dcbf0fdbd68b10',
    QA_ENTRY: '250080c62f87e620a9e6c9b918a7eafe75d01aa92d943bbbcec69b3c9c6c813b',
}
CHILD = """
from importlib.metadata import version
import runpy
import sys
if sys.prefix != '/root/nox/browser_qa/venv' or version('playwright') != '1.65.2':
    raise RuntimeError('HOLD_1A01_EXISTING_RUNTIME')
runpy.run_path(sys.argv[1], run_name='__main__')
"""


def require(condition, reason):
    if not condition:
        raise RuntimeError('HOLD_1A01_' + reason)


def emit(kind, data):
    print('NOX_MAINT_REPAIR=' + json.dumps(
        {'kind': kind, 'data': data}, separators=(',', ':'), allow_nan=False), flush=True)


def sources(bundle):
    require(isinstance(bundle, dict) and set(bundle) == set(PINS), 'BUNDLE_SCOPE')
    verified = {}
    for name, pin in PINS.items():
        value = bundle[name]
        require(isinstance(value, str) and 0 < len(value) <= 350000, 'BUNDLE_BOUND')
        raw = base64.b64decode(value, validate=True)
        require(hashlib.sha256(raw).hexdigest() == pin, 'BUNDLE_PIN')
        compile(raw, name, 'exec')
        verified[name] = raw
    return verified


def run_browser(python, entry, environment):
    process = subprocess.Popen([str(python), '-I', '-B', '-c', CHILD, str(entry)],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, env=environment,
                               start_new_session=True)
    try:
        return process.wait(timeout=165)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        # Keep the group leader unreaped while terminating remaining browser children.
        time.sleep(2)
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            raise RuntimeError('HOLD_1A01_BROWSER_CLEANUP_UNKNOWN') from None
        raise RuntimeError('HOLD_1A01_BROWSER_TIMEOUT') from None


def receipt_projection(raw, request, source):
    result = json.loads(raw)
    require(isinstance(result, dict)
            and result.get('schema') == 'NOX_1A01_ORIGINAL_CARD_BROWSER_QA_V1'
            and result.get('request') == request and result.get('source_sha') == source
            and result.get('state') == 'ORIGINAL_CARD_UI_QA_PASSED_S03_UNEVALUATED'
            and result.get('onehost_1a01_original_card_acceptance_state') == 'ORIGINAL_CARD_UI_ACCEPTED'
            and result.get('two_turn_condition') == 'NOT_RUN_SEPARATE_FROM_FROZEN_1A01_CARD', 'RECEIPT_SCOPE')
    require(all(result.get(key) is True for key in (
        'actual_native_backend', 'actual_native_model_stream_verified', 'original_card_one_turn',
        'progressive_stream_render_verified', 'accepted_input_waiting_answer_completed_ui_verified',
    )) and all(result.get(key) is False for key in (
        'synthetic_backend_used', 'canonical_s03_readback_verified',
        'supplemental_dialog_receipt_used_for_acceptance',
    )), 'RECEIPT_ACCEPTANCE')
    stream = result.get('stream')
    require(isinstance(stream, dict) and type(stream.get('native_calls')) is int
            and stream['native_calls'] == 1 and stream.get('native_eof') is True
            and stream.get('dom_answer_matches_native') is True, 'STREAM_SCOPE')
    return {
        'task_id': '1A01',
        'spec_sha256': TASK_SPEC_SHA256,
        'request': request,
        'source_sha': source,
        'receipt_sha256': hashlib.sha256(raw).hexdigest(),
        'owner_chat_stream_posts_observed': 1,
        'frozen_original_card_ui_witness': True,
        'canonical_s03_readback_verified': False,
        'original_task_acceptance_delta': 0,
    }


def main():
    verified = sources(BUNDLE)
    with tempfile.TemporaryDirectory(prefix='nox-1a01-source-') as directory:
        root = Path(directory)
        for name, raw in verified.items():
            (root / name).write_bytes(raw)
        helpers = runpy.run_path(str(root / RUNTIME_ENTRY), run_name='nox_1a01_runtime_helpers')
        request, source = helpers['owner_context']()
        receipt_dir = STATE / request
        helpers['plain_directory'](STATE.parent)
        if os.path.lexists(STATE):
            helpers['plain_directory'](STATE, private=True)
        require(not os.path.lexists(receipt_dir), 'REQUEST_ALREADY_OBSERVED')
        python = helpers['existing_runtime']()
        helpers['resource_budget']()
        env = helpers['child_environment'](request, source)
        result_code = run_browser(python, root / QA_ENTRY, env)
        require(os.path.lexists(receipt_dir), 'BROWSER_RECEIPT_MISSING')
        helpers['plain_directory'](receipt_dir, private=True)
        raw = helpers['read_private'](receipt_dir / 'receipt.json', 131072)
        if result_code != 0:
            receipt = json.loads(raw)
            reason = receipt.get('reason') if isinstance(receipt, dict) else None
            if isinstance(reason, str) and re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}', reason):
                raise RuntimeError(reason)
            raise RuntimeError('HOLD_1A01_BROWSER_EXECUTION')
        result = receipt_projection(raw, request, source)
    emit('browser_original_card_receipt', result)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        value = str(exc)
        reason = value if re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}', value) else type(exc).__name__
        emit('browser_original_card_hold', {'reason': reason})
        raise SystemExit(2)
