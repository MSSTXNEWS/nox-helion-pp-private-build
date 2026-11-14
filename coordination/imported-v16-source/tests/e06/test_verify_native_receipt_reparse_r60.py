"""Original E06 JSON proof admission, Linux tests simulating Windows junction metadata.

Not a native Windows build or same-SHA physical E07 receipt.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2] / 'coordination/e06/verify_native_receipt_json.py'
spec = importlib.util.spec_from_file_location('nox_native_receipt_r60', SOURCE)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class TestReceiptPathTrust(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.original_dir = self.base / 'actual'
        self.original_dir.mkdir()
        self.proof = self.original_dir / 'receipt.json'
        self.payload = b'{"state":"HOLD","count":3}'
        self.proof.write_bytes(self.payload)

    def test_original_valid_receipt_canonical_and_sha(self):
        value = guard.admit(str(self.proof))
        sha, canonical = value.split('\t', 1)
        self.assertEqual(sha, hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(json.loads(canonical), {"state":"HOLD","count":3})

    def test_parent_directory_symlink_must_hold(self):
        alias = self.base / 'alias'
        alias.symlink_to(self.original_dir, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'reparse'):
            guard.admit(str(alias / 'receipt.json'))

    def test_windows_junction_flag_on_parent_must_hold(self):
        original_lstat = os.lstat
        parent = str(self.original_dir)

        class ReparseStat:
            def __init__(self, info):
                self.info = info
                self.st_mode = info.st_mode
                self.st_file_attributes = 0x400
            def __getattr__(self, name):
                return getattr(self.info, name)

        def lstat(path, *args, **kw):
            info = original_lstat(path, *args, **kw)
            return ReparseStat(info) if os.fspath(path) == parent else info

        with patch.object(os, 'lstat', lstat):
            with self.assertRaisesRegex(ValueError, 'reparse'):
                guard.admit(str(self.proof))

    def test_reparse_introduced_mid_read_must_hold(self):
        original_lstat, original_open = os.lstat, os.open
        parent = str(self.original_dir)
        flag = {"after_open": False}

        class ReparseStat:
            def __init__(self, info):
                self.info = info
                self.st_mode = info.st_mode
                self.st_file_attributes = 0x400
            def __getattr__(self, name):
                return getattr(self.info, name)

        def lstat(path, *args, **kw):
            info = original_lstat(path, *args, **kw)
            if os.fspath(path) == parent and flag['after_open']:
                return ReparseStat(info)
            return info

        def opened(path, flags, *args, **kw):
            fd = original_open(path, flags, *args, **kw)
            flag['after_open'] = True
            return fd

        with patch.object(os, 'lstat', lstat), patch.object(os, 'open', opened):
            with self.assertRaisesRegex(ValueError, 'reparse'):
                guard.admit(str(self.proof))

    def test_path_parent_traversal_denied(self):
        with self.assertRaisesRegex(ValueError, 'noncanonical'):
            guard.admit(str(self.original_dir / '..' / 'actual' / 'receipt.json'))

    def test_duplicate_json_key_still_rejected(self):
        self.proof.write_bytes(b'{"a":1,"a":2}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            guard.admit(str(self.proof))

    def test_nonfinite_constant_still_rejected(self):
        self.proof.write_bytes(b'{"model_score":NaN}')
        with self.assertRaises(ValueError):
            guard.admit(str(self.proof))

    def test_leaf_symlink_still_rejected(self):
        linked = self.original_dir / 'alias-proof.json'
        linked.symlink_to(self.proof)
        with self.assertRaisesRegex(ValueError, 'reparse'):
            guard.admit(str(linked))

    def test_size_limit_still_rejected(self):
        self.proof.write_bytes(b'x' * (guard.MAX_PROOF_BYTES + 1))
        with self.assertRaisesRegex(ValueError, 'receipt size'):
            guard.admit(str(self.proof))


if __name__ == '__main__':
    unittest.main()
