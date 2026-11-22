"""RTE-05 rte_server.py: asyncio-фронт «ответ без ожидания» перед шлюзом :8082 (слушает :8084).
POST /v1/turns            {conversation_id?, client_msg_id, message, mode?, source?: full|mini}  [?stream=1 — сразу SSE]
GET  /v1/turns/<id>/events   Last-Event-ID: <turn>:<seq> | ?after=<seq>   [&compat=openai]
POST /v1/turns/<id>/stop     -> квитанция (stop.py)
GET  /v1/conversations/<id>  -> общая история полного и мини-чата
GET  /v1/rte/health
Конвейер хода: router -> (быстрое вступление || GLM-стрим) -> дельты; GLM молчит/упал до первого токена -> честный запасной быстрый ответ."""
import asyncio, json, os, sys, time
from urllib.parse import urlparse, parse_qs
import aio, router as R, bridge_intro as BI
from stream_hub import Hub, to_sse, parse_last_event_id
from stop import StopController


class Cfg:
    def __init__(self, **kw):
        e = os.environ.get
        self.gateway = e("NOX_GATEWAY_URL", "http://127.0.0.1:8082")
        self.deep_slots = e("NOX_DEEP_SLOTS_URL", "http://127.0.0.1:8081")   # llama-server GLM (/slots)
        self.fast = e("NOX_FAST_UPSTREAM", "http://127.0.0.1:8083")
        self.host, self.port = e("RTE_HOST", "127.0.0.1"), int(e("RTE_PORT", "8084"))
        self.state_dir = e("RTE_STATE_DIR", "/root/nox/state/rte")
        self.receipts_dir = e("NOX_RECEIPTS_DIR", "/root/nox/receipts")
        self.intro_deadline_s = float(e("RTE_INTRO_DEADLINE_S", "1.8"))
        self.first_token_max_s = float(e("RTE_FIRST_TOKEN_MAX_S", "240"))   # дольше GLM без токена -> запасной быстрый ответ
        self.hb_s = float(e("RTE_HB_S", "3"))
        self.intro_on = e("RTE_INTRO", "0") == "1"          # c600: вступление «Слышу вас…» выключено; RTE_INTRO=1 вернёт
        self.default_deep_tps = float(e("NOX_DEFAULT_TPS_DEEP", "1.5"))
        self.settle_s = float(e("RTE_STOP_SETTLE_S", "4"))
        self.__dict__.update(kw)


class Pipeline:
    def __init__(self, cfg):
        self.cfg = cfg
        self.tps_deep = cfg.default_deep_tps       # обновляется по факту (EWMA) из завершённых ходов
        self.deep_down_until = 0.0
        self.router_cfg, self._cfg_mtime = R.RouterConfig(), None       # RTE-11: пороги из router_thresholds.json
        self.drafts = None                                               # RTE-12: DraftStore (ночные заготовки), если есть state_dir
        if getattr(cfg, "state_dir", None):
            import drafts as _D
            self.drafts = _D.DraftStore(os.path.join(cfg.state_dir, "drafts.json"))

    def _reload_cfg(self):
        p = os.path.join(self.cfg.state_dir, "router_thresholds.json") if getattr(self.cfg, "state_dir", None) else None
        try:
            m = os.path.getmtime(p) if p else None
        except OSError:
            m = None
        if m != self._cfg_mtime:
            self._cfg_mtime = m
            self.router_cfg = R.tuned_config(p) if m else R.RouterConfig()

    def deep_up(self):
        return time.time() >= self.deep_down_until

    async def fetch_tps(self):
        try:
            st, obj = await aio.json_call("GET", self.cfg.gateway + "/v1/nox/stats", None, 1.5)
            t = ((obj or {}).get("speed") or {}).get("deep", {}).get("tps")
            if st == 200 and t:
                self.tps_deep = float(t)
        except Exception:
            pass

    async def __call__(self, turn, messages, opts):
        cfg = self.cfg
        user = messages[-1]["content"]
        await self.fetch_tps()
        self._reload_cfg()
        if self.drafts and opts.get("mode") not in ("deep", "max"):
            try:
                hit = self.drafts.lookup(user)
            except Exception:
                hit = None
            if hit:     # RTE-12: заготовка с TTL и пометкой источника, GLM не трогаем
                await turn.publish("meta", plan={"tier": "draft", "reason": "sleep_time_draft", "eta_s": 0.0}, deep_tps=round(self.tps_deep, 2))
                return await turn.publish("delta", stage="draft", text=hit["text"])
        plan = R.route(user, deep_tps=self.tps_deep, deep_up=self.deep_up(), fast_up=bool(cfg.fast), mode=opts.get("mode"), history_turns=len(messages) // 2, cfg=self.router_cfg)
        await turn.publish("meta", plan=plan.to_dict(), deep_tps=round(self.tps_deep, 2))
        if plan.tier == "fast":
            return await self._fast_answer(turn, messages, "fast")
        q = asyncio.Queue()
        deep = asyncio.ensure_future(self._pump_deep(turn, messages, plan, q))
        intro_task = asyncio.ensure_future(BI.make_intro(user, cfg.fast, deadline_s=cfg.intro_deadline_s)) if (plan.intro and cfg.intro_on) else None
        intro_text = None
        try:
            first = asyncio.ensure_future(q.get())
            if intro_task:
                done, _ = await asyncio.wait({intro_task, first}, return_when=asyncio.FIRST_COMPLETED)
                if intro_task in done:
                    r = intro_task.result()
                    intro_text = r["text"]
                    await turn.publish("delta", stage="intro", text=intro_text, source=r["source"], ms=r["ms"], memory=False)
                else:
                    intro_task.cancel()
            deadline = time.time() + cfg.first_token_max_s
            got_any = False
            while True:
                try:
                    kind, val = await asyncio.wait_for(asyncio.shield(first), cfg.hb_s)
                except asyncio.TimeoutError:
                    el = round(time.time() - turn.created, 1)
                    if not got_any and time.time() > deadline:
                        deep.cancel()
                        return await self._fallback(turn, messages, intro_text, "первый токен GLM не пришёл за %d с" % cfg.first_token_max_s)
                    await turn.publish("stage", phase="thinking" if not got_any else "writing", elapsed_s=el, eta_s=plan.eta_s)
                    continue
                first = asyncio.ensure_future(q.get())
                if kind == "delta":
                    if not got_any and intro_text:
                        val = "\n\n" + val
                    got_any = True
                    await turn.publish("delta", stage="deep", text=val)
                elif kind == "end":
                    if val.get("tokens"):
                        self.tps_deep = 0.7 * self.tps_deep + 0.3 * val["tokens"] / max(val["secs"], 0.5)
                    await turn.publish("meta", nox={"tier": "glm", "stages": {"deep": {"status": "ok"}}})   # c600: метка уровня
                    return
                else:   # error
                    self.deep_down_until = time.time() + 20.0 if not got_any else 0.0
                    if got_any:
                        await turn.publish("error", code="deep_broken", message="GLM оборвал ответ: " + val, partial=True)
                        return
                    return await self._fallback(turn, messages, intro_text, val)
        finally:
            for t in (deep, first, intro_task):
                if t is not None and not t.done():
                    t.cancel()

    async def _pump_deep(self, turn, messages, plan, q):
        cfg = self.cfg
        msgs = BI.with_intro_note(messages) if (plan.intro and cfg.intro_on) else messages   # GLM стартует сразу, не дожидаясь вступления
        body = dict(plan.gateway_fields(), messages=msgs, stream=True, nox_session=turn.conv_id)
        writer, t0, n = None, time.time(), 0
        try:
            st, hdrs, reader, writer = await aio.open_request("POST", cfg.gateway + "/v1/chat/completions", body, timeout=10.0)
            turn.upstream["request_id"] = hdrs.get("x-nox-request-id")
            if st != 200:
                raw = await asyncio.wait_for(aio.read_body(reader, hdrs), 5)
                return await q.put(("error", "шлюз HTTP %d %s" % (st, raw[:120].decode("utf-8", "replace"))))
            t_first = None
            async for data in aio.iter_sse_data(reader, hdrs):
                if data == "[DONE]":
                    break
                try:
                    o = json.loads(data)
                except ValueError:
                    continue
                if o.get("error"):
                    return await q.put(("error", str((o["error"] or {}).get("message", "ошибка апстрима"))))
                ch = (o.get("choices") or [{}])[0]
                piece = (ch.get("delta") or {}).get("content") or ""
                if (o.get("nox") or {}).get("request_id") and not turn.upstream.get("request_id"):
                    turn.upstream["request_id"] = o["nox"]["request_id"]
                if piece:
                    t_first = t_first or time.time()
                    n += 1
                    await q.put(("delta", piece))
            await q.put(("end", {"tokens": n, "secs": (time.time() - t_first) if t_first else 0}))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await q.put(("error", "%s: %s" % (type(e).__name__, e)))
        finally:
            if writer is not None:
                writer.close()
                turn.upstream["closed"] = True

    async def _fast_answer(self, turn, messages, stage, prefix=None):
        cfg = self.cfg
        if not cfg.fast:
            return await turn.publish("error", code="no_upstream", message="ни GLM, ни быстрый слой не доступны")
        await turn.publish("meta", nox={"tier": "fallback" if stage == "fallback" else "fast", "stages": {"fast": {"status": "ok"}}})   # c600
        body = {"model": "fast", "messages": messages, "stream": True, "max_tokens": 1500, "temperature": 0.7, "cache_prompt": True,
                "chat_template_kwargs": {"enable_thinking": False}}
        writer = None
        try:
            st, hdrs, reader, writer = await aio.open_request("POST", cfg.fast.rstrip("/") + "/v1/chat/completions", body, timeout=5.0)
            if st != 200:
                return await turn.publish("error", code="fast_http_%d" % st, message="быстрый слой вернул %d" % st)
            if prefix:
                await turn.publish("delta", stage=stage, text=prefix)
            async for data in aio.iter_sse_data(reader, hdrs):
                if data == "[DONE]":
                    break
                try:
                    piece = ((json.loads(data).get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
                except ValueError:
                    continue
                if piece:
                    await turn.publish("delta", stage=stage, text=piece)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await turn.publish("error", code="fast_failed", message="%s: %s" % (type(e).__name__, e))
        finally:
            if writer is not None:
                writer.close()

    async def _fallback(self, turn, messages, intro_text, why):
        await turn.publish("stage", phase="fallback", reason=why)
        return await self._fast_answer(turn, messages, "fallback", prefix=("\n\n" if intro_text else "") + "GLM сейчас недоступен (%s), отвечаю быстрым слоем. " % why[:80])


# ---------------- HTTP ----------------
async def read_request(reader):
    line = await reader.readline()
    if not line:
        return None
    method, target, _ = line.decode("latin1").split(" ", 2)
    hdrs = {}
    while True:
        h = await reader.readline()
        if h in (b"\r\n", b"\n", b""):
            break
        k, _, v = h.decode("latin1").partition(":")
        hdrs[k.strip().lower()] = v.strip()
    body = b""
    n = int(hdrs.get("content-length", "0") or 0)
    if n:
        body = await reader.readexactly(n)
    return method, target, hdrs, body


async def send_json(writer, code, obj):
    b = json.dumps(obj, ensure_ascii=False).encode()
    writer.write(("HTTP/1.1 %d X\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % (code, len(b))).encode() + b)
    await writer.drain()


async def stream_turn(writer, turn, after, compat):
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\nX-Accel-Buffering: no\r\nConnection: close\r\n"
                 + ("X-NOX-Turn-Id: %s\r\nX-NOX-Conversation-Id: %s\r\n\r\n" % (turn.id, turn.conv_id)).encode())
    writer.write(b"retry: 1500\n\n")
    await writer.drain()
    try:
        async for ev in turn.subscribe(after):
            writer.write(to_sse(turn.id, ev, compat))
            await writer.drain()      # обрыв клиента -> исключение; ГЕНЕРАЦИЯ ПРОДОЛЖАЕТСЯ (задача хода независима)
    except (ConnectionError, asyncio.CancelledError):
        pass


def make_app(cfg, pipeline=None):
    pipe = pipeline or Pipeline(cfg)
    hub = Hub(pipe, persist_dir=cfg.state_dir)
    ctl = StopController(hub, slots_url=cfg.deep_slots, gateway_url=cfg.gateway, receipts_dir=cfg.receipts_dir, settle_s=cfg.settle_s)

    async def handle(reader, writer):
        try:
            req = await read_request(reader)
            if not req:
                return
            method, target, hdrs, body = req
            u = urlparse(target)
            qs = {k: v[0] for k, v in parse_qs(u.query).items()}
            parts = [p for p in u.path.split("/") if p]
            if method == "GET" and u.path == "/v1/rte/health":
                return await send_json(writer, 200, {"ok": True, "tps_deep": round(pipe.tps_deep, 2), "turns": len(hub.turns), "conversations": len(hub.convs)})
            if method == "POST" and u.path == "/v1/turns":
                try:
                    b = json.loads(body or b"{}")
                    msg = str(b["message"]).strip()
                except (ValueError, KeyError):
                    return await send_json(writer, 400, {"error": "need JSON {message}"})
                if not msg:
                    return await send_json(writer, 400, {"error": "empty message"})
                turn, state = hub.start_turn(b.get("conversation_id"), b.get("client_msg_id"), msg, b.get("source", "full"), {"mode": b.get("mode")})
                turn.hb_s = cfg.hb_s
                if state == "busy":
                    return await send_json(writer, 409, dict(turn.summary(), state="busy", hint="идёт другой ход этого диалога: подпишитесь на его events или остановите"))
                if qs.get("stream"):
                    return await stream_turn(writer, turn, parse_last_event_id(hdrs.get("last-event-id"), turn.id) if state == "duplicate" else 0, qs.get("compat"))
                return await send_json(writer, 200, dict(turn.summary(), state=state))
            if len(parts) == 4 and parts[:2] == ["v1", "turns"] and parts[3] == "events" and method == "GET":
                turn = hub.get(parts[2])
                if not turn:
                    return await send_json(writer, 404, {"error": "unknown_turn"})
                turn.hb_s = cfg.hb_s
                after = parse_last_event_id(hdrs.get("last-event-id"), turn.id) or int(qs.get("after", 0) or 0)
                return await stream_turn(writer, turn, after, qs.get("compat"))
            if len(parts) == 4 and parts[:2] == ["v1", "turns"] and parts[3] == "stop" and method == "POST":
                r = await ctl.stop(parts[2])
                return await send_json(writer, 200 if r.get("ok") else 404, r)
            if len(parts) == 3 and parts[:2] == ["v1", "conversations"] and method == "GET":
                c = hub.conversation(parts[2])
                return await send_json(writer, 200, {"conversation_id": c["id"], "messages": c["messages"], "turns": [hub.turns[t].summary() for t in c["turns"] if t in hub.turns]})
            await send_json(writer, 404, {"error": "not_found"})
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass
    return handle, hub, ctl, pipe


async def serve(cfg=None):
    cfg = cfg or Cfg()
    handle, hub, _, _ = make_app(cfg)
    hub.load()
    srv = await asyncio.start_server(handle, cfg.host, cfg.port)
    print("RTE %s:%d -> gateway %s fast %s" % (cfg.host, cfg.port, cfg.gateway, cfg.fast or "off"), flush=True)
    async with srv:
        await srv.serve_forever()


if __name__ == "__main__":
    asyncio.run(serve())
