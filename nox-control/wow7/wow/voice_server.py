"""voice_server: единый HTTP-вход голоса NOX поверх уже существующего пакета nox-control/voice (не замена, а надстройка).

Добавляет к voice/tts_server.py + voice/stt_server.py:
  * мужские голоса RU/ES: Silero v5 (ru, aidar/eugene), Kokoro (es, em_alex/em_santa), запасной Piper/XTTS из voice/;
    порядок по языку (NOX_VOICE_ORDER_RU / _ES), упавший бэкенд отключается на cooldown (логика BackendManager);
  * настроение в голосе: mood {p,a} -> скорость речи (Kokoro; для остальных игнорируется, об этом честно сказано в /health);
  * стрим чанками: POST /tts -> chunked PCM16 (X-Sample-Rate) или SSE; отмена POST /cancel и разрывом соединения;
  * перебивание: POST /barge?sid= (PCM16 16 кГц с микрофона) -> VAD (silero-vad, иначе энергетический) -> при >= min_ms
    речи во время озвучки сессия sid отменяется на сервере;
  * понятная ошибка, если пакета/модели нет: 503 {error, missing[], hint} вместо падения или тишины.
Порт NOX_VOICE_PORT (8095), хост 127.0.0.1. Веб-прокси: /voice/* -> этот порт.
"""
import array
import base64
import json
import os
import queue
import shutil
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.environ.get("NOX_CONTROL"), os.path.join(HERE, "..", ".."), "/root/nox/src/nox-control"):
    if _p and os.path.isdir(os.path.join(_p, "voice")) and _p not in sys.path:
        sys.path.insert(0, _p)
try:
    from voice import common
    from voice.common import env, env_float, env_int
    from voice.textproc import SentenceSegmenter, clean_for_tts, detect_lang, has_speakable
    from voice.tts_server import BackendError, BackendManager, PiperBackend, TTSBackend, XttsBackend
    from voice.stt_server import FasterWhisperTranscriber, TranscribeError
except ImportError as _e:       # понятная ошибка вместо трассировки
    raise SystemExit("voice_server: не найден пакет nox-control/voice (%s). Задайте NOX_CONTROL=/путь/к/nox-control." % _e)

OUT_RATE = env_int("NOX_TTS_OUT_RATE", 24000)
PIP_HINT = {
    "torch": "pip install torch --index-url https://download.pytorch.org/whl/cpu",
    "kokoro": "pip install 'kokoro>=0.9.4' soundfile  (+ apt install espeak-ng)",
    "silero_vad": "pip install silero-vad onnxruntime",
}
_ctx = threading.local()        # скорость речи текущего запроса (BackendManager не передаёт лишних аргументов)


def current_speed():
    return getattr(_ctx, "speed", 1.0)


def mood_speed(mood):
    """mood {p,a} (-1..1) -> множитель скорости 0.9..1.12: бодрее при высоком возбуждении, медленнее при унынии."""
    if not isinstance(mood, dict):
        return 1.0
    try:
        p, a = float(mood.get("p", 0.0)), float(mood.get("a", 0.0))
    except (TypeError, ValueError):
        return 1.0
    sp = 1.0 + 0.10 * max(-1.0, min(1.0, a)) + (0.04 * p if p > 0 else 0.06 * p)
    return round(max(0.9, min(1.12, sp)), 3)


def to_pcm16(audio):
    """float [-1,1] (list/np/torch) -> PCM16 LE bytes."""
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    try:
        import numpy as np
        a = np.clip(np.asarray(audio, dtype=np.float32).reshape(-1), -1.0, 1.0)
        return (a * 32767.0).astype("<i2").tobytes()
    except ImportError:
        arr = array.array("h", (int(max(-1.0, min(1.0, float(x))) * 32767) for x in audio))
        if sys.byteorder == "big":
            arr.byteswap()
        return arr.tobytes()


# ---------------- бэкенды ----------------

def _missing_dep(mod):
    return "python package %r not installed (%s)" % (mod, PIP_HINT.get(mod, "pip install " + mod))


class SileroBackend(TTSBackend):
    """Silero TTS v5 (ru). Файл модели ставит install_voice_s1.sh: NOX_SILERO_PATH (по умолчанию $NOX_VOICE_MODELS/silero/v5_ru.pt).
    Лицензия модели v5_ru - CC BY-NC (некоммерческая); v5_cis_base - MIT. Голоса: aidar, eugene (муж.), baya, kseniya, xenia."""
    name = "silero"
    LANGS = {"ru"}

    def __init__(self):
        self.path = env("NOX_SILERO_PATH", os.path.join(env("NOX_VOICE_MODELS", os.path.expanduser("~/nox-voice-models")), "silero", "v5_ru.pt"))
        self.speaker = env("NOX_VOICE_RU", "aidar")
        self.model = None
        self._lock = threading.Lock()

    def available(self):
        if not common.have_module("torch"):
            return False, _missing_dep("torch")
        if not os.path.isfile(self.path):
            return False, "silero model file not found: %s (run install_voice_s1.sh)" % self.path
        return True, ""

    def _load(self):
        with self._lock:
            if self.model is None:
                import torch
                torch.set_num_threads(env_int("NOX_SILERO_THREADS", env_int("NOX_VOICE_THREADS", 2)))
                m = torch.package.PackageImporter(self.path).load_pickle("tts_models", "model")
                m.to("cpu")
                self.model = m
        return self.model

    def synth(self, text, lang, voice=None):
        if lang not in self.LANGS:
            raise BackendError("silero: only ru supported, got %r" % lang)
        ok, why = self.available()
        if not ok:
            raise BackendError(why)
        try:
            audio = self._load().apply_tts(text=text, speaker=voice or self.speaker, sample_rate=24000, put_accent=True, put_yo=True)
        except Exception as e:
            raise BackendError("silero: %s: %s" % (type(e).__name__, e))
        return to_pcm16(audio), 24000


class KokoroBackend(TTSBackend):
    """Kokoro-82M (Apache-2.0). ES: lang_code 'e', мужские em_alex / em_santa. Нужны пакет kokoro и системный espeak-ng.
    Скорость берётся из mood (current_speed())."""
    name = "kokoro"
    CODES = {"es": "e", "en": "a"}

    def __init__(self):
        self.voices = {"es": env("NOX_VOICE_ES", "em_alex"), "en": env("NOX_VOICE_EN", "am_michael")}
        self.pipes = {}
        self._lock = threading.Lock()

    def available(self):
        if not common.have_module("kokoro"):
            return False, _missing_dep("kokoro")
        if not shutil.which("espeak-ng"):
            return False, "espeak-ng not found (apt install espeak-ng)"
        return True, ""

    def synth(self, text, lang, voice=None):
        if lang not in self.CODES:
            raise BackendError("kokoro: supports es/en here, got %r" % lang)
        ok, why = self.available()
        if not ok:
            raise BackendError(why)
        try:
            with self._lock:
                if lang not in self.pipes:
                    from kokoro import KPipeline
                    self.pipes[lang] = KPipeline(lang_code=self.CODES[lang])
                pipe = self.pipes[lang]
            parts = [to_pcm16(a) for _, _, a in pipe(text, voice=voice or self.voices[lang], speed=current_speed()) if a is not None]
        except Exception as e:
            raise BackendError("kokoro: %s: %s" % (type(e).__name__, e))
        if not parts:
            raise BackendError("kokoro: empty audio")
        return b"".join(parts), 24000


REGISTRY = {"silero": SileroBackend, "kokoro": KokoroBackend, "piper": PiperBackend, "xtts": XttsBackend}
DEFAULT_ORDER = {"ru": "silero,piper,xtts", "es": "kokoro,piper,xtts", "en": "kokoro,piper,xtts"}


def build_managers(registry=None, orders=None):
    """-> {lang: BackendManager}. Экземпляры бэкендов общие (модель грузится один раз)."""
    reg = registry or REGISTRY
    inst = {}
    out = {}
    for lang, default in DEFAULT_ORDER.items():
        names = [x.strip() for x in ((orders or {}).get(lang) or env("NOX_VOICE_ORDER_" + lang.upper(), default)).split(",") if x.strip() in reg]
        for n in names:
            inst.setdefault(n, reg[n]())
        out[lang] = BackendManager(backends=[inst[n] for n in names])
    return out


# ---------------- VAD и перебивание ----------------

class EnergyVad:
    """Запасной VAD по энергии: порог = max(abs_min, ratio * шумовой пол); пол медленно подстраивается под тишину."""
    kind = "energy"
    frame = 512

    def __init__(self, ratio=3.0, abs_min=400.0):
        self.ratio, self.abs_min, self.floor = ratio, abs_min, 100.0

    def prob(self, frame):
        s = common.to_samples(frame)
        if not s:
            return 0.0
        rms = (sum(x * x for x in s) / len(s)) ** 0.5
        thr = max(self.abs_min, self.ratio * self.floor)
        if rms < thr:
            self.floor = 0.98 * self.floor + 0.02 * max(rms, 20.0)
            return 0.0
        return 1.0


class SileroVad:
    """silero-vad (MIT-код, ONNX/torch), кадр 512 сэмплов @16 кГц (32 мс), вероятность речи."""
    kind = "silero-vad"
    frame = 512

    def __init__(self):
        import numpy as np
        import torch
        from silero_vad import load_silero_vad
        self._np, self._torch = np, torch
        self.model = load_silero_vad(onnx=common.have_module("onnxruntime"))

    def prob(self, frame):
        x = self._torch.from_numpy(self._np.frombuffer(frame, dtype="<i2").astype("float32") / 32768.0)
        return float(self.model(x, 16000).item())


def make_vad():
    if common.have_module("silero_vad") and common.have_module("torch") and common.have_module("numpy"):
        try:
            return SileroVad()
        except Exception as e:
            sys.stderr.write("voice_server: silero-vad не поднялся (%s), использую энергетический VAD\n" % e)
    return EnergyVad()


class BargeDetector:
    """Копит подряд идущие речевые кадры; barge=True, когда речи >= min_ms (по умолчанию 250). Один сбойный кадр прощается."""

    def __init__(self, vad, min_ms=250, threshold=0.5, grace=1):
        self.vad, self.min_ms, self.thr, self.grace = vad, min_ms, threshold, grace
        self.buf = b""
        self.run_ms = 0.0
        self.miss = 0

    def feed(self, pcm):
        """-> (speech_now, barge). pcm: PCM16 16 кГц mono."""
        self.buf += bytes(pcm[: len(pcm) - len(pcm) % 2])
        step = self.vad.frame * 2
        speech = barge = False
        while len(self.buf) >= step:
            fr, self.buf = self.buf[:step], self.buf[step:]
            if self.vad.prob(fr) >= self.thr:
                self.run_ms += self.vad.frame / 16.0
                self.miss = 0
                speech = True
                if self.run_ms >= self.min_ms:
                    barge, self.run_ms = True, 0.0
            else:
                self.miss += 1
                if self.miss > self.grace:
                    self.run_ms = 0.0
        return speech, barge


# ---------------- задания и сервис ----------------

class Job:
    def __init__(self, sid):
        self.id = uuid.uuid4().hex[:12]
        self.sid = sid
        self.cancel = threading.Event()
        self.t0 = time.time()


class VoiceService:
    def __init__(self, managers=None, transcriber=None, vad_factory=make_vad):
        self.tts = managers if managers is not None else build_managers()
        self.stt = transcriber if transcriber is not None else FasterWhisperTranscriber()
        self.stt_lock = threading.Lock()
        self.jobs = {}
        self.detectors = {}
        self.lock = threading.Lock()
        self._vad_factory = vad_factory
        self._vad = None

    # --- отмена ---
    def start_job(self, sid=None):
        j = Job(sid or "")
        with self.lock:
            self.jobs[j.id] = j
        return j

    def end_job(self, j):
        with self.lock:
            self.jobs.pop(j.id, None)

    def cancel(self, job_id=None, sid=None):
        """Отменяет задание(я) -> список id. Без аргументов - все."""
        with self.lock:
            hit = [j for j in self.jobs.values() if (job_id is None and sid is None) or j.id == job_id or (sid and j.sid == sid)]
        for j in hit:
            j.cancel.set()
        return [j.id for j in hit]

    # --- перебивание ---
    def barge_feed(self, sid, pcm):
        with self.lock:
            if self._vad is None:
                self._vad = self._vad_factory()
            det = self.detectors.get(sid)
            if det is None:
                det = self.detectors[sid] = BargeDetector(self._vad, env_int("NOX_BARGE_MIN_MS", 250))
                if len(self.detectors) > 64:
                    self.detectors.pop(next(iter(self.detectors)))
            speaking = any(j.sid == sid and not j.cancel.is_set() for j in self.jobs.values())
        speech, barge = det.feed(pcm)
        cancelled = self.cancel(sid=sid) if (barge and speaking) else []
        return {"speech": speech, "barge": barge, "speaking": speaking, "cancelled": cancelled, "vad": self._vad.kind}

    # --- здоровье ---
    def health(self):
        tts = {}
        for lang, mgr in self.tts.items():
            h = mgr.health()
            tts[lang] = {"ready": h["ready"], "backends": h["backends"]}
        d = self.stt.deps() if hasattr(self.stt, "deps") else {}
        stt_ready = bool(self.stt.available())
        return {"ok": True, "service": "nox-voice", "out_rate": OUT_RATE, "tts": tts,
                "stt": {"ready": stt_ready, "deps": d, "model": self.stt.info() if hasattr(self.stt, "info") else {},
                        "hint": None if stt_ready else "pip install faster-whisper numpy"},
                "vad": {"silero_vad": common.have_module("silero_vad"), "active": self._vad.kind if self._vad else "lazy"},
                "mood_speed_backends": ["kokoro"], "jobs": len(self.jobs)}

    # --- синтез ---
    def phrases(self, text, lang):
        seg = SentenceSegmenter()
        raw = seg.feed(text) + seg.flush()
        out = []
        for p in raw:
            c = clean_for_tts(p, lang)
            if has_speakable(c):
                out.append(c)
        return out

    def synth_phrase(self, phrase, lang, speed=1.0, voice=None):
        mgr = self.tts.get(lang) or self.tts["ru"]
        _ctx.speed = speed
        return mgr.synth(phrase, lang, voice)


def tts_error_payload(exc):
    msg = str(exc)
    missing = sorted({m for m in ("torch", "kokoro", "piper", "TTS", "espeak-ng", "model file") if m.lower() in msg.lower()})
    return {"error": msg, "missing": missing,
            "hint": "bash install_voice_s1.sh (поставит то, что доступно); /health покажет, какой бэкенд готов"}


def make_handler(svc):
    class H(common.JsonHandler):
        def _q(self):
            from urllib.parse import parse_qs, urlparse
            return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

        def _path(self):
            from urllib.parse import urlparse
            return urlparse(self.path).path.rstrip("/")

        def do_GET(self):
            if self._path() in ("/health", ""):
                return self.send_json(200, svc.health())
            self.send_json(404, {"error": "not found"})

        def do_POST(self):
            try:
                p = self._path()
                if p == "/tts":
                    return self._tts()
                if p == "/cancel":
                    b = self.json_body()
                    return self.send_json(200, {"cancelled": svc.cancel(b.get("id"), b.get("sid"))})
                if p == "/barge":
                    pcm = self.read_body()
                    sid = self._q().get("sid") or "default"
                    return self.send_json(200, svc.barge_feed(sid, pcm))
                if p == "/stt":
                    return self._stt()
                self.send_json(404, {"error": "not found"})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except ValueError as e:
                self.send_json(400, {"error": str(e)})
            except Exception as e:
                self.send_json(500, {"error": "%s: %s" % (type(e).__name__, e)})

        def _stt(self):
            q = self._q()
            try:
                pcm = common.decode_audio(self.read_body(), self.headers.get("Content-Type", ""), q.get("format", "auto"))
            except common.AudioError as e:
                return self.send_json(400, {"error": str(e)})
            t0 = time.time()
            try:
                with svc.stt_lock:
                    r = svc.stt.transcribe(pcm, q.get("language") or None, words=False)
            except TranscribeError as e:
                return self.send_json(e.code if e.code in (400, 503) else 500, {"error": str(e), "hint": "pip install faster-whisper numpy"})
            r["elapsed_s"] = round(time.time() - t0, 3)
            self.send_json(200, r)

        def _tts(self):
            b = self.json_body()
            text = str(b.get("text") or "")
            lang = b.get("lang") or "auto"
            if lang == "auto":
                lang = detect_lang(text, "ru")
            fmt = b.get("format", "pcm")
            if fmt not in ("pcm", "sse"):
                return self.send_json(400, {"error": "format must be pcm or sse"})
            speed = mood_speed(b.get("mood")) if b.get("speed") is None else max(0.7, min(1.4, float(b["speed"])))
            phrases = svc.phrases(text, lang)
            if not phrases:
                return self.send_json(400, {"error": "nothing to speak after cleaning"})
            job = svc.start_job(b.get("sid"))
            q = queue.Queue(maxsize=2)

            def producer():
                try:
                    for i, ph in enumerate(phrases):
                        if job.cancel.is_set():
                            break
                        try:
                            pcm, backend = svc.synth_phrase(ph, lang, speed, b.get("voice"))
                        except BackendError as e:
                            q.put(("error", i, ph, e))
                            return
                        q.put(("audio", i, ph, (pcm, backend)))
                finally:
                    q.put(("end", 0, "", None))

            threading.Thread(target=producer, daemon=True).start()
            try:
                kind, i, ph, val = q.get()
                if kind == "error":                          # до первого байта - честный HTTP-статус
                    job.cancel.set()
                    return self.send_json(503, tts_error_payload(val))
                if kind == "end":
                    return self.send_json(499 if job.cancel.is_set() else 500, {"error": "cancelled" if job.cancel.is_set() else "no audio"})
                hdr = {"X-Voice-Id": job.id, "X-Sample-Rate": str(OUT_RATE), "X-Voice-Speed": str(speed)}
                self.start_chunked("text/event-stream" if fmt == "sse" else "audio/L16;rate=%d" % OUT_RATE, hdr)
                end = "end"
                while True:
                    if kind == "audio" and not job.cancel.is_set():
                        pcm, backend = val
                        if fmt == "sse":
                            ev = {"type": "audio", "seq": i, "text": ph, "backend": backend, "sample_rate": OUT_RATE,
                                  "pcm_b64": base64.b64encode(pcm).decode("ascii")}
                            self.write_chunk(("data: %s\n\n" % json.dumps(ev)).encode("utf-8"))
                        else:
                            step = OUT_RATE * 2 // 10            # кадры по 100 мс: отмена срабатывает быстро
                            for k in range(0, len(pcm), step):
                                if job.cancel.is_set():
                                    break
                                self.write_chunk(pcm[k:k + step])
                    elif kind == "error":
                        if fmt == "sse":
                            self.write_chunk(("data: %s\n\n" % json.dumps(dict(tts_error_payload(val), type="error"))).encode("utf-8"))
                        end = "error"
                        break
                    elif kind == "end":
                        break
                    if job.cancel.is_set():
                        end = "cancelled"
                        break
                    kind, i, ph, val = q.get()
                if fmt == "sse":
                    self.write_chunk(("data: %s\n\n" % json.dumps({"type": "cancelled" if job.cancel.is_set() else "end"})).encode("utf-8"))
                self.end_chunked()
            except (BrokenPipeError, ConnectionResetError):
                job.cancel.set()                              # клиент ушёл = отмена
            finally:
                job.cancel.set()
                svc.end_job(job)
    return H


def main():
    host, port = env("NOX_VOICE_HOST", "127.0.0.1"), env_int("NOX_VOICE_PORT", 8095)
    svc = VoiceService()
    srv = common.serve(make_handler(svc), host, port)
    h = svc.health()
    print("[nox-voice] %s:%d tts=%s stt_ready=%s" % (host, port, {k: v["ready"] for k, v in h["tts"].items()}, h["stt"]["ready"]), flush=True)
    for lang, v in h["tts"].items():
        for b in v["backends"]:
            if not b["available"]:
                print("[nox-voice] %s/%s недоступен: %s" % (lang, b["name"], b["reason"]), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
