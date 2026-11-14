"""Contract for physical owner-scoped STOP QA. No Vast calls in these tests."""
import ast
import unittest
from nox_runpod.teacher_mesh.v122.scoped_stop_native_e2e import REMOTE


class ScopedStopSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        marker="/root/nox/venv/bin/python - <<'PYREMOTE'\n"
        assert marker in REMOTE
        cls.code=REMOTE.split(marker,1)[1].rsplit("\nPYREMOTE",1)[0]
        cls.tree=ast.parse(cls.code)

    def test_real_native_source_compiles(self):
        compile(self.code,"<nox-v122-native>",'exec')

    def test_exact_live_identity_and_p0_gate(self):
        for s in ("PROXY_SHA = '4d90215d7099344dd5aaed2412645b764baa0228acc0b0e153cfe425217591ad'",
                  "BRIDGE_SHA = '066ed91555a9a6251420b5897a040eda13a03b3d6c2d85b936e384c5f4113cd4'",
                  "HOLD_LIVE_SHA_DRIFT", "HOLD_OWNER_CHAT_BUSY",
                  "if stopped():", "len(rows)!=6"):
            self.assertIn(s,self.code)

    def test_fails_closed_on_cross_cookie_stop(self):
        for s in ("scope(jar_a)==scope(jar_b)",
                  "with post(owner_b,'/api/nox/stop',{})",
                  "if cross_code!=409", "with post(owner_a,'/api/nox/stop',{})",
                  "response.get('gpu_stop_verified') is not False",
                  "STREAM_STOP_REQUESTED", "HOLD_STOP_SESSION_ISOLATION"):
            self.assertIn(s,self.code)

    def test_only_synthetic_prompt_and_no_private_data_export(self):
        self.assertIn("marker='noxv122stop_'+secrets.token_hex(6)",self.code)
        self.assertIn("'message':'[QA '+marker+'] Перечисли числа",self.code)
        self.assertIn("s03_cancelled_exchange_absent=True",self.code)
        self.assertIn("PRAGMA quick_check",self.code)
        for bad in ("print(password)", "print(jar_a)", "print(jar_b)",
                    "print(answer)", "print(line)", "shutil.rmtree(",
                    "supervisorctl", "killall ", "torch.save(",
                    "optimizer.step(", "import requests", "pip install"):
            self.assertNotIn(bad,self.code)

    def test_never_claims_gpu_compute_cancellation(self):
        self.assertIn("'backend_gpu_stop_verified':False",self.code)
        self.assertIn("'model_weights_changed':False",self.code)
        self.assertIn("'proxy_restart':False",self.code)


if __name__=='__main__':
    unittest.main()
