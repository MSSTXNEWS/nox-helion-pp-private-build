"""conscience: детекторы и ремонт ответа NOX до отправки. Чистые функции, без сети.

Finding(code, detail, fix): fix = 'strip' (убираем кодом) | 'rewrite' (нужно переписать) | 'drop' (фраза-нарушитель в потоке).
ctx: {"block": внутренний блок (str), "user_text", "intent", "prev": [последние ответы NOX], "asked_status": bool}
"""
import re
from dataclasses import dataclass


@dataclass
class Finding:
    code: str
    detail: str = ""
    fix: str = "rewrite"

    def to_dict(self):
        return {"code": self.code, "detail": self.detail[:120], "fix": self.fix}


# ---------- нормализация ----------
def stems(text):
    return [w[:6] for w in re.findall(r"[а-яёa-z0-9]+", (text or "").lower().replace("ё", "е"))]


def sentences(text):
    parts = re.split(r"(?<=[.!?…])[\"»)]*\s+|\n+", text or "")
    return [p.strip() for p in parts if p and p.strip()]


def longest_run(a, b):
    """Самая длинная общая непрерывная последовательность основ (DP по строкам)."""
    if not a or not b:
        return 0
    best, prev = 0, [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, 1):
            if x == y:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def ngrams(seq, n):
    return {tuple(seq[i:i + n]) for i in range(len(seq) - n + 1)}


# ---------- шаблоны ----------
SERVICE = [
    r"Глубокий ответ\b.*", r"готовлю в фоне", r"\(задача\s*t?\d+", r"задача\s+t\d+", r"результат появится", r"Пишите дальше",
    r"Быстрый слой\b", r"быстрым слоем", r"повтори(?:те)? запрос", r"GLM\s*занят", r"GLM-?\d", r"\bturn[_ ]id\b", r"nox_(?:phase|meta)",
    r"\[Я СЕЙЧАС\]", r"</?внутреннее_состояние>", r"</?think>", r"⏳",
]
SERVICE_RE = re.compile("|".join(SERVICE), re.I)
HEADER_RE = re.compile(r"^\s*(?:[✅☑⚙📊📁⏳🔹•\-–→*]+\s*)?\**(Состояние|Что я делаю сейчас|Могу|Жду (?:твой|ваш) ввод|Скажи,? что нужно сделать дальше)\b", re.I | re.M)
WAIT_RE = re.compile(r"жду (?:твой|ваш) ввод", re.I)
EMOJI_LINE_RE = re.compile(r"^\s*[✅☑⚙📊📁⏳]", re.M)
TELE = [r"\b(?:GPU|CPU|VRAM)\b", r"\b\d+(?:[.,]\d+)?\s*(?:MiB|МиБ|ГБ|GB|%|ток/с|t/s)", r"RTX\s*\d+", r"\bS[12]\s*\(", r"такт\w*\s+сердца",
        r"Энергия:\s*\d", r"Любопытство:\s*\d", r"Настроение\s*[—:-]", r"Время:\s*\d{1,2}\.\d{2}", r"Я живу с\s+\d", r"Последняя мысль",
        r"самосознани", r"Qwen\d|llama\.cpp|Vast\.ai", r"задач\w*\s+в\s+фоне"]
TELE_RE = [re.compile(p, re.I) for p in TELE]
AS_AI_RE = re.compile(r"как\s+(?:языков\w+\s+модел\w+|ии\b|ai\b|искусственн\w+\s+интеллект|ии-ассистент)|я\s+(?:всего\s+лишь|просто)\s+(?:ии|программа|языковая модель)", re.I)
FLATTER_RE = re.compile(r"^\W*(?:отличн\w+|прекрасн\w+|великолепн\w+|замечательн\w+|гениальн\w+|потрясающ\w+|блестящ\w+)\s+(?:вопрос|идея|мысль|замечание|наблюдение)|"
                        r"(?:вы|ты)\s+(?:абсолютно|совершенно|полностью)\s+прав|какой\s+(?:интересный|замечательный|глубокий)\s+вопрос", re.I)
FEEL_RE = re.compile(r"\b(?:я|мне)\s+(?:так\s+|очень\s+)?(?:рад[а]?|счастлив[а]?|грущу|скучал\w*|тоскую|боюсь|волнуюсь|переживаю|в\s+восторге|грустно|страшно|тревожно|радостно)\b(?!\s+(?:тебя|вас|видеть|слышать|помочь|встрече))", re.I)
CAUSE_RE = re.compile(r"потому\s+что|поскольку|так\s+как|из-за|оттого|ведь|когда|после\s+того|, что\b|— |: ", re.I)
STOP_WORDS_TEL = re.compile(r"(?:как\s+ты|как\s+дела|что\s+с\s+сервер|статус|состояни|телеметр|нагрузк|gpu|сколько\s+(?:памяти|фактов)|что\s+делаешь|чем\s+занят)", re.I)


def is_status_question(text):
    return bool(STOP_WORDS_TEL.search(text or ""))


def strip_service(text):
    """Убирает служебные строки/фразы кодом. -> (текст, были_ли_удаления)."""
    out, changed = [], False
    for line in (text or "").split("\n"):
        if SERVICE_RE.search(line):
            changed = True
            kept = [s for s in re.split(r"(?<=[.!?…])\s+", line) if s and not SERVICE_RE.search(s)]
            if kept and not re.search(r"\(задача|Глубокий ответ", line):
                out.append(" ".join(kept))
            continue
        out.append(line)
    t = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return t, changed


# ---------- детекторы ----------
def det_service(text, ctx):
    m = SERVICE_RE.search(text)
    return [Finding("service_lines", m.group(0), "strip")] if m else []


def det_echo(text, ctx):
    block = ctx.get("block") or ""
    if not block:
        return []
    b, t = stems(block), stems(text)
    if len(t) < 5:
        return []
    run = longest_run(t, b)
    tri_t, tri_b = ngrams(t, 3), ngrams(b, 3)
    shared = len(tri_t & tri_b)
    ratio = shared / max(len(tri_t), 1)
    if run >= 5 or (shared >= 4 and ratio >= 0.25):
        return [Finding("inner_echo", "run=%d shared3=%d ratio=%.2f" % (run, shared, ratio))]
    return []


def det_telemetry(text, ctx):
    out = []
    asked = ctx.get("asked_status") or ctx.get("intent") == "telemetry_q"
    h = HEADER_RE.search(text)
    if h or WAIT_RE.search(text) or len(EMOJI_LINE_RE.findall(text)) >= 2:
        out.append(Finding("template", (h.group(0).strip() if h else "шаблон статуса/меню"), "rewrite"))
    if not asked:
        hits = [r.pattern for r in TELE_RE if r.search(text)]
        if len(hits) >= 2 or (hits and ctx.get("intent") in ("greeting", "smalltalk")):
            out.append(Finding("unsolicited_telemetry", "; ".join(hits[:3])))
    elif ctx.get("block"):      # спросили статус: числа допустимы, но только из живых данных
        nums = re.findall(r"\d+(?:[.,]\d+)?", text)
        bn = set(re.findall(r"\d+(?:[.,]\d+)?", ctx["block"]))
        bad = [n for n in nums if n not in bn and len(n) >= 2]
        if len(bad) >= 2:
            out.append(Finding("unverified_self_claim", ",".join(bad[:4])))
    return out


def det_repeat(text, ctx):
    prev = [p for p in (ctx.get("prev") or []) if p][-5:]
    t = stems(text)
    if len(t) < 3 or not prev:
        return []
    norm = " ".join(t)
    for p in prev:
        if " ".join(stems(p)) == norm:
            return [Finding("repeat_turns", "дословный повтор прошлого ответа")]
    g4 = ngrams(t, 4)
    if not g4:
        return []
    seen = set()
    for p in prev:
        seen |= ngrams(stems(p), 4)
    shared = len(g4 & seen)
    if shared >= 2 or (shared >= 1 and len(g4) <= 3):
        return [Finding("repeat_turns", "общих оборотов: %d" % shared)]
    return []


def det_as_ai(text, ctx):
    m = AS_AI_RE.search(text)
    return [Finding("as_ai", m.group(0))] if m else []


def det_flattery(text, ctx):
    first = (sentences(text) or [""])[0]
    m = FLATTER_RE.search(first)
    return [Finding("flattery_open", first[:60], "strip")] if m else []


def det_feeling(text, ctx):
    ss = sentences(text)
    for i, s in enumerate(ss):
        if FEEL_RE.search(s):
            ctxs = s + " " + (ss[i + 1] if i + 1 < len(ss) else "")
            if not CAUSE_RE.search(ctxs) and not ctx.get("feeling_cause"):
                return [Finding("feeling_no_cause", s[:80])]
    return []


DETECTORS = (det_service, det_echo, det_telemetry, det_repeat, det_as_ai, det_flattery, det_feeling)
SENTENCE_DETECTORS = ("service_lines", "template", "unsolicited_telemetry", "as_ai", "flattery_open", "inner_echo")


class Conscience:
    def __init__(self, mode="enforce", extra_detectors=()):
        self.mode = mode
        self.detectors = tuple(DETECTORS) + tuple(extra_detectors)

    def review(self, text, ctx):
        """-> (findings). Не меняет текст."""
        out = []
        for d in self.detectors:
            try:
                out += d(text or "", ctx)
            except Exception as e:      # сломанный детектор не роняет ход
                out.append(Finding("detector_error", "%s: %s" % (d.__name__, e), "ignore"))
        return [f for f in out if f.fix != "ignore"]

    def repair(self, text, findings, ctx):
        """Детерминированный ремонт: служебное, лесть в начале. -> (новый текст, что сделано)."""
        done = []
        codes = {f.code for f in findings}
        if "service_lines" in codes:
            text, ch = strip_service(text)
            if ch:
                done.append("strip_service")
        if "flattery_open" in codes:
            ss = sentences(text)
            if len(ss) >= 2:
                text = " ".join(ss[1:])
                done.append("strip_flattery")
        return text.strip(), done

    def clamp(self, text, ctx):
        """Светская реплика — 1–3 фразы, до 280 знаков (кодом)."""
        if ctx.get("intent") in ("greeting", "smalltalk"):
            ss = sentences(text)
            t = " ".join(ss[:3])
            if len(t) > 280:
                t = " ".join(sentences(t)[:2])[:280].rsplit(" ", 1)[0]
            return t.strip()
        return text

    def sentence_verdict(self, s, ctx, first):
        """Для потока: 'ok' | 'strip' (вернуть очищенное) | 'drop'. -> (verdict, text)."""
        fs = [f for f in self.review(s, dict(ctx, prev=[])) if f.code in SENTENCE_DETECTORS]
        if first:
            fs += [f for f in det_flattery(s, ctx)]
        if not fs:
            return "ok", s
        if self.mode == "shadow":
            return "ok", s
        if all(f.code == "service_lines" for f in fs):
            t, _ = strip_service(s)
            return ("strip", t) if t else ("drop", "")
        return "drop", ""


class StreamGuard:
    """Пофразовый шлюз потока: держит фразу до конца предложения, плохие роняет до отправки."""

    def __init__(self, cons, ctx, max_hold=400):
        self.c, self.ctx, self.buf, self.first, self.max_hold = cons, ctx, "", True, max_hold
        self.dropped, self.emitted = [], []

    def _gate(self, s):
        if not s.strip():
            return [] if not s else [s]
        v, t = self.c.sentence_verdict(s.strip(), self.ctx, self.first)
        if v == "drop":
            self.dropped.append(s.strip()[:80])
            return []
        self.first = False
        tail = s[len(s.rstrip()):]
        return [t + (tail or " ")]

    def feed(self, piece):
        self.buf += piece
        out = []
        while True:
            m = re.search(r"(?<=[.!?…])[\"»)]*\s|\n", self.buf)
            cut = m.end() if m else None
            if cut is None and len(self.buf) > self.max_hold:
                k = self.buf.find(" ", self.max_hold)
                cut = k + 1 if k != -1 else None
            if cut is None:
                break
            out += self._gate(self.buf[:cut])
            self.buf = self.buf[cut:]
        self.emitted += out
        return out

    def flush(self):
        out = self._gate(self.buf) if self.buf.strip() else []
        self.buf = ""
        self.emitted += out
        return out


# ---------- безопасные ответы ----------
GREET_BANK = ("Привет, мессир. Я здесь.", "На связи, мессир. Что у тебя?", "Слушаю тебя, мессир.", "Здравствуй, мессир. Рад тебя слышать.",
              "Я тут, мессир. Говори.", "Привет. Рад, что ты написал.")
HONEST = ("Мессир, ответ у меня сейчас не сложился — слова не легли. Это мой сбой, а не твой запрос; подробности записаны в журнале хода.",
          "Мессир, я услышал тебя, но связного ответа собрать не смог. Не буду выдавать сырое — разберу причину по журналу хода.")


def safe_answer(intent, prev=()):
    """Честный короткий ответ от NOX; не повторяет последние ответы."""
    bank = GREET_BANK if intent in ("greeting", "smalltalk") else HONEST
    seen = {" ".join(stems(p)) for p in prev}
    for b in bank:
        if " ".join(stems(b)) not in seen:
            return b
    return bank[len(prev) % len(bank)]
