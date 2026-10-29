"""Read-only reconstruction preflight for #6 (never extracts, installs or rewrites assets)."""
from __future__ import annotations
import hashlib
import pathlib
import re
from collections.abc import Sequence

PART_NAMES = ('source_00.part','source_01.part','source_02.part')
# These bytes are pinned by BUILD_INPUTS_README.txt in the canonical GitHub packaging tree.
EXPECTED_BYTES = 60_364_346
EXPECTED_SHA256 = 'ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a'


def inspect_parts(root: str | pathlib.Path, expected_bytes: int = EXPECTED_BYTES,
                  expected_sha256: str = EXPECTED_SHA256, names: Sequence[str] = PART_NAMES) -> dict:
    """Compute joined source SHA-256 without writing zip or touching originals."""
    root = pathlib.Path(root)
    if not expected_sha256 or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('Expected SHA-256 must be pinned lowercase hex')
    digest = hashlib.sha256()
    size = 0
    for name in names:
        if pathlib.Path(name).name != name or name in ('.','..'):
            raise ValueError('Unsafe archive part name')
        path = root / name
        if path.is_symlink() or not path.is_file():
            return {'status': 'HOLD', 'blocker': 'PART_MISSING_OR_SYMLINK', 'path': name,
                    'bytes_seen': size, 'sha256': None}
        with path.open('rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''):
                size += len(block)
                if size > expected_bytes:
                    return {'status': 'HOLD', 'blocker': 'ARCHIVE_TOO_LARGE',
                            'bytes_seen': size, 'sha256': None}
                digest.update(block)
    observed = digest.hexdigest()
    return {'status': 'VERIFIED' if size == expected_bytes and observed == expected_sha256 else 'HOLD',
            'blocker': None if size == expected_bytes and observed == expected_sha256 else 'SHA_OR_LENGTH_MISMATCH',
            'bytes_seen': size, 'sha256': observed}


def inventory_extracted_tree(root: str | pathlib.Path) -> dict:
    """Bounded, read-only path inventory; never treat unopened archive as absent source."""
    root = pathlib.Path(root)
    if not root.exists() or not root.is_dir():
        return {'status': 'HOLD', 'blocker': 'EXTRACTED_TREE_UNAVAILABLE', 'files': []}
    matched = []
    needles = ('chat', 'sqlite', 'ollama', 'events', 'rag', 'persona', 'maestro',
               'voice', 'sip', 'mainWindow', 'webview')
    for p in root.rglob('*'):
        if p.is_symlink() or not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(n.lower() in rel.lower() for n in needles):
            matched.append(rel)
        if len(matched) >= 400:
            return {'status': 'PARTIAL', 'blocker': 'MATCH_LIMIT', 'files': sorted(matched)}
    return {'status': 'INVENTORY', 'blocker': None, 'files': sorted(matched)}
