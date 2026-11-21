"""Шлюз NOX -> llama-server. Слушает 127.0.0.1:8082. GLM-5.3 (NOX_UPSTREAM, :8081) + быстрый тир (NOX_FAST_UPSTREAM, :8083).
QS6: роутер тиров, двухтактный стрим (delta.nox_stage), режимы nox_mode, ETA, STOP, кэш-метрики, «на чём остановились». См. README_QS6.md."""
import json, sys, os, time, select, socket, queue, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import glm_profile as P
import qs6_core as C
import qs6_resume as RS
sys.path.insert(0, os.path.dirname(HERE))   # .../nox-control: рядом лежит пакет community
try:
    from community.chalie_router import route as _route
except Exception:
    _route = None

class State:
    def __init__(self, cfg):
        self.cfg = cfg; self.meter = C.SpeedMeter(cfg); self.cache = C.CacheStats(); self.reg = C.Registry(); self.fast_down_until = 0.0
    def fast_ok(self): return bool(self.cfg.fast_url) and time.time() >= self.fast_down_until
    def fast_failed(self): self.fast_down_until = time.time() + self.cfg.fast_cooldown_s

def make_handler(st):
    cfg = st.cfg
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        # ---- вспомогательное
        def _json(self, code, obj, extra=None):
            b = json.dumps(obj, ensure_ascii=False).encode(); self.send_response(code)
            self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
            for k, v in (extra or {}).items(): self.send_header(k, v)
            self.end_headers(); self.wfile.write(b)
        def _client_gone(self):
            try:
                r, _, _ = select.select([self.connection], [], [], 0)
                return bool(r) and self.connection.recv(1, socket.MSG_PEEK) == b""
            except Exception: return True
        def _sse(self, obj):
            self.wfile.write(b"data: " + (obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)).encode() + b"\n\n"); self.wfile.flush()
        def _relay(self, path, body=None):
            r = C.Req()
            try:
                c, resp = C.open_upstream(cfg.deep_url, path, body, r, cfg.connect_timeout, cfg.deep_timeout) if body is not None else (None, None)
                if c is None:
                    import urllib.request
                    with urllib.request.urlopen(cfg.deep_url + path, timeout=30) as rr: data = rr.read(); code = rr.status
                else:
                    data = resp.read(); code = 200; C.Req.close(c)
                self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
            except Exception as e: self._json(502, {"error": str(e)})
        # ---- маршруты
        def do_GET(self):
            p = self.path.split("?")[0]
            if p == "/v1/nox/stats":
                return self._json(200, {"speed": st.meter.snapshot(), "cache": st.cache.snapshot(), "active": st.reg.active(), "fast_available": st.fast_ok(), "prefix": C.prefix_hash()})
            if p == "/v1/resume":
                return self._json(200, {"text": RS.resume_answer(cfg.session_summary)})
            self._relay(self.path)
        def do_POST(self):
            n = int(self.headers.get("Content-Length", "0"))
            try: body = json.loads(self.rfile.read(n) or b"{}")
            except Exception: return self._json(400, {"error": "bad json"})
            p = self.path.split("?")[0].rstrip("/")
            if p == "/v1/stop":
                rid = body.get("request_id") or ""
                return self._json(200, {"request_id": rid, "stopped": st.reg.stop(rid)})
            if p not in ("/v1/chat/completions", "/chat/completions"):
                return self._relay(self.path, body)
            self.chat(body)
        # ---- чат
        def chat(self, body):
            msgs = body.get("messages") or []; user = P.last_user_text(msgs); stream = bool(body.get("stream"))
            req = st.reg.new(); rid = req.id
            try:
                if RS.is_resume_query(user) and cfg.session_summary:
                    return self._local(req, RS.resume_answer(cfg.session_summary), stream, {"skipped_model": True, "source": "session_summary"})
                decision = None
                if _route and not body.get("nox_no_route"):
                    try: decision = _route(msgs).to_dict()
                    except Exception: decision = None
                if decision and decision.get("action") == "ignore":
                    return self._local(req, "", stream, {"route": decision, "skipped_model": True})
                tools = bool(body.get("tools")) or any(m.get("role") == "tool" for m in msgs)
                plan = C.plan_request(body, cfg, tools, decision and decision.get("action"), st.fast_ok())
                eta = st.meter.eta(plan)
                info = {"request_id": rid, "mode": plan["mode"], "tier": plan["tier"], "effort": plan["effort"], "eta_s": eta["eta_s"], "eta_basis": eta["basis"],
                        "prefix": C.prefix_hash()}
                if "eta_first_s" in eta: info["eta_first_s"] = eta["eta_first_s"]
                if plan["route"]: info["router"] = {"reason": plan["route"]["reason"]}
                if decision: info["route"] = decision
                if plan["note"]: info["note"] = plan["note"]
                if stream: self.chat_stream(body, plan, req, info)
                else: self.chat_plain(body, plan, req, info, user)
            finally:
                st.reg.done(req)
        def _local(self, req, text, stream, extra):
            nox = dict(extra, request_id=req.id, memory_text=text)
            hdr = {"X-NOX-Request-Id": req.id}
            if not stream:
                return self._json(200, {"object": "chat.completion", "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}], "nox": nox}, hdr)
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache"); self.send_header("X-NOX-Request-Id", req.id); self.end_headers()
            self._sse(self._chunk(req.id, {"role": "assistant", "content": ""}, nox={"request_id": req.id}))
            if text: self._sse(self._chunk(req.id, {"content": text, "nox_stage": "local"}))
            self._sse(self._chunk(req.id, {}, "stop", nox)); self._sse("[DONE]")
        @staticmethod
        def _chunk(rid, delta, finish=None, nox=None, extra=None):
            o = {"id": "nox-" + rid, "object": "chat.completion.chunk", "created": int(time.time()), "model": "nox",
                 "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            if nox: o["nox"] = nox
            if extra: o.update(extra)
            return o
        # ---- без стрима
        def chat_plain(self, body, plan, req, info, user):
            t0 = time.time(); hdr = {"X-NOX-Request-Id": req.id, "X-NOX-Mode": plan["mode"]}
            def call(tier, b):
                base = cfg.fast_url if tier == "fast" else cfg.deep_url
                c, r = C.open_upstream(base, "/v1/chat/completions", b, req, cfg.connect_timeout, cfg.fast_timeout if tier == "fast" else cfg.deep_timeout)
                try: return json.loads(r.read())
                finally: C.Req.close(c)
            try:
                tier = "fast" if plan["tier"] == "fast" else "deep"
                if tier == "fast":
                    try: resp = call("fast", C.build_fast(body, plan, cfg, False, False))
                    except C.UpstreamError as e:
                        st.fast_failed(); info["fast"] = "skipped: " + str(e); tier = "deep"
                        plan = dict(plan, effort=P.pick_effort(P.last_user_text(body.get("messages") or [])), max_tokens=None, expected_tokens=250)
                if tier == "deep":
                    b, effort = C.build_deep(body, plan, cfg, False); info["effort"] = effort
                    resp = call("deep", b)
                dt = time.time() - t0
                u = resp.get("usage") or {}; n = u.get("completion_tokens") or 0
                st.meter.record(tier, n, dt)
                cs = C.cache_from(resp)
                if cs and tier == "deep": st.cache.record(*cs); info["cache"] = {"tokens_cached": cs[0], "prompt_tokens": cs[1]}
                resp = P.postprocess(resp, user)
                v = resp.get("nox", {}).get("violations") or []
                if v and tier == "deep" and not body.get("nox_no_retry") and not req.cancelled.is_set():
                    b2 = json.loads(json.dumps(b)); b2["messages"].append({"role": "user", "content": "Перепиши ответ без: " + ", ".join(v) + ". Только исправленный ответ."})
                    r2 = P.postprocess(call("deep", b2), user); r2["nox"]["retried_for"] = v; resp = r2
                if plan["tier"] == "two_stage": info["two_stage"] = "только в stream=true"
                info["actual_s"] = round(time.time() - t0, 1); info["stopped"] = req.cancelled.is_set()
                resp.setdefault("nox", {}).update(info)
                self._json(200, resp, hdr)
            except Exception as e:
                if req.cancelled.is_set(): self._json(499, {"error": "stopped", "nox": {"request_id": req.id, "stopped": True}}, hdr)
                else: self._json(502, {"error": str(e), "nox": info}, hdr)
        # ---- стрим (один поток, два такта)
        def chat_stream(self, body, plan, req, info):
            q = queue.Queue(); t0 = time.time(); rid = req.id
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no"); self.send_header("X-NOX-Request-Id", rid); self.send_header("X-NOX-Mode", plan["mode"]); self.end_headers()
            try: self._sse(self._chunk(rid, {"role": "assistant", "content": ""}, nox=info))
            except Exception: return req.cancel()
            tier = plan["tier"]; use_fast = tier in ("fast", "two_stage"); use_deep = tier in ("deep", "two_stage")
            deep_started = [False]
            def start_deep(after_fast):
                if deep_started[0]: return
                deep_started[0] = True
                b, effort = C.build_deep(body, plan if plan["effort"] else dict(plan, effort=P.pick_effort(P.last_user_text(body.get("messages") or [])), max_tokens=None), cfg, True, after_fast)
                info["effort"] = effort
                threading.Thread(target=C.pump, args=(cfg, st.meter, st.cache, "deep", cfg.deep_url, b, req, q), daemon=True).start()
            if use_fast:
                b = C.build_fast(body, plan, cfg, True, first_part=(tier == "two_stage"))
                threading.Thread(target=C.pump, args=(cfg, st.meter, st.cache, "fast", cfg.fast_url, b, req, q, cfg.fast_sentences if tier == "two_stage" else None), daemon=True).start()
            if use_deep: start_deep(after_fast=use_fast)
            fast_done = not use_fast; fast_text = ""; fast_info = None; stitch = None; pend = []; deep_done = not use_deep
            deep_fin = None; deep_err = None; err_sent = False; stages = {}; first_deep = True; stopped_sent = False
            def emit(stage, text):
                self._sse(self._chunk(rid, {"content": text, "nox_stage": stage}))
            def emit_deep(text):
                nonlocal first_deep
                if not text: return
                if first_deep and fast_text.strip(): text = "\n\n" + text
                first_deep = False; emit("deep", text)
            def become_fast_done():
                nonlocal stitch
                stitch = C.Stitcher(fast_text) if use_deep else None
                for d in pend: emit_deep(stitch.feed(d))
                pend.clear()
                if deep_done and stitch and not deep_err: emit_deep(stitch.finish())
            last_ping = time.time()
            try:
                while not (fast_done and deep_done):
                    try: tr, kind, val = q.get(timeout=0.5)
                    except queue.Empty:
                        if req.cancelled.is_set(): break
                        if self._client_gone(): req.cancel(); return
                        if time.time() - last_ping >= cfg.ping_s: self.wfile.write(b": ping\n\n"); self.wfile.flush(); last_ping = time.time()
                        continue
                    last_ping = time.time()
                    if tr == "fast":
                        if kind == "delta": fast_text += val; emit("fast", val)
                        elif kind == "end":
                            fast_done = True; fast_info = val; stages["fast"] = {"tokens": val.get("tokens"), "ttft_s": val.get("ttft_s"), "status": "ok"}
                            if val.get("cancelled"): break
                            become_fast_done()
                        else:
                            msg, had, _ = val; st.fast_failed(); fast_done = True
                            stages["fast"] = {"status": "partial_error" if had else "skipped", "reason": msg}
                            if not had: self._sse(self._chunk(rid, {"content": "", "nox_stage": "deep" if use_deep else "fast"}, nox={"fast": "skipped", "reason": msg}))
                            if not use_deep: start_deep(False); use_deep = True; deep_done = False   # быстрый-only: честный откат на GLM
                            become_fast_done()
                    else:
                        if kind == "delta":
                            if not fast_done: pend.append(val)
                            else: emit_deep(stitch.feed(val) if stitch else val)
                        elif kind == "end":
                            deep_done = True; deep_fin = val
                            if val.get("cancelled"): break
                            if fast_done and stitch: emit_deep(stitch.finish())
                            stages["deep"] = {"tokens": val.get("tokens"), "ttft_s": val.get("ttft_s"), "status": "ok", "cache": val.get("cache")}
                            if val.get("cache"): info["cache"] = val["cache"]
                        else:
                            deep_done = True; deep_err = val[0]; stages["deep"] = {"status": "error", "reason": val[0]}
                            if fast_done:
                                self._sse({"error": {"message": "GLM недоступен: " + val[0], "type": "upstream_unavailable", "nox_stage": "deep"}}); err_sent = True
                if deep_err and not err_sent and not fast_done:
                    pass
                if req.cancelled.is_set():
                    stopped_sent = True
                if deep_err and not err_sent:
                    self._sse({"error": {"message": "GLM недоступен: " + deep_err, "type": "upstream_unavailable", "nox_stage": "deep"}})
                fin = "error" if deep_err else ("stop" if not deep_fin or not deep_fin.get("finish") or deep_fin.get("finish") == "nox_sentence_limit" else deep_fin["finish"])
                if stopped_sent: fin = "stop"
                dt = time.time() - t0; fin_nox = {"request_id": rid, "stages": stages, "actual_s": round(dt, 1), "eta_s": info["eta_s"], "stopped": stopped_sent,
                                                  "tps": st.meter.snapshot(), "cache_total": st.cache.snapshot()}
                if "cache" in info: fin_nox["cache"] = info["cache"]
                if stitch and stitch.dropped: fin_nox["dedup_sentences_dropped"] = stitch.dropped
                if deep_err: fin_nox["error"] = deep_err
                self._sse(self._chunk(rid, {}, fin, fin_nox)); self._sse("[DONE]")
            except (BrokenPipeError, ConnectionResetError, OSError):
                req.cancel()                    # клиент ушёл: закрываем сокеты к llama-server
            finally:
                if not (fast_done and deep_done): req.cancel()
    return H

def make_server(cfg, host=None, port=None):
    st = State(cfg)
    srv = ThreadingHTTPServer((host or cfg.host, cfg.port if port is None else port), make_handler(st))
    srv.daemon_threads = True; srv.state = st
    return srv

if __name__ == "__main__":
    cfg = C.Cfg()
    print("NOX gateway %s:%d deep=%s fast=%s" % (cfg.host, cfg.port, cfg.deep_url, cfg.fast_url or "off"), flush=True)
    make_server(cfg).serve_forever()
