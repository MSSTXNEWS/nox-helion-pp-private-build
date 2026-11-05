"""Regression: original native STOP revokes consent leases even if STOP fails."""
import ast
from pathlib import Path
import textwrap
import threading
import unittest

OWNER = Path(__file__).resolve().parents[2] / "coordination/e06/e06_native_stdio_owner.py"


def original_native_operations():
    source = OWNER.read_text("utf-8")
    module = ast.parse(source)
    factory = next(node for node in module.body
                   if isinstance(node, ast.FunctionDef) and node.name == "create_existing_ingress")
    operations = {node.name: node for node in factory.body
                  if isinstance(node, ast.FunctionDef) and node.name in {"authorize", "stop"}}
    if set(operations) != {"authorize", "stop"}:
        raise AssertionError("Original native authorizer or STOP is missing")
    scope = "def make(adapter, lease_lock, leases, training_lease, stop_hooks, principal):\n"
    scope += "    a1_wpf_proof = object()\n"
    for name in ("authorize", "stop"):
        scope += textwrap.indent(ast.get_source_segment(source, operations[name]), "    ") + "\n"
    scope += "    return authorize, stop, lambda: a1_wpf_proof\n"
    result = {}
    exec(compile(scope, str(OWNER), "exec"), result)
    return result["make"]


class OwnerSession:
    tenant = "local"
    principal = "owner"
    chat_id = "default"

    def validate(self):
        return None


class NativeAdapter:
    def __init__(self, fail=False, epoch=3):
        self.fail = fail
        self._stop_epoch = epoch

    def stop(self, session, args):
        if self.fail:
            raise RuntimeError("INJECTED_NATIVE_STOP_FAILURE")
        self._stop_epoch += 1
        return {"status": "STOP_REQUESTED"}


class OriginalNativeStopLeaseRevocation(unittest.TestCase):
    def setUp(self):
        self.adapter = NativeAdapter()
        self.leases = {("default", "training.start"): 3,
                       ("other", "selfbuilder.worker.start"): 3}
        self.training_lease = [("default", "training.start", 3)]
        self.hooks = []
        self.authorize, self.stop, self.proof = original_native_operations()(
            self.adapter, threading.Lock(), self.leases, self.training_lease,
            [lambda: self.hooks.append("stop")], "owner")
        self.session = OwnerSession()

    def assert_revoked(self):
        self.assertEqual(self.leases, {})
        self.assertIsNone(self.training_lease[0])
        self.assertIsNone(self.proof())
        self.assertEqual(self.hooks, ["stop"])
        self.assertFalse(self.authorize(self.session, "training.start", {}))

    def test_successful_stop_revokes_all_native_leases(self):
        self.assertTrue(self.authorize(self.session, "training.start", {}))
        self.assertEqual(self.stop(self.session, {}), {"status": "STOP_REQUESTED"})
        self.assert_revoked()

    def test_failing_stop_revokes_leases_without_epoch_advance(self):
        self.adapter.fail = True
        self.assertTrue(self.authorize(self.session, "training.start", {}))
        with self.assertRaisesRegex(RuntimeError, "INJECTED_NATIVE_STOP_FAILURE"):
            self.stop(self.session, {})
        self.assertEqual(self.adapter._stop_epoch, 3)
        self.assert_revoked()

    def test_missing_lease_never_authorizes_unknown_epoch(self):
        self.adapter._stop_epoch = None
        self.leases.clear()
        self.assertFalse(self.authorize(self.session, "training.start", {}))
        self.leases[("default", "training.start")] = None
        self.assertFalse(self.authorize(self.session, "training.start", {}))

    def test_other_principal_denied_even_with_matching_lease(self):
        self.session.principal = "other"
        self.assertFalse(self.authorize(self.session, "training.start", {}))


if __name__ == "__main__":
    unittest.main()
