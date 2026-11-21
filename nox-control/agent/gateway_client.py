"""Клиент шлюза NOX (/v1/chat/completions, /v1/stop, /v1/nox/stats). Только stdlib.
Вызовы идут без stream: шлюз в stream-режиме не пропускает tool_calls. Отмена: /v1/stop по id активных запросов, появившихся во время нашего вызова."""
import http.client, json, threading, time
from urllib.parse import urlparse


class GatewayError(Exception):
    pass


class StopRequested(Exception):
    pass


class CallTimeout(Exception):
    pass


class Gateway:
    def __init__(self, cfg):
        self.cfg = cfg
        u = urlparse(cfg.gateway)
        self.host, self.port, self.base = u.hostname or "127.0.0.1", u.port or 80, u.path.rstrip("/")

    def _req(self, method, path, body=None, timeout=10):
        c = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        try:
            c.request(method, self.base + path, body=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
                      headers={"Content-Type": "application/json"} if body is not None else {})
            r = c.getresponse()
            data = r.read()
            try: return r.status, json.loads(data or b"{}")
            except ValueError: return r.status, {"raw": data[:300].decode("utf-8", "replace")}
        finally:
            c.close()

    def active_ids(self):
        try:
            st, d = self._req("GET", "/v1/nox/stats", timeout=3)
            return set(d.get("active") or []) if st == 200 else set()
        except Exception:
            return set()

    def stop_ids(self, ids):
        done = []
        for i in ids:
            try:
                st, d = self._req("POST", "/v1/stop", {"request_id": i}, timeout=3)
                if st == 200 and d.get("stopped"): done.append(i)
            except Exception:
                pass
        return done

    def chat(self, messages, tools=None, mode=None, max_tokens=None, timeout=None, stop_check=None, extra=None):
        body = {"model": "nox", "messages": messages, "stream": False, "nox_mode": mode or self.cfg.mode, "nox_no_route": True, "nox_no_retry": True}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if max_tokens: body["max_tokens"] = max_tokens
        body.update(extra or {})
        before = self.active_ids()
        box = {}
        timeout = timeout or self.cfg.call_timeout

        def work():
            c = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
            box["conn"] = c
            try:
                c.request("POST", self.base + "/v1/chat/completions", body=json.dumps(body, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
                r = c.getresponse()
                box["status"], box["data"] = r.status, r.read()
                box["rid"] = r.getheader("X-NOX-Request-Id")
            except Exception as e:
                box["exc"] = e
            finally:
                try: c.close()
                except Exception: pass

        th = threading.Thread(target=work, daemon=True)
        t0 = time.time()
        th.start()
        while th.is_alive():
            th.join(0.2)
            if stop_check and stop_check():
                stopped = self.stop_ids(self.active_ids() - before)
                c = box.get("conn")
                try:
                    if c is not None and c.sock is not None: c.sock.shutdown(2)
                except Exception: pass
                e = StopRequested("stopped")
                e.gateway_stopped = stopped
                raise e
            if time.time() - t0 > timeout + 5:
                self.stop_ids(self.active_ids() - before)
                raise CallTimeout("вызов шлюза дольше %.0f с" % timeout)
        if "exc" in box:
            if isinstance(box["exc"], TimeoutError) or "timed out" in str(box["exc"]): raise CallTimeout(str(box["exc"]))
            raise GatewayError("%s: %s" % (type(box["exc"]).__name__, box["exc"]))
        if box["status"] != 200:
            raise GatewayError("шлюз HTTP %s: %s" % (box["status"], box["data"][:300].decode("utf-8", "replace")))
        try:
            return json.loads(box["data"])
        except ValueError:
            raise GatewayError("шлюз вернул не JSON")
