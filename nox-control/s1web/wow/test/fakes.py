"""Поддельные шлюз GLM (8192), STT (8193), TTS (8194) для проверки веб-сборки в песочнице. Ничего не имитирует на S1."""
import json, time, math, base64, struct, threading, sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
class Q(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def j(self, c, o):
        b = json.dumps(o, ensure_ascii=False).encode(); self.send_response(c); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def body(self):
        n = int(self.headers.get("Content-Length", 0)); return self.rfile.read(n) if n else b""
class GW(Q):
    def do_GET(self):
        if self.path.startswith("/v1/models"): return self.j(200, {"data": [{"id": "glm-5.3"}]})
        self.j(404, {})
    def do_POST(self):
        d = self.body()
        if self.path.startswith("/v1/stop"): return self.j(200, {"stopped": True})
        if self.path.startswith("/v1/chat/completions"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Connection", "close"); self.end_headers()
            parts = ["Привет! ", "Это живой ", "потоковый ответ. ", "Вторая фраза для озвучки, ", "проверка потока. ", "```py\nprint('ok')\n```", "\nКонец."]
            for p in parts:
                self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": p}}]}) + "\n\n").encode()); self.wfile.flush(); time.sleep(.18)
            self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'); self.close_connection = True; return
        self.j(404, {})
class STT(Q):
    def do_GET(self): self.j(200, {"ok": True, "ready": True, "model": {"name": "small"}})
    def do_POST(self):
        d = self.body(); LOG.append(("stt", self.path, self.headers.get("Content-Type"), len(d), d[:4].hex()))
        self.j(200, {"language": "ru", "text": "Проверка голосового ввода", "segments": []})
class TTS(Q):
    S = {}
    def do_GET(self):
        if self.path.startswith("/health"): return self.j(200, {"ok": True, "ready": True, "backends": [{"name": "piper", "available": True}]})
        if "/audio" in self.path:
            sid = self.path.split("/")[2]; self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Transfer-Encoding", "chunked"); self.end_headers()
            def ch(b): self.wfile.write(("%x\r\n" % len(b)).encode() + b + b"\r\n"); self.wfile.flush()
            n = 0
            while time.time() < TTS.S.get(sid, {}).get("end", 0) + 5 and not TTS.S.get(sid, {}).get("stop"):
                st = TTS.S[sid]
                while st["q"]:
                    t = st["q"].pop(0)
                    pcm = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 24000))) for i in range(2400))
                    ch(("data: " + json.dumps({"type": "audio", "seq": n, "text": t, "backend": "fake", "sample_rate": 24000, "pcm_b64": base64.b64encode(pcm).decode()}) + "\n\n").encode()); n += 1
                if st.get("final") and not st["q"]: break
                time.sleep(.05)
            ch(b'data: {"type":"end"}\n\n'); ch(b""); self.close_connection = True; return
        self.j(404, {})
    def do_POST(self):
        d = self.body(); p = self.path
        if p == "/session": sid = "s%d" % len(TTS.S); TTS.S[sid] = {"q": [], "end": time.time()}; return self.j(200, {"id": sid, "out_rate": 24000})
        parts = p.strip("/").split("/")
        if len(parts) == 3 and parts[2] == "text":
            o = json.loads(d or b"{}"); st = TTS.S[parts[1]]; LOG.append(("tts-text", o)); 
            if o.get("text"): st["q"].append(o["text"])
            if o.get("final"): st["final"] = True
            st["end"] = time.time(); return self.j(200, {"accepted": True})
        if len(parts) == 3 and parts[2] == "stop": TTS.S[parts[1]]["stop"] = True; LOG.append(("tts-stop", parts[1])); return self.j(200, {"stopped": 1})
        self.j(404, {})
LOG = []
class LogH(Q):
    def do_GET(self): self.j(200, LOG)
if __name__ == "__main__":
    for port, h in ((8192, GW), (8193, STT), (8194, TTS), (8195, LogH)):
        threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", port), h).serve_forever, daemon=True).start()
    print("fakes up", flush=True); time.sleep(3600)
