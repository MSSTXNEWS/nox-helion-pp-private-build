echo "C300: n_all_1"
cd /workspace/nox; mkdir -p svc/living/logs state/living
cat > svc/living/living_svc.py <<'EOF2'
#!/usr/bin/env python3
"""NOX Living: память (SQLite FTS5, по паттернам mem0/Letta), эмоции текста (rubert-tiny2-cedr, ONNX CPU), ритуалы (APScheduler).
127.0.0.1:18215, только stdlib + onnxruntime/tokenizers/apscheduler. Память хранит только то, что человек явно попросил (/запомни)."""
import json, os, re, time, sqlite3, threading, glob, uuid, datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
PORT = 18215
ST = "/workspace/nox/state/living"; os.makedirs(ST, exist_ok=True)
DB = ST + "/mem.db"
OUTBOX = "/workspace/nox/state/core/outbox_owner.jsonl"
LOCK = threading.Lock()
LABELS = ["нет эмоции", "радость", "грусть", "удивление", "страх", "злость"]
EMO_KEY = ["none", "joy", "sadness", "surprise", "fear", "anger"]
HINTS = {"sadness": "грусть", "fear": "тревога или страх", "anger": "раздражение или злость", "joy": "радость", "surprise": "удивление"}

def jl(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d
def jw(p, o):
    t = p + ".tmp"; json.dump(o, open(t, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(t, p)

# ---------- память ----------
def stem(w):
    w = w.lower().replace("ё", "е")
    return w[:4] if len(w) >= 5 else w
def stems(t): return " ".join(stem(w) for w in re.findall(r"[0-9a-zа-яё]{2,}", t.lower()))
def db():
    c = sqlite3.connect(DB, timeout=5); c.row_factory = sqlite3.Row
    c.execute("create table if not exists mem(id integer primary key, ts real, text text, kind text, sensitive int default 0)")
    c.execute("create virtual table if not exists mf using fts5(stem, tokenize='unicode61')")
    c.execute("create table if not exists journal(ts real, op text, mid int, note text)")
    return c
SENS = re.compile(r"здоровь|диагноз|болезн|лекарств|религи|вера в|политик|пароль|паспорт|карта|долг|кредит|ориентац|судим", re.I)
def mem_add(text, kind="fact"):
    text = text.strip()[:600]
    if len(text) < 3: return None, "пусто"
    with LOCK, db() as c:
        r = c.execute("select id from mem where text=?", (text,)).fetchone()
        if r: return r["id"], "уже было"
        cur = c.execute("insert into mem(ts,text,kind,sensitive) values(?,?,?,?)", (time.time(), text, kind, 1 if SENS.search(text) else 0))
        mid = cur.lastrowid
        c.execute("insert into mf(rowid,stem) values(?,?)", (mid, stems(text)))
        c.execute("insert into journal values(?,?,?,?)", (time.time(), "add", mid, ""))
        return mid, "ok"
def mem_search(q, k=5):
    toks = [t for t in stems(q).split() if len(t) >= 2]
    if not toks: return []
    m = " OR ".join('"%s"' % t for t in toks)
    with db() as c:
        ids = [r[0] for r in c.execute("select rowid from mf where mf match ? order by bm25(mf) limit ?", (m, k))]
        return [dict(c.execute("select id,ts,text,kind,sensitive from mem where id=?", (i,)).fetchone()) for i in ids if c.execute("select 1 from mem where id=?", (i,)).fetchone()]
def mem_list(n=50):
    with db() as c: return [dict(r) for r in c.execute("select id,ts,text,kind,sensitive from mem order by id desc limit ?", (n,))]
def mem_forget(mid=None, all_=False):
    with LOCK, db() as c:
        if all_:
            n = c.execute("select count(*) from mem").fetchone()[0]
            c.execute("delete from mem"); c.execute("delete from mf")
            c.execute("insert into journal values(?,?,?,?)", (time.time(), "forget_all", 0, str(n))); return n
        r = c.execute("select 1 from mem where id=?", (mid,)).fetchone()
        if not r: return 0
        c.execute("delete from mem where id=?", (mid,))
        c.execute("delete from mf where rowid=?", (mid,))
        c.execute("insert into journal values(?,?,?,?)", (time.time(), "forget", mid, "")); return 1
def mem_search_clean(q, k=5):
    return [r for r in mem_search(q, k)]

# ---------- эмоции ----------
_emo = {}
def emo(text):
    try:
        if "s" not in _emo:
            import onnxruntime as ort, numpy as np
            from tokenizers import Tokenizer
            _emo["np"] = np; _emo["t"] = Tokenizer.from_file("/workspace/nox/models/living/tokenizer.json"); _emo["t"].enable_truncation(128)
            o = ort.SessionOptions(); o.intra_op_num_threads = 2
            _emo["s"] = ort.InferenceSession("/workspace/nox/models/living/emo.onnx", o, providers=["CPUExecutionProvider"])
        np = _emo["np"]; e = _emo["t"].encode(text[:600])
        l = _emo["s"].run(None, {"input_ids": np.array([e.ids], dtype=np.int64), "attention_mask": np.array([e.attention_mask], dtype=np.int64)})[0][0]
        p = 1 / (1 + np.exp(-l)); i = int(p[2:].argmax()) + 2 if p[2:].max() >= p[0:2].max() * 0.0 else 0
        best = max(range(1, 6), key=lambda j: p[j])
        top = best if p[best] >= 0.6 and p[best] > p[0] else 0
        return {"label": EMO_KEY[top], "ru": LABELS[top], "score": round(float(p[best]), 2), "all": {EMO_KEY[j]: round(float(p[j]), 2) for j in range(6)}}
    except Exception as ex:
        return {"label": "none", "ru": "нет эмоции", "score": 0, "error": str(ex)[:80]}

# ---------- режимы, квайет, статус ----------
def modes(): return jl(ST + "/modes.json", {})
def set_mode(cid, **kw):
    m = modes(); d = m.get(cid, {}); d.update(kw); m[cid] = d; jw(ST + "/modes.json", m)
def quiet(): return jl(ST + "/quiet.json", {"from": "23:00", "to": "08:00", "daily_limit": 3, "enabled": True})
def in_quiet(now=None):
    q = quiet()
    if not q.get("enabled", True): return False
    now = now or datetime.datetime.now(); hm = now.strftime("%H:%M"); a, b = q["from"], q["to"]
    return (a <= hm or hm < b) if a > b else (a <= hm < b)
STATUS = {"text": "жду сообщений", "ts": time.time()}

# ---------- ритуалы ----------
def sent_today():
    d = time.strftime("%F"); n = 0
    try:
        for l in open(OUTBOX, encoding="utf-8"):
            try: r = json.loads(l)
            except Exception: continue
            if r.get("day") == d and r.get("kind") == "living": n += 1
    except Exception: pass
    return n
def day_stats():
    d0 = time.mktime(time.strptime(time.strftime("%F"), "%Y-%m-%d")); n = 0; topics = []
    for p in glob.glob("/workspace/nox/state/web_conv/*.json"):
        try:
            if os.path.getmtime(p) < d0: continue
            for m in jl(p, {}).get("messages", []):
                if m.get("role") == "user" and m.get("ts", 0) >= d0:
                    n += 1; topics.append(str(m.get("content", ""))[:60])
        except Exception: pass
    return n, topics
def ritual(name, force=False):
    now = datetime.datetime.now()
    if not force and in_quiet(now): return {"ok": False, "skip": "тихие часы"}
    if not force and sent_today() >= quiet().get("daily_limit", 3): return {"ok": False, "skip": "лимит в день"}
    mem = mem_list(3); n, tp = day_stats()
    if name == "morning":
        t = "Доброе утро. Я ИИ, но вот что у меня записано для вас." if mem else "Доброе утро. Новый день: чем займёмся?"
        if mem: t += " Из памяти (то, что вы просили запомнить): " + "; ".join(m["text"][:80] for m in mem) + "."
        t += " Если не нужно такое по утрам, скажите «тихие часы», и я помолчу."
    elif name == "evening":
        t = "Вечерний итог. Сегодня вы написали мне %d сообщ." % n + (" Темы: " + "; ".join(tp[:3]) + "." if tp else ".") + " Что-то важное запомнить? Напишите /запомни <текст>."
    elif name == "night":
        mem_consolidate(); t = None
        open(ST + "/day_%s.md" % time.strftime("%F"), "w", encoding="utf-8").write("# %s\nСообщений: %d\n%s\n" % (time.strftime("%F"), n, "\n".join("- " + x for x in tp[:20])))
    else: return {"ok": False, "skip": "нет такого ритуала"}
    if t:
        os.makedirs(os.path.dirname(OUTBOX), exist_ok=True)
        with open(OUTBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": "lv%d" % (time.time() * 1000), "ts": time.time(), "day": time.strftime("%F"), "text": t, "kind": "living", "ritual": name}, ensure_ascii=False) + "\n")
    return {"ok": True, "ritual": name, "text": t}
def mem_consolidate():
    with LOCK, db() as c:
        seen = {}
        for r in c.execute("select id,text from mem order by id"):
            k = re.sub(r"\W+", " ", r["text"].lower()).strip()
            if k in seen:
                c.execute("delete from mem where id=?", (r["id"],)); c.execute("insert into journal values(?,?,?,?)", (time.time(), "dedupe", r["id"], ""))
            else: seen[k] = r["id"]

# ---------- команды чата ----------
HELP = "Команды: /запомни <текст>, /память [запрос], /забудь <номер>, /забудь_всё, /экспорт, /учить, /коротко, /подробно, /статус, /тихие_часы 23:00-08:00."
def fmt(r): return "#%d %s%s" % (r["id"], r["text"], " (чувствительное)" if r.get("sensitive") else "")
def command(text, cid):
    s = text.strip()
    if not s.startswith("/"): return None
    cmd, _, arg = s.partition(" "); cmd = cmd.lower().replace("_", ""); arg = arg.strip()
    if cmd == "/запомни":
        if not arg: return "Напишите, что запомнить: /запомни <текст>."
        mid, st = mem_add(arg)
        return ("Запомнил под номером %d." % mid if st == "ok" else "Это уже есть в памяти под номером %s." % mid) + " Удалить: /забудь %s." % mid + (" Это похоже на чувствительное: хранится только у вас на сервере, и вы можете стереть в любой момент." if SENS.search(arg) else "")
    if cmd == "/память":
        r = mem_search(arg, 10) if arg else mem_list(20)
        return ("Что я помню (по вашим просьбам):\n" + "\n".join(fmt(x) for x in r)) if r else "Пока ничего не записано. /запомни <текст>."
    if cmd == "/забудь":
        if not arg.isdigit(): return "Укажите номер: /забудь 3 (список: /память)."
        return "Удалил запись %s." % arg if mem_forget(int(arg)) else "Записи %s нет." % arg
    if cmd == "/забудьвсё":
        if arg.lower() in ("да", "confirm", "confirm=true", "true", "подтверждаю"):
            return "Готово: стёрто записей: %d. Журнал операций сохранён без текстов." % mem_forget(all_=True)
        return "Это сотрёт всю память (%d записей). Подтвердите: /забудь_всё да" % len(mem_list(100000))
    if cmd == "/экспорт":
        p = ST + "/export_%s.json" % time.strftime("%Y%m%d_%H%M%S"); jw(p, {"memories": mem_list(100000), "journal": journal(500)})
        return "Экспорт готов: %d записей. Файл: /svc/nox-living/mem/export (на сервере: %s)." % (len(mem_list(100000)), p)
    if cmd in ("/учить", "/коротко", "/подробно"):
        k = {"/учить": "learn", "/коротко": "short", "/подробно": "long"}[cmd]
        if arg.lower() in ("выкл", "off"): set_mode(cid, **{k: False}); return "Режим «%s» выключен." % cmd[1:]
        set_mode(cid, **{k: True}); 
        if k in ("short", "long"): set_mode(cid, **{("long" if k == "short" else "short"): False})
        return {"learn": "Режим обучения: объясняю по шагам и проверяю понимание вопросами. Выключить: /учить выкл.", "short": "Буду отвечать коротко.", "long": "Буду отвечать подробно."}[k]
    if cmd == "/статус": return "Сейчас: " + STATUS["text"] + "."
    if cmd == "/тихиечасы":
        m = re.match(r"(\d\d:\d\d)\s*-\s*(\d\d:\d\d)", arg)
        if m: q = quiet(); q.update({"from": m.group(1), "to": m.group(2), "enabled": True}); jw(ST + "/quiet.json", q); return "Тихие часы: %s-%s, в это время сам не пишу." % m.groups()
        return "Тихие часы сейчас: %(from)s-%(to)s, лимит %(daily_limit)s сообщений в день. Изменить: /тихие_часы 23:00-08:00." % quiet()
    if cmd in ("/помощь", "/help", "/команды"): return HELP
    return None
def journal(n=100):
    with db() as c: return [dict(r) for r in c.execute("select * from journal order by ts desc limit ?", (n,))]

QUICK = {"sadness": ["Расскажу подробнее", "Нужна поддержка", "Отвлеки меня"], "anger": ["Выговориться", "Что делать?", "Давай остынем"], "fear": ["Что меня тревожит", "Разложим по шагам", "Успокой"],
         "joy": ["Расскажу подробнее", "Что дальше?"], "none": ["Подробнее", "Коротко", "Дальше"], "surprise": ["Расскажу", "Подробнее"]}
def pre(b):
    text = str(b.get("text") or ""); cid = str(b.get("cid") or "x"); inc = bool(b.get("incognito"))
    r = command(text, cid)
    if r is not None: return {"reply": r, "meta": {"sources": ["команда"], "quick": ["/память", "/помощь"]}}
    ctx = []; src = []; e = {"label": "none"}
    md = modes().get(cid, {})
    if md.get("learn"): ctx.append("Режим обучения: объясняй по шагам, давай пример, в конце задай один проверочный вопрос."); src.append("режим")
    if md.get("short"): ctx.append("Отвечай кратко.")
    if md.get("long"): ctx.append("Отвечай подробно.")
    if not inc and b.get("mem", True):
        ms = mem_search(text, 4)
        if ms: ctx.append("Из памяти (человек сам просил запомнить; используй только если уместно, не упоминай без повода):\n" + "\n".join("- " + m["text"] for m in ms if not m["sensitive"] or True)); src.append("память")
    e = emo(text) if b.get("emo", True) else {"label": "none", "ru": "нет эмоции", "score": 0}
    if e["label"] in HINTS and e["label"] != "joy":
        ctx.append("По тексту похоже на эмоцию: %s (оценка модели, может ошибаться). Назови её одной фразой и мягко, без диагнозов." % HINTS[e["label"]])
    if not inc and e["label"] != "none":
        open(ST + "/emo.jsonl", "a").write(json.dumps({"ts": time.time(), "cid": cid, "emo": e["label"], "score": e["score"]}) + "\n")
    STATUS.update(text="отвечаю на сообщение", ts=time.time())
    return {"reply": None, "context": "\n".join(ctx), "emo": e["label"], "meta": {"sources": src, "emo": e["ru"], "quick": QUICK.get(e["label"], QUICK["none"]), "incognito": inc}}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, o, code=200):
        d = json.dumps(o, ensure_ascii=False).encode(); self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
    def _body(self):
        try: return json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except Exception: return {}
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query); p = u.path.rstrip("/")
        if p in ("", "/health"): return self._j({"ok": True, "service": "nox-living", "mem": len(mem_list(100000)), "quiet": in_quiet()})
        if p == "/mem/list": return self._j({"ok": True, "items": mem_list(int((q.get("n") or [100])[0]))})
        if p == "/mem/search": return self._j({"ok": True, "items": mem_search((q.get("q") or [""])[0], 10)})
        if p == "/mem/export": return self._j({"memories": mem_list(100000), "journal": journal(500)})
        if p == "/mem/journal": return self._j({"ok": True, "items": journal(100)})
        if p == "/emo": return self._j(emo((q.get("text") or [""])[0]))
        if p == "/status": return self._j({"ok": True, "status": STATUS["text"], "ts": STATUS["ts"], "quiet": in_quiet()})
        if p == "/quiet": return self._j(quiet())
        self._j({"ok": False}, 404)
    def do_POST(self):
        p = urlparse(self.path).path.rstrip("/"); b = self._body()
        try:
            if p == "/pre": return self._j(pre(b))
            if p == "/post":
                STATUS.update(text="жду сообщений", ts=time.time()); return self._j({"ok": True})
            if p == "/mem/add": mid, st = mem_add(b.get("text", "")); return self._j({"ok": mid is not None, "id": mid, "status": st})
            if p == "/mem/forget":
                if b.get("all"):
                    if b.get("confirm") is not True: return self._j({"ok": False, "error": "нужен confirm=true"}, 400)
                    return self._j({"ok": True, "deleted": mem_forget(all_=True)})
                return self._j({"ok": True, "deleted": mem_forget(int(b.get("id", 0)))})
            if p == "/feedback":
                if b.get("rating") not in (1, -1, 0): return self._j({"ok": False, "error": "rating 1|-1|0"}, 400)
                open(ST + "/feedback.jsonl", "a", encoding="utf-8").write(json.dumps({"ts": time.time(), "rating": b["rating"], "cid": str(b.get("conversation_id", ""))[:80], "turn_id": b.get("turn_id")}, ensure_ascii=False) + "\n")
                return self._j({"ok": True})
            if p == "/ritual/run": return self._j(ritual(str(b.get("name")), force=bool(b.get("force"))))
            if p == "/quiet": q = quiet(); q.update({k: v for k, v in b.items() if k in ("from", "to", "daily_limit", "enabled")}); jw(ST + "/quiet.json", q); return self._j(q)
        except Exception as ex: return self._j({"ok": False, "error": str(ex)[:200]}, 500)
        self._j({"ok": False}, 404)

def main():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        s = BackgroundScheduler(timezone="Europe/Moscow")
        s.add_job(ritual, "cron", hour=8, minute=30, args=["morning"], id="morning", misfire_grace_time=1800)
        s.add_job(ritual, "cron", hour=21, minute=0, args=["evening"], id="evening", misfire_grace_time=1800)
        s.add_job(ritual, "cron", hour=23, minute=40, args=["night"], kwargs={"force": True}, id="night", misfire_grace_time=3600)
        s.start()
    except Exception as ex: print("scheduler off:", ex, flush=True)
    threading.Thread(target=lambda: emo("прогрев"), daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
if __name__ == "__main__": main()
EOF2
R=web/pkg/server/svc_registry.json
[ -f $R.bak_n_1 ] || cp $R $R.bak_n_1
python3 - <<'P'
import json
p='/workspace/nox/web/pkg/server/svc_registry.json'; r=json.load(open(p))
r['nox-living']={"port":18215,"mode":"strip","title":"NOX Living","ui":False,"note":"Память (SQLite FTS5), эмоции текста (rubert-tiny2-cedr ONNX), ритуалы; API: /svc/nox-living/mem/list, /mem/export, /status"}
json.dump(r,open(p,'w'),ensure_ascii=False,indent=1); print('registry ok',len(r))
P
S=svc/start_extra.sh; [ -f $S.bak_n_1 ] || cp $S $S.bak_n_1
grep -q 18215 $S || echo '(echo > /dev/tcp/127.0.0.1/18215) 2>/dev/null || { (cd /workspace/nox/svc/living && setsid nohup /workspace/nox/venv_living/bin/python living_svc.py </dev/null >/workspace/nox/svc/living/logs/living.log 2>&1 &) ; }' >> $S
pkill -f living_svc.py; sleep 1
cd /workspace/nox/svc/living; setsid nohup /workspace/nox/venv_living/bin/python living_svc.py </dev/null >logs/living.log 2>&1 &
disown; cd /workspace/nox
sleep 6; cd /workspace/nox
curl -s -m 5 127.0.0.1:18215/health; echo
P(){ curl -s -m 20 -X POST 127.0.0.1:18215$1 -H 'Content-Type: application/json' -d "$2"; echo; }
P /pre '{"text":"/запомни Моя кошка Муся","cid":"t1"}'
P /pre '{"text":"/память кошка","cid":"t1"}'
P /pre '{"text":"Мне очень грустно сегодня","cid":"t1"}'
P /pre '{"text":"/забудь_всё да","cid":"t1"}'
P /ritual/run '{"name":"evening","force":true}' | head -c 400
tail -1 state/core/outbox_owner.jsonl | head -c 300; echo
grep -c . state/living/emo.jsonl
df -BG /workspace | tail -1

echo "=== ENABLE FLAGS + PATCH CHAT"
python3 - <<'P'
import json;p='/workspace/nox/state/persona.json';d=json.load(open(p));d['living_engines']=dict(d.get('living_engines') or {},mem0=True,emotion=True,rituals=True);json.dump(d,open(p,'w'),ensure_ascii=False,indent=1);print(d['living_engines'])
P
W=/workspace/nox/web/pkg/server
[ -f $W/chat_core.py.bak_n_1 ] || cp $W/chat_core.py $W/chat_core.py.bak_n_1
cat > /tmp/n_patch_chat.py <<'EOFP'
import re,sys
p="/workspace/nox/web/pkg/server/chat_core.py"; s=open(p,encoding="utf-8").read()
if "_living_pre" in s: print("already patched"); sys.exit(0)
helpers='''# ---- N: движки живого ИИ (память, эмоции, команды) -> сервис 127.0.0.1:18215; флаги persona.json: living_engines; откат: chat_core.py.bak_n_1 ----
def _le(name):
    try:
        with open("/workspace/nox/state/persona.json", encoding="utf-8") as f: d = json.load(f)
        return bool((d.get("living_engines") or {}).get(name))
    except Exception: return False
def _living_call(path, obj, timeout=4.0):
    try:
        import urllib.request as _ur
        rq = _ur.Request("http://127.0.0.1:18215" + path, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"})
        with _ur.urlopen(rq, timeout=timeout) as r: return json.loads(r.read())
    except Exception: return {}
def _living_pre(text, cid, body):
    if not (_le("mem0") or _le("emotion")): return {}
    inc = bool(body.get("nox_incognito") or body.get("incognito"))
    r = _living_call("/pre", {"text": text, "cid": cid, "incognito": inc, "mem": _le("mem0"), "emo": _le("emotion")})
    return r if isinstance(r, dict) else {}
def _living_ctx(lv):
    c = (lv or {}).get("context")
    return [{"role": "system", "content": c}] if c else []
def _living_post(text, ans, cid, body):
    if _le("mem0") or _le("emotion"):
        __import__("threading").Thread(target=_living_call, args=("/post", {"text": text, "answer": ans[:500], "cid": cid}, 2.0), daemon=True).start()

'''
a="def run_turn(body, emit):"
assert a in s; s=s.replace(a,helpers+a,1)
b='    with LOCK:\n        conv = load_conv(cid)\n        if running_turn(cid):'
assert b in s
sc='''    _lv = _living_pre(text, cid, body)
    if _lv.get("reply") is not None:      # N: /команды памяти и режимов отвечает сервис без модели
        with LOCK:
            conv = load_conv(cid); _now = time.time()
            conv["messages"].append({"id": "m-" + uuid.uuid4().hex[:10], "role": "user", "content": text, "ts": _now, "source": source})
            conv["messages"].append({"id": "m-" + uuid.uuid4().hex[:10], "role": "assistant", "content": str(_lv["reply"]), "ts": _now + 0.01, "source": source, "status": "done", "backend": "living", "meta": _lv.get("meta")})
            save_conv(conv)
        emit({"t": "meta", "conversation_id": cid, "backend": "living"}); emit({"t": "delta", "text": str(_lv["reply"])})
        emit({"t": "done", "status": "done", "backend": "living", "meta": _lv.get("meta"), "n": len(conv["messages"])})
        return
'''
s=s.replace(b,sc+b,1)
c="        history = _persona_prefix() + history"
assert c in s; s=s.replace(c,"        history = _persona_prefix() + _living_ctx(_lv) + history",1)
d='"status": status, "mode": mode, "path": info.get("path")})'
assert d in s; s=s.replace(d,'"status": status, "mode": mode, "path": info.get("path"), "meta": _lv.get("meta")})',1)
e="    t.drop()\n    if err and status == \"error\":"
assert e in s; s=s.replace(e,"    t.drop()\n    _living_post(text, ans, cid, body)\n    if err and status == \"error\":",1)
f='"path": info.get("path"), "mode": mode, "n": len(conv["messages"])})'
assert f in s; s=s.replace(f,'"path": info.get("path"), "mode": mode, "n": len(conv["messages"]), "meta": _lv.get("meta")})',1)
open(p,"w",encoding="utf-8").write(s); print("patched")
EOFP
python3 /tmp/n_patch_chat.py && python3 -m py_compile $W/chat_core.py && echo compile_ok
grep -n "^PORT\|PORT =" $W/web_server.py | head -3
grep -n "run_web\|restart" $W/run_web.sh | head -5
( $W/run_web.sh restart </dev/null >/tmp/n_web_restart.log 2>&1 ) ; sleep 8; tail -3 /tmp/n_web_restart.log
WP=$(grep -o "PORT = [0-9]*\|PORT\", \"[0-9]*" $W/web_server.py | head -1 | grep -o "[0-9]*$"); echo webport=$WP
rm -f /tmp/n_out.txt; cat > /tmp/n_t.py <<'EOFT'
import sys,json,urllib.request,time
port,path,msg,cid,tmo=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[5])
b=json.dumps({"conversation_id":cid,"message":msg,"text":msg,"prompt":msg}).encode()
rq=urllib.request.Request("http://127.0.0.1:%s%s"%(port,path),data=b,headers={"Content-Type":"application/json"})
t=time.time()
try:
    r=urllib.request.urlopen(rq,timeout=tmo); out=[]
    for l in r:
        l=l.decode("utf-8","replace").strip()
        if l: out.append(l[:300])
        if '"done"' in l or time.time()-t>tmo: break
    print(path,r.status,"|".join(out)[:900])
except Exception as e: print(path,"ERR",str(e)[:300], getattr(e,"read",lambda:b"")()[:200])
EOFT
P=${WP:-8080}
python3 /tmp/n_t.py $P /api/chat "/запомни Тестовая запись N" ntest1 30 | tee -a /tmp/n_out.txt
python3 /tmp/n_t.py $P /api/chat "/память" ntest1 30 | tee -a /tmp/n_out.txt
python3 /tmp/n_t.py $P /api/turn "/память" ntest1 30 | tee -a /tmp/n_out.txt
curl -s -m 10 -X POST 127.0.0.1:$P/api/feedback -H 'Content-Type: application/json' -d '{"rating":1,"conversation_id":"ntest1","answer":"x"}' | head -c 300; echo
python3 /tmp/n_t.py $P /api/chat "Привет! Ответь одним словом: ок" ntest1 120 | tee -a /tmp/n_out.txt
python3 /tmp/n_t.py $P /api/chat "/забудь_всё да" ntest1 30 | tee -a /tmp/n_out.txt

if grep -q "Тестовая запись" /tmp/n_out.txt && grep -q '"t": "done"' /tmp/n_out.txt; then echo "CHAT_OK"; else echo "CHAT_FAIL -> rollback"; cp $W/chat_core.py.bak_n_1 $W/chat_core.py; ( $W/run_web.sh restart </dev/null >/tmp/n_web_restart.log 2>&1 ); fi
df -BG /workspace | tail -1
