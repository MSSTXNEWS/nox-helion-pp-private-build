"""Offline tests for one-shot NOX V63 Downloads CLI PATH repair."""
import ast
import unittest
import os
from unittest.mock import patch
from nox_runpod.teacher_mesh.v63 import native_once,repair_download_hf_path

def py_script():
    value=repair_download_hf_path.REMOTE
    prefix="python3 - <<'PYREMOTE'\n"
    assert value.count(prefix)==1
    return value.split(prefix,1)[1].split("\nPYREMOTE",1)[0]

class TestNativeWriteGate(unittest.TestCase):
    def test_remote_syntax(self):
        ast.parse(py_script())

    def test_no_supervisor_start_or_model_download_invoked(self):
        text=py_script()
        self.assertIn("NAME='nox-downloads-t802u'",text)
        self.assertNotIn("['supervisorctl','start'",text)
        self.assertNotIn("['supervisorctl','restart'",text)
        self.assertIn("download_started=False",text)

    def test_exact_original_sha_and_checkpoint_reserve(self):
        text=py_script()
        self.assertIn("ed83da5dbf9692166ef2a1f26c37d4402e16f0cf0f5ce6aabae06a0884f07267",text)
        self.assertIn("16_000_000_000",text)
        self.assertIn("HOLD_DISK_FLOOR",text)

    def test_atomic_backup_readback_and_rollback(self):
        text=py_script()
        for req in ("os.replace(tmp,file)","os.fsync(fp.fileno())",
                    "HOLD_BACKUP_SHA_MISMATCH","backup_sha256",
                    "rolled_back=","NATIVE_HF_PATH_PATCH_VERIFIED"):
            self.assertIn(req,text)

    def test_separate_native_ack_not_fake_readonly(self):
        self.assertIn("NATIVE_PATCH_COMPLETE=true",repair_download_hf_path.REMOTE)
        self.assertNotIn("NATIVE_READ_ONLY_COMPLETE=true",repair_download_hf_path.REMOTE)
        self.assertEqual(native_once.native_once.__defaults__,("NATIVE_PATCH_COMPLETE=true",))

    def test_untrusted_payload_cannot_run(self):
        x=native_once.native_once("echo bad",required_marker="NATIVE_PATCH_COMPLETE=true")
        self.assertEqual(x["state"],"HOLD_UNTRUSTED_REMOTE_SOURCE")
        self.assertEqual(x["write_attempts"],0)

    def test_unexpected_ack_not_allowed(self):
        x=native_once.native_once(repair_download_hf_path.REMOTE,required_marker="fake-success")
        self.assertEqual(x["state"],"HOLD_ACK_PROTOCOL")
        self.assertEqual(x["write_attempts"],0)

    def test_checked_in_source_is_accepted_before_any_vast_api(self):
        with patch.dict(os.environ,{"NOX2":""}):
            x=native_once.native_once(repair_download_hf_path.REMOTE)
        self.assertEqual(x["state"],"HOLD_NOX2")
        self.assertEqual(x["write_attempts"],0)

    def test_production_result_fail_closed(self):
        self.assertTrue("NOX_V63_DOWNLOAD_HF_INTEGRATION_VERIFIED=" in repair_download_hf_path.main.__code__.co_consts)
        self.assertTrue("NATIVE_HF_PATH_PATCH_VERIFIED" in repr(repair_download_hf_path.main.__code__.co_consts))

if __name__=="__main__":unittest.main()
