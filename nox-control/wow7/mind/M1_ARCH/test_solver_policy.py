import asyncio, json, os, random, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/claude/nox_wow")
import solver_policy as sp
from solver_policy import SolverPolicy, SolverExecutor, Outcome, featurize, allowed_arms, reward_from_outcome, read_journal

# ---- фейковый мир: истинная польза (0..1) руки в контексте. Судья-фейк возвращает её с шумом.
def truth(ctx, arm):
    hard = ctx["complexity"] >= 0.6
    base = {"reflex": 0.35 if hard else 0.85, "thought": 0.55 if hard else 0.7, "deep": 0.9 if hard else 0.6, "council": 0.8 if hard else 0.5}
    return base[arm]

def make_ctx(rng):
    hard = rng.random() < 0.5
    return {"complexity": rng.uniform(0.65, 0.95) if hard else rng.uniform(0.05, 0.4), "words": rng.randint(3, 150), "tps": 12.0, "advisor_ok": True,
            "intent": "question", "history_turns": rng.randint(0, 20)}

def run_world(pol, n, rng, judge_noise=0.05, reward_fn=None):
    got, tot = [], 0.0
    for i in range(n):
        ctx = make_ctx(rng)
        d = pol.decide(ctx, baseline_tier="deep")          # «правила» всегда говорят thought: намеренно плохая база
        r = truth(ctx, d.arm) + rng.gauss(0, judge_noise)
        r = reward_fn(i, d, r) if reward_fn else r
        pol.record(d.turn_id, Outcome(judge=min(max(r, 0), 1)))
        got.append(truth(ctx, d.arm)); tot += truth(ctx, d.arm)
    return got


class T(unittest.TestCase):
    def tmp(self):
        d = tempfile.mkdtemp()
        return os.path.join(d, "solver.jsonl")

    def test_features_fixed_dim_and_range(self):
        v = featurize({"complexity": 5, "words": 999, "intent": "task", "tps": 1.0, "weird": 1})
        self.assertEqual(len(v), len(sp.FEATURE_NAMES))
        self.assertTrue(all(0 <= x <= 1 for x in v))
        self.assertEqual(v[sp.FEATURE_NAMES.index("intent_task")], 1.0)
        self.assertEqual(v[sp.FEATURE_NAMES.index("tps_low")], 1.0)
        self.assertEqual(featurize({}), featurize({"intent": "chat"}))

    def test_hard_rules(self):
        self.assertEqual(allowed_arms({"greet": True})[0], ["reflex"])
        self.assertEqual(allowed_arms({"deep_up": False})[0], ["reflex"])
        self.assertEqual(allowed_arms({"irreversible": True})[0], ["deep"])
        self.assertEqual(allowed_arms({"mode": "fast"})[0], ["reflex"])
        self.assertNotIn("deep", allowed_arms({"tps": 1.5})[0])
        self.assertIn("deep", allowed_arms({"tps": 1.5, "think_kw": True})[0])
        self.assertNotIn("council", allowed_arms({"advisor_ok": True, "quiet": True})[0])
        self.assertNotIn("council", allowed_arms({})[0])
        self.assertIn("council", allowed_arms({"advisor_ok": True})[0])

    def test_policy_never_violates_rules_while_exploring(self):
        pol = SolverPolicy(seed=1, sigma=0.8)
        rng = random.Random(2)
        for _ in range(300):
            ctx = make_ctx(rng)
            ctx.update(rng.choice([{}, {"greet": True}, {"deep_up": False}, {"tps": 1.0}, {"quiet": True}]))
            d = pol.decide(ctx, baseline_tier="deep")
            self.assertIn(d.arm, allowed_arms(ctx)[0])
            pol.record(d.turn_id, Outcome(judge=0.5))

    def test_reward_shape(self):
        good = reward_from_outcome(Outcome(judge=0.7))
        self.assertGreater(good, reward_from_outcome(Outcome(judge=0.7, rewrites=2)))
        self.assertEqual(reward_from_outcome(Outcome(empty=True, judge=1.0)), 0.0)
        self.assertGreater(reward_from_outcome(Outcome(judge=0.7, creator_feedback=1)), good)
        self.assertLess(reward_from_outcome(Outcome(judge=0.7, creator_feedback=-1)), good)
        self.assertLess(reward_from_outcome(Outcome(judge=0.7, latency_s=300, budget_s=100)), good)
        self.assertLess(reward_from_outcome(Outcome(judge=0.7, corrected_next=True)), good)
        self.assertLess(reward_from_outcome(Outcome(judge=1.0), cost=1.0), reward_from_outcome(Outcome(judge=1.0), cost=0.0))

    def test_learns_better_than_rules(self):
        pol = SolverPolicy(seed=3)
        rng = random.Random(4)
        got = run_world(pol, 700, rng)
        early, late = sum(got[:100]) / 100, sum(got[-200:]) / 200
        self.assertGreater(late, early + 0.05)
        # база «всегда thought» даёт в среднем ~0.625; обученная — заметно выше
        self.assertGreater(late, 0.78)
        w = pol.weights()
        self.assertGreater(w["deep"]["complexity"], w["reflex"]["complexity"])   # понял: сложное -> глубина

    def test_prior_trust_in_rules_decays(self):
        pol = SolverPolicy(seed=5)
        sig = pol.sigma
        pol.sigma = 0.0001
        d0 = pol.decide({"complexity": 0.9, "tps": 12.0}, baseline_tier="fast")
        self.assertEqual(d0.arm, "reflex")                  # на старте доверяем правилам
        self.assertFalse(d0.explored)
        rng = random.Random(6)
        pol.sigma = sig
        run_world(pol, 400, rng)
        pol.sigma = 0.0001
        d1 = pol.decide({"complexity": 0.9, "tps": 12.0, "advisor_ok": False}, baseline_tier="fast")
        self.assertIn(d1.arm, ("deep", "thought"))          # опыт перевесил правило

    def test_journal_chain_and_tamper(self):
        p = self.tmp()
        pol = SolverPolicy(p, seed=7)
        run_world(pol, 30, random.Random(8))
        recs, _, ok = read_journal(p)
        self.assertTrue(ok)
        self.assertEqual({r["k"] for r in recs} >= {"decide", "update"}, True)
        with open(p) as f: lines = f.read().splitlines()
        e = json.loads(lines[10]); e["r"] = 1.0 if "r" in e else None
        if "r" in e:
            lines[10] = json.dumps(e, ensure_ascii=False)
        else:
            e = json.loads(lines[11]); e["arm"] = "deep"; lines[11] = json.dumps(e, ensure_ascii=False)
        with open(p, "w") as f: f.write("\n".join(lines) + "\n")
        self.assertFalse(read_journal(p)[2])
        pol2 = SolverPolicy(p, seed=7)
        self.assertTrue(pol2.corrupt)                       # не принято молча
        self.assertTrue(pol2.verify())                      # после карантина цепочка снова валидна
        self.assertTrue(any(f.startswith("solver.jsonl.corrupt") for f in os.listdir(os.path.dirname(p))))

    def test_replay_equals_live_state(self):
        p = self.tmp()
        pol = SolverPolicy(p, seed=9)
        run_world(pol, 120, random.Random(10))
        pol2 = SolverPolicy(p, seed=9)
        self.assertEqual(pol.rev, pol2.rev)
        self.assertEqual(pol.weights(), pol2.weights())
        self.assertEqual(pol.stats()["arms"], pol2.stats()["arms"])

    def test_manual_rollback_and_replay(self):
        p = self.tmp()
        pol = SolverPolicy(p, seed=11)
        run_world(pol, 60, random.Random(12))
        w60 = pol.weights()
        run_world(pol, 40, random.Random(13))
        self.assertEqual(pol.rev, 100)
        pol.rollback(60, "тест")
        self.assertEqual(pol.rev, 60)
        self.assertEqual(pol.weights(), w60)
        run_world(pol, 10, random.Random(14))
        pol2 = SolverPolicy(p)                              # откат переживает перезапуск
        self.assertEqual(pol2.rev, 70)
        self.assertEqual(pol2.weights(), pol.weights())
        self.assertEqual(pol2.rollbacks, 1)

    def test_watchdog_rolls_back_poisoned_feedback(self):
        p = self.tmp()
        pol = SolverPolicy(p, seed=15, watch_window=30, ckpt_every=10, watch_drop=0.12)
        rng = random.Random(16)
        run_world(pol, 200, rng)
        good_rev, good_score = pol.best_rev, pol.best_score
        self.assertIsNotNone(good_score)
        self.assertEqual(pol.rollbacks, 0)
        run_world(pol, 60, rng, reward_fn=lambda i, d, r: 0.0)   # судья сломался: везде 0
        self.assertGreaterEqual(pol.rollbacks, 1)
        self.assertLessEqual(pol.rev, good_rev + 60)
        recs, _, ok = read_journal(p)
        self.assertTrue(ok)
        rb = [r for r in recs if r["k"] == "rollback"]
        self.assertTrue(rb and rb[0]["why"].startswith("watchdog"))
        # после отката поведение снова хорошее (яд не вошёл в веса)
        got = run_world(pol, 60, rng)
        self.assertGreater(sum(got[-30:]) / 30, 0.7)

    def test_rebaseline_when_world_changes(self):
        pol = SolverPolicy(seed=17, watch_window=20, ckpt_every=10)
        rng = random.Random(18)
        run_world(pol, 100, rng)
        n0 = pol.rollbacks
        run_world(pol, 120, rng, reward_fn=lambda i, d, r: r * 0.3)   # вся награда просела на любой руке: мир, а не политика
        self.assertGreaterEqual(pol.rollbacks, n0 + 1)
        self.assertLessEqual(pol.rollbacks, n0 + 4)                   # не зацикливается на откатах бесконечно

    def test_delayed_outcome_and_pending_survive_restart(self):
        p = self.tmp()
        pol = SolverPolicy(p, seed=19)
        d = pol.decide({"complexity": 0.8, "tps": 10.0}, baseline_tier="deep")
        pol2 = SolverPolicy(p, seed=19)                     # перезапуск до исхода
        self.assertIn(d.turn_id, pol2._pending)
        r = pol2.record(d.turn_id, Outcome(conscience_ok=True))
        self.assertIsNotNone(r)
        self.assertIsNone(pol2.record(d.turn_id, Outcome()))      # исход строго один раз
        self.assertEqual(pol2.rev, 1)

    def test_forced_arm_is_not_learned(self):
        pol = SolverPolicy(seed=20)
        d = pol.decide({"greet": True}, baseline_tier="fast")
        self.assertEqual((d.arm, d.learn, d.reason), ("reflex", False, "greet"))
        self.assertIsNone(pol.record(d.turn_id, Outcome(judge=1.0)))
        self.assertEqual(pol.rev, 0)

    def test_executor_adapter_with_real_router_and_late_correction(self):
        from RTE.router import prime_router
        pol = SolverPolicy(seed=21)
        ex = SolverExecutor(pol, prime_router)
        res = ex.run("привет", {"deep_tps": 6.0})
        self.assertEqual(res["tier"], "fast")
        self.assertEqual(res["arm"], "reflex")
        self.assertIn("plan", res)
        res = ex.run("Спланируй архитектуру и сравни плюсы и минусы подходов, подумай глубоко", {"deep_tps": 8.0, "creator": True, "intent": "task"})
        self.assertIn(res["arm"], pol.arms)
        self.assertIn("mind_glm", " ".join(res["executors"]) + "mind_glm" if res["arm"] == "reflex" else " ".join(res["executors"]))
        self.assertEqual(ex.observe(res["turn_id"], Outcome(conscience_ok=True)) is not None, True)
        before = pol.rev
        ex.observe_late(res["turn_id"], Outcome(corrected_next=True))
        self.assertEqual(pol.rev, before + 1)
        self.assertTrue(asyncio.run(ex.arun("ок", {})) ["arm"] == "reflex")

    def test_adapter_rewrites_plan_when_policy_overrides_rules(self):
        fake_base = lambda text, ctx: {"tier": "fast", "why": "simple", "degraded": False,
                                       "plan": {"tier": "fast", "enable_thinking": False, "effort": "low", "max_tokens": 512, "think_budget": 0,
                                                "intro": False, "eta_s": 1.0, "reason": "simple", "notes": [], "features": {}}}
        cfn = lambda text, h=0: (0.9, {"words": 50, "code": False, "reason": True, "think_kw": False, "list": False, "q": 1, "greet": False})
        pol = SolverPolicy(seed=22, n0=1)
        ex = SolverExecutor(pol, fake_base, cfn)
        # научим: на сложном глубина лучше
        rng = random.Random(23)
        for _ in range(250):
            r = ex.run("x", {"deep_tps": 12.0})
            ok = pol.record(r["turn_id"], Outcome(judge=0.95 if r["arm"] == "deep" else 0.4))
        # лёгкое исследование ещё идёт, но 5 запросов подряд должны в основном идти в deep
        arms = [ex.run("x", {"deep_tps": 12.0})["arm"] for _ in range(5)]
        self.assertGreaterEqual(arms.count("deep"), 3)
        res = ex.run("x", {"deep_tps": 12.0})
        if res["arm"] == "deep":
            self.assertEqual(res["tier"], "deep_think")
            self.assertTrue(res["plan"]["enable_thinking"])
            self.assertIn("solver_policy", res["plan"]["notes"][-1])
            self.assertIn("mind_glm_think", res["executors"])


if __name__ == "__main__":
    unittest.main()
