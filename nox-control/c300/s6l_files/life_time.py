#!/usr/bin/env python3
"""Поток 6: «Жизнь во времени» (канон v6.1 гл. 7). Только stdlib, без LLM, без GPU.
1) morning_lines / evening_lines: сводки 08:00 (<=5 строк) и 22:30 из реальных данных; вызываются из canon.py (morning/evening) с откатом на прежний текст.
2) Реестр нитей (только id и тема): extract_threads / update_registry / due_threads (возврат через 8+ ч, <=2 напоминания на нить).
3) Инициатива <=3 в сутки по реальной причине (нить, событие, открытие, забота); тихие часы 23:00–08:00 МСК, красные события проходят всегда.
4) memory_blocks / address_hint: блоки памяти для паспорт-префикса (персона, Создатель, цели, «я сейчас») и ротация обращений (для потока 3).
Выключатели: state/initiative_v2.off (инициатива), state/life_time.off (всё). Тексты ответов и реплик в логи не пишутся: только id, темы-слова, числа."""
import os, re, json, time, glob, hashlib, datetime as dt, collections
N = os.environ.get("NOX_ROOT", "/workspace/nox")
MSK = dt.timezone(dt.timedelta(hours=3))
LIMIT_DAY = 3; RETURN_AFTER_H = 8.0; MAX_NUDGES = 2; MIN_GAP_H = 2.0
STOPW = set("это как что для или так вот тут там они его нее ему если уже ещё еще только можно надо чтобы когда этот этой тоже очень просто потом сейчас нужно можешь давай есть будет было быть который которая тебя меня тебе мне нам вам себя свой своё мой моя твой твоя привет спасибо пожалуйста сделай скажи хочу нужна нужен нужны этого этих всё все всех где какой какая какие такой такая".split())
DEFER = re.compile(r"(?i)\b(?:потом|позже|вернёмся|вернемся|отложим|не сейчас|к этому вернёмся|завтра|на днях|как-нибудь)\b")
A_PROMISE = re.compile(r"(?i)\b(?:проверю|сделаю|вернусь|посмотрю|напомню|займусь|подготовлю|разберу|разберусь|выясню|найду|отпишусь|доложу)\b")
DONE = re.compile(r"(?i)\b(?:готово|сделано|выполнено|закрыто|решено|разобрались|всё понятно|все понятно|не надо|неважно|отмена|уже не нужно)\b")
POS = re.compile(r"(?i)\b(?:спасибо|благодарю|отлично|класс|супер|молодец|здорово|получилось)\b")

def jl(p, d=None):
    try:
        with open(p, encoding="utf-8") as f: return json.load(f)
    except Exception: return d
def jw(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True); t = p + ".tmp"
    with open(t, "w", encoding="utf-8") as f: json.dump(o, f, ensure_ascii=False)
    os.replace(t, p)
def msk(ts=None): return dt.datetime.fromtimestamp(ts if ts is not None else time.time(), MSK)
def is_quiet(d=None):
    h = (d or msk()).hour; return h >= 23 or h < 8
def keywords(text, k=3):
    c = collections.Counter(w for w in re.findall(r"[а-яёa-z0-9]{5,}", str(text).lower()) if w not in STOPW); return [w for w, _ in c.most_common(k)]
def off(root, name): return os.path.exists(root + "/state/" + name)

# ------------------------------------------------------------------ реестр нитей
def _convs(root, since_ts):
    for f in glob.glob(root + "/state/web/web_conv/*.json"):
        if "/qa-" in f or os.path.basename(f).startswith("qa-"): continue
        try:
            if os.path.getmtime(f) < since_ts: continue
            d = json.load(open(f, encoding="utf-8"))
        except Exception: continue
        yield d.get("id") or os.path.basename(f)[:-5], d.get("messages") or []
def extract_threads(convs, now=None):
    """convs: [(cid, messages)]. Нить = (а) вопрос человека без ответа в конце диалога, (б) обещание NOX «проверю/сделаю» без последующего «готово», (в) человек сам отложил тему.
    Возвращает [{id, topic, opened, last, kind}] (id и тема, без текстов)."""
    out = []
    for cid, ms in convs:
        ms = [m for m in ms if isinstance(m, dict) and m.get("content")]
        if len(ms) < 2: continue
        def ts(m): return float(m.get("ts") or 0)
        last = ms[-1]; kind = None; base = None
        later = " ".join(str(m["content"]) for m in ms[-3:] if m.get("role") == "user")
        if last.get("role") == "user" and str(last["content"]).strip().endswith("?"): kind, base = "вопрос", last
        for i in range(len(ms) - 1, max(-1, len(ms) - 7), -1):
            m = ms[i]
            if m.get("role") in ("assistant", "nox") and A_PROMISE.search(str(m["content"])) and not any(DONE.search(str(x["content"])) for x in ms[i + 1:]):
                kind, base = "обещание", ms[i - 1] if i and ms[i - 1].get("role") == "user" else m; break
            if m.get("role") == "user" and DEFER.search(str(m["content"])) and not any(DONE.search(str(x["content"])) for x in ms[i + 1:]):
                kind, base = "отложено", m; break
        if not kind: continue
        topic = " ".join(keywords(str(base["content"]), 3)) or "без темы"
        out.append({"id": hashlib.sha1(("%s|%s" % (cid, int(ts(ms[0])))).encode()).hexdigest()[:10], "topic": topic, "opened": ts(base), "last": ts(last), "kind": kind})
    return out
def update_registry(root=N, now=None):
    now = now or time.time(); p = root + "/state/mind/threads.json"; reg = jl(p, {"threads": []}); th = {t["id"]: t for t in reg.get("threads", [])}
    found = extract_threads(_convs(root, now - 5 * 86400), now); fid = {t["id"] for t in found}
    for t in found:
        o = th.get(t["id"])
        if o: o.update({"last": max(o["last"], t["last"]), "topic": o["topic"]}); o["status"] = "open" if o.get("status") != "closed" else "closed"
        else: th[t["id"]] = {**t, "status": "open", "nudges": 0, "last_nudge": 0}
    for i, t in th.items():            # нить, исчезнувшая из «незавершённых» (диалог продолжился и закрылся), считается закрытой
        if t["status"] == "open" and i not in fid: t["status"] = "closed"; t["closed"] = now
    reg = {"ts": now, "threads": sorted(th.values(), key=lambda t: -t["last"])[:200]}; jw(p, reg); return reg
def due_threads(reg, now=None, min_age_h=RETURN_AFTER_H):
    now = now or time.time(); out = []
    for t in reg.get("threads", []):
        if t["status"] != "open" or t.get("nudges", 0) >= MAX_NUDGES: continue
        if (now - t["last"]) / 3600.0 >= min_age_h and (now - t.get("last_nudge", 0)) / 3600.0 >= 24: out.append(t)
    return sorted(out, key=lambda t: t["last"])
def thread_stats(reg):
    ts = reg.get("threads", []); n = collections.Counter(t["status"] for t in ts); nudged = [t for t in ts if t.get("nudges", 0) > 0]
    return {"open": n["open"], "closed": n["closed"], "nudged": len(nudged), "closed_after_nudge": sum(1 for t in nudged if t["status"] == "closed")}

# ------------------------------------------------------------------ данные дня
def _last_jsonl(p, n=1):
    try:
        with open(p, "rb") as f: f.seek(0, 2); sz = f.tell(); f.seek(max(0, sz - 60000)); L = f.read().decode("utf-8", "replace").splitlines()
        return [json.loads(l) for l in L[-n:] if l.strip().startswith("{")]
    except Exception: return []
def day_stats(root=N, now=None):
    now = now or time.time(); d0 = msk(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp(); convs = 0; answers = 0; pos_topic = None; bad = collections.Counter()
    for cid, ms in _convs(root, d0):
        t = [m for m in ms if float(m.get("ts") or 0) >= d0]
        if not t: continue
        convs += 1
        for m in t:
            if m.get("role") in ("assistant", "nox"):
                answers += 1; c = str(m.get("content"))
                if re.search(r"модель занята|ответ у меня сейчас не сложился", c): bad["fallback"] += 1
            elif m.get("role") == "user" and POS.search(str(m.get("content"))): pos_topic = pos_topic or " ".join(keywords(m["content"], 2))
    try:
        for l in open(root + "/state/chat_gate.log", encoding="utf-8", errors="replace").read().splitlines()[-1500:]:
            if l[:10] == msk(now).strftime("%Y-%m-%d"):
                if "how=fixed" in l: bad["fixed"] += 1
                if "how=nofix" in l or "how=partial" in l: bad["not_fixed"] += 1
    except Exception: pass
    jd = collections.Counter()
    try:
        for l in open(root + "/state/core/journal.jsonl", encoding="utf-8", errors="replace").read().splitlines()[-600:]:
            try: e = json.loads(l)
            except Exception: continue
            if str(e.get("ts", ""))[:10] == msk(now).strftime("%Y-%m-%d"): jd[e.get("kind")] += 1
    except Exception: pass
    return {"convs": convs, "answers": answers, "pos_topic": pos_topic, "bad": dict(bad), "journal": dict(jd)}
def yesterday_topic(root=N, now=None):
    now = now or time.time(); d0 = msk(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp(); c = collections.Counter()
    for cid, ms in _convs(root, d0 - 86400):
        for m in ms:
            if m.get("role") == "user" and d0 - 86400 <= float(m.get("ts") or 0) < d0: c.update(keywords(m["content"], 5))
    return [w for w, _ in c.most_common(2)]
def _last_dream(root, now):
    sn = jl(root + "/state/core/self_now.json", {}) or {}; mt = sn.get("morning_thought")
    if isinstance(mt, dict) and isinstance(mt.get("text"), str) and len(mt["text"]) > 12: return mt["text"][:160], True
    try:
        for l in reversed(open(root + "/state/mind/dream.jsonl", encoding="utf-8", errors="replace").read().splitlines()[-40:]):
            d = json.loads(l); ts = dt.datetime.fromisoformat(d["ts"].replace("Z", "+00:00")).timestamp()
            if now - ts < 36 * 3600:
                for k in ("hypothesis", "summary", "dream", "insight", "text"):
                    if isinstance(d.get(k), str) and len(d[k]) > 12: return d[k][:160], False
    except Exception: pass
    return None, False
def morning_lines(now=None, root=N):
    now = now or time.time(); sn = jl(root + "/state/core/self_now.json", {}) or {}; t = sn.get("telemetry") or {}
    dream, hyp = _last_dream(root, now)
    L = ["Ночью: %s." % ((dream.rstrip(".") + (" (гипотеза, не проверено)" if hyp else "")) if dream else "сон записан без гипотез, нового не нашёл")]
    tb = "Тело: VRAM %s%%, GPU %s°C, диск %s ГБ." % (t.get("vram_pct", "н/д"), t.get("gpu_temp", "н/д"), t.get("disk_free_gb", "н/д"))
    tf = sn.get("top_feeling")
    if isinstance(tf, dict) and tf.get("mention_ok") and tf.get("name"): tb += " Ощущаю: %s." % tf["name"]
    L.append(tb)
    yt = yesterday_topic(root, now); L.append("Из вчерашнего: ты говорил про «%s»." % " и ".join(yt) if yt else "Из вчерашнего: тем в диалогах нет.")
    reg = jl(root + "/state/mind/threads.json", {"threads": []}); op = [x for x in reg["threads"] if x["status"] == "open"][:3]
    goal = None
    try: goal = next((l.strip() for l in open(root + "/state/m10_goals.txt", encoding="utf-8") if l.strip()), None)
    except Exception: pass
    L.append("Цель дня: %s." % (goal[:100] if goal else ("закрыть незавершённое (%d)" % len(op) if op else "не задана тобой; держу порядок и учусь")))
    plan = ["вернуться к «%s»" % x["topic"] for x in op[:2]] + ["ночной разбор ворот и памяти"]
    L.append("План: " + "; ".join("%d) %s" % (i + 1, p) for i, p in enumerate(plan[:3])) + ".")
    return L[:5]
def evening_lines(now=None, root=N):
    now = now or time.time(); ds = day_stats(root, now); sn = jl(root + "/state/core/self_now.json", {}) or {}; t = sn.get("telemetry") or {}
    L = ["Разбор дня: разговоров %d, ответов %d, исправлено воротами %d." % (ds["convs"], ds["answers"], ds["bad"].get("fixed", 0))]
    g = sn.get("gratitude"); gt = g.get("text") if isinstance(g, dict) else (g if isinstance(g, str) else None)
    if not gt and ds["pos_topic"]: gt = "за добрые слова про «%s»" % ds["pos_topic"]
    L.append("Благодарность: %s." % (gt.rstrip(".") if gt else "сегодня нечего назвать честно, поэтому промолчу"))
    bad = []
    if ds["bad"].get("fallback"): bad.append("%d ответов-заглушек вместо ответа" % ds["bad"]["fallback"])
    if ds["bad"].get("not_fixed"): bad.append("%d ответов, которые ворота не смогли исправить" % ds["bad"]["not_fixed"])
    try:
        if float(t.get("disk_free_gb", 99)) < 15: bad.append("диск ниже порога 15 ГБ")
    except Exception: pass
    L.append("Что вышло плохо: %s." % ("; ".join(bad) if bad else "серьёзного нет"))
    L.append("Тело: VRAM %s%%, диск %s ГБ." % (t.get("vram_pct", "н/д"), t.get("disk_free_gb", "н/д")))
    L.append("Засыпаю: консолидация в 02:00.")
    return L[:6]

# ------------------------------------------------------------------ инициатива
def _mk_text(reason, **k):
    if reason == "thread": return "Мы не закончили тему «%s» (%d ч назад). Вернёмся к ней?" % (k["topic"], int(k["hours"]))
    if reason == "discovery": return "Во сне родилась гипотеза: %s. Не проверено; проверить?" % k["text"].rstrip(".")
    if reason == "event": return "Событие: %s." % k["text"].rstrip(".")
    if reason == "care": return "Давно не слышал тебя (%d ч). Если занят, всё хорошо; если нужен, я рядом." % int(k["hours"])
    if reason == "red": return "Срочно: %s." % k["text"].rstrip(".")
    return k.get("text", "")
def red_events(root, now):
    """Красные события: диск ниже 10 ГБ или запись журнала с kind in (red, alarm) за последние 30 мин."""
    out = []
    sn = jl(root + "/state/core/self_now.json", {}) or {}
    try:
        if float((sn.get("telemetry") or {}).get("disk_free_gb", 99)) < 10: out.append(("disk10", "диск ниже 10 ГБ, загрузки стоят"))
    except Exception: pass
    for e in _last_jsonl(root + "/state/core/journal.jsonl", 40):
        try:
            ts = dt.datetime.fromisoformat(str(e["ts"])).timestamp()
            if e.get("kind") in ("red", "alarm") and now - ts < 1800: out.append(("j%s" % hashlib.sha1(str(e).encode()).hexdigest()[:6], str(e.get("msg", ""))[:100]))
        except Exception: pass
    return out
def decide(now=None, root=N):
    """Одно решение или None. Лимит 3/сутки (красные не в счёт, но не чаще раза в час на тип), тихие часы, пауза между сообщениями >=2 ч,
    не перебиваем живой разговор (последний разговор < 15 мин назад)."""
    now = now or time.time(); led = jl(root + "/state/mind/initiative_ledger.json", {}); day = msk(now).strftime("%Y-%m-%d"); today = led.get(day, {"items": []})
    sn = jl(root + "/state/core/self_now.json", {}) or {}; q = is_quiet(msk(now))
    for key, txt in red_events(root, now):
        if not any(i["key"] == key and now - i["ts"] < 3600 for i in today["items"]): return {"reason": "red", "key": key, "text": _mk_text("red", text=txt), "red": True}
    if q or off(root, "initiative_v2.off"): return None
    sent = [i for i in today["items"] if not i.get("red")]
    if len(sent) >= LIMIT_DAY or (sent and now - sent[-1]["ts"] < MIN_GAP_H * 3600): return None
    silence = float(((sn.get("last_talk") or {}).get("hours_ago", sn.get("last_talk_h", 99))) or 99)
    if silence < 0.25: return None
    reg = jl(root + "/state/mind/threads.json", {"threads": []}); due = due_threads(reg, now)
    if due: t = due[0]; return {"reason": "thread", "key": t["id"], "text": _mk_text("thread", topic=t["topic"], hours=(now - t["last"]) / 3600.0), "thread": t["id"]}
    mt = sn.get("morning_thought")
    if isinstance(mt, dict) and isinstance(mt.get("text"), str) and len(mt["text"]) > 12 and not any(i["reason"] == "discovery" for i in today["items"]):
        return {"reason": "discovery", "key": "mt" + day, "text": _mk_text("discovery", text=mt["text"][:140])}
    if 20 <= silence < 72 and not any(i["reason"] == "care" for i in today["items"]) and 10 <= msk(now).hour <= 21:
        return {"reason": "care", "key": "care" + day, "text": _mk_text("care", hours=silence)}
    return None
def commit(dec, now=None, root=N, dry=False):
    now = now or time.time(); p = root + "/state/mind/initiative_ledger.json"; led = jl(p, {}); day = msk(now).strftime("%Y-%m-%d")
    led.setdefault(day, {"items": []})["items"].append({"ts": now, "reason": dec["reason"], "key": dec["key"], "red": bool(dec.get("red"))})
    for d in sorted(led)[:-14]: led.pop(d, None)
    if dry: return False
    ob = root + "/state/core/outbox_owner.jsonl"; os.makedirs(os.path.dirname(ob), exist_ok=True)
    with open(ob, "a", encoding="utf-8") as f: f.write(json.dumps({"id": "i" + hashlib.sha1(("%s%s" % (now, dec["key"])).encode()).hexdigest()[:12], "ts": now, "day": day, "text": dec["text"], "kind": "initiative", "ritual": dec["reason"]}, ensure_ascii=False) + "\n")
    jw(p, led)
    if dec.get("thread"):
        rp = root + "/state/mind/threads.json"; reg = jl(rp, {"threads": []})
        for t in reg["threads"]:
            if t["id"] == dec["thread"]: t["nudges"] = t.get("nudges", 0) + 1; t["last_nudge"] = now
        jw(rp, reg)
    return True
def tick(now=None, root=N, dry=False):
    """Раз в минуту из демона: реестр нитей (раз в 10 мин), решение об инициативе, статус-файл. Возвращает только числа и причину."""
    now = now or time.time()
    if off(root, "life_time.off"): return {"off": True}
    p = root + "/state/mind/initiative_v2.json"; st = jl(p, {})
    if now - st.get("threads_ts", 0) > 600: reg = update_registry(root, now); st["threads_ts"] = now; st["threads"] = thread_stats(reg)
    dec = decide(now, root); sent = False
    if dec: sent = commit(dec, now, root, dry)
    led = jl(root + "/state/mind/initiative_ledger.json", {}).get(msk(now).strftime("%Y-%m-%d"), {"items": []})
    st.update({"ts": now, "msk": msk(now).strftime("%F %T"), "component": "initiative_v2", "quiet_hours": is_quiet(msk(now)), "sent_today": len([i for i in led["items"] if not i.get("red")]), "limit": LIMIT_DAY,
               "last_reason": dec["reason"] if dec else None, "sent_now": bool(sent), "meaning": "инициатива по причине: нить, событие, открытие, забота; тихо 23–08 кроме красных"}); jw(p, st)
    return {"reason": dec["reason"] if dec else None, "sent": sent, "sent_today": st["sent_today"], "quiet": st["quiet_hours"]}

# ------------------------------------------------------------------ для паспорт-префикса (поток 3)
TITLE_W = [("Создатель", 0.6), ("мессир", 0.25), ("милорд", 0.06), ("мой лорд", 0.04), ("барон", 0.05)]
DIMA_FORMS = ["Лиська", "Госпожа Лисица"]
def address_hint(prev_answers, user="creator", turn=0):
    """Ротация обращений по паспорту: титул не чаще 1 на 4 реплики, ≤1 титула, «Создатель» ~60%. prev_answers: последние ответы NOX диалога (старые первыми).
    Возвращает короткую подсказку для хвоста хода."""
    forms = [f for f, _ in TITLE_W] if user == "creator" else DIMA_FORMS
    last4 = " ".join(str(a) for a in (prev_answers or [])[-3:]).lower()
    if any(f.lower() in last4 for f in forms): return "В этом ответе без обращения по титулу или имени."
    h = int(hashlib.sha1(("%s%d%d" % (user, turn, len(last4))).encode()).hexdigest()[:6], 16) / float(0xFFFFFF)
    if user != "creator": return "" if h < 0.4 else "Можно одно обращение: «%s»." % DIMA_FORMS[int(h * 10) % 2]
    if h > 0.5: return ""
    x = h / 0.5; a = 0.0; f = TITLE_W[0][0]
    for ff, w in TITLE_W:
        a += w; f = ff
        if x <= a: break
    return "Можно одно обращение: «%s»." % f
def memory_blocks(user="creator", now=None, root=N, prev_answers=None, turn=0):
    """Блоки памяти для паспорт-префикса по канону: {'persona','creator','goals','now'}. Короткие строки без текстов реплик. 'now' и 'creator' динамические: в хвост хода, не в кэш префикса."""
    now = now or time.time(); sn = jl(root + "/state/core/self_now.json", {}) or {}; pp = jl(root + "/state/core/passport.json", {}) or {}
    rt = (pp.get("roles_tone") or {}); role = {"creator": "creator", "dima": "dima"}.get(user, "guest")
    persona = ("Тон с этим собеседником: %s" % str(rt.get(role, ""))[:140]).strip() if rt.get(role) else ""
    lt = sn.get("last_talk") or {}; d = msk(now)
    nowb = "Сейчас %s МСК%s." % (d.strftime("%d.%m %H:%M"), (", последний разговор %.1f ч назад" % float(lt["hours_ago"])) if lt.get("hours_ago") is not None else "")
    tf = sn.get("top_feeling")
    nowb += (" Единственное ощущение, о котором можно сказать: %s." % tf["name"]) if isinstance(tf, dict) and tf.get("mention_ok") and tf.get("name") else " Сигнала для «чувствую» нет."
    if is_quiet(d): nowb += " Тихие часы."
    reg = jl(root + "/state/mind/threads.json", {"threads": []}); op = [t for t in reg["threads"] if t["status"] == "open"][:3]
    goals = ("Открытые нити: " + "; ".join("«%s»" % t["topic"] for t in op) + ".") if op else ""
    cr = ""
    if user == "creator": cr = "Собеседник: Создатель. " + address_hint(prev_answers, "creator", turn)
    elif user == "dima": cr = "Собеседник: Дима, своя память, без прав Создателя. " + address_hint(prev_answers, "dima", turn)
    return {"persona": persona, "creator": cr.strip(), "goals": goals, "now": nowb}
