"""Static regression for exact-SHA minimal hotpatch. No production actions here."""
import ast
import unittest
from nox_runpod.teacher_mesh.v111.guarded_stream_patch import REMOTE


class GuardedPatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data=REMOTE.split("python3 - <<'PYREMOTE'\n",1)[1].rsplit("\nPYREMOTE",1)[0]
        cls.source=data
        cls.tree=ast.parse(data)

    def test_compiles(self):
        compile(self.source,"<v111-native>", "exec")

    def test_checks_exact_live_sha_and_busy_state(self):
        for part in ("OLD_PROXY=", "OLD_BRIDGE=", "digest(P.read_bytes())!=OLD_PROXY",
                     "digest(M.read_bytes())!=OLD_BRIDGE",
                     "HOLD_ACTIVE_CHAT", "HOLD_STOP", "idle()", "HOLD_LIVE_SOURCE_SHA_DRIFT"):
            self.assertIn(part,self.source)

    def test_protects_auth_and_does_not_touch_s03_or_models(self):
        for part in ("auth_status('/api/nox/chat/stream')!=401",
                     "auth_status('/api/nox/stop')!=401",
                     "supervisorctl','restart','nox-proxy", "rollback(old,meta)"):
            self.assertIn(part,self.source)
        for forbidden in ("optimizer.step(", "torch.save(", "rmtree(", "pip install",
                          "os.system(", "nvidia-smi -pm", "trainer restart"):
            self.assertNotIn(forbidden,self.source)

    def test_only_target_parser_anchor_is_changed(self):
        scope={}
        exec(compile(ast.Module(body=[
            n for n in self.tree.body if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id in ("OLD","NEW") for t in n.targets)
        ],type_ignores=[]),"<v111-constants>","exec"),scope)
        self.assertIn("for choice in obj.get('choices') or []:",scope["OLD"])
        self.assertIn("if not isinstance(delta, dict):",scope["NEW"])
        self.assertIn("if not isinstance(choices, list):",scope["NEW"])
        self.assertIn("text.count(OLD)!=1",self.source)


if __name__=="__main__":
    unittest.main()
