import asyncio, json, os, shutil, tempfile, time, unittest
import aio, router as R, bridge_intro as BI
from stream_hub import Hub, parse_last_event_id, to_sse
from stop import StopController, parse_slots
import rte_server as S
from fakes import FakeLLM


def run(coro):
    return asyncio.run(coro)


async def sse_events(url, headers=None, limit=None, timeout=15.0):
    """Читает SSE; -> список (id, event, data). limit — оборвать соединение после N кадров (имитация обрыва сети)."""
    st, h, r, w = await aio.open_request("GET", url, None, timeout, headers)
    out, cur = [], {}
    try:
        buf = b""
        async for chunk in aio._chunks(r, h):
            buf += chunk
            while b"\n\n" in buf:
                frame, buf = buf.split(b"\n\n", 1)
                cur = {}
                for ln in frame.decode().split("\n"):
                    k, _, v = ln.partition(": ")
                    cur[k] = v
                if "data" in cur:
                    out.append((cur.get("id"), cur.get("event"), json.loads(cur["data"])))
                    if limit and len([e for e in out if e[1] != "hb"]) >= limit:
                        return out
    finally:
        w.close()
    return out


async def post(url, obj, timeout=10.0):
    return await aio.json_call("POST", url, obj, timeout)


class RouterTests(unittest.TestCase):
    def test_greeting_fast(self):
        p = R.route("привет", deep_tps=1.5)
        self.assertEqual(p.tier, "fast")
        self.assertFalse(p.enable_thinking)

    def test_deep_down_goes_fast(self):
        p = R.route("Спроектируй архитектуру и объясни почему", deep_tps=1.5, deep_up=False)
        self.assertEqual((p.tier, p.reason), ("fast", "deep_down"))

    def test_low_tps_skips_thinking_and_caps_answer(self):
        p = R.route("Проанализируй архитектуру, объясни почему так, сравни варианты и подумай глубоко над рисками", deep_tps=1.5)
        self.assertFalse(p.enable_thinking)
        self.assertTrue(any("think_skipped_low_tps" in n for n in p.notes))
        self.assertLessEqual(p.eta_s, 245)
        self.assertTrue(p.intro)

    def test_fast_gpu_gets_thinking(self):
        p = R.route("Проанализируй архитектуру, объясни почему так, сравни варианты и подумай глубоко над рисками", deep_tps=12.0)
        self.assertEqual(p.tier, "deep_think")
        self.assertTrue(p.enable_thinking)
        self.assertGreaterEqual(p.think_budget, 256)
        self.assertEqual(p.gateway_fields()["chat_template_kwargs"], {"enable_thinking": True})

    def test_mode_max_forces_think_budget_by_tps(self):
        p = R.route("ответь", deep_tps=6.0, mode="max")
        self.assertEqual((p.tier, p.effort), ("deep_think", "max"))
        self.assertEqual(p.think_budget, 360)       # 6 ток/с * 60 с

    def test_mode_fast(self):
        self.assertEqual(R.route("посчитай интеграл и объясни", deep_tps=9, mode="fast").tier, "fast")


class HubTests(unittest.TestCase):
    def test_parse_last_event_id(self):
        self.assertEqual(parse_last_event_id("t-1:7", "t-1"), 7)
        self.assertEqual(parse_last_event_id("t-2:7", "t-1"), 0)
        self.assertEqual(parse_last_event_id("мусор", "t-1"), 0)

    def test_resume_no_dups_no_gaps_and_generation_survives_disconnect(self):
        async def go():
            async def prod(turn, msgs, opts):
                for i in range(10):
                    await turn.publish("delta", stage="deep", text="%d," % i)
                    await asyncio.sleep(0.01)
            hub = Hub(prod)
            turn, st = hub.start_turn("c1", "m1", "q")
            self.assertEqual(st, "created")
            got = []
            async for ev in turn.subscribe(0):          # клиент «обрывается» после 4 событий
                got.append(ev)
                if len(got) == 4:
                    break
            last = got[-1]["seq"]
            await asyncio.sleep(0.3)                    # ход продолжается без клиента
            self.assertEqual(turn.status, "done")
            rest = [e async for e in turn.subscribe(last)]
            seqs = [e["seq"] for e in got + rest]
            self.assertEqual(seqs, list(range(1, len(seqs) + 1)))
            text = "".join(e["text"] for e in got + rest if e["type"] == "delta")
            self.assertEqual(text, "".join("%d," % i for i in range(10)))
        run(go())

    def test_idempotent_start_and_busy_and_shared_history(self):
        async def go():
            gate = asyncio.Event()
            calls = []

            async def prod(turn, msgs, opts):
                calls.append(msgs)
                await turn.publish("delta", stage="deep", text="ответ%d" % len(calls))
                await gate.wait()
            hub = Hub(prod)
            t1, s1 = hub.start_turn("c", "m1", "первый", source="full")
            t1b, s1b = hub.start_turn("c", "m1", "первый", source="full")
            self.assertEqual((s1, s1b, t1 is t1b), ("created", "duplicate", True))
            t2, s2 = hub.start_turn("c", "m2", "второй", source="mini")
            self.assertEqual((s2, t2 is t1), ("busy", True))
            gate.set()
            await asyncio.sleep(0.05)
            t3, s3 = hub.start_turn("c", "m3", "третий", source="mini")
            self.assertEqual(s3, "created")
            await asyncio.sleep(0.05)
            self.assertEqual(len(calls), 2)
            self.assertEqual([m["role"] for m in calls[1]], ["user", "assistant", "user"])   # мини-чат видит историю полного
            self.assertEqual(calls[1][1]["content"], "ответ1")
        run(go())

    def test_hb_frames_and_error_on_producer_exception(self):
        async def go():
            async def slow(turn, msgs, opts):
                await asyncio.sleep(0.35)

            async def boom(turn, msgs, opts):
                raise RuntimeError("упал")
            hub = Hub(slow)
            t, _ = hub.start_turn("c", "a", "q")
            t.hb_s = 0.1
            evs = [e async for e in t.subscribe(0)]
            self.assertTrue(any(e["type"] == "hb" for e in evs))
            self.assertNotIn("seq", [e for e in evs if e["type"] == "hb"][0])
            hub2 = Hub(boom)
            t2, _ = hub2.start_turn("c", "a", "q")
            evs2 = [e async for e in t2.subscribe(0)]
            self.assertEqual(evs2[-1]["type"], "error")
        run(go())

    def test_persist_and_restart_marks_unfinished(self):
        async def go():
            d = tempfile.mkdtemp()
            try:
                async def prod(turn, msgs, opts):
                    await turn.publish("delta", stage="deep", text="часть")
                    await asyncio.sleep(10)
                hub = Hub(prod, persist_dir=d)
                t, _ = hub.start_turn("c", "m", "q")
                await asyncio.sleep(0.1)
                t.task.cancel()
                await asyncio.sleep(0.05)
                os.replace(os.path.join(d, t.id + ".jsonl"), os.path.join(d, t.id + ".jsonl"))
                # имитируем падение процесса: терминального события в файле нет
                lines = open(os.path.join(d, t.id + ".jsonl"), encoding="utf-8").read().splitlines()
                with open(os.path.join(d, t.id + ".jsonl"), "w", encoding="utf-8") as f:
                    f.write("\n".join(l for l in lines if '"type": "error"' not in l) + "\n")
                hub2 = Hub(prod, persist_dir=d)
                self.assertEqual(hub2.load(), 1)
                t2 = hub2.get(t.id)
                self.assertEqual(t2.status, "error")
                self.assertEqual(t2.events[-1]["code"], "restart")
                self.assertEqual("".join(e["text"] for e in t2.events if e["type"] == "delta"), "часть")
            finally:
                shutil.rmtree(d, ignore_errors=True)
        run(go())

    def test_openai_compat_frame(self):
        b = to_sse("t-1", {"seq": 3, "type": "delta", "stage": "intro", "text": "я"}, "openai").decode()
        self.assertTrue(b.startswith("id: t-1:3\n"))
        o = json.loads(b.split("data: ", 1)[1])
        self.assertEqual(o["choices"][0]["delta"]["content"], "я")
        self.assertIn("[DONE]", to_sse("t-1", {"seq": 4, "type": "done"}, "openai").decode())


class IntroTests(unittest.TestCase):
    def test_validator(self):
        self.assertTrue(BI.intro_safe("Принял, мессир, секунду.")[0])
        self.assertEqual(BI.intro_safe("Столица Франции Париж.")[1][:11], "proper_name")
        self.assertFalse(BI.intro_safe("Это 5 минут работы")[0])
        self.assertFalse(BI.intro_safe("Хотите узнать подробнее?")[0])
        self.assertFalse(BI.intro_safe("Принял, мессир. Разбираю архитектуру базы", "расскажи про архитектуру базы")[0])

    def test_fast_intro_under_2s(self):
        async def go():
            f = FakeLLM(intro_text="Слышу вас, мессир, берусь разбирать.")
            url = await f.start()
            try:
                r = await BI.make_intro("Объясни устройство памяти", url)
                self.assertEqual(r["source"], "fast")
                self.assertLess(r["ms"], 2000)
            finally:
                await f.stop()
        run(go())

    def test_slow_fast_model_gets_canned_within_deadline(self):
        async def go():
            f = FakeLLM(intro_delay=3.0)
            url = await f.start()
            try:
                r = await BI.make_intro("Объясни устройство памяти", url, deadline_s=0.5)
                self.assertEqual(r["source"], "canned")
                self.assertLess(r["ms"], 900)
            finally:
                await f.stop()
        run(go())

    def test_unsafe_fast_output_replaced(self):
        async def go():
            f = FakeLLM(intro_text="Столица Франции — Париж, 2 млн человек.")
            url = await f.start()
            try:
                r = await BI.make_intro("Какая столица у Франции", url)
                self.assertEqual(r["source"], "canned")
                self.assertTrue(r["reason"].startswith(("fact_markers", "proper_name")))
            finally:
                await f.stop()
        run(go())

    def test_dead_fast_url(self):
        r = run(BI.make_intro("привет", "http://127.0.0.1:1"))
        self.assertEqual(r["source"], "canned")
        self.assertEqual(r["text"], BI.canned("привет"))

    def test_deep_note_appended_to_last_user(self):
        m = BI.with_intro_note([{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}])
        self.assertTrue(m[-1]["content"].startswith("c\n\n[Мессиру"))
        self.assertEqual(m[0]["content"], "a")


class SlotsParse(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_slots([{"id": 0, "is_processing": True, "next_token": [{"n_decoded": 5}]}]), [{"id": 0, "busy": True, "n_decoded": 5}])
        self.assertEqual(parse_slots([{"id": 1, "is_processing": False, "next_token": {"n_decoded": 0}}])[0]["busy"], False)
        self.assertEqual(parse_slots({"error": 1}), [])


async def _setup(deep_kw=None, fast_kw=None, deep_url_override=None, **cfgkw):
    deep, fast = FakeLLM(**(deep_kw or {})), FakeLLM(**(fast_kw or {"intro_text": "Принял, мессир, секунду."}))
    du, fu = await deep.start(), await fast.start()
    d = tempfile.mkdtemp()
    cfg = S.Cfg(gateway=deep_url_override or du, deep_slots=du, fast=fu, host="127.0.0.1", port=0, state_dir=d, receipts_dir=os.path.join(d, "rc"),
                hb_s=0.15, settle_s=2.0, **cfgkw)
    handle, hub, ctl, pipe = S.make_app(cfg)
    srv = await asyncio.start_server(handle, "127.0.0.1", 0)
    base = "http://127.0.0.1:%d" % srv.sockets[0].getsockname()[1]

    async def close():
        srv.close()
        await deep.stop()
        await fast.stop()
        shutil.rmtree(d, ignore_errors=True)
    return base, deep, fast, hub, close


LONG = "Объясни подробно, почему архитектура памяти устроена так, и сравни варианты"


class StopTests(unittest.TestCase):
    def _stop_case(self, honor, linger):
        async def go():
            base, deep, fast, hub, close = await _setup(deep_kw=dict(tokens=200, tok_delay=0.02, first_delay=0.05, honor_disconnect=honor, linger_tokens=linger))
            try:
                st, t = await post(base + "/v1/turns", {"conversation_id": "c", "client_msg_id": "m", "message": LONG})
                for _ in range(100):
                    await asyncio.sleep(0.05)
                    if hub.get(t["turn_id"]).text.count("т") > 3:
                        break
                st, r = await post(base + "/v1/turns/%s/stop" % t["turn_id"], {})
                self.assertEqual(st, 200)
                rc = r["receipt"]
                turn = hub.get(t["turn_id"])
                self.assertEqual(turn.status, "stopped")
                self.assertEqual(turn.events[-1]["type"], "stopped")
                n = len(turn.events)
                await asyncio.sleep(0.4)
                self.assertEqual(len(turn.events), n)         # после STOP новых кадров нет
                return rc, deep
            finally:
                await close()
        return run(go())

    def test_stop_receipt_zero_tokens_after_stop(self):
        rc, deep = self._stop_case(honor=True, linger=0)
        self.assertTrue(rc["upstream_closed"])
        self.assertTrue(rc["slot_idle"])
        self.assertEqual(rc["tokens_after_stop"], 0)
        self.assertTrue(rc["verified"])
        self.assertLess(deep.n_decoded, 200)

    def test_stop_receipt_honest_when_upstream_ignores_disconnect(self):
        rc, deep = self._stop_case(honor=False, linger=40)
        self.assertGreater(rc["tokens_after_stop"], 0)         # не врём нулём
        self.assertFalse(rc["verified"])

    def test_stop_without_slots_is_unverified_not_zero(self):
        async def go():
            async def prod(turn, m, o):
                await turn.publish("delta", stage="deep", text="x")
                await asyncio.sleep(10)
            hub = Hub(prod)
            t, _ = hub.start_turn("c", "m", "q")
            await asyncio.sleep(0.05)
            ctl = StopController(hub, slots_url="http://127.0.0.1:1", receipts_dir=None, settle_s=0.3)
            r = await ctl.stop(t.id)
            self.assertIsNone(r["receipt"]["tokens_after_stop"])
            self.assertFalse(r["receipt"]["verified"])
            r2 = await ctl.stop(t.id)
            self.assertEqual(r2["already"], "stopped")
            self.assertEqual((await ctl.stop("нет"))["error"], "unknown_turn")
        run(go())

    def test_receipt_file_written(self):
        async def go():
            d = tempfile.mkdtemp()
            try:
                async def prod(turn, m, o):
                    await asyncio.sleep(10)
                hub = Hub(prod)
                t, _ = hub.start_turn("c", "m", "q")
                await asyncio.sleep(0.02)
                await StopController(hub, receipts_dir=d, settle_s=0.1).stop(t.id)
                with open(os.path.join(d, "RTE-stop-%s.json" % t.id), encoding="utf-8") as fh:
                    rc = json.load(fh)
                self.assertEqual(rc["turn_id"], t.id)
            finally:
                shutil.rmtree(d, ignore_errors=True)
        run(go())


class E2E(unittest.TestCase):
    def test_intro_first_then_deep_and_resume_after_drop_without_duplicates(self):
        async def go():
            base, deep, fast, hub, close = await _setup(deep_kw=dict(tokens=14, first_delay=0.4, tok_delay=0.03))
            try:
                t0 = time.time()
                st, t = await post(base + "/v1/turns", {"conversation_id": "conv", "client_msg_id": "m1", "message": LONG, "source": "full"})
                self.assertEqual((st, t["state"]), (200, "created"))
                first = await sse_events(base + "/v1/turns/%s/events" % t["turn_id"], limit=4)
                self.assertLess(len(first), 8)
                last_id = [e for e in first if e[0]][-1][0]
                self.assertEqual(first[0][1], "meta")
                full_text_before = "".join(e[2]["text"] for e in first if e[1] == "delta")
                await asyncio.sleep(0.2)
                rest = await sse_events(base + "/v1/turns/%s/events" % t["turn_id"], {"Last-Event-ID": last_id})
                allev = [e for e in first if e[1] != "hb"] + [e for e in rest if e[1] != "hb"]
                ids = [e[0] for e in allev if e[0]]
                seqs = [int(i.split(":")[1]) for i in ids]
                # перекрытия нет: seq строго растёт, пропусков нет
                self.assertEqual(seqs, list(range(1, len(seqs) + 1)))
                deltas = [e[2] for e in allev if e[1] == "delta"]
                self.assertEqual(deltas[0]["stage"], "intro")
                self.assertEqual(deltas[0]["memory"], False)
                deep_text = "".join(d["text"] for d in deltas if d["stage"] == "deep")
                self.assertEqual(deep_text.strip().split(), ["т%d" % i for i in range(14)])
                self.assertEqual(allev[-1][1], "done")
                self.assertEqual(deep.generations, 1)               # обрыв клиента НЕ перезапустил GLM
                # intro пришёл раньше первого токена GLM (first_delay 0.4 с) и быстрее 2 с
                ti = [e for e in hub.get(t["turn_id"]).events if e["type"] == "delta"]
                self.assertEqual(ti[0]["stage"], "intro")
                self.assertLess(ti[0]["t"] - t0, 2.0)
                # дубль POST после обрыва: тот же ход, без второй генерации
                st, t2 = await post(base + "/v1/turns", {"conversation_id": "conv", "client_msg_id": "m1", "message": LONG})
                self.assertEqual((t2["state"], t2["turn_id"]), ("duplicate", t["turn_id"]))
                self.assertEqual(deep.generations, 1)
                # общий диалог: мини-чат видит историю полного
                st, t3 = await post(base + "/v1/turns", {"conversation_id": "conv", "client_msg_id": "m2", "message": "привет", "source": "mini"})
                self.assertEqual(t3["state"], "created")
                st, conv = await aio.json_call("GET", base + "/v1/conversations/conv", None, 5)
                roles = [m["role"] for m in conv["messages"]]
                self.assertEqual(roles[:3], ["user", "assistant", "user"])
                self.assertEqual({m.get("source") for m in conv["messages"] if m["role"] == "user"}, {"full", "mini"})
                await sse_events(base + "/v1/turns/%s/events" % t3["turn_id"])
            finally:
                await close()
        run(go())

    def test_deep_in_gateway_body_has_plan_fields_and_intro_note(self):
        async def go():
            base, deep, fast, hub, close = await _setup(deep_kw=dict(tokens=3, first_delay=0.05))
            try:
                st, t = await post(base + "/v1/turns", {"conversation_id": "c", "client_msg_id": "m", "message": LONG})
                await sse_events(base + "/v1/turns/%s/events" % t["turn_id"])
                b = [r for r in deep.requests if r.get("stream")][0]
                self.assertEqual(b["nox_mode"], "deep_only")
                self.assertIn("enable_thinking", b["chat_template_kwargs"])
                self.assertIn("Мессиру уже показана", b["messages"][-1]["content"])
            finally:
                await close()
        run(go())

    def test_busy_409(self):
        async def go():
            base, deep, fast, hub, close = await _setup(deep_kw=dict(tokens=100, tok_delay=0.05))
            try:
                st, t = await post(base + "/v1/turns", {"conversation_id": "c", "client_msg_id": "m1", "message": LONG})
                st2, b = await post(base + "/v1/turns", {"conversation_id": "c", "client_msg_id": "m2", "message": "привет"})
                self.assertEqual((st2, b["turn_id"]), (409, t["turn_id"]))
                await post(base + "/v1/turns/%s/stop" % t["turn_id"], {})
            finally:
                await close()
        run(go())

    def test_gateway_502_falls_back_to_fast_with_honest_notice(self):
        async def go():
            base, deep, fast, hub, close = await _setup(deep_url_override="http://127.0.0.1:1", fast_kw=dict(tokens=5, first_delay=0.05, prefix="б"))
            try:
                st, t = await post(base + "/v1/turns", {"conversation_id": "c", "client_msg_id": "m", "message": LONG})
                evs = await sse_events(base + "/v1/turns/%s/events" % t["turn_id"])
                txt = "".join(e[2]["text"] for e in evs if e[1] == "delta")
                self.assertIn("GLM сейчас недоступен", txt)
                self.assertIn("б4", txt)
                self.assertEqual(evs[-1][1], "done")
                self.assertTrue(any(e[1] == "stage" and e[2].get("phase") == "fallback" for e in evs))
            finally:
                await close()
        run(go())

    def test_thinking_phase_emits_data_frames_not_empty_stream(self):
        async def go():
            base, deep, fast, hub, close = await _setup(deep_kw=dict(tokens=2, first_delay=0.8, tok_delay=0.01))
            try:
                st, t = await post(base + "/v1/turns", {"conversation_id": "c", "client_msg_id": "m", "message": LONG})
                evs = await sse_events(base + "/v1/turns/%s/events" % t["turn_id"])
                stages = [e for e in evs if e[1] == "stage"]
                self.assertTrue(stages and stages[0][2]["phase"] == "thinking")
                self.assertGreaterEqual(len([e for e in evs if e[1] in ("delta", "stage", "hb")]), 3)
            finally:
                await close()
        run(go())

    def test_simple_greeting_uses_fast_tier_without_touching_glm(self):
        async def go():
            base, deep, fast, hub, close = await _setup(fast_kw=dict(tokens=4, first_delay=0.02, prefix="ф"))
            try:
                st, t = await post(base + "/v1/turns", {"conversation_id": "c", "client_msg_id": "m", "message": "привет"})
                evs = await sse_events(base + "/v1/turns/%s/events" % t["turn_id"])
                self.assertEqual(deep.generations, 0)
                self.assertIn("ф3", "".join(e[2]["text"] for e in evs if e[1] == "delta"))
                self.assertEqual([e[2]["plan"]["tier"] for e in evs if e[1] == "meta" and "plan" in e[2]], ["fast"])
            finally:
                await close()
        run(go())


if __name__ == "__main__":
    unittest.main(verbosity=1)


class ProbeTest(unittest.TestCase):
    def test_probe_passes_against_rte_with_fakes(self):
        import probe_pv01 as PV

        async def go():
            base, deep, fast, hub, close = await _setup(deep_kw=dict(tokens=40, first_delay=0.3, tok_delay=0.1))
            try:
                return await PV.run_probe(base, LONG, first_frame_s=2.0)
            finally:
                await close()
        res = run(go())
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["stop_receipt"]["tokens_after_stop"], 0)
