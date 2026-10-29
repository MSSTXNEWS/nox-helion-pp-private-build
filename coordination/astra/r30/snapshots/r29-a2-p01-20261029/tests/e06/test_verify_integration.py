import copy
import json
import unittest
from pathlib import Path
from coordination.e06.verify_integration import audit, safe_path, GATES

DATA = json.loads((Path(__file__).resolve().parents[2] / "coordination/e06/intake.json").read_text(encoding="utf-8"))

class NoLossTest(unittest.TestCase):
    def test_01_current_commit_tree_pinned(self):
        self.assertEqual(audit(DATA)["gates"][GATES[0]], "PASS")
    def test_02_archive_bytes_not_assumed(self):
        self.assertEqual(audit(DATA)["gates"][GATES[1]], "HOLD")
    def test_03_pr_heads_and_bases_recorded(self):
        self.assertEqual(audit(DATA)["gates"][GATES[2]], "PASS")
    def test_04_owner_unique_by_path(self):
        self.assertEqual(audit(DATA)["gates"][GATES[3]], "PASS")
    def test_05_actual_overlaps_identified(self):
        result = audit(DATA)
        self.assertEqual(result["gates"][GATES[4]], "PASS")
        self.assertEqual(result["path_conflicts"]["Packages/P04/train_qlora.py"], [6, 7, 12])
    def test_06_foreign_receipts_never_inferred(self):
        self.assertEqual(audit(DATA)["gates"][GATES[5]], "HOLD")
    def test_07_legacy_hash_drift_quarantined(self):
        self.assertEqual(audit(DATA)["gates"][GATES[6]], "PASS")
    def test_08_second_events_bus_not_inferred(self):
        self.assertEqual(audit(DATA)["gates"][GATES[7]], "HOLD")
    def test_09_seven_lanes_unmeasured(self):
        result = audit(DATA)
        self.assertEqual(result["gates"][GATES[8]], "PASS")
        self.assertTrue(all(x["progress"] is None for x in result["lanes"]))
    def test_10_no_fake_exe_acceptance(self):
        result = audit(DATA)
        self.assertEqual(result["gates"][GATES[9]], "HOLD")
        self.assertEqual(result["release"], "BLOCKED")
    def test_reject_path_traversal(self):
        for p in ("../MainWindow.xaml.cs", "A/../B", "/root/file", "C:\\temp"):
            self.assertFalse(safe_path(p))
    def test_sha1_and_sha256_are_not_interchangeable(self):
        damaged = copy.deepcopy(DATA)
        damaged["main"]["tree_sha1"] = "a" * 64
        self.assertEqual(audit(damaged)["gates"][GATES[0]], "HOLD")
    def test_missing_owner_causes_hold(self):
        damaged = copy.deepcopy(DATA)
        del damaged["owner_map"]["Packages/P04/train_qlora.py"]
        self.assertEqual(audit(damaged)["gates"][GATES[3]], "HOLD")
    def test_forged_E07_alone_never_releases(self):
        damaged = copy.deepcopy(DATA)
        damaged["exe_sha256"] = "a" * 64
        damaged["e07_exe_sha256"] = "a" * 64
        damaged["e07_runtime"] = "PASS"
        self.assertEqual(audit(damaged)["release"], "BLOCKED")

if __name__ == "__main__":
    unittest.main()
