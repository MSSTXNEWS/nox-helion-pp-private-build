#!/usr/bin/env python3
"""Read the persistent training guard immediately before media handback.

This optional binding extends the exact existing Qwen handoff in memory. It
does not write guard state, clear flags, launch services, or add a queue. The
original handoff performs its existing claim/checkpoint/resource checks and
owns the only release operation. Completed window6 remains unaffected.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
import types

ROOT = Path('/root/nox')
BASE_SHA = '1afc9705e1b84e0847f9a36d296458eab5098ad2939cbc7f8268a6bf2dfe7ea4'  # Exact reviewed revision consumer, supplied by final source rendering.
# Exact separately reviewed guard; the already installed handoff stays unchanged.
GUARD_SHA = 'd5217f5bdfe21418d6210a18faac8eef422e49009d8abbcd3e71a06988a8b06b'
BASE_PATH = ROOT / 'scripts/owner_qwen_media_handoff.py'
GUARD_PATH = ROOT / 'scripts/owner_qwen_training_guard.py'
MARKER = 'NOX_QWEN_MEDIA_GUARD_BIND_V1'
SCHEMA = 'NOX_QWEN_MEDIA_GUARD_BINDING_V1'
BOUND = None


class GuardHold(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise GuardHold(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checked_read(path, expected=None):
    path = Path(path)
    require(not any(item.is_symlink() for item in (*path.parents, path)), 'HOLD_QWEN_MEDIA_GUARD_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 2 * 1024 ** 2,
                'HOLD_QWEN_MEDIA_GUARD_SOURCE_BOUND')
        raw = stream.read(2 * 1024 ** 2 + 1)
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        require(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)), 'HOLD_QWEN_MEDIA_GUARD_SOURCE_RACE')
    require(expected is None or isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected)
            and sha(raw) == expected, 'HOLD_QWEN_MEDIA_GUARD_SOURCE_PIN')
    return raw


class Reader:
    def __init__(self, core):
        self.core, self.handback = core, core.BOUND
        self.source_path = Path(__file__)
        self.source_sha256 = sha(checked_read(self.source_path))
        self.guard = None
        self.original_resource_gate = self.handback.resource_gate
        self.original_release_flags = self.handback.release_flags

    def checked_guard(self):
        require(isinstance(GUARD_SHA, str) and re.fullmatch('[a-f0-9]{64}', GUARD_SHA),
                'HOLD_QWEN_MEDIA_GUARD_SOURCE_NOT_REVIEWED')
        checked_read(self.source_path, self.source_sha256)
        checked_read(BASE_PATH, BASE_SHA)
        raw = checked_read(GUARD_PATH, GUARD_SHA)
        if self.guard is None:
            value = types.ModuleType('_nox_qwen_media_verified_training_guard')
            value.__file__ = str(GUARD_PATH)
            sys.modules[value.__name__] = value
            exec(compile(raw, str(GUARD_PATH), 'exec'), value.__dict__)
            require(callable(getattr(value, 'resume_block_reason', None)), 'HOLD_QWEN_MEDIA_GUARD_INTERFACE')
            self.guard = value
        require(Path(self.guard.__file__) == GUARD_PATH, 'HOLD_QWEN_MEDIA_GUARD_MODULE_PATH')
        return self.guard

    def admission(self):
        """No flock: the caller already owns the handback maintenance EX lease."""
        try:
            config = self.handback.configuration()
            if config.get('resume_training_after_media') is False:
                return {'state': 'COMPLETED_SIX_UNAFFECTED', 'guard_consulted': False}
            require(config.get('enabled') is True and config.get('resume_training_after_media') is True,
                    'HOLD_QWEN_MEDIA_GUARD_HANDOFF_MODE')
            context = self.handback.actions.admission
            expected_context = config.get('execution_revision', config.get('window_admission'))
            require(isinstance(context, dict) and set(context) == {'request', 'source_sha', 'receipt_sha256'}
                    and expected_context == context
                    and isinstance(context['request'], str) and re.fullmatch('[0-9]{1,24}', context['request'])
                    and re.fullmatch('[a-f0-9]{40}', str(context['source_sha']))
                    and re.fullmatch('[a-f0-9]{64}', str(context['receipt_sha256'])),
                    'HOLD_QWEN_MEDIA_GUARD_ADMISSION_CONTEXT')
            guard = self.checked_guard()
            reason = guard.resume_block_reason(dict(context))
            if reason is not None:
                require(isinstance(reason, str) and re.fullmatch('(WAIT|HOLD)_[A-Z0-9_]{1,120}', reason),
                        'HOLD_QWEN_MEDIA_GUARD_RESULT')
                raise GuardHold(reason)
            return {'state': 'FRESH_GUARD_ADMITS_RESUME', 'guard_consulted': True,
                    'source_sha256': self.source_sha256, 'guard_source_sha256': GUARD_SHA,
                    'window_admission': dict(config['window_admission']),
                    'execution_revision': dict(context) if 'execution_revision' in config else None}
        except GuardHold:
            raise
        except Exception as exc:
            code = str(exc)
            if not re.fullmatch('(WAIT|HOLD)_[A-Z0-9_]{1,120}', code):
                code = 'HOLD_QWEN_MEDIA_GUARD_UNVERIFIED'
            raise GuardHold(code) from None

    def resource_gate(self):
        proof = self.admission()
        value = self.original_resource_gate()
        require(isinstance(value, dict), 'HOLD_QWEN_MEDIA_GUARD_RESOURCE_INTERFACE')
        return {**value, 'persistent_training_guard': proof}

    def release_flags(self, job_id, flags):
        # This is the last read before the unchanged owner-specific archive.
        # Guard writers take maintenance SH; the existing caller holds EX.
        proof = self.admission()
        require(proof['state'] == 'FRESH_GUARD_ADMITS_RESUME', 'WAIT_QWEN_COMPLETED_WINDOW_HAS_NO_HANDOFF')
        return self.original_release_flags(job_id, flags)


def bind_dispatcher(namespace, core):
    global BOUND
    require(BOUND is None and namespace.get('_owner_qwen_media_handoff_bound') is True
            and namespace.get('_owner_lifecycle_bound') is not True and namespace.get('WORKERS') == 6
            and not namespace.get('_owner_qwen_media_guard_bound'), 'HOLD_QWEN_MEDIA_GUARD_BIND_ORDER')
    require(Path(getattr(core, '__file__', '')) == BASE_PATH and sha(checked_read(BASE_PATH)) == BASE_SHA,
            'HOLD_QWEN_MEDIA_GUARD_BASE_PIN')
    handback = getattr(core, 'BOUND', None)
    require(handback is not None and handback.source_pin == BASE_SHA
            and all(getattr(getattr(handback, name, None), '__self__', None) is handback
                    for name in ('resource_gate', 'release_flags', 'configuration')),
            'HOLD_QWEN_MEDIA_GUARD_HANDOFF_INTERFACE')
    reader = Reader(core)
    # Validate source bytes before adding any hook, but do not consult the
    # guard for completed6, for which no 1000 config is active yet.
    require(isinstance(GUARD_SHA, str) and re.fullmatch('[a-f0-9]{64}', GUARD_SHA),
            'HOLD_QWEN_MEDIA_GUARD_SOURCE_NOT_REVIEWED')
    checked_read(GUARD_PATH, GUARD_SHA)
    handback.resource_gate, handback.release_flags = reader.resource_gate, reader.release_flags
    BOUND = reader
    namespace['_owner_qwen_media_guard_bound'] = True
    namespace['_owner_qwen_media_guard_binding'] = {'schema': SCHEMA, 'source_sha256': reader.source_sha256,
        'base_source_sha256': BASE_SHA, 'guard_source_sha256': GUARD_SHA,
        'checkpoints': ['RESOURCE_GATE', 'IMMEDIATELY_BEFORE_OWN_FLAG_RELEASE'],
        'new_queue_created': False, 'training_started': False}
