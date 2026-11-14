"""Fail-closed source contract for native one-file downloader PATH repair."""
import ast
import unittest
from nox_runpod.teacher_mesh.v64 import download_path_patch as mod

def extract():
    start="python3 - <<'PYREMOTE'\n"
    end="\nPYREMOTE"
    assert mod.REMOTE.count(start)==1 and mod.REMOTE.count(end)==1
    return mod.REMOTE.split(start,1)[1].split(end,1)[0]

class TestDownloadPathRepair(unittest.TestCase):
    def test_remote_python_compiles(self):
        ast.parse(extract())
    def test_fixed_sha_preimage(self):
        s=extract()
        self.assertIn("ed83da5dbf9692166ef2a1f26c37d4402e16f0cf0f5ce6aabae06a0884f07267",s)
        self.assertIn("6f78469d6e8f41698710b947f213bfa1f4934ed2d3aabf8d728807c03899c152",s)
    def test_only_expected_service_no_supervisor_start(self):
        s=extract()
        self.assertIn("TARGET='nox-downloads-t802u'",s)
        self.assertIn("supervisor_state()!='STOPPED'",s)
        self.assertNotIn("['supervisorctl','start'",s)
        self.assertNotIn("['supervisorctl','restart'",s)
    def test_one_atomic_patch_and_rollback(self):
        s=extract()
        self.assertIn("os.replace(tmp,script)",s)
        self.assertIn("os.replace(name,script)",s)
        self.assertIn("HOLD_PATCH_ROLLBACK",s)
        self.assertIn("sha(backup.read_bytes())!=EXPECTED_DOWNLOADER_SHA",s)
        self.assertIn("fcntl.flock",s)
    def test_hf_existing_venv_only(self):
        s=extract()
        self.assertIn("hf=bin_dir/'hf'",s)
        self.assertIn("os.access(hf,os.X_OK)",s)
        self.assertIn("HOLD_NO_EXISTING_HF_CLI",s)
        self.assertNotIn("pip install",s)
        self.assertNotIn("hf download",s)
    def test_stop_and_disk_gate(self):
        s=extract()
        self.assertIn("HOLD_GLOBAL_STOP",s)
        self.assertIn("HOLD_STOP_CHANGED",s)
        self.assertIn("16_000_000_000",s)
        self.assertIn("bash','-n'",s)
    def test_receipt_fail_closed(self):
        s=mod.main.__code__
        self.assertTrue(any(isinstance(x,str) and "HOLD_NOT_ACCEPTED" in x for x in s.co_consts))
        self.assertIn("NATIVE_DOWNLOAD_CLI_PATH_PATCHED",repr(s.co_consts))
if __name__=="__main__":unittest.main()
