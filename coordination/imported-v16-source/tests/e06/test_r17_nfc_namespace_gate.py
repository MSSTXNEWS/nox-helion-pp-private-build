"""Hermetic R17 regression for canonical ZIP SourceLock NFC namespace policy.

Run from project root with: python -m unittest discover -s tests/e06 -p 'test_r17_nfc_namespace_gate.py' -v
No NOX original archive or Windows E2E is used.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest
from zipfile import ZipInfo

SOURCE = Path(__file__).resolve().parents[2] / 'coordination/source-lock/verify_original_archive.py'
spec = importlib.util.spec_from_file_location('nox_source_lock_canonical_r17', SOURCE)
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


def member(name: str) -> ZipInfo:
    return ZipInfo(name)


class NfcNamespaceGate(unittest.TestCase):
    def test_ascii_filename_is_preserved(self):
        self.assertTrue(source.safe_name('assets/HOME_OWNER_APPROVED.png'))
        source.validate_members([member('assets/HOME_OWNER_APPROVED.png')])

    def test_composed_unicode_is_accepted(self):
        self.assertTrue(source.safe_name('Caf\u00e9/notes.txt'))
        source.validate_members([member('Caf\u00e9/notes.txt')])

    def test_standalone_decomposed_unicode_is_rejected(self):
        self.assertFalse(source.safe_name('Cafe\u0301/notes.txt'))
        with self.assertRaisesRegex(ValueError, 'Unsafe path'):
            source.validate_members([member('Cafe\u0301/notes.txt')])

    def test_combined_nfc_nfd_collision_is_rejected(self):
        with self.assertRaises(ValueError):
            source.validate_members([member('Caf\u00e9/one.txt'), member('Cafe\u0301/one.txt')])

    def test_decomposed_directory_entry_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unsafe path'):
            source.validate_members([member('Cafe\u0301/')])

    def test_decomposed_nested_filename_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unsafe path'):
            source.validate_members([member('root/Sub/e\u0301.txt')])

    def test_original_symlink_gate_unchanged(self):
        info=member('one')
        info.create_system=3
        info.external_attr = (0o120777 << 16)
        with self.assertRaisesRegex(ValueError, 'Symlink/special file'):
            source.validate_members([info])

    def test_original_casefold_gate_unchanged(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate/case collision'):
            source.validate_members([member('A/name'), member('a/NAME')])

if __name__ == '__main__':
    unittest.main()
