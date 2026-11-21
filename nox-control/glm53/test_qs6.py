import unittest, sys, os, json, time, threading, http.client, sqlite3, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import qs6_core as C, qs6_resume as RS, gateway as G

class Fake:
    """Поддельный llama-server: SSE с управляемой скоростью, обрывом, ошибкой; фиксирует разрыв клиента."""
    def __init__(self, pieces, delay=0.01, status=200, drop_after=None, infinite=False, timings=None):
        self.pieces, self.delay, self.status, self.drop_after, self.infinite, self.timings = pieces, delay, status, drop_after, infinite, timings
        self.disconnected = threading.Event(); self.bodies = []; self.started = threading.Event()
        outer = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); outer.bodies.append(body); outer.started.set()
                if outer.status != 200:
                    self.send_response(outer.status); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"no"); return
                if not body.get("stream"):
                    d = json.dumps({"choices": [{"message": {"role": "assistant", "content": "".join(outer.pieces)}}], "usage": {"completion_tokens": 5}, "timings": outer.timings or {}}).encode()
                    self.send_response(200); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d); return
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                try:
                    i = 0
                    while True:
                        if not outer.infinite and i >= len(outer.pieces): break
                        if outer.drop_after is not None and i >= outer.drop_after: self.connection.close(); return
                        p = outer.pieces[i % len(outer.pieces)]; i += 1
                        self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": p}}]}).encode() + b"\n\n"); self.wfile.flush(); time.sleep(outer.delay)
                    last = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
                    if outer.timings: last["timings"] = outer.timings
                    self.wfile.write(b"data: " + json.dumps(last).encode() + b"\n\ndata: [DONE]\n\n"); self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    outer.disconnected.set()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H); self.srv.daemon_threads = True
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def close(self): self.srv.shutdown(); self.srv.server_close()

class GW:
    def __init__(self, deep=None, fast=None, **kw):
        self.cfg = C.Cfg(deep_url=deep.url if deep else "http://127.0.0.1:1", fast_url=fast.url if fast else "", ping_s=0.3, connect_timeout=1, **kw)
        self.srv = G.make_server(self.cfg, "127.0.0.1", 0); self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def close(self): self.srv.shutdown(); self.srv.server_close()
    def post(self, body, path="/v1/chat/completions"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20); c.request("POST", path, json.dumps(body), {"Content-Type": "application/json"}); return c, c.getresponse()
    def stream(self, body):
        body = dict(body, stream=True); c, r = self.post(body); evs = []
        for line in r.read().decode().splitlines():
            if line.startswith("data: "): evs.append(line[6:])
        return r, evs
def parse(evs): return [json.loads(e) for e in evs if e != "[DONE]"]
def text_of(chunks, stage=None):
    return "".join(c["choices"][0]["delta"].get("content", "") for c in chunks if c.get("choices") and (stage is None or c["choices"][0]["delta"].get("nox_stage") == stage))
def U(t, **kw): return dict({"messages": [{"role": "user", "content": t}], "nox_no_route": True}, **kw)
LONG = "Объясни, почему небо голубое и как это связано с рассеянием света в атмосфере Земли"

class TRouter(unittest.TestCase):
    def setUp(self): self.cfg = C.Cfg(fast_url="http://x")
    def r(self, t, **k): return C.route_tier([{"role": "user", "content": t}], self.cfg, **k)["tier"]
    def test_tiers(self):
        self.assertEqual(self.r("привет, как дела?"), "fast")
        self.assertEqual(self.r("напиши функцию на python"), "deep")
        self.assertEqual(self.r(LONG), "two_stage")
        self.assertEqual(self.r("подумай над этим"), "two_stage")
        self.assertEqual(self.r("слово " * 200), "deep")
        self.assertEqual(self.r("привет", tools=True), "deep")
    def test_env_json(self):
        os.environ["NOX_ROUTER_JSON"] = '{"fast_max_words": 2}'
        try: cfg = C.Cfg()
        finally: del os.environ["NOX_ROUTER_JSON"]
        self.assertEqual(C.route_tier([{"role": "user", "content": "как твои дела сегодня"}], cfg)["tier"], "two_stage")

class TModes(unittest.TestCase):
    def test_plan(self):
        cfg = C.Cfg(fast_url="http://x")
        b = lambda m, t="привет": {"nox_mode": m, "messages": [{"role": "user", "content": t}]}
        p = C.plan_request(b("fast"), cfg); self.assertEqual((p["tier"], p["effort"]), ("fast", None))
        p = C.plan_request(b("deep"), cfg); self.assertEqual((p["tier"], p["effort"], p["max_tokens"]), ("two_stage", "high", 8192))
        p = C.plan_request(b("max"), cfg); self.assertEqual((p["effort"], p["max_tokens"]), ("max", 16384))
        p = C.plan_request(b("auto"), cfg); self.assertEqual(p["tier"], "fast")
        p = C.plan_request(b("bogus"), cfg); self.assertEqual(p["mode"], "auto")
        p = C.plan_request(b("deep"), cfg, fast_ok=False); self.assertEqual((p["tier"], p["note"]), ("deep", "fast_unavailable"))
    def test_eta(self):
        cfg = C.Cfg(fast_url="http://x"); m = C.SpeedMeter(cfg)
        plan = C.plan_request({"nox_mode": "deep", "messages": [{"role": "user", "content": "x"}]}, cfg)
        e0 = m.eta(plan); self.assertEqual(e0["basis"], "default"); self.assertAlmostEqual(e0["eta_s"], 2 + 700 / 1.5, 0)
        for _ in range(3): m.record("deep", 100, 10)          # 10 ток/с
        e1 = m.eta(plan); self.assertTrue(e1["basis"].startswith("measured")); self.assertAlmostEqual(e1["eta_s"], 2 + 70, 0)
        m.record("deep", 100, 20)                              # скользящее среднее: (400)/(50)=8
        self.assertAlmostEqual(m.tps("deep")[0], 8.0, 1)
        for _ in range(30): m.record("deep", 50, 10)           # окно 20: старое вытеснено
        self.assertAlmostEqual(m.tps("deep")[0], 5.0, 1)

class TStitch(unittest.TestCase):
    def test_dedup(self):
        s = C.Stitcher("Да, расскажу. Это про рассеяние Рэлея.")
        out = "".join(s.feed(x) for x in ["Да, расск", "ажу. Это про рассеяние Рэлея. ", "Подробнее: свет рассеивается."]) + s.finish()
        self.assertEqual(out.strip(), "Подробнее: свет рассеивается."); self.assertEqual(s.dropped, 2)
    def test_no_dup(self):
        s = C.Stitcher("Привет."); out = s.feed("Глубина без повтора. ") + s.finish(); self.assertEqual(out, "Глубина без повтора. ")
    def test_only_dup(self):
        s = C.Stitcher("Привет."); self.assertEqual(s.feed("Привет.") + s.finish(), "")
    def test_think(self):
        f = C.ThinkFilter(); out = "".join(f.feed(x) for x in ["a<thi", "nk>секрет</th", "ink>b"]) + f.flush(); self.assertEqual(out, "ab")

class TGateway(unittest.TestCase):
    def tearDown(self):
        for x in getattr(self, "cl", []): x.close()
    def mk(self, deep=None, fast=None, **kw):
        gw = GW(deep, fast, **kw); self.cl = [x for x in (gw, deep, fast) if x]; return gw
    def test_two_stage_stitch(self):
        fast = Fake(["Да, ", "объясню. ", "Это рассеяние. ", "Лишнее. "]); deep = Fake(["Да, объясню. ", "Подробно: ", "рассеяние Рэлея. ", "Конец."], delay=0.05)
        gw = self.mk(deep, fast); r, evs = gw.stream(U(LONG, nox_mode="deep"))
        ch = parse(evs); self.assertEqual(evs[-1], "[DONE]"); rid = r.getheader("X-NOX-Request-Id"); self.assertTrue(rid)
        self.assertEqual(ch[0]["nox"]["request_id"], rid); self.assertEqual(ch[0]["nox"]["mode"], "deep"); self.assertIn("eta_s", ch[0]["nox"])
        f = text_of(ch, "fast"); d = text_of(ch, "deep")
        self.assertEqual(f, "Да, объясню. Это рассеяние. "); self.assertNotIn("Лишнее", f)    # лимит 2 предложения
        self.assertEqual(d.strip(), "Подробно: рассеяние Рэлея. Конец.")                     # дубль отброшен
        stages = [c["choices"][0]["delta"].get("nox_stage") for c in ch if c["choices"][0]["delta"].get("content")]
        self.assertEqual(sorted(set(stages)), ["deep", "fast"]); self.assertLess(stages.index("fast"), stages.index("deep"))
        last = ch[-1]; self.assertEqual(last["choices"][0]["finish_reason"], "stop"); self.assertGreaterEqual(last["nox"]["dedup_sentences_dropped"], 1)
        self.assertEqual(ch[-1]["nox"]["stages"]["fast"]["status"], "ok")
        # промпт глубокого такта: система первой, хвост с инструкцией, cache_prompt
        db = deep.bodies[0]; self.assertEqual(db["messages"][0]["role"], "system"); self.assertTrue(db["cache_prompt"]); self.assertIn("Не повторяй", db["messages"][-1]["content"])
        self.assertNotIn("nox_mode", db)
    def test_fast_first_arrives_before_deep(self):
        fast = Fake(["Суть. ", "Ещё. "]); deep = Fake(["Глубина. "], delay=0.01)
        gw = self.mk(deep, fast); c, r = gw.post(dict(U(LONG, nox_mode="deep"), stream=True)); order = []
        for line in r.read().decode().splitlines():
            if line.startswith("data: {") and "nox_stage" in line: order.append(json.loads(line[6:])["choices"][0]["delta"]["nox_stage"])
        self.assertEqual(order[0], "fast"); self.assertEqual(order[-1], "deep")
    def test_fast_unavailable(self):
        deep = Fake(["Только ", "GLM."]); gw = self.mk(deep, None); r, evs = gw.stream(U(LONG, nox_mode="deep")); ch = parse(evs)
        self.assertEqual(text_of(ch, "deep"), "Только GLM."); self.assertEqual(text_of(ch, "fast"), ""); self.assertEqual(ch[0]["nox"]["note"], "fast_unavailable")
    def test_fast_down_runtime(self):
        fast = Fake([], status=503); deep = Fake(["Ответ GLM."]); gw = self.mk(deep, fast); r, evs = gw.stream(U(LONG, nox_mode="deep")); ch = parse(evs)
        self.assertEqual(text_of(ch, "deep"), "Ответ GLM."); self.assertEqual(ch[-1]["nox"]["stages"]["fast"]["status"], "skipped")
        self.assertTrue(any(c.get("nox", {}).get("fast") == "skipped" for c in ch))
        self.assertFalse(gw.srv.state.fast_ok())       # кулдаун
    def test_deep_down(self):
        fast = Fake(["Суть. ", "Ещё. "]); deep = Fake([], status=500); gw = self.mk(deep, fast); r, evs = gw.stream(U(LONG, nox_mode="deep")); ch = parse(evs)
        self.assertEqual(text_of(ch, "fast"), "Суть. Ещё. "); err = [c for c in ch if "error" in c]
        self.assertEqual(len(err), 1); self.assertIn("GLM недоступен", err[0]["error"]["message"]); self.assertEqual(ch[-1]["choices"][0]["finish_reason"], "error")
    def test_both_down(self):
        gw = self.mk(None, None); r, evs = gw.stream(U("привет", nox_mode="deep")); ch = parse(evs)
        self.assertTrue(any("error" in c for c in ch)); self.assertEqual(evs[-1], "[DONE]")
    def test_fast_mode_only_fast(self):
        fast = Fake(["Привет!"]); deep = Fake(["не должен"]); gw = self.mk(deep, fast); r, evs = gw.stream(U("привет", nox_mode="fast")); ch = parse(evs)
        self.assertEqual(text_of(ch, "fast"), "Привет!"); self.assertEqual(deep.bodies, []); self.assertEqual(fast.bodies[0]["max_tokens"], 512)
    def test_fast_mode_fallback_to_glm(self):
        fast = Fake([], status=500); deep = Fake(["GLM вместо быстрого."]); gw = self.mk(deep, fast); r, evs = gw.stream(U("привет", nox_mode="fast")); ch = parse(evs)
        self.assertEqual(text_of(ch, "deep"), "GLM вместо быстрого.")
    def test_mode_max_params(self):
        deep = Fake(["ok. "]); gw = self.mk(deep, None); gw.stream(U("привет", nox_mode="max"))
        b = deep.bodies[0]; self.assertEqual(b["chat_template_kwargs"]["reasoning_effort"], "max"); self.assertEqual(b["max_tokens"], 16384 - 512)
    def test_stop_endpoint(self):
        deep = Fake(["т "], delay=0.05, infinite=True); gw = self.mk(deep, None)
        c, r = gw.post(dict(U("привет", nox_mode="max"), stream=True)); rid = r.getheader("X-NOX-Request-Id")
        self.assertTrue(deep.started.wait(5))
        c2, r2 = gw.post({"request_id": rid}, "/v1/stop"); self.assertTrue(json.loads(r2.read())["stopped"])
        self.assertTrue(deep.disconnected.wait(5), "upstream не получил разрыв")
        evs = [l[6:] for l in r.read().decode().splitlines() if l.startswith("data: ")]
        self.assertEqual(evs[-1], "[DONE]"); self.assertTrue(json.loads(evs[-2])["nox"]["stopped"])
        c3, r3 = gw.post({"request_id": rid}, "/v1/stop"); self.assertFalse(json.loads(r3.read())["stopped"])
    def test_client_disconnect(self):
        deep = Fake(["т "], delay=0.05, infinite=True); gw = self.mk(deep, None)
        c, r = gw.post(dict(U("привет", nox_mode="max"), stream=True)); r.fp.readline(); r.close(); c.close()
        self.assertTrue(deep.disconnected.wait(5), "upstream не получил разрыв после ухода клиента")
        t = time.time()
        while gw.srv.state.reg.active() and time.time() - t < 3: time.sleep(0.05)
        self.assertEqual(gw.srv.state.reg.active(), [])
    def test_stream_unbuffered(self):
        deep = Fake(["а "], delay=0.3, infinite=True); gw = self.mk(deep, None); c, r = gw.post(dict(U("привет", nox_mode="max"), stream=True))
        t = time.time(); r.fp.readline(); r.fp.readline(); r.fp.readline(); r.fp.readline()   # первый чанк + первый токен
        self.assertLess(time.time() - t, 2); c.close()
    def test_non_stream_and_cache(self):
        deep = Fake(["Ответ."], timings={"cache_n": 90, "prompt_n": 10}); gw = self.mk(deep, None)
        c, r = gw.post(U("привет", nox_mode="max")); j = json.loads(r.read())
        self.assertEqual(j["choices"][0]["message"]["content"], "Ответ."); self.assertEqual(j["nox"]["cache"]["tokens_cached"], 90)
        self.assertEqual(j["nox"]["request_id"], r.getheader("X-NOX-Request-Id")); self.assertIn("eta_s", j["nox"])
        c, r = gw.post(U("привет", nox_mode="max"), ); r.read()
        c = http.client.HTTPConnection("127.0.0.1", gw.port); c.request("GET", "/v1/nox/stats"); s = json.loads(c.getresponse().read())
        self.assertEqual(s["cache"]["tokens_cached"], 180); self.assertEqual(s["cache"]["hit_ratio"], 0.9); self.assertTrue(s["prefix"])
    def test_stream_cache_and_speed(self):
        deep = Fake(["а. ", "б. ", "в. "], timings={"cache_n": 50, "prompt_n": 50, "predicted_n": 30, "predicted_ms": 1000}); gw = self.mk(deep, None)
        r, evs = gw.stream(U("привет", nox_mode="max")); ch = parse(evs)
        self.assertEqual(ch[-1]["nox"]["cache"]["tokens_cached"], 50); self.assertAlmostEqual(gw.srv.state.meter.tps("deep")[0], 30.0, 1)
    def test_prefix_stable(self):
        deep = Fake(["ok"]); gw = self.mk(deep, None)
        gw.post(U("первый вопрос", nox_mode="max"))[1].read(); gw.post(U("второй другой вопрос", nox_mode="max"))[1].read()
        a, b = deep.bodies[0]["messages"][0], deep.bodies[1]["messages"][0]; self.assertEqual(a, b); self.assertEqual(a["role"], "system")
    def test_resume_no_model(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"ts": "2026-11-20", "summary": "старая"}) + "\n" + json.dumps({"ts": "2026-11-21", "summary": "чинили шлюз", "open_items": ["тесты STOP"], "next_step": "слить PR"}, ensure_ascii=False) + "\n")
            deep = Fake(["не вызывать"]); gw = self.mk(deep, None, session_summary=p)
            c, r = gw.post(dict(U("На чём мы остановились?"))); j = json.loads(r.read())
            self.assertIn("чинили шлюз", j["choices"][0]["message"]["content"]); self.assertNotIn("старая", j["choices"][0]["message"]["content"]); self.assertEqual(deep.bodies, [])

class TResume(unittest.TestCase):
    def test_sqlite_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.db"); c = sqlite3.connect(p); c.execute("create table sessions(ts text, summary text, open_items text, next_step text)")
            c.execute("insert into sessions values('1','a','[]','')"); c.execute("insert into sessions values('2','сводка 2','[\"задача А\"]','шаг Б')"); c.commit(); c.close()
            t = RS.resume_answer(p); self.assertIn("сводка 2", t); self.assertIn("задача А", t); self.assertIn("шаг Б", t)
            self.assertIn("нет", RS.resume_answer(os.path.join(d, "no.jsonl")))
    def test_detect(self):
        self.assertTrue(RS.is_resume_query("Нокс, на чём мы остановились?")); self.assertFalse(RS.is_resume_query("привет"))

if __name__ == "__main__": unittest.main()
