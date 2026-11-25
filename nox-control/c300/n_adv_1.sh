echo "C300: n_adv_1"
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
def commands():
    r = jl(REG, [])
    if isinstance(r, dict): r = r.get("commands") or r.get("items") or list(r.values())
    out = []
    for c in r if isinstance(r, list) else []:
        if isinstance(c, dict) and c.get("id"): out.append({"id": c["id"], "title": c.get("title") or c["id"], "confirm": bool(c.get("confirm")), "endpoint": c.get("endpoint"), "_k": toks(str(c.get("id")) + " " + str(c.get("title")) + " " + str(c.get("desc", "")))})
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
    try:
        d = get(GLM + "/models", 2).get("data", [])
        if d: return d[0]["id"]
    except Exception: pass
    return None
def llm(system, user, max_tokens=40, timeout=60):
    m = pick_model()
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
        with LOCK: CACHE[key] = (time.time(), "")
    finally: SEM.release()
def draft(q):
    chat, page, last, typed = [(q.get(k) or [""])[0] for k in ("chat", "page", "last", "typed")]
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
    return {"draft": "", "pending": True}
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
