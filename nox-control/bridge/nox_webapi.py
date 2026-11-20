"""NOX web adapter: делает веб-сборку «Резонанс» рабочей поверх умного моста (ядро, память S03, эмоции остаются на пути ответа).
Подключается из nox_bridge.py: WEB.install(app, bridge_module). Слушает тот же 127.0.0.1:8091.
Без выдумок: нет измерения -> null / HOLD. Токен доступа: если есть /root/nox/state/web_token, он обязателен."""
import asyncio, hashlib, json, os, shutil, subprocess, threading, time
import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse, RedirectResponse

TAG = "nox-helion:latest"
ST = "/root/nox/state"
TOKEN_FILE = ST + "/web_token"
SET_FILE = ST + "/web_settings.json"
FACTS = ST + "/owner_facts.jsonl"
WEBROOT = "/opt/nox-web"
M = {"t": 0, "gpu": [], "cpu": None, "ram": None, "disk": None}
SRC = {}
CANCEL = set()
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
        if c and m and m.isdigit() and int(m) < (1 << 50):
            return int(c) / 2**30, int(m) / 2**30
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


def _status_flat():
    g = M["gpu"]
    ru, rt = M["ram"] or (None, None)
    df, dt = M["disk"] or (None, None)
    fresh = M["t"] and time.time() - M["t"] < 30
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(M["t"])) if M["t"] else None,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(M["t"])) if M["t"] else None,
        "source": "nox-bridge:/proc+nvidia-smi", "gpu_source": "nvidia-smi", "fresh": bool(fresh),
        "cpu_percent": M["cpu"], "ram_percent": round(100 * ru / rt, 1) if ru and rt else None,
        "ram_used_gb": round(ru, 1) if ru else None, "ram_total_gb": round(rt, 1) if rt else None,
        "gpu_percent": round(sum(x["util"] or 0 for x in g) / len(g), 1) if g else None,
        "vram_used_gb": round(sum(x["mem_used_gib"] for x in g), 1) if g else None,
        "vram_total_gb": round(sum(x["mem_total_gib"] for x in g), 1) if g else None,
        "gpu_temperature_c": max((x["temp_c"] or 0 for x in g), default=None) if g else None,
        "gpu_hotspot_c": max((x["temp_c"] or 0 for x in g), default=None) if g else None,
        "gpu_power_w": round(sum(x["power_w"] or 0 for x in g), 0) if g else None,
        "cpu_temperature_c": None, "disk_free_gib": round(df, 1) if df else None, "disk_total_gib": round(dt, 1) if dt else None,
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


def install(app, B):
    global _lock, _lock_mini
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
        rows.sort(key=lambda r: r.get("t") or 0, reverse=True)
        return {"status": "OK", "facts": rows[:limit], "note": "confidence не измеряется (null = Н/Д)"}

    @app.get("/api/nox/unknown")
    async def a_unknown():
        items = [{"t": j.get("t"), "question": j.get("question"), "learn": j.get("learn")} for j in _jl(ST + "/self_journal.jsonl", 30) if j.get("question") or j.get("learn")]
        return {"status": "OK", "items": list(reversed(items)), "note": "голод знаний: вопросы и темы из самоанализа NOX"}

    @app.get("/api/nox/decisions")
    async def a_decisions():
        items = [{"t": j.get("t"), "weak": j.get("weak"), "improve": j.get("improve")} for j in _jl(ST + "/self_journal.jsonl", 30) if j.get("weak") or j.get("improve")]
        return {"status": "OK", "decisions": list(reversed(items)), "level": "L3: предложения, сам не применяет"}

    @app.get("/api/nox/changes")
    async def a_changes(since: int = 0):
        facts = [f for f in _jl(FACTS, 200) if (f.get("t") or 0) > since]
        jr = [j for j in _jl(ST + "/self_journal.jsonl", 200) if (j.get("t") or 0) > since]
        fb = [f for f in _jl(ST + "/feedback.jsonl", 500) if (f.get("t") or 0) > since]
        tr = [t for t in _jl(ST + "/turns.jsonl", 500) if (t.get("t") or 0) > since]
        return {"status": "OK", "since": since, "now": int(time.time()), "new_facts": facts[-20:], "new_journal": jr[-10:],
                "feedback": {"up": sum(1 for f in fb if f.get("v") == 1), "down": sum(1 for f in fb if f.get("v") != 1)}, "new_turns": len(tr)}

    @app.post("/api/chat/stop")
    @app.post("/api/nox/stop")
    async def a_stop(request: Request):
        try:
            b = await request.json()
        except Exception:
            b = {}
        CANCEL.add(str(b.get("request_id", "*")))
        return {"status": "STOPPING"}

    @app.post("/api/chat")
    async def a_chat(request: Request):
        b = await request.json()
        rid = str(b.get("request_id") or "")
        msgs_in = [m for m in (b.get("messages") or []) if m.get("role") in ("user", "assistant")]
        user = next((m["content"] for m in reversed(msgs_in) if m["role"] == "user"), "")
        use_mem = b.get("use_memory", True) is not False
        npred = int((b.get("options") or {}).get("num_predict") or 700)
        mini = b.get("mini") is True
        if mini:
            use_mem, npred = False, min(npred, 400)

        def fr(**k):
            d = {"model": TAG, "request_id": rid, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            d.update(k)
            return json.dumps(d, ensure_ascii=False) + "\n"

        async def gen():
            t0, n = time.time(), 0
            full = ""
            CANCEL.discard(rid); CANCEL.discard("*")
            yield fr(message={"role": "assistant", "content": ""}, done=False, nox_status="слушаю тебя…")
            async with (_lock_mini if mini else _lock):
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
                    srcs.append({"id": i + 1, "source": "S03", "category": "memory", "text": l[:300]})
                yield fr(message={"role": "assistant", "content": ""}, done=False, nox_sources=srcs, memory_reason=("найдено %d фрагм." % len(lines)) if lines else "в памяти ничего близкого", nox_status="чувствую…",
                         nox_event={"step": "memory", "text": ("найдено %d фрагм. памяти" % len(lines)) if lines else ("память не использовалась" if not use_mem else "в памяти ничего близкого")})
                yield fr(message={"role": "assistant", "content": ""}, done=False, nox_event={"step": "think", "text": "формулирую ответ"})
                if mini:
                    last = msgs_in[-1]["content"] if msgs_in else user
                    mm = [{"role": "system", "content": B.IDENTITY + " Ты мини-помощник интерфейса: отвечай по-русски, не более 4 предложений, без блока «Уверенность»."},
                          {"role": "user", "content": str(last)[:3000]}]
                else:
                    vol = B.self_vol(user)
                    mm = B.build_msgs(msgs_in, user, mem, vol)
                body = {"messages": mm, "max_tokens": max(64, min(npred, 900)), "temperature": 0.6, "id_slot": 1 if mini else 0, "cache_prompt": True, "stream": True,
                        "chat_template_kwargs": {"enable_thinking": False}}
                err = None
                try:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=10)) as c:
                        async with c.stream("POST", B.MODEL, json=body) as r:
                            async for line in r.aiter_lines():
                                if rid in CANCEL or "*" in CANCEL:
                                    break
                                if not line.startswith("data:"):
                                    continue
                                d = line[5:].strip()
                                if d == "[DONE]":
                                    break
                                try:
                                    t = json.loads(d)["choices"][0].get("delta", {}).get("content") or ""
                                except Exception:
                                    t = ""
                                if t:
                                    full += t
                                    n += 1
                                    yield fr(message={"role": "assistant", "content": t}, done=False)
                except Exception as e:
                    err = type(e).__name__
                    B.log("web_stream_error %s" % err)
                if not mini:
                    B.LAST_CHAT["t"] = time.time()
                if err and not full:
                    yield json.dumps({"error": "модель не ответила: " + err, "request_id": rid}, ensure_ascii=False) + "\n"
                    return
                hist = {"status": "HOLD", "reason": "ответ пуст или остановлен"}
                stopped = rid in CANCEL or "*" in CANCEL
                if full.strip() and not stopped:
                    try:
                        import s03_memory as S
                        await asyncio.to_thread(S.persist_turn, ("[mini] " + user) if mini else user, full.strip())
                        hist = {"status": "SAVED", "mini": mini}
                    except Exception as e:
                        hist = {"status": "HOLD", "reason": "S03: " + type(e).__name__}
                    if B.SOUL and not mini:
                        B.SOUL.log_turn(user, full.strip())
                CANCEL.discard(rid); CANCEL.discard("*")
                yield fr(message={"role": "assistant", "content": ""}, done=True, done_reason="stop" if not stopped else "stopped",
                         digest=hashlib.sha256(full.encode()).hexdigest(), frames=n, memory_history=hist,
                         total_duration=int((time.time() - t0) * 1e9), eval_count=n)

        return StreamingResponse(gen(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/app")
    async def a_app():
        return RedirectResponse("/web/chat.html")

    if os.path.isdir(WEBROOT):
        from fastapi.staticfiles import StaticFiles
        app.mount("/web", StaticFiles(directory=WEBROOT, html=True), name="web")
