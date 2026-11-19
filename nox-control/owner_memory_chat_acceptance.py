#!/usr/bin/env python3
"""Finite owner transition: semantic memory, original chat layout, browser proof."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

STAGES = (
    ('owner_s03_recover_activate.py', '55fbbb2bbdf346cb68dc8fc55594fe1971609a182c26ce2ff8b097cad9831a14'),
    ('owner_chat_layout_entry.py', '038ef7025b69be1c8cedfe26d90615f67705e233daf132b0afd91ccf4f9d162b'),
    ('owner_browser_qa_entry.py', '7baa663b475fee7bd8abd2d0b1348becf5a257fdfad04792a6ba8185fbbc5042'),
)


def emit(kind, data):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': data}, separators=(',', ':')), flush=True)


def _unique_receipt_keys(pairs):
    """Reject ambiguous receipt evidence instead of Python's last-key-wins JSON."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate receipt evidence field')
        result[key] = value
    return result


def _reject_receipt_constant(value):
    raise ValueError('nonfinite receipt JSON constant')


def verify_browser_receipt(browser_started_ns):
    """Require native stream and durable S03 proof, not just a zero exit code."""
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'[0-9]{1,24}', request) or not re.fullmatch(r'[a-f0-9]{40}', source):
        raise RuntimeError('HOLD_BROWSER_QA_RECEIPT_CONTEXT')
    path = Path('/root/nox') / 'state/owner_browser_qa' / request / 'receipt.json'
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise RuntimeError('HOLD_BROWSER_QA_RECEIPT_PATH')
    try:
        # A FIFO or device at this path must never hang owner acceptance.
        # Open nonblocking/no-follow, then inspect the very inode being read.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise RuntimeError('HOLD_BROWSER_QA_RECEIPT_TYPE')
            raw = stream.read(262145)
            receipt_mtime_ns = info.st_mtime_ns
    except OSError:
        raise RuntimeError('HOLD_BROWSER_QA_RECEIPT_MISSING') from None
    # A prior successful run must not satisfy a new browser/S03 acceptance.
    # Inspect the same opened inode used to read the actual receipt bytes.
    if receipt_mtime_ns < browser_started_ns:
        raise RuntimeError('HOLD_BROWSER_QA_RECEIPT_STALE')
    if len(raw) > 262144:
        raise RuntimeError('HOLD_BROWSER_QA_RECEIPT_SIZE')
    try:
        proof = json.loads(raw, object_pairs_hook=_unique_receipt_keys,
                           parse_constant=_reject_receipt_constant)
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError('HOLD_BROWSER_QA_RECEIPT_FORMAT') from None
    if (not isinstance(proof, dict) or proof.get('schema') != 'NOX_OWNER_NATIVE_BROWSER_QA_V1'
            or proof.get('request') != request or proof.get('source_sha') != source
            or proof.get('state') != 'PASSED'
            or any(proof.get(key) is not True for key in (
                'functional_acceptance_verified', 'actual_native_model_stream_verified',
                's03_readback_verified', 'screenshot_capture_verified',
                'actual_native_backend', 'nonloopback_auth',
                'empty_dialog_history_verified', 'synthetic_number_sequence_pass',
                'progressive_stream_render_verified', 'stop_visible_during_generation'))
            or proof.get('synthetic_backend_used') is not False
            or proof.get('private_text_or_credentials_exported') is not False):
        raise RuntimeError('HOLD_BROWSER_QA_RECEIPT_INCOMPLETE')

def main():
    failed = []
    for name, expected in STAGES:
        if any((Path('/root/nox') / flag).exists() for flag in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')):
            failed.append({'component': name, 'reason': 'HOLD_OWNER_STOP'})
            break
        # The nested browser QA accepts inventory mode with exit 0 but no
        # real streaming/browser/S03 acceptance. Never run an owner batch in
        # this mode, even if the inventory-only stage would return success.
        if os.environ.get('NOX_BROWSER_QA_MODE') == 'inventory':
            failed.append({'component': 'owner_browser_qa_entry.py',
                           'reason': 'HOLD_BROWSER_QA_INVENTORY_MODE'})
            emit('memory_chat_component_hold', failed[-1])
            break
        try:
            browser_started_ns = time.time_ns() if name == 'owner_browser_qa_entry.py' else None
            raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
            if len(raw) > 200000 or hashlib.sha256(raw).hexdigest() != expected:
                raise RuntimeError('HOLD_ACCEPTANCE_COMPONENT_PIN')
            module = types.ModuleType('nox_memory_chat_' + name[:-3])
            module.__file__ = '/root/nox/scripts/' + name
            module.__dict__['__NOX_' + 'BUNDLE_JSON__'] = BUNDLE
            sys.modules[module.__name__] = module
            exec(compile(raw, module.__file__, 'exec'), module.__dict__)
            result = module.main()
            conventional_main = name == 'owner_browser_qa_entry.py' and result is None
            if not conventional_main and (type(result) is not int or result != 0):
                raise RuntimeError('HOLD_ACCEPTANCE_COMPONENT_RESULT')
            # Browser entry returns None even after a subprocess exit. A real
            # native/S03 acceptance receipt for this exact owner request is mandatory.
            if name == 'owner_browser_qa_entry.py':
                verify_browser_receipt(browser_started_ns)
            # A STOP raised while the final stage ran must not produce success.
            if any((Path('/root/nox') / flag).exists() for flag in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')):
                raise RuntimeError('HOLD_OWNER_STOP')
        except (Exception, SystemExit) as exc:
            # A bundled stage can call sys.exit(0) before any durable S03
            # receipt is written. Never accept that as owner batch completion.
            value = str(exc)
            reason = ('HOLD_ACCEPTANCE_COMPONENT_SYSTEM_EXIT' if isinstance(exc, SystemExit)
                      else value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]+', value) else type(exc).__name__)
            failed.append({'component': name, 'reason': reason})
            emit('memory_chat_component_hold', failed[-1])
            # All later stages depend on S03 recovery and ordered owner acceptance.
            # Never mutate the chat layout or start browser QA after a failed stage.
            break
    emit('memory_chat_batch', {'failed': failed, 'training_started': False, 'private_content_exported': False})
    if not failed:
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 2 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
