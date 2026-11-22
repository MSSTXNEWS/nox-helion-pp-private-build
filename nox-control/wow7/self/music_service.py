"""SELF-09: серверная часть генерации музыки на ПК/S2 (НЕ на S1: GPU и RAM нужны там). Мини-сервис для клиента soundscape.js (fetchGenerated):
  POST /gen {prompt, seconds[5..30], model?:"musicgen-small"|"stable-audio-open", seed?, loop?:true} -> audio/wav (ответ ждёт окончания; очередь 1 воркер)
  GET /health | /status | /receipt/<id> ; POST /unload ; POST /cancel/<id> ; OPTIONS (CORS для браузера).
Принцип как у IMG: состояния модели COLD (на диске) -> WARM (веса в RAM процесса) -> GPU (только на время генерации) -> WARM; незанятая модель выгружается из RAM по таймеру.
Окно VRAM: Gate.acquire ждёт, пока свободно >= need + запас (игра/чат на том же ПК), иначе 503 vram_unavailable; RAM перед загрузкой проверяется (mem_min).
Запуск «только по запросу»: сервис ничего не генерирует сам. Лицензии: MusicGen-small - веса CC-BY-NC 4.0 (только личное некоммерческое использование),
Stable Audio Open 1.0 - Stability AI Community License (гейтованный репозиторий, нужен HF-токен; проверить условия). Лицензия попадает в ответ (X-NOX-License) и квитанцию.
Квитанция MUSIC-JOB-<id>.json с SHA-256 wav и цепочкой (MUSIC-LEDGER.jsonl). Луп: хвост кроссфейдом смешивается с началом (бесшовное зацикливание в soundscape).
env: NOX_MUSIC_HOST(127.0.0.1) NOX_MUSIC_PORT(8098) NOX_MUSIC_MODEL_DIR NOX_MUSIC_STATE NOX_RECEIPTS_DIR NOX_MUSIC_TOKEN NOX_MUSIC_ORIGIN(*) NOX_MUSIC_QUEUE_MAX(4)
NOX_MUSIC_GEN_TIMEOUT_S(600) NOX_MUSIC_VRAM_WAIT_S(60) NOX_MUSIC_RAM_IDLE_EVICT_S(900) NOX_MEM_MIN_GB(8) NOX_MUSIC_DEFAULT_MODEL.   Запуск: python3 music_service.py [--fake]
"""
import array, hashlib, io, json, math, os, queue, random, re, struct, subprocess, sys, threading, time, uuid, wave
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

E = os.environ.get
HOME = E("NOX_HOME", "/root/nox")

MODELS = {   # need_mb / ram_gb - гипотезы по размеру весов (fp32 MusicGen-small ~2,4 ГБ; Stable Audio Open ~5 ГБ в fp16), мерить на ПК
    "musicgen-small": {"repo": "facebook/musicgen-small", "dir": "musicgen-small", "license": "CC-BY-NC-4.0 (weights; personal non-commercial use)", "rate": 32000, "channels": 1,
                       "max_s": 30, "need_mb": 3500, "ram_gb": 4},
    "stable-audio-open": {"repo": "stabilityai/stable-audio-open-1.0", "dir": "stable-audio-open-1.0", "license": "Stability AI Community License (gated; verify terms)", "rate": 44100,
                          "channels": 2, "max_s": 47, "need_mb": 8000, "ram_gb": 8},
}
MIN_S, MAX_PROMPT = 5, 600


class Cancelled(Exception):
    pass


class EngineError(Exception):
    pass


class VramUnavailable(Exception):
    pass


# ------------------------------------------------------------------ WAV
def encode_wav(pcm16, rate, channels):
    """pcm16: bytes little-endian int16 interleaved."""
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm16)
    return b.getvalue()


def make_loop(pcm16, rate, channels, xfade_s=1.0):
    """Бесшовный луп: последние xfade секунд эквимощностно смешиваются с первыми и отрезаются; длина уменьшается на xfade."""
    a = array.array("h")
    a.frombytes(pcm16)
    if sys.byteorder == "big":
        a.byteswap()
    n = len(a) // channels
    x = min(int(xfade_s * rate), n // 3)
    if x < 2:
        return pcm16
    out = array.array("h", a[: (n - x) * channels])
    for i in range(x):
        t = i / (x - 1)
        g_in, g_out = math.sin(t * math.pi / 2), math.cos(t * math.pi / 2)
        for c in range(channels):
            tail = a[(n - x + i) * channels + c]
            head = a[i * channels + c]
            v = int(head * g_in + tail * g_out)
            out[i * channels + c] = max(-32768, min(32767, v))
    if sys.byteorder == "big":
        out.byteswap()
    return out.tobytes()


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def mem_available_gb():
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable"):
                return int(line.split()[1]) / 1048576
    except OSError:
        pass
    return None


def gpu_free_mb():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        return int(out.stdout.strip().splitlines()[0]) if out.returncode == 0 and out.stdout.strip() else None
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


# ------------------------------------------------------------------ окно VRAM
class Gate:
    def __init__(self, free_mb=gpu_free_mb, wait_s=None, margin_mb=512, sleep=time.sleep, clock=time.time):
        self.free_mb, self.margin, self.sleep, self.clock = free_mb, margin_mb, sleep, clock
        self.wait_s = float(E("NOX_MUSIC_VRAM_WAIT_S", "60")) if wait_s is None else wait_s

    def acquire(self, need_mb, cancel=None):
        """-> {'free_mb','waited_s'}. free=None (нет nvidia-smi): GPU не виден, не блокируем (движок сам упадёт на CPU или в ошибку)."""
        t0 = self.clock()
        while True:
            free = self.free_mb()
            if free is None or free - self.margin >= need_mb:
                return {"free_mb": free, "waited_s": round(self.clock() - t0, 2)}
            if (cancel is not None and cancel.is_set()):
                raise Cancelled()
            if self.clock() - t0 >= self.wait_s:
                raise VramUnavailable("свободно %s МБ, нужно %d + запас %d" % (free, need_mb, self.margin))
            self.sleep(1.0)


# ------------------------------------------------------------------ движки
class FakeEngine:
    """Без GPU/torch: детерминированный «пэд» из синусов (по seed и тексту). Для тестов и дымового запуска (--fake)."""
    def __init__(self, warm_s=0.0, step_s=0.0):
        self.where, self.log, self.warm_s, self.step_s, self.fail_next = {}, [], warm_s, step_s, None

    def installed(self, key):
        return True

    def loaded(self):
        return dict(self.where)

    def warm(self, key):
        self.log.append(("warm", key))
        time.sleep(self.warm_s)
        self.where[key] = "ram"

    def to_gpu(self, key):
        self.log.append(("to_gpu", key))
        self.where[key] = "gpu"

    def run(self, key, p, cancel, progress):
        self.log.append(("run", key, p["seed"], p["seconds"]))
        if self.fail_next:
            e, self.fail_next = self.fail_next, None
            raise EngineError(e)
        spec = MODELS[key]
        rate, ch = min(spec["rate"], 8000), spec["channels"]      # маленькая частота: тесты быстрые
        n = int(rate * p["seconds"])
        rnd = random.Random(p["seed"])
        f = [110 * 2 ** (rnd.choice([0, 3, 5, 7, 10]) / 12.0) for _ in range(3)]
        pcm = array.array("h")
        for i in range(n):
            if i % rate == 0:
                if cancel.is_set():
                    raise Cancelled()
                time.sleep(self.step_s)
                progress(i // rate + 1, p["seconds"])
            v = sum(math.sin(2 * math.pi * fr * i / rate) for fr in f) / 3.0
            s = int(v * 9000)
            for _ in range(ch):
                pcm.append(s)
        return {"pcm": pcm.tobytes() if sys.byteorder == "little" else (pcm.byteswap() or pcm.tobytes()), "rate": rate, "channels": ch}

    def to_ram(self, key):
        self.log.append(("to_ram", key))
        if key in self.where:
            self.where[key] = "ram"

    def drop(self, key):
        self.log.append(("drop", key))
        self.where.pop(key, None)


def tensor_to_pcm16(t):
    """torch.Tensor (channels, n) float [-1,1] -> bytes int16 interleaved. Только методы torch (подменяемо в тестах)."""
    t = t.detach().cpu().float().clamp(-1.0, 1.0).mul(32767.0).short()
    if t.dim() == 1:
        return t.numpy().tobytes()
    return t.t().contiguous().numpy().tobytes()


class TorchEngine:
    """MusicGen (transformers) и Stable Audio Open (diffusers). Веса в RAM (CPU), на GPU только на время генерации.
    torch/transformers/diffusers передаются в конструктор для тестов; по умолчанию импортируются лениво."""
    def __init__(self, model_dir, torch=None, transformers=None, diffusers=None):
        self.model_dir, self._torch, self._tf, self._df = model_dir, torch, transformers, diffusers
        self.m, self.aux, self.where = {}, {}, {}

    def _libs(self):
        try:
            if self._torch is None:
                import torch
                self._torch = torch
            if self._tf is None:
                import transformers
                self._tf = transformers
            if self._df is None:
                try:
                    import diffusers
                    self._df = diffusers
                except Exception:
                    self._df = False
        except Exception as e:
            raise EngineError("torch/transformers не установлены: %s" % e)
        return self._torch, self._tf, self._df

    def installed(self, key):
        d = os.path.join(self.model_dir, MODELS[key]["dir"])
        return os.path.isfile(os.path.join(d, "config.json")) or os.path.isfile(os.path.join(d, "model_index.json"))

    def loaded(self):
        return dict(self.where)

    def warm(self, key):
        torch, tf, df = self._libs()
        if not self.installed(key):
            raise EngineError("веса %s не установлены в %s (install_music_pc.sh)" % (key, self.model_dir))
        path = os.path.join(self.model_dir, MODELS[key]["dir"])
        if key == "musicgen-small":
            self.aux[key] = tf.AutoProcessor.from_pretrained(path)
            self.m[key] = tf.MusicgenForConditionalGeneration.from_pretrained(path, torch_dtype=torch.float32)
        else:
            if not df:
                raise EngineError("diffusers не установлен (Stable Audio Open)")
            self.m[key] = df.StableAudioPipeline.from_pretrained(path, torch_dtype=torch.float16)
        self.where[key] = "ram"

    def to_gpu(self, key):
        torch = self._libs()[0]
        self.m[key].to("cuda")
        self.where[key] = "gpu"

    def run(self, key, p, cancel, progress):
        torch = self._libs()[0]
        spec, mdl = MODELS[key], self.m[key]
        gen = torch.Generator("cpu").manual_seed(p["seed"])
        try:
            with torch.no_grad():
                if key == "musicgen-small":
                    inp = self.aux[key](text=[p["prompt"]], padding=True, return_tensors="pt")
                    inp = {k: v.to("cuda") for k, v in inp.items()}
                    torch.manual_seed(p["seed"])
                    out = mdl.generate(**inp, do_sample=True, guidance_scale=3.0, max_new_tokens=int(p["seconds"] * 50))   # 50 кадров/с кодека EnCodec
                    audio, rate = out[0], mdl.config.audio_encoder.sampling_rate
                else:
                    out = mdl(prompt=p["prompt"], negative_prompt="low quality, vocals, speech", audio_end_in_s=float(p["seconds"]), num_inference_steps=p["steps"], generator=gen,
                              num_waveforms_per_prompt=1)
                    audio, rate = out.audios[0], mdl.vae.sampling_rate
        finally:
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
        if cancel.is_set():
            raise Cancelled()
        pcm = tensor_to_pcm16(audio)
        ch = spec["channels"] if audio.dim() > 1 and audio.shape[0] > 1 else 1
        return {"pcm": pcm, "rate": int(rate), "channels": ch}

    def to_ram(self, key):
        torch = self._libs()[0]
        if self.where.get(key) == "gpu":
            self.m[key].to("cpu")
            self.where[key] = "ram"
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass

    def drop(self, key):
        self.m.pop(key, None)
        self.aux.pop(key, None)
        self.where.pop(key, None)
        import gc
        gc.collect()
        try:
            self._libs()[0].cuda.empty_cache()
        except Exception:
            pass


# ------------------------------------------------------------------ сервис
class Job:
    def __init__(self, p):
        self.id, self.p, self.state, self.created = uuid.uuid4().hex[:12], p, "queued", time.time()
        self.step, self.steps, self.error, self.result = 0, p["seconds"], None, None
        self.cancel, self.done, self.timings = threading.Event(), threading.Event(), {}

    def info(self):
        return {"id": self.id, "state": self.state, "step": self.step, "steps": self.steps, "error": self.error, "model": self.p["model"], "timings": self.timings}


class Service:
    def __init__(self, engine, gate=None, state_dir=None, receipts_dir=None, queue_max=None, gen_timeout_s=None, ram_idle_evict_s=None, mem_min_gb=None,
                 mem_avail=mem_available_gb, clock=time.time, default_model=None):
        self.engine, self.gate, self.clock, self.mem_avail = engine, gate or Gate(), clock, mem_avail
        self.state_dir = state_dir or E("NOX_MUSIC_STATE", os.path.join(HOME, "state", "music"))
        self.out_dir = os.path.join(self.state_dir, "out")
        self.receipts_dir = receipts_dir or E("NOX_RECEIPTS_DIR", os.path.join(HOME, "receipts"))
        self.queue_max = int(E("NOX_MUSIC_QUEUE_MAX", "4")) if queue_max is None else queue_max
        self.gen_timeout = float(E("NOX_MUSIC_GEN_TIMEOUT_S", "600")) if gen_timeout_s is None else gen_timeout_s
        self.evict_s = float(E("NOX_MUSIC_RAM_IDLE_EVICT_S", "900")) if ram_idle_evict_s is None else ram_idle_evict_s
        self.mem_min = float(E("NOX_MEM_MIN_GB", "8")) if mem_min_gb is None else mem_min_gb
        self.default_model = default_model or E("NOX_MUSIC_DEFAULT_MODEL", "musicgen-small")
        self.jobs, self.q, self.lock = {}, queue.Queue(), threading.Lock()
        self.current, self.last_used, self._stop = None, clock(), threading.Event()
        self.counters = {"done": 0, "error": 0, "cancelled": 0, "timeout": 0}
        os.makedirs(self.out_dir, exist_ok=True)
        os.makedirs(self.receipts_dir, exist_ok=True)
        threading.Thread(target=self._run, daemon=True, name="music-worker").start()
        threading.Thread(target=self._evictor, daemon=True, name="music-evict").start()

    def submit(self, body):
        if not isinstance(body, dict):
            return 400, {"error": "bad_request", "message": "тело должно быть JSON-объектом"}
        try:
            prompt = re.sub(r"[\x00-\x1f]+", " ", str(body.get("prompt") or "")).strip()
            if not prompt:
                raise ValueError("нужен prompt")
            if len(prompt) > MAX_PROMPT:
                raise ValueError("prompt длиннее %d символов" % MAX_PROMPT)
            key = body.get("model") or self.default_model
            if key not in MODELS:
                raise ValueError("неизвестная модель %r; доступны: %s" % (key, ", ".join(MODELS)))
            spec = MODELS[key]
            seconds = int(body.get("seconds", 20))
            if not MIN_S <= seconds <= spec["max_s"]:
                raise ValueError("seconds: %d..%d для %s" % (MIN_S, spec["max_s"], key))
            seed = int(body["seed"]) if body.get("seed") is not None else random.randrange(2 ** 31)
            steps = int(body.get("steps", 100))
            if not 10 <= steps <= 200:
                raise ValueError("steps: 10..200")
        except (ValueError, TypeError) as e:
            return 400, {"error": "bad_request", "message": str(e)}
        if "vocal" not in prompt.lower():
            prompt += ", instrumental, no vocals"
        if not self.engine.installed(key):
            return 503, {"error": "weights_not_installed", "model": key, "message": "веса %s не установлены (install_music_pc.sh)" % spec["repo"]}
        p = {"model": key, "prompt": prompt, "seconds": seconds, "seed": seed, "steps": steps, "loop": body.get("loop", True) is not False}
        with self.lock:
            waiting = sum(1 for j in self.jobs.values() if j.state == "queued")
            if waiting >= self.queue_max:
                return 429, {"error": "queue_full", "message": "очередь полна (%d)" % self.queue_max}
            job = Job(p)
            self.jobs[job.id] = job
            self.q.put(job)
            for j in sorted((j for j in self.jobs.values() if j.done.is_set()), key=lambda j: j.created)[:-20]:
                self.jobs.pop(j.id, None)
        return 202, {"id": job.id, "state": job.state, "model": key}

    def cancel(self, jid):
        j = self.jobs.get(jid)
        if not j:
            return 404, {"error": "not_found"}
        if j.done.is_set():
            return 409, {"error": "already_finished", "state": j.state}
        j.cancel.set()
        if j.state == "queued":
            self._finish(j, "cancelled")
        return 200, {"id": j.id, "state": j.state if j.state == "cancelled" else "cancelling"}

    def _finish(self, job, state, error=None, result=None):
        job.state, job.error, job.result = state, error, result
        if state in self.counters:
            self.counters[state] += 1
        job.done.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                job = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            if job.done.is_set():
                continue
            self.current = job
            try:
                self._process(job)
            except Cancelled:
                self._finish(job, "cancelled")
            except VramUnavailable as e:
                self._finish(job, "error", "vram_unavailable: %s" % e)
            except Exception as e:
                self._finish(job, "error", "%s: %s" % (type(e).__name__, e))
            finally:
                self.current, self.last_used = None, self.clock()

    def _process(self, job):
        p, t, key = job.p, job.timings, job.p["model"]
        if key not in self.engine.loaded():
            job.state, t0 = "warming", self.clock()
            avail = self.mem_avail()
            if avail is not None and avail - MODELS[key]["ram_gb"] < self.mem_min:
                raise EngineError("ram_low: доступно %.1f ГБ, нужно %d + запас %.0f" % (avail, MODELS[key]["ram_gb"], self.mem_min))
            self.engine.warm(key)
            t["warm_s"] = round(self.clock() - t0, 2)
        job.state, t0 = "waiting_vram", self.clock()
        win = self.gate.acquire(MODELS[key]["need_mb"], job.cancel)
        t["vram_wait_s"] = win["waited_s"]
        timer = threading.Timer(self.gen_timeout, lambda: (job.cancel.set(), t.__setitem__("timed_out", True)))
        timer.daemon = True
        try:
            job.state, t0 = "generating", self.clock()
            timer.start()
            self.engine.to_gpu(key)
            audio = self.engine.run(key, p, job.cancel, lambda s, n, j=job: setattr(j, "step", s))
        except Cancelled:
            if t.get("timed_out"):
                job.state = "timeout"
                self._finish(job, "timeout", "генерация дольше %.0f с" % self.gen_timeout)
                return
            raise
        finally:
            timer.cancel()
            job.state = "unloading"
            self.engine.to_ram(key)                      # окно VRAM возвращается сразу
        t["gen_s"] = round(self.clock() - t0, 2)
        pcm = make_loop(audio["pcm"], audio["rate"], audio["channels"]) if p["loop"] else audio["pcm"]
        wav = encode_wav(pcm, audio["rate"], audio["channels"])
        dur = len(pcm) / 2 / audio["channels"] / audio["rate"]
        path = os.path.join(self.out_dir, job.id + ".wav")
        with open(path, "wb") as f:
            f.write(wav)
        t["total_s"] = round(self.clock() - job.created, 2)
        rec = {"id": "MUSIC-JOB-" + job.id, "job_id": job.id, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "model": key, "repo": MODELS[key]["repo"], "license": MODELS[key]["license"],
               "params": {k: p[k] for k in ("seconds", "seed", "steps", "loop")}, "prompt_sha256": sha256(p["prompt"].encode()), "wav_sha256": sha256(wav), "bytes": len(wav),
               "duration_s": round(dur, 2), "rate": audio["rate"], "timings": t, "vram_window": win}
        rec["receipt_sha256"] = self._receipt(rec)
        self._finish(job, "done", result={"path": path, "wav_sha256": rec["wav_sha256"], "duration_s": rec["duration_s"], "license": MODELS[key]["license"], "receipt_sha256": rec["receipt_sha256"]})

    def _receipt(self, rec):
        ledger, prev = os.path.join(self.receipts_dir, "MUSIC-LEDGER.jsonl"), ""
        try:
            with open(ledger, encoding="utf-8") as f:
                prev = json.loads([x for x in f.read().splitlines() if x.strip()][-1])["receipt_sha256"]
        except (OSError, IndexError, ValueError, KeyError):
            pass
        rec["prev"] = prev
        h = sha256(json.dumps(rec, sort_keys=True, ensure_ascii=False).encode())
        full = dict(rec, receipt_sha256=h)
        with open(os.path.join(self.receipts_dir, "MUSIC-JOB-%s.json" % rec["job_id"]), "w", encoding="utf-8") as f:
            json.dump(full, f, ensure_ascii=False, indent=1)
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(full, ensure_ascii=False) + "\n")
        return h

    def unload(self, model=None):
        if self.current is not None:
            return 409, {"error": "busy", "message": "идёт генерация %s" % self.current.id}
        done = []
        for k in ([model] if model else list(self.engine.loaded())):
            if k in self.engine.loaded():
                self.engine.to_ram(k)
                self.engine.drop(k)
                done.append(k)
        return 200, {"unloaded": done, "loaded": self.engine.loaded()}

    def _evictor(self):
        while not self._stop.is_set():
            time.sleep(1.0)
            if self.evict_s > 0 and self.current is None and self.engine.loaded() and self.q.empty() and self.clock() - self.last_used > self.evict_s:
                self.unload()
                self.last_used = self.clock()

    def status(self, jid=None):
        if jid:
            j = self.jobs.get(jid)
            if not j:
                return 404, {"error": "not_found"}
            d = j.info()
            if j.state == "done":
                d["result"] = {k: v for k, v in j.result.items() if k != "path"}
            return 200, d
        return 200, {"ok": True, "service": "nox-music", "state": self.current.state if self.current else "idle", "queued": sum(1 for j in self.jobs.values() if j.state == "queued"),
                     "models": {k: {"repo": v["repo"], "license": v["license"], "installed": self.engine.installed(k), "where": self.engine.loaded().get(k, "cold")} for k, v in MODELS.items()},
                     "counters": dict(self.counters), "mem_available_gb": None if self.mem_avail() is None else round(self.mem_avail(), 1), "gpu_free_mb": self.gate.free_mb()}

    def close(self):
        self._stop.set()


def make_handler(svc, token=None, origin=None):
    token = E("NOX_MUSIC_TOKEN") if token is None else token
    origin = E("NOX_MUSIC_ORIGIN", "*") if origin is None else origin

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        WAIT = float(E("NOX_MUSIC_WAIT_S", "900"))

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Expose-Headers", "X-NOX-License, X-NOX-Duration, X-NOX-Receipt")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _j(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def _auth(self):
            if token and self.headers.get("Authorization") != "Bearer " + token:
                self._j(401, {"error": "unauthorized"})
                return False
            return True

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            path = self.path.partition("?")[0]
            if path == "/health":
                return self._j(200, {"ok": True})
            if not self._auth():
                return
            if path == "/status":
                return self._j(*svc.status())
            m = re.fullmatch(r"/status/([0-9a-f]+)", path)
            if m:
                return self._j(*svc.status(m.group(1)))
            m = re.fullmatch(r"/receipt/([0-9a-f]+)", path)
            if m:
                try:
                    return self._send(200, open(os.path.join(svc.receipts_dir, "MUSIC-JOB-%s.json" % m.group(1)), "rb").read())
                except OSError:
                    return self._j(404, {"error": "not_found"})
            self._j(404, {"error": "not_found"})

        def do_POST(self):
            if not self._auth():
                return
            path = self.path.partition("?")[0]
            try:
                n = int(self.headers.get("Content-Length", "0") or 0)
                if n > 65536:
                    raise ValueError("тело больше 64 КБ")
                body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            except (ValueError, json.JSONDecodeError) as e:
                return self._j(400, {"error": "bad_request", "message": "некорректный JSON: %s" % e})
            if path == "/gen":
                code, pl = svc.submit(body)
                if code != 202:
                    return self._j(code, pl)
                job = svc.jobs[pl["id"]]
                if body.get("async") is True:
                    return self._j(202, pl)
                if not job.done.wait(self.WAIT):
                    return self._j(504, {"error": "timeout", "id": job.id, "message": "задача идёт, см. /status/" + job.id})
                if job.state == "done":
                    r = job.result
                    return self._send(200, open(r["path"], "rb").read(), "audio/wav", {"X-NOX-License": r["license"], "X-NOX-Duration": str(r["duration_s"]), "X-NOX-Receipt": r["receipt_sha256"]})
                code = {"cancelled": 409, "timeout": 504}.get(job.state, 503 if (job.error or "").startswith(("vram_unavailable", "weights", "ram_low")) else 500)
                return self._j(code, {"error": job.state, "id": job.id, "message": job.error})
            if path == "/unload":
                return self._j(*svc.unload(body.get("model")))
            m = re.fullmatch(r"/cancel/([0-9a-f]+)", path)
            if m:
                return self._j(*svc.cancel(m.group(1)))
            self._j(404, {"error": "not_found"})
    return H


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    eng = FakeEngine() if "--fake" in a else TorchEngine(E("NOX_MUSIC_MODEL_DIR", os.path.join(HOME, "dl", "hf", "music")))
    svc = Service(eng)
    srv = ThreadingHTTPServer((E("NOX_MUSIC_HOST", "127.0.0.1"), int(E("NOX_MUSIC_PORT", "8098"))), make_handler(svc))
    print("NOX MUSIC %s:%d engine=%s" % (srv.server_address[0], srv.server_address[1], type(eng).__name__), flush=True)
    try:
        srv.serve_forever()
    finally:
        svc.close()


if __name__ == "__main__":
    main()
