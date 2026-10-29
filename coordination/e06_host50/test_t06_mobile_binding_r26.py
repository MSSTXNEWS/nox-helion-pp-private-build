"""T06 R26: mobile.connect is an existing E06 owner port, not an installed gateway.

This is an offline source regression only. Do not count it as native/E07 QA.
"""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PACK = ROOT / "proposals" / "NOX-PACK01-50"
MOBILE = ROOT / "coordination" / "e06" / "adapters" / "g2_space_mobile.py"

spec = importlib.util.spec_from_file_location("nox_t06_mobile_admission", HERE / "admission.py")
admission = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = admission
spec.loader.exec_module(admission)


class ExistingMobileOwnerPort(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((PACK / "catalog.json").read_text(encoding="utf-8"))
        cls.mapping = json.loads((PACK / "owner-binding-map.json").read_text(encoding="utf-8"))

    def test_existing_handler_and_owner6_are_source_bound(self):
        mapping = self.mapping
        audit = admission.audit_registry(self.catalog, mapping)
        by_route = {x["routeId"]: x for x in audit["routes"]}
        mobile = next(x for x in mapping["routes"] if x["routeId"] == "mobile.connect")
        self.assertEqual(mobile["taskId"], "NIP01-50")
        self.assertEqual(mobile["owner"], 6)
        self.assertEqual(mobile["sourceBinding"],
                         "coordination/e06/adapters/g2_space_mobile.py:PrivateMobileContract.connect")
        tree = ast.parse(MOBILE.read_text(encoding="utf-8"))
        self.assertTrue(any(isinstance(node, ast.ClassDef) and
                            node.name == "PrivateMobileContract" and
                            any(isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and
                                child.name == "connect" for child in node.body)
                            for node in tree.body))
        source = MOBILE.read_text(encoding="utf-8")
        self.assertIn("self.mobile.connect, self.mobile.available,", source)
        self.assertIn('self._receipt("E06"), 6', source)
        self.assertEqual(by_route["mobile.connect"]["sourceState"], "SOURCE")
        self.assertEqual(audit["sourceBound"], mapping["counts"]["sourceOwnerMethodBound"])
        self.assertEqual(audit["unbound"], mapping["counts"]["unbound"])
        self.assertEqual(audit["sourceBound"] + audit["unbound"], 50)

    def test_no_false_native_or_release_acceptance(self):
        row = next(x for x in self.mapping["routes"] if x["routeId"] == "mobile.connect")
        self.assertEqual(row["componentCI"], "NOT_RUN")
        for key in ("exeIntegrated", "hardwareAccepted", "releaseAccepted"):
            self.assertIs(row[key], False)
        self.assertEqual(row["blocker"],
                         "NATIVE_PRIVATE_GATEWAY_HOST_ACK_AND_SAME_SHA_QA_PENDING")
        audit = admission.audit_registry(self.catalog, self.mapping)
        self.assertEqual(audit["nativeIntegrated"], 0)
        self.assertEqual(audit["windowsAccepted"], 0)


if __name__ == "__main__":
    unittest.main()
