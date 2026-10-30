"""R63 · real Python threads and shared SQLite: STOP before late COMMIT."""
import sqlite3, tempfile, threading, unittest
from pathlib import Path
from p02_runtime import P02Store, Cancelled
from native_bridge import ExistingP02Adapter, NativeSession, HostHold

class FakeClient:
    def __init__(self): self.enter=None;self.release=None
    def models(self):
        if self.enter:
            self.enter.set();self.release.wait(2)
        return ["tiny"]
    def stream(self, model, messages, stop=None):
        yield {"delta":"ready","done":False}
        yield {"delta":"","done":True}
    def stop(self): pass

class StopWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=sqlite3.connect(":memory:", check_same_thread=False)
        self.store=P02Store(self.db,Path(self.tmp.name)/"att")
        self.store.initialize()
        self.store.create_chat("t","p","c")
        self.client=FakeClient()
        self.adapter=ExistingP02Adapter(self.client,self.store)
        self.scope=NativeSession("t","p","c")
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def history(self):return self.store.history("t","p","c")
    def worker(self):
        output=[]
        def run():
            try:output.append(self.adapter.chat(self.scope,{"text":"question","model":"tiny"}))
            except Exception as exc:output.append(exc)
        thread=threading.Thread(target=run);thread.start()
        return thread,output
    def test_stop_after_last_token_before_commit(self):
        entered=threading.Event();release=threading.Event()
        original=self.store.add_turn
        def delayed(*args,**kwargs):
            entered.set()
            if not release.wait(2):raise RuntimeError("Missing test synchronization")
            return original(*args,**kwargs)
        self.store.add_turn=delayed
        worker,result=self.worker()
        try:
            self.assertTrue(entered.wait(1))
            self.assertTrue(self.adapter.stop(self.scope,{})["stopRequested"])
        finally:
            release.set();worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.history(),[])
        self.assertEqual(len(result),1)
        self.assertIsInstance(result[0],Cancelled)
    def test_stop_during_model_discovery_never_starts_chat(self):
        self.client.enter=threading.Event()
        self.client.release=threading.Event()
        worker,result=self.worker()
        try:
            self.assertTrue(self.client.enter.wait(1))
            self.adapter.stop(self.scope,{})
        finally:
            self.client.release.set();worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.history(),[])
        self.assertEqual(len(result),1)
        self.assertIsInstance(result[0],HostHold)
    def test_normal_completion_persists_one_turn(self):
        answer=self.adapter.chat(self.scope,{"text":"question","model":"tiny"})
        self.assertEqual(answer,{"answer":"ready","done":True})
        self.assertEqual([(m["role"],m["content"]) for m in self.history()],
                         [("user","question"),("assistant","ready")])
if __name__=="__main__":unittest.main()
