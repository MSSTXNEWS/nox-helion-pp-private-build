"""Manual #2 focused safety regression; these are source-only tests, NOT Windows E07."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

TARGET = Path(__file__).with_name("T08_GUARD_PROPOSED_R18.py")
spec = importlib.util.spec_from_file_location("nox_t08_proposed", TARGET)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fake():
    a, b, c = "a"*40, "b"*40, "c"*64
    key = "ERR-T08-20261029-HOST50-SOURCELOCK-AUTOFIX-CHAIN-BROKEN"
    return {"incident_id":key,"claimed_status":"DONE",
            "source":{"head":a,"tree":b,"manifest_sha256":c},
            "t06":{"accepted":True,"head":a,"tree":b,"manifest_sha256":c,
                   "owner_receipt_blob":"d"*40,"p01_p05_accepted":True,
                   "host50_native_contracts_verified":True},
            "p0p1":{"head":a,"status":"NO_CODE_BLOCKERS","receipt_blob":"e"*40},
            "journal":{z:{"incident_id":key,"revision_id":"fake_rev_123456789",
                          "readback_pass":True} for z in m.DOCS},
            "handoff":{"head":a,"t09_t10_delivered":True,
                       "comment_readback_pass":True,"receipt_blob":"f"*40}}


class T08ForgedProof(unittest.TestCase):
    def test_forged_sha_fails_closed(self):
        self.assertEqual(m.decide(fake())["status"], "HOLD_EVIDENCE")

    def test_no_native_13_route_evidence_cannot_close(self):
        obj = fake()
        obj["t06"]["host50_native_contracts_verified"] = False
        self.assertEqual(m.decide(obj)["status"], "HOLD_EVIDENCE")

    def test_p0_receipts_cannot_be_laundered_by_owner_success(self):
        with patch.object(m, "_verified_git_proof", return_value=True):
            self.assertEqual(m.decide(fake())["status"], "HOLD_EVIDENCE")

    def test_missing_lessons_readback_blocks(self):
        obj = fake()
        obj["journal"].pop("Lessons")
        self.assertEqual(m.decide(obj)["status"], "HOLD_EVIDENCE")

    def test_manifest_sha_shape_not_proof(self):
        obj = fake()
        obj["source"]["manifest_sha256"] = "f"*64
        self.assertEqual(m.decide(obj)["status"], "HOLD_EVIDENCE")

    def test_unbound_source_denies(self):
        obj = fake()
        obj["t06"]["accepted"] = False
        self.assertEqual(m.decide(obj)["status"], "HOLD_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
