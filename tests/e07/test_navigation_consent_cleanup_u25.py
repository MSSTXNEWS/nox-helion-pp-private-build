"""C34 same-Setup functional regression: dismiss only exact native catalog dialog.

Source-only guards, not authorization, Windows evidence or E07 release PASS.
"""
from pathlib import Path
import importlib.util
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"coordination/e07/probe_final_same_setup.py"
sys.path.insert(0,str(SOURCE.parent))
spec=importlib.util.spec_from_file_location("nox_e07_navigation_consent_u25",SOURCE)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CatalogConsentSafety(unittest.TestCase):
    def test_only_original_owner_and_catalog_while_negative_no(self):
        text=SOURCE.read_text(encoding="utf-8")
        self.assertIn("NOX HELION · Native consent",text)
        self.assertIn("ProcessId -eq $pidNumber",text)
        self.assertIn("Разрешить локальный маршрут NOX: models.catalog?",text)
        self.assertIn("('No','Нет')",text.replace("@('No','Нет')","('No','Нет')"))
        self.assertIn("$p.Invoke()",text)
        self.assertIn("permissionGranted=$false",text)
        self.assertIn("if($routeCount -ne 1 -or $no.Count -ne 1)",text)
        self.assertNotIn("GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]",text)

    def test_absent_or_negative_only_valid_shapes(self):
        for status in ("ABSENT","NEGATIVE_DISMISSED"):
            valid={"schema":"NOX-E07-NAV-DIALOG-CLOSE-v1","status":status,
                   "ownerProcessIdMatched":True,"permissionGranted":False,
                   "negativeActionInvoked":status=="NEGATIVE_DISMISSED"}
            with self.subTest(status=status):
                with patch.object(module,"_run_ps",return_value=valid) as stub:
                    self.assertEqual(module.dismiss_readonly_models_catalog_consent(123)["status"],status)
                    self.assertEqual(stub.call_args.kwargs["phase"],"UNKNOWN")
        for invalid in (
            {"schema":"NOX-E07-NAV-DIALOG-CLOSE-v1","status":"APPROVED",
             "ownerProcessIdMatched":True,"permissionGranted":False,"negativeActionInvoked":False},
            {"schema":"NOX-E07-NAV-DIALOG-CLOSE-v1","status":"NEGATIVE_DISMISSED",
             "ownerProcessIdMatched":True,"permissionGranted":True,"negativeActionInvoked":True},
            {"schema":"NOX-E07-NAV-DIALOG-CLOSE-v1","status":"NEGATIVE_DISMISSED",
             "ownerProcessIdMatched":False,"permissionGranted":False,"negativeActionInvoked":True},
            {"schema":"NOX-E07-NAV-DIALOG-CLOSE-v1","status":"ABSENT",
             "ownerProcessIdMatched":True,"permissionGranted":False,"negativeActionInvoked":True},
        ):
            with patch.object(module,"_run_ps",return_value=invalid):
                with self.assertRaisesRegex(module.e07.Hold,
                                            "E07_FINAL_NAV_DIALOG_NEGATIVE_RECEIPT_HOLD"):
                    module.dismiss_readonly_models_catalog_consent(123)

    def test_disposable_qa_may_approve_only_readonly_catalog_owner_dialog(self):
        from unittest.mock import patch
        import os
        allowed={"GITHUB_ACTIONS":"true","RUNNER_OS":"Windows",
                 "RUNNER_ENVIRONMENT":"github-hosted",
                 "GITHUB_REPOSITORY":"MSSTXNEWS/nox-helion-pp-private-build"}
        for status in ("ABSENT","QA_READONLY_CATALOG_APPROVED"):
            witness={"schema":"NOX-E07-QA-CATALOG-CONSENT-v1","status":status,
                     "sameOwnerProcess":True,
                     "readOnlyCatalogConsentGranted":status=="QA_READONLY_CATALOG_APPROVED",
                     "fullModelPermissionsVerified":False}
            with self.subTest(status=status),patch.dict(os.environ,allowed),patch.object(
                  module.sys,"platform","win32"),patch.object(module,"_run_ps",return_value=witness):
                actual=module.qa_approve_readonly_catalog_consent(123)
                self.assertFalse(actual["fullModelPermissionsVerified"])
        bad={"schema":"NOX-E07-QA-CATALOG-CONSENT-v1",
             "status":"QA_READONLY_CATALOG_APPROVED",
             "sameOwnerProcess":True,"readOnlyCatalogConsentGranted":True,
             "fullModelPermissionsVerified":True}
        with patch.dict(os.environ,allowed),patch.object(module.sys,"platform","win32"),patch.object(module,"_run_ps",return_value=bad):
            with self.assertRaisesRegex(module.e07.Hold,"E07_CATALOG_QA_CONSENT_RECEIPT_HOLD"):
                module.qa_approve_readonly_catalog_consent(123)
        with patch.dict(os.environ,{"GITHUB_ACTIONS":"false"}),patch.object(module.sys,"platform","win32"):
            with self.assertRaisesRegex(module.e07.Hold,"E07_CATALOG_QA_HOST_NOT_AUTHORIZED_HOLD"):
                module.qa_approve_readonly_catalog_consent(123)

    def test_no_other_native_permission_can_be_auto_granted(self):
        text=SOURCE.read_text(encoding="utf-8")
        self.assertIn("Разрешить локальный маршрут NOX: models.catalog?",text)
        self.assertIn("'QA_READONLY_CATALOG_APPROVED'",text)
        self.assertIn("fullModelPermissionsVerified=$false",text)
        self.assertIn('\"model_pull\":\"NOT_TESTED\"',text)
        self.assertIn('\"model_download_queue\":\"NOT_TESTED\"',text)
        self.assertNotIn('"permissions_verified":"PASS"',text)

    def test_separate_from_native_function_and_release_acceptance(self):
        source=SOURCE.read_text(encoding="utf-8")
        self.assertLess(source.index("navigation_consent = dismiss_readonly_models_catalog_consent"),
                        source.index("    actions={}"))
        self.assertIn('"navigation_consent_cleanup":navigation_consent',source)
        self.assertIn('"permissions_verified":"NOT_TESTED"',source)
        self.assertNotIn('"permissions_verified":"PASS"',source)

if __name__=="__main__":
    unittest.main()
