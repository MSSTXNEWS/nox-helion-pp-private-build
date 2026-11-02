"""R44 source regression for the one original BOOST -> E06 Windows builder.
Not a native Windows build, Setup install, WebView2 registration or E07 PASS.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "coordination/e06/build_onehost_with_boost.ps1"
OWNER = ROOT / "coordination/e06/build_onehost_installer.ps1"
STAGER = ROOT / "coordination/e06/boost_v4_stage.py"


class BoostOwnerOutputLifecycleR44(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")
        cls.owner = OWNER.read_text(encoding="utf-8")
        cls.stager = STAGER.read_text(encoding="utf-8")

    def test_fix_original_guaranteed_output_precondition_conflict(self):
        self.assertIn("OUTPUT_ALREADY_EXISTS_NO_OVERWRITE", self.owner)
        self.assertNotIn("BOOST_EXISTING_OUTPUT_ROOT_REQUIRED", self.wrapper)
        self.assertIn("BOOST_OWNER_OUTPUT_EXISTS_NO_OVERWRITE", self.wrapper)
        self.assertIn("$stageRoot=$outFull + '.boost-v4-staged'", self.wrapper)
        self.assertIn("--out $stageRoot", self.wrapper)
        self.assertLess(self.wrapper.index("BOOST_OWNER_OUTPUT_EXISTS_NO_OVERWRITE"),
                        self.wrapper.index("boost_v4_stage.py"))
        self.assertLess(self.wrapper.index("boost_v4_stage.py"),
                        self.wrapper.index("build_onehost_installer.ps1"))

    def test_stage_disposable_and_real_sha_before_original_owner(self):
        self.assertIn("BOOST_PARENT_REPARSE_HOLD", self.wrapper)
        self.assertIn("BOOST_SOURCE_OUTPUT_OVERLAP_HOLD", self.wrapper)
        self.assertIn("BOOST_STAGE_OUTPUT_COLLISION_HOLD", self.wrapper)
        self.assertIn("BOOST_STAGE_PHYSICAL_SHA_HOLD", self.wrapper)
        self.assertIn("BOOST_STAGE_APPROVED_D02_OR_NUGET_COUNT_HOLD", self.wrapper)
        self.assertIn("EXPECTED_CACHE_SHA", self.stager)
        self.assertIn("BOOST_CACHE_D02_SOURCELOCK_HOLD", self.stager)
        self.assertIn("NOX-BOOST-V4-STAGE-V1", self.wrapper)
        self.assertIn("stage_only -ne $true", self.wrapper)
        self.assertIn("Get-FileHash -LiteralPath $local -Algorithm SHA256", self.wrapper)
        self.assertLess(self.wrapper.index("BOOST_STAGE_PHYSICAL_SHA_HOLD"),
                        self.wrapper.index("build_onehost_installer.ps1"))

    def test_pinned_python_and_reused_nuget_not_second_owner(self):
        self.assertIn("BOOST_WINDOWS_PYTHON_31210_REQUIRED", self.wrapper)
        self.assertIn("-cne '3.12.10'", self.wrapper)
        self.assertEqual(self.wrapper.count("& (Join-Path $repo 'coordination/e06/build_onehost_installer.ps1')"), 1)
        self.assertIn("'RestoreAdditionalProjectSources','Process'", self.wrapper)
        self.assertIn("$additional=$feed", self.wrapper)
        self.assertRegex(self.wrapper, r"(?s)try \{.*RestoreAdditionalProjectSources.*build_onehost_installer\.ps1.*\} finally \{.*RestoreAdditionalProjectSources")

    def test_diagnostic_proof_and_no_mock_release(self):
        self.assertIn("ONEHOST_DIAGNOSTIC_RECEIPT.json", self.wrapper)
        self.assertIn("NOX-HELION-V16-DIAGNOSTIC-SETUP.exe", self.wrapper)
        self.assertIn("source_commit_sha1 -cne $head", self.wrapper)
        self.assertIn("installer_sha256", self.wrapper)
        self.assertIn("BOOST_OWNER_DIAGNOSTIC_BYTES_OR_HEAD_HOLD", self.wrapper)
        self.assertIn("BOOST_V4_OWNER_SETUP_BUILT_NOT_E07_ACCEPTED", self.wrapper)
        self.assertNotIn("release_accepted=$true", self.wrapper)
        self.assertNotIn("E07_PASS", self.wrapper)


if __name__ == "__main__":
    unittest.main()
