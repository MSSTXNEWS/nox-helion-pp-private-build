"""Веб «Резонанс» на S1: статика /web/, старый протокол чата /api/chat (Ollama-NDJSON) -> шлюз GLM-5.3 (8082), новый чат /glm/* -> шлюз, голос /stt/* -> STT 8093, /tts/* -> TTS 8094. Слушает только 127.0.0.1:8091 (доступ через SSH-туннель)."""
import os, sys, json, http.client, threading, mimetypes, urllib.parse, subprocess, time
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

# ---- /api/pc-metrics: реальные цифры сервера (nvidia-smi, /proc, statvfs); нет источника - честная ошибка в поле, без выдумок ----
_CPU = {"t": 0.0, "a": None}
def _cpu_times():
    with open("/proc/stat") as f: v = [int(x) for x in f.readline().split()[1:]]
    return sum(v), v[3] + (v[4] if len(v) > 4 else 0)
def _cpu_pct():
    t1, i1 = _cpu_times(); a = _CPU["a"]
    if a is None or time.time() - _CPU["t"] > 30:
        time.sleep(0.25); t2, i2 = _cpu_times()
    else: t2, i2, (t1, i1) = t1, i1, a
    _CPU["a"] = (t2, i2); _CPU["t"] = time.time(); dt = t2 - t1
    return round(100.0 * (dt - (i2 - i1)) / dt, 1) if dt > 0 else None
def pc_metrics():
    out = {"ts": int(time.time()), "source": "web_server.py (nvidia-smi, /proc, statvfs)"}
    try: out["cpu"] = {"percent": _cpu_pct(), "cores": os.cpu_count()}
    except Exception as e: out["cpu"] = {"error": str(e)}
    try:
        m = {}
        for ln in open("/proc/meminfo"):
            k, v = ln.split(":", 1); m[k] = int(v.split()[0]) * 1024
        tot = m["MemTotal"]; av = m.get("MemAvailable", m.get("MemFree", 0))
        out["ram"] = {"total_bytes": tot, "used_bytes": tot - av, "percent": round(100.0 * (tot - av) / tot, 1)}
    except Exception as e: out["ram"] = {"error": str(e)}
    try:
        st = os.statvfs("/dev/shm"); tot = st.f_blocks * st.f_frsize; fr = st.f_bavail * st.f_frsize
        out["shm"] = {"total_bytes": tot, "used_bytes": tot - fr, "percent": round(100.0 * (tot - fr) / tot, 1) if tot else None}
    except Exception as e: out["shm"] = {"error": str(e)}
    try:
        best = None
        import glob
        for z in sorted(glob.glob("/sys/class/thermal/thermal_zone*")):
            try:
                ty = open(z + "/type").read().strip().lower(); v = int(open(z + "/temp").read().strip()) / 1000.0
                if best is None or any(k in ty for k in ("x86_pkg", "cpu", "k10temp", "coretemp")): best = {"celsius": round(v, 1), "zone": ty}
            except Exception: pass
        out["cpu_temp"] = best or {"error": "нет /sys/class/thermal"}
    except Exception as e: out["cpu_temp"] = {"error": str(e)}
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=6)
        if r.returncode != 0: raise RuntimeError((r.stderr or r.stdout).strip()[:200] or "nvidia-smi код %d" % r.returncode)
        gp = []
        for ln in r.stdout.strip().splitlines():
            n, mu, mt, ut, tp = [x.strip() for x in ln.split(",")]
            num = lambda x: float(x) if x.replace(".", "", 1).isdigit() else None
            gp.append({"name": n, "vram_used_mib": num(mu), "vram_total_mib": num(mt), "util_percent": num(ut), "temp_c": num(tp)})
        out["gpus"] = gp; out["gpu"] = gp[0] if gp else {"error": "nvidia-smi без GPU"}
    except FileNotFoundError: out["gpu"] = {"error": "nvidia-smi не найден"}
    except Exception as e: out["gpu"] = {"error": "nvidia-smi: %s" % e}
    # плоские поля для старых датчиков чата (nox-telemetry.js): только если измерение реально получено
    c, r_, g, ct = out.get("cpu", {}), out.get("ram", {}), out.get("gpu", {}), out.get("cpu_temp", {})
    flat = {"timestamp": out["ts"], "cpu_percent": c.get("percent"), "ram_percent": r_.get("percent"),
            "ram_used_gb": round(r_["used_bytes"] / 2**30, 2) if "used_bytes" in r_ else None, "ram_total_gb": round(r_["total_bytes"] / 2**30, 2) if "total_bytes" in r_ else None,
            "gpu_percent": g.get("util_percent"), "vram_used_gb": round(g["vram_used_mib"] / 1024, 2) if g.get("vram_used_mib") is not None else None,
            "vram_total_gb": round(g["vram_total_mib"] / 1024, 2) if g.get("vram_total_mib") is not None else None,
            "gpu_core_c": g.get("temp_c"), "gpu_temperature_c": g.get("temp_c"), "cpu_temperature_c": ct.get("celsius"), "source": "/api/pc-metrics (nvidia-smi, /proc)"}
    out.update(flat)
    return out

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
        if p == "/api/pc-metrics": return self._j(200, pc_metrics())
        if p == "/api/health": return self._j(200, {"ok": True, "service": "nox-web (S1)", "panel_s2": False, "pc_metrics": True})
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
        if b.get("nox_mode") in ("auto", "fast", "deep"): req["nox_mode"] = b["nox_mode"]   # режим чата Авто/Быстро/Глубоко -> шлюз
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
                    if j.get("nox"): out({"model": TAG, "message": {"role": "assistant", "content": ""}, "done": False, "nox": j["nox"]})   # честная подпись уровня: mode/tier/stages шлюза
                    if t: out(dict({"model": TAG, "message": {"role": "assistant", "content": t}, "done": False}, **({"nox_stage": delta["nox_stage"]} if delta.get("nox_stage") else {})))
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
