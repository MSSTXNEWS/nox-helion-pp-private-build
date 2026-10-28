"""E06 offline tests; no original NOX archive or Windows acceptance is implied."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

SRC = Path(__file__).resolve().parents[2] / 'coordination/e06/verify_original_729_source.py'
spec = importlib.util.spec_from_file_location('e06_original_source_lock', SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fixture(root, files, symlink=False):
    archive = root / 'source.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            if symlink and name == 'link':
                entry = zipfile.ZipInfo('link')
                entry.create_system = 3
                entry.external_attr = (0o120777 << 16)
                z.writestr(entry, data)
            else:
                z.writestr(name, data)
    raw = archive.read_bytes()
    blocks = [raw[:len(raw)//3], raw[len(raw)//3:2*len(raw)//3], raw[2*len(raw)//3:]]
    pins = []
    for (name, _, _), block in zip(mod.PARTS, blocks):
        (root / name).write_bytes(block)
        sha1 = hashlib.sha1(b'blob '+str(len(block)).encode()+b'\0'+block).hexdigest()
        pins.append((name, len(block), sha1))
    return pins, hashlib.sha256(raw).hexdigest()


class Original729SourceLockTests(unittest.TestCase):
    def check(self, files, *, symlink=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins, sha = fixture(root, files, symlink)
            return mod.verify_original(root, part_pins=pins, archive_sha=sha,
                                       expected_files=len(files), run_id='NOX-R10-20261028')

    def test_valid_zip_produces_file_hashes_not_release_claim(self):
        result = self.check([('a/p01.cs', b'123'), ('assets/wow.png', b'PNG')])
        self.assertEqual(result['fileCount'], 2)
        self.assertEqual(result['files'][0]['sha256'], hashlib.sha256(b'123').hexdigest())
        self.assertFalse(result['releaseAccepted'])
        self.assertFalse(result['nativeWindowsAccepted'])
        self.assertFalse(result['ownerReceiptsVerified'])

    def test_missing_part_holds(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pins, sha = fixture(root, [('one', b'A')])
            (root / mod.PARTS[1][0]).unlink()
            with self.assertRaisesRegex(mod.SourceHold, 'MISSING_OR_SYMLINK'):
                mod.verify_original(root, part_pins=pins, archive_sha=sha, expected_files=1, run_id='NOX-R10-20261028')

    def test_tampered_part_holds_before_zip_parse(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pins, sha = fixture(root, [('one', b'ABC')])
            name = mod.PARTS[0][0]
            source = root / name
            data = source.read_bytes()
            source.write_bytes(b'X' + data[1:])
            with self.assertRaisesRegex(mod.SourceHold, 'GIT_BLOB_SHA1'):
                mod.verify_original(root, part_pins=pins, archive_sha=sha, expected_files=1, run_id='NOX-R10-20261028')

    def test_wrong_combined_sha_holds(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pins, _ = fixture(root, [('one', b'A')])
            with self.assertRaisesRegex(mod.SourceHold, 'ZIP_SHA256_MISMATCH'):
                mod.verify_original(root, part_pins=pins, archive_sha='0'*64, expected_files=1, run_id='NOX-R10-20261028')

    def test_wrong_file_count_holds(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pins, sha = fixture(root, [('one', b'A')])
            with self.assertRaisesRegex(mod.SourceHold, 'ZIP_FILE_COUNT_MISMATCH'):
                mod.verify_original(root, part_pins=pins, archive_sha=sha, expected_files=729, run_id='NOX-R10-20261028')

    def test_zip_traversal_rejected(self):
        with self.assertRaisesRegex(mod.SourceHold, 'ZIP_WINDOWS_PATH_COLLISION_OR_TRAVERSAL'):
            self.check([('../escape', b'unsafe')])

    def test_win_case_collision_rejected(self):
        with self.assertRaisesRegex(mod.SourceHold, 'ZIP_DUPLICATE_WINDOWS_NAME'):
            self.check([('A/file.cs', b'a'), ('a/FILE.cs', b'b')])

    def test_windows_reserved_filename_rejected(self):
        with self.assertRaisesRegex(mod.SourceHold, 'ZIP_WINDOWS_PATH_COLLISION_OR_TRAVERSAL'):
            self.check([('base/CON.txt', b'bad')])

    def test_zip_symlink_rejected(self):
        with self.assertRaisesRegex(mod.SourceHold, 'ZIP_SYMLINK_NOT_ALLOWED'):
            self.check([('link', b'target')], symlink=True)

    def test_windows_ads_rejected(self):
        with self.assertRaisesRegex(mod.SourceHold, 'ZIP_ABSOLUTE_OR_ADS_PATH'):
            self.check([('foo.txt:extra', b'bad')])

    def test_unicode_normalization_collision_rejected(self):
        with self.assertRaisesRegex(mod.SourceHold, 'ZIP_NONCANONICAL_UNICODE'):
            self.check([('Cafe\u0301/data', b'bad')])

    def test_invalid_run_id_rejected(self):
        with self.assertRaisesRegex(mod.SourceHold, 'INVALID_RUN_ID'):
            mod.verify_original(Path('.'), run_id='')


if __name__ == '__main__':
    unittest.main()
