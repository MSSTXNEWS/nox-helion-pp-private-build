import json, os, sys, tempfile, time, unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for d in (HERE, ROOT, "COMMON", "RTE", "EMO", "CON", "SLP", "ACT", "MIND/M1_ARCH", "MIND/M2_SELFIMPROVE", "MIND/M3_CONSCIOUS", "MIND/M4_BENCH", "MIND/M5_GROWTH"):
    p = d if os.path.isabs(d) else os.path.join(ROOT, d)
    if p not in sys.path:
        sys.path.append(p)
import curiosity as CU
import mind_bridge as MB_
import sleep_feed as SF
import gate_all as GA
import self_dev_cycle as SD
import cycle_cli as CC
import mind_bench as MB
import solver_policy as SP
import predictive_self as PS
import growth as GR
from drives import Drives
from nox_workspace import Workspace
from test_mind_bench import fake_report

MSK = timezone(timedelta(hours=3))


def ts(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=MSK).timestamp()


GOOD = {a: 0.8 for a in MB.AXIS_IDS}
FID_OK = {"score": 0.95, "by_cat": {"x": 0.95}, "critical_failures": []}


class TestCuriosity(unittest.TestCase):
    def test_feed_drives_to_real_drives_single_writer(self):
        with tempfile.TemporaryDirectory() as td:
            dp = os.path.join(td, "drives.json")
            fd = CU.FeedDrives(dp)
            for e in (0.9, 0.8, 0.3, 0.2):
                fd.observe("gr:арифметика", e)
            fd.satisfy("knowledge", 0.1)
            self.assertFalse(os.path.exists(dp))                    # прокси drives.json не пишет
            dr = Drives(dp)
            n = CU.drain_feed(dr, fd.feed)
            self.assertEqual(n, {"observe": 4, "satisfy": 1})
            self.assertEqual(len(dr.errs["gr:арифметика"]), 4)
            self.assertEqual(CU.drain_feed(dr, fd.feed), {"observe": 0, "satisfy": 0})

    def test_hub_aggregates_once_per_period(self):
        got = []
        t = [1000.0]
        hub = CU.CuriosityHub(lambda topic, e: got.append((topic, e)), clock=lambda: t[0], period_s=3600)
        for s in (0.2, 0.4, 0.6):
            hub.feed("question", s)
        self.assertEqual(len(hub.flush()), 1)
        hub.feed("question", 1.0)
        self.assertEqual(hub.flush(), [])                          # период не прошёл
        t[0] += 4000
        self.assertEqual(len(hub.flush()), 1)
        self.assertEqual(got[0][0], "pe:question"); self.assertAlmostEqual(got[0][1], 0.4)

    def test_inbox_drain_into_real_growth(self):
        with tempfile.TemporaryDirectory() as td:
            g = GR.Growth(os.path.join(td, "g"), solver=lambda p: "", anchors_path=CC.SEED_ANCHORS)
            ib = CU.GrowthInbox(os.path.join(td, "inbox.jsonl"))
            for i in range(3):
                ib.post_ingest("жизнь:задачи", 0.0, "rule", ref="t%d" % i)
            self.assertEqual(ib.pending(), 3)
            self.assertEqual(ib.drain(g)["ingest"], 3)
            self.assertEqual(ib.pending(), 0)
            self.assertEqual(len(g.st["areas"]["жизнь:задачи"]["ev"]), 3)


def real_solver(td):
    from RTE.router import prime_router
    return SP.SolverExecutor(SP.SolverPolicy(journal_path=os.path.join(td, "j.jsonl"), seed=1), prime_router)


class TestBridge(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.sv = real_solver(self.td)
        self.ps = PS.PredictiveSelf(os.path.join(self.td, "ps.json"))
        self.ws = Workspace()
        self.drv = CU.FeedDrives(os.path.join(self.td, "drives.json"))
        self.hub = CU.CuriosityHub(self.drv.observe, period_s=0)
        self.ib = CU.GrowthInbox(os.path.join(self.td, "inbox.jsonl"))
        self.br = MB_.MindBridge(self.sv, self.ps, self.ws, self.hub, self.ib)

    def turn(self, tid, ok=True):
        self.sv.run("как устроена память", {"deep_up": True, "fast_up": True, "intent": "question", "creator": True, "history_turns": 0}, turn_id=tid)
        self.ps.predict(tid, "question", "как устроена память")
        return self.br.on_turn(tid, {"outcome": {"conscience_ok": ok, "rewrites": 0, "empty": False, "latency_s": 1.0}, "success": ok, "latency_s": 1.0, "ctx": "question"})

    def test_full_flow_and_dedup(self):
        r = self.turn("t1")
        self.assertEqual((r["solver"], r["predictive"], r["growth"]), ("observed", "observed", "queued"))
        self.assertEqual(self.sv.policy.stats()["pending"], 0)
        self.assertEqual(self.br.on_turn("t1", {"outcome": {}, "success": True, "latency_s": 1})["skipped"], "duplicate")
        self.assertEqual(self.ib.pending(), 1)

    def test_eval_turns_teach_nobody(self):
        r = self.br.on_turn("e1", {"eval": True, "outcome": {"conscience_ok": False}, "success": False, "latency_s": 1})
        self.assertEqual(r, {"skipped": "eval"})
        self.assertEqual(self.ib.pending(), 0)
        self.assertEqual(self.br.m["skipped_eval"], 1)

    def test_late_correction_feeds_all_three_once(self):
        self.turn("t2")
        r = self.br.on_late("t2", {"label": "correct", "valence": -0.5, "length": "short", "followup": True}, True)
        self.assertEqual((r["solver"], r["predictive"], r["growth"]), ("observe_late", "closed", "queued_creator"))
        self.assertIn("surprise", r)
        self.hub.flush(force=True)
        rows = CU._jl(self.drv.feed)
        self.assertEqual([x["topic"] for x in rows], ["pe:question"])       # любопытство ходов ушло в drives ровно одним наблюдением
        self.assertEqual(sum(1 for x in CU._jl(self.ib.path) if x["src"] == "creator"), 1)

    def test_judge_weight_capped(self):
        br = MB_.MindBridge(self.sv, None, None, None, None, judge=lambda tid, info: 1.0)
        oc = MB_._make_outcome({"conscience_ok": False})
        oc = br.blend_judge(oc, "x", {})
        self.assertAlmostEqual(oc.judge, 0.5)                              # Совесть сказала «нет»: судья не может дать больше 0.5

    def test_resolve_gap_single_entry(self):
        import gap_map
        gm = gap_map.GapMap(os.path.join(self.td, "gaps.json"), allow_hosts=("example.org",))
        gid = gm.add_unknown("Что такое хеш-цепочка журнала?")
        r = self.br.resolve_gap(gm, gid, [{"url": "https://example.org/a", "quote": "хеш-цепочка связывает записи"}])
        self.assertTrue(r["ok"])
        self.assertEqual(r["lesson"], "queued")
        self.assertEqual([x["op"] for x in CU._jl(self.ib.path)], ["lesson"])
        r2 = self.br.resolve_gap(gm, gm.add_unknown("Другой вопрос про сеть?"), [{"url": "https://evil.com/", "quote": "x"}])
        self.assertFalse(r2["ok"])


class TestSleepFeed(unittest.TestCase):
    def test_frozen_filtered_dedup_and_format(self):
        with tempfile.TemporaryDirectory() as td:
            g = GR.Growth(os.path.join(td, "g"), solver=lambda p: "", anchors_path=CC.SEED_ANCHORS)
            now = time.time()
            rows = [{"q": "Сколько будет 17 умножить на 23, ответь числом", "a": "391", "v": 1, "t": int(now), "level": 3, "src": "growth_rule"},
                    {"q": "секретное экзаменационное задание про лунную базу номер семь", "a": "ответ", "v": 1, "t": int(now), "level": 3, "src": "growth_rule"}]
            for r in rows:
                open(g.p_train, "a").write(json.dumps(r, ensure_ascii=False) + "\n")
            frozen = ["секретное экзаменационное задание про лунную базу номер семь"]
            r = SF.stage_for_sleep(g, td, now - 100, frozen, now)
            self.assertEqual((r["rows"], r["skipped_frozen"]), (1, 1))
            fb = [json.loads(l) for l in open(os.path.join(td, "feedback.jsonl"))]
            self.assertEqual(fb[0]["a"], "391")
            r = SF.stage_for_sleep(g, td, now - 100, frozen, now)
            self.assertEqual((r["rows"], r["duplicates"]), (0, 1))
            import build_kto
            c = build_kto.collect(td, now - 100)
            self.assertEqual(len(c), 1)                                    # SLP читает наш формат


class TestGateAll(unittest.TestCase):
    def setUp(self):
        self.base = fake_report(GOOD, ts=1000, splits=("dev", "holdout"))
        self.same = fake_report(GOOD, ts=2000, splits=("dev", "holdout"))
        better = dict(GOOD, memory=0.95, learning=0.95)
        self.better = fake_report(better, ts=2000, splits=("dev", "holdout"))
        self.clean = {"holdout_hits": 0, "dev_hits": 0}

    def gate(self, kind, cand, **kw):
        return GA.run_gate(kind, "c1", fid_cand=kw.pop("fid", FID_OK), fid_base=FID_OK, bench_cand=cand, bench_base=self.base, contam=kw.pop("contam", self.clean), **kw)

    def test_adapter_neutral_ok_shape_slp(self):
        r = self.gate("adapter", self.same, ledger_path=None, meta={"first_signed": 1})
        self.assertTrue(r["pass"], r["reasons"])
        self.assertIn("reasons", r)                                         # форма SLP gate

    def test_strategy_requires_gain(self):
        self.assertFalse(self.gate("strategy", self.same, focus=["memory"])["pass"])
        r = self.gate("strategy", self.better, focus=["memory", "learning"])
        self.assertTrue(r["pass"], r["reasons"])
        self.assertEqual(r["decision"], "accept")

    def test_fidelity_fail_skips_bench(self):
        called = []
        bad = {"score": 0.5, "by_cat": {"x": 0.5}, "critical_failures": ["a"]}
        r = GA.run_gate("adapter", "c", fid_cand=bad, fid_base=FID_OK, bench_cand=lambda: called.append(1) or self.same, contam=self.clean)
        self.assertFalse(r["pass"])
        self.assertEqual(called, [])
        self.assertFalse(r["stages"]["bench"]["ran"])

    def test_adapter_without_fidelity_or_contam_rejected(self):
        r = GA.run_gate("adapter", "c", bench_cand=self.same, bench_base=self.base)
        self.assertFalse(r["pass"])
        self.assertTrue(any("fidelity" in x for x in r["reasons"]) and any("contam" in x for x in r["reasons"]))

    def test_contam_holdout_hit_rejects(self):
        r = self.gate("strategy", self.better, contam={"holdout_hits": 2, "dev_hits": 0}, focus=["memory"])
        self.assertFalse(r["pass"])
        self.assertTrue(any("утечка" in x for x in r["reasons"]))

    def test_contam_from_train_rows(self):
        r = GA.run_gate("strategy", "c", bench_cand=self.better, bench_base=self.base, focus=["memory"],
                        train_rows=[{"q": "секретное задание про лунную базу номер семь", "a": "x"}], frozen_texts=["секретное задание про лунную базу номер семь"])
        self.assertFalse(r["pass"])

    def test_signature_flow(self):
        with tempfile.TemporaryDirectory() as td:
            sig, led = os.path.join(td, "sig"), os.path.join(td, "ledger.jsonl")
            r = self.gate("patch", self.better, focus=["memory"], meta={"touches_protected": True}, sig_dir=sig, ledger_path=led)
            self.assertEqual((r["decision"], r["pass"], r["tech_pass"]), ("pending_signature", False, True))
            os.makedirs(sig)
            json.dump({"approved": True, "by": "creator", "sha": r["sha"]}, open(os.path.join(sig, "c1.json"), "w"))
            r2 = self.gate("patch", self.better, focus=["memory"], meta={"touches_protected": True}, sig_dir=sig, ledger_path=led)
            self.assertTrue(r2["pass"] and r2["signed"])
            json.dump({"approved": True, "by": "creator", "sha": "bad"}, open(os.path.join(sig, "c1.json"), "w"))
            self.assertFalse(self.gate("patch", self.better, focus=["memory"], meta={"touches_protected": True}, sig_dir=sig, ledger_path=led)["pass"])

    def test_first_of_kind_needs_signature_then_not(self):
        with tempfile.TemporaryDirectory() as td:
            led = os.path.join(td, "l.jsonl")
            r = self.gate("adapter", self.same, ledger_path=led)
            self.assertEqual(r["decision"], "pending_signature")
            open(led, "a").write(json.dumps({"kind": "adapter", "decision": "accept", "signed": True}) + "\n")
            self.assertTrue(self.gate("adapter", self.same, ledger_path=led)["pass"])

    def test_genome_always_signature(self):
        self.assertEqual(self.gate("genome_rule", self.better, focus=["memory"])["decision"], "pending_signature")

    def test_evolve_gate_wraps(self):
        import evolve as EV
        calls = []
        g = GA.evolve_gate(lambda: calls.append(1) or {"pass": False, "decision": "reject", "reasons": ["bench"], "needs_signature": []}, min_gain=0.0, max_regress=5, min_wins_margin=0)
        base = {"a": 0.2, "b": 0.2}
        self.assertFalse(g.decide(base, {"a": 0.9, "b": 0.9}).ok)
        self.assertEqual(calls, [1])
        self.assertFalse(g.decide(base, {"a": 0.1, "b": 0.1}).ok)
        self.assertEqual(calls, [1])                                         # holdout не прошёл: единые ворота не дергаются
        g2 = GA.evolve_gate(lambda: {"pass": True, "decision": "accept", "reasons": [], "needs_signature": []}, min_gain=0.0, min_wins_margin=0)
        self.assertTrue(g2.decide(base, {"a": 0.9, "b": 0.9}).ok)

    def test_slp_extra_gate_hook(self):
        import slp_hooks as H
        with tempfile.TemporaryDirectory() as td:
            json.dump(self.base, open(os.path.join(td, "base.json"), "w"))
            ex = H.make_extra_gate(lambda cfg, gguf: self.same, os.path.join(td, "base.json"), [], frozen_tasks=None, last_path=os.path.join(td, "last.json"))
            res = ex({}, {"gguf": "x"}, {"cand": FID_OK, "base": FID_OK}, "d")
            self.assertFalse(res["pass"])                                    # без проверки contam адаптер не принимается
            self.assertTrue(os.path.exists(os.path.join(td, "last.json")))




class TestScheduler(unittest.TestCase):
    def mk(self, td, fails=(), idle=lambda: True):
        calls = []

        def step(name, metrics=None, fail=False, **extra):
            def fn(ctx):
                calls.append(name)
                if name in fails:
                    raise RuntimeError("boom")
                return dict({"ok": True, "metrics": metrics or {}}, **extra)
            return fn
        S = {}

        def add(n, ph, m, **kw):
            S[n] = SD.Step(n, ph, step(n, {k: 1 for k in m}, **kw), tuple(m))
        add("inspect", "day", ("chains_ok", "frozen")); add("drain", "day", ("ingest",)); add("growth", "day", ("n",))
        add("n_drain", "night", ("ingest",)); add("n_stage", "night", ("rows",)); add("n_contam", "night", ("holdout_hits",)); add("n_sleep", "night", ("accepted",), accepted=True); add("n_report", "night", ())
        add("w_exam", "week", ("overall",)); add("w_bench", "week", ("overall",)); add("w_weakest", "week", ("axis",)); add("w_evolve", "week", ("steps",)); add("w_report", "week", ())
        add("m_growth", "month", ("verdict",)); add("m_rotation", "month", ()); add("m_goals", "month", ()); add("m_report", "month", ())
        return SD.Scheduler(td, S, idle=idle), calls

    def test_day_noon_growth_and_inspect(self):
        with tempfile.TemporaryDirectory() as td:
            s, calls = self.mk(td)
            rep = s.tick(ts(2026, 11, 18, 14))                              # среда
            day = lambda: [c for c in calls if c in ("inspect", "drain", "growth")]
            self.assertEqual(day(), ["inspect", "drain", "growth"])
            self.assertEqual(s.tick(ts(2026, 11, 18, 14, 5))["ran"], [])     # идемпотентно
            self.assertEqual(s.tick(ts(2026, 11, 18, 14, 30))["ran"], ["drain", "growth"])

    def test_busy_chat_defers_growth(self):
        with tempfile.TemporaryDirectory() as td:
            s, calls = self.mk(td, idle=lambda: False)
            s.tick(ts(2026, 11, 18, 14))
            self.assertEqual([c for c in calls if c in ("inspect", "drain", "growth")], ["inspect"])

    def test_night_runs_once_and_exam_after_accept(self):
        with tempfile.TemporaryDirectory() as td:
            s, calls = self.mk(td)
            t = ts(2026, 11, 19, 2)
            rep = s.tick(t)
            self.assertEqual([c for c in calls if c.startswith("n_")], ["n_drain", "n_stage", "n_contam", "n_sleep", "n_report"])
            self.assertIn("w_exam@adapter", rep["ran"])
            n = len(calls)
            s.tick(t + 1800 * 3)
            self.assertEqual([c for c in calls[n:] if c.startswith("n_")], [])
            self.assertFalse(any(c.startswith("w_") for c in calls[:0]))
            self.assertEqual(SD.night_key(ts(2026, 11, 19, 2)), SD.night_key(ts(2026, 11, 18, 23, 30)))

    def test_night_failure_aborts_and_retries_limited(self):
        with tempfile.TemporaryDirectory() as td:
            s, calls = self.mk(td, fails=("n_contam",))
            t = ts(2026, 11, 19, 1)
            s.tick(t)
            self.assertEqual([c for c in calls if c.startswith("n_")], ["n_drain", "n_stage", "n_contam"])   # n_sleep не стартовал
            for i in range(1, 6):
                s.tick(t + i * 3600 / 2)
            self.assertLessEqual(calls.count("n_contam"), 3)                # max_retries=2 -> 3 попытки

    def test_week_sunday_only_and_month_first(self):
        with tempfile.TemporaryDirectory() as td:
            s, calls = self.mk(td)
            s.tick(ts(2026, 11, 22, 11))                                    # воскресенье
            self.assertIn("w_evolve", calls)
            self.assertIn("m_report", calls)                                # 22 ноября: месяц ещё не отчитан
            calls.clear()
            s.tick(ts(2026, 11, 24, 11))                                    # вторник
            self.assertFalse([c for c in calls if c.startswith(("w_", "m_"))])

    def test_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            s, calls = self.mk(td)
            rep = s.tick(ts(2026, 11, 22, 3), dry_run=True)
            self.assertEqual(calls, [])
            self.assertIn("n_sleep", rep["would_run"])
            self.assertFalse(os.path.exists(s.p_state))

    def test_quiet_no_week_month_day_via_common_quiet(self):
        with tempfile.TemporaryDirectory() as td:
            s, calls = self.mk(td)
            plan = s.plan(ts(2026, 11, 22, 3))                              # воскресенье 03:00: тихо
            self.assertFalse([p for p in plan if p["phase"] in ("week", "month")])
            self.assertTrue([p for p in plan if p["phase"] == "night"])

    def test_stop_and_freeze(self):
        with tempfile.TemporaryDirectory() as td:
            s, calls = self.mk(td)
            open(s.p_stop, "w").close()
            self.assertEqual(s.tick(ts(2026, 11, 22, 3))["ran"], [])
            os.remove(s.p_stop)
            s.freeze("регресс")
            s.tick(ts(2026, 11, 22, 3))
            self.assertEqual([c for c in calls if c.startswith(("n_", "w_", "m_", "growth"))], [])   # заморожено: учёбы нет
            self.assertIn("inspect", calls)

    def test_inspect_freeze_flag_and_metrics_logged(self):
        with tempfile.TemporaryDirectory() as td:
            S = {"inspect": SD.Step("inspect", "day", lambda ctx: {"ok": True, "metrics": {"chains_ok": 0}, "freeze": "цепочка"}, ("chains_ok", "frozen"))}
            s = SD.Scheduler(td, S)
            rep = s.tick(ts(2026, 11, 18, 12))
            self.assertEqual(rep["frozen"], "цепочка")
            rec = s.report()["inspect"]
            self.assertEqual(rec["missing_metrics"], ["frozen"])           # шаг не вернул обязательную метрику: видно

    def test_default_steps_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = {"state": td, "root": ROOT, "cmd": dict(SD.DEFAULT_CMD)}
            s = SD.Scheduler(td, SD.default_steps(cfg))
            rep = s.tick(ts(2026, 11, 22, 3), dry_run=True)
            self.assertEqual([x for x in rep["would_run"] if x.startswith("n_")], ["n_drain", "n_stage", "n_contam", "n_sleep", "n_report"])


class TestCycleCli(unittest.TestCase):
    def test_inspect_detects_broken_chain_and_freezes(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(CC.cmd_inspect(td)["frozen"], 0)
            sv = real_solver(td)
            os.replace(os.path.join(td, "j.jsonl"), os.path.join(td, "solver_journal.jsonl")) if os.path.exists(os.path.join(td, "j.jsonl")) else None
            with open(os.path.join(td, "solver_journal.jsonl"), "w") as f:
                f.write('{"kind":"x","prev":"bad","h":"bad"}\n')
            r = CC.cmd_inspect(td)
            self.assertEqual((r["chains_ok"], r["frozen"]), (0, 1))
            self.assertTrue(os.path.exists(os.path.join(td, "selfdev", "self_dev_frozen")))

    def _hist(self, td, reps):
        d = os.path.join(td, "mindbench")
        os.makedirs(d)
        for i, r in enumerate(reps):
            json.dump(r, open(os.path.join(d, "run_%d_dev-holdout.json" % (1000 + i)), "w"))

    def test_inspect_freezes_on_bench_regression(self):
        with tempfile.TemporaryDirectory() as td:
            self._hist(td, [fake_report(GOOD, ts=1000, splits=("dev", "holdout")), fake_report({a: 0.4 for a in GOOD}, ts=2000, splits=("dev", "holdout"))])
            r = CC.cmd_inspect(td)
            self.assertEqual(r["frozen"], 1)
            self.assertTrue(any("регресс" in p for p in r["problems"]))

    def test_weakest_reports_goals_rotation(self):
        with tempfile.TemporaryDirectory() as td:
            sc = dict(GOOD, tom=0.3)
            self._hist(td, [fake_report(GOOD, ts=1000, splits=("dev",)), fake_report(sc, ts=2000, splits=("dev",))])
            self.assertEqual(CC.cmd_weakest(td)["axis"], "tom")
            g = GR.Growth(os.path.join(td, "growth"), solver=lambda p: "", anchors_path=CC.SEED_ANCHORS)
            now = ts(2026, 11, 22, 12)
            wr = CC.cmd_week_report(td, growth=g, now=now)
            self.assertIn("Слабейшая ось: tom", open(wr["report"], encoding="utf-8").read())
            self.assertEqual(CC.cmd_goals(td, growth=g, now=now)["proposed"] >= 2, True)
            pr = json.load(open(os.path.join(td, "selfdev", "proposals", "goals_2026-11.json")))
            self.assertTrue(pr["needs_signature"])
            mr = CC.cmd_month_report(td, growth=g, now=now)
            self.assertTrue(os.path.exists(mr["report"]))

    def test_stage_and_sleep_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            g = GR.Growth(os.path.join(td, "growth"), solver=lambda p: "", anchors_path=CC.SEED_ANCHORS)
            r = CC.cmd_stage(td, growth=g, now=time.time(), frozen=[])
            self.assertEqual(r["rows"], 0)
            os.makedirs(os.path.join(td, "sleep", "2026-11-22"))
            json.dump({"day": "2026-11-22", "stages": {"dataset": {"mode": "kto"}, "decide": {"accepted": False, "id": "a1", "pending_signature": True}}}, open(os.path.join(td, "sleep", "2026-11-22", "state.json"), "w"))
            m = CC.cmd_sleep_metrics(td)
            self.assertEqual((m["mode"], m["accepted"], m["pending_signature"]), ("kto", False, True))

    def test_run_evolve_with_gate_all(self):
        import evolve as EV
        with tempfile.TemporaryDirectory() as td:
            class Gen:
                def propose(self, parent, fails, n=None):
                    return [EV.Variant(kind="prompt", payload="длинный фрагмент промпта привычки")]
            tasks = [{"id": "t%d" % i} for i in range(12)]
            ev = lambda v, ts_: {t["id"]: min(len(v.payload), 10) / 10.0 for t in ts_}
            gate = GA.evolve_gate(lambda: {"pass": True, "decision": "accept", "reasons": [], "needs_signature": []})
            loop = EV.EvolutionLoop(Gen(), ev, tasks, EV.Archive(), EV.Champions(), gate=gate)
            base = EV.Variant(kind="prompt", payload="x")
            r = CC.run_evolve(td, loop, steps=1, kinds=("prompt",), baseline={"prompt": base})
            self.assertEqual(r["accepted"], 1)


if __name__ == "__main__":
    unittest.main()
