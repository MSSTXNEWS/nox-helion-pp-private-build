"""Сервис генерации изображений NOX на S1: 127.0.0.1:8096.

GPU (RTX 5060 Ti 16 ГБ) занят GLM-5.3 и быстрым тиром Qwen3-4B, поэтому картинки идут ПО ОЧЕРЕДИ (одна задача за раз)
с CPU-offload диффузии (NOX_IMG_OFFLOAD=auto|sequential|model|none). Тир и слои GLM не трогаем.

Эндпоинты:
  POST /v1/images/generate {prompt, negative, width, height, steps, seed, model, guidance, async, real_person_consent}
        по умолчанию ждёт и отдаёт image/png (метаданные: заголовок X-Nox-Meta и PNG-чанк tEXt "nox-meta");
        "Accept: application/json" или ?format=json -> JSON {id, meta, png_base64}; "async": true -> 202 {id}
  GET  /v1/images/jobs/{id}            статус;   GET /v1/images/jobs/{id}/png   результат
  POST /v1/images/jobs/{id}/cancel     отмена (в очереди - сразу, в работе - между шагами)
  POST /v1/images/pause | /resume      пауза очереди (текущая задача доедет)
  GET  /health                         состояние, модели, очередь
  GET  /v1/images/refusals             хвост журнала отказов
Коды: 400 неверный запрос, 403 отказ по жёсткому правилу, 429 очередь полна, 503 нет весов / нет diffusers.
"""
import base64, json, os, queue, random, re, struct, sys, threading, time, uuid, zlib
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import policy

HOST = "127.0.0.1"
PORT = int(os.environ.get("NOX_IMG_PORT", "8096"))
MODEL_DIR = os.environ.get("NOX_IMG_MODEL_DIR", "")
STATE_DIR = os.environ.get("NOX_IMG_STATE_DIR", os.path.join(os.path.expanduser("~"), ".nox", "imagegen"))
QUEUE_MAX = int(os.environ.get("NOX_IMG_QUEUE_MAX", "8"))
WAIT_S = float(os.environ.get("NOX_IMG_WAIT_S", "1800"))
MAX_BODY = 1 << 20
MAX_PIXELS = 1536 * 1536
KEEP_FINISHED = 20


class Cancelled(Exception):
    pass


class BackendUnavailable(Exception):
    """Нет весов или библиотек - честный 503."""


# ---------------------------------------------------------------- PNG-утилиты (stdlib)
def _chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def png_add_text(png, key, value):
    """Вставить tEXt-чанк перед IEND."""
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("не PNG")
    i = png.rfind(b"IEND") - 4
    txt = _chunk(b"tEXt", key.encode("latin-1") + b"\x00" + value.encode("latin-1", "replace"))
    return png[:i] + txt + png[i:]


def png_read_text(png):
    out, p = {}, 8
    while p + 8 <= len(png):
        n = struct.unpack(">I", png[p:p + 4])[0]
        tag = png[p + 4:p + 8]
        if tag == b"tEXt":
            k, _, v = png[p + 8:p + 8 + n].partition(b"\x00")
            out[k.decode("latin-1")] = v.decode("latin-1")
        p += 12 + n
    return out


def make_png(width, height, rgb=(0, 0, 0)):
    """Минимальный PNG без PIL (для поддельного бэкенда и тестов)."""
    row = b"\x00" + bytes(rgb) * width
    raw = row * height
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, 6)) + _chunk(b"IEND", b""))


# ---------------------------------------------------------------- каталог моделей
def scan_models(model_dir):
    """Модели в NOX_IMG_MODEL_DIR: подпапки diffusers (model_index.json) и одиночные *.safetensors/*.ckpt (SDXL)."""
    out = {}
    if not model_dir or not os.path.isdir(model_dir):
        return out
    for name in sorted(os.listdir(model_dir)):
        p = os.path.join(model_dir, name)
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, "model_index.json")):
            try:
                with open(os.path.join(p, "model_index.json"), encoding="utf-8") as f:
                    cls = json.load(f).get("_class_name", "")
            except Exception:
                continue
            fam = "flux" if "flux" in cls.lower() else "sdxl" if "xl" in cls.lower() else "other"
            out[name] = {"path": p, "family": fam, "kind": "diffusers", "class": cls}
        elif os.path.isfile(p) and name.lower().endswith((".safetensors", ".ckpt")):
            out[os.path.splitext(name)[0]] = {"path": p, "family": "sdxl", "kind": "single_file", "class": "StableDiffusionXLPipeline"}
    return out


def family_defaults(family):
    if family == "flux":
        return {"steps": 4, "guidance": 0.0}   # FLUX.1-schnell: 1-4 шага, без CFG
    return {"steps": 30, "guidance": 6.0}


def pick_model(models, wanted, default_name=None):
    """-> (name, info) либо BackendUnavailable / ValueError."""
    if not models:
        raise BackendUnavailable("веса не установлены: в NOX_IMG_MODEL_DIR=%r нет ни одной модели (папка diffusers с model_index.json или SDXL .safetensors). "
                                 "Скачайте веса вручную, см. README." % MODEL_DIR)
    name = wanted or default_name or ("FLUX.1-schnell" if "FLUX.1-schnell" in models else next(iter(models)))
    if name not in models:
        raise ValueError("модель %r не найдена; доступны: %s" % (name, ", ".join(models)))
    return name, models[name]


# ---------------------------------------------------------------- бэкенд diffusers
class DiffusersBackend:
    """FLUX.1-schnell и SDXL-совместимые чекпойнты. Лениво грузит torch/diffusers, держит одну модель в RAM."""
    def __init__(self, model_dir=None, offload=None):
        self.model_dir = MODEL_DIR if model_dir is None else model_dir
        self.offload = offload or os.environ.get("NOX_IMG_OFFLOAD", "auto")
        self._pipe, self._name = None, None

    def models(self):
        return scan_models(self.model_dir)

    def status(self):
        try:
            import torch, diffusers  # noqa
            lib = {"torch": torch.__version__, "diffusers": diffusers.__version__, "cuda": bool(torch.cuda.is_available())}
        except Exception as e:
            lib = {"error": "%s: %s" % (type(e).__name__, e)}
        return {"backend": "diffusers", "offload": self.offload, "libs": lib}

    def _load(self, name, info):
        if self._name == name and self._pipe is not None:
            return self._pipe
        try:
            import torch
            import diffusers
        except Exception as e:
            raise BackendUnavailable("diffusers/torch не установлены (%s). Запустите c127/imagegen_install_s1.sh" % e)
        self._pipe = None
        import gc
        gc.collect()
        dtype = torch.bfloat16 if info["family"] == "flux" else torch.float16
        if info["kind"] == "single_file":
            pipe = diffusers.StableDiffusionXLPipeline.from_single_file(info["path"], torch_dtype=dtype)
        else:
            pipe = diffusers.DiffusionPipeline.from_pretrained(info["path"], torch_dtype=dtype)
        mode = self.offload
        if mode == "auto":
            mode = "sequential" if info["family"] == "flux" else "model"   # 12B FLUX в bf16 (24 ГБ) на 16 ГБ целиком не помещается
        if mode not in ("sequential", "model", "none"):
            raise ValueError("NOX_IMG_OFFLOAD=%r: допустимо auto|sequential|model|none" % mode)
        if not torch.cuda.is_available() or mode == "none":
            pass   # CPU / без offload
        elif mode == "sequential":
            pipe.enable_sequential_cpu_offload()
        else:
            pipe.enable_model_cpu_offload()
        try:
            pipe.vae.enable_tiling()
        except Exception:
            pass
        self._pipe, self._name = pipe, name
        return pipe

    def generate(self, p, cancel, progress):
        """p: нормализованные параметры + _model (name, info). Вернёт PNG bytes."""
        import io
        import torch
        name, info = p["_model"]
        pipe = self._load(name, info)

        def on_step(pp, i, t, kw):
            progress(i + 1, p["steps"])
            if cancel.is_set():
                raise Cancelled()
            return kw
        gen = torch.Generator("cpu").manual_seed(p["seed"])
        kw = dict(prompt=p["prompt"], width=p["width"], height=p["height"], num_inference_steps=p["steps"],
                  guidance_scale=p["guidance"], generator=gen, callback_on_step_end=on_step)
        if info["family"] == "flux":
            kw["max_sequence_length"] = 256
        elif p["negative"]:
            kw["negative_prompt"] = p["negative"]
        try:
            img = pipe(**kw).images[0]
        finally:
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()   # вернуть VRAM соседям (GLM / Qwen3-4B)
            except Exception:
                pass
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


# ---------------------------------------------------------------- очередь
class Job:
    def __init__(self, params):
        self.id = uuid.uuid4().hex[:12]
        self.params = params
        self.state = "queued"          # queued|running|done|error|cancelled
        self.created = time.time()
        self.started = self.finished = None
        self.step = 0
        self.steps = params["steps"]
        self.error = None
        self.png = None
        self.meta = None
        self.cancel = threading.Event()
        self.done = threading.Event()

    def info(self):
        return {"id": self.id, "state": self.state, "step": self.step, "steps": self.steps, "error": self.error,
                "created": self.created, "started": self.started, "finished": self.finished, "meta": self.meta}


class Service:
    def __init__(self, backend, state_dir=None, queue_max=QUEUE_MAX):
        self.backend = backend
        self.state_dir = state_dir or STATE_DIR
        self.refusals = policy.RefusalLog(os.path.join(self.state_dir, "refusals.jsonl"))
        self.queue_max = queue_max
        self.jobs = {}
        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.current = None
        self.paused = threading.Event()
        self._stop = threading.Event()
        self.worker = threading.Thread(target=self._run, daemon=True, name="imagegen-worker")
        self.worker.start()

    # --- приём запроса
    def normalize(self, body):
        if not isinstance(body, dict):
            raise ValueError("тело должно быть JSON-объектом")
        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt обязателен (непустая строка)")
        if len(prompt) > 4000:
            raise ValueError("prompt длиннее 4000 символов")
        negative = body.get("negative") or ""
        if not isinstance(negative, str) or len(negative) > 2000:
            raise ValueError("negative: строка до 2000 символов")

        def num(key, default, lo, hi, typ=int):
            v = body.get(key)
            if v is None:
                return default
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError("%s: нужно число" % key)
            v = typ(v)
            if not lo <= v <= hi:
                raise ValueError("%s: допустимо %s..%s" % (key, lo, hi))
            return v
        w = num("width", 1024, 256, 2048)
        h = num("height", 1024, 256, 2048)
        w, h = (w // 16) * 16, (h // 16) * 16
        if w * h > MAX_PIXELS:
            raise ValueError("слишком много пикселей: максимум %d (1536x1536)" % MAX_PIXELS)
        seed = num("seed", None, 0, 2 ** 32 - 1) if body.get("seed") is not None else random.randrange(2 ** 32)
        return {"prompt": prompt.strip(), "negative": negative.strip(), "width": w, "height": h, "seed": seed,
                "model": body.get("model") or None, "consent": body.get("real_person_consent") is True, "steps_in": num("steps", None, 1, 100) if body.get("steps") is not None else None,
                "guidance_in": num("guidance", None, 0, 30, float) if body.get("guidance") is not None else None}

    def submit(self, body):
        """-> (code, payload). Порядок: валидация -> запреты -> веса -> очередь."""
        try:
            n = self.normalize(body)
        except ValueError as e:
            return 400, {"error": "bad_request", "message": str(e)}
        verdict = policy.check_prompt(n["prompt"], real_person_consent=n["consent"])
        if verdict:
            self.refusals.write(verdict, n["prompt"], {"consent_flag": n["consent"]})
            return 403, {"error": "refused", "rule": verdict["rule"], "reason": verdict["reason"]}
        try:
            name, info = pick_model(self.backend.models(), n["model"], os.environ.get("NOX_IMG_DEFAULT_MODEL"))
        except BackendUnavailable as e:
            return 503, {"error": "weights_not_installed", "message": str(e)}
        except ValueError as e:
            return 400, {"error": "bad_request", "message": str(e)}
        d = family_defaults(info["family"])
        params = {"prompt": n["prompt"], "negative": n["negative"], "width": n["width"], "height": n["height"], "seed": n["seed"],
                  "steps": n["steps_in"] or d["steps"], "guidance": d["guidance"] if n["guidance_in"] is None else n["guidance_in"],
                  "model": name, "family": info["family"], "_model": (name, info)}
        with self.lock:
            waiting = sum(1 for j in self.jobs.values() if j.state == "queued")
            if waiting >= self.queue_max:
                return 429, {"error": "queue_full", "message": "очередь полна (%d)" % self.queue_max}
            job = Job(params)
            self.jobs[job.id] = job
            self.q.put(job)
            self._prune()
        return 202, {"id": job.id, "state": job.state, "position": waiting + (1 if self.current else 0)}

    def _prune(self):
        fin = sorted((j for j in self.jobs.values() if j.state in ("done", "error", "cancelled")), key=lambda j: j.finished or 0)
        for j in fin[:-KEEP_FINISHED]:
            self.jobs.pop(j.id, None)

    def cancel(self, jid):
        j = self.jobs.get(jid)
        if not j:
            return 404, {"error": "not_found"}
        if j.state in ("done", "error", "cancelled"):
            return 409, {"error": "already_finished", "state": j.state}
        j.cancel.set()
        if j.state == "queued":
            j.state, j.finished = "cancelled", time.time()
            j.done.set()
        return 200, {"id": j.id, "state": j.state if j.state == "cancelled" else "cancelling"}

    # --- воркер: одна задача за раз
    def _run(self):
        while not self._stop.is_set():
            try:
                job = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            while self.paused.is_set() and not self._stop.is_set() and not job.cancel.is_set():
                time.sleep(0.05)
            if job.state == "cancelled" or job.cancel.is_set():
                if job.state != "cancelled":
                    job.state, job.finished = "cancelled", time.time()
                job.done.set()
                continue
            self.current = job
            job.state, job.started = "running", time.time()

            def prog(i, n, job=job):
                job.step = i
            try:
                png = self.backend.generate(job.params, job.cancel, prog)
                meta = {k: job.params[k] for k in ("prompt", "negative", "width", "height", "steps", "seed", "guidance", "model", "family")}
                meta.update(job_id=job.id, seconds=round(time.time() - job.started, 2), negative_ignored=bool(job.params["negative"] and job.params["family"] == "flux"))
                job.png = png_add_text(png, "nox-meta", json.dumps(meta, ensure_ascii=True))
                job.meta, job.state = meta, "done"
            except Cancelled:
                job.state = "cancelled"
            except BackendUnavailable as e:
                job.state, job.error = "error", "weights_not_installed: %s" % e
            except Exception as e:
                job.state, job.error = "error", "%s: %s" % (type(e).__name__, e)
            finally:
                job.finished = time.time()
                self.current = None
                job.done.set()

    def pause(self, on):
        (self.paused.set if on else self.paused.clear)()

    def health(self):
        models = {}
        try:
            models = self.backend.models()
        except Exception:
            pass
        with self.lock:
            queued = sum(1 for j in self.jobs.values() if j.state == "queued")
        h = {"ok": True, "port": PORT, "weights_installed": bool(models),
             "models": {k: {"family": v["family"], "kind": v["kind"]} for k, v in models.items()},
             "model_dir": MODEL_DIR or None, "queued": queued, "running": self.current.info() if self.current else None,
             "paused": self.paused.is_set(), "refusals_logged": len(self.refusals.tail(10 ** 6)),
             "vision_judge": bool(os.environ.get("NOX_VISION_URL"))}
        try:
            h.update(self.backend.status())
        except Exception:
            pass
        if not models:
            h["message"] = "веса не установлены"
        return h

    def close(self):
        self._stop.set()


# ---------------------------------------------------------------- HTTP
def make_handler(svc):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _send(self, code, body=b"", ctype="application/json", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _j(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _png(self, job, as_json):
            if as_json:
                return self._j(200, {"id": job.id, "meta": job.meta, "png_base64": base64.b64encode(job.png).decode()})
            self._send(200, job.png, "image/png", {"X-Nox-Meta": json.dumps(job.meta, ensure_ascii=True), "X-Nox-Job": job.id})

        def _body(self):
            n = int(self.headers.get("Content-Length", "0") or 0)
            if n > MAX_BODY:
                raise ValueError("тело больше 1 МБ")
            raw = self.rfile.read(n) if n else b""
            return json.loads(raw.decode("utf-8")) if raw.strip() else {}

        def do_GET(self):
            path, _, qs = self.path.partition("?")
            if path == "/health":
                return self._j(200, svc.health())
            if path == "/v1/images/refusals":
                return self._j(200, {"refusals": svc.refusals.tail(50)})
            m = re.fullmatch(r"/v1/images/jobs/([0-9a-f]+)(/png)?", path)
            if m:
                j = svc.jobs.get(m.group(1))
                if not j:
                    return self._j(404, {"error": "not_found"})
                if not m.group(2):
                    return self._j(200, j.info())
                if j.state != "done":
                    return self._j(409, {"error": "not_ready", "state": j.state, "message": j.error})
                return self._png(j, "format=json" in qs or "json" in (self.headers.get("Accept") or ""))
            self._j(404, {"error": "not_found"})

        def do_POST(self):
            path, _, qs = self.path.partition("?")
            try:
                body = self._body()
            except (ValueError, json.JSONDecodeError) as e:
                return self._j(400, {"error": "bad_request", "message": "некорректный JSON: %s" % e})
            if path == "/v1/images/generate":
                code, pl = svc.submit(body)
                if code != 202:
                    return self._j(code, pl)
                if body.get("async") is True:
                    return self._j(202, pl)
                job = svc.jobs[pl["id"]]
                as_json = "format=json" in qs or "application/json" in (self.headers.get("Accept") or "")
                if not job.done.wait(WAIT_S):
                    return self._j(504, {"error": "timeout", "id": job.id, "message": "задача ещё идёт, см. /v1/images/jobs/" + job.id})
                if job.state == "done":
                    return self._png(job, as_json)
                if job.state == "cancelled":
                    return self._j(409, {"error": "cancelled", "id": job.id})
                code = 503 if (job.error or "").startswith("weights_not_installed") else 500
                return self._j(code, {"error": "generation_failed", "id": job.id, "message": job.error})
            m = re.fullmatch(r"/v1/images/jobs/([0-9a-f]+)/cancel", path)
            if m:
                return self._j(*svc.cancel(m.group(1)))
            if path == "/v1/images/cancel":
                return self._j(*svc.cancel(str(body.get("id", ""))))
            if path in ("/v1/images/pause", "/v1/images/resume"):
                svc.pause(path.endswith("pause"))
                return self._j(200, {"paused": svc.paused.is_set()})
            self._j(404, {"error": "not_found"})

        def do_DELETE(self):
            m = re.fullmatch(r"/v1/images/jobs/([0-9a-f]+)", self.path.split("?")[0])
            if m:
                return self._j(*svc.cancel(m.group(1)))
            self._j(404, {"error": "not_found"})
    return H


def serve(backend=None, host=HOST, port=PORT, state_dir=None):
    svc = Service(backend or DiffusersBackend(), state_dir=state_dir)
    httpd = ThreadingHTTPServer((host, port), make_handler(svc))
    httpd.daemon_threads = True
    httpd.svc = svc
    return httpd


if __name__ == "__main__":
    httpd = serve()
    print("nox imagegen: http://%s:%d  model_dir=%r" % (HOST, PORT, MODEL_DIR), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
