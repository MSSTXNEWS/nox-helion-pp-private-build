"""NOX TTS: озвучка по кусочкам. Бэкенды XTTS (coqui TTS, RU/ES, клонирование по образцу) и запасной Piper.

Эндпоинты:
  GET  /health
  POST /synth     {text, lang?, format: sse|pcm|wav|json}   весь текст сразу -> поток аудио по фразам (chunked HTTP)
  POST /session   {lang?, format?}  -> {id}                 сессия потокового текста (для токенов LLM)
  POST /session/<id>/text   {text, final?}                  дописать текст; фразы озвучиваются по мере готовности
  GET  /session/<id>/audio?format=sse|pcm|wav               поток аудио (chunked): SSE base64 или сырой PCM16/WAV
  POST /session/<id>/stop   (и POST /stop {session?})       отмена озвучки (STOP)
Формат аудио на выходе фиксирован: PCM16 mono, NOX_TTS_OUT_RATE (по умолчанию 24000) - любой бэкенд ресемплится к нему.
SSE-события: {"type":"audio","seq","text","backend","sample_rate","pcm_b64"} ... {"type":"end"} | {"type":"cancelled"}.
"""
import base64
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from voice import common  # noqa: E402
from voice.common import env, env_float, env_int, env_bool  # noqa: E402
from voice.textproc import SentenceSegmenter, clean_for_tts, detect_lang, has_speakable  # noqa: E402

OUT_RATE = env_int("NOX_TTS_OUT_RATE", 24000)


class BackendError(Exception):
    pass


class TTSBackend:
    name = "base"

    def available(self):
        """(bool, причина)"""
        return False, "not implemented"

    def synth(self, text, lang, voice=None):
        """-> (pcm16 mono bytes, sample_rate). Бросает BackendError при сбое."""
        raise NotImplementedError

    def info(self):
        ok, why = self.available()
        return {"name": self.name, "available": ok, "reason": None if ok else why}


class XttsBackend(TTSBackend):
    """coqui TTS XTTS-v2. env: NOX_XTTS_MODEL, NOX_TTS_DEVICE (cpu|cuda), NOX_XTTS_SPEAKER_WAV (образец голоса для клонирования),
    NOX_XTTS_SPEAKER (имя встроенного голоса, если образца нет), NOX_XTTS_AGREE_TOS=1 (принять лицензию CPML от имени владельца)."""
    name = "xtts"
    LANGS = {"ru", "es", "en"}

    def __init__(self):
        self.model_name = env("NOX_XTTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")
        self.device = env("NOX_TTS_DEVICE", "cpu")
        self.speaker_wav = env("NOX_XTTS_SPEAKER_WAV")
        self.speaker = env("NOX_XTTS_SPEAKER", "Claribel Dervla")
        self.tts = None
        self.error = None
        self._lock = threading.Lock()
        self.rate = 24000

    def available(self):
        if not common.have_module("TTS"):
            return False, "python package 'TTS' (coqui) not installed"
        if self.error:
            return False, self.error
        if self.speaker_wav and not os.path.isfile(self.speaker_wav):
            return False, "NOX_XTTS_SPEAKER_WAV not found: %s" % self.speaker_wav
        return True, ""

    def _load(self):
        with self._lock:
            if self.tts is not None:
                return
            if env_bool("NOX_XTTS_AGREE_TOS"):
                os.environ["COQUI_TOS_AGREED"] = "1"
            try:
                from TTS.api import TTS
                t = TTS(self.model_name)
                try:
                    t = t.to(self.device)
                except Exception:
                    if self.device != "cpu":
                        raise
                self.tts = t
                try:
                    self.rate = int(t.synthesizer.output_sample_rate)
                except Exception:
                    pass
            except Exception as e:
                self.error = "load failed: %s: %s" % (type(e).__name__, str(e)[:200])
                raise BackendError(self.error)

    def synth(self, text, lang, voice=None):
        ok, why = self.available()
        if not ok:
            raise BackendError(why)
        if lang not in self.LANGS:
            raise BackendError("xtts: language %r unsupported" % lang)
        self._load()
        try:
            kw = {"text": text, "language": lang}
            sw = voice or self.speaker_wav
            if sw and os.path.isfile(sw):
                kw["speaker_wav"] = sw
            else:
                kw["speaker"] = self.speaker
            wav = self.tts.tts(**kw)
        except Exception as e:
            raise BackendError("xtts synth failed: %s: %s" % (type(e).__name__, str(e)[:200]))
        import array
        vals = wav.tolist() if hasattr(wav, "tolist") else list(wav)
        pcm = array.array("h", [max(-32768, min(32767, int(float(x) * 32767))) for x in vals])
        return common.from_samples(pcm), self.rate


class PiperBackend(TTSBackend):
    """Piper через CLI. env: NOX_PIPER_BIN (путь/имя, по умолчанию 'piper'; нет бинаря, но есть python-модуль piper -> `python -m piper`),
    NOX_PIPER_MODEL_RU / NOX_PIPER_MODEL_ES / NOX_PIPER_MODEL (.onnx; рядом .onnx.json с sample_rate)."""
    name = "piper"

    def __init__(self):
        self.bin = env("NOX_PIPER_BIN", "piper")

    def _cmd(self):
        b = shutil.which(self.bin) or (self.bin if os.path.isfile(self.bin) and os.access(self.bin, os.X_OK) else None)
        if b:
            return [b]
        if common.have_module("piper"):
            return [sys.executable, "-m", "piper"]
        return None

    def model_for(self, lang):
        return env("NOX_PIPER_MODEL_%s" % lang.upper()) or env("NOX_PIPER_MODEL")

    def available(self):
        if not self._cmd():
            return False, "piper not found (binary NOX_PIPER_BIN=%s / python module piper)" % self.bin
        if not any(env("NOX_PIPER_MODEL_%s" % l) for l in ("RU", "ES")) and not env("NOX_PIPER_MODEL"):
            return False, "no Piper model (NOX_PIPER_MODEL_RU / NOX_PIPER_MODEL_ES / NOX_PIPER_MODEL)"
        return True, ""

    @staticmethod
    def model_rate(model):
        try:
            with open(model + ".json", encoding="utf-8") as f:
                return int(json.load(f)["audio"]["sample_rate"])
        except Exception:
            return 22050

    def _run(self, args, text):
        try:
            return subprocess.run(self._cmd() + args, input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=env_float("NOX_PIPER_TIMEOUT", 60))
        except subprocess.TimeoutExpired:
            raise BackendError("piper timeout")
        except OSError as e:
            raise BackendError("piper exec failed: %s" % e)

    def synth(self, text, lang, voice=None):
        ok, why = self.available()
        if not ok:
            raise BackendError(why)
        model = voice if (voice and voice.endswith(".onnx")) else self.model_for(lang)
        if not model or not os.path.isfile(model):
            raise BackendError("piper: no model file for lang %r (%s)" % (lang, model))
        last = ""
        for flag in ("--output-raw", "--output_raw"):          # сырой PCM16 в stdout (разные версии piper)
            p = self._run(["--model", model, flag], text)
            if p.returncode == 0 and p.stdout:
                return p.stdout, self.model_rate(model)
            last = p.stderr.decode("utf-8", "ignore")[-200:]
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            for flag in ("-f", "--output_file"):                # запасной путь: WAV во временный файл
                p = self._run(["--model", model, flag, tmp], text)
                if p.returncode == 0 and os.path.getsize(tmp) > 44:
                    with open(tmp, "rb") as f:
                        pcm, rate = common.decode_wav(f.read())
                    return pcm, rate
                last = p.stderr.decode("utf-8", "ignore")[-200:]
        except common.AudioError as e:
            raise BackendError("piper wav: %s" % e)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise BackendError("piper failed: %s" % last)


class BackendManager:
    """Перебирает бэкенды по порядку NOX_TTS_BACKENDS (xtts,piper). Сбой -> откат на следующий; упавший бэкенд
    отключается на cooldown секунд (NOX_TTS_COOLDOWN, 120), недоступный - пропускается без попыток."""

    def __init__(self, backends=None, cooldown=None):
        if backends is None:
            reg = {"xtts": XttsBackend, "piper": PiperBackend}
            order = [x.strip() for x in env("NOX_TTS_BACKENDS", "xtts,piper").split(",") if x.strip() in reg]
            backends = [reg[n]() for n in order]
        self.backends = backends
        self.cooldown = env_float("NOX_TTS_COOLDOWN", 120) if cooldown is None else cooldown
        self.down_until = {}
        self.last_error = {}
        self.stats = {}
        self.lock = threading.Lock()

    def synth(self, text, lang, voice=None):
        """-> (pcm16 @ OUT_RATE, backend_name). BackendError, если не вышло ни одним."""
        errs = []
        for b in self.backends:
            with self.lock:
                if self.down_until.get(b.name, 0) > time.time():
                    errs.append("%s: cooling down (%s)" % (b.name, self.last_error.get(b.name)))
                    continue
            ok, why = b.available()
            if not ok:
                errs.append("%s: %s" % (b.name, why))
                continue
            try:
                pcm, rate = b.synth(text, lang, voice)
                if not pcm:
                    raise BackendError("empty audio")
            except Exception as e:
                msg = str(e)
                with self.lock:
                    self.last_error[b.name] = msg
                    self.down_until[b.name] = time.time() + self.cooldown
                    self.stats[b.name + "_errors"] = self.stats.get(b.name + "_errors", 0) + 1
                errs.append("%s: %s" % (b.name, msg))
                continue
            with self.lock:
                self.stats[b.name] = self.stats.get(b.name, 0) + 1
            return common.resample_pcm16(pcm, rate, OUT_RATE), b.name
        raise BackendError("no TTS backend produced audio: " + "; ".join(errs))

    def health(self):
        infos = []
        for b in self.backends:
            i = b.info()
            i["cooling_down"] = self.down_until.get(b.name, 0) > time.time()
            i["last_error"] = self.last_error.get(b.name)
            infos.append(i)
        return {"backends": infos, "stats": dict(self.stats),
                "ready": any(i["available"] for i in infos)}


class SpeechSession:
    """Потоковый текст -> фразы -> аудио-события в очереди audio_q."""

    def __init__(self, mgr, lang="auto", voice=None, **seg_kw):
        self.id = uuid.uuid4().hex[:12]
        self.mgr = mgr
        self.lang = lang or "auto"
        self.voice = voice
        self.seg = SentenceSegmenter(**seg_kw)
        self.text_q = queue.Queue()
        self.audio_q = queue.Queue()
        self.cancelled = threading.Event()
        self.done = threading.Event()
        self.seq = 0
        self.created = time.time()
        self.last_active = time.time()
        self.stats = {"phrases": 0, "bytes": 0, "errors": 0}
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def push(self, text, final=False):
        if self.cancelled.is_set():
            return False
        self.last_active = time.time()
        self.text_q.put((text or "", bool(final)))
        return True

    def cancel(self):
        self.cancelled.set()
        try:
            while True:
                self.text_q.get_nowait()
        except queue.Empty:
            pass
        self.text_q.put(None)
        try:
            while True:
                self.audio_q.get_nowait()
        except queue.Empty:
            pass
        self.audio_q.put({"type": "cancelled"})

    def _speak(self, phrase):
        lang = self.lang if self.lang != "auto" else detect_lang(phrase)
        t = clean_for_tts(phrase, lang)
        if not has_speakable(t):
            return
        try:
            pcm, backend = self.mgr.synth(t, lang, self.voice)
        except BackendError as e:
            self.stats["errors"] += 1
            self.audio_q.put({"type": "error", "message": str(e), "text": t})
            return
        if self.cancelled.is_set():
            return
        self.seq += 1
        self.stats["phrases"] += 1
        self.stats["bytes"] += len(pcm)
        self.audio_q.put({"type": "audio", "seq": self.seq, "text": t, "backend": backend, "sample_rate": OUT_RATE, "pcm": pcm})

    def _run(self):
        try:
            while not self.cancelled.is_set():
                item = self.text_q.get()
                if item is None or self.cancelled.is_set():
                    break
                text, final = item
                for ph in self.seg.feed(text):
                    if self.cancelled.is_set():
                        break
                    self._speak(ph)
                if final:
                    for ph in self.seg.flush():
                        if self.cancelled.is_set():
                            break
                        self._speak(ph)
                    if not self.cancelled.is_set():
                        self.audio_q.put({"type": "end", "stats": dict(self.stats)})
                    break
        finally:
            self.done.set()

    def events(self, idle_timeout=120):
        """Генератор событий до end/cancelled."""
        while True:
            try:
                e = self.audio_q.get(timeout=idle_timeout)
            except queue.Empty:
                yield {"type": "timeout"}
                return
            yield e
            if e["type"] in ("end", "cancelled", "timeout"):
                return


class TtsService:
    def __init__(self, mgr=None):
        self.mgr = mgr or BackendManager()
        self.sessions = {}
        self.lock = threading.Lock()
        self.ttl = env_float("NOX_TTS_SESSION_TTL", 600)

    def _seg_kw(self):
        return {"max_chars": env_int("NOX_TTS_MAX_CHARS", 180), "min_chars": env_int("NOX_TTS_MIN_CHARS", 12),
                "first_min_chars": env_int("NOX_TTS_FIRST_MIN_CHARS", 30)}

    def new_session(self, lang="auto", voice=None):
        now = time.time()
        with self.lock:
            for k in [k for k, s in self.sessions.items() if now - s.last_active > self.ttl]:
                self.sessions.pop(k).cancel()
            s = SpeechSession(self.mgr, lang, voice, **self._seg_kw())
            self.sessions[s.id] = s
        return s

    def get(self, sid):
        with self.lock:
            return self.sessions.get(sid)

    def stop(self, sid=None):
        with self.lock:
            targets = [self.sessions[sid]] if sid and sid in self.sessions else ([] if sid else list(self.sessions.values()))
        for s in targets:
            s.cancel()
        return len(targets)

    def health(self):
        h = self.mgr.health()
        h.update(ok=True, service="nox-tts", out_rate=OUT_RATE, sessions=len(self.sessions),
                 text_cleaning=True,
                 ready_note=None if h["ready"] else "no backend available: install TTS (XTTS) or piper-tts + model; see voice/README.md")
        return h


def event_to_wire(e, fmt):
    """Событие -> bytes для выбранного формата."""
    t = e["type"]
    if fmt == "sse":
        o = {k: v for k, v in e.items() if k != "pcm"}
        if t == "audio":
            o["pcm_b64"] = base64.b64encode(e["pcm"]).decode("ascii")
        return ("data: " + json.dumps(o, ensure_ascii=False) + "\n\n").encode("utf-8")
    if t == "audio":
        return e["pcm"]
    return b""


def make_handler(svc):
    class H(common.JsonHandler):
        def _qs(self):
            u = urllib.parse.urlparse(self.path)
            return u.path.rstrip("/") or "/", {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}

        def _stream(self, s, fmt):
            if fmt == "sse":
                self.start_chunked("text/event-stream", {"X-Session": s.id})
            elif fmt == "wav":
                self.start_chunked("audio/wav", {"X-Session": s.id, "X-Sample-Rate": str(OUT_RATE)})
                self.write_chunk(common.wav_stream_header(OUT_RATE))
            else:
                self.start_chunked("audio/L16; rate=%d; channels=1" % OUT_RATE, {"X-Session": s.id, "X-Sample-Rate": str(OUT_RATE)})
            try:
                for e in s.events():
                    self.write_chunk(event_to_wire(e, fmt))
                self.end_chunked()
            except (BrokenPipeError, ConnectionResetError, OSError):
                s.cancel()     # клиент ушёл - не синтезируем в пустоту

        def do_GET(self):
            path, q = self._qs()
            if path == "/health":
                return self.send_json(200, svc.health())
            p = path.strip("/").split("/")
            if len(p) == 3 and p[0] == "session" and p[2] == "audio":
                s = svc.get(p[1])
                if not s:
                    return self.send_json(404, {"error": "no such session"})
                return self._stream(s, q.get("format", "sse"))
            self.send_json(404, {"error": "not found"})

        def do_POST(self):
            path, q = self._qs()
            try:
                p = path.strip("/").split("/")
                if path == "/synth":
                    o = self.json_body()
                    text = str(o.get("text", ""))
                    if not text.strip():
                        return self.send_json(400, {"error": "text required"})
                    fmt = o.get("format", q.get("format", "sse"))
                    s = svc.new_session(o.get("lang", "auto"), o.get("voice"))
                    s.push(text, final=True)
                    if fmt == "json":
                        evs = list(s.events())
                        out = [{k: (base64.b64encode(v).decode() if k == "pcm" else v) for k, v in e.items()} for e in evs]
                        return self.send_json(200, {"events": out})
                    return self._stream(s, fmt)
                if path == "/session":
                    o = self.json_body()
                    s = svc.new_session(o.get("lang", "auto"), o.get("voice"))
                    return self.send_json(200, {"id": s.id, "out_rate": OUT_RATE, "format": "PCM16 mono"})
                if path == "/stop":
                    o = self.json_body()
                    return self.send_json(200, {"stopped": svc.stop(o.get("session"))})
                if len(p) == 3 and p[0] == "session":
                    s = svc.get(p[1])
                    if not s:
                        self.read_body()
                        return self.send_json(404, {"error": "no such session"})
                    if p[2] == "text":
                        o = self.json_body()
                        ok = s.push(str(o.get("text", "")), bool(o.get("final", False)))
                        return self.send_json(200 if ok else 409, {"accepted": ok, "cancelled": s.cancelled.is_set()})
                    if p[2] == "stop":
                        self.read_body()
                        s.cancel()
                        return self.send_json(200, {"stopped": 1})
                self.read_body()
                self.send_json(404, {"error": "not found"})
            except ValueError as e:
                self.send_json(400, {"error": str(e)})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                self.send_json(500, {"error": "%s: %s" % (type(e).__name__, e)})
    return H


def main():
    host = env("NOX_TTS_HOST", "127.0.0.1")
    port = env_int("NOX_TTS_PORT", 8094)
    svc = TtsService()
    srv = common.serve(make_handler(svc), host, port)
    h = svc.health()
    print("[nox-tts] %s:%d ready=%s backends=%s" % (host, port, h["ready"], [(b["name"], b["available"], b["reason"]) for b in h["backends"]]), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
