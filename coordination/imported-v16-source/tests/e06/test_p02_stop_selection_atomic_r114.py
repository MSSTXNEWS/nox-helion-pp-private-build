"""BOOST03 R114: STOP overtaking live model resolution cannot commit selection.

Executes original OneHostP02 AST with authenticated owner-scoped test doubles;
no network, GPU, model download, external backend or Windows acceptance claim.
"""
import ast
from contextlib import contextmanager, nullcontext
import hashlib
from pathlib import Path
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Packages/P02/worker-python/p02_onehost.py"
STAGE = ROOT / "coordination/e06/stage_native_stdio.py"

class Held(Exception):
    pass

class Denied(Exception):
    pass

class Cancelled(Exception):
    pass

class Store:
    def assert_model_switch_safe(self):
        return None
    def lineage_status(self):
        return {"status": "OK"}
    def model_context(self, model):
        return nullcontext()

class Client:
    def __init__(self, *, blocking=False):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.blocking = blocking
        self.stops = 0
    def models(self):
        self.entered.set()
        if self.blocking and not self.release.wait(3):
            raise AssertionError("MODELS_WAIT_TIMED_OUT")
        return ["prior", "new"]
    def stop(self):
        self.stops += 1

class Base:
    def __init__(self, client, store, event_sink=None):
        self.client, self.store = client, store
        self._stop_epoch = 0
        self.chat_calls = 0
    def chat(self, session, payload):
        self.chat_calls += 1
        return {"status": "OK", "model": payload["model"]}
    def stop(self, session, args):
        self._stop_epoch += 1
        self.client.stop()
        return {"stopRequested": True}

def original_host():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    node = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == "OneHostP02")
    ns = dict(ExistingP02Adapter=Base, HostDenied=Denied, HostHold=Held,
              ProtocolHold=Held, P02Error=Held, P02Timeout=Held,
              Cancelled=Cancelled, OllamaClient=Client,
              threading=threading, contextmanager=contextmanager,
              replace=lambda session, **kwargs: session)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns["OneHostP02"]

def git_blob(content):
    return hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + bytes([0]) + content).hexdigest()

class StopSelectionAtomic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Host = original_host()
    def host(self, blocking=False):
        client = Client(blocking=blocking)
        host = self.Host(Store(), client=client)
        host._scope = lambda session, args: (session, args)
        host._selected = "prior"
        return host, client
    def raced(self, action):
        host, client = self.host(True)
        observed = []
        def worker():
            try:
                observed.append(("OK", action(host)))
            except Exception as exc:
                observed.append((type(exc).__name__, str(exc)))
        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(client.entered.wait(3), "must reach blocked real owner inventory call")
        host.stop(object(), {})
        client.release.set()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(observed, [("Held", "NATIVE_CHAT_STOP")])
        self.assertEqual(host._selected, "prior", "canceled request cannot change selected model")
        self.assertTrue(host.stop_event.is_set())
        self.assertEqual(host.chat_calls, 0)
    def test_stop_during_explicit_chat_model_lookup_keeps_prior_selection(self):
        self.raced(lambda h: h.chat(object(), {"text": "hi", "model": "new"}))
    def test_stop_during_standalone_model_selection_keeps_prior_selection(self):
        self.raced(lambda h: h.list_models(object(), {"model": "new"}))
    def test_later_new_model_request_after_stop_can_select(self):
        host, client = self.host()
        host.stop(object(), {})
        res = host.list_models(object(), {"model": "new"})
        self.assertEqual(res["selectedModel"], "new")
        self.assertEqual(host._selected, "new")
        self.assertTrue(host.stop_event.is_set(), "model selection never re-arms stopped chat")
    def test_no_stop_keeps_existing_explicit_chat_model_behavior(self):
        host, client = self.host()
        res = host.chat(object(), {"text": "hi", "model": "new"})
        self.assertEqual(res["model"], "new")
        self.assertEqual(host._selected, "new")
        self.assertEqual(host.chat_calls, 1)
    def test_exact_source_pin(self):
        source = SOURCE.read_bytes()
        expected = ("('Packages/P02/worker-python/p02_onehost.py', "
                    "'p02_onehost.py', '" + git_blob(source) + "')")
        self.assertEqual(STAGE.read_text(encoding="utf-8").count(expected), 1)
if __name__ == "__main__":
    unittest.main()
