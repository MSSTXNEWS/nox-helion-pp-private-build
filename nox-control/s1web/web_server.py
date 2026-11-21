"""Веб «Резонанс» на S1: статика /web/, старый протокол чата /api/chat (Ollama-NDJSON) -> шлюз GLM-5.3 (8082), новый чат /glm/* -> шлюз, голос /stt/* -> STT 8093, /tts/* -> TTS 8094. Слушает только 127.0.0.1:8091 (доступ через SSH-туннель)."""
import os, sys, json, http.client, threading, mimetypes, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
ROOT = os.environ.get("NOX_WEB_ROOT", "/root/nox/web")
GW = os.environ.get("NOX_GW", "127.0.0.1:8082")
STT = os.environ.get("NOX_STT", "127.0.0.1:8093")   # голос: /stt/* -> faster-whisper (voice/stt_server.py)
TTS = os.environ.get("NOX_TTS", "127.0.0.1:8094")   # голос: /tts/* -> XTTS/Piper (voice/tts_server.py), SSE/PCM
MEM = os.environ.get("NOX_MEMORY_API", "127.0.0.1:8095")   # «что NOX вспомнил»: qs6/recall_server.py, наружу только как /memory/*
MEM_PATHS = ("/health", "/api")
PORT = int(os.environ.get("NOX_WEB_PORT", "8091"))
MAX_BODY = 40 * 1024 * 1024
TAG = "nox-helion:latest"
ACTIVE = {}; LOCK = threading.Lock()
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def _send(self, code, body=b"", ctype="application/json", extra=None):
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(body)
    def _j(self, code, obj): self._send(code, json.dumps(obj, ensure_ascii=False).encode())
    def do_HEAD(self): self.do_GET()
    def do_GET(self):
        p = urllib.parse.unquote(self.path.split("?")[0]); qs = self.path[len(self.path.split("?")[0]):]
        if p in ("/", ""): return self._send(302, b"", extra={"Location": "/web/chat.html"})
        if p.startswith("/glm/"): return self._proxy("GET", p[4:], None)
        if p.startswith("/stt/"): return self._proxy("GET", p[4:] + qs, None, STT, "STT (127.0.0.1:8093)")
        if p.startswith("/tts/"): return self._proxy("GET", p[4:] + qs, None, TTS, "TTS (127.0.0.1:8094)")
        if p.startswith("/memory/"): return self._memory("GET", p[7:], None)
        if p.startswith("/api/"): return self._j(503, {"error": "API панели S2 не подключено (работает только чат через GLM-5.3 на S1)"})
        if p.startswith("/web/"):
            rel = p[5:] or "index.html"
            full = os.path.abspath(os.path.join(ROOT, rel))
            if not (full == ROOT or full.startswith(ROOT + os.sep)): return self._j(403, {"error": "forbidden"})
            if os.path.isdir(full): full = os.path.join(full, "index.html")
            if not os.path.isfile(full): return self._j(404, {"error": "not found"})
            ct = mimetypes.guess_type(full)[0] or "application/octet-stream"
            with open(full, "rb") as f: data = f.read()
            return self._send(200, data, ct + ("; charset=utf-8" if ct.startswith("text/") or "javascript" in ct or ct.endswith("json") else ""), {"Cache-Control": "no-cache"})
        return self._j(404, {"error": "not found"})
    def _body(self):
        n = int(self.headers.get("Content-Length", "0") or 0); return self.rfile.read(n) if n else b""
    def do_POST(self):
        p = urllib.parse.unquote(self.path.split("?")[0]); qs = self.path[len(self.path.split("?")[0]):]
        if int(self.headers.get("Content-Length", "0") or 0) > MAX_BODY:
            self.close_connection = True; return self._j(413, {"error": "тело запроса больше %d МБ" % (MAX_BODY // 1048576)})
        raw = self._body()
        if p == "/api/chat": return self._chat(raw)
        if p == "/api/chat/stop":
            try: rid = json.loads(raw or b"{}").get("request_id")
            except Exception: rid = None
            with LOCK: c = ACTIVE.pop(rid, None)
            if c:
                try: c.close()
                except Exception: pass
            return self._j(200, {"ok": True, "stopped": bool(c)})
        if p.startswith("/glm/"): return self._proxy("POST", p[4:], raw)
        if p.startswith("/stt/"): return self._proxy("POST", p[4:] + qs, raw, STT, "STT (127.0.0.1:8093)", self.headers.get("Content-Type"))
        if p.startswith("/tts/"): return self._proxy("POST", p[4:] + qs, raw, TTS, "TTS (127.0.0.1:8094)", self.headers.get("Content-Type"))
        if p.startswith("/memory/"): return self._memory("POST", p[7:], raw)
        if p.startswith("/api/"): return self._j(503, {"error": "API панели S2 не подключено"})
        return self._j(404, {"error": "not found"})
    def _memory(self, method, path, raw):
        """/memory/health, /memory/api -> recall_api (127.0.0.1:8095). Других путей у recall_api нет, остальное 404."""
        if path not in MEM_PATHS or (path == "/health") != (method == "GET"): return self._j(404, {"ok": False, "error": "доступно: GET /memory/health, POST /memory/api"})
        return self._proxy(method, path, raw, MEM, "память (recall_api %s)" % MEM)
    def _proxy(self, method, path, raw, host=None, name="шлюз GLM", ctype=None):
        c = None; started = False
        try:
            c = http.client.HTTPConnection(host or GW, timeout=900)
            hd = {"Content-Type": ctype or "application/json"} if method == "POST" else {}
            c.request(method, path, body=raw, headers=hd); r = c.getresponse()
            self.send_response(r.status); self.send_header("Content-Type", r.getheader("Content-Type", "application/json"))
            stream = "text/event-stream" in (r.getheader("Content-Type") or "") or r.getheader("Content-Length") is None  # SSE, chunked PCM/WAV
            started = True
            if stream:
                self.send_header("Cache-Control", "no-cache"); self.send_header("Connection", "close"); self.end_headers()
                while True:
                    ch = r.read1(65536)
                    if not ch: break
                    self.wfile.write(ch); self.wfile.flush()
                self.close_connection = True
            else:
                data = r.read(); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError): self.close_connection = True
        except Exception as e:
            if started: self.close_connection = True
            else: self._j(502, {"error": "%s недоступен: %s" % (name, e)})
        finally:
            if c is not None:
                try: c.close()
                except Exception: pass
    def _chat(self, raw):
        """Старый протокол: Ollama-запрос -> OpenAI-стрим шлюза -> NDJSON кадры с model=TAG."""
        try: b = json.loads(raw or b"{}")
        except Exception: return self._j(400, {"error": "bad json"})
        rid = b.get("request_id"); opts = b.get("options") or {}
        req = {"messages": b.get("messages") or [], "stream": True}
        if opts.get("num_predict"): req["max_tokens"] = int(opts["num_predict"])
        if opts.get("temperature") is not None: req["temperature"] = opts["temperature"]
        try:
            c = http.client.HTTPConnection(GW, timeout=900)
            c.request("POST", "/v1/chat/completions", body=json.dumps(req), headers={"Content-Type": "application/json"}); r = c.getresponse()
        except Exception as e:
            return self._j(502, {"error": "шлюз GLM недоступен: %s" % e})
        if r.status != 200:
            return self._j(502, {"error": "шлюз GLM ответил %s: %s" % (r.status, r.read()[:200].decode("utf-8", "replace"))})
        if rid:
            with LOCK: ACTIVE[rid] = c
        self.send_response(200); self.send_header("Content-Type", "application/x-ndjson"); self.send_header("Cache-Control", "no-cache"); self.send_header("Connection", "close"); self.end_headers()
        def out(o): self.wfile.write((json.dumps(o, ensure_ascii=False) + "\n").encode()); self.wfile.flush()
        ok = False
        try:
            buf = b""
            while True:
                ch = r.read1(65536)
                if not ch: break
                buf += ch
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1); line = line.strip()
                    if not line.startswith(b"data:"): continue
                    d = line[5:].strip()
                    if d == b"[DONE]": ok = True; continue
                    try: j = json.loads(d)
                    except Exception: continue
                    delta = ((j.get("choices") or [{}])[0].get("delta") or {})
                    t = delta.get("content")
                    if t: out({"model": TAG, "message": {"role": "assistant", "content": t}, "done": False})
                    if ((j.get("choices") or [{}])[0].get("finish_reason")): ok = True
            if ok: out({"model": TAG, "message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"})
            else: out({"error": "поток модели оборвался"})
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception as e:
            try: out({"error": str(e)})
            except Exception: pass
        finally:
            with LOCK: ACTIVE.pop(rid, None)
            try: c.close()
            except Exception: pass
            self.close_connection = True
if __name__ == "__main__":
    print("NOX web S1 127.0.0.1:%d root=%s gw=%s stt=%s tts=%s" % (PORT, ROOT, GW, STT, TTS), flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
