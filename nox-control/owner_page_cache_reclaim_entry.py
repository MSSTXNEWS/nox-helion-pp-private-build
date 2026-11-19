#!/usr/bin/env python3
"""Run one owner-authorized, fresh-audit page-cache hint pass.

This performs no file unlink, model/weight/S03 change, process kill, service
restart, or native/browser admission. The pinned helper owns its receipt and
nonblocking storage/maintenance lease checks.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import re
import tempfile
import time
from pathlib import Path

ROOT = Path('/root/nox')
STOP_NAMES = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
              'state/STOP', 'state/STOP.flag')
HELPER_SOURCE_COMMIT = 'e35f194fc62fc3b91ea573dfc0149f8bb8c84258'
HELPER_BLOB_SHA = '569c8f727d1c3b2bee656b03f5766771ea4220ef'
RECEIPT_SCHEMA = 'NOX_OWNER_PAGE_CACHE_RECLAIM_GUARD_V1'
RECEIPT_MARKER = 'NOX_MAINT_PAGE_CACHE_RECLAIM='
COMPLETE_MARKER = 'NOX_MAINT_PAGE_CACHE_RECLAIM_COMPLETE=true'
SAFE_CATEGORIES = frozenset({
    'PIP_DOWNLOAD_CACHE', 'PIP_WHEEL_CACHE',
    'OLD_DEBUG_LOG_ROTATION', 'INACTIVE_ELF_CORE',
})
HELPER_B64 = __NOX_STORAGE_HELPER_B64__


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def owner_context():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(bool(re.fullmatch(r'[0-9]{1,20}', request))
            and bool(re.fullmatch(r'[0-9a-f]{40}', source)),
            'HOLD_PAGE_CACHE_OWNER_CONTEXT')
    return request, source


def stop_present():
    paths = [ROOT / name for name in STOP_NAMES]
    paths.append(Path('/workspace/NOX_STOP'))
    return any(path.exists() or path.is_symlink() for path in paths)


def clean_state(exc):
    value = str(exc)
    if re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}', value):
        return value
    name = re.sub(r'[^A-Z0-9_]', '_', type(exc).__name__.upper())[:60]
    return 'HOLD_PAGE_CACHE_' + (name or 'ERROR')


def receipt(request, source, state, audit_sha=None, result=None):
    if result is None:
        result = {}
    advised = result.get('advised_files', [])
    headroom = result.get('headroom_at_start_bytes')
    native_floor = result.get('two_gib_admission_memory_threshold_met_after')
    browser_floor = result.get('browser_memory_prerequisite_met_after')
    stop_reason = result.get('stop_reason')
    logical = result.get('logical_bytes_advised', 0)
    return {
        'schema': RECEIPT_SCHEMA,
        'action': 'PAGE_CACHE_RECLAIM',
        'request': request,
        'source_sha': source,
        'helper_source_commit': HELPER_SOURCE_COMMIT,
        'helper_blob_sha': HELPER_BLOB_SHA,
        'audit_request': request,
        'audit_sha256': audit_sha,
        'state': state,
        'files_advised': len(advised) if isinstance(advised, list) else 0,
        'logical_bytes_advised': logical if type(logical) is int else 0,
        'actual_reclaimed_bytes_confirmed': 0,
        'reclaim_amount_unverified': True,
        'files_unlinked': 0,
        'model_files_touched': False,
        'weights_or_S03_modified': False,
        'processes_killed': 0,
        'services_restarted': 0,
        'native_job_admitted': False,
        'browser_runtime_admitted': False,
        'browser_disk_prerequisite_checked': False,
        'headroom_at_start_bytes': headroom if type(headroom) is int else None,
        'two_gib_admission_memory_threshold_met_after': native_floor if type(native_floor) is bool else None,
        'browser_memory_prerequisite_met_after': browser_floor if type(browser_floor) is bool else None,
        'stop_reason': stop_reason if isinstance(stop_reason, str) else None,
        'public_output_contains_paths_or_private_text': False,
    }


def resource_headroom(storage):
    budget = storage.filesystem_budget()
    cgroup = budget.get('cgroup') if isinstance(budget, dict) else None
    if not isinstance(cgroup, dict):
        raise RuntimeError('HOLD_PAGE_CACHE_RESOURCE_UNVERIFIED')
    headroom = cgroup.get('headroom_bytes')
    limit = cgroup.get('limit_bytes')
    if (type(headroom) is not int or type(limit) is not int
            or headroom < 0 or limit <= 0 or headroom > limit):
        raise RuntimeError('HOLD_PAGE_CACHE_RESOURCE_UNVERIFIED')
    return headroom


def execute(request, source):
    if stop_present():
        raise RuntimeError('HOLD_PAGE_CACHE_STOP_PRESENT')
    try:
        helper_raw = base64.b64decode(HELPER_B64, validate=True)
    except Exception:
        raise RuntimeError('HOLD_PAGE_CACHE_HELPER_ENCODING') from None
    if (not helper_raw or len(helper_raw) > 1024 * 1024
            or hashlib.sha1(b'blob ' + str(len(helper_raw)).encode('ascii') + b'\x00' + helper_raw).hexdigest() != HELPER_BLOB_SHA):
        raise RuntimeError('HOLD_PAGE_CACHE_HELPER_PIN')

    temporary_root = Path(tempfile.mkdtemp(prefix='nox-page-cache-helper-'))
    staged = temporary_root / 'owner_storage_reclaim.py'
    try:
        fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'wb') as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(helper_raw)
            output.flush()
            os.fsync(output.fileno())
        if staged.is_symlink() or staged.read_bytes() != helper_raw:
            raise RuntimeError('HOLD_PAGE_CACHE_HELPER_READBACK')
        spec = importlib.util.spec_from_file_location('_nox_page_cache_reclaim', staged)
        if spec is None or spec.loader is None:
            raise RuntimeError('HOLD_PAGE_CACHE_HELPER_LOAD')
        storage = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(storage)

        # Validate resources before auditing; the helper rechecks under its lease.
        resource_headroom(storage)
        if stop_present():
            raise RuntimeError('HOLD_PAGE_CACHE_STOP_CHANGED')

        audit = storage.audit(request, source)
        if (not isinstance(audit, dict) or audit.get('schema') != storage.SCHEMA
                or audit.get('action') != 'AUDIT' or audit.get('instance_id') != storage.INSTANCE
                or audit.get('request') != request or audit.get('source_sha') != source
                or audit.get('helper_sha256') != hashlib.sha256(helper_raw).hexdigest()
                or audit.get('files_deleted') != 0
                or audit.get('process_scan', {}).get('complete') is not True
                or not isinstance(audit.get('cleanup_candidates'), list)
                or len(audit['cleanup_candidates']) > storage.MAX_CANDIDATES
                or any(row.get('category') not in SAFE_CATEGORIES for row in audit['cleanup_candidates'])
                or type(audit.get('finished_at')) not in (int, float)
                or not 0 <= time.time() - audit['finished_at'] <= storage.AUDIT_TTL):
            raise RuntimeError('HOLD_PAGE_CACHE_AUDIT_SCOPE')
        audit_path = storage.receipt_directory() / ('audit_' + request + '.json')
        audit_sha = storage.write_receipt(audit_path, audit)
        audit_raw = storage.bounded_bytes(audit_path, 2 * 1024 * 1024)
        if storage.digest_bytes(audit_raw) != audit_sha or json.loads(audit_raw) != audit:
            raise RuntimeError('HOLD_PAGE_CACHE_AUDIT_READBACK')

        # Re-read STOP and current resource headroom immediately before the pass.
        if stop_present():
            raise RuntimeError('HOLD_PAGE_CACHE_STOP_CHANGED')
        resource_headroom(storage)
        original_fadvise = getattr(storage.os, 'posix_fadvise', None)
        if not callable(original_fadvise):
            raise RuntimeError('HOLD_PAGE_CACHE_FADVISE_UNAVAILABLE')
        stop_seen = [False]

        def guarded_fadvise(fd, offset, length, advice):
            if stop_seen[0] or stop_present():
                stop_seen[0] = True
                raise storage.StorageHold('HOLD_PAGE_CACHE_STOP_PRESENT')
            return original_fadvise(fd, offset, length, advice)

        storage.os.posix_fadvise = guarded_fadvise
        try:
            result = storage.reclaim_page_cache(request, source, request, audit_sha)
        finally:
            storage.os.posix_fadvise = original_fadvise
        if stop_seen[0] or stop_present():
            raise RuntimeError('HOLD_PAGE_CACHE_STOP_PRESENT')

        output_path = storage.receipt_directory() / ('page_cache_' + request + '.json')
        output_raw = storage.bounded_bytes(output_path, 2 * 1024 * 1024)
        if (json.loads(output_raw) != result or result.get('schema') != storage.SCHEMA
                or result.get('action') != 'PAGE_CACHE_RECLAIM'
                or result.get('request') != request or result.get('source_sha') != source
                or result.get('audit_request') != request or result.get('audit_sha256') != audit_sha
                or result.get('one_shot_no_retry') is not True
                or result.get('actual_reclaimed_bytes_confirmed') != 0
                or result.get('reclaim_amount_unverified') is not True
                or result.get('files_unlinked') != 0
                or result.get('model_files_touched') is not False
                or result.get('weights_or_S03_modified') is not False
                or result.get('processes_killed') != 0 or result.get('services_restarted') != 0
                or result.get('native_job_admitted') is not False
                or result.get('browser_runtime_admitted') is not False
                or result.get('browser_disk_prerequisite_checked') is not False):
            raise RuntimeError('HOLD_PAGE_CACHE_RESULT_SCOPE')
        return receipt(request, source, result.get('state', 'HOLD_PAGE_CACHE_RESULT'),
                       audit_sha, result)
    finally:
        try:
            if staged.exists() or staged.is_symlink():
                if staged.is_symlink():
                    raise RuntimeError('HOLD_PAGE_CACHE_TEMP_CLEANUP')
                staged.unlink(missing_ok=True)
                if staged.exists() or staged.is_symlink():
                    raise RuntimeError('HOLD_PAGE_CACHE_TEMP_CLEANUP')
            temporary_root.rmdir()
            if temporary_root.exists() or temporary_root.is_symlink():
                raise RuntimeError('HOLD_PAGE_CACHE_TEMP_CLEANUP')
        except OSError:
            raise RuntimeError('HOLD_PAGE_CACHE_TEMP_CLEANUP') from None


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'[0-9]{1,20}', request) or not re.fullmatch(r'[0-9a-f]{40}', source):
        raise SystemExit(2)
    try:
        value = execute(request, source)
    except Exception as exc:
        value = receipt(request, source, clean_state(exc))
        print(RECEIPT_MARKER + json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False), flush=True)
        raise SystemExit(2)
    print(RECEIPT_MARKER + json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False), flush=True)
    print(COMPLETE_MARKER, flush=True)


if __name__ == '__main__':
    main()
