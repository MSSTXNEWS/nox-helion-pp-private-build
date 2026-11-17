"""Deterministic source-only builder; never imports or invokes the native audit."""
import ast
import base64
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ('model_identity_projection', 'native_model_identity_readback', 'model_identity_audit_entry')


def build():
    pins = {}
    lines = ['#!/usr/bin/env python3', '"""Source-pinned generation-free model identity audit."""',
             'import base64,gzip,hashlib,sys,types', 'sys.dont_write_bytecode=True']
    for name in MODULES:
        raw = (HERE / (name + '.py')).read_bytes()
        ast.parse(raw)
        digest = hashlib.sha256(raw).hexdigest()
        pins[name] = {'sha256': digest, 'bytes': len(raw)}
        encoded = base64.b64encode(gzip.compress(raw, mtime=0)).decode('ascii')
        lines += ['raw=gzip.decompress(base64.b64decode(' + repr(encoded) + ',validate=True))',
                  'if hashlib.sha256(raw).hexdigest()!=' + repr(digest) + ':raise RuntimeError("HOLD_IDENTITY_MODULE_SHA")',
                  'm=types.ModuleType(' + repr(name) + ');m.__file__=' + repr('<reviewed-' + name + '>') + ';sys.modules[m.__name__]=m',
                  'exec(compile(raw,m.__file__,"exec"),m.__dict__)']
    lines.append('raise SystemExit(m.main())')
    raw = ('\n'.join(lines) + '\n').encode('utf8')
    ast.parse(raw)
    output = HERE / 'public_payload/nox-control/owner_native_audit.py'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    manifest = {'schema': 'NOX_MODEL_IDENTITY_AUDIT_BUILD_V1', 'repository_path': 'nox-control/owner_native_audit.py',
                'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'modules': pins,
                'native_calls_during_build': 0, 'payload_executed': False,
                'allowed_destination': 'http://127.0.0.1:8098/health', 'maximum_gets': 1,
                'maximum_posts': 0, 'maximum_model_requests': 0, 'maximum_output_bytes': 32768,
                'hard_deadline_seconds': 20, 'existing_lock_only': True,
                'source_code_inputs_exported': False, 'private_key_inputs': 0}
    (HERE / 'BUILD_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    result = build()
    print(json.dumps({key: result[key] for key in ('sha256', 'bytes', 'repository_path')}, indent=2))
