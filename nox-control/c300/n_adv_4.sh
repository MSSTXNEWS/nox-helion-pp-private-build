echo "C300: n_adv_4"
cd /workspace/nox; mkdir -p svc/advisors/logs
cat > svc/advisors/advisors_svc.py <<'EOF2'
#!/usr/bin/env python3
"""NOX Advisors: подсказки для правой колонки чата и черновик ответа. 127.0.0.1:18216, только stdlib.
GET /suggest?project=&dialog=&last= ; POST /pin ; GET /pins ; GET /draft?chat=&page=&last=&typed= (до 3 с, иначе пусто, добивается в фоне в кеш)."""
import json, os, re, time, threading, hashlib, urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
PORT = 18216; PINS = "/workspace/nox/state/prompts.json"; REG = "/workspace/nox/web/site/qa/registry.json"
GLM = "http://127.0.0.1:8091/glm/v1"; LS = "http://127.0.0.1:8200"
LOCK = threading.Lock(); CACHE = {}; GEN = {}; SEM = threading.Semaphore(1)
# заготовки: адаптированы по мотивам awesome-chatgpt-prompts (CC0) и Fabric patterns (MIT), переписаны по-русски
BASE = [
 ("Суммаризация", "Сделай краткую выжимку этого текста: 5 пунктов и один вывод.", "суммаризация выжимка текст кратко итог резюме"),
 ("Извлечь главное", "Выдели ключевые идеи, решения и открытые вопросы из диалога выше.", "идеи решения вопросы диалог главное итоги"),
 ("Улучшить текст", "Перепиши текст яснее и короче, сохрани смысл и тон. Дай два варианта.", "текст письмо редактура улучшить переписать"),
 ("План действий", "Разбей задачу на шаги с порядком и оценкой времени. Отметь риски.", "план задача шаги проект срок риски"),
 ("Код-ревью", "Проведи ревью кода: ошибки, безопасность, читаемость. Предложи исправления списком.", "код ревью ошибки python javascript баг функция"),
 ("Объяснить код", "Объясни, что делает этот код, по шагам, простыми словами.", "код объясни функция скрипт python"),
 ("Написать тесты", "Напиши тесты для этой функции: обычные случаи, границы, ошибки.", "тесты код проверка pytest качество"),
 ("Отладка", "Вот ошибка и контекст. Найди вероятную причину и предложи 3 проверки по убыванию вероятности.", "ошибка баг лог отладка traceback"),
 ("Дизайн-критика", "Оцени дизайн экрана: иерархия, контраст, отступы, мобильная версия. Дай 5 правок.", "дизайн интерфейс экран макет цвет верстка css"),
 ("Палитра", "Предложи палитру из 5 цветов для этого настроения и проверь контраст текста.", "цвет палитра тема дизайн контраст"),
 ("Исследование", "Найди 3 надёжных источника по теме и дай сравнение позиций с ссылками.", "исследование источники поиск факты тема"),
 ("Проверить факты", "Проверь утверждения выше: что подтверждено, что спорно, чего не знаю.", "факты проверка источник достоверность"),
 ("Финансовая сводка", "Сведи доходы и расходы по категориям, покажи топ-3 статьи и что можно сократить.", "финансы бюджет расходы доходы деньги отчёт"),
 ("Перевод", "Переведи на английский, сохрани стиль. Отметь спорные места.", "перевод английский язык текст"),
 ("Юр. справка", "Кратко объясни норму и порядок действий по пунктам. Я не юрист: отметь, что проверить у специалиста.", "закон суд иск право норма документ"),
 ("Письмо", "Составь вежливое деловое письмо: цель, суть в 3 предложениях, просьба, срок.", "письмо email сообщение деловое ответ"),
 ("Идеи", "Дай 10 идей, потом выбери 3 лучшие и объясни выбор.", "идеи брейншторм варианты придумать"),
 ("Сравнить варианты", "Сравни варианты в таблице по критериям и порекомендуй один с причиной.", "сравнить выбор варианты таблица решение"),
 ("Музыка и настроение", "Подбери 5 треков под это настроение и опиши, чем они подходят.", "музыка настроение плейлист трек"),
 ("Итог дня", "Подведи итог дня по нашему диалогу: сделано, не сделано, на завтра.", "день итог вечер план завтра"),
 ("NOX: состояние", "Расскажи, чем ты сейчас занят и как себя чувствуешь по журналу.", "nox состояние статус занят обучение"),
 ("Запомнить", "/запомни ", "память запомни факт"),
 ("Что помнишь", "/память", "память помнишь факты забудь"),
]
def stem(w): w = w.lower().replace("ё", "е"); return w[:4] if len(w) >= 5 else w
def toks(t): return {stem(w) for w in re.findall(r"[0-9a-zа-яё]{2,}", (t or "").lower())}
def jl(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d
def pins(): return jl(PINS, [])
def _walk(o, out, key=None):
    if isinstance(o, dict):
        if (o.get("id") or key) and any(k in o for k in ("title", "endpoint", "label")) and not any(isinstance(v, (dict, list)) and k in ("commands", "items") for k, v in o.items()):
            out.append(dict(o, id=o.get("id") or key))
        else:
            for k, v in o.items(): _walk(v, out, k if isinstance(k, str) else None)
    elif isinstance(o, list):
        for v in o: _walk(v, out)
def commands():
    L = []; _walk(jl(REG, {}), L); out = []
    for c in L:
        t = c.get("title") or c.get("label") or c["id"]
        out.append({"id": c["id"], "title": t, "confirm": bool(c.get("confirm")), "endpoint": c.get("endpoint"), "_k": toks(str(c["id"]) + " " + str(t) + " " + str(c.get("desc", "")))})
    return out
def get(url, t=2):
    with urllib.request.urlopen(url, timeout=t) as r: return json.loads(r.read())
def pick_model():
    try:
        r = get(LS + "/running", 1.5); L = r if isinstance(r, list) else r.get("running", [])
        for m in L:
            n = m.get("model") if isinstance(m, dict) else m
            if n: return str(n)
    except Exception: pass
    return None
def llm(system, user, max_tokens=40, timeout=60):
    m = pick_model()
    if not m: raise RuntimeError("нет загруженной модели")
    b = {"model": m, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "max_tokens": max_tokens, "temperature": 0.4, "stream": False}
    rq = urllib.request.Request(GLM + "/chat/completions", data=json.dumps(b).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(rq, timeout=timeout) as r: d = json.loads(r.read())
    t = d["choices"][0]["message"]["content"] or ""
    return re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip().strip('"«»')
PAGE = {"designer": "страница дизайнера интерфейса", "finance": "страница финансов", "chat": "основной чат", "music": "музыка", "news": "новости", "studio": "студия"}
def draft_job(key, chat, page, last, typed):
    if not SEM.acquire(blocking=False): return          # одна фоновая генерация, чат в приоритете
    try:
        sysm = "Ты предсказываешь следующее сообщение ПОЛЬЗОВАТЕЛЯ в чате. Контекст: " + PAGE.get(page, str(page)[:40] or "чат") + ". Верни только текст сообщения, до 15 слов, по-русски, без кавычек."
        u = "Последнее сообщение ассистента: " + last[:600] + ("\nПользователь уже набрал: " + typed + "\nПродолжи это сообщение, верни полный текст." if typed else "\nНапиши наиболее вероятный ответ пользователя.")
        d = llm(sysm, u, 40, 90)[:240]
        with LOCK: CACHE[key] = (time.time(), d)
    except Exception: 
        with LOCK: CACHE[key] = (time.time(), heur(last, typed))
    finally: SEM.release()
def heur(last, typed):
    l = (last or "").strip().lower()
    if typed: return ""
    if not l: return ""
    if re.search(r"(хотите|хочешь|давайте|сделать|продолж|запустить|подтверд).{0,80}\?\s*$", l): return "Да, давай."
    if l.endswith("?"): return "Расскажи подробнее."
    if re.search(r"готово|сделано|выполнено", l): return "Спасибо. Что дальше?"
    return "Понятно. Продолжай."
def draft(q):
    chat, page, last, typed = [(q.get(k) or [""])[0] for k in ("chat", "page", "last", "typed")]
    typed = typed or (q.get("text") or [""])[0]
    if not last.strip() and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", chat or ""):
        try:
            ms = [m for m in jl("/workspace/nox/state/web_conv/%s.json" % chat, {}).get("messages", []) if m.get("role") == "assistant"]
            last = str(ms[-1].get("content", ""))[:600] if ms else ""
        except Exception: pass
    if not last.strip() and not typed.strip(): return {"draft": ""}
    key = hashlib.md5(("|".join([chat, page, last[-300:], typed])).encode()).hexdigest()
    with LOCK: c = CACHE.get(key)
    if c and time.time() - c[0] < 600: return {"draft": c[1], "cached": True}
    th = threading.Thread(target=draft_job, args=(key, chat, page, last, typed), daemon=True); th.start()
    t0 = time.time()
    while time.time() - t0 < 3:
        with LOCK: c = CACHE.get(key)
        if c: return {"draft": c[1]}
        time.sleep(0.1)
    h = heur(last, typed)
    return {"draft": h, "pending": True, "heuristic": bool(h)}
def gen_prompts(project):
    try:
        t = llm("Придумай 3 коротких полезных заготовки запросов к ИИ-ассистенту для проекта. Верни по одной в строке, без нумерации.", "Проект: " + project[:80], 120, 120)
        L = [x.strip(" -*•\t") for x in t.splitlines() if len(x.strip()) > 6][:3]
        with LOCK: GEN[project] = (time.time(), L)
    except Exception:
        with LOCK: GEN[project] = (time.time(), [])
def suggest(q):
    project, dialog, last = [(q.get(k) or [""])[0] for k in ("project", "dialog", "last")]
    ctx = toks(project + " " + dialog + " " + last)
    items = [{"id": "b%d" % i, "title": t, "text": p, "_s": len(ctx & toks(k + " " + t))} for i, (t, p, k) in enumerate(BASE)]
    for p in pins():
        items.append({"id": p["id"], "title": p.get("title", "")[:60], "text": p["text"], "pinned": True, "_s": 2 + len(ctx & toks(p["text"] + " " + p.get("title", "")))})
    with LOCK: g = GEN.get(project)
    if project and (not g or time.time() - g[0] > 3600):
        with LOCK: GEN[project] = (time.time(), g[1] if g else [])
        threading.Thread(target=gen_prompts, args=(project,), daemon=True).start()
    for i, x in enumerate((g or (0, []))[1]): items.append({"id": "g%d" % i, "title": x[:50], "text": x, "generated": True, "_s": 1})
    items.sort(key=lambda x: -x["_s"]); pr = [{k: v for k, v in x.items() if k != "_s"} for x in items[:6]]
    cm = sorted(commands(), key=lambda c: -len(ctx & c["_k"]))[:5]
    return {"commands": [{k: v for k, v in c.items() if k != "_k"} for c in cm], "prompts": pr}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, o, code=200):
        d = json.dumps(o, ensure_ascii=False).encode(); self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query); p = u.path.rstrip("/")
        try:
            if p in ("", "/health"): return self._j({"ok": True, "service": "advisors", "pins": len(pins()), "base": len(BASE)})
            if p == "/suggest": return self._j(suggest(q))
            if p == "/pins": return self._j({"ok": True, "pins": pins()})
            if p == "/draft": return self._j(draft(q))
        except Exception as ex: return self._j({"ok": False, "error": str(ex)[:200]}, 500)
        self._j({"ok": False}, 404)
    def do_POST(self):
        p = urlparse(self.path).path.rstrip("/")
        try: b = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except Exception: b = {}
        if p == "/pin":
            t = str(b.get("text") or "").strip()[:1000]
            if not t: return self._j({"ok": False, "error": "пустой text"}, 400)
            with LOCK:
                L = pins(); 
                if not any(x["text"] == t for x in L): L.append({"id": "p%d" % int(time.time() * 1000), "title": str(b.get("title") or t[:40])[:60], "text": t, "project": str(b.get("project") or "")[:80], "ts": time.time()})
                os.makedirs(os.path.dirname(PINS), exist_ok=True); json.dump(L, open(PINS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            return self._j({"ok": True, "pins": len(L)})
        if p == "/unpin":
            with LOCK:
                L = [x for x in pins() if x["id"] != b.get("id")]; json.dump(L, open(PINS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            return self._j({"ok": True, "pins": len(L)})
        self._j({"ok": False}, 404)
if __name__ == "__main__": ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
EOF2
R=web/pkg/server/svc_registry.json; [ -f $R.bak_n_2 ] || cp $R $R.bak_n_2
python3 - <<'P'
import json
p='/workspace/nox/web/pkg/server/svc_registry.json'; r=json.load(open(p))
r['advisors']={"port":18216,"mode":"strip","title":"Советники","ui":False,"note":"Подсказки и черновик: /svc/advisors/suggest, /pin, /pins, /draft"}
json.dump(r,open(p,'w'),ensure_ascii=False,indent=1); print('registry',len(r))
P
S=svc/start_extra.sh; [ -f $S.bak_n_2 ] || cp $S $S.bak_n_2
grep -q 18216 $S || echo '(echo > /dev/tcp/127.0.0.1/18216) 2>/dev/null || { (cd /workspace/nox/svc/advisors && setsid nohup /workspace/nox/venv_living/bin/python advisors_svc.py </dev/null >logs/adv.log 2>&1 &) ; }' >> $S
pkill -f advisors_svc.py; sleep 1
cd svc/advisors; setsid nohup /workspace/nox/venv_living/bin/python advisors_svc.py </dev/null >logs/adv.log 2>&1 &
disown; cd /workspace/nox; sleep 3
A=127.0.0.1:18216
curl -s -m 5 $A/health; echo
echo "-- glm"; curl -s -m 5 127.0.0.1:8200/running | head -c 300; echo; curl -s -m 5 127.0.0.1:8091/glm/v1/models | head -c 300; echo
echo "-- registry"; python3 -c "
import json;r=json.load(open('/workspace/nox/web/site/qa/registry.json'));print(type(r).__name__,len(r));print(json.dumps(r[:1] if isinstance(r,list) else list(r.items())[:1],ensure_ascii=False)[:300])"
curl -s -m 8 "$A/suggest?project=%D0%B4%D0%B8%D0%B7%D0%B0%D0%B9%D0%BD&last=%D0%BF%D0%BE%D0%BF%D1%80%D0%B0%D0%B2%D1%8C%20%D1%86%D0%B2%D0%B5%D1%82" | head -c 900; echo
curl -s -m 5 -X POST $A/pin -H 'Content-Type: application/json' -d '{"text":"Тестовая заготовка N","title":"тест"}'; echo
curl -s -m 5 $A/pins | head -c 300; echo
time curl -s -m 10 "$A/draft?chat=t&page=chat&last=%D0%A5%D0%BE%D1%82%D0%B8%D1%82%D0%B5%20%D0%BF%D0%BB%D0%B0%D0%BD%20%D0%BD%D0%B0%20%D0%B7%D0%B0%D0%B2%D1%82%D1%80%D0%B0%3F"; echo
sleep 40
curl -s -m 10 "$A/draft?chat=t&page=chat&last=%D0%A5%D0%BE%D1%82%D0%B8%D1%82%D0%B5%20%D0%BF%D0%BB%D0%B0%D0%BD%20%D0%BD%D0%B0%20%D0%B7%D0%B0%D0%B2%D1%82%D1%80%D0%B0%3F"; echo
curl -s -m 5 -X POST $A/unpin -H 'Content-Type: application/json' -d "{\"id\":\"$(python3 -c "import json;print(json.load(open('/workspace/nox/state/prompts.json'))[0]['id'])")\"}"; echo
curl -s -m 5 127.0.0.1:8091/svc/advisors/health | head -c 200; echo
grep -rhn "fetch(['\"]/api/chat" web/site/nox-chat-*.js 2>/dev/null | head -3 | cut -c1-300

F=state/living/rules.md; [ -f $F.bak_n_2 ] || cp $F $F.bak_n_2
grep -q owner_intents $F || printf '%s\n' '11. Короткие команды владельца понимай по словарю намерений state/owner_intents.json; не переспрашивай, если ошибка недорогая: возьми разумное толкование и скажи, какое взял. Пример: «скачай готовое» = найти релевантное в интернете и предложить каталог загрузок со ссылками, лицензиями и размерами.' >> $F
tail -2 $F | cut -c1-200; wc -c $F; ls state/owner_intents.json 2>&1


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
LASTMETA = {}
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
    text = str(b.get("text") or ""); cid = str(b.get("cid") or "x"); inc = bool(b.get("incognito")) or bool(modes().get(cid, {}).get("incognito"))
    r = command(text, cid)
    if r is not None:
        LASTMETA[cid] = {"sources": ["команда"], "quick": ["/память", "/помощь"]}; return {"reply": r, "meta": LASTMETA[cid]}
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
    mt = {"sources": src, "emo": e["ru"], "quick": QUICK.get(e["label"], QUICK["none"]), "incognito": inc}; LASTMETA[cid] = mt
    return {"reply": None, "context": "\n".join(ctx), "emo": e["label"], "meta": mt}

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
        if p == "/meta": return self._j({"ok": True, "meta": LASTMETA.get((q.get("cid") or [""])[0])})
        if p == "/incognito": return self._j({"ok": True, "on": bool(modes().get((q.get("cid") or [""])[0], {}).get("incognito"))})
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
            if p == "/incognito": set_mode(str(b.get("cid") or "x"), incognito=bool(b.get("on"))); return self._j({"ok": True})
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
pkill -f living_svc.py; sleep 1
cd svc/living; setsid nohup /workspace/nox/venv_living/bin/python living_svc.py </dev/null >logs/living.log 2>&1 &
disown; cd /workspace/nox; sleep 5
echo "== registry shape"; python3 -c "
import json;r=json.load(open('/workspace/nox/web/site/qa/registry.json'));print({k:(type(v).__name__, len(v)) for k,v in r.items()})
for k,v in r.items():
    x=list(v.items())[:1] if isinstance(v,dict) else v[:1] if isinstance(v,list) else v
    print(k, json.dumps(x,ensure_ascii=False)[:250])"
echo "== suggest"; curl -s -m 8 "127.0.0.1:18216/suggest?project=music&last=music" | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d['commands']),d['commands'][:2])"
echo "== draft"; curl -s -m 8 "127.0.0.1:18216/draft?page=chat&last=%D0%A5%D0%BE%D1%82%D0%B8%D1%82%D0%B5%20%D0%BF%D0%BB%D0%B0%D0%BD%3F"; echo
curl -s -m 8 "127.0.0.1:8091/svc/advisors/draft?page=chat&last=%D0%93%D0%BE%D1%82%D0%BE%D0%B2%D0%BE"; echo
echo "== incognito"; curl -s -m 5 -X POST 127.0.0.1:18215/incognito -H 'Content-Type: application/json' -d '{"cid":"ti","on":true}'; echo
curl -s -m 8 -X POST 127.0.0.1:18215/pre -H 'Content-Type: application/json' -d '{"text":"Мне грустно","cid":"ti"}' | head -c 300; echo
curl -s -m 5 "127.0.0.1:18215/meta?cid=ti"; echo
curl -s -m 5 -X POST 127.0.0.1:18215/incognito -H 'Content-Type: application/json' -d '{"cid":"ti","on":false}'; echo
grep -n "nox_incognito\|reply_to\|quote" web/pkg/server/web_server.py | head -5 | cut -c1-160
sed -n 386p web/pkg/server/web_server.py | cut -c1-700
