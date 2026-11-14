"""Regression of native V29 bridge registration order; no Vast writes here."""
import ast
import unittest

from nox_runpod.teacher_mesh.v106.native_install_v29_bridge import REMOTE_TEMPLATE

class RegistrationOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        start="python3 - <<'PYREMOTE'\n"
        code=REMOTE_TEMPLATE.lstrip("\n")
        assert start in code
        cls.native=code.split(start,1)[1].rsplit("\nPYREMOTE",1)[0]
        cls.tree=ast.parse(cls.native)

    def test_embedded_source_compiles(self):
        compile(self.native,"<nox-v108-v106>","exec")

    def test_handler_must_exist_before_binding(self):
        self.assertIn("HOLD_NATIVE_OWNER_HANDLER_NOT_DEFINED",self.native)
        self.assertIn("x.name=='_proxy_completion'",self.native)

    def test_defers_all_registration_until_end_of_module(self):
        self.assertIn("lines.append('register_native_v29_chat(app, globals())",self.native)
        self.assertNotIn("lines.insert(where,",self.native)
        self.assertNotIn("where=min(d.lineno",self.native)

    def test_synthetic_real_import_order(self):
        source='''app = object()
def _session_ok(request): return True
def _unauthorized(): return None
async def chat_api(request): return None
async def _proxy_completion(payload): return payload
'''
        lines=source.splitlines(keepends=True)
        if lines and not lines[-1].endswith("\n"):lines.append("\n")
        lines.append("\nfrom nox_v29_chat_bridge import register_native_v29_chat\n")
        lines.append("register_native_v29_chat(app, globals())\n")
        result="".join(lines)
        parsed=ast.parse(result)
        names=[n.name for n in parsed.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
        self.assertIn("_proxy_completion",names)
        call=[n.lineno for n in ast.walk(parsed)
              if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and
                 n.func.id=="register_native_v29_chat"]
        fn=[n.end_lineno for n in parsed.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
            and n.name=="_proxy_completion"]
        self.assertEqual(len(call),1)
        self.assertGreater(call[0],fn[0])

    def test_native_stop_and_security_unchanged(self):
        for marker in ("HOLD_SOURCE_SHA_CHANGED","HOLD_AUTH_NOT_ENFORCED",
           "HOLD_ACTIVE_CHAT_OR_HEALTH","HOLD_BACKUP_CONFLICT",
           "HOLD_REGISTERED_ROUTES_NOT_VERIFIED","revert(original,meta)",
           "supervisorctl','restart','nox-proxy"):
            self.assertIn(marker,self.native)
        self.assertNotIn("supervisorctl','stop'"," ".join(self.native.splitlines()))

if __name__=="__main__":
    unittest.main()
