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
SOURCE_ADDENDUM_SCHEMA = 'NOX_SOURCE_EVIDENCE_ADDENDUM_V1'
SOURCE_MANIFEST_PATH = 'nox-control/model_manifests/4A01_DEEPSEEK_V41_1017_TRAINING_SOURCE_20261119.json'
SOURCE_MANIFEST_BLOB = 'f3e11cfc92bb75fe7ef13589a35fb127a81fceea'
TOKENIZER_MANIFEST_PATH = 'nox-control/model_manifests/evidence/4A01_DEEPSEEK_V41_TOKENIZER_MANIFEST_20261119.json'
TOKENIZER_MANIFEST_BLOB = '7e0f848c89c3f57e0ec31f9c0c79e229d01cd81a'
GGUF_MANIFEST_PATH = 'nox-control/model_manifests/evidence/4A01_DEEPSEEK_V41_1017_GGUF_INFERENCE_ROUTE_20261119.json'
GGUF_MANIFEST_BLOB = '19684cbe1b524df8c11b7b177b5773cb2dc0cc60'
I49_POST_MERGE_SCHEMA = 'NOX_SOURCE_POST_MERGE_ACCEPTANCE_RECEIPT_V1'
I49_POST_MERGE_PATH = 'nox-control/complete_executor_20261118/evidence/addenda/i49_post_merge_acceptance_receipt_20261119_pr486.json'
I49_POST_MERGE_BLOB = 'ed36a4d374565437d8c298e2a7eeddcebec79534'
I49_WORK_IDEAS_PATH = 'nox-control/four_queue_20261118/work_ideas.json'
I49_WORK_IDEAS_BLOB = '6f84f315d9792cb43f08b72b062dc2f71ce1d4a6'
I49_SPEC_SHA256 = 'c126701e3699969ab557e9fb99f4c2085a0d678f06e11895835d89241f194e1f'
I49_TITLE = 'Сравнить тензоры двух checkpoints на CPU'
I49_CRITERION = 'Проверить разрешённые параметры выборочно, без загрузки полной модели'
I49_COMPARISON_PATH = 'nox-control/i49_checkpoint_compare_20261119/evidence/all500_tensor_delta_corrected_source_20261119.json'
I49_COMPARISON_BLOB = '4b136169a2a8fc76b64cc2001ff66ced393d18c4'
I49_COMPARISON_SHA256 = 'cde4705f5803e3a23292bd2a1026ac8bbcce08fe3758e9e62d170c203403f8b4'


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


def _validate_record_sidecar(document, task_id, spec_sha256, source_path, source_hash, source_blob):
    scope_document = document.get('scope')
    if not isinstance(scope_document, dict):
        raise ValueError('SCOPE_MISSING')
    criteria = document.get('criteria')
    if not isinstance(criteria, dict):
        criteria = scope_document.get('criteria')
    criterion = criteria.get(task_id) if isinstance(criteria, dict) else None
    if not isinstance(criterion, dict):
        raise ValueError('CRITERION_RECORD_MISSING')
    if criterion.get('spec_sha256') != spec_sha256:
        raise ValueError('CRITERION_SPEC_SHA_MISMATCH')
    if criterion.get('addendum_assessment') != 'ACCEPTED':
        raise ValueError('CRITERION_NOT_ACCEPTED')
    if criterion.get('result') not in (None, 'ACCEPTED'):
        raise ValueError('CRITERION_RESULT_NOT_ACCEPTED')
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
    record_spec = record.get('criterion_spec_sha256')
    if isinstance(record_criterion, dict):
        if record_spec is not None and record_spec != record_criterion.get('spec_sha256'):
            raise ValueError('RECORD_SPEC_FIELDS_DISAGREE')
        record_spec = record_criterion.get('spec_sha256')
    if record_spec != spec_sha256:
        raise ValueError('RECORD_SPEC_SHA_MISMATCH')

    acceptance_scope = (criterion.get('acceptance_scope')
                        or record.get('acceptance_scope')
                        or binding.get('scope_limit'))
    if not isinstance(acceptance_scope, str) or not acceptance_scope.strip():
        raise ValueError('ACCEPTANCE_SCOPE_MISSING')
    if (criterion.get('acceptance_scope') is not None
            and record.get('acceptance_scope') is not None
            and criterion['acceptance_scope'] != record['acceptance_scope']):
        raise ValueError('ACCEPTANCE_SCOPE_MISMATCH')
    evidence_pointer = record.get('evidence_pointer')
    if (criterion.get('evidence_pointer') is not None
            and criterion.get('evidence_pointer') != evidence_pointer):
        raise ValueError('CRITERION_EVIDENCE_POINTER_MISMATCH')
    evidence = _pointer_value(document, evidence_pointer)
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError('EVIDENCE_POINTER_NOT_OBJECT')

    audit = document.get('audit_binding')
    if audit is not None and not isinstance(audit, dict):
        raise ValueError('AUDIT_BINDING_INVALID')
    audit = audit if isinstance(audit, dict) else {}
    audit_workflow = audit.get('workflow') if isinstance(audit.get('workflow'), dict) else {}
    audit_request = audit.get('request') if isinstance(audit.get('request'), dict) else {}
    record_workflow = record.get('workflow') if isinstance(record.get('workflow'), dict) else {}

    run_id = binding.get('workflow_run_id', binding.get('run_id'))
    job_id = binding.get('workflow_job_id', binding.get('job_id'))
    owner_id = binding.get('owner_authorization_id',
               binding.get('owner_comment_id', binding.get('request_id')))
    if not all(_positive_int(value) for value in (run_id, job_id, owner_id)):
        raise ValueError('WORKFLOW_IDS_INVALID')
    record_run = record_workflow.get('run_id', record.get('workflow_run_id'))
    record_job = record_workflow.get('job_id', record.get('workflow_job_id'))
    record_owner = record_workflow.get(
        'owner_authorization_id',
        record_workflow.get('owner_authorization_comment_id',
        record_workflow.get('request_id',
        record.get('owner_authorization_id', record.get('owner_comment_id')))))
    evidence_binding = document.get('evidence') if task_id == '2V14-12' else evidence
    if not isinstance(evidence_binding, dict):
        raise ValueError('EVIDENCE_RUN_BINDING_MISSING')
    if task_id == '2V14-12' and evidence_binding.get('inventory') is not evidence:
        raise ValueError('GPU_INVENTORY_POINTER_MISMATCH')
    evidence_run = evidence_binding.get('workflow_run_id')
    evidence_job = evidence_binding.get('workflow_job_id', evidence_binding.get('job_id'))
    evidence_owner = evidence_binding.get(
        'owner_authorization_id',
        evidence_binding.get('owner_authorization_comment_id', evidence_binding.get('owner_comment_id')))
    if (record_run != run_id or record_job != job_id or record_owner != owner_id
            or evidence_run != run_id or evidence_job != job_id or evidence_owner != owner_id):
        raise ValueError('WORKFLOW_EVIDENCE_BINDING_MISMATCH')

    audit_run = audit_workflow.get('run_id')
    audit_job = audit_workflow.get('job_id')
    request_owner = audit_request.get('owner_authorization_id',
                    audit_request.get('github_issue_comment_id'))
    if audit_workflow or audit_request:
        if audit_run != run_id or audit_job != job_id or request_owner != owner_id:
            raise ValueError('AUDIT_BINDING_RUN_OR_OWNER_MISMATCH')
    run_url = 'https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/%d' % run_id
    job_url = run_url + '/job/' + str(job_id)
    for row in (binding, record_workflow, record, evidence_binding, audit_workflow):
        if row.get('run_url') is not None and row.get('run_url') != run_url:
            raise ValueError('WORKFLOW_RUN_URL_MISMATCH')
        if row.get('job_url') is not None and row.get('job_url') != job_url:
            raise ValueError('WORKFLOW_JOB_URL_MISMATCH')

    source_blobs = record.get('source_artifact_blobs')
    if source_blobs is not None:
        if not isinstance(source_blobs, dict):
            raise ValueError('SOURCE_ARTIFACT_BLOBS_INVALID')
        evidence_blobs = evidence.get('source_artifact_blobs')
        audit_evidence = _pointer_value(document, '#/audit_evidence/point_in_time_census')
        audit_blobs = audit_evidence.get('source_artifact_blobs') if isinstance(audit_evidence, dict) else None
        if (source_blobs.get('task_registry') != FROZEN_WORK_TASKS_BLOB
                or source_blobs.get('all295_manifest') != FROZEN_295_MANIFEST_BLOB
                or source_blobs.get('work_receipts') != FROZEN_WORK_RECEIPTS_BLOB
                or not isinstance(evidence_blobs, dict) or source_blobs != evidence_blobs
                or not isinstance(audit_blobs, dict) or source_blobs != audit_blobs):
            raise ValueError('SOURCE_ARTIFACT_BLOB_BINDING_MISMATCH')
        pinned = audit.get('pinned_audit_source')
        host = audit.get('host')
        remote = audit.get('remote_execution')
        transfer = audit.get('transfer_bundle')
        if not all(isinstance(row, dict) for row in (pinned, host, remote, transfer)):
            raise ValueError('AUDIT_PROVENANCE_BINDING_MISSING')
        census_pointer = evidence.get('process_census_pointer')
        if census_pointer != '#/process_census':
            raise ValueError('PROCESS_CENSUS_POINTER_MISMATCH')
        census_for_hash = _pointer_value(document, census_pointer)
        if (record.get('audit_pin_commit_sha') != pinned.get('audit_pin_commit_sha')
                or record.get('source_head_sha') != audit_workflow.get('run_head_sha')
                or source_blobs.get('workflow') != audit_workflow.get('workflow_file_blob_sha')
                or source_blobs.get('owner_guard') != pinned.get('owner_guard_blob_sha')
                or source_blobs.get('operator_source') != pinned.get('operator_source_blob_sha')
                or source_blobs.get('audit_source') != pinned.get('audit_source_blob_sha')
                or source_blobs.get('transfer_bundle') != transfer.get('sha256')
                or source_blobs.get('process_rows') != census_for_hash.get('process_rows_sha256')
                or host.get('host_pin_verified') is not True
                or not transfer.get('request_and_source_binding_verified')
                or not transfer.get('reassembly_verified')
                or remote.get('remote_exit_code') != 0):
            raise ValueError('AUDIT_PROVENANCE_MISMATCH')
        if not _hex_digest(source_blobs.get('workflow'), 40):
            raise ValueError('WORKFLOW_SOURCE_BLOB_INVALID')
        if evidence.get('overall_audit') != document.get('overall_audit'):
            raise ValueError('AUDIT_RESULT_BINDING_MISMATCH')

    if task_id == '2V14-12':
        inventory = evidence
        if (evidence_binding.get('source_auth') != 'PASS'
                or evidence_binding.get('workflow_run_conclusion') != 'success'
                or evidence_binding.get('inventory_complete') is not True
                or evidence_binding.get('temporary_ssh_key_cleanup') != 'DETACHED_AND_VERIFIED'
                or not isinstance(inventory, dict)
                or inventory.get('schema') != 'NOX_GPU_INVENTORY_V1'
                or inventory.get('identity_stable') is not True):
            raise ValueError('GPU_INVENTORY_ACCEPTANCE_EVIDENCE_INVALID')
        snapshots = inventory.get('snapshots')
        if not isinstance(snapshots, list) or len(snapshots) < 2:
            raise ValueError('GPU_INVENTORY_SNAPSHOTS_MISSING')
        reference = None
        for snapshot in snapshots:
            rows = snapshot.get('rows') if isinstance(snapshot, dict) else None
            if (not isinstance(snapshot, dict) or snapshot.get('nvidia_smi_rc') != 0
                    or not isinstance(rows, list) or len(rows) != 2):
                raise ValueError('GPU_INVENTORY_SNAPSHOT_INVALID')
            identity = []
            for gpu in rows:
                if (not isinstance(gpu, dict) or gpu.get('model') != 'Tesla V100-SXM2-32GB'
                        or not isinstance(gpu.get('uuid'), str)
                        or type(gpu.get('memory_free_mib')) is not int
                        or gpu.get('memory_free_mib') <= 0):
                    raise ValueError('GPU_INVENTORY_DEVICE_INVALID')
                identity.append((gpu['uuid'], gpu['model']))
            if len({row[0] for row in identity}) != 2:
                raise ValueError('GPU_UUIDS_NOT_DISTINCT')
            if reference is not None and identity != reference:
                raise ValueError('GPU_IDENTITIES_NOT_STABLE')
            reference = identity
        checks = inventory.get('computed_checks')
        if (not isinstance(checks, dict)
                or checks.get('distinct_uuid_count') != 2
                or checks.get('stable_uuids_across_snapshots') is not True
                or checks.get('all_nvidia_smi_calls_successful') is not True
                or checks.get('positive_free_memory_both_devices') is not True
                or not _hex_digest(evidence_binding.get('inventory_sha256'))
                or record_workflow.get('inventory_sha256') != evidence_binding.get('inventory_sha256')
                or record_workflow.get('pinned_source_sha') != evidence_binding.get('pinned_source_sha')
                or binding.get('pinned_source_sha') != evidence_binding.get('pinned_source_sha')
                or evidence_binding.get('request_id') != owner_id):
            raise ValueError('GPU_INVENTORY_CHECKS_INVALID')
        conclusion = record_workflow.get('conclusion')
        result_status = evidence_binding.get('workflow_run_conclusion')
        if conclusion != 'success' or result_status != 'success':
            raise ValueError('GPU_WORKFLOW_STATUS_NOT_SUCCESS')
    elif task_id == '6V14-02':
        if acceptance_scope != 'POINT_IN_TIME_PROCESS_SET_ENUMERATION_AND_CORE_IDENTITY_ONLY':
            raise ValueError('PROCESS_CENSUS_SCOPE_UNSUPPORTED')
        census_pointer = evidence.get('process_census_pointer')
        if census_pointer != '#/process_census':
            raise ValueError('PROCESS_CENSUS_POINTER_MISMATCH')
        census = _pointer_value(document, census_pointer)
        if not isinstance(census, dict):
            raise ValueError('PROCESS_CENSUS_EVIDENCE_MISSING')
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
            raise ValueError('PROCESS_CENSUS_CORE_CRITERION_NOT_MET')
        remote = audit.get('remote_execution')
        if (not isinstance(remote, dict)
                or evidence.get('overall_audit') != 'HOLD'
                or document.get('overall_audit') != 'HOLD'
                or remote.get('workflow_result') != 'HOLD_AUDIT_CENSUS_INCOMPLETE'):
            raise ValueError('PROCESS_CENSUS_OVERALL_STATUS_MISMATCH')
        conclusion = audit_workflow.get('job_conclusion')
        result_status = remote.get('workflow_result')
        if conclusion != 'failure' or result_status != 'HOLD_AUDIT_CENSUS_INCOMPLETE':
            raise ValueError('PROCESS_CENSUS_WORKFLOW_STATUS_MISMATCH')
    else:
        raise ValueError('TASK_ACCEPTANCE_VARIANT_UNSUPPORTED')

    if (criterion.get('acceptance_increment') not in (None, 0)
            or record.get('acceptance_increment') not in (None, 0)
            or record.get('original_all295_ledger_updated') not in (None, False)):
        raise ValueError('ORIGINAL_LEDGER_MUTATION_CLAIM')
    if task_id == '6V14-02' and document.get('overall_audit') != 'HOLD':
        raise ValueError('PROCESS_CENSUS_OVERALL_STATUS_MISMATCH')
    task_criterion = scope_document.get('task_criterion')
    if not isinstance(task_criterion, dict):
        task_criterion = {}
    task_registry = task_criterion.get('task_registry')
    if not isinstance(task_registry, dict):
        task_registry = {}
    return {
        'task_id': task_id,
        'title': criterion.get('title') or record.get('title')
                 or task_criterion.get('task_title') or task_registry.get('task_title'),
        'result': 'ACCEPTED',
        'acceptance_scope': acceptance_scope,
        'acceptance_pointer': pointer,
        'evidence_pointer': evidence_pointer,
        'run_binding_pointer': '#/criteria/%s/acceptance_binding' % task_id,
        'workflow_run_id': run_id,
        'job_id': job_id,
        'owner_authorization_id': owner_id,
        'workflow_conclusion': conclusion,
        'evidence_result': result_status,
        'spec_sha256': spec_sha256,
        'record_number': record.get('record_number'),
        'source_path': source_path,
        'source_url': REPOSITORY_URL + '/blob/' + REPOSITORY_REF + '/' + source_path,
        'source_sha256': source_hash,
        'source_git_blob_sha': source_blob,
    }


def _control_file_path(control_root, repository_path):
    prefix = 'nox-control/'
    if not isinstance(repository_path, str) or not repository_path.startswith(prefix):
        raise ValueError('SOURCE_PATH_OUTSIDE_NOX_CONTROL')
    relative = Path(repository_path[len(prefix):])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('SOURCE_PATH_TRAVERSAL')
    return Path(control_root) / relative


MAX_TOKENIZER_ASSET_BYTES = 8 * 1024 * 1024


def _hash_regular_file(path, expected_size, max_size):
    """Hash a bounded regular file twice through a no-follow descriptor."""
    path = Path(path)
    if (type(expected_size) is not int or expected_size <= 0
            or type(max_size) is not int or not expected_size <= max_size
            or max_size > 16 * 1024 * 1024):
        raise ValueError('SOURCE_ASSET_SIZE_INVALID')
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError('SOURCE_ASSET_UNSAFE_PARENT')
    fd = _open_registry_no_follow(
        path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    )
    try:
        before = os.fstat(fd)
        on_path = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size != expected_size
                or _file_identity(before) != _file_identity(on_path)):
            raise ValueError('SOURCE_ASSET_UNSAFE_FILE')
        def digest_pass():
            os.lseek(fd, 0, os.SEEK_SET)
            sha256 = hashlib.sha256()
            blob_sha1 = hashlib.sha1(
                b'blob ' + str(expected_size).encode('ascii') + b'\0'
            )
            remaining = expected_size
            while remaining:
                chunk = os.read(fd, min(131072, remaining))
                if not chunk:
                    raise ValueError('SOURCE_ASSET_SIZE_CHANGED')
                remaining -= len(chunk)
                sha256.update(chunk)
                blob_sha1.update(chunk)
            if os.read(fd, 1):
                raise ValueError('SOURCE_ASSET_SIZE_CHANGED')
            return sha256.hexdigest(), blob_sha1.hexdigest()
        first = digest_pass()
        second = digest_pass()
        after = os.fstat(fd)
        final_path = path.lstat()
        if (first != second or _file_identity(before) != _file_identity(after)
                or _file_identity(after) != _file_identity(final_path)
                or any(parent.is_symlink() for parent in path.parents)):
            raise ValueError('SOURCE_ASSET_CHANGED_DURING_READ')
        return expected_size, first[0], first[1]
    finally:
        os.close(fd)


def _validate_source_sidecar(document, manifest_rows, manifest_titles, control_root,
                             source_path, source_hash, source_blob):
    task = document.get('task')
    if not isinstance(task, dict):
        raise ValueError('SOURCE_TASK_BINDING_MISSING')
    task_id = task.get('task_id')
    if task_id != '4A01' or task_id not in manifest_rows:
        raise ValueError('SOURCE_TASK_ID_UNSUPPORTED')
    spec_sha = manifest_rows[task_id]
    if task.get('spec_sha256') != spec_sha:
        raise ValueError('SOURCE_TASK_SPEC_SHA_MISMATCH')
    if task.get('title') != manifest_titles.get(task_id) or task.get('required_evidence') != 'source':
        raise ValueError('SOURCE_TASK_TITLE_OR_EVIDENCE_MISMATCH')
    if (document.get('state') != 'SOURCE_CRITERION_COMPLETE'
            or document.get('accepted_source_criterion') is not True):
        raise ValueError('SOURCE_CRITERION_NOT_ACCEPTED')
    if document.get('original_295_acceptance_increment') != 1:
        raise ValueError('SOURCE_SUPPLEMENTAL_INCREMENT_CLAIM_INVALID')
    if (document.get('frozen_registry_mutation') is not False
            or document.get('work_receipts_mutation') is not False
            or document.get('live_training_or_weight_update') is not False
            or document.get('training_admission') != 'HOLD'):
        raise ValueError('SOURCE_MUTATION_OR_ADMISSION_BOUNDARY_INVALID')

    frozen = document.get('frozen_inputs')
    if not isinstance(frozen, dict):
        raise ValueError('SOURCE_FROZEN_INPUTS_MISSING')
    expected_inputs = {
        'all295_execution_disposition': (
            'nox-control/complete_executor_20261118/evidence/all295_execution_disposition.json',
            FROZEN_295_MANIFEST_BLOB),
        'work_tasks': (
            'nox-control/four_queue_20261118/work_tasks.json',
            FROZEN_WORK_TASKS_BLOB),
        'work_receipts': (
            'nox-control/four_queue_20261118/work_receipts.json',
            FROZEN_WORK_RECEIPTS_BLOB),
    }
    for key, (expected_path, expected_blob) in expected_inputs.items():
        row = frozen.get(key)
        if (not isinstance(row, dict) or row.get('path') != expected_path
                or row.get('git_blob_sha') != expected_blob or row.get('mutated') is not False):
            raise ValueError('SOURCE_FROZEN_INPUT_BINDING_MISMATCH_'+key)

    if document.get('exact_manifest_path') != SOURCE_MANIFEST_PATH:
        raise ValueError('SOURCE_EXACT_MANIFEST_PATH_MISMATCH')
    source_manifest_raw, source_manifest = read_json_with_raw(
        _control_file_path(control_root, SOURCE_MANIFEST_PATH)
    )
    acceptance = source_manifest.get('acceptance')
    tokenizer = source_manifest.get('tokenizer')
    target = source_manifest.get('canonical_target')
    if (git_blob_sha(source_manifest_raw) != SOURCE_MANIFEST_BLOB
            or source_manifest.get('schema') != 'NOX_MODEL_SOURCE_MANIFEST_V1'
            or source_manifest.get('task_id') != task_id
            or source_manifest.get('task_spec_sha256') != spec_sha
            or source_manifest.get('source_status') != 'SOURCE_CRITERION_COMPLETE'
            or source_manifest.get('training_admission') != 'HOLD'
            or not isinstance(acceptance, dict)
            or acceptance.get('accepted_source_criterion') is not True
            or not isinstance(tokenizer, dict)
            or not isinstance(target, dict)):
        raise ValueError('SOURCE_MODEL_MANIFEST_BINDING_MISMATCH')

    tokenizer_manifest_path = document.get('tokenizer_asset_manifest_path')
    if tokenizer_manifest_path != TOKENIZER_MANIFEST_PATH:
        raise ValueError('TOKENIZER_MANIFEST_PATH_MISMATCH')
    tokenizer_manifest_raw, tokenizer_manifest = read_json_with_raw(
        _control_file_path(control_root, tokenizer_manifest_path)
    )
    if (git_blob_sha(tokenizer_manifest_raw) != TOKENIZER_MANIFEST_BLOB
            or tokenizer_manifest.get('schema') != 'NOX_TOKENIZER_ASSET_MANIFEST_V1'
            or tokenizer_manifest.get('task_id') != task_id
            or tokenizer_manifest.get('model_revision') != target.get('model_revision')
            or tokenizer_manifest.get('tokenizer_revision') != tokenizer.get('source_revision')
            or tokenizer_manifest.get('path') != tokenizer.get('source_path')
            or tokenizer_manifest.get('local_path') != tokenizer.get('local_path')
            or tokenizer_manifest.get('sha256') != tokenizer.get('sha256')
            or tokenizer_manifest.get('source_git_blob_sha1') != tokenizer.get('source_git_blob_sha1')
            or tokenizer_manifest.get('size_bytes') != tokenizer.get('size_bytes')):
        raise ValueError('TOKENIZER_ASSET_MANIFEST_BINDING_MISMATCH')
    asset_path = tokenizer.get('local_path')
    if asset_path != 'nox-control/model_manifests/evidence/assets/deepseek_v41_1017/tokenizer.json':
        raise ValueError('TOKENIZER_ASSET_PATH_MISMATCH')
    declared_size = tokenizer.get('size_bytes')
    declared_sha256 = tokenizer.get('sha256')
    declared_blob_sha1 = tokenizer.get('source_git_blob_sha1')
    if (not _hex_digest(declared_sha256)
            or not _hex_digest(declared_blob_sha1, 40)):
        raise ValueError('TOKENIZER_ASSET_HASH_INVALID')
    actual_size, actual_sha256, actual_blob_sha1 = _hash_regular_file(
        _control_file_path(control_root, asset_path), declared_size,
        MAX_TOKENIZER_ASSET_BYTES
    )
    if (actual_size != declared_size or actual_sha256 != declared_sha256
            or actual_blob_sha1 != declared_blob_sha1):
        raise ValueError('TOKENIZER_ASSET_FILE_BINDING_MISMATCH')

    gguf_path = document.get('gguf_inference_route_manifest_path')
    if (gguf_path != GGUF_MANIFEST_PATH
            or source_manifest.get('gguf_inference_route_manifest_path') != GGUF_MANIFEST_PATH):
        raise ValueError('GGUF_MANIFEST_PATH_MISMATCH')
    gguf_raw, gguf_manifest = read_json_with_raw(_control_file_path(control_root, gguf_path))
    sidecar_gguf = document.get('gguf_inference_boundary')
    if (git_blob_sha(gguf_raw) != GGUF_MANIFEST_BLOB
            or gguf_manifest.get('schema') != 'NOX_GGUF_INFERENCE_ROUTE_MANIFEST_V1'
            or gguf_manifest.get('task_id') != task_id
            or gguf_manifest.get('task_spec_sha256') != spec_sha
            or not isinstance(sidecar_gguf, dict)
            or sidecar_gguf.get('schema') != 'NOX_GGUF_INFERENCE_ROUTE_MANIFEST_V1'
            or sidecar_gguf.get('task_id') != task_id
            or sidecar_gguf.get('task_spec_sha256') != spec_sha
            or sidecar_gguf.get('status') != gguf_manifest.get('status')
            or gguf_manifest.get('status') != 'SOURCE_PINNED_INFERENCE_ONLY_WEIGHTS_NOT_DOWNLOADED_RUNTIME_UNVERIFIED'):
        raise ValueError('GGUF_INFERENCE_BOUNDARY_MISMATCH')
    sources = document.get('sources')
    if not isinstance(sources, list) or len(sources) < 3 or any(not isinstance(row, dict) for row in sources):
        raise ValueError('SOURCE_REFERENCE_LIST_INVALID')

    return {
        'task_id': task_id,
        'title': task.get('title'),
        'result': 'ACCEPTED',
        'evidence_kind': 'SOURCE_CRITERION',
        'acceptance_scope': 'Source criterion complete; training admission and runtime remain on HOLD.',
        'acceptance_pointer': '#/accepted_source_criterion',
        'evidence_pointer': '#/exact_manifest_path',
        'source_references_pointer': '#/sources',
        'run_binding_pointer': None,
        'workflow_run_id': None,
        'job_id': None,
        'owner_authorization_id': None,
        'workflow_conclusion': None,
        'evidence_result': document.get('state'),
        'spec_sha256': spec_sha,
        'record_number': document.get('receipt_id'),
        'source_path': source_path,
        'source_url': REPOSITORY_URL + '/blob/' + REPOSITORY_REF + '/' + source_path,
        'source_sha256': source_hash,
        'source_git_blob_sha': source_blob,
        'source_manifest_path': SOURCE_MANIFEST_PATH,
        'source_manifest_git_blob_sha': git_blob_sha(source_manifest_raw),
        'tokenizer_manifest_path': tokenizer_manifest_path,
        'tokenizer_manifest_git_blob_sha': git_blob_sha(tokenizer_manifest_raw),
        'gguf_manifest_path': gguf_path,
        'gguf_manifest_git_blob_sha': git_blob_sha(gguf_raw),
        'source_claimed_original_295_acceptance_increment': document['original_295_acceptance_increment'],
        'original_acceptance_added': 0,
        'training_admission': document.get('training_admission'),
        'live_training_or_weight_update': document.get('live_training_or_weight_update'),
    }


def _validate_i49_post_merge_receipt(document, manifest_rows, manifest_titles,
                                      manifest_records, control_root,
                                      source_path, source_hash, source_blob):
    """Validate the exact post-merge I-49 source receipt as a 295 supplemental item."""
    task = document.get('task')
    if not isinstance(task, dict) or task.get('task_id') != 'I-49':
        raise ValueError('I49_TASK_BINDING_MISMATCH')
    if (task.get('spec_sha256') != I49_SPEC_SHA256
            or manifest_rows.get('I-49') != I49_SPEC_SHA256
            or task.get('title') != I49_TITLE
            or manifest_titles.get('I-49') != I49_TITLE):
        raise ValueError('I49_FROZEN_SPEC_BINDING_MISMATCH')
    frozen_row = manifest_records.get('I-49')
    routing = frozen_row.get('routing_source') if isinstance(frozen_row, dict) else None
    if (not isinstance(frozen_row, dict)
            or frozen_row.get('original_acceptance_added') is not False
            or frozen_row.get('prior_receipt_state') != 'verified'
            or frozen_row.get('prior_receipt_scope') != 'source'
            or not isinstance(routing, dict)
            or routing.get('registry') != 'work_ideas.json'
            or routing.get('native_binding') != 'UNBOUND_PENDING_NATIVE_CATALOG'):
        raise ValueError('I49_FROZEN_ROW_ROUTING_MISMATCH')
    if (document.get('schema') != I49_POST_MERGE_SCHEMA
            or document.get('append_only') is not True
            or source_path != I49_POST_MERGE_PATH
            or source_blob != I49_POST_MERGE_BLOB):
        raise ValueError('I49_POST_MERGE_RECEIPT_PIN_MISMATCH')

    ideas_raw, ideas_doc = read_json_with_raw(
        Path(control_root) / 'four_queue_20261118' / 'work_ideas.json'
    )
    idea_rows = ideas_doc.get('ideas') if isinstance(ideas_doc, dict) else None
    if (git_blob_sha(ideas_raw) != I49_WORK_IDEAS_BLOB
            or ideas_doc.get('schema') != 'nox-work-ideas-v1'
            or not isinstance(idea_rows, list)
            or len(idea_rows) != IDEA_TOTAL):
        raise ValueError('I49_WORK_IDEAS_REGISTRY_PIN_MISMATCH')
    matches = [row for row in idea_rows
               if isinstance(row, dict) and row.get('id') == 'I-49']
    if (len(matches) != 1 or matches[0].get('title') != I49_TITLE
            or matches[0].get('evidence') != 'source'
            or matches[0].get('acceptance') != I49_CRITERION):
        raise ValueError('I49_WORK_IDEA_ROW_MISMATCH')

    if (task.get('required_evidence') != 'source'
            or task.get('criterion') != I49_CRITERION
            or task.get('work_ideas_path') != I49_WORK_IDEAS_PATH
            or task.get('work_ideas_git_blob_sha') != I49_WORK_IDEAS_BLOB
            or task.get('all295_path') != 'nox-control/complete_executor_20261118/evidence/all295_execution_disposition.json'
            or task.get('all295_git_blob_sha') != FROZEN_295_MANIFEST_BLOB
            or task.get('work_receipts_path') != 'nox-control/four_queue_20261118/work_receipts.json'
            or task.get('work_receipts_git_blob_sha') != FROZEN_WORK_RECEIPTS_BLOB
            or task.get('frozen_files_mutated') is not False):
        raise ValueError('I49_SOURCE_RECEIPT_TASK_BINDING_MISMATCH')

    merge = document.get('merge_binding')
    if (not isinstance(merge, dict)
            or merge.get('pull_request_number') != 486
            or merge.get('pull_request_url') != REPOSITORY_URL + '/pull/486'
            or merge.get('state') != 'MERGED'
            or merge.get('merged_head_sha') != 'a5a999e2705a242d266030ac0b09c29bb215e805'
            or merge.get('merge_commit_sha') != '4193544b6b7fe4db82d64ef18fc33cc3bc5649ce'
            or merge.get('base_branch') != REPOSITORY_REF):
        raise ValueError('I49_MERGE_BINDING_MISMATCH')
    review = document.get('independent_review')
    if (not isinstance(review, dict) or review.get('result') != 'PASS'
            or review.get('reviewed_head_sha') != merge.get('merged_head_sha')):
        raise ValueError('I49_INDEPENDENT_REVIEW_BINDING_MISMATCH')

    assessment = document.get('assessment')
    mutation = document.get('mutation_boundary')
    if (not isinstance(assessment, dict)
            or assessment.get('status') != 'ACCEPTED_SOURCE_CRITERION'
            or assessment.get('accepted_scope') != (
                'Only the frozen I-49 source criterion: bounded CPU payload-byte hash comparison '
                'for the currently authorized exact checkpoint pair and exact 500-name set without '
                'loading the full base model.')
            or assessment.get('acceptance_claim_for_immutable_295_snapshot') is not False
            or not isinstance(mutation, dict)
            or mutation.get('all295_changed') is not False
            or mutation.get('work_ideas_changed') is not False
            or mutation.get('work_receipts_changed') is not False
            or mutation.get('drive_changed') is not False
            or mutation.get('server_changed') is not False):
        raise ValueError('I49_ACCEPTANCE_OR_MUTATION_BOUNDARY_MISMATCH')

    evidence = document.get('evidence')
    comparison_receipt = evidence.get('corrected_comparison') if isinstance(evidence, dict) else None
    if (not isinstance(comparison_receipt, dict)
            or comparison_receipt.get('path') != I49_COMPARISON_PATH
            or comparison_receipt.get('git_blob_sha') != I49_COMPARISON_BLOB
            or comparison_receipt.get('content_sha256') != I49_COMPARISON_SHA256):
        raise ValueError('I49_COMPARISON_POINTER_MISMATCH')
    artifact_raw, artifact = read_json_with_raw(
        Path(control_root) / 'i49_checkpoint_compare_20261119' / 'evidence' /
        'all500_tensor_delta_corrected_source_20261119.json'
    )
    artifact_hash = hashlib.sha256(artifact_raw).hexdigest()
    comparator = comparison_receipt.get('comparator')
    artifact_comparator = artifact.get('comparator') if isinstance(artifact, dict) else None
    pair = comparison_receipt.get('pair')
    artifact_sources = artifact.get('sources') if isinstance(artifact, dict) else None
    if (git_blob_sha(artifact_raw) != I49_COMPARISON_BLOB
            or artifact_hash != I49_COMPARISON_SHA256
            or artifact.get('schema') != 'NOX_I49_ALL_SHARED_TENSORS_CPU_DELTA_V2'
            or artifact.get('task_id') != 'I-49'
            or artifact.get('training_started') is not False
            or artifact.get('full_base_model_loaded') is not False
            or artifact.get('drive_written') is not False
            or artifact.get('server_written') is not False
            or not isinstance(comparator, dict) or not isinstance(artifact_comparator, dict)
            or comparator.get('revision') != 'e10c80f64e3fd88298be2776c58d03939e6e71f6'
            or comparator.get('source_sha256') != 'f71ed5466efed6fe70a19c222df9dc7c97a1a44e5bee82b4747d099c7f65abf0'
            or comparator.get('git_blob_sha') != '93a5963b0951a38c00438ced561b1077fd8bf7ca'
            or comparator != artifact_comparator
            or not isinstance(pair, dict)
            or pair.get('pair_sha256') != '1df59f1bd9fc4712b8ba01c429af5aa19895ea9ed907d1f807b99b9195a87bd1'
            or not isinstance(artifact_sources, list) or len(artifact_sources) != 2):
        raise ValueError('I49_COMPARISON_ARTIFACT_BINDING_MISMATCH')
    names = artifact.get('tensor_name_set')
    summary = artifact.get('summary')
    if (not isinstance(names, dict) or names.get('count') != 500
            or names.get('sorted_names_sha256') != 'd0baf44eff8da1fd86afaf812900b0f7ee273d7286a20f49de0237f4689ac7da'
            or names.get('matches_current_owner_instruction_binding') is not True
            or not isinstance(summary, dict)
            or summary.get('common_tensor_count') != 500
            or summary.get('compared_tensor_count') != 500
            or summary.get('changed_tensor_count') != 500
            or summary.get('unchanged_tensor_count') != 0
            or summary.get('all_matching_tensors_compared') is not True):
        raise ValueError('I49_COMPARISON_SCOPE_NOT_MET')
    if (comparison_receipt.get('tensor_name_count') != 500
            or comparison_receipt.get('tensor_name_set_sha256') != names.get('sorted_names_sha256')
            or comparison_receipt.get('compared_tensors') != summary.get('compared_tensor_count')
            or comparison_receipt.get('changed_payload_hashes') != summary.get('changed_tensor_count')
            or comparison_receipt.get('comparison_issues') != 0
            or comparison_receipt.get('training_started') is not False
            or comparison_receipt.get('full_base_model_loaded') is not False
            or comparison_receipt.get('drive_written') is not False
            or comparison_receipt.get('server_written') is not False):
        raise ValueError('I49_COMPARISON_RESULT_BINDING_MISMATCH')
    if not isinstance(document.get('merged_premerge_acceptance_sidecar'), dict):
        raise ValueError('I49_PREMERGE_SIDECAR_BINDING_MISSING')
    previous = document['merged_premerge_acceptance_sidecar']
    if (previous.get('path') != 'nox-control/complete_executor_20261118/evidence/addenda/source_acceptance_addendum_20261119_i49_corrected.json'
            or previous.get('git_blob_sha') != '564fa0dd1e578e46338a0c1476f09ec63150627d'
            or previous.get('recorded_premerge_effective_state') != 'PENDING_PR_MERGE'):
        raise ValueError('I49_PREMERGE_SIDECAR_BINDING_MISMATCH')

    return {
        'task_id': 'I-49',
        'title': I49_TITLE,
        'result': 'ACCEPTED',
        'evidence_kind': 'SOURCE_POST_MERGE',
        'acceptance_scope': assessment['accepted_scope'],
        'acceptance_pointer': '#/assessment/status',
        'evidence_pointer': '#/evidence/corrected_comparison',
        'merge_binding_pointer': '#/merge_binding',
        'review_binding_pointer': '#/independent_review',
        'workflow_run_id': None,
        'job_id': None,
        'owner_authorization_id': None,
        'merge_commit_sha': merge['merge_commit_sha'],
        'merged_head_sha': merge['merged_head_sha'],
        'spec_sha256': I49_SPEC_SHA256,
        'source_path': source_path,
        'source_url': REPOSITORY_URL + '/blob/' + REPOSITORY_REF + '/' + source_path,
        'source_sha256': source_hash,
        'source_git_blob_sha': source_blob,
        'work_ideas_path': I49_WORK_IDEAS_PATH,
        'work_ideas_git_blob_sha': git_blob_sha(ideas_raw),
        'comparison_path': I49_COMPARISON_PATH,
        'comparison_git_blob_sha': git_blob_sha(artifact_raw),
        'comparison_sha256': artifact_hash,
        'comparator_revision': comparator['revision'],
        'pair_sha256': pair['pair_sha256'],
        'tensor_name_count': names['count'],
        'tensor_name_set_sha256': names['sorted_names_sha256'],
        'original_acceptance_added': 0,
        'training_started': False,
        'full_base_model_loaded': False,
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
        manifest_titles = {}
        manifest_records = {}
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
            manifest_titles[task_id] = row['spec'].get('title')
            manifest_records[task_id] = row
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
        try:
            with os.scandir(dir_fd) as entries:
                names = sorted(entry.name for entry in entries if entry.name.endswith('.json'))
        finally:
            os.close(dir_fd)
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
            if document.get('append_only') is not True:
                raise ValueError('ADDENDUM_NOT_APPEND_ONLY')
            if document.get('schema') == I49_POST_MERGE_SCHEMA:
                source_task = document.get('task')
                source_task_id = source_task.get('task_id') if isinstance(source_task, dict) else None
                try:
                    if source_path != I49_POST_MERGE_PATH:
                        raise ValueError('I49_POST_MERGE_PATH_MISMATCH')
                    item = _validate_i49_post_merge_receipt(
                        document, manifest_rows, manifest_titles, manifest_records,
                        directory.parent, source_path, source_hash, git_blob_sha(raw)
                    )
                    items.append(item)
                except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
                    excluded.append({'path': source_path, 'task_id': source_task_id, 'reason': str(exc)})
                continue
            if document.get('schema') == SOURCE_ADDENDUM_SCHEMA:
                source_task = document.get('task')
                source_task_id = source_task.get('task_id') if isinstance(source_task, dict) else None
                try:
                    item = _validate_source_sidecar(
                        document, manifest_rows, manifest_titles, directory.parent,
                        source_path, source_hash, git_blob_sha(raw)
                    )
                    items.append(item)
                except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
                    excluded.append({'path': source_path, 'task_id': source_task_id, 'reason': str(exc)})
                continue
            if document.get('schema') != SIDECAR_SCHEMA:
                raise ValueError('UNSUPPORTED_ADDENDUM_SCHEMA')
            declared = document.get('scope', {}).get('task_ids') if isinstance(document.get('scope'), dict) else None
            if not isinstance(declared, list) or not declared:
                raise ValueError('ADDENDUM_TASK_IDS_MISSING')
            accepted_claims = set()
            scope_document = document.get('scope')
            criteria = document.get('criteria')
            if not isinstance(criteria, dict) and isinstance(scope_document, dict):
                criteria = scope_document.get('criteria')
            if isinstance(criteria, dict):
                accepted_claims.update(
                    task_id for task_id, row in criteria.items()
                    if isinstance(row, dict)
                    and row.get('addendum_assessment') == 'ACCEPTED'
                    and row.get('result', 'ACCEPTED') == 'ACCEPTED'
                )
            for task_id in sorted(set(declared)):
                if task_id not in accepted_claims:
                    continue
                try:
                    if task_id not in manifest_rows:
                        raise ValueError('TASK_ID_NOT_IN_FROZEN_295')
                    spec_sha = manifest_rows[task_id]
                    _sidecar_refs(document, task_id, spec_sha)
                    if not isinstance(criteria, dict) or task_id not in criteria:
                        raise ValueError('SUPPORTED_ACCEPTANCE_BINDING_MISSING')
                    item = _validate_record_sidecar(
                        document, task_id, spec_sha, source_path, source_hash, git_blob_sha(raw)
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
                'original_acceptance_added': 0,
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
            'original_acceptance_added': 0,
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
