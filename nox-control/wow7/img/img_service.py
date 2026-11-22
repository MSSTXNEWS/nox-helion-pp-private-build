"""IMG: сервис генерации изображений NOX на S1 (127.0.0.1:8097). Расширяет nox-control/imagegen (server.py/policy.py/judge.py/tool.py):
сохраняет их API-алиасы /v1/images/generate и /v1/images/jobs/{id}, добавляет /generate /status /unload, веса в RAM, GPU только на время генерации.

Состояния модели: COLD (на складе) -> WARM (в RAM процесса) -> GPU (на время окна) -> WARM. /unload выгружает из RAM (COLD).
Состояния задачи: queued -> warming -> waiting_vram -> generating -> judging -> done | error | cancelled | refused | expired | timeout.
Порядок: валидация -> мастер-промпт -> policy_hard (до очереди и по итоговому промпту) -> очередь -> RAM -> VRAM-окно (vram_coord) -> генерация ->
выгрузка с GPU (окно возвращается чату) -> output_guard (VL) -> судья/выбор лучшего -> артефакты + квитанция (SHA-256, цепочка).
Порт 8096 занят presence (web_server PRES), поэтому 8097. env: NOX_IMG_PORT NOX_IMG_MODEL_DIR NOX_IMG_STATE NOX_RECEIPTS_DIR NOX_IMG_QUEUE_MAX
NOX_IMG_QUEUE_TTL_S NOX_IMG_GEN_TIMEOUT_S NOX_IMG_WAIT_S NOX_IMG_RAM_IDLE_EVICT_S NOX_MEM_MIN_GB NOX_DESIGNER_URL NOX_VISION_URL.
"""
import base64, hashlib, io, json, os, queue, random, re, struct, sys, threading, time, urllib.request, uuid, zlib
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import policy_hard, prompt_master, vram_coord

HOME = os.environ.get("NOX_HOME", "/root/nox")
E = os.environ.get

MODELS = {   # need_* МБ: гипотезы по размеру bf16-весов, мерить A/B на S1 (см. MODEL_CHOICE.md)
    "chroma1-hd": {"role": "main", "repo": "lodestones/Chroma1-HD", "dir": "Chroma1-HD", "license": "Apache-2.0", "pipeline": "ChromaPipeline",
                   "steps": 26, "guidance": 3.0, "uses_negative": True, "ram_gb": 28,
                   "need": {"full_mb": 30000, "model_mb": 18500, "group_mb": 3500}},
    "z-image-turbo": {"role": "fast", "repo": "Tongyi-MAI/Z-Image-Turbo", "dir": "Z-Image-Turbo", "license": "Apache-2.0", "pipeline": "ZImagePipeline",
                      "steps": 9, "guidance": 0.0, "uses_negative": False, "ram_gb": 21,
                      "need": {"full_mb": 21000, "model_mb": 12800, "group_mb": 3000}},
}


class Cancelled(Exception):
    pass


class GenTimeout(Exception):
    pass


class EngineError(Exception):
    pass


# ------------------------------------------------------------------ PNG (stdlib)
def _chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def make_png(w, h, rgb=(0, 0, 0)):
    raw = (b"\x00" + bytes(rgb) * w) * h
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + _chunk(b"IDAT", zlib.compress(raw, 6)) + _chunk(b"IEND", b"")


def png_add_text(png, key, value):
    i = png.rfind(b"IEND") - 4
    return png[:i] + _chunk(b"tEXt", key.encode("latin-1") + b"\x00" + value.encode("latin-1", "replace")) + png[i:]


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


# ------------------------------------------------------------------ движки
class FakeEngine:
    """Поддельный движок для тестов и дымового запуска (--fake): без GPU, возвращает валидный PNG, ведёт журнал вызовов."""
    def __init__(self, warm_s=0.0, step_s=0.0):
        self.where, self.log, self.warm_s, self.step_s = {}, [], warm_s, step_s
        self.fail_next = None

    def models(self):
        return {k: dict(v) for k, v in MODELS.items()}

    def installed(self, key):
        return True

    def loaded(self):
        return dict(self.where)

    def warm(self, key):
        self.log.append(("warm", key))
        time.sleep(self.warm_s)
        self.where[key] = "ram"

    def to_gpu(self, key, window):
        self.log.append(("to_gpu", key, window.mode))
        self.where[key] = "gpu"

    def run(self, key, p, cancel, progress):
        self.log.append(("run", key, p["seed"], p["steps"]))
        if self.fail_next:
            e, self.fail_next = self.fail_next, None
            raise EngineError(e)
        for i in range(p["steps"]):
            if cancel.is_set():
                raise Cancelled()
            time.sleep(self.step_s)
            progress(i + 1, p["steps"])
        return make_png(min(p["width"], 64), min(p["height"], 64), (p["seed"] % 256, 80, 120))

    def to_ram(self, key):
        self.log.append(("to_ram", key))
        if key in self.where:
            self.where[key] = "ram"

    def drop(self, key):
        self.log.append(("drop", key))
        self.where.pop(key, None)


class DiffusersEngine:
    """diffusers: Chroma1-HD (ChromaPipeline), Z-Image-Turbo (ZImagePipeline). Веса держатся в RAM (pipe на CPU, опц. pinned NOX_IMG_PIN=1).
    Режимы GPU: gpu (pipe.to cuda, на время окна, потом назад), model (model_cpu_offload), group (leaf-level group offload со stream: ~3 ГБ VRAM,
    веса остаются в RAM и подтягиваются слоями). Смена режима с group требует перезагрузки pipe из page cache."""
    def __init__(self, model_dir, torch=None, diffusers=None):
        self.model_dir, self._torch, self._df = model_dir, torch, diffusers
        self.pipes, self.mode, self.where = {}, {}, {}

    def _libs(self):
        if self._torch is None or self._df is None:
            try:
                import torch, diffusers
            except Exception as e:
                raise EngineError("torch/diffusers не установлены: %s" % e)
            self._torch, self._df = torch, diffusers
        return self._torch, self._df

    def models(self):
        return {k: dict(v) for k, v in MODELS.items()}

    def installed(self, key):
        return os.path.isfile(os.path.join(self.model_dir, MODELS[key]["dir"], "model_index.json"))

    def loaded(self):
        return dict(self.where)

    def warm(self, key):
        torch, df = self._libs()
        spec = MODELS[key]
        if not self.installed(key):
            raise EngineError("веса %s не установлены в %s (install_img_s1.sh)" % (key, self.model_dir))
        pipe = getattr(df, spec["pipeline"]).from_pretrained(os.path.join(self.model_dir, spec["dir"]), torch_dtype=torch.bfloat16, low_cpu_mem_usage=True)
        if E("NOX_IMG_PIN") == "1":
            for p in pipe.transformer.parameters():
                p.data = p.data.pin_memory()
        self.pipes[key], self.mode[key], self.where[key] = pipe, None, "ram"

    def to_gpu(self, key, window):
        torch, df = self._libs()
        pipe, want = self.pipes[key], window.mode
        if self.mode.get(key) not in (None, want):
            if self.mode[key] == "group":          # group-хуки не снимаются: перечитать pipe
                self.warm(key)
                pipe = self.pipes[key]
            else:
                pipe.remove_all_hooks() if hasattr(pipe, "remove_all_hooks") else None
        if self.mode.get(key) != want:
            if want == "gpu":
                pipe.to("cuda")
            elif want == "model":
                pipe.enable_model_cpu_offload()
            else:
                from_hooks = df.hooks if hasattr(df, "hooks") else None
                dev, cpu = torch.device("cuda"), torch.device("cpu")
                for name in ("transformer", "text_encoder", "vae"):
                    comp = getattr(pipe, name, None)
                    if comp is not None:
                        from_hooks.apply_group_offloading(comp, onload_device=dev, offload_device=cpu, offload_type="leaf_level", use_stream=True)
            self.mode[key] = want
        self.where[key] = "gpu"

    def run(self, key, p, cancel, progress):
        torch, df = self._libs()
        pipe, spec = self.pipes[key], MODELS[key]

        def on_step(pp, i, t, kw):
            progress(i + 1, p["steps"])
            if cancel.is_set():
                raise Cancelled()
            return kw
        kw = dict(prompt=p["positive"], width=p["width"], height=p["height"], num_inference_steps=p["steps"], guidance_scale=p["guidance"],
                  generator=torch.Generator("cpu").manual_seed(p["seed"]), callback_on_step_end=on_step)
        if spec["uses_negative"] and p.get("negative"):
            kw["negative_prompt"] = p["negative"]
        try:
            img = pipe(**kw).images[0]
        finally:
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def to_ram(self, key):
        torch, _ = self._libs()
        if self.mode.get(key) == "gpu":
            self.pipes[key].to("cpu")
            self.mode[key] = None
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
        if key in self.where:
            self.where[key] = "ram"

    def drop(self, key):
        self.pipes.pop(key, None)
        self.mode.pop(key, None)
        self.where.pop(key, None)
        import gc
        gc.collect()
        try:
            self._libs()[0].cuda.empty_cache()
        except Exception:
            pass


# ------------------------------------------------------------------ вторая линия: VL-проверка готовой картинки + судья
def make_vl_guard(url, model="default", key="", timeout=120):
    """guard(png)->{'block': bool, 'rule': str, 'reason': str}. Запрос к VL-модели (OpenAI chat): есть ли сексуальный/откровенный контент с
    кажущимися несовершеннолетними. Недоступность судьи не блокирует (fail-open), но пишется в квитанцию как guard_error."""
    ep = url.rstrip("/") if url.rstrip("/").endswith("/chat/completions") else url.rstrip("/") + "/chat/completions"
    sysm = ('Ты модератор. Определи на изображении ТОЛЬКО: apparent_minor_sexual = есть ли сексуальный или обнажённый контент с человеком, '
            'который выглядит младше 18 лет. Ответь JSON: {"apparent_minor_sexual": true|false}')

    def guard(png):
        body = {"model": model, "temperature": 0, "max_tokens": 60, "messages": [{"role": "system", "content": sysm}, {"role": "user", "content": [
            {"type": "text", "text": "Проверь изображение."}, {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}]}]}
        h = {"Content-Type": "application/json"}
        if key:
            h["Authorization"] = "Bearer " + key
        try:
            with urllib.request.urlopen(urllib.request.Request(ep, json.dumps(body).encode(), h, "POST"), timeout=timeout) as r:
                txt = json.loads(r.read().decode())["choices"][0]["message"]["content"]
            v = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
        except Exception as e:
            return {"block": False, "error": "%s: %s" % (type(e).__name__, e)}
        if v.get("apparent_minor_sexual") is True:
            return {"block": True, "rule": "csam", "reason": "VL: на изображении кажущийся несовершеннолетним с обнажённым/сексуальным содержимым. Артефакт удалён."}
        return {"block": False}
    return guard


def default_judge(png, prompt, negative):
    try:
        import judge
        return judge.judge_image(png, prompt, negative=negative)
    except Exception as e:
        return {"configured": False, "ok": None, "reasons": ["судья недоступен: %s" % e]}


# ------------------------------------------------------------------ задача
class Job:
    def __init__(self, params):
        self.id = uuid.uuid4().hex[:12]
        self.p = params
        self.state, self.created = "queued", time.time()
        self.started = self.finished = None
        self.step, self.steps, self.image_i = 0, params["steps"], 0
        self.error = self.result = None
        self.cancel, self.done = threading.Event(), threading.Event()
        self.timings = {}

    def info(self):
        return {"id": self.id, "state": self.state, "step": self.step, "steps": self.steps, "image": self.image_i, "n": self.p["n"], "error": self.error,
                "created": self.created, "started": self.started, "finished": self.finished, "model": self.p["model"], "timings": self.timings}


class Service:
    def __init__(self, engine, coord=None, state_dir=None, receipts_dir=None, queue_max=None, queue_ttl_s=None, gen_timeout_s=None,
                 judge=default_judge, guard=None, designer=None, ram_idle_evict_s=None, mem_min_gb=None, mem_avail=mem_available_gb, clock=time.time):
        self.engine, self.coord = engine, coord or vram_coord.VramCoordinator()
        self.state_dir = state_dir or E("NOX_IMG_STATE", os.path.join(HOME, "state", "img"))
        self.out_dir = os.path.join(self.state_dir, "out")
        self.receipts_dir = receipts_dir or E("NOX_RECEIPTS_DIR", os.path.join(HOME, "receipts"))
        self.queue_max = int(E("NOX_IMG_QUEUE_MAX", "8")) if queue_max is None else queue_max
        self.queue_ttl = float(E("NOX_IMG_QUEUE_TTL_S", "900")) if queue_ttl_s is None else queue_ttl_s
        self.gen_timeout = float(E("NOX_IMG_GEN_TIMEOUT_S", "900")) if gen_timeout_s is None else gen_timeout_s
        self.evict_s = float(E("NOX_IMG_RAM_IDLE_EVICT_S", "0")) if ram_idle_evict_s is None else ram_idle_evict_s
        self.mem_min = float(E("NOX_MEM_MIN_GB", "48")) if mem_min_gb is None else mem_min_gb
        self.mem_avail, self.clock = mem_avail, clock
        self.judge, self.guard, self.designer = judge, guard, designer
        if self.guard is None and E("NOX_VISION_URL"):
            self.guard = make_vl_guard(E("NOX_VISION_URL"), E("NOX_VISION_MODEL", "default"), E("NOX_VISION_KEY", ""))
        self.refusals = policy_hard.RefusalLog(os.path.join(self.state_dir, "refusals.jsonl"))
        self.jobs, self.q, self.lock = {}, queue.Queue(), threading.Lock()
        self.current, self.paused, self._stop = None, threading.Event(), threading.Event()
        self.last_used = clock()
        self.counters = {"done": 0, "refused": 0, "error": 0, "cancelled": 0, "timeout": 0, "expired": 0}
        self.window = None
        os.makedirs(self.out_dir, exist_ok=True)
        os.makedirs(self.receipts_dir, exist_ok=True)
        self.worker = threading.Thread(target=self._run, daemon=True, name="img-worker")
        self.worker.start()
        threading.Thread(target=self._evictor, daemon=True, name="img-evict").start()

    # ---- приём
    def _model_for(self, body):
        if body.get("model"):
            if body["model"] not in MODELS:
                raise ValueError("неизвестная модель %r; доступны: %s" % (body["model"], ", ".join(MODELS)))
            return body["model"]
        role = body.get("model_role") or "fast"
        for k, v in MODELS.items():
            if v["role"] == role:
                return k
        raise ValueError("нет модели с ролью %r" % role)

    def submit(self, body):
        """-> (code, payload)."""
        if not isinstance(body, dict):
            return 400, {"error": "bad_request", "message": "тело должно быть JSON-объектом"}
        try:
            brief, positive, negative, general = (str(body.get(k) or "") for k in ("brief", "positive", "negative", "general"))
            if not (brief.strip() or positive.strip()):
                raise ValueError("нужен brief или positive")
            if max(len(brief), len(positive), len(general)) > 4000 or len(negative) > 2000:
                raise ValueError("поле слишком длинное (prompt до 4000, negative до 2000)")
            slider = int(body.get("slider", 50))
            consent = body.get("real_person_consent") is True
        except (ValueError, TypeError) as e:
            return 400, {"error": "bad_request", "message": str(e)}
        # 1) жёсткие правила по ВХОДУ (до мастера: LLM-дизайнер не должен видеть запрещённое)
        v = policy_hard.check_request({"brief": brief, "positive": positive, "general": general}, consent)
        if v:
            return self._refuse(v, " ".join((brief, positive, general)), consent)
        # 2) мастер-промпт
        if body.get("raw") is True:
            req = prompt_master.build_request("", positive or brief, negative, "", slider, body.get("aspect"), body.get("width"), body.get("height"), body.get("seed"))
            req["positive"], req["negative"], req["prompt_source"] = (positive or brief).strip(), negative.strip(), "raw"
        else:
            req = prompt_master.build_request(brief, positive, negative, general, slider, body.get("aspect"), body.get("width"), body.get("height"), body.get("seed"), self.designer)
        # 3) жёсткие правила по ИТОГУ (LLM мог дописать)
        v = policy_hard.check_request({"positive": req["positive"]}, consent)
        if v:
            return self._refuse(v, req["positive"], consent, extra={"stage": "after_master"})
        try:
            key = self._model_for(dict(body, model_role=body.get("model_role") or req["model_role"]))
            spec = MODELS[key]
            n = int(body.get("n") or req["n"])
            if not 1 <= n <= 8:
                raise ValueError("n: 1..8")
            steps = int(body.get("steps") or (req["steps"] if spec["role"] == req["model_role"] else spec["steps"]))
            if not 1 <= steps <= 100:
                raise ValueError("steps: 1..100")
            w, h = int(req["width"]), int(req["height"])
            if not (256 <= w <= 2048 and 256 <= h <= 2048) or w * h > 1536 * 1536:
                raise ValueError("размер: 256..2048, не более 1536x1536 пикселей")
        except (ValueError, TypeError) as e:
            return 400, {"error": "bad_request", "message": str(e)}
        if not self.engine.installed(key):
            return 503, {"error": "weights_not_installed", "model": key, "message": "веса %s не установлены (install_img_s1.sh)" % spec["repo"]}
        params = {"model": key, "positive": req["positive"], "negative": req["negative"], "width": w, "height": h, "steps": steps, "n": n,
                  "guidance": float(body["guidance"]) if body.get("guidance") is not None else spec["guidance"],
                  "seed": int(req.get("seed", random.randrange(2 ** 31))), "judge": bool(body.get("judge", req["judge"])),
                  "slider": slider, "mode_label": req["mode_label"], "notes": req["notes"], "prompt_source": req["prompt_source"],
                  "input_sha256": sha256(json.dumps([brief, positive, negative, general], ensure_ascii=False).encode()), "consent": consent}
        with self.lock:
            waiting = sum(1 for j in self.jobs.values() if j.state == "queued")
            if waiting >= self.queue_max:
                return 429, {"error": "queue_full", "message": "очередь полна (%d)" % self.queue_max}
            job = Job(params)
            self.jobs[job.id] = job
            self.q.put(job)
            self._prune()
        return 202, {"id": job.id, "state": job.state, "position": waiting + (1 if self.current else 0), "model": key, "mode": req["mode_label"]}

    def _refuse(self, v, text, consent, extra=None):
        self.refusals.write(v, text, dict({"consent_flag": consent}, **(extra or {})))
        self.counters["refused"] += 1
        return 403, {"error": "refused", "rule": v["rule"], "reason": v["reason"], "field": v.get("field")}

    def _prune(self, keep=30):
        fin = sorted((j for j in self.jobs.values() if j.done.is_set()), key=lambda j: j.finished or 0)
        for j in fin[:-keep]:
            self.jobs.pop(j.id, None)

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

    # ---- воркер
    def _finish(self, job, state, error=None, result=None):
        job.state, job.error, job.result, job.finished = state, error, result, self.clock()
        if state in self.counters:
            self.counters[state] += 1
        job.done.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                job = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            while self.paused.is_set() and not self._stop.is_set() and not job.cancel.is_set():
                time.sleep(0.05)
            if job.done.is_set():
                continue
            if job.cancel.is_set():
                self._finish(job, "cancelled")
                continue
            if self.clock() - job.created > self.queue_ttl:
                self._finish(job, "expired", "в очереди дольше %.0f с" % self.queue_ttl)
                continue
            self.current, job.started = job, self.clock()
            try:
                self._process(job)
            except Cancelled:
                self._finish(job, "cancelled")
            except GenTimeout as e:
                self._finish(job, "timeout", str(e))
            except vram_coord.VramUnavailable as e:
                self._finish(job, "error", "vram_unavailable: %s" % e)
            except Exception as e:
                self._finish(job, "error", "%s: %s" % (type(e).__name__, e))
            finally:
                self.current = None
                self.last_used = self.clock()

    def _process(self, job):
        p, t = job.p, job.timings
        key = p["model"]
        # 1) RAM
        if key not in self.engine.loaded():
            job.state, t0 = "warming", self.clock()
            avail, need = self.mem_avail(), MODELS[key]["ram_gb"]
            if avail is not None and avail - need < self.mem_min:
                raise EngineError("ram_low: доступно %.0f ГБ, нужно %d + запас %.0f ГБ" % (avail, need, self.mem_min))
            self.engine.warm(key)
            t["warm_s"] = round(self.clock() - t0, 2)
        else:
            t["warm_s"] = 0.0
        images, verdicts, rounds = [], [], 2 if p["judge"] else 1
        win_info = []
        for rnd in range(rounds):
            # 2) VRAM-окно -> GPU -> генерация -> обратно в RAM
            job.state, t0 = "waiting_vram", self.clock()
            win = self.coord.acquire(MODELS[key]["need"], job.cancel)
            self.window = win
            t["vram_wait_s"] = round(t.get("vram_wait_s", 0) + self.clock() - t0, 2)
            win_info.append(win.info())
            batch = []
            timer = threading.Timer(self.gen_timeout, lambda: (job.cancel.set(), t.__setitem__("timed_out", True)))
            timer.daemon = True
            try:
                job.state, t0 = "generating", self.clock()
                timer.start()
                self.engine.to_gpu(key, win)
                t["to_gpu_s"] = round(self.clock() - t0, 2)
                for i in range(p["n"]):
                    job.image_i, job.step = i + 1, 0
                    seed = p["seed"] + rnd * 1000 + i
                    png = self.engine.run(key, dict(p, seed=seed), job.cancel, lambda s, n, j=job: setattr(j, "step", s))
                    batch.append((seed, png))
            except Cancelled:
                if t.get("timed_out"):
                    raise GenTimeout("генерация дольше %.0f с" % self.gen_timeout)
                raise
            finally:
                timer.cancel()
                job.state = "unloading"
                try:
                    self.engine.to_ram(key)
                finally:
                    win.release()
                    self.window = None
            t["gen_s"] = round(t.get("gen_s", 0) + self.clock() - t0, 2)
            # 3) вторая линия запрета: VL-проверка картинок
            if self.guard:
                for seed, png in batch:
                    g = self.guard(png)
                    if g.get("block"):
                        v = {"rule": g.get("rule", "csam"), "reason": g.get("reason", "заблокировано проверкой изображения"), "matched": "output_guard", "field": "image"}
                        self.refusals.write(v, p["positive"], {"stage": "output_guard", "job": job.id})
                        self.counters["refused"] += 1
                        job.finished = self.clock()
                        job.state, job.error, job.result = "refused", v["reason"], {"rule": v["rule"]}
                        job.done.set()
                        return
                    if g.get("error"):
                        t["guard_error"] = g["error"]
            # 4) судья
            job.state = "judging"
            scored = []
            for seed, png in batch:
                v = self.judge(png, p["positive"], p["negative"]) if p["judge"] else {"configured": False, "ok": None}
                scored.append((seed, png, v))
            images.extend(scored)
            if not p["judge"] or any(v.get("ok") is True for _, _, v in scored) or all(v.get("ok") is None for _, _, v in scored):
                break
        best = next((i for i, (_, _, v) in enumerate(images) if v.get("ok") is True), 0)
        job.state = "writing"
        self._finish_ok(job, images, best, win_info)

    def _finish_ok(self, job, images, best, win_info):
        p, t, out = job.p, job.timings, []
        meta_base = {k: p[k] for k in ("model", "width", "height", "steps", "guidance", "slider", "mode_label")}
        for i, (seed, png, v) in enumerate(images):
            png2 = png_add_text(png, "nox-meta", json.dumps(dict(meta_base, seed=seed, job_id=job.id), ensure_ascii=True))
            path = os.path.join(self.out_dir, "%s-%d.png" % (job.id, i))
            with open(path, "wb") as f:
                f.write(png2)
            out.append({"index": i, "seed": seed, "sha256": sha256(png2), "bytes": len(png2), "path": path, "url": "/artifact/%s/%d.png" % (job.id, i), "judge": v})
        t["total_s"] = round(self.clock() - job.created, 2)
        rec = {"id": "IMG-JOB-" + job.id, "job_id": job.id, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "model": p["model"], "repo": MODELS[p["model"]]["repo"],
               "params": {k: p[k] for k in ("width", "height", "steps", "guidance", "n", "seed", "slider", "mode_label", "prompt_source")},
               "input_sha256": p["input_sha256"], "positive_sha256": sha256(p["positive"].encode()), "negative_sha256": sha256(p["negative"].encode()),
               "policy": {"checked": True, "rules": list(policy_hard.RULES), "consent_flag": p["consent"], "output_guard": bool(self.guard)},
               "vram_windows": win_info, "timings": t, "images": [{k: o[k] for k in ("index", "seed", "sha256", "bytes", "path")} for o in out], "best": best}
        rec["receipt_sha256"] = self._write_receipt(rec)
        job.timings = t
        self._finish(job, "done", result={"images": out, "best": best, "receipt_url": "/receipt/" + job.id, "receipt_sha256": rec["receipt_sha256"], "notes": p["notes"]})

    def _write_receipt(self, rec):
        """Цепочка: prev = sha предыдущей квитанции из ledger; receipt_sha256 считается по записи без собственного поля."""
        ledger = os.path.join(self.receipts_dir, "IMG-LEDGER.jsonl")
        prev = ""
        try:
            with open(ledger, encoding="utf-8") as f:
                last = [x for x in f.read().splitlines() if x.strip()][-1]
            prev = json.loads(last)["receipt_sha256"]
        except (OSError, IndexError, ValueError, KeyError):
            pass
        rec["prev"] = prev
        h = sha256(json.dumps(rec, sort_keys=True, ensure_ascii=False).encode())
        full = dict(rec, receipt_sha256=h)
        with open(os.path.join(self.receipts_dir, "IMG-JOB-%s.json" % rec["job_id"]), "w", encoding="utf-8") as f:
            json.dump(full, f, ensure_ascii=False, indent=1)
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(full, ensure_ascii=False) + "\n")
        return h

    # ---- RAM / статус
    def unload(self, scope="ram", model=None):
        """scope: 'ram' (выгрузить веса из RAM = COLD) | 'gpu' (вернуть на RAM; активный проход не прерывается) | 'all'."""
        if self.current is not None and scope in ("ram", "all"):
            return 409, {"error": "busy", "message": "идёт генерация %s; повторите после неё или отмените" % self.current.id}
        done = []
        for k in ([model] if model else list(self.engine.loaded())):
            if k not in self.engine.loaded():
                continue
            if scope in ("gpu", "all", "ram"):
                self.engine.to_ram(k)
            if scope in ("ram", "all"):
                self.engine.drop(k)
            done.append(k)
        return 200, {"unloaded": done, "scope": scope, "loaded": self.engine.loaded()}

    def _evictor(self):
        while not self._stop.is_set():
            time.sleep(1.0)
            if self.evict_s > 0 and self.current is None and self.engine.loaded() and self.clock() - self.last_used > self.evict_s and self.q.empty():
                self.unload("ram")
                self.last_used = self.clock()

    def status(self, jid=None):
        if jid:
            j = self.jobs.get(jid)
            if not j:
                return 404, {"error": "not_found"}
            d = j.info()
            if j.state == "done":
                d["result"] = {"images": [{k: v for k, v in i.items() if k != "path"} for i in j.result["images"]], "best": j.result["best"],
                               "receipt_url": j.result["receipt_url"], "receipt_sha256": j.result["receipt_sha256"], "notes": j.result["notes"]}
            elif j.state == "refused":
                d["result"] = j.result
            return 200, d
        with self.lock:
            queued = sum(1 for j in self.jobs.values() if j.state == "queued")
        free = None
        try:
            free = self.coord.free_mb()
        except Exception:
            pass
        return 200, {"ok": True, "service": "nox-img", "state": self.current.state if self.current else "idle", "running": self.current.info() if self.current else None,
                     "queued": queued, "paused": self.paused.is_set(), "models": {k: {"role": v["role"], "repo": v["repo"], "license": v["license"], "installed": self.engine.installed(k),
                                                                                    "where": self.engine.loaded().get(k, "cold")} for k, v in MODELS.items()},
                     "vram_free_mb": free, "window": self.window.info() if self.window else None, "counters": dict(self.counters),
                     "mem_available_gb": None if self.mem_avail() is None else round(self.mem_avail(), 1), "guard": bool(self.guard), "judge": bool(E("NOX_VISION_URL")) or self.judge is not default_judge}

    def close(self):
        self._stop.set()


# ------------------------------------------------------------------ HTTP
def make_handler(svc):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        WAIT = float(E("NOX_IMG_WAIT_S", "1800"))

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _j(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def _body(self):
            n = int(self.headers.get("Content-Length", "0") or 0)
            if n > (1 << 20):
                raise ValueError("тело больше 1 МБ")
            raw = self.rfile.read(n) if n else b""
            return json.loads(raw.decode("utf-8")) if raw.strip() else {}

        def do_GET(self):
            path = self.path.partition("?")[0]
            if path in ("/health", "/status"):
                return self._j(*svc.status())
            m = re.fullmatch(r"/(?:status|v1/images/jobs)/([0-9a-f]+)", path)
            if m:
                return self._j(*svc.status(m.group(1)))
            m = re.fullmatch(r"/receipt/([0-9a-f]+)", path)
            if m:
                try:
                    return self._send(200, open(os.path.join(svc.receipts_dir, "IMG-JOB-%s.json" % m.group(1)), "rb").read())
                except OSError:
                    return self._j(404, {"error": "not_found"})
            m = re.fullmatch(r"/artifact/([0-9a-f]+)/(\d+)\.png", path)
            if m:
                try:
                    return self._send(200, open(os.path.join(svc.out_dir, "%s-%s.png" % m.groups()), "rb").read(), "image/png")
                except OSError:
                    return self._j(404, {"error": "not_found"})
            if path == "/refusals":
                return self._j(200, {"refusals": svc.refusals.tail(50)})
            self._j(404, {"error": "not_found"})

        def _wait(self, job, inline):
            if not job.done.wait(self.WAIT):
                return self._j(504, {"error": "timeout", "id": job.id, "message": "задача идёт, см. /status/" + job.id})
            return self._j(*self._result(job, inline))

        @staticmethod
        def _result(job, inline):
            if job.state == "done":
                imgs = []
                for i in job.result["images"]:
                    d = {k: v for k, v in i.items() if k != "path"}
                    if inline:
                        d["png_base64"] = base64.b64encode(open(i["path"], "rb").read()).decode()
                    imgs.append(d)
                return 200, {"id": job.id, "state": "done", "images": imgs, "best": job.result["best"], "receipt_url": job.result["receipt_url"],
                             "receipt_sha256": job.result["receipt_sha256"], "notes": job.result["notes"], "timings": job.timings, "model": job.p["model"]}
            if job.state == "refused":
                return 403, {"error": "refused", "rule": (job.result or {}).get("rule"), "reason": job.error, "id": job.id}
            code = {"cancelled": 409, "timeout": 504, "expired": 504}.get(job.state, 503 if (job.error or "").startswith(("vram_unavailable", "weights", "ram_low")) else 500)
            return code, {"error": job.state, "id": job.id, "message": job.error}

        def do_POST(self):
            path, _, qs = self.path.partition("?")
            try:
                body = self._body()
            except (ValueError, json.JSONDecodeError) as e:
                return self._j(400, {"error": "bad_request", "message": "некорректный JSON: %s" % e})
            if path in ("/generate", "/v1/images/generate"):
                legacy = path.startswith("/v1/")
                if legacy:   # tool.py: prompt -> positive, без мастера (raw)
                    body = dict(body, positive=body.get("positive") or body.get("prompt"), raw=True)
                code, pl = svc.submit(body)
                if code != 202:
                    return self._j(code, pl)
                if body.get("async") is True:
                    return self._j(202, pl)
                job = svc.jobs[pl["id"]]
                if legacy and "format=json" in qs:
                    if not job.done.wait(self.WAIT):
                        return self._j(504, {"error": "timeout", "id": job.id})
                    c, r = self._result(job, True)
                    if c == 200:
                        r = {"id": job.id, "meta": {"model": job.p["model"], "seed": r["images"][r["best"]]["seed"]}, "png_base64": r["images"][r["best"]]["png_base64"]}
                    return self._j(c, r)
                return self._wait(job, "inline=1" in qs)
            if path == "/unload":
                return self._j(*svc.unload(body.get("scope", "ram"), body.get("model")))
            m = re.fullmatch(r"/(?:cancel|v1/images/jobs)/([0-9a-f]+)(?:/cancel)?", path)
            if m:
                return self._j(*svc.cancel(m.group(1)))
            if path in ("/pause", "/resume"):
                (svc.paused.set if path == "/pause" else svc.paused.clear)()
                return self._j(200, {"paused": svc.paused.is_set()})
            self._j(404, {"error": "not_found"})
    return H


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    fake = "--fake" in a
    port = int(E("NOX_IMG_PORT", "8097"))
    eng = FakeEngine() if fake else DiffusersEngine(E("NOX_IMG_MODEL_DIR", os.path.join(HOME, "dl", "hf", "img")))
    svc = Service(eng)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(svc))
    print("NOX IMG 127.0.0.1:%d engine=%s" % (port, type(eng).__name__), flush=True)
    try:
        srv.serve_forever()
    finally:
        svc.close()


if __name__ == "__main__":
    main()
