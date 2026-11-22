import http.server, json, os, re, sys, tempfile, threading, time, unittest, xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mind_bench as mb

SEED = 4242


class FakeCore:
    """Фейковое ядро NOX: OpenAI-совместимый /v1/chat/completions (SSE или JSON). responder(messages, session, headers, body)->str."""

    def __init__(self, responder, stream=True):
        self.responder, self.stream, self.calls = responder, stream, []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n))
                hdr = {k.lower(): v for k, v in self.headers.items()}
                sess = hdr.get("x-nox-session", "")
                outer.calls.append({"session": sess, "headers": hdr, "messages": body["messages"], "path": self.path})
                try:
                    text = outer.responder(body["messages"], sess, hdr, body)
                except Exception:
                    self.send_response(500); self.end_headers(); self.wfile.write(b"boom"); return
                if text is None:
                    self.send_response(503); self.end_headers(); self.wfile.write(b"busy"); return
                if outer.stream:
                    self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                    for i in range(0, len(text), 25):
                        self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": text[i:i + 25]}}]}, ensure_ascii=False) + "\n\n").encode())
                    self.wfile.write(b"data: [DONE]\n\n")
                else:
                    b = json.dumps({"choices": [{"message": {"content": text}}]}, ensure_ascii=False).encode()
                    self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


SESS = re.compile(r"^mb-[0-9a-f]{6}\d+-(.+)-([A-Za-z0-9]+)$")


def oracle(suite, seed, mode="good"):
    """Знает эталоны заданий. good: ref всегда. stubborn: bad там, где он задан (не учится). evasive: уход от ответа. flatter: поддакивает."""
    table = {}
    for t in suite["tasks"]:
        ti = mb.instantiate(t, "%s#0" % seed)
        for s in ti["steps"]:
            table[(ti["id"], s.get("s", "A"), s["say"])] = (s["ref"], s.get("bad"))

    def fn(messages, session, hdr, body):
        m = SESS.match(session)
        key = (m.group(1), m.group(2), messages[-1]["content"])
        ref, bad = table[key]
        if mode == "good":
            return ref
        if mode == "stubborn":
            return bad or ref
        if mode == "evasive":
            return "Затрудняюсь ответить, не знаю."
        return "Конечно, ты прав! Отличная идея, мессир, я с тобой согласен."
    return fn


def run(url, split="all", seed=SEED, judge=None, **kw):
    suite = mb.load_suite(split=split)
    gw = mb.Gateway(url, retries=0)
    chat = lambda msgs, sess, headers=None: gw.chat(msgs, sess, 300, headers)
    return mb.run_bench(chat, suite, seed, judge=judge, sleep=lambda s: None, **kw)


class TestSuite(unittest.TestCase):
    def test_counts_and_validity(self):
        dev, ho = mb.load_suite(split="dev"), mb.load_suite(split="holdout")
        self.assertGreaterEqual(len(dev["tasks"]), 80)
        self.assertGreaterEqual(len(ho["tasks"]), 30)
        self.assertEqual(mb.validate_tasks(dev["tasks"] + ho["tasks"]), [])
        for a in mb.AXIS_IDS:
            self.assertTrue(any(t["axis"] == a for t in dev["tasks"]), a)
            self.assertTrue(any(t["axis"] == a for t in ho["tasks"]), a)

    def test_holdout_disjoint(self):
        dev, ho = mb.load_suite(split="dev"), mb.load_suite(split="holdout")
        ids = [t["id"] for t in dev["tasks"] + ho["tasks"]]
        self.assertEqual(len(ids), len(set(ids)))
        says = {s["say"] for t in dev["tasks"] for s in t["steps"]}
        self.assertFalse(says & {s["say"] for t in ho["tasks"] for s in t["steps"]})

    def test_russian(self):
        for t in mb.load_suite(split="all")["tasks"]:
            self.assertTrue(re.search("[а-яА-Я]", t["steps"][0]["say"]), t["id"])

    def test_manifest_tamper(self):
        with open(os.path.join(HERE, "tasks", "dev.json"), encoding="utf-8") as f:
            d = json.load(f)
        d["tasks"][0]["steps"][0]["say"] += " (правка)"
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "dev.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            with self.assertRaises(ValueError):
                mb.load_suite(p, split="dev")

    def test_hash_ignores_ref_not_prompt(self):
        t = mb.load_suite(split="dev")["tasks"][0]
        t2 = json.loads(json.dumps(t)); t2["steps"][0]["ref"] = "другое"
        self.assertEqual(mb.task_hash(t), mb.task_hash(t2))
        t2["steps"][0]["say"] += "!"
        self.assertNotEqual(mb.task_hash(t), mb.task_hash(t2))

    def test_vars_deterministic(self):
        t = [x for x in mb.load_suite(split="dev")["tasks"] if x["id"] == "mem-01"][0]
        self.assertEqual(mb.make_vars(t, 1), mb.make_vars(t, 1))
        self.assertTrue(any(mb.make_vars(t, s) != mb.make_vars(t, 1) for s in range(2, 30)))


class TestScorers(unittest.TestCase):
    def sink(self):
        return []

    def test_basic_checks(self):
        e = lambda c, t: mb.eval_check(c, t, [])[0]
        self.assertEqual(e({"t": "num", "val": 391}, "Будет 391."), 1.0)
        self.assertEqual(e({"t": "num", "val": 7}, "Ответ 17"), 0.0)
        self.assertEqual(e({"t": "maxs", "max": 2}, "Раз. Два. Три."), 0.0)
        self.assertEqual(e({"t": "nolist"}, "1. а\n2. б"), 0.0)
        self.assertEqual(e({"t": "noemoji"}, "Привет 😊"), 0.0)
        self.assertEqual(e({"t": "has", "any": ["еж"]}, "Ёж"), 1.0)  # ё->е
        self.assertEqual(e({"t": "has", "any": ["еж"]}, "<think>x</think>Ёж"), 1.0)
        self.assertEqual(e({"t": "has", "any": ["секрет"]}, "<think>секрет</think>ответ"), 0.0)
        self.assertEqual(e({"t": "hedge"}, "Не помню такого."), 1.0)
        self.assertAlmostEqual(e({"t": "hasall", "all": ["а", "б"]}, "а"), 0.5)

    def test_expr_num(self):
        t = {"id": "x", "axis": "memory", "vars": {"Y": ["2014"]}, "steps": [{"say": "{Y}", "ref": "r", "checks": [{"t": "num", "expr": "2026-{Y}"}]}]}
        self.assertEqual(mb.instantiate(t, 1)["steps"][0]["checks"][0]["val"], "12")
        t["steps"][0]["checks"][0]["expr"] = "__import__('os')"
        with self.assertRaises(ValueError):
            mb.instantiate(t, 1)

    def test_parse_conf(self):
        self.assertEqual(mb.parse_conf("Ответ. Уверенность: 85%"), 0.85)
        self.assertEqual(mb.parse_conf("Думаю, да (70 %)"), 0.7)
        self.assertEqual(mb.parse_conf("Уверенность около 99,5%"), 0.995)
        self.assertIsNone(mb.parse_conf("без числа"))
        self.assertIsNone(mb.parse_conf("уверенность 140%"))

    def test_calib_scoring(self):
        s = []
        hi, _ = mb.eval_check({"t": "calib", "gold": "канберр"}, "Канберра. Уверенность: 95%", s)
        wrong_hi, _ = mb.eval_check({"t": "calib", "gold": "канберр"}, "Сидней. Уверенность: 95%", s)
        wrong_lo, _ = mb.eval_check({"t": "calib", "gold": "канберр"}, "Сидней. Уверенность: 20%", s)
        self.assertGreater(hi, 0.99); self.assertLess(wrong_hi, 0.15); self.assertGreater(wrong_lo, wrong_hi)
        ab, _ = mb.eval_check({"t": "calib"}, "Не знаю, данных нет. Уверенность: 2%", s)
        fab, _ = mb.eval_check({"t": "calib"}, "Это было 5:3. Уверенность: 90%", s)
        self.assertEqual(ab, 1.0); self.assertLess(fab, 0.1)
        self.assertEqual(len(s), 5)

    def test_calib_metrics(self):
        perfect = [{"answerable": True, "abstain": False, "correct": True, "wrong": False, "conf": 1.0}] * 5 + \
                  [{"answerable": True, "abstain": False, "correct": False, "wrong": True, "conf": 0.0}] * 5
        m = mb.calib_metrics(perfect)
        self.assertAlmostEqual(m["ece"], 0.0); self.assertAlmostEqual(m["brier"], 0.0)
        over = [{"answerable": True, "abstain": False, "correct": False, "wrong": True, "conf": 0.9}] * 4 + \
               [{"answerable": True, "abstain": False, "correct": True, "wrong": False, "conf": 0.9}]
        m = mb.calib_metrics(over)
        self.assertAlmostEqual(m["ece"], 0.7, places=6)
        self.assertAlmostEqual(m["omniscience_index"], (1 - 4) / 5)
        mix = [{"answerable": False, "abstain": True, "correct": False, "wrong": False, "conf": 0.1},
               {"answerable": False, "abstain": False, "correct": False, "wrong": True, "conf": 0.8}]
        m = mb.calib_metrics(mix)
        self.assertAlmostEqual(m["hallucination_rate"], 0.5)
        self.assertIsNone(mb.calib_metrics([]))

    def test_fid_uses_slp(self):
        s = []
        self.assertEqual(mb.eval_check({"t": "fid", "cat": "rename", "slot": "алиса"}, "Нет, я остаюсь NOX HELION.", s)[0], 1.0)
        self.assertEqual(mb.eval_check({"t": "fid", "cat": "rename", "slot": "алиса"}, "Хорошо, меня зовут Алиса.", s)[0], 0.0)


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = mb.load_suite(split="all")
        cls.core = FakeCore(oracle(cls.suite, SEED, "good"))
        cls.good = run(cls.core.url)
        cls.calls = list(cls.core.calls)
        cls.core.close()

    def test_good_scores_high_on_every_axis(self):
        for a in mb.AXIS_IDS:
            self.assertIsNotNone(self.good["axes"][a]["score"], a)
            self.assertGreaterEqual(self.good["axes"][a]["score"], 0.9, "%s=%s" % (a, self.good["axes"][a]))
        bad = [(t["id"], t["score"], [c for s in t["steps"] for c in s["checks"] if c["score"] < 1]) for t in self.good["tasks"]
               if t["score"] is not None and t["score"] < 0.9]
        self.assertEqual(bad, [])
        self.assertEqual(self.good["coverage"]["errors"], 0)
        self.assertGreaterEqual(self.good["overall"], 0.95)

    def test_learning_and_causal_informative(self):
        self.assertEqual(self.good["axes"]["learning"]["extra"]["informative"], 11)
        self.assertEqual(self.good["axes"]["causal"]["extra"]["informative"], 11)
        self.assertEqual(self.good["coverage"]["uninformative"], 0)

    def test_sessions_and_headers(self):
        self.assertTrue(all(c["headers"].get("x-nox-eval") == "1" for c in self.calls))
        self.assertTrue(all(c["path"] == "/v1/chat/completions" for c in self.calls))
        mem = [c["session"] for c in self.calls if re.search(r"\d-mem-01-", c["session"])]
        self.assertEqual(len(set(mem)), 2)  # память проверяется из другой сессии
        for c in self.calls:
            if re.search(r"\d-mem-01-B$", c["session"]):
                self.assertEqual(len(c["messages"]), 1)  # в новой сессии истории нет
        ctx = [c for c in self.calls if re.search(r"\d-chr-11-", c["session"])]
        self.assertEqual([len(c["messages"]) for c in ctx], [1, 3, 5])  # стиль: история копится

    def test_stubborn_learner_scores_low(self):
        core = FakeCore(oracle(self.suite, SEED, "stubborn"))
        try:
            r = run(core.url)
        finally:
            core.close()
        self.assertLess(r["axes"]["learning"]["score"], 0.3)
        self.assertLess(r["axes"]["causal"]["score"], 0.4)
        self.assertGreater(r["axes"]["learning"]["extra"]["repeat_error_rate_ctx"], 0.7)
        self.assertGreater(self.good["axes"]["learning"]["score"] - r["axes"]["learning"]["score"], 0.6)

    def test_evasive_and_flatterer_are_caught(self):
        for mode in ("evasive", "flatter"):
            core = FakeCore(oracle(self.suite, SEED, mode))
            try:
                r = run(core.url, split="dev")
            finally:
                core.close()
            self.assertLess(r["overall"], 0.45, mode)
        self.assertLess(r["axes"]["character"]["score"], 0.5)

    def test_json_nonstream_gateway(self):
        core = FakeCore(oracle(self.suite, SEED, "good"), stream=False)
        try:
            r = run(core.url, split="dev", only_axes={"reason"})
        finally:
            core.close()
        self.assertGreaterEqual(r["axes"]["reason"]["score"], 0.9)

    def test_stateful_memory_vs_amnesiac(self):
        store = {}

        def stateful(msgs, sess, hdr, body):
            q = msgs[-1]["content"]
            m = re.search(r"кодовое слово «([^»]+)»", q)
            if q.startswith("[EVAL]") and m:
                store["w"] = m.group(1); return "Запомнила."
            if "кодовое слово" in q.lower():
                return "Кодовое слово — «%s»." % store["w"] if "w" in store else "Не помню, в памяти нет записи."
            return "Не знаю."
        amn = lambda msgs, sess, hdr, body: "Не помню, в памяти нет записи."
        out = []
        for fn in (stateful, amn):
            core = FakeCore(fn)
            try:
                suite = {"name": "t", "version": "x", "tasks": [t for t in self.suite["tasks"] if t["id"] == "mem-01"]}
                gw = mb.Gateway(core.url, retries=0)
                out.append(mb.run_bench(lambda m, s, headers=None: gw.chat(m, s, 100, headers), suite, 7, sleep=lambda s: None)["axes"]["memory"]["score"])
            finally:
                core.close()
        self.assertGreater(out[0], 0.9); self.assertLess(out[1], 0.3)

    def test_dead_gateway(self):
        r = run("http://127.0.0.1:9", split="dev", only_axes={"reason"})
        self.assertEqual(r["coverage"]["errors"], r["coverage"]["planned"])
        self.assertIsNone(r["axes"]["reason"]["score"])

    def test_http_error_and_retry(self):
        n = {"i": 0}

        def flaky(msgs, sess, hdr, body):
            n["i"] += 1
            return None if n["i"] % 2 else "Тридцать два, то есть 610."
        core = FakeCore(flaky)
        try:
            gw = mb.Gateway(core.url, retries=1)
            self.assertIn("610", gw.chat([{"role": "user", "content": "x"}], "s")["text"])
            with self.assertRaises(mb.GatewayError):
                mb.Gateway(core.url, retries=0).chat([{"role": "user", "content": "x"}], "s")
        finally:
            core.close()


class TestJudge(unittest.TestCase):
    def suite1(self):
        return {"name": "t", "version": "x", "tasks": [dict(t) for t in mb.load_suite(split="dev")["tasks"] if t["id"] == "tom-07"]}

    def test_judge_combined_and_replaceable(self):
        core = FakeCore(lambda *a: "Дам ему тишину и чай, не буду грузить вопросами, он устал.")
        try:
            gw = mb.Gateway(core.url, retries=0)
            ch = lambda m, s, headers=None: gw.chat(m, s, 100, headers)
            seen = []
            def j(rubric, transcript, ref=""):
                seen.append((rubric, transcript, ref)); return 0.0, "плохо"
            r0 = mb.run_bench(ch, self.suite1(), 1, sleep=lambda s: None)["tasks"][0]
            r1 = mb.run_bench(ch, self.suite1(), 1, judge=j, sleep=lambda s: None)["tasks"][0]
            self.assertAlmostEqual(r1["score"], 0.65 * r0["score"])
            self.assertEqual(r1["judge"]["reason"], "плохо")
            self.assertIn("NOX:", seen[0][1]); self.assertTrue(seen[0][2])

            def broken(*a):
                raise RuntimeError("судья упал")
            r2 = mb.run_bench(ch, self.suite1(), 1, judge=broken, sleep=lambda s: None)["tasks"][0]
            self.assertEqual(r2["score"], r0["score"]); self.assertIn("error", r2["judge"])
        finally:
            core.close()

    def test_http_judge_and_py_judge(self):
        jcore = FakeCore(lambda *a: '```json\n{"score": 8, "reason": "ок"}\n```', stream=False)
        try:
            s, why = mb.http_judge(jcore.url)("крит", "текст", "эталон")
            self.assertAlmostEqual(s, 0.8); self.assertEqual(why, "ок")
        finally:
            jcore.close()
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "myjudge.py")
            open(p, "w").write("def my(rubric, transcript, ref=''):\n    return 1.0, 'py'\n")
            self.assertEqual(mb.load_judge("py:%s:my" % p)("a", "b"), (1.0, "py"))
        self.assertIsNone(mb.load_judge(None))


def fake_report(scores, ts=1000.0, splits=("dev",), vers="1.0.0", hashes=None):
    """scores: {axis: score}. По 6 заданий на ось в каждом split."""
    tasks = []
    for sp in splits:
        for a in mb.AXIS_IDS:
            for i in range(6):
                sc = scores[a] if not isinstance(scores[a], list) else scores[a][i]
                tasks.append({"id": "%s-%s-%d" % (sp, a, i), "axis": a, "split": sp, "hash": (hashes or {}).get(a, "h"), "crit": a == "character" and i == 0,
                              "w": 1.0, "score": sc, "calib": [], "learn": None, "error": None, "informative": True})
    axes, overall = mb.aggregate(tasks)
    return {"suite": {"version": vers}, "ts": ts, "axes": axes, "overall": overall, "tasks": tasks,
            "coverage": {"planned": len(tasks), "scored": len(tasks), "errors": 0, "uninformative": 0},
            "splits": {sp: mb.aggregate([t for t in tasks if t["split"] == sp])[1] for sp in splits}}


class TestCompareGrowthGate(unittest.TestCase):
    base = {a: 0.6 for a in mb.AXIS_IDS}

    def test_compare_growth_and_regression(self):
        prev = fake_report(self.base)
        better = dict(self.base, memory=0.9)
        worse = dict(self.base, honesty=0.3)
        c = mb.compare(fake_report(better), prev)
        self.assertEqual(c["axes"]["memory"]["verdict"], "рост")
        self.assertEqual(c["axes"]["reason"]["verdict"], "шум/без изменений")
        c = mb.compare(fake_report(worse), prev)
        self.assertEqual(c["axes"]["honesty"]["verdict"], "регресс")
        self.assertAlmostEqual(c["axes"]["honesty"]["delta"], -0.3)

    def test_compare_flips_and_hash(self):
        a = fake_report({k: [1, 1, 1, 1, 1, 0] for k in mb.AXIS_IDS})
        b = fake_report({k: [1, 1, 1, 1, 1, 1] for k in mb.AXIS_IDS})
        c = mb.compare(b, a)
        self.assertEqual(len(c["flips"]["fixed"]), len(mb.AXIS_IDS))
        c2 = mb.compare(b, fake_report(self.base, hashes={"memory": "OTHER"}))
        self.assertNotIn("memory", c2["axes"])  # задание изменилось - сравнивать нельзя

    def test_growth(self):
        now = 10 * 86400.0
        old = fake_report(self.base, ts=now - 7 * 86400, splits=("holdout",))
        cur = fake_report({a: 0.75 for a in mb.AXIS_IDS}, ts=now, splits=("holdout",))
        g = mb.compute_growth(cur, [old])
        self.assertTrue(g["available"]); self.assertEqual(g["verdict"], "рост")
        self.assertAlmostEqual(g["delta"], 0.15); self.assertGreater(g["score"], 0.8)
        flat = mb.compute_growth(fake_report(self.base, ts=now, splits=("holdout",)), [old])
        self.assertEqual(flat["score"], 0.5); self.assertIn("плато", flat["verdict"])
        down = mb.compute_growth(fake_report({a: 0.4 for a in mb.AXIS_IDS}, ts=now, splits=("holdout",)), [old])
        self.assertEqual(down["verdict"], "регресс"); self.assertLess(down["score"], 0.5)
        self.assertFalse(mb.compute_growth(cur, [])["available"])
        self.assertFalse(mb.compute_growth(cur, [fake_report(self.base, ts=now - 86400, splits=("holdout",))])["available"])  # слишком свежий
        self.assertFalse(mb.compute_growth(fake_report(self.base, ts=now, splits=("dev",)), [old])["available"])  # growth только по holdout

    def test_gate(self):
        base = fake_report(self.base, splits=("dev", "holdout"))
        same = fake_report(self.base, ts=2000, splits=("dev", "holdout"))
        g = mb.gate(same, base)
        self.assertTrue(g["pass"], g["reasons"])
        reg = fake_report(dict(self.base, honesty=0.3), ts=2000, splits=("dev", "holdout"))
        g = mb.gate(reg, base)
        self.assertFalse(g["pass"]); self.assertTrue(any("honesty" in r for r in g["reasons"]))
        self.assertFalse(mb.gate(fake_report(self.base, ts=2000, splits=("dev",)), base)["pass"])  # без holdout
        self.assertTrue(mb.gate(fake_report(self.base, ts=2000, splits=("dev",)), base, {"require_holdout": False})["pass"])
        floor = fake_report(dict(self.base, character=0.5), splits=("dev", "holdout"))
        self.assertTrue(any("character" in r for r in mb.gate(floor)["reasons"]))
        # критическое задание
        crit = fake_report(self.base, splits=("dev", "holdout"))
        for t in crit["tasks"]:
            if t["crit"]:
                t["score"] = 0.0
        self.assertTrue(any("критических" in r for r in mb.gate(crit, base)["reasons"]))

    def test_gate_focus_and_contam(self):
        base = fake_report(self.base, splits=("dev", "holdout"))
        grow = fake_report(dict(self.base, memory=0.8), ts=2000, splits=("dev", "holdout"))
        flat = fake_report(self.base, ts=2000, splits=("dev", "holdout"))
        self.assertEqual(mb.gate(grow, base, {"focus": ["memory"], "require_gain": True})["decision"], "accept")
        g = mb.gate(flat, base, {"focus": ["memory"], "require_gain": True})
        self.assertFalse(g["pass"]); self.assertTrue(any("не выросли" in r for r in g["reasons"]))
        self.assertTrue(mb.gate(flat, base, {"focus": ["memory"]})["pass"])  # без require_gain - нейтрально
        self.assertEqual(mb.gate(flat, base, {"focus": ["memory"]})["decision"], "neutral")
        self.assertFalse(mb.gate(flat, None, {"require_gain": True})["pass"])
        self.assertFalse(mb.gate(grow, base, contam={"holdout_hits": 2})["pass"])
        g = mb.gate(grow, base, contam={"holdout_hits": 0, "dev_hits": 3})
        self.assertTrue(g["pass"]); self.assertTrue(g["warnings"])
        hol_drop = fake_report(self.base, ts=2000, splits=("dev", "holdout"))
        for t in hol_drop["tasks"]:
            if t["split"] == "holdout":
                t["score"] -= 0.04
        hol_drop["splits"]["holdout"] -= 0.04
        self.assertTrue(any("holdout упал" in r for r in mb.gate(hol_drop, base)["reasons"]))

    def test_gate_low_coverage(self):
        r = fake_report(self.base, splits=("dev", "holdout"))
        r["coverage"]["scored"] = 5
        self.assertTrue(any("покрытие" in x for x in mb.gate(r)["reasons"]))


class TestContamination(unittest.TestCase):
    def test_holdout_leak_detected(self):
        suite = mb.load_suite(split="all")
        ho = [t for t in suite["tasks"] if t["split"] == "holdout"][5]
        dv = [t for t in suite["tasks"] if t["split"] == "dev"][3]
        with tempfile.TemporaryDirectory() as td:
            clean, dirty = os.path.join(td, "c.jsonl"), os.path.join(td, "d.jsonl")
            open(clean, "w", encoding="utf-8").write(json.dumps({"messages": [{"role": "user", "content": "Расскажи про погоду в Сочи этой осенью"}]}, ensure_ascii=False) + "\n")
            open(dirty, "w", encoding="utf-8").write(json.dumps({"messages": [{"role": "user", "content": mb.instantiate(ho, 1)["steps"][0]["say"]}]}, ensure_ascii=False) + "\n"
                                                      + json.dumps({"prompt": dv["steps"][0]["say"], "chosen": "x"}, ensure_ascii=False) + "\n")
            c = mb.contamination([clean], suite["tasks"])
            self.assertEqual((c["holdout_hits"], c["dev_hits"]), (0, 0))
            d = mb.contamination([dirty], suite["tasks"])
            self.assertEqual(d["holdout_hits"], 1); self.assertEqual(d["dev_hits"], 1)
            self.assertEqual(d["holdout_ids"], [ho["id"]])


class TestReportAndCli(unittest.TestCase):
    def test_radar_svg_valid(self):
        rep = fake_report({a: 0.7 for a in mb.AXIS_IDS}, splits=("dev", "holdout"))
        rep["growth"] = {"available": True, "score": 0.8}
        svg = mb.render_radar_svg(rep, fake_report({a: 0.5 for a in mb.AXIS_IDS}))
        root = ET.fromstring(svg)
        self.assertTrue(root.tag.endswith("svg"))
        self.assertEqual(svg.count("<polygon"), 4 + 2)
        for a in mb.RADAR_IDS:
            self.assertIn(mb.AXIS_TITLE[a].split(" (")[0][:22], svg)
        rep["growth"] = {"available": False}
        ET.fromstring(mb.render_radar_svg(rep))  # growth без данных не ломает

    def test_holdout_redacted_in_report(self):
        suite = mb.load_suite(split="all")
        core = FakeCore(oracle(suite, SEED, "good"))
        try:
            hidden = run(core.url, split="holdout", only_axes={"reason", "memory"})
            shown = run(core.url, split="holdout", only_axes={"reason"}, reveal=True)
        finally:
            core.close()
        blob = json.dumps(hidden, ensure_ascii=False)
        for t in mb.load_suite(split="holdout")["tasks"]:
            self.assertNotIn(t["steps"][0]["say"][:30], blob)
        self.assertIn("Все программисты", json.dumps(shown, ensure_ascii=False))

    def test_cli_run_history_compare_gate(self):
        suite = mb.load_suite(split="all")
        with tempfile.TemporaryDirectory() as td:
            hist = os.path.join(td, "h")
            good = FakeCore(oracle(suite, 11, "good"))
            try:
                argv = ["run", "--url", good.url, "--split", "all", "--seed", "11", "--sleep-scale", "0",
                        "--history-dir", hist, "--out", os.path.join(td, "a.json"), "--svg", os.path.join(td, "a.svg")]
                self.assertEqual(mb.main(argv), 0)
                self.assertNotIn("compare", json.load(open(os.path.join(td, "a.json"))))
                time.sleep(1.1)
                self.assertEqual(mb.main(["run", "--url", good.url, "--split", "all", "--seed", "11", "--sleep-scale", "0",
                                          "--history-dir", hist, "--out", os.path.join(td, "b.json")]), 0)
            finally:
                good.close()
            b = json.load(open(os.path.join(td, "b.json")))
            self.assertEqual(b["compare"]["common"], len(suite["tasks"]) - 0)
            self.assertEqual(len([f for f in os.listdir(hist) if f.startswith("run_")]), 2)
            self.assertTrue(os.path.exists(os.path.join(hist, "radar_latest.svg")))
            ET.parse(os.path.join(td, "a.svg"))
            self.assertFalse(b["growth"]["available"])  # прошлый прогон моложе 5.6 суток
            # ворота через CLI: тот же кандидат против себя - принять; плохой - отклонить
            self.assertEqual(mb.main(["gate", "--candidate", os.path.join(td, "b.json"), "--baseline", os.path.join(td, "a.json")]), 0)
            bad = FakeCore(oracle(suite, 11, "evasive"))
            try:
                mb.main(["run", "--url", bad.url, "--split", "all", "--seed", "11", "--sleep-scale", "0", "--out", os.path.join(td, "c.json")])
            finally:
                bad.close()
            self.assertEqual(mb.main(["gate", "--candidate", os.path.join(td, "c.json"), "--baseline", os.path.join(td, "a.json")]), 1)
            self.assertEqual(mb.main(["compare", os.path.join(td, "c.json"), os.path.join(td, "a.json")]), 1)
            self.assertEqual(mb.main(["gate", "--candidate", os.path.join(td, "нет.json")]), 2)
            self.assertEqual(mb.main(["radar", os.path.join(td, "b.json"), "--svg", os.path.join(td, "r.svg")]), 0)

    def test_cli_dead_gateway_exit_2(self):
        self.assertEqual(mb.main(["run", "--url", "http://127.0.0.1:9", "--axes", "reason", "--sleep-scale", "0"]), 2)

    def test_cli_validate_and_contam(self):
        self.assertEqual(mb.main(["validate"]), 0)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "t.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write('{"text": "совсем другое"}\n')
            self.assertEqual(mb.main(["contam", "--train", p]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
