"""P02 owner source-label spoofing regression; native Windows host NOT_RUN."""
import importlib.util
import pathlib
import sys
import types
import unittest

class P02Error(Exception): pass
class Identity:
    tenant = 'tenant'
    principal = 'principal'
class ChatBridge:
    @staticmethod
    def _safe_citation_url(url): return url.startswith('https://')

class RelayLabelGate(unittest.TestCase):
    def test_labels(self):
        dependencies = {'p02_runtime': types.SimpleNamespace(P02Error=P02Error),
                        'p02_capabilities': types.SimpleNamespace(Identity=Identity),
                        'p02_chat_bridge': types.SimpleNamespace(ChatBridge=ChatBridge)}
        previous = {k: sys.modules.get(k) for k in dependencies}
        try:
            sys.modules.update(dependencies)
            path = pathlib.Path(__file__).with_name('p02_host_admission.py')
            spec = importlib.util.spec_from_file_location('p02_label_gate', path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            for key, value in previous.items():
                if value is None: sys.modules.pop(key, None)
                else: sys.modules[key] = value
        published = []
        routes = {name: 'v3:' + name for name in module.P02_TYPES}
        relay = module.P02EventRelay(module.NativeHostBinding(
            Identity(), True, frozenset(routes.values()), routes,
            lambda name, payload: published.append(payload)))
        run_id = 'c' * 32
        relay.relay({'type':'chat.start','run_id':run_id,'model':'local'})
        for label_id, title in [('doc\u202Eevil','Valid'), ('doc','Title\u2066spoof'),
                                 ('doc\ninvalid','Valid'), ('doc','Title\rspoof')]:
            with self.subTest(label_id=label_id, title=title):
                with self.assertRaises(P02Error):
                    relay.relay({'type':'chat.sources','run_id':run_id,
                        'sources':[{'source_id':label_id,'title':title}]})
                self.assertEqual(len(published),1)
        relay.relay({'type':'chat.sources','run_id':run_id,
                     'sources':[{'source_id':'es-ñ','title':'История de España'}]})
        self.assertEqual(len(published),2)

if __name__ == '__main__': unittest.main()
