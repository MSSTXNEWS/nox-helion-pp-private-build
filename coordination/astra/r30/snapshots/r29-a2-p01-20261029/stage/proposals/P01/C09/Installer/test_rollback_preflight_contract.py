"""Source control-flow regression; Windows execution is a separate required gate."""
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent


class RollbackPreflightContract(unittest.TestCase):
    def test_rollback_checks_paths_before_any_rename(self):
        source = (HERE / "NOX-HELION-Setup.nsi").read_text()
        body = source.split("Function RestorePrevious\n", 1)[1].split("FunctionEnd", 1)[0]
        call = re.search(r"nsExec::ExecToStack[^\n]+Preflight-InstallPath\.ps1[^\n]+-PathOnly", body)
        self.assertIsNotNone(call, "Rollback must run path preflight")
        first_rename = body.index('  Rename ')
        self.assertLess(call.end(), first_rename)
        guard = body[call.end():body.index('  File ', call.end())]
        self.assertRegex(guard, r'\$\{If\} \$ExitCode != "0"')
        self.assertIn('SetErrorLevel 2', guard)
        self.assertIn('Abort ', guard)

    def test_path_only_still_checks_ownership_and_ancestors(self):
        source = (HERE / "Preflight-InstallPath.ps1").read_text()
        self.assertRegex(source, r'\[switch\]\$PathOnly')
        branch = source.index('if ($PathOnly)')
        self.assertLess(source.index('P01_INSTALL_REPARSE_ANCESTOR'), branch)
        self.assertLess(source.index('P01_INSTALL_MARKER_INVALID'), branch)
        self.assertLess(branch, source.index('$regPaths'))
        self.assertIn('return', source[branch:source.index('$regPaths')])


if __name__ == "__main__":
    unittest.main()
