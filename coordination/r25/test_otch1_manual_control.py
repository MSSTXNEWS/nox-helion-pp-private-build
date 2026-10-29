"""NOX V16 R25 evidence monitor: no synthetic acceptance or fake 10/10."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("nox_otch1_r25", Path(__file__).with_name("otch1_manual_control.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    x = {"schema": "NOX_V16_R25_MANUAL_FIRST_OTCH1_V1", "head": "a"*40,
         "product_percent": None, "journal": {}, "error_register": {}, "manuals": []}
    for role in ("1","3","2"):
        x["manuals"].append({
            "role": role, "role_name": "test", "run_status": "INCOMPLETE",
            "approaches": [], "approaches_logged": False, "frozen_denominator": None,
            "tasks": [], "gates": {s:{"status":"NOT_RUN","proof":""} for s in "ABCDE"}
        })
    return x


class ManualFirstMonitorTests(unittest.TestCase):
    def test_valid_unverified_input_does_not_fake_completion(self):
        x = fixture()
        self.assertEqual(module.validate_snapshot(x, x["head"]), [])
        rendered = module.render(x, [])
        self.assertIn("Approaches: N/D", rendered)
        self.assertIn("PRODUCT: N/D", rendered)
        self.assertIn("Manual №1", rendered)
        self.assertIn("Manual №3", rendered)
        self.assertIn("Manual №2", rendered)

    def test_head_movement_fails_closed(self):
        self.assertIn("STALE_HEAD", module.validate_snapshot(fixture(), "b"*40))

    def test_manual_duplicate_fails(self):
        x=fixture()
        x["manuals"][2]["role"]="1"
        self.assertIn("MANUAL_ROLES_MISSING_OR_DUPLICATED", module.validate_snapshot(x))

    def test_pass_gate_needs_real_proof(self):
        x=fixture()
        x["manuals"][0]["gates"]["B"]={"status":"PASS","proof":"YES"}
        self.assertIn("UNPROVEN_PASS_1_B", module.validate_snapshot(x))

    def test_forged_accepted_rejected(self):
        x=fixture()
        x["manuals"][0]["tasks"]=[{"task_id":"P04","stage":"QA_ACCEPTED","qa":{
            "reviewer":"manual-1","pass":True,"head":x["head"],"receipt_blob":"b"*40}}]
        self.assertTrue(any("QA_ACCEPTED_WITHOUT_INDEPENDENT_PROOF" in s
                            for s in module.validate_snapshot(x)))

    def test_stale_qa_receipt_rejected(self):
        x=fixture()
        x["manuals"][2]["tasks"]=[{"task_id":"P04","stage":"QA_ACCEPTED","qa":{
            "reviewer":"manual-2","pass":True,"head":"b"*40,"receipt_blob":"b"*40}}]
        self.assertTrue(any("QA_ACCEPTED_WITHOUT_INDEPENDENT_PROOF" in s
                            for s in module.validate_snapshot(x)))

    def test_valid_same_head_qa_allows_stage_only_not_product_percent(self):
        x=fixture()
        x["manuals"][2]["tasks"]=[{"task_id":"P04","stage":"QA_ACCEPTED","qa":{
            "reviewer":"manual-2","pass":True,"head":x["head"],"receipt_blob":"b"*40}}]
        self.assertEqual(module.validate_snapshot(x), [])
        x["product_percent"]=1
        self.assertIn("PRODUCT_PERCENT_UNSUPPORTED_WITHOUT_FROZEN_LEDGER",
                      module.validate_snapshot(x))

    def test_approach_gap_rejected(self):
        x=fixture()
        x["manuals"][0]["approaches"]=[{"number":2,"status":"DONE","proof":"unit-test-readback"}]
        self.assertIn("APPROACH_ORDER_INVALID_1", module.validate_snapshot(x))


if __name__ == "__main__":
    unittest.main()
