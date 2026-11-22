"""ctxcommon: общие примитивы CTX - счёт токенов, извлечение фактов, HTTP-клиенты llama.cpp (stdlib).

Факты бывают ЖЁСТКИЕ (number/date/id/url: проверка точным совпадением нормализованного ключа) и МЯГКИЕ
(name/decision: проверка по основам слов). Потеря жёсткого факта в выжимке недопустима.
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import hashlib
import json

import math
import re
import urllib.request

HARD = ("number", "date", "id", "url")
SOFT = ("name", "decision")

_UNIT = r"(?:%|ГиБ|ГБ|МБ|КБ|GiB|GB|MB|KB|ток/с|t/s|tok/s|мс|ms|сек|мин|ч|₽|\$|руб)"
RE_URL = re.compile(r"https?://[^\s)>\]»\"']+")
RE_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\b|\b\d{1,2}:\d{2}(?::\d{2})?\b")
RE_PATH = re.compile(r"(?<![\w.])(?:/[\w.\-]+){2,}")
RE_FILE = re.compile(r"\b[\w\-]+\.(?:py|sh|md|json|jsonl|txt|js|yml|yaml|gguf|cpp|toml|sql|db|log)\b")
RE_CODE = re.compile(r"\b[A-Z]{2,5}-\d{1,4}\b|\b[a-z]+(?:_[a-z0-9]+)+\b|\b[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+\b|(?<![\w-])--[a-z][\w-]+|\b[0-9a-f]{8,64}\b")
RE_NUM = re.compile(r"(?<![\w.])\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?|(?<![\w.])\d+(?:[.,]\d+)?(?=\s?" + _UNIT + r"|[^\w]|$)")
RE_ACR = re.compile(r"\b[A-Z][A-Z0-9]{1,}\b")
RE_CAPS = re.compile(r"(?<=[^\s.!?\n«\"(\[])\s+([A-ZА-ЯЁ][A-Za-zА-Яа-яё]{2,})")
RE_SENT = re.compile(r"(?<=[.!?])\s+|\n+")
RE_DECISION = re.compile(r"(решил|решили|решение|решено|договорил|давай|будем|не будем|нужно|надо|должен|должна|запрещ|нельзя|"
                         r"всегда|никогда|отмени|выбра|приоритет|требован|не делай|сделай|обещ|остановим)", re.I)
RE_WORD = re.compile(r"[A-Za-zА-Яа-яёЁ0-9]+")


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def estimate_tokens(text):
    """Грубая оценка для русского/латиницы под BPE Qwen/GLM (~2.6 симв./токен). Для точности - LlamaTokenizer."""
    return int(math.ceil(len(text) / 2.6)) + 0 if text else 0


def messages_tokens(messages, per_message=6, counter=estimate_tokens):
    return sum(counter(m["content"]) + per_message for m in messages) + 3


def stem(w, n=5):
    return w.lower()[:n]


def stems_of(text, min_len=4, n=5):
    return {stem(w, n) for w in RE_WORD.findall(text) if len(w) >= min_len and not w.isdigit()}


def norm_number(s):
    s = re.sub(r"[  ]", "", s).replace(",", ".")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


class Fact(dict):
    """{kind, text, key, hard, turn}"""

    @property
    def hard(self):
        return self["kind"] in HARD


def _mk(kind, text, key, turn=None):
    return Fact(kind=kind, text=text, key=key, turn=turn)


def extract_facts(text, turn=None, max_decisions=12):
    """Детерминированно достаёт факты из текста. Порядок: url/date/path/file/code вырезаются до чисел."""
    out, seen = [], set()

    def add(kind, surface, key):
        k = (kind, key)
        if k not in seen:
            seen.add(k)
            out.append(_mk(kind, surface, key, turn))

    work = text
    for m in RE_URL.finditer(work):
        u = m.group(0).rstrip(".,;:!?")
        add("url", u, u)
    work = RE_URL.sub(" ", work)
    for m in RE_DATE.finditer(work):
        add("date", m.group(0), m.group(0))
    work = RE_DATE.sub(" ", work)
    for rx in (RE_PATH, RE_FILE, RE_CODE):
        for m in rx.finditer(work):
            s = m.group(0)
            if rx is RE_CODE and re.fullmatch(r"[0-9a-f]{8,64}", s) and not re.search(r"\d", s):
                continue  # слово из букв a-f (напр. «deadbeef» ok, «facade» без цифр - слово)
            add("id", s, s)
        work = rx.sub(" ", work)
    for m in RE_NUM.finditer(work):
        raw = m.group(0)
        key = norm_number(raw)
        digits = re.sub(r"\D", "", key)
        tail = work[m.end():m.end() + 6]
        has_unit = re.match(r"\s?" + _UNIT, tail) is not None
        if len(digits) >= 2 or "." in key or has_unit:
            add("number", raw.strip(), key)
    for m in RE_ACR.finditer(text):
        add("name", m.group(0), m.group(0).lower())
    for m in RE_CAPS.finditer(text):
        add("name", m.group(1), stem(m.group(1)))
    dec = []
    for s in RE_SENT.split(text):
        s = s.strip()
        if 12 <= len(s) <= 300 and RE_DECISION.search(s) and len(stems_of(s)) >= 2:
            dec.append(s)
    dec.sort(key=len)
    for s in dec[:max_decisions]:
        add("decision", s, "|".join(sorted(stems_of(s))))
    return out


def dedupe_facts(facts):
    seen, out = set(), []
    for f in facts:
        k = (f["kind"], f["key"])
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def fact_present(fact, summary, summary_keys=None):
    """Есть ли факт в тексте выжимки. summary_keys - кэш извлечённых из неё ключей (number/date)."""
    k, kind = fact["key"], fact["kind"]
    if kind in ("number", "date"):
        keys = summary_keys if summary_keys is not None else {(f["kind"], f["key"]) for f in extract_facts(summary)}
        return (kind, k) in keys or (kind == "number" and k in {x[1] for x in keys if x[0] == "number"})
    if kind in ("id", "url"):
        return k in summary
    if kind == "name":
        return any(w.lower().startswith(k) for w in RE_WORD.findall(summary))
    if kind == "decision":
        need = set(k.split("|"))
        have = stems_of(summary)
        return len(need & have) / max(1, len(need)) >= 0.6
    return False


def check_facts(facts, summary, soft_min=0.85):
    """-> {ok, missing_hard, missing_soft, soft_cov, hard_cov}"""
    keys = {(f["kind"], f["key"]) for f in extract_facts(summary)}
    hard = [f for f in facts if f["kind"] in HARD]
    soft = [f for f in facts if f["kind"] in SOFT]
    mh = [f for f in hard if not fact_present(f, summary, keys)]
    ms = [f for f in soft if not fact_present(f, summary, keys)]
    sc = 1.0 if not soft else 1 - len(ms) / len(soft)
    hc = 1.0 if not hard else 1 - len(mh) / len(hard)
    return {"ok": not mh and sc >= soft_min, "missing_hard": mh, "missing_soft": ms, "soft_cov": sc, "hard_cov": hc}


def unsupported_hard(summary, source_text_or_keys):
    """Жёсткие факты, которых нет в источнике (выдумка модели)."""
    if isinstance(source_text_or_keys, str):
        src = source_text_or_keys
        skeys = {(f["kind"], f["key"]) for f in extract_facts(src)}
    else:
        src, skeys = "", set(source_text_or_keys)
    snums = {x[1] for x in skeys if x[0] == "number"}
    bad = []
    for f in extract_facts(summary):
        if f["kind"] == "number" and f["key"] not in snums:
            bad.append(f)
        elif f["kind"] == "date" and ("date", f["key"]) not in skeys:
            bad.append(f)
        elif f["kind"] in ("id", "url") and f["key"] not in src and ("id", f["key"]) not in skeys and ("url", f["key"]) not in skeys:
            bad.append(f)
    return bad


class LlamaTokenizer:
    """Точный счёт токенов через llama-server POST /tokenize (кэш по sha). Падение сервера -> оценка."""

    def __init__(self, base_url, timeout=5.0):
        self.url = base_url.rstrip("/") + "/tokenize"
        self.timeout = timeout
        self.cache = {}
        self.failures = 0

    def count_text(self, text):
        if not text:
            return 0
        h = sha256(text)
        if h in self.cache:
            return self.cache[h]
        try:
            req = urllib.request.Request(self.url, json.dumps({"content": text}).encode(), {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                n = len(json.loads(r.read())["tokens"])
        except Exception:
            self.failures += 1
            n = estimate_tokens(text)
        self.cache[h] = n
        return n

    def __call__(self, messages):
        return sum(self.count_text(m["content"]) + 6 for m in messages) + 3


def http_llm(base_url, model="", timeout=120.0, temperature=0.2, prio=None):
    """Фабрика llm(messages, max_tokens)->str для быстрой модели :8083 ТОЛЬКО через COMMON/fastq (по умолчанию P2: свёртка/idle).
    Занятый чат/слот GLM -> fastq.Deferred (потребитель обязан пережить: свёртка откладывается)."""
    import fastq
    fq = fastq.get(base_url.rstrip("/") + "/v1/chat/completions", model or None)
    return fq.llm(fastq.P2 if prio is None else prio, temperature=temperature, timeout=timeout, wait=timeout)


def kv_warm_http(base_url, timeout=600.0):
    """warm(messages): прогревает префикс в llama-server (prefill без генерации) -> KV остаётся в слоте."""
    url = base_url.rstrip("/") + "/v1/chat/completions"

    def warm(messages):
        body = {"messages": messages, "max_tokens": 1, "temperature": 0, "cache_prompt": True,
                "chat_template_kwargs": {"enable_thinking": False}}
        req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
        return True
    return warm
