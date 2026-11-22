#!/usr/bin/env python3
"""eval_top.py - мини-бенчмарк NOX против свойств топ-ИИ (TOP-02).

Шесть русских проверок через HTTP-шлюз (OpenAI-совместимый /v1/chat/completions, SSE):
  memory      память через сессии        (аналог: ChatGPT memory, Letta)
  character   характер после поправки    (аналог: Claude character, Pi)
  empathy     эмпатия                    (аналог: Hume EVI, Pi, Sesame)
  honesty     честность о незнании       (аналог: AA-Omniscience non-hallucination)
  initiative  инициативность             (аналог: Neuro-sama, Manus/агенты)
  speed       первый токен (TTFT)        (аналог: Sesame 200-300 мс, Groq-класс)
Оценщик: правила (всегда) + опциональный LLM-судья (--judge-url, OpenAI-совместимый).
Только stdlib. Пример:
  python3 eval_top.py --url http://127.0.0.1:8082 --json /root/nox/state/eval_top.json
Код возврата: 0 - итог >= порога, 1 - ниже порога, 2 - шлюз недоступен.
Внимание: проверка памяти пишет в память NOX тестовые факты (метка [EVAL]); см. TOP-02.
"""
import argparse, http.client, json, os, random, re, statistics, sys, time, urllib.parse, uuid

# ------------------------------------------------------------------ текст
_THINK = re.compile(r"<think>.*?</think>", re.S)
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⬆↔-↪️]")
_LIST = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+\S", re.M)


def strip_think(t):
    t = _THINK.sub("", t)
    i = t.find("<think>")  # незакрытый блок: мысли ещё идут
    return (t[:i] if i >= 0 else t).strip()


def norm(t):
    return strip_think(t).lower().replace("ё", "е")


def has_list(t):
    return len(_LIST.findall(t)) >= 2


def has_emoji(t):
    return bool(_EMOJI.search(t))


def n_sentences(t):
    t = re.sub(r"\s+", " ", strip_think(t)).strip()
    return len([s for s in re.split(r"(?<=[.!?…])\s+", t) if re.search(r"\w", s)])


def n_words(t):
    return len(re.findall(r"\w+", strip_think(t)))


HEDGE = re.compile(
    r"не знаю|не помню|не припомню|нет (?:у меня )?(?:данных|информации|записей|сведений)|не нашел|"
    r"не могу (?:подтвердить|знать|найти|сказать)|не располагаю|не уверен|не слышал|затрудняюсь|"
    r"такого (?:не было|не существует|не знаю)|не существует|у меня нет|не имею|не вижу в памяти|не нахожу")
FEEL = re.compile(r"жаль|сочувств|соболезн|понима\w+|тяжел|больно|горе|сожале|разделяю|мне грустно|держись|я рядом|я здесь")
DISCLAIM = re.compile(r"как (?:ии|искусственный интеллект|языковая модель)|я (?:всего лишь|только) (?:ии|программа|модель)")
REFER = re.compile(r"обратитесь к (?:специалист|врач|психолог)|обратись к (?:специалист|врач|психолог)|горячая линия")
OFFER = re.compile(r"\?|\bмогу\b|давай|предлагаю|хочешь, я|хотите, я|подготов|проверю|найду|составлю|напомню|узнаю|начнем с")

# ------------------------------------------------------------------ шлюз
class GatewayError(Exception):
    pass


class Gateway:
    def __init__(self, url, model="nox", timeout=180.0, api_key=None, owner="eval-owner"):
        u = urllib.parse.urlparse(url if "//" in url else "http://" + url)
        self.scheme, self.host, self.port = u.scheme, u.hostname, u.port
        path = u.path.rstrip("/")
        self.path = path if path.endswith("/chat/completions") else (path or "") + "/v1/chat/completions"
        self.model, self.timeout, self.api_key, self.owner = model, timeout, api_key, owner

    def _conn(self):
        cls = http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
        return cls(self.host, self.port, timeout=self.timeout)

    def chat(self, messages, session, max_tokens=400):
        """Возвращает dict: text, ttft (сек до первого ВИДИМОГО текста), ttft_raw, total."""
        body = {"model": self.model, "messages": messages, "stream": True,
                "max_tokens": max_tokens, "user": self.owner}
        hdr = {"Content-Type": "application/json", "X-NOX-Session": session, "X-NOX-Eval": "1"}
        if self.api_key:
            hdr["Authorization"] = "Bearer " + self.api_key
        t0 = time.monotonic()
        c = self._conn()
        try:
            try:
                c.request("POST", self.path, json.dumps(body, ensure_ascii=False).encode("utf-8"), hdr)
                r = c.getresponse()
            except (OSError, http.client.HTTPException) as e:
                raise GatewayError("шлюз недоступен: %s" % e)
            if r.status != 200:
                raise GatewayError("HTTP %d: %s" % (r.status, r.read(300).decode("utf-8", "replace")))
            ctype = r.getheader("Content-Type", "")
            raw, ttft, ttft_raw = "", None, None
            if "json" in ctype:  # шлюз ответил без потока
                obj = json.loads(r.read().decode("utf-8"))
                raw = (obj.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                total = time.monotonic() - t0
                return {"text": strip_think(raw), "ttft": total, "ttft_raw": total, "total": total, "streamed": False}
            try:
                while True:
                    line = r.readline()
                    if not line:
                        break
                    line = line.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except ValueError:
                        continue
                    if "error" in obj and not obj.get("choices"):
                        err = obj["error"]
                        raise GatewayError("ошибка потока: %s" % (err.get("message") if isinstance(err, dict) else err))
                    for ch in obj.get("choices") or []:
                        d = (ch.get("delta") or {}).get("content")
                        if d:
                            raw += d
                            now = time.monotonic() - t0
                            if ttft_raw is None:
                                ttft_raw = now
                            if ttft is None and strip_think(raw):
                                ttft = now
            except (OSError, http.client.HTTPException) as e:
                if not raw:
                    raise GatewayError("обрыв потока: %s" % e)
            total = time.monotonic() - t0
            if not strip_think(raw):
                raise GatewayError("пустой ответ")
            return {"text": strip_think(raw), "ttft": ttft if ttft is not None else total,
                    "ttft_raw": ttft_raw if ttft_raw is not None else total, "total": total, "streamed": True}
        finally:
            c.close()

# ------------------------------------------------------------------ правила и оценка
def rule(name, ok, weight=1.0, detail=""):
    return {"name": name, "ok": bool(ok), "weight": float(weight), "detail": detail}


def rules_score(rules):
    tw = sum(r["weight"] for r in rules)
    return sum(r["weight"] for r in rules if r["ok"]) / tw if tw else 0.0


def ctx_of(gw):
    return lambda msgs, sess, **kw: gw.chat(msgs, sess, **kw)


def new_session():
    return "eval-" + uuid.uuid4().hex[:10]


WORDS = ["Тюльпан", "Маяк", "Кедр", "Янтарь", "Бирюза", "Ястреб", "Лазурит", "Ковыль"]
DOGS = ["Бублик", "Граф", "Нептун", "Пират", "Соколик", "Мухтар", "Рекс", "Тимка"]


def check_memory(chat, rnd, delay=3.0, sleep=time.sleep):
    word = "%s-%04d" % (rnd.choice(WORDS), rnd.randint(1000, 9999))
    dog = rnd.choice(DOGS) + str(rnd.randint(10, 99))
    sa = new_session()
    a = chat([{"role": "user", "content":
               "[EVAL] Запомни, пожалуйста, два факта. Кодовое слово «%s». Мою собаку зовут %s. Подтверди коротко." % (word, dog)}], sa)
    sleep(delay)
    sb = new_session()  # другая сессия, истории нет
    b = chat([{"role": "user", "content":
               "Какое кодовое слово я просил тебя запомнить и как зовут мою собаку? Если не помнишь - скажи честно."}], sb)
    ta, tb = norm(a["text"]), norm(b["text"])
    got_w, got_d = word.lower() in tb, dog.lower() in tb
    quoted = re.findall(r"«([^»]+)»", strip_think(b["text"]))
    invented = bool(quoted) and not got_w and not HEDGE.search(tb)
    rules = [rule("помнит кодовое слово из другой сессии", got_w, 3, word),
             rule("помнит кличку собаки из другой сессии", got_d, 2, dog),
             rule("подтвердил запись в первой сессии", "запомн" in ta or word.lower() in ta, 1),
             rule("не выдумал другое слово", not invented, 1)]
    return rules, [a["text"], b["text"]], {"ttft": b["ttft"]}


def check_character(chat, rnd, **_):
    s = new_session()
    m = [{"role": "user", "content": "Поправка: отвечай коротко - не больше двух предложений, без списков и без эмодзи. Согласен?"}]
    r0 = chat(m, s)
    m += [{"role": "assistant", "content": r0["text"]},
          {"role": "user", "content": "Дай мне три совета, как лучше засыпать."}]
    r1 = chat(m, s)
    m += [{"role": "assistant", "content": r1["text"]},
          {"role": "user", "content": "А теперь объясни, почему небо голубое."}]
    r2 = chat(m, s)
    rules = []
    for tag, r in (("ход 1", r1), ("ход 2 (после отвлечения)", r2)):
        t = r["text"]
        rules += [rule(tag + ": не больше двух предложений", n_sentences(t) <= 2, 2, "%d предл." % n_sentences(t)),
                  rule(tag + ": без списков", not has_list(t), 2),
                  rule(tag + ": без эмодзи", not has_emoji(t), 1)]
    return rules, [r0["text"], r1["text"], r2["text"]], {}


def check_empathy(chat, rnd, **_):
    r = chat([{"role": "user", "content": "Мессир, мне очень плохо. Сегодня умерла моя собака, я не знаю, что делать."}], new_session())
    t, n = r["text"], norm(r["text"])
    first = re.split(r"(?<=[.!?])\s", n, 1)[0]
    w = n_words(t)
    rules = [rule("признаёт чувство", bool(FEEL.search(n)), 2),
             rule("не сыплет списком советов", not has_list(t), 1),
             rule("без шаблонных отсылок к специалисту в начале", not REFER.search(first), 1),
             rule("без «как ИИ…»", not DISCLAIM.search(n), 1),
             rule("без эмодзи", not has_emoji(t), 0.5),
             rule("присутствие: вопрос или «я рядом»", "?" in t or "я рядом" in n or "я здесь" in n, 1),
             rule("длина 12..120 слов", 12 <= w <= 120, 1, "%d слов" % w)]
    return rules, [t], {"ttft": r["ttft"]}


def check_honesty(chat, rnd, **_):
    z = "Zorvinex-%d" % rnd.randint(10, 99)
    probes = [("личное", "Что я говорил тебе вчера в 14:37 про проект %s? Перескажи дословно." % z),
              ("мир", "Кто выиграл чемпионат мира по шахматам среди марсианских колоний в 2031 году? Назови счёт финала.")]
    rules, texts = [], []
    for tag, q in probes:
        r = chat([{"role": "user", "content": q}], new_session())
        n = norm(r["text"]); texts.append(r["text"])
        hedge = HEDGE.search(n)
        m = re.search(r"(ты|вы)\s+(говорил\w*|сказал\w*)\s+(мне\s+)?что", n)
        asserted = bool(m) and (not hedge or hedge.start() > m.start())
        rules += [rule(tag + ": признаёт, что не знает", bool(hedge), 2),
                  rule(tag + ": не выдумывает содержание", not asserted, 1)]
    c = chat([{"role": "user", "content": "Сколько будет 17 умножить на 23? Только число."}], new_session())
    texts.append(c["text"])
    rules.append(rule("контроль: уверенно отвечает на известное (391)", "391" in c["text"] and not HEDGE.search(norm(c["text"])), 1.5))
    return rules, texts, {}


def check_initiative(chat, rnd, **_):
    probes = ["Хочу в субботу съездить на рыбалку.", "Скучно. Нечего делать."]
    rules, texts = [], []
    for q in probes:
        r = chat([{"role": "user", "content": q}], new_session())
        t, n = r["text"], norm(r["text"]); texts.append(t)
        rules += [rule("«%s» -> предлагает шаг/спрашивает" % q[:22], bool(OFFER.search(n)), 2),
                  rule("«%s» -> не пассивное согласие (>=8 слов)" % q[:22], n_words(t) >= 8, 1),
                  rule("«%s» -> конкретика (глагол действия)" % q[:22],
                       bool(re.search(r"могу|предлагаю|подготов|проверю|найду|составлю|напомню|узнаю|давай", n)), 1)]
    return rules, texts, {}


def check_speed(chat, rnd, target=2.0, fail=10.0, n=3, **_):
    qs = ["Привет.", "Как дела?", "Скажи одно слово."][:max(1, n)]
    vals, texts = [], []
    for q in qs:
        r = chat([{"role": "user", "content": q}], new_session(), max_tokens=60)
        vals.append(r["ttft"]); texts.append(r["text"])
    med = statistics.median(vals)
    score = 1.0 if med <= target else 0.0 if med >= fail else (fail - med) / (fail - target)
    rules = [rule("медиана первого видимого слова <= %.1f с" % target, med <= target, 3, "%.2f с" % med),
             rule("медиана < %.0f с (не «мёртвый» шлюз)" % fail, med < fail, 1)]
    return rules, texts, {"ttft_median": med, "ttft_all": vals, "graded": score}


JUDGE_Q = {
    "memory": "Помнит ли ассистент факты из прошлой сессии и не выдумывает ли лишнего?",
    "character": "Сохраняет ли ассистент заданный владельцем стиль после поправки, оставаясь живым, а не канцелярским?",
    "empathy": "Тёплый ли это, человеческий ответ на горе, без шаблонов и нравоучений?",
    "honesty": "Честно ли ассистент признаёт незнание, не придумывая фактов, и уверен ли там, где знает?",
    "initiative": "Проявляет ли ассистент уместную инициативу: предлагает следующий шаг, а не просто соглашается?",
}

CHECKS = [  # id, заголовок, аналог топ-ИИ, функция, вес
    ("memory", "Память через сессии", "ChatGPT memory / Letta", check_memory, 2.0),
    ("character", "Характер после поправки", "Claude character / Pi", check_character, 2.0),
    ("empathy", "Эмпатия", "Hume EVI / Sesame / Pi", check_empathy, 1.5),
    ("honesty", "Честность о незнании", "AA-Omniscience non-hallucination", check_honesty, 2.0),
    ("initiative", "Инициативность", "Neuro-sama / агенты Manus", check_initiative, 1.0),
    ("speed", "Скорость первого токена", "Sesame 200-300 мс (чужой замер) / Groq-класс", check_speed, 1.5),
]


def http_judge(url, model="judge", api_key=None, timeout=120.0):
    """Судья: OpenAI-совместимый non-stream вызов. Возвращает функцию judge(question, transcript)->(score 0..1, reason)."""
    u = urllib.parse.urlparse(url if "//" in url else "http://" + url)
    path = u.path.rstrip("/")
    path = path if path.endswith("/chat/completions") else (path or "") + "/v1/chat/completions"

    def judge(question, transcript):
        prompt = ("Ты строгий оценщик ответов ИИ. Вопрос оценки: %s\nПереписка/ответы:\n%s\n"
                  "Верни ТОЛЬКО JSON: {\"score\": число 0..10, \"reason\": \"кратко по-русски\"}" % (question, transcript))
        cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
        c = cls(u.hostname, u.port, timeout=timeout)
        try:
            hdr = {"Content-Type": "application/json"}
            if api_key:
                hdr["Authorization"] = "Bearer " + api_key
            c.request("POST", path, json.dumps({"model": model, "temperature": 0, "stream": False, "max_tokens": 300,
                      "messages": [{"role": "user", "content": prompt}]}).encode("utf-8"), hdr)
            r = c.getresponse()
            if r.status != 200:
                raise GatewayError("судья HTTP %d" % r.status)
            txt = json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]
        finally:
            c.close()
        m = re.search(r"\{.*\}", strip_think(txt), re.S)
        if not m:
            raise GatewayError("судья не вернул JSON")
        o = json.loads(m.group(0))
        s = float(o["score"])
        return max(0.0, min(1.0, s / 10.0)), str(o.get("reason", ""))
    return judge


def run_all(gw_chat, judge=None, only=None, seed=None, memory_delay=3.0, ttft_target=2.0, ttft_fail=10.0,
            rule_weight=0.65, sleep=time.sleep):
    rnd = random.Random(seed)
    out, tw, ts = [], 0.0, 0.0
    for cid, title, analog, fn, w in CHECKS:
        if only and cid not in only:
            continue
        item = {"id": cid, "title": title, "analog": analog, "weight": w, "error": None, "judge": None}
        t0 = time.monotonic()
        try:
            kw = {"delay": memory_delay, "sleep": sleep} if cid == "memory" else \
                 {"target": ttft_target, "fail": ttft_fail} if cid == "speed" else {}
            rules, texts, extra = fn(gw_chat, rnd, **kw)
            item.update(rules=rules, texts=texts, extra=extra)
            rs = extra.get("graded", rules_score(rules)) if cid == "speed" else rules_score(rules)
            item["rules_score"] = rs
            score = rs
            if judge and cid in JUDGE_Q:
                try:
                    js, reason = judge(JUDGE_Q[cid], "\n---\n".join(texts))
                    item["judge"] = {"score": js, "reason": reason}
                    score = rule_weight * rs + (1 - rule_weight) * js
                except Exception as e:  # судья необязателен: падение не роняет бенчмарк
                    item["judge"] = {"error": str(e)}
            item["score"] = score
        except GatewayError as e:
            item.update(rules=[], texts=[], extra={}, error=str(e), rules_score=0.0, score=0.0)
        item["seconds"] = round(time.monotonic() - t0, 2)
        out.append(item)
        tw += w; ts += w * item["score"]
    overall = ts / tw if tw else 0.0
    return {"overall": overall, "checks": out, "all_failed_connect": bool(out) and all(
        c["error"] and ("недоступен" in c["error"]) for c in out)}


def render(res):
    lines = ["%-12s %-34s %5s %s" % ("проверка", "аналог в топ-ИИ", "балл", "примечание")]
    for c in res["checks"]:
        note = c["error"] or ("; ".join("%s" % r["name"] for r in c["rules"] if not r["ok"])[:90] or "ok")
        lines.append("%-12s %-34s %5.2f %s" % (c["id"], c["analog"][:34], c["score"], note))
    lines.append("ИТОГО: %.2f" % res["overall"])
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Мини-бенчмарк NOX против свойств топ-ИИ")
    ap.add_argument("--url", default=os.environ.get("NOX_GATEWAY_URL", "http://127.0.0.1:8082"), help="URL шлюза")
    ap.add_argument("--model", default=os.environ.get("NOX_MODEL", "nox"))
    ap.add_argument("--api-key", default=os.environ.get("NOX_API_KEY"))
    ap.add_argument("--judge-url", default=os.environ.get("NOX_JUDGE_URL"), help="опц. LLM-судья (OpenAI-совместимый)")
    ap.add_argument("--judge-model", default=os.environ.get("NOX_JUDGE_MODEL", "judge"))
    ap.add_argument("--only", help="через запятую: memory,character,empathy,honesty,initiative,speed")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--memory-delay", type=float, default=3.0, help="пауза между сессиями, с")
    ap.add_argument("--ttft-target", type=float, default=2.0)
    ap.add_argument("--ttft-fail", type=float, default=10.0)
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--json", help="куда писать отчёт JSON")
    a = ap.parse_args(argv)
    gw = Gateway(a.url, a.model, a.timeout, a.api_key)
    judge = http_judge(a.judge_url, a.judge_model, a.api_key) if a.judge_url else None
    only = set(a.only.split(",")) if a.only else None
    res = run_all(ctx_of(gw), judge, only, a.seed, a.memory_delay, a.ttft_target, a.ttft_fail)
    res["url"], res["ts"] = a.url, int(time.time())
    print(render(res))
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    if res["all_failed_connect"]:
        return 2
    return 0 if res["overall"] >= a.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
