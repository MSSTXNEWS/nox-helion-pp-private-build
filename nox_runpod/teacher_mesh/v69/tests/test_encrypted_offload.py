"""Source-only guards for native offsite RAM staging and encrypted owner copy."""
import ast
import unittest
from nox_runpod.teacher_mesh.v69 import encrypted_single_zip_offload as x

class TestEncryptedOffload(unittest.TestCase):
    def test_remote_python_syntax(self):
        ast.parse(x.REMOTE)

    def test_archive_is_exact_and_never_main_model(self):
        s=x.REMOTE
        for marker in ("Path('/root/nox/incoming_t800u')",x.SOURCE_SHA,
                       "size=85218466","len(candidates)!=1",
                       "after.st_mtime_ns!=meta.st_mtime_ns"):
            self.assertIn(marker,s)

    def test_volatile_ram_and_chat_throttle(self):
        s=x.REMOTE
        for marker in ("tempfile.TemporaryFile(mode='w+b',dir='/dev/shm')",
                       "vfs.f_bavail*vfs.f_frsize < size*3",
                       "os.nice(10)", "time.sleep(0.025)"):
            self.assertIn(marker,s)

    def test_no_persistent_model_or_s03_mutation(self):
        s=x.REMOTE
        for banned in ("unlink(","os.replace(","supervisorctl","current.gguf",
                       "nox_infinite_memory.sqlite3"):
            self.assertNotIn(banned,s)

    def test_encrypt_with_owner_and_independent_decrypt(self):
        import inspect
        src=inspect.getsource(x.run)
        for marker in ("existing_owner_recipient","'age','-R'",
                       "test_decrypt","if length!=SOURCE_BYTES or digest!=SOURCE_SHA",
                       "v60.conn.cleanup()","'remote_source_deleted':False",
                       "'active_prime_model_or_s03_changed':False"):
            self.assertIn(marker,src)

    def test_failure_removes_unverified_outputs(self):
        import inspect
        src=inspect.getsource(x)
        self.assertIn("OUTPUT.unlink(missing_ok=True)",src)
        self.assertIn("RECEIPT.unlink(missing_ok=True)",src)

if __name__=="__main__":unittest.main()
