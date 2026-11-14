"""V125 source-only controls for physical fact SAVE→S03→V120 readback.

No credentials, network calls or runtime service actions in these tests.
"""
import ast
import unittest
from nox_runpod.teacher_mesh.v125.owner_fact_native_e2e import REMOTE


class LiveFactContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src=REMOTE.split("<<'PYREMOTE'\n",1)[1].rsplit('\nPYREMOTE',1)[0]
        cls.tree=ast.parse(cls.src)

    def test_embedded_source_compiles(self):
        compile(self.src,"<V125_REAL_OWNER_FACT>","exec")

    def test_one_existing_no_loss_s03_and_owner_login(self):
        for value in (
            "HOLD_V125_LIVE_PROXY_SHA_DRIFT",
            "HOLD_NATIVE_SOURCE_BACKUP_SHA",
            "_read_chat_password()", "cookiejar.CookieJar()",
            "'/chat/login'", "'/chat/session'", "'/chat/logout'",
            "HOLD_STOP_BEFORE_FACT_POST", "HOLD_STOP_AFTER_FACT"):
            self.assertIn(value,self.src)

    def test_real_original_s03_row_and_history_not_just_json_200(self):
        for value in (
            "'/api/nox/memory/facts','POST',payload",
            "'/api/ui/memory/facts/history?fact_key='",
            "SELECT id,segment,sha256 FROM s03_items WHERE provenance=?",
            "PRAGMA quick_check", "HOLD_FACT_NOT_FOUND_IN_EXISTING_HISTORY",
            "HOLD_NATIVE_FACT_DEDUPLICATION", "'M2'",
            "EXISTING_OWNER_FACT_TO_S03_HISTORY_PASS"):
            self.assertIn(value,self.src)

    def test_no_fake_training_and_no_private_records_leak(self):
        for value in ("'model_weights_changed':False",
                      "'services_restarted':False",
                      "'private_records_exported':False"):
            self.assertIn(value,self.src)
        for forbidden in ("print(password)", "print(text)", "print(payload)",
                          "print(jar)", "print(hist)", "os.system(",
                          "subprocess.run(", "supervisorctl", "killall",
                          "torch.save(", "optimizer.step(", "pip install"):
            self.assertNotIn(forbidden,self.src)


if __name__=='__main__':
    unittest.main()
