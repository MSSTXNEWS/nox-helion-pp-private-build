"""U11: real installed smoke offline model is not a GUI/NSIS first failure.

Execute isolated AST of the original bridge helper, not mocked E07/Windows.
The negative cases ensure no fallback can masquerade as a model PASS.
"""
import ast
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[2]/"coordination/e06/t06_local_onehost_bridge.py"
tree=ast.parse(SOURCE.read_text("utf-8"),filename=str(SOURCE))
node=next(x for x in tree.body if isinstance(x,ast.FunctionDef)
          and x.name=="verified_samevm_lifecycle_state")
scope={}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(SOURCE),"exec"),scope)
verify=scope["verified_samevm_lifecycle_state"]

class BridgeLifecycleR147(unittest.TestCase):
    def fixture(self,offline=True):
        return {"phase":("INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PROVIDER_OFFLINE_HOLD_NOT_E07"
                        if offline else "INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PASS_NOT_E07"),
                "release_accepted":False,"e07_independent_acceptance":"NOT_RUN",
                "original_home_and_core01_sha_verified":True,
                "manifest_files_checked":485,
                "installer_lifecycle":{
                    **{name:{"code":0} for name in (
                        "preflight_final","install","verify","update",
                        "backup_payload_verify","rollback",
                        "rollback_payload_restored","rollback_payload_superseded",
                        "uninstall")},
                    "uninstall_owned_files_checked":485,
                    "uninstall_registry_views_checked":2,
                    "original_wpf_gui":{"new_nav_ok":True,"new_python_ipc_handshake":True},
                    "native_ipc":{"route":"models.installed","status":("PROVIDER_OFFLINE_HOLD" if offline else "PASS"),
                                  "model_inventory_route_verified":not offline,
                                  "real_model_inference_tested":False,
                                  "run_id_matched":True,"request_id_matched":True}}}
    def test_real_offline_lifecycle_is_diagnostic_hold_not_model_pass(self):
        self.assertEqual(verify(self.fixture(),{"return_code":0}),
                         "PROVIDER_OFFLINE_HOLD_NOT_E07")
    def test_online_inventory_is_still_only_diagnostic_not_e07(self):
        self.assertEqual(verify(self.fixture(False),{"return_code":0}),
                         "INSTALLED_NATIVE_INVENTORY_DIAGNOSTIC_NOT_E07")
    def test_mismatched_offline_receipt_never_grants_candidate(self):
        for path,value in (("phase","INVALID"),("release_accepted",True),
                           ("e07_independent_acceptance","PASS"),
                           ("original_home_and_core01_sha_verified",False)):
            with self.subTest(path=path):
                data=self.fixture();data[path]=value
                with self.assertRaisesRegex(RuntimeError,"T06_M1_REAL_WINDOWS_GUI_IPC_LIFECYCLE_GATE_HOLD"):
                    verify(data,{"return_code":0})
        for field,value in (("status","PASS"),("model_inventory_route_verified",True),
                            ("real_model_inference_tested",True),("route","chat.stream"),
                            ("request_id_matched",False),("run_id_matched",False)):
            with self.subTest(field=field):
                data=self.fixture();data["installer_lifecycle"]["native_ipc"][field]=value
                with self.assertRaisesRegex(RuntimeError,"T06_M1_REAL_WINDOWS_GUI_IPC_LIFECYCLE_GATE_HOLD"):
                    verify(data,{"return_code":0})
    def test_strict_install_process_and_gui(self):
        for third in ({"return_code":1},{"return_code":False},{"return_code":"0"},{},None):
            with self.subTest(third=third):
                with self.assertRaisesRegex(RuntimeError,"T06_M1_REAL_WINDOWS_GUI_IPC_LIFECYCLE_GATE_HOLD"):
                    verify(self.fixture(),third)
        for key in ("new_nav_ok","new_python_ipc_handshake"):
            data=self.fixture();data["installer_lifecycle"]["original_wpf_gui"][key]=False
            with self.assertRaisesRegex(RuntimeError,"T06_M1_REAL_WINDOWS_GUI_IPC_LIFECYCLE_GATE_HOLD"):
                verify(data,{"return_code":0})
    def test_no_physical_stage_can_be_skipped_or_faked(self):
        stages=("preflight_final","install","verify","update",
                "backup_payload_verify","rollback","rollback_payload_restored",
                "rollback_payload_superseded","uninstall")
        for stage in stages:
            for invalid in (None,{},{"code":1},{"code":False},
                            {"code":"0"},{"code":0.0}):
                with self.subTest(stage=stage,invalid=invalid):
                    data=self.fixture()
                    data["installer_lifecycle"][stage]=invalid
                    with self.assertRaisesRegex(RuntimeError,
                            "T06_M1_REAL_WINDOWS_GUI_IPC_LIFECYCLE_GATE_HOLD"):
                        verify(data,{"return_code":0})

    def test_owned_uninstall_receipt_must_be_physical(self):
        for key,invalid in (("uninstall_owned_files_checked",None),
                            ("uninstall_owned_files_checked",False),
                            ("uninstall_owned_files_checked",0),
                            ("uninstall_owned_files_checked","485"),
                            ("uninstall_registry_views_checked",True),
                            ("uninstall_registry_views_checked",0),
                            ("uninstall_registry_views_checked","2")):
            with self.subTest(key=key,invalid=invalid):
                data=self.fixture(False)
                data["installer_lifecycle"][key]=invalid
                with self.assertRaisesRegex(RuntimeError,
                        "T06_M1_REAL_WINDOWS_GUI_IPC_LIFECYCLE_GATE_HOLD"):
                    verify(data,{"return_code":0})

    def test_uninstall_must_cover_entire_source_verified_manifest(self):
        for invalid in (None, False, 0, 1, 484, 486, 50001, "485"):
            with self.subTest(source_count=invalid):
                data=self.fixture(False)
                data["manifest_files_checked"]=invalid
                with self.assertRaisesRegex(RuntimeError,
                        "T06_M1_REAL_WINDOWS_GUI_IPC_LIFECYCLE_GATE_HOLD"):
                    verify(data,{"return_code":0})
        for invalid in (1, 484, 486, 50001):
            with self.subTest(owned_count=invalid):
                data=self.fixture(False)
                data["installer_lifecycle"]["uninstall_owned_files_checked"]=invalid
                with self.assertRaisesRegex(RuntimeError,
                        "T06_M1_REAL_WINDOWS_GUI_IPC_LIFECYCLE_GATE_HOLD"):
                    verify(data,{"return_code":0})
        self.assertEqual(verify(self.fixture(False),{"return_code":0}),
                         "INSTALLED_NATIVE_INVENTORY_DIAGNOSTIC_NOT_E07")

    def test_no_silent_undocumented_phase(self):
        data=self.fixture();data["phase"]="INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PASS_NOT_E07"
        with self.assertRaisesRegex(RuntimeError,"T06_M1_REAL_WINDOWS_GUI_IPC_LIFECYCLE_GATE_HOLD"):
            verify(data,{"return_code":0})
        data=self.fixture(False);data["installer_lifecycle"]["native_ipc"]["model_inventory_route_verified"]=False
        with self.assertRaisesRegex(RuntimeError,"T06_M1_REAL_WINDOWS_GUI_IPC_LIFECYCLE_GATE_HOLD"):
            verify(data,{"return_code":0})

if __name__=="__main__":unittest.main()
