"""E06 R07 P02↔P04 STOP/citation boundary: offline owner stubs only.

Never count as real Windows, SQLite persistence, Ollama or GPU verification.
"""
from __future__ import annotations
import importlib.util
import sys
import threading
import types
import unittest
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Identity:
    tenant: str = "tenant"
    principal: str = "user"
    core_id: str = "CORE-1"
    persona_id: str = "PERSONA-1"
    session_id: str = "session-1"


@dataclass(frozen=True)
class NativeScope:
    tenant: str = "tenant"
    principal: str = "user"
    conversation_id: str = "existing"
    windows_sid: str = "S-1-5-21-1234"
    session_id: str = "session-1"
    identity: Identity = Identity()


class OllamaClient:
    base = "http://127.0.0.1:11434"


class P02Store:
    def history(self, tenant, principal, chat, limit=1):
        assert (tenant, principal, chat) == ("tenant", "user", "existing")
        return []


class ChatBridge:
    def __init__(self, store, ollama):
        self.store, self.ollama, self.rag_context = store, ollama, None

    def send(self, *args):
        yield {"type": "chat.sources", "sources": [{"id": "trusted"}]}


class LocalRag:
    endpoint = "http://127.0.0.1:11434/api/embed"


def context_key(identity, cores, personas):
    assert identity.core_id in cores and identity.persona_id in personas
    return "existing"


def load_seam():
    exports = {
        "p02_capabilities": {"context_key": context_key},
        "p02_chat_bridge": {"ChatBridge": ChatBridge},
        "p02_owner_route_ports": {"NativeScope": NativeScope},
        "p02_runtime": {"OllamaClient": OllamaClient, "P02Store": P02Store},
        "rag_python_compat": {"LocalRag": LocalRag, "p02_callback": lambda *a: (lambda *a: None)},
    }
    previous = {k: sys.modules.get(k) for k in exports}
    try:
        for name, members in exports.items():
            stub = types.ModuleType(name)
            stub.__dict__.update(members)
            sys.modules[name] = stub
        path = Path(__file__).resolve().parents[2] / "coordination/e06/onehost_p02_p04.py"
        spec = importlib.util.spec_from_file_location("e06_stop_gate_under_test", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for name, prior in previous.items():
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior


SEAM = load_seam()


class E06StopInterlock(unittest.TestCase):
    def setUp(self):
        self.chat = ChatBridge(P02Store(), OllamaClient())
        self.calls = 0
        self.seam = SEAM.P02P04OneHost(
            chat=self.chat, store=self.chat.store, rag=LocalRag(),
            native_sid=lambda *a: "S-1-5-21-1234",
            native_context_chat=lambda *a: "existing",
            native_authorize=self.authorize,
            approved_core_ids=frozenset(f"CORE-{i}" for i in range(1, 9)),
            approved_personas=frozenset(f"PERSONA-{i}" for i in range(1, 6)),
            native_verify_registry=lambda *a: True,
        )

    def authorize(self, scope, operation):
        self.calls += 1
        return operation == "chat.send"

    def stream(self, stop):
        return self.seam.stream_chat(NativeScope(), "installed-model", "hello", stop)

    def test_01_cancel_before_first_next_skips_owner(self):
        stop, advanced = threading.Event(), []
        def owner(*args):
            advanced.append("next")
            yield {"type": "chat.sources"}
        self.chat.send = owner
        stream = self.stream(stop)
        stop.set()
        with self.assertRaises(StopIteration):
            next(stream)
        self.assertEqual(advanced, [])

    def test_02_cancel_after_start_blocks_private_sources(self):
        stop, advanced = threading.Event(), []
        def owner(*args):
            yield {"type": "chat.start"}
            advanced.append("sources")
            yield {"type": "chat.sources", "sources": [{"id": "private"}]}
        self.chat.send = owner
        stream = self.stream(stop)
        self.assertEqual(next(stream)["type"], "chat.start")
        stop.set()
        with self.assertRaises(StopIteration):
            next(stream)
        self.assertEqual(advanced, [])

    def test_03_cancel_while_owner_next_blocks_new_frame(self):
        stop = threading.Event()
        def owner(*args):
            yield {"type": "chat.start"}
            stop.set()
            yield {"type": "chat.sources", "sources": [{"id": "private"}]}
        self.chat.send = owner
        stream = self.stream(stop)
        self.assertEqual(next(stream)["type"], "chat.start")
        with self.assertRaises(StopIteration):
            next(stream)

    def test_04_cancel_during_post_owner_authorization(self):
        stop = threading.Event()
        original = self.seam._authorize
        def auth(scope, operation):
            allowed = original(scope, operation)
            if self.calls == 3:
                stop.set()
            return allowed
        self.seam._authorize = auth
        with self.assertRaises(StopIteration):
            next(self.stream(stop))

    def test_05_normal_frame_and_owner_stop_token_survive(self):
        stop = threading.Event()
        stream = self.stream(stop)
        self.assertEqual(next(stream)["type"], "chat.sources")
        stream.close()
        self.assertTrue(stop.is_set())

    def test_06_real_owner_terminal_error_without_cancel_passes(self):
        stop = threading.Event()
        self.chat.send = lambda *args: (x for x in [{"type": "chat.error", "code": "STOP"}])
        stream = self.stream(stop)
        self.assertEqual(next(stream)["code"], "STOP")
        stream.close()


if __name__ == "__main__":
    unittest.main()
