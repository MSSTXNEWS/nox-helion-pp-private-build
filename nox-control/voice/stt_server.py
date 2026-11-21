"""NOX STT: HTTP-сервис распознавания речи на faster-whisper (RU/ES) + конец реплики через community/smart_turn.

Эндпоинты:
  GET  /health                          честный статус зависимостей/модели/smart_turn
  POST /transcribe?language=ru&words=1&format=auto   тело = WAV | raw PCM16 16 кГц | webm/opus/... (если есть ffmpeg)
  POST /stream/start        {language?, partial?, words?}  -> {id}
  POST /stream/<id>/chunk   тело = PCM16 16 кГц mono (или WAV) -> {events:[...], state:{...}}
  GET  /stream/<id>/events?after=N      накопленные события (id > N)
  POST /stream/<id>/finish  принудительно финализировать фразу (+ end_of_turn)
  POST /stream/<id>/close
События: speech_start, partial, final, end_of_turn.  Порядок при конце реплики: final, затем end_of_turn.
"""
import os
import sys
import threading
import time
import urllib.parse
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from voice import common  # noqa: E402
from voice.common import env, env_bool, env_float, env_int, SR  # noqa: E402

try:
    from community import smart_turn  # noqa: E402
except Exception as _e:  # pragma: no cover
    smart_turn = None
    _SMART_ERR = str(_e)
else:
    _SMART_ERR = None


# ---------------- конфиг ----------------
class TurnConfig:
    """Пороги конца реплики. Все из env (NOX_TURN_*), можно переопределить в /stream/start {"turn": {...}}."""

    def __init__(self, **kw):
        self.base_pause = env_float("NOX_TURN_BASE_PAUSE", 0.6)        # базовая пауза, с (эвристика)
        self.min_speech = env_float("NOX_TURN_MIN_SPEECH", 0.15)       # минимум речи, с
        self.min_trailing = env_float("NOX_TURN_MIN_TRAILING", 0.3)    # жёсткий минимум тишины после речи, с (для любого бэкенда)
        self.onnx_threshold = env_float("NOX_TURN_ONNX_THRESHOLD", 0.5)
        self.max_utterance = env_float("NOX_TURN_MAX_UTTERANCE", 30.0) # принудительный конец, с
        self.window = env_float("NOX_TURN_WINDOW", 8.0)                # хвост для анализа, с
        self.partial_interval = env_float("NOX_STT_PARTIAL_INTERVAL", 1.5)  # период частичных, с (0 = выключить)
        self.speech_start_ms = env_int("NOX_TURN_SPEECH_START_MS", 250)    # речи для события speech_start
        self.pre_roll = env_float("NOX_TURN_PRE_ROLL", 0.5)            # сколько тишины держать до начала речи, с
        for k, v in kw.items():
            if hasattr(self, k):
                setattr(self, k, type(getattr(self, k))(v))

    def as_dict(self):
        return dict(self.__dict__)


def analyze_turn(pcm, cfg):
    """Обёртка над smart_turn: ONNX если загружен, иначе эвристика с порогами из cfg."""
    if smart_turn is None:
        return {"backend": "none", "complete": False, "speech": False, "trailing_silence": 0.0, "speech_ms": 0}
    tail = bytes(pcm[-int(cfg.window * SR) * 2:])
    if smart_turn.backend() == "onnx":
        r = smart_turn.analyze(tail, cfg.onnx_threshold)
    else:
        r = smart_turn.heuristic_analyze(tail, cfg.base_pause, cfg.min_speech)
    r = dict(r)
    if r.get("complete") and r.get("trailing_silence", 0) < cfg.min_trailing:
        r["complete"] = False
    return r


# ---------------- транскрайбер ----------------
class TranscribeError(Exception):
    def __init__(self, msg, code=500):
        Exception.__init__(self, msg)
        self.code = code


class FasterWhisperTranscriber:
    """Ленивая загрузка faster-whisper. Параметры из env: NOX_STT_MODEL (small), NOX_STT_DEVICE (cpu), NOX_STT_COMPUTE (int8),
    NOX_STT_THREADS (8), NOX_STT_MODEL_DIR (кэш), NOX_STT_BEAM (1), NOX_STT_LANGS (ru,es)."""

    def __init__(self):
        self.name = env("NOX_STT_MODEL", "small")
        self.device = env("NOX_STT_DEVICE", "cpu")
        self.compute = env("NOX_STT_COMPUTE", "int8")
        self.threads = env_int("NOX_STT_THREADS", 8)
        self.model_dir = env("NOX_STT_MODEL_DIR")
        self.beam = env_int("NOX_STT_BEAM", 1)
        self.langs = [x.strip() for x in env("NOX_STT_LANGS", "ru,es").split(",") if x.strip()]
        self.model = None
        self.error = None
        self._load_lock = threading.Lock()
        self._np = None

    def deps(self):
        return {"faster_whisper": common.have_module("faster_whisper"), "numpy": common.have_module("numpy"),
                "ctranslate2": common.have_module("ctranslate2")}

    def available(self):
        d = self.deps()
        return d["faster_whisper"] and d["numpy"]

    def info(self):
        return {"name": self.name, "device": self.device, "compute_type": self.compute, "threads": self.threads,
                "languages": self.langs, "loaded": self.model is not None, "error": self.error}

    def _load(self):
        with self._load_lock:
            if self.model is not None:
                return
            if not self.available():
                missing = [k for k, v in self.deps().items() if not v and k != "ctranslate2"]
                raise TranscribeError("dependencies missing: %s (run voice/install_deps.sh)" % ", ".join(missing), 503)
            try:
                import numpy as np
                from faster_whisper import WhisperModel
                kw = dict(device=self.device, compute_type=self.compute, cpu_threads=self.threads)
                if self.model_dir:
                    kw["download_root"] = self.model_dir
                self.model = WhisperModel(self.name, **kw)
                self._np = np
                self.error = None
            except Exception as e:
                self.error = "%s: %s" % (type(e).__name__, e)
                raise TranscribeError("model load failed: %s" % self.error, 503)

    def preload(self):
        self._load()

    def _detect(self, audio):
        """Язык только из разрешённых (ru/es). Нет detect_language -> None (пусть решает whisper)."""
        try:
            _lang, _p, allp = self.model.detect_language(audio)
            probs = dict(allp) if allp else {}
            cands = [(probs.get(l, 0.0), l) for l in self.langs]
            if cands and max(cands)[0] > 0:
                p, l = max(cands)
                return l, float(p)
        except Exception:
            pass
        return None, None

    def transcribe(self, pcm, language=None, words=True, prompt=None):
        self._load()
        np = self._np
        audio = np.frombuffer(bytes(pcm[: len(pcm) - len(pcm) % 2]), dtype=np.int16).astype(np.float32) / 32768.0
        dur = len(audio) / float(SR)
        if dur < 0.1:
            return {"language": language, "language_probability": None, "text": "", "segments": [], "duration": round(dur, 3)}
        lang_p = None
        if not language:
            language, lang_p = self._detect(audio)
        try:
            segs, info = self.model.transcribe(audio, language=language, beam_size=self.beam, word_timestamps=bool(words),
                                               vad_filter=False, condition_on_previous_text=False, initial_prompt=prompt)
            out = []
            for s in segs:
                item = {"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip()}
                if words and getattr(s, "words", None):
                    item["words"] = [{"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3),
                                      "probability": round(float(w.probability), 3)} for w in s.words]
                out.append(item)
        except TranscribeError:
            raise
        except Exception as e:
            raise TranscribeError("transcribe failed: %s: %s" % (type(e).__name__, e))
        lp = lang_p if lang_p is not None else getattr(info, "language_probability", None)
        return {"language": getattr(info, "language", language) or language,
                "language_probability": round(float(lp), 3) if lp is not None else None,
                "text": " ".join(x["text"] for x in out).strip(), "segments": out, "duration": round(dur, 3)}


# ---------------- потоковая сессия ----------------
class StreamSession:
    def __init__(self, svc, language=None, words=True, partial=None, turn=None):
        self.svc = svc
        self.id = uuid.uuid4().hex[:12]
        self.language = language or None
        self.words = words
        self.cfg = TurnConfig(**(turn or {}))
        if partial is not None:
            self.cfg.partial_interval = float(partial)
        self.lock = threading.Lock()
        self.utt = bytearray()        # текущая реплика (с pre-roll)
        self.total = 0                # всего принято байт
        self.events = []
        self.next_id = 1
        self.speaking = False
        self.speech_started = False
        self.last_partial_at = 0.0
        self.last_partial_text = ""
        self.last_active = time.time()
        self.turns = 0
        self.closed = False

    def _ev(self, typ, **kw):
        e = {"id": self.next_id, "type": typ, "t": round(self.total / 2.0 / SR, 3)}
        e.update(kw)
        self.next_id += 1
        self.events.append(e)
        if len(self.events) > 500:
            del self.events[:100]
        return e

    def state(self):
        return {"speaking": self.speaking, "buffered_s": round(len(self.utt) / 2.0 / SR, 2), "turns": self.turns,
                "received_s": round(self.total / 2.0 / SR, 2)}

    def _trim_pre_roll(self):
        keep = int(self.cfg.pre_roll * SR) * 2
        if len(self.utt) > keep:
            del self.utt[: len(self.utt) - keep]

    def feed(self, pcm):
        with self.lock:
            self.last_active = time.time()
            if len(pcm) % 2:
                pcm = pcm[:-1]
            self.utt += pcm
            self.total += len(pcm)
            new = []
            a = analyze_turn(self.utt, self.cfg)
            self.speaking = bool(a.get("speech")) and a.get("trailing_silence", 0) < 0.25
            if not a.get("speech"):
                self._trim_pre_roll()
                self.speech_started = False
                return new, a
            if not self.speech_started and a.get("speech_ms", 0) >= self.cfg.speech_start_ms:
                self.speech_started = True
                self.last_partial_at = time.time()
                new.append(self._ev("speech_start", speech_ms=a.get("speech_ms")))
            dur = len(self.utt) / 2.0 / SR
            if a.get("complete"):
                new += self._finalize("smart_turn", a)
            elif dur >= self.cfg.max_utterance:
                new += self._finalize("max_len", a)
            elif (self.cfg.partial_interval > 0 and self.speech_started and self.speaking
                  and time.time() - self.last_partial_at >= self.cfg.partial_interval):
                p = self._partial()
                if p:
                    new.append(p)
            return new, a

    def _partial(self):
        self.last_partial_at = time.time()
        if not self.svc.tr_lock.acquire(blocking=False):
            return None                     # занято (идёт финал/другая сессия) - частичные не копим
        try:
            r = self.svc.tr.transcribe(bytes(self.utt), self.language, words=False)
        except Exception as e:
            return self._ev("warning", message=str(e)[:200])
        finally:
            self.svc.tr_lock.release()
        txt = r.get("text", "")
        if not txt or txt == self.last_partial_text:
            return None
        self.last_partial_text = txt
        return self._ev("partial", text=txt, language=r.get("language"))

    def _finalize(self, reason, analysis):
        new = []
        pcm = bytes(self.utt)
        self.utt.clear()
        self.speech_started = False
        self.speaking = False
        self.last_partial_text = ""
        try:
            with self.svc.tr_lock:
                r = self.svc.tr.transcribe(pcm, self.language, words=self.words)
            new.append(self._ev("final", text=r.get("text", ""), language=r.get("language"),
                                language_probability=r.get("language_probability"), segments=r.get("segments", []),
                                duration=r.get("duration")))
        except Exception as e:
            new.append(self._ev("error", message=str(e)[:300]))
        self.turns += 1
        new.append(self._ev("end_of_turn", reason=reason, turn={k: analysis.get(k) for k in (
            "backend", "confidence", "trailing_silence", "required_silence", "speech_ms")}))
        return new

    def finish(self):
        with self.lock:
            a = analyze_turn(self.utt, self.cfg)
            if not a.get("speech"):
                self.utt.clear()
                return [self._ev("end_of_turn", reason="finish_no_speech", turn={"backend": a.get("backend")})]
            return self._finalize("finish", a)

    def events_after(self, after):
        with self.lock:
            return [e for e in self.events if e["id"] > after]


class SttService:
    def __init__(self, transcriber=None):
        self.tr = transcriber or FasterWhisperTranscriber()
        self.tr_lock = threading.Lock()
        self.sessions = {}
        self.slock = threading.Lock()
        self.ttl = env_float("NOX_STT_SESSION_TTL", 600)
        self.turn_model_loaded = False
        mp = env("NOX_SMART_TURN_MODEL")
        if mp and smart_turn is not None:
            self.turn_model_loaded = smart_turn.load_onnx(mp)

    def health(self):
        d = self.tr.deps() if hasattr(self.tr, "deps") else {}
        d["ffmpeg"] = bool(common.ffmpeg_path())
        d["onnxruntime"] = common.have_module("onnxruntime")
        ready = bool(self.tr.available()) if hasattr(self.tr, "available") else True
        st = {"backend": smart_turn.backend() if smart_turn else "none",
              "onnx_error": (smart_turn.onnx_error() if smart_turn else _SMART_ERR),
              "config": TurnConfig().as_dict()}
        return {"ok": True, "service": "nox-stt", "ready": ready,
                "ready_note": None if ready else "faster-whisper/numpy not installed: /transcribe and /stream return 503",
                "deps": d, "model": self.tr.info() if hasattr(self.tr, "info") else {}, "smart_turn": st,
                "sessions": len(self.sessions)}

    def _gc(self):
        now = time.time()
        with self.slock:
            for k in [k for k, s in self.sessions.items() if now - s.last_active > self.ttl]:
                self.sessions.pop(k, None)

    def new_session(self, **kw):
        self._gc()
        s = StreamSession(self, **kw)
        with self.slock:
            self.sessions[s.id] = s
        return s

    def get(self, sid):
        with self.slock:
            return self.sessions.get(sid)


def make_handler(svc):
    class H(common.JsonHandler):
        def _err(self, code, msg):
            self.send_json(code, {"error": msg})

        def _qs(self):
            u = urllib.parse.urlparse(self.path)
            return u.path.rstrip("/") or "/", {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}

        def do_GET(self):
            path, q = self._qs()
            if path == "/health":
                return self.send_json(200, svc.health())
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "stream" and parts[2] == "events":
                s = svc.get(parts[1])
                if not s:
                    return self._err(404, "no such session")
                return self.send_json(200, {"events": s.events_after(int(q.get("after", 0) or 0)), "state": s.state()})
            self._err(404, "not found")

        def do_POST(self):
            path, q = self._qs()
            try:
                if path == "/transcribe":
                    return self._transcribe(q)
                if path == "/stream/start":
                    o = self.json_body()
                    s = svc.new_session(language=o.get("language") or None, words=bool(o.get("words", True)),
                                        partial=o.get("partial"), turn=o.get("turn"))
                    return self.send_json(200, {"id": s.id, "turn_config": s.cfg.as_dict(),
                                                "audio": "PCM16 LE 16000 Hz mono (or WAV chunks)"})
                parts = path.strip("/").split("/")
                if len(parts) == 3 and parts[0] == "stream":
                    s = svc.get(parts[1])
                    if not s:
                        self.read_body()
                        return self._err(404, "no such session")
                    if parts[2] == "chunk":
                        data = self.read_body()
                        pcm = common.decode_audio(data, self.headers.get("Content-Type", ""),
                                                  "wav" if data[:4] == b"RIFF" else "pcm16")
                        ev, a = s.feed(pcm)
                        return self.send_json(200, {"events": ev, "state": s.state(),
                                                    "turn": {k: a.get(k) for k in ("backend", "complete", "trailing_silence", "required_silence", "speech_ms")}})
                    if parts[2] == "finish":
                        self.read_body()
                        return self.send_json(200, {"events": s.finish(), "state": s.state()})
                    if parts[2] == "close":
                        self.read_body()
                        with svc.slock:
                            svc.sessions.pop(s.id, None)
                        return self.send_json(200, {"closed": True})
                self.read_body()
                self._err(404, "not found")
            except common.AudioError as e:
                self._err(400, str(e))
            except TranscribeError as e:
                self._err(e.code, str(e))
            except ValueError as e:
                self._err(400, str(e))
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                self._err(500, "%s: %s" % (type(e).__name__, e))

        def _transcribe(self, q):
            data = self.read_body()
            pcm = common.decode_audio(data, self.headers.get("Content-Type", ""), q.get("format", "auto"))
            words = q.get("words", "1") not in ("0", "false", "no")
            t0 = time.time()
            with svc.tr_lock:
                r = svc.tr.transcribe(pcm, q.get("language") or None, words=words, prompt=q.get("prompt"))
            r["elapsed_s"] = round(time.time() - t0, 3)
            self.send_json(200, r)
    return H


def main():
    host = env("NOX_STT_HOST", "127.0.0.1")
    port = env_int("NOX_STT_PORT", 8093)
    svc = SttService()
    srv = common.serve(make_handler(svc), host, port)
    h = svc.health()
    print("[nox-stt] %s:%d ready=%s model=%s device=%s compute=%s smart_turn=%s" % (
        host, port, h["ready"], svc.tr.name, svc.tr.device, svc.tr.compute, h["smart_turn"]["backend"]), flush=True)
    if not h["ready"]:
        print("[nox-stt] WARNING: %s" % h["ready_note"], flush=True)
    elif env_bool("NOX_STT_PRELOAD", True):
        threading.Thread(target=lambda: _preload(svc), daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def _preload(svc):
    try:
        svc.tr.preload()
        print("[nox-stt] model loaded", flush=True)
    except Exception as e:
        print("[nox-stt] preload failed: %s" % e, flush=True)


if __name__ == "__main__":
    main()
