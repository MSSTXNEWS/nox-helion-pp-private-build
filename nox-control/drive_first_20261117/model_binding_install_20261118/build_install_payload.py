"""Deterministic local build of the existing owner repair entrypoint payload."""
from __future__ import annotations

import ast
import base64
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BINDING = HERE.parent / 'model_identity_binding_20261118'
BASE_SHA = 'dff6a3841d76a07de5552e81476a8f322179091b641a3b14a3795ee120b6ef27'
ARTIFACT_PINS = {
    'owner_model_reference_binding.py': {'sha256': 'b9f4addc252c8a0339e2123680fe5a0ab47cef15e725ecec0747f5934a2759ad', 'bytes': 18265},
    'verified_model_reference.json': {'sha256': '0d0a839b7a30e6b617accd1ba61f5a2e04b99a7d144ab5a99b107ae09a4cf668', 'bytes': 1204},
}
MODULES = ('source_transform', 'native_menu_overlay_transform', 'native_v24_dialog_transform',
           'native_v24_dialog_installer', 'binding_install_artifacts', 'native_model_binding_installer')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    if sha((HERE / 'native_v24_dialog_installer.py').read_bytes()) != BASE_SHA:
        raise ValueError('HOLD_SUCCESSFUL_BASE_DRIFT')
    artifacts = {}
    for name, pin in ARTIFACT_PINS.items():
        raw = (BINDING / name).read_bytes()
        if len(raw) != pin['bytes'] or sha(raw) != pin['sha256']:
            raise ValueError('HOLD_REVIEWED_BINDING_ARTIFACT_DRIFT')
        artifacts[name] = raw
    artifact_module = ('"""Only two reviewed non-secret installation bodies, no import-time I/O."""\n'
                       'import base64\nARTIFACT_PINS = ' + repr(ARTIFACT_PINS) + '\nARTIFACTS = {\n')
    for name, raw in artifacts.items():
        artifact_module += repr(name) + ': base64.b64decode(' + repr(base64.b64encode(raw).decode()) + ',validate=True),\n'
    artifact_module += '}\n'
    (HERE / 'binding_install_artifacts.py').write_text(artifact_module)
    wrapper = '#!/usr/bin/env python3\n"""Single existing OneHost owner repair: model-reference binding + menu."""\n'
    wrapper += 'import base64,gzip,hashlib,sys,types\n'
    modules = {}
    for name in MODULES:
        raw = (HERE / (name + '.py')).read_bytes()
        ast.parse(raw)
        compile(raw, name, 'exec')
        digest = sha(raw)
        modules[name] = {'sha256': digest, 'bytes': len(raw)}
        encoded = base64.b64encode(gzip.compress(raw, mtime=0)).decode()
        wrapper += 'raw=gzip.decompress(base64.b64decode(' + repr(encoded) + ',validate=True))\n'
        wrapper += 'if len(raw)!=' + str(len(raw)) + ' or hashlib.sha256(raw).hexdigest()!=' + repr(digest) + ':raise RuntimeError("HOLD_REVIEWED_SOURCE_DIGEST")\n'
        wrapper += 'm=types.ModuleType(' + repr(name) + ');m.__file__=' + repr('<reviewed-' + name + '>') + ';sys.modules[m.__name__]=m\n'
        wrapper += 'exec(compile(raw,m.__file__,"exec"),m.__dict__)\n'
    wrapper += 'raise SystemExit(m.entry())\n'
    body = wrapper.encode()
    compile(body, 'owner_resonance_canary_v3_20261117.py', 'exec')
    output = HERE / 'public_payload/nox-control/owner_resonance_canary_v3_20261117.py'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(body)
    manifest = {'schema': 'NOX_MODEL_BINDING_OWNER_INSTALL_PAYLOAD_V1', 'instructions_version': '0.0.6',
                'operator_base': '8b7f431f419a3618bed7a9442ccf1072a48e747a',
                'operator_changes': False, 'action': 'repair', 'entrypoint': 'nox-control/owner_resonance_canary_v3_20261117.py',
                'successful_lifecycle_base_sha256': BASE_SHA, 'modules': modules, 'artifacts': ARTIFACT_PINS,
                'payload': {'sha256': sha(body), 'bytes': len(body)}, 'native_calls_during_build': 0,
                'payload_executed': False, 'automatic_retry_allowed': False,
                'source_install_count': 3, 'new_file_count': 2, 'service': 'nox-proxy',
                'model_posts': 0, 'model_restarts': 0, 'counter_or_queue_resets': 0,
                'publication': 'NOT_DONE', 'runtime_acceptance': 'PENDING'}
    (HERE / 'BUILD_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest['payload']))


if __name__ == '__main__':
    main()
