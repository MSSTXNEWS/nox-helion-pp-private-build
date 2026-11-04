"""R133: frozen HEAD bytes cannot be accepted via redirected source ancestors."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

PACKER = Path(__file__).resolve().parents[2] / 'coordination/e06/express_source_snapshot_pack.py'

def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()

class SourceSnapshotFdIdentityR133(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        git(self.repo, 'config', 'user.email', 'source-fixture@example.invalid')
        git(self.repo, 'config', 'user.name', 'Source Fixture')
        owner = self.repo / 'owner'
        owner.mkdir()
        (owner / 'file.txt').write_bytes(b'original Git-pinned bytes\n')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-qm', 'freeze owner files')
        self.head = git(self.repo, 'rev-parse', 'HEAD')
        self.target = self.root / 'source.zip'
        spec = importlib.util.spec_from_file_location('nox_r133_pack', PACKER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.pack = module

    def test_normal_file_retains_exact_git_sha_and_archive_bytes(self):
        receipt = self.pack.build(self.repo, self.head, self.target)
        self.assertEqual(receipt['sha'], self.head)
        self.assertEqual(receipt['files'], 1)
        with zipfile.ZipFile(self.target) as archive:
            self.assertEqual(archive.read('source/owner/file.txt'),
                             b'original Git-pinned bytes\n')
            manifest = json.loads(archive.read('SOURCE_MANIFEST.json'))
            self.assertEqual(manifest['files'][0]['git_blob_sha1'],
                             git(self.repo, 'rev-parse', 'HEAD:owner/file.txt'))

    def test_assume_unchanged_plus_identical_symlink_parent_denied(self):
        git(self.repo, 'update-index', '--assume-unchanged', 'owner/file.txt')
        outside = self.root / 'original-owner'
        (self.repo / 'owner').rename(outside)
        try:
            (self.repo / 'owner').symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('directory symlinks unavailable')
        with (self.repo / '.git/info/exclude').open('a', encoding='utf-8') as f:
            f.write('\n/owner\n')
        self.assertEqual(git(self.repo, 'status', '--porcelain',
                             '--untracked-files=normal'), '')
        self.assertEqual((self.repo / 'owner/file.txt').read_bytes(),
                         b'original Git-pinned bytes\n')
        with self.assertRaisesRegex(RuntimeError,
                                    'OUTPUT_PARENT_REPARSE_OR_UNSAFE|SOURCE_PART_'):
            self.pack.build(self.repo, self.head, self.target)
        self.assertFalse(self.target.exists())

if __name__ == '__main__':
    unittest.main()
