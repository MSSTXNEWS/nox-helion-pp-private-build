"""Ten independent E06 safety regressions for serial NO-LOSS intake."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from coordination.e06.verify_integration import GATES, audit, read_archive, safe_path

DATA = json.loads((Path(__file__).resolve().parents[2] / "coordination/e06/intake.json").read_text(encoding="utf-8"))

def altered():
    return copy.deepcopy(DATA)

class HardenedNoLoss(unittest.TestCase):
    def test_01_windows_reserved_paths_and_ads_denied(self):
        for path in ("C:evil", "A/CON.txt", "A/NUL", "A/COM9.log", "A/b. ", "A/evil:secret", "A/line\nfeed"):
            with self.subTest(path=path):
                self.assertFalse(safe_path(path))
        self.assertTrue(safe_path("Packages/P04/train_qlora.py"))

    def test_02_symlink_archive_root_is_hold(self):
        with tempfile.TemporaryDirectory() as t:
            target = Path(t)/"actual"
            target.mkdir()
            alias = Path(t)/"alias"
            try:
                alias.symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Windows symlink privilege unavailable")
            self.assertFalse(read_archive(DATA["archive"]["parts"], alias, DATA["archive"]["expected_sha256"]))

    def test_03_duplicate_candidate_pr_is_hold(self):
        d=altered()
        d["prs"].append(copy.deepcopy(d["prs"][0]))
        self.assertEqual(audit(d)["gates"][GATES[2]], "HOLD")

    def test_04_duplicate_candidate_path_is_hold(self):
        d=altered()
        d["prs"][0]["paths"].append(d["prs"][0]["paths"][0])
        self.assertEqual(audit(d)["gates"][GATES[2]], "HOLD")

    def test_05_windows_case_collision_is_hold(self):
        d=altered()
        row=d["prs"][0]["paths"][0]
        d["prs"][0]["paths"].append(row.upper())
        d["owner_map"][row.upper()]=d["owner_map"][row]
        self.assertEqual(audit(d)["gates"][GATES[3]], "HOLD")

    def test_06_duplicate_conflict_receipt_is_hold(self):
        d=altered()
        d["conflicts"].append(copy.deepcopy(d["conflicts"][0]))
        self.assertEqual(audit(d)["gates"][GATES[4]], "HOLD")

    def test_07_quarantine_and_donor_deduplication(self):
        d=altered()
        d["donors"][1]["drive_id"]=d["donors"][0]["drive_id"]
        self.assertEqual(audit(d)["gates"][GATES[6]], "HOLD")

    def test_08_no_unverified_events_bridge(self):
        d=altered()
        d.update(sourcelock="VERIFIED",host_merge=True,events_bridge_test="PASS")
        self.assertEqual(audit(d)["gates"][GATES[7]], "HOLD")

    def test_09_unproven_numeric_progress_denied(self):
        d=altered()
        d["lanes"][0]["progress"]=100
        d["weighted_progress"]=20
        self.assertEqual(audit(d)["gates"][GATES[8]], "HOLD")
        self.assertIsNone(audit(d)["weighted_product_progress"])

    def test_10_fake_same_exe_and_acceptance_denied(self):
        d=altered()
        d["exe_sha256"]=d["e07_exe_sha256"]="a"*64
        d["build_id"]=d["e07_build_id"]="some-build"
        d["e07_runtime"]="PASS"
        d["e07_independent_owner"]=7
        d["e07_acceptance"]="ACCEPTED"
        self.assertEqual(audit(d)["release"], "BLOCKED")

if __name__ == "__main__":
    unittest.main()
