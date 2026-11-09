"""E06 R11 negative regression for untrusted 50-route JSON and native envelope shape.

Runs against the existing admission.py only. No host, SQLite, LLM or installer.
"""
from __future__ import annotations
import copy
import importlib.util
import json
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("admission", HERE / "admission.py")
admission = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = admission
spec.loader.exec_module(admission)

class RegistryIngressShape(unittest.TestCase):
    def setUp(self):
        self.cat = {"version": "NOX-INTEGRATION-PACK-01", "actions": [
            {"taskId": f"NIP01-{i:02d}", "routeId": row[0], "owner": row[1],
             "risk": row[2], "settings": []}
            for i, row in enumerate(admission.APPROVED_ROUTE_POLICY, 1)]}
        self.map = {"sourceBaseCommit": admission.BASE_COMMIT, "routes": [
            {"taskId": f"NIP01-{i:02d}", "routeId": row[0], "owner": row[1],
             "sourceBinding": "owner:valid", "exeIntegrated": False,
             "releaseAccepted": False}
            for i, row in enumerate(admission.APPROVED_ROUTE_POLICY, 1)]}

    def test_50_canonical_policy_rows(self):
        out = admission.audit_registry(self.cat, self.map)
        self.assertEqual(len(out["routes"]), 50)
        self.assertEqual(out["sourceBound"], 50)
        self.assertEqual(out["nativeIntegrated"], 0)
        self.assertEqual(out["windowsAccepted"], 0)

    def test_taskid_arrays_and_objects_fail_managed(self):
        for target in ("catalog", "map"):
            for invalid in ([], {}, ["NIP01-01"], {"nested": "NIP01-01"}):
                with self.subTest(target=target, invalid=invalid):
                    c = copy.deepcopy(self.cat); m = copy.deepcopy(self.map)
                    (c["actions"] if target == "catalog" else m["routes"])[0]["taskId"] = invalid
                    with self.assertRaisesRegex(admission.Hold, "BAD_OR_DUPLICATE_TASKID"):
                        admission.audit_registry(c, m)

    def test_option_source_arrays_and_objects_fail_managed(self):
        for source in ([], {}, ["host.models.installed"], {"a": 1}):
            with self.subTest(source=source):
                c = copy.deepcopy(self.cat)
                c["actions"][0]["settings"] = [
                    {"key": "model", "kind": "select", "source": source}]
                with self.assertRaisesRegex(admission.Hold, "UNTRUSTED_NATIVE_OPTION_SOURCE"):
                    admission.audit_registry(c, self.map)

    def test_nonobject_roots_fail_managed(self):
        for invalid in (None, [], 5, "data"):
            for target in ("catalog", "map"):
                with self.subTest(invalid=invalid, target=target):
                    c = self.cat if target != "catalog" else invalid
                    m = self.map if target != "map" else invalid
                    with self.assertRaisesRegex(admission.Hold, "REGISTRY_JSON_OBJECT_REQUIRED"):
                        admission.audit_registry(c, m)

    def test_native_session_unhashable_scope_rejected(self):
        host = admission.Host50Admission(self.cat, self.map,
            signing_key=b"X" * 32, allowed_origins={"https://nox.invalid"},
            active_tree=admission.BASE_TREE, capabilities={})
        with self.assertRaisesRegex(admission.Denied, "NATIVE_SESSION_ISSUE_DENIED"):
            host.issue_session(tenant="t", principal="p", chat="c",
                origin="https://nox.invalid", scopes=({},), sensitive=())

    def test_native_capability_receipt_wrong_type_is_hold(self):
        row = self.map["routes"][0]
        from dataclasses import replace
        cap = admission.Capability("helion.chat", 2, "owner:valid", [],
                                  admission.BASE_TREE, True, True)
        host = admission.Host50Admission(self.cat, self.map,
            signing_key=b"X" * 32, allowed_origins={"https://nox.invalid"},
            active_tree=admission.BASE_TREE, capabilities={"helion.chat": cap})
        with self.assertRaisesRegex(admission.Hold, "NATIVE_OWNER_CAPABILITY_UNVERIFIED"):
            host._cap(host.by_route["helion.chat"])

if __name__ == "__main__":
    unittest.main()
