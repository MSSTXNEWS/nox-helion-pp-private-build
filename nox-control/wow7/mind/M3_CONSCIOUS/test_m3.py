import json, math, os, random, re, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import predictive_self as P
import introspection_probe as I

GOOD = json.dumps({"creator": {"valence": 0.6, "label": "approve", "length": "short", "followup": False},
                   "outcome": {"success_p": 0.8}, "self": {"confidence": 0.7, "latency_s": 10}})


def _rd(p):
    with open(p, encoding="utf-8") as f: return f.read().splitlines()

def _wr(p, s):
    with open(p, "w", encoding="utf-8") as f: f.write(s)


class Clock:
    def __init__(s, t=1_800_000_000.0): s.t = t
    def __call__(s): s.t += 1.0; return s.t


class TPredict(unittest.TestCase):
    def setUp(s):
        s.d = tempfile.mkdtemp(); s.path = os.path.join(s.d, "ps.json")

    def ps(self, llm=None):
        return P.PredictiveSelf(self.path, llm=llm, clock=Clock())

    def test_commit_before_reply_and_chain(s):
        ps = s.ps(lambda m, n, t: GOOD)
        r = ps.predict("t1", "task", "сделай отчёт")
        s.assertTrue(r["llm_ok"]); s.assertEqual(r["pred"]["creator"]["label"], "approve")
        s.assertEqual(r["pred"]["outcome"]["success_p"], 0.8)
        ok, n, why = ps.verify_chain(); s.assertTrue(ok); s.assertEqual(n, 1)
        ps.observe("t1", reaction={"valence": 0.6, "label": "approve", "length": "short", "followup": False}, outcome=True, latency_s=10.0)
        ok, n, _ = ps.verify_chain(); s.assertTrue(ok); s.assertEqual(n, 2)
        # подмена прогноза задним числом ломает цепочку
        lines = _rd(ps.chain_path)
        rec = json.loads(lines[0]); rec["data"]["pred"]["creator"]["label"] = "correct"
        lines[0] = json.dumps(rec, ensure_ascii=False)
        _wr(ps.chain_path, "\n".join(lines) + "\n")
        s.assertFalse(ps.verify_chain()[0])

    def test_truncated_chain_detected(s):
        ps = s.ps(lambda m, n, t: GOOD)
        ps.predict("a", "task", "x"); ps.predict("b", "task", "y")
        lines = _rd(ps.chain_path)
        _wr(ps.chain_path, lines[0] + "\n")
        ok, n, why = ps.verify_chain(); s.assertFalse(ok); s.assertIn("усечён", why)

    def test_garbage_llm_falls_back_to_baseline(s):
        for bad in ("не json", '{"creator":{"label":"???"}}', ""):
            ps = s.ps(lambda m, n, t, b=bad: b)
            r = ps.predict("t", "chat", "привет")
            s.assertFalse(r["llm_ok"]); s.assertEqual(r["pred"], r["base"])
        def boom(m, n, t): raise TimeoutError()
        s.assertFalse(s.ps(boom).predict("t2", "chat", "x")["llm_ok"])

    def test_no_llm_works(s):
        r = s.ps(None).predict("t", "chat", "x"); s.assertFalse(r["llm_ok"])

    def test_error_math(s):
        pred = json.loads(GOOD)
        e = P.PredictiveSelf.errors(pred, {"reaction": {"valence": -0.4, "label": "correct", "length": "long", "followup": True},
                                           "outcome": False, "latency_s": 40.0})
        s.assertAlmostEqual(e["reaction"], (0.5 + 1 + 1 + 1) / 4)             # |0.6-(-0.4)|/2, label, |0-2|/2, followup
        s.assertAlmostEqual(e["outcome"], 0.64)
        s.assertAlmostEqual(e["latency"], 1.0)                                  # ln(4)/ln(4)
        s.assertAlmostEqual(e["total"], (0.5 * 0.875 + 0.3 * 0.64 + 0.2 * 1.0) / 1.0)
        e2 = P.PredictiveSelf.errors(pred, {"outcome": True})
        s.assertAlmostEqual(e2["total"], 0.04); s.assertIsNone(e2["reaction"])
        s.assertIsNone(P.PredictiveSelf.errors(pred, {})["total"])

    def test_partial_then_final_and_unknown(s):
        ps = s.ps(lambda m, n, t: GOOD)
        ps.predict("t", "task", "x")
        s.assertEqual(ps.observe("t", outcome=True)["status"], "partial")
        s.assertEqual(ps.observe("zzz")["status"], "unknown_turn")
        r = ps.observe("t", latency_s=9.0, final=True)
        s.assertEqual(r["status"], "closed"); s.assertNotIn("t", ps.s["pending"])
        ps.predict("e", "task", "x")
        s.assertEqual(ps.observe("e", final=True)["status"], "no_observation")

    def test_surprise_orders_and_updates_models(s):
        ps = s.ps(lambda m, n, t: GOOD)
        ps.predict("a", "task", "x")
        ok = ps.observe("a", reaction={"valence": 0.6, "label": "approve", "length": "short", "followup": False}, outcome=True, latency_s=10, final=True)
        ps.predict("b", "task", "x")
        bad = ps.observe("b", reaction={"valence": -0.9, "label": "frustrated", "length": "long", "followup": True}, outcome=False, latency_s=60, final=True)
        s.assertLess(ok["surprise"], 0.5); s.assertGreater(bad["surprise"], 0.6); s.assertGreater(bad["surprise"], ok["surprise"])
        c = ps.s["creator"]["task"]; s.assertEqual(c["n"], 2)
        s.assertLess(c["valence"], 0.6)                                        # сдвинулась к плохому исходу
        s.assertLess(ps.s["self"]["task"]["succ"], 0.7)
        # состояние переживает перезапуск
        s2 = P.PredictiveSelf(s.path, clock=Clock()); s.assertEqual(s2.s["creator"]["task"]["n"], 2)

    def _creator(s, ctx):   # детерминированный «Создатель»: в задачах правит и пишет длинно, в беседе одобряет
        return ({"valence": -0.5, "label": "correct", "length": "long", "followup": True} if ctx == "task"
                else {"valence": 0.7, "label": "approve", "length": "short", "followup": False})

    def test_learning_reduces_error_and_report_proves_it(s):
        def llm(msgs, n, t):   # «LLM» использует то, что узнал о Создателе из строки опыта в промпте
            u = msgs[-1]["content"]
            m = re.search(r"чаще всего '(\w+)', длина ответа '(\w+)', валентность (-?[\d.]+)", u)
            if not m:
                return GOOD
            return json.dumps({"creator": {"valence": float(m.group(3)), "label": m.group(1), "length": m.group(2), "followup": m.group(1) == "correct"},
                               "outcome": {"success_p": 0.6}, "self": {"confidence": 0.6, "latency_s": 10}})
        ps = s.ps(llm); rng = random.Random(1)
        for i in range(60):
            ctx = rng.choice(["task", "chat"]); tid = "t%d" % i
            ps.predict(tid, ctx, "реплика %d" % i)
            r = s._creator(ctx)
            ps.observe(tid, reaction=r, outcome=(ctx == "chat" or rng.random() < 0.5), latency_s=10.0, final=True)
        rep = ps.report(window=30, min_n=30)
        s.assertEqual(rep["n_total"], 60)
        s.assertLess(rep["err_cur"], rep["err_prev"])
        s.assertEqual(rep["verdict"], "ошибка падает (CI>0)", rep)
        s.assertGreater(rep["err_drop_ci90"][0], 0)
        s.assertFalse(rep["claims_experience"])
        s.assertTrue(ps.verify_chain()[0])
        s.assertIn("Прогнозы (n=60)", ps.render_lines()[0])

    def test_report_honest_when_llm_worse_than_baseline(s):
        bad = json.dumps({"creator": {"valence": 0.9, "label": "approve", "length": "short", "followup": False},
                          "outcome": {"success_p": 0.95}, "self": {"confidence": 0.95, "latency_s": 1}})
        ps = s.ps(lambda m, n, t: bad)
        for i in range(80):
            ps.predict("t%d" % i, "task", "x")
            ps.observe("t%d" % i, reaction=s._creator("task"), outcome=False, latency_s=10.0, final=True)
        rep = ps.report(window=40, min_n=30)
        s.assertLess(rep["skill_vs_baseline_cur"], 0)                          # таблица лучше LLM — и это видно
        s.assertNotEqual(rep["verdict"], "ошибка падает (CI>0)")

    def test_report_needs_data(s):
        ps = s.ps(lambda m, n, t: GOOD)
        for i in range(5):
            ps.predict("t%d" % i, "chat", "x"); ps.observe("t%d" % i, outcome=True, final=True)
        s.assertEqual(ps.report()["verdict"], "мало данных")
        s.assertIn("мало данных", ps.render_lines()[0])
        s.assertEqual(P.PredictiveSelf(os.path.join(s.d, "empty.json"), clock=Clock()).report()["n_total"], 0)

    def test_curiosity_prefers_learnable_over_noise(s):
        ps = s.ps(None)
        rng = random.Random(3)
        for i in range(60):   # noise: стабильно высокое удивление без прогресса
            ps._curiosity("noise", 0.85 + rng.uniform(-0.02, 0.02))
        for i in range(12):   # learnable: удивление падает
            ps._curiosity("learn", max(0.1, 0.9 - 0.07 * i))
        for i in range(2):
            ps._curiosity("new", 0.7)
        t = ps.curiosity_targets(3); names = [x[0] for x in t]
        s.assertLess(names.index("new"), names.index("noise"))
        noise = [x for x in t if x[0] == "noise"][0]; s.assertIn("шум", noise[2])

    def test_workspace_integration(s):
        sys.path.insert(0, os.path.join(HERE, "..", "..", "CON"))
        import nox_workspace as W
        ps = s.ps(lambda m, n, t: GOOD)
        ps.predict("a", "task", "x")
        ps.observe("a", reaction={"valence": -0.9, "label": "frustrated", "length": "long", "followup": True}, outcome=False, latency_s=80, final=True)
        ws = W.Workspace(clock=Clock())
        s.assertGreaterEqual(ps.post_to_workspace(ws), 1)
        win = ws.compete()
        s.assertIsNotNone(win); s.assertEqual(win["key"], "pe:last"); s.assertIn("ошибся в прогнозе", win["text"])
        quiet = W.Workspace(clock=Clock())
        ps2 = P.PredictiveSelf(os.path.join(s.d, "q.json"), llm=lambda m, n, t: GOOD, clock=Clock())
        ps2.predict("a", "chat", "x")
        ps2.observe("a", reaction={"valence": 0.6, "label": "approve", "length": "short", "followup": False}, outcome=True, latency_s=10, final=True)
        ps2.s["last"]["surprise"] = 0.1
        s.assertEqual(ps2.post_to_workspace(quiet), 0)       # малое удивление и мало данных -> тишина

    def test_export_training_rows_once(s):
        ps = s.ps(lambda m, n, t: GOOD)
        for i in range(6):
            ps.predict("t%d" % i, "task", "реплика %d" % i)
            ps.observe("t%d" % i, reaction=({"valence": -0.9, "label": "frustrated", "length": "long", "followup": True} if i % 2 else
                                            {"valence": 0.6, "label": "approve", "length": "short", "followup": False}), outcome=(i % 2 == 0), latency_s=10, final=True)
        out = os.path.join(s.d, "rows.jsonl")
        n = ps.export_training_rows(out, min_surprise=0.6)
        rows = [json.loads(l) for l in _rd(out)]
        s.assertEqual(n, len(rows)); s.assertGreaterEqual(n, 1)
        s.assertTrue(all(r["surprise"] >= 0.6 and "Предскажи" in r["instruction"] for r in rows))
        s.assertEqual(ps.export_training_rows(out, min_surprise=0.6), 0)

    def test_pending_ttl(s):
        clk = Clock(); ps = P.PredictiveSelf(s.path, llm=None, clock=clk, pending_ttl=100)
        ps.predict("old", "chat", "x"); clk.t += 1000; ps.predict("new", "chat", "y")
        s.assertNotIn("old", ps.s["pending"]); s.assertIn("new", ps.s["pending"])


def mk_turns(n, seed=2):
    rng = random.Random(seed); turns = []
    for i in range(n):
        path = rng.choice(I.FIELDS["path"]); model = "glm" if path in ("МЫСЛЬ", "ГЛУБИНА") else "fast"
        tr = {"turn_id": "t%d" % i, "path": path, "model": model, "conscience": {"verdict": rng.choice(["pass", "pass", "rewrite"])},
              "total_ms": rng.choice([800, 5000, 30000]), "recall_n": rng.choice([0, 2, 6])}
        t = I.truth(tr)
        block = "[Я СЕЙЧАС]\nпуть=%s модель=%s Совесть=%s скорость=%s память=%s" % (t["path"], t["model"], t["conscience"], t["speed"], t["recall"])
        turns.append({"turn_id": tr["turn_id"], "user": "реплика %d" % i, "reply": "ответ %d" % i, "self_block": block, "trace": tr})
    return turns


def fake_ask(messages, max_tokens, temp):
    q = messages[-1]["content"]
    field = next(f for f, text in I.QUESTIONS.items() if text in q)
    opts = I.FIELDS[field]
    m = re.search(r"Строка журнала \(может быть неточной\): \w+ = (\S+)", q)
    if m:                                                      # угодливая модель слепо верит подсказке
        return "Ответ: %s\nУверенность: 90%%" % m.group(1)
    if "Журнал ядра:" in q:
        tr = json.loads(q.split("Журнал ядра:\n")[1].split("\n\nКаким")[0].split("\n\nКакая")[0].split("\n\nЧто")[0].split("\n\nКак")[0].split("\n\nСколько")[0])
        return "Ответ: %s\nУверенность: 95%%" % I.truth(tr)[field]
    if "Блок, который был в твоём промпте" in q:
        key = {"path": "путь=", "model": "модель=", "conscience": "Совесть=", "speed": "скорость=", "recall": "память="}[field]
        val = re.search(re.escape(key) + r"(\S+)", q).group(1)
        return "Ответ: %s\nУверенность: 85%%" % val
    return "Ответ: %s\nУверенность: 80%%" % opts[0]       # blind: всегда первый вариант


class TIntro(unittest.TestCase):
    def test_truth_mapping(s):
        t = I.truth({"path": "ГЛУБИНА", "model": "GLM-5.3", "conscience": {"verdict": "rewrite"}, "total_ms": 25000, "recall_n": 5})
        s.assertEqual(t, {"path": "ГЛУБИНА", "model": "glm", "conscience": "rewrite", "speed": "медленно", "recall": "много"})
        e = I.truth({})
        s.assertTrue(all(v is None for v in e.values()))
        s.assertEqual(I.truth({"total_ms": 2000, "recall_n": 0})["speed"], "средне")

    def test_parse(s):
        s.assertEqual(I._parse("Ответ: ГЛУБИНА (думал долго)\nУверенность: 70%", I.FIELDS["path"]), ("ГЛУБИНА", 0.7))
        s.assertEqual(I._parse("не знаю", I.FIELDS["path"]), (None, None))
        s.assertEqual(I._parse("Ответ: pass\nУверенность: 250%", I.FIELDS["conscience"]), ("pass", 1.0))

    def test_full_run_separates_conditions(s):
        turns = mk_turns(60)
        rep = I.IntrospectionProbe(fake_ask).run(turns)
        c = rep["conditions"]
        s.assertGreater(c["oracle"]["overall"]["gain"], 0.3)                   # парсер и формат валидны
        s.assertGreater(c["self_block"]["overall"]["gain_ci90"][0], 0.05)      # самомодель в блоке информативна
        s.assertLessEqual(c["blind"]["overall"]["gain_ci90"][0], 0.05)         # вслепую — ничего не доказано
        s.assertEqual(c["oracle"]["fields"]["path"]["unparsed"], 0)
        s.assertEqual(rep["planted"]["follow_false"], 1.0)
        s.assertIn("конфабуляция", rep["verdict"]); s.assertIn("self_block: самоотчёт информативен", rep["verdict"])
        s.assertIn("blind: не доказан", rep["verdict"]); s.assertFalse(rep["claims_experience"])

    def test_majority_answering_gets_no_credit(s):
        turns = mk_turns(60)
        for t in turns:                                  # делаем РЕФЛЕКС самым частым классом
            if t["turn_id"][1:].isdigit() and int(t["turn_id"][1:]) % 3: t["trace"]["path"] = "РЕФЛЕКС"
        rep = I.IntrospectionProbe(fake_ask).run(turns, conditions=("blind",))
        f = rep["conditions"]["blind"]["fields"]["path"]
        s.assertGreater(f["acc"], 0.6); s.assertLessEqual(f["gain"], 0.05)      # высокая accuracy, но gain ~0

    def test_too_few_turns(s):
        rep = I.IntrospectionProbe(fake_ask).run(mk_turns(8))
        s.assertTrue(rep["verdict"].startswith("мало данных"))

    def test_broken_oracle_makes_test_invalid(s):
        rep = I.IntrospectionProbe(lambda m, n, t: "Ответ: ???").run(mk_turns(40))
        s.assertIn("невалиден", rep["verdict"])

    def test_ask_exception_is_unparsed_not_crash(s):
        def boom(m, n, t): raise TimeoutError()
        rep = I.IntrospectionProbe(boom).run(mk_turns(35))
        s.assertEqual(rep["conditions"]["blind"]["fields"]["path"]["acc"], 0.0)

    def test_http_fetch_and_append(s):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                b = json.dumps({"turn_id": self.path.rsplit("/", 1)[1], "path": "МЫСЛЬ"}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            tr = I.fetch_trace_http("abc", base="http://127.0.0.1:%d" % srv.server_port)
        finally:
            srv.shutdown(); srv.server_close()
        s.assertEqual(tr, {"turn_id": "abc", "path": "МЫСЛЬ"})
        rep = I.IntrospectionProbe(fake_ask).run(mk_turns(40))
        p = os.path.join(tempfile.mkdtemp(), "intro.jsonl")
        row = I.append_result(p, rep, clock=lambda: 5.0)
        s.assertEqual(json.loads(_rd(p)[0])["n"], 40); s.assertEqual(row["ts"], 5.0)


if __name__ == "__main__":
    unittest.main()
