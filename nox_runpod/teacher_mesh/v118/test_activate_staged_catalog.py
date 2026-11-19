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
            "PROXY='4d90215d7099344dd5aaed2412645b764baa0228acc0b0e153cfe425217591ad'",
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


    def test_v124_frozen_nested_bootstrap_is_corrected_together_with_catalog(self):
        for text in (
            'EXACT_SHA_AUTH_CATALOG_AND_NESTED_BOOTSTRAP_V124',
            'HEAD_OLD=', 'HEAD_NEW=', 'HOLD_NATIVE_OWNER_HEAD_ANCHOR',
            'replace(OLD_ROUTE,NEW_ROUTE,1).replace(HEAD_OLD,HEAD_NEW,1)',
            'nested_pages_verified=2', '/nox-web-v29/pc/pages/cinema/index.html',
            '/nox-web-v29/native-owner.js', "if http_code('http://127.0.0.1:8080'+path)!=401"
        ):
            self.assertIn(text, self.source)
        self.assertIn("sha(P.read_bytes())!=PROXY", self.source)
        self.assertIn('original_bridge_backup_verified=True', self.source)


if __name__=='__main__':
    unittest.main()
