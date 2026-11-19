"""Project progress derived from recorded evidence. Used inside authenticated OneHost."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import errno
from collections import defaultdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
import stat
from pathlib import Path
import re
import secrets
import tempfile
from urllib.parse import urlparse

GROUPS = ('NOX PRIME', 'Резонанс', 'Maya и GPU', 'Мозг и S03', 'FORGE',
          'WEB и медиа', 'Диспетчер')
STATES = {'pending', 'running', 'blocked', 'paused', 'failed', 'verified'}
EVIDENCE = {'source', 'native'}
TASK_ID = re.compile(r'[0-6](?:[AB][0-9]{2}|V14-[0-9]{2})\Z')
BASE_TOTAL = 230
IDEA_TOTAL = 65
IDEA_IDS = frozenset(f'I-{index:02d}' for index in range(1, IDEA_TOTAL + 1))
FINAL_TASK_ID = '0V14-15'
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
WAVE_PLAN = 'work_wave_plan.json'


def _unique_json_keys(pairs):
    """Reject shadowed TaskID, state, scope or receipt fields at every JSON depth."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('WORK_PROGRESS_DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def _reject_json_constant(_value):
    """NaN/Infinity are not JSON evidence and must never enter task status."""
    raise ValueError('WORK_PROGRESS_NONFINITE_JSON')


MAX_JSON_BYTES = 2 * 1024 * 1024


def _path_entry_exists(path: Path):
    """A dangling symlink is an unsafe entry, not an absent manifest."""
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _file_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def receipt_writer_lock(directory: Path):
    """Never follow/lock an alias of a protected file as the receipt writer lock."""
    lock_path = directory / '.work_receipts.lock'
    try:
        # Anchor the entire ancestor walk; O_NOFOLLOW on only the basename
        # does not protect the writer lock from a symlinked parent directory.
        fd = _open_registry_no_follow(lock_path,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.EISDIR):
            raise ValueError('WORK_PROGRESS_UNSAFE_RECEIPT_LOCK') from exc
        raise
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                _file_identity(before) != _file_identity(lock_path.lstat())):
            raise ValueError('WORK_PROGRESS_UNSAFE_RECEIPT_LOCK')
        fcntl.flock(fd, fcntl.LOCK_EX)
        if _file_identity(os.fstat(fd)) != _file_identity(lock_path.lstat()):
            raise ValueError('WORK_PROGRESS_UNSAFE_RECEIPT_LOCK')
        yield
    finally:
        os.close(fd)


def _open_registry_no_follow(path: Path, flags: int):
    """Walk absolute path with O_NOFOLLOW directory FDs, not path-string open.

    No directory alias is followed, even when a parent changes after the
    preliminary is_symlink() scan. All intermediate descriptors are closed.
    Linux OneHost only; a live writer still requires owner-auth fencing.
    """
    absolute = Path(os.path.abspath(os.fspath(path)))
    parts = absolute.parts[1:]
    directory_fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in parts[:-1]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY |
                              os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        return os.open(parts[-1], flags, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)


def read_bytes(path: Path, limit=MAX_JSON_BYTES):
    """Bound reads and pin every path component with no-follow openat."""
    if type(limit) is not int or not 1 <= limit <= MAX_JSON_BYTES:
        raise ValueError('WORK_PROGRESS_FILE_LIMIT')
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError('WORK_PROGRESS_UNSAFE_PARENT_LINK')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    fd = _open_registry_no_follow(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError('WORK_PROGRESS_UNSAFE_FILE_TYPE')
        if before.st_size > limit:
            raise ValueError('WORK_PROGRESS_FILE_LIMIT')
        remaining = limit + 1
        chunks = []
        while remaining:
            part = os.read(fd, min(131072, remaining))
            if not part:
                break
            chunks.append(part)
            remaining -= len(part)
        data = b''.join(chunks)
        if len(data) > limit:
            raise ValueError('WORK_PROGRESS_FILE_LIMIT')
        reread = bytearray()
        reread_limit = min(limit + 1, len(data) + 1)
        while len(reread) < reread_limit:
            part = os.pread(fd, min(131072, reread_limit - len(reread)), len(reread))
            if not part:
                break
            reread.extend(part)
        if bytes(reread) != data:
            raise ValueError('WORK_PROGRESS_FILE_CHANGED_DURING_READ')
        after = os.fstat(fd)
        on_path = path.lstat()
        if any(parent.is_symlink() for parent in path.parents):
            raise ValueError('WORK_PROGRESS_UNSAFE_PARENT_LINK')
        if (_file_identity(before) != _file_identity(after) or
                _file_identity(after) != _file_identity(on_path)):
            raise ValueError('WORK_PROGRESS_FILE_CHANGED_DURING_READ')
    finally:
        os.close(fd)
    return data


def _decode_json(data):
    return json.loads(data, object_pairs_hook=_unique_json_keys,
                      parse_constant=_reject_json_constant,
                      parse_float=_parse_finite_json_float)


def read_json(path: Path):
    """Read bounded JSON with duplicate-key and nonfinite-value rejection."""
    return _decode_json(read_bytes(path))


def read_json_with_raw(path: Path):
    """Return the exact verified source bytes as well as their parsed JSON."""
    raw = read_bytes(path)
    return raw, _decode_json(raw)

def _parse_finite_json_float(raw):
    """JSON exponent overflow is nonfinite evidence even without NaN literals."""
    value = float(raw)
    if value in (float('inf'), float('-inf')):
        raise ValueError('WORK_PROGRESS_NONFINITE_JSON')
    return value


def read_manifest(path: Path):
    data = read_json(path)
    items = data['tasks']
    if data.get('schema') != 'nox-work-tasks-v1' or not isinstance(items, list) or not items:
        raise ValueError('WORK_PROGRESS_MANIFEST')
    tasks = {}
    for task in items:
        key = task['id']
        if (not isinstance(key, str) or not TASK_ID.fullmatch(key) or key in tasks or
                task['evidence'] not in EVIDENCE or not isinstance(task['title'], str) or
                not task['title'].strip() or task['group'] != int(key[0])):
            raise ValueError('WORK_PROGRESS_TASK')
        tasks[key] = task
    if {task['group'] for task in tasks.values()} != set(range(len(GROUPS))):
        raise ValueError('WORK_PROGRESS_GROUPS')
    return tasks


def read_ideas(path: Path):
    if not _path_entry_exists(path):
        return {}
    data = read_json(path)
    items = data.get('ideas')
    if data.get('schema') != 'nox-work-ideas-v1' or not isinstance(items, list):
        raise ValueError('WORK_PROGRESS_IDEAS_MANIFEST')
    ideas = {}
    for idea in items:
        key = idea['id']
        group = idea['group']
        if (not isinstance(key, str) or key not in IDEA_IDS or key in ideas or
                type(group) is not int or not 0 <= group < len(GROUPS) or
                idea['evidence'] not in EVIDENCE or not isinstance(idea['title'], str) or
                not idea['title'].strip()):
            raise ValueError('WORK_PROGRESS_IDEA')
        ideas[key] = idea
    if ideas.keys() != IDEA_IDS:
        raise ValueError('WORK_PROGRESS_IDEAS_INCOMPLETE')
    return ideas


def registries(directory):
    tasks = read_manifest(directory / 'work_tasks.json')
    ideas = read_ideas(directory / 'work_ideas.json')
    if ideas and (len(tasks) != BASE_TOTAL or tasks.get(FINAL_TASK_ID, {}).get('evidence') != 'native'):
        raise ValueError('WORK_PROGRESS_BASELINE')
    return tasks, ideas


def read_receipt_payload(path: Path):
    if not _path_entry_exists(path):
        return {'schema': 'nox-work-receipts-v1', 'tasks': {}}
    data = read_json(path)
    if data.get('schema') != 'nox-work-receipts-v1' or not isinstance(data.get('tasks'), dict):
        raise ValueError('WORK_PROGRESS_RECEIPTS')
    return data


def read_receipts(path: Path):
    return read_receipt_payload(path)['tasks']


def valid_link(value):
    if not isinstance(value, str) or len(value) > 1500 or any(char.isspace() for char in value):
        return False
    try:
        target = urlparse(value)
        return target.scheme == 'https' and bool(target.hostname) and target.username is None
    except ValueError:
        return False


def valid_time(value):
    """Reject naive or implausibly future-dated receipts before counting PASS."""
    try:
        if not isinstance(value, str):
            return False
        parsed = datetime.fromisoformat(value)
        return (parsed.utcoffset() is not None and
                parsed.timestamp() <= datetime.now(timezone.utc).timestamp() + 300)
    except (ValueError, OverflowError, OSError):
        return False


def is_verified(task, record):
    return (isinstance(record, dict) and record.get('state') == 'verified' and
            record.get('scope') == task['evidence'] and
            valid_link(record.get('evidence')) and valid_time(record.get('updated_at')))


def counts(completed, total):
    return {'completed': completed, 'total': total, 'percent': 100 * completed // total if total else 0}


def evidence_set_digest(tasks, receipts):
    snapshot = [(key, task, receipts[key]) for key, task in sorted(tasks.items())]
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def valid_sha256(value):
    return isinstance(value, str) and bool(SHA256.fullmatch(value)) and value != '0' * 64


def final_status(tasks, receipts, candidate, complete):
    if not complete:
        return {'passed': False, 'state': 'pending_implementation'}
    if (not isinstance(candidate, dict) or candidate.get('scope') != 'native' or
            not valid_sha256(candidate.get('artifact_sha256')) or
            not valid_link(candidate.get('evidence')) or not valid_time(candidate.get('updated_at')) or
            candidate.get('evidence') != receipts.get(FINAL_TASK_ID, {}).get('evidence') or
            datetime.fromisoformat(candidate['updated_at']) <
            max(datetime.fromisoformat(receipts[key]['updated_at']) for key in tasks) or
            candidate.get('evidence_set_sha256') != evidence_set_digest(tasks, receipts)):
        return {'passed': False, 'state': 'pending_native_acceptance'}
    return {'passed': True, 'state': 'verified', 'scope': 'native',
            'artifact_sha256': candidate['artifact_sha256'], 'evidence': candidate['evidence'],
            'updated_at': candidate['updated_at']}


def optional_wave_view(directory, base, ideas, payload):
    wave_path = directory / WAVE_PLAN
    try:
        if not wave_path.is_file():
            return None
        if __name__ == 'nox_v15_work_progress':
            from nox_v15_wave_progress import read_wave_view
        else:
            from wave_progress import read_wave_view
        return read_wave_view(wave_path, base, ideas, payload)
    except FileNotFoundError:
        return None
    except (ImportError, OSError, KeyError, TypeError, ValueError, AttributeError):
        return {'status': 'unavailable'}


FROZEN_295_MANIFEST_BLOB = 'f5c45dc8919b1b800e89a421676a3627e75fb3bb'
FROZEN_WORK_TASKS_BLOB = 'ca8f24491de0fa5fcfec12fead78fd22999f521f'
FROZEN_WORK_RECEIPTS_BLOB = '6a9c71393735dbc4b5c1577272f22cef38ab6338'
SUPPLEMENTAL_SCHEMA = 'NOX_SUPPLEMENTAL_ACCEPTANCE_ROLLUP_V1'
SIDECAR_SCHEMA = 'NOX_NATIVE_EVIDENCE_ADDENDUM_V1'
SUPPLEMENTAL_MAX_FILES = 512
REPOSITORY_REF = 'repair/nox-native-reflex-autorefill-20261119'
REPOSITORY_URL = 'https://github.com/MSSTXNEWS/nox-helion-pp-private-build'


def git_blob_sha(raw):
    header = b'blob ' + str(len(raw)).encode('ascii') + b'\0'
    return hashlib.sha1(header + raw).hexdigest()


def _pointer_value(document, pointer):
    """Resolve a strict RFC 6901 fragment pointer used by addendum bindings."""
    if not isinstance(pointer, str) or not pointer.startswith('#/'):
        raise ValueError('POINTER_NOT_ABSOLUTE_FRAGMENT')
    current = document
    for raw_token in pointer[2:].split('/'):
        if re.search(r'~(?![01])', raw_token):
            raise ValueError('POINTER_BAD_ESCAPE')
        token = raw_token.replace('~1', '/').replace('~0', '~')
        if isinstance(current, dict):
            if token not in current:
                raise ValueError('POINTER_TARGET_MISSING')
            current = current[token]
        elif isinstance(current, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', token):
                raise ValueError('POINTER_BAD_INDEX')
            index = int(token)
            if index >= len(current):
                raise ValueError('POINTER_TARGET_MISSING')
            current = current[index]
        else:
            raise ValueError('POINTER_PARENT_NOT_CONTAINER')
    return current


def _hex_digest(value, length=64):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{%d}' % length, value) is not None


def _positive_int(value):
    return type(value) is int and value > 0


def _sidecar_refs(document, task_id, spec_sha256):
    scope = document.get('scope')
    if not isinstance(scope, dict):
        raise ValueError('SCOPE_MISSING')
    task_ids = scope.get('task_ids')
    if not isinstance(task_ids, list) or task_ids.count(task_id) != 1:
        raise ValueError('TASK_ID_SCOPE_MISMATCH')
    manifest = scope.get('immutable_295_manifest')
    frozen = scope.get('frozen_ledgers')
    if not isinstance(manifest, dict) and isinstance(frozen, dict):
        manifest = frozen.get('all295_manifest')
    if not isinstance(manifest, dict):
        raise ValueError('FROZEN_MANIFEST_BINDING_MISSING')
    if (manifest.get('path') != 'nox-control/complete_executor_20261118/evidence/all295_execution_disposition.json'
            or manifest.get('git_blob_sha') != FROZEN_295_MANIFEST_BLOB
            or manifest.get('task_record_key') != task_id
            or manifest.get('spec_sha256') != spec_sha256
            or manifest.get('original_acceptance_added') is not False):
        raise ValueError('FROZEN_MANIFEST_BINDING_MISMATCH')
    registry = scope.get('task_registry')
    task_criterion = scope.get('task_criterion')
    if not isinstance(registry, dict) and isinstance(task_criterion, dict):
        registry = task_criterion.get('task_registry')
    if not isinstance(registry, dict):
        raise ValueError('TASK_REGISTRY_BINDING_MISSING')
    if (registry.get('path') != 'nox-control/four_queue_20261118/work_tasks.json'
            or registry.get('git_blob_sha') != FROZEN_WORK_TASKS_BLOB):
        raise ValueError('TASK_REGISTRY_BINDING_MISMATCH')
    frozen_receipts = scope.get('receipts')
    if not isinstance(frozen_receipts, dict) and isinstance(frozen, dict):
        frozen_receipts = frozen.get('work_receipts')
    if not isinstance(frozen_receipts, dict):
        raise ValueError('FROZEN_RECEIPT_BINDING_MISSING')
    if (frozen_receipts.get('path') != 'nox-control/four_queue_20261118/work_receipts.json'
            or frozen_receipts.get('git_blob_sha') != FROZEN_WORK_RECEIPTS_BLOB):
        raise ValueError('FROZEN_RECEIPT_BINDING_MISMATCH')
    criterion = task_criterion.get('task_spec_sha256') if isinstance(task_criterion, dict) else None
    if criterion is not None and criterion != spec_sha256:
        raise ValueError('TASK_CRITERION_SHA_MISMATCH')
    return scope


def _validate_record_sidecar(document, task_id, spec_sha256, source_path, source_hash):
    criteria = document.get('criteria')
    criterion = criteria.get(task_id) if isinstance(criteria, dict) else None
    if not isinstance(criterion, dict):
        raise ValueError('CRITERION_RECORD_MISSING')
    if criterion.get('spec_sha256') != spec_sha256:
        raise ValueError('CRITERION_SPEC_SHA_MISMATCH')
    if criterion.get('addendum_assessment') != 'ACCEPTED':
        raise ValueError('CRITERION_NOT_ACCEPTED')
    binding = criterion.get('acceptance_binding')
    if not isinstance(binding, dict):
        raise ValueError('ACCEPTANCE_BINDING_MISSING')
    pointer = binding.get('evidence_pointer')
    record = _pointer_value(document, pointer)
    records = document.get('additional_evidence_records')
    if not isinstance(records, list) or not isinstance(record, dict):
        raise ValueError('ACCEPTANCE_RECORD_MISSING')
    if not any(record is row for row in records):
        raise ValueError('ACCEPTANCE_POINTER_OUTSIDE_RECORDS')
    if record.get('task_id') != task_id or record.get('result') != 'ACCEPTED':
        raise ValueError('ACCEPTANCE_RECORD_TASK_OR_RESULT_MISMATCH')
    record_criterion = record.get('criterion')
    if not isinstance(record_criterion, dict) or record_criterion.get('spec_sha256') != spec_sha256:
        raise ValueError('RECORD_SPEC_SHA_MISMATCH')
    evidence_pointer = record.get('evidence_pointer')
    evidence = _pointer_value(document, evidence_pointer)
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError('EVIDENCE_POINTER_NOT_OBJECT')
    workflow = record.get('workflow')
    if not isinstance(workflow, dict):
        raise ValueError('WORKFLOW_BINDING_MISSING')
    run_id = binding.get('workflow_run_id')
    job_id = binding.get('job_id')
    owner_comment_id = binding.get('owner_comment_id', binding.get('request_id'))
    if not all(_positive_int(value) for value in (run_id, job_id, owner_comment_id)):
        raise ValueError('WORKFLOW_IDS_INVALID')
    if (workflow.get('run_id') != run_id or workflow.get('job_id') != job_id
            or workflow.get('owner_authorization_comment_id', workflow.get('request_id')) != owner_comment_id):
        raise ValueError('WORKFLOW_BINDING_MISMATCH')
    if evidence.get('workflow_run_id') != run_id or evidence.get('job_id') != job_id:
        raise ValueError('EVIDENCE_RUN_BINDING_MISMATCH')
    if evidence.get('owner_authorization_comment_id', evidence.get('owner_comment_id')) != owner_comment_id:
        raise ValueError('EVIDENCE_OWNER_BINDING_MISMATCH')
    if evidence.get('source_auth') != 'PASS' or evidence.get('workflow_run_conclusion') != 'success':
        raise ValueError('EVIDENCE_AUTH_OR_RUN_NOT_SUCCESS')
    run_url = 'https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/%d' % run_id
    job_url = run_url + '/job/' + str(job_id)
    if binding.get('run_url') != run_url or binding.get('job_url') != job_url:
        raise ValueError('WORKFLOW_URL_BINDING_MISMATCH')
    return {
        'task_id': task_id,
        'title': criterion.get('title') or record.get('title'),
        'result': 'ACCEPTED',
        'acceptance_pointer': pointer,
        'evidence_pointer': evidence_pointer,
        'run_binding_pointer': '#/criteria/%s/acceptance_binding' % task_id,
        'workflow_run_id': run_id,
        'job_id': job_id,
        'owner_authorization_comment_id': owner_comment_id,
        'workflow_result': workflow.get('conclusion'),
        'evidence_result': evidence.get('workflow_run_conclusion'),
        'spec_sha256': spec_sha256,
        'record_number': record.get('record_number'),
        'source_path': source_path,
        'source_url': REPOSITORY_URL + '/blob/' + REPOSITORY_REF + '/' + source_path,
        'source_sha256': source_hash,
    }


def _validate_criterion_assessment_sidecar(document, task_id, spec_sha256, source_path, source_hash):
    assessment = document.get('criterion_assessment')
    if not isinstance(assessment, dict):
        raise ValueError('SUPPORTED_ACCEPTANCE_BINDING_MISSING')
    if task_id != '6V14-02':
        raise ValueError('CRITERION_ASSESSMENT_VARIANT_UNSUPPORTED_TASK')
    if (assessment.get('accepted') is not True
            or assessment.get('criterion_confirmed_for_point_in_time_process_census') is not True):
        raise ValueError('CRITERION_ASSESSMENT_NOT_ACCEPTED')
    if (assessment.get('acceptance_increment') != 0
            or assessment.get('original_all295_ledger_updated') is not False):
        raise ValueError('ORIGINAL_LEDGER_MUTATION_CLAIM')
    if assessment.get('acceptance_scope') != 'POINT_IN_TIME_PROCESS_SET_ENUMERATION_AND_CORE_IDENTITY_ONLY':
        raise ValueError('CRITERION_SCOPE_UNSUPPORTED')
    census = _pointer_value(document, '#/process_census')
    if not isinstance(census, dict):
        raise ValueError('CENSUS_POINTER_NOT_OBJECT')
    count = census.get('observed_row_count')
    if (census.get('scope') != 'ALL_NUMERIC_PROC_PIDS_MINIMAL_IDENTITY'
            or census.get('numeric_pid_enumeration_complete') is not True
            or census.get('truncated') is not False
            or census.get('enumeration_error_count') != 0
            or census.get('unique_pid_row_count') != count
            or census.get('duplicate_pid_row_count') != 0
            or census.get('core_identity_complete') is not True
            or census.get('core_identity_complete_row_count') != count
            or not _positive_int(count)
            or not _hex_digest(census.get('process_rows_sha256'))):
        raise ValueError('CENSUS_CORE_CRITERION_NOT_MET')
    audit = document.get('audit_binding')
    if not isinstance(audit, dict):
        raise ValueError('AUDIT_BINDING_MISSING')
    request = audit.get('request')
    workflow = _pointer_value(document, '#/audit_binding/workflow')
    remote = audit.get('remote_execution')
    transfer = audit.get('transfer_bundle')
    host = audit.get('host')
    pinned = audit.get('pinned_audit_source')
    if not all(isinstance(x, dict) for x in (request, workflow, remote, transfer, host, pinned)):
        raise ValueError('AUDIT_BINDING_COMPONENT_MISSING')
    run_id, job_id = workflow.get('run_id'), workflow.get('job_id')
    comment_id = request.get('github_issue_comment_id')
    if not all(_positive_int(value) for value in (run_id, job_id, comment_id)):
        raise ValueError('AUDIT_RUN_IDS_INVALID')
    if (request.get('request_kind') != 'owner-authenticated explicit read-only audit'
            or not isinstance(request.get('command'), str)
            or not request['command'].startswith('/nox-maintain ')
            or not request['command'].endswith(' audit')):
        raise ValueError('OWNER_AUDIT_REQUEST_BINDING_INVALID')
    if (not _hex_digest(workflow.get('run_head_sha'), 40)
            or not _hex_digest(pinned.get('audit_pin_commit_sha'), 40)
            or not _hex_digest(pinned.get('audit_source_blob_sha'), 40)
            or host.get('host_pin_verified') is not True
            or not _positive_int(host.get('instance_id'))
            or transfer.get('request_and_source_binding_verified') is not True
            or transfer.get('reassembly_verified') is not True
            or not _hex_digest(transfer.get('sha256'))
            or not _positive_int(transfer.get('byte_count'))
            or not _positive_int(transfer.get('chunk_count'))
            or remote.get('remote_exit_code') != 0):
        raise ValueError('AUDIT_SOURCE_OR_TRANSFER_BINDING_INVALID')
    conclusion = workflow.get('job_conclusion')
    workflow_result = remote.get('workflow_result')
    if conclusion != 'success' and not (conclusion == 'failure' and
            isinstance(workflow_result, str) and workflow_result.startswith('HOLD_')):
        raise ValueError('AUDIT_WORKFLOW_STATUS_INVALID')
    audit_hashes = (pinned.get('owner_guard_blob_sha'),
                    pinned.get('operator_source_blob_sha'),
                    pinned.get('audit_source_blob_sha'))
    if not all(_hex_digest(value, 40) for value in audit_hashes):
        raise ValueError('AUDIT_SOURCE_HASH_INVALID')
    return {
        'task_id': task_id,
        'title': _pointer_value(document, '#/scope/task_criterion').get('task_title'),
        'result': 'ACCEPTED',
        'acceptance_pointer': '#/criterion_assessment',
        'evidence_pointer': '#/process_census',
        'run_binding_pointer': '#/audit_binding/workflow',
        'workflow_run_id': run_id,
        'job_id': job_id,
        'owner_authorization_comment_id': comment_id,
        'workflow_result': workflow_result,
        'evidence_result': 'criterion_confirmed_for_point_in_time_process_census',
        'spec_sha256': spec_sha256,
        'record_number': None,
        'source_path': source_path,
        'source_url': REPOSITORY_URL + '/blob/' + REPOSITORY_REF + '/' + source_path,
        'source_sha256': source_hash,
    }


def supplemental_acceptance(directory, existing_receipt_count):
    """Read append-only sidecars; never mutate or add them to original receipts."""
    directory = Path(directory)
    evidence_dir = directory.parent / 'complete_executor_20261118' / 'evidence'
    manifest_path = evidence_dir / 'all295_execution_disposition.json'
    addenda_dir = evidence_dir / 'addenda'
    excluded = []
    items = []
    scan_complete = True
    try:
        manifest_raw, manifest = read_json_with_raw(manifest_path)
        if (git_blob_sha(manifest_raw) != FROZEN_295_MANIFEST_BLOB
                or manifest.get('schema') != 'NOX_PROJECT_EXECUTION_DISPOSITION_OVERLAY_V1'
                or manifest.get('total_original_ids') != 295
                or not isinstance(manifest.get('tasks'), list)
                or len(manifest['tasks']) != 295):
            raise ValueError('FROZEN_295_MANIFEST_MISMATCH')
        manifest_rows = {}
        for row in manifest['tasks']:
            if not isinstance(row, dict):
                raise ValueError('FROZEN_295_TASK_ROW_INVALID')
            task_id = row.get('task_id')
            spec_sha = row.get('spec_sha256')
            if (not isinstance(task_id, str) or task_id in manifest_rows
                    or not _hex_digest(spec_sha)
                    or not isinstance(row.get('spec'), dict)
                    or row['spec'].get('id') != task_id):
                raise ValueError('FROZEN_295_TASK_ID_OR_SPEC_INVALID')
            manifest_rows[task_id] = spec_sha
        if len(manifest_rows) != 295:
            raise ValueError('FROZEN_295_TASK_IDS_INVALID')
    except (OSError, KeyError, ValueError, TypeError, AttributeError) as exc:
        return {
            'schema': SUPPLEMENTAL_SCHEMA,
            'state': 'HOLD_FROZEN_MANIFEST',
            'frozen_295_count': 295,
            'existing_receipt_count': existing_receipt_count,
            'supplemental_accepted_count': 0,
            'accepted_task_ids': [],
            'original_acceptance_added': 0,
            'scan_complete': False,
            'items': [],
            'excluded': [{'path': str(manifest_path), 'reason': str(exc)}],
        }
    if not _path_entry_exists(addenda_dir):
        return {
            'schema': SUPPLEMENTAL_SCHEMA,
            'state': 'HOLD_ADDENDA_DIRECTORY_MISSING',
            'frozen_295_count': 295,
            'existing_receipt_count': existing_receipt_count,
            'supplemental_accepted_count': 0,
            'accepted_task_ids': [],
            'original_acceptance_added': 0,
            'scan_complete': False,
            'items': [],
            'excluded': [{'path': str(addenda_dir), 'reason': 'ADDENDA_DIRECTORY_MISSING'}],
        }
    try:
        dir_fd = _open_registry_no_follow(
            addenda_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        with os.scandir(dir_fd) as entries:
            names = sorted(entry.name for entry in entries if entry.name.endswith('.json'))
        if len(names) > SUPPLEMENTAL_MAX_FILES:
            raise ValueError('ADDENDA_FILE_COUNT_LIMIT')
    except (OSError, ValueError) as exc:
        return {
            'schema': SUPPLEMENTAL_SCHEMA,
            'state': 'HOLD_ADDENDA_DIRECTORY',
            'frozen_295_count': 295,
            'existing_receipt_count': existing_receipt_count,
            'supplemental_accepted_count': 0,
            'accepted_task_ids': [],
            'original_acceptance_added': 0,
            'scan_complete': False,
            'items': [],
            'excluded': [{'path': str(addenda_dir), 'reason': str(exc)}],
        }
    for name in names:
        path = addenda_dir / name
        source_path = 'nox-control/complete_executor_20261118/evidence/addenda/' + name
        try:
            if len(name) > 200 or Path(name).name != name:
                raise ValueError('ADDENDUM_FILENAME_INVALID')
            raw, document = read_json_with_raw(path)
            source_hash = hashlib.sha256(raw).hexdigest()
            if document.get('schema') != SIDECAR_SCHEMA or document.get('append_only') is not True:
                raise ValueError('ADDENDUM_SCHEMA_OR_APPEND_ONLY_INVALID')
            declared = document.get('scope', {}).get('task_ids') if isinstance(document.get('scope'), dict) else None
            if not isinstance(declared, list) or not declared:
                raise ValueError('ADDENDUM_TASK_IDS_MISSING')
            accepted_claims = set()
            criteria = document.get('criteria')
            if isinstance(criteria, dict):
                accepted_claims.update(task_id for task_id, row in criteria.items()
                                       if isinstance(row, dict) and row.get('addendum_assessment') == 'ACCEPTED')
            assessment = document.get('criterion_assessment')
            if isinstance(assessment, dict) and assessment.get('accepted') is True:
                for task_id in declared:
                    accepted_claims.add(task_id)
            for task_id in sorted(set(declared)):
                if task_id not in accepted_claims:
                    continue
                try:
                    if task_id not in manifest_rows:
                        raise ValueError('TASK_ID_NOT_IN_FROZEN_295')
                    spec_sha = manifest_rows[task_id]
                    _sidecar_refs(document, task_id, spec_sha)
                    if isinstance(criteria, dict) and task_id in criteria:
                        item = _validate_record_sidecar(document, task_id, spec_sha, source_path, source_hash)
                    else:
                        item = _validate_criterion_assessment_sidecar(
                            document, task_id, spec_sha, source_path, source_hash
                        )
                    items.append(item)
                except (KeyError, TypeError, ValueError, AttributeError) as exc:
                    excluded.append({'path': source_path, 'task_id': task_id, 'reason': str(exc)})
        except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
            scan_complete = False
            excluded.append({'path': source_path, 'reason': str(exc)})
    accepted_ids = sorted({item['task_id'] for item in items})
    state = 'COMPLETE' if scan_complete and not excluded else ('PARTIAL' if items else 'HOLD')
    return {
        'schema': SUPPLEMENTAL_SCHEMA,
        'state': state,
        'frozen_295_count': 295,
        'existing_receipt_count': existing_receipt_count,
        'supplemental_accepted_count': len(accepted_ids),
        'accepted_task_ids': accepted_ids,
        'original_acceptance_added': 0,
        'scan_complete': scan_complete,
        'items': items,
        'excluded': excluded,
    }


def summarize(directory: Path):
    base, ideas = registries(directory)
    tasks = {**base, **ideas}
    payload = read_receipt_payload(directory / 'work_receipts.json')
    receipts = payload['tasks']
    groups = defaultdict(list)
    latest = None
    for key, task in tasks.items():
        record = receipts.get(key, {})
        if not isinstance(record, dict):
            record = {}
        timestamp = record.get('updated_at')
        if valid_time(timestamp):
            date = datetime.fromisoformat(timestamp)
            latest = max(latest, date) if latest else date
        groups[task['group']].append((task, record))
    rows = []
    for group_id, label in enumerate(GROUPS):
        group = groups[group_id]
        complete = sum(is_verified(task, record) for task, record in group)
        active = [(task, record) for task, record in group
                  if record.get('state') in ('running', 'paused', 'blocked', 'failed')]
        chosen = next((item for item in active if item[1]['state'] == 'running'), None)
        if chosen is None and active:
            chosen = active[0]
        task, record = chosen if chosen else ({}, {})
        rows.append({'id': group_id, 'label': label, **counts(complete, len(group)),
                     'state': record.get('state') or ('done' if complete == len(group) else 'pending'),
                     'active_task': (task['id'] + ' · ' + task['title'])[:160] if task else None})
    updated_at = latest.isoformat() if latest else None
    done = sum(row['completed'] for row in rows)
    supplemental = supplemental_acceptance(directory, done)
    if len(base) != BASE_TOTAL:
        total = counts(done, len(tasks))
        total['percent'] = min(99, total['percent'])
        return {'schema': 'nox-work-progress-v1', 'frozen_295_count': 295,
                'existing_receipt_count': done,
                'supplemental_accepted_count': supplemental['supplemental_accepted_count'],
                'supplemental_accepted_task_ids': supplemental['accepted_task_ids'],
                'supplemental_acceptance': supplemental,
                'total': total, 'groups': rows, 'updated_at': updated_at}
    ideas_done = sum(is_verified(idea, receipts.get(key)) for key, idea in ideas.items())
    total = counts(done, BASE_TOTAL + IDEA_TOTAL)
    acceptance = final_status(tasks, receipts, payload.get('final_acceptance'),
                              done == total['total'])
    if acceptance['passed']:
        updated_at = acceptance['updated_at']
    else:
        total['percent'] = min(99.9, 1000 * done // total['total'] / 10)
    result = {'schema': 'nox-work-progress-v2',
            'tasks': {**counts(done - ideas_done, BASE_TOTAL), 'registered': len(base)},
            'ideas': {**counts(ideas_done, IDEA_TOTAL), 'registered': len(ideas)},
            'total': {**total, 'registered': len(tasks)},
            'frozen_295_count': 295,
            'existing_receipt_count': done,
            'supplemental_accepted_count': supplemental['supplemental_accepted_count'],
            'supplemental_accepted_task_ids': supplemental['accepted_task_ids'],
            'supplemental_acceptance': supplemental,
            'final_acceptance': acceptance, 'groups': rows, 'updated_at': updated_at}
    wave = optional_wave_view(directory, base, ideas, payload)
    if wave is not None:
        result['work_wave'] = wave
    return result


def save_receipt_payload(directory, target, data):
    """Atomically publish and durably sync a receipt in one pinned directory.

    Using NamedTemporaryFile(dir=path) then Path.replace(path) after pinning
    a directory FD is unsafe: an ancestor can be renamed/rebound between
    operations. Stage, rename and unlink only with the SAME directory FD.
    This is source-level NO-LOSS, not an owner-authorized writer lease.
    """
    directory, target = Path(directory), Path(target)
    if os.path.abspath(os.fspath(target.parent)) != os.path.abspath(os.fspath(directory)):
        raise ValueError('WORK_PROGRESS_RECEIPT_TARGET_OUTSIDE_DIRECTORY')
    directory_fd = _open_registry_no_follow(
        directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    staged_name = '.work_receipts.' + secrets.token_hex(16) + '.tmp'
    try:
        fd = os.open(staged_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory_fd)
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(data, out, ensure_ascii=False, allow_nan=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(staged_name, target.name,
                   src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        try:
            os.unlink(staged_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)

def record_task(directory, key, state, scope, evidence):
    base, ideas = registries(directory)
    tasks = {**base, **ideas}
    if key not in tasks:
        raise ValueError('WORK_PROGRESS_TASK_UNKNOWN')
    if state not in STATES or (scope is not None and scope not in EVIDENCE):
        raise ValueError('WORK_PROGRESS_RECEIPT_STATE')
    if state == 'verified' and (scope != tasks[key]['evidence'] or not valid_link(evidence)):
        raise ValueError('WORK_PROGRESS_EVIDENCE_REQUIRED')
    if evidence and not valid_link(evidence):
        raise ValueError('WORK_PROGRESS_EVIDENCE_URL')
    target = directory / 'work_receipts.json'
    with receipt_writer_lock(directory):
        payload = read_receipt_payload(target)
        data = payload['tasks']
        previous = data.get(key)
        if isinstance(previous, dict) and previous.get('state') == 'verified':
            # Freeze even malformed verified receipts: a corrupt date/scope/link
            # must not turn a formerly accepted TaskID into a mutable one.
            if not is_verified(tasks[key], previous):
                raise ValueError('WORK_PROGRESS_VERIFIED_RECEIPT_REQUIRES_REVIEW')
            if state != 'verified':
                raise ValueError('WORK_PROGRESS_VERIFIED_TASK_REQUIRES_REVIEW')
            if evidence != previous['evidence']:
                raise ValueError('WORK_PROGRESS_VERIFIED_EVIDENCE_CHANGE_REQUIRES_REVIEW')
            return
        data[key] = {'state': state, 'scope': scope, 'evidence': evidence,
                     'updated_at': datetime.now(timezone.utc).isoformat()}
        payload.pop('final_acceptance', None)
        save_receipt_payload(directory, target, payload)


def record_final_acceptance(directory, scope, evidence, artifact_sha256):
    if scope != 'native' or not valid_link(evidence) or not valid_sha256(artifact_sha256):
        raise ValueError('WORK_PROGRESS_FINAL_NATIVE_EVIDENCE_REQUIRED')
    base, ideas = registries(directory)
    tasks = {**base, **ideas}
    target = directory / 'work_receipts.json'
    with receipt_writer_lock(directory):
        payload = read_receipt_payload(target)
        receipts = payload['tasks']
        if (len(tasks) != BASE_TOTAL + IDEA_TOTAL or
                any(not is_verified(task, receipts.get(key)) for key, task in tasks.items())):
            raise ValueError('WORK_PROGRESS_FINAL_TASKS_INCOMPLETE')
        if receipts[FINAL_TASK_ID]['evidence'] != evidence:
            raise ValueError('WORK_PROGRESS_FINAL_RECEIPT_MISMATCH')
        candidate = {'scope': scope, 'evidence': evidence, 'artifact_sha256': artifact_sha256,
                     'evidence_set_sha256': evidence_set_digest(tasks, receipts),
                     'updated_at': datetime.now(timezone.utc).isoformat()}
        if not final_status(tasks, receipts, candidate, True)['passed']:
            raise ValueError('WORK_PROGRESS_FINAL_RECEIPT_INVALID')
        payload['final_acceptance'] = candidate
        save_receipt_payload(directory, target, payload)


def recent_verified_changes(directory: Path, since_value: str, limit: int = 100):
    """Read-only latest receipt snapshot; never pretend it is an append-only change log."""
    from datetime import timedelta

    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('WORK_CHANGES_LIMIT')
    if since_value == 'today-msk':
        msk = timezone(timedelta(hours=3))
        since = datetime.now(msk).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        try:
            since = datetime.fromisoformat(since_value)
        except (ValueError, TypeError) as exc:
            raise ValueError('WORK_CHANGES_SINCE') from exc
        if since.utcoffset() is None:
            raise ValueError('WORK_CHANGES_SINCE_TZ_REQUIRED')
    if since.timestamp() > datetime.now(timezone.utc).timestamp() + 300:
        raise ValueError('WORK_CHANGES_FUTURE_SINCE')

    base, ideas = registries(directory)
    tasks = {**base, **ideas}
    receipts = read_receipt_payload(directory / 'work_receipts.json')['tasks']
    rows = []
    for task_id, task in tasks.items():
        receipt = receipts.get(task_id)
        if not is_verified(task, receipt):
            continue
        receipt_time = datetime.fromisoformat(receipt['updated_at'])
        if receipt_time < since:
            continue
        rows.append({'task_id': task_id, 'project': 'NOX HELION',
                     'title': task['title'], 'date': receipt_time.isoformat(),
                     'verification_scope': task['evidence'],
                     'result': 'verified_receipt', 'source_url': receipt['evidence'],
                     'experiment': None, 'metric_delta': None, 'rollback_url': None,
                     'native_live_proven': False})
    rows.sort(key=lambda row: (row['date'], row['task_id']), reverse=True)
    return {'schema': 'nox-change-receipt-snapshot-v1', 'since': since.isoformat(),
            'history_complete': False,
            'notice': ('Only latest valid TaskID receipts, not an append-only log. '
                       'No experiment, metric improvement, rollback or native LIVE is inferred.'),
            'count': min(len(rows), limit), 'truncated': len(rows) > limit,
            'changes': rows[:limit]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    verbs = parser.add_subparsers(dest='command', required=True)
    verbs.add_parser('report')
    changes = verbs.add_parser('changes')
    changes.add_argument('--since', default='today-msk', help='ISO-8601 with offset or today-msk')
    changes.add_argument('--limit', type=int, default=100)
    record = verbs.add_parser('record')
    record.add_argument('task')
    record.add_argument('state', choices=sorted(STATES))
    record.add_argument('--scope', choices=sorted(EVIDENCE))
    record.add_argument('--evidence')
    accept = verbs.add_parser('accept-final')
    accept.add_argument('--scope', choices=sorted(EVIDENCE), required=True)
    accept.add_argument('--evidence', required=True)
    accept.add_argument('--artifact-sha256', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'changes':
            output = recent_verified_changes(args.directory, args.since, args.limit)
        else:
            if args.command == 'record':
                record_task(args.directory, args.task, args.state, args.scope, args.evidence)
            elif args.command == 'accept-final':
                record_final_acceptance(args.directory, args.scope, args.evidence, args.artifact_sha256)
            output = summarize(args.directory)
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except (OSError, KeyError, ValueError, TypeError, AttributeError) as exc:
        print(json.dumps({'status': 'HOLD', 'reason': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
