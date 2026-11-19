"""Pure, exact-source hooks; no native reads/writes or secret source exports."""
from __future__ import annotations
import hashlib
import re

PROXY_BEFORE = 'a25dbbbd74a67f8c9847d2a2f68d51177f73a8f49dbc66d985ca4def517ce976'
OBSERVER_BEFORE = '5abf1f582f82e626f7370ebaeaefb326b8689acd440955d93b4d016b628a6d34'
STREAM_BEFORE = '852c5dcbc43e03a5b485d3e45f1af0fea6ae2803f88bb6b4e44bbac62e986ec7'


def _source(raw, expected):
    if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('HOLD_CHAT_EVIDENCE_SOURCE_PIN')
    return raw.decode()


def patch_proxy(raw):
    old = ('        from owner_chat_stream import executor_status_query as _nox_executor_status_query\n'
           '        _self_query = _self_query or _nox_executor_status_query(_utext)\n')
    new = ('        from owner_chat_stream import owner_request_query as _nox_owner_request_query\n'
           '        _self_query = _self_query or _nox_owner_request_query(_utext)\n')
    source = raw.decode() if isinstance(raw, bytes) else ''
    if source.count(new) == 1 and old not in source:
        # Idempotence is proven by exact reversal to the full pinned preimage.
        _source(source.replace(new, old, 1).encode(), PROXY_BEFORE)
        return raw
    source = _source(raw, PROXY_BEFORE)
    if source.count(old) != 1:
        raise ValueError('HOLD_CHAT_EVIDENCE_PROXY_ANCHOR')
    result = source.replace(old, new, 1).encode()
    compile(result, '<native-proxy-current-evidence>', 'exec')
    return result


def patch_self_observation(raw):
    tail = ('\n# NOX_OWNER_CURRENT_DOWNLOAD_EVIDENCE_V1\n'
            'from owner_chat_evidence import bind_self_observation as _nox_bind_current_evidence\n'
            '_nox_bind_current_evidence(globals())\n').encode()
    if isinstance(raw, bytes) and raw.endswith(tail):
        _source(raw[:-len(tail)], OBSERVER_BEFORE)
        return raw
    source = _source(raw, OBSERVER_BEFORE)
    result = source.encode()+tail
    compile(result, '<native-v137-current-evidence>', 'exec')
    return result


def tool_registry_projection(tools):
    """Optional native preflight: names only, no prompts/config/tool execution."""
    if not isinstance(tools, list) or not 1 <= len(tools) <= 200:
        raise ValueError('HOLD_CHAT_TOOL_REGISTRY_SCHEMA')
    names = []
    for row in tools:
        name = (row.get('function') or {}).get('name') if isinstance(row, dict) else None
        if not isinstance(name, str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,99}', name) or name in names:
            raise ValueError('HOLD_CHAT_TOOL_REGISTRY_SCHEMA')
        names.append(name)
    reserved = {'owner_verified_download_inventory', 'owner_queue_media_v1', 'owner_media_job_v1'}
    return {'schema': 'NOX_OWNER_CHAT_TOOL_NAMES_V1', 'names': names,
            'reserved_names_free': not bool(reserved.intersection(names)), 'tool_execution_performed': False}
