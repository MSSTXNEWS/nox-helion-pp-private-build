"""Failure-only, immutable R11 NSIS UninstallString preimage witness; never an acceptance gate."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

SOURCE_PARTS = ('work', 'e06', 'staged', 'R11', 'Installer', 'NOX-HELION-Setup.nsi')
OUTPUT_PARTS = ('work', 'e06', 'registry-firstfail', 'T06_R11_REGISTRY_FIRSTFAIL_WITNESS.json')
EXPECTED_BYTES = 7308
EXPECTED_SHA256 = '2158b71759e72b3b93cafcf27196386c1885b39fb99f80b4bd1872273a0b2248'
MAX_LINE_BYTES = 320


def _plain_components(root: Path, parts: tuple[str, ...]) -> Path:
    """Reject redirected components including Windows junctions before any read/write."""
    cursor = root
    for part in parts:
        cursor = cursor / part
        try:
            attrs = cursor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(attrs.st_mode) or (getattr(attrs, 'st_file_attributes', 0) & 0x400):
            raise ValueError('R11_WITNESS_REPARSE_HOLD')
    return cursor


def witness(root: Path, expected_sha: str = EXPECTED_SHA256,
            expected_bytes: int = EXPECTED_BYTES) -> dict:
    """A source observation, not a repair, build, installed test or release PASS."""
    base = {'schema': 'NOX-E06-R11-NSIS-REGISTRY-PREIMAGE-WITNESS-v1',
            'release_accepted': False, 'e07_tested': False,
            'status': 'WITNESS_NOT_AVAILABLE_HOLD', 'source_sha256': None,
            'source_bytes': None, 'marker_count': 0, 'markers': []}
    path = _plain_components(root, SOURCE_PARTS)
    try:
        st = path.lstat()
    except FileNotFoundError:
        return base
    if not stat.S_ISREG(st.st_mode) or st.st_size > 1048576:
        base['status'] = 'R11_WITNESS_SOURCE_NOT_REGULAR_HOLD'
        return base
    data = path.read_bytes()
    base['source_sha256'] = hashlib.sha256(data).hexdigest()
    base['source_bytes'] = len(data)
    if len(data) != expected_bytes or base['source_sha256'] != expected_sha:
        base['status'] = 'R11_WITNESS_UNEXPECTED_SOURCE_SHA_HOLD'
        return base
    raw_lines = data.splitlines()
    markers = [(number, line) for number, line in enumerate(raw_lines, 1)
               if b'uninstallstring' in line.lower()]
    base['marker_count'] = len(markers)
    if len(markers) == 0:
        base['status'] = 'R11_WITNESS_NO_UNINSTALLSTRING_MARKER_HOLD'
    elif len(markers) != 1:
        base['status'] = 'R11_WITNESS_MULTIPLE_UNINSTALLSTRING_MARKERS_HOLD'
    else:
        base['status'] = 'WITNESS_CAPTURED_NOT_BUILD_ACCEPTANCE'
    for number, line in markers[:4]:
        item = {'line_number': number, 'line_sha256': hashlib.sha256(line).hexdigest(),
                'line_bytes': len(line), 'line_escaped': None}
        if len(line) <= MAX_LINE_BYTES:
            item['line_escaped'] = line.decode('ascii', errors='backslashreplace')
        base['markers'].append(item)
    return base


def main() -> int:
    root = Path.cwd()
    try:
        report = witness(root)
        target = _plain_components(root, OUTPUT_PARTS)
        target.parent.mkdir(parents=True, exist_ok=True)
        _plain_components(root, OUTPUT_PARTS)
        payload = json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
        with target.open('x', encoding='utf-8', newline='\n') as output:
            output.write(payload + '\n')
        print('T06_R11_REGISTRY_FIRSTFAIL_WITNESS ' + payload)
        return 0 if report['status'] == 'WITNESS_CAPTURED_NOT_BUILD_ACCEPTANCE' else 2
    except (OSError, ValueError) as exc:
        print('T06_R11_REGISTRY_FIRSTFAIL_WITNESS_HOLD ' + type(exc).__name__)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
