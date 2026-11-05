"""Read-only, exact-HEAD source inventory for the existing NOX OneHost.

Discovery does NOT import material into S03, grant a licence, download donor
archives, or make generated code executable. Explicit owner source_paths and
native consent still gate actual knowledge ingestion / code proposals.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
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


_WINDOWS_RESERVED = frozenset({"CON", "PRN", "AUX", "NUL",
                               *(f"COM{i}" for i in range(1, 10)),
                               *(f"LPT{i}" for i in range(1, 10))})
_WINDOWS_INVALID = frozenset('<>:"|?*')


def _safe_source_path(path):
    """Admit only checkout-stable Windows names to native S03 source inventory."""
    if (type(path) is not str or not 0 < len(path) <= 300 or
            "\\" in path or PurePosixPath(path).is_absolute()):
        return False
    for component in path.split("/"):
        if (not component or component in (".", "..") or
                component.endswith((" ", ".")) or component.casefold() == ".git" or
                unicodedata.normalize("NFC", component) != component or
                component.split(".", 1)[0].rstrip(" ").upper() in _WINDOWS_RESERVED or
                any(ord(ch) < 32 or ord(ch) == 127 or ch in _WINDOWS_INVALID
                    for ch in component)):
            return False
    return True

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
    windows_components = {}
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
        if PurePosixPath(path).suffix.lower() not in SUFFIXES:
            continue
        if not _safe_source_path(path):
            raise ValueError('GIT_TREE_WINDOWS_UNSAFE_SOURCE_PATH')
        # Every component matters: Foo/a.py and foo/b.py share a Windows parent.
        folded = []
        for component in path.split('/'):
            folded.append(component.casefold())
            alias = '/'.join(folded)
            previous = windows_components.setdefault(alias, component)
            if previous != component:
                raise ValueError('GIT_TREE_WINDOWS_NAMESPACE_COLLISION')
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

# Selected source inspection is a read-only handoff to ORIGINAL native P02/S03.
# Catalog choice is not ingest consent and never executes downloaded code.
MAX_SOURCE_DETAIL_BYTES = 128 * 1024
MAX_SOURCE_PREVIEW = 2048
_GIT_OBJECT_SHA = re.compile(r'^[0-9a-f]{40}(?:[0-9a-f]{24})?$')


def inspect_selected_source(source, selected_path, source_paths=(), *,
                            expected_head=None, expected_git_blob_sha=None):
    """Verify an owner-selected regular Git blob by exact HEAD + SHA-256.

    An unapproved selection returns metadata only. An approved selected path
    gets a bounded read-only preview. This does NOT import into S03, grant
    rights, create a code candidate, start a model, or authorize execution.
    """
    base = {'status': 'HOLD', 'items': [], 'imported_into_s03': False,
            'source_executed': False, 'candidate_executed': False,
            'native_ingest_consent': 'REQUIRED', 'source_rights': 'REVIEW_REQUIRED'}
    if (not _safe_source_path(selected_path) or
            PurePosixPath(selected_path).suffix.lower() not in SUFFIXES or
            type(source_paths) not in (tuple, list) or len(source_paths) > 30 or
            len(set(map(str, source_paths))) != len(source_paths) or
            any(not _safe_source_path(p) or PurePosixPath(p).suffix.lower() not in SUFFIXES
                for p in source_paths) or
            (expected_head is not None and
             (type(expected_head) is not str or not _GIT_OBJECT_SHA.fullmatch(expected_head))) or
            (expected_git_blob_sha is not None and
             (type(expected_git_blob_sha) is not str or
              not _GIT_OBJECT_SHA.fullmatch(expected_git_blob_sha)))):
        return {**base, 'reason': 'SOURCE_SELECTION_INPUT_INVALID'}
    if getattr(source, 'root', None) is None:
        return {**base, 'reason': 'MANAGED_GIT_SOURCE_NOT_CONFIGURED'}
    try:
        head = source.head()
        if expected_head is not None and head != expected_head:
            return {**base, 'reason': 'SOURCE_SELECTION_HEAD_DRIFT', 'source_head': head}
        if not source.admitted(head):
            return {**base, 'reason': 'EXACT_CLEAN_HEAD_REQUIRED', 'source_head': head}
        blobs = _regular_blobs(source.git('ls-tree', '-r', '-z', head))
        selected = blobs.get(selected_path)
        if selected is None:
            return {**base, 'reason': 'SOURCE_SELECTION_NOT_REGULAR_BLOB',
                    'source_head': head}
        blob, mode = selected
        if expected_git_blob_sha is not None and blob != expected_git_blob_sha:
            return {**base, 'reason': 'SOURCE_SELECTION_BLOB_DRIFT',
                    'source_head': head}
        record = {'path': selected_path, 'category': classify(selected_path),
                  'source_ref': 'git:' + head + ':' + selected_path,
                  'source_head': head, 'git_blob_sha': blob,
                  'git_blob_mode': mode, 'owner_admitted': selected_path in source_paths}
        if selected_path not in source_paths:
            return {**base, **record,
                    'status': 'SOURCE_SELECTION_OWNER_APPROVAL_REQUIRED',
                    'preview': None, 'source_sha256': None}
        size_text = source.git('cat-file', '-s', blob).strip()
        if not size_text.isascii() or not size_text.isdecimal():
            return {**base, 'reason': 'SOURCE_BLOB_SIZE_INVALID', **record}
        size = int(size_text)
        if size > MAX_SOURCE_DETAIL_BYTES:
            return {**base, 'reason': 'SOURCE_BLOB_PREVIEW_QUOTA',
                    'source_bytes': size, **record}
        contents = source.git('cat-file', 'blob', blob)
        raw = contents.encode('utf-8')
        if (len(raw) != size or '\0' in contents or
                not source.admitted(head)):
            return {**base, 'reason': 'SOURCE_DETAIL_INTEGRITY_HOLD', **record}
        return {**base, **record, 'status': 'SOURCE_SELECTION_READ_ONLY',
                'source_sha256': hashlib.sha256(raw).hexdigest(),
                'source_bytes': size, 'preview': contents[:MAX_SOURCE_PREVIEW],
                'preview_truncated': len(contents) > MAX_SOURCE_PREVIEW,
                'owner_approved_source_reference': True,
                'ingestion_authorized': False,
                'model_called': False}
    except OverflowError:
        return {**base, 'reason': 'SOURCE_TREE_TOO_LARGE_FOR_BOUNDED_INVENTORY'}
    except (OSError, ValueError, RuntimeError, UnicodeError, AttributeError, TypeError):
        return {**base, 'reason': 'MANAGED_GIT_READ_HOLD'}
