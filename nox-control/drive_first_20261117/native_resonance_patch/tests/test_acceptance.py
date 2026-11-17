import importlib.util
import io
import json
from pathlib import Path
import tempfile
import time
import unittest

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

if __name__ == '__main__':
    unittest.main()
