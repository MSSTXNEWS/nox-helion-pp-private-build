#!/usr/bin/env python3
"""Фейковый сервис для тестов диспетчера: настоящий HTTP-процесс (stdlib), поведение задаётся флагами.
--port P  --load-s N (до N с после старта /health=503)  --crash-after S (выйти с --exit-code)  --exit-code C
--chat-code-file F (код ответа на POST /v1/chat/completions читается из файла; нет файла -> 200)
--model NAME (виден в /props)  --hold-bind (ничего не делает, нужно для занятого порта)
GET /health, GET /props, POST /v1/chat/completions, POST /slots/0?action=save|restore, POST /v1/stop
"""
import argparse, json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, required=True)
ap.add_argument("--load-s", type=float, default=0)
ap.add_argument("--crash-after", type=float, default=-1)
ap.add_argument("--exit-code", type=int, default=3)
ap.add_argument("--chat-code-file", default="")
ap.add_argument("--model", default="fake")
ap.add_argument("--log-line", default="")
ap.add_argument("--calls-log", default="")
a, _ = ap.parse_known_args()
T0 = time.time()
if a.log_line:
    print(a.log_line, flush=True)


class H(BaseHTTPRequestHandler):
    def log_message(self, *x):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _note(self, what):
        if a.calls_log:
            with open(a.calls_log, "a") as f:
                f.write(what + "\n")

    def do_GET(self):
        if self.path == "/health":
            return self._send(503 if time.time() - T0 < a.load_s else 200, {"status": "ok"})
        if self.path == "/props":
            return self._send(200, {"model_path": a.model})
        self._send(404, {})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        self._note("POST " + self.path + " " + body[:3000].decode("utf8", "replace"))
        if self.path.startswith("/v1/chat/completions"):
            code = 200
            if a.chat_code_file and os.path.exists(a.chat_code_file):
                code = int(open(a.chat_code_file).read().strip() or 200)
            return self._send(code, {"choices": [{"message": {"content": "ok"}}]})
        if self.path.startswith("/slots/"):
            return self._send(200, {"ok": True})
        self._send(200, {"ok": True})


def crasher():
    time.sleep(a.crash_after)
    os._exit(a.exit_code)


if a.crash_after >= 0:
    threading.Thread(target=crasher, daemon=True).start()
ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
