import json, os, random, shutil, tempfile, unittest
from evolve import (Variant, Archive, Gate, Champions, EvolutionLoop, LLMGenerator, PatchSandbox,
                    split_tasks, to_selfbuild_task, touched_paths, check_patch_policy)

TASKS = [{"id": "t%d" % i} for i in range(12)]
DIFF = "--- a/m.py\n+++ b/m.py\n@@ -1 +1 @@\n-def f(): return 1\n+def f(): return 2\n"
BAD = "--- a/nox-control/agent/release.py\n+++ b/nox-control/agent/release.py\n@@ -1 +1 @@\n-a\n+b\n"


def ev_len(v, tasks):
    """Фейковый evaluator: чем длиннее фрагмент (до 10), тем лучше; одна «охранная» задача t0 портится словом BAD."""
    s = min(len(v.payload), 10) / 10.0
    return {t["id"]: (0.0 if (t["id"] == "t0" and "BADWORD" in v.payload) else s) for t in tasks}


def fake_llm(replies):
    it = iter(replies)
    return lambda prompt: next(it)


def js(*vs): return json.dumps(list(vs))


class TestSplit(unittest.TestCase):
    def test_split_stable_disjoint(self):
        d1, h1 = split_tasks(TASKS); d2, h2 = split_tasks(list(reversed(TASKS)))
        self.assertEqual({t["id"] for t in d1}, {t["id"] for t in d2})
        self.assertFalse({t["id"] for t in d1} & {t["id"] for t in h1})
        self.assertEqual(len(d1) + len(h1), 12)
        with self.assertRaises(ValueError): split_tasks([{"id": "x"}])


class TestArchive(unittest.TestCase):
    def v(self, p, desc, feat, score):
        v = Variant("prompt", p, descriptor=desc, features=feat); v.score = score; return v

    def test_cell_keeps_best_and_novelty(self):
        a = Archive(novelty_min=0.3)
        self.assertEqual(a.add(self.v("a", (0,), (0.1,), 0.5)), "cell")
        self.assertEqual(a.add(self.v("b", (0,), (0.1,), 0.4)), None)          # хуже и не нов
        self.assertEqual(a.add(self.v("c", (0,), (0.9,), 0.4)), "novel")       # хуже, но далеко
        self.assertEqual(a.add(self.v("d", (0,), (0.1,), 0.9)), "cell")
        self.assertEqual(a.best().payload, "d"); self.assertEqual(a.coverage(), 1)

    def test_persist_and_visits(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "arch.jsonl"); a = Archive(p)
            a.add(self.v("a", (1,), (0.2,), 0.7)); a.add(self.v("b", (2,), (0.8,), 0.6))
            a.sample_parent(random.Random(1))
            b = Archive(p)
            self.assertEqual(b.coverage(), 2); self.assertEqual(sum(b.visits.values()), 1)

    def test_sample_prefers_less_visited(self):
        a = Archive(); x = self.v("x", (0,), (0.1,), 0.5); y = self.v("y", (1,), (0.9,), 0.5)
        a.add(x); a.add(y); a.visits[x.id] = 50
        picks = [a.sample_parent(random.Random(i)).payload for i in range(30)]
        self.assertGreater(picks.count("y"), 20)

    def test_unscored_rejected(self):
        with self.assertRaises(ValueError): Archive().add(Variant("prompt", "z"))


class TestGate(unittest.TestCase):
    base = {"a": .5, "b": .5, "c": .5, "d": .5}

    def test_accept_growth(self):
        v = Gate().decide(self.base, {"a": .7, "b": .6, "c": .5, "d": .5}); self.assertTrue(v.ok, v.reasons)

    def test_reject_flat_and_regress(self):
        self.assertFalse(Gate().decide(self.base, dict(self.base)).ok)
        self.assertFalse(Gate(max_regress=0).decide(self.base, {"a": 1, "b": 1, "c": 1, "d": .1}).ok)

    def test_guard_and_mismatch(self):
        self.assertFalse(Gate(guard_ids=["d"]).decide(self.base, {"a": 1, "b": 1, "c": 1, "d": .49}).ok)
        self.assertFalse(Gate().decide(self.base, {"a": 1}).ok)
        self.assertFalse(Gate().decide({}, {}).ok)

    def test_one_outlier_not_enough(self):
        # среднее выросло из-за одной задачи; побед 1, просадок 0 -> margin 1 ок; но 1 победа и 1 просадка -> нет
        v = Gate(min_gain=0.01).decide(self.base, {"a": 1.0, "b": .39, "c": .5, "d": .5}); self.assertFalse(v.ok)


class TestPolicy(unittest.TestCase):
    def test_paths(self):
        self.assertEqual(touched_paths(DIFF), ["m.py"])
        self.assertTrue(check_patch_policy(BAD)); self.assertFalse(check_patch_policy(DIFF))
        self.assertTrue(check_patch_policy("--- a/../x\n+++ b/../x\n"))
        self.assertTrue(check_patch_policy("diff --git a/x b/x\ndeleted file mode 100644\n--- a/x\n+++ /dev/null\n"))


class TestSandbox(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); open(os.path.join(self.d, "m.py"), "w").write("def f(): return 1\n")
        open(os.path.join(self.d, "check.py"), "w").write("import m,sys; sys.exit(0 if m.f()==2 else 1)\n")
        self.sb = PatchSandbox(self.d, ["python3", "-I", "-c", "import sys; sys.path.insert(0,'.'); import m; sys.exit(0 if m.f()==2 else 1)"])

    def tearDown(self): shutil.rmtree(self.d, ignore_errors=True)

    def test_good_patch_passes_and_live_tree_untouched(self):
        r = self.sb.run(Variant("patch", DIFF)); self.assertTrue(r["ok"], r)
        self.assertIn("return 1", open(os.path.join(self.d, "m.py")).read())

    def test_failing_tests_bad_apply_policy(self):
        self.assertFalse(PatchSandbox(self.d, ["false"]).run(Variant("patch", DIFF))["ok"])
        self.assertIn("git apply", self.sb.run(Variant("patch", DIFF.replace("return 1", "return 9")))["report"])
        self.assertIn("политика", self.sb.run(Variant("patch", BAD))["report"])


class TestLoop(unittest.TestCase):
    def mk(self, replies, tmp, **kw):
        arch = Archive(os.path.join(tmp, "a.jsonl")); ch = Champions(os.path.join(tmp, "c.json"))
        return EvolutionLoop(LLMGenerator(fake_llm(replies)), ev_len, TASKS, arch, ch, seed=1, **kw), arch, ch

    def test_generator_parsing(self):
        g = LLMGenerator(fake_llm(["<think>x</think> мусор " + js({"kind": "prompt", "payload": "p", "descriptor": [1], "features": [0.5]},
                                                                  {"kind": "bogus", "payload": "z"}, {"kind": "prompt", "payload": ""}, "str")]))
        out = g.propose(None); self.assertEqual(len(out), 1); self.assertEqual(out[0].descriptor, (1,))
        self.assertEqual(LLMGenerator(fake_llm(["не json"])).propose(None), [])

    def test_evolve_improves_and_promotes_then_rolls_back(self):
        with tempfile.TemporaryDirectory() as t:
            base = Variant("prompt", "ab")
            r1 = js({"kind": "prompt", "payload": "abcdef", "descriptor": [0], "features": [0.1]},
                    {"kind": "prompt", "payload": "abcdefghij", "descriptor": [1], "features": [0.9]})
            r2 = js({"kind": "prompt", "payload": "abcdefghijk BADWORD", "descriptor": [0], "features": [0.3]})
            loop, arch, ch = self.mk([r1, r2], t)
            loop.step(); loop.step()
            self.assertGreaterEqual(arch.coverage(), 2)
            res = loop.promote("prompt", baseline=base)
            self.assertTrue(res["accepted"], res); self.assertEqual(ch.current("prompt")["variant"]["payload"], "abcdefghij")
            # повторное продвижение того же — отказ; чемпион сохранён на диске
            self.assertFalse(loop.promote("prompt")["accepted"])
            self.assertEqual(Champions(os.path.join(t, "c.json")).current("prompt")["variant"]["payload"], "abcdefghij")
            self.assertIsNotNone(ch.rollback("prompt")); self.assertIsNone(ch.current("prompt"))

    def test_gate_blocks_worse_candidate(self):
        with tempfile.TemporaryDirectory() as t:
            loop, arch, ch = self.mk([js({"kind": "prompt", "payload": "abc", "descriptor": [0], "features": [0.1]})], t)
            loop.step()
            res = loop.promote("prompt", baseline=Variant("prompt", "abcdefghij"))
            self.assertFalse(res["accepted"]); self.assertIsNone(ch.current("prompt"))

    def test_duplicates_and_evaluator_errors(self):
        with tempfile.TemporaryDirectory() as t:
            p = js({"kind": "prompt", "payload": "same", "descriptor": [0], "features": [0.1]})
            def boom(v, tasks): raise RuntimeError("упал")
            loop, arch, ch = self.mk([p, p], t); loop.step(); r = loop.step()
            self.assertIn(r[0]["status"], ("duplicate",))
            l2 = EvolutionLoop(LLMGenerator(fake_llm([p])), boom, TASKS, Archive(), Champions(), seed=1)
            self.assertEqual(l2.step()[0]["score"], 0.0); self.assertTrue(any("evaluator_error" in e for e in l2.log))

    def test_patch_needs_sandbox_and_goes_to_selfbuild(self):
        with tempfile.TemporaryDirectory() as t:
            p = js({"kind": "patch", "payload": DIFF, "descriptor": [0], "features": [0.2]})
            loop, _, _ = self.mk([p], t)
            self.assertEqual(loop.step()[0]["status"], "no_sandbox")
            class SB:
                def run(self, v): return {"ok": True, "report": ""}
            loop, arch, ch = self.mk([p], t, sandbox=SB())
            loop.step(); res = loop.promote("patch", baseline=Variant("patch", "x"))
            self.assertTrue(res["accepted"], res)
            task = to_selfbuild_task(Variant.from_json(ch.current("patch")["variant"]), res["verdict"])
            self.assertTrue(task["title"].startswith("код:")); self.assertIn("```diff", task["body"])
            with self.assertRaises(ValueError): to_selfbuild_task(Variant("prompt", "x"))

    def test_stop_file(self):
        with tempfile.TemporaryDirectory() as t:
            sf = os.path.join(t, "STOP"); open(sf, "w").close()
            loop, _, _ = self.mk([], t, stop_file=sf)
            self.assertEqual(loop.step()[0]["status"], "stopped"); self.assertFalse(loop.promote("prompt")["accepted"])

    def test_run_end_to_end(self):
        with tempfile.TemporaryDirectory() as t:
            r = js({"kind": "prompt", "payload": "abcdefghij", "descriptor": [0], "features": [0.5]})
            loop, _, _ = self.mk([r, r, r], t)
            out = dict(loop.run(1, kinds=("prompt",), baseline={"prompt": Variant("prompt", "a")}))
            self.assertTrue(out["prompt"]["accepted"])


if __name__ == "__main__":
    unittest.main()
