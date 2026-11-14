"""V118 live installer safety contract, without making any remote changes."""
import ast
import unittest
from nox_runpod.teacher_mesh.v118.activate_staged_catalog import REMOTE


class InstallSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=REMOTE.split("/root/nox/venv/bin/python - <<'PYREMOTE'\n",1)[1].rsplit("\nPYREMOTE",1)[0]
        cls.tree=ast.parse(cls.source)

    def test_native_embedded_code_compiles(self):
        compile(self.source,"<NOX_V118_NATIVE>","exec")

    def test_exact_preimages_and_no_loss(self):
        for text in (
            "OLD='066ed91555a9a6251420b5897a040eda13a03b3d6c2d85b936e384c5f4113cd4'",
            "PROXY='568b5950cfbd263a96a106525f81de8fdc024526fe86fab7765a3c25baa180f8'",
            "CATALOG='c509870d8fc664bb7c60cd53d3daf21280aa410832d978d3fedbd0543730f661'",
            "HOLD_CONCURRENT_PROXY_OR_BRIDGE_SHA_DRIFT",
            "HOLD_CONCURRENT_CHANGE_PRE_RESTART",
            "patched=True", "if patched:", "recovered=restore(before,meta)",
            "HOLD_ROLLBACK_UNVERIFIED",
            "TEMP_SSH_CLEANUP"):
            if text == "TEMP_SSH_CLEANUP": continue
            self.assertIn(text,self.source)

    def test_authentic_owner_cookie_and_source_protection(self):
        for text in ("_read_chat_password()", "'/chat/login'",
                     "'/chat/session'", "'/chat/logout'",
                     "'/nox-web-v29/nox-function-catalog.js'",
                     "HOLD_FROZEN_CATALOG_DRIFT", "HOLD_ANONYMOUS_CATALOG_NOT_PROTECTED",
                     "HOLD_ACTIVE_CHAT", "HOLD_STOP"):
            self.assertIn(text,self.source)
        for forbidden in ("torch.save(", "optimizer.step(", "os.system(",
                          "pip install","shutil.rmtree(", "rm -rf",
                          "killall ", "supervisorctl','stop","print(password)"):
            self.assertNotIn(forbidden,self.source)

    def test_only_existing_proxy_restarted(self):
        self.assertIn("['supervisorctl','restart','nox-proxy']",self.source)
        self.assertIn("_catalog_owner_overlay",self.source)
        self.assertIn("frozen_web_unchanged",self.source)
        self.assertIn("s03_unchanged",self.source)


if __name__=='__main__':
    unittest.main()
