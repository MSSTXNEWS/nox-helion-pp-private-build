import importlib.util
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('acceptance', Path(__file__).parents[1] / 'native_acceptance.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

class AcceptanceTests(unittest.TestCase):
    def test_auth_ast_no_eval_no_secret_export(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = '''from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SECRETS = ROOT / 'secrets'
CHAT_PASSWORD_PATH = SECRETS / 'owner_private'
def _read_chat_password():
    try:
        return CHAT_PASSWORD_PATH.read_text(encoding='utf-8').strip()
    except OSError:
        return ''
'''
            path = m.resolve_password_path(source, root / 'scripts/chat_proxy.py', root)
            self.assertEqual(path, root / 'secrets/owner_private')
            # Native dependency identifiers need not be ROOT/BASE/SECRETS.
            renamed = source.replace('ROOT', 'PROJECT_HOME').replace('SECRETS', 'PRIVATE_FILES')
            renamed += "\nUNRELATED = __import__('os').system('must_never_run')\nUNRELATED = 'duplicate outside dependency chain'\n"
            self.assertEqual(m.resolve_password_path(renamed, root / 'scripts/chat_proxy.py', root), path)
            for definition, expected in (("PRIVATE_FILES = UNKNOWN_ROOT / 'secrets'", 'HOLD_PATH_NAME'),
                                         ("PRIVATE_FILES = CYCLE\nCYCLE = PRIVATE_FILES", 'HOLD_PATH_CYCLE'),
                                         ("PRIVATE_FILES = Path(os.environ['PRIVATE_TOKEN'])", 'HOLD_PATH_EXPRESSION')):
                broken = renamed.replace("PRIVATE_FILES = PROJECT_HOME / 'secrets'", definition)
                with self.assertRaises(m.Hold) as caught:
                    m.resolve_password_path(broken, root / 'scripts/chat_proxy.py', root)
                self.assertEqual(str(caught.exception), expected)
                self.assertIn('PRIVATE_FILES', caught.exception.dependency_identifiers)
                self.assertNotIn('PRIVATE_TOKEN', json.dumps(caught.exception.dependency_identifiers))
                self.assertNotIn('owner_private', json.dumps(caught.exception.dependency_identifiers))
            for bad in ("__import__('os').system('false')", "Path('/etc/shadow')", "ROOT / '../escape'"):
                with self.assertRaises(m.Hold) as caught:
                    m.resolve_password_path(source.replace("SECRETS / 'owner_private'", bad), root / 'scripts/chat_proxy.py', root)
                self.assertNotIn('owner_private', str(caught.exception))
                self.assertNotIn('shadow', str(caught.exception))
            imported = source.replace("SECRETS = ROOT / 'secrets'", 'from common import SECRETS')
            common = "from pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\nSECRETS = ROOT / 'secrets'\nUNRELATED = __import__('os').system('must_never_run')\n"
            self.assertEqual(m.resolve_password_path(imported, root / 'scripts/chat_proxy.py', root, common_source=common), path)
            with self.assertRaisesRegex(m.Hold, 'HOLD_COMMON_SOURCE_REQUIRED'):
                m.resolve_password_path(imported, root / 'scripts/chat_proxy.py', root)
            for unsafe in (imported.replace('from common import SECRETS', 'from other import SECRETS'),
                           imported.replace('from common import SECRETS', 'from .common import SECRETS'),
                           imported.replace('from common import SECRETS', 'from common import OTHER as SECRETS')):
                with self.assertRaises(m.Hold):
                    m.resolve_password_path(unsafe, root / 'scripts/chat_proxy.py', root, common_source=common)
            for bad_common in (common.replace("ROOT / 'secrets'", "Path(os.getenv('PRIVATE_TOKEN'))"),
                               common.replace("ROOT / 'secrets'", "SECRETS"),
                               common.replace("ROOT / 'secrets'", "Path('/etc')")):
                with self.assertRaises(m.Hold):
                    m.resolve_password_path(imported, root / 'scripts/chat_proxy.py', root, common_source=bad_common)
            common_file = root / 'common.py'
            common_file.write_text(common)
            common_raw, proof = m.stable_common_read(common_file)
            self.assertEqual(proof['sha256'], m.digest(common_raw))
            self.assertTrue(proof['stable_file_identity_verified'])
            self.assertNotIn('secrets', json.dumps(proof).lower().replace('import_secrets', ''))
            scoped = '''def register_native_v29_chat(app, trusted, site_dir=None):
 @app.post('/api/nox/stop')
 async def stream_stop(request: Request):
  if not check(request):
   return trusted['_unauthorized']()
  key = scope(request)
  if key is None or key not in active:
   return JSONResponse({'status':'HOLD'}, status_code=409)
  active[key].set()
  return {'status':'STOP_REQUESTED', 'gpu_stop_verified':False}
'''
            self.assertTrue(m.scoped_stop_supported(scoped))
            self.assertFalse(m.scoped_stop_supported(scoped.replace('active[key].set()', 'global_event.set()')))
            self.assertFalse(m.scoped_stop_supported(scoped.replace('key = scope(request)', 'key = global_key')))

    def test_served_html_transform_and_real_ndjson_receipt(self):
        html = (Path(__file__).parents[1] / 'source_after/resonance.html').read_bytes()
        self.assertTrue(m.served_asset_matches('resonance.html', html))
        injected = html.replace(b'<head>', m.OWNER_HTML_INJECTION)
        self.assertTrue(m.served_asset_matches('resonance.html', injected))
        self.assertFalse(m.served_asset_matches('resonance.html', injected + m.OWNER_HTML_INJECTION))
        self.assertFalse(m.served_asset_matches('resonance.html', injected + b'<script>foreign()</script>'))
        self.assertFalse(m.served_asset_matches('nox-resonance-native-fix-v1.js', injected))
        frames = [{'type': 'preparing'}, {'type': 'delta', 'text': '…'},
                  {'type': 'delta', 'text': '42'}, {'type': 'done', 'saved': True, 's03_integrated': True}]
        raw = b''.join(json.dumps(f).encode() + b'\n' for f in frames)
        turn = m.read_stream(io.BytesIO(raw), time.monotonic(), time.monotonic() + 1)
        self.assertEqual(turn['answer'], '…42')
        self.assertEqual(turn['placeholder_delta_count'], 1)
        self.assertIsNotNone(turn['first_meaningful_delta_ms'])
        with self.assertRaises(m.Hold):
            m.read_stream(io.BytesIO(raw[:raw.rfind(b'{')]), time.monotonic(), time.monotonic() + 1)

    def test_own_history_exact_pair_no_unexpected_text_export(self):
        question = '[QA own] 17 + 25?'
        turn = {'answer': '42', 'done': {'saved': True, 's03_integrated': True},
                'first_meaningful_delta_ms': 12, 'delta_count': 1, 'placeholder_delta_count': 0, 'stream_total_ms': 25}
        history = {'messages': [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': '42'}]}
        result = m.public_turn(turn, history, question)
        self.assertTrue(result['useful_chat_pass'])
        history['messages'][0]['content'] = 'unrelated owner message'
        self.assertFalse(m.public_turn(turn, history, question)['history_persisted'])
        turn['answer'] = 'private unexpected text'
        result = m.public_turn(turn, history, question)
        self.assertNotIn('private unexpected text', json.dumps(result))
        self.assertEqual(result['answer_public_synthetic'], '[WITHHELD]')

    def test_unknown_html_diagnostic_hashes_only_and_pinned_source_projection(self):
        html = (Path(__file__).parents[1] / 'source_after/resonance.html').read_bytes()
        sentinel = 'PRIVATE_HTML_SENTINEL_8d29'
        changed = html.replace(b'<head>', m.OWNER_HTML_INJECTION + ('<script src="/' + sentinel + '"></script>').encode(), 1)
        report = m.served_asset_diagnostic('resonance.html', changed, html, content_type='text/html; charset=UTF-8')
        self.assertFalse(report['matches_pinned_asset'])
        self.assertEqual(report['accepted_transform'], 'NONE')
        self.assertEqual(report['known_owner_head_injection_count'], 1)
        self.assertEqual(report['difference_after_known_injection_normalization']['expected_middle']['bytes'], 0)
        self.assertNotIn(sentinel, json.dumps(report))
        self.assertIn(m.digest(('/' + sentinel).encode()), json.dumps(report))
        source = ("OVERLAY = '" + sentinel + "'\nclass _OwnerStatic:\n def get_response(self, raw):\n  return raw.replace('<head>', OVERLAY, 1)\n").encode()
        projection = m.serving_source_projection(source, 'bridge')
        self.assertEqual(projection['functions'][0]['function'], '_OwnerStatic.get_response')
        self.assertEqual(projection['functions'][0]['replacements'][0]['args'][1]['identifier'], 'OVERLAY')
        self.assertNotIn(sentinel, json.dumps(projection))
        self.assertIn(m.digest(sentinel.encode()), json.dumps(projection))

    def test_ui_mismatch_still_runs_exactly_one_guarded_own_chat_and_overall_holds(self):
        fixture_dir = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); site = root / 'site'; (site / 'pc').mkdir(parents=True)
            for name in m.EXPECTED:
                original = fixture_dir / ('source_after' if name.endswith('.html') else 'pc') / name
                (site / 'pc' / name).write_bytes(original.read_bytes())
            proxy, bridge, wrapper = (root / name for name in ('proxy.py', 'bridge.py', 'wrapper.py'))
            proxy.write_text('pass\n'); bridge.write_text('pass\n')
            wrapper.write_text("def proxy(raw):\n return raw.replace('<head>', '<head>unrecognized')\n")
            password = root / 'credential'; password.write_text('PRIVATE_PASSWORD_SENTINEL'); password.chmod(0o600)
            lock = root / 'owner.lock'; lock.touch()
            class Response(io.BytesIO):
                status = 200
            class Client:
                def __init__(self):
                    self.jar = []; self.created = 0; self.requested = 0; self.question = None
                def raw(self, path, data=None, **kwargs):
                    assert path == '/chat/login' and data == {'password': 'PRIVATE_PASSWORD_SENTINEL'}
                    self.jar.append('OWN_COOKIE_SENTINEL'); return b'{}'
                def asset(self, name, expected_raw):
                    raw = expected_raw.replace(b'<head>', b'<head><script>UNRECOGNIZED_OVERLAY</script>', 1) if name.endswith('.html') else expected_raw
                    return m.served_asset_diagnostic(name, raw, expected_raw, content_type='text/html')
                def json(self, path, data=None, **kwargs):
                    if path == '/slots':
                        return [{'is_processing': False}]
                    if path == '/api/ui/memory/dialogs/create':
                        self.created += 1
                        return {'dialog_id': 'a' * 32}
                    assert path == '/api/ui/memory/dialogs/history?dialog_id=' + 'a' * 32 + '&limit=2'
                    return {'messages': [{'role': 'user', 'content': self.question}, {'role': 'assistant', 'content': '42'}]}
                def request(self, path, data=None, **kwargs):
                    assert path == '/api/nox/chat/stream'
                    self.requested += 1; self.question = data['message']
                    assert data['dialog_id'] == 'a' * 32 and data['history'] == []
                    return Response(b'{"type":"delta","text":"42"}\n{"type":"done","saved":true,"s03_integrated":true}\n')
            client = Client()
            patches = {'PROXY': proxy, 'PROXY_SHA': m.digest(proxy.read_bytes()), 'BRIDGE': bridge,
                       'BRIDGE_SHA': m.digest(bridge.read_bytes()), 'WRAPPER': wrapper,
                       'WRAPPER_SHA': m.digest(wrapper.read_bytes()), 'SITE': site, 'LOCK': lock}
            with mock.patch.multiple(m, **patches), mock.patch.object(m, 'resolve_password_path', return_value=password), \
                 mock.patch.object(m, 'scoped_stop_supported', return_value=True), \
                 mock.patch.object(m, 'priority_snapshot', return_value={'CHAT_ACTIVE':'0', 'MODE':'IDLE'}), \
                 mock.patch.object(m, 'LoopbackClient', return_value=client), \
                 mock.patch.dict(m.os.environ, {'NOX_OWNER_REQUEST_ID': '123', 'NOX_OWNER_SOURCE_SHA': 'b' * 40}):
                result = m.run(True, expected_source_sha='b' * 40)
            self.assertEqual(client.created, 1); self.assertEqual(client.requested, 1)
            self.assertTrue(result['native_chat_canary_pass'])
            self.assertFalse(result['ui_asset_acceptance_pass'])
            self.assertFalse(result['native_canary_pass'])
            self.assertEqual(result['status'], 'HOLD_SERVED_ASSET_HASH')
            self.assertEqual(result['external_http_requests'], 0)
            self.assertEqual(client.jar, [])
            exported = json.dumps(result)
            for withheld in ('PRIVATE_PASSWORD_SENTINEL', 'OWN_COOKIE_SENTINEL', 'UNRECOGNIZED_OVERLAY', '<head>'):
                self.assertNotIn(withheld, exported)

if __name__ == '__main__':
    unittest.main()
