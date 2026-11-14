"""Guard regressions for V112 single token stream; no remote call in tests."""
import ast
import unittest
from nox_runpod.teacher_mesh.v112.native_inference_smoke import REMOTE


class StreamSmokeSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script=REMOTE.split("python3 - <<'PYREMOTE'\n",1)[1].rsplit("\nPYREMOTE",1)[0]
        cls.tree=ast.parse(cls.script)

    def test_compiles(self):
        compile(self.script,"<v112-native>","exec")

    def test_single_student_and_bounded_request(self):
        for marker in ("len(models)!=1","check_idle()", "stopped()",
                       "'max_tokens':16","'stream':True","'temperature':0",
                       "NATIVE_V112_RESULT", "first_token_ms", "done_frame"):
            self.assertIn(marker,self.script)

    def test_no_server_restarts_or_data_writes(self):
        for forbidden in ("supervisorctl", "torch.save(", "optimizer.step(",
                          "open('w')", "pip install", "save_pretrained(",
                          "s03_memory.remember", "subprocess.run"):
            self.assertNotIn(forbidden,self.script)

    def test_no_content_egress(self):
        self.assertNotIn("print(text)",self.script)
        self.assertNotIn("print(model)",self.script)
        self.assertIn("answer_characters=len(text)",self.script)
        self.assertIn("browser_auth_tested':False",self.script)


if __name__=="__main__":
    unittest.main()
