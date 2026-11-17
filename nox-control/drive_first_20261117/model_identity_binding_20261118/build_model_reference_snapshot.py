"""Materialize only the accepted native audit's bounded reference metadata.

This local builder never connects to NOX. Installation of the resulting 0600
snapshot is a separate source-pinned coordinator transaction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from owner_model_reference_binding import validate_snapshot

ACCEPTED_RAW_SHA = 'f430bfb170c74ec39b57a59b676e4cbf0ad32063d70962e17681738ff03b45ef'


def build(raw):
    if hashlib.sha256(raw).hexdigest() != ACCEPTED_RAW_SHA:
        raise ValueError('HOLD_ACCEPTED_AUDIT_SHA')
    envelope = json.loads(raw)
    if envelope.get('kind') != 'model_identity_readback':
        raise ValueError('HOLD_ACCEPTED_AUDIT_KIND')
    data = envelope['data']
    if not (data['listener_model_reference_verified'] is True
            and data['owner_request'] == '6963059953'
            and data['source_sha'] == 'dd824cbd6cc4508deeb84681f9612b9cee2fe31d'
            and data['weight_content_identity_verified'] is False
            and data['architecture_or_training_identity_verified'] is False
            and data['last_chat_backend_identified'] is False):
        raise ValueError('HOLD_ACCEPTED_AUDIT_SCOPE')
    process = data['process']
    listener = data['listener']
    argument = data['argv_projection']['model_argument']
    snapshot = {
        'schema': 'NOX_VERIFIED_MODEL_REFERENCE_V1',
        'evidence': {'run': '44192038242', 'request': data['owner_request'], 'source_sha': data['source_sha'],
                     'raw_sha256': ACCEPTED_RAW_SHA, 'observed_at': data['observed_at']},
        'route': {'host': '127.0.0.1', 'port': listener['port'], 'path': '/v1/chat/completions'},
        'process': {key: process[key] for key in ('pid', 'start_ticks', 'ppid', 'uid', 'argv_sha256',
                                                 'exe_path_sha256', 'cwd_sha256')},
        'listener': {'fd': listener['file_descriptors'][0], 'socket_inode': listener['socket_inode'],
                     'network_namespace_sha256': listener['network_namespace_sha256'], 'address': listener['address']},
        'model_reference': {'basename': argument['model_basename'], 'argument_sha256': argument['sha256']},
        'scope': 'CURRENT_LISTENER_ARGV_REFERENCE_ONLY',
    }
    validate_snapshot(snapshot, data['observed_at'])
    return (json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audit', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    raw = args.audit.read_bytes()
    body = build(raw)
    # Never overwrite an existing snapshot inadvertently in a local build.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as target:
        target.write(body)
        target.flush()
        os.fsync(target.fileno())
    print(json.dumps({'path': str(args.output), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
                      'native_calls': 0, 'installed': False}))


if __name__ == '__main__':
    main()
