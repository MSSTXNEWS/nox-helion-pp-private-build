#!/usr/bin/env python3
"""V34 real-file source stage, never deploy or overwrite production.

On actual Japanese host: stage beside installed NOX, snapshot source fingerprints,
verify original P02 seam and V34 trained weight files. No remote access assumed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
P02_SUBPATH = 'Packages/P02/worker-python/p02_chat_bridge.py'
ONEHOST_SUBPATH = 'Packages/P02/worker-python/p02_onehost.py'


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for x in iter(lambda: f.read(1024*1024), b''):
            h.update(x)
    return h.hexdigest()


def stage(*, nox_root, stage_root):
    old, dest = Path(nox_root).resolve(), Path(stage_root).resolve()
    if not old.is_dir() or not dest.parent.is_dir():
        raise RuntimeError('EXISTING_NOX_AND_STAGING_PARENT_REQUIRED')
    if old == dest or old in dest.parents or dest in old.parents:
        raise RuntimeError('STAGING_MUST_BE_SEPARATE_FROM_ACTIVE_NOX')
    if dest.exists():
        raise RuntimeError('STAGING_ALREADY_EXISTS_NO_OVERWRITE')
    p02 = sorted(old.rglob('p02_chat_bridge.py'))
    onehost = sorted(old.rglob('p02_onehost.py'))
    if not p02 or not onehost:
        raise RuntimeError('NATIVE_ONEHOST_P02_MISSING')
    for filename in ('brain_weights/router.safetensors', 'brain_weights/assoc_v33.safetensors',
                     'brain/neural_s03_live_v34.py', 'brain/forge_bridge_v34.py'):
        if not (ROOT / filename).is_file():
            raise RuntimeError('SOURCE_MISSING:' + filename)
    expected = ROOT / 'source_v29' / 'inherited_native_pr162' / P02_SUBPATH
    # If active P02 is different from the source-locked baseline, stage code but
    # explicitly require contract review before integration.
    p02_drift = bool(expected.is_file() and sha(expected) != sha(p02[0]))
    dest.mkdir(parents=False)
    for folder in ('brain', 'brain_weights', 'web'):
        shutil.copytree(ROOT / folder, dest / folder,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('READ_ME_V34_RU.md', 'RUN_CHECK_V34.ps1', 'RUN_CHECK_V34.sh'):
        shutil.copy2(ROOT / name, dest / name)
    fingerprint = {str(f.relative_to(dest)): sha(f) for f in sorted(dest.rglob('*')) if f.is_file()}
    status = {
        'state': 'SOURCE_STAGED_NOT_DEPLOYED', 'source_root': str(old), 'staging_root': str(dest),
        'stage_file_count': len(fingerprint), 'native_p02_sha256': sha(p02[0]),
        'native_onehost_sha256': sha(onehost[0]), 'source_locked_p02_sha256': sha(expected) if expected.is_file() else None,
        'p02_baseline_drift': p02_drift, 'native_integration_allowed': not p02_drift,
        'files_sha256': fingerprint, 'active_nox_modified': False,
        'active_weights_modified': False, 'live_s03_verified': False,
        'gpu_optimizer_steps_executed': 0, 'windows_e07_accepted': False,
        'requires_native_owner_stop_and_acl': True,
    }
    (dest / 'V34_STAGE_RECEIPT.json').write_text(json.dumps(status, indent=2, ensure_ascii=False), 'utf-8')
    return {k: v for k, v in status.items() if k != 'files_sha256'}

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--nox-root', required=True)
    p.add_argument('--stage-root', required=True)
    args = p.parse_args()
    print(json.dumps(stage(nox_root=args.nox_root, stage_root=args.stage_root), indent=2, ensure_ascii=False))
