"""Source-only parity gate; no real 729 ZIP, Windows, network or builds.

Set NOX_CANONICAL_SOURCE_FILE to a pinned before/after copy for RED/GREEN.
Without override, run from repository root against the canonical original verifier.
"""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

SOURCE = Path(os.environ.get('NOX_CANONICAL_SOURCE_FILE',
    str(Path(__file__).resolve().parents[2] / 'coordination/source-lock/verify_original_archive.py')))


def module():
    spec = importlib.util.spec_from_file_location('nox_source_lock_r18', SOURCE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_zip(name='normal.txt', data=b'normal-source-fixture'):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as f:
        f.writestr(name, data)
    return out.getvalue()


def synthetic_audit(m, raw):
    # Only synthetic pins IN MEMORY. Original SHA / member pass is NOT implied.
    a,b = len(raw)//3, 2*len(raw)//3
    chunks = [raw[:a],raw[a:b],raw[b:]]
    m.EXPECTED_SIZE = len(raw)
    m.EXPECTED_PART_SIZES = tuple(map(len, chunks))
    m.EXPECTED_PART_GIT_BLOBS = tuple(hashlib.sha1(
        b'blob ' + str(len(c)).encode() + b'\0' + c).hexdigest() for c in chunks)
    m.EXPECTED_SHA256 = hashlib.sha256(raw).hexdigest()
    with tempfile.TemporaryDirectory() as td:
        for filename, chunk in zip(m.PARTS, chunks):
            (Path(td)/filename).write_bytes(chunk)
        return m.audit(Path(td), 1)


class CanonicalZipParity(unittest.TestCase):
    def test_path_length_501_rejected(self):
        self.assertFalse(module().safe_name('a'*501))

    def test_path_length_500_accepted(self):
        self.assertTrue(module().safe_name('a'*500))

    def test_compression_bomb_ratio_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Suspicious ZIP compression ratio'):
            synthetic_audit(module(), test_zip('inflate.txt', b'X'*150_000))

    def test_normal_source_fixture_positive(self):
        r = synthetic_audit(module(), test_zip())
        self.assertEqual(r['file_count'], 1)

    def test_original_unicode_nfc_rule_retained(self):
        self.assertFalse(module().safe_name('e\u0301.txt'))

    def test_file_parent_collision_denied(self):
        with self.assertRaises(ValueError):
            module().validate_members([zipfile.ZipInfo('root'), zipfile.ZipInfo('root/x')])

    def test_immutable_expected_original_pin_unchanged(self):
        text = SOURCE.read_text(encoding='utf-8')
        self.assertIn('ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a', text)
        self.assertIn('e484e10d7b4ec9badeaae4c9d3a7e3aee5faa16b', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
