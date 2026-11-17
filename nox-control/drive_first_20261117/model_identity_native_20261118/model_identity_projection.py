"""Bounded pure projections for the existing owner's read-only identity audit.

No native module import, file read, network, model request or service operation.
The caller supplies source-pinned byte strings and existing JSON/argv values.
"""
from __future__ import annotations

import hashlib
import re


SOURCE_PINS = {
    'chat_proxy.py': 'b202301a3b94076a5152478dd9d1ad1eeceaa72e09cd2ce93e537eaab70740bc',
    'nox_v29_chat_bridge.py': '17932e2f49a659119593e6819acf945ebbedfb274595b8086f1031096b7d2a0f',
    'common.py': '618b2b24ffdf780e64a5d09955438dec5a9b6b8b04b3346b29c57fc750403167',
    'agent_loop.py': '0ecec93bcf3239b7decc768862d27fbdc60fe2b613103f201406761bb4850aaa',
    'owner_chat_stream.py': '2c4ae86d1d8e2113c8dbb55807f0d52890f098904ac2914f0b1383156ed7ea25',
}
JSON_READSET = ('/root/nox/status/status.json', '/root/nox/config/backend.json')
MODEL_ROOT = '/root/nox/models/'
_PUBLIC_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:+/ -]{0,199}\Z')
_BASENAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.+ -]{0,199}\.gguf\Z', re.I)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def source_contract(sources: dict) -> dict:
    if not isinstance(sources, dict):
        raise ValueError('HOLD_IDENTITY_SOURCE_INPUT')
    for name, pin in SOURCE_PINS.items():
        value = sources.get(name)
        if not isinstance(value, bytes) or _sha(value) != pin:
            raise ValueError('HOLD_IDENTITY_SOURCE_SHA:' + name)
    return {
        'source_pins': dict(SOURCE_PINS),
        'status_read_path': JSON_READSET[0],
        'status_origin': 'disk snapshot via chat_proxy.nox_status -> common.load_json',
        'status_model_selector': 'model string; else model.name, model.model, model.id; sliced to200 chars',
        'status_is_live_model_response': False,
        'backend_read_path': JSON_READSET[1],
        'completion_route': 'load_backend(host,port) -> /v1/chat/completions',
        'primary_health_route': '/health on configured port',
        'fallback_health_route': 'http://127.0.0.1:8085/health only after primary health failure',
        'fallback_completion_route': 'http://127.0.0.1:8085/v1/chat/completions',
        'upstream_cache_ttl_seconds': 2,
        'owner_runtime_chain': [
            'chat_proxy._proxy_completion -> agent_loop.owner_completion',
            'agent_loop bottom import owner_chat_stream.install(globals())',
            'owner_chat_stream.install replaces owner_completion',
            'owner_chat_stream._run -> _model_events(client,url,model_request)',
            '_model_events streams POST at the same supplied url',
        ],
        'proxy_v1_models_origin': 'synthetic config model_name; not a live backend catalog',
        'prior_request_backend_identity_reconstructed': False,
    }


def _kind(value):
    if value is None:
        return 'null'
    if type(value) is bool:
        return 'boolean'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, dict):
        return 'object'
    if isinstance(value, list):
        return 'array'
    if isinstance(value, (int, float)):
        return 'number'
    return 'other'


def _sensitive_marker(value):
    low = value.lower()
    return any(x in low for x in ('secret', 'password', 'token', '://', '?', '@',
                                 'bearer ', 'sk-', 'ghp_', 'github_pat_', 'hf_'))


def identifier(value, *, present=True) -> dict:
    """Export a bounded identifier or path basename; never export a full path."""
    out = {'present': bool(present), 'type': _kind(value)}
    if not present or not isinstance(value, str):
        return out
    raw = value.encode('utf-8', errors='replace')
    out.update(chars=len(value), bytes=len(raw), sha256=_sha(raw), empty=not value)
    reasons = []
    if not value:
        reasons.append('empty')
    if len(value) > 120:
        reasons.append('previous_audit_limit120')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:+/ -]{0,119}', value):
        reasons.append('previous_audit_character_or_length_rule')
    if any(x in value.lower() for x in ('secret', 'password', 'token', '/root/', '/home/', '://')):
        reasons.append('previous_audit_sensitive_marker')
    out['previous_audit_mask_reasons'] = reasons
    if (value.startswith(MODEL_ROOT) and not _sensitive_marker(value)
            and not any(part in ('', '.', '..') for part in value[len(MODEL_ROOT):].split('/'))):
        basename = value.rsplit('/', 1)[-1]
        if _BASENAME.fullmatch(basename):
            out['model_basename'] = basename
            out['under_known_model_root'] = True
    elif (_PUBLIC_ID.fullmatch(value) and not value.startswith('/')
          and not _sensitive_marker(value)):
        out['identifier'] = value
    return out


def status_projection(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {'schema_valid': False}
    model = payload.get('model')
    selected, field = None, None
    if isinstance(model, str):
        selected, field = model[:200], 'model'
    elif isinstance(model, dict):
        for key in ('name', 'model', 'id'):
            value = model.get(key)
            if isinstance(value, str) and value:
                selected, field = value[:200], 'model.' + key
                break
    out = {
        'schema_valid': True,
        'origin': 'snapshot or API status; no model execution proof',
        'model_field_type': _kind(model),
        'selected_source_field': field,
        'selected_model': identifier(selected, present=field is not None),
        'primary_model': identifier(payload.get('primary_model'), present='primary_model' in payload),
    }
    bound = payload.get('native_p02_bound')
    out['native_p02_bound'] = bound if type(bound) is bool else None
    if isinstance(model, dict):
        out['model_fields'] = {key: identifier(model[key]) for key in ('name', 'model', 'id', 'path') if key in model}
    return out


def backend_probe_plan(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError('HOLD_BACKEND_JSON_SHAPE')
    host = payload.get('host', '127.0.0.1')
    raw_port = payload.get('port', 8081)
    if host not in ('127.0.0.1', 'localhost'):
        raise ValueError('HOLD_BACKEND_NON_LOOPBACK_HOST')
    if type(raw_port) is int:
        port = raw_port
    elif isinstance(raw_port, str) and re.fullmatch(r'[0-9]{1,5}', raw_port):
        port = int(raw_port)
    else:
        raise ValueError('HOLD_BACKEND_PORT_TYPE')
    if not 1 <= port <= 65535:
        raise ValueError('HOLD_BACKEND_PORT_RANGE')
    return {
        'host': host,
        'port': port,
        'completion_path': '/v1/chat/completions',
        'primary_health_url': f'http://127.0.0.1:{port}/health',
        'health_host_matches_completion_host': host == '127.0.0.1',
        'fallback_health_url': 'http://127.0.0.1:8085/health',
        'fallback_only_after_primary_definite_failure': True,
        'maximum_health_gets': 2,
        'model_posts': 0,
        'configured_model': identifier(payload.get('model'), present='model' in payload),
        'configured_model_name': identifier(payload.get('model_name', 'nox')),
        'default_host_used': 'host' not in payload,
        'default_port_used': 'port' not in payload,
        'read_only_sample_does_not_reconstruct_previous_request': True,
    }


def health_projection(status: int, body: bytes, *, truncated=False) -> dict:
    if (type(status) is not int or not isinstance(body, bytes)
            or len(body) > 65536 or type(truncated) is not bool):
        raise ValueError('HOLD_HEALTH_INPUT')
    if truncated:
        return {'complete': False, 'healthy_by_source_rule': None}
    text = body.decode('utf-8', errors='replace')
    healthy = status == 200 and ('ok' in text.lower() or 'status' in text.lower() or bool(text.strip()))
    return {'http_status': status, 'bytes': len(body), 'sha256': _sha(body),
            'complete': True, 'healthy_by_source_rule': healthy,
            'rule': 'exact _nox_t153_port_ok source predicate; no response body exported'}


def model_argv_projection(argv) -> dict:
    """Project only model-path flags after caller proves listener PID/start."""
    if (not isinstance(argv, list) or not argv or len(argv) > 256
            or any(not isinstance(x, str) or len(x.encode('utf-8', errors='replace')) > 16384 for x in argv)
            or sum(len(x.encode('utf-8', errors='replace')) + 1 for x in argv) > 32768):
        raise ValueError('HOLD_MODEL_ARGV_BOUND')
    found = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        # A credential value may itself begin with '--model='. Consume it as
        # data belonging to the credential option, never as another switch.
        flag = arg.split('=', 1)[0].lower().replace('_', '-')
        credential_flag = (flag == '-hft' or flag.startswith('-') and any(marker in flag for marker in
                           ('api-key', 'token', 'password', 'secret', 'auth', 'credential')))
        if credential_flag:
            if '=' not in arg:
                if index + 1 >= len(argv):
                    raise ValueError('HOLD_MODEL_ARGV_CREDENTIAL_VALUE')
                index += 2
            else:
                index += 1
            continue
        if arg in ('-m', '--model'):
            if index + 1 >= len(argv):
                raise ValueError('HOLD_MODEL_ARGV_MISSING_VALUE')
            found.append(argv[index + 1])
            index += 2
            continue
        elif arg.startswith('--model='):
            found.append(arg.split('=', 1)[1])
        index += 1
    if len(found) > 1:
        raise ValueError('HOLD_MODEL_ARGV_AMBIGUOUS')
    projected = {'present': False}
    if found:
        candidate = identifier(found[0]) if found[0].startswith(MODEL_ROOT) else {}
        # Unlike an explicitly typed status field, arbitrary argv may contain
        # unrelated private values. Export only a validated known-root GGUF
        # reference, and omit even length/hash for other potential arguments.
        projected = candidate if 'model_basename' in candidate else {
            'present': True, 'unvalidated_value_withheld': True}
    return {
        'model_argument': projected,
        'model_argument_count': len(found),
        'full_argv_exported': False,
        'environment_read': False,
        'listener_process_binding_verified': False,
        'requires_listener_pid_start_witness': True,
        'weight_content_or_training_identity_proven': False,
    }
