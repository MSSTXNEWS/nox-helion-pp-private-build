#!/usr/bin/env python3
"""Construct an exact-source overlay in a NEW local staging directory only.

Never imports torch/trainer, launches training, changes the source tree, or
copies into /root/nox. No shell, network, credentials or live server operations.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import os

REL = Path('nox_runpod/teacher_mesh/v135')
EXPECTED = {
    'train_full_base_zero3.py':'c2e7b231d5af8b9493ec3578144f95e60ff31c7c',
    'curate_teacher_distillation.py':'e1012794c1dbae911c3ca853c3686357e54faa3c',
    'verified_resume.py':'f0cf9bf3546144f2d6b752fa88e626bb3a511151',
}


def git_blob(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def regular(path):
    if path.is_symlink() or not path.is_file() or any(p.is_symlink() for p in path.parents):
        raise RuntimeError('HOLD_STAGE_SYMLINK_OR_MISSING_FILE')
    return path.read_bytes()


def stage(source_root, output, package=None):
    package = Path(__file__).parent if package is None else Path(package)
    source_root, output = Path(source_root).absolute(), Path(output).absolute()
    if (source_root.is_symlink() or output.exists() or output.is_symlink()
            or source_root == output or source_root in output.parents
            or not output.parent.is_dir() or any(p.is_symlink() for p in output.parents)
            or str(output).startswith('/root/nox')):
        raise RuntimeError('HOLD_NEW_LOCAL_STAGE_ONLY')
    originals = {}
    for name, expected in EXPECTED.items():
        actual = git_blob(regular(source_root / REL / name))
        if actual != expected:
            raise RuntimeError('HOLD_DEPLOYED_BLOB_MISMATCH:'+name)
        originals[name] = actual
    receipt = json.loads(regular(package/'SOURCE_RECEIPT.json'))
    names = [str(REL/name) for name in EXPECTED] + [str(REL/'resource_safe_point.py'),str(REL/'resource_native_binding.py')]
    payloads = {name:regular(package/name) for name in names}
    # Bind the previous reviewed source package and the new native attachment.
    pins = {**receipt['files'], **json.loads(regular(package/'ATTACH_RECEIPT.json'))['files']}
    for name, raw in payloads.items():
        if hashlib.sha256(raw).hexdigest() != pins.get(name):
            raise RuntimeError('HOLD_STAGE_PACKAGE_HASH:'+name)
    output.mkdir(mode=0o700)
    for name, raw in payloads.items():
        target = output/name;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:
            os.chmod(target,0o600);f.write(raw);f.flush();os.fsync(f.fileno())
        if regular(target) != raw: raise RuntimeError('HOLD_STAGE_READBACK')
    report = dict(schema='NOX_EXISTING_TRAINER_STAGE_ONLY_V1',run_id='NOX-49-20261117',
        originals=originals,files={name:hashlib.sha256(raw).hexdigest() for name,raw in payloads.items()},
        training_started=False,source_tree_changed=False,server_changed=False,native_accepted_ids=[])
    with (output/'STAGE_RECEIPT.json').open('x') as f:
        os.chmod(output/'STAGE_RECEIPT.json',0o600);json.dump(report,f,indent=2);f.write('\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',required=True)
    parser.add_argument('--stage-dir',required=True)
    args=parser.parse_args()
    try: result=stage(args.source_root,args.stage_dir)
    except (OSError,ValueError,RuntimeError) as exc:
        print(json.dumps({'state':'HOLD_STAGE_ONLY','reason':str(exc)}));return 2
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__': raise SystemExit(main())
