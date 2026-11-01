"""Read-only, exact-HEAD source inventory for the existing NOX OneHost.

Discovery does NOT import material into S03, grant a licence, download donor
archives, or make generated code executable. Explicit owner source_paths and
native consent still gate actual knowledge ingestion / code proposals.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

SUFFIXES = frozenset({'.py', '.cs', '.mjs', '.js', '.css', '.html', '.json',
                      '.md', '.patch', '.diff', '.ps1', '.yml', '.yaml'})
MAX_DISPLAY = 120
MAX_TREE = 12000
CATEGORY_KEYS = ('code_modules', 'templates', 'patches', 'integrations', 'contracts_docs')
# These are Git *object* identities, not per-file SHA256 or rights receipts.
_TREE_ENTRY = re.compile(r'^(100644|100755|120000|160000) (blob|commit) ([0-9a-f]{40}|[0-9a-f]{64})$')


def classify(path: str) -> str:
    low = path.lower()
    if low.endswith(('.patch', '.diff')) or '/patches/' in low:
        return 'patches'
    if any(t in low for t in ('template', '/templates/', 'design_master')):
        return 'templates'
    if any(t in low for t in ('integration', '/e06/', 'bridge', 'adapter', 'onehost')):
        return 'integrations'
    if low.endswith(('.css', '.html')):
        return 'templates'
    if low.endswith(('.py', '.cs', '.mjs', '.js', '.ps1')):
        return 'code_modules'
    return 'contracts_docs'


def _safe_source_path(path):
    return (type(path) is str and 0 < len(path) <= 300 and
            not any(ord(ch) < 32 or ord(ch) == 127 for ch in path) and
            '\\' not in path and not PurePosixPath(path).is_absolute() and
            not any(part in ('', '.', '..') for part in path.split('/')))


def _regular_blobs(tree):
    """Parse NUL-delimited Git entries; never confuse symlinks/gitlinks with source."""
    if not tree:
        return {}
    if not tree.endswith('\0'):
        raise ValueError('GIT_TREE_NOT_NUL_TERMINATED')
    rows = tree[:-1].split('\0')
    if len(rows) > MAX_TREE:
        raise OverflowError('SOURCE_TREE_TOO_LARGE_FOR_BOUNDED_INVENTORY')
    found = {}
    for row in rows:
        meta, tab, path = row.partition('\t')
        match = _TREE_ENTRY.fullmatch(meta)
        if not tab or match is None:
            raise ValueError('GIT_TREE_ENTRY_INVALID')
        mode, kind, blob = match.groups()
        if mode == '160000' and kind == 'commit':
            continue  # A gitlink is not a readable source blob.
        if mode == '120000' and kind == 'blob':
            continue  # A symlink is a pathname, not reviewed source content.
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise ValueError('GIT_TREE_FILE_MODE_INVALID')
        if not _safe_source_path(path) or PurePosixPath(path).suffix.lower() not in SUFFIXES:
            continue
        if path in found:
            raise ValueError('GIT_TREE_DUPLICATE_PATH')
        found[path] = (blob, mode)
    return found


def inspect_managed_sources(source, source_paths=(), *, category=None, offset=0):
    """Page regular blobs of a clean exact Git HEAD without importing or writing."""
    if getattr(source, 'root', None) is None:
        return {'status': 'HOLD', 'reason': 'MANAGED_GIT_SOURCE_NOT_CONFIGURED',
                'items': [], 'imported_into_s03': False}
    if (category is not None and (type(category) is not str or category not in CATEGORY_KEYS)) or (
            type(offset) is not int or not 0 <= offset <= MAX_TREE):
        return {'status': 'HOLD', 'reason': 'SOURCE_CATALOG_FILTER_INVALID',
                'items': [], 'imported_into_s03': False}
    try:
        head = source.head()
        if not source.admitted(head):
            return {'status': 'HOLD', 'reason': 'EXACT_CLEAN_HEAD_REQUIRED',
                    'items': [], 'source_head': head, 'imported_into_s03': False}
        if (type(source_paths) not in (tuple, list) or len(source_paths) > 30 or
                any(not _safe_source_path(p) or PurePosixPath(p).suffix.lower() not in SUFFIXES
                    for p in source_paths) or len(set(source_paths)) != len(source_paths)):
            return {'status': 'HOLD', 'reason': 'OWNER_SOURCE_PATH_CONFIG_INVALID',
                    'items': [], 'source_head': head, 'imported_into_s03': False}
        tree = source.git('ls-tree', '-r', '-z', head)
        blobs = _regular_blobs(tree)
        if not source.admitted(head):
            return {'status': 'HOLD', 'reason': 'EXACT_CLEAN_HEAD_REQUIRED',
                    'items': [], 'source_head': head, 'imported_into_s03': False}
    except OverflowError:
        return {'status': 'HOLD', 'reason': 'SOURCE_TREE_TOO_LARGE_FOR_BOUNDED_INVENTORY',
                'items': [], 'imported_into_s03': False}
    except (OSError, ValueError, RuntimeError, UnicodeError, AttributeError):
        return {'status': 'HOLD', 'reason': 'MANAGED_GIT_READ_HOLD',
                'items': [], 'imported_into_s03': False}
    approved = set(source_paths)
    valid = list(blobs)
    selected = sorted((p for p in valid if category is None or classify(p) == category),
                      key=lambda p: (p not in approved, p.lower(), p))
    display = selected[offset:offset + MAX_DISPLAY]
    counts = {key: 0 for key in CATEGORY_KEYS}
    for path in valid:
        counts[classify(path)] += 1
    items = [{'path': p, 'category': classify(p),
              'source_ref': 'git:' + head + ':' + p,
              'git_blob_sha': blobs[p][0], 'git_blob_mode': blobs[p][1],
              'owner_admitted': p in approved} for p in display]
    next_offset = offset + len(display)
    has_more = next_offset < len(selected)
    return {'status': 'SOURCE_INVENTORY_READ_ONLY',
            'source_head': head, 'items': items, 'categories': counts,
            'supported_total': len(valid), 'displayed': len(items),
            'truncated': has_more, 'category_filter': category, 'offset': offset,
            'matching_total': len(selected), 'next_offset': next_offset if has_more else None,
            'has_more': has_more,
            'owner_admitted_total': sum(p in approved for p in valid),
            'all_sources_loaded': False, 'imported_into_s03': False,
            'licence_and_hash_review': 'REQUIRED_BEFORE_USE',
            'source_generation': 'SEPARATE_NATIVE_CONSENT_REQUIRED'}
