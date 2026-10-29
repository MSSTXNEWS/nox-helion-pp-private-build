"""G2-A R30: source-only events.v3 error-code admission regression.

Exact existing P02EventRelay is loaded with minimal host-owned dependency
stubs. No network, extra host, database, installation or native Windows run.
"""
import importlib.util
import pathlib
import sys
import types
import unittest


class P02Error(Exception):
    pass


class Identity:
    tenant = "tenant"
    principal = "principal"


class ChatBridge:
    @staticmethod
    def _safe_citation_url(url):
        return isinstance(url, str) and url.startswith("https://")


def load_native_relay():
    stubs = {
        "p02_runtime": types.SimpleNamespace(P02Error=P02Error),
        "p02_capabilities": types.SimpleNamespace(Identity=Identity),
        "p02_chat_bridge": types.SimpleNamespace(ChatBridge=ChatBridge),
    }
    prior = {name: sys.modules.get(name) for name in stubs}
    try:
        sys.modules.update(stubs)
        file = pathlib.Path(__file__).with_name("p02_host_admission.py")
        spec = importlib.util.spec_from_file_location("p02_r30_g2a_admission", file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, module in prior.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class G2AChatErrorCodeGate(unittest.TestCase):
    def setUp(self):
        self.mod = load_native_relay()
        self.run = "a" * 32
        self.sent = []
        self.routes = {name: "host:" + name for name in self.mod.P02_TYPES}
        binding = self.mod.NativeHostBinding(
            Identity(), True, frozenset(self.routes.values()),
            self.routes, lambda name, payload: self.sent.append((name, payload)))
        self.relay = self.mod.P02EventRelay(binding)
        self.relay.relay({"type": "chat.start", "run_id": self.run,
                          "model": "local-verified"})

    def error(self, code):
        return {"type": "chat.error", "run_id": self.run,
                "code": code, "detail": "native provider status"}

    def test_control_bidi_and_ambiguous_codes_never_publish(self):
        invalid = (
            "", "STOP\\nINJECT", "STOP\\r", "STOP\\x00", "STOP\\u202e",
            "timeout", "0STOP", "STOP-FAILED", "Z" * 33,
        )
        # Evaluate the escaped probes into the actual boundary characters.
        for index, code in enumerate(invalid):
            if index in (1, 2, 3, 4):
                code = code.encode("utf-8").decode("unicode_escape")
            with self.subTest(code=repr(code)):
                with self.assertRaisesRegex(P02Error, "CHAT_ERROR_SCHEMA_INVALID"):
                    self.relay.relay(self.error(code))
                self.assertEqual(len(self.sent), 1)

    def test_existing_stop_timeout_and_ollama_codes_admitted(self):
        for code in ("STOP", "TIMEOUT", "OLLAMA_ERROR", "Z" * 32):
            with self.subTest(code=code):
                self.setUp()
                self.relay.relay(self.error(code))
                self.assertEqual(len(self.sent), 2)
                self.assertEqual(self.sent[-1][1]["code"], code)

    def test_native_destination_is_snapshot_not_mutable_registry(self):
        self.routes["chat.error"] = "host:privileged-install"
        self.relay.relay(self.error("STOP"))
        self.assertEqual(self.sent[-1][0], "host:chat.error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
