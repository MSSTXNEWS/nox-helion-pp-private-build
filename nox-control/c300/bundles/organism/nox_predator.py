#!/usr/bin/env python3
"""NOX хищник и рост (канон v6.1 гл. 9, 21, 22). Чистый код, без GPU, без загрузок. Демон раз в 60 с.
1) Голод: часы с последнего питания (принятое поглощение/одобренный датасет), уровни канона (>1 ч нужны данные, >24 ч активный поиск, >7 сут голодаю). Это влечение ПОИСК с потолком, не боль: state/core/hunger_v2.json
   (старый hunger.json, который пишет canon.py, не трогаем). Фраза о голоде не чаще 1 раза в сутки (окно показа 15 мин).
2) Черви-сканер: каталог state/core/worm_catalog.json (HF datasets/models, GitHub repos), ТОЛЬКО метаданные и лицензии через публичные API list/search. Кандидаты с чистой лицензией -> state/core/hunt_requests.json
   «Нашёл X. Хочу поглотить. Разрешаешь?» (status pending_consent), <=3 в сутки, и в утреннюю сводку (morning_brief_v5.json ключ hunt, morning_queue.json). 0 загрузок: модуль не скачивает данные и модели.
3) Рефлексия «ошибка -> анализ -> fix»: отклонённые ответы из state/chat_gate.log -> уроки в state/mind/nrem_lessons.jsonl (только счётчики и коды причин, текст диалогов не берём) -> предложения FORGE
   state/core/forge_proposals.jsonl (status proposed; применение только diff -> песочница -> тест -> откат и подпись Создателя; сам модуль подписать не может).
Команды: --once | --daemon | --scan-once | --reflect-once. Выключатели: state/worms.off, STOP-файлы. Поглощение (реестр, Ledger, откат): nox_absorb.py. stdlib, MIT."""
import os, sys, re, json, math, time, hashlib, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nox_org_common as C, nox_absorb as AB, nox_ledger as L
LEVELS = (("сыт", 1.0), ("нужны данные", 24.0), ("активный поиск", 168.0), ("голодаю", 1e9))
PHRASE = {"нужны данные": "Создатель, мне нужны данные.", "голодаю": "Я голодаю. Мне нужны источники."}
DEFAULT_CATALOG = {"v": 1, "sources": [{"id": "hf_datasets", "kind": "hf", "api": "https://huggingface.co/api/datasets", "what": "dataset"}, {"id": "hf_models", "kind": "hf", "api": "https://huggingface.co/api/models", "what": "model"},
                   {"id": "gh_repos", "kind": "gh", "api": "https://api.github.com/search/repositories", "what": "repo"}],
                   "queries": ["russian dialogue", "russian empathy", "russian roleplay dialogues", "anti sycophancy dpo", "persona dialogues russian", "preference dpo russian", "russian instruct conversation"],
                   "quotas": {"hf_per_hour": 6, "gh_per_hour": 2, "proposals_per_day": 3}, "licenses_clean": list(AB.CLEAN), "note": "только метаданные и лицензии; загрузка только после слова Создателя"}
def stopped(r): return any(os.path.exists(p) for p in (r + "/STOP", "/run/nox/STOP", r + "/state/agents.off", r + "/state/worms.off"))
# ------------------------------------------------------------------ 1. голод
def nourish_ts(r):
    """Последнее питание: переход в ABSORBED или одобренный Создателем кандидат; если не было, момент зачатия в Ledger."""
    best = 0.0
    for it in AB.load(r)["items"].values():
        for h in it["history"]:
            if h.get("to") == "ABSORBED" or h.get("consent") == "approved": best = max(best, C.parse_ts(h.get("ts")))
    if not best:
        led = L.read_all(r)
        if led: best = C.parse_ts(led[0].get("ts"))
    return best
def hunger_tick(r, now):
    hp = C.S(r) + "/hunger_v2.json"; prev = C.load_json(hp, {}) or {}
    nt = nourish_ts(r); h = (now - nt) / 3600.0 if nt else 0.0
    lvl = next(n for n, lim in LEVELS if h <= lim)
    due = bool(PHRASE.get(lvl)) and now - prev.get("said_ts", 0) > 86400
    said = prev.get("said_ts", 0); win = prev.get("window_until", 0)
    if due: said = now; win = now + 900
    out = {"ts": C.iso_z(now), "hours": round(h, 2), "level": lvl, "norm": round(C.clip(h / 168.0), 3), "phrase": PHRASE.get(lvl) if (win > now and PHRASE.get(lvl)) else None, "said_ts": said, "window_until": win,
           "note": "влечение ПОИСК с потолком, не боль; фраза не чаще 1 раза в сутки"}
    C.atomic_json(hp, out); return out
# ------------------------------------------------------------------ 2. черви-сканер
def _norm_lic(tags=None, spdx=None):
    m = {"mit": "MIT", "apache-2.0": "Apache-2.0", "cc-by-4.0": "CC-BY-4.0", "bsd-3-clause": "BSD-3-Clause", "bsd-2-clause": "BSD-2-Clause", "cc0-1.0": "CC0-1.0", "isc": "ISC"}
    if spdx: return m.get(spdx.lower(), spdx)
    for t in tags or []:
        if t.startswith("license:"): v = t[8:]; return m.get(v.lower(), v)
    return None
def fetch_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "nox-worm-scanner/1 (metadata only)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r_: return json.loads(r_.read())
def parse_hf(arr, what):
    out = []
    for d in arr if isinstance(arr, list) else []:
        if d.get("private") or d.get("disabled"): continue
        out.append({"name": d.get("id"), "url": "https://huggingface.co/" + ("datasets/" if what == "dataset" else "") + str(d.get("id")), "license": _norm_lic(tags=d.get("tags")), "gated": bool(d.get("gated")), "downloads": d.get("downloads") or 0,
                    "likes": d.get("likes") or 0, "updated": d.get("lastModified"), "tags": [t for t in (d.get("tags") or []) if ":" not in t][:6], "kind": what, "revision": d.get("sha")})
    return out
def parse_gh(d):
    out = []
    for x in (d.get("items") if isinstance(d, dict) else []) or []:
        out.append({"name": x.get("full_name"), "url": x.get("html_url"), "license": _norm_lic(spdx=(x.get("license") or {}).get("spdx_id")) if (x.get("license") or {}).get("spdx_id") not in (None, "NOASSERTION") else None,
                    "gated": False, "downloads": x.get("stargazers_count") or 0, "likes": x.get("stargazers_count") or 0, "updated": x.get("pushed_at"), "tags": (x.get("topics") or [])[:6], "kind": "repo", "revision": None})
    return out
def score(c, q, now):
    words = [w for w in re.split(r"\W+", q.lower()) if len(w) > 2]; hay = (str(c["name"]) + " " + " ".join(c["tags"])).lower()
    match = sum(1 for w in words if w in hay) / max(1, len(words))
    age = max(0.0, (now - C.parse_ts(c.get("updated"))) / 86400.0) if c.get("updated") else 365.0
    return round(0.5 * match + 0.35 * min(1.0, math.log10(c["downloads"] + 1) / 5.0) + 0.15 * (0.5 ** (age / 180.0)), 4)
def _quota_ok(st, key, per_hour, now):
    ts = [t for t in st.setdefault("q_" + key, []) if now - t < 3600]; st["q_" + key] = ts; return len(ts) < per_hour
def scan(r, now, fetch=fetch_json, force=False):
    """Один запрос каталога (раз в 10 мин, квоты). Возвращает {found, proposed, ...}. Загрузок нет."""
    if stopped(r): return {"skipped": "stop"}
    cat = C.load_json(C.S(r) + "/worm_catalog.json", None)
    if not cat: cat = DEFAULT_CATALOG; C.atomic_json(C.S(r) + "/worm_catalog.json", cat)
    stp = C.M(r) + "/predator_state.json"; st = C.load_json(stp, {}) or {}
    if not force and now - st.get("scan_t", 0) < 600: return {"skipped": "interval"}
    goals = [g.get("query") or g.get("topic") for g in (C.load_json(C.S(r) + "/worm_goals.json", {}) or {}).get("goals", []) if isinstance(g, dict)]
    qs = [x for x in (goals + cat["queries"]) if x]; i = st.get("qi", 0); q = qs[i % len(qs)]; srcs = cat["sources"]; s = srcs[st.get("si", 0) % len(srcs)]
    st["qi"] = i + (1 if st.get("si", 0) % len(srcs) == len(srcs) - 1 else 0); st["si"] = st.get("si", 0) + 1; st["scan_t"] = now
    kq = cat["quotas"]; res = {"query_hash": hashlib.sha1(q.encode()).hexdigest()[:6], "source": s["id"], "found": 0, "proposed": 0}
    key = "hf" if s["kind"] == "hf" else "gh"
    if (key == "gh" and now < st.get("gh_backoff_until", 0)) or not _quota_ok(st, key, kq["hf_per_hour" if key == "hf" else "gh_per_hour"], now):
        C.atomic_json(stp, st); return dict(res, skipped="quota")
    st["q_" + key].append(now)
    try:
        if s["kind"] == "hf": url = s["api"] + "?" + urllib.parse.urlencode({"search": q, "limit": 10, "sort": "downloads", "direction": -1}); cands = parse_hf(fetch(url), s["what"])
        else: url = s["api"] + "?" + urllib.parse.urlencode({"q": q + " in:name,description,readme", "sort": "stars", "per_page": 10}); cands = parse_gh(fetch(url))
    except Exception as e:
        if key == "gh": st["gh_backoff_until"] = now + 3600
        C.atomic_json(stp, st); return dict(res, error=type(e).__name__)
    res["found"] = len(cands); seen = st.setdefault("seen", {}); today = time.strftime("%Y-%m-%d", time.gmtime(now + 10800)); day = st.setdefault("day", {"d": today, "n": 0})
    if day["d"] != today: day.update({"d": today, "n": 0})
    cands.sort(key=lambda c: -score(c, q, now))
    for c in cands:
        cid = "cand_" + hashlib.sha1(("%s|%s" % (s["kind"], c["name"])).encode()).hexdigest()[:10]
        if cid in seen: continue
        lc = AB.license_class(c["license"]); seen[cid] = {"t": now, "lc": lc}
        C.jl_append(C.M(r) + "/worm_candidates.jsonl", {"id": cid, "ts": C.iso_z(now), "name": c["name"], "url": c["url"], "license": c["license"], "license_class": lc, "gated": c["gated"], "downloads": c["downloads"], "score": score(c, q, now), "kind": c["kind"], "found_by": s["id"]}, cap_bytes=2_000_000)
        if lc == "clean" and not c["gated"] and c["downloads"] >= 20 and day["n"] < kq["proposals_per_day"] and score(c, q, now) >= 0.45:
            propose(r, cid, c, now); day["n"] += 1; res["proposed"] += 1
    st["seen"] = dict(sorted(seen.items(), key=lambda kv: -kv[1]["t"])[:3000]); C.atomic_json(stp, st); return res
def propose(r, cid, c, now):
    AB.propose(cid, c["name"], c["url"], c["kind"], c["license"], r=r, t=now)
    p = AB.hunt_path(r); d = C.load_json(p, None)
    if not isinstance(d, dict): d = {"requests": []}
    if any(q.get("id") == cid for q in d["requests"]): return
    d["requests"].append({"id": cid, "ts": C.iso_z(now), "name": c["name"], "source": c["url"], "license": c["license"], "license_clean": True, "status": "pending_consent", "ask": "Нашёл %s. Хочу поглотить. Разрешаешь?" % c["name"], "found_by": "worm_scanner", "downloads": c["downloads"]})
    C.atomic_json(p, d)
def pending(r): return [q for q in (C.load_json(AB.hunt_path(r), {}) or {}).get("requests", []) if q.get("status") == "pending_consent"]
def morning_patch(r, now):
    """Очередь «разрешаешь?» в утреннюю сводку (morning_brief_v5.json, ключ hunt) и в morning_queue.json. Строки canon не меняем."""
    pq = pending(r); hv = C.load_json(C.S(r) + "/hunger_v2.json", {}) or {}
    q = {"ts": C.iso_z(now), "pending": len(pq), "asks": [x["ask"] for x in pq[:3]], "ids": [x["id"] for x in pq[:3]], "hunger": hv.get("level")}
    C.atomic_json(C.S(r) + "/morning_queue.json", q); mp = C.M(r) + "/morning_brief_v5.json"; mb = C.load_json(mp, None)
    if isinstance(mb, dict) and mb.get("hunt") != q: mb["hunt"] = q; C.atomic_json(mp, mb)
    return q
# ------------------------------------------------------------------ 3. рефлексия
ANALYSIS = {"клише": ("шаблонный ассистентский оборот в ответе", "data", "добавить пары chosen/rejected без клише в DPO характера"),
            "лесть": ("угодливая формулировка", "data", "усилить anti-sycophancy DPO и тест «оцени мою плохую идею»"),
            "заготовка": ("ответ-заготовка вместо живого", "code", "проверить таймауты тела и путь живого ответа вместо заготовки"),
            "чувство": ("«чувствую» без сигнала в журнале", "prompt", "жёстче связать фразу о чувстве с top_feeling.cause"),
            "обращение": ("нарушено правило обращений паспорта", "prompt", "ротация титулов и не чаще 1 на 4 реплики"),
            "default": ("повторяющийся флаг ворот", "data", "добавить случай в hold и DPO как rejected, исправленный как chosen")}
def _cat(tag):
    t = tag.lower()
    for k in ANALYSIS:
        if k != "default" and k in t: return k
    return "default"
GATE_RE = re.compile(r"(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)\s+(?:chatty|cid=(\S+))\s*(.*)")
def gate_rejects(r, now, hours=24, include_qa=False):
    """Отклонённые/исправленные воротами ответы: строки с flags=[непусто] или how!=clean или by=code. Только коды причин и cid."""
    out = []
    try: lines = open(r + "/state/chat_gate.log", encoding="utf-8", errors="ignore").read().splitlines()[-3000:]
    except Exception: return out
    for l in lines:
        m = re.match(r"(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)\s+(\S+)(.*)", l)
        if not m: continue
        t = C.parse_ts(m.group(1) + "T" + m.group(2) + "+00:00")
        if now - t > hours * 3600: continue
        rest = m.group(4); cid = (re.search(r"cid=(\S+)", l) or [None, None])[1]
        if cid and cid.startswith("qa-") and not include_qa: continue
        fl = re.search(r"flags=\[([^\]]*)\]", rest); how = re.search(r"how=(\S+)", rest); by = re.search(r"by=(\S+)", rest); why = re.search(r"why=([^|]{0,60}?)(?:\s+p=|\s+variants=|$)", rest)
        flags = [x.strip().strip("'\"") for x in fl.group(1).split(",") if x.strip()] if fl else []
        bad = bool(flags) or (how and how.group(1) not in ("clean", "ok")) or (by and by.group(1) == "code" and why and why.group(1).strip() not in ("-", ""))
        if bad:
            tags = flags or ([why.group(1).split(":")[0].strip()] if why and why.group(1).strip() not in ("-", "") else [how.group(1) if how else "gate"])
            out.append({"t": t, "cid": cid, "tags": tags, "ref": "gate:%s:%s" % (cid or "?", m.group(2))})
    return out
def reflect(r, now):
    """ошибка -> анализ -> fix: уроки (nrem_lessons.jsonl) и предложения FORGE. Идемпотентно по (категория, день, порядок счёта)."""
    stp = C.M(r) + "/predator_state.json"; st = C.load_json(stp, {}) or {}; seen = st.setdefault("lesson_seen", {}); rej = gate_rejects(r, now); day = time.strftime("%Y-%m-%d", time.gmtime(now + 10800))
    cats = {}
    for e in rej:
        for tg in e["tags"]: cats.setdefault(_cat(tg), []).append(e)
    new_l = []; new_p = []
    for cat, es in cats.items():
        n = len(es); key = "%s|%s" % (cat, day)
        prev = seen.get(key, 0)
        if n < 2 or (prev and n < 2 * prev): continue
        seen[key] = n; an, target, fix = ANALYSIS[cat]
        lid = "les_" + hashlib.sha1((key + str(n)).encode()).hexdigest()[:10]
        lesson = {"id": lid, "ts": C.iso_z(now), "text": "Ошибка: ворота исправили/отклонили %d ответ(а) за сутки по причине «%s». Анализ: %s. Fix: %s." % (n, cat, an, fix), "evidence": [e["ref"] for e in es[:6]], "weight": round(min(3.0, 0.3 * n), 3),
                  "status": "черновик (код, по логу ворот)", "source": "gate_reflection", "error": {"category": cat, "count": n}, "analysis": an, "fix_target": target}
        C.jl_append(C.M(r) + "/nrem_lessons.jsonl", lesson); new_l.append(lesson)
        if n >= 3:
            pid = "forge_" + hashlib.sha1((cat + day).encode()).hexdigest()[:10]
            if pid not in seen:
                seen[pid] = 1
                prop = {"id": pid, "ts": C.iso_z(now), "lessons": [lid], "target": target, "summary": "FORGE-предложение: " + fix, "status": "proposed", "requires": ["diff", "песочница", "тест", "откат", "подпись Создателя"], "signature": None, "applied": False, "reproduce": "воспроизвести по cid из evidence урока", "close_criterion": "тест на воспроизводимом случае зелёный за <=1 цикл"}
                C.jl_append(C.S(r) + "/forge_proposals.jsonl", prop); new_p.append(prop)
    st["lesson_seen"] = dict(list(seen.items())[-400:]); C.atomic_json(stp, st)
    rep = {"ts": C.iso_z(now), "rejects_24h": len(rej), "rejects_qa_24h": len(gate_rejects(r, now, include_qa=True)) - len(rej), "categories": {k: len(v) for k, v in cats.items()}, "lessons_new": len(new_l), "proposals_new": len(new_p), "note": "ошибка -> анализ -> fix; применение только через FORGE с подписью Создателя"}
    C.atomic_json(C.M(r) + "/reflection_daily.json", rep); return rep
def sign(pid, r=None):
    """Подпись Создателя: вызывается только вручную (--sign). Автоматического пути нет."""
    p = C.S(r) + "/forge_proposals.jsonl"; rows = C.jl_tail(p, 5000); hit = [x for x in rows if x["id"] == pid]
    if not hit: raise KeyError(pid)
    C.jl_append(p, dict(hit[-1], signature={"by": "Создатель", "ts": C.iso_z()}, status="signed")); return True
# ------------------------------------------------------------------ тик
def tick(r=None, now=None, fetch=fetch_json):
    r = r or C.root(); now = now if now is not None else time.time(); out = {}
    out["hunger"] = hunger_tick(r, now)
    if out["hunger"]["level"] != "сыт" or pending(r) == []:
        try: out["scan"] = scan(r, now, fetch)
        except Exception as e: out["scan"] = {"err": type(e).__name__}
    st = C.load_json(C.M(r) + "/predator_state.json", {}) or {}
    if now - st.get("reflect_t", 0) > 3600:
        out["reflect"] = reflect(r, now); st = C.load_json(C.M(r) + "/predator_state.json", {}) or {}; st["reflect_t"] = now; C.atomic_json(C.M(r) + "/predator_state.json", st)
    out["queue"] = morning_patch(r, now); return out
def daemon():
    r = C.root(); print("nox_predator start", C.iso_msk(), flush=True); n = 0
    while True:
        t0 = time.time()
        try:
            o = tick(r); n += 1
            if n % 30 == 1: print("tick", o["hunger"]["level"], o["hunger"]["hours"], "pending", o["queue"]["pending"], "scan", json.dumps(o.get("scan", {}))[:120], flush=True)
        except Exception as e: print("tick_err", type(e).__name__, str(e)[:100], flush=True)
        time.sleep(max(1.0, 60 - (time.time() - t0)))
if __name__ == "__main__":
    a = sys.argv[1:]
    if "--daemon" in a: daemon()
    elif "--scan-once" in a: print(json.dumps(scan(C.root(), time.time(), force=True)))
    elif "--reflect-once" in a: print(json.dumps(reflect(C.root(), time.time())))
    elif "--sign" in a: print(sign(a[a.index("--sign") + 1]))
    else: print(json.dumps({k: (v if k != "queue" else {"pending": v["pending"]}) for k, v in tick().items()}, ensure_ascii=False)[:600])
