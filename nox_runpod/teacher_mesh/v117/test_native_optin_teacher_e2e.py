"""V117 local contract tests; no remote calls or credential access."""
import ast
import unittest
from nox_runpod.teacher_mesh.v117.native_optin_teacher_e2e import REMOTE


class OwnerTeacherE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code=REMOTE.split(" - <<'PYREMOTE'\n",1)[1].rsplit("\nPYREMOTE",1)[0]
        cls.tree=ast.parse(cls.code)

    def test_compiles(self):
        compile(self.code,"<V117-remote>","exec")

    def test_exact_public_optin_and_teacher_proof(self):
        for s in ("prompt='@учитель: 17*19'",
                  "HOLD_NATIVE_TEACHER_HINT_NOT_OBSERVED",
                  "nox_v113_verified_local_teacher_hint_applied=1",
                  "teacher_log.stat().st_size",
                  "V117_OWNER_OPTIN_TEACHER_NOX_S03_PASS"):
            self.assertIn(s,self.code)

    def test_existing_official_owner_only_and_s03(self):
        for s in ("chat_proxy._read_chat_password()",
                  "'/chat/login'", "'/chat/session'",
                  "'/api/nox/chat/stream'","'s03_integrated'",
                  "'/api/ui/memory/dialogs/history?dialog_id='",
                  "HOLD_OWNER_S03_DIALOG_READBACK",
                  "HOLD_STOP_FLAG", "HOLD_NATIVE_BUILD_SHA_CHANGED"):
            self.assertIn(s,self.code)

    def test_safe_no_login_export_or_service_replacement(self):
        for s in ("'/chat/logout'", "NATIVE_V117_PRIVATE_OWNER_AUTH_EXPORTED=false",
                  "user_private_data_exported=False","model_weights_changed=False"):
            self.assertIn(s,self.code)
        for bad in ("supervisorctl", "pip install", "torch.save(", "optimizer.step(",
                    "print(password)", "print(answer)", "print(log_tail)",
                    "save_pretrained(", "shutil.rmtree("):
            self.assertNotIn(bad,self.code)


if __name__=="__main__":
    unittest.main()
