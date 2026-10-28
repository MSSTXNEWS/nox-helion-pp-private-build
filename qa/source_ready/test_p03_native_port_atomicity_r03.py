"""NOX V16 §47 independent P03 no-op dispatcher contract regression.

Imports the real P03 ONEHOST module by path; tests only existing-owner ports.
The fail-closed no-op cases are intentionally RED until owner #1 implements
post-bind identity checks with rollback. This is source-level, not Windows E07.
Run: python -m unittest discover -s qa/source_ready -p 'test_p03_native_port_atomicity_r03.py' -v
"""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
OWNER = ROOT / "Packages/P03/Source/python-host/p03_onehost_port.py"


def load_owner():
    spec = importlib.util.spec_from_file_location("nox_p03_owner_qa_r03", OWNER)
    if spec is None or spec.loader is None:
        raise AssertionError("P03_OWNER_MODULE_NOT_FOUND")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakePort:
    def __init__(self, call, available, receipt, owner):
        self.call = call
        self.available = available
        self.receipt = receipt
        self.owner = owner


class OriginalHost:
    def __init__(self, behavior="normal"):
        self.routes = {name: {"owner": 3} for name in
                       ("models.catalog", "models.installed", "models.digest")}
        self.ports = {}
        self.behavior = behavior
        self.count = 0

    def bind(self, name, port):
        self.count += 1
        if self.behavior == "silent_all":
            return
        if self.behavior == "silent_second" and self.count == 2:
            return
        self.ports[name] = port
        if self.behavior == "raise_second" and self.count == 2:
            raise OSError("Injected original host bind failure")


class P03PortAdmissionNegative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_owner()

    def owner(self):
        instance = self.mod.P03OneHostPort.__new__(self.mod.P03OneHostPort)
        instance.backend = None
        instance.native_approve = None
        return instance

    def test_three_real_bindings_positive(self):
        host = OriginalHost()
        result = self.owner().register(host, FakePort, receipt="owner3-pin")
        self.assertEqual(result, frozenset(host.routes))
        self.assertEqual(set(host.ports), set(host.routes))
        self.assertTrue(all(p.owner == 3 for p in host.ports.values()))

    def test_second_bind_exception_rolls_back_owner_ports(self):
        host = OriginalHost("raise_second")
        with self.assertRaises(self.mod.P03PortHold):
            self.owner().register(host, FakePort, receipt="owner3-pin")
        self.assertEqual(host.ports, {}, "No partially published ModelCenter owner ports")

    def test_silent_host_no_op_must_fail_closed(self):
        host = OriginalHost("silent_all")
        with self.assertRaises(self.mod.P03PortHold):
            self.owner().register(host, FakePort, receipt="owner3-pin")
        self.assertEqual(host.ports, {}, "No phantom ModelCenter routes")

    def test_second_no_op_must_fail_with_atomic_rollback(self):
        host = OriginalHost("silent_second")
        with self.assertRaises(self.mod.P03PortHold):
            self.owner().register(host, FakePort, receipt="owner3-pin")
        self.assertEqual(host.ports, {}, "No mixed partially live ModelCenter route set")


if __name__ == "__main__":
    unittest.main()
