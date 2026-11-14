"""Tests validate one-service guarded no-loss scheduling, not GPU training."""
import ast
import inspect
import unittest
from nox_runpod.teacher_mesh.v73 import prime_chat_priority as x

class TestNativeP0(unittest.TestCase):
    def test_remote_python_compiles(self):
        start="python3 - <<'PYREMOTE'\n"
        end="\nPYREMOTE"
        self.assertEqual(x.REMOTE.count(start),1)
        ast.parse(x.REMOTE.split(start,1)[1].split(end,1)[0])

    def test_only_two_background_service_identities(self):
        t=x.REMOTE
        self.assertIn("'nox-agent-tuner-t858u','nox_agent_tuner_t858u.py',7",t)
        self.assertIn("'nox-teacher-serve-t811u','teacher_serve_t811u.sh',4",t)
        self.assertIn("proc_identity(pid,script)",t)
        self.assertIn("second['start_ticks']!=first['start_ticks']",t)

    def test_main_chat_and_s03_health_guard(self):
        t=x.REMOTE
        self.assertIn("health(8080)",t)
        self.assertIn("health(8081)",t)
        self.assertIn("model.name=='nox36-mix_final_pref-Q4_K_M.gguf'",t)
        self.assertIn("memory.stat().st_size>500000",t)
        self.assertIn("HOLD_STOP_OR_CHAT_HEALTH",t)
        self.assertIn("HOLD_MAIN_MODEL_OR_S03",t)

    def test_priority_decreases_background_only(self):
        t=x.REMOTE
        self.assertIn("desired=max(old,target_nice)",t)
        self.assertIn("os.setpriority(os.PRIO_PROCESS,pid,desired)",t)
        self.assertIn("'nice_after':second['nice']",t)
        self.assertNotIn("nvidia-smi -pm",t)
        self.assertNotIn("supervisorctl','restart",t)
        self.assertNotIn("os.kill",t)

    def test_fail_closed_and_key_cleanup(self):
        m=inspect.getsource(x.main)
        self.assertIn("conn.cleanup()",m)
        self.assertIn("NOX_V73_CHAT_PRIORITY_NATIVE_VERIFIED",m)
        self.assertIn("NATIVE_PRIORITY_OR_HEALTH_NOT_VERIFIED",m)
        t=x.REMOTE
        self.assertIn("'optimizer_steps':0",t)
        self.assertIn("'training_started':False",t)
        self.assertIn("'gpu_settings_changed':False",t)

    def test_never_mutates_weights_or_private_memory(self):
        t=x.REMOTE
        self.assertNotIn("model.save_pretrained",t)
        self.assertNotIn("torch.save",t)
        self.assertNotIn("sqlite3.connect",t)
        self.assertNotIn("shutil.rmtree",t)
        self.assertNotIn("subprocess.Popen",t)

if __name__=='__main__':
    unittest.main()
