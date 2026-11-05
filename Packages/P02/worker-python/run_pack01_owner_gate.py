"""NOX P02 owner-only integration gate for existing PACK01 route adapter.

The integrator's PACK01 files are checked out at an immutable SHA. They are
never modified or copied into production. This runner disables a deliberately
obsolete 'expected failure' label for the SQLite ordering defect that owner #2
has fixed, and requires the real upstream test to PASS on the new owner source.
No new host/DB/webserver is installed. Only GitHub CI test fixtures are used.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import unittest

OLD_EXPECTED_FAILURE = "test_known_owner_p02_same_second_order_is_still_blocked"


def main() -> int:
    source = Path(os.environ["NOX_PACK01_CHECKOUT"]).resolve()
    owner = Path(os.environ["NOX_P02_OWNER_PATH"]).resolve()
    if not (source / "native_bridge.py").is_file() or not (source / "test_native_bridge.py").is_file():
        raise RuntimeError("Pinned PACK01 source checkout missing")
    if not (owner / "p02_runtime.py").is_file():
        raise RuntimeError("Pinned current P02 source checkout missing")
    if source == owner or source in owner.parents or owner in source.parents:
        raise RuntimeError("Source/owner checkout overlap")
    file = source / "test_native_bridge.py"
    spec = importlib.util.spec_from_file_location("nox_pack01_upstream_contract", file)
    if spec is None or spec.loader is None:
        raise RuntimeError("Invalid exact upstream module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    test_method = getattr(module.BridgeTest, OLD_EXPECTED_FAILURE)
    if not getattr(test_method, "__unittest_expecting_failure__", False):
        raise RuntimeError("Upstream expected-failure contract drift: do not silently change the test")
    test_method.__unittest_expecting_failure__ = False
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.BridgeTest)
    count = suite.countTestCases()
    if count < 12:
        raise RuntimeError(f"Upstream contract unexpectedly shrank: {count}")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.failures or result.errors or result.skipped or result.expectedFailures or result.unexpectedSuccesses:
        raise RuntimeError("PACK01/P02 integration still blocked: non-PASS test result")
    if not result.wasSuccessful():
        return 1
    print(f"NATIVE_BRIDGE_GATE=PASS tests={count} SQLite_same_second=FIXED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
