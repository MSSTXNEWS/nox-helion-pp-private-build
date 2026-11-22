"""RTE-04 bridge_intro.py: быстрое вступление «в характере, без фактов» за <2 с, дальше — стрим GLM.
Отличие от двухтактного режима шлюза (qs6_core FIRST_TAIL): там быстрая модель получает факты и может ВЫДУМАТЬ суть; здесь она видит только
тип запроса и настроение, а выход проходит валидатор (нет цифр/имён/утверждений/вопросов) — иначе берётся заготовка из банка.
Вступление в истории считается показанным (GLM получает DEEP_NOTE), в память фактов не пишется (stage=intro)."""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import fastq
import asyncio, hashlib, re
import aio

CAP = re.compile(r"^[A-ZА-ЯЁ]")
ALLOWED_CAPS = {"мессир", "nox", "нокс", "я", "так", "ладно", "хорошо", "понял", "принял", "секунду", "момент"}
BAD = re.compile(r"\d|https?:|`|\?|\b(?:это|является|составляет|равн\w+|потому что|поскольку|ответ[:\s]|значит|всегда|никогда|гарантирую|точно)\b|[=:/\\]", re.I)

KINDS = (
    ("greeting", re.compile(r"^\W*(привет\w*|здравствуй\w*|добр\w+ (?:день|вечер|утро)|хай|салют)", re.I)),
    ("task", re.compile(r"^\W*(?:нокс[,\s]+)?(сделай|напиши|создай|запусти|найди|открой|проверь|исправь|собери|посчитай|переведи|составь|добавь|удали)", re.I)),
    ("question", re.compile(r"\?|^\W*(?:а\s+)?(почему|как|что|зачем|где|когда|кто|сколько|какой|какая|какие|можно)", re.I)),
)
BANK = {
    "greeting": ("Мессир, я здесь.", "На связи, мессир.", "Слушаю, мессир."),
    "task": ("Принял, мессир, берусь за дело.", "Понял, мессир, приступаю и соберу всё как надо.", "Задача ясна, мессир, берусь."),
    "question": ("Хороший вопрос, мессир, сейчас разберу.", "Принял, мессир, думаю над ответом.", "Секунду, мессир, обдумываю как следует."),
    "other": ("Слышу вас, мессир, сейчас отвечу.", "Принял, мессир, секунду.", "Понял, мессир, собираюсь с мыслями."),
}
DEEP_NOTE = ("\n\n[Короткое вступление уже показано мессиру: «%s». Не повторяй и не перефразируй его, сразу переходи к содержанию ответа.]")
SYSTEM = ("Ты NOX, личный ИИ мессира. Напиши ОДНУ короткую фразу-вступление (до 14 слов) в своём характере: собранно, тепло, с лёгким предвкушением. "
          "СТРОГО: без фактов, чисел, имён, терминов, без ответа по существу, без вопросов и обещаний результата. Только отклик: принял/слышу/разбираю. Тип запроса: %s. Настроение: %s.")


def kind_of(text):
    for k, rx in KINDS:
        if rx.search(text):
            return k
    return "other"


def canned(text):
    k = kind_of(text)
    bank = BANK[k]
    return bank[int(hashlib.sha1(text.encode()).hexdigest(), 16) % len(bank)]


def intro_safe(s, user_text=""):
    """Валидатор: вступление не должно нести фактов. -> (ok, причина)."""
    s = (s or "").strip().strip('"«»')
    if not s:
        return False, "empty"
    if BAD.search(s):
        return False, "fact_markers"
    if len(s.split()) > 20 or len(re.findall(r"[.!…]+", s)) > 2:
        return False, "too_long"
    words = re.findall(r"[\w-]+", s)
    for sent in re.split(r"[.!…]+\s*", s):
        for i, w in enumerate(re.findall(r"[\w-]+", sent)):
            if i > 0 and CAP.match(w) and w.lower() not in ALLOWED_CAPS:
                return False, "proper_name:" + w
    uw = {w.lower() for w in re.findall(r"[\w-]{5,}", user_text)}
    if any(w.lower() in uw for w in words if len(w) >= 7):
        return False, "echoes_user_terms"       # не пересказываем содержание запроса
    return True, "ok"


async def make_intro(user_text, fast_url, mood="ровное", deadline_s=1.8, model="fast", max_tokens=40):
    """-> {'text', 'source': 'fast'|'canned', 'ms', 'reason'}. Никогда не дольше deadline_s: при сбое/таймауте — заготовка."""
    t0 = asyncio.get_event_loop().time()
    k = kind_of(user_text)

    async def call():
        msgs = [{"role": "system", "content": SYSTEM % (k, mood)},
                {"role": "user", "content": "Тип запроса: %s. (Содержание запроса тебе не показано намеренно.)" % k}]
        fq = fastq.get(fast_url.rstrip("/") + "/v1/chat/completions", model)       # единый клиент :8083, приоритет P0
        return await fq.achat(msgs, fastq.P0, max_tokens=max_tokens, temperature=0.7, timeout=deadline_s, wait=deadline_s)

    reason = "no_fast_url"
    text = None
    if fast_url:
        try:
            raw = await asyncio.wait_for(call(), deadline_s)
            raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S).strip().split("\n")[0]
            ok, reason = intro_safe(raw, user_text)
            text = raw.strip('"«» ') if ok else None
        except Exception as e:
            reason = "fast_failed:" + type(e).__name__
    src = "fast" if text else "canned"
    return {"text": text or canned(user_text), "source": src, "ms": int((asyncio.get_event_loop().time() - t0) * 1000), "reason": reason, "kind": k}


DEEP_NOTE_GENERIC = "\n\n[Мессиру уже показана короткая фраза-отклик (принял/слышу). Не начинай с подтверждения и приветствия, сразу переходи к содержанию ответа.]"


def with_intro_note(messages, intro_text=None):
    """Копия messages для GLM: к последнему user-сообщению добавлена пометка о показанном вступлении (динамика в хвосте, KV-префикс цел).
    GLM стартует параллельно с вступлением, поэтому по умолчанию пометка общая (intro_text=None)."""
    note = DEEP_NOTE % intro_text if intro_text else DEEP_NOTE_GENERIC
    msgs = [dict(m) for m in messages]
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i].get("role") == "user" and isinstance(msgs[i].get("content"), str):
            msgs[i]["content"] += note
            break
    return msgs
