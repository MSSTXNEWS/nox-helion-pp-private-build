"""Source-only security checks, not an original-729 or native-Windows acceptance."""
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import threading
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "coordination" / "source-lock"))
import verify_original_archive as archive


class ExclusiveManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.receipt = {'schema': 'SYNTHETIC_ONLY', 'status': 'SOURCE_ONLY_NOT_E07'}

    def test_no_output_replaced_when_file_already_exists(self):
        output = self.root/'receipt.json'
        output.write_bytes(b'ORIGINAL_OWNER_RECEIPT')
        with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS_NO_OVERWRITE'):
            archive.publish_manifest_exclusive(output, self.receipt)
        self.assertEqual(output.read_bytes(), b'ORIGINAL_OWNER_RECEIPT')
        self.assertFalse(list(self.root.glob('.nox-source-audit-*')))

    def test_broken_symlink_does_not_escape_output_dir(self):
        output = self.root/'receipt.json'
        target = self.root/'outside-not-existing.json'
        try:
            output.symlink_to(target)
        except (NotImplementedError, OSError) as e:
            self.skipTest('symlink unavailable: '+str(e))
        with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS_NO_OVERWRITE'):
            archive.publish_manifest_exclusive(output, self.receipt)
        self.assertTrue(output.is_symlink())
        self.assertFalse(target.exists())

    def test_symlink_parent_is_denied(self):
        trusted = self.root/'real'; trusted.mkdir()
        alias = self.root/'alias'
        try:
            alias.symlink_to(trusted, target_is_directory=True)
        except (NotImplementedError, OSError) as e:
            self.skipTest('symlink unavailable: '+str(e))
        with self.assertRaisesRegex(ValueError, 'OUTPUT_PARENT_REPARSE_HOLD'):
            archive.publish_manifest_exclusive(alias/'receipt.json', self.receipt)
        self.assertFalse((trusted/'receipt.json').exists())

    def test_output_complete_and_no_temporary_leak(self):
        output = self.root/'sub'/'receipt.json'
        archive.publish_manifest_exclusive(output, self.receipt)
        self.assertEqual(json.loads(output.read_text(encoding='utf-8')), self.receipt)
        self.assertFalse(list(output.parent.glob('.nox-source-audit-*')))

    def test_parallel_writers_do_not_overwrite(self):
        output = self.root/'receipt.json'
        barrier = threading.Barrier(2)
        def write(idx):
            barrier.wait(timeout=3)
            try:
                archive.publish_manifest_exclusive(output, {'run': idx})
                return 'saved'
            except ValueError as exc:
                return str(exc)
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(write, (1,2)))
        self.assertEqual(sorted(results), ['OUTPUT_EXISTS_NO_OVERWRITE', 'saved'])
        self.assertIn(json.loads(output.read_text())['run'], (1,2))
        self.assertFalse(list(self.root.glob('.nox-source-audit-*')))

    def test_original_archive_contract_is_not_changed(self):
        self.assertEqual(archive.PARTS, ('source_00.part', 'source_01.part', 'source_02.part'))
        self.assertEqual(archive.EXPECTED_SIZE, 60364346)
        self.assertEqual(archive.EXPECTED_PART_SIZES, (20971520, 20971520, 18421306))
        self.assertEqual(len(archive.EXPECTED_PART_GIT_BLOBS), 3)
        self.assertEqual(archive.EXPECTED_SHA256,
            'ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a')

    def test_synthetic_archive_returns_only_source_status(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('src/hello.txt', 'offline test only')
        payload = stream.getvalue()
        splits = (payload[:15], payload[15:30], payload[30:])
        for i, fragment in enumerate(splits):
            (self.root/f'source_0{i}.part').write_bytes(fragment)
        synthetic_pins = tuple(hashlib.sha1(b'blob ' + str(len(p)).encode() + b'\0' + p).hexdigest() for p in splits)
        with patch.object(archive, 'EXPECTED_SIZE', len(payload)), \
             patch.object(archive, 'EXPECTED_PART_SIZES', tuple(map(len, splits))), \
             patch.object(archive, 'EXPECTED_PART_GIT_BLOBS', synthetic_pins), \
             patch.object(archive, 'EXPECTED_SHA256', hashlib.sha256(payload).hexdigest()):
            receipt = archive.audit(self.root, expected_files=1)
        self.assertEqual(receipt['file_count'], 1)
        self.assertEqual(receipt['files'][0]['sha256'],
                         hashlib.sha256(b'offline test only').hexdigest())
        self.assertEqual(receipt['status'], 'SOURCE_ARCHIVE_VERIFIED_ONLY_NOT_E07_RELEASE')

    def test_empty_archive_parts_refused(self):
        for name in archive.PARTS:
            (self.root/name).write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'Part sizes mismatch'):
            archive.audit(self.root, expected_files=729)

if __name__ == '__main__':
    unittest.main()
