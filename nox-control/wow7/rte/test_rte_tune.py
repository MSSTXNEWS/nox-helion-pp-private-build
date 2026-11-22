import asyncio, json, os, tempfile, time, unittest
import router as R, tune as T, drafts as D

NIGHT = 1_700_000_000 - (1_700_000_000 + 3 * 3600) % 86400
NOW = NIGHT + 7 * 86400 + 2 * 3600          # 02:00 МСК


def write_turn(d, i, t0, text, ttft=10.0, tps=2.0, n=30, status="done", tier="deep"):
    evs = [{"seq": 1, "type": "meta", "t": t0, "text": text, "conversation_id": "c"},
           {"seq": 2, "type": "meta", "t": t0 + 0.1, "plan": {"tier": tier}}]
    t = t0 + ttft
    for k in range(n):
        evs.append({"seq": 3 + k, "type": "delta", "stage": "deep", "t": t + k / tps, "text": "x"})
    evs.append({"seq": 3 + n, "type": status, "t": t + n / tps})
    with open(os.path.join(d, "t-%04d.jsonl" % i), "w") as f:
        f.write("\n".join(json.dumps(e) for e in evs) + "\n")


def fill(d, n, **kw):
    for i in range(n):
        write_turn(d, i, NOW - 3600 * (i + 1) - 86400 * (i % 5), kw.pop("text", None) or "расскажи про вопрос номер %d подробно" % i, **kw)


class TTune(unittest.TestCase):
    def setUp(s): s.d = tempfile.mkdtemp(); s.out = os.path.join(s.d, "router_thresholds.json")

    def test_read_turn_metrics(s):
        write_turn(s.d, 1, NOW - 100, "привет всем", ttft=12.0, tps=2.0, n=21)
        t = T.read_turn(os.path.join(s.d, "t-0001.jsonl"))
        s.assertAlmostEqual(t["ttft_s"], 12.0, places=1); s.assertAlmostEqual(t["tps"], 2.0, places=1); s.assertEqual(t["text"], "привет всем")

    def test_insufficient_data_no_file(s):
        fill(s.d, 5)
        r = T.tune(s.d, s.out, NOW)
        s.assertEqual(r["status"], "insufficient_data"); s.assertFalse(os.path.exists(s.out))

    def test_applies_with_justification_and_prev(s):
        fill(s.d, 30, ttft=40.0, tps=1.5)
        r = T.tune(s.d, s.out, NOW)
        s.assertEqual(r["status"], "applied", r)
        d = json.load(open(s.out))
        s.assertEqual(d["think_budget_s"], 60.0)                         # 1.5*40
        s.assertEqual(d["wait_budget_s"], 370.0)                         # 1.2*(40+400/1.5)=368 -> 370
        s.assertEqual(d["measured"]["n"], 30); s.assertIn("TTFT", d["basis"])
        s.assertEqual(T.tune(s.d, s.out, NOW)["status"], "unchanged")
        # смена скорости -> новый файл, .prev хранит старый
        for f in os.listdir(s.d):
            if f.startswith("t-"): os.remove(os.path.join(s.d, f))
        fill(s.d, 30, ttft=100.0, tps=4.0)
        s.assertEqual(T.tune(s.d, s.out, NOW)["status"], "applied")
        s.assertTrue(os.path.exists(s.out + ".prev")); s.assertEqual(T.rollback(s.out)["status"], "rolled_back")
        s.assertEqual(json.load(open(s.out))["think_budget_s"], 60.0)
        s.assertEqual(R.tuned_config(s.out).think_budget_s, 60.0)

    def test_ab_rejects_worse(s):
        fill(s.d, 30, ttft=40.0, tps=1.5)
        calls = {"n": 0}
        def bad(plan, turn):
            calls["n"] += 1
            return 1.0 if calls["n"] % 2 else 0.0          # чётные вызовы = новая конфигурация -> хуже
        o = os.path.join(s.d, "other.json")
        r = T.tune(s.d, o, NOW, score_fn=bad)
        s.assertEqual(r["status"], "rejected_ab"); s.assertFalse(os.path.exists(o))

    def test_quiet_and_dry(s):
        fill(s.d, 30)
        s.assertEqual(T.tune(s.d, s.out, NOW + 10 * 3600)["status"], "skipped")
        s.assertEqual(T.tune(s.d, s.out, NOW, dry_run=True)["status"], "applied"); s.assertFalse(os.path.exists(s.out))

    def test_router_honors_tuned(s):
        long = "Проанализируй архитектуру, объясни почему так, сравни варианты и подумай глубоко над рисками"
        a = R.route(long, deep_tps=12.0)
        b = R.route(long, deep_tps=12.0, cfg=R.RouterConfig(think_budget_s=20.0))
        s.assertLess(b.think_budget, a.think_budget)


class TDrafts(unittest.TestCase):
    def setUp(s): s.d = tempfile.mkdtemp(); s.clock = [NOW]

    def test_similar_and_eligible(s):
        s.assertTrue(D.similar("Как включить режим экономии?", "как включить режим экономии"))
        s.assertTrue(D.similar("как поменять пароль в системе почты", "как поменять пароли в системе почты?"))
        s.assertFalse(D.similar("сколько будет 2+2 в степени", "сколько будет 3+2 в степени"))
        s.assertFalse(D.eligible("какая погода сегодня в москве"))
        s.assertFalse(D.eligible("ты помнишь что я говорил вчера"))
        s.assertFalse(D.eligible("привет"))

    def test_top_questions_threshold(s):
        T_ = [{"text": "как работает кэш префикса в llama", "status": "done"}, {"text": "Как работает кэш префикса в llama?", "status": "done"},
              {"text": "что такое квитанция остановки", "status": "done"}, {"text": "какая погода сегодня", "status": "done"}] * 1 + [{"text": "какая погода сегодня", "status": "done"}]
        r = D.top_questions(T_)
        s.assertEqual([q for q, n in r], ["как работает кэш префикса в llama"]); s.assertEqual(r[0][1], 2)

    def test_build_lookup_ttl_and_source_mark(s):
        for i in range(3): write_turn(s.d, i, NOW - 3600 * (i + 1), "как работает кэш префикса в llama")
        write_turn(s.d, 9, NOW - 500, "что-то редкое и единичное про луну")
        calls = []
        def gen(q): calls.append(q); return "Кэш префикса хранит KV для общего начала запроса, поэтому повторный запрос быстрее."
        r = D.build(s.d, gen, now=NOW)
        s.assertEqual((r["status"], len(r["made"]), calls), ("built", 1, ["как работает кэш префикса в llama"]))
        st = D.DraftStore(os.path.join(s.d, "drafts.json"), clock=lambda: s.clock[0])
        h = st.lookup("Как работает кэш префикса в llama?")
        s.assertIn("заготовлено ночью", h["text"]); s.assertIn("источник: GLM", h["text"])
        s.assertIsNone(st.lookup("как работает кэш у тостера"))
        s.assertEqual(D.build(s.d, gen, now=NOW)["kept"], 1); s.assertEqual(len(calls), 1)      # повторно не генерим
        s.clock[0] = NOW + 25 * 3600
        s.assertIsNone(st.lookup("как работает кэш префикса в llama"))                             # TTL 24 ч
        s.assertEqual(st.purge(), 0)

    def test_build_errors_quiet_dry_evaluate(s):
        for i in range(3): write_turn(s.d, i, NOW - 3600 * (i + 1), "как работает кэш префикса в llama")
        def boom(q): raise OSError("down")
        s.assertEqual(D.build(s.d, boom, now=NOW)["failed"][0]["err"], "OSError")
        s.assertEqual(D.build(s.d, boom, now=NOW + 11 * 3600)["status"], "skipped")
        s.assertEqual(D.build(s.d, lambda q: "ответ достаточно длинный для заготовки", now=NOW, dry_run=True)["status"], "dry")
        st = D.DraftStore(os.path.join(s.d, "drafts.json"), clock=lambda: NOW)
        st.put("как работает кэш префикса в llama", "Кэш префикса хранит KV общего начала запроса")
        ev = D.evaluate(st, [{"text": "как работает кэш префикса в llama", "answer": "Кэш префикса хранит KV общего начала"}, {"text": "другой вопрос про звёзды", "answer": "x"}])
        s.assertEqual(ev["instant_share"], 0.5); s.assertGreater(ev["parity"], 0.5)

    def test_pipeline_serves_draft_without_glm(s):
        import rte_server as S
        from fakes import FakeLLM
        from stream_hub import Hub
        async def go():
            deep = FakeLLM(); url = await deep.start()
            cfg = S.Cfg(gateway=url, deep_slots=url, fast="", state_dir=s.d, receipts_dir=s.d)
            pipe = S.Pipeline(cfg)
            pipe.drafts.clock = lambda: time.time()
            pipe.drafts.put("как работает кэш префикса в llama", "Кэш префикса хранит KV общего начала запроса.")
            hub = Hub(pipe, persist_dir=s.d)
            turn, st = hub.start_turn("c", "m1", "Как работает кэш префикса в llama?")
            await turn.task
            await deep.stop()
            return turn, deep
        turn, deep = asyncio.run(go())
        s.assertEqual(turn.status, "done"); s.assertEqual(deep.generations, 0)
        s.assertIn("заготовлено ночью", turn.text)
        s.assertEqual([e for e in turn.events if e["type"] == "delta"][0]["stage"], "draft")


if __name__ == "__main__":
    unittest.main()
