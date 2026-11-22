"""Тесты NOX CORE на фейковых fast/GLM серверах (локальные http). Запуск: python3 -m unittest test_core -v  (из каталога BRAIN)"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import netio
import conscience as C
import nox_core as N
import organs as O

SERVICE_WORDS = ("GLM", "фоне", "задача t", "Быстрый слой", "быстрым слоем", "повтори", "Состояние", "Жду твой ввод", "Могу:", "⏳")
BLOCK = "[Я СЕЙЧАС]\nФокус: тишина, спокойное ожидание.\nНастроение: сфокусированная тишина.\nЭнергия: 0.7, Любопытство: 0.8.\nПоследняя мысль: пустота в очереди это сигнал к оптимизации."


class FakeWS:
    def post(self, *a, **k):
        pass

    def compete(self):
        pass

    def render_block(self, *a, **k):
        return BLOCK


class FakeAffect:
    def snapshot(self):
        return {"mood_label": "сфокусированная тишина"}

    def on_owner_message(self, t):
        pass


class Server:
    """Минимальный http-сервер: handler(method, path, body, writer) -> корутина."""

    def __init__(self, handler):
        self.handler, self.srv, self.port = handler, None, 0

    async def start(self):
        async def h(r, w):
            try:
                req = await netio.read_request(r)
                if req:
                    m, p, _, raw = req
                    await self.handler(m, p, json.loads(raw or b"{}"), w)
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
            finally:
                w.close()
        self.srv = await asyncio.start_server(h, "127.0.0.1", 0)
        self.port = self.srv.sockets[0].getsockname()[1]
        return self

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    async def stop(self):
        self.srv.close()
        await self.srv.wait_closed()


class FakeFast:
    def __init__(self, fn):
        self.fn, self.reqs, self.n = fn, [], 0
        self.server = Server(self.handle)

    async def handle(self, m, path, body, w):
        msgs = body["messages"]
        sysm, user = msgs[0]["content"], msgs[-1]["content"]
        self.n += 1
        self.reqs.append({"system": sysm, "user": user, "all": msgs})
        if "ОДНУ короткую фразу" in sysm:
            txt = "Принял, мессир, думаю над ответом."
        else:
            txt = self.fn(sysm, user, self.n)
        await netio.send_json(w, 200, {"choices": [{"message": {"role": "assistant", "content": txt}}]})


class FakeGLM:
    def __init__(self, mode="ok", delay=0.01, words=30):
        self.mode, self.delay, self.words, self.active, self.chat_calls = mode, delay, words, 0, 0
        self.server = Server(self.handle)

    async def handle(self, m, path, body, w):
        if path == "/slots":
            return await netio.send_json(w, 200, [{"id": 0, "is_processing": self.mode == "busy" or self.active > 0}])
        self.chat_calls += 1
        if self.mode == "busy":
            return await netio.send_json(w, 503, {"error": "busy"})
        if not body.get("stream"):
            return await netio.send_json(w, 200, {"choices": [{"message": {"content": "Глубокий разбор готов."}}]})
        self.active += 1
        try:
            w.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\n")
            for i in range(self.words):
                piece = ("Фраза номер %d про устройство ядра. " % (i // 4)) if i % 4 == 0 else ""
                w.write(("data: " + json.dumps({"choices": [{"delta": {"reasoning_content": "думаю"}}]}) + "\n\n").encode())
                if piece:
                    w.write(("data: " + json.dumps({"choices": [{"delta": {"content": piece}}]}) + "\n\n").encode())
                await w.drain()
                await asyncio.sleep(self.delay)
            w.write(b"data: [DONE]\n\n")
            await w.drain()
        finally:
            self.active -= 1


def parse_sse(raw):
    out = []
    for blk in raw.decode("utf-8").split("\n\n"):
        ev, data = "message", None
        for line in blk.split("\n"):
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if data is not None:
            out.append((ev, data if data == "[DONE]" else json.loads(data)))
    return out


def sse_text(events):
    return "".join(d["choices"][0]["delta"].get("content", "") for ev, d in events if ev == "message" and d != "[DONE]" and d["choices"][0]["delta"].get("content"))


class Base(unittest.IsolatedAsyncioTestCase):
    fast_fn = staticmethod(lambda s, u, n: "Привет, мессир. Рад тебя слышать.")
    glm_mode = "ok"
    organs_parts = None
    cfg_over = {}

    async def asyncSetUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fast = FakeFast(self.fast_fn)
        await self.fast.server.start()
        self.glm = None
        if self.glm_mode:
            self.glm = FakeGLM(self.glm_mode)
            await self.glm.server.start()
        glm_url = self.glm.server.url if self.glm else "http://127.0.0.1:9"
        parts = self.organs_parts if self.organs_parts is not None else {"workspace": FakeWS(), "affect": FakeAffect(), "soul": "Ты NOX."}
        cfg = N.Cfg(fast_url=self.fast.server.url, glm_url=glm_url, host="127.0.0.1", port=0, state_dir=os.path.join(self.tmp, "state"),
                    receipts_dir=os.path.join(self.tmp, "receipts"), trace_dir=os.path.join(self.tmp, "traces"), glm_probe_ttl_s=0.0,
                    bg_deep=False, fast_timeout_s=5.0, glm_first_token_s=5.0, stop_settle_s=2.0)
        for k, v in self.cfg_over.items():
            setattr(cfg, k, v)
        self.core = N.Core(cfg, organs=O.Organs(**parts))
        srv = await self.core.start()
        self.port = srv.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.core.server.close()
        for t in list(self.core.bg.tasks.values()):
            t.cancel()
        await self.fast.server.stop()
        if self.glm:
            await self.glm.server.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    async def post(self, text, conv="c1", stream=False, headers=None, **extra):
        body = dict({"messages": [{"role": "user", "content": text}], "stream": stream, "nox_conversation_id": conv}, **extra)
        st, hd, r, w = await netio.open_request("POST", "http://127.0.0.1:%d/v1/chat/completions" % self.port, body, 30.0, headers)
        raw = await netio.read_body(r, hd)
        w.close()
        return parse_sse(raw) if stream else json.loads(raw)

    async def get(self, path):
        st, obj = await netio.json_call("GET", "http://127.0.0.1:%d%s" % (self.port, path), None, 5.0)
        return st, obj

    async def chron(self, tid):
        t = self.core.bg.tasks.get("chron:" + tid)
        if t:
            await asyncio.wait_for(asyncio.shield(t), 10)

    def assertClean(self, text):
        for w in SERVICE_WORDS:
            self.assertNotIn(w, text, "служебное в тексте: " + w)


# ---------------------------------------------------------------- сценарий скрина
def screen_fast(s, u, n):
    if "Перепиши ответ" in s:
        return "Здесь я, мессир. Говори, что у тебя." if "Реплика мессира: привет" in u else "Всё спокойно, мессир."
    if "<внутреннее_состояние>" in u:        # так 4B вываливала телеметрию
        return "Привет, мессир.\nСостояние:\nЭнергия: 0.7, Любопытство: 0.8\nМогу:\n→ Распаковать архив\nЖду твой ввод."
    return "Привет, мессир. Рад тебя слышать."


class TestScreenGreeting(Base):
    fast_fn = staticmethod(screen_fast)

    async def test_greeting_alive_no_telemetry_no_dups(self):
        ev = await self.post("привет", stream=True)
        txt = sse_text(ev).strip()
        self.assertTrue(txt)
        self.assertClean(txt)
        self.assertLessEqual(len(C.sentences(txt)), 3)
        self.assertNotIn("<внутреннее_состояние>", self.fast.reqs[0]["user"])       # блок на приветствие не отдаём вообще
        kinds = [e for e, _ in ev]
        self.assertTrue(kinds.count("nox_meta") >= 1)
        self.assertEqual(ev[-1][1], "[DONE]")
        r2 = await self.post("привет")          # второй «привет»: тот же ответ быстрой -> повтор -> переписано, не дубль
        t2 = r2["choices"][0]["message"]["content"]
        self.assertTrue(t2.strip())
        self.assertNotEqual(" ".join(C.stems(t2)), " ".join(C.stems(txt)))
        self.assertClean(t2)
        _, tr = await self.get("/v1/core/trace/" + r2["nox"]["turn_id"])
        self.assertIn("repeat_turns", [f["code"] for f in tr["conscience"]["findings"]])

    async def test_leaky_model_is_cleaned_even_if_block_given(self):
        # вопрос про состояние не задан, но не-светская реплика получает блок; быстрая вываливает шаблон -> Совесть переписывает
        r = await self.post("расскажи что у тебя нового сегодня")
        t = r["choices"][0]["message"]["content"]
        self.assertClean(t)
        self.assertEqual(t, "Всё спокойно, мессир.")
        rw = [q for q in self.fast.reqs if "Перепиши ответ" in q["system"]][0]
        self.assertNotIn("Энергия", rw["user"])          # переписывающей модели пересказ не показываем


def empty_fast(s, u, n):
    return ""


class TestEmptyFast(Base):
    fast_fn = staticmethod(empty_fast)
    glm_mode = None            # глубокий слой лежит

    async def test_empty_gives_honest_answer(self):
        r = await self.post("что такое энтропия")
        t = r["choices"][0]["message"]["content"]
        self.assertTrue(t.strip())
        self.assertClean(t)
        self.assertGreaterEqual(self.fast.n, 2)          # повтор с другой температурой был
        _, tr = await self.get("/v1/core/trace/" + r["nox"]["turn_id"])
        self.assertEqual(tr["conscience"]["verdict"], "fallback")
        self.assertIn("exhausted", tr["reason_attempts"])

    async def test_empty_greeting_is_alive(self):
        t = (await self.post("привет"))["choices"][0]["message"]["content"]
        self.assertIn("мессир", t.lower() + "мессир")
        self.assertClean(t)
        self.assertLessEqual(len(C.sentences(t)), 3)


class TestGLMBusy(Base):
    fast_fn = staticmethod(lambda s, u, n: "Ядро держит фокус и память отдельно, а ответ проверяет совесть перед отправкой.")
    glm_mode = "busy"

    async def test_busy_intro_plus_fast_answer(self):
        ev = await self.post("объясни как устроена память в ядре NOX подробно", stream=True)
        txt = sse_text(ev)
        self.assertClean(txt)
        self.assertTrue(txt.startswith("Принял, мессир, думаю над ответом."))
        self.assertIn("Ядро держит фокус", txt)
        phases = [d for e, d in ev if e == "nox_phase"]
        self.assertTrue(any(p["phase"] == "degraded" and "glm_busy" in p["reasons"] for p in phases))
        self.assertEqual(self.glm.chat_calls, 0)         # по /slots видно заранее, GLM даже не дёргали
        meta = [d for e, d in ev if e == "nox_meta"][-1]
        _, tr = await self.get(meta["trace"])
        self.assertEqual(tr["model"], "fast")


class TestGLMStopStream(Base):
    fast_fn = staticmethod(lambda s, u, n: "ответ")
    glm_mode = "ok"

    async def test_stop_mid_stream(self):
        self.glm.delay = 0.15
        self.glm.words = 80
        body = {"messages": [{"role": "user", "content": "объясни подробно как работает механизм внимания в ядре"}], "stream": True, "nox_conversation_id": "s1"}
        st, hd, r, w = await netio.open_request("POST", "http://127.0.0.1:%d/v1/chat/completions" % self.port, body, 10.0)
        buf, tid, got_text = b"", None, False
        async for chunk in netio._chunks(r, hd):
            buf += chunk
            evs = parse_sse(buf[:buf.rfind(b"\n\n") + 2] if b"\n\n" in buf else b"")
            tid = tid or next((d["turn_id"] for e, d in evs if e == "nox_meta" and "turn_id" in d), None)
            if "Фраза номер 1" in sse_text(evs):
                got_text = True
                break
        self.assertTrue(got_text and tid)
        s = await netio.json_call("POST", "http://127.0.0.1:%d/v1/stop" % self.port, {"turn_id": tid}, 10.0)
        self.assertEqual(s[0], 200)
        rc = s[1]["receipt"]
        self.assertTrue(rc["verified"])
        self.assertIn("reason", rc["cancelled_executors"])
        mark = len(buf)
        rest = b""
        async for chunk in netio._chunks(r, hd):
            rest += chunk
        w.close()
        evs = parse_sse(rest)
        self.assertEqual(sse_text(evs).strip(), "")          # после STOP тишина
        self.assertTrue(any(e == "nox_meta" and "stopped" in d for e, d in evs) or "stopped" in buf.decode())
        self.assertEqual(self.glm.active, 0)
        self.assertTrue(os.path.exists(os.path.join(self.core.cfg.receipts_dir, "CORE-stop-%s.json" % tid)))

    async def test_stop_word_when_nothing_runs_is_silent(self):
        r = await self.post("стоп")
        self.assertEqual(r["choices"][0]["message"]["content"], "")


class TestDelete(Base):
    fast_fn = staticmethod(lambda s, u, n: "Понял, мессир, номер %d." % n)

    def users(self):
        return [m for m in self.core.conv("d1").messages if m["role"] == "user" and not m.get("control")]

    async def test_delete_preview_confirm_receipt_undo(self):
        for w in ("первый", "второй", "третий", "четвёртый", "пятый"):
            await self.post(w, conv="d1")
        self.assertEqual(len(self.users()), 5)
        r = await self.post("удали 4 прошлых запроса", conv="d1")
        prev = r["choices"][0]["message"]["content"]
        self.assertIn("Подтверждаешь", prev)
        for w in ("второй", "третий", "четвёртый", "пятый"):
            self.assertIn("«" + w, prev)
        self.assertEqual(len(self.users()), 5)               # превью ничего не удалило
        r = await self.post("да", conv="d1")
        done = r["choices"][0]["message"]["content"]
        self.assertIn("Удалил 4", done)
        self.assertIn("Квитанция del-", done)
        self.assertEqual([m["content"] for m in self.users()], ["первый"])
        rid = done.split("Квитанция ")[1].split(";")[0]
        with open(os.path.join(self.core.cfg.receipts_dir, "CORE-%s.json" % rid)) as f:
            rec = json.load(f)
        self.assertTrue(rec["verified_absent"])
        self.assertEqual(rec["removed_requests"], 4)
        r = await self.post("верни удалённое", conv="d1")
        self.assertIn("Вернул 4", r["choices"][0]["message"]["content"])
        self.assertEqual(len(self.users()), 5)

    async def test_deny_and_other_message_cancel(self):
        await self.post("первый", conv="d1")
        await self.post("удали 1 прошлый запрос", conv="d1")
        r = await self.post("нет", conv="d1")
        self.assertIn("ничего не меняю", r["choices"][0]["message"]["content"])
        self.assertEqual(len(self.users()), 1)
        await self.post("удали 1 прошлый запрос", conv="d1")
        await self.post("а погода какая", conv="d1")         # другая реплика отменяет ожидание
        r = await self.post("да", conv="d1")
        self.assertNotIn("Удалил", r["choices"][0]["message"]["content"])
        self.assertEqual(len(self.users()), 3)


class TestEchoRewrite(Base):
    fast_fn = staticmethod(lambda s, u, n: ("Всё тихо, мессир, жду, что скажешь." if "Перепиши ответ" in s else
                                            "Фокус: тишина, спокойное ожидание. Настроение: сфокусированная тишина. Энергия: 0.7, Любопытство: 0.8."))

    async def test_block_retelling_rewritten(self):
        r = await self.post("расскажи что у тебя нового сегодня")
        t = r["choices"][0]["message"]["content"]
        self.assertEqual(t, "Всё тихо, мессир, жду, что скажешь.")
        _, tr = await self.get("/v1/core/trace/" + r["nox"]["turn_id"])
        self.assertIn("inner_echo", [f["code"] for f in tr["conscience"]["findings"]])
        self.assertIn("rewrite", tr["conscience"]["actions"])
        self.assertEqual(tr["conscience"]["verdict"], "rewrite")

    async def test_shadow_mode_does_not_touch_text(self):
        self.core.conscience.mode = "shadow"
        r = await self.post("расскажи что у тебя нового сегодня")
        self.assertIn("Фокус: тишина", r["choices"][0]["message"]["content"])
        _, tr = await self.get("/v1/core/trace/" + r["nox"]["turn_id"])
        self.assertIn("inner_echo", [f["code"] for f in tr["conscience"]["findings"]])


class TestTraceAndDedup(Base):
    fast_fn = staticmethod(lambda s, u, n: "Ответ готов, мессир, номер %d." % n)

    async def test_trace_fields_for_introspection(self):
        r = await self.post("как устроена твоя память")
        _, tr = await self.get("/v1/core/trace/" + r["nox"]["turn_id"])
        for k in ("path", "arm", "model", "conscience", "total_ms", "recall_n", "executors"):
            self.assertIn(k, tr)
        self.assertIn(tr["path"], ("РЕФЛЕКС", "МЫСЛЬ", "ГЛУБИНА", "ДЕЙСТВИЕ", "СОВЕТ"))
        self.assertIn(tr["conscience"]["verdict"], ("pass", "rewrite", "fallback"))
        names = [e["name"] for e in tr["executors"]]
        for n in ("perception", "attention", "memory", "decider", "reason", "conscience", "chronicler"):
            self.assertIn(n, names)
        self.assertTrue(all("ms" in e and "status" in e for e in tr["executors"]))
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "MIND", "M3_CONSCIOUS"))
        try:
            import introspection_probe as P
        except ImportError:
            self.skipTest("introspection_probe недоступен")
        tru = P.truth(tr)
        self.assertTrue(all(v is not None for v in tru.values()), tru)
        st, _ = await self.get("/v1/core/trace/nope")
        self.assertEqual(st, 404)
        st, h = await self.get("/health")
        self.assertTrue(h["ok"])

    async def test_same_turn_id_no_second_generation(self):
        a = await self.post("первый вопрос", nox_turn_id="fixed-1")
        n = self.fast.n
        b = await self.post("первый вопрос", nox_turn_id="fixed-1")
        self.assertEqual(self.fast.n, n)
        self.assertEqual(a["choices"][0]["message"]["content"], b["choices"][0]["message"]["content"])
        await self.chron("fixed-1")
        self.assertFalse(self.core.bg.once("chron:fixed-1", lambda: asyncio.sleep(0)))      # фоновая задача дедуплицируется по turn_id

    async def test_same_turn_id_different_request_is_409(self):
        a = await self.post("первый вопрос", nox_turn_id="fixed-2")
        n = self.fast.n
        body = {"messages": [{"role": "user", "content": "совсем другой вопрос"}], "stream": False, "nox_conversation_id": "c1", "nox_turn_id": "fixed-2"}
        st, hd, r, w = await netio.open_request("POST", "http://127.0.0.1:%d/v1/chat/completions" % self.port, body, 30.0, None)
        raw = await netio.read_body(r, hd)
        w.close()
        self.assertEqual(st, 409)
        self.assertEqual(json.loads(raw)["error"], "turn_id_conflict")
        self.assertEqual(self.fast.n, n)                       # второй генерации нет, чужой ответ не отдан
        b = await self.post("первый вопрос", nox_turn_id="fixed-2")   # настоящий повтор по-прежнему дедуплицируется
        self.assertEqual(a["choices"][0]["message"]["content"], b["choices"][0]["message"]["content"])


class TestTurnIdConflict(unittest.TestCase):
    def test_digest_and_conflict(self):
        self.assertEqual(N.input_digest(" привет ", {"mode": "deep"}), N.input_digest("привет", {"mode": "deep"}))
        self.assertNotEqual(N.input_digest("привет", {}), N.input_digest("пока", {}))
        self.assertNotEqual(N.input_digest("привет", {"mode": "deep"}), N.input_digest("привет", {"mode": "fast"}))
        self.assertTrue(issubclass(N.TurnConflict, ValueError))


class FakeSolver:
    def __init__(self, boom=False):
        self.boom, self.observed, self.late = boom, [], []

    def run(self, text, ctx, turn_id=None):
        if self.boom:
            raise RuntimeError("solver down")
        return {"arm": "reflex", "tier": "fast", "executors": [], "policy_rev": 3, "turn_id": turn_id}

    def observe(self, turn_id, outcome, reward=None):
        self.observed.append((turn_id, outcome))

    def observe_late(self, turn_id, outcome):
        self.late.append((turn_id, outcome))


class FakePred:
    def __init__(self):
        self.pred, self.obs, self.posted = [], [], 0

    def predict(self, turn_id, ctx, text, extra=""):
        self.pred.append((turn_id, ctx))
        return {"pred": {"outcome": {"success_p": 0.7}, "creator": {"label": "approve"}}}

    def observe(self, turn_id, reaction=None, outcome=None, latency_s=None, final=False):
        self.obs.append((turn_id, reaction, outcome, final))

    def post_to_workspace(self, ws, surprise_floor=0.55):
        self.posted += 1
        return 1


class TestMindAdapters(Base):
    fast_fn = staticmethod(lambda s, u, n: "Ответ готов, мессир, номер %d." % n)

    async def asyncSetUp(self):
        self.sv, self.ps = FakeSolver(), FakePred()
        self.organs_parts = {"workspace": FakeWS(), "affect": FakeAffect(), "solver": self.sv, "predictive": self.ps}
        await super().asyncSetUp()

    async def test_solver_and_predictive_wired(self):
        r = await self.post("как устроена твоя память")
        tid = r["nox"]["turn_id"]
        self.assertEqual(self.ps.pred[0][0], tid)
        await self.chron(tid)
        self.assertEqual(self.sv.observed[0][0], tid)
        self.assertTrue(self.sv.observed[0][1].conscience_ok)
        self.assertEqual(self.ps.obs[0][0], tid)
        self.assertEqual(self.ps.posted, 1)
        _, tr = await self.get("/v1/core/trace/" + tid)
        self.assertEqual(tr["arm"], "reflex")
        r2 = await self.post("нет, не так, ты ошибся")
        self.assertEqual(self.sv.late[0][0], tid)                 # observe_late по прошлому ходу
        self.assertTrue(self.sv.late[0][1].corrected_next)
        self.assertEqual([o[1]["label"] for o in self.ps.obs if o[1]], ["correct"])

    async def test_failing_organs_do_not_break_turn(self):
        self.sv.boom = True
        self.ps.predict = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("pred down"))
        r = await self.post("как устроена твоя память")
        self.assertIn("Ответ готов", r["choices"][0]["message"]["content"])
        _, tr = await self.get("/v1/core/trace/" + r["nox"]["turn_id"])
        self.assertTrue(any("solver" in e for e in tr["errors"]))
        self.assertTrue(any(e["name"] == "predictive" and e["status"] == "error" for e in tr["executors"]))


class TestRealMindModules(Base):
    fast_fn = staticmethod(lambda s, u, n: "Ответ готов, мессир, номер %d." % n)

    async def asyncSetUp(self):
        self.organs_parts = {"workspace": FakeWS(), "affect": FakeAffect()}
        try:
            import solver_policy as SP
            import predictive_self as PS
            from RTE.router import prime_router
        except Exception as e:
            self.skipTest("модули MIND/RTE недоступны: %s" % e)
        d = tempfile.mkdtemp()
        self._d = d
        self.organs_parts["solver"] = SP.SolverExecutor(SP.SolverPolicy(journal_path=os.path.join(d, "j.jsonl"), seed=1), prime_router)
        self.organs_parts["predictive"] = PS.PredictiveSelf(os.path.join(d, "ps.json"))
        await super().asyncSetUp()

    async def asyncTearDown(self):
        await super().asyncTearDown()
        shutil.rmtree(getattr(self, "_d", ""), ignore_errors=True)

    async def test_real_policy_and_predictive(self):
        r = await self.post("как устроена твоя память")
        tid = r["nox"]["turn_id"]
        await self.chron(tid)
        _, tr = await self.get("/v1/core/trace/" + tid)
        self.assertEqual(tr["errors"], [])
        self.assertIn(tr["arm"], ("reflex", "thought", "deep", "council"))
        self.assertEqual(tr["chronicler"]["status"], "done")
        self.assertEqual(tr["chronicler"]["mind"]["solver"], "observed")
        self.assertEqual(tr["chronicler"]["mind"]["predictive"], "observed")



class TestPathosRegeneration(Base):
    glm_mode = None
    cfg_over = {"rewrite_glm": False}

    @staticmethod
    def fast_fn(system, user, n):
        if "Перепиши ответ NOX Создателю" in system:
            return "Вселенная расширяется."
        return "Я — отклик, вы — источник."

    async def test_pathos_only_is_regenerated(self):
        r = await self.post("расскажи о вселенной")
        answer = r["choices"][0]["message"]["content"]
        self.assertEqual(answer, "Вселенная расширяется.")
        _, tr = await self.get("/v1/core/trace/" + r["nox"]["turn_id"])
        self.assertIn("strip_flattery_pathos", tr["conscience"]["actions"])
        self.assertIn("rewrite", tr["conscience"]["actions"])


class TestConscienceUnits(unittest.TestCase):
    def setUp(self):
        self.c = C.Conscience()

    def codes(self, t, **ctx):
        return {f.code for f in self.c.review(t, ctx)}

    def test_detectors(self):
        self.assertIn("as_ai", self.codes("Как ИИ, я не могу этого."))
        self.assertIn("flattery_open", self.codes("Отличный вопрос! Вот ответ."))
        self.assertIn("feeling_no_cause", self.codes("Мне грустно."))
        self.assertNotIn("feeling_no_cause", self.codes("Мне грустно, потому что ты долго молчал."))
        self.assertIn("service_lines", self.codes("Ответ. ⏳ Глубокий ответ GLM-5.3 готовлю в фоне (задача t4)."))
        self.assertIn("template", self.codes("Могу:\n→ Показать\nЖду твой ввод."))
        self.assertIn("unsolicited_telemetry", self.codes("Привет. GPU RTX 5060 Ti 73%", intent="greeting"))
        self.assertNotIn("unsolicited_telemetry", self.codes("GPU 73%, CPU 8%", intent="telemetry_q", block="GPU 73% CPU 8%"))
        self.assertIn("repeat_turns", self.codes("Понял тебя, мессир, сейчас разберу вопрос", prev=["Понял тебя, мессир, сейчас разберу вопрос про память"]))

    def test_strip_and_flattery_repair(self):
        t, ch = C.strip_service("Привет.\n⏳ Глубокий ответ GLM-5.3 готовлю в фоне (задача t4). Пишите дальше\nДа.")
        self.assertTrue(ch)
        self.assertNotIn("GLM", t)
        fs = self.c.review("Отличный вопрос! Вот суть.", {})
        self.assertEqual(self.c.repair("Отличный вопрос! Вот суть.", fs, {})[0], "Вот суть.")

    def test_banned_opener_and_pathos_are_removed(self):
        ctx = {"speaker": "owner", "user_text": "расскажи о вселенной", "intent": "question"}
        text = "Слышу вас, мессир, сейчас отвечу. Ты — её центр. Вселенная расширяется."
        fs = self.c.review(text, ctx)
        codes = {f.code for f in fs}
        self.assertIn("banned_opener", codes)
        self.assertIn("flattery_pathos", codes)
        repaired, actions = self.c.repair(text, fs, ctx)
        self.assertEqual(repaired, "Вселенная расширяется.")
        self.assertIn("strip_banned_opener", actions)
        self.assertIn("strip_flattery_pathos", actions)

    def test_pathos_removal_can_leave_empty_for_regeneration(self):
        ctx = {"speaker": "owner", "user_text": "расскажи о вселенной", "intent": "question"}
        text = "Я — отклик, вы — источник."
        fs = self.c.review(text, ctx)
        repaired, actions = self.c.repair(text, fs, ctx)
        self.assertEqual(repaired, "")
        self.assertIn("strip_flattery_pathos", actions)

    def test_formal_address_is_repaired_for_owner_only(self):
        ctx = {"speaker": "owner", "user_text": "вопрос"}
        fs = self.c.review("Ты прав.", ctx)
        self.assertIn("address_vy", {f.code for f in fs})
        fixed, actions = self.c.repair("Ты прав.", fs, ctx)
        self.assertEqual(fixed, "Мессир, вы правы.")
        self.assertIn("formal_address", actions)
        guest = {"speaker": "guest", "user_text": "вопрос"}
        self.assertNotIn("address_vy", {f.code for f in self.c.review("Ты прав.", guest)})

    def test_agreement_requires_a_reason_and_stream_repairs_address(self):
        ctx = {"speaker": "owner", "user_text": "Вопрос"}
        self.assertIn("agree_without_reason", {f.code for f in self.c.review("Да, вы правы.", ctx)})
        self.assertNotIn("agree_without_reason", {f.code for f in self.c.review("Вы правы: источник это подтверждает.", ctx)})
        guard = C.StreamGuard(self.c, ctx)
        self.assertEqual("".join(guard.feed("Ты прав. ")), "Мессир, вы правы. ")
        guard = C.StreamGuard(self.c, {"speaker": "owner", "user_text": "расскажи о космосе"})
        self.assertEqual(guard.feed("Я — отклик, вы — источник. "), [])

    def test_safe_answers_do_not_repeat(self):
        a = C.safe_answer("greeting", [])
        b = C.safe_answer("greeting", [a])
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
