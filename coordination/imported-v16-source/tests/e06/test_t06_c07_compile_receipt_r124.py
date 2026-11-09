"""Real P01-C07 donor staging count vs the independent 729-file G1 archive.

Executes the original package build gate, stopping BEFORE any artifact download.
No mock installation, Windows, backend, or E07 success is implied.
"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'coordination/e06/t06_package_original_onehost.py'
C07 = ROOT / 'donors/P01_C07/P01_C07_RECEIPT.json'
SOURCE_HEAD = 'a' * 40

class AfterVerifiedCompileGate(Exception):
    """Intentional boundary: no artifact download or downstream release test."""

class C07RealCompileGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('r124_original_package', PACKAGE)
        cls.owner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.owner)
        r = json.loads(C07.read_text('utf-8'))
        data = bytearray()
        for entry in r['parts']:
            part = (ROOT / entry['path']).read_bytes()
            assert len(part) == entry['size_bytes']
            assert hashlib.sha1(b'blob ' + str(len(part)).encode() + b'\0' + part).hexdigest() == entry['git_blob_sha1']
            data.extend(part)
        assert len(data) == r['original_zip_bytes']
        assert hashlib.sha256(data).hexdigest() == r['original_zip_sha256']
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            assert z.testzip() is None
            cls.original_all = [m for m in z.infolist() if not m.is_dir()]
            cls.staged_r11 = [m for m in cls.original_all if m.filename.startswith('R11/')]
        cls.donor_zip_sha = r['original_zip_sha256']

    def make_receipt(self, **kwargs):
        row = dict(source_git_sha=SOURCE_HEAD,
                   original_zip_sha256=self.donor_zip_sha,
                   original_files_staged=len(self.staged_r11),
                   dotnet_build_exit=0)
        row.update(kwargs)
        return row

    def run_original_gate(self, receipt, head=SOURCE_HEAD):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            staged = root / 'staged'
            staged.mkdir()
            (staged / 'T06_COMPILE_EVIDENCE.json').write_text(json.dumps(receipt), 'utf-8')
            module = types.SimpleNamespace(verified_source_head=lambda: head)
            with patch.dict(sys.modules, {'t06_compile_original_wpf_p02': module}):
                with patch.object(self.owner, 'download_artifact', side_effect=AfterVerifiedCompileGate):
                    self.owner.build(root, staged)

    def test_physical_c07_selected_only_94_of_104_not_729(self):
        self.assertEqual(len(self.original_all), 104)
        self.assertEqual(len(self.staged_r11), 94)
        self.assertEqual(self.owner.EXPECTED_ZIP_SHA, self.donor_zip_sha)
        with self.assertRaises(AfterVerifiedCompileGate):
            self.run_original_gate(self.make_receipt())

    def test_wrong_source_head_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'T06_PACKAGE_COMPILE_SOURCE_HEAD_OR_R11_94_HOLD'):
            self.run_original_gate(self.make_receipt(), head='b' * 40)

    def test_different_archive_counts_rejected(self):
        for count in (729, 104, 93, 95, True, None, '94'):
            with self.subTest(count=count), self.assertRaisesRegex(RuntimeError, 'T06_PACKAGE_COMPILE_SOURCE_HEAD_OR_R11_94_HOLD'):
                self.run_original_gate(self.make_receipt(original_files_staged=count))

    def test_wrong_archive_hash_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'T06_PACKAGE_COMPILE_SOURCE_HEAD_OR_R11_94_HOLD'):
            self.run_original_gate(self.make_receipt(original_zip_sha256='0'*64))

    def test_failed_or_invalid_compiler_exit_rejected(self):
        for code in (1, True, None, '0'):
            with self.subTest(code=code), self.assertRaisesRegex(RuntimeError, 'T06_PACKAGE_COMPILE_SOURCE_HEAD_OR_R11_94_HOLD'):
                self.run_original_gate(self.make_receipt(dotnet_build_exit=code))

if __name__ == '__main__':
    unittest.main()
