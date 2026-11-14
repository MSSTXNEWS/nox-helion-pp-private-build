"""NOX V76 single-run static gates; never touches a live GPU."""
from __future__ import annotations
import ast
import unittest
from nox_runpod.teacher_mesh.v76 import onepass_full_accept as job

class SevenStages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script=job.REMOTE.lstrip('\n')
        start="python3 - <<'PYREMOTE'\n"
        assert script.startswith("set -euo pipefail\n"+start)
        assert script.rstrip().endswith('PYREMOTE')
        body=script.split(start,1)[1].rsplit("\nPYREMOTE",1)[0]
        cls.code=body
        cls.tree=ast.parse(body)
    def test_compiles(self):
        self.assertTrue(self.tree.body)
    def test_onehost_and_no_new_service(self):
        for bad in ('systemctl restart','supervisorctl restart','subprocess.Popen(',
                    'os.kill(','killall','ssh-keygen','DROP TABLE','CREATE DATABASE',
                    'get_peft_model(','LoraConfig(','cuda:0'):
            self.assertNotIn(bad,self.code)
    def test_ram_sqlite_snapshot_and_original_readonly(self):
        self.assertIn("mode=ro",self.code)
        self.assertIn("sqlite3.connect(':memory:')",self.code)
        self.assertIn("source.backup(mirror",self.code)
        self.assertIn("PRAGMA quick_check",self.code)
    def test_git_sha_pinned_and_staged_not_live(self):
        self.assertIn('aa77a7d43bcceee696e2d6ff73d3285d217ab001',self.code)
        self.assertIn("sha_blob(body)!=sources[member.name]",self.code)
        self.assertIn('production_activated=False',self.code)
        self.assertIn("base64.b64decode(BUNDLE_B64",self.code)
        self.assertNotIn("raw.githubusercontent.com",self.code)
        self.assertGreater(len(job._bundle_existing_sources()),100)
    def test_single_model_onehost_preserved(self):
        self.assertIn("'production_main_model_changed':False",self.code)
        self.assertIn("'production_proxy_changed':False",self.code)
        self.assertIn("'native_onehost_replaced':False",self.code)
        self.assertIn("'optimizer_steps':0",self.code)
    def test_seven_gates_disclosed(self):
        for k in ('chat_and_one_model','s03_ram','onehost_native','cold_restore',
                  'forge_weight_change','r60_jobs','quality_and_rollback'):
            self.assertIn("'"+k+"'",self.code)
    def test_no_fake_training_and_queue_ids(self):
        self.assertIn("HOLD_NATIVE_TRAINABLE_STUDENT_OWNER_LEASE_AND_RESTORE",self.code)
        self.assertIn("HOLD_NATIVE_QUEUE_OWNER_READBACK_AND_SIGNED_JOB_RECEIPTS",self.code)
        self.assertIn("'native_task_ids':[]",self.code)
    def test_single_native_runner_one_invocation(self):
        # Transport is existing V72, which enforces a single remote payload
        # after authorization, with key cleanup in its finally block.
        import inspect
        self.assertIn("runner.REMOTE=REMOTE",inspect.getsource(job.main))
if __name__=='__main__':
    unittest.main()
