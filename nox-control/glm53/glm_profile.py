"""GLM-5.3 профиль NOX: чистые функции (G01-G05, G07, G09, G22, G24-G27, G30, G33). Без внешних зависимостей."""
import re, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
EFFORTS = ("low", "high", "max")
SAMPLER = {"temperature": 1.0, "top_p": 0.95, "min_p": 0.01}              # G09
MAX_TOKENS_MIN = {"low": 2048, "high": 8192, "max": 16384}                   # G04: запас на размышление + ответ
CTX_LIMIT = 16384                                                            # должен совпадать с -c сервера
THINK_RE = re.compile(r"<think>.*?</think>", re.S)
CODE_RE = re.compile(r"```|\bdef |\bclass |function\b|\bSELECT\b|\bimport \w+|код|скрипт|функци|баг|ошибк|traceback|python|bash|sql|регуляр", re.I)
REASON_RE = re.compile(r"почему|докажи|рассчитай|посчитай|сравни|спланируй|архитектур|оптимиз|проанализируй|объясни подробно|шаг за шагом", re.I)
BAN_PATTERNS = [                                                              # G30
    (re.compile(r"\bне\s+[^,.;\n]{1,40},\s*а\s+[^,.;\n]{1,40}", re.I), "not_x_but_y"),
    (re.compile(r"\bя\s*[—-]?\s*claude\b|\bclaude\b", re.I), "names_self_claude"),
    (re.compile(r"^(отличный|прекрасный|замечательный|великолепный)\s+(вопрос|идея|мысль)", re.I | re.M), "flattery_opener"),
    (re.compile(r"\b(вы абсолютно правы|совершенно верно, вы правы)\b", re.I), "sycophancy"),
]
LEN_RE = re.compile(r"(\d{1,5})\s*(слов|слова|символ|символов|предложени)", re.I)

def persona():
    with open(os.path.join(HERE, "persona_short_ru.txt"), encoding="utf-8") as f:
        return f.read().strip()

def last_user_text(messages):
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            return c if isinstance(c, str) else " ".join(p.get("text", "") for p in (c or []) if isinstance(p, dict))
    return ""

def pick_effort(text, requested=None):
    """G02/G05/G34: low для простого, high для рассуждений, max для кода. G03: неверное значение -> high, не max."""
    if requested is not None:
        return requested if requested in EFFORTS else "high"
    t = text or ""
    if CODE_RE.search(t) or len(t) > 1500:
        return "max"
    if REASON_RE.search(t) or len(t.split()) > 40:
        return "high"
    return "low"

def strip_think(text):
    return THINK_RE.sub("", text or "").strip()

def clean_history(messages, keep_reasoning):
    """G01: убрать старые размышления из истории в обычном чате; G06/G32: в задачах с инструментами оставить."""
    out = []
    for m in messages:
        m = dict(m)
        if m.get("role") == "assistant" and not keep_reasoning:
            m.pop("reasoning_content", None)
            if isinstance(m.get("content"), str):
                m["content"] = strip_think(m["content"])
        out.append(m)
    return out

def compact_facts(facts, limit=12):
    """G22: важное компактным блоком, самое значимое первым."""
    if not facts:
        return ""
    return "Важные факты:\n" + "\n".join("- " + str(f).strip() for f in facts[:limit])

def task_prompt(goal, constraints):
    """G33: цель + жёсткие ограничения."""
    return "Цель: %s\nЖёсткие ограничения:\n%s" % (goal.strip(), "\n".join("- " + c.strip() for c in constraints))

def build_request(body):
    """Возвращает (тело для llama-server, effort). Системный префикс неизменен (G24)."""
    b = dict(body)
    msgs = list(b.get("messages") or [])
    tools = bool(b.get("tools")) or any(m.get("role") == "tool" for m in msgs)
    msgs = clean_history(msgs, keep_reasoning=tools)
    user = last_user_text(msgs)
    effort = pick_effort(user, b.pop("reasoning_effort", None))
    facts = b.pop("nox_facts", None)
    sysmsg = {"role": "system", "content": persona() + "\nЯзык ответа: язык вопроса (русский по умолчанию); размышления тоже по-русски."}  # G25, G27
    msgs = [sysmsg] + [m for m in msgs if not (m.get("role") == "system" and m.get("content") == sysmsg["content"])]
    block = compact_facts(facts)
    if msgs and msgs[-1].get("role") == "user" and isinstance(msgs[-1].get("content"), str):
        tail = "\n\n[Напоминание: отвечай по-русски, без лести, без «не X, а Y», не называй себя Claude.]"   # G27 повтор в конце
        msgs[-1] = dict(msgs[-1], content=(block + "\n\n" if block else "") + msgs[-1]["content"] + tail)
    b["messages"] = msgs
    for k, v in SAMPLER.items():
        b.setdefault(k, v)
    need = MAX_TOKENS_MIN[effort]
    mt = b.get("max_tokens") or 0
    b["max_tokens"] = min(max(mt, need), CTX_LIMIT - 512)
    b["cache_prompt"] = True
    kw = dict(b.get("chat_template_kwargs") or {}); kw["reasoning_effort"] = effort
    b["chat_template_kwargs"] = kw
    return b, effort

def violations(text):
    return [name for rx, name in BAN_PATTERNS if rx.search(text or "")]

def length_check(request_text, answer):
    """G26: длину проверяем кодом. Возвращает None или dict(spec, want, got, ok)."""
    m = LEN_RE.search(request_text or "")
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    if unit.startswith("слов"):
        got = len(re.findall(r"\w+", answer or ""))
    elif unit.startswith("символ"):
        got = len(answer or "")
    else:
        got = len([s for s in re.split(r"(?<=[.!?])\s+", (answer or "").strip()) if s])
    return {"want": n, "unit": unit, "got": got, "ok": got == n}

def postprocess(resp, user_text):
    """G07: чистый текст для памяти S03 без размышлений; G26/G30: метки качества."""
    try:
        msg = resp["choices"][0]["message"]
    except Exception:
        return resp
    content = msg.get("content") or ""
    clean = strip_think(content)
    resp["nox"] = {"memory_text": clean, "violations": violations(clean), "length": length_check(user_text, clean)}
    return resp
