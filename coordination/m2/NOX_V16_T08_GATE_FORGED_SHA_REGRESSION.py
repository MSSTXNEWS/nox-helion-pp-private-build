"""M2 narrow regression: arbitrary SHA-shaped IDs may never close T08."""
import importlib.util
from pathlib import Path
import unittest

TARGET = Path(__file__).with_name("NOX_V16_T08_GATE_PROPOSED.py")
spec = importlib.util.spec_from_file_location("nox_m2_gate_proposed", TARGET)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

class SyntheticSHAReject(unittest.TestCase):
    def test_no_git_objects_no_100_percent(self):
        fake = {
            "incident_id": "ERR-T08-20261029-GIT-EVIDENCE-FORGED",
            "claimed_status": "DONE",
            "source": {"head": "a"*40, "tree": "b"*40, "manifest_sha256": "c"*64},
            "t06": {"accepted": True, "head": "a"*40, "tree": "b"*40,
                    "manifest_sha256": "c"*64, "owner_receipt_blob": "d"*40,
                    "p01_p05_accepted": True, "host50_native_contracts_verified": True},
            "p0p1": {"head": "a"*40, "status": "NO_CODE_BLOCKERS", "receipt_blob": "e"*40},
            "journal": {k: {"incident_id": "ERR-T08-20261029-GIT-EVIDENCE-FORGED",
                            "revision_id": "A-Really-Long-Revision-Id", "readback_pass": True}
                        for k in ("Master", "E06", "Lessons")},
            "handoff": {"head": "a"*40, "t09_t10_delivered": True,
                        "comment_readback_pass": True, "receipt_blob": "f"*40},
        }
        outcome = gate.decide(fake)
        self.assertEqual(outcome["status"], "HOLD_EVIDENCE")
        self.assertEqual(outcome["progress"], "0/3")
        self.assertTrue(outcome["premature_done_rejected"])

if __name__ == "__main__":
    unittest.main()
