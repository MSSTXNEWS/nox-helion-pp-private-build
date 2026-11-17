"""Pure, exact-preimage update for the existing native V29 menu overlay.

The owner installer supplies two already-read byte strings. This module never
reads files, imports the native application, authenticates, reloads a service,
or submits a model request. It changes only one tuple in the existing serving
overlay. Rollback recovers the exact pinned preimage, not an older whole file.
"""
from __future__ import annotations

import ast
import hashlib


BRIDGE_BEFORE_SHA256 = '17932e2f49a659119593e6819acf945ebbedfb274595b8086f1031096b7d2a0f'
BRIDGE_BEFORE_BYTES = 51632
BRIDGE_AFTER_SHA256 = '9d7475428ad8c553c756ca50280ac2363e7c03854abab285de560ae066d4586a'
BRIDGE_AFTER_BYTES = 51865
FROZEN_UI_SHA256 = 'c5f6b23d5fc6c31c4c388a574bfa8c61243cda6000cefb0026732ebe4183b765'
SERVED_BEFORE_SHA256 = '18d8c8d6009323188b9f903920308b3b871a6123f7b425a77184a6b2c147640e'
SERVED_BEFORE_BYTES = 42933
SERVED_AFTER_SHA256 = '13897495d7c9c628ef4f3094fafdad5f5932a3570d21c650112ba7138ab3c2f0'
SERVED_AFTER_BYTES = 43021
TARGET = '_V122_OWNER_UI_PATCHES'
OLD_JS = "link.setAttribute('href','/nox/'+page+(match[2]||''));"
NEW_JS = "link.setAttribute('href',(page==='chat'&&location.pathname.startsWith('/nox-web-v29/')?'/nox-web-v29/chat.html':'/nox/'+page)+(match[2]||''));"
ADDED_PAIR = (OLD_JS, NEW_JS)
INSERTION = (
    '    (\n'
    '        "' + OLD_JS + '",\n'
    '        "' + NEW_JS + '",\n'
    '    ),\n'
).encode('utf-8')


class PatchHold(ValueError):
    """The exact patch contract is not met; leave native files unchanged."""


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _parse(raw: bytes):
    try:
        return ast.parse(raw.decode('utf-8'), filename='nox_v29_chat_bridge.py')
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise PatchHold('HOLD_MENU_SOURCE_SYNTAX') from exc


def _constant(tree, name: str):
    matches = [node for node in tree.body if isinstance(node, ast.Assign)
               and len(node.targets) == 1
               and isinstance(node.targets[0], ast.Name)
               and node.targets[0].id == name]
    if len(matches) != 1:
        raise PatchHold('HOLD_MENU_CONSTANT_SCOPE')
    try:
        value = ast.literal_eval(matches[0].value)
    except (ValueError, TypeError, SyntaxError) as exc:
        raise PatchHold('HOLD_MENU_CONSTANT_LITERAL') from exc
    return matches[0], value


def _pairs(tree):
    node, pairs = _constant(tree, TARGET)
    if (not isinstance(node.value, ast.Tuple) or not isinstance(pairs, tuple)
            or not pairs or any(not isinstance(pair, tuple) or len(pair) != 2
                               or any(not isinstance(x, str) or not x for x in pair)
                               for pair in pairs)):
        raise PatchHold('HOLD_MENU_OVERLAY_PAIRS')
    _, frozen = _constant(tree, '_V122_FROZEN_NOX_UI_SHA')
    if frozen != FROZEN_UI_SHA256:
        raise PatchHold('HOLD_MENU_FROZEN_SOURCE_PIN')
    return node, pairs


def _overlay(raw_ui: bytes, pairs) -> bytes:
    if not isinstance(raw_ui, bytes) or sha256(raw_ui) != FROZEN_UI_SHA256:
        raise PatchHold('HOLD_MENU_FROZEN_UI_BYTES')
    try:
        value = raw_ui.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise PatchHold('HOLD_MENU_FROZEN_UI_ENCODING') from exc
    for old, new in pairs:
        if value.count(old) != 1 or new in value:
            raise PatchHold('HOLD_MENU_OVERLAY_ANCHOR')
        value = value.replace(old, new, 1)
    return value.encode('utf-8')


def _splice_tuple_bytes(raw: bytes) -> bytes:
    """Structural primitive; the public entry point adds mandatory file pins."""
    before_tree = _parse(raw)
    node, pairs = _pairs(before_tree)
    if len(pairs) != 3 or any(OLD_JS in pair or NEW_JS in pair for pair in pairs):
        raise PatchHold('HOLD_MENU_BASE_OVERLAY_CHANGED')
    # Python AST column offsets are UTF-8 byte offsets, not Unicode positions.
    # Require the observed multiline tuple shape, then preserve every old byte.
    lines = raw.splitlines(keepends=True)
    value = node.value
    closing = sum(map(len, lines[:value.end_lineno - 1])) + value.end_col_offset - 1
    if (value.end_col_offset != 1 or raw[closing:closing + 1] != b')'
            or raw[closing - 2:closing] != b',\n'):
        raise PatchHold('HOLD_MENU_TUPLE_CLOSING_LAYOUT')
    after = raw[:closing] + INSERTION + raw[closing:]
    after_tree = _parse(after)
    after_node, after_pairs = _pairs(after_tree)
    if after_pairs != pairs + (ADDED_PAIR,):
        raise PatchHold('HOLD_MENU_NONEXACT_PAIR_DELTA')
    # Normalise only the appended tuple. All other AST nodes, including auth,
    # S03, STOP, routing and model paths, must be literally identical.
    after_node.value.elts.pop()
    if ast.dump(before_tree, include_attributes=False) != ast.dump(after_tree, include_attributes=False):
        raise PatchHold('HOLD_MENU_OTHER_AST_CHANGED')
    if len(after) != len(raw) + len(INSERTION) or after.replace(INSERTION, b'', 1) != raw:
        raise PatchHold('HOLD_MENU_NONEXACT_BYTE_DELTA')
    compile(after, 'nox_v29_chat_bridge.py', 'exec')
    return after


def transform(raw: bytes, raw_ui: bytes, *, rollback: bool = False) -> bytes:
    """Return the prepared bytes, or raise before any installer side effect.

    Forward operation accepts only the exact installed 51,632-byte bridge.
    Rollback removes exactly this insertion and must recover that same full
    SHA-256; it rejects unrelated edits and cannot restore an historical file.
    """
    if not isinstance(raw, bytes) or not isinstance(raw_ui, bytes) or type(rollback) is not bool:
        raise PatchHold('HOLD_MENU_INPUT_TYPE')
    if rollback:
        if (len(raw) != BRIDGE_AFTER_BYTES or raw.count(INSERTION) != 1):
            raise PatchHold('HOLD_MENU_ROLLBACK_LAYOUT')
        original = raw.replace(INSERTION, b'', 1)
        if len(original) != BRIDGE_BEFORE_BYTES or sha256(original) != BRIDGE_BEFORE_SHA256:
            raise PatchHold('HOLD_MENU_ROLLBACK_PREIMAGE')
        if sha256(raw) != BRIDGE_AFTER_SHA256:
            raise PatchHold('HOLD_MENU_ROLLBACK_POSTIMAGE')
        if transform(original, raw_ui) != raw:
            raise PatchHold('HOLD_MENU_ROLLBACK_NONEXACT_POSTIMAGE')
        return original
    if len(raw) != BRIDGE_BEFORE_BYTES or sha256(raw) != BRIDGE_BEFORE_SHA256:
        raise PatchHold('HOLD_MENU_BRIDGE_PREIMAGE')
    tree = _parse(raw)
    _, pairs = _pairs(tree)
    before_ui = _overlay(raw_ui, pairs)
    if len(before_ui) != SERVED_BEFORE_BYTES or sha256(before_ui) != SERVED_BEFORE_SHA256:
        raise PatchHold('HOLD_MENU_SERVED_BASELINE')
    prepared = _splice_tuple_bytes(raw)
    if len(prepared) != BRIDGE_AFTER_BYTES or sha256(prepared) != BRIDGE_AFTER_SHA256:
        raise PatchHold('HOLD_MENU_BRIDGE_POSTIMAGE')
    _, next_pairs = _pairs(_parse(prepared))
    after_ui = _overlay(raw_ui, next_pairs)
    if len(after_ui) != SERVED_AFTER_BYTES or sha256(after_ui) != SERVED_AFTER_SHA256:
        raise PatchHold('HOLD_MENU_SERVED_POSTIMAGE')
    if after_ui.replace(NEW_JS.encode(), OLD_JS.encode(), 1) != before_ui:
        raise PatchHold('HOLD_MENU_OTHER_JS_CHANGED')
    return prepared


def describe(raw: bytes, raw_ui: bytes) -> dict:
    """Prepare and describe the exact candidate without exposing source text."""
    prepared = transform(raw, raw_ui)
    if transform(prepared, raw_ui, rollback=True) != raw:
        raise PatchHold('HOLD_MENU_ROLLBACK_ROUNDTRIP')
    return {
        'schema': 'NOX_NATIVE_MENU_EXACT_DELTA_V1',
        'instructions_version': '0.0.6',
        'before_sha256': BRIDGE_BEFORE_SHA256,
        'before_bytes': BRIDGE_BEFORE_BYTES,
        'after_sha256': sha256(prepared),
        'after_bytes': len(prepared),
        'insertion_sha256': sha256(INSERTION),
        'insertion_bytes': len(INSERTION),
        'served_before_sha256': SERVED_BEFORE_SHA256,
        'served_before_bytes': SERVED_BEFORE_BYTES,
        'served_after_sha256': SERVED_AFTER_SHA256,
        'served_after_bytes': SERVED_AFTER_BYTES,
        'source_scope': 'one appended tuple in existing _V122_OWNER_UI_PATCHES',
        'other_ast_and_bytes_unchanged': True,
        'rollback_to_exact_preimage': True,
        'native_installed': False,
        'native_used': False,
    }
