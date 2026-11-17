"""Verify or copy one SHA-pinned source tree into a NEW staging directory.

No live installation, process control, STOP changes, network calls or task execution.
A ready staging receipt is not native acceptance or authorization to deploy.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil

MANIFEST = 'integration/owner_mini_source/CURRENT_SOURCE_MANIFEST.json'
SCHEMA = 'NOX_CURRENT_SOURCE_STAGE_V1'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def safe_source(root, name):
    rel = PurePosixPath(name)
    if rel.is_absolute() or not rel.parts or any(x in ('..', '.') for x in rel.parts) or '\\' in name:
        raise ValueError('HOLD_UNSAFE_SOURCE_PATH')
    path = root.joinpath(*rel.parts)
    if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
        raise ValueError('HOLD_SOURCE_SYMLINK')
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('HOLD_SOURCE_MISSING_OR_ESCAPE ' + name)
    return path

def verify(root, expected_sha=None):
    root = Path(root).resolve()
    raw = safe_source(root, MANIFEST).read_bytes()
    digest = sha(raw)
    if expected_sha is not None and digest != expected_sha:
        raise ValueError('HOLD_CURRENT_MANIFEST_SHA')
    manifest = json.loads(raw)
    if manifest.get('schema') != SCHEMA or manifest.get('native_accepted') is not False:
        raise ValueError('HOLD_SOURCE_SCHEMA')
    files = manifest.get('files')
    if not isinstance(files, dict) or not files or MANIFEST in files:
        raise ValueError('HOLD_SOURCE_FILES')
    for name, expected in files.items():
        content = safe_source(root, name).read_bytes()
        if sha(content) != expected:
            raise ValueError('HOLD_CURRENT_FILE_SHA ' + name)
        if name.startswith('integration/owner_mini_source/') and name.endswith('.py'):
            compile(content, name, 'exec')
    return {'schema': SCHEMA, 'source_manifest_sha256': digest, 'verified_files': len(files),
            'native_deployed': False, 'native_accepted': False,
            'gate': 'HOLD_OWNER_LEASE_ORDERED_SERVER_ADMISSION'}, manifest, raw

def stage(root, destination, expected_sha):
    if not expected_sha:
        raise ValueError('HOLD_EXPLICIT_CURRENT_SHA_REQUIRED')
    root = Path(root).resolve()
    destination = Path(destination).absolute()
    if destination.resolve().is_relative_to(root):
        raise ValueError('HOLD_STAGE_OUTSIDE_SOURCE_REQUIRED')
    receipt, manifest, raw = verify(root, expected_sha)
    # Exclusive creation: never overwrite a previous source stage or live tree.
    destination.mkdir(parents=False, exist_ok=False)
    try:
        for name, expected in manifest['files'].items():
            content = safe_source(root, name).read_bytes()
            if sha(content) != expected:
                raise ValueError('HOLD_SOURCE_CHANGED_DURING_STAGE ' + name)
            out = destination.joinpath(*PurePosixPath(name).parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open('xb') as handle:
                handle.write(content)
            if sha(out.read_bytes()) != expected:
                raise ValueError('HOLD_STAGE_COPY_SHA ' + name)
        current = destination / MANIFEST
        current.parent.mkdir(parents=True, exist_ok=True)
        current.write_bytes(raw)
        verify(destination, expected_sha)
        receipt['stage_ready'] = True
        (destination/'SOURCE_STAGE_RECEIPT.json').write_text(json.dumps(receipt, indent=2)+'\n')
    except BaseException:
        shutil.rmtree(destination)
        raise
    return receipt

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--expected-sha256')
    parser.add_argument('--stage-to', type=Path)
    args = parser.parse_args()
    result = stage(args.source_root, args.stage_to, args.expected_sha256) if args.stage_to else verify(args.source_root, args.expected_sha256)[0]
    print(json.dumps(result, sort_keys=True))

if __name__ == '__main__':
    main()
