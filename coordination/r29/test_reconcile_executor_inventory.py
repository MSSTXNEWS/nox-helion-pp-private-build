"""NOX R29 inventory: owner roster + real scheduler, no synthetic acceptance."""
import copy
import unittest
from reconcile_executor_inventory import reconcile


def fixtures():
    roster = {"schema": "NOX_R29_EXECUTOR_ROSTER_V1",
              "owner_manual_roles": [
                  {"id": "1", "role": "source", "scope": "current"},
                  {"id": "3", "role": "P04", "scope": "current"},
                  {"id": "2", "role": "QA", "scope": "current"}],
              "automation_roles": [
                  {"id": "auto-A", "scope": "current"},
                  {"id": "auto-B", "scope": "historical"}]}
    export = {"schema": "NOX_R29_AUTHENTICATED_SCHEDULER_EXPORT_V1",
              "complete": True, "observed_at": "2026-10-30T01:00:00+03:00",
              "automations": [
                  {"id": "auto-A", "title": "Current", "is_enabled": True,
                   "schedule": "BYMINUTE=15",
                   "last_run": {"status": "failed",
                                "started_at": "2026-10-29T21:14:00Z",
                                "completed_at": "2026-10-29T21:24:00Z"}},
                  {"id": "auto-B", "title": "Archive", "is_enabled": False,
                   "schedule": None, "last_run": None}]}
    data = {"schema": "NOX_CONTROL_CENTER_R26_SNAPSHOT_V1",
            "manuals": [], "automations": [], "product_percent": None}
    return roster, export, data


class InventoryTests(unittest.TestCase):
    def test_counts_and_actual_run(self):
        data, runs = reconcile(*fixtures())
        self.assertEqual(data["manual_count"], 3)
        self.assertEqual(data["automation_counts"]["current_roster"], 1)
        self.assertEqual(data["automation_counts"]["historical"], 1)
        self.assertEqual(data["automation_counts"]["current_enabled_confirmed"], 1)
        self.assertEqual(runs["tasks"][0]["last_run"]["status"], "failed")
        self.assertIsNone(data["product_percent"])

    def test_new_automation_unassigned(self):
        a,b,c = fixtures()
        b["automations"].append({"id": "auto-C", "title": "New", "is_enabled": True})
        result,_ = reconcile(a,b,c)
        self.assertEqual(result["automation_counts"]["unassigned"], 1)
        self.assertEqual(result["automation_counts"]["current_roster"], 1)

    def test_disabled_current_remains_current(self):
        a,b,c = fixtures()
        b["automations"][0]["is_enabled"] = False
        result,_ = reconcile(a,b,c)
        self.assertEqual(result["automation_counts"]["current_roster"], 1)
        self.assertEqual(result["automation_counts"]["current_enabled_confirmed"], 0)

    def test_missing_record_preserves_history(self):
        a,b,c = fixtures()
        b["automations"].pop()
        result,runs = reconcile(a,b,c)
        self.assertEqual(result["automation_counts"]["missing_in_scheduler"], 1)
        self.assertEqual(runs["missing_ids"], ["auto-B"])
        self.assertTrue(any(x["id"] == "auto-B" for x in result["automations"]))

    def test_partial_export_rejected(self):
        a,b,c = fixtures()
        b["complete"] = False
        with self.assertRaisesRegex(ValueError, "INCOMPLETE"):
            reconcile(a,b,c)

    def test_duplicate_scheduler_id_rejected(self):
        a,b,c = fixtures()
        b["automations"].append(copy.deepcopy(b["automations"][0]))
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            reconcile(a,b,c)

    def test_invalid_actual_time_rejected(self):
        a,b,c = fixtures()
        b["automations"][0]["last_run"]["started_at"] = "yesterday"
        with self.assertRaisesRegex(ValueError, "STARTED_AT"):
            reconcile(a,b,c)

    def test_manual_count_dynamic(self):
        a,b,c = fixtures()
        a["owner_manual_roles"].append({"id": "4", "role": "approved", "scope": "current"})
        result,_ = reconcile(a,b,c)
        self.assertEqual(result["manual_count"], 4)

    def test_no_accepted_claim_created(self):
        result,_ = reconcile(*fixtures())
        self.assertFalse(result.get("source_ready", False))
        self.assertIsNone(result["product_percent"])


if __name__ == "__main__":
    unittest.main()
