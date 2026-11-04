"""Installed NOX HELION auto-selects ONLY already installed named local model.
Original OneHost AST is executed, not a replacement transport or fake E07.
"""
from __future__ import annotations
import ast
from contextlib import contextmanager, nullcontext
from pathlib import Path
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Packages/P02/worker-python/p02_onehost.py"

class Held(Exception): pass
class Denied(Exception): pass
class Cancelled(Exception): pass

class Store:
    def __init__(self, safe=True): self.safe, self.lineage_calls = safe, 0
    def assert_model_switch_safe(self):
        self.lineage_calls += 1
        if not self.safe: raise Held("S03_LINEAGE_HOLD")
    def lineage_status(self): return {"status":"OK" if self.safe else "HOLD"}
    def model_context(self, name): return nullcontext()

class Client:
    def __init__(self, installed, block=False):
        self.installed=list(installed);self.block=block
        self.enter=threading.Event();self.release=threading.Event()
    def models(self):
        self.enter.set()
        if self.block and not self.release.wait(3): raise AssertionError("WAIT_TIMEOUT")
        return list(self.installed)
    def stop(self): pass

class Base:
    def __init__(self, client, store, event_sink=None):
        self.client, self.store = client, store
        self._stop_epoch=0
    def chat(self, session, payload): return {"status":"OK","model":payload["model"]}
    def stop(self, session, args):
        self._stop_epoch += 1
        return {"status":"STOPPED"}

def owner_class():
    tree=ast.parse(SOURCE.read_text(encoding="utf-8"),str(SOURCE))
    cl=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=="OneHostP02")
    ns=dict(ExistingP02Adapter=Base,HostDenied=Denied,HostHold=Held,
            ProtocolHold=Held,P02Error=Held,P02Timeout=Held,
            Cancelled=Cancelled,OllamaClient=Client,threading=threading,
            contextmanager=contextmanager,replace=lambda x,**k:x)
    exec(compile(ast.Module(body=[cl],type_ignores=[]),str(SOURCE),"exec"),ns)
    return ns["OneHostP02"]

class LocalFirstbootModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.Host=owner_class()
    def make(self,installed,safe=True,block=False):
        store=Store(safe);client=Client(installed,block)
        host=self.Host(store,client=client)
        host._scope=lambda session,args:(session,args)
        return host,client,store
    def test_nox_helion_selected_when_installed_and_s03_safe(self):
        host,client,store=self.make(["qwen3:8b","nox-helion:latest","qwen2.5-coder:7b"])
        r=host.list_models(object(),{})
        self.assertEqual(r["selectedModel"],"nox-helion:latest")
        self.assertEqual(r["source"],"EXISTING_P02_OLLAMA")
        self.assertEqual(store.lineage_calls,1)
        self.assertEqual(host.chat(object(),{"text":"Hello"})["model"],"nox-helion:latest")
    def test_manual_selection_remains_authoritative(self):
        host,client,store=self.make(["nox-helion:latest","qwen3:8b"])
        self.assertEqual(host.list_models(object(),{"model":"qwen3:8b"})["selectedModel"],"qwen3:8b")
        self.assertEqual(host.list_models(object(),{})["selectedModel"],"qwen3:8b")
    def test_no_local_nox_model_no_implicit_selection(self):
        host,_,_=self.make(["qwen3:8b","qwen2.5-coder:7b"])
        self.assertIsNone(host.list_models(object(),{})["selectedModel"])
    def test_s03_lineage_hold_never_commits_default(self):
        host,_,_=self.make(["nox-helion:latest"],safe=False)
        with self.assertRaisesRegex(Held,"S03_LINEAGE_HOLD"):
            host.list_models(object(),{})
        self.assertIsNone(host.selected_model())
    def test_stop_during_inventory_cannot_default_or_rearm(self):
        host,client,_=self.make(["nox-helion:latest"],block=True)
        seen=[]
        t=threading.Thread(target=lambda:seen.append(host.list_models(object(),{})))
        t.start();self.assertTrue(client.enter.wait(3));host.stop(object(),{})
        client.release.set();t.join(3);self.assertFalse(t.is_alive())
        self.assertEqual(len(seen),1)
        self.assertIsNone(seen[0]["selectedModel"])
        self.assertTrue(host.stop_event.is_set())

if __name__=="__main__": unittest.main()
