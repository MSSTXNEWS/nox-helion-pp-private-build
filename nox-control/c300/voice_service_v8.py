#!/usr/bin/env python3
"""V2-15: голосовой сервис NOX на 127.0.0.1:18797 (stdlib, MIT). В автозапуск не ставится: запуск вручную `python3 -I voice_service.py`.
Цепочка: аудио -> STT faster-whisper (:8093 POST /transcribe) -> /api/turn (NDJSON, web :8091) -> разбор на предложения -> Piper (V2-14) -> события audio.
Barge-in: клиент шлёт кадры микрофона на /voice/vad пока играет ответ; VAD (silero ONNX, MIT, при наличии onnxruntime и модели; иначе энергетический) видит речь -> ход останавливается (/api/turn/stop) и поток audio обрывается.
Маршруты: GET /health | POST /tts {text} -> wav | POST /voice/turn?cid=&user= (тело = аудио, Content-Type audio/*) -> NDJSON {t:stt|delta|audio|barge|done|error} | POST /voice/vad?cid=&sr=16000 (тело = PCM16 mono, кадры по 512 отсчётов) -> {speech,p,barge} | POST /voice/stop {cid}.
Env: NOX_STT=127.0.0.1:8093 NOX_WEB=127.0.0.1:8091 NOX_PIPER_MODEL=/workspace/nox/voice/ru_RU-dmitri-medium.onnx NOX_PIPER=piper NOX_SILERO=/workspace/nox/voice/silero_vad.onnx NOX_TTS_FAKE=1 (тест: синус вместо Piper).
V8 (28.11): Piper в процессе (без запуска на каждую фразу, прогрев), кэш коротких фраз и филлеров, ранний сброс первой фразы, барж-ин с гистерезисом + «понял, слушаю» + конец реплики, обрыв апстрима сокетом, темп/пауза из self_now.pad (тембр не меняется). Запуск: venv Piper (voice/venv/bin/python).
Флаг отката: state/voice.off -> сервис отвечает 503 на всё, кроме /health. Pipecat не взят: цепочка ниже короче и без новых зависимостей."""
import os, sys, re, json, time, wave, io, struct, math, base64, threading, subprocess, http.client, tempfile, socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from piper_tts import normalize
E = os.environ.get
STT, WEB = E("NOX_STT", "127.0.0.1:8093"), E("NOX_WEB", "127.0.0.1:8091")
MODEL, PIPER, SILERO = E("NOX_PIPER_MODEL", "/workspace/nox/voice/ru_RU-dmitri-medium.onnx"), E("NOX_PIPER", "piper"), E("NOX_SILERO", "/workspace/nox/voice/silero_vad.onnx")
FLAG = "/workspace/nox/state/voice.off"; SR = 22050
SESS = {}; SL = threading.Lock()
def hp(addr): h, p = addr.split(":"); return http.client.HTTPConnection(h, int(p), timeout=60)
# ---- TTS (Piper в процессе)
PAD_F = E("NOX_PAD_FILE", "/workspace/nox/state/core/self_now.json")
_voice = [None]; TL = threading.Lock(); CACHE = {}; _pad = [0.0, (1.0, 0.15)]
def pad_prosody():
    """(length_scale, sentence_silence) из self_now.pad: темп от возбуждения a, пауза от валентности v. Тембр не трогаем."""
    now = time.time()
    if now - _pad[0] < 5: return _pad[1]
    r = (1.0, 0.15)
    try:
        p = json.load(open(PAD_F)).get("pad") or {}
        v, a = float(p.get("v", 0)), float(p.get("a", 0.3))
        r = (round(min(1.12, max(0.9, 1.0 - 0.25 * (a - 0.3))), 3), round(min(0.4, max(0.08, 0.15 + 0.2 * max(0, -v) - 0.05 * max(0, v))), 3))
    except Exception: pass
    _pad[0] = now; _pad[1] = r; return r
def _load():
    if _voice[0] is None:
        from piper import PiperVoice; _voice[0] = PiperVoice.load(MODEL)
    return _voice[0]
def tts_pcm(text, pad=True):
    """-> (pcm16 bytes, sample_rate). Кэш для коротких фраз (<=80 симв.)."""
    t = normalize(text)
    if not t.strip(): return b"", SR
    if E("NOX_TTS_FAKE"):
        n = int(SR * min(3.0, 0.05 * len(t))); return b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * i / SR))) for i in range(n)), SR
    ls, ss = pad_prosody() if pad else (1.0, 0.15); key = (t, ls, ss)
    if key in CACHE: return CACHE[key]
    try:
        with TL:
            v = _load(); r = (b"".join(v.synthesize_stream_raw(t, length_scale=ls, sentence_silence=ss)), int(v.config.sample_rate))
    except ImportError:
        p = subprocess.run([PIPER, "--model", MODEL, "--output-raw"], input=t.encode(), capture_output=True, timeout=60)
        if p.returncode: raise RuntimeError(p.stderr.decode("utf-8", "replace")[-200:])
        r = (p.stdout, SR)
    if len(t) <= 80 and len(CACHE) < 300: CACHE[key] = r
    return r
FILLERS = ["Угу.", "Секунду.", "Смотрю."]; ACK = "Понял, слушаю."; FIX = {}
def prewarm():
    """Прогрев модели и фиксированные фразы (без PAD: стабильные, из кэша на диске памяти)."""
    try:
        for t in FILLERS + [ACK]: FIX[t] = tts_pcm(t, pad=False)
    except Exception: pass
def wav_of(pcm, sr):
    b = io.BytesIO(); w = wave.open(b, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm); w.close(); return b.getvalue()
# ---- VAD
class Vad:
    """Silero v5 ONNX (MIT) если есть onnxruntime+модель, иначе энергетический порог с удержанием. kadr 512 отсчётов 16 кГц."""
    def __init__(self):
        self.kind = "energy"; self.sess = None; self.st = None; self.ctx = None; self.hang = 0; self.run = 0; self.sil = 0; self.inspeech = False
        try:
            import onnxruntime as ort, numpy as np
            if os.path.exists(SILERO):
                self.np = np; self.sess = ort.InferenceSession(SILERO, providers=["CPUExecutionProvider"]); self.kind = "silero"; self.reset()
        except Exception: pass
    def reset(self):
        if self.sess: self.st = self.np.zeros((2, 1, 128), dtype="float32"); self.ctx = self.np.zeros((1, 64), dtype="float32")
    def prob(self, pcm):
        n = len(pcm) // 2; xs = struct.unpack("<%dh" % n, pcm[:n * 2])
        if self.kind == "silero" and n >= 512:
            np = self.np; x = np.array(xs[:512], dtype="float32")[None] / 32768.0; x = np.concatenate([self.ctx, x], 1); self.ctx = x[:, -64:]
            o, self.st = self.sess.run(None, {"input": x, "state": self.st, "sr": np.array(16000, dtype="int64")}); return float(o[0][0])
        rms = math.sqrt(sum(x * x for x in xs) / max(n, 1)); return min(1.0, rms / 2500.0)
    def feed(self, pcm):
        """Кадры по 512 отсчётов. -> (p_max, speech_run_frames, eou). Барж-ин: >=3 кадров речи подряд (~96 мс). Конец реплики: >=22 кадров тишины (~700 мс) после речи."""
        pmax = 0.0; eou = False; th = 0.5 if self.kind == "silero" else 0.3
        for i in range(0, len(pcm) - 1023, 1024):
            pr = self.prob(pcm[i:i + 1024]); pmax = max(pmax, pr)
            if pr >= th: self.run += 1; self.sil = 0; self.inspeech = self.inspeech or self.run >= 3
            else:
                self.run = 0
                if self.inspeech:
                    self.sil += 1
                    if self.sil >= 22: eou = True; self.inspeech = False; self.sil = 0
        return pmax, self.run, eou
VAD = {}
def vad_for(cid):
    with SL:
        if cid not in VAD: VAD[cid] = Vad()
        return VAD[cid]
# ---- ход
SENT = re.compile(r"(.+?[.!?…]+[\"»)]*(?:\s+|$)|.+?\n+)", re.S)
def split_sent(buf, final=False, first=False):
    out = []; pos = 0
    for m in SENT.finditer(buf):
        out.append(m.group(1).strip()); pos = m.end()
    rest = buf[pos:]
    if first and not out and not final and len(rest) >= 14:
        m = re.search(r"[,;:—–]\s", rest[8:])
        if m: k = 8 + m.end(); out.append(rest[:k].strip()); rest = rest[k:]
        elif len(rest) >= 40: k = rest.rfind(" ", 0, 40); k = k if k > 15 else 40; out.append(rest[:k].strip()); rest = rest[k:]
    if final and rest.strip(): out.append(rest.strip()); rest = ""
    elif len(rest) > 240:
        k = rest.rfind(", ", 0, 240); k = k if k > 60 else 240; out.append(rest[:k + 1].strip()); rest = rest[k + 1:]
    return [x for x in out if x], rest
def stop_turn(cid, sync=False):
    s = SESS.get(cid)
    if s:
        s["stop"] = True; s["stop_t"] = time.time()
        try: s["up"].sock.shutdown(socket.SHUT_RDWR)
        except Exception: pass
    def _web():
        try:
            c = hp(WEB); c.request("POST", "/api/turn/stop", json.dumps({"conversation_id": cid}), {"Content-Type": "application/json"}); c.getresponse().read(); c.close()
        except Exception: pass
    th = threading.Thread(target=_web, daemon=True); th.start()
    if sync: th.join(10)
def voice_turn(h, cid, user):
    s = SESS[cid] = {"stop": False, "speaking": True, "t0": time.time(), "done": threading.Event(), "up": None}
    wl = threading.Lock()
    def ev(o):
        d = json.dumps(o, ensure_ascii=False).encode() + b"\n"
        with wl: h.wfile.write(b"%x\r\n" % len(d) + d + b"\r\n"); h.wfile.flush()
    try:
        audio = h.rfile.read(int(h.headers.get("Content-Length") or 0)); t0 = time.time()
        c = hp(STT); c.request("POST", "/transcribe", audio, {"Content-Type": h.headers.get("Content-Type") or "audio/wav"}); r = c.getresponse(); j = json.loads(r.read() or b"{}"); c.close()
        text = str(j.get("text") or "").strip(); ev({"t": "stt", "text": text, "ms": int((time.time() - t0) * 1000)})
        if not text: return ev({"t": "done", "empty": True})
        c = hp(WEB); s["up"] = c; c.request("POST", "/api/turn", json.dumps({"conversation_id": cid, "message": text, "mode": "fast", "user_id": user, "source": "voice"}), {"Content-Type": "application/json"}); r = c.getresponse()
        buf = ""; seq = 0; first = [None]; filler_s = [None]
        def emit(pcm, sr, sn, filler=False):
            nonlocal seq
            if pcm and not s["stop"]:
                ev({"t": "audio", "seq": seq, "sr": sr, "text": sn, "filler": filler, "pcm_b64": base64.b64encode(pcm).decode()}); seq += 1
        def fire_filler():
            if first[0] is None and not s["stop"] and filler_s[0] is None:
                f = FILLERS[hash(text) % len(FILLERS)]
                try:
                    pcm, sr = FIX.get(f) or tts_pcm(f, pad=False)
                    if first[0] is None and not s["stop"]: filler_s[0] = time.time() - t0; emit(pcm, sr, f, True)
                except Exception: pass
        if not E("NOX_NO_FILLER"):
            tm = threading.Timer(max(0.0, float(E("NOX_FILLER_S", "0.5")) - (time.time() - t0)), fire_filler); tm.daemon = True; tm.start()
        def speak(sents):
            for sn in sents:
                if s["stop"]: return
                pcm, sr = tts_pcm(sn)
                if s["stop"]: return
                if pcm: first[0] = first[0] or time.time() - t0; emit(pcm, sr, sn)
        while not s["stop"]:
            l = r.readline()
            if not l: break
            try: o = json.loads(l)
            except Exception: continue
            if o.get("t") == "delta":
                ev({"t": "delta", "text": o.get("text")}); buf += str(o.get("text") or ""); sents, buf = split_sent(buf, first=first[0] is None); speak(sents)
            elif o.get("t") in ("error",): ev(o); break
        if not s["stop"]: speak(split_sent(buf, True)[0])
        try: c.close()
        except Exception: pass
        ev({"t": "barge" if s["stop"] else "done", "first_audio_s": first[0], "filler_s": filler_s[0], "chunks": seq, "cancel_ms": int((time.time() - s["stop_t"]) * 1000) if s.get("stop_t") else None})
    except Exception as e:
        try: ev({"t": "error", "error": str(e)[:150]})
        except Exception: pass
    finally:
        s["speaking"] = False; s["done"].set()
        try: h.wfile.write(b"0\r\n\r\n")
        except Exception: pass
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def _j(self, code, o):
        d = json.dumps(o, ensure_ascii=False).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
    def q(self, k, d=""): m = re.search(r"[?&]%s=([^&]*)" % k, self.path); return m.group(1) if m else d
    def do_GET(self):
        if self.path.startswith("/health"):
            st = None
            try: c = hp(STT); c.request("GET", "/health"); st = c.getresponse().status; c.close()
            except Exception: pass
            return self._j(200, {"ok": True, "off": os.path.exists(FLAG), "model": os.path.exists(MODEL) or bool(E("NOX_TTS_FAKE")), "stt_http": st, "vad": Vad().kind, "tts": "inproc" if _voice[0] else "cold", "fix": len(FIX), "pad": list(pad_prosody())})
        self._j(404, {})
    def do_POST(self):
        if os.path.exists(FLAG): return self._j(503, {"error": "voice.off"})
        p = self.path.split("?")[0]
        if p == "/voice/turn":
            cid = re.sub(r"[^A-Za-z0-9_.-]", "", self.q("cid")) or "voice-" + str(int(time.time())); user = self.q("user", "owner")
            self.send_response(200); self.send_header("Content-Type", "application/x-ndjson"); self.send_header("Transfer-Encoding", "chunked"); self.end_headers(); return voice_turn(self, cid, user)
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if p == "/tts":
            try: pcm, sr = tts_pcm(str(json.loads(raw or b"{}").get("text") or "")[:2000])
            except Exception as e: return self._j(500, {"error": str(e)[:150]})
            d = wav_of(pcm, sr); self.send_response(200); self.send_header("Content-Type", "audio/wav"); self.send_header("Content-Length", str(len(d))); self.end_headers(); return self.wfile.write(d)
        if p == "/voice/vad":
            cid = self.q("cid", "x"); v = vad_for(cid); t_in = time.time(); pr, run, eou = v.feed(raw); sp = run >= 1
            s = SESS.get(cid); barge = bool(run >= 3 and s and s.get("speaking") and not s.get("stop")); o = {"speech": sp, "p": round(pr, 3), "barge": False, "eou": eou, "vad": v.kind}
            if barge:
                stop_turn(cid); s["done"].wait(1.5); pcm, sr = FIX.get(ACK) or tts_pcm(ACK, pad=False)
                o.update({"barge": True, "cancel_ms": int((time.time() - t_in) * 1000), "ack": ACK, "ack_sr": sr, "ack_pcm_b64": base64.b64encode(pcm).decode()})
            return self._j(200, o)
        if p == "/voice/stop":
            cid = str(json.loads(raw or b"{}").get("cid") or ""); stop_turn(cid); return self._j(200, {"ok": True})
        self._j(404, {})
if __name__ == "__main__":
    threading.Thread(target=prewarm, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", int(E("NOX_VOICE_PORT", "18797"))), H).serve_forever()
