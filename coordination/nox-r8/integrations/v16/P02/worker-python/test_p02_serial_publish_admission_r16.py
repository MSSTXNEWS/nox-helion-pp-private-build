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

def load_owner():
    dependencies={'p02_runtime':types.SimpleNamespace(P02Error=P02Error),
                  'p02_capabilities':types.SimpleNamespace(Identity=Identity),
                  'p02_chat_bridge':types.SimpleNamespace(ChatBridge=ChatBridge)}
    previous={k:sys.modules.get(k) for k in dependencies}
    try:
        sys.modules.update(dependencies)
        path=pathlib.Path(__file__).with_name('p02_host_admission.py')
        spec=importlib.util.spec_from_file_location('p02_serial_admission_r16',path)
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        return module
    finally:
        for k,v in previous.items():
            if v is None:sys.modules.pop(k,None)
            else:sys.modules[k]=v

class SerialPublishAdmission(unittest.TestCase):
    def setUp(self):
        self.mod=load_owner()
        self.routes={name:'v3:'+name for name in self.mod.P02_TYPES}
        self.run='d'*32
        self.start={'type':'chat.start','run_id':self.run,'model':'local'}
    def binding(self,publish):
        return self.mod.P02EventRelay(self.mod.NativeHostBinding(
            Identity(),True,frozenset(self.routes.values()),self.routes,publish))
    def test_reentrant_duplicate_start(self):
        published=[];denied=[];relay=None
        def publish(name,payload):
            published.append(name)
            if len(published)==1:
                try:relay.relay(self.start)
                except P02Error as e:denied.append(str(e))
        relay=self.binding(publish)
        relay.relay(self.start)
        self.assertEqual(len(published),1)
        self.assertEqual(len(denied),1)
    def test_parallel_duplicate_start(self):
        import threading
        entered=threading.Event();release=threading.Event();published=[];errors=[]
        def publish(name,payload):
            published.append(name);entered.set()
            if not release.wait(2):raise TimeoutError('test publisher release timeout')
        relay=self.binding(publish)
        def worker():
            try:relay.relay(self.start)
            except Exception as e:errors.append(type(e).__name__)
        thread=threading.Thread(target=worker,daemon=True);thread.start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaises(P02Error):relay.relay(self.start)
            self.assertEqual(len(published),1)
        finally:
            release.set();thread.join(timeout=3)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
    def test_publish_failure_allows_retry(self):
        delivered=[]
        def publish(name,payload):
            delivered.append(name)
            if len(delivered)==1:raise RuntimeError('publish failed')
        relay=self.binding(publish)
        with self.assertRaises(RuntimeError):relay.relay(self.start)
        relay.relay(self.start)
        relay.relay({'type':'chat.delta','run_id':self.run,'text':'Hola'})
        self.assertEqual(len(delivered),3)

if __name__=='__main__':unittest.main()
