"""Source-only T08 false-DONE regressions. No builds/Windows/native activity."""
import copy
import unittest
from t08_autofix_closeout_gate import decide


def good():
    h, t, m = "a" * 40, "b" * 40, "c" * 64
    incident = "ERR-T08-HOST50-SOURCELOCK"
    return {"incident_id": incident, "claimed_status": "DONE",
            "source": {"head": h, "tree": t, "manifest_sha256": m},
            "t06": {"accepted": True, "head": h, "tree": t,
                    "manifest_sha256": m, "owner_receipt_blob": "d" * 40,
                    "p01_p05_accepted": True, "host50_native_contracts_verified": True},
            "p0p1": {"head": h, "status": "NO_CODE_BLOCKERS",
                     "receipt_blob": "e" * 40},
            "journal": {x: {"incident_id": incident, "revision_id": "AHj4eMT_revision_valid",
                                  "readback_pass": True}
                        for x in ("Master", "E06", "Lessons")},
            "handoff": {"head": h, "t09_t10_delivered": True,
                        "comment_readback_pass": True, "receipt_blob": "1" * 40}}


class TestT08Gate(unittest.TestCase):
    def test_true_done_requires_all_three(self):
        self.assertEqual(decide(good())["status"], "DONE")
        self.assertEqual(decide(good())["percentage"], 100.0)

    def test_false_done_blocked_on_t06(self):
        d = good(); d["t06"]["accepted"] = False
        o = decide(d)
        self.assertEqual(o["progress"], "0/3")
        self.assertTrue(o["premature_done_rejected"])

    def test_host50_not_proved(self):
        d = good(); d["t06"]["host50_native_contracts_verified"] = False
        self.assertEqual(decide(d)["status"], "HOLD_EVIDENCE")

    def test_source_sha_drift_rejects_old_disposition(self):
        d = good(); d["p0p1"]["head"] = "2" * 40
        self.assertEqual(decide(d)["progress"], "1/3")

    def test_missing_shared_journal_readback_blocks_closeout(self):
        d = good(); del d["journal"]["Lessons"]
        self.assertEqual(decide(d)["progress"], "2/3")

    def test_docs_revision_must_be_read_back(self):
        d = good(); d["journal"]["Lessons"]["revision_id"] = ""
        self.assertEqual(decide(d)["progress"], "2/3")
        d = good(); d["journal"]["Master"]["readback_pass"] = False
        self.assertEqual(decide(d)["progress"], "2/3")

    def test_handoff_requires_confirmed_delivery_not_qa_ack(self):
        d = good(); d["handoff"]["comment_readback_pass"] = False
        self.assertEqual(decide(d)["progress"], "2/3")
        d = good(); d["handoff"]["t09_t10_delivered"] = False
        self.assertEqual(decide(d)["progress"], "2/3")

    def test_patch_needs_focused_test_receipt(self):
        d = good(); d["p0p1"]["status"] = "PATCH_APPLIED"
        self.assertEqual(decide(d)["progress"], "1/3")
        d["p0p1"]["focused_test_blob"] = "f" * 40
        self.assertEqual(decide(d)["progress"], "3/3")

    def test_forged_native_attestation_is_not_enough(self):
        d = good(); d["t06"]["owner_receipt_blob"] = "not-a-sha"
        self.assertEqual(decide(d)["status"], "HOLD_EVIDENCE")

    def test_incident_id_required(self):
        d = good(); d.pop("incident_id")
        with self.assertRaisesRegex(ValueError, "UNIQUE_ERROR_INCIDENT_REQUIRED"):
            decide(d)


if __name__ == "__main__":
    unittest.main()
