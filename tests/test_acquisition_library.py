"""Megapatch A: real SQLite FTS5 and real-byte readback, no fake downloads."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from src.nox_selfbuilder.acquisition_library import AcquisitionHold, audit_library


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'library.sqlite'
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute('CREATE VIRTUAL TABLE acquisitions USING fts5(title, origin)')
            con.executemany('INSERT INTO acquisitions VALUES (?,?)',
                            [(f'asset-{i}', 'official') for i in range(143)])
        self.pin = sha(self.db)
        self.asset = self.root / 'weights' / 'sample.gguf'
        self.asset.parent.mkdir()
        self.asset.write_bytes(b'real-download-bytes-for-hash-verification')
        self.manifest = self.root / 'physical.json'
        self.manifest.write_text(json.dumps({'schema': 'NOX-ACQUISITION-FILES-v1',
            'files': [{'path': 'weights/sample.gguf', 'sha256': sha(self.asset),
                       'bytes': self.asset.stat().st_size}]}), encoding='utf-8')

    def audit(self, **kwargs):
        return audit_library(str(self.db), self.pin, approved_roots=[str(self.root)], **kwargs)

    def test_pinned_fts5_read_only(self):
        result = self.audit()
        self.assertEqual(result['fts5_rows']['acquisitions'], 143)
        self.assertEqual(result['physical_files_verified'], 0)
        self.assertFalse(result['models_installed'])

    def test_physical_bytes(self):
        result = self.audit(manifest_path=str(self.manifest), manifest_sha256=sha(self.manifest), assets_root=str(self.root))
        self.assertEqual(result['physical_files_verified'], 1)
        self.assertEqual(result['status'], 'PHYSICAL_FILES_SHA256_VERIFIED')
        self.assertFalse(result['tools_installed'])

    def test_db_tamper(self):
        with self.db.open('ab') as f: f.write(b'x')
        with self.assertRaisesRegex(AcquisitionHold, 'DB_SHA256_MISMATCH'): self.audit()

    def test_manifest_tamper(self):
        with self.assertRaisesRegex(AcquisitionHold, 'MANIFEST_SHA256_MISMATCH'):
            self.audit(manifest_path=str(self.manifest), manifest_sha256='f'*64, assets_root=str(self.root))

    def test_asset_tamper(self):
        self.asset.write_bytes(b'tampered')
        with self.assertRaises(AcquisitionHold):
            self.audit(manifest_path=str(self.manifest), manifest_sha256=sha(self.manifest), assets_root=str(self.root))

    def test_manifest_path_escape(self):
        payload = {'schema': 'NOX-ACQUISITION-FILES-v1', 'files': [{'path': '../secret', 'sha256': 'a'*64, 'bytes': 1}]}
        self.manifest.write_text(json.dumps(payload), encoding='utf-8')
        with self.assertRaisesRegex(AcquisitionHold, 'PATH_TRAVERSAL'):
            self.audit(manifest_path=str(self.manifest), manifest_sha256=sha(self.manifest), assets_root=str(self.root))

    def test_manifest_duplicate_case(self):
        payload={'schema':'NOX-ACQUISITION-FILES-v1','files':[
            {'path':'weights/sample.gguf','sha256':sha(self.asset),'bytes':self.asset.stat().st_size},
            {'path':'WEIGHTS/SAMPLE.GGUF','sha256':sha(self.asset),'bytes':self.asset.stat().st_size}]}
        self.manifest.write_text(json.dumps(payload), encoding='utf-8')
        with self.assertRaisesRegex(AcquisitionHold, 'DUPLICATE_FILE'):
            self.audit(manifest_path=str(self.manifest),manifest_sha256=sha(self.manifest),assets_root=str(self.root))

    def test_wrong_root(self):
        with self.assertRaisesRegex(AcquisitionHold, 'OUTSIDE_APPROVED_ROOTS'):
            audit_library(str(self.db), self.pin, approved_roots=[str(self.root / 'elsewhere')])

    def test_symlink_hold(self):
        alias = self.root / 'alias.sqlite'
        try: alias.symlink_to(self.db)
        except (OSError, NotImplementedError): self.skipTest('no symlink')
        with self.assertRaisesRegex(AcquisitionHold, 'REPARSE_PATH_DENIED'):
            audit_library(str(alias), self.pin, approved_roots=[str(self.root)])

    def test_requires_db_pin(self):
        with self.assertRaisesRegex(AcquisitionHold, 'DB_NATIVE_SHA_REQUIRED'):
            audit_library(str(self.db), '0'*64, approved_roots=[str(self.root)])


if __name__ == '__main__': unittest.main()
