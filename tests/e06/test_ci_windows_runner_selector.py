"""Source contract for choosing an owner-controlled Windows runner, not E07."""
from pathlib import Path
import unittest

FILE=Path(__file__).resolve().parents[2]/'.github/workflows/nox-v16-e06-d02-onehost.yml'
class ExactWindowsRunner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.yaml=FILE.read_text(encoding='utf-8')
    def test_both_windows_jobs_use_same_owned_selector(self):
        self.assertEqual(self.yaml.count("vars.NOX_WINDOWS_RUNNER == 'self-hosted'"),2)
        self.assertEqual(self.yaml.count('["self-hosted","Windows","X64","nox-win-x64"]'),2)
        self.assertEqual(self.yaml.count("|| 'windows-2022'"),2)
    def test_diagnostic_linux_gate_not_release_block_for_selfhost(self):
        self.assertIn("if: vars.NOX_WINDOWS_RUNNER != 'self-hosted'",self.yaml)
        self.assertIn("runs-on: ubuntu-24.04",self.yaml)
    def test_existing_source_and_installer_steps_preserved(self):
        self.assertIn('visual-source-stage:',self.yaml)
        self.assertIn('diagnostic-onehost:',self.yaml)
        self.assertIn('needs: visual-source-stage',self.yaml)
        self.assertIn('build_onehost_installer.ps1',self.yaml)
        self.assertIn('stage_wow200.py',self.yaml)
        self.assertNotIn('continue-on-error: true',self.yaml)
if __name__=='__main__':
    unittest.main()
