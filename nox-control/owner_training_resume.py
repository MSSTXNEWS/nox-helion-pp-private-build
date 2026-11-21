#!/usr/bin/env python3
"""Admit the hybrid trainer after verified BOOST, lifecycle and S03 activation.

Executed only by the pinned owner operator. The BOOST policy stays enabled;
heavy legacy writers and teachers remain paused. Five bounded training steps,
verified optimizer updates and seven independently hashed checkpoint files precede continuation of that same
optimizer lineage. A bounded observation timeout never kills healthy training.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
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
SERVICE = 'nox-train-volta-t866u'
ENTRY = ROOT / 'scripts/hybrid_training_entry.py'
WRAPPER = ROOT / 'scripts/run_train_volta_t866u.sh'
TRAINER = ROOT / 'scripts/train_qlora_35b_t866u.py'
OUTPUT = ROOT / 'lora/qlora_t866u/runs_owner_hybrid'
BOOST_REQUEST = '6903121842'
BOOST_SOURCE = '3b964f6c9861ca89437aa158b912dc9686e99cb6'
# Filled only from the owner's successful, pinned native upgrade receipt.
# An unpublished or unsuccessful upgrade is never an alternate admission path.
DISPATCHER_UPGRADE_REQUEST = '6904167779'
DISPATCHER_UPGRADE_SOURCE = 'a7059f0deff8c6236a1b8ba72cb81f1ba3d14af0'
DISPATCHER_UPGRADE_SHA = 'd4e665915ae2a9f0be8ae4603be3768467e0f88be876e408465c3a7cc156c243'
# Populated from the successful native semantic activation and content reindex.
S03_ACTIVATION_REQUEST = '6905063285'
S03_ACTIVATION_SOURCE = '432b6195e7a8e3e56b32b9abcfd258dfc21465ec'
S03_ACTIVATION_RECEIPT_SHA = '22b5e72e80a62c29ac4bf1f730adc102e86aaf43a59d3fa69d6fe4f6717e5d86'
S03_PREPARE_REQUEST = '6904379098'
S03_PREPARE_RECEIPT_SHA = 'f6be4b08c1eb3a053b65c977479367354ffa31a50d479ce527b42e096929981c'
S03_PREPARE_GATEWAY_SHA = '40caff3109111d971ff2d37cb81c0c2050ead08ae42d1f631a245778dd1a7a4d'
S03_GATEWAY_SHA = 'cb7f373cf2d3c4f01d47ed4ef0c48b0a89af7a05eb92a06530752c40453fdf20'
S03_MODEL_CONTENT_SHA = '6d39681b26c61279ac1f82db35a04a05009e94c415b51c858ff571489a82fc06'
S03_MODEL_IDENTITY = '748d9efea2dd22943f1f3b99feca6105579f06b67f7003d2777c063a32f0ee10'
S03_BEFORE_SHA = '82c592ea5a59281fb5fc1061d133ac4e149b8e95a6d0947a254882715cba7f91'
S03_AFTER_SHA = '3ebdc3585f32bafbd0e1210ceee286b174a657c37696e16fce9fcafb57c43e10'
S03_DISPATCHER_SHA = '2294ad543cf78ae7c72cb79f399d458a86feae9c4d144586abc8630d9b4295e0'
MEDIA_ACCEPTANCE_REQUEST = '6904718718'
MEDIA_ACCEPTANCE_SOURCE = '4cfc1fc8fcab16a70d1c637ef4593ef2fc496f8a'
MEDIA_ACCEPTANCE_RECEIPT_SHA = 'f224353628c1aef7ac5ff70c9d74a0f4a1b82569bccb70ab59faf234bdbe4fdb'
HELPER_SHA = 'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0'
NATIVE_SHA = '703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a'
SCHEMA = 'NOX_OWNER_TRAINING_RESUME_V1'
POINTER = STATE / 'owner_training_admission.json'
POLICY = STATE / 'task_boost_mode.json'
CONTROLS = {
    ROOT / 'scripts/nox_dispatcher_t855u.py': '31fafe9501a81684ab3476acb940e1a8ea439067a610164c9057a647f0990fa2',
    ROOT / 'scripts/nox_autoscale_t877u.py': '4d582d71c10e71486d881cb005002374f7f9d5c3af39f1c361ba8830e4806441',
    Path('/root/nox_selfheal.py'): '84a841854e25e94a91d1582106ce2825287e631c068775529790f9843add3538',
    ROOT / 'scripts/nox_priority_scheduler.py': '5decaeba7bc1d329abbb627861cd03d99b8150136e98d0e2facd8fcb8e29f45a',
}
BOOST_PINS = {
    **CONTROLS,
    ENTRY: '54e1707dd25a7128690e90722ced5885a3fcb347b50126e69e3cac216cf6c557',
    WRAPPER: '846c13c8e949d58764d81c844f0ff1d5bf0939e8952e0272ffd264b07cdf5164',
    ROOT / 'scripts/owner_dispatcher_mentor.py': '12211a29f77de8e5181d4dd78c35d5da2ed5de0dc6ea529149d32f0896809292',
    ROOT / 'config/dispatcher_agents_t868u.json': '2216efe323366107f882557013edf7a57e88c7ebdffc3509c8c5e13f593b3f66',
    STATE / 'train_cpu_max.env': '70cb2855de545553966fcd15e0a4341f329fc88bd855b49b4ac1bc101214ac7f',
}
UPGRADE_SOURCE_PINS = {
    'owner_mentor': '12211a29f77de8e5181d4dd78c35d5da2ed5de0dc6ea529149d32f0896809292',
    'owner_event_outbox': 'af4edd2c34e4d46902ccf914b5be9c845a95d682d34f92a08cd69357c4b69c00',
    'owner_media_runtime': 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5',
    'owner_task_plans': '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773',
    'owner_senior_gateway': '1fd1556009ce62fa806bdee0a9a34577d276344e728fe9d94b33f44eb151346e',
}
UPGRADE_PINS = {
    ROOT / 'scripts/nox_dispatcher_t855u.py': DISPATCHER_UPGRADE_SHA,
    ROOT / 'scripts/owner_task_lifecycle.py': '020fcee6d1267189811c51da031761aa9ae681a3a2bcd567fbbc150c33db8605',
    ROOT / 'scripts/owner_s03_diagnostic.py': 'a06e45cfe58b6350f5d67787ab13b834a168f78f910574db51af7635e8c969f1',
    ROOT / 'config/owner_task_lifecycle.json': '70d600e861a1e9908d06691790e54e2abcd814b460144ece2af3d2b6a54e0e80',
    ROOT / 'config/owner_download_manifest.json': '7ce1b32c3e007fefa5b8c96aca34bd8ca10d97cce15968100e40b29685c091f9',
    **{ROOT / 'scripts' / (('owner_dispatcher_mentor' if name == 'owner_mentor' else name) + '.py'): sha
       for name, sha in UPGRADE_SOURCE_PINS.items()},
}
S03_SOURCE_PINS = {
    **UPGRADE_SOURCE_PINS,
    'owner_event_outbox': 'e15d458f9d1f03b23fcbf0267206621769ff92f2bfe00d3baf79217e2ab74a02',
    'owner_s03_gateway': S03_GATEWAY_SHA,
}
S03_PINS = {
    ROOT / 'scripts/nox_dispatcher_t855u.py': S03_DISPATCHER_SHA,
    ROOT / 'scripts/s03_memory.py': S03_AFTER_SHA,
    ROOT / 'scripts/owner_s03_gateway.py': S03_GATEWAY_SHA,
    ROOT / 'scripts/owner_task_lifecycle.py': '909502a75799096e094a622639fe959ecfa835cc70db705a4062541940cea27e',
    ROOT / 'scripts/owner_event_outbox.py': S03_SOURCE_PINS['owner_event_outbox'],
    ROOT / 'config/owner_task_lifecycle.json': '14f4b38e2c058dc9335c8d7a70e9a8987ef6db0febcb426eef66a92f8817a315',
}
CONTROLLER_SERVICES = {
    'nox-dispatcher-t855u': ROOT / 'scripts/nox_dispatcher_t855u.py',
    'nox-priority-scheduler': ROOT / 'scripts/nox_priority_scheduler.py',
    'nox-selfheal': Path('/root/nox_selfheal.py'),
}
STOPPED = ('STOPPED', 'EXITED', 'FATAL')
# Native owner handoff SIX_LANE_EXECUTION_PIN_20261119 fixes physical cap at 3.
# Six logical lanes are NOT six native worker processes.
NATIVE_WORKER_CAP = 3


def read_json(path, limit=4_000_000, expected_sha256=None, include_mtime=False):
    """Bounded descriptor read: an untrusted state path cannot be swapped to a symlink."""
    path = Path(path)
    if type(limit) is not int or limit < 0:
        raise RuntimeError('HOLD_BOUNDED_STATE_READ')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except OSError as exc:
        raise RuntimeError('HOLD_BOUNDED_STATE_READ') from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise RuntimeError('HOLD_BOUNDED_STATE_READ')
        with os.fdopen(fd, 'rb') as stream:
            fd = -1
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > limit:
            raise RuntimeError('HOLD_BOUNDED_STATE_READ')
        # A stable FD is insufficient if the named state file was rebound
        # during reading; the next checkpoint stage will reopen this path.
        # Reject a missing, swapped, symlinked or concurrently changed name.
        try:
            named = os.stat(path, follow_symlinks=False)
        except OSError as exc:
            raise RuntimeError('HOLD_STATE_FILE_MUTATED') from exc
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if (len(raw) != info.st_size
                or any(getattr(info, field) != getattr(after, field)
                       or getattr(info, field) != getattr(named, field)
                       for field in fields)):
            raise RuntimeError('HOLD_STATE_FILE_MUTATED')
    finally:
        if fd >= 0:
            os.close(fd)
    # Bind the parsed trainer state to the exact bytes hashed in the checkpoint receipt.
    # A writer may replace or modify the inode after the earlier file_sha() sweep.
    if expected_sha256 is not None:
        if (not isinstance(expected_sha256, str)
                or not re.fullmatch('[0-9a-f]{64}', expected_sha256)
                or hashlib.sha256(raw).hexdigest() != expected_sha256):
            raise RuntimeError('HOLD_PAUSED_CHECKPOINT_HASH')
    # Refuse ambiguous or nonstandard JSON even when its byte hash is valid.
    # Different parsers can otherwise disagree about an optimizer step.
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise RuntimeError('HOLD_DUPLICATE_STATE_KEY')
            value[key] = item
        return value

    def finite_json_constant(token):
        raise RuntimeError('HOLD_NONFINITE_STATE_JSON')

    def finite_json_float(token):
        # parse_constant catches NaN/Infinity literals, but standard JSON
        # exponents such as 1e999 can still overflow to float infinity.
        number = float(token)
        if not math.isfinite(number):
            raise RuntimeError('HOLD_NONFINITE_STATE_JSON')
        return number

    value = json.loads(raw, object_pairs_hook=unique_object,
                       parse_constant=finite_json_constant,
                       parse_float=finite_json_float)
    if not isinstance(value, dict):
        raise RuntimeError('HOLD_STATE_OBJECT_REQUIRED')
    # Freshness must be evaluated against this verified descriptor snapshot,
    # never a pathname that can be rebound after the JSON read.
    return (value, info.st_mtime) if include_mtime else value


def file_sha(path):
    """Hash only a stable, pathname-bound regular file from one descriptor."""
    path = Path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except OSError as exc:
        raise RuntimeError('HOLD_SOURCE_PATH') from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size < 0:
            raise RuntimeError('HOLD_SOURCE_PATH')
        digest = hashlib.sha256()
        with os.fdopen(fd, 'rb') as stream:
            fd = -1
            remaining = before.st_size
            while remaining:
                block = stream.read(min(8 * 1024 * 1024, remaining))
                if not block:
                    raise RuntimeError('HOLD_CHECKPOINT_FILE_MUTATED')
                digest.update(block)
                remaining -= len(block)
            if stream.read(1):
                raise RuntimeError('HOLD_CHECKPOINT_FILE_MUTATED')
            after = os.fstat(stream.fileno())
            # A stable open descriptor is insufficient if the named checkpoint
            # was replaced after open; the caller will use the pathname again.
            try:
                named = os.stat(path, follow_symlinks=False)
            except OSError as exc:
                raise RuntimeError('HOLD_CHECKPOINT_FILE_MUTATED') from exc
            keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            if any(getattr(before, key) != getattr(after, key)
                   or getattr(before, key) != getattr(named, key) for key in keys):
                raise RuntimeError('HOLD_CHECKPOINT_FILE_MUTATED')
        return digest.hexdigest()
    finally:
        if fd >= 0:
            os.close(fd)



def stable_backup_bytes(path, expected_sha256=None, max_bytes=64 * 1024 * 1024):
    """Back up only a single stable named regular-file preimage, never a swapped link."""
    path = Path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except OSError as exc:
        raise RuntimeError('HOLD_BACKUP_SOURCE_CHANGED') from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= max_bytes:
            raise RuntimeError('HOLD_BACKUP_SOURCE_CHANGED')
        with os.fdopen(fd, 'rb') as stream:
            fd = -1
            raw = stream.read(before.st_size + 1)
            after = os.fstat(stream.fileno())
        try:
            named = os.stat(path, follow_symlinks=False)
        except OSError as exc:
            raise RuntimeError('HOLD_BACKUP_SOURCE_CHANGED') from exc
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if (len(raw) != before.st_size
                or any(getattr(before, key) != getattr(after, key)
                       or getattr(before, key) != getattr(named, key)
                       for key in fields)):
            raise RuntimeError('HOLD_BACKUP_SOURCE_CHANGED')
        if (expected_sha256 is not None
                and (type(expected_sha256) is not str
                     or not re.fullmatch('[0-9a-f]{64}', expected_sha256)
                     or hashlib.sha256(raw).hexdigest() != expected_sha256)):
            raise RuntimeError('HOLD_BACKUP_PREIMAGE_MISMATCH')
        return raw
    finally:
        if fd >= 0:
            os.close(fd)


def load_helper():
    data = base64.b64decode(BUNDLE.get('owner_native_repair.py', ''), validate=True)
    if hashlib.sha256(data).hexdigest() != HELPER_SHA:
        raise RuntimeError('HOLD_REVIEWED_NATIVE_HELPER_MISSING')
    module = types.ModuleType('owner_resume_reviewed_helpers')
    sys.modules[module.__name__] = module
    exec(compile(data, '<reviewed-native-helpers>', 'exec'), module.__dict__)
    return module


PERMISSION_HELPER = '''
# NOX_OWNER_SINGLE_TRAINER_PERMISSION_V1
def _nox_owner_training_allowed():
    import json as _json
    import math as _math
    import os as _os
    import stat as _stat
    _p = ROOT / "state/task_boost_mode.json"
    _fd = -1
    try:
        # Authorize exactly the stable regular file named at this path, not
        # a symlink/fifo rebound between the old is_symlink/stat/read_text.
        _fd = _os.open(_p, _os.O_RDONLY | _os.O_NOFOLLOW | _os.O_NONBLOCK | _os.O_CLOEXEC)
        _before = _os.fstat(_fd)
        if not _stat.S_ISREG(_before.st_mode) or not 0 < _before.st_size <= 16000:
            return False
        _raw = _os.read(_fd, 16001)
        _after = _os.fstat(_fd)
        _named = _os.stat(_p, follow_symlinks=False)
        _fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if (len(_raw) != _before.st_size
                or any(getattr(_before, key) != getattr(_after, key)
                       or getattr(_before, key) != getattr(_named, key)
                       for key in _fields)):
            return False
        # Duplicate authority keys must not be interpreted last-value-wins.
        # A verifier and the runtime must agree on one unambiguous policy.
        def _unique_pairs(pairs):
            _value = {}
            for _key, _item in pairs:
                if _key in _value:
                    raise ValueError("duplicate owner policy key")
                _value[_key] = _item
            return _value
        # Python's permissive JSON decoder accepts NaN/Infinity and can
        # overflow a standards-compliant exponent (1e999) to infinity.
        # Do not authorize a policy that the canonical state reader rejects.
        def _finite_constant(_token):
            raise ValueError("nonfinite owner policy constant")
        def _finite_float(_token):
            _number = float(_token)
            if not _math.isfinite(_number):
                raise ValueError("nonfinite owner policy float")
            return _number
        _v = _json.loads(_raw, object_pairs_hook=_unique_pairs,
                         parse_constant=_finite_constant,
                         parse_float=_finite_float)
        return (type(_v) is dict and _v.get("enabled") is True
                and _v.get("mode") == "TASK_BOOST"
                and _v.get("training_allowed") is True
                and _v.get("training_service") == "nox-train-volta-t866u"
                and _v.get("training_request") == "__NOX_OWNER_REQUEST_ID__"
                and _v.get("training_source_sha") == "__NOX_OWNER_SOURCE_SHA__")
    except (ValueError, OSError, UnicodeError, TypeError, AttributeError):
        return False
    finally:
        if _fd >= 0:
            _os.close(_fd)

'''

def replace_once(source, before, after):
    if source.count(before) != 1:
        raise RuntimeError('HOLD_DEPLOYED_GUARD_ANCHOR_CHANGED')
    return source.replace(before, after, 1)


def bound_permission_helper(request_id, source_sha):
    """Bind controller permission to the exact reviewed owner request/source."""
    if (type(request_id) is not str or not re.fullmatch('[0-9]+', request_id)
            or type(source_sha) is not str
            or not re.fullmatch('[0-9a-f]{40}', source_sha)):
        raise RuntimeError('HOLD_OWNER_REQUEST_CONTEXT')
    rendered = PERMISSION_HELPER.replace('"__NOX_OWNER_REQUEST_ID__"', repr(request_id))
    rendered = rendered.replace('"__NOX_OWNER_SOURCE_SHA__"', repr(source_sha))
    if '__NOX_OWNER_REQUEST_ID__' in rendered or '__NOX_OWNER_SOURCE_SHA__' in rendered:
        raise RuntimeError('HOLD_OWNER_PERMISSION_BINDING')
    compile(rendered, '<bound-owner-permission>', 'exec')
    return rendered


def patch_permission(source, request_id, source_sha, selfheal=False):
    if source.count('NOX_OWNER_ADMISSION_GUARD_V1') != 1 or 'NOX_OWNER_SINGLE_TRAINER_PERMISSION_V1' in source:
        raise RuntimeError('HOLD_DEPLOYED_GUARD_VERSION')
    source = replace_once(source, 'def _nox_owner_task_admitted(task):\n',
                          bound_permission_helper(request_id, source_sha) + 'def _nox_owner_task_admitted(task):\n')
    source = replace_once(source,
        '    if _nox_owner_boost_active() and name in ("nox-train-volta-t866u","nox-train-worm-t811u",\n',
        '    if (_nox_owner_boost_active()\n'
        '            and not (name=="nox-train-volta-t866u" and _nox_owner_training_allowed())\n'
        '            and name in ("nox-train-volta-t866u","nox-train-worm-t811u",\n')
    source = replace_once(source,
        '            "nox-offload-t850u","nox-downloads-t802u","nox-watch-swap-t845u","nox-agent-architect-t859u","nox-agent-tuner-t858u"):\n',
        '            "nox-offload-t850u","nox-downloads-t802u","nox-watch-swap-t845u","nox-agent-architect-t859u","nox-agent-tuner-t858u")):\n')
    if selfheal:
        # This old playbook rewrites the CPU cap/wrapper using historical OOM
        # logs. Allowing sv_start must not re-enable those unverified repairs.
        source = replace_once(source, 'def fix_training(st: dict, why: str) -> dict:\n',
            'def fix_training(st: dict, why: str) -> dict:\n'
            '    if _nox_owner_boost_active(): return {"result":"owner_hold","fix":"single hybrid lineage is owner/media controlled"}\n')
    compile(source, '<single-trainer-permission>', 'exec')
    return source


def boost_pins(receipt):
    if (receipt.get('schema') != 'NOX_OWNER_OPTIMIZE_HYBRID_V1'
            or receipt.get('request') != BOOST_REQUEST or receipt.get('source_sha') != BOOST_SOURCE
            or receipt.get('state') != 'TASK_BOOST_SIX_NATIVE_WORKERS_ACTIVE_TRAINING_PAUSED'
            or receipt.get('hold_retained') is not True or receipt.get('training_started') is not False):
        raise RuntimeError('HOLD_VERIFIED_NATIVE_BOOST_REQUIRED')
    installed = {row['data']['path']: row['data']['after'] for row in receipt.get('steps', [])
                 if row.get('kind') == 'source_installed'}
    if any(installed.get(str(path)) != sha for path, sha in BOOST_PINS.items()):
        raise RuntimeError('HOLD_BOOST_INSTALLED_RECEIPT_MISMATCH')
    return dict(BOOST_PINS)


def dispatcher_upgrade_pins(receipt, request=None, source=None):
    """Accept only the reviewed upgrade, with its real six-branch audit proof.

    The caller must still verify the original BOOST receipt and every current
    file. This returns only the exact, subsequently installed source delta.
    """
    request = DISPATCHER_UPGRADE_REQUEST if request is None else request
    source = DISPATCHER_UPGRADE_SOURCE if source is None else source
    if (not isinstance(request, str) or not request.isdigit()
            or not isinstance(source, str) or not re.fullmatch('[0-9a-f]{40}', source)):
        raise RuntimeError('HOLD_PINNED_DISPATCHER_UPGRADE_CONTEXT_REQUIRED')
    dispatcher = ROOT / 'scripts/nox_dispatcher_t855u.py'
    if (receipt.get('schema') != 'NOX_OWNER_DISPATCHER_UPGRADE_V1'
            or receipt.get('request') != request or receipt.get('source_sha') != source
            or receipt.get('state') != 'SIX_WORKER_LIFECYCLE_MEDIA_PLANS_REPORTS_VERIFIED'
            or receipt.get('dispatcher_before') != BOOST_PINS[dispatcher]
            or receipt.get('dispatcher_after') != DISPATCHER_UPGRADE_SHA
            or receipt.get('source_pins') != UPGRADE_SOURCE_PINS
            or receipt.get('rollback') is not False or receipt.get('training_started') is not False
            or not isinstance(receipt.get('training_hold_sha256'), str)
            or not re.fullmatch('[0-9a-f]{64}', receipt['training_hold_sha256'])):
        raise RuntimeError('HOLD_VERIFIED_DISPATCHER_UPGRADE_REQUIRED')
    workers = receipt.get('workers') or {}
    worker_ids = workers.get('ids') or []
    if (not isinstance(worker_ids, list) or len(worker_ids) != 6 or any(not isinstance(value, str) for value in worker_ids)
            or len(set(worker_ids)) != 6):
        raise RuntimeError('HOLD_DISPATCHER_UPGRADE_SIX_WORKERS_REQUIRED')
    plan = receipt.get('native_plan') or {}
    children = plan.get('children') or []
    parent_id = 'owner.autonomy.audit.' + request
    child_ids = [row.get('id') for row in children if isinstance(row, dict)]
    if (plan.get('verified') is not True or plan.get('parent_status') != 'done'
            or plan.get('scope') != 'BOUNDED_COMPONENT_AUDIT' or plan.get('unique_claims') != 7
            or plan.get('training_optimizer_update_proven') is not False
            or len(child_ids) != 6 or any(not isinstance(value, str) or not value for value in child_ids)
            or len(set(child_ids)) != 6 or parent_id in child_ids
            or any(row.get('status') != 'done' for row in children)):
        raise RuntimeError('HOLD_DISPATCHER_UPGRADE_NATIVE_PLAN_REQUIRED')
    task_ids = set(child_ids + [parent_id])
    proofs = plan.get('proofs') or []
    reports = plan.get('owner_reports') or []
    if (len(proofs) != 7 or any(not isinstance(row, dict) for row in proofs)
            or {row.get('id') for row in proofs} != task_ids
            or any(not isinstance(row.get('receipt_sha256'), str)
                   or not re.fullmatch('[0-9a-f]{64}', row['receipt_sha256']) for row in proofs)
            or len(reports) != 7 or any(not isinstance(row, dict) for row in reports)
            or {row.get('task_id') for row in reports} != task_ids
            or any(row.get('kind') != 'task_verified' or not isinstance(row.get('claim'), str)
                   or not re.fullmatch('[0-9a-f]{24}', row['claim']) for row in reports)
            or len({row['claim'] for row in reports}) != 7):
        raise RuntimeError('HOLD_DISPATCHER_UPGRADE_DURABLE_REPORTS_REQUIRED')
    return dict(UPGRADE_PINS)


def dispatcher_upgrade_evidence():
    if (not DISPATCHER_UPGRADE_REQUEST.isdigit()
            or not re.fullmatch('[0-9a-f]{40}', DISPATCHER_UPGRADE_SOURCE)):
        raise RuntimeError('HOLD_PINNED_DISPATCHER_UPGRADE_CONTEXT_REQUIRED')
    path = STATE / ('owner_dispatcher_upgrade_' + DISPATCHER_UPGRADE_REQUEST + '.json')
    receipt = read_json(path)
    pins = dispatcher_upgrade_pins(receipt)
    chain = {'request': DISPATCHER_UPGRADE_REQUEST, 'source_sha': DISPATCHER_UPGRADE_SOURCE,
             'receipt_sha256': file_sha(path), 'dispatcher_sha256': DISPATCHER_UPGRADE_SHA,
             'training_hold_sha256': receipt['training_hold_sha256']}
    return pins, chain


def s03_activation_pins(receipt, upgrade_chain, request=None, source=None):
    """Verify the complete approved S03 source delta, never replace older proof."""
    request = S03_ACTIVATION_REQUEST if request is None else request
    source = S03_ACTIVATION_SOURCE if source is None else source
    if (not isinstance(request, str) or not request.isdigit()
            or not isinstance(source, str) or not re.fullmatch('[0-9a-f]{40}', source)):
        raise RuntimeError('HOLD_PINNED_S03_ACTIVATION_CONTEXT_REQUIRED')
    if (not isinstance(receipt, dict) or receipt.get('schema') != 'NOX_OWNER_S03_ACTIVATION_V1'
            or receipt.get('request') != request or receipt.get('source_sha') != source
            or receipt.get('state') != 'LIVE_SHARED_SEMANTIC_MEMORY_AND_NATIVE_INDEX_VERIFIED'
            or receipt.get('prepare_request') != S03_PREPARE_REQUEST
            or receipt.get('prepare_receipt_sha256') != S03_PREPARE_RECEIPT_SHA
            or receipt.get('source_pins') != S03_SOURCE_PINS
            or receipt.get('dispatcher_after_sha256') != S03_DISPATCHER_SHA
            or receipt.get('s03_after_sha256') != S03_AFTER_SHA
            or receipt.get('lifecycle_config_sha256') != S03_PINS[ROOT/'config/owner_task_lifecycle.json']
            or receipt.get('training_hold_sha256') != upgrade_chain.get('training_hold_sha256')
            or any(receipt.get(key) is not False for key in
                   ('rollback', 'training_started', 'llama_restarted', 'private_text_exported'))
            or any(type(receipt.get(key)) is not int or receipt[key] != 0
                   for key in ('weights_deleted', 'memory_records_deleted'))):
        raise RuntimeError('HOLD_VERIFIED_S03_ACTIVATION_REQUIRED')
    content = receipt.get('content_reindex') or {}
    if (content.get('schema') != 'NOX_OWNER_S03_CONTENT_REINDEX_V1'
            or content.get('request') != request or content.get('source_sha') != source
            or content.get('state') != 'CONTENT_IDENTITY_AND_REEMBEDDED_INDEX_VERIFIED'
            or content.get('gateway_sha256') != S03_GATEWAY_SHA
            or content.get('model_identity') != S03_MODEL_IDENTITY
            or content.get('model_content_sha256') != S03_MODEL_CONTENT_SHA
            or not re.fullmatch('[a-f0-9]{64}', str(content.get('receipt_sha256', '')))
            or type(content.get('current_embeddings')) is not int or content['current_embeddings'] < 514
            or type(content.get('indexed_in_action')) is not int or content['indexed_in_action'] < 0
            or content.get('stale_embeddings') != 0 or content.get('legacy_vectors_relabelled') is not False):
        raise RuntimeError('HOLD_S03_VERIFIED_CONTENT_REINDEX_REQUIRED')
    workers = receipt.get('workers') or {}
    if (workers.get('configured') != 6 or workers.get('observed') != 6
            or type(workers.get('unique_active_claims')) is not int
            or not 0 <= workers['unique_active_claims'] <= 6):
        raise RuntimeError('HOLD_S03_NATIVE_SIX_WORKERS_REQUIRED')
    before, after = receipt.get('model_process_before'), receipt.get('model_process_after')
    if (not isinstance(before, dict) or before != after
            or type(before.get('pid')) is not int or before['pid'] <= 0
            or not str(before.get('starttime', '')).isdigit()
            or any((receipt.get('health_after') or {}).get(port) != 200 for port in ('8080', '8081', '8082'))):
        raise RuntimeError('HOLD_S03_LIVE_CHAT_PROOF_REQUIRED')
    proof = receipt.get('native_index_proof') or {}
    if (proof.get('kind') != 'bounded_native_s03_index' or proof.get('scope') != 'BOUNDED_S03_VECTOR_INDEX'
            or proof.get('source_sha256') != S03_GATEWAY_SHA
            or not re.fullmatch('[0-9a-f]{64}', str(proof.get('receipt_sha256', '')))
            or type(proof.get('indexed')) is not int or proof['indexed'] < 0
            or type(proof.get('stale_remaining')) is not int or proof['stale_remaining'] != 0
            or type(proof.get('training_examples_accepted')) is not int or proof['training_examples_accepted'] != 0):
        raise RuntimeError('HOLD_S03_NATIVE_INDEX_PROOF_REQUIRED')
    events = {row.get('kind'): row.get('data') for row in receipt.get('steps', []) if isinstance(row, dict)}
    live, recall = events.get('s03_live_proxy_recall') or {}, events.get('s03_lifecycle_recall') or {}
    methods = live.get('methods') or {}
    if (live.get('state') != 'SEMANTIC_LEXICAL_BOUNDED_PINS' or live.get('private_text_exported') is not False
            or not all(type(methods.get(key)) is int and methods[key] >= 0 for key in ('semantic', 'hybrid', 'pin'))
            or methods['semantic'] + methods['hybrid'] < 1 or methods['pin'] > 2
            or recall.get('retrieval_kind') != 'SEMANTIC_LEXICAL_BOUNDED_PINS'
            or recall.get('gateway_source_sha256') != S03_GATEWAY_SHA
            or recall.get('source_sha256') != S03_AFTER_SHA or recall.get('content_exported') is not False):
        raise RuntimeError('HOLD_S03_ACTUAL_SEMANTIC_RECALL_REQUIRED')
    rows = receipt.get('installed_sources')
    required = {path.name: (path, sha) for path, sha in S03_PINS.items()}
    required_names = set(required) | {'owner_senior_gateway.json'}
    if (not isinstance(rows, list) or len(rows) != len(required_names)
            or any(not isinstance(row, dict) for row in rows)
            or {row.get('name') for row in rows} != required_names):
        raise RuntimeError('HOLD_S03_INSTALLED_SOURCE_SET')
    previous = {path.name: sha for path, sha in UPGRADE_PINS.items()}
    previous.update({'s03_memory.py': S03_BEFORE_SHA, 'owner_s03_gateway.py': S03_PREPARE_GATEWAY_SHA})
    pins = dict(S03_PINS)
    for row in rows:
        if row['name'] == 'owner_senior_gateway.json':
            if any(not re.fullmatch('[0-9a-f]{64}', str(row.get(key, ''))) for key in ('before', 'after')):
                raise RuntimeError('HOLD_S03_SENIOR_CONFIG_PROVENANCE')
            pins[ROOT/'config/owner_senior_gateway.json'] = row['after']
        elif row.get('before') != previous[row['name']] or row.get('after') != required[row['name']][1]:
            raise RuntimeError('HOLD_S03_INSTALLED_SOURCE_DELTA')
    return pins


def s03_content_reindex_proof(receipt, content, upgrade_chain):
    """Bind real reembedding, stable model content and retained original history."""
    identity = receipt.get('content_identity') or {}
    status = receipt.get('status') or {}
    before = receipt.get('before_index') or {}
    process = receipt.get('bge_process_before') or {}
    recall = receipt.get('public_recall') or {}
    methods = recall.get('methods') or {}
    if (receipt.get('schema') != 'NOX_OWNER_S03_CONTENT_REINDEX_V1'
            or receipt.get('request') != content['request'] or receipt.get('source_sha') != content['source_sha']
            or receipt.get('state') != 'CONTENT_IDENTITY_AND_REEMBEDDED_INDEX_VERIFIED'
            or receipt.get('gateway_sha256') != S03_GATEWAY_SHA
            or receipt.get('prepare_request') != S03_PREPARE_REQUEST
            or receipt.get('prepare_source_sha') != '2a09e5975e0bfbd84e22bbaea1c0347a9b41ec63'
            or receipt.get('prepare_receipt_sha256') != S03_PREPARE_RECEIPT_SHA
            or identity.get('content_sha256') != S03_MODEL_CONTENT_SHA or identity.get('identity') != S03_MODEL_IDENTITY
            or identity.get('dimensions') != 1024 or identity.get('full_file_hash_verified') is not True
            or status.get('model_identity') != S03_MODEL_IDENTITY or status.get('stale_embeddings') != 0
            or type(status.get('current_embeddings')) is not int
            or not 514 <= status['current_embeddings'] <= content['current_embeddings']
            or type(status.get('original_history_records_preserved')) is not int
            or status['original_history_records_preserved'] < 1014
            or type(before.get('legacy_identity_vectors')) is not int or before['legacy_identity_vectors'] < 0
            or receipt.get('indexed_in_action') != content['indexed_in_action']
            or receipt['indexed_in_action'] < before['legacy_identity_vectors']
            or receipt.get('legacy_vectors_remaining') != 0 or receipt.get('legacy_vectors_relabelled') is not False
            or receipt.get('historical_model_content_sha_known') is not False
            or receipt.get('canonical_originals_preserved') is not True
            or receipt.get('sources_and_flags_unchanged') is not True
            or receipt.get('training_hold_sha256') != upgrade_chain['training_hold_sha256']
            or receipt.get('training_pause_sha256') != upgrade_chain['training_hold_sha256']
            or receipt.get('private_text_exported') is not False or receipt.get('training_examples_accepted') != 0
            or receipt.get('services_restarted') != [] or receipt.get('live_sources_changed') is not False
            or type(process.get('pid')) is not int or process['pid'] <= 0
            or type(process.get('starttime')) is not int or process['starttime'] <= 0
            or process != receipt.get('bge_process_after')
            or (receipt.get('synthetic_retrieval_acceptance') or {}).get('state') != 'SYNTHETIC_SEMANTIC_FIXTURES_VERIFIED'
            or recall.get('state') != 'SEMANTIC_LEXICAL_BOUNDED_PINS'
            or not all(type(methods.get(k)) is int and methods[k] >= 0 for k in ('semantic', 'hybrid', 'pin'))
            or methods['semantic'] + methods['hybrid'] < 1 or methods['pin'] > 2):
        raise RuntimeError('HOLD_S03_CONTENT_REINDEX_CHAIN_REQUIRED')
    return {'receipt_sha256': content['receipt_sha256'], 'model_identity': S03_MODEL_IDENTITY,
            'model_content_sha256': S03_MODEL_CONTENT_SHA, 'current_embeddings': content['current_embeddings'],
            'legacy_vectors_relabelled': False}


def s03_activation_evidence(upgrade_chain):
    if (not S03_ACTIVATION_REQUEST.isdigit()
            or not re.fullmatch('[0-9a-f]{40}', S03_ACTIVATION_SOURCE)
            or not re.fullmatch('[0-9a-f]{64}', S03_ACTIVATION_RECEIPT_SHA)):
        raise RuntimeError('HOLD_PINNED_S03_ACTIVATION_CONTEXT_REQUIRED')
    path = STATE/'owner_s03'/('activation_'+S03_ACTIVATION_REQUEST+'.json')
    if file_sha(path) != S03_ACTIVATION_RECEIPT_SHA:
        raise RuntimeError('HOLD_S03_ACTIVATION_RECEIPT_PIN')
    activation = read_json(path)
    pins = s03_activation_pins(activation, upgrade_chain)
    content = activation['content_reindex']
    reindex_path = STATE/'owner_s03'/('content_reindex_'+S03_ACTIVATION_REQUEST+'.json')
    if file_sha(reindex_path) != content['receipt_sha256']:
        raise RuntimeError('HOLD_S03_CONTENT_REINDEX_RECEIPT_PIN')
    content_chain = s03_content_reindex_proof(read_json(reindex_path), content, upgrade_chain)
    return pins, {'request': S03_ACTIVATION_REQUEST, 'source_sha': S03_ACTIVATION_SOURCE,
                  'receipt_sha256': S03_ACTIVATION_RECEIPT_SHA, 'dispatcher_sha256': S03_DISPATCHER_SHA,
                  's03_sha256': S03_AFTER_SHA, 'gateway_sha256': S03_GATEWAY_SHA,
                  'content_reindex': content_chain,
                  'training_hold_sha256': upgrade_chain['training_hold_sha256']}


def media_acceptance_proof(receipt, upgrade_chain):
    """Accept actual decoded samples, never installed files or a queued job."""
    if (not isinstance(receipt, dict) or receipt.get('schema') != 'NOX_OWNER_MEDIA_ACCEPTANCE_V1'
            or receipt.get('request') != MEDIA_ACCEPTANCE_REQUEST or receipt.get('source') != MEDIA_ACCEPTANCE_SOURCE
            or receipt.get('state') != 'GENERATED_DECODED_AND_GPU_RELEASED'
            or receipt.get('pixels_exported') is not False):
        raise RuntimeError('HOLD_VERIFIED_MEDIA_ACCEPTANCE_REQUIRED')
    release = receipt.get('release') or {}; trainer = release.get('trainer') or {}; gpu = release.get('gpu1') or {}
    if (any(release.get(key) is not True for key in
            ('forge_lease_reacquired', 'forge_lease_released', 'original_flags_preserved'))
            or release.get('training_started') is not False
            or release.get('hold_sha256') != upgrade_chain.get('training_hold_sha256')
            or release.get('pause_sha256') != upgrade_chain.get('training_hold_sha256')
            or trainer.get('state') not in STOPPED or trainer.get('pid') is not None
            or type(gpu.get('free_mib')) is not int or gpu['free_mib'] < 30000):
        raise RuntimeError('HOLD_MEDIA_ACCEPTANCE_GPU_AND_TRAINER_RELEASE')
    rows = receipt.get('artifacts')
    if (not isinstance(rows, list) or len(rows) != 2 or any(not isinstance(row, dict) for row in rows)
            or {row.get('kind') for row in rows} != {'image', 'video'}):
        raise RuntimeError('HOLD_MEDIA_ACCEPTANCE_TWO_DECODED_OUTPUTS')
    artifacts = []
    for row in rows:
        job_id = row.get('job_id'); kind = row['kind']; proof = row.get('decode') or {}
        path = Path(row.get('path', ''))
        extension, media_type = ('.png', 'image/png') if kind == 'image' else ('.webm', 'video/webm')
        if (not isinstance(job_id, str) or not re.fullmatch('[0-9a-f]{32}', job_id)
                or path.parent != ROOT/'media/outputs/nox'/job_id or path.suffix != extension
                or not re.fullmatch('[A-Za-z0-9_.-]{1,100}', path.name)
                or row.get('url') != '/api/ui/media/jobs/'+job_id+'/outputs/0'
                or row.get('media_type') != media_type or row.get('decode_verified') is not True
                or row.get('authenticated_http_verified') is not True or row.get('pixels_exported') is not False
                or row.get('scope') != 'GENERATED_FILE_DECODE_AND_AUTHENTICATED_DELIVERY'
                or type(row.get('bytes')) is not int or not 0 < row['bytes'] <= 64*1024*1024
                or not re.fullmatch('[0-9a-f]{64}', str(row.get('sha256', '')))):
            raise RuntimeError('HOLD_MEDIA_ACCEPTANCE_ARTIFACT_PROOF')
        numeric = ('max_channel_range', 'max_channel_variance') if kind == 'image' else (
            'max_channel_range', 'decoded_fps', 'timestamp_span_seconds', 'max_frame_interval_error_seconds')
        if any(type(proof.get(key)) not in (int, float) or not math.isfinite(proof[key]) for key in numeric):
            raise RuntimeError('HOLD_MEDIA_ACCEPTANCE_FINITE_DECODE')
        dimensions = (512, 512, 1, 'png') if kind == 'image' else (256, 256, 9, 'vp9')
        if (any(type(proof.get(key)) is not int for key in ('width', 'height', 'frames'))
                or tuple(proof.get(key) for key in ('width', 'height', 'frames', 'codec')) != dimensions
                or proof['max_channel_range'] < 4
                or (kind == 'image' and proof['max_channel_variance'] < 1)
                or (kind == 'video' and (type(proof.get('distinct_decoded_frames')) is not int
                    or not 2 <= proof['distinct_decoded_frames'] <= 9
                    or proof.get('timestamps_strictly_increasing') is not True
                    or abs(proof['decoded_fps']-8) > .01
                    or abs(proof['timestamp_span_seconds']-1) > .025
                    or not 0 <= proof['max_frame_interval_error_seconds'] <= .002))):
            raise RuntimeError('HOLD_MEDIA_ACCEPTANCE_REAL_IMAGE_VIDEO_DECODE')
        artifacts.append({key: row[key] for key in ('kind', 'job_id', 'path', 'bytes', 'sha256')})
    return sorted(artifacts, key=lambda row: row['kind'])


def verify_media_artifact(row):
    path = Path(row['path'])
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise RuntimeError('HOLD_MEDIA_ACCEPTANCE_OUTPUT_PATH_CHANGED')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size != row['bytes']:
            raise RuntimeError('HOLD_MEDIA_ACCEPTANCE_OUTPUT_SIZE_CHANGED')
        value = hashlib.sha256(); count = 0
        while True:
            block = os.read(fd, min(1024*1024, row['bytes']+1-count))
            if not block:
                break
            count += len(block); value.update(block)
            if count > row['bytes']:
                raise RuntimeError('HOLD_MEDIA_ACCEPTANCE_OUTPUT_SIZE_CHANGED')
        after = os.fstat(fd); named = path.stat(follow_symlinks=False)
        keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if (count != row['bytes'] or value.hexdigest() != row['sha256']
                or any(getattr(before, key) != getattr(after, key) or getattr(before, key) != getattr(named, key) for key in keys)):
            raise RuntimeError('HOLD_MEDIA_ACCEPTANCE_OUTPUT_HASH_CHANGED')
    finally:
        os.close(fd)


def media_acceptance_evidence(upgrade_chain, rehash_outputs=True):
    path = STATE/'owner_media_acceptance'/('accepted_'+MEDIA_ACCEPTANCE_REQUEST+'.json')
    if file_sha(path) != MEDIA_ACCEPTANCE_RECEIPT_SHA:
        raise RuntimeError('HOLD_MEDIA_ACCEPTANCE_RECEIPT_PIN')
    artifacts = media_acceptance_proof(read_json(path), upgrade_chain)
    if rehash_outputs:
        for row in artifacts:
            verify_media_artifact(row)
    return {'request': MEDIA_ACCEPTANCE_REQUEST, 'source_sha': MEDIA_ACCEPTANCE_SOURCE,
            'receipt_sha256': MEDIA_ACCEPTANCE_RECEIPT_SHA, 'artifacts': artifacts,
            'training_hold_sha256': upgrade_chain['training_hold_sha256']}


def native_training(helper):
    """Fail closed if native process census cannot identify trainer candidates."""
    names = {str(TRAINER), str(ENTRY), str(WRAPPER)}
    census = helper.process_table()
    if type(census) is not dict:
        raise RuntimeError('HOLD_NATIVE_TRAINER_CENSUS_READBACK')
    candidates = []
    for row in census.values():
        if type(row) is not dict or type(row.get('state')) is not str:
            raise RuntimeError('HOLD_NATIVE_TRAINER_CENSUS_READBACK')
        if row['state'] == 'Z':
            continue
        argv = row.get('argv')
        if (type(argv) not in (list, tuple)
                or any(type(arg) is not str for arg in argv)):
            raise RuntimeError('HOLD_NATIVE_TRAINER_CENSUS_READBACK')
        if names.intersection(argv):
            candidates.append(row)
    return candidates


def prove_training(helper):
    rows = native_training(helper)
    entries = [row for row in rows if str(ENTRY) in row['argv']]
    if (len(entries) != 1 or any(row.get('service') != SERVICE or row.get('cuda') != '1' for row in rows)
            or any(str(TRAINER) in row['argv'] and str(ENTRY) not in row['argv'] for row in rows)):
        raise RuntimeError('HOLD_SINGLE_NATIVE_TRAINER_IDENTITY')
    return helper.public_process(entries[0])


def prove_existing_training(helper):
    """Only accept a previously launched trainer after Supervisor RUNNING and native identity.

    A followup may attach while Supervisor still reports STARTING. This is
    observation only: never issue another start or mutate the existing process.
    """
    def read_state():
        # Malformed Supervisor status is never evidence of an active trainer.
        status = helper.service_state()
        if type(status) is not dict or type(status.get('state')) is not str:
            raise RuntimeError('HOLD_EXISTING_TRAINER_STATUS_READBACK')
        return status['state']

    state = read_state()
    if state == 'STARTING':
        deadline = time.monotonic() + 15
    while state == 'STARTING':
        if global_stop():
            raise RuntimeError('HOLD_GLOBAL_STOP_REMAINS')
        if time.monotonic() >= deadline:
            raise RuntimeError('HOLD_EXISTING_TRAINER_START_TIMEOUT')
        time.sleep(0.5)
        state = read_state()
    if global_stop():
        raise RuntimeError('HOLD_GLOBAL_STOP_REMAINS')
    if state != 'RUNNING':
        raise RuntimeError('HOLD_EXISTING_TRAINER_NOT_RUNNING')
    return prove_training(helper)


def global_stop():
    return any(path.exists() or path.is_symlink() for path in
               (ROOT/'STOP', ROOT/'STOP.flag', ROOT/'stop.flag', STATE/'STOP'))


def lease_free():
    fd = os.open(STATE/'forge_training.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False
    finally:
        os.close(fd)


def read_installed_train_cpu_cap(path):
    """Read exactly one approved env assignment from a stable regular file."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except OSError as exc:
        raise RuntimeError('HOLD_INSTALLED_TRAIN_CPU_LIMIT') from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 64:
            raise RuntimeError('HOLD_INSTALLED_TRAIN_CPU_LIMIT')
        with os.fdopen(fd, 'rb') as stream:
            fd = -1
            raw = stream.read(65)
            after = os.fstat(stream.fileno())
            named = os.stat(path, follow_symlinks=False)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if (len(raw) != before.st_size
                or any(getattr(before, field) != getattr(after, field)
                       or getattr(before, field) != getattr(named, field)
                       for field in fields)):
            raise RuntimeError('HOLD_INSTALLED_TRAIN_CPU_LIMIT')
        configured = re.fullmatch(r'TRAIN_CPU_MAX=([0-9]+)GiB\n?', raw.decode('ascii'))
        if configured is None or not 56 <= int(configured.group(1)) <= 64:
            raise RuntimeError('HOLD_INSTALLED_TRAIN_CPU_LIMIT')
        return int(configured.group(1))
    except (OSError, UnicodeError) as exc:
        raise RuntimeError('HOLD_INSTALLED_TRAIN_CPU_LIMIT') from exc
    finally:
        if fd >= 0:
            os.close(fd)


def resource_admission(helper):
    if global_stop():
        raise RuntimeError('HOLD_GLOBAL_STOP_REMAINS')
    if not lease_free():
        raise RuntimeError('HOLD_SHARED_GPU1_LEASE_BUSY')
    # Native admission must use a well-shaped, unambiguous supervisor and
    # GPU census. In particular bool is an int subclass (True == GPU index 1).
    trainer_snapshot = helper.service_state()
    if (type(trainer_snapshot) is not dict
            or type(trainer_snapshot.get('state')) is not str):
        raise RuntimeError('HOLD_TRAINER_STATE_READBACK')
    if trainer_snapshot['state'] not in STOPPED or native_training(helper):
        raise RuntimeError('HOLD_EXISTING_TRAINER_NOT_TERMINAL')
    gpu_snapshot = helper.gpu()
    if (type(gpu_snapshot) is not dict or type(gpu_snapshot.get('gpus')) is not list):
        raise RuntimeError('HOLD_GPU1_CENSUS_READBACK')
    gpu_rows = gpu_snapshot['gpus']
    if any(type(row) is not dict or type(row.get('index')) is not int
           or type(row.get('free_mib')) is not int or row['free_mib'] < 0
           for row in gpu_rows):
        raise RuntimeError('HOLD_GPU1_CENSUS_READBACK')
    gpu1_rows = [row for row in gpu_rows if row['index'] == 1]
    if len(gpu1_rows) != 1:
        raise RuntimeError('HOLD_GPU1_CENSUS_READBACK')
    gpu1 = gpu1_rows[0]
    if gpu1['free_mib'] < 27000:
        raise RuntimeError('HOLD_GPU1_HEADROOM')
    # cgroup v2 uses "max PERIOD" when CPU quota is unlimited.  Treat
    # that as the effective CPU affinity, without silently admitting malformed
    # or zero quotas/periods or bypassing the existing RAM/VRAM gates.
    try:
        cpu_spec = Path('/sys/fs/cgroup/cpu.max').read_text().split()
        if (len(cpu_spec) != 2 or len(cpu_spec[0]) > 32 or len(cpu_spec[1]) > 32
                or not re.fullmatch('[0-9]+', cpu_spec[1])):
            raise ValueError('invalid cpu.max')
        period = int(cpu_spec[1])
        affinity_cpus = len(os.sched_getaffinity(0))
        if period <= 0 or affinity_cpus < 1:
            raise ValueError('invalid CPU period or affinity')
        if cpu_spec[0] == 'max':
            quota_cpus = affinity_cpus
        elif re.fullmatch('[0-9]+', cpu_spec[0]) and int(cpu_spec[0]) >= period:
            # A fractional cgroup CPU cannot be rounded up to an admitted
            # full CPU: that would overstate headroom protecting live chat.
            quota_cpus = int(cpu_spec[0]) // period
        else:
            raise ValueError('invalid CPU quota')
    except (OSError, ValueError) as exc:
        raise RuntimeError('HOLD_CGROUP_CPU_QUOTA') from exc
    # Cgroup v2 may report an unlimited memory.max as "max".  An
    # unbounded/malformed limit is not a verifiable RAM budget for training.
    # Fail closed without treating host RAM as the owner's cgroup allowance.
    try:
        memory_limit_text = Path('/sys/fs/cgroup/memory.max').read_text().strip()
        memory_current_text = Path('/sys/fs/cgroup/memory.current').read_text().strip()
        if (not re.fullmatch('[0-9]{1,20}', memory_limit_text)
                or not re.fullmatch('[0-9]{1,20}', memory_current_text)):
            raise ValueError('unbounded or malformed cgroup memory')
        memory_limit = int(memory_limit_text)
        memory_current = int(memory_current_text)
        if memory_limit <= 0 or memory_current > memory_limit:
            raise ValueError('invalid cgroup memory limit or usage')
    except (OSError, ValueError) as exc:
        raise RuntimeError('HOLD_CGROUP_MEMORY_LIMIT') from exc
    budget = helper.resource_budget(memory_limit, memory_current, quota_cpus, affinity_cpus)
    # The helper is a separate native component, not an authority to bypass
    # the pinned resource gate. NaN, bool and missing/malformed values must
    # never compare as sufficient RAM (NaN < configured_limit is False).
    if (type(budget) is not dict or type(budget.get('train_cpu_gib')) is not int
            or not 0 <= budget['train_cpu_gib'] <= memory_limit // (1024 ** 3)):
        raise RuntimeError('HOLD_RESOURCE_BUDGET_READBACK')
    # A regular-file, pathname-bound, bounded read is required here.
    # A symlink may be switched before the wrapper sources the env cap;
    # a FIFO can otherwise block this admission check indefinitely.
    configured_gib = read_installed_train_cpu_cap(STATE/'train_cpu_max.env')
    # The native loader uses the installed env cap. A smaller computed budget
    # is an admission refusal, never an implicit change to that loader setting.
    if budget['train_cpu_gib'] < configured_gib:
        raise RuntimeError('HOLD_INSTALLED_TRAIN_CPU_RAM_HEADROOM')
    budget['configured_train_cpu_gib'] = configured_gib
    # Owner readback 2026-11-19: existing nox-proxy listens on 8080, not 8081.
    # Fail closed on the serving route's actual /health; never start a new proxy.
    health_snapshot = helper.health()
    # A malformed native proxy reply is not proof of a healthy served chat.
    # In Python, 200.0 == 200: use strict integer shape before the HTTP gate.
    if type(health_snapshot) is not dict:
        raise RuntimeError('HOLD_CHAT_HEALTH_READBACK')
    status = health_snapshot.get('8080')
    # Native health reports connection errors as strings; preserve the
    # established unhealthy-chat HOLD. Only a spoofed 200-equivalent value
    # requires a separate schema HOLD rather than successful admission.
    if status == 200 and type(status) is not int:
        raise RuntimeError('HOLD_CHAT_HEALTH_READBACK')
    if status != 200:
        raise RuntimeError('HOLD_CHAT_HEALTH_BEFORE_TRAINING')
    return {'gpu1': gpu1, 'budget': budget}


def worker_readback(helper, fresh_after=0):
    path = ROOT/'status/agents_t856u.json'
    # The descriptor-bound reader already rejects non-object JSON roots.
    # Normalize only this known generic HOLD to the native-worker admission
    # code, so a malformed census has a single owner-specific failure reason.
    try:
        value, snapshot_mtime = read_json(path, include_mtime=True)
    except RuntimeError as exc:
        if str(exc) != 'HOLD_STATE_OBJECT_REQUIRED':
            raise
        raise RuntimeError('HOLD_NATIVE_WORKER_CAP_READBACK') from exc
    rows = value.get('workers', [])
    # A historical six-worker BOOST receipt is not a fresh native-worker census.
    # The pinned six-lane handoff observes exactly three physical workers; a
    # stale six-worker status must never be accepted as current admission.
    if type(rows) is not list or any(type(row) is not dict for row in rows):
        raise RuntimeError('HOLD_NATIVE_WORKER_CAP_READBACK')
    ids = [row.get('id') for row in rows]
    # External JSON IDs can be arrays, objects or booleans; set(ids) would
    # otherwise raise TypeError, and current_task without id raises KeyError.
    # Treat ambiguous owner identity as an explicit admission HOLD.
    claimed = []
    for row in rows:
        task = row.get('current_task')
        if task is None:
            continue
        if (type(task) is not dict or type(task.get('id')) is not str
                or not task['id'].strip()):
            raise RuntimeError('HOLD_NATIVE_WORKER_CAP_READBACK')
        claimed.append(task['id'])
    # A far-future file timestamp is not evidence of a current native owner.
    # Without an upper bound, stale worker IDs can remain 'fresh' indefinitely.
    now = time.time()
    if (snapshot_mtime < max(fresh_after, now-90)
            or snapshot_mtime > now + 5
            or type(value.get('n')) is not int or value['n'] != NATIVE_WORKER_CAP
            or len(rows) != NATIVE_WORKER_CAP
            or any(type(worker_id) is not str or not worker_id.strip()
                   for worker_id in ids)
            or len(set(ids)) != NATIVE_WORKER_CAP
            or len(set(claimed)) != len(claimed)):
        raise RuntimeError('HOLD_NATIVE_WORKER_CAP_READBACK')
    service = helper.service_state('nox-dispatcher-t855u')
    # An incomplete or malformed Supervisor response is not RUNNING proof.
    # Fail closed before accessing PID; do not leak KeyError/TypeError.
    if type(service) is not dict or service.get('state') != 'RUNNING':
        raise RuntimeError('HOLD_DISPATCHER_NOT_RUNNING')
    # RUNNING alone is not evidence of a live, identified dispatcher.
    # Supervisor may expose no PID or a malformed value during transitions.
    if type(service.get('pid')) is not int or service['pid'] <= 0:
        raise RuntimeError('HOLD_DISPATCHER_IDENTITY')
    return {'workers': NATIVE_WORKER_CAP, 'worker_ids': ids,
            'busy_count': len(claimed), 'claimed_task_ids': claimed,
            'dispatcher_pid': service['pid'], 'mtime': snapshot_mtime}


def stop_controller(helper, name, script):
    status = helper.service_state(name)
    # Do not treat a malformed Supervisor snapshot or bool/int-coerced PID
    # as evidence that this particular controller is safe to stop.
    if type(status) is not dict or status.get('state') != 'RUNNING':
        raise RuntimeError('HOLD_EXPECTED_CONTROLLER_NOT_RUNNING')
    if type(status.get('pid')) is not int or status['pid'] <= 0:
        raise RuntimeError('HOLD_CONTROLLER_IDENTITY')
    config = helper.program_config(name)
    argv = shlex.split(config.get('command', ''))
    bound = str(script) in argv
    for arg in argv:
        path = Path(arg)
        if (path.parent == Path('/opt/supervisor-scripts') and path.suffix == '.sh'
                and not path.is_symlink() and path.is_file() and path.stat().st_size < 32000
                and str(script) in path.read_text()):
            bound = True
    row = helper.process(status['pid'])
    if not bound or not row or row['service'] != name or str(script) not in row['argv']:
        raise RuntimeError('HOLD_CONTROLLER_IDENTITY')
    if config.get('stopasgroup', '').lower() == 'true' or config.get('killasgroup', '').lower() == 'true':
        # Group-stop must not act on an incomplete native process census.
        # bool is an int subclass: True is not process group 1.
        census = helper.process_table()
        if (type(census) is not dict or type(row.get('pgrp')) is not int
                or row['pgrp'] <= 0):
            raise RuntimeError('HOLD_CONTROLLER_PROCESS_GROUP_READBACK')
        group = []
        for item in census.values():
            if (type(item) is not dict or type(item.get('pgrp')) is not int
                    or item['pgrp'] <= 0 or type(item.get('state')) is not str):
                raise RuntimeError('HOLD_CONTROLLER_PROCESS_GROUP_READBACK')
            if item['pgrp'] == row['pgrp'] and item['state'] != 'Z':
                if type(item.get('service')) is not str:
                    raise RuntimeError('HOLD_CONTROLLER_PROCESS_GROUP_READBACK')
                group.append(item)
        if not group:
            raise RuntimeError('HOLD_CONTROLLER_PROCESS_GROUP_READBACK')
        if any(item['service'] != name for item in group):
            raise RuntimeError('HOLD_CONTROLLER_FOREIGN_PROCESS_GROUP')
    rc, _ = helper.command(['supervisorctl', 'stop', name], 75)
    # A successful supervisorctl command is not a verified controller stop.
    # Missing/malformed post-stop Supervisor state must fail closed, not raise
    # an unrelated KeyError/TypeError or count as an accepted stop.
    if rc:
        raise RuntimeError('HOLD_CONTROLLER_STOP_FAILED')
    final_status = helper.service_state(name)
    if (type(final_status) is not dict
            or final_status.get('state') not in ('STOPPED', 'EXITED')):
        raise RuntimeError('HOLD_CONTROLLER_STOP_FAILED')


def verify_policy(value):
    if (value.get('enabled') is not True or value.get('mode') != 'TASK_BOOST'
            or value.get('request') != BOOST_REQUEST or value.get('source_sha') != BOOST_SOURCE):
        raise RuntimeError('HOLD_NATIVE_BOOST_POLICY_CHANGED')


def verify_training_policy_owner(policy, admission):
    """Require owner-lineage identity on follow-up and continuation."""
    if (type(policy) is not dict or type(admission) is not dict
            or type(admission.get('request')) is not str
            or not re.fullmatch('[0-9]+', admission['request'])
            or type(admission.get('source_sha')) is not str
            or not re.fullmatch('[0-9a-f]{40}', admission['source_sha'])
            or policy.get('training_request') != admission['request']
            or policy.get('training_source_sha') != admission['source_sha']):
        raise RuntimeError('HOLD_TRAINING_POLICY_OWNER_MISMATCH')
    return True


def owned_flag(path, prefix):
    """Verify an owned STOP flag through one bounded, pathname-stable descriptor."""
    path = Path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except OSError as exc:
        raise RuntimeError('HOLD_CURRENT_OWNER_FLAG_CHANGED') from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 4096:
            raise RuntimeError('HOLD_CURRENT_OWNER_FLAG_CHANGED')
        with os.fdopen(fd, 'rb') as stream:
            fd = -1
            raw = stream.read(4097)
            after = os.fstat(stream.fileno())
            named = os.stat(path, follow_symlinks=False)
        # A matching hash prefix is not ownership: require a token boundary.
        identity = prefix.encode('utf-8') if isinstance(prefix, str) else b''
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if (len(raw) != before.st_size
                or any(getattr(before, field) != getattr(after, field)
                       or getattr(before, field) != getattr(named, field)
                       for field in fields)
                or not identity or not raw.startswith(identity)
                or raw[len(identity):len(identity) + 1] not in (b'', b' ', b'\n', b'\r')):
            raise RuntimeError('HOLD_CURRENT_OWNER_FLAG_CHANGED')
    except (OSError, UnicodeError) as exc:
        raise RuntimeError('HOLD_CURRENT_OWNER_FLAG_CHANGED') from exc
    finally:
        if fd >= 0:
            os.close(fd)


def verify_paused_result(helper, result, max_step=5, allow_completed=False):
    """A user/media pause is evidence only after its checkpoint is rehashed."""
    step = result.get('global_step')
    allowed_states = ('CHECKPOINTED_OWNER_STOP', 'VERIFIED_BOUNDED_ADAPTER_UPDATE') if allow_completed else ('CHECKPOINTED_OWNER_STOP',)
    if (result.get('state') not in allowed_states or result.get('native_sha256') != NATIVE_SHA
            or type(step) is not int or not 1 <= step <= max_step
            or type(result.get('successful_optimizer_steps')) is not int
            or not 1 <= result['successful_optimizer_steps'] <= step
            # During the initial bounded 1..5 step run, each global step must
            # correspond to an independently reported optimizer update. A
            # resumed 1000-step lineage may carry a per-run delta instead.
            or (not allow_completed and result['successful_optimizer_steps'] != step)
            or result.get('adapter_delta_verified') is not True
            or type(result.get('loss')) not in (int, float) or not math.isfinite(result['loss'])
            # Bounded cross-entropy is nonnegative; a signed checkpoint
            # cannot prove valid optimizer loss with a finite negative value.
            or result['loss'] < 0):
        raise RuntimeError('HOLD_PAUSED_OPTIMIZER_RECEIPT')
    before, after = result.get('before_tensor_sha256'), result.get('after_tensor_sha256')
    if any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value) for value in (before, after)) or before == after:
        raise RuntimeError('HOLD_PAUSED_ADAPTER_DELTA')
    checkpoint = result.get('checkpoint', {})
    path = OUTPUT/('checkpoint-'+str(step))
    if not isinstance(checkpoint, dict):
        raise RuntimeError('HOLD_PAUSED_CHECKPOINT_SCOPE')
    hashes = checkpoint.get('files_sha256', {})
    if (checkpoint.get('path') != str(path) or type(checkpoint.get('global_step')) is not int
            or checkpoint['global_step'] != step or not isinstance(hashes, dict)
            or path.is_symlink() or any(parent.is_symlink() for parent in path.parents)
            or set(hashes) != set(helper.CHECKPOINT_NAMES)):
        raise RuntimeError('HOLD_PAUSED_CHECKPOINT_SCOPE')
    if any(file_sha(path/name) != hashes[name] for name in helper.CHECKPOINT_NAMES):
        raise RuntimeError('HOLD_PAUSED_CHECKPOINT_HASH')
    state = read_json(path/'trainer_state.json', expected_sha256=hashes['trainer_state.json'])
    if type(state.get('global_step')) is not int or state['global_step'] != step:
        raise RuntimeError('HOLD_PAUSED_CHECKPOINT_STEP')
    return True


def continuation_terminal_state(terminal):
    """Never label an owner-paused checkpoint as completed solely by step."""
    if (terminal.get('state') == 'VERIFIED_BOUNDED_ADAPTER_UPDATE'
            and type(terminal.get('global_step')) is int
            and terminal['global_step'] == 1000):
        return 'CONTINUATION_TARGET_1000_COMPLETED'
    return 'CONTINUATION_CHECKPOINTED_BY_OWNER_PAUSE'


def main():
    helper = load_helper()
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not request.isdigit() or not re.fullmatch('[0-9a-f]{40}', source):
        raise RuntimeError('HOLD_OWNER_REQUEST_CONTEXT')
    receipt_path = STATE/('owner_maintenance_'+request+'.json')
    if receipt_path.exists():
        raise RuntimeError('HOLD_REQUEST_ALREADY_STARTED_INSPECT_RECEIPT')
    fd = os.open(STATE/'owner_maintenance.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    lock_held = True
    result = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'boost_request': BOOST_REQUEST,
              'started': time.time(), 'steps': [], 'training_started': False, 'optimizer_steps_verified': False,
              'weights_deleted': 0, 's03_modified': False, 'chat_before': helper.health()}
    backups = ROOT/'backup/owner_training_resume'/request
    controllers_stopped = []
    success = False
    pointer = None
    expected = {}
    upgrade_evidence = None
    memory_evidence = None
    media_evidence = None

    def save():
        helper.atomic(receipt_path, json.dumps(result, indent=2).encode())

    def step(kind, data):
        result['steps'].append({'kind': kind, 'data': data, 'time': time.time()})
        save(); helper.emit(kind, data)

    def backup(path, expected_sha256=None):
        destination = backups/str(path).lstrip('/')
        if destination.exists() or path.is_symlink():
            raise RuntimeError('HOLD_SOURCE_BACKUP_COLLISION')
        data = stable_backup_bytes(path, expected_sha256)
        helper.atomic(destination, data)

    def install(path, data):
        old = file_sha(path)
        if old != expected[path]:
            raise RuntimeError('HOLD_INSTALLED_TRAINING_SOURCE_CHANGED')
        backup(path, expected[path]); helper.atomic(path, data); os.chmod(path, 0o755)
        expected[path] = hashlib.sha256(data).hexdigest()
        step('source_installed', {'path': str(path), 'before': old, 'after': expected[path]})

    def release_flags(prefix, pause_required=False):
        hold = STATE/'TRAIN_HOLD.flag'
        pause = STATE/'TRAIN_PAUSE_REQUEST.flag'
        owned_flag(hold, prefix)
        if pause.exists() or pause.is_symlink() or pause_required:
            owned_flag(pause, prefix)
        if global_stop():
            raise RuntimeError('HOLD_GLOBAL_STOP_REMAINS')
        for path in (hold, pause):
            if not path.exists():
                continue
            # Move proven owned flags into private durable backup; no deletion.
            target = backups/('released_'+str(time.time_ns())+'_'+path.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            path.rename(target)
        step('owned_training_flags_released', {'backed_up': True})

    def publish_admission(max_steps):
        nonlocal pointer
        pointer = {'schema': 'NOX_OWNER_TRAINING_ADMISSION_V1', 'request': request, 'source_sha': source,
                   'boost_request': BOOST_REQUEST, 'wrapper_request': request, 'max_steps': max_steps,
                   'resume': max_steps == 1000, 'dispatcher_upgrade': upgrade_evidence,
                   's03_activation': memory_evidence,
                   'media_acceptance': media_evidence,
                   'sources': {str(path): sha for path, sha in expected.items()}}
        result['admitted_sources'] = pointer['sources']; result['admission'] = pointer
        save(); helper.atomic(POINTER, json.dumps(pointer, indent=2).encode())

    def start_once(max_steps):
        # STOP can be asserted after the earlier resource/flag admission.
        # Recheck at the last owner-controlled point before starting training.
        if global_stop():
            raise RuntimeError('HOLD_GLOBAL_STOP_REMAINS')
        rc, _ = helper.command(['supervisorctl', 'start', SERVICE], 35)
        # RUNNING may describe an older service, not this failed start.
        # A nonzero supervisor exit cannot establish a fresh native launch.
        if rc != 0:
            raise RuntimeError('HOLD_SINGLE_TRAINER_START_FAILED')
        # Supervisor can report STARTING before the native ENTRY process exists.
        # A successful start command is not a process identity proof; allow one
        # bounded transition to RUNNING, without sending a second start command.
        # A successful supervisorctl start is not proof of a well-shaped
        # Supervisor readback; reject invalid states before any identity claim.
        def read_start_status():
            status = helper.service_state()
            if type(status) is not dict or type(status.get('state')) is not str:
                raise RuntimeError('HOLD_NEW_TRAINER_STATUS_READBACK')
            return status

        status = read_start_status()
        if status['state'] == 'STARTING':
            deadline = time.monotonic() + 15
        while status['state'] == 'STARTING':
            if global_stop():
                raise RuntimeError('HOLD_GLOBAL_STOP_REMAINS')
            if time.monotonic() >= deadline:
                raise RuntimeError('HOLD_SINGLE_TRAINER_START_TIMEOUT')
            time.sleep(0.5)
            status = read_start_status()
        if global_stop():
            raise RuntimeError('HOLD_GLOBAL_STOP_REMAINS')
        if status['state'] != 'RUNNING':
            raise RuntimeError('HOLD_SINGLE_TRAINER_START_FAILED')
        identity = prove_training(helper)
        result['training_started'] = True
        step('single_native_training_started', {'rc': rc, 'service': status, 'process': identity,
             'max_steps': max_steps, 'planned_steps': 1000, 'shared_gpu1_lease': 'forge_training.lock'})

    save()
    try:
        expected = boost_pins(read_json(STATE/('owner_maintenance_'+BOOST_REQUEST+'.json')))
        upgrade_pins, upgrade_evidence = dispatcher_upgrade_evidence()
        expected.update(upgrade_pins)
        result['dispatcher_upgrade'] = upgrade_evidence
        memory_pins, memory_evidence = s03_activation_evidence(upgrade_evidence)
        expected.update(memory_pins)
        result['s03_activation'] = memory_evidence
        # The immutable media proof is carried forward. Rehash these small
        # output files on initial admission; subsequent continuation depends on
        # its sealed lineage and current GPU lease, not indefinite sample retention.
        media_evidence = media_acceptance_evidence(upgrade_evidence, rehash_outputs=not POINTER.exists())
        result['media_acceptance'] = media_evidence
        policy = read_json(POLICY, 16000); verify_policy(policy)
        followup = POINTER.exists()
        if followup:
            pointer = read_json(POINTER, 32000)
            if (pointer.get('schema') != 'NOX_OWNER_TRAINING_ADMISSION_V1'
                    or pointer.get('boost_request') != BOOST_REQUEST
                    or not str(pointer.get('request', '')).isdigit()
                    or not re.fullmatch('[0-9a-f]{40}', pointer.get('source_sha', ''))):
                raise RuntimeError('HOLD_PREVIOUS_TRAINING_ADMISSION')
            verify_training_policy_owner(policy, pointer)
            previous = read_json(STATE/('owner_maintenance_'+pointer['request']+'.json'))
            if (previous.get('schema') != SCHEMA or previous.get('source_sha') != pointer['source_sha']
                    or previous.get('admission') != pointer or policy.get('training_allowed') is not True
                    or policy.get('training_service') != SERVICE
                    or pointer.get('dispatcher_upgrade') != upgrade_evidence
                    or previous.get('dispatcher_upgrade') != upgrade_evidence
                    or pointer.get('s03_activation') != memory_evidence
                    or previous.get('s03_activation') != memory_evidence
                    or pointer.get('media_acceptance') != media_evidence
                    or previous.get('media_acceptance') != media_evidence
                    or set(pointer.get('sources', {})) != {str(path) for path in expected}):
                raise RuntimeError('HOLD_PREVIOUS_TRAINING_RECEIPT')
            allowed_changes = set(CONTROLS) | {WRAPPER}
            for path in expected:
                recorded = pointer.get('sources', {}).get(str(path))
                if path not in allowed_changes and recorded != expected[path]:
                    raise RuntimeError('HOLD_PREVIOUS_ADMISSION_STABLE_SOURCE')
                if not isinstance(recorded, str) or not re.fullmatch('[0-9a-f]{64}', recorded):
                    raise RuntimeError('HOLD_PREVIOUS_ADMISSION_SOURCE_HASH')
                expected[path] = recorded
        for path, sha in expected.items():
            if file_sha(path) != sha:
                raise RuntimeError('HOLD_INSTALLED_TRAINING_SOURCE_CHANGED')
        if file_sha(TRAINER) != NATIVE_SHA:
            raise RuntimeError('HOLD_NATIVE_TRAIN_SOURCE_CHANGED')
        config = helper.program_config(SERVICE)
        if shlex.split(config.get('command', '')) != ['/bin/bash', str(WRAPPER)]:
            raise RuntimeError('HOLD_TRAIN_SUPERVISOR_COMMAND')
        if global_stop():
            raise RuntimeError('HOLD_GLOBAL_STOP_REMAINS')
        if not (STATE/'train_wants_gpu1').is_file():
            raise RuntimeError('HOLD_TEACHER_RESERVATION_MISSING')
        active_heavy = [name for name in helper.HEAVY_SERVICES if helper.service_state(name)['state'] not in STOPPED]
        if active_heavy:
            raise RuntimeError('HOLD_LEGACY_HEAVY_SERVICE_REACTIVATED')
        result['native_workers'] = worker_readback(helper)
        if not followup:
            prefix = 'OWNER_REQUESTED_TRAINING_HALT request='+helper.HALT_REQUEST+' source='+helper.HALT_SOURCE
            owned_flag(STATE/'TRAIN_HOLD.flag', prefix); owned_flag(STATE/'TRAIN_PAUSE_REQUEST.flag', prefix)
            if file_sha(STATE/'TRAIN_HOLD.flag') != upgrade_evidence['training_hold_sha256']:
                raise RuntimeError('HOLD_TRAINING_FLAG_CHANGED_AFTER_DISPATCHER_UPGRADE')
            halt = read_json(STATE/('owner_maintenance_'+helper.HALT_REQUEST+'.json'))
            if halt.get('source_sha') != helper.HALT_SOURCE or halt.get('halt_verified') is not True:
                raise RuntimeError('HOLD_ORIGINAL_HALT_RECEIPT')
            if OUTPUT.exists():
                raise RuntimeError('HOLD_EXISTING_HYBRID_OUTPUT_INSPECT_FIRST')
            admission = resource_admission(helper); step('native_resource_admission', admission)
            # Render only the exact, stable source preimage already admitted above.
            # A later pathname read must not silently rebound to foreign code.
            changed = {
                path: patch_permission(
                    stable_backup_bytes(path, expected[path]).decode('utf-8'),
                    request, source, path.name == 'nox_selfheal.py'
                ).encode('utf-8')
                for path in CONTROLS
            }
            # Maintenance gates new claims; let already claimed CPU jobs finish.
            deadline = time.monotonic()+45
            while worker_readback(helper)['busy_count'] and time.monotonic() < deadline:
                # STOP may latch while existing native claims drain; never
                # perform maintenance after a newly asserted global STOP.
                if global_stop():
                    raise RuntimeError('HOLD_GLOBAL_STOP_REMAINS')
                time.sleep(2)
            if worker_readback(helper)['busy_count']:
                raise RuntimeError('HOLD_DISPATCHER_BUSY_DRAIN_REQUIRED')
            # Also fence STOP asserted exactly as the final worker goes idle.
            if global_stop():
                raise RuntimeError('HOLD_GLOBAL_STOP_REMAINS')
            for name, script in CONTROLLER_SERVICES.items():
                stop_controller(helper, name, script); controllers_stopped.append(name)
            for path, data in changed.items():
                install(path, data)
            install(WRAPPER, helper.wrapper_source(request).encode())
            if helper.command(['bash', '-n', str(WRAPPER)])[0]:
                raise RuntimeError('HOLD_WRAPPER_SYNTAX')
            backup(POLICY, file_sha(POLICY))
            policy.update(training_allowed=True, training_service=SERVICE,
                          training_request=request, training_source_sha=source,
                          training_gpu=1, training_planned_steps=1000,
                          training_gpu_lease='forge_training.lock', legacy_heavy_services_allowed=False)
            helper.atomic(POLICY, json.dumps(policy, indent=2).encode())
            for name in list(controllers_stopped):
                rc, _ = helper.command(['supervisorctl', 'start', name], 30)
                if rc:
                    raise RuntimeError('HOLD_CONTROLLER_RESTART')
                # A malformed Supervisor snapshot cannot certify controller recovery.
                restart_snapshot = helper.service_state(name)
                if (type(restart_snapshot) is not dict
                        or restart_snapshot.get('state') not in ('RUNNING', 'STARTING')):
                    raise RuntimeError('HOLD_CONTROLLER_RESTART')
                controllers_stopped.remove(name)
            # Recheck resources after configuration while admissions remain held.
            resource_admission(helper)
            publish_admission(5)
            release_flags(prefix, pause_required=True)
            start_once(5)
        elif helper.service_state()['state'] in ('RUNNING', 'STARTING'):
            identity = prove_existing_training(helper)
            result['training_started'] = True
            step('existing_single_training_observed', identity)
        elif not (OUTPUT/'owner_last_result.json').is_file():
            raise RuntimeError('HOLD_EXISTING_RUN_TERMINAL_WITHOUT_PROOF')
        # CPU work and media admission continue while observation is read-only.
        fcntl.flock(fd, fcntl.LOCK_UN); lock_held = False
        result['state'] = 'BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING'; save()
        if pointer.get('max_steps') == 1000:
            if helper.service_state()['state'] in ('RUNNING', 'STARTING'):
                result['continuation_process'] = prove_existing_training(helper)
                result['state'] = 'EXISTING_CONTINUATION_RUNNING'; success = True
            else:
                terminal = read_json(OUTPUT/'owner_last_result.json')
                verify_paused_result(helper, terminal, max_step=1000, allow_completed=True)
                if terminal['global_step'] <= 5 or terminal.get('requested_step') != 1000:
                    raise RuntimeError('HOLD_STALE_FIRST_FIVE_RECEIPT_AFTER_CONTINUATION')
                if terminal['state'] == 'VERIFIED_BOUNDED_ADAPTER_UPDATE' and terminal['global_step'] != 1000:
                    raise RuntimeError('HOLD_CONTINUATION_TARGET_NOT_REACHED')
                result['continuation_terminal_receipt'] = terminal
                result['state'] = continuation_terminal_state(terminal)
                success = True
        else:
            deadline = time.monotonic()+400; candidate = None; previous_progress = None
            while time.monotonic() < deadline:
                status = helper.service_state()
                terminal = OUTPUT/'owner_last_result.json'
                if terminal.is_file():
                    candidate = read_json(terminal)
                    if candidate.get('state') == 'CHECKPOINTED_OWNER_STOP':
                        verify_paused_result(helper, candidate)
                        result['state'] = 'TRAINING_CHECKPOINTED_BY_NEW_PAUSE'; result['checkpointed_result'] = candidate
                        success = True; break
                    helper.verify_five_result(candidate)
                    result['five_step_receipt'] = candidate; result['optimizer_steps_verified'] = True
                    step('five_steps_independently_verified', {'global_step': 5, 'finite_loss': candidate['loss'],
                         'adapter_tensor_changed': True, 'seven_checkpoint_hashes_verified': True})
                    break
                observed = helper.progress()
                if observed != previous_progress:
                    step('native_training_progress', observed); previous_progress = observed
                if status['state'] in STOPPED:
                    raise RuntimeError('HOLD_TRAINER_EXITED_WITHOUT_OPTIMIZER_PROOF')
                time.sleep(8)
            if not candidate:
                prove_training(helper)
                result['state'] = 'BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING'; success = True
            elif result['optimizer_steps_verified']:
                deadline = time.monotonic()+40
                while helper.service_state()['state'] in ('RUNNING', 'STARTING') and time.monotonic() < deadline:
                    time.sleep(2)
                # A media/owner operation may now own maintenance. Leave the
                # verified five-step checkpoint available instead of racing it.
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); lock_held = True
                except BlockingIOError:
                    result['state'] = 'FIVE_STEPS_VERIFIED_CONTINUATION_DEFERRED'; success = True
                if lock_held:
                    resource_admission(helper)
                    current_policy = read_json(POLICY, 16000); verify_policy(current_policy)
                    if current_policy.get('training_allowed') is not True or current_policy.get('training_service') != SERVICE:
                        raise RuntimeError('HOLD_NEW_TRAINING_POLICY')
                    verify_training_policy_owner(current_policy, pointer)
                    for path, sha in expected.items():
                        if file_sha(path) != sha:
                            raise RuntimeError('HOLD_SOURCE_CHANGED_DURING_TRAINING')
                    prefix = 'OWNER_HYBRID_BOUNDED_COMPLETE request='+pointer['wrapper_request']
                    owned_flag(STATE/'TRAIN_HOLD.flag', prefix)
                    if (STATE/'TRAIN_PAUSE_REQUEST.flag').exists() or (STATE/'TRAIN_PAUSE_REQUEST.flag').is_symlink():
                        result['state'] = 'FIVE_STEPS_VERIFIED_OWNER_PAUSE_RETAINED'; success = True
                    else:
                        # Keep initial and continuation wrapper backups distinct.
                        # Bind the five-step wrapper backup to the original admitted bytes.
                        # The earlier source sweep cannot authorize a later raw pathname read.
                        helper.atomic(backups/'first_five_wrapper.sh',
                                      stable_backup_bytes(WRAPPER, expected[WRAPPER]))
                        data = helper.wrapper_source(request, 1000, True).encode()
                        helper.atomic(WRAPPER, data); os.chmod(WRAPPER, 0o755)
                        expected[WRAPPER] = hashlib.sha256(data).hexdigest()
                        publish_admission(1000)
                        release_flags(prefix)
                        start_once(1000)
                        result['state'] = 'FIVE_STEPS_VERIFIED_CONTINUATION_STARTED'
                        result['continuation_target_steps'] = 1000; success = True
                    fcntl.flock(fd, fcntl.LOCK_UN); lock_held = False
    except Exception as exc:
        code = str(exc)
        result['state'] = 'HOLD_TRAINING_RESUME'
        result['error'] = code if re.fullmatch('HOLD_[A-Z0-9_]+', code) else type(exc).__name__
        # Mutate flags only with the shared writer lock. Never kill a running
        # trainer: its existing callback checkpoints a newly latched HOLD.
        if lock_held and not (STATE/'TRAIN_HOLD.flag').exists():
            helper.atomic(STATE/'TRAIN_HOLD.flag', ('OWNER_TRAINING_RESUME_FAILED request='+request+'\n').encode())
    finally:
        if lock_held:
            try:
                for name in controllers_stopped:
                    try:
                        before_restore = helper.service_state(name)
                        # A malformed/future Supervisor state is not evidence
                        # that this controller is safe or already restored.
                        if (type(before_restore) is not dict
                                or before_restore.get('state') not in
                                ('STOPPED', 'EXITED', 'RUNNING', 'STARTING')):
                            raise RuntimeError('HOLD_CONTROLLER_RESTORE_READBACK')
                        if before_restore['state'] in ('STOPPED', 'EXITED'):
                            rc, _ = helper.command(['supervisorctl', 'start', name], 30)
                            if rc:
                                raise RuntimeError('HOLD_CONTROLLER_RESTORE_FAILED')
                            after_restore = helper.service_state(name)
                            if (type(after_restore) is not dict
                                    or after_restore.get('state') not in ('RUNNING', 'STARTING')):
                                raise RuntimeError('HOLD_CONTROLLER_RESTORE_READBACK')
                            result['steps'].append({'kind': 'controller_restored',
                                'data': {'name': name, 'rc': rc}, 'time': time.time()})
                    except Exception as exc:
                        # A restoration failure must not mask the owner receipt
                        # or leave the shared maintenance lock held indefinitely.
                        reason = str(exc)
                        if not re.fullmatch('HOLD_[A-Z0-9_]+', reason):
                            reason = 'HOLD_CONTROLLER_RESTORE_READBACK'
                        result['steps'].append({'kind': 'controller_restore_hold',
                            'data': {'name': name, 'error': reason}, 'time': time.time()})
                        result['restore_error'] = reason
                        result['state'] = 'HOLD_TRAINING_RESUME'
                        success = False
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN); lock_held = False
        result.update(finished=time.time(), service_after=helper.service_state(),
                      hold_retained=(STATE/'TRAIN_HOLD.flag').exists(),
                      pause_retained=(STATE/'TRAIN_PAUSE_REQUEST.flag').exists(),
                      chat_after=helper.health(), gpu_after=helper.gpu(), progress_after=helper.progress())
        try:
            result['native_workers_after'] = worker_readback(helper)
        except Exception as exc:
            result['native_workers_readback_error'] = str(exc) if str(exc).startswith('HOLD_') else type(exc).__name__
        # Use the live serving proxy on 8080 for the final receipt too; 8081
        # is a retired endpoint and must not turn healthy serving into failure.
        if result['chat_after'].get('8080') != 200:
            result['chat_health_regression'] = True; success = False
        save(); helper.emit('native_training_resume_receipt', result); os.close(fd)
    if success:
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        code = str(exc)
        reason = code if re.fullmatch('HOLD_[A-Z0-9_]+', code) else type(exc).__name__
        print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'failure', 'data': reason}), flush=True)
        raise SystemExit(2)
