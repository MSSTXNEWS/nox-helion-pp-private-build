"""E06 R16 source-only tests: reject cross-runtime ambiguous JSON property identities.

No native dispatch, Windows build, LLM, database or actual handler claimed.
"""
import json
import tempfile
import unittest
from pathlib import Path
from admission import APPROVED_ROUTE_POLICY, BASE_COMMIT, Hold, run_read_only_audit


class StrictJsonPropertyIdentity(unittest.TestCase):
    def setUp(self):
        self.cat = {
            "version": "NOX-INTEGRATION-PACK-01",
            "actions": [
                {"taskId": f"NIP01-{i:02}", "routeId": route, "owner": owner,
                 "risk": risk, "settings": []}
                for i, (route, owner, risk) in enumerate(APPROVED_ROUTE_POLICY, 1)
            ],
        }
        self.binding = {
            "sourceBaseCommit": BASE_COMMIT,
            "routes": [
                {"taskId": f"NIP01-{i:02}", "routeId": route,
                 "owner": owner, "sourceBinding": None}
                for i, (route, owner, risk) in enumerate(APPROVED_ROUTE_POLICY, 1)
            ],
        }

    def run_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "catalog.json", Path(tmp) / "binding.json"
            a.write_text(json.dumps(self.cat, ensure_ascii=False), encoding="utf-8")
            b.write_text(json.dumps(self.binding, ensure_ascii=False), encoding="utf-8")
            return run_read_only_audit(str(a), str(b))

    def test_clean_fifty_still_pass(self):
        got = self.run_audit()
        self.assertEqual(len(got["routes"]), 50)
        self.assertEqual(got["unbound"], 50)

    def test_root_casefold_collision_rejected(self):
        # Old Python parser kept both; .NET readers may interpret as same property.
        self.cat["VERSION"] = "conflicting-user-version"
        with self.assertRaisesRegex(Hold, "AUDIT_AMBIGUOUS_JSON_PROPERTY"):
            self.run_audit()

    def test_nested_taskid_casefold_collision_rejected(self):
        self.cat["actions"][0]["TASKID"] = "NIP01-50"
        with self.assertRaisesRegex(Hold, "AUDIT_AMBIGUOUS_JSON_PROPERTY"):
            self.run_audit()

    def test_binding_owner_casefold_collision_rejected(self):
        self.binding["routes"][0]["OWNER"] = 5
        with self.assertRaisesRegex(Hold, "AUDIT_AMBIGUOUS_JSON_PROPERTY"):
            self.run_audit()

    def test_unicode_nfc_collision_rejected_even_if_metadata_ignored(self):
        self.cat["metadata"] = {"Résumé": "true", "Re\u0301sume\u0301": "false"}
        with self.assertRaisesRegex(Hold, "AUDIT_AMBIGUOUS_JSON_PROPERTY"):
            self.run_audit()

    def test_distinct_unicode_keys_not_rejected(self):
        self.cat["metadata"] = {"Résumé": "true", "Unrelated": "safe"}
        self.assertEqual(self.run_audit()["unbound"], 50)

    def test_identical_duplicate_still_rejected(self):
        # Actual duplicate JSON must remain forbidden independently of NFC logic.
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "catalog.json", Path(tmp) / "binding.json"
            b.write_text(json.dumps(self.binding), encoding="utf-8")
            raw = json.dumps(self.cat)
            a.write_text(raw.replace('"version": ', '"version": "dup", "version": ', 1), encoding="utf-8")
            with self.assertRaisesRegex(Hold, "AUDIT_DUPLICATE_JSON_KEY"):
                run_read_only_audit(str(a), str(b))


if __name__ == "__main__":
    unittest.main()
