"""V118 regression: native HTTP helper must not mask cookiejar module.

Read-only source test. Does not import chat_proxy or access Vast.
"""
import ast
import http.cookiejar
import unittest
from nox_runpod.teacher_mesh.v118.owner_nested_static_hotfix import REMOTE


class CookieJarCollision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=REMOTE.split(" - <<'PYREMOTE'\n",1)[1].rsplit("\nPYREMOTE",1)[0]
        cls.ast=ast.parse(cls.source)

    def test_native_script_compiles(self):
        compile(self.source,"<NOX_V118_NATIVE>","exec")

    def test_import_is_not_overwritten_by_http_helper(self):
        imports=[node for node in self.ast.body if isinstance(node,ast.Import)
                 for alias in node.names if alias.name=='http.cookiejar']
        self.assertEqual(len(imports),1)
        self.assertEqual(imports[0].names[0].asname,'_nox_cookiejar')
        self.assertTrue(any(isinstance(n,ast.FunctionDef) and n.name=='http'
                            for n in self.ast.body))
        self.assertIn('jar=_nox_cookiejar.CookieJar()',self.source)
        self.assertNotIn('jar=http.cookiejar.CookieJar()',self.source)

    def test_helper_name_and_cookiejar_can_coexist(self):
        scope={}
        exec("import http.cookiejar as _nox_cookiejar\n"
             "def http(url,opener=None): return 401\n"
             "jar=_nox_cookiejar.CookieJar()",scope)
        self.assertIsInstance(scope['jar'],http.cookiejar.CookieJar)
        self.assertEqual(scope['http']('/test'),401)

    def test_live_v118_requires_manual_admission(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[3]
        for name in ("nox-v118-nested-owner-static.yml",
                     "nox-v118-real-read-surfaces.yml"):
            with self.subTest(workflow=name):
                workflow=(root/'.github'/'workflows'/name).read_text()
                self.assertIn("inputs.allow_native == 'YES'",workflow)
                self.assertIn("github.event_name == 'workflow_dispatch'",workflow)
                self.assertIn("default: 'NO'",workflow)
                self.assertNotIn("if: ${{ github.actor == 'MSSTXNEWS' }}",workflow)

    def test_no_unsafe_restart_added(self):
        self.assertIn("HOLD_ROLLED_BACK",self.source)
        self.assertIn("if touched and original is not None",self.source)


if __name__=='__main__':
    unittest.main()
