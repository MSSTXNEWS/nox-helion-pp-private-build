import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

MODULE = Path(__file__).with_name('verify_original_parts_r05.py')
spec = importlib.util.spec_from_file_location('original_parts_r05', MODULE)
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


def digest(b):
    return hashlib.sha256(b).hexdigest()


class OriginalPartsR05(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw = b'hello original source'
        self.member = 'assets/HOME_OWNER_APPROVED.png'
        self.lock = {'files': [{'path': self.member, 'sha256': digest(self.raw),
                                 'bytes': len(self.raw)}]}
        self.archive = self.make_zip(self.member, self.raw)
        self.parts_dir = self.root / 'parts'
        self.parts_dir.mkdir()
        self.lock_file = self.root / 'lock.json'
        self.lock_file.write_text(json.dumps(self.lock))
        self.put_parts(self.archive)

    def make_zip(self, name, value):
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(name, value)
        return b.getvalue()

    def put_parts(self, payload):
        chunks = (payload[:10], payload[10:20], payload[20:])
        for name, chunk in zip(source.PINNED_NAMES, chunks):
            (self.parts_dir / name).write_bytes(chunk)
        return tuple(map(len, chunks))

    def check(self, **overrides):
        return source.attest(self.parts_dir, self.lock_file, lock_digest=digest(self.lock_file.read_bytes()),
                             archive_digest=digest(self.archive), part_sizes=self.lengths,
                             expected_count=1, **overrides)

    @property
    def lengths(self):
        return tuple((self.parts_dir / name).stat().st_size for name in source.PINNED_NAMES)

    def test_happy_fixture_three_parts_and_member(self):
        r = self.check()
        self.assertEqual(r['status'], 'RAW_BYTES_VERIFIED')
        self.assertEqual(r['file_members_verified'], 1)
        self.assertEqual(len(r['parts']), 3)

    def test_missing_part(self):
        sizes = self.lengths
        (self.parts_dir / 'source_01.part').unlink()
        r = source.attest(self.parts_dir, self.lock_file,
                          lock_digest=digest(self.lock_file.read_bytes()),
                          archive_digest=digest(self.archive), part_sizes=sizes,
                          expected_count=1)
        self.assertEqual(r['status'], 'HOLD')

    def test_corrupt_archive(self):
        sizes = self.lengths
        (self.parts_dir / 'source_00.part').write_bytes(b'Z' * sizes[0])
        r = source.attest(self.parts_dir, self.lock_file,
                          lock_digest=digest(self.lock_file.read_bytes()),
                          archive_digest=digest(self.archive), part_sizes=sizes,
                          expected_count=1)
        self.assertIn('archive size/SHA-256 mismatch', r['error'])

    def test_mismatched_manifest(self):
        self.lock['files'][0]['sha256'] = '0' * 64
        self.lock_file.write_text(json.dumps(self.lock))
        self.assertIn('member SHA-256 mismatch', self.check()['error'])

    def test_unsafe_zip_path(self):
        self.member = '../escape.txt'
        self.lock['files'][0]['path'] = self.member
        self.lock_file.write_text(json.dumps(self.lock))
        self.archive = self.make_zip(self.member, self.raw)
        self.put_parts(self.archive)
        self.assertIn('unsafe/duplicate SourceLock path', self.check()['error'])

    def test_manifest_tamper_rejected(self):
        r = source.attest(self.parts_dir, self.lock_file,
                          lock_digest='0'*64, archive_digest=digest(self.archive),
                          part_sizes=self.lengths, expected_count=1)
        self.assertIn('SourceLock SHA-256 mismatch', r['error'])

    def test_symlink_part_rejected(self):
        p = self.parts_dir / 'source_01.part'
        target = self.root / 'copied.bin'
        target.write_bytes(p.read_bytes())
        p.unlink()
        p.symlink_to(target)
        self.assertIn('not an ordinary regular file', self.check()['error'])

    def test_no_part_bytes_no_success(self):
        expected_sizes = self.lengths
        for name in source.PINNED_NAMES:
            (self.parts_dir / name).unlink()
        result = source.attest(self.parts_dir, self.lock_file,
                               lock_digest=digest(self.lock_file.read_bytes()),
                               archive_digest=digest(self.archive),
                               part_sizes=expected_sizes, expected_count=1)
        self.assertFalse(result['raw_original_verified'])

    def test_unsafe_directory_traversal(self):
        for name in ('a/../b', '/root/x', 'a\\b', './x'):
            self.assertFalse(source._safe_member(name), name)

    def test_benign_member_path(self):
        self.assertTrue(source._safe_member('helion/personas.py'))

if __name__ == '__main__':
    unittest.main()
