"""Owner P02 detached events.v3 payload regression; no native host or LLM started."""
import importlib.util
import pathlib
import sys
import types
import unittest
import urllib.parse


class P02Error(Exception):
    pass


class Identity:
    tenant = 't1'
    principal = 'u1'


class ChatBridge:
    @staticmethod
    def _safe_citation_url(url):
        return isinstance(url, str) and url.startswith('https://') and '@' not in urllib.parse.urlsplit(url).netloc


def load_source():
    mods = {
        'p02_runtime': types.SimpleNamespace(P02Error=P02Error),
        'p02_capabilities': types.SimpleNamespace(Identity=Identity),
        'p02_chat_bridge': types.SimpleNamespace(ChatBridge=ChatBridge),
    }
    backup = {k: sys.modules.get(k) for k in mods}
    try:
        sys.modules.update(mods)
        path = pathlib.Path(__file__).with_name('p02_host_admission.py')
        spec = importlib.util.spec_from_file_location('p02_exact_r14', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for key, old in backup.items():
            if old is None: sys.modules.pop(key, None)
            else: sys.modules[key] = old


class TestDetachedEvent(unittest.TestCase):
    def test_original_citation_cannot_mutate_after_validation(self):
        mod = load_source()
        delivered = []
        routes = {name: 'v3:' + name for name in mod.P02_TYPES}
        binding = mod.NativeHostBinding(Identity(), True, frozenset(routes.values()),
                                        routes, lambda kind, obj: delivered.append(obj))
        relay = mod.P02EventRelay(binding)
        nonce = 'a' * 32
        relay.relay({'type': 'chat.start', 'run_id': nonce, 'model': 'qwen'})
        ev = {'type': 'chat.sources', 'run_id': nonce, 'sources': [
            {'source_id': 'one', 'title': 'Verified', 'url': 'https://example.com'}]}
        relay.relay(ev)
        ev['sources'][0]['url'] = 'javascript:unsafe()'
        ev['sources'].append({'source_id': 'two', 'title': 'Late', 'url': 'https://example.com'})
        self.assertEqual(delivered[-1]['sources'], [
            {'source_id': 'one', 'title': 'Verified', 'url': 'https://example.com'}])
        delivered[-1]['sources'][0]['title'] = 'host changed'
        self.assertEqual(ev['sources'][0]['title'], 'Verified')


if __name__ == '__main__':
    unittest.main()
