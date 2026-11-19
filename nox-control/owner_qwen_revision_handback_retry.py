#!/usr/bin/env python3
"""Retry only mutable queue snapshots and three transient guard observations.

The inherited claim, source, schema, checkpoint, flag ownership and resource
checks remain authoritative. This binding never writes a flag or starts a
service; it only lets the existing handler return its native wait outcome.
"""
import hashlib
import os
from pathlib import Path
import stat
import time

ROOT = Path('/root/nox')
QUEUE = ROOT / 'state/dispatcher/state.json'
BASE = ROOT / 'scripts/owner_media_training_handoff.py'
CORE = ROOT / 'scripts/owner_qwen_media_handoff.py'
READER = ROOT / 'scripts/owner_qwen_media_guard.py'
GUARD = ROOT / 'scripts/owner_qwen_training_guard.py'
PINS = {
    BASE: '36db3c363ffddfc144c6127e1a9407132bbe39d38996233bf3dd64e5b3cb6ec8',
    CORE: 'e8fa87f3e84d90fad90030cff9b8e548280b4d3097bde83ba6cedd9f4bef46ce',  # Final reviewed revision consumer pins, never guessed at runtime.
    READER: 'c0feb873174e776285563fdb0290a4b1064402d33c3c05c58d847531690d7723',
    GUARD: '6f5aaebaf196c6ec5bd2ad434c5633f457019368568d93b7f71efcc0effcf656',
}
FRESHNESS = frozenset('HOLD_QWEN_GUARD_' + name for name in
                      ('STATE_STALE', 'STATE_CHECKPOINT_PENDING', 'STATE_MISSING'))
MAX_ATTEMPTS = 3
BOUND = None


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_QWEN_HANDBACK_RETRY_' + code)


def checked(path, expected):
    path = Path(path)
    require(not any(item.is_symlink() for item in (*path.parents, path)), 'SOURCE_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 2 * 1024 ** 2, 'SOURCE_BOUND')
        raw = stream.read(2 * 1024 ** 2 + 1)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)), 'SOURCE_CHANGED')
    require(hashlib.sha256(raw).hexdigest() == expected, 'SOURCE_PIN')
    return raw


def queue_reader(original, hold_type):
    def read(path, maximum=262144):
        if Path(path) != QUEUE:
            return original(path, maximum)
        for attempt in range(MAX_ATTEMPTS):
            try:
                return original(path, maximum)
            except hold_type as exc:
                if str(exc) != 'HOLD_MEDIA_HANDBACK_FILE_CHANGED':
                    raise
                if attempt + 1 == MAX_ATTEMPTS:
                    raise hold_type('WAIT_QUEUE_SNAPSHOT_CHANGED') from None
                time.sleep(.01 * (attempt + 1))
        raise AssertionError('unreachable')
    return read


def guard_admission(original, hold_type):
    def admission():
        try:
            return original()
        except hold_type as exc:
            if str(exc) not in FRESHNESS:
                raise
            raise hold_type(str(exc).replace('HOLD_', 'WAIT_', 1)) from None
    return admission


def bind_dispatcher(namespace, core, reader_module):
    global BOUND
    require(BOUND is None and namespace.get('WORKERS') == 6
            and namespace.get('_owner_media_inbox_fair_bound') is True
            and namespace.get('_owner_qwen_media_handoff_bound') is True
            and namespace.get('_owner_qwen_media_guard_bound') is True
            and not namespace.get('_owner_lifecycle_bound')
            and not namespace.get('_owner_qwen_handback_retry_bound')
            and Path(namespace.get('STATE', '')) == QUEUE, 'BIND_ORDER')
    require(Path(getattr(core, '__file__', '')) == CORE
            and Path(getattr(reader_module, '__file__', '')) == READER, 'MODULE_PATH')
    for path, pin in PINS.items():
        checked(path, pin)
    handback = getattr(core, 'BOUND', None)
    reader = getattr(reader_module, 'BOUND', None)
    require(handback is not None and reader is not None and reader.handback is handback
            and handback.source_pin == PINS[CORE]
            and getattr(namespace.get('HANDLERS', {}).get('owner_media_resume'), '__self__', None) is handback
            and getattr(handback.resource_gate, '__self__', None) is reader
            and getattr(handback.release_flags, '__self__', None) is reader,
            'EXISTING_BINDINGS')
    base = handback.run.__func__.__globals__
    original = base.get('read')
    require(callable(original) and original.__globals__ is base
            and handback.claim.__func__.__globals__ is base
            and base.get('document').__globals__ is base
            and original.__code__.co_filename == str(BASE)
            and callable(base.get('HandoffHold'))
            and getattr(reader.admission, '__self__', None) is reader, 'INHERITED_READ_SCOPE')
    wrapped_read = queue_reader(original, base['HandoffHold'])
    old_admission = reader.admission
    wrapped_admission = guard_admission(old_admission, reader_module.GuardHold)
    base['read'] = wrapped_read
    reader.admission = wrapped_admission
    BOUND = {'base': base, 'original_read': original, 'read': wrapped_read,
             'reader': reader, 'original_admission': old_admission, 'admission': wrapped_admission}
    namespace['_owner_qwen_handback_retry_bound'] = True
    namespace['_owner_qwen_handback_retry_binding'] = {
        'schema': 'NOX_QWEN_HANDBACK_RETRY_BINDING_V1', 'queue_snapshot_attempts': MAX_ATTEMPTS,
        'transient_guard_codes': sorted(FRESHNESS), 'claim_validation_preserved': True,
        'source_files_unchanged': True, 'flags_written': False, 'training_started': False}
