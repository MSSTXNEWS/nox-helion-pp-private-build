"""Azure Windows Python pin must match original private_build.ps1 exactly.

Source-only CI guard. Does not claim an Azure-hosted runner or Windows EXE.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "azure-pipelines-nox-v16.yml"
ORIGINAL = ROOT / "private_build.ps1"

class AzurePythonPinContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.yaml = PIPELINE.read_text(encoding="utf-8")
        cls.original = ORIGINAL.read_text(encoding="utf-8")

    def test_azure_python_matches_immutable_private_builder(self):
        self.assertIn('sys.version_info[:3]==(3,12,10)', self.original)
        self.assertRegex(self.yaml, r"versionSpec:\s*'3\.12\.10'")
        self.assertIn("AZURE_EXACT_PYTHON_3_12_10_OR_X64_HOLD", self.yaml)

    def test_py_launcher_routed_to_selected_python_not_unrelated_system_patch(self):
        self.assertEqual(self.yaml.count("      function py {"), 1)
        self.assertIn("$arguments[0] -cne '-3.12'", self.yaml)
        self.assertIn("& python @pythonArgs", self.yaml)
        self.assertIn("AZURE_PINNED_PY_LAUNCH_FAILED", self.yaml)
        self.assertLess(self.yaml.index("      function py {"), self.yaml.index("      & ./private_build.ps1"))

    def test_original_private_build_is_not_weakened(self):
        self.assertIn("& py -3.12 -m venv $venv", self.original)
        self.assertIn('PINNED_PYTHON_TK_AND_BUILD_IMPORTS_REQUIRED', self.original)
        self.assertIn("ORIGINAL_PYTHON_BUILD_HOLD", self.yaml)

    def test_retain_one_existing_creative_wow_staging_owner(self):
        self.assertEqual(self.yaml.count("& ./coordination/e06/build_onehost_installer.ps1"), 0)
        self.assertEqual(self.yaml.count("& $builderCopy -SourceRoot"), 1)
        self.assertIn("-CreativeSourceRoot 'integrations/creative'", self.yaml)
        self.assertIn("-WowSourceRoot 'integrations/wow200'", self.yaml)
        self.assertNotRegex(self.yaml, r"(?m)^\s*python integrations/(?:creative/stage_creative|wow200/stage_wow200)\.py")

if __name__ == "__main__":
    unittest.main()
