"""B06 source-only regression: immutable same-Setup E07 eligibility when E06 host is offline.

Never accepts E06 as Qwen-ready or independent E07 PASS. Run:
python -m unittest discover -s tests/e07 -p test_b06_offline_producer_admission_r86.py -v
"""
from pathlib import Path
import importlib.util
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"coordination/e07"))
spec=importlib.util.spec_from_file_location("b06_offline_admission",ROOT/"coordination/e07/independent_setup_e07.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class OfflineProducerAdmission(unittest.TestCase):
    def setUp(self):
        self.count=1013
        self.lifecycle={"install":{"code":0},"verify":{"code":0},
                        "update":{"code":0},"rollback":{"code":0},
                        "uninstall":{"code":0},
                        "uninstall_owned_files_checked":self.count,
                        "unmanaged_install_file_noloss":"PRESERVED_VERIFIED",
                        "uninstall_any_exit_no_loss":{
                            "persistent_user_data":"PRESERVED",
                            "unmanaged_install_data":"PRESERVED",
                            "release_accepted":False},
                        "native_ipc":{"status":"PROVIDER_OFFLINE_HOLD",
                                      "model_inventory_route_verified":False,
                                      "real_model_inference_tested":False,
                                      "run_id_matched":True,
                                      "request_id_matched":True}}
        self.receipt={"phase":"INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PROVIDER_OFFLINE_HOLD_NOT_E07",
                      "reason":"","installer_lifecycle":self.lifecycle}

    def verify(self,candidate="d02-pinned"):
        return mod.samevm_provider_preflight_eligible(
            self.receipt,candidate=candidate,expected_owned_files=self.count)

    def test_real_lifecycle_provider_offline_only_eligible_for_pinned_e07(self):
        self.assertTrue(self.verify())
        self.assertFalse(self.verify("d02-current"))

    def test_zero_native_uninstall_is_mandatory(self):
        self.lifecycle["uninstall"]["code"]=1
        self.assertFalse(self.verify())

    def test_exact_owned_count_is_mandatory(self):
        self.lifecycle["uninstall_owned_files_checked"]=1012
        self.assertFalse(self.verify())

    def test_no_loss_both_data_classes_mandatory(self):
        self.lifecycle["uninstall_any_exit_no_loss"]["unmanaged_install_data"]="HOLD"
        self.assertFalse(self.verify())

    def test_persistent_no_loss_mandatory(self):
        self.lifecycle["uninstall_any_exit_no_loss"]["persistent_user_data"]="HOLD"
        self.assertFalse(self.verify())

    def test_actual_provider_evidence_cannot_be_faked(self):
        self.lifecycle["native_ipc"]["real_model_inference_tested"]=True
        self.assertFalse(self.verify())

    def test_native_run_and_request_id_must_match(self):
        self.lifecycle["native_ipc"]["request_id_matched"]=False
        self.assertFalse(self.verify())

    def test_provider_bad_phase_never_admitted(self):
        self.receipt["phase"]="HOLD"
        self.assertFalse(self.verify())

    def test_existing_success_phase_retained(self):
        self.receipt["phase"]="INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PASS_NOT_E07"
        self.assertTrue(self.verify())

    def test_no_lifecycle_or_untrusted_payload_refused(self):
        self.assertFalse(mod.samevm_provider_preflight_eligible(
            {},candidate="d02-pinned",expected_owned_files=self.count))


if __name__=="__main__":
    unittest.main()
