"""M2 focused fail-closed source regression; no build or native tests."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
p=Path(__file__).with_name("NOX_V16_T08_GATE_PROPOSED.py")
spec=importlib.util.spec_from_file_location("nox_m2_t08",p)
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

def fixture():
    h,t,m="a"*40,"b"*40,"c"*64
    incident="ERR-T08-20261029-GIT-EVIDENCE-FORGED-DONE"
    return {"incident_id":incident,"claimed_status":"DONE",
      "source":{"head":h,"tree":t,"manifest_sha256":m},
      "t06":{"accepted":True,"head":h,"tree":t,"manifest_sha256":m,
        "owner_receipt_blob":"d"*40,"p01_p05_accepted":True,
        "host50_native_contracts_verified":True},
      "p0p1":{"head":h,"status":"NO_CODE_BLOCKERS","receipt_blob":"e"*40},
      "journal":{k:{"incident_id":incident,"revision_id":"AHj4eMT_valid_revision",
        "readback_pass":True} for k in ("Master","E06","Lessons")},
      "handoff":{"head":h,"t09_t10_delivered":True,
        "comment_readback_pass":True,"receipt_blob":"f"*40}}

class TestM2SourceGate(unittest.TestCase):
    def test_forged_git_objects_never_complete(self):
        x=gate.decide(fixture())
        self.assertEqual(x["progress"],"0/3")
        self.assertTrue(x["premature_done_rejected"])
    def test_forged_secondary_receipts_never_complete(self):
        with patch.object(gate,"_verified_git_proof",return_value=True):
            self.assertEqual(gate.decide(fixture())["progress"],"1/3")
    def test_synthetic_sha_not_a_real_receipt(self):
        self.assertFalse(gate._bound_receipt(Path.cwd(),"f"*40,"a"*40))
    def test_fixed_three_criteria(self):
        self.assertEqual(len(gate.STEPS),3)
    def test_t10_is_not_prerequisite_to_t06(self):
        self.assertNotIn("t10_acceptance",gate.STEPS)

if __name__=="__main__":
    unittest.main()
