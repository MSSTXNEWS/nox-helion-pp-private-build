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
            "SELECT id,segment,sha256,meta,text FROM s03_items WHERE provenance=?",
            "PRAGMA quick_check", "HOLD_FACT_NOT_FOUND_IN_EXISTING_HISTORY",
            "HOLD_NATIVE_FACT_DEDUPLICATION", "'M2'",
            "EXISTING_OWNER_FACT_TO_S03_HISTORY_PASS"):
            self.assertIn(value,self.src)

    def test_s03_internal_digest_is_not_assumed_equal_to_source_digest(self):
        self.assertIn("internal_sha=rows[0][2]",self.src)
        self.assertIn("source_meta.get('source_sha256')!=content_sha",self.src)
        self.assertIn("x.get('source_sha256')==internal_sha",self.src)
        self.assertNotIn("x.get('source_sha256')==content_sha",self.src)

    def test_acceptance_reuses_existing_qa_fact_without_polluting_s03(self):
        self.assertIn("reused_qa=previous is not None",self.src)
        self.assertIn("if before_count!=int(reused_qa)",self.src)
        self.assertIn("reused_existing_synthetic_fact=reused_qa",self.src)
        self.assertIn("HOLD_PREVIOUS_QA_SOURCE_META",self.src)

    def test_vast_429_backoff_never_retries_post_writes(self):
        import inspect
        from nox_runpod.teacher_mesh.v125.owner_fact_native_e2e import transport
        source=inspect.getsource(transport)
        self.assertIn('method!="GET"',source)
        self.assertIn('"HOLD_VAST_API_HTTP_429"',source)
        self.assertIn('(10,20,40)',source)

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
