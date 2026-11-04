"""Source-level frozen original EXPRESS admission; never a native E07 PASS."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location("nox_original_u06",ROOT/"coordination/e07/independent_setup_e07.py")
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)
class FrozenOriginalU06(unittest.TestCase):
    def test_frozen_hash_and_unchanged_d02(self):
        self.assertEqual(MOD.ORIGINAL_E06_SOURCE,"8e938107519fc2ca33b6024884c8410c2803e3ba")
        self.assertEqual(MOD.ORIGINAL_E06_SETUP_SHA,"d468e00b31fea04b6d726cc077f65048d8f132cd5f0bb51bf30c6241ce139c5d")
        self.assertEqual(MOD.ORIGINAL_E06_SETUP_BYTES,87342506)
        self.assertEqual(MOD.ORIGINAL_E06_OWNED_FILES,485)
        self.assertEqual(MOD.SOURCE_SHA,"c35c1d330b36900c61d41f65661c535dcd6fc78a")
    def test_conservative_uninstall_count(self):
        good={k:{"code":0} for k in ("install","verify","update","rollback","uninstall")}
        good["uninstall_owned_files_checked"]=485
        self.assertTrue(MOD.samevm_lifecycle_verified(good,expected_owned_files=485))
        for num in (484,486,True,"485"):
            wrong=dict(good)
            wrong["uninstall_owned_files_checked"]=num
            self.assertFalse(MOD.samevm_lifecycle_verified(wrong,expected_owned_files=485))
    def test_invalid_path_holds_before_install(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            with self.assertRaisesRegex(MOD.Hold,"E07_ORIGINAL_CANDIDATE_PATH_HOLD"):
                MOD.setup_lock_original(base/"wrong.exe",base)
    def test_actual_pe_sig_excludes_escape_backsplash(self):
        src=(ROOT/"coordination/e07/independent_setup_e07.py").read_text()
        self.assertIn('header[offset:offset+4]==bytes.fromhex("50450000")',src)
        self.assertEqual(bytes.fromhex("50450000"),b"PE"+bytes(2))
    def test_real_uia_tree_roles_are_button_presence_not_clicks(self):
        five=("CHAT","INSTALL","MODELS","LEARN","REPORTS")
        physical={"schema":"NOX-E07-UIA-V1","labels":[],
                  "treeCount":74,"treeScanned":74,
                  "targetTypes":[v+"|ControlType.Button|VISIBLE_ENABLED" for v in five]}
        evidence=MOD.classify_primary_uia_evidence(physical)
        self.assertEqual(evidence["buttons_present"],list(five))
        self.assertEqual(evidence["status"],"PASS")
        self.assertEqual(evidence["actions_invoked"],0)
        for kind in ("Text","Custom","Hyperlink"):
            bad={**physical,"targetTypes":[v+"|ControlType."+kind+"|VISIBLE_ENABLED" for v in five]}
            self.assertEqual(MOD.classify_primary_uia_evidence(bad)["status"],"HOLD")
        for state in ("OFFSCREEN","DISABLED","TOO_SMALL"):
            bad={**physical,"targetTypes":[v+"|ControlType.Button|"+state for v in five]}
            self.assertEqual(MOD.classify_primary_uia_evidence(bad)["status"],"HOLD")
        with self.assertRaisesRegex(MOD.Hold,"E07_UIA_DIAGNOSTIC_UNTRUSTED_HOLD"):
            MOD.classify_primary_uia_evidence({**physical,"treeScanned":1})
    def test_original_workflow_single_hash_frozen(self):
        workflow=(ROOT/".github/workflows/nox-express-independent-e07-candidate.yml").read_text()
        self.assertIn("run-id: 41785340462",workflow)
        self.assertIn("NOX-EXPRESS-ONEHOST-8e938107519fc2ca33b6024884c8410c2803e3ba",workflow)
        self.assertIn("--artifact-kind original",workflow)
        self.assertNotIn("run-id: 41769983592",workflow)
    def test_release_stays_hold(self):
        script=(ROOT/"coordination/e07/independent_setup_e07.py").read_text()
        self.assertIn('"release_accepted":False}',script)
        self.assertIn('result["error"]="E07_REAL_MODEL_AND_VISUAL_ACCEPTANCE_NOT_COMPLETE"',script)
if __name__=="__main__": unittest.main()
