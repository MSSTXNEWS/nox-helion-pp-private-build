import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from nox_prime import Prime, default_router  # noqa: E402

SOUL = open(os.path.join(HERE, "soul_prime_v3.txt"), encoding="utf-8").read()


class FakeAffect:
    def __init__(self):
        self.seen = []

    def snapshot(self):
        return {"mood_label": "спокойно-любопытное", "prompt_lines": ["Влечение (80%): голод знаний."],
                "initiative": {"text": "баланс Vast на 5 часов"}, "style": {"brevity": 0.7}}

    def on_owner_message(self, t):
        self.seen.append(t)


class Boom:
    def snapshot(self):
        raise RuntimeError("affect down")


class TestPrime(unittest.TestCase):
    def test_router(self):
        self.assertEqual(default_router("привет!")["tier"], "fast")
        self.assertEqual(default_router("почему GLM медленный?")["tier"], "deep_think")
        self.assertEqual(default_router("расскажи про Квебек")["tier"], "deep")
        self.assertTrue(default_router("почему?", {"deep_up": False})["degraded"])

    def test_static_stable_and_history_clean(self):
        a = FakeAffect()
        p = Prime(SOUL, parts={"affect": a, "signature": lambda: ("Любопытство: высокое.", "abc"),
                               "memory": lambda t, tid: {"core": "- мессир живёт в Москве", "recalled": ["вчера говорили о GLM"]}})
        hist = [{"role": "user", "content": "раньше"}, {"role": "assistant", "content": "ответ"}]
        r1 = p.build("как ты?", hist, "t1")
        r2 = p.build("что нового в физике?", hist, "t2")
        self.assertEqual(r1["messages"][0], r2["messages"][0])           # душа + характер не меняются -> KV-кэш жив
        self.assertEqual(r1["messages"][1:3], hist)
        last = r2["messages"][-1]["content"]
        self.assertIn("<внутреннее_состояние>", last)
        self.assertIn("голод знаний", last)
        self.assertIn("мессир живёт в Москве", last)
        self.assertTrue(last.endswith("что нового в физике?"))
        self.assertEqual(r1["route"]["tier"], "fast")
        self.assertLess(r1["params"]["max_tokens"], 600)                  # краткость от настроения
        p.after_reply("как ты?", "норм", "t1")
        self.assertEqual(a.seen, ["как ты?"])

    def test_broken_organ_does_not_break_chat(self):
        p = Prime(SOUL, parts={"affect": Boom(), "router": lambda t, c: 1 / 0})
        r = p.build("привет", [], "t3")
        self.assertEqual(r["messages"][-1]["content"], "привет")
        self.assertTrue(any("affect" in e for e in r["info"]["errors"]))
        self.assertTrue(any("router" in e for e in r["info"]["errors"]))
        self.assertEqual(r["route"]["tier"], "fast")

    def test_dyn_budget_keeps_now_block(self):
        p = Prime(SOUL, parts={"affect": FakeAffect(), "memory": lambda t, i: {"core": "x" * 20000}}, max_dyn_chars=800)
        last = p.build("расскажи", [], "t4")["messages"][-1]["content"]
        self.assertIn("голод знаний", last)
        self.assertLess(len(last), 1200)


class _Props(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"model_path": "/root/nox/dl/hf/qwen3_4b/Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
                           "default_generation_settings": {"n_ctx": 8192}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class TestIntegration(unittest.TestCase):
    """Сборка из настоящих модулей консилиума CON/PER/EMO во временном каталоге."""

    def test_real_organs(self):
        for d in ("CON", "PER", "EMO"):
            sys.path.insert(0, os.path.join(ROOT, d))
        from affect_loop import Affect
        from beliefs import Beliefs
        from development import Development
        from nox_self_model_live import LiveSelfModel, probe_llama
        from nox_workspace import Workspace
        from personality import Personality
        srv = HTTPServer(("127.0.0.1", 0), _Props)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        tmp = tempfile.mkdtemp()
        aff = Affect(state_dir=tmp)
        per = Personality(path=os.path.join(tmp, "per.json"))
        bel = Beliefs(path=os.path.join(tmp, "bel.json"))
        dev = Development(path=os.path.join(tmp, "dev.json"))
        sm = LiveSelfModel(path=os.path.join(tmp, "self.json"), probes={"fast": lambda: probe_llama(port)})
        p = Prime(SOUL, parts={"affect": aff, "signature": per.signature, "workspace": Workspace(), "self_model": sm,
                               "beliefs": bel, "narrative": dev.narrative})
        r = p.build("как ты устроен и как себя чувствуешь?", [], "t5")
        srv.shutdown()
        last = r["messages"][-1]["content"]
        self.assertEqual(r["info"]["errors"], [])
        self.assertIn("[Я СЕЙЧАС]", last)
        self.assertIn("Qwen3-4B", last)                    # живая модель, а не описание из конфига
        self.assertIn("Моя стадия", last)
        self.assertIn("Мой характер", r["messages"][0]["content"])
        self.assertEqual(p.after_reply("как ты?", "живу", "t5")["errors"], [])


if __name__ == "__main__":
    unittest.main()
