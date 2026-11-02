"""Guard E06 wiring for original T06 current-source and candidate receipts.

Source-only checks. No Windows install/model/network call is made.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
E06 = ROOT / ".github/workflows/nox-v16-e06-d02-onehost.yml"
TRIGGERS = [
    "coordination/e06/t06_compile_original_wpf_p02.py",
    "coordination/e06/t06_source_receipt_guard.py",
    "coordination/e06/t06_local_onehost_bridge.py",
    "tests/e06/test_t06_compile_source_head.py",
    "tests/e06/test_t06_source_receipt_guard.py",
    "tests/e06/test_i2_local_bridge_receipt_gate.py",
    "tests/e06/test_t06_gitlab_runner_authorization.py",
    "tests/e06/test_t06_e06_workflow_source_gate.py"
]
TESTS = [
    "test_t06_compile_source_head.py",
    "test_t06_source_receipt_guard.py",
    "test_i2_local_bridge_receipt_gate.py",
    "test_t06_gitlab_runner_authorization.py",
    "test_t06_e06_workflow_source_gate.py"
]

class T06WorkflowSourceGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = E06.read_text(encoding="utf-8")
        cls.paths = cls.source.split("permissions:", 1)[0]
        cls.linux = cls.source.split("  activator-portable-source:", 1)[1].split("  visual-source-stage:", 1)[0]
        cls.windows = cls.source.split("  visual-source-stage:", 1)[1].split("  diagnostic-onehost:", 1)[0]

    def test_t06_changes_trigger_existing_e06(self):
        for path in TRIGGERS:
            with self.subTest(path=path):
                self.assertIn("      - '" + path + "'", self.paths)

    def test_linux_runs_all_original_tests_fail_closed(self):
        self.assertIn("set -euo pipefail", self.linux)
        self.assertIn('python -m unittest discover -s tests/e06 -p "$test" -v', self.linux)
        for name in TESTS:
            with self.subTest(name=name):
                self.assertIn(name, self.linux)

    def test_windows_runs_all_original_tests_fail_closed(self):
        self.assertIn("shell: pwsh", self.windows)
        self.assertIn("python -m unittest discover -s tests/e06 -p $test -v", self.windows)
        self.assertIn('if ($LASTEXITCODE -ne 0) { throw "E06_T06_SOURCE_RECEIPT_GATE_HOLD:$test" }', self.windows)
        for name in TESTS:
            with self.subTest(name=name):
                self.assertIn("'" + name + "'", self.windows)

    def test_original_build_route_remains_strict(self):
        self.assertIn("needs: visual-source-stage", self.source)
        self.assertIn("runs-on: ${{ vars.NOX_WINDOWS_RUNNER", self.source)
        self.assertIn("python coordination/source-lock/verify_original_archive.py", self.source)
        self.assertNotIn("continue-on-error: true", self.source)

if __name__ == "__main__":
    unittest.main()
