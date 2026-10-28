"""NOX V16 independent SOURCE QA R03: direct original Host50 artifacts.

Run: python -m unittest discover -s qa/source_ready -p 'test_host50_map_reconciliation_r03.py' -v
The mismatch test is intentionally RED until owner #1 reconciles source receipts;
it does NOT assert missing executable functions merely from a legacy map.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "proposals/NOX-PACK01-50/owner-binding-map.json"
LEDGER = ROOT / "coordination/e06_host50/CURRENT_50_TASK_LEDGER.json"
CATALOG = ROOT / "proposals/NOX-PACK01-50/catalog.json"


class Host50MapReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = json.loads(MAP.read_text(encoding="utf-8"))
        cls.ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
        cls.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_all_fifty_catalog_taskids_unique(self):
        actions = self.catalog["actions"]
        self.assertEqual(len(actions), 50)
        self.assertEqual(len({a["taskId"] for a in actions}), 50)
        self.assertEqual(len({a["routeId"] for a in actions}), 50)

    def test_owner_map_is_fifty_distinct_tasks(self):
        rows = self.owner["routes"]
        self.assertEqual(len(rows), 50)
        self.assertEqual(len({r["taskId"] for r in rows}), 50)

    def test_owner_catalog_id_and_route_correspondence(self):
        owner = {r["taskId"]: r for r in self.owner["routes"]}
        for action in self.catalog["actions"]:
            with self.subTest(taskId=action["taskId"]):
                m = owner[action["taskId"]]
                self.assertEqual(m["routeId"], action["routeId"])
                self.assertEqual(m["owner"], action["owner"])

    def test_source_ledger_matches_current_owner_map(self):
        # Expected RED on historical exact owner SHA:
        # NIP01-07/chat.rag is CANDIDATE in ledger but unbound in owner map.
        owner = {r["taskId"]: r for r in self.owner["routes"]}
        self.assertEqual(len(self.ledger["rows"]), 50)
        mismatches = []
        for row in self.ledger["rows"]:
            actual = owner[row["taskId"]]
            if (row["SOURCE"] == "CANDIDATE") != bool(actual.get("sourceBinding")):
                mismatches.append((row["taskId"], row["routeId"]))
        self.assertEqual(mismatches, [], "Legacy Host50 task ledger must reconcile with real source-owner map")

    def test_bound_unbound_counters_are_consistent(self):
        actual_bound = sum(bool(row.get("sourceBinding")) for row in self.owner["routes"])
        self.assertEqual(actual_bound, self.owner["counts"]["sourceOwnerMethodBound"])
        self.assertEqual(50 - actual_bound, self.owner["counts"]["unbound"])

    def test_unproven_native_capabilities_never_report_pass(self):
        self.assertEqual(self.ledger["capabilitiesVerified"], 0)
        self.assertEqual(self.ledger["integrated"], 0)
        self.assertEqual(self.owner["counts"]["exeIntegrated"], 0)
        self.assertEqual(self.owner["counts"]["releaseAccepted"], 0)


if __name__ == "__main__":
    unittest.main()
