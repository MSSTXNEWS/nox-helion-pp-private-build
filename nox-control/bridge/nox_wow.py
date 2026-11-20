"""NOX WOW-слой B: скептик, сон, карта неизвестного, журнал решений, стиль владельца, напоминания, план, дрейф личности.
Без внешних зависимостей. Всё пишет в /root/nox/state/*.jsonl; ничего не применяет само выше уровня L1.
Принципы: честность (не заявляем сознание), новые факты советников только в карантин, обучение — факты старше 7 дней и >=1-2 независимых источника."""
import json, os, re, time

D = "/root/nox/state"
os.makedirs(D, exist_ok=True)
F = {k: D + "/" + v for k, v in dict(
    turns="turns.jsonl", journal="self_journal.jsonl", notes_adv="teacher_notes.jsonl", feedback="feedback.jsonl", facts="owner_facts.jsonl",
    unknown="unknown.jsonl", decisions="decisions.jsonl", sleep="sleep.jsonl", drift="drift_log.jsonl", notes="mini_notes.jsonl",
    remind="reminders.jsonl", visit="last_visit.json", style="style_profile.json", sleepstate="sleep_state.json", regress="regress.json").items()}
TZ_H = 3  # Создатель в МСК
DAY = 86400


def append(p, o):
    try:
        with open(p, "a", encoding="utf-8") as f: f.write(json.dumps(o, ensure_ascii=False) + "\n")
    except Exception: pass


def tail(p, n=100):
    try: return [json.loads(l) for l in open(p, encoding="utf-8").read().splitlines()[-n:] if l.strip()]
    except Exception: return []


def jread(p, d=None):
    try: return json.load(open(p))
    except Exception: return d


def jwrite(p, o):
    try:
        t = p + ".tmp"; json.dump(o, open(t, "w"), ensure_ascii=False); os.replace(t, p)
    except Exception: pass


# ---------- уровни изменяемости личности (L0–L3) ----------
LEVELS = {
    "L0": "хартия и честность: не меняется никогда",
    "L1": "стиль ответа (длина, тон): NOX меняет сам, каждое изменение в журнале дрейфа, не чаще 1 раза в сутки",
    "L2": "правила поведения, инициатива: только предложение, применяет Создатель",
    "L3": "веса модели (LoRA/QLoRA): только офлайн, факты старше 7 дней, с подтверждением Создателя",
}
_L0 = ("хартия", "честност", "безопасност", "stop", "согласи", "создател", "ценност")
_L3 = ("lora", "qlora", "вес", "дообуч", "обучен")
_L2 = ("правил", "инициатив", "поведен", "характер", "личност")


def level_of(text):
    t = (text or "").lower()
    if any(w in t for w in _L0): return "L0"
    if any(w in t for w in _L3): return "L3"
    if any(w in t for w in _L2): return "L2"
    return "L1"


# ---------- стиль владельца (слой промпта) ----------
def style_profile(force=False):
    """Короткая строка о том, как писать Создателю. Считается из реальных ходов и 👍/👎; кэш 10 мин; изменение пишется в журнал дрейфа (L1, <=1 раз/сутки)."""
    st = jread(F["style"], {}) or {}
    if not force and time.time() - st.get("t", 0) < 600 and st.get("line"): return st["line"]
    turns = tail(F["turns"], 60)
    ws = [len(str(t.get("u", "")).split()) for t in turns if t.get("u")]
    avg = sum(ws) / len(ws) if ws else 0
    fb = tail(F["feedback"], 200)
    up = [len(str(f.get("a", ""))) for f in fb if f.get("v") == 1]
    dn = [len(str(f.get("a", ""))) for f in fb if f.get("v") == -1]
    cap = 6
    if up and dn and sum(dn) / len(dn) > 1.25 * sum(up) / len(up): cap = 4   # длинные ответы чаще получают 👎
    elif up and (not dn or sum(up) / len(up) > 1.25 * sum(dn) / len(dn)): cap = 8
    if avg and avg < 8 and cap > 5: cap = 5
    line = "Стиль Создателя: по-русски, кратко, по делу, без воды; обычно до %d предложений, подробнее только если попросит." % cap
    old = st.get("line")
    if old and old != line and time.time() - st.get("changed", 0) < DAY:
        line = old  # дрейф-лимит L1: не чаще раза в сутки
    elif old != line:
        append(F["drift"], {"t": int(time.time()), "level": "L1", "what": "style_line", "before": old, "after": line, "basis": {"turns": len(turns), "avg_words": round(avg, 1), "up": len(up), "down": len(dn)}})
        st["changed"] = int(time.time())
    st.update(t=int(time.time()), line=line); jwrite(F["style"], st)
    return line


# ---------- мода и режимы ----------
_FACT = re.compile(r"(кто|когда|сколько|какой год|какая дата|где находится|столиц|формул|сколько стоит|\d{3,}|в каком году|кто такой|что такое|курс|население|расстояни)", re.I)


def is_factual(q):
    q = (q or "").strip()
    return len(q) > 12 and bool(_FACT.search(q)) and not q.lower().startswith(("напомни", "/"))


def mode_hint(mode):
    if mode == "thoughtful": return "[Режим: вдумчиво — сначала 2–3 коротких шага рассуждения, затем вывод.]"
    if mode == "fast": return "[Режим: быстро — самое важное, до 3 предложений.]"
    return ""


# ---------- скептик (самопроверка факта) ----------
async def skeptic(ask, q, ans, record=True):
    """Один короткий проход. Возвращает {'ok':bool,'doubt':str}. Работает на слоте 1, после ответа, TTFT не трогает."""
    msgs = [{"role": "system", "content": "Ты строгий скептик. Если в ответе есть утверждение, в котором нельзя быть уверенным (дата, число, имя, источник), верни одну строку «СОМНЕНИЕ: что именно». Если всё надёжно — верни «ОК»."},
            {"role": "user", "content": "Вопрос: %s\nОтвет: %s" % (q[:300], ans[:700])}]
    try: r = (await ask(msgs, 60) or "").strip()
    except Exception: return {"ok": None, "doubt": "", "error": True}
    if r.upper().startswith("СОМНЕН"):
        d = r.split(":", 1)[-1].strip()[:200]
        if record: note_unknown(q, "скептик: " + d, src="skeptic")
        return {"ok": False, "doubt": d}
    return {"ok": True, "doubt": ""}


# ---------- карта неизвестного ----------
_UNK = re.compile(r"(не знаю|не уверен|нет данных|в памяти нет|не могу (?:знать|проверить)|не располагаю)", re.I)
_LEARN = re.compile(r"Чтобы узнать:\s*(.+)", re.I)
_CONF = re.compile(r"Уверенность:\s*(\d{1,3})\s*%")


def note_unknown(q, why, src="answer", learn=""):
    append(F["unknown"], {"t": int(time.time()), "question": str(q)[:300], "why": str(why)[:300], "learn": str(learn)[:300], "source": src, "status": "open"})


def scan_answer(q, ans):
    """Вызывается из log_turn: замечает «не знаю», низкую уверенность и «Чтобы узнать»."""
    m = _LEARN.search(ans or ""); c = _CONF.search(ans or "")
    low = bool(c and int(c.group(1)) < 50)
    if _UNK.search(ans or "") or low or m:
        note_unknown(q, ("уверенность %s%%" % c.group(1)) if low else "ответил «не знаю/не уверен»", learn=m.group(1).strip() if m else "")
        return True
    return False


def unknown_items(limit=40):
    items = [{"t": r.get("t"), "question": r.get("question"), "why": r.get("why"), "learn": r.get("learn"), "source": r.get("source"), "status": r.get("status", "open")} for r in tail(F["unknown"], limit)]
    for j in tail(F["journal"], 30):
        if j.get("question") or j.get("learn"):
            items.append({"t": j.get("t"), "question": j.get("question"), "why": "самоанализ", "learn": j.get("learn"), "source": "reflect", "status": "open"})
    items.sort(key=lambda r: r.get("t") or 0, reverse=True)
    return items[:limit]


# ---------- журнал решений ----------
def log_decision(rec, basis="reflect_once"):
    d = {"t": int(time.time()), "decision": rec.get("improve") or rec.get("weak") or "", "reason": rec.get("weak") or "", "question": rec.get("question") or "",
         "learn": rec.get("learn") or "", "level": level_of((rec.get("improve") or "") + " " + (rec.get("weak") or "")), "basis": basis, "status": "proposed"}
    if not d["decision"]: return None
    if d["level"] == "L0": d["status"] = "blocked"; d["note"] = "L0 не меняется"
    elif d["level"] in ("L2", "L3"): d["note"] = "ждёт решения Создателя"
    append(F["decisions"], d)
    return d


def decisions_items(limit=40):
    rows = tail(F["decisions"], limit)
    if not rows:  # старые записи самоанализа, пока журнал решений пуст
        rows = [{"t": j.get("t"), "decision": j.get("improve"), "reason": j.get("weak"), "level": "L3", "basis": "self_journal", "status": "proposed"} for j in tail(F["journal"], limit) if j.get("improve") or j.get("weak")]
    return list(reversed(rows))


# ---------- сон: консолидация памяти ----------
def should_sleep(idle_s):
    st = jread(F["sleepstate"], {}) or {}
    h = (time.gmtime(time.time() + TZ_H * 3600).tm_hour)
    return (time.time() - st.get("t", 0) > 20 * 3600) and idle_s > 1800 and (h in (2, 3, 4, 5) or time.time() - st.get("t", 0) > 3 * DAY)


async def sleep_once(ask, persist=None):
    since = (jread(F["sleepstate"], {}) or {}).get("t", time.time() - DAY)
    turns = [t for t in tail(F["turns"], 80) if t.get("t", 0) > since][-20:]
    if len(turns) < 3: return None
    dump = "\n".join("Создатель: %s\nЯ: %s" % (str(t.get("u"))[:200], str(t.get("a"))[:200]) for t in turns)
    r = await ask([{"role": "system", "content": "Ты NOX во сне: консолидируешь память. Из разговоров выдели до 5 устойчивых фактов о Создателе, его делах и предпочтениях (только то, что он сам сказал). По строке, формат «- факт». Без выдумок."},
                   {"role": "user", "content": dump}], 220)
    facts = [l.strip("-• ").strip()[:200] for l in (r or "").splitlines() if l.strip().startswith(("-", "•"))][:5]
    rec = {"t": int(time.time()), "turns": len(turns), "facts": facts, "sources": ["owner_dialog"], "lora_after": int(time.time()) + 7 * DAY}
    append(F["sleep"], rec)
    if persist and facts:
        try: persist("[КОНСОЛИДАЦИЯ СНА] " + "; ".join(facts), "Сохранено после сна.")
        except Exception: pass
    jwrite(F["sleepstate"], {"t": int(time.time()), "facts": len(facts)})
    append(F["decisions"], {"t": int(time.time()), "decision": "консолидация памяти (%d фактов)" % len(facts), "reason": "ночной сон", "level": "L1", "basis": "sleep", "status": "applied"})
    return rec


def lora_candidates():
    """Факты только старше 7 дней и с владельцем как источником; советники — только если подтвердили >=2 независимых."""
    now, out = time.time(), []
    for r in tail(F["sleep"], 200):
        if now - r.get("t", now) >= 7 * DAY:
            out += [{"fact": f, "t": r["t"], "sources": r.get("sources")} for f in r.get("facts", [])]
    for f in tail(F["facts"], 300):
        if now - (f.get("t") or now) >= 7 * DAY: out.append({"fact": f.get("content"), "t": f.get("t"), "sources": ["owner_fact"]})
    advs = {}
    for n in tail(F["notes_adv"], 200):
        if n.get("a") and n.get("q") and now - n.get("t", now) >= 7 * DAY: advs.setdefault(n["q"][:80], set()).add(n.get("advisor"))
    out += [{"fact": q, "sources": sorted(a for a in s if a), "t": None, "note": "советники, 2+ независимых"} for q, s in advs.items() if len(s) >= 2]
    return out


# ---------- изменения с прошлого раза ----------
def changes(since=0, mark=False):
    v = jread(F["visit"], {}) or {}
    if not since: since = v.get("t") or int(time.time()) - DAY
    now = int(time.time())
    out = {"since": since, "now": now,
           "new_unknown": [u for u in unknown_items(100) if (u.get("t") or 0) > since][:10],
           "new_decisions": [d for d in decisions_items(100) if (d.get("t") or 0) > since][:10],
           "new_facts": [f for f in tail(F["facts"], 100) if (f.get("t") or 0) > since][-10:],
           "sleep": [{"t": s["t"], "facts": s.get("facts")} for s in tail(F["sleep"], 20) if s.get("t", 0) > since][-3:],
           "drift": [d for d in tail(F["drift"], 50) if d.get("t", 0) > since][-5:]}
    fb = [f for f in tail(F["feedback"], 500) if f.get("t", 0) > since]
    out["feedback"] = {"up": sum(1 for f in fb if f.get("v") == 1), "down": sum(1 for f in fb if f.get("v") != 1)}
    out["new_turns"] = sum(1 for t in tail(F["turns"], 500) if t.get("t", 0) > since)
    if mark: jwrite(F["visit"], {"t": now})
    return out


# ---------- заметки и напоминания ----------
_REM = re.compile(r"напомни(?:ть)?(?:\s+мне)?\s*(.*)", re.I | re.S)
_REL = re.compile(r"через\s+(\d+)\s*(мин|час|ч\b|д)", re.I)
_ABS = re.compile(r"(?:(завтра|сегодня)\s+)?в\s+(\d{1,2})[:.](\d{2})", re.I)


def parse_due(text, now=None):
    now = now or time.time()
    m = _REL.search(text)
    if m:
        n, u = int(m.group(1)), m.group(2).lower()
        return int(now + n * (60 if u.startswith("мин") else 3600 if u.startswith(("час", "ч")) else DAY))
    m = _ABS.search(text)
    if m:
        loc = time.gmtime(now + TZ_H * 3600)
        day0 = (now + TZ_H * 3600) - (loc.tm_hour * 3600 + loc.tm_min * 60 + loc.tm_sec)
        t = day0 + int(m.group(2)) * 3600 + int(m.group(3)) * 60 - TZ_H * 3600
        if (m.group(1) or "").lower() == "завтра" or t <= now: t += DAY
        return int(t)
    return None


def add_note(text, page="", due=None):
    rec = {"id": "n%d" % int(time.time() * 1000), "t": int(time.time()), "text": str(text)[:1000], "page": str(page)[:60]}
    append(F["notes"], rec)
    if due:
        r = {"id": "r" + rec["id"][1:], "t": rec["t"], "text": rec["text"], "due": int(due), "done": False, "note_id": rec["id"]}
        append(F["remind"], r); rec["reminder"] = r
    return rec


def maybe_reminder(text, page=""):
    """Если в тексте «напомни … через 10 мин / завтра в 9:00» — создаёт реальное напоминание."""
    m = _REM.search(text or "")
    if not m: return None
    due = parse_due(text)
    if not due: return None
    return add_note(m.group(1).strip() or text, page, due)


def reminders(due_only=False):
    rows, done = {}, set()
    for r in tail(F["remind"], 300):
        if r.get("done_id"): done.add(r["done_id"])
        elif r.get("id"): rows[r["id"]] = r
    out = [dict(r, done=r["id"] in done) for r in rows.values()]
    if due_only: out = [r for r in out if not r["done"] and r["due"] <= time.time()]
    return sorted(out, key=lambda r: r["due"])


def done_reminder(rid):
    append(F["remind"], {"done_id": str(rid), "t": int(time.time())}); return True


# ---------- планирование ----------
_PLAN = re.compile(r"(спланируй|составь план|разбей|пошагов|по шагам|план действий|распиши шаги)", re.I)


def wants_plan(text, mode=""):
    return mode == "plan" or bool(_PLAN.search(text or ""))


async def make_plan(ask, q):
    r = await ask([{"role": "system", "content": "Разбей задачу на 3–5 шагов. По строке, формат «N. действие», каждый не длиннее 8 слов. Только список."},
                   {"role": "user", "content": q[:600]}], 110)
    steps = [re.sub(r"^\s*\d+[.)]\s*", "", l).strip()[:100] for l in (r or "").splitlines() if re.match(r"^\s*\d+[.)]", l)]
    return steps[:5]


# ---------- KTO ----------
def kto_export():
    rows = []
    for f in tail(F["feedback"], 2000):
        if f.get("q") and f.get("a"): rows.append({"prompt": f["q"], "completion": f["a"], "label": f.get("v") == 1, "t": f.get("t")})
    return rows


# ---------- провенанс источников ----------
def provenance(line):
    t = (line or "").lower()
    for f in tail(F["facts"], 200):
        c = str(f.get("content", "")).lower()
        if c and (c[:40] in t or t[:40] in c): return {"provenance": "OWNER", "origin": "owner_fact", "t": f.get("t")}
    if "консолидация сна" in t: return {"provenance": "SLEEP", "origin": "sleep"}
    if "[mini]" in t: return {"provenance": "S03:mini", "origin": "mini_note"}
    return {"provenance": "S03:dialog", "origin": "dialog"}
