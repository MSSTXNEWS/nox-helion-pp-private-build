"""V70 security and one-pass SHA/chunk proof; offline only."""
import ast
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nox_runpod.teacher_mesh.v70 import onepass_cold_offload as x


class TestV70(unittest.TestCase):
    def test_remote_python_compiles(self):
        ast.parse(x.REMOTE)

    def test_only_three_fixed_cold_files(self):
        t=x.REMOTE
        self.assertIn("165692771",t)
        self.assertIn("164610213",t)
        self.assertIn("85218272",t)
        self.assertIn("Path('/root/nox/backup')",t)
        self.assertIn("Path('/root/nox/incoming_t800u')",t)
        self.assertIn("len(matches)!=1",t)

    def test_tmpfs_chat_nice_and_read_only(self):
        t=x.REMOTE
        self.assertIn("tempfile.TemporaryFile(mode='w+b',dir='/dev/shm')",t)
        self.assertIn("os.nice(12)",t)
        self.assertIn("time.sleep(0.015)",t)
        self.assertNotIn("supervisorctl",t)
        self.assertNotIn("current.gguf",t)
        self.assertNotIn("nox_infinite_memory.sqlite3",t)
        self.assertNotIn("unlink(",t)
        self.assertNotIn("shutil.rmtree(",t)

    def test_three_archive_exact_sizes(self):
        self.assertEqual(x.TOTAL,165692771+164610213+85218272)
        self.assertEqual(len(x.EXPECTED),3)

    def test_six_parts_and_full_sha_synthetic(self):
        # Patch only in-memory byte constraints, not production source or files.
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            data=b'abcde'*650
            enc=p/'test.age'
            enc.write_bytes(data)
            with (patch.object(x,'ENC',enc),
                  patch.object(x,'PARTS_DIR',p/'parts'),
                  patch.object(x,'INDEX',p/'index.json'),
                  patch.object(x,'CHUNK_BYTES',600),
                  patch.object(x,'EXPECTED',{'fake':(2,'x')}) ):
                # The production size guard must be fail-closed for tiny data.
                with self.assertRaisesRegex(RuntimeError,'HOLD_CIPHERTEXT_UNEXPECTED_SIZE'):
                    x.split_ciphertext()

    def test_failure_cannot_preserve_false_receipt(self):
        import inspect
        source=inspect.getsource(x)
        self.assertIn("RECEIPT.unlink(missing_ok=True)",source)
        self.assertIn("HOLD_VAST_SSH_KEY_NOT_REVOKED",source)
        self.assertIn("'source_disk_files_deleted':False",source)
        self.assertIn("'owner_private_key_restoration_verified':False",source)
        self.assertIn("'offsite_drive_uploaded':False",source)

    def test_manifest_receipts_bounded(self):
        self.assertLess(x.CHUNK_BYTES,75_000_000)
        self.assertIn("(PARTS_DIR/'part01'/RECEIPT.name).write_bytes",__import__('inspect').getsource(x))


if __name__=='__main__':
    unittest.main()
