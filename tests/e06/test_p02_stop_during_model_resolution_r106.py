"""BOOST03 R106: deterministic original OneHost STOP/model-selection race regression.

Source-only fail-closed contract; never label stubbed owner as native E07 PASS.
"""
import ast
from contextlib import contextmanager, nullcontext
import hashlib
from pathlib import Path
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
P02 = ROOT / "Packages/P02/worker-python/p02_onehost.py"
STAGE = ROOT / "coordination/e06/stage_native_stdio.py"

class StubCancelled(Exception):
    pass

class StubHold(Exception):
    pass

class StubDenied(Exception):
    pass

class StubBase:
    chat_calls = 0

    def __init__(self, client, store, event_sink=None):
        self.client = client
        self.store = store

    def chat(self, session, payload):
        self.chat_calls += 1
        if self.stop_event.is_set():
            raise StubCancelled("STOP overtook the provider")
        return {"status": "OK"}

    def stop(self, session, args):
        return {"status": "STOPPED"}

class StubStore:
    def model_context(self, model):
        return nullcontext()

def load_original_onehost_class():
    """Run the exact owner Python class AST; no new process, DB, or provider."""
    original = P02.read_text(encoding="utf-8")
    tree = ast.parse(original, filename=str(P02))
    owner = next(node for node in tree.body
                 if isinstance(node, ast.ClassDef) and node.name == "OneHostP02")
    definition = ast.Module(body=[owner], type_ignores=[])
    namespace = {
        "ExistingP02Adapter": StubBase,
        "HostDenied": StubDenied,
        "HostHold": StubHold,
        "ProtocolHold": StubHold,
        "P02Error": StubHold,
        "P02Timeout": StubHold,
        "Cancelled": StubCancelled,
        "OllamaClient": lambda: object(),
        "threading": threading,
        "nullcontext": nullcontext,
        "contextmanager": contextmanager,
    }
    exec(compile(definition, str(P02), "exec"), namespace)
    return namespace["OneHostP02"]

def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()

class StopDuringModelSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Host = load_original_onehost_class()

    def host(self):
        instance = self.Host(StubStore(), client=object())
        instance._scope = lambda session, payload: (session, payload)
        instance.selected_model = lambda: "approved-local-model"
        return instance

    def test_stop_while_model_inventory_blocked_never_clears_cancel(self):
        host = self.host()
        entered = threading.Event()
        release = threading.Event()
        result = []
        def model_list(session, payload):
            entered.set()
            if not release.wait(3):
                raise AssertionError("model resolver wait expired")
            return None
        host.list_models = model_list
        def chat():
            try:
                result.append(("OK", host.chat(object(), {"text": "hello", "model": "approved-local-model"})))
            except Exception as exc:
                result.append((type(exc).__name__, str(exc)))
        worker = threading.Thread(target=chat)
        worker.start()
        self.assertTrue(entered.wait(3), "original chat must enter model lookup")
        host.stop(object(), {})
        release.set()
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result, [("StubHold", "NATIVE_CHAT_STOP")])
        self.assertTrue(host.stop_event.is_set(), "a completed STOP cannot be cleared")
        self.assertEqual(host.chat_calls, 0, "no chat provider invocation after STOP")

    def test_later_explicit_new_chat_can_rearm_without_a_race(self):
        host = self.host()
        host.stop(object(), {})
        response = host.chat(object(), {"text": "fresh"})
        self.assertEqual(response["status"], "OK")
        self.assertFalse(host.stop_event.is_set())
        self.assertEqual(host.chat_calls, 1)

    def test_invalid_scoped_request_does_not_rearm_stopped_host(self):
        host = self.host()
        host.stop(object(), {})
        def deny(session, payload):
            raise StubDenied("native scope denied")
        host._scope = deny
        with self.assertRaisesRegex(StubDenied, "native scope denied"):
            host.chat(object(), {"text": "invalid"})
        self.assertTrue(host.stop_event.is_set())

    def test_exact_approved_p02_source_pin_is_updated(self):
        source = P02.read_bytes()
        stage = STAGE.read_text(encoding="utf-8")
        match = ("('Packages/P02/worker-python/p02_onehost.py', "
                 "'p02_onehost.py', '" + git_blob(source) + "')")
        self.assertEqual(stage.count(match), 1)
        self.assertIn("self._stop_generation != chat_stop_generation",
                      source.decode("utf-8"))
        self.assertIn("self._stop_generation += 1", source.decode("utf-8"))

if __name__ == "__main__":
    unittest.main()
