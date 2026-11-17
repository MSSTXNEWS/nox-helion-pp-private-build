"""Build the four-module changed-path QA payload; never execute it."""
from pathlib import Path
import base64
import gzip
import hashlib
import json

HERE = Path(__file__).resolve().parent
NAMES = ('p0_witness_protocol', 'p0_native_helpers', 'model_reference_qa_release',
         'model_reference_changed_path_qa')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build():
    pins, packed = {}, {}
    for name in NAMES:
        raw = (HERE / (name + '.py')).read_bytes()
        compile(raw, name + '.py', 'exec')
        pins[name + '.py'] = {'sha256': sha(raw), 'bytes': len(raw)}
        packed[name + '.py'] = base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode('ascii')
    template = '''"""One owned changed-path QA. Root-coordinated native execution only."""
import base64, gzip, hashlib, pathlib, sys, tempfile
PINS = {pins!r}
PACKED = {packed!r}
with tempfile.TemporaryDirectory(prefix='nox-model-reference-qa-') as directory:
    root = pathlib.Path(directory)
    for name, encoded in PACKED.items():
        raw = gzip.decompress(base64.b64decode(encoded, validate=True))
        expected = PINS[name]
        if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
            raise SystemExit('HOLD_QA_EMBEDDED_MODULE_PIN')
        (root / name).write_bytes(raw)
    sys.path.insert(0, str(root))
    import model_reference_changed_path_qa as m
    raise SystemExit(m.entry())
'''
    wrapper = template.format(pins=pins, packed=packed).encode()
    compile(wrapper, 'owner_resonance_canary_v3_20261117.py', 'exec')
    output = HERE / 'public_payload/nox-control/owner_resonance_canary_v3_20261117.py'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(wrapper)
    manifest = {'schema': 'NOX_MODEL_REFERENCE_QA_PAYLOAD_V1', 'payload_path': str(output.relative_to(HERE)),
        'repository_payload_path': 'nox-control/owner_resonance_canary_v3_20261117.py',
        'payload_sha256': sha(wrapper), 'payload_bytes': len(wrapper), 'modules': pins,
        'deterministic_gzip_mtime': 0, 'entry_count': 1, 'entry': 'model_reference_changed_path_qa.entry',
        'native_execution_by_builder': 0, 'operator': 'UNCHANGED_EXISTING_OWNER_REPAIR_ROUTE',
        'actual_install_source': '5da7849bffc2b590201bb1917840b5a2b39ca2a7',
        'actual_install_request': '6963969126', 'actual_proxy_pid': 3648425,
        'actual_proxy_start_ticks': 175058217, 'hard_deadline_seconds': 120,
        'sse_total_cooperative_deadline_seconds': 90, 'socket_timeout_seconds': 20,
        'max_output_bytes': 65536, 'allowed_http': {
            '127.0.0.1:18775': {'POST /chat/login': 1, 'POST /api/nox/chat': 1,
                'GET /nox-web-v29/nox-ui.js': 1,
                'GET /api/ui/memory/dialogs/history?dialog_id=12092579cf5144419cfa4fadc2e3a03b&limit=4': 2},
            '127.0.0.1:8098': {'GET /slots': 2}},
        'dialog_create_posts': 0, 'model_reloads': 0, 'service_mutations': 0, 'counter_resets': 0,
        'automatic_retry_allowed': False, 'native_dispatch_owner': '/root'}
    (HERE / 'BUILD_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    result = build()
    print(json.dumps({'payload_sha256': result['payload_sha256'], 'payload_bytes': result['payload_bytes'],
                      'module_count': len(result['modules']), 'native_calls': 0}))
