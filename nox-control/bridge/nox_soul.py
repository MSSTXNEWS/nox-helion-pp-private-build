"""Зачатки души и разума NOX (уровень L3: журнал и предложения, ничего само не применяет).
- awareness_line(): общая осознанность процессов и сервера
- log_turn(): журнал ходов для рефлексии
- reflect_once(): в простое NOX разбирает свои ответы: слабое место, улучшение, вопрос, чему научиться
- consult(): совет от внешних моделей через API (OpenAI-совместимые), ответы в карантин; отвечает всегда сам NOX
Ключи API кладёт только владелец в /root/nox/state/advisors.json. Без ключей совет выключен."""
import json, os, subprocess, time, shutil, urllib.request
D = "/root/nox/state"
TURNS, JOURNAL, NOTES, ADV = D + "/turns.jsonl", D + "/self_journal.jsonl", D + "/teacher_notes.jsonl", D + "/advisors.json"
os.makedirs(D, exist_ok=True)
_c = {"t": 0, "v": ""}

def _append(path, obj):
    try:
        with open(path, "a") as f: f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception: pass

def _tail(path, n):
    try: return [json.loads(l) for l in open(path).read().splitlines()[-n:]]
    except Exception: return []

def awareness_line():
    if time.time() - _c["t"] < 30: return _c["v"]
    parts = []
    try:
        o = subprocess.run(["supervisorctl", "status"], capture_output=True, text=True, timeout=6).stdout.splitlines()
        run = [l.split()[0] for l in o if " RUNNING" in l]; bad = [l.split()[0] for l in o if any(x in l for x in ("FATAL", "BACKOFF", "EXITED"))]
        parts.append("процессов работает %d, сбойных %d%s" % (len(run), len(bad), (": " + ", ".join(bad[:5])) if bad else ""))
    except Exception: parts.append("процессы: нет данных")
    try:
        u = shutil.disk_usage("/root"); parts.append("диск занят %d%%" % (u.used * 100 // u.total))
    except Exception: pass
    try:
        parts.append("модель " + ("жива" if urllib.request.urlopen("http://127.0.0.1:8098/health", timeout=2).status == 200 else "не отвечает"))
    except Exception: parts.append("модель не отвечает")
    j = _tail(JOURNAL, 1)
    if j: parts.append("моя последняя мысль о развитии: " + str(j[0].get("improve", ""))[:120])
    _c.update(t=time.time(), v="; ".join(parts)); return _c["v"]

def log_turn(user, ans):
    _append(TURNS, {"t": int(time.time()), "u": user[:400], "a": ans[:700]})
    try:
        import nox_wow as W
        W.scan_answer(user, ans)
    except Exception: pass

async def reflect_once(ask):
    turns = _tail(TURNS, 6)
    if len(turns) < 2: return None
    dump = "\n".join("Создатель: %s\nЯ: %s" % (t["u"], t["a"]) for t in turns)
    msgs = [{"role": "system", "content": "Ты NOX. Разбери свои последние ответы честно, как самокритичный ученик. Верни ровно 4 строки: СЛАБОЕ: ... / УЛУЧШИТЬ: ... / ВОПРОС СОВЕТНИКУ: ... / НАУЧИТЬСЯ: ... "},
            {"role": "user", "content": dump}]
    txt = await ask(msgs, 300)
    if not txt: return None
    rec = {"t": int(time.time()), "raw": txt[:1200]}
    for k, key in (("СЛАБОЕ", "weak"), ("УЛУЧШИТЬ", "improve"), ("ВОПРОС СОВЕТНИКУ", "question"), ("НАУЧИТЬСЯ", "learn")):
        for l in txt.splitlines():
            if l.upper().startswith(k): rec[key] = l.split(":", 1)[-1].strip()[:300]
    _append(JOURNAL, rec)
    try:
        import nox_wow as W
        W.log_decision(rec)
    except Exception: pass
    return rec

def consult(question, limit_per_day=5):
    try: cfg = json.load(open(ADV))
    except Exception: return {"status": "off", "why": "нет advisors.json с ключами"}
    today = time.strftime("%Y-%m-%d")
    used = sum(1 for n in _tail(NOTES, 200) if str(n.get("d")) == today)
    if used >= limit_per_day: return {"status": "limit"}
    out = []
    for a in cfg.get("advisors", []):
        key = a.get("key") or os.environ.get(a.get("key_env", ""), "")
        if not key: continue
        try:
            req = urllib.request.Request(a["url"], data=json.dumps({"model": a["model"], "max_tokens": 500, "messages": [
                {"role": "system", "content": "Отвечай кратко и по делу, укажи источники, если есть."}, {"role": "user", "content": question[:1500]}]}).encode(),
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
            r = json.loads(urllib.request.urlopen(req, timeout=60).read())
            txt = r["choices"][0]["message"]["content"]
            note = {"d": today, "t": int(time.time()), "advisor": a["name"], "q": question[:300], "a": txt[:1500], "status": "QUARANTINE"}
            _append(NOTES, note); out.append(note)
        except Exception as e: _append(NOTES, {"d": today, "advisor": a.get("name"), "error": type(e).__name__})
    return {"status": "ok", "notes": len(out)}
