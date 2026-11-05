"""Source-only regression for E06 onehost path ancestry; never executes dotnet/NSIS."""
from pathlib import Path
import unittest

SCRIPT = (Path(__file__).resolve().parents[2] / "coordination/e06/build_onehost_installer.ps1").read_text(encoding="utf-8")

class ReparseAncestorAdmissionTests(unittest.TestCase):
    def assert_before(self, check, operation):
        self.assertEqual(SCRIPT.count(check), 1)
        self.assertIn(operation, SCRIPT)
        self.assertLess(SCRIPT.index(check), SCRIPT.index(operation))

    def test_guard_inspects_windows_reparse_attribute(self):
        self.assertIn("function Assert-E06PlainPathAncestors", SCRIPT)
        self.assertIn("[IO.File]::GetAttributes($cursor)", SCRIPT)
        self.assertIn("[IO.FileAttributes]::ReparsePoint", SCRIPT)
        self.assertIn('E06_${Scope}_REPARSE_ANCESTOR_HOLD', SCRIPT)

    def test_untrusted_source_checked_before_resolve(self):
        self.assert_before("-Candidate $SourceRoot -Scope 'SOURCE'",
                           "$source=(Resolve-Path -LiteralPath $SourceRoot).Path")

    def test_untrusted_python_checked_before_resolve(self):
        self.assert_before("-Candidate $PythonExe -Scope 'PYTHON'",
                           "$original=(Resolve-Path -LiteralPath $PythonExe).Path")

    def test_output_ancestors_checked_before_any_directory_creation(self):
        self.assert_before("-Candidate $OutputRoot -Scope 'OUTPUT'",
                           "New-Item -ItemType Directory -Path $OutputRoot -Force")

    def test_output_recheck_before_dotnet_publish(self):
        self.assert_before("-Candidate $OutputRoot -Scope 'OUTPUT_POST_CREATE'",
                           "& dotnet publish $project")

    def test_nsis_owner_source_checked_before_read(self):
        self.assert_before("-Scope 'NSIS_OWNER'",
                           "if (!(Test-Path -LiteralPath (Join-Path $installer 'NOX-HELION-Setup.nsi')")

    def test_disposable_source_lock_checked_before_deserialization(self):
        self.assert_before("-Scope 'SOURCELOCK'",
                           "$lock=Get-Content -LiteralPath $lockPath -Raw -Encoding UTF8")

    def test_optional_visual_source_ancestors_checked(self):
        for scope in ("CREATIVE", "WOW", "PERSONA"):
            self.assertIn("-Scope '" + scope + "'", SCRIPT)

    def test_original_wpf_nsis_and_d02_contract_retained(self):
        for token in ("& dotnet publish $project", "& $makensisPath /V2",
                      "ORIGINAL_NSIS_PAYLOAD_SHA_GATE_HOLD", "D02_ASSET_SHA_HOLD"):
            self.assertIn(token, SCRIPT)

if __name__ == "__main__":
    unittest.main()
