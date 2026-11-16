#!/usr/bin/env python3
"""Read only the fixed isolated-browser runtime metadata; never repair it."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

AREA = Path('/root/nox/browser_qa')
SPEC = {'schema': 'NOX_OWNER_BROWSER_ENV_V1', 'playwright': '1.65.2',
        'base_python': '/root/nox/venv/bin/python', 'torch_modified': False}
SCHEMA = 'NOX_BROWSER_RUNTIME_METADATA_V1'
NATIVE_QA_ENTRY_SHA = '8866e963acd01f5b5775e079b8d6b85753d8e34ad1d636fcca04f1a6c841d6de'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def metadata(info):
    return {'uid': info.st_uid, 'gid': info.st_gid, 'mode_octal': format(stat.S_IMODE(info.st_mode), '04o'),
        'owner_matches_euid': info.st_uid == os.geteuid(), 'group_or_world_writable': bool(info.st_mode & 0o022),
        'type': 'DIRECTORY' if stat.S_ISDIR(info.st_mode) else 'REGULAR' if stat.S_ISREG(info.st_mode)
                else 'SYMLINK' if stat.S_ISLNK(info.st_mode) else 'OTHER',
        'device': str(info.st_dev), 'inode': str(info.st_ino), 'bytes': info.st_size,
        'mtime_ns': str(info.st_mtime_ns), 'ctime_ns': str(info.st_ctime_ns)}


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mode, info.st_uid, info.st_gid, info.st_mtime_ns, info.st_ctime_ns


def directory(path):
    """No symlink traversal, including each parent of the fixed allowed path."""
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd); raise


def directory_record(path, private):
    fd = None
    try:
        fd = directory(path); info = os.fstat(fd)
        result = {'present': True, **metadata(info)}
        result['original_directory_gate_passes'] = bool(info.st_uid == os.geteuid() and not info.st_mode & 0o022)
        result['original_private_gate_passes'] = not private or stat.S_IMODE(info.st_mode) == 0o700
        return result
    except OSError as exc:
        return {'present': None, 'read_state': type(exc).__name__, 'original_directory_gate_passes': False,
                'original_private_gate_passes': False}
    finally:
        if fd is not None:
            os.close(fd)


def marker_record():
    parent = fd = None
    result = {'label': 'OWNER_ENVIRONMENT_MARKER', 'raw_contents_exported': False}
    try:
        parent = directory(AREA)
        fd = os.open('owner-environment.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
                     | getattr(os, 'O_NOATIME', 0), dir_fd=parent)
        before = os.fstat(fd); result.update(metadata(before))
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 4096:
            return dict(result, read_state='NONREGULAR_OR_OUT_OF_BOUND', original_marker_gate_passes=False)
        raw = os.pread(fd, 4097, 0)
        after = os.fstat(fd); named = os.stat('owner-environment.json', dir_fd=parent, follow_symlinks=False)
        if len(raw) != before.st_size or identity(before) != identity(after) or identity(after) != identity(named):
            return dict(result, read_state='CHANGED', original_marker_gate_passes=False)
        result.update(sha256=digest(raw), read_state='STABLE_READ')
        def unique(pairs):
            out = {}
            for key, value in pairs:
                if key in out:
                    raise ValueError('duplicate')
                out[key] = value
            return out
        def constant(_):
            raise ValueError('nonfinite')
        try:
            value = json.loads(raw, object_pairs_hook=unique, parse_constant=constant)
        except (ValueError, UnicodeError):
            return dict(result, json_state='INVALID', original_marker_gate_passes=False)
        matches = isinstance(value, dict) and value == SPEC
        result.update(json_state='VALID', exact_expected_marker=matches,
            declared_schema=SPEC['schema'] if isinstance(value, dict) and value.get('schema') == SPEC['schema'] else 'UNEXPECTED',
            declared_playwright_version=SPEC['playwright'] if isinstance(value, dict) and value.get('playwright') == SPEC['playwright'] else 'UNEXPECTED',
            declared_base_python_matches_expected=isinstance(value, dict) and value.get('base_python') == SPEC['base_python'],
            declared_torch_modified_false=isinstance(value, dict) and value.get('torch_modified') is False,
            original_marker_gate_passes=matches and before.st_uid == os.geteuid() and stat.S_IMODE(before.st_mode) == 0o600)
        return result
    except OSError as exc:
        return dict(result, read_state=type(exc).__name__, original_marker_gate_passes=False)
    finally:
        for handle in (fd, parent):
            if handle is not None:
                os.close(handle)


def python_record():
    result = {'label': 'QA_PYTHON', 'target_path_exported': False, 'raw_symlink_exported': False}
    parent = fd = None
    try:
        parent = directory(AREA / 'venv/bin')
        before = os.stat('python', dir_fd=parent, follow_symlinks=False)
        result['link_or_file'] = metadata(before)
        python = AREA / 'venv/bin/python'
        target = python.resolve(strict=True)
        result['resolved_target_path_sha256'] = digest(os.fsencode(str(target)))
        result['target_category'] = ('QA_ENV' if target.is_relative_to(AREA)
            else 'NOX_BASE_ENV' if target.is_relative_to(Path('/root/nox/venv'))
            else 'SYSTEM_BIN' if target.parent in (Path('/usr/bin'), Path('/usr/local/bin')) else 'OTHER')
        target_before = target.stat(follow_symlinks=False)
        result['target'] = metadata(target_before)
        if not stat.S_ISREG(target_before.st_mode):
            return dict(result, read_state='TARGET_NOT_REGULAR', target_regular=False,
                        original_python_gate_passes=False)
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        info = os.fstat(fd); result['target'] = metadata(info)
        if identity(info) != identity(target_before):
            return dict(result, read_state='TARGET_CHANGED', original_python_gate_passes=False)
        after = os.stat('python', dir_fd=parent, follow_symlinks=False)
        result['link_metadata_unchanged'] = identity(before) == identity(after)
        result['target_regular'] = stat.S_ISREG(info.st_mode)
        result['target_elf_header'] = stat.S_ISREG(info.st_mode) and os.pread(fd, 4, 0) == b'\x7fELF'
        result['original_python_gate_passes'] = bool(identity(before) == identity(after)
            and stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o022
            and os.access(python, os.X_OK))
        return result
    except (OSError, RuntimeError) as exc:
        return dict(result, read_state=type(exc).__name__, original_python_gate_passes=False)
    finally:
        for handle in (fd, parent):
            if handle is not None:
                os.close(handle)


def interpreter_version(allowed):
    # Refuse to execute anything under a directory that failed the original QA
    # gate. -S also skips all pth/site imports; this probe never imports Playwright.
    if not allowed:
        return {'executed': False, 'reason': 'ORIGINAL_RUNTIME_GATE_HELD'}
    program = ("import hashlib,json,sys;print(json.dumps({'version':list(sys.version_info[:3]),"
        "'executable_path_sha256':hashlib.sha256(sys.executable.encode()).hexdigest(),"
        "'site_imported':'site' in sys.modules}))")
    try:
        proc = subprocess.run([str(AREA / 'venv/bin/python'), '-I', '-S', '-B', '-c', program],
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, capture_output=True, timeout=5)
        if proc.returncode != 0 or len(proc.stdout) > 4096 or len(proc.stderr) > 4096:
            return {'executed': True, 'reason': 'INTERPRETER_PROBE_FAILED', 'raw_output_exported': False}
        value = json.loads(proc.stdout)
        version = value.get('version')
        if (not isinstance(version, list) or len(version) != 3 or any(type(n) is not int or not 0 <= n <= 1000 for n in version)
                or not re.fullmatch('[a-f0-9]{64}', value.get('executable_path_sha256', '')) or value.get('site_imported') is not False):
            return {'executed': True, 'reason': 'INTERPRETER_PROJECTION_INVALID', 'raw_output_exported': False}
        return {'executed': True, 'state': 'VERSION_ONLY_VERIFIED', **value, 'raw_output_exported': False}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'executed': True, 'reason': 'INTERPRETER_PROBE_FAILED', 'raw_output_exported': False}


def snapshot():
    rows = {name: directory_record(path, private) for name, path, private in (
        ('AREA', AREA, True), ('VENV', AREA / 'venv', False), ('BIN', AREA / 'venv/bin', False))}
    marker, python = marker_record(), python_record()
    failures = [label for label, row in rows.items() if row.get('original_directory_gate_passes') is not True]
    private_failures = [label for label, row in rows.items() if row.get('original_private_gate_passes') is not True]
    passed = not failures and not private_failures and marker.get('original_marker_gate_passes') is True and python.get('original_python_gate_passes') is True
    return {'schema': SCHEMA, 'state': 'RUNTIME_METADATA_OBSERVED', 'original_entry_sha256': NATIVE_QA_ENTRY_SHA,
        'euid': os.geteuid(), 'egid': os.getegid(), 'directories': rows,
        'failing_original_directory_labels': failures, 'failing_original_private_labels': private_failures,
        'marker': marker, 'python': python, 'original_runtime_gate_passes': passed,
        'interpreter_version_probe': interpreter_version(passed),
        'browser_started': False, 'native_chat_posts': 0, 'permission_or_package_changes': False,
        'credential_or_cookie_files_read': False, 'runtime_gate_weakened': False}


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch('[0-9]{1,24}', request) or not re.fullmatch('[a-f0-9]{40}', source):
        raise RuntimeError('HOLD_BROWSER_RUNTIME_INSPECT_CONTEXT')
    started = time.time(); result = snapshot()
    result.update(request=request, source_sha=source, started_at=started, finished_at=time.time())
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'browser_runtime_inspect', 'data': result}, separators=(',', ':'), allow_nan=False), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'browser_runtime_inspect_hold', 'data': {
            'reason': type(exc).__name__, 'raw_exception_exported': False, 'browser_started': False, 'native_chat_posts': 0}}), flush=True)
        raise SystemExit(2)
