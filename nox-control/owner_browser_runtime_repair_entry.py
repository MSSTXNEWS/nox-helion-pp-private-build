#!/usr/bin/env python3
"""Repair two observed QA directory modes, then run pinned STREAM_ONLY once.

Only VENV and BIN may change 0775 to 0755. No ownership, recursive permission,
package, UI, service, training, flag or model changes are performed. An immutable
private prepared receipt precedes fchmod. Setup failure restores only our exact
directory changes; an actual QA HOLD retains the independently verified modes.
"""
from __future__ import annotations

import base64
import fcntl
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

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
AREA = ROOT / 'browser_qa'
DIAG = 'owner_browser_runtime_inspect.py'
ENTRY = 'owner_browser_stream_only_entry.py'
PINS = {
    DIAG: '54cb27fbbfbfe25e8129d88a43b4975b5b4b3a64b0ed7eaa5d651c98fae1d280',
    ENTRY: '8866e963acd01f5b5775e079b8d6b85753d8e34ad1d636fcca04f1a6c841d6de',
}
MARKER_SHA = 'ec8959f9fdfad8a3c55445e2f3626187ad36d3446da88c441ac6b269cbf0dd4c'
TARGET_PATH_SHA = 'f0d7a494a3f776233427cb85a7e198c7cf4913b50a203c6febc678cc4f5bf265'
EXPECTED = {
    'AREA': ('39', '3409008543', 99, '1794790121218048755'),
    'VENV': ('39', '367582191', 74, '1794788467037473208'),
    'BIN': ('39', '2250370622', 186, '1794788475337361251'),
    'MARKER': ('39', '3409008548', 131, '1794788469124445014'),
    'PYTHON_LINK': ('39', '2255459172', 10, '1794788467037473208'),
    'PYTHON_TARGET': ('39', '31591', 7913744, '1793028481000000000'),
}
MODES = {'AREA': {0o700}, 'VENV': {0o775, 0o755}, 'BIN': {0o775, 0o755},
         'MARKER': {0o600}, 'PYTHON_LINK': {0o777}, 'PYTHON_TARGET': {0o755}}
SCHEMA = 'NOX_BROWSER_RUNTIME_SCOPED_PERMISSION_REPAIR_V1'
OWNER_UID = 0
OWNER_GID = 0


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_BROWSER_RUNTIME_REPAIR_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe(exc):
    message = str(exc)
    return message if re.fullmatch('HOLD_[A-Z0-9_]{1,120}', message) else type(exc).__name__


def emit(kind, value):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': value},
          separators=(',', ':'), allow_nan=False), flush=True)


def module(name, raw):
    value = types.ModuleType('_nox_runtime_repair_' + name[:-3]); value.__file__ = '<' + name + '>'
    sys.modules[value.__name__] = value
    exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    return value


def prepared():
    assets = {}
    for name, pin in PINS.items():
        value = BUNDLE.get(name)
        require(isinstance(value, str) and 0 < len(value) <= 350000, 'BUNDLE_BOUND')
        raw = base64.b64decode(value, validate=True)
        require(0 < len(raw) <= 262144 and digest(raw) == pin, 'BUNDLE_PIN')
        compile(raw, name, 'exec'); assets[name] = raw
    diagnostic, qa = module(DIAG, assets[DIAG]), module(ENTRY, assets[ENTRY])
    qa.BUNDLE = BUNDLE
    assets.update(qa.sources())
    program = qa.child_program({name: assets[name] for name in qa.PINS})
    compile(program, '<frozen-stream-only-child>', 'exec')
    return assets, diagnostic, qa, digest(program)


def metadata(info):
    return {'device': str(info.st_dev), 'inode': str(info.st_ino), 'bytes': info.st_size,
        'mtime_ns': str(info.st_mtime_ns), 'ctime_ns': str(info.st_ctime_ns),
        'uid': info.st_uid, 'gid': info.st_gid, 'mode_octal': format(stat.S_IMODE(info.st_mode), '04o'),
        'nlink': info.st_nlink}


def known(label, info):
    kind = stat.S_IFMT(info.st_mode)
    expected_kind = stat.S_IFDIR if label in ('AREA', 'VENV', 'BIN') else stat.S_IFLNK if label == 'PYTHON_LINK' else stat.S_IFREG
    require(kind == expected_kind and info.st_uid == OWNER_UID and info.st_gid == OWNER_GID
            and stat.S_IMODE(info.st_mode) in MODES[label], label + '_OWNER_TYPE_MODE')
    require((str(info.st_dev), str(info.st_ino), info.st_size, str(info.st_mtime_ns)) == EXPECTED[label],
            label + '_KNOWN_IDENTITY')
    # Historical ctime is deliberately not pinned: compare fresh live identities
    # within this invocation instead of treating SSH-time chown/chmod as data loss.
    return metadata(info)


def live_identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mode, info.st_uid, info.st_gid, info.st_nlink, info.st_mtime_ns, info.st_ctime_ns


def named(label, path, fd):
    current = os.fstat(fd); path_info = path.stat(follow_symlinks=False)
    require(live_identity(current) == live_identity(path_info), label + '_PATH_CHANGED')
    known(label, current)
    return metadata(current)


def marker_bytes(fd):
    before = os.fstat(fd); known('MARKER', before)
    raw = os.pread(fd, 4097, 0)
    require(len(raw) == before.st_size and digest(raw) == MARKER_SHA
            and live_identity(before) == live_identity(os.fstat(fd)), 'MARKER_SHA_OR_CHANGE')
    return raw


def open_objects(diag):
    objects = {}; handles = []
    try:
        for label, path in (('AREA', AREA), ('VENV', AREA / 'venv'), ('BIN', AREA / 'venv/bin')):
            fd = diag.directory(path); handles.append(fd)
            objects[label] = {'path': path, 'fd': fd, 'before': named(label, path, fd)}
        marker = AREA / 'owner-environment.json'
        fd = os.open('owner-environment.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                     | os.O_CLOEXEC | getattr(os, 'O_NOATIME', 0), dir_fd=objects['AREA']['fd'])
        handles.append(fd); objects['MARKER'] = {'path': marker, 'fd': fd, 'before': named('MARKER', marker, fd)}
        require(json.loads(marker_bytes(fd)) == diag.SPEC, 'MARKER_CONTENT')
        link = AREA / 'venv/bin/python'; link_before = known('PYTHON_LINK', link.lstat())
        target = link.resolve(strict=True)
        require(digest(os.fsencode(str(target))) == TARGET_PATH_SHA, 'PYTHON_TARGET_PATH')
        known('PYTHON_TARGET', target.stat(follow_symlinks=False))
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        handles.append(fd); objects['PYTHON_TARGET'] = {'path': target, 'fd': fd, 'before': named('PYTHON_TARGET', target, fd)}
        require(os.pread(fd, 4, 0) == b'\x7fELF' and known('PYTHON_LINK', link.lstat()) == link_before,
                'PYTHON_ELF_OR_LINK_CHANGED')
        objects['PYTHON_LINK'] = {'path': link, 'before': link_before}
        return objects, handles
    except BaseException:
        for fd in reversed(handles):
            os.close(fd)
        raise


def protected_unchanged(objects):
    for label in ('AREA', 'MARKER', 'PYTHON_TARGET'):
        row = objects[label]
        require(named(label, row['path'], row['fd']) == row['before'], label + '_LIVE_CHANGE')
    row = objects['PYTHON_LINK']
    require(known('PYTHON_LINK', row['path'].lstat()) == row['before']
            and digest(os.fsencode(str(row['path'].resolve(strict=True)))) == TARGET_PATH_SHA,
            'PYTHON_LINK_LIVE_CHANGE')
    marker_bytes(objects['MARKER']['fd'])


def private_record(state_fd, name, value):
    require(re.fullmatch('[a-zA-Z0-9_.-]{1,160}', name), 'RECEIPT_NAME')
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    require(len(raw) <= 65536, 'RECEIPT_BOUND')
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=state_fd)
    with os.fdopen(fd, 'wb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == OWNER_UID and info.st_nlink == 1, 'RECEIPT_MODE')
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.fsync(state_fd)
    check = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=state_fd)
    try:
        before = os.fstat(check)
        require(stat.S_ISREG(before.st_mode) and stat.S_IMODE(before.st_mode) == 0o600
                and before.st_uid == OWNER_UID and before.st_nlink == 1
                and (before.st_dev, before.st_ino) == (info.st_dev, info.st_ino)
                and before.st_size == len(raw), 'RECEIPT_READBACK_SCOPE')
        actual = os.pread(check, 65537, 0)
        require(actual == raw and live_identity(before) == live_identity(os.fstat(check))
                == live_identity(os.stat(name, dir_fd=state_fd, follow_symlinks=False)), 'RECEIPT_READBACK_CHANGED')
    finally:
        os.close(check)
    return {'sha256': digest(raw), 'bytes': len(raw), 'readback_verified': True}


def repair_modes(objects, changed):
    protected_unchanged(objects)
    for label in ('VENV', 'BIN'):
        row = objects[label]
        require(named(label, row['path'], row['fd']) == row['before'], label + '_BEFORE_CHANGED')
        if row['before']['mode_octal'] == '0755':
            row['after'] = row['before']; continue
        os.fchmod(row['fd'], 0o755)
        # Latch own successful chmod before fsync or later verification can fail.
        changed.append(label)
        row['after'] = named(label, row['path'], row['fd'])
        require(row['after']['mode_octal'] == '0755' and all(row['after'][key] == row['before'][key]
            for key in row['before'] if key not in ('mode_octal', 'ctime_ns')), label + '_CHMOD_SCOPE')
        os.fsync(row['fd'])
    protected_unchanged(objects)


def rollback_modes(objects, changed):
    restored = []
    for label in reversed(changed):
        row = objects[label]
        require('after' in row and named(label, row['path'], row['fd']) == row['after'], label + '_ROLLBACK_FOREIGN_CHANGE')
        os.fchmod(row['fd'], int(row['before']['mode_octal'], 8)); os.fsync(row['fd'])
        current = named(label, row['path'], row['fd'])
        require(all(current[key] == row['before'][key] for key in row['before'] if key != 'ctime_ns'),
                label + '_ROLLBACK_READBACK')
        restored.append(label)
    return restored


def lock_file(diag, path, operation):
    parent = diag.directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == OWNER_UID and stat.S_IMODE(info.st_mode) == 0o600, 'LOCK_SCOPE')
        fcntl.flock(fd, operation | fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd); raise


def main():
    assets, diag, qa, program_sha = prepared()
    request, source = qa.owner_context()
    require(os.geteuid() == OWNER_UID and os.getegid() == OWNER_GID, 'CURRENT_OWNER')
    require(not qa.stop_present(), 'OWNER_STOP')
    resources = qa.resource_budget()
    result = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'started_at': time.time(),
        'state': 'PREFLIGHT', 'source_pins': {name: digest(raw) for name, raw in assets.items()},
        'qa_child_sha256': program_sha, 'resources_before_mutation': resources,
        'changed_directory_labels': [], 'permissions_verified': False, 'qa_execution_delegated': False,
        'qa_returncode': None, 'qa_acceptance_verified': False, 'rollback_performed': False,
        'recursive_chmod': False, 'chown_performed': False, 'package_installations': 0,
        'training_or_service_actions': 0, 'training_flags_written': False,
        'runtime_gate_weakened': False, 'historical_ctime_ignored': True,
        'live_marker_and_python_identity_checks': True, 'maximum_authorized_native_posts': 1}
    state = maintenance = qa_lock = None; objects = {}; handles = []; changed = []; delegated = False
    prefix = 'owner_browser_runtime_repair_' + request
    try:
        state = diag.directory(STATE)
        maintenance = lock_file(diag, STATE / 'owner_maintenance.lock', fcntl.LOCK_SH)
        require(not (STATE / 'OWNER_MAINTENANCE.flag').exists() and not (STATE / 'OWNER_MAINTENANCE.flag').is_symlink(), 'MAINTENANCE_ACTIVE')
        qa_lock = lock_file(diag, STATE / 'owner_browser_qa/qa.lock', fcntl.LOCK_EX)
        objects, handles = open_objects(diag)
        result['before'] = {label: row['before'] for label, row in objects.items()}
        result['prepared_receipt'] = private_record(state, prefix + '_prepared.json', {
            **result, 'state': 'PREPARED_BEFORE_ANY_PERMISSION_MUTATION',
            'allowed_mode_transition': {'VENV': '0775_TO_0755_OR_ALREADY_0755', 'BIN': '0775_TO_0755_OR_ALREADY_0755'},
            'marker_sha256': MARKER_SHA, 'python_target_path_sha256': TARGET_PATH_SHA})
        require(not qa.stop_present(), 'OWNER_STOP')
        repair_modes(objects, changed)
        result['changed_directory_labels'] = list(changed)
        qa.existing_runtime(); qa.resource_budget()
        protected_unchanged(objects)
        result['after'] = {label: objects[label]['after'] for label in ('VENV', 'BIN')}
        result['permissions_verified'] = True
        result['permissions_receipt'] = private_record(state, prefix + '_permissions.json', {
            **result, 'state': 'EXACT_QA_DIRECTORY_PERMISSIONS_VERIFIED_BEFORE_QA'})
        emit('browser_runtime_permissions', {**result, 'state': 'EXACT_QA_DIRECTORY_PERMISSIONS_VERIFIED_BEFORE_QA'})
        os.close(qa_lock); qa_lock = None
        # A new exclusive QA claimant after this release causes the unchanged
        # child to HOLD on its own lock; it cannot create a second native turn.
        old_run, old_emit = qa.run_child, qa.emit
        def run(*args):
            nonlocal delegated
            delegated = True; result['qa_execution_delegated'] = True
            return old_run(*args)
        def observe(kind, value):
            if kind == 'browser_stream_only_receipt':
                result['qa_observation'] = {key: value.get(key) for key in (
                    'state', 'reason', 'stream_only_acceptance_verified', 'two_parts_observed',
                    'strict_progressive_stream_observed', 'two_proper_prefixes_before_done',
                    'proper_prefix_count_before_done', 'native_posts_admitted', 's03_readback_verified')}
            old_emit(kind, value)
        qa.run_child = run; qa.emit = observe
        result['qa_returncode'] = qa.main()
        protected_unchanged(objects)
        for label in ('VENV', 'BIN'):
            row = objects[label]
            require(named(label, row['path'], row['fd']) == row['after'], label + '_AFTER_QA_CHANGED')
        result['qa_acceptance_verified'] = result['qa_returncode'] == 0
        result['post_qa_runtime_identity_verified'] = True
        result['state'] = 'RUNTIME_PERMISSIONS_AND_STREAM_ONLY_VERIFIED' if result['qa_returncode'] == 0 else 'RUNTIME_PERMISSIONS_VERIFIED_STREAM_ONLY_HOLD'
    except BaseException as exc:
        result.update(state='HOLD', reason=safe(exc), changed_directory_labels=list(changed))
        if changed and not delegated:
            try:
                result['rollback_directory_labels'] = rollback_modes(objects, changed)
                result['rollback_performed'] = True; result['permissions_verified'] = False
            except BaseException as rollback:
                result['rollback_reason'] = safe(rollback)
        elif delegated:
            # QA failure does not undo a verified permission improvement, but
            # do not report stale permission/target proof after concurrent drift.
            try:
                protected_unchanged(objects)
                for label in ('VENV', 'BIN'):
                    row = objects[label]
                    require(named(label, row['path'], row['fd']) == row['after'], label + '_FAILURE_POSTCHECK_CHANGED')
                result['post_qa_runtime_identity_verified'] = True
            except BaseException as postcheck:
                result['permissions_verified'] = False
                result['post_qa_runtime_identity_verified'] = False
                result['post_qa_identity_reason'] = safe(postcheck)
        result['qa_returncode'] = 2
    finally:
        result['finished_at'] = time.time()
        try:
            if state is not None:
                receipt = private_record(state, prefix + '.json', result)
                result['final_receipt'] = receipt
            emit('browser_runtime_repair', result)
        finally:
            for fd in reversed(handles):
                os.close(fd)
            for fd in (qa_lock, maintenance, state):
                if fd is not None:
                    os.close(fd)
    rc = 0 if result['state'] == 'RUNTIME_PERMISSIONS_AND_STREAM_ONLY_VERIFIED' else 2
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(rc == 0).lower(), flush=True)
    return rc


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit('browser_runtime_repair_preflight', {'state': 'HOLD', 'reason': safe(exc), 'private_exception_exported': False})
        raise SystemExit(2)
