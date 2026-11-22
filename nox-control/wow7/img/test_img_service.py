import json, os, tempfile, threading, time, types, unittest, urllib.request, urllib.error
from http.server import ThreadingHTTPServer
import img_service as S, vram_coord as V, prompt_master as PM


class FakeCoord:
    def __init__(self, mode="group", fail=False):
        self.mode, self.fail, self.acquired, self.released = mode, fail, 0, 0
        self.free_mb = lambda: 9000

    def acquire(self, need, cancel=None):
        if self.fail:
            raise V.VramUnavailable("нет VRAM")
        self.acquired += 1
        w = V.Window(need.get(self.mode + "_mb", 1000), self.mode, ["fake"], [lambda: setattr(self, "released", self.released + 1)])
        return w


def mk(**kw):
    d = tempfile.mkdtemp()
    eng = kw.pop("engine", S.FakeEngine())
    svc = S.Service(eng, coord=kw.pop("coord", FakeCoord()), state_dir=d + "/st", receipts_dir=d + "/rc", mem_avail=lambda: 400.0, judge=kw.pop("judge", lambda p, a, b: {"ok": None}), **kw)
    return svc, eng, d


def run(svc, body, timeout=10):
    c, pl = svc.submit(body)
    if c != 202:
        return c, pl
    j = svc.jobs[pl["id"]]
    assert j.done.wait(timeout), j.state
    return 202, j


class TestPipeline(unittest.TestCase):
    def test_happy_path_ram_gpu_ram_and_receipt(self):
        svc, eng, d = mk()
        c, j = run(svc, {"brief": "red fox in snow", "slider": 10})
        self.assertEqual(j.state, "done", j.error)
        kinds = [x[0] for x in eng.log]
        self.assertEqual(kinds[:4], ["warm", "to_gpu", "run", "to_ram"])       # RAM -> GPU -> RAM
        self.assertEqual(eng.loaded(), {"z-image-turbo": "ram"})                # после генерации веса в RAM, не на GPU
        self.assertEqual(svc.coord.acquired, 1)
        self.assertEqual(svc.coord.released, 1)
        im = j.result["images"][0]
        data = open(im["path"], "rb").read()
        self.assertEqual(S.sha256(data), im["sha256"])
        rc = json.load(open(d + "/rc/IMG-JOB-%s.json" % j.id))
        self.assertEqual(rc["images"][0]["sha256"], im["sha256"])
        self.assertTrue(rc["policy"]["checked"])
        self.assertEqual(rc["vram_windows"][0]["mode"], "group")

    def test_warm_once_second_job_no_warm(self):
        svc, eng, _ = mk()
        run(svc, {"brief": "a cat", "slider": 5})
        run(svc, {"brief": "a dog", "slider": 5})
        self.assertEqual([x for x in eng.log if x[0] == "warm"], [("warm", "z-image-turbo")])
        self.assertEqual(svc.coord.acquired, 2)

    def test_quality_uses_main_model_with_negative(self):
        svc, eng, _ = mk()
        c, j = run(svc, {"brief": "portrait", "positive": "dramatic light", "negative": "hands", "slider": 100})
        self.assertEqual(j.p["model"], "chroma1-hd")
        self.assertEqual(j.p["n"], 3)
        self.assertIn("hands", j.p["negative"])
        self.assertGreaterEqual(j.p["steps"], 36)

    def test_receipt_chain(self):
        svc, eng, d = mk()
        run(svc, {"brief": "a", "slider": 0})
        run(svc, {"brief": "b", "slider": 0})
        lines = [json.loads(x) for x in open(d + "/rc/IMG-LEDGER.jsonl")]
        self.assertEqual(lines[0]["prev"], "")
        self.assertEqual(lines[1]["prev"], lines[0]["receipt_sha256"])

    def test_policy_refuses_before_queue(self):
        svc, eng, d = mk()
        c, pl = svc.submit({"brief": "nude schoolgirl"})
        self.assertEqual((c, pl["rule"]), (403, "csam"))
        self.assertEqual(eng.log, [])
        self.assertEqual(svc.refusals.tail()[0]["rule"], "csam")
        c, pl = svc.submit({"brief": "fake passport"})
        self.assertEqual(pl["rule"], "fake_document")

    def test_policy_after_master(self):
        svc, eng, _ = mk(designer=lambda m: json.dumps({"positive": "nude 10 year old girl", "negative": ""}))
        c, pl = svc.submit({"brief": "a nice picture"})
        self.assertEqual((c, pl["rule"]), (403, "csam"))

    def test_output_guard_blocks_and_deletes_nothing_returned(self):
        svc, eng, d = mk(guard=lambda png: {"block": True, "rule": "csam", "reason": "VL"})
        c, j = run(svc, {"brief": "a woman", "slider": 0})
        self.assertEqual(j.state, "refused")
        self.assertEqual(os.listdir(svc.out_dir), [])
        self.assertTrue(eng.loaded())      # окно возвращено
        self.assertEqual(svc.coord.released, 1)

    def test_vram_unavailable(self):
        svc, eng, _ = mk(coord=FakeCoord(fail=True))
        c, j = run(svc, {"brief": "a", "slider": 0})
        self.assertEqual(j.state, "error")
        self.assertIn("vram_unavailable", j.error)

    def test_engine_error_releases_window(self):
        svc, eng, _ = mk()
        eng.fail_next = "boom"
        c, j = run(svc, {"brief": "a", "slider": 0})
        self.assertEqual(j.state, "error")
        self.assertEqual(svc.coord.released, 1)
        self.assertEqual(eng.loaded()["z-image-turbo"], "ram")

    def test_gen_timeout(self):
        svc, eng, _ = mk(engine=S.FakeEngine(step_s=0.05), gen_timeout_s=0.2)
        c, j = run(svc, {"brief": "a", "slider": 0, "steps": 50})
        self.assertEqual(j.state, "timeout")
        self.assertEqual(svc.coord.released, 1)

    def test_queue_ttl_and_full_and_cancel(self):
        svc, eng, _ = mk(engine=S.FakeEngine(step_s=0.05), queue_max=1, queue_ttl_s=0.2)
        c1, p1 = svc.submit({"brief": "a", "slider": 0, "steps": 12})
        time.sleep(0.1)
        c2, p2 = svc.submit({"brief": "b", "slider": 0})
        c3, p3 = svc.submit({"brief": "c", "slider": 0})
        self.assertEqual((c1, c2, c3), (202, 202, 429))
        j2 = svc.jobs[p2["id"]]
        j2.done.wait(5)
        self.assertEqual(j2.state, "expired")
        c4, p4 = svc.submit({"brief": "d", "slider": 0})
        self.assertEqual(svc.cancel(p4["id"])[0], 200)
        self.assertEqual(svc.jobs[p4["id"]].state, "cancelled")

    def test_cancel_running(self):
        svc, eng, _ = mk(engine=S.FakeEngine(step_s=0.05))
        c, p = svc.submit({"brief": "a", "slider": 0, "steps": 100})
        time.sleep(0.3)
        svc.cancel(p["id"])
        j = svc.jobs[p["id"]]
        j.done.wait(5)
        self.assertEqual(j.state, "cancelled")

    def test_judge_best_of_n_and_regen_round(self):
        calls = []

        def judge(png, p, n):
            calls.append(1)
            return {"ok": len(calls) == 4, "reasons": []}     # первые 3 плохие -> второй раунд, 4-я хорошая
        svc, eng, _ = mk(judge=judge)
        c, j = run(svc, {"brief": "a", "slider": 80, "model": "z-image-turbo", "n": 3, "judge": True})
        self.assertEqual(j.state, "done")
        self.assertEqual(svc.coord.acquired, 2)
        self.assertEqual(j.result["best"], 3)
        self.assertEqual(len(j.result["images"]), 6)

    def test_unload_ram_and_busy(self):
        svc, eng, _ = mk()
        run(svc, {"brief": "a", "slider": 0})
        c, r = svc.unload("ram")
        self.assertEqual((c, r["unloaded"]), (200, ["z-image-turbo"]))
        self.assertEqual(eng.loaded(), {})
        run(svc, {"brief": "a", "slider": 0})
        self.assertEqual(len([x for x in eng.log if x[0] == "warm"]), 2)      # холодный старт заново

    def test_ram_low_guard(self):
        d = tempfile.mkdtemp()
        svc = S.Service(S.FakeEngine(), coord=FakeCoord(), state_dir=d + "/s", receipts_dir=d + "/r", mem_avail=lambda: 50.0)
        c, j = run(svc, {"brief": "a", "slider": 0})
        self.assertEqual(j.state, "error")
        self.assertIn("ram_low", j.error)

    def test_idle_evict(self):
        svc, eng, _ = mk(ram_idle_evict_s=0.5)
        run(svc, {"brief": "a", "slider": 0})
        time.sleep(2.5)
        self.assertEqual(eng.loaded(), {})


class TestVram(unittest.TestCase):
    NEED = {"full_mb": 21000, "model_mb": 12800, "group_mb": 3000}

    def coord(self, frees, busy=lambda: False, **kw):
        it = iter(frees)
        last = [frees[-1]]
        cmds = []

        def free():
            try:
                last[0] = next(it)
            except StopIteration:
                pass
            return last[0]
        d = tempfile.mkdtemp()
        c = V.VramCoordinator(free_mb=free, busy=busy, run=lambda a, timeout=120: (cmds.append(a) or (0, "")), sleep=lambda s: None,
                              lease_path=d + "/lease.json", home=d, idle_wait_s=3, **kw)
        return c, cmds, d

    def test_A_enough_no_window(self):
        c, cmds, d = self.coord([22000])
        w = c.acquire(self.NEED)
        self.assertEqual((w.mode, cmds), ("gpu", []))

    def test_A_group_fallback_picks_group_when_little(self):
        c, cmds, d = self.coord([4500, 4500])
        w = c.acquire(self.NEED)
        self.assertEqual(w.mode, "group")      # 4500-768 >= 3000, но модель/целиком не лезут; освобождение тира сделано (C)
        self.assertTrue(any(x[-2:] == ["stop", "fast"] for x in cmds))

    def test_C_stop_fast_frees_vram_and_release_restores(self):
        c, cmds, d = self.coord([2000, 14000])
        w = c.acquire(self.NEED)
        self.assertEqual(w.mode, "model")
        self.assertEqual(V.leased_names(d + "/lease.json"), {"fast"})
        w.release()
        self.assertEqual(V.leased_names(d + "/lease.json"), set())
        self.assertEqual(cmds[-1][-2:], ["start", "fast"])

    def test_B_waits_for_idle_chat_then_gives_up_no_stop_when_busy(self):
        t = [0.0]
        c, cmds, d = self.coord([2000])
        c.busy, c.clock, c.sleep = (lambda: True), (lambda: t[0]), (lambda s: t.__setitem__(0, t[0] + s))
        with self.assertRaises(V.VramUnavailable):
            c.acquire(self.NEED)
        self.assertEqual(cmds, [])             # чат занят: тир не трогаем
        self.assertEqual(V.leased_names(d + "/lease.json"), set())

    def test_unavailable_clears_lease(self):
        c, cmds, d = self.coord([1000, 1200])
        with self.assertRaises(V.VramUnavailable):
            c.acquire(self.NEED)
        self.assertEqual(V.leased_names(d + "/lease.json"), set())

    def test_D_glm_ngl_only_when_allowed(self):
        c, cmds, d = self.coord([1000, 1000, 14000], allow_glm_restart=True)
        os.makedirs(d + "/gpu_tier")
        open(d + "/gpu_tier/glm.args", "w").write("-c 16384 -ngl 24 -ot exps=CPU")
        w = c.acquire(self.NEED)
        self.assertEqual(w.mode, "model")
        self.assertIn("-ngl 16", open(d + "/gpu_tier/glm.args").read())
        w.release()
        self.assertIn("-ngl 24", open(d + "/gpu_tier/glm.args").read())
        c2, cmds2, d2 = self.coord([1000, 1000])
        with self.assertRaises(V.VramUnavailable):
            c2.acquire(self.NEED)
        self.assertFalse(any("glm" in x for cm in cmds2 for x in cm))

    def test_lease_expiry(self):
        d = tempfile.mkdtemp()
        V.write_lease("img", ["fast"], 10, d + "/l.json", now=100)
        self.assertEqual(V.leased_names(d + "/l.json", now=105), {"fast"})
        self.assertEqual(V.leased_names(d + "/l.json", now=111), set())

    def test_no_gpu_info(self):
        c = V.VramCoordinator(free_mb=lambda: None)
        self.assertEqual(c.acquire(self.NEED).mode, "cpu_or_unknown")


class TestPromptMaster(unittest.TestCase):
    def test_slider(self):
        self.assertEqual(PM.mode_params(0)["role"], "fast")
        self.assertEqual(PM.mode_params(50)["n"], 2)
        self.assertTrue(PM.mode_params(50)["judge"])
        self.assertEqual(PM.mode_params(100)["role"], "main")
        self.assertLess(PM.mode_params(70)["steps"], PM.mode_params(100)["steps"])

    def test_offline_fields(self):
        r = PM.build_request(brief="a fox", positive="snow", negative="cartoon", general="film grain", slider=50)
        self.assertIn("fox", r["positive"]); self.assertIn("film grain", r["positive"]); self.assertIn("snow", r["positive"])
        self.assertTrue(r["negative"].startswith("cartoon"))
        self.assertEqual(r["prompt_source"], "offline")

    def test_llm_and_fallback(self):
        ok = lambda m: '```json {"positive":"fox, golden hour","negative":"","aspect":"16:9","notes":"x"}```'
        r = PM.build_request(brief="fox", general="film grain", negative="cartoon", llm=ok)
        self.assertEqual((r["prompt_source"], r["width"], r["height"]), ("llm", 1344, 768))
        self.assertIn("film grain", r["positive"]); self.assertIn("cartoon", r["negative"])
        bad = lambda m: "не json"
        r = PM.build_request(brief="fox", llm=bad)
        self.assertEqual(r["prompt_source"], "offline"); self.assertIn("LLM не ответил", r["notes"])
        self.assertIn("ведущий графический дизайнер", PM.MASTER_PROMPT)


class TestHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svc, cls.eng, cls.d = mk()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), S.make_handler(cls.svc))
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.svc.close()

    def call(self, method, path, body=None):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), json.dumps(body).encode() if body is not None else None, {"Content-Type": "application/json"}, method)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, r.read(), r.headers.get("Content-Type")
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers.get("Content-Type")

    def test_generate_status_artifact_receipt_unload(self):
        c, b, _ = self.call("POST", "/generate", {"brief": "a lighthouse", "slider": 20})
        self.assertEqual(c, 200, b)
        r = json.loads(b)
        im = r["images"][0]
        c, png, ct = self.call("GET", im["url"])
        self.assertEqual((c, ct), (200, "image/png"))
        self.assertEqual(S.sha256(png), im["sha256"])
        c, rc, _ = self.call("GET", r["receipt_url"])
        self.assertEqual(json.loads(rc)["receipt_sha256"], r["receipt_sha256"])
        c, st, _ = self.call("GET", "/status")
        s = json.loads(st)
        self.assertEqual(s["models"]["z-image-turbo"]["where"], "ram")
        self.assertEqual(s["models"]["chroma1-hd"]["where"], "cold")
        c, u, _ = self.call("POST", "/unload", {"scope": "ram"})
        self.assertEqual(json.loads(u)["loaded"], {})
        self.assertEqual(json.loads(self.call("GET", "/status")[1])["models"]["z-image-turbo"]["where"], "cold")

    def test_403_and_400_and_async(self):
        c, b, _ = self.call("POST", "/generate", {"brief": "naked child"})
        self.assertEqual((c, json.loads(b)["rule"]), (403, "csam"))
        self.assertEqual(self.call("POST", "/generate", {})[0], 400)
        c, b, _ = self.call("POST", "/generate", {"brief": "x", "slider": 0, "async": True})
        self.assertEqual(c, 202)
        jid = json.loads(b)["id"]
        for _ in range(50):
            st = json.loads(self.call("GET", "/status/" + jid)[1])
            if st["state"] == "done":
                break
            time.sleep(0.1)
        self.assertEqual(st["state"], "done")

    def test_legacy_alias(self):
        c, b, _ = self.call("POST", "/v1/images/generate?format=json", {"prompt": "a red fox in snow"})
        self.assertEqual(c, 200, b)
        self.assertIn("png_base64", json.loads(b))


class TestDiffusersEngineStub(unittest.TestCase):
    """DiffusersEngine на заглушках torch/diffusers (без GPU): порядок вызовов warm -> to_gpu(group) -> run -> to_ram."""
    def test_flow(self):
        calls = []

        class Img:
            def save(self, buf, format):
                buf.write(S.make_png(8, 8))

        class Pipe:
            transformer = object(); text_encoder = object(); vae = object()
            @classmethod
            def from_pretrained(cls, path, torch_dtype, low_cpu_mem_usage):
                calls.append(("load", os.path.basename(path)))
                return cls()
            def __call__(self, **kw):
                calls.append(("call", kw["num_inference_steps"], "negative_prompt" in kw))
                kw["callback_on_step_end"](self, 0, 0, {})
                return types.SimpleNamespace(images=[Img()])
            def to(self, d): calls.append(("to", d))
        torch = types.SimpleNamespace(bfloat16="bf16", device=lambda x: x, Generator=lambda d: types.SimpleNamespace(manual_seed=lambda s: s),
                                      cuda=types.SimpleNamespace(empty_cache=lambda: calls.append(("empty",))))
        df = types.SimpleNamespace(ZImagePipeline=Pipe, ChromaPipeline=Pipe,
                                   hooks=types.SimpleNamespace(apply_group_offloading=lambda c, **kw: calls.append(("group", kw["offload_type"], kw["use_stream"]))))
        d = tempfile.mkdtemp()
        os.makedirs(d + "/Z-Image-Turbo"); open(d + "/Z-Image-Turbo/model_index.json", "w").write("{}")
        e = S.DiffusersEngine(d, torch, df)
        self.assertTrue(e.installed("z-image-turbo")); self.assertFalse(e.installed("chroma1-hd"))
        e.warm("z-image-turbo")
        self.assertEqual(e.loaded(), {"z-image-turbo": "ram"})
        e.to_gpu("z-image-turbo", V.Window(3000, "group", [], []))
        self.assertEqual(e.loaded()["z-image-turbo"], "gpu")
        png = e.run("z-image-turbo", {"positive": "x", "negative": "y", "width": 64, "height": 64, "steps": 9, "guidance": 0.0, "seed": 1}, threading.Event(), lambda s, n: None)
        self.assertEqual(png[:4], b"\x89PNG")
        e.to_ram("z-image-turbo")
        self.assertEqual(e.loaded()["z-image-turbo"], "ram")
        self.assertIn(("group", "leaf_level", True), calls)
        self.assertIn(("call", 9, False), calls)           # Z-Image: негатив не передаётся (CFG 0)
        e.drop("z-image-turbo")
        self.assertEqual(e.loaded(), {})
        with self.assertRaises(S.EngineError):
            e.warm("chroma1-hd")


class TestBrainAndPatch(unittest.TestCase):
    def test_planner(self):
        import brain_img, asyncio
        pl = brain_img.ImgActionPlanner(post=lambda path, body: (200, {"images": [{"url": "/artifact/ab/0.png", "sha256": "f" * 64}], "best": 0, "receipt_url": "/receipt/ab"}))
        card = pl.match("Нокс, нарисуй картинку: красная лиса в снегу, максимальное качество")
        self.assertEqual(card["slider"], 100)
        self.assertFalse(pl.irreversible(card))
        self.assertIn("лиса", pl.preview(card))
        self.assertIn("SHA ffffffffffff", asyncio.run(pl.execute(card)))
        self.assertIsNone(pl.match("привет, как дела"))
        self.assertIn("не буду", pl.describe(403, {"reason": "Запрещено: x"}))

    def test_dsp_patch_valid_for_registry(self):
        import copy, sys
        dsp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "DSP")
        if not os.path.isfile(dsp + "/services.json"):
            self.skipTest("нет DSP")
        sys.path.insert(0, dsp)
        import nox_dispatcher as nd
        raw = json.load(open(dsp + "/services.json"))
        patch = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dsp_patch.json")))
        raw["services"] += copy.deepcopy(patch["services_add"])
        r = nd.Registry(raw, home="/tmp/x")
        self.assertIn("img", r.order())
        self.assertEqual(r.services["img"]["exclusive"], "vram")


if __name__ == "__main__":
    unittest.main()
