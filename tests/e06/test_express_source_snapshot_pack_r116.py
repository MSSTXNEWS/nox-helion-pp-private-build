"""Real Git fixture tests: immutable HEAD-to-ZIP provenance (no Windows claim)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


PACKER = Path(__file__).resolve().parents[2] / 'coordination/e06/express_source_snapshot_pack.py'


def run(repo: Path, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


class ExpressSourceProvenanceR116(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.repo = root / 'repo'
        self.repo.mkdir()
        self.target = root / 'source.zip'
        run(self.repo, 'init', '-q')
        run(self.repo, 'config', 'user.email', 'fixture@example.invalid')
        run(self.repo, 'config', 'user.name', 'Fixture')
        (self.repo / 'original.txt').write_bytes(b'approved source payload\n')
        run(self.repo, 'add', 'original.txt')
        run(self.repo, 'commit', '-qm', 'freeze immutable source')
        self.head = run(self.repo, 'rev-parse', 'HEAD')
        spec = importlib.util.spec_from_file_location('nox_pack_r116', PACKER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.packer = mod

    def test_clean_frozen_git_build_receipt_and_manifest_hash(self):
        receipt = self.packer.build(self.repo, self.head, self.target)
        self.assertEqual(receipt['sha'], self.head)
        self.assertEqual(receipt['files'], 1)
        with zipfile.ZipFile(self.target) as z:
            doc = json.loads(z.read('SOURCE_MANIFEST.json'))
            record, = doc['files']
            raw = z.read('source/original.txt')
            self.assertEqual(record['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(record['git_blob_sha1'],
                             run(self.repo, 'rev-parse', 'HEAD:original.txt'))
            self.assertEqual(doc['gates']['G4_E07'], 'NOT_RUN')

    def test_hidden_assume_unchanged_mutation_is_rejected_and_not_published(self):
        run(self.repo, 'update-index', '--assume-unchanged', 'original.txt')
        (self.repo / 'original.txt').write_bytes(b'tampered source bytes!\n')
        self.assertEqual(run(self.repo, 'status', '--porcelain'), '')
        with self.assertRaisesRegex(ValueError, 'TRACKED_GIT_BLOB_MISMATCH'):
            self.packer.build(self.repo, self.head, self.target)
        self.assertFalse(self.target.exists())

    def test_disagreeing_git_index_and_head_is_rejected(self):
        (self.repo / 'new.txt').write_bytes(b'not part of head\n')
        run(self.repo, 'add', 'new.txt')
        with self.assertRaisesRegex(ValueError, 'DIRTY_CHECKOUT_HOLD'):
            self.packer.build(self.repo, self.head, self.target)
        self.assertFalse(self.target.exists())

    def test_head_symlink_cannot_be_packaged_as_regular_file(self):
        link = self.repo / 'linked.txt'
        try:
            link.symlink_to('original.txt')
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable')
        run(self.repo, 'add', 'linked.txt')
        run(self.repo, 'commit', '-qm', 'freeze a symlink')
        self.head = run(self.repo, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'NONREGULAR_HEAD_TREE_ENTRY'):
            self.packer.build(self.repo, self.head, self.target)
        self.assertFalse(self.target.exists())


if __name__ == '__main__':
    unittest.main()
