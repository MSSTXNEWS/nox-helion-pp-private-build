"""Actual synthetic ZIP regressions; never attest original 729 source bytes."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[4]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


canonical = load_module('a01_canonical', 'coordination/source-lock/verify_original_archive.py')
e06 = load_module('a01_e06', 'coordination/e06/verify_original_729_source.py')


def parts(root, member):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_STORED) as archive:
        archive.writestr('safeXhidden.txt', b'original payload')
    raw = buffer.getvalue().replace(b'safeXhidden.txt', member)
    lengths = (len(raw) // 3, len(raw) // 3)
    blocks = (raw[:lengths[0]], raw[lengths[0]:sum(lengths)], raw[sum(lengths):])
    pins = []
    for name, block in zip(canonical.PARTS, blocks):
        (root / name).write_bytes(block)
        blob = hashlib.sha1(f'blob {len(block)}\0'.encode() + block).hexdigest()
        pins.append((name, len(block), blob))
    return raw, pins


class OriginalNameTests(unittest.TestCase):
    def test_zipinfo_nul_truncation_denied(self):
        info = zipfile.ZipInfo('safe\0hidden.txt')
        self.assertEqual(info.filename, 'safe')
        with self.assertRaisesRegex(ValueError, 'Unsafe original ZIP name'):
            canonical.validate_members([info])

    def test_hidden_traversal_suffix_denied(self):
        with self.assertRaisesRegex(ValueError, 'Unsafe original ZIP name'):
            canonical.validate_members([zipfile.ZipInfo('safe\0/../hidden')])

    def test_raw_nul_zip_denied_by_canonical_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw, pins = parts(root, b'safe\0hidden.txt')
            with patch.multiple(canonical, EXPECTED_SIZE=len(raw),
                                EXPECTED_PART_SIZES=tuple(p[1] for p in pins),
                                EXPECTED_PART_GIT_BLOBS=tuple(p[2] for p in pins),
                                EXPECTED_SHA256=hashlib.sha256(raw).hexdigest()):
                with self.assertRaisesRegex(ValueError, 'Unsafe original ZIP name'):
                    canonical.audit(root, 1)

    def test_raw_nul_zip_denied_by_e06_shared_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw, pins = parts(root, b'safe\0hidden.txt')
            with self.assertRaisesRegex(e06.SourceHold, 'ZIP_NAMESPACE_OR_SPECIAL_FILE_HOLD'):
                e06.verify_original(root, part_pins=pins, archive_sha=hashlib.sha256(raw).hexdigest(),
                                    expected_files=1, run_id='ASTRA-R27-A01-NULL')

    def test_actual_safe_zip_still_hashes_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw, pins = parts(root, b'safeXhidden.txt')
            result = e06.verify_original(root, part_pins=pins, archive_sha=hashlib.sha256(raw).hexdigest(),
                                         expected_files=1, run_id='ASTRA-R27-A01-SAFE')
            self.assertEqual(result['files'][0]['path'], 'safeXhidden.txt')
            self.assertEqual(result['files'][0]['sha256'], hashlib.sha256(b'original payload').hexdigest())
            self.assertFalse(result['releaseAccepted'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
