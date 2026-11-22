"""c600: настройка длины ответа чата (max_tokens) для Создателя. Только добавление: файл состояния <NOX_STATE>/chat_settings.json.
Команды: «увеличь/уменьши длину ответа», «длина ответа 2000», «убери ограничение длины», «верни длину по умолчанию»."""
import json
import os
import re
import time

DEFAULT = 1500            # >=1500: запас под рассуждение Flash
LO, HI = 300, 8000
SAFE_THINK = 1500         # нижняя граница при включённом рассуждении (deep): ответ не должен получиться пустым
RESERVE = 256
UNLIM = "unlimited"

RESET = re.compile(r"верни\w*\s+(?:\w+\s+)?длин\w*(?:\s+ответ\w*)?\s+по\s+умолчани|длин\w*\s+(?:ответ\w*\s+)?по\s+умолчани|сбрось\w*\s+длин", re.I)
UNLIMITED = re.compile(r"(?:убер\w+|сним\w+|сними|отключ\w+|выключ\w+)\s+(?:\w+\s+)?огранич\w*(?:\s+(?:на\s+)?(?:длин\w*|ответ\w*))?|без\s+огранич\w*\s+(?:длин\w*|ответ\w*)?|без\s+огранич\w*\s*$|огранич\w*\s+длин\w*\s+(?:убер|сним|отключ)\w*", re.I)
UP = re.compile(r"(?:увелич\w+|удлин\w+|прибав\w+)\s+(?:\w+\s+)?(?:длин\w*|ответ\w*)|(?:длин\w*\s+ответ\w*\s+(?:больше|подлинн\w*))|(?:ответ\w*\s+(?:длиннее|подробнее))|сделай\s+(?:ответ\w*\s+)?длиннее", re.I)
DOWN = re.compile(r"(?:уменьш\w+|сократ\w+|укороти\w*|убав\w+)\s+(?:\w+\s+)?(?:длин\w*|ответ\w*)|длин\w*\s+ответ\w*\s+(?:меньше|короче)|сделай\s+(?:ответ\w*\s+)?короче", re.I)
SETN = re.compile(r"(?:длин\w*\s+ответ\w*|ответ\w*\s+длин\w*|max_tokens|макс\w*\s+токен\w*)\D{0,20}?(\d{3,5})", re.I)


def _path():
    return os.path.join(os.environ.get("NOX_STATE", "/root/nox/state"), "chat_settings.json")


def load():
    try:
        with open(_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(d):
    p = _path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        return True
    except OSError:
        return False


def current(speaker="owner"):
    v = (load().get(speaker or "owner") or {}).get("max_tokens", DEFAULT)
    return v if v == UNLIM else max(LO, min(HI, int(v)))


def _set(speaker, v):
    d = load()
    d[speaker or "owner"] = {"max_tokens": v, "ts": int(time.time())}
    return save(d)


def effective(speaker, thinking, prompt_chars, slot_ctx=8192, path_cap=None):
    """Итоговый max_tokens запроса. unlimited = контекст слота - токены промпта - запас; лимит лишь предохранитель, длину модель не считает."""
    v = current(speaker)
    if v == UNLIM:
        est = int(prompt_chars / 2.2) + 64      # грубо для русского; точный счёт не нужен
        return max(512, int(slot_ctx) - est - RESERVE)
    if thinking:
        v = max(v, SAFE_THINK)
    return max(LO, v)


def handle(text, speaker="owner"):
    """Возвращает ответ-текст, если реплика - команда настройки длины; иначе None."""
    t = (text or "").strip()
    if not t or len(t) > 160:
        return None
    cur = current(speaker)
    if RESET.search(t):
        ok = _set(speaker, DEFAULT)
        return "Готово: длина ответа теперь до %d токенов (по умолчанию)." % DEFAULT + ("" if ok else " (Сохранить настройку не удалось: действует до перезапуска.)")
    if UNLIMITED.search(t):
        ok = _set(speaker, UNLIM)
        return "Готово: длина ответа теперь без ограничения. Вернуть — «верни длину по умолчанию»." + ("" if ok else " (Сохранить настройку не удалось.)")
    m = SETN.search(t)
    if m or UP.search(t) or DOWN.search(t):
        base = DEFAULT if cur == UNLIM else cur
        if m:
            n = int(m.group(1))
        elif UP.search(t):
            n = base * 2
        else:
            n = base // 2
        n = max(LO, min(HI, n))
        ok = _set(speaker, n)
        extra = " Для режима с рассуждением нижняя граница остаётся %d." % SAFE_THINK if n < SAFE_THINK else ""
        return "Готово: длина ответа теперь до %d токенов. Вернуть — «верни длину по умолчанию».%s" % (n, extra) + ("" if ok else " (Сохранить настройку не удалось.)")
    return None
