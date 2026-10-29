"""Source ordering/mutation checks only; does not execute Windows PowerShell."""
from pathlib import Path
import re
import unittest

SOURCE = Path(__file__).with_name('Preflight-InstallPath.ps1')


def assert_directory_guards(test, source):
    preflight = source[:source.index('if ($PathOnly)')]
    targets = preflight[preflight.index('foreach ($path'):preflight.index('# Never stage')]
    for suffix in ('', '.__p01_stage', '.__p01_previous', '.__p01_rollback_saved'):
        test.assertIn('$root' + suffix, targets)
    test.assertRegex(targets, r'(?s)Get-Item[^\n]*\n\s*if \(-not \$item\.PSIsContainer\) \{ throw "P01_INSTALL_NOT_DIRECTORY:\$path" \}')
    ancestry = preflight[preflight.index('$localRoot ='):preflight.index('# Verify the existing')]
    test.assertRegex(ancestry, r'(?s)Get-Item[^\n]*\n\s*if \(-not \$node\.PSIsContainer\) \{ throw "P01_INSTALL_NOT_DIRECTORY:\$cursor" \}')
    test.assertIn('$cursor -ieq $localRoot', ancestry)
    test.assertLess(preflight.index('P01_INSTALL_NOT_DIRECTORY'), preflight.index('P01_INSTALL_MARKER_INVALID'))
    test.assertIn('P01_INSTALL_REPARSE_ANCESTOR', ancestry)


class DirectoryKindContract(unittest.TestCase):
    def test_all_target_and_ancestor_guards_precede_path_only_success(self):
        assert_directory_guards(self, SOURCE.read_text())

    def test_deleted_or_inverted_kind_guards_are_detected(self):
        source = SOURCE.read_text()
        for variable, path in [('item', 'path'), ('node', 'cursor')]:
            guard = f'if (-not ${variable}.PSIsContainer) {{ throw "P01_INSTALL_NOT_DIRECTORY:${path}" }}'
            self.assertIn(guard, source)
            for replacement in ['', guard.replace('-not ', '')]:
                with self.subTest(variable=variable, replacement=replacement):
                    with self.assertRaises(AssertionError):
                        assert_directory_guards(self, source.replace(guard, replacement))

    def test_guard_moved_after_early_return_is_detected(self):
        source = SOURCE.read_text()
        guard = 'if (-not $node.PSIsContainer) { throw "P01_INSTALL_NOT_DIRECTORY:$cursor" }'
        self.assertIn(guard, source)
        moved = source.replace(guard, '') + '\n' + guard
        with self.assertRaises(AssertionError):
            assert_directory_guards(self, moved)


if __name__ == '__main__':
    unittest.main()
