"""Inspect the reviewed NOX sources for the native adviser ABI without loading them."""

import ast
from hashlib import sha256

REVIEWED_SOURCE_SHA256 = {
    'bridge': '3b1f1c22279b2fbca3be03ef53579e8dd93ab3ea44a3c5404e7584f07e3bbf1b',
    'dispatcher': 'eac3ce9e2d8c862d1a7917ec447ea72e84454b7775a4260ad1e72e59de96fe11',
    'proxy': '54b1932c3e408c91c3086de994eb9b85709d65066746b5ca520582829ab94d89',
}
DISPATCHER_CALLBACKS = (
    'host_submit',
    'host_result_sink',
    'host_acquire_remote_lease',
    'host_release_remote_lease',
)
HANDLER_KIND = 'nox.online_advice.v1'
MAX_SOURCE_BYTES = 512 * 1024


def _reviewed_tree(raw, expected):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_SOURCE_BYTES:
        return None, 'SOURCE_ABSENT_OR_OVERSIZE'
    if sha256(raw).hexdigest() != expected:
        return None, 'SOURCE_SHA_MISMATCH'
    try:
        return ast.parse(raw.decode('utf-8')), 'EXACT_SOURCE'
    except (UnicodeError, SyntaxError, ValueError, RecursionError):
        return None, 'SOURCE_PARSE_FAILED'


def _function_names(tree):
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def _adapter_assignment(tree):
    return any(isinstance(node, ast.Attribute) and node.attr == 'nox_native_advisors'
               and isinstance(node.ctx, ast.Store) and isinstance(node.value, ast.Attribute)
               and node.value.attr == 'state'
               for node in ast.walk(tree))


def inspect_native_binding(sources):
    """Return metadata only. Never import sources, inspect keys, register or call."""
    if type(sources) is not dict or set(sources) - REVIEWED_SOURCE_SHA256.keys():
        raise ValueError('ADVISOR_PREFLIGHT_SOURCE_SCOPE')

    trees, source_states = {}, {}
    for role, expected in REVIEWED_SOURCE_SHA256.items():
        tree, state = _reviewed_tree(sources.get(role), expected)
        source_states[role] = state
        if tree is not None:
            trees[role] = tree

    missing = []
    dispatcher = trees.get('dispatcher')
    if dispatcher is not None:
        names = _function_names(dispatcher)
        missing.extend(sorted(set(DISPATCHER_CALLBACKS) - names))
        if not any(isinstance(node, ast.Constant) and node.value == HANDLER_KIND
                   for node in ast.walk(dispatcher)):
            missing.append('nox_online_advice_handler_binding')

    if 'bridge' in trees and 'proxy' in trees:
        if not any(_adapter_assignment(trees[role]) for role in ('bridge', 'proxy')):
            missing.append('app.state.nox_native_advisors')

    state = ('HOLD_SOURCE_PREIMAGE' if len(trees) != len(REVIEWED_SOURCE_SHA256)
             else 'HOLD_NATIVE_CALLBACKS' if missing else 'HOLD_OWNER_RUNTIME_WITNESS')
    return {
        'schema': 'NOX_ADVISOR_NATIVE_BINDING_PREFLIGHT_V1',
        'state': state,
        'source_states': source_states,
        'unbound_in_reviewed_source': missing,
        'runtime_bindings_verified': False,
        'provider_accessed': False,
        'registered': False,
    }
