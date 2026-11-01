"""Read-only, exact-HEAD source inventory for the existing NOX OneHost.

Discovery does NOT import material into S03, grant a licence, download donor
archives, or make generated code executable. Explicit owner source_paths and
native consent still gate actual knowledge ingestion / code proposals.
"""
from __future__ import annotations

from pathlib import PurePosixPath

SUFFIXES = frozenset({'.py', '.cs', '.mjs', '.js', '.css', '.html', '.json',
                      '.md', '.patch', '.diff', '.ps1', '.yml', '.yaml'})
MAX_DISPLAY = 120
MAX_TREE = 12000


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


def inspect_managed_sources(source, source_paths=()):
    """Only filenames from Git's immutable HEAD; never page-provided paths."""
    if getattr(source, 'root', None) is None:
        return {'status': 'HOLD', 'reason': 'MANAGED_GIT_SOURCE_NOT_CONFIGURED',
                'items': [], 'imported_into_s03': False}
    try:
        head = source.head()
        if not source.admitted(head):
            return {'status': 'HOLD', 'reason': 'EXACT_CLEAN_HEAD_REQUIRED',
                    'items': [], 'source_head': head, 'imported_into_s03': False}
        all_paths = source.git('ls-tree', '-r', '--name-only', head).splitlines()
    except (OSError, ValueError, RuntimeError):
        return {'status': 'HOLD', 'reason': 'MANAGED_GIT_READ_HOLD',
                'items': [], 'imported_into_s03': False}
    if len(all_paths) > MAX_TREE:
        return {'status': 'HOLD', 'reason': 'SOURCE_TREE_TOO_LARGE_FOR_BOUNDED_INVENTORY',
                'items': [], 'source_head': head, 'imported_into_s03': False}
    approved = set(source_paths)
    if len(approved) > 30 or len(approved) != len(tuple(source_paths)):
        return {'status': 'HOLD', 'reason': 'OWNER_SOURCE_PATH_CONFIG_INVALID',
                'items': [], 'source_head': head, 'imported_into_s03': False}
    valid = []
    for path in all_paths:
        if (not path or len(path) > 300 or '\\' in path or
            PurePosixPath(path).is_absolute() or
            any(part in ('', '.', '..') for part in path.split('/')) or
            PurePosixPath(path).suffix.lower() not in SUFFIXES):
            continue
        valid.append(path)
    selected = sorted(valid, key=lambda p: (p not in approved, p.lower()))
    display = selected[:MAX_DISPLAY]
    counts = {key: 0 for key in ('code_modules', 'templates', 'patches', 'integrations', 'contracts_docs')}
    for path in valid:
        counts[classify(path)] += 1
    items = [{'path': p, 'category': classify(p),
              'source_ref': 'git:' + head + ':' + p,
              'owner_admitted': p in approved} for p in display]
    return {'status': 'SOURCE_INVENTORY_READ_ONLY',
            'source_head': head, 'items': items, 'categories': counts,
            'supported_total': len(valid), 'displayed': len(items),
            'truncated': len(valid) > MAX_DISPLAY,
            'owner_admitted_total': sum(p in approved for p in valid),
            'all_sources_loaded': False, 'imported_into_s03': False,
            'licence_and_hash_review': 'REQUIRED_BEFORE_USE',
            'source_generation': 'SEPARATE_NATIVE_CONSENT_REQUIRED'}
