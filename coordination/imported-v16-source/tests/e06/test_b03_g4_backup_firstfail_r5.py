"""B03 R5 source regression for bounded G4 backup first-failure diagnostics.

SOURCE_ONLY: do not infer Windows E06/E07 success from these unit checks.
"""
from __future__ import annotations
import ast
from pathlib import Path
import re
import unittest

SOURCE = Path(__file__).resolve().parents[2] / 'coordination/e06/t06_samevm_installed_smoke.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'), filename=str(SOURCE))
FUNCTIONS = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and
             n.name == 'verified_probe_first_failure']
if len(FUNCTIONS) != 1:
    raise RuntimeError('B03_G4_BOUNDED_PROBE_REASON_MISSING')
NAMESPACE = {'re': re, 'RuntimeError': RuntimeError}
exec(compile(ast.Module(body=FUNCTIONS, type_ignores=[]), str(SOURCE), 'exec'), NAMESPACE)
verified_probe_first_failure = NAMESPACE['verified_probe_first_failure']

class TestOriginalBackupFirstFailure(unittest.TestCase):
    def test_manifest_exact_code(self):
        self.assertEqual(verified_probe_first_failure(RuntimeError(
            'T06_EXACT_PROBE_SLOT_MANIFEST_PATH_HOLD')),
            'T06_EXACT_PROBE_SLOT_MANIFEST_PATH_HOLD')
    def test_identity_exact_code(self):
        self.assertEqual(verified_probe_first_failure(RuntimeError(
            'T06_EXACT_PROBE_SLOT_PROBE_IDENTITY_HOLD')),
            'T06_EXACT_PROBE_SLOT_PROBE_IDENTITY_HOLD')
    def test_directory_exact_code(self):
        self.assertEqual(verified_probe_first_failure(RuntimeError(
            'T06_EXACT_PROBE_SLOT_UNEXPECTED_DIRECTORY_HOLD')),
            'T06_EXACT_PROBE_SLOT_UNEXPECTED_DIRECTORY_HOLD')
    def test_reject_foreign_path(self):
        self.assertEqual(verified_probe_first_failure(RuntimeError('C:/Users/private.bin')),
            'T06_EXACT_PROBE_SLOT_UNCLASSIFIED_HOLD')
    def test_reject_multiline(self):
        self.assertEqual(verified_probe_first_failure(RuntimeError(
            'T06_EXACT_PROBE_SLOT_MANIFEST_HOLD\\nmore')),
            'T06_EXACT_PROBE_SLOT_UNCLASSIFIED_HOLD')
    def test_reject_other_exception(self):
        self.assertEqual(verified_probe_first_failure(ValueError(
            'T06_EXACT_PROBE_SLOT_MANIFEST_HOLD')),
            'T06_EXACT_PROBE_SLOT_UNCLASSIFIED_HOLD')

if __name__ == '__main__':
    unittest.main()
