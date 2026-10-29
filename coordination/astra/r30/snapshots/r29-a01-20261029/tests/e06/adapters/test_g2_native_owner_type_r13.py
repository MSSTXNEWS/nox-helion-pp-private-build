"""E06 in-process regression: exact P02/P03 native BoundPort owner/receipt types.
Windows: python -m unittest discover -s tests/e06/adapters -p test_g2_native_owner_type_r13.py
Synthetic owner registry; native Windows EXE / Ollama / GPU not exercised.
"""
import pathlib
import sys
import threading
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "coordination" / "e06" / "adapters"))
from g2_space_mobile import G2Hold, G2OneHostBinder, P02_REQUIRED, P03_REQUIRED

class Port:
    def __init__(self, evidence_id, owner):
        self.evidence_id, self.owner = evidence_id, owner

class Host:
    def __init__(self):
        self.routes = {name: {"owner": 2} for name in P02_REQUIRED}
        self.routes.update({name: {"owner": 3} for name in P03_REQUIRED})
        self.ports = {}
    def bind(self, route, port):
        self.ports[route] = port

class P02:
    def __init__(self, owner=2, evidence=None):
        self.owner, self.evidence = owner, evidence
    def register(self, host, *, receipt):
        for r in P02_REQUIRED:
            host.ports[r] = Port(receipt if self.evidence is None else self.evidence, self.owner)
        return frozenset(P02_REQUIRED)

class P03:
    def __init__(self, owner=3):
        self.owner = owner
    def register(self, host, port_type, *, receipt):
        for r in P03_REQUIRED:
            host.ports[r] = port_type(receipt, self.owner)
        return frozenset(P03_REQUIRED)

class E05:
    def available(self, route):
        return False

def make_binder(*, owner2=2, owner3=3, evidence=None):
    host = Host()
    binder = G2OneHostBinder(host, Port, existing_p02=P02(owner2, evidence),
        existing_p03=P03(owner3), e05=E05(), mobile=None, existing_p02_voice=None,
        source_lock_sha256="a" * 64,
        owner_receipts_sha256={"P02": "b" * 64, "P03": "c" * 64, "P05": "d" * 64},
        verify_original_preimages=lambda source, receipts: True,
        existing_host_mutation_lock=threading.RLock())
    return host, binder

class ExactOwnerType(unittest.TestCase):
    def test_real_integer_and_string_receipts_admit(self):
        host, binder = make_binder()
        self.assertEqual(binder.bind(), P02_REQUIRED | P03_REQUIRED)
        self.assertTrue(host.ports)

    def test_float_owner_2_rejected_with_rollback(self):
        host, binder = make_binder(owner2=2.0)
        with self.assertRaises(G2Hold): binder.bind()
        self.assertFalse(host.ports)

    def test_complex_owner_3_rejected_with_rollback(self):
        host, binder = make_binder(owner3=3+0j)
        with self.assertRaises(G2Hold): binder.bind()
        self.assertFalse(host.ports)

    def test_receipt_string_subclass_rejected(self):
        class DigestAlias(str): pass
        host, binder = make_binder(evidence=DigestAlias("b"*64))
        with self.assertRaises(G2Hold): binder.bind()
        self.assertFalse(host.ports)

    def test_existing_port_preserved_on_failed_registration(self):
        host, binder = make_binder(owner2=2.0)
        previous = Port("a"*64, 9)
        host.ports["existing.owner.port"] = previous
        with self.assertRaises(G2Hold): binder.bind()
        self.assertIs(host.ports["existing.owner.port"], previous)
        self.assertEqual(len(host.ports), 1)

if __name__ == "__main__":
    unittest.main()
