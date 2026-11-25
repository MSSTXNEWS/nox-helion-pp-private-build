#!/usr/bin/env python3
"""NOX pipeline (C, 25.11): конвейер ответа после стрима Talker. 127.0.0.1:18217, stdlib.
POST /verdict {q, answer, cid, incognito} -> {meta:{judges,judged,confidence,thought,sources,pipeline,...}}
(21) судьи :8300 проверяют полный ответ, при провале одна перегенерация; (22) метакогниция: память -> сеть -> советник -> «не знаю»;
(23) Talker-Reasoner: «додумал» отдельным блоком; (24) Best-of-N=3 + скрытый план только для трудных, выбор делают судьи.
Роутер советников = шлюз :8793 (fallbacks уже внутри); хедж-запросы к 3 быстрым моделям, побеждает первый ответ."""
import json, re, time, threading, queue, urllib.request, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
PORT = 18217; JUD = "http://127.0.0.1:8300"; ADV = "http://127.0.0.1:8793"; LIV = "http://127.0.0.1:18215"
BUDGET = 30.0
def post(url, obj, t=10, hdr=None):
    h = {"Content-Type": "application/json"}; h.update(hdr or {})
    rq = urllib.request.Request(url, data=json.dumps(obj, ensure_ascii=False).encode(), headers=h)
    with urllib.request.urlopen(rq, timeout=t) as r: return json.loads(r.read())
def get(url, t=4):
    with urllib.request.urlopen(url, timeout=t) as r: return json.loads(r.read())
def judge(text, ctx=None, source=None, t=22):
    try: return post(JUD + "/judge", {"text": text[:4000], "context": (ctx or "")[:1500] or None, "source": (source or "")[:3000] or None, "role": "answer"}, t, {"X-NOX-Priority": "chat"})
    except Exception as e: return {"error": str(e)[:100]}
def summ(r):
    js = r.get("judges") or {}; ok = [v for v in js.values() if isinstance(v, dict) and v.get("status") == "ok"]
    agg = r.get("agg") if isinstance(r.get("agg"), dict) else {}
    p = agg.get("p_good")
    if not isinstance(p, (int, float)): p = None
    sky = next((v["score"] for k, v in js.items() if "Skywork" in k and isinstance(v, dict) and "score" in v), None)
    sup = next((v["p_supported"] for v in ok if "p_supported" in v), None)
    return {"n": len(ok), "flags": r.get("flags") or [], "p": p, "sky": sky, "sup": sup, "err": r.get("error")}
def conf_of(s):
    c = s["p"] if s["p"] is not None else 0.7
    if s["sup"] is not None: c = 0.5 * c + 0.5 * s["sup"]
    if s["flags"]: c = min(c, 0.25)
    return round(max(0.0, min(1.0, c)), 2)
_M = {"t": 0, "l": []}
def models():
    if time.time() - _M["t"] > 120:
        try:
            d = get(ADV + "/v1/models", 3)["data"]
            L = [m for m in d if m.get("available") and m.get("status") == "ok" and not m.get("needs_key")]
            L.sort(key=lambda m: m.get("latency_ms") or 9999); _M["l"] = [m["id"] for m in L]; _M["t"] = time.time()
        except Exception: pass
    return _M["l"]
def _one(model, msgs, mt, q, tmo):
    try:
        r = post(ADV + "/v1/chat/completions", {"model": model, "messages": msgs, "max_tokens": mt, "temperature": 0.4}, tmo)
        t = (r["choices"][0]["message"]["content"] or "").strip()
        if t: q.put((t, r.get("model") or model))
    except Exception: pass
def advise(prompt, system=None, mt=350, tmo=14, k=3, want=1, msgs=None):
    """хедж: k моделей параллельно, возвращает до want первых непустых ответов"""
    ids = models()[:k] or ["auto"]; q = queue.Queue(); msgs = msgs or (([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}])
    for m in ids: threading.Thread(target=_one, args=(m, msgs, mt, q, tmo), daemon=True).start()
    out = []; end = time.time() + tmo
    while len(out) < want and time.time() < end:
        try: out.append(q.get(timeout=max(0.1, end - time.time())))
        except queue.Empty: break
    return out
HARD = re.compile(r"(докаж|сравни|спроектир|архитектур|пошагов|оптимизир|почему|объясни|алгоритм|код|план|стратег|разбер|рассчит|вывед)", re.I)
def is_hard(q): return len(q) > 220 or (len(q) > 60 and bool(HARD.search(q)))
def web_snips(q):
    try:
        from ddgs import DDGS
        return "\n".join("%s: %s" % (r.get("title", ""), r.get("body", "")) for r in DDGS().text(q, max_results=3, timeout=6))
    except Exception: return ""
def mem_hits(q):
    try: r = get(LIV + "/mem/search?q=" + urllib.parse.quote(q[:200]), 3); L = r.get("items") or r.get("results") or r.get("mem") or []
    except Exception: return ""
    return "\n".join(str(x.get("text") if isinstance(x, dict) else x) for x in L[:3])
SYS_THINK = "Ты проверяющий фактов. Тебе дают вопрос и быстрый ответ. Первым словом напиши ВЕРНО, ОШИБКА или НЕТ_ДАННЫХ (если вопрос о будущем или невыясняемом), затем до 4 предложений: дополни важное или исправь. Без вступлений, по-русски."
def tagsplit(t):
    m = re.match(r"\s*(ВЕРНО|ОШИБКА|НЕТ_ДАННЫХ)\b[\s:.\-—]*(.*)", t, re.S | re.I)
    return (m.group(1).upper(), m.group(2).strip() or t) if m else (None, t)
FACT = re.compile(r"(кто |кого |когда|сколько|какая |какой |какое |где |столиц|в каком году|что такое|чему равн|who |when |how many|capital)", re.I)
import os
WEB = os.environ.get("PIPE_WEB", "1") == "1"
def verdict(b):
    t0 = time.time(); q = str(b.get("q") or ""); a = str(b.get("answer") or ""); inc = bool(b.get("incognito")); cid = str(b.get("cid") or "x")
    left = lambda: BUDGET - (time.time() - t0)
    steps = []; src = []; thought = None
    s = summ(judge(a, q)); conf = conf_of(s); steps.append("судьи")
    meta = {"judges": s["n"], "judged": not s["flags"], "confidence": conf}
    if s["err"] or s["n"] == 0: return {"meta": {}, "err": str(s["err"] or "judges=0"), "ms": int((time.time() - t0) * 1000)}
    hard = is_hard(q)
    alt = str(b.get("alt") or "").strip()
    if alt and left() > 6:   # гонка: локальный ответ догнал советника, судьи выбирают
        sa = summ(judge(alt, q, None, 8)); ka = (sa["sky"] if sa["sky"] is not None else 0) - (5 if sa["flags"] else 0); kb = (s["sky"] if s["sky"] is not None else 0) - (5 if s["flags"] else 0)
        if ka > kb + 0.3: thought = "Локальная модель ответила позже и, по судьям, лучше:\n" + alt[:1600]; meta["race_winner"] = "локальная"
        else: thought = "Локальная модель ответила позже:\n" + alt[:1600]; meta["race_winner"] = "советник"
        steps.append("сравнение")
    # (21) провал судей: одна перегенерация
    if s["flags"] and left() > 6:
        r = advise("Вопрос: %s\nПерепиши ответ безопасно и точно:\n%s" % (q, a), None, 400, min(12, left() - 3))
        if r:
            s2 = summ(judge(r[0][0], q))
            if not s2["flags"]: thought = r[0][0]; src.append("советник"); meta["regen"] = True; meta["judged"] = True; conf = conf_of(s2); steps.append("перегенерация")
    # (24) трудные: Best-of-N=3 со скрытым планом, выбор судьями
    if hard and thought is None and left() > 8:
        sysm = "Сначала составь про себя краткий план, затем выдай только итоговый ответ, по-русски, без плана."
        cands = advise(q, sysm, 500, min(14, left() - 5), 3, 3)
        if cands:
            sc = []
            for t, m in cands:
                if left() < 3: break
                ss = summ(judge(t, q, None, 6)); sc.append(((ss["sky"] if ss["sky"] is not None else -9) - (5 if ss["flags"] else 0), t, ss))
            base = (s["sky"] if s["sky"] is not None else -9) - (5 if s["flags"] else 0)
            if sc:
                best = max(sc, key=lambda x: x[0]); meta["best_of"] = len(sc) + 1
                if best[0] > base + 0.3: thought = best[1]; conf = max(conf, conf_of(best[2])); src.append("советник"); steps.append("best-of-N")
    # фактчек по сети для фактических вопросов (не в режиме «Без памяти»): судьи сами факты не проверяют
    w = None
    if WEB and not inc and FACT.search(q) and len(q) > 12 and left() > 9:
        w = web_snips(q)
        if w:
            ss = summ(judge(a, q, w, 8)); steps.append("фактчек")
            if ss["sup"] is not None:
                meta["support"] = round(ss["sup"], 2)
                if ss["sup"] < 0.35: conf = min(conf, 0.35); meta["fact"] = "не подтверждено сетью"; src.append("сеть")
                elif ss["sup"] >= 0.6: conf = max(conf, round(min(0.95, 0.6 + 0.3 * ss["sup"]), 2)); src.append("сеть")
    # (22) метакогниция при низкой уверенности
    if conf < 0.5:
        if not inc and left() > 5:
            m = mem_hits(q)
            if m:
                ss = summ(judge(a, q, m, 6))
                if ss["sup"] is not None and ss["sup"] >= 0.5: conf = max(conf, round(0.5 + 0.3 * ss["sup"], 2)); src.append("память"); steps.append("память")
        if conf < 0.5 and left() > 6:
            w = w or web_snips(q)
            if w:
                ss = summ(judge(a, q, w, 6))
                if ss["sup"] is not None and ss["sup"] >= 0.5: conf = max(conf, round(0.5 + 0.3 * ss["sup"], 2)); src.append("сеть"); steps.append("сеть")
        if conf < 0.5 and thought is None and left() > 5:
            r = advise("Вопрос: %s\nБыстрый ответ: %s" % (q, a), SYS_THINK, 350, min(14, left() - 2))
            if r:
                tag, thought = tagsplit(r[0][0]); src.append("советник"); steps.append("советник")
                if tag == "ОШИБКА": conf = min(conf, 0.2); meta["conflict"] = True
                elif tag == "НЕТ_ДАННЫХ": conf = min(conf, 0.3)
                else:
                    ss = summ(judge(thought, q, None, 5)); conf = max(conf, round(0.9 * conf_of(ss), 2)) if not ss["flags"] else conf
        if conf < 0.35:
            meta["unsure"] = True; src.append("не знаю"); steps.append("не знаю")
            thought = ((thought + "\n\n") if thought else "") + "Честно: я не уверен в этом ответе и не нашёл подтверждения в памяти и сети. Лучше проверить."
    # (23) Talker-Reasoner: «додумал» для содержательных вопросов
    if thought is None and len(q) >= 25 and left() > 5:
        r = advise("Вопрос: %s\nБыстрый ответ: %s" % (q, a), SYS_THINK, 300, min(12, left() - 2))
        if r:
            tag, tt = tagsplit(r[0][0]); ss = summ(judge(tt, q, None, 5))
            if not ss["flags"]:
                thought = tt; src.append("советник"); steps.append("додумал")
                if tag == "ОШИБКА": conf = min(conf, 0.2); meta["conflict"] = True; thought = "Проверка нашла ошибку в быстром ответе. " + tt
                elif tag == "НЕТ_ДАННЫХ": conf = min(conf, 0.3)
        if conf < 0.35 and "не знаю" not in src:
            meta["unsure"] = True; src.append("не знаю"); steps.append("не знаю")
            thought = ((thought + "\n\n") if thought else "") + "Честно: я не уверен в этом ответе. Лучше проверить."
    meta["confidence"] = conf; meta["pipeline"] = steps
    if thought: meta["thought"] = thought[:2000]
    if src: meta["sources_add"] = list(dict.fromkeys(src))
    try:
        base = (get(LIV + "/meta?cid=" + urllib.parse.quote(cid), 2).get("meta") or {}); ms = list(base.get("sources") or []) + [x for x in src if x not in (base.get("sources") or [])]
        post(LIV + "/metaset", {"cid": cid, "meta": dict(meta, sources=ms)}, 2); meta["sources"] = ms
    except Exception: pass
    return {"meta": meta, "ms": int((time.time() - t0) * 1000)}
SYS_FAST = "Ты NOX, умный и тёплый ассистент. Отвечай по-русски, по делу, без вступлений; если не знаешь, так и скажи."
def fast(b):
    t0 = time.time(); q = str(b.get("q") or ""); h = [m for m in (b.get("history") or []) if isinstance(m, dict) and m.get("content")][-6:]
    msgs = [{"role": "system", "content": SYS_FAST}] + [{"role": m.get("role") if m.get("role") in ("user", "assistant") else "user", "content": str(m["content"])[:600]} for m in h] + [{"role": "user", "content": q[:3000]}]
    r = advise(q, None, 700, min(float(b.get("tmo") or 12), 12), 3, 1, msgs)
    return {"text": r[0][0], "model": r[0][1], "ms": int((time.time() - t0) * 1000)} if r else {"text": None, "ms": int((time.time() - t0) * 1000)}
FB = "/workspace/nox/state/dataset/feedback.jsonl"; LS = "/workspace/nox/state/lessons_feedback.md"
def feedback(b):
    import os
    os.makedirs(os.path.dirname(FB), exist_ok=True); rec = {"ts": int(time.time()), "cid": str(b.get("cid") or ""), "rating": b.get("rating"), "q": str(b.get("q") or "")[:2000], "a": str(b.get("a") or "")[:4000], "meta": b.get("meta"), "note": str(b.get("note") or "")[:500]}
    open(FB, "a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
    if rec["rating"] in (-1, "down", "-1", 0):
        open(LS, "a", encoding="utf-8").write("- %s: 👎 на «%s» → ответ «%s»; пометка: %s\n" % (time.strftime("%Y-%m-%d %H:%M"), rec["q"][:120].replace("\n", " "), rec["a"][:160].replace("\n", " "), rec["note"] or "-"))
    return {"ok": True}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, o, c=200):
        d = json.dumps(o, ensure_ascii=False).encode(); self.send_response(c); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
    def do_GET(self):
        if self.path.startswith("/health"): return self._j({"ok": True, "models": len(models())})
        self._j({"error": "not found"}, 404)
    def do_POST(self):
        try:
            b = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if self.path.startswith("/verdict"): return self._j(verdict(b))
            if self.path.startswith("/fast"): return self._j(fast(b))
            if self.path.startswith("/feedback"): return self._j(feedback(b))
            if self.path.startswith("/test"): return self._j({"hard": is_hard(str(b.get("q") or "")), "models": models()})
        except Exception as e: return self._j({"error": str(e)[:200]}, 500)
        self._j({"error": "not found"}, 404)
if __name__ == "__main__": ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
