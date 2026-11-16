#!/usr/bin/env python3
"""Finalize one explicitly supplied future transport revision; never restart it.

REFERENCE is deliberately unbound. The owner may render this one literal only
after receiving the real immutable admission reference, or call main(reference)
from an explicitly pinned capsule. Native dependencies are already installed;
this entry requires no source bundle and never invokes the installer's main.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types

PATH = Path('/root/nox/scripts/owner_qwen_revision_install.py')
PIN = '711912d596ce6c8e806d4ee16d9d5a1fae41c89b527825b13cf2c6788a17975a'
SHARED = 'owner_qwen_execution_revision.py'
SHARED_PIN = '0dbb06d3384b3436165056ccf4e35bff937fda4f85d96ab2a97ab16a6619998e'
STUDENT_PIN = 'ce7dcbef53c61c63ebab96553ef4c48d9f138a3c426008fa329eb5fd66ee041c'
REFERENCE = {'request': '6914959637', 'source_sha': 'a06c6a039ebccd6eaa754914624ab5477beca47b', 'receipt_sha256': '2f16be7a0bf648621f845c898dd2cc078a98f608fa5b01b3153890c7e3dc41d9'}


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_TRANSPORT_FINALIZE_' + code)


def checked_reference(value):
    require(isinstance(value, dict) and set(value) == {'request', 'source_sha', 'receipt_sha256'}
            and type(value['request']) is str and re.fullmatch('[0-9]{1,24}', value['request'])
            and type(value['source_sha']) is str and re.fullmatch('[a-f0-9]{40}', value['source_sha'])
            and type(value['receipt_sha256']) is str and re.fullmatch('[a-f0-9]{64}', value['receipt_sha256']),
            'EXPLICIT_IMMUTABLE_REFERENCE_REQUIRED')
    return dict(value)


def load_installer():
    require(not any(p.is_symlink() for p in (*PATH.parents, PATH)), 'SOURCE_PATH')
    fd = os.open(PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mode, info.st_uid,
                info.st_gid, info.st_nlink, info.st_mtime_ns, info.st_ctime_ns)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and before.st_nlink == 1 and not stat.S_IMODE(before.st_mode) & 0o022
                and 0 < before.st_size <= 262144, 'SOURCE_SCOPE')
        raw = stream.read(262145)
        require(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
                == identity(PATH.stat(follow_symlinks=False)), 'SOURCE_CHANGED')
    require(hashlib.sha256(raw).hexdigest() == PIN, 'SOURCE_PIN')
    core = types.ModuleType('_nox_transport_finalize_issuer')
    core.__file__ = str(PATH)
    exec(compile(raw, str(PATH), 'exec'), core.__dict__)
    require(core.SELF == PATH.name and core.SHARED == SHARED and core.PINS[SHARED] == SHARED_PIN
            and core.PINS[core.STUDENT] == STUDENT_PIN, 'ISSUER_BINDING')
    return core


def bound_installer(reference):
    expected = checked_reference(reference)
    core = load_installer()
    original_loader = core.module

    def scoped_module(name, raw):
        if name == SHARED:
            require(hashlib.sha256(raw).hexdigest() == SHARED_PIN, 'SHARED_PIN')
        value = original_loader(name, raw)
        if name == SHARED:
            current_context = value.current_context

            def explicit_context(reference=None):
                require(reference is None or checked_reference(reference) == expected, 'REFERENCE_ARGUMENT_CHANGED')
                ctx = current_context(dict(expected))
                require(ctx['context'] == expected and ctx['execution']['runtime_entry_sha256'] == STUDENT_PIN
                        and ctx['execution']['verifier_sha256'] == SHARED_PIN
                        and ctx['execution']['descriptor']['activation_issuer_sha256'] == PIN, 'CURRENT_EXECUTION_BINDING')
                return ctx

            # This private loader supplies the same mandatory reference to the
            # frozen finalizer's own current_context() read. No native source
            # or verifier validation is replaced or skipped.
            value.current_context = explicit_context
        return value

    core.module = scoped_module
    return core


def main(reference=None):
    expected = checked_reference(REFERENCE if reference is None else reference)
    core = bound_installer(expected)
    pending_context(core)
    return core.finalize_current()


def pending_context(core):
    # A previous finalizer may have issued the immutable activation before a
    # transport interruption. Reject that case before entering its mutation
    # handler: the frozen finalizer would otherwise request an owned pause.
    shared = core.module(SHARED, core.read(core.SCRIPTS / SHARED))
    ctx = shared.current_context()
    state = shared.activation_status(ctx)
    require(state.get('active') is False and state.get('bootstrap_pending') is True,
            'NOT_PENDING_USE_READ_ONLY_OBSERVER')
    return ctx


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        value = str(exc)
        reason = value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,160}', value) else type(exc).__name__
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_transport_finalize',
              'data': {'state': 'UNVERIFIED', 'reason': reason, 'start_command_issued': False}},
              separators=(',', ':')), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
