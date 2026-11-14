"""V125 native installer safety contract; never connects to Vast in tests."""
import ast
import unittest
from nox_runpod.teacher_mesh.v125.install_fact_route import REMOTE


class NativeFactInstallSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script=REMOTE.split("/root/nox/venv/bin/python - <<'PYREMOTE'\n",1)[1].rsplit("\nPYREMOTE",1)[0]
        cls.tree=ast.parse(cls.script)

    def test_native_script_compiles(self):
        compile(self.script,"<v125-native-proxy>", "exec")

    def test_current_exact_native_hash_and_no_duplicate_route(self):
        for needle in ("OLD_PROXY=", "OLD_BRIDGE=", "MODULE_SHA='___MODULE_SHA___'",
                       "HOLD_CONCURRENT_PROXY_SOURCE_SHA",
                       "HOLD_BRIDGE_OR_STAGED_FACT_SHA",
                       "HOLD_REGISTRATION_OR_AUTH_ANCHOR",
                       "HOLD_CONCURRENT_CHANGE_BEFORE_WRITE"):
            self.assertIn(needle,self.script)

    def test_original_s03_backup_is_verified_before_restart(self):
        for needle in ("source.backup(dest", "PRAGMA quick_check",
                       "HOLD_S03_BACKUP_INTEGRITY", "HOLD_S03_POSTBACKUP_DISK_FLOOR",
                       "HOLD_PROXY_BACKUP_NOT_VERIFIED", "s03_backup_sha",
                       "rollback(previous,meta,new_sha)"):
            self.assertIn(needle,self.script)

    def test_before_route_404_is_not_a_false_failure_or_an_auth_bypass(self):
        self.assertIn("pre_http not in (401,404)",self.script)
        self.assertIn("HOLD_ANONYMOUS_FACT_ROUTE_PRECHECK",self.script)
        self.assertIn("if code_for('/api/nox/memory/facts','POST',{})[0]!=401",
                      self.script)

    def test_real_authorization_and_no_fake_pass(self):
        for needle in ("_read_chat_password()", "cookiejar.CookieJar()",
                       "'/chat/login'", "'/chat/session'", "'/chat/logout'",
                       "'/api/nox/memory/facts','POST',{}",
                       "HOLD_ANONYMOUS_FACT_AUTH",
                       "HOLD_FACT_ROUTE_OWNER_JSON_CONTRACT",
                       "new_actual_s03_fact_tested=False"):
            self.assertIn(needle,self.script)
        for disallowed in ("optimizer.step(", "torch.save(", "save_pretrained(",
                           "rm -rf", "shutil.rmtree(", "print(password)",
                           "print(jar)", "echo $NOX2"):
            self.assertNotIn(disallowed,self.script)

    def test_no_unbounded_retry_or_gpu_restarts(self):
        self.assertIn("['supervisorctl','restart','nox-proxy']",self.script)
        self.assertNotIn("supervisorctl','restart','nox-train",self.script)
        self.assertIn("if patched:",self.script)
        self.assertIn("rollback(previous,meta,new_sha)",self.script)


if __name__=='__main__':
    unittest.main()
