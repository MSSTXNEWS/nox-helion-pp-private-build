"""Source regressions for original V51 owner status read-only probe."""
import unittest
from pathlib import Path
from nox_runpod.teacher_mesh.v112.owner_status_readonly import REMOTE,native_status_evidence

ROOT=Path(__file__).resolve().parents[4]
class OwnerReadOnlyStatusTests(unittest.TestCase):
    def test_only_manual_owner_v51_session(self):
        wf=(ROOT/".github/workflows/nox-v51-ephemeral-ssh-native.yml").read_text()
        self.assertIn("workflow_dispatch:",wf)
        self.assertNotIn("  push:",wf)
        self.assertIn("inputs.allow_native == 'YES'",wf)
        self.assertIn("github.actor == 'MSSTXNEWS'",wf)
        self.assertIn("owner_status_readonly as status",wf)
        self.assertIn("ssh.REMOTE=ssh.REMOTE+\"\\n\"+bench.REMOTE+\"\\n\"+status.REMOTE",wf)
        self.assertIn("ONEHOST_NATIVE_QUEUE_READBACK=HOLD_NOT_QUERIED",wf)
    def test_native_script_reads_existing_owner_routes_only(self):
        self.assertIn('/api/nox/status',REMOTE)
        self.assertIn('/api/ui/memory/dialogs/status',REMOTE)
        self.assertIn('/chat/session',REMOTE)
        self.assertNotIn('/api/nox/stop',REMOTE)
        self.assertNotIn('/v1/chat/completions',REMOTE)
        self.assertNotIn('queue_enqueue(',REMOTE)
        self.assertNotIn('sqlite3.connect(',REMOTE)
        self.assertNotIn('os.remove(',REMOTE)
    def test_no_fake_queue_or_s03_event(self):
        valid={"state":"AUTH_OWNER_S03_STATUS_READY","native_p02_bound":True,
               "original_s03_schema_ready":True,"original_dialogs_ready":True,
               "original_s03_backing_store":True,
               "native_queue_jobs_verified":False,"signed_s03_task_receipts_verified":False}
        self.assertTrue(native_status_evidence(["NATIVE_V112_OWNER_STATUS="+__import__('json').dumps(valid)]))
        for field in ("native_queue_jobs_verified","signed_s03_task_receipts_verified"):
            wrong=dict(valid);wrong[field]=True
            self.assertFalse(native_status_evidence(["NATIVE_V112_OWNER_STATUS="+__import__('json').dumps(wrong)]))
        self.assertFalse(native_status_evidence([]))
        self.assertFalse(native_status_evidence(["NATIVE_V112_OWNER_STATUS={bad json"]))
        self.assertFalse(native_status_evidence(["NATIVE_V112_OWNER_STATUS="+__import__('json').dumps(valid)]*2))
        self.assertFalse(native_status_evidence(['NATIVE_V112_OWNER_STATUS={"state":"HOLD_OWNER_LOGIN"}']))
if __name__=="__main__":unittest.main()
