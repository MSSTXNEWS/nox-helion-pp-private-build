"""NOX web adapter: делает веб-сборку «Резонанс» рабочей поверх умного моста (ядро, память S03, эмоции остаются на пути ответа).
Подключается из nox_bridge.py: WEB.install(app, bridge_module). Слушает тот же 127.0.0.1:8091.
Без выдумок: нет измерения -> null / HOLD. Токен доступа: если есть /root/nox/state/web_token, он обязателен."""
import asyncio, hashlib, json, math, os, re, shutil, subprocess, threading, time
import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse, RedirectResponse
try:
    import nox_wow as W
except Exception:
    W = None

TAG = "nox-helion:latest"
ST = "/root/nox/state"
TOKEN_FILE = ST + "/web_token"
SET_FILE = ST + "/web_settings.json"
FACTS = ST + "/owner_facts.jsonl"
WEBROOT = "/opt/nox-web"
M = {"t": 0, "gpu": [], "cpu": None, "ram": None, "disk": None}
SRC = {}
CANCEL = set()
# Increment-only broadcast STOP epoch: a new request cannot clear an older stream's STOP.
CANCEL_ALL_EPOCH = 0
_lock = None
_lock_mini = None
_cpu_prev = [None]


def _read(p):
    try:
        return open(p).read().strip()
    except Exception:
        return None


def _ram():
    # лимит контейнера (cgroup) важнее, чем 385 ГБ машины
    for cur, mx in (("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.max"),
                    ("/sys/fs/cgroup/memory/memory.usage_in_bytes", "/sys/fs/cgroup/memory/memory.limit_in_bytes")):
        c, m = _read(cur), _read(mx)
        if c is None and m is None:
            continue
        # "max" and huge v1 sentinel limits mean the cgroup is unlimited.
        if m == "max":
            continue
        # A declared finite cgroup limit outranks host /proc/meminfo. A bad
        # usage sample must be unknown, not silently replaced with host RAM.
        if not (c is not None and m is not None and
                c.isascii() and c.isdecimal() and
                m.isascii() and m.isdecimal()):
            return None, None
        used, limit = int(c), int(m)
        if limit < (1 << 50):
            if limit <= 0 or used > limit:
                return None, None
            return used / 2**30, limit / 2**30
    try:
        mi = dict(l.split(":") for l in open("/proc/meminfo").read().splitlines() if ":" in l)
        tot = int(mi["MemTotal"].split()[0]) / 1048576
        return tot - int(mi["MemAvailable"].split()[0]) / 1048576, tot
    except Exception:
        return None, None


def _cpu():
    try:
        v = [int(x) for x in open("/proc/stat").readline().split()[1:8]]
        idle, tot = v[3] + v[4], sum(v)
        p = _cpu_prev[0]
        _cpu_prev[0] = (idle, tot)
        if p and tot > p[1]:
            return round(100 * (1 - (idle - p[0]) / (tot - p[1])), 1)
    except Exception:
        pass
    return None


def _gpu():
    try:
        o = subprocess.run(["nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=4).stdout.strip().splitlines()
        out = []
        for l in o:
            i, u, mu, mt, t, pw = [x.strip() for x in l.split(",")]
            f = lambda x: float(x) if x.replace(".", "", 1).isdigit() else None
            out.append({"index": int(i), "util": f(u), "mem_used_gib": round(float(mu) / 1024, 2), "mem_total_gib": round(float(mt) / 1024, 2), "temp_c": f(t), "power_w": f(pw)})
        return out
    except Exception:
        return []


def _sampler(B):
    # всё тяжёлое (nvidia-smi, supervisorctl) в фоне, запрос чата никогда не ждёт эти вызовы
    while True:
        try:
            M["gpu"] = _gpu()
            M["cpu"] = _cpu()
            M["ram"] = _ram()
            u = shutil.disk_usage("/root")
            M["disk"] = (u.free / 2**30, u.total / 2**30)
            M["t"] = time.time()
            B.body_line()
            if B.SOUL:
                B.SOUL.awareness_line()
        except Exception:
            pass
        time.sleep(8)


def _gpu_utilization_percent(samples):
    """Unknown per-GPU utilization is NOT zero or free GPU capacity (6A04)."""
    if not isinstance(samples, list) or not samples:
        return None
    values = []
    for sample in samples:
        if not isinstance(sample, dict):
            return None
        value = sample.get("util")
        if type(value) not in (int, float):
            return None
        try:
            if not 0 <= value <= 100 or not math.isfinite(value):
                return None
        except (OverflowError, ValueError):
            return None
        values.append(float(value))
    return round(sum(values) / len(values), 1)


def _verified_gpu_sensor_values(samples, key):
    """Never substitute zero for a missing/invalid safety-relevant GPU sensor."""
    if not isinstance(samples, list) or not samples:
        return None
    values = []
    for sample in samples:
        if not isinstance(sample, dict):
            return None
        value = sample.get(key)
        if type(value) not in (int, float):
            return None
        try:
            if not math.isfinite(value) or value < 0:
                return None
            values.append(float(value))
        except (ValueError, OverflowError):
            return None
    return values


def _status_flat():
    g = M["gpu"]
    temperatures = _verified_gpu_sensor_values(g, "temp_c")
    powers = _verified_gpu_sensor_values(g, "power_w")
    ru, rt = M["ram"] or (None, None)
    df, dt = M["disk"] or (None, None)
    fresh = M["t"] and time.time() - M["t"] < 30
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(M["t"])) if M["t"] else None,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(M["t"])) if M["t"] else None,
        "source": "nox-bridge:/proc+nvidia-smi", "gpu_source": "nvidia-smi", "fresh": bool(fresh),
        "cpu_percent": M["cpu"], "ram_percent": round(100 * ru / rt, 1) if ru is not None and rt else None,
        "ram_used_gb": round(ru, 1) if ru is not None else None, "ram_total_gb": round(rt, 1) if rt is not None else None,
        "gpu_percent": _gpu_utilization_percent(g),
        "vram_used_gb": round(sum(x["mem_used_gib"] for x in g), 1) if g else None,
        "vram_total_gb": round(sum(x["mem_total_gib"] for x in g), 1) if g else None,
        "gpu_temperature_c": max(temperatures) if temperatures is not None else None,
        # nvidia-smi query here measures GPU core temperature, NOT hot-spot.
        "gpu_hotspot_c": None,
        "gpu_power_w": round(sum(powers), 0) if powers is not None else None,
        "cpu_temperature_c": None, "disk_free_gib": round(df, 1) if df is not None else None, "disk_total_gib": round(dt, 1) if dt is not None else None,
        "gpus": g,
    }


def _model_ok():
    try:
        import urllib.request
        return urllib.request.urlopen("http://127.0.0.1:8098/health", timeout=2).status == 200
    except Exception:
        return False


def _procs():
    try:
        o = subprocess.run(["supervisorctl", "status"], capture_output=True, text=True, timeout=8).stdout.splitlines()
        return [{"name": l.split()[0], "state": l.split()[1] if len(l.split()) > 1 else "?", "detail": " ".join(l.split()[2:])[:60]} for l in o if l.strip()]
    except Exception:
        return []


_pc = {"t": 0, "v": []}


def _procs_cached():
    if time.time() - _pc["t"] > 20:
        _pc.update(t=time.time(), v=_procs())
    return _pc["v"]


def _jl(path, n):
    try:
        return [json.loads(l) for l in open(path).read().splitlines()[-n:]]
    except Exception:
        return []


def _warm(B):
    """Прогрев: загрузить S03 и закэшировать стабильный префикс промпта в обоих слотах, чтобы первый ответ не ждал."""
    time.sleep(25)
    try:
        B.memory_block("прогрев")
    except Exception:
        pass
    for slot in (0, 1):
        try:
            httpx.post(B.MODEL, json={"messages": [{"role": "system", "content": B.IDENTITY + B.STATIC_RULES}, {"role": "user", "content": "."}],
                       "max_tokens": 1, "id_slot": slot, "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False}}, timeout=400)
            B.log("warm_slot_%d_ok" % slot)
        except Exception as e:
            B.log("warm_slot_%d_fail %s" % (slot, type(e).__name__))


def install(app, B):
    global _lock, _lock_mini
    threading.Thread(target=_warm, args=(B,), daemon=True).start()
    _lock = asyncio.Semaphore(1)
    _lock_mini = asyncio.Semaphore(1)
    threading.Thread(target=_sampler, args=(B,), daemon=True).start()
    digest = "sha256:" + hashlib.sha256(("NOX-HELION|bridge-v1|" + B.MODEL).encode()).hexdigest()

    @app.middleware("http")
    async def guard(request: Request, call_next):
        tok = _read(TOKEN_FILE)
        if tok and request.url.path != "/health":
            got = request.headers.get("x-nox-token") or request.cookies.get("nox_token") or request.query_params.get("token")
            if got != tok:
                return JSONResponse({"error": "нужен токен NOX"}, status_code=401)
            resp = await call_next(request)
            if request.query_params.get("token") == tok:
                resp.set_cookie("nox_token", tok, httponly=True, samesite="strict")
            return resp
        return await call_next(request)

    @app.get("/api/health")
    async def a_health():
        return {"status": "ok", "service": "nox-bridge", "model_alive": _model_ok()}

    @app.get("/api/nox/status")
    async def a_nstatus():
        alive = _model_ok()
        d = {"status": "READY" if alive else "HOLD", "model": TAG, "digest": digest, "backend": "NOX_BRIDGE", "primary_model": "DeepSeek V4.1 Flash IQ2_XXS",
             "memory": {"status": "S03 подключена (мост)"}, "reason": None if alive else "модель :8098 не отвечает",
             "native_p02_bound": False, "core_path": "identity+S03+affect+self"}
        d.update(_status_flat())
        return d

    @app.get("/api/status")
    async def a_status():
        f = _status_flat()
        f["system"] = {"cpu_usage_pct": f["cpu_percent"], "ram_usage_pct": f["ram_percent"], "ram_used_gib": f["ram_used_gb"], "ram_total_gib": f["ram_total_gb"],
                       "disk_total_gib": f["disk_total_gib"], "data_source": "nox-bridge:/proc"}
        f["load"] = {"gpu_load_pct": f["gpu_percent"], "gpu_memory_used_gib": f["vram_used_gb"], "gpu_memory_total_gib": f["vram_total_gb"], "cpu_temp_c": None}
        f["gpu_temp"], f["gpu_core_temp"], f["gpu_sensor_source"] = f["gpu_hotspot_c"], f["gpu_temperature_c"], "nvidia-smi"
        return f

    @app.get("/api/pc-metrics")
    async def a_pc():
        return _status_flat()

    @app.api_route("/api/settings", methods=["GET", "POST"])
    async def a_settings(request: Request):
        cur = {}
        try:
            cur = json.load(open(SET_FILE))
        except Exception:
            pass
        if request.method == "POST":
            try:
                b = await request.json()
                cur.update(b.get("settings", b) if isinstance(b, dict) else {})
                json.dump(cur, open(SET_FILE, "w"), ensure_ascii=False)
            except Exception as e:
                return JSONResponse({"status": "HOLD", "reason": str(e)[:100]}, status_code=400)
        return {"status": "OK", "settings": cur}

    @app.get("/api/voice/status")
    async def a_voice():
        return {"status": "UNAVAILABLE", "reason": "голос на сервере не подключён", "local_assets": []}

    @app.get("/api/nox/system/processes")
    async def a_procs():
        p = _procs_cached()
        return {"status": "OK" if p else "HOLD", "processes": p, "running": sum(1 for x in p if x["state"] == "RUNNING"),
                "failed": [x["name"] for x in p if x["state"] in ("FATAL", "BACKOFF", "EXITED")]}

    @app.get("/api/nox/training/status")
    async def a_train():
        p = [x for x in _procs_cached() if "train" in x["name"] or "distill" in x["name"]]
        live = [x["name"] for x in p if x["state"] == "RUNNING"]
        return {"status": "TRAINING_ACTIVE" if live else "TRAINING_IDLE", "verified_live": bool(live), "processes": p,
                "journal": _jl(ST + "/self_journal.jsonl", 3), "hold_reason": None if live else "обучение сейчас не запущено"}

    @app.get("/api/training/status")
    async def a_train2():
        return await a_train()

    @app.get("/api/nox/activity")
    async def a_act():
        age = time.time() - B.LAST_CHAT["t"] if B.LAST_CHAT["t"] else None
        return {"active": bool(CANCEL is not None and _lock.locked()), "last_chat_age_s": round(age) if age is not None else None, "emotion": B.affect_words(B.affect_update(""))}

    @app.get("/api/notifications")
    async def a_notif():
        return {"notifications": [], "items": []}

    @app.get("/api/nox/premium/capabilities")
    async def a_caps():
        return {"status": "OK", "capabilities": ["chat", "memory", "soul", "metrics", "processes", "feedback"]}

    @app.get("/api/nox/soul")
    async def a_soul():
        return {"awareness": B.SOUL.awareness_line() if B.SOUL else "", "emotion": B.affect_words(B.affect_update("")),
                "journal": _jl(ST + "/self_journal.jsonl", 5), "advisor_notes": _jl(ST + "/teacher_notes.jsonl", 3)}

    @app.get("/api/s03/export")
    async def a_export(category: str = "history"):
        rows = [{"id": i + 1, "title": t.get("u", "")[:80], "content": t.get("a", ""), "source": "S03"} for i, t in enumerate(reversed(_jl(ST + "/turns.jsonl", 50)))]
        return {"status": "OK", "rows": rows, "next": None}

    @app.get("/api/nox/history")
    async def a_hist():
        msgs = []
        for t in _jl(ST + "/turns.jsonl", 40):
            msgs += [{"role": "user", "content": t.get("u", "")}, {"role": "assistant", "content": t.get("a", "")}]
        return {"status": "OK", "messages": msgs, "next": None}

    @app.get("/api/s03/record")
    async def a_record(id: str = ""):
        r = SRC.get(str(id))
        return {"status": "OK", "id": id, "content": r or "запись не найдена в последнем поиске", "category": "memory"}

    @app.post("/api/nox/memory/facts")
    @app.post("/api/s03/remember")
    async def a_fact(request: Request):
        b = await request.json()
        txt = str(b.get("content", "")).strip()[:2000]
        if not txt:
            return JSONResponse({"status": "HOLD", "reason": "пустой факт"}, status_code=400)
        # The S03 write must succeed before a secondary facts log advertises
        # the candidate. This is NOT an independent S03 readback/acceptance.
        try:
            import s03_memory as S
            await asyncio.to_thread(S.persist_turn, "[ФАКТ ОТ СОЗДАТЕЛЯ] " + txt, "Принято и запомнено.")
        except Exception as e:
            B.log("fact_persist_error %s" % type(e).__name__)
            return JSONResponse({"status": "HOLD", "reason": "S03_PERSIST_FAILED",
                                 "saved": False, "s03_readback_verified": False},
                                status_code=503)
        try:
            with open(FACTS, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": int(time.time()), "key": str(b.get("fact_key", ""))[:120], "content": txt, "source": str(b.get("source_ref") or b.get("source", ""))[:200]}, ensure_ascii=False) + "\n")
            return {"status": "RECORDED_UNVERIFIED", "saved": True,
                    "s03_readback_verified": False}
        except Exception as e:
            B.log("fact_mirror_error %s" % type(e).__name__)
            return JSONResponse({"status": "PARTIAL_HOLD", "reason": "FACTS_MIRROR_WRITE_FAILED",
                                 "saved": False, "s03_readback_verified": False},
                                status_code=500)

    @app.get("/api/nox/memory/facts")
    async def a_facts(limit: int = 20):
        limit = max(1, min(limit, 100))
        rows = [{"kind": "owner_fact", "t": f.get("t"), "key": f.get("key"), "content": f.get("content"), "provenance": f.get("source") or "OWNER",
                 "confidence": None} for f in _jl(FACTS, limit)]
        rows += [{"kind": "dialog_turn", "t": t.get("t"), "key": None, "content": (t.get("u", "")[:160] + " → " + t.get("a", "")[:160]), "provenance": "S03:dialog",
                  "confidence": None} for t in _jl(ST + "/turns.jsonl", limit)]
        if W:
            for sl in W.tail(W.F["sleep"], limit):
                rows += [{"kind": "sleep_fact", "t": sl.get("t"), "key": None, "content": f, "provenance": "SLEEP", "confidence": None,
                          "lora_after": sl.get("lora_after")} for f in sl.get("facts", [])]
        rows.sort(key=lambda r: r.get("t") or 0, reverse=True)
        return {"status": "OK", "facts": rows[:limit], "note": "confidence не измеряется (null = Н/Д)"}

    @app.get("/api/nox/unknown")
    async def a_unknown(limit: int = 40):
        items = W.unknown_items(max(1, min(limit, 100))) if W else []
        return {"status": "OK", "items": items, "open": sum(1 for i in items if i.get("status") == "open"), "note": "голод знаний: «не знаю», низкая уверенность, сомнения скептика, вопросы самоанализа"}

    @app.get("/api/nox/decisions")
    async def a_decisions(limit: int = 40):
        rows = W.decisions_items(max(1, min(limit, 100))) if W else []
        return {"status": "OK", "decisions": rows, "levels": W.LEVELS if W else {}, "level": "L1 стиль сам с журналом; L2/L3 только предложения"}

    @app.get("/api/nox/changes")
    async def a_changes(since: int = 0, mark: int = 0):
        out = W.changes(since, bool(mark)) if W else {}
        out["status"] = "OK"
        return out

    @app.get("/api/nox/personality")
    async def a_personality():
        return {"status": "OK", "levels": W.LEVELS, "style": W.style_profile(), "drift_log": W.tail(W.F["drift"], 30)[::-1], "limit": "L1 не чаще 1 раза в сутки; L0 не меняется"}

    @app.get("/api/nox/lora/candidates")
    async def a_lora():
        rows = W.lora_candidates()
        return {"status": "OK", "rule": "только факты старше 7 дней; советники - 2+ независимых; решает Создатель", "candidates": rows, "count": len(rows)}

    @app.post("/api/nox/sleep/run")
    async def a_sleep(request: Request):
        async def a1(m, n): return await B.ask(m, n, slot=1)
        async with _lock_mini:
            rec = await W.sleep_once(a1, B.remember_fact)
        return {"status": "OK" if rec else "SKIP", "sleep": rec, "reason": None if rec else "мало новых разговоров"}

    @app.get("/api/nox/sleep")
    async def a_sleep_log():
        return {"status": "OK", "sleeps": W.tail(W.F["sleep"], 20)[::-1]}

    @app.api_route("/api/nox/notes", methods=["GET", "POST"])
    async def a_notes(request: Request):
        if request.method == "POST":
            b = await request.json()
            txt = str(b.get("text", "")).strip()
            if not txt:
                return JSONResponse({"status": "HOLD", "reason": "пустая заметка"}, status_code=400)
            due = b.get("due") or W.parse_due(txt)
            return {"status": "OK", "note": W.add_note(txt, b.get("page", ""), due if b.get("remind", True) else None)}
        return {"status": "OK", "notes": W.tail(W.F["notes"], 50)[::-1]}

    @app.get("/api/nox/reminders")
    async def a_reminders(due: int = 0):
        return {"status": "OK", "now": int(time.time()), "reminders": W.reminders(bool(due))}

    @app.post("/api/nox/reminders/done")
    async def a_rem_done(request: Request):
        b = await request.json()
        return {"status": "OK", "done": W.done_reminder(b.get("id", ""))}

    @app.post("/api/nox/feedback")
    async def a_feedback(request: Request):
        b = await request.json()
        try:
            with open(ST + "/feedback.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": int(time.time()), "q": str(b.get("q", ""))[:400], "a": str(b.get("a", ""))[:900], "v": 1 if b.get("v") in (1, "up", True) else -1, "request_id": str(b.get("request_id", ""))}, ensure_ascii=False) + "\n")
            return {"status": "OK"}
        except Exception as e:
            return JSONResponse({"status": "HOLD", "reason": type(e).__name__}, status_code=500)

    @app.get("/api/nox/kto/export")
    async def a_kto():
        rows = W.kto_export()
        return {"status": "OK", "format": "KTO {prompt, completion, label}", "count": len(rows), "rows": rows[-500:]}

    @app.get("/api/nox/regress")
    async def a_regress():
        return {"status": "OK", "result": W.jread(W.F["regress"], None)}

    @app.post("/api/chat/stop")
    @app.post("/api/nox/stop")
    async def a_stop(request: Request):
        global CANCEL_ALL_EPOCH
        # Malformed input must never escalate into an implicit broadcast STOP.
        # This API is generation-only: media/task/OWNER STOP have separate fences.
        try:
            b = await request.json()
        except Exception:
            return JSONResponse({"status": "HOLD", "reason": "STOP_INVALID_JSON"}, status_code=400)
        if not isinstance(b, dict):
            return JSONResponse({"status": "HOLD", "reason": "STOP_INVALID_BODY"}, status_code=400)
        if b.get("scope", "generation") != "generation":
            return JSONResponse({"status": "HOLD", "reason": "STOP_WRONG_SCOPE"}, status_code=409)
        target = b.get("request_id", "*")
        if not isinstance(target, str) or re.fullmatch(r"(?:[*]|[A-Za-z0-9._:-]{1,128})", target) is None:
            return JSONResponse({"status": "HOLD", "reason": "STOP_INVALID_REQUEST_ID"}, status_code=400)
        if target == "*":
            # A broadcast applies only to previously admitted requests.
            CANCEL_ALL_EPOCH += 1
        else:
            CANCEL.add(target)
        # Signal queued is not evidence that generation actually stopped.
        return {"status": "STOPPING", "scope": "generation",
                "target_request_id": target, "stop_confirmed": False,
                "media_stopped": False, "task_cancelled": False, "owner_stop": False}

    @app.post("/api/chat")
    async def a_chat(request: Request):
        # Capture before body parsing: STOP during request admission is binding.
        request_stop_epoch = CANCEL_ALL_EPOCH
        b = await request.json()
        rid = str(b.get("request_id") or "")
        msgs_in = [m for m in (b.get("messages") or []) if m.get("role") in ("user", "assistant")]
        user = next((m["content"] for m in reversed(msgs_in) if m["role"] == "user"), "")
        use_mem = b.get("use_memory", True) is not False
        npred = int((b.get("options") or {}).get("num_predict") or 700)
        mini = b.get("mini") is True
        opts = b.get("options") or {}
        mode = str(opts.get("mode") or b.get("mode") or "auto")
        eph = b.get("ephemeral") is True
        if mode == "fast": npred = min(npred, 300)
        if mini:
            use_mem, npred = False, min(npred, 400)

        def fr(**k):
            d = {"model": TAG, "request_id": rid, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            d.update(k)
            return json.dumps(d, ensure_ascii=False) + "\n"

        async def gen():
            t0, n, shown = time.time(), 0, 0
            full = ""
            yield fr(message={"role": "assistant", "content": ""}, done=False, nox_status="слушаю тебя…",
                     request_receipt={"status": "RECEIVED", "request_id": rid, "native_admission_verified": False})
            async with (_lock_mini if mini else _lock):
                if rid in CANCEL or CANCEL_ALL_EPOCH != request_stop_epoch:
                    CANCEL.discard(rid)
                    yield fr(message={"role": "assistant", "content": ""}, done=True,
                             done_reason="stopped",
                             completion_receipt={"status": "STOPPED", "request_id": rid,
                                                 "upstream_done": False},
                             memory_write_receipt={"status": "SKIPPED", "request_id": rid,
                                                   "s03_readback_verified": False},
                             memory_history={"status": "SKIPPED", "reason": "USER_STOP",
                                             "s03_readback_verified": False})
                    return
                yield fr(message={"role": "assistant", "content": ""}, done=False, nox_event={"step": "think", "text": "вопрос получен"})
                mem = ""
                if use_mem:
                    yield fr(message={"role": "assistant", "content": ""}, done=False, nox_status="вспоминаю…", nox_event={"step": "memory", "text": "ищу в памяти S03"})
                    mem = await asyncio.to_thread(B.memory_block, user)
                lines = [l for l in mem.splitlines() if l.strip()] if mem else []
                SRC.clear()
                srcs = []
                for i, l in enumerate(lines[:8]):
                    SRC[str(i + 1)] = l
                    srcs.append(dict({"id": i + 1, "source": "S03", "category": "memory", "text": l[:300]}, **(W.provenance(l) if W else {})))
                yield fr(message={"role": "assistant", "content": ""}, done=False, nox_sources=srcs, memory_reason=("найдено %d фрагм." % len(lines)) if lines else "в памяти ничего близкого", nox_status="чувствую…",
                         nox_event={"step": "memory", "text": ("найдено %d фрагм. памяти" % len(lines)) if lines else ("память не использовалась" if not use_mem else "в памяти ничего близкого")})
                extra, plan, rem = "", [], None
                if W and not eph:
                    try: rem = W.maybe_reminder(user, "mini" if mini else "chat")
                    except Exception: rem = None
                    if rem:
                        hh = time.strftime("%d.%m %H:%M", time.gmtime(rem["reminder"]["due"] + 3 * 3600))
                        extra += "[Напоминание создано на %s МСК: подтверди коротко.]" % hh
                        yield fr(message={"role": "assistant", "content": ""}, done=False, nox_event={"step": "reminder", "text": "напоминание на " + hh + " МСК", "reminder": rem["reminder"]})
                if W and not mini:
                    if W.wants_plan(user, mode):
                        yield fr(message={"role": "assistant", "content": ""}, done=False, nox_event={"step": "plan", "text": "разбиваю задачу на шаги"})
                        try: plan = await W.make_plan(lambda m, n: B.ask(m, n, slot=1), user)
                        except Exception: plan = []
                        if plan:
                            extra += "[План (следуй по порядку, нумеруй шаги): " + "; ".join("%d) %s" % (i + 1, x) for i, x in enumerate(plan)) + "]"
                            yield fr(message={"role": "assistant", "content": ""}, done=False, nox_event={"step": "plan", "text": "план: %d шагов" % len(plan), "plan": plan})
                    extra += W.mode_hint(mode)
                yield fr(message={"role": "assistant", "content": ""}, done=False, nox_event={"step": "think", "text": "формулирую ответ"})
                if mini:
                    last = msgs_in[-1]["content"] if msgs_in else user
                    mm = [{"role": "system", "content": B.IDENTITY + B.STATIC_RULES},
                          {"role": "user", "content": "[Режим мини-помощника: ответ не длиннее 4 предложений, без строки «Уверенность»]" + extra + "\n" + str(last)[:3000]}]
                else:
                    vol = await asyncio.to_thread(B.self_vol, user)
                    mm = B.build_msgs(msgs_in, user, mem, vol, "\n" + extra if extra else "")
                body = {"messages": mm, "max_tokens": max(64, min(npred, 900, (400 if mini else (900 if mode == "thoughtful" else B.adapt_tokens(user, 900))))), "temperature": 0.4 if mode == "thoughtful" else 0.6, "id_slot": 1 if mini else 0, "cache_prompt": True, "n_keep": B.NKEEP, "stream": True,
                        "chat_template_kwargs": {"enable_thinking": False}}
                err = None
                upstream_done = False
                upstream_failure = None
                try:
                    if True:
                        async with B.hc().stream("POST", B.MODEL, json=body) as r:
                            if r.status_code != 200:
                                raise RuntimeError("UPSTREAM_HTTP_NON_200")
                            async for line in r.aiter_lines():
                                if rid in CANCEL or CANCEL_ALL_EPOCH != request_stop_epoch:
                                    break
                                if not line.startswith("data:"):
                                    continue
                                d = line[5:].strip()
                                if d == "[DONE]":
                                    upstream_done = True
                                    break
                                # A model can send [DONE] after a truncated finish or
                                # an explicit SSE error. Neither is a completed answer.
                                try:
                                    event = json.loads(d)
                                except (TypeError, ValueError):
                                    upstream_failure = "INVALID_SSE_JSON"
                                    break
                                if not isinstance(event, dict) or "error" in event:
                                    upstream_failure = "UPSTREAM_ERROR_EVENT"
                                    break
                                choices = event.get("choices")
                                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                                    upstream_failure = "UPSTREAM_CHOICES_INVALID"
                                    break
                                choice = choices[0]
                                finish_reason = choice.get("finish_reason")
                                if finish_reason is not None and finish_reason != "stop":
                                    upstream_failure = "UPSTREAM_NONSTOP_FINISH"
                                    break
                                delta = choice.get("delta") or {}
                                if not isinstance(delta, dict):
                                    upstream_failure = "UPSTREAM_DELTA_INVALID"
                                    break
                                t = delta.get("content") or ""
                                if not isinstance(t, str):
                                    upstream_failure = "UPSTREAM_CONTENT_INVALID"
                                    break
                                if t:
                                    full += t
                                    n += 1
                                    yield fr(message={"role": "assistant", "content": t}, done=False)
                                    if plan and "\n" in t:
                                        k = len(re.findall(r"(?m)^\s*(?:Шаг\s*)?\d+[.)]", full))
                                        if k > shown and k <= len(plan):
                                            shown = k
                                            yield fr(message={"role": "assistant", "content": ""}, done=False, nox_event={"step": "plan", "text": "шаг %d/%d: %s" % (k, len(plan), plan[k - 1]), "index": k, "total": len(plan)})
                except Exception as e:
                    err = type(e).__name__
                    B.log("web_stream_error %s" % err)
                if not mini:
                    B.LAST_CHAT["t"] = time.time()
                stopped = rid in CANCEL or CANCEL_ALL_EPOCH != request_stop_epoch
                # Incomplete HTTP streams must never yield successful DONE or S03 writes.
                if not stopped and (err or upstream_failure or not upstream_done or not full.strip()):
                    B.log("web_stream_incomplete " + (err or upstream_failure or "MISSING_DONE_OR_EMPTY"))
                    CANCEL.discard(rid)
                    yield json.dumps({"status": "HOLD", "reason": "MODEL_STREAM_INCOMPLETE",
                                      "error": "ответ модели не завершён — можно повторить запрос",
                                      "request_id": rid, "done": False,
                                      "memory_history": {"status": "HOLD", "reason": "UPSTREAM_NOT_COMPLETE", "s03_readback_verified": False},
                                       "completion_receipt": {"status": "HOLD", "request_id": rid,
                                                              "upstream_done": upstream_done},
                                       "memory_write_receipt": {"status": "SKIPPED", "request_id": rid,
                                                                "s03_readback_verified": False}},
                                     ensure_ascii=False) + "\n"
                    return
                hist = {"status": "HOLD", "reason": "ответ пуст или остановлен"}
                sk = None
                if W and not mini and not stopped and full.strip() and mode != "fast" and (mode == "thoughtful" or W.is_factual(user)):
                    yield fr(message={"role": "assistant", "content": ""}, done=False, nox_event={"step": "check", "text": "проверяю факты (скептик)"})
                    sk = await W.skeptic(lambda m, n_: B.ask(m, n_, slot=1), user, full, record=not eph)
                    if sk.get("ok") is False:
                        add = "\n\n⚠ Скептик: " + sk["doubt"]
                        full += add
                        yield fr(message={"role": "assistant", "content": add}, done=False)
                    yield fr(message={"role": "assistant", "content": ""}, done=False, nox_event={"step": "check", "text": ("сомнение: " + sk["doubt"]) if sk.get("ok") is False else "проверка пройдена" if sk.get("ok") else "проверка недоступна", "ok": sk.get("ok")})
                # STOP may arrive while the post-generation skeptic awaits. Never
                # persist a cancelled answer using the stale pre-skeptic flag.
                stopped = stopped or rid in CANCEL or CANCEL_ALL_EPOCH != request_stop_epoch
                if eph:
                    hist = {"status": "SKIPPED", "reason": "ephemeral"}
                elif full.strip() and not stopped:
                    try:
                        import s03_memory as S
                        await asyncio.to_thread(S.persist_turn, ("[mini] " + user) if mini else user, full.strip())
                        hist = {"status": "SAVED", "mini": mini, "s03_readback_verified": False}
                    except Exception as e:
                        hist = {"status": "HOLD", "reason": "S03: " + type(e).__name__}
                    if B.SOUL and not mini:
                        B.SOUL.log_turn(user, full.strip())
                CANCEL.discard(rid)
                yield fr(message={"role": "assistant", "content": ""}, done=True, done_reason="stop" if not stopped else "stopped",
                         completion_receipt={"status": "STOPPED" if stopped else "GENERATED",
                                             "request_id": rid, "upstream_done": bool(upstream_done and not stopped)},
                         memory_write_receipt={"status": "WRITE_RETURNED_UNVERIFIED" if hist["status"] == "SAVED" else hist["status"],
                                               "request_id": rid, "s03_readback_verified": False},
                         digest=hashlib.sha256(full.encode()).hexdigest(), frames=n, memory_history=hist, nox_mode=mode, skeptic=sk, plan=plan or None,
                         total_duration=int((time.time() - t0) * 1e9), eval_count=n)

        return StreamingResponse(gen(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/app")
    async def a_app():
        return RedirectResponse("/web/chat.html")

    if os.path.isdir(WEBROOT):
        from fastapi.staticfiles import StaticFiles
        from starlette.middleware.gzip import GZipMiddleware
        _TXT = (".html", ".css", ".js", ".mjs", ".json", ".svg", ".txt", ".md", ".map")
        _static = StaticFiles(directory=WEBROOT, html=True)
        _gz = GZipMiddleware(_static, minimum_size=1024, compresslevel=5)

        async def _web_app(scope, receive, send):
            if scope["type"] == "http" and scope["path"].lower().endswith(_TXT) or scope["type"] == "http" and scope["path"].endswith("/"):
                return await _gz(scope, receive, send)
            return await _static(scope, receive, send)
        app.mount("/web", _web_app, name="web")

        @app.middleware("http")
        async def web_cache(request: Request, call_next):
            resp = await call_next(request)
            p = request.url.path
            if p.startswith("/web/"):
                if p.lower().endswith((".html", "/")):
                    resp.headers["Cache-Control"] = "no-cache"
                else:
                    resp.headers["Cache-Control"] = "public, max-age=86400"
            return resp
