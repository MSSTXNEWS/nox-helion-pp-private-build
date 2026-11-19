#!/usr/bin/env python3
"""Observe only the live Forge preimage and I-39 verifier registration."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat


ROOT = Path('/root/nox')
CONFIG = 'config/owner_native_subagents.json'
WORKSPACE = 'projects/owner_executor/source_workspace'
BOOTSTRAP = 'NOX_EXECUTOR_BOOTSTRAP.json'
FORGE = 'forge_split_guard.py'
VERIFIER = 'test_forge_source_minhash.py'
VERIFIER_SHA = 'dda57a0e6d13275dcb4ec5934358df217630f8a2b3f425265e26ad70aa322ecc'
KNOWN_FORGE = {
    '30677e7012b3d266cc98425d89df25814e6b38f4d840e6fd0f883b77f6703f35': 'PRIVATE_I39_BASE',
    '82969cfb2b02939cfe60c6fbd62ab921754e5f61ff96183ccea53ddcc40cc9fb': 'REVIEWED_FORGE_BUDGET_POSTIMAGE',
}
MARKER = 'NOX_MAINT_REFLEX_RESTORE='


class Hold(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise Hold('HOLD_I39_CENSUS_' + reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def stable_read(path, limit):
    """Use the existing observer's anchored, bounded O_NOFOLLOW read pattern."""
    require(path.is_absolute(), 'PATH_SCOPE')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            current = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=parent)
            os.close(parent)
            parent = current
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'FILE_BOUND')
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            require(len(raw) == before.st_size and stamp(before) == stamp(after) == stamp(named),
                    'FILE_CHANGED')
            return raw, stamp(after)
    finally:
        os.close(parent)


def optional_read(path, limit):
    try:
        return stable_read(path, limit)
    except FileNotFoundError:
        return None


def read_snapshot(root):
    workspace = root / WORKSPACE
    return {
        CONFIG: stable_read(root / CONFIG, 2 * 1024 * 1024),
        BOOTSTRAP: stable_read(workspace / BOOTSTRAP, 64 * 1024),
        FORGE: stable_read(workspace / FORGE, 2 * 1024 * 1024),
        VERIFIER: optional_read(workspace / VERIFIER, 64 * 1024),
    }


def observe(root=ROOT):
    data = read_snapshot(root)
    require(read_snapshot(root) == data, 'OBSERVED_DRIFT')
    workspace = str(root / WORKSPACE)
    configuration = json.loads(data[CONFIG][0])
    project = configuration.get('project_executor', {}).get('roots', {}).get('NOX_PROJECT_SOURCE', {})
    require(configuration.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
            and configuration.get('instance_id') == 60509551
            and configuration.get('owner_authorized') is True
            and project.get('integration_kind') == 'SOURCE_WORKSPACE'
            and project.get('path') == workspace, 'OWNER_SOURCE_SCOPE')
    allowed = project.get('allowed_paths')
    marker = json.loads(data[BOOTSTRAP][0])
    pins = marker.get('file_pins')
    refs = marker.get('source_refs')
    require(isinstance(allowed, list) and 1 <= len(allowed) <= 256
            and all(isinstance(path, str) for path in allowed) and len(set(allowed)) == len(allowed)
            and FORGE in allowed and isinstance(pins, dict) and set(pins) == set(allowed)
            and all(isinstance(pin, str) and re.fullmatch(r'[0-9a-f]{64}', pin) for pin in pins.values())
            and isinstance(refs, list) and marker.get('source_file_count') == len(allowed)
            and marker.get('schema') == 'NOX_PROJECT_SOURCE_BOOTSTRAP_RECEIPT_V1'
            and marker.get('root') == workspace, 'BOOTSTRAP_SCOPE')
    require(marker.get('manifest_sha256') == sha(canonical({
        'schema': 'NOX_PROJECT_SOURCE_BASELINE_V1', 'files': pins, 'source_refs': refs,
    })), 'BOOTSTRAP_MANIFEST')
    forge_sha = sha(data[FORGE][0])
    registered = VERIFIER in pins
    verifier_sha = sha(data[VERIFIER][0]) if data[VERIFIER] is not None else None
    return {
        'schema': 'NOX_I39_PREUPGRADE_CENSUS_V1', 'state': 'OBSERVED_TWO_STABLE_READS',
        'read_only': True, 'full_workspace_census': False, 'atomic_snapshot': False,
        'config_sha256': sha(data[CONFIG][0]), 'bootstrap_sha256': sha(data[BOOTSTRAP][0]),
        'bootstrap_manifest_sha256': marker['manifest_sha256'], 'allowed_count': len(allowed),
        'forge_sha256': forge_sha, 'forge_baseline_sha256': pins[FORGE],
        'forge_known_preimage': KNOWN_FORGE.get(forge_sha, 'UNKNOWN_REVIEW_REQUIRED'),
        'verifier_allowlisted': registered, 'verifier_sha256': verifier_sha,
        'verifier_bootstrap_sha256': pins.get(VERIFIER),
        'exact_i39_verifier_registered': registered and pins[VERIFIER] == verifier_sha == VERIFIER_SHA,
        'original_task_accepted': False,
    }


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    try:
        require(os.geteuid() == 0 and re.fullmatch(r'[1-9][0-9]{0,23}', request)
                and re.fullmatch(r'[0-9a-f]{40}', source), 'OWNER_CONTEXT')
        result = observe()
    except (Hold, OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        reason = str(exc) if isinstance(exc, Hold) else 'HOLD_I39_CENSUS_UNAVAILABLE'
        print(MARKER + json.dumps({'schema': 'NOX_I39_PREUPGRADE_CENSUS_V1', 'state': reason,
                                  'read_only': True}), flush=True)
        return 2
    print(MARKER + json.dumps({**result, 'request': request, 'source_sha': source}), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
