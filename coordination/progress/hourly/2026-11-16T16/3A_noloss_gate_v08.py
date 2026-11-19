#!/usr/bin/env python3
"""Read-only, exact-SHA WEB29 preimage / cinematic no-loss gate.

Does not deploy, rewrite manifests, modify archives, or claim LIVE acceptance.
V29 SOURCE_MANIFEST_V29 is historical; compare it at both revisions to avoid
mistaking pre-existing drift for a new regression.
"""
import argparse
import hashlib
import json
import stat
import tempfile
from pathlib import Path
from zipfile import ZipFile, ZIP_STORED

BASE_SHA = '611a3cf21b37ff79dbaece57f4c65c5efb70e0c302b5fc4b4f64dbfa060f15bc'
CANDIDATE_SHA = 'd5603047763b9abfe03973e61fbb00e7b0c0f2acde9187c70f200f055bde9ea6'
# Only observed, accepted source deltas; any other changed path is HOLD.
CHANGED = frozenset({
    'site/pc/v25/nox-shell-v25.js', 'site/pc/hub.html',
    'site/chat.html', 'site/pc/world.html', 'site/pc/menu.html',
    'site/progress.html', 'site/pc/progress.html', 'site/nox-chat.js',
})
ADDED = frozenset({'site/nox-cinematic-accessibility-3d.css',
                   'site/nox-motion-idle-loader.js'})
IMMUTABLE = frozenset({'site/index.html', 'site/pc/index.html',
                       'site/nox-visual-source-lock-v24.js',
                       'site/nox-visual-source-lock-v24.css'})


def digest_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for part in iter(lambda: f.read(1048576), b''):
            h.update(part)
    return h.hexdigest()


def entries(z):
    result = {}
    for i in z.infolist():
        n = i.filename
        if (n in result or not n or n.startswith('/') or '\\' in n or
                any(v in ('.', '..', '') for v in n.split('/')) or
                (i.external_attr >> 16 & 0o170000) == stat.S_IFLNK):
            raise ValueError('HOLD_UNSAFE_OR_DUPLICATE_MEMBER:' + n)
        if not i.is_dir():
            result[n] = {'bytes': i.file_size, 'sha256': hashlib.sha256(z.read(i)).hexdigest()}
    if z.testzip() is not None:
        raise ValueError('HOLD_ZIP_CRC')
    return result


def manifest_drift(z, members):
    try:
        raw = z.read('site/SOURCE_MANIFEST_V29.json')
        manifest = json.loads(raw)
    except (KeyError, ValueError, TypeError):
        return {'status': 'UNKNOWN_HISTORIC_MANIFEST'}
    stale = []
    for name, expected in manifest.items():
        actual = members.get('site/' + name)
        if (actual is None or actual['sha256'] != expected.get('sha256')
                or actual['bytes'] != expected.get('bytes')):
            stale.append('site/' + name)
    return {'status': 'HISTORICAL_SOURCE_LOCK_DRIFT' if stale else 'MATCH',
            'entries': len(manifest), 'stale': sorted(stale)}


def audit(base, candidate, *, sha_required=True):
    base, candidate = Path(base), Path(candidate)
    bsha, csha = digest_file(base), digest_file(candidate)
    if sha_required and (bsha != BASE_SHA or csha != CANDIDATE_SHA):
        raise ValueError('HOLD_EXACT_ARCHIVE_SHA_PREIMAGE')
    with ZipFile(base) as bz, ZipFile(candidate) as cz:
        bm, cm = entries(bz), entries(cz)
        missing = set(bm) - set(cm)
        new = set(cm) - set(bm)
        changed = {x for x in bm.keys() & cm.keys() if bm[x] != cm[x]}
        unexpected = (changed - CHANGED) | (new - ADDED) | missing
        if missing or unexpected or (IMMUTABLE & changed):
            raise ValueError('HOLD_NOLOSS_UNEXPECTED_DELTA:' + ','.join(sorted(unexpected)))
        bb, cb = manifest_drift(bz, bm), manifest_drift(cz, cm)
    newly_stale = sorted(set(cb.get('stale', [])) - set(bb.get('stale', [])))
    media_names = {n for n in bm if n.lower().endswith(
        ('.png', '.jpeg', '.jpg', '.webp', '.svg', '.glb', '.hdr', '.wasm', '.mp4', '.woff2'))}
    return {
        'status': 'SOURCE_NOLOSS_BOUNDED_PASS__LIVE_UNVERIFIED',
        'base_zip_sha256': bsha, 'candidate_zip_sha256': csha,
        'base_paths': len(bm), 'candidate_paths': len(cm),
        'deleted_paths': len(missing), 'added': sorted(new),
        'changed': sorted(changed), 'unchanged': len(set(bm) & set(cm)) - len(changed),
        'protected_media_files_compared_identical': len(media_names - changed),
        'historical_v29_source_manifest': {
            'original_stale_entries': len(bb.get('stale', [])),
            'candidate_stale_entries': len(cb.get('stale', [])),
            'newly_stale_from_candidate': newly_stale,
            'note': 'Legacy manifest has pre-existing drift: NOT a current-build SOURCE_LOCK PASS. Original unchanged.'},
        'cinematic_512_independent_manifest_check': 'NOT_CLAIMED',
        'live_web29_deployed': False, 'live_browser_e2e': 'NOT_RUN',
        'native_stop_lease_rollback': 'UNKNOWN',
    }


def selftest():
    with tempfile.TemporaryDirectory() as d:
        b, c = Path(d) / 'b.zip', Path(d) / 'c.zip'
        with ZipFile(b, 'w', ZIP_STORED) as f:
            f.writestr('site/index.html', 'ORIGINAL')
            f.writestr('site/D02.png', b'D02')
        with ZipFile(c, 'w', ZIP_STORED) as f:
            f.writestr('site/index.html', 'ORIGINAL')
            f.writestr('site/D02.png', b'D02')
            f.writestr('site/nox-motion-idle-loader.js', 'improved')
        assert audit(b, c, sha_required=False)['status'].startswith('SOURCE_NOLOSS')
        with ZipFile(c, 'w', ZIP_STORED) as f:
            f.writestr('site/index.html', 'ORIGINAL')
            f.writestr('site/D02.png', b'D02-DAMAGED')
        try:
            audit(b, c, sha_required=False)
            raise AssertionError('protected asset change should hold')
        except ValueError as e:
            assert str(e).startswith('HOLD_NOLOSS_UNEXPECTED_DELTA:')
        with ZipFile(c, 'w', ZIP_STORED) as f:
            f.writestr('site/index.html', 'ORIGINAL')
            f.writestr('site/index.html', 'WRONG')
        try:
            audit(b, c, sha_required=False)
            raise AssertionError('duplicate ZIP names should hold')
        except ValueError as e:
            assert str(e).startswith('HOLD_UNSAFE_OR_DUPLICATE_MEMBER:')
    return '3/3 synthetic regression checks PASS'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', type=Path)
    p.add_argument('--candidate', type=Path)
    p.add_argument('--selftest', action='store_true')
    args = p.parse_args()
    if args.selftest:
        print(selftest())
    if args.base and args.candidate:
        print(json.dumps(audit(args.base, args.candidate), indent=2, sort_keys=True))
    elif not args.selftest:
        p.error('--base and --candidate are required')

if __name__ == '__main__':
    main()
