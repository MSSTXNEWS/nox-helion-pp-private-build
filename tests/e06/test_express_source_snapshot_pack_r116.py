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


    def _commit_extra_name(self, name: str):
        target = self.repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"extra committed bytes\\n")
        run(self.repo, 'add', '--', name)
        run(self.repo, 'commit', '-qm', 'freeze test path')
        self.head = run(self.repo, 'rev-parse', 'HEAD')

    def test_win32_device_alias_is_rejected_before_publication(self):
        self._commit_extra_name('CON.txt')
        with self.assertRaisesRegex(ValueError, 'WINDOWS_SOURCE_PATH_HOLD'):
            self.packer.build(self.repo, self.head, self.target)
        self.assertFalse(self.target.exists())

    def test_win32_illegal_punctuation_is_rejected_before_publication(self):
        self._commit_extra_name('models/bad?.gguf')
        with self.assertRaisesRegex(ValueError, 'WINDOWS_SOURCE_PATH_HOLD'):
            self.packer.build(self.repo, self.head, self.target)
        self.assertFalse(self.target.exists())

    def test_win32_trailing_dot_is_rejected_before_publication(self):
        self._commit_extra_name('notes.')
        with self.assertRaisesRegex(ValueError, 'WINDOWS_SOURCE_PATH_HOLD'):
            self.packer.build(self.repo, self.head, self.target)
        self.assertFalse(self.target.exists())

    def test_regular_nested_windows_path_preserves_git_provenance(self):
        self._commit_extra_name('models/Qwen3.gguf')
        receipt = self.packer.build(self.repo, self.head, self.target)
        self.assertEqual(receipt['files'], 2)
        with zipfile.ZipFile(self.target) as archive:
            manifest = json.loads(archive.read('SOURCE_MANIFEST.json'))
            self.assertEqual(manifest['file_count'], 2)
            self.assertEqual(
                archive.read('source/models/Qwen3.gguf'), b"extra committed bytes\\n")


    def test_existing_immutable_output_never_overwritten(self):
        sentinel = b'FROZEN_ARCHIVE_NOLOSS\\n'
        self.target.write_bytes(sentinel)
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_DESTINATION_ALREADY_EXISTS_HOLD'):
            self.packer.build(self.repo, self.head, self.target)
        self.assertEqual(self.target.read_bytes(), sentinel)

    def test_existing_destination_symlink_is_not_followed_or_replaced(self):
        sentinel_path = self.target.parent / 'other-owned.zip'
        sentinel = b'OTHER_OWNER_ARCHIVE_UNTOUCHED\\n'
        sentinel_path.write_bytes(sentinel)
        try:
            self.target.symlink_to(sentinel_path)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_DESTINATION_ALREADY_EXISTS_HOLD'):
            self.packer.build(self.repo, self.head, self.target)
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(sentinel_path.read_bytes(), sentinel)

if __name__ == '__main__':
    unittest.main()
