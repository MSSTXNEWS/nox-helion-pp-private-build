"""Regression for V118 remote cookiejar namespace shadowing. No native calls."""
import ast
import unittest
from nox_runpod.teacher_mesh.v118.owner_nested_static_hotfix import REMOTE

class CookieJarShadowTests(unittest.TestCase):
    def test_remote_cookiejar_namespace_is_not_overwritten_by_http_helper(self):
        source = REMOTE.split("<<'PYREMOTE'", 1)[1].split('\\nPYREMOTE', 1)[0]
        tree = ast.parse(source)
        imports = [n for n in tree.body if isinstance(n, ast.Import)]
        self.assertTrue(any(any(a.name == 'http.cookiejar' and a.asname == 'cookiejar'
                                for a in node.names) for node in imports))
        self.assertTrue(any(isinstance(n, ast.FunctionDef) and n.name == 'http'
                            for n in tree.body))
        self.assertIn('jar=cookiejar.CookieJar()', source)
        self.assertNotIn('jar=http.cookiejar.CookieJar()', source)

if __name__ == '__main__':
    unittest.main()
