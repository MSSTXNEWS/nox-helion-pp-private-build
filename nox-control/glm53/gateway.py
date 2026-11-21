"""Шлюз NOX -> llama-server GLM-5.3. Слушает 127.0.0.1:8082, пересылает на 127.0.0.1:8081. Профиль G01-G33 из glm_profile."""
import json, sys, urllib.request, os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glm_profile as P
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # .../nox-control или /root/nox: рядом лежит пакет community
try:
    from community.chalie_router import route as _route                         # роутер Chalie до модели (мс)
except Exception:
    _route = None
UP = os.environ.get("NOX_UPSTREAM", "http://127.0.0.1:8081")
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode(); self.send_response(code)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _up(self, path, body=None):
        req = urllib.request.Request(UP + path, data=(json.dumps(body).encode() if body is not None else None), headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(req, timeout=900)
    def do_GET(self):
        try:
            with self._up(self.path) as r: data = r.read(); code = r.status
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        except Exception as e:
            self._json(502, {"error": str(e)})
    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0")); body = json.loads(self.rfile.read(n) or b"{}")
        if self.path.rstrip("/") not in ("/v1/chat/completions", "/chat/completions"):
            try:
                with self._up(self.path, body) as r: data = r.read(); code = r.status
                self.send_response(code); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
            except Exception as e: self._json(502, {"error": str(e)})
            return
        user = P.last_user_text(body.get("messages") or [])
        decision = None
        if _route and not body.get("nox_no_route"):
            try: decision = _route(body.get("messages") or []).to_dict()
            except Exception: decision = None
        if decision and decision.get("action") == "ignore":              # пустое/эхо/повтор: модель не запускаем
            self._json(200, {"object": "chat.completion", "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": ""}}], "nox": {"route": decision, "skipped_model": True}})
            return
        req, effort = P.build_request(body)
        try:
            if req.get("stream"):
                with self._up("/v1/chat/completions", req) as r:
                    self.send_response(r.status); self.send_header("Content-Type", "text/event-stream"); self.send_header("X-NOX-Effort", effort); self.end_headers()
                    while True:
                        chunk = r.read1(65536) if hasattr(r, "read1") else r.read(65536)
                        if not chunk: break
                        self.wfile.write(chunk); self.wfile.flush()
                return
            with self._up("/v1/chat/completions", req) as r: resp = json.loads(r.read())
            resp = P.postprocess(resp, user)
            v = resp.get("nox", {}).get("violations") or []
            if v and not body.get("nox_no_retry"):                       # одна повторная попытка при нарушении стиля (G29/G30)
                req2 = json.loads(json.dumps(req)); req2["messages"].append({"role": "user", "content": "Перепиши ответ без: " + ", ".join(v) + ". Только исправленный ответ."})
                with self._up("/v1/chat/completions", req2) as r: resp2 = P.postprocess(json.loads(r.read()), user)
                resp2["nox"]["retried_for"] = v; resp = resp2
            resp["nox"]["effort"] = effort
            if decision: resp["nox"]["route"] = decision
            self._json(200, resp)
        except Exception as e:
            self._json(502, {"error": str(e)})
if __name__ == "__main__":
    print("NOX GLM gateway 127.0.0.1:8082 ->", UP, flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8082), H).serve_forever()
