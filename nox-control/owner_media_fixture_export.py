#!/usr/bin/env python3
"""Read exactly two synthetic outputs and emit encrypted chunks; no writes."""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
import base64
import hashlib
import json
import os
import re
import subprocess

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

TRANSPORT_SHA = '5208f16465410140ab38da1c1e44a0711667bd34e3a4fc5f17237df11693230f'
PUBLIC_METADATA_SHA = 'b543c29b5883d398694ba676e9270407a1d6435434ed26772072e5509c3bdafa'
MAX_OUTPUT = 700000


def fail(code):
    raise RuntimeError(code)


def bundle(name, expected):
    raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
    if not re.fullmatch('[a-f0-9]{64}', expected) or not raw or len(raw) > 64000 or hashlib.sha256(raw).hexdigest() != expected:
        fail('HOLD_MEDIA_FIXTURE_BUNDLE_PIN')
    return raw


CHILD = r'''
import sys
sys.dont_write_bytecode=True
import base64,hashlib,json,re,types
try:
 raw=sys.stdin.buffer.read(150001)
 if len(raw)>150000:raise RuntimeError('HOLD_MEDIA_FIXTURE_CHILD_BUDGET')
 value=json.loads(raw)
 source=base64.b64decode(value['transport'],validate=True)
 if hashlib.sha256(source).hexdigest()!=value['transport_sha256']:raise RuntimeError('HOLD_MEDIA_FIXTURE_CHILD_PIN')
 module=types.ModuleType('nox_private_fixture_transport')
 sys.modules[module.__name__]=module
 exec(compile(source,'<reviewed-media-fixture-transport>','exec'),module.__dict__)
 metadata=base64.b64decode(value['metadata'],validate=True)
 if hashlib.sha256(metadata).hexdigest()!=value['metadata_sha256']:raise RuntimeError('HOLD_MEDIA_FIXTURE_CHILD_METADATA')
 rows=module.seal(module.decode_json(metadata),value['request'],value['source_sha'])
 for row in rows:print('NOX_MAINT_REPAIR='+json.dumps(row,separators=(',',':')),flush=True)
 print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
except Exception as exc:
 code=str(exc)
 if not re.fullmatch('HOLD_MEDIA_FIXTURE_[A-Z0-9_]+',code):code='HOLD_MEDIA_FIXTURE_CRYPTO_'+type(exc).__name__.upper()
 print('NOX_MAINT_REPAIR='+json.dumps({'kind':'media_fixture_export_failure','data':code}),flush=True)
 raise SystemExit(2)
'''


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch('[0-9]{1,24}', request) or not re.fullmatch('[a-f0-9]{40}', source):
        fail('HOLD_MEDIA_FIXTURE_OWNER_CONTEXT')
    transport = bundle('owner_media_fixture_transport.py', TRANSPORT_SHA)
    metadata = bundle('owner_media_fixture_public_key.json', PUBLIC_METADATA_SHA)
    payload = {'transport': base64.b64encode(transport).decode(), 'transport_sha256': TRANSPORT_SHA,
               'metadata': base64.b64encode(metadata).decode(), 'metadata_sha256': PUBLIC_METADATA_SHA,
               'request': request, 'source_sha': source}
    # This exact native interpreter already passed the AESGCM/OAEP capability
    # probe. The child has no credentials, inherited proxies, GPU or write cache.
    result = subprocess.run(['/usr/bin/python3', '-I', '-B', '-c', CHILD],
        input=json.dumps(payload).encode(), capture_output=True, timeout=25,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONNOUSERSITE': '1',
             'PYTHONDONTWRITEBYTECODE': '1', 'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1'})
    if len(result.stdout) > MAX_OUTPUT or any(len(line) >= 80000 for line in result.stdout.splitlines()):
        fail('HOLD_MEDIA_FIXTURE_NATIVE_OUTPUT_BUDGET')
    if result.returncode:
        # No raw stderr, filenames or exception text is published.
        fail('HOLD_MEDIA_FIXTURE_NATIVE_EXPORT_FAILED')
    lines = result.stdout.decode('ascii').splitlines()
    if not lines or lines[-1] != 'NOX_MAINT_REPAIR_COMPLETE=true':
        fail('HOLD_MEDIA_FIXTURE_NATIVE_COMPLETION')
    if any(not line.startswith('NOX_MAINT_REPAIR=') for line in lines[:-1]):
        fail('HOLD_MEDIA_FIXTURE_NATIVE_PROTOCOL')
    for line in lines:
        print(line, flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        value = str(exc)
        code = value if re.fullmatch('HOLD_MEDIA_FIXTURE_[A-Z0-9_]+', value) else 'HOLD_MEDIA_FIXTURE_EXPORT_'+type(exc).__name__.upper()
        print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'media_fixture_export_failure', 'data': code}), flush=True)
        raise SystemExit(2)
