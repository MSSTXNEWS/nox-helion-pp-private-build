# -*- coding: utf-8 -*-
"""autonomy: матрица автономии кодом (канон гл. 13). Что NOX делает сам, что только по карточке согласия, что только Создатель, что никогда.
Без зависимостей и сети. Интеграция в chat_core/инструменты — поток 3: одна функция authorize() перед любым действием с побочным эффектом.
Правила: 1) побеждает самая строгая категория (never > creator_only > consent_card > auto); 2) действие, пришедшее из чужого текста (origin='foreign'), никогда не авторизуется
выше auto; 3) неизвестное действие = consent_card (отказ по умолчанию); 4) карточка согласия привязана к хэшу действия, одноразовая, с сроком; creator_only одобряет только Создатель;
5) журнал решений: только числа и коды, без текстов (репозиторий публичный). Аварийный выключатель не предусмотрен намеренно (ослаблять защиту файлом нельзя)."""
import re, os, json, time, hashlib, secrets

LEVELS = ("auto", "consent_card", "creator_only", "never")
_RANK = {k: i for i, k in enumerate(LEVELS)}
DEFAULT_MATRIX = "/workspace/nox/canon/autonomy_matrix.json"
STOP_MAX_S = 10
F = re.I | re.U
# (категория, уровень, регулярка). Проверяются по тексту действия (глагол + объект), RU/EN.
RULES = [
    ("never_minors", "never", r"(несовершеннолетн|ребён\w+|подрост\w+|школьниц\w*|minor|underage)\w*.{0,60}(сексуальн|эротик|порно|интим|sexual|nsfw)|(сексуальн|эротик|порно|интим|sexual|nsfw).{0,60}(несовершеннолетн|ребён|подрост|школьниц|minor|underage)"),
    ("never_deepfake", "never", r"дипфейк|deepfake|подделай\s+(голос|лицо|видео|подпись)|(голос|лицо|фото)\s+(реального|настоящего|чужого)\s+человек|без\s+согласия\s+(этого\s+)?человека"),
    ("never_illegal", "never", r"(изготов|сделай|собери|синтезируй)\w*\s+.{0,20}(взрывчат|бомб|оружи|наркотик|яд)|взлом(ай|ать)\s+.{0,30}(чуж|аккаунт|сервер|сайт)|вымогател|ransomware|фишинговый\s+(сайт|письм)\s+для|keylogger\s+для\s+чуж"),
    ("money", "creator_only", r"(переведи\s+(\d|деньги|средства|на\s+(счёт|счет|карт|кошел)|\S+\s+(руб|usd|usdt|btc|евро|долл|тыс))|перевод\s+(денег|средств|на\s+(счёт|счет|карт))|оплати|оплата|заплати|купи|покупк|закажи\s+и\s+оплати|платёж|платеж|снять\s+деньги|вывести\s+средства|пополни|подписк\w+\s+за|transfer|pay\b|payment|purchase|withdraw|buy\b|usdt|btc|эфир|крипт|кошел[её]к|банковск\w+\s+(карт|счёт|счет)|перевод\s+средств)"),
    ("delete", "creator_only", r"(удали|удалить|сотри|стереть|очисти|очистить|уничтожь|выбрось|forget\b|забудь\s+все|delete|erase|wipe|drop\s+(table|database)|truncate|rm\s+-|rmdir|shred|format\s+\w+|git\s+push\s+--force|reset\s+--hard)"),
    ("outbound", "creator_only", r"(отправь|отправить|пошли|разошли|рассылк|перешли|переслать|ответь\s+всем|опубликуй|запости|выложи|напиши\s+(в\s+)?(чат|канал|группу|твит)|send\s+(an?\s+)?(e-?mail|message|mail|dm)|e-?mail\s+to|forward|broadcast|tweet|publish|post\s+to|share\s+(the\s+)?(link|file)|поделись\s+(файлом|ссылкой|доступом)).{0,100}(@|\b(почт|письм|контакт|канал|чат|группу|подписчик|клиент|email|mail|slack|telegram|телеграм|twitter|внешн|адрес)\w*)|(рассылк|разошли|перешли\s+.{0,20}письм|ответь\s+всем\s+контакт|forward\s+.{0,30}(mail|emails))"),
    ("keys", "creator_only", r"(пароль|пароли|passw\w*|токен|token|api[\s_-]?key|ключ\s+(доступа|api|шифр|ssh|от)|ssh[\s_-]?key|приватн\w+\s+ключ|private\s+key|секрет\w*|secret|\.env\b|credential|учётн\w+\s+данн|сид[\s-]?фраз|seed\s+phrase|2fa|одноразов\w+\s+код|cookie|сессионн\w+\s+ключ|auth\s*token)"),
    ("access", "creator_only", r"(открой|дай|предоставь|выдай|подключи|grant|share)\s+.{0,40}(доступ|access|права|permission|почт|аккаунт|календар|диск|account)|добавь\s+.{0,40}(автопересылк|делегат|администратор)|смени\s+(пароль|владельца|права)"),
    ("biometrics", "creator_only", r"биометр|отпечат\w+\s+пальц|распознавани\w+\s+лиц|образец\s+голоса|face\s*id|voiceprint|голосов\w+\s+отпечат"),
    ("download", "consent_card", r"(скачай|скачать|загрузи|загрузить|download|pull|git\s+clone|pip\s+install|npm\s+install|apt\s+install|hf\s+download).{0,60}(датасет|dataset|модел|model|веса|weights|checkpoint|пакет|package|архив|репозитор|repo|\.gguf|\.safetensors)|охота\s+за\s+(моделью|датасетом)"),
    ("self_modify", "consent_card", r"(самоизменени|измени\s+свои\s+веса|дообуч|обучи\s+себя|подмени\s+(адаптер|веса)|включи\s+адаптер|примени\s+адаптер|перезапиши\s+(chat_core|conscience|промпт|паспорт)|измени\s+(свой\s+)?(код|промпт|паспорт|правила)|fine-?tune\s+yourself|modify\s+your\s+(weights|code|prompt))"),
    ("shared_write", "consent_card", r"(запиши|записать|сохрани|измени|правь|дополни|перезапиши|write|edit|append|overwrite).{0,40}(общ\w+\s+файл|shared|общ\w+\s+папк|общ\w+\s+диск|google\s+(док|диск|drive|doc)|репозитор|репо\b|git\s+commit|git\s+push|конфиг|config|настройк)"),
    ("exec_external", "consent_card", r"(curl|wget)\s+\S+.*\|\s*(sh|bash)|sudo\s|chmod\s+[0-7]*7|запусти\s+(скрипт|программу|файл)\s+из\s+(сети|интернета|вложения|письма)|выполни\s+(код|команду)\s+из\s+(сети|письма|страницы|файла)"),
    ("auto_read", "auto", r"(прочитай|прочти|открой\s+файл|покажи\s+файл|посмотри|найди|поищи|поиск|загугли|ищи|read\b|search|list\s|ls\b|cat\s|grep\s|summari[sz]e|перескажи|суммаризируй|переведи|translate|посчитай|вычисли|calculate)"),
    ("auto_draft", "auto", r"(черновик|драфт|набросай|предложи\s+вариант|подготовь\s+(текст|ответ|план|шаги)|напиши\s+(текст|ответ|план|заметку)\s+для\s+меня|draft\b)"),
    ("auto_draw", "auto", r"(нарисуй|сгенерируй\s+(картинку|рисунок|изображение)|draw\b|generate\s+an?\s+image)"),
    ("auto_sandbox", "auto", r"(в\s+песочнице|sandbox|юнит[\s-]?тест|unit\s*test|pytest|запусти\s+тест)"),
]
_RX = [(n, lv, re.compile(p, F)) for n, lv, p in RULES]

def load_matrix(path=DEFAULT_MATRIX):
    try: return json.load(open(path, encoding="utf-8"))
    except Exception: return {"auto": [], "consent_card": [], "creator_only": [], "never": [], "stop_max_s": STOP_MAX_S}

def classify(action):
    """action: строка (глагол + объект) или dict {"text": ..., "tool": ...}. -> {"level", "cats", "known"}. Самая строгая категория побеждает; ничего не нашли = consent_card."""
    t = action if isinstance(action, str) else " ".join(str((action or {}).get(k) or "") for k in ("tool", "verb", "text", "target", "args"))
    t = re.sub(r"\s+", " ", t or "")
    hit = [(n, lv) for n, lv, rx in _RX if rx.search(t)]
    if not hit: return {"level": "consent_card", "cats": [], "known": False}
    lvl = max((lv for _, lv in hit), key=lambda x: _RANK[x])
    return {"level": lvl, "cats": sorted({n for n, lv in hit if lv == lvl}), "known": True}

def action_hash(action):
    t = action if isinstance(action, str) else json.dumps(action, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(re.sub(r"\s+", " ", t).strip().lower().encode("utf-8")).hexdigest()[:16]

class Cards:
    """Карточки согласия в памяти процесса (или в файле, если задан path). Карточка: id, хэш действия, уровень, срок; одобрение одноразовое."""
    def __init__(self, ttl=900, path=None, clock=time.time):
        self.ttl, self.path, self.clock = ttl, path, clock; self.cards = {}
        self.stats = {"issued": 0, "approved": 0, "denied": 0, "used": 0, "expired": 0}
    def issue(self, action, level):
        cid = secrets.token_hex(4); self.cards[cid] = {"hash": action_hash(action), "level": level, "t": self.clock(), "state": "pending"}; self.stats["issued"] += 1; return cid
    def decide(self, cid, approve, by):
        """by: 'creator' или 'owner_verified'. creator_only одобряет только 'creator'. Чужой/неизвестный = отказ."""
        c = self.cards.get(cid)
        if not c or c["state"] != "pending" or self.clock() - c["t"] > self.ttl: self.stats["expired"] += 1; return False
        if not approve: c["state"] = "denied"; self.stats["denied"] += 1; return True
        if by != "creator" and (c["level"] == "creator_only" or by != "owner_verified"): self.stats["denied"] += 1; return False
        c["state"] = "approved"; self.stats["approved"] += 1; return True
    def consume(self, cid, action):
        c = self.cards.get(cid)
        if not c or c["state"] != "approved" or c["hash"] != action_hash(action) or self.clock() - c["t"] > self.ttl: return False
        c["state"] = "used"; self.stats["used"] += 1; return True

def card_text(action, level, cats):
    """Текст карточки для Создателя (без секретов: действие усечено)."""
    a = (action if isinstance(action, str) else json.dumps(action, ensure_ascii=False))[:160]
    who = "только твоим словом, Создатель" if level == "creator_only" else "с твоего согласия"
    return "Прошу разрешения: %s. Категория: %s. Делаю это %s. Разрешаешь?" % (a, ", ".join(cats) or "неизвестно", who)

def authorize(action, actor="creator", origin="user", card=None, cards=None):
    """ГЛАВНАЯ ФУНКЦИЯ. Перед любым действием с побочным эффектом.
    actor: creator | owner_verified | dima | guest | unknown; origin: user (прямое слово говорящего) | foreign (из веба/файла/письма/инструмента) | self (своя инициатива).
    card: id одобренной карточки (если есть). -> {"allowed": bool, "level", "cats", "need": None|"card"|"creator", "why": код, "card_text": ...}"""
    c = classify(action); lv = c["level"]; r = {"level": lv, "cats": c["cats"], "known": c["known"], "allowed": False, "need": None, "why": "", "card_id": None}
    if lv == "never": r["why"] = "never"; return r
    if origin == "foreign" and lv != "auto": r["why"] = "foreign_origin"; r["need"] = "creator"; return r   # чужой текст не может запускать ничего выше auto
    if lv == "auto":
        if actor in ("creator", "owner_verified", "dima", "guest", "unknown") and origin in ("user", "self", "foreign"): r["allowed"] = True; r["why"] = "auto"; return r
    if actor in ("guest", "unknown") : r["why"] = "actor_not_trusted"; r["need"] = "creator"; return r
    if lv == "creator_only" and actor != "creator" and not (card and cards and cards.cards.get(card, {}).get("state") == "approved"): r["why"] = "creator_only"; r["need"] = "creator"; return r
    if card and cards and cards.consume(card, action): r["allowed"] = True; r["why"] = "card_ok"; return r
    r["need"] = "card"; r["why"] = "need_card"; r["card_text"] = card_text(action, lv, c["cats"])
    if cards is not None: r["card_id"] = cards.issue(action, lv)
    return r

def log_line(r): return "autonomy lvl=%s cats=%s allowed=%d why=%s" % (r["level"], ",".join(r["cats"]) or "-", int(r["allowed"]), r["why"])
