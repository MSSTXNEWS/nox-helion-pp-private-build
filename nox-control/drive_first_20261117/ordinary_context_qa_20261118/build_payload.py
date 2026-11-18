"""Build the five-module ordinary-context QA payload; never execute it."""
from pathlib import Path
import base64
import gzip
import hashlib
import json

HERE = Path(__file__).resolve().parent
NAMES = ('p0_witness_protocol', 'p0_native_helpers', 'p0_login_idle_wait', 'model_reference_qa_release',
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
with tempfile.TemporaryDirectory(prefix='nox-ordinary-context-qa-') as directory:
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
    manifest = {'schema': 'NOX_ORDINARY_CONTEXT_QA_PAYLOAD_V1', 'payload_path': str(output.relative_to(HERE)),
        'repository_payload_path': 'nox-control/owner_resonance_canary_v3_20261117.py',
        'payload_sha256': sha(wrapper), 'payload_bytes': len(wrapper), 'modules': pins,
        'deterministic_gzip_mtime': 0, 'entry_count': 1, 'entry': 'model_reference_changed_path_qa.entry',
        'native_execution_by_builder': 0, 'operator': 'UNCHANGED_EXISTING_OWNER_REPAIR_ROUTE',
        'actual_install_source': '2b6f338342bdd7eb0e9ef0e64c6c65bccb7e60cb',
        'actual_install_request': '6965635795', 'actual_proxy_pid': 3703386,
        'actual_proxy_start_ticks': 175609570, 'hard_deadline_seconds': 420,
        'sse_total_cooperative_deadline_seconds': 90, 'socket_timeout_seconds': 20,
        'max_output_bytes': 65536, 'allowed_http': {
            '127.0.0.1:18775': {'POST /chat/login': 1, 'POST /api/nox/chat': 1,
                'GET /nox-web-v29/nox-ui.js': 1,
                'GET /api/ui/memory/dialogs/history?dialog_id=12092579cf5144419cfa4fadc2e3a03b&limit=8': 2},
            '127.0.0.1:8098': {'GET /slots': 3}},
        'dialog_create_posts': 0, 'model_reloads': 0, 'service_mutations': 0, 'counter_resets': 0,
        'automatic_retry_allowed': False, 'native_dispatch_owner': '/root',
        'ordinary_context_acceptance': {
            'journal': 'owner_ordinary_context_acceptance_20261118',
            'previous_completed_qa_run': 44214744070,
            'previous_exchange_id': 'S03-eb3abcc1321949b3',
            'previous_record_sha256': 'c9bd7a7f70b8204ef74c018d5c54a0197bf2a8a632644b196e0291eabd85e1e1',
            'prior_messages': 6, 'after_messages': 8,
            'fresh_exclusive_purpose': True, 'old_journal_reused': False,
            'new_question': 'В одном коротком предложении объясни, почему резервная копия должна храниться отдельно от рабочей копии.',
            'max_owner_chat_posts_in_this_purpose': 1},
        'login_idle_wait': {'module': 'p0_login_idle_wait.py',
            'sha256': 'c69fa4d8ec05a6d147ef1172581fd00ff28fc24705fca8502fd2bca909afd3ad',
            'bytes': 12459, 'unchanged': True, 'max_seconds': 240,
            'source': 'nox_refresh/launcher_parent_file_fix_20261118/frozen_22302/p0_login_idle_wait.py',
            'previous_accepted_native_run': 44207277921, 'observed_wait_seconds': 182.777,
            'repeated_login_allowed': False, 'priority_writes': 0},
        'counter_raw_snapshot_max_bytes': 4096, 'counter_expected_value_assigned': False,
        'counter_raw_publicly_exported': False,
        'counter_private_evidence_files': ['counter_before.json', 'counter_after.json'],
        'counter_observed_identity_presence_fields': ['writer_key_present', 'activity_schema_key_present'],
        'ordinary_context_evidence': {'path': '/root/nox/logs/proxy.log',
            'read_scope': 'HELD_INODE_FRESH_APPEND_ONLY', 'max_append_bytes': 65536,
            'max_actual_read_bytes': 131328, 'raw_log_exported': False,
            'positive_status': 'SOURCE_INFERRED_CONTEXT_HELPER_RETURNED',
            'exact_tokenizer_rounds': None, 'exact_cache_hits': None,
            'missing_evidence_replays_question': False, 'proxy_restart_required': False}}
    (HERE / 'BUILD_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    result = build()
    print(json.dumps({'payload_sha256': result['payload_sha256'], 'payload_bytes': result['payload_bytes'],
                      'module_count': len(result['modules']), 'native_calls': 0}))
