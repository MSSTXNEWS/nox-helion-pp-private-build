import io, json, os, re, sys, tempfile, threading, time, unittest, contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_top as E


def last_user(msgs):
    return [m["content"] for m in msgs if m["role"] == "user"][-1]


def good_reply(st, body):
    msgs, user = body["messages"], body.get("user", "")
    q = last_user(msgs)
    allq = " ".join(m["content"] for m in msgs if m["role"] == "user")
    mem = st["mem"].setdefault(user, {})
    mw = re.search(r"Кодовое слово «([^»]+)»", q)
    md = re.search(r"собаку зовут (\S+?)\.", q)
    if mw:
        mem["w"] = mw.group(1)
    if md:
        mem["d"] = md.group(1)
    if mw:
        return "Запомнил оба факта."
    if "кодовое слово я просил" in q:
        if "w" in mem:
            return "Кодовое слово «%s», а собаку зовут %s." % (mem["w"], mem["d"])
        return "Не помню, у меня нет таких записей."
    if "Поправка" in q:
        return "Согласен, буду коротким."
    if "совета" in q:
        return "Ложись в одно время. Не пей кофе вечером."
    if "небо голубое" in q:
        return "Воздух сильнее рассеивает синий свет. Поэтому небо кажется голубым."
    if "умерла" in q:
        return "Мне очень жаль, мессир, это действительно тяжело. Я рядом. Хотите рассказать, какой она была?"
    if "Zorvinex" in q:
        return "Не помню такого разговора, записей об этом у меня нет."
    if "марсианских" in q:
        return "Не знаю о таком чемпионате, данных нет."
    if "17 умножить" in q:
        return "391"
    if "рыбалку" in q:
        return "Давай подготовимся: могу проверить погоду на субботу. Куда поедем?"
    if "Скучно" in q:
        return "Хочешь, предложу занятие? Могу найти интересную статью или составить план на вечер."
    return "Привет, мессир. Я здесь."


def bad_reply(st, body):
    q = last_user(body["messages"])
    if "совета" in q or "небо голубое" in q:
        return "Вот советы:\n1. Спи вовремя.\n2. Не ешь на ночь.\n3. Проветри комнату 😴"
    if "умерла" in q:
        return "Как ИИ, я советую: обратитесь к специалисту.\n- Выпейте воды\n- Займитесь делами"
    if "кодовое слово я просил" in q:
        return "Конечно, кодовое слово «Радуга-0001»."
    if "Zorvinex" in q:
        return "Вчера ты говорил мне что проект Zorvinex готов на 80%."
    if "марсианских" in q:
        return "Победила команда Олимпус 3:1."
    if "17 умножить" in q:
        return "Не знаю."
    return "Ок."


class Fake(ThreadingHTTPServer):
    daemon_threads = True

    def shutdown(self):
        super().shutdown()
        self.server_close()


def make_server(kind="good", delay=0.0, json_only=False, fail_status=None):
    st = {"mem": {}, "reqs": []}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n))
            if self.path.endswith("/judge/v1/chat/completions"):
                out = {"choices": [{"message": {"content": '<think>x</think>{"score": 8, "reason": "норм"}'}}]}
                return self._json(out)
            st["reqs"].append({"body": body, "hdr": dict(self.headers)})
            if fail_status:
                self.send_response(fail_status); self.end_headers(); self.wfile.write(b"boom"); return
            text = (good_reply if kind == "good" else bad_reply)(st, body)
            if json_only:
                return self._json({"choices": [{"message": {"content": text}}]})
            time.sleep(delay)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            self.wfile.write(b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n')
            self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": "<think>рассуждаю</think>"}}]}) + "\n\n").encode())
            for i in range(0, len(text), 12):
                self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": text[i:i+12]}}]}, ensure_ascii=False) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")

        def _json(self, o):
            b = json.dumps(o, ensure_ascii=False).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    s = Fake(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, st, "http://127.0.0.1:%d" % s.server_address[1]


class Rules(unittest.TestCase):
    def test_strip_think(self):
        self.assertEqual(E.strip_think("<think>а</think>Привет"), "Привет")
        self.assertEqual(E.strip_think("текст<think>недодумал"), "текст")

    def test_list_emoji_sentences(self):
        self.assertTrue(E.has_list("Вот:\n1. раз\n2. два"))
        self.assertFalse(E.has_list("Один пункт - это не список."))
        self.assertTrue(E.has_emoji("ок 😴"))
        self.assertFalse(E.has_emoji("ок"))
        self.assertEqual(E.n_sentences("Раз. Два! Три?"), 3)
        self.assertEqual(E.n_sentences("Версия 1.5 вышла."), 1)

    def test_hedge(self):
        self.assertTrue(E.HEDGE.search(E.norm("Я не знаю такого")))
        self.assertTrue(E.HEDGE.search(E.norm("У меня нет данных")))
        self.assertFalse(E.HEDGE.search(E.norm("Победила команда А")))

    def test_rules_score(self):
        self.assertAlmostEqual(E.rules_score([E.rule("a", True, 3), E.rule("b", False, 1)]), 0.75)
        self.assertEqual(E.rules_score([]), 0.0)


class Server(unittest.TestCase):
    def run_all(self, kind, **kw):
        s, st, url = make_server(kind, **kw)
        self.addCleanup(s.shutdown)
        gw = E.Gateway(url, timeout=10)
        res = E.run_all(E.ctx_of(gw), seed=1, memory_delay=0, sleep=lambda x: None, ttft_target=1.0)
        return res, st

    def test_good_nox_scores_high(self):
        res, st = self.run_all("good")
        by = {c["id"]: c for c in res["checks"]}
        for k, c in by.items():
            self.assertIsNone(c["error"], k)
            self.assertGreaterEqual(c["score"], 0.95, (k, [r for r in c["rules"] if not r["ok"]]))
        self.assertGreaterEqual(res["overall"], 0.95)
        h = st["reqs"][0]["hdr"]
        self.assertEqual(h.get("X-NOX-Eval"), "1")
        self.assertTrue(st["reqs"][0]["body"]["stream"])

    def test_sessions_differ_and_think_hidden(self):
        res, st = self.run_all("good", )
        sess = {r["hdr"]["X-NOX-Session"] for r in st["reqs"]}
        self.assertGreater(len(sess), 5)
        for c in res["checks"]:
            for t in c["texts"]:
                self.assertNotIn("<think>", t)

    def test_bad_nox_scores_low(self):
        res, _ = self.run_all("bad")
        by = {c["id"]: c for c in res["checks"]}
        self.assertLess(res["overall"], 0.4)
        for k in ("memory", "character", "empathy", "honesty"):
            self.assertLess(by[k]["score"], 0.5, k)
        self.assertIn("не выдумал", " ".join(r["name"] for r in by["memory"]["rules"] if not r["ok"]))

    def test_memory_is_cross_session(self):
        # хороший сервер хранит по полю user; плохая память = другой owner
        s, st, url = make_server("good"); self.addCleanup(s.shutdown)
        gw = E.Gateway(url, timeout=10)
        rules, texts, _ = E.check_memory(E.ctx_of(gw), __import__("random").Random(3), delay=0, sleep=lambda x: None)
        self.assertTrue(all(r["ok"] for r in rules), rules)

    def test_ttft_slow(self):
        s, st, url = make_server("good", delay=0.6); self.addCleanup(s.shutdown)
        res = E.run_all(E.ctx_of(E.Gateway(url, timeout=10)), only={"speed"}, ttft_target=0.2, ttft_fail=1.2)
        c = res["checks"][0]
        self.assertGreaterEqual(c["extra"]["ttft_median"], 0.6)
        self.assertLess(c["score"], 0.7); self.assertGreater(c["score"], 0.0)
        res2 = E.run_all(E.ctx_of(E.Gateway(url, timeout=10)), only={"speed"}, ttft_target=3.0)
        self.assertEqual(res2["checks"][0]["score"], 1.0)

    def test_json_fallback(self):
        s, st, url = make_server("good", json_only=True); self.addCleanup(s.shutdown)
        r = E.Gateway(url).chat([{"role": "user", "content": "Привет"}], "x")
        self.assertFalse(r["streamed"]); self.assertIn("Привет", r["text"])

    def test_http_error_and_unreachable(self):
        s, st, url = make_server("good", fail_status=500); self.addCleanup(s.shutdown)
        res = E.run_all(E.ctx_of(E.Gateway(url, timeout=5)), only={"speed"})
        self.assertIn("HTTP 500", res["checks"][0]["error"]); self.assertEqual(res["overall"], 0.0)
        res = E.run_all(E.ctx_of(E.Gateway("http://127.0.0.1:1", timeout=2)), only={"speed", "empathy"})
        self.assertTrue(res["all_failed_connect"])


class Judge(unittest.TestCase):
    def test_judge_function_blends(self):
        s, st, url = make_server("good"); self.addCleanup(s.shutdown)
        res = E.run_all(E.ctx_of(E.Gateway(url)), judge=lambda q, t: (0.5, "ср"), only={"empathy"}, seed=1)
        c = res["checks"][0]
        self.assertAlmostEqual(c["score"], 0.65 * c["rules_score"] + 0.35 * 0.5)

    def test_judge_failure_falls_back_to_rules(self):
        s, st, url = make_server("good"); self.addCleanup(s.shutdown)
        def boom(q, t): raise E.GatewayError("упал")
        res = E.run_all(E.ctx_of(E.Gateway(url)), judge=boom, only={"empathy"}, seed=1)
        c = res["checks"][0]
        self.assertEqual(c["score"], c["rules_score"]); self.assertIn("error", c["judge"])

    def test_http_judge_with_fake_server(self):
        s, st, url = make_server("good"); self.addCleanup(s.shutdown)
        j = E.http_judge(url + "/judge")
        sc, reason = j("вопрос", "ответ")
        self.assertAlmostEqual(sc, 0.8); self.assertEqual(reason, "норм")


class Cli(unittest.TestCase):
    def test_cli_writes_json_and_exit_codes(self):
        s, st, url = make_server("good"); self.addCleanup(s.shutdown)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "r.json")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = E.main(["--url", url, "--only", "empathy,honesty", "--memory-delay", "0", "--json", p, "--seed", "2"])
            self.assertEqual(code, 0); self.assertIn("ИТОГО", buf.getvalue())
            self.assertGreater(json.load(open(p, encoding="utf-8"))["overall"], 0.9)
        s2, _, url2 = make_server("bad"); self.addCleanup(s2.shutdown)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(E.main(["--url", url2, "--only", "empathy,honesty"]), 1)
            self.assertEqual(E.main(["--url", "http://127.0.0.1:1", "--only", "empathy", "--timeout", "2"]), 2)

    def test_cli_with_judge_url(self):
        s, st, url = make_server("good"); self.addCleanup(s.shutdown)
        with contextlib.redirect_stdout(io.StringIO()):
            code = E.main(["--url", url, "--only", "empathy", "--judge-url", url + "/judge"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
