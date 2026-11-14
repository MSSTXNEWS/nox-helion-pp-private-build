"""V110 contract tests; never contacts Vast or accesses private datasets."""
import ast
import unittest
from nox_runpod.teacher_mesh.v110.live_no_write_preflight import REMOTE


class NativeReadOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        marker = "python3 - <<'PYREMOTE'\n"
        assert marker in REMOTE
        cls.code = REMOTE.split(marker, 1)[1].rsplit("\nPYREMOTE", 1)[0]
        cls.tree = ast.parse(cls.code)

    def test_embedded_program_compiles(self):
        compile(self.code, "<nox-v110>", "exec")

    def test_audit_does_not_restart_or_load_models(self):
        for forbidden in ("supervisorctl','restart", "supervisorctl\", \"restart",
                          "torch.load(", "save_pretrained(", "pip install",
                          "model.generate(", "optimizer.step(", "shutil.rmtree("):
            self.assertNotIn(forbidden, self.code)

    def test_no_dialog_text_in_output_contract(self):
        for expected in ("NATIVE_V110_", "NOX_NATIVE_V51_SSH_EXECUTED=true",
                         "NATIVE_READ_ONLY_COMPLETE=true", "owner_lease_verified=False",
                         "restore_verified=False"):
            self.assertIn(expected, self.code)

    def test_fail_closed_idle_contract(self):
        self.assertIn("len(obj) == 6", self.code)
        self.assertIn("all(flag is False for flag in flags)", self.code)
        self.assertIn("idle_proven", self.code)

    def test_training_not_claimed(self):
        self.assertIn("NOX_V110_TRAINING_OR_DEPLOYMENT_PERFORMED=false",
                      __import__("inspect").getsource(
                          __import__("nox_runpod.teacher_mesh.v110.live_no_write_preflight",
                                     fromlist=["main"]).main))


if __name__ == "__main__":
    unittest.main()
