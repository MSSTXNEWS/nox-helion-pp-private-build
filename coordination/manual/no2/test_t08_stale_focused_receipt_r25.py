"""Manual2 R25 independent source-only proof: focused test receipts must bind exact HEAD.
Uses real temporary Git blob fixture already in this QA branch.
Run: python -m unittest test_t08_stale_focused_receipt_r25.py -v
No native Windows or product acceptance is implied.
"""
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
from test_t08_real_git_objects_r19 import RealGitReadbackTests

CANDIDATE = Path(__file__).with_name("T08_R25_CUMULATIVE_CANDIDATE.py")
spec = importlib.util.spec_from_file_location("nox_t08_r25_candidate", CANDIDATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class R25SameHeadFocusedTest(RealGitReadbackTests):
    def check_receipts(self, focused):
        p0 = {"head": self.head, "status": "PATCH_APPLIED"}
        hand = {"head_sha": self.head}
        testblob = self.blob(json.dumps(focused).encode())
        p0["receipt_blob"] = self.blob(json.dumps(p0).encode())
        hand["receipt_blob"] = self.blob(json.dumps(hand).encode())
        p0["focused_test_blob"] = testblob
        journal = {}
        for name in gate.DOCS:
            row = {"doc":name, "revision_id":"revision_"+name+"_valid",
                   "incident_id":"ERR-T08-20261029-HOST50-SOURCELOCK-AUTOFIX-CHAIN-BROKEN",
                   "readback_pass":True}
            journal[name] = {"revision_id":row["revision_id"],
                             "incident_id":row["incident_id"],
                             "readback_receipt_blob":self.blob(json.dumps(row).encode())}
        with patch.object(gate, "_root_git", return_value=(self.root, self.git_reader)):
            return gate._verified_downstream(self.source, p0, hand, journal)

    def test_stale_focused_test_pass_rejected(self):
        self.assertFalse(self.check_receipts({"status":"PASS","head_sha":"f"*40}))

    def test_conflicting_test_head_aliases_rejected(self):
        self.assertFalse(self.check_receipts({"status":"PASS","head_sha":self.head,
                                              "source_head_sha":"f"*40}))

    def test_headless_test_pass_rejected(self):
        self.assertFalse(self.check_receipts({"status":"PASS"}))

    def test_matching_focused_test_pass_is_source_only(self):
        self.assertTrue(self.check_receipts({"status":"PASS","head_sha":self.head}))


if __name__ == "__main__":
    import unittest
    unittest.main()
