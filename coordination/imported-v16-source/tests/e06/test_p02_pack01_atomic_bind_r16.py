"""NOX V16 P02 / PACK01 source regression: no partial native port binding.

Uses existing OwnerTwoPorts and a minimal existing PACK01 dispatcher fixture;
it does NOT open a second DB/host, and not a Windows E2E claim.
Run: python -m unittest discover -s tests/e06 -p test_p02_pack01_atomic_bind_r16.py -v
"""
from dataclasses import dataclass
from pathlib import Path
import sys
import unittest

WORKER = Path(__file__).resolve().parents[2] / "Packages" / "P02" / "worker-python"
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))
from p02_owner_route_ports import OwnerTwoPorts, RouteHold, register_with_existing_pack01

ROUTES = ("chat.rag", "chat.voice", "calls.history")


@dataclass(frozen=True)
class ExistingBoundPort:
    call: object
    available: object
    evidence_id: str
    owner: int


class ExistingDispatcher:
    def __init__(self, *, bad_owner=None, prebound=None, fail_route=None, fail_after=False):
        self.routes = {r: {"owner": 2} for r in ROUTES}
        if bad_owner:
            self.routes[bad_owner] = {"owner": 3}
        self.ports = dict(prebound or {})
        self.fail_route = fail_route
        self.fail_after = fail_after

    def bind(self, route, port):
        if route in self.ports:
            raise ValueError("Original native handler must not be overwritten")
        if self.fail_route == route and not self.fail_after:
            raise RuntimeError("EXISTING_NATIVE_BIND_FAILED")
        self.ports[route] = port
        if self.fail_route == route and self.fail_after:
            raise RuntimeError("EXISTING_NATIVE_BIND_FAILED_AFTER_INSERT")


class AtomicNativeOwnerBindings(unittest.TestCase):
    def setUp(self):
        # Registration only: original P02Store/voice backend is NEVER replaced.
        self.owner = object.__new__(OwnerTwoPorts)
        self.host_scope_from_session = lambda session: session

    def bind(self, dispatcher, port_type=ExistingBoundPort):
        return register_with_existing_pack01(
            dispatcher, port_type, self.host_scope_from_session,
            self.owner, receipt="P02-EXACT-OWNER-RECEIPT-R16")

    def test_late_wrong_owner_does_not_publish_first_two_ports(self):
        dispatcher = ExistingDispatcher(bad_owner="calls.history")
        with self.assertRaisesRegex(RouteHold, "CANONICAL_PACK01_OWNER_ROUTE_REQUIRED"):
            self.bind(dispatcher)
        self.assertEqual(dispatcher.ports, {})

    def test_preexisting_late_owner_port_is_preserved_without_partial_bind(self):
        preserved = object()
        dispatcher = ExistingDispatcher(prebound={"calls.history": preserved})
        with self.assertRaisesRegex(RouteHold, "EXISTING_ROUTE_ALREADY_BOUND_NO_OVERRIDE"):
            self.bind(dispatcher)
        self.assertEqual(dispatcher.ports, {"calls.history": preserved})

    def test_missing_late_route_does_not_partially_bind(self):
        dispatcher = ExistingDispatcher()
        del dispatcher.routes["calls.history"]
        with self.assertRaisesRegex(RouteHold, "CANONICAL_PACK01_OWNER_ROUTE_REQUIRED"):
            self.bind(dispatcher)
        self.assertEqual(dispatcher.ports, {})

    def test_factory_failure_on_third_port_publishes_nothing(self):
        dispatcher = ExistingDispatcher()
        calls = []
        def factory(*args):
            calls.append(args)
            if len(calls) == 3:
                raise ValueError("PORT_FACTORY_FAIL")
            return ExistingBoundPort(*args)
        with self.assertRaisesRegex(ValueError, "PORT_FACTORY_FAIL"):
            self.bind(dispatcher, factory)
        self.assertEqual(dispatcher.ports, {})

    def test_bind_failure_before_last_insert_rolls_back_only_new_ports(self):
        dispatcher = ExistingDispatcher(fail_route="calls.history")
        with self.assertRaisesRegex(RuntimeError, "EXISTING_NATIVE_BIND_FAILED"):
            self.bind(dispatcher)
        self.assertEqual(dispatcher.ports, {})

    def test_bind_failure_after_last_insert_rolls_back_all_new_ports(self):
        dispatcher = ExistingDispatcher(fail_route="calls.history", fail_after=True)
        with self.assertRaisesRegex(RuntimeError, "EXISTING_NATIVE_BIND_FAILED_AFTER_INSERT"):
            self.bind(dispatcher)
        self.assertEqual(dispatcher.ports, {})

    def test_success_registers_only_three_original_ports(self):
        dispatcher = ExistingDispatcher()
        result = self.bind(dispatcher)
        self.assertEqual(result, frozenset(ROUTES))
        self.assertEqual(set(dispatcher.ports), set(ROUTES))
        self.assertTrue(all(isinstance(port, ExistingBoundPort)
                            and port.owner == 2
                            and port.evidence_id == "P02-EXACT-OWNER-RECEIPT-R16"
                            and callable(port.call) and callable(port.available)
                            for port in dispatcher.ports.values()))


if __name__ == "__main__":
    unittest.main()
