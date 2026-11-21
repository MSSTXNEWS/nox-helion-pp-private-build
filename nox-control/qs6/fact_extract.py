"""fact_extract: простые явные правила: что из реплики ВЛАДЕЛЬЦА можно записать в память как факт.

Никакой модели и никаких размышлений: на вход только текст самого владельца. Правила узкие и читаемые,
лучше пропустить, чем записать лишнее. Секреты (ключи, пароли, токены, длинные числа) не берутся никогда.
Результат: [{"text", "kind", "source_kind", "rule"}], kind из s03_store.FACT_KINDS, source_kind - вид свидетельства
для лестницы Riverse (owner/direct = сильное, chat = обычное).
"""
import re

from .s03_store import SECRET_RE

MAX_FACT = 200
MIN_FACT = 6
LONG_DIGITS = re.compile(r"\d[\d \-]{10,}\d")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_END = r"\s*[.!]?\s*$"

# (имя, регэксп по одному предложению, шаблон факта, kind, source_kind)
RULES = [
    ("remember", re.compile(r"^(?:пожалуйста[, ]+)?запомни(?:,|:|\s+что)?\s+(?P<x>.+)$", re.I), "{x}", "fact", "direct"),
    ("call_me", re.compile(r"^(?:пожалуйста[, ]+)?(?:называй|зови)\s+меня\s+(?P<x>[^,.!?]{2,40})" + _END, re.I), "Владелец просит называть его: {x}", "owner", "direct"),
    ("name", re.compile(r"^меня\s+зовут\s+(?P<x>[^,.!?]{2,40})" + _END, re.I), "Владельца зовут {x}", "owner", "direct"),
    ("lives", re.compile(r"^я\s+живу\s+(?P<x>(?:в|во|на)\s+[^,.!?]{2,60})" + _END, re.I), "Владелец живёт {x}", "owner", "chat"),
    ("works", re.compile(r"^я\s+работаю\s+(?P<x>[^,.!?]{2,80})" + _END, re.I), "Владелец работает {x}", "owner", "chat"),
    ("likes", re.compile(r"^я\s+(?P<v>люблю|обожаю|предпочитаю)\s+(?P<x>[^,.!?]{2,80})" + _END, re.I), "Владелец {v} {x}", "fact", "chat"),
    ("dislikes", re.compile(r"^я\s+не\s+(?P<v>люблю|выношу|использую)\s+(?P<x>[^,.!?]{2,80})" + _END, re.I), "Владелец не {v} {x}", "fact", "chat"),
    ("always", re.compile(r"^(?P<x>(?:всегда|никогда)\s+(?:отвечай|пиши|говори|не\s+\w+)\s+[^.!?]{2,100})" + _END, re.I), "Установка владельца: {x}", "setting", "direct"),
    ("my_is", re.compile(r"^мо[йяеи]\s+(?P<k>[а-яё\- ]{2,30}?)\s+(?:—|-|это|был|была|будет)\s+(?P<x>[^,.!?]{2,80})" + _END, re.I), "У владельца {k}: {x}", "fact", "chat"),
]
SENT = re.compile(r"(?<=[.!?\n])\s+")


def unsafe(text):
    return bool(SECRET_RE.search(text) or LONG_DIGITS.search(text) or EMAIL.search(text))


def extract(user_text, max_facts=3):
    out, seen = [], set()
    for sent in SENT.split((user_text or "").strip()):
        s = " ".join(sent.split())
        if not s or s.endswith("?") or len(s) > 300 or unsafe(s):
            continue
        for rule, rx, tpl, kind, sk in RULES:
            m = rx.match(s)
            if not m:
                continue
            d = {k: (v or "").strip() for k, v in m.groupdict().items()}
            if rule == "remember" and (d["x"].endswith("?") or len(d["x"].split()) < 2):
                continue
            text = tpl.format(**d).strip().rstrip(".!")
            if rule == "remember":
                text = text[:1].upper() + text[1:]
            if not (MIN_FACT <= len(text) <= MAX_FACT) or unsafe(text) or text.casefold() in seen:
                break
            seen.add(text.casefold())
            out.append({"text": text, "kind": kind, "source_kind": sk, "rule": rule})
            break
        if len(out) >= max_facts:
            break
    return out


# события для emotion_pad по репликам владельца (явные слова, без угадывания настроения)
THANKS = re.compile(r"\b(спасибо|благодарю|отлично|молодец|супер)\b", re.I)
CORRECT = re.compile(r"\b(ты ошибся|ты ошиблась|это неверно|неправильно|не так|ты неправ)\b", re.I)


def emotion_event(user_text):
    t = user_text or ""
    if CORRECT.search(t):
        return "owner_correction"
    if THANKS.search(t):
        return "owner_thanks"
    return None
