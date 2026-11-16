#!/usr/bin/env python3
"""Read a fixed historical receipt without exporting task text, then dedupe.

The receipt observation changes no source, pin, policy, queue, or training flag.
The independent extent operation retains its exact reviewed implementation.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

PIN = '3918297de579a35cd76585dde6101b244e0a074fe941fe338862a4bbfc93dbea'
PATH = Path('/root/nox/state/owner_native_subagents_recovery_6907376498.json')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def probe():
    if any(p.is_symlink() for p in (PATH, *PATH.parents)):
        raise RuntimeError('HOLD_SUBAGENT_RECEIPT_PROBE_SYMLINK')
    fd = os.open(PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= 262144:
            raise RuntimeError('HOLD_SUBAGENT_RECEIPT_PROBE_SCOPE')
        raw = stream.read(262145)
        after = os.fstat(stream.fileno())
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    current = PATH.stat(follow_symlinks=False)
    if len(raw) != before.st_size or any(
            getattr(before, name) != getattr(value, name)
            for name in fields for value in (after, current)):
        raise RuntimeError('HOLD_SUBAGENT_RECEIPT_PROBE_CHANGED')
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get('request') != '6907376498' or value.get('source_sha') != '6c2d82701ead34c50311b14a48c4b01278ba2879':
        raise RuntimeError('HOLD_SUBAGENT_RECEIPT_PROBE_OWNER')
    projection = {name: value.get(name) for name in (
        'schema', 'request', 'source_sha', 'state', 'new_callback_loaded',
        'module_after_sha256', 'config_after_sha256')}
    projection.update(file_bytes=len(raw), file_sha256=digest(raw),
                      canonical_sha256=digest(encoded(value)),
                      top_level_value_hashes={name: digest(encoded(item)) for name, item in value.items()},
                      task_text_exported=False, source_modified=False)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'native_subagent_prior_receipt_probe',
          'data': projection}, sort_keys=True), flush=True)


def main():
    raw = base64.b64decode(BUNDLE.get('owner_builder_extent_dedupe.py', ''), validate=True)
    if digest(raw) != PIN:
        raise RuntimeError('HOLD_STORAGE_SUBAGENT_PROBE_DEPENDENCY')
    module = types.ModuleType('_reviewed_builder_extent_operation')
    exec(compile(raw, '<pinned-builder-extent-operation>', 'exec'), module.__dict__)
    probe()
    return module.main()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        reason = str(exc)
        if not re.fullmatch('HOLD_[A-Z0-9_]+', reason):
            reason = 'HOLD_STORAGE_SUBAGENT_PROBE_' + type(exc).__name__.upper()
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'storage_subagent_probe_hold',
              'data': {'reason': reason}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
