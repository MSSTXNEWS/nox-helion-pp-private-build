"""Static no-delete-before-manifest-entrypoint guard; native fixture is separate."""
from pathlib import Path
import unittest


class UninstallManifestContract(unittest.TestCase):
    def test_registered_entrypoint_required_before_commit(self):
        source = (Path(__file__).parent / 'Remove-InstalledPayload.ps1').read_text()
        guard = "if (-not $registered.Contains('NOX.P01.Shell.exe'))"
        self.assertIn(guard, source)
        offset = source.index(guard)
        self.assertLess(offset, source.index('# PHASE 2'))
        self.assertIn("throw 'P01_UNINSTALL_ENTRYPOINT_UNREGISTERED'", source[offset:source.index('# PHASE 2')])
        self.assertGreater(offset, source.index('[void]$checked.Add($entry)'))


if __name__ == '__main__':
    unittest.main()
