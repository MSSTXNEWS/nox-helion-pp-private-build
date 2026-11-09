"""MB3 original NSIS Setup: reject redirected path ancestry before PE/SHA admission.

Scoped to verify_nsis_setup. This does not establish Authenticode, E07, or installed UI.
"""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'coordination/e06/t06_package_original_onehost.py'
spec = importlib.util.spec_from_file_location('nox_original_t06_setup', SOURCE)
assert spec is not None and spec.loader is not None
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


def make_pe(path):
    content = bytearray(1024 * 1024)
    content[0:2] = b'MZ'
    content[60:64] = (128).to_bytes(4, 'little')
    content[128:132] = b'PE\x00\x00'
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


class OriginalNsisSetupAncestry(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def test_regular_owner_setup_retains_same_bytes_sha(self):
        binary = self.home / 'Setup.exe'
        digest = make_pe(binary)
        proof = owner.verify_nsis_setup(binary)
        self.assertEqual(proof, {'bytes': 1024 * 1024, 'sha256': digest})

    def test_redirected_ancestor_denied_before_hash_admission(self):
        physical = self.home / 'physical'
        physical.mkdir()
        make_pe(physical / 'Setup.exe')
        redirected = self.home / 'redirected'
        try:
            redirected.symlink_to(physical, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('directory symlink privileges unavailable')
        with self.assertRaisesRegex(RuntimeError, 'T06_NSIS_SETUP_REPARSE_ANCESTOR_HOLD'):
            owner.verify_nsis_setup(redirected / 'Setup.exe')

    def test_redirected_leaf_remains_denied(self):
        physical = self.home / 'physical.exe'
        make_pe(physical)
        alias = self.home / 'alias.exe'
        try:
            alias.symlink_to(physical)
        except (OSError, NotImplementedError):
            self.skipTest('file symlink privileges unavailable')
        with self.assertRaisesRegex(RuntimeError, 'T06_NSIS_SETUP_MISSING_OR_REDIRECTED'):
            owner.verify_nsis_setup(alias)

    def test_invalid_pe_still_denied(self):
        binary = self.home / 'Setup.exe'
        binary.write_bytes(b'X' * (1024 * 1024))
        with self.assertRaisesRegex(RuntimeError, 'T06_NSIS_SETUP_NOT_WINDOWS_PE'):
            owner.verify_nsis_setup(binary)


if __name__ == '__main__':
    unittest.main()
