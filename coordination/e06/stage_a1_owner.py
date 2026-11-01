"""A.1 source staging into the EXISTING EXPRESS INTEGRATOR OneHost.

This does not launch internet requests, native models or a second Python host.
All staged sources are exact, immutable Git blobs pinned by the single I0 owner.
Apply only to disposable Windows build staging, never the original NOX archive.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name('A1_BUILD_SOURCES.lock.json')
_SHA = re.compile(r'[0-9a-f]{40}\Z')
_BASE = 'src/nox_selfbuilder/'
REQUIRED = (
    'worms.py', 'worm_providers.py', 'worm_idea_loop.py',
    'growth_sandbox.py', 'growth_forge.py', 'worm_autopilot.py',
    'a1_initiative_bridge.py', 'a1_official_catalog.py',
    'firstboot_coordinator.py', 'acquisition_library.py',
)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def regular_owned(path: Path, base: Path) -> None:
    try:
        if not path.absolute().is_relative_to(base.absolute()):
            raise ValueError('A1_STAGE_OUTSIDE_OWNER_ROOT')
        curr = path.absolute()
        while curr != base.absolute():
            try:
                info = curr.lstat()
            except FileNotFoundError:
                curr = curr.parent
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('A1_STAGE_REPARSE_OR_SYMLINK_HOLD')
            curr = curr.parent
    except (OSError, RuntimeError) as exc:
        raise ValueError('A1_STAGE_PATH_INSPECTION_HOLD') from exc


def stage(source: Path, *, repo: Path = ROOT, manifest_path: Path = MANIFEST) -> dict:
    repo = repo.resolve(strict=True)
    source = source.resolve(strict=True)
    if source == repo or source.is_relative_to(repo / 'src') or source.is_relative_to(repo / 'coordination'):
        raise ValueError('A1_DISPOSABLE_STAGE_REQUIRED')
    if not source.is_dir():
        raise ValueError('A1_STAGE_DIRECTORY_REQUIRED')
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    if data.get('schema') != 'NOX-A1-ONEHOST-STAGE-LOCK-v1' or set(data.get('sources', {})) != set(REQUIRED):
        raise ValueError('A1_EXACT_TEN_SOURCE_LOCK_REQUIRED')
    staged = []
    # Validate every source/destination before writing even the first byte.
    for name in REQUIRED:
        expected = data['sources'][name]
        if not isinstance(expected, str) or not _SHA.fullmatch(expected):
            raise ValueError('A1_GIT_BLOB_PIN_REQUIRED')
        rel = _BASE + name
        src = repo / rel
        target = source / 'nox_selfbuilder' / name
        regular_owned(src, repo)
        regular_owned(target, source)
        if not src.is_file() or not stat.S_ISREG(src.stat().st_mode):
            raise ValueError('A1_SOURCE_REGULAR_FILE_REQUIRED')
        if target.exists() or target.is_symlink():
            raise ValueError('A1_STAGE_DUPLICATE_OWNER_OR_FILE_HOLD')
        payload = src.read_bytes()
        if b'\x00' in payload or len(payload) > 256_000 or git_blob(payload) != expected:
            raise ValueError('A1_EXACT_GIT_SOURCE_SHA_HOLD:' + name)
        compile(payload, str(src), 'exec')
        staged.append((target, payload, name))
    created = []
    try:
        for target, payload, _name in staged:
            target.parent.mkdir(parents=True, exist_ok=True)
            regular_owned(target, source)
            with target.open('xb') as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            created.append(target)
            if target.read_bytes() != payload:
                raise ValueError('A1_STAGE_SOURCE_READBACK_HOLD')
    except BaseException:
        # Never remove unrelated files; remove only exact bytes just created.
        for target, payload, _name in reversed(staged):
            if target in created and target.is_file() and not target.is_symlink():
                if target.read_bytes() == payload:
                    target.unlink()
        raise
    return {
        'schema': 'NOX-A1-ONEHOST-SOURCE-STAGE-v1',
        'source_count': len(staged),
        'runtime_data_files': [
            {'source': _BASE+name, 'runtime_path': 'nox_selfbuilder/'+name,
             'sha256': hashlib.sha256(payload).hexdigest(),
             'pyinstaller_destination': 'nox_selfbuilder'}
            for _target, payload, name in staged],
        'native_activation_verified': False,
        'installed_exe_accepted': False,
        'model_weights_installed': False,
    }


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('USAGE: stage_a1_owner.py DISPOSABLE_ORIGINAL_PYTHON_SOURCE')
    print(json.dumps(stage(Path(sys.argv[1])), sort_keys=True))
