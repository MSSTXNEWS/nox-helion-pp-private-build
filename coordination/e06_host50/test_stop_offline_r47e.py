"""G2-A NIP01-09: emergency STOP must not depend on model-list readiness.
Exact native_bridge.py component test; no WPF/native-install claims.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "proposals" / "NOX-PACK01-50" / "native_bridge.py"
spec = importlib.util.spec_from_file_location("nox_g2a_stop_source", PATH)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class OfflineOllama:
    def __init__(self):
        self.probes = 0
        self.stop_calls = 0
    def models(self):
        self.probes += 1
        raise ConnectionError("Ollama daemon unavailable")
    def stream(self, *args):
        raise ConnectionError("Ollama unavailable")
    def stop(self):
        self.stop_calls += 1

class Store:
    def history(self, *args): return []
    def add_message(self, *args): return None
    def store_file(self, *args): return "no-data"

class EmergencyStopOfflineTests(unittest.TestCase):
    def setUp(self):
        self.client = OfflineOllama()
        catalog = {"version": "NOX-INTEGRATION-PACK-01", "actions": [
            {"routeId": route, "taskId": f"NIP01-{i:02d}",
             "owner": owner, "risk": risk}
            for i, (route, owner, risk) in enumerate(bridge.APPROVED_NATIVE_POLICY, 1)
        ]}
        self.host = bridge.NoxPackHost(catalog)
        bridge.ExistingP02Adapter(self.client, Store()).register(self.host, receipt="TEST_OWNER_PIN")
        self.session = bridge.NativeSession("tenant", "principal", "chat",
            allowed=frozenset({"chat.stop", "helion.chat"}))

    def test_stop_executes_without_model_probe(self):
        reply = self.host.execute("chat.stop", {}, self.session)
        self.assertEqual(reply, {"stopRequested": True})
        self.assertEqual(self.client.stop_calls, 1)
        self.assertEqual(self.client.probes, 0)

    def test_chat_remains_hold_when_backend_offline(self):
        with self.assertRaises(bridge.HostHold):
            self.host.execute("helion.chat", {"text": "hello"}, self.session)
        self.assertEqual(self.client.stop_calls, 0)
        self.assertEqual(self.client.probes, 1)

    def test_stop_cannot_bypass_acl(self):
        denied = bridge.NativeSession("tenant", "principal", "chat", allowed=frozenset())
        with self.assertRaises(bridge.HostDenied):
            self.host.execute("chat.stop", {}, denied)
        self.assertEqual(self.client.stop_calls, 0)
        self.assertEqual(self.client.probes, 0)

if __name__ == "__main__":
    unittest.main()
