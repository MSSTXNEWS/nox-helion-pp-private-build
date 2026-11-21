"""Роутер сообщений ДО модели (миллисекунды, чистые правила): answer / clarify / act / ignore.

API для шлюза:
    from community.chalie_router import route
    d = route(body["messages"])   # -> Decision; d.action, d.reason, d.confidence; d.to_dict()
Русский и английский. Не обращается к сети и модели.
"""
import re
import unicodedata
from dataclasses import dataclass, asdict

ANSWER, CLARIFY, ACT, IGNORE = "answer", "clarify", "act", "ignore"


@dataclass
class Decision:
    action: str
    reason: str
    confidence: float
    features: dict = None

    def to_dict(self):
        return asdict(self)


_RU_IMP = (r"открой|откройте|запусти|запустите|создай|создайте|удали|удалите|найди|найдите|проверь|проверьте|напомни|напомните|"
           r"отправь|отправьте|пришли|пришлите|включи|включите|выключи|выключите|останови|остановите|установи|установите|"
           r"сделай|сделайте|добавь|добавьте|закрой|закройте|сохрани|сохраните|скопируй|перенеси|переименуй|скачай|загрузи|"
           r"перезапусти|перезагрузи|запиши|поставь|поставьте|обнови|обновите|собери|разверни|подключи|отключи|прочитай|"
           r"позвони|набери|поищи|зайди|выполни|выполните|покажи|покажите|посчитай|переведи|напиши|измени|исправь|почини|"
           r"отмени|запланируй|заведи|поменяй|убери|очисти|архивируй|залей|выгрузи|синхронизируй|сбрось")
_EN_IMP = (r"open|run|launch|start|create|delete|remove|find|search|check|remind|send|turn|switch|stop|install|make|add|close|save|"
           r"copy|move|rename|download|upload|restart|reboot|write|set|update|build|deploy|connect|disconnect|read|call|execute|"
           r"show|calculate|translate|change|fix|cancel|schedule|clear|sync|reset|kill|play|pause")
_POLITE = r"(?:пожалуйста|пож|плиз|ну|а ну|давай|давайте|теперь|потом|тогда|и|а|слушай|нокс|nox|please|pls|now|then|and|ok|okay|hey|так|вот)"
_CAN_RU = r"(?:можешь|можете|сможешь|не мог бы ты|не могли бы вы|ты можешь|ты не мог бы|мог бы ты|могла бы ты)"
_CAN_EN = r"(?:can you|could you|would you|will you|can u|i need you to|i want you to|go ahead and|let's|lets)"

_ACT_RE = re.compile(r"^(?:%s[\s,]+)*(?:(?:%s|%s)[\s,]+)*(?:(?:%s)|(?:%s))\b" % (_POLITE, _CAN_RU, _CAN_EN, _RU_IMP, _EN_IMP), re.I)
_Q_WORDS = re.compile(
    r"^(?:а |и |ну |слушай,? )?(?:что|чего|чем|как|какой|какая|какое|какие|каких|почему|зачем|где|куда|откуда|когда|кто|кого|кому|"
    r"сколько|ли|разве|неужели|правда ли|можно ли|есть ли|будет ли|"
    r"what|whats|what's|how|why|where|when|who|whom|whose|which|is|are|am|was|were|do|does|did|can|could|should|would|will|"
    r"has|have|had|may|might|tell me|explain)\b", re.I)
_GREET = re.compile(r"^(?:привет\w*|здравствуй\w*|здорово|добрый (?:день|вечер|утро)|доброе утро|доброй ночи|салют|хай|йо|hi|hello|hey|yo|good (?:morning|evening|afternoon)|greetings)(?: нокс| nox)?$", re.I)
_ASKY = re.compile(r"^(?:расскажи|объясни|скажи|подскажи|опиши|поясни|разъясни|tell|explain|describe|say|suggest|help)\b", re.I)
_QMARK = re.compile(r"[?？]")
_ACK = re.compile(r"^(?:ага|угу|ок|окей|окей\.|хорошо|ладно|понятно|ясно|ясненько|спасибо|благодарю|пасиб|да|нет|ну|так|мм+|м+|э+м*|эм+|"
                  r"хм+|ах|ох|ой|а|о|ok|okay|k|kk|thanks|thx|ty|thank you|yes|no|yeah|yep|nope|hm+|um+|uh+|ah+|oh|got it|cool|nice|sure|fine|right)$", re.I)
_TRAIL_OPEN = re.compile(
    r"(?:,|:|;|\.{2,}|…|\b(?:и|а|но|что|чтобы|потому что|если|когда|как|или|ещё|еще|который|которая|которые|в|на|с|к|по|для|про|от|из|у|о|об|за|до|"
    r"без|над|под|при|между|через|ни|не|то|же|бы|ли|это|мне|тебе|нам|мой|моя|мои|твой|этот|эта|эти|тот|та|те|так|такой|"
    r"and|but|or|so|because|if|when|that|which|who|the|a|an|to|of|in|on|at|for|with|by|from|about|into|my|your|is|are|was|then|than|as)\s*)$", re.I)
_DEICTIC = re.compile(r"^(?:это|его|её|ее|их|этот|эту|то|тот|эти|it|this|that|them|these|those|same|так же|так)$", re.I)
_PUNCT_ONLY = re.compile(r"^[\W_]+$", re.U)
_WS = re.compile(r"\s+")
_URL = re.compile(r"https?://\S+")
_CODEISH = re.compile(r"[{};=<>]|^\s*(?:def|class|import|\$ |#!)")


def _norm(s):
    s = unicodedata.normalize("NFKC", s or "").casefold().replace("ё", "е")
    s = re.sub(r"[^\w\s]", " ", s, flags=re.U)
    return _WS.sub(" ", s).strip()


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # OpenAI-формат с частями
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") in (None, "text"))
    return ""


def _has_emoji_only(s):
    s2 = _WS.sub("", s)
    return bool(s2) and all(unicodedata.category(c) in ("So", "Sk", "Sm", "Cf", "Mn", "Po", "Pd", "Ps", "Pe", "Pi", "Pf", "Zs", "Cs", "Co") for c in s2)


def route(messages):
    """messages - список {role, content}. Решение принимается по последнему user-сообщению с учётом истории."""
    msgs = [m for m in (messages or []) if isinstance(m, dict)]
    last_i = None
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i].get("role") == "user":
            last_i = i
            break
    if last_i is None:
        return Decision(IGNORE, "нет сообщения пользователя / no user message", 0.99, {})
    raw = _text(msgs[last_i].get("content"))
    text = raw.strip()
    n = _norm(text)
    words = n.split()
    hist = msgs[:last_i]
    prev_user = next((_text(m.get("content")) for m in reversed(hist) if m.get("role") == "user"), None)
    prev_asst = next((_text(m.get("content")) for m in reversed(hist) if m.get("role") == "assistant"), None)
    asst_asked = bool(prev_asst and _QMARK.search(prev_asst.strip()[-200:]))
    feats = {"words": len(words), "chars": len(text), "has_qmark": bool(_QMARK.search(text)),
             "history": len(hist), "assistant_asked": asst_asked}

    def D(a, r, c):
        return Decision(a, r, round(c, 2), feats)

    # --- ignore: пустота, шум, эхо, повтор
    if not text or _PUNCT_ONLY.match(text) or not n:
        if text and _QMARK.fullmatch(text):
            return D(CLARIFY, "только вопросительный знак / bare '?'", 0.7)
        return D(IGNORE, "пустое или только знаки/эмодзи / empty or symbols", 0.98 if not text else 0.9)
    if prev_asst and n and n == _norm(prev_asst) and len(words) >= 2:
        return D(IGNORE, "эхо ответа ассистента / echo of assistant", 0.95)
    if prev_user and n == _norm(prev_user) and len(words) >= 2:
        return D(IGNORE, "точный повтор предыдущего сообщения / duplicate of previous", 0.9)
    if _ACK.match(n) and not feats["has_qmark"]:
        if asst_asked:
            return D(ANSWER, "короткий ответ на вопрос ассистента / reply to assistant question", 0.8)
        return D(IGNORE, "реплика-подтверждение без запроса / bare acknowledgement", 0.8)
    if len(words) == 1 and len(n) <= 2:
        return D(IGNORE, "шум: один-два символа / noise", 0.8)

    # --- act: команда (проверяем до вопросительности: «можешь открыть?» - это действие)
    first = n.split(" ", 1)[0] if words else ""
    is_act = bool(_ACT_RE.match(n))
    if not is_act:
        m = re.match(r"^(?:%s)\s+(.+)$" % (_CAN_RU + "|" + _CAN_EN).replace("'", "'"), n)
        if m:
            nxt = m.group(1).split(" ", 1)[0]
            is_act = bool(re.match(r"^(?:%s)$" % _EN_IMP, nxt, re.I)) or bool(re.match(r"^[а-я]+(?:ть|ти|чь)$", nxt))
    if is_act:
        rest = [w for w in words[1:] if not re.match(r"^(?:%s)$" % _POLITE, w, re.I)]
        if len(words) <= 2 and all(_DEICTIC.match(w) for w in rest) and not hist:
            return D(CLARIFY, "команда без объекта и без контекста / command without object", 0.8)
        if rest and all(_DEICTIC.match(w) for w in rest) and not hist:
            return D(CLARIFY, "команда с неясным «это/it» без истории / unresolved reference", 0.75)
        if _TRAIL_OPEN.search(text) and not _DEICTIC.match(words[-1]):
            return D(CLARIFY, "команда оборвана / command looks cut off", 0.7)
        conf = 0.9 if len(words) >= 3 else 0.75
        return D(ACT, "императив-команда / imperative command", conf)

    if _GREET.match(n):
        return D(ANSWER, "приветствие / greeting", 0.9)
    if _ASKY.match(n):
        return D(ANSWER, "просьба объяснить/рассказать / explain request", 0.85)

    # --- неполные фразы
    if _TRAIL_OPEN.search(text) and not feats["has_qmark"]:
        return D(CLARIFY, "фраза оборвана (союз/предлог/запятая) / unfinished sentence", 0.8)

    # --- answer: вопрос
    if feats["has_qmark"]:
        return D(ANSWER, "вопросительный знак / question mark", 0.92)
    if _Q_WORDS.match(n):
        return D(ANSWER, "вопросительное слово / interrogative word", 0.85)

    # --- короткие и невнятные
    if len(words) == 1:
        if asst_asked:
            return D(ANSWER, "одно слово в ответ на вопрос / single-word reply", 0.65)
        if _URL.search(text) or _CODEISH.search(text):
            return D(ANSWER, "одиночный фрагмент кода/ссылка / lone code or link", 0.5)
        return D(CLARIFY, "одно слово без контекста / single word, unclear intent", 0.7)
    if len(words) == 2 and not hist:
        return D(CLARIFY, "слишком короткое утверждение без контекста / too short, no context", 0.55)

    # --- по умолчанию: утверждение/просьба - ответить
    conf = 0.7 if len(words) >= 4 else 0.6
    return D(ANSWER, "обычное утверждение/просьба - отвечать / statement, respond", conf)


def route_text(text, history=None):
    """Удобная обёртка: route_text("привет") без истории."""
    return route(list(history or []) + [{"role": "user", "content": text}])


if __name__ == "__main__":
    import sys, json
    print(json.dumps(route_text(" ".join(sys.argv[1:])).to_dict(), ensure_ascii=False))
