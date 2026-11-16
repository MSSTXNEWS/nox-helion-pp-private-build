"""No network, no server, no GPU; focused V13 archive publication regression."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from v13_split_archive import assemble


class ArchiveSafetyTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.parts = [b'first part', b'last part']
        self.archive = b''.join(self.parts)
        self.entries = []
        for n, payload in enumerate(self.parts, 1):
            name = 'test.zip.%03d' % n
            (self.root/name).write_bytes(payload)
            self.entries.append({'file': name, 'bytes': len(payload),
                                 'sha256': hashlib.sha256(payload).hexdigest()})
        self.manifest = self.root/'parts_manifest.json'
        self.metadata = {'schema': 'NOX_SPLIT_ARCHIVE_V1', 'archive': 'test.zip',
                         'archive_bytes': len(self.archive),
                         'archive_sha256': hashlib.sha256(self.archive).hexdigest(),
                         'parts': self.entries}
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.metadata), encoding='utf8')

    def test_success_then_verified_reuse(self):
        out = assemble(self.manifest, reserve=0)
        self.assertEqual(out.read_bytes(), self.archive)
        self.assertEqual(assemble(self.manifest, reserve=0), out)
        self.assertEqual(list(self.root.glob('*.assembling-*')), [])

    def test_corrupted_part_fails_without_output(self):
        (self.root/'test.zip.002').write_bytes(b'bad part!')
        with self.assertRaisesRegex(ValueError, 'DIGEST_MISMATCH'):
            assemble(self.manifest, reserve=0)
        self.assertFalse((self.root/'test.zip').exists())
        self.assertEqual(list(self.root.glob('*.assembling-*')), [])

    def test_publish_race_does_not_overwrite_unique_preimage(self):
        def concurrent_writer(dest):
            dest.write_bytes(b'unique-owner-file')
        with self.assertRaises(FileExistsError):
            assemble(self.manifest, reserve=0, before_publish=concurrent_writer)
        self.assertEqual((self.root/'test.zip').read_bytes(), b'unique-owner-file')
        self.assertEqual(list(self.root.glob('*.assembling-*')), [])

    def test_manifest_duplicate_key_rejected(self):
        good = self.manifest.read_text()
        self.manifest.write_text(good.replace('"schema":', '"schema":"wrong", "schema":', 1))
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_MANIFEST_KEY'):
            assemble(self.manifest, reserve=0)

    def test_symlink_part_rejected(self):
        (self.root/'test.zip.001').unlink()
        (self.root/'payload').write_bytes(self.parts[0])
        (self.root/'test.zip.001').symlink_to(self.root/'payload')
        with self.assertRaises(OSError):
            assemble(self.manifest, reserve=0)
        self.assertFalse((self.root/'test.zip').exists())

    def test_archive_existing_different_never_clobbered(self):
        out = self.root/'test.zip'
        out.write_bytes(b'original')
        with self.assertRaises(FileExistsError):
            assemble(self.manifest, reserve=0)
        self.assertEqual(out.read_bytes(), b'original')

    def test_path_traversal_rejected(self):
        self.metadata['parts'][0]['file'] = '../unsafe'
        self.save()
        with self.assertRaisesRegex(ValueError, 'INVALID_LOCAL_NAME'):
            assemble(self.manifest, reserve=0)

    def test_no_bool_size(self):
        self.metadata['parts'][0]['bytes'] = True
        self.save()
        with self.assertRaisesRegex(ValueError, 'INVALID_PART_SIZE'):
            assemble(self.manifest, reserve=0)


if __name__ == '__main__':
    unittest.main()
