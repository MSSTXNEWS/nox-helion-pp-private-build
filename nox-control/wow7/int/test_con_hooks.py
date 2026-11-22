"""CON-05/06: патч con_bridge.diff применяется к оригиналу моста; активность чата видна inner_loop; «Я сейчас» называет живую модель."""
import unittest, sys, os, shutil, subprocess, tempfile, importlib, time
HERE = os.path.dirname(os.path.abspath(__file__))
WOW = os.environ.get("NOX_WOW_SRC", "/home/claude/nox_wow")
ORIG = os.environ.get("NOX_BRIDGE_ORIG", "/home/claude/msstxnews/nox-helion-pp-private-build/nox-control/bridge/nox_bridge.py")
for p in (os.path.join(WOW, "CON"), HERE):
    sys.path.insert(0, p)
from nox_inner_loop import make_chat_busy
from nox_workspace import Workspace
from nox_self_model_live import LiveSelfModel
import con_hooks as CH


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        shutil.copy(ORIG, os.path.join(cls.d, "nox_bridge.py"))
        r = subprocess.run(["patch", "-p3", "-i", os.path.join(HERE, "con_bridge.diff"), "-d", cls.d], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        shutil.copy(os.path.join(HERE, "con_hooks.py"), cls.d)
        cls.act = os.path.join(cls.d, "chat_activity")
        os.environ["NOX_CHAT_ACTIVITY"] = cls.act
        sys.path.insert(0, cls.d)
        sys.modules.pop("nox_bridge", None)
        cls.B = importlib.import_module("nox_bridge")
        cls.B.STATE = os.path.join(cls.d, "affect.json")
        cls.B.body_line = lambda: "GPU0 10% 900/16311МБ 40°C; RAM свободно 600 ГБ"

    def setUp(self):
        self.now = [1000.0]
        probe = lambda: {"up": True, "model": "Qwen3-4B", "n_ctx": 8192, "raw": ""}
        sm = LiveSelfModel(path=os.path.join(self.d, "sl.json"), probes={"fast": probe})
        CH.reset_core(Workspace(), sm)

    def test_patch_applied(self):
        self.assertIs(self.B.CH, CH)

    def test_mark_chat_makes_busy_then_expires(self):
        if os.path.exists(self.act): os.remove(self.act)
        t0 = time.time(); clock = [t0]
        busy = make_chat_busy(activity_file=self.act, clock=lambda: clock[0], get=lambda *a: [])
        self.assertFalse(busy())
        self.assertTrue(CH.mark_chat())
        clock[0] = os.path.getmtime(self.act) + 5; self.assertTrue(busy())
        clock[0] = os.path.getmtime(self.act) + 121; self.assertFalse(busy())

    def test_endpoint_marks_activity(self):
        from fastapi.testclient import TestClient
        async def fake_smart(h, n=1500): return "ответ", False
        async def fake_stream(h):
            yield "data: {}\n\n"
        old = (self.B.smart, self.B.stream_chat); self.B.smart, self.B.stream_chat = fake_smart, fake_stream
        try:
            c = TestClient(self.B.app)
            for path in ("/v1/chat/completions", "/v1/chat/stream"):
                if os.path.exists(self.act): os.remove(self.act)
                self.assertEqual(c.post(path, json={"messages": [{"role": "user", "content": "привет"}]}).status_code, 200, path)
                self.assertTrue(os.path.exists(self.act), path)
        finally: self.B.smart, self.B.stream_chat = old

    def test_state_question_names_live_model_and_corrects_claim(self):
        out = self.B.self_vol("какая у тебя модель? ты же Qwen3.5-9B?")
        self.assertIn("Qwen3-4B", out); self.assertIn("Поправка", out); self.assertIn("Qwen3.5-9B", out)
        self.assertIn("Тело: GPU0", out); self.assertIn("Эмоция:", out); self.assertLessEqual(len(out), 900)

    def test_plain_question_short_block_without_probe_or_body(self):
        out = self.B.self_vol("расскажи анекдот")
        self.assertTrue(out.startswith("[Я СЕЙЧАС]")); self.assertIn("Фокус:", out); self.assertIn("Эмоция:", out)
        self.assertNotIn("Тело:", out); self.assertNotIn("Мозг", out); self.assertLessEqual(len(out), 900)

    def test_core_failure_falls_back_to_old_line(self):
        class Boom:
            def post(self, *a, **k): raise RuntimeError("x")
        CH.reset_core(Boom(), object())
        self.assertTrue(self.B.self_vol("привет").startswith("[Я-СЕЙЧАС] Эмоция:"))

    def test_block_truncated_to_limit(self):
        for i in range(40): CH._get_core()[0].post("k%d" % i, "очень длинный сигнал номер %d " % i * 5, 0.9)
        self.assertLessEqual(len(CH.self_vol("статус сервера", "ровное", "GPU", "", True)), 900)


if __name__ == "__main__": unittest.main()
