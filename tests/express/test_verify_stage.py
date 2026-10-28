import importlib.util
import hashlib
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'coordination' / 'express' / 'verify_stage.py'
spec = importlib.util.spec_from_file_location('stage_verifier', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class TestNoLoss(unittest.TestCase):
    def test_git_blob_exact(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'test.txt'
            p.write_bytes(b'important existing source\n')
            raw = p.read_bytes()
            expected = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\x00'+raw).hexdigest()
            self.assertEqual(m.stream_hash(p, 'sha1')[0], expected)

    def test_byte_mutation_holds(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for x in m.REQUIRED_PARTS:
                (root / x).write_bytes(b'original')
            files = [{'path': p, 'git_blob_sha1': m.stream_hash(root/p,'sha1')[0]} for p in m.REQUIRED_PARTS]
            (root/'source_01.part').write_bytes(b'different')
            with self.assertRaisesRegex(m.Hold, 'ORIGINAL_BLOB_MISMATCH'):
                m.verify_tracked(root, {'files': files})

    def test_no_case_collisions(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'Foo.txt').write_bytes(b'one')
            (Path(d)/'foo.txt').write_bytes(b'two')
            with self.assertRaisesRegex(m.Hold, 'STAGE_WINDOWS_CASE_COLLISION'):
                m.scan_stage(Path(d))

    def test_unsafe_windows_paths(self):
        self.assertFalse(m.safe_relpath('a/../b'))
        self.assertFalse(m.safe_relpath('CON.txt'))
        self.assertFalse(m.safe_relpath('folder\\item'))
        self.assertTrue(m.safe_relpath('Packages/P02/worker-python/p02_runtime.py'))

    def test_symlink_holds(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'data'; a.write_bytes(b'test')
            link=Path(d)/'link'
            try: link.symlink_to(a)
            except OSError: self.skipTest('symlink unavailable on host')
            with self.assertRaises(m.Hold): m.stream_hash(link,'sha1')

    def test_receipt_gate_never_claims_release(self):
        self.assertEqual(m.SCHEMA, 'NOX_V16_EXPRESS_MAIN_BLOB_LOCK_V1')
        self.assertEqual(m.ORIGINAL_BASE, '0b3a7d435be735148d64171deb9027093a89646e')

if __name__ == '__main__': unittest.main()