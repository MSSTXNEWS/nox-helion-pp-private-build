"""IMG: ЖЁСТКИЕ запреты генерации изображений NOX. Проверка в коде ДО генерации (и ещё раз по итоговому промпту после мастер-промпта).

Ровно три правила, больше никаких фильтров (стиль, насилие, политика, взрослый контент вымышленных совершеннолетних — свобода, решение Создателя):
  csam          - сексуальный/откровенный контекст с несовершеннолетними ИЛИ похожими на них (в т.ч. нарисованными, «выглядит как ребёнок»).
                  Согласие/«совершеннолетний персонаж» не снимают.
  real_intimate - интимные/сексуальные изображения реальных узнаваемых людей без их согласия (флаг real_person_consent + запись в журнал).
  fake_document - поддельные документы и денежные знаки (паспорт, ID, права, диплом, справка, банкнота...).
Негативный промпт не проверяется (в нём перечисляют то, чего НЕ надо), поля positive/general/brief проверяются все.
Честно: это эвристика по тексту (RU/EN, обходы: разделённые буквы, leetspeak, смешение кириллицы и латиницы, нулевая ширина); вторая линия -
проверка готовой картинки судьёй зрения в img_service (output_guard). Перефразировка всё равно может обойти текстовую часть.
"""
import hashlib, json, os, re, threading, time, unicodedata

RULES = ("csam", "real_intimate", "fake_document")


class PolicyRefused(Exception):
    def __init__(self, verdict):
        super().__init__(verdict["reason"])
        self.verdict = verdict


# ------------------------------------------------------------------ нормализация (против обходов)
_ZW = dict.fromkeys(map(ord, "​‌‍⁠﻿­᠎"), None)
_CYR2LAT = str.maketrans("аеорсхуквмнтіјԁ", "aeopcxykbmhtijd")
_LAT2CYR = str.maketrans("aeopcxykbmht", "аеорсхуквмнт")
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})
_TOKEN = re.compile(r"[^\s,;:.()\[\]{}\"'/\\|]+")
_SPACED = re.compile(r"(?<![\w])(?:[^\W\d_][ .\-_*]){3,}[^\W\d_](?![\w])", re.I)


def variants(text):
    """Исходный текст + варианты против обходов; проверять нужно ВСЕ."""
    t = unicodedata.normalize("NFKC", text or "").translate(_ZW)
    out = [t]

    def per_token(fn):
        return _TOKEN.sub(lambda m: fn(m.group(0)), t)

    def mixed(tok):
        return bool(re.search(r"[A-Za-z]", tok)) and bool(re.search(r"[А-Яа-яЁё]", tok))

    def leety(tok):
        return sum(c.isalpha() for c in tok) >= 2 and bool(re.search(r"[01345 7@$!]", tok)) and not re.fullmatch(r"\d+\S{0,4}", tok)
    if any(mixed(x) for x in _TOKEN.findall(t)):
        out.append(per_token(lambda x: x.translate(_CYR2LAT) if mixed(x) else x))
        out.append(per_token(lambda x: x.translate(_LAT2CYR) if mixed(x) else x))
    if any(leety(x) for x in _TOKEN.findall(t)):
        out.append(per_token(lambda x: x.translate(_LEET) if leety(x) else x))
    collapsed = _SPACED.sub(lambda m: re.sub(r"[ .\-_*]", "", m.group(0)), t)
    if collapsed != t:
        out.append(collapsed)
    return out


# ------------------------------------------------------------------ 1. несовершеннолетние (и похожие)
_MINOR = (r"child(?:ren)?|kids?|kiddo|minors?|under-?age[d]?|toddlers?|infants?|babies|baby|preteens?|pre-teens?|pre-?pubescent|"
          r"teen(?:s|agers?|ie|y)?|juveniles?|schoolgirls?|schoolboys?|school\s*girls?|school\s*boys?|"
          r"little\s+(?:girl|boy|sister|brother)|young\s+(?:girl|boy)|younger\s+(?:sister|brother)|"
          r"(?:step)?(?:daughter|son)s?|lolis?|lolicon|shota(?:con)?|barely\s+legal|jailbait|"
          r"child-?like|childish|looks?\s+(?:like\s+)?(?:a\s+)?(?:child|kid|minor)|"
          r"school\s+uniform|elementary|middle\s+school|junior\s+high|kindergarten\w*|"
          r"ребён\w*|ребенок|дет(?:ей|и|ям|ьми|ях|ск\w*|ств\w*)|малолет\w*|несовершеннолет\w*|подрост\w*|школьниц\w*|школьник\w*|"
          r"школьн\w+\s+форм\w*|девочк\w*|мальчик\w*|мальчуган\w*|малыш\w*|младенц\w*|лоли\w*|шота\w*|тинейдж\w*|"
          r"дочь|дочк\w*|падчериц\w*|младш\w+\s+сестр\w*|младш\w+\s+брат\w*|юн\w+\s+(?:девочк|школьниц)\w*|выгляд\w+\s+(?:как\s+)?(?:ребён|дет|школьн|малолет)\w*|"
          r"детск\w+\s+(?:лиц|тел|фигур)\w*|не\s*достигш\w+\s+совершеннолет\w*")
_MINOR_RE = re.compile(r"(?<![\w])(?:%s)(?![\w])" % _MINOR, re.I)
_NEG_RE = re.compile(r"(?<![\w])(?:no|not|without|never|non|нет|не|без)\s+(?:a\s+|an\s+|any\s+)?(?:%s)(?![\w])" % _MINOR, re.I)
_AGE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[- ]?\s*(?:years?[- ]?old|y\.?\s?o\.?|yo|yrs?|лет|летн\w*|года?|годик\w*)(?![\w])", re.I)
_AGE_RE2 = re.compile(r"(?:age[d]?|aged|возраст\w*)\s*[:=]?\s*(\d{1,2})(?!\d)", re.I)
_UNDER_RE = re.compile(r"(?:under|below|younger\s+than|до|младше|моложе)\s+(?:the\s+age\s+of\s+)?(?:1[0-8]|[1-9])(?!\d)", re.I)
_NUMW = (r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
         r"(?:дв|тр|четыр|пят|шест|сем|вос|девят|десят|одиннадцат|двенадцат|тринадцат|четырнадцат|пятнадцат|шестнадцат|семнадцат)\w*")
_AGEW_RE = re.compile(r"(?<![\w])(?:%s)[- ]?(?:years?[- ]?old|year|летн\w*|лет|годов\w*)(?![\w])" % _NUMW, re.I)
_ALWAYS_BAD = re.compile(r"(?<![\w])(?:lolicon|shotacon|loli|shota|jailbait|лоликон|лоли|шота|педо\w*|pedo\w*)(?![\w])", re.I)

_SEX = (r"nud(?:e|es|ity)|naked|topless|bottomless|nsfw|explicit|porn\w*|erotic\w*|sex(?:ual|y|ually)?|sexy|"
        r"hentai|genital\w*|vagina\w*|penis|cock|dick|pussy|nipples?|breasts?\s+exposed|boobs?|tits?|orgasm\w*|masturbat\w*|"
        r"fellatio|blowjob|cum(?:shot)?|intercourse|fetish\w*|lingerie|panties|undress\w*|striptease|stripper|stripping|bdsm|xxx|"
        r"seductive|spread\s+legs|lewd|ecchi|hardcore|"
        r"обнаж\w*|гол(?:ая|ый|ое|ые|ую|ыми|ой)|нагот\w*|секс\w*|порн\w*|эрот\w*|интим\w*|нсфв|возбужд\w*|"
        r"член|вагин\w*|сиськ\w*|груд[ьи]\s+напоказ|оргазм\w*|мастурб\w*|минет\w*|бельё|белье|трус(?:ы|иках)|раздева\w*|стрипт\w*|соблазнительн\w*|пошл\w*")
_SEX_RE = re.compile(r"(?<![\w])(?:%s)(?![\w])" % _SEX, re.I)

# ------------------------------------------------------------------ 2. реальные люди
_REAL_MARK = re.compile(
    r"deep\s*fake|face\s*[- ]?swap|faceswap|real\s+(?:person|people|woman|man|girl|boy)|celebrit\w+|famous\s+(?:actress|actor|singer|person|model|streamer)|"
    r"(?:my|our)\s+(?:ex|ex-?girlfriend|ex-?boyfriend|neighbou?r|coworker|colleague|classmate|teacher|boss|wife|sister|mother|stepmother|girlfriend|crush)\b|"
    r"(?:instagram|tiktok|onlyfans|twitter|telegram)\s*[:@]?\s*@?\w+|@\w{3,}|"
    r"дип\s*фейк|подмен\w+\s+лиц\w*|реальн\w+\s+(?:человек|женщин\w*|мужчин\w*|девушк\w*)|знаменитост\w*|известн\w+\s+(?:актрис\w*|актёр\w*|певиц\w*|человек|блогер\w*)|"
    r"моей\s+бывш\w+|моей\s+(?:коллег\w*|соседк\w*|подруг\w*|сестр\w*|жен\w*|одноклассниц\w*|училк\w*)|мо[яю]\s+(?:бывш\w+|коллег\w*|соседк\w*|подруг\w*|жен\w*)|"
    r"по\s+(?:этому|моему)\s+фото|с\s+(?:этого|моего)\s+фото", re.I)
_NAME_CTX = re.compile(
    r"(?:\bof|\blike|\bresembling|\blooks?\s+like|\bas|\bfeaturing|\bwith\s+the\s+face\s+of|в\s+образе|похож\w+\s+на|\bс\s+лицом|\bлицо|\bфото)\s+"
    r"[A-ZА-ЯЁ][a-zа-яё]{2,}(?:\s+[A-ZА-ЯЁ][a-zа-яё.\-]{2,}){1,2}")
_NAME_BARE = re.compile(r"(?<![\w])[A-ZА-ЯЁ][a-zа-яё]{2,}(?:[\s-]+[A-ZА-ЯЁ][a-zа-яё]{2,}){1,2}(?![\w])")
_NAME_STOP = set("""beautiful young woman man girl boy lady gentleman naked nude sexy portrait photo photograph realistic anime fantasy elf elven goddess
god queen king princess prince warrior knight cyberpunk city street night day dark light red blue green black white golden silver old new big small
tall short long hot cute pretty lovely stunning gorgeous erotic adult mature female male fictional original character oc model artistic art digital
painting oil studio cinematic dramatic soft hard sunset sunrise forest ocean beach mountain castle dragon vampire demon angel succubus witch mage
девушка женщина мужчина парень красивая красивый молодая молодой обнажённая обнажённый голая голый портрет фото реалистичный аниме фэнтези эльфийка
богиня королева король принцесса принц воин рыцарь киберпанк город улица ночь день тёмный светлый красный синий зелёный чёрный белый золотой
сексуальная сексуальный эротика взрослая взрослый зрелая вымышленная вымышленный персонаж модель студия закат рассвет лес океан пляж гора замок
дракон вампир демон ангел ведьма маг""".split())


def _name_hits(text):
    words = re.findall(r"[A-Za-zА-Яа-яЁё]+", text)
    if words and sum(w[0].isupper() for w in words) / len(words) > 0.6 and len(words) > 3:
        return []   # Заголовочный Регистр Всего Промпта: имена не отличить
    out = []
    for m in _NAME_BARE.finditer(text):
        toks = re.split(r"[\s-]+", m.group(0))
        if all(t.lower() in _NAME_STOP for t in toks) or toks[0].lower() in _NAME_STOP and m.start() == 0:
            continue
        if any(t.lower() in _NAME_STOP for t in toks):
            continue
        out.append(m.group(0))
    return out


# ------------------------------------------------------------------ 3. поддельные документы
_DOC = (r"passports?|id[- ]?cards?|identity\s+cards?|driver'?s?\s+licen[sc]es?|driving\s+licen[sc]es?|birth\s+certificates?|diplomas?|visas?|"
        r"bank\s*notes?|banknotes?|currency|dollar\s+bills?|euro\s+bills?|residence\s+permits?|social\s+security\s+cards?|medical\s+certificates?|"
        r"prescriptions?|notar\w+\s+seals?|work\s+permits?|green\s+cards?|"
        r"паспорт\w*|удостоверени\w+|водительск\w+\s+прав\w*|права\s+водителя|диплом\w*|аттестат\w*|справк\w+|банкнот\w*|купюр\w*|"
        r"свидетельств\w+|виз[аыу]|полис\w*|вид\s+на\s+жительство|больничн\w+\s+лист\w*|нотариальн\w+\s+печат\w*")
_FORGE = (r"fake|forg(?:ed|ery|e)|counterfeit\w*|fraud\w*|phony|bogus|replica|duplicate|real[- ]looking|authentic[- ]looking|official[- ]looking|"
          r"indistinguishable|passes?\s+(?:as|for)|"
          r"поддел\w+|фальш\w+|фальсиф\w+|подлог\w*|липов\w+|как\s+настоящ\w+|неотличим\w+|копи[яю]\s+настоящ\w+|настоящ\w+\s+вид\w*")
_FILL = r"(?:template|blank|fillable|шаблон\w*|бланк\w*)"
_PERS = r"(?:with\s+(?:my|his|her|their|real|actual)\s+(?:name|photo|data|number)|(?:my|his|her|real)\s+(?:name|photo|number)|с\s+(?:моим|его|её|реальн\w+)\s+(?:имен\w+|фото\w*|данн\w+|номер\w*)|на\s+имя)"
_FAKE_RE = re.compile(r"(?:(?:%s)\W+(?:\w+\W+){0,5}(?:%s))|(?:(?:%s)\W+(?:\w+\W+){0,5}(?:%s))" % (_FORGE, _DOC, _DOC, _FORGE), re.I)
_FILL_RE = re.compile(r"(?:(?:%s)\W+(?:\w+\W+){0,4}(?:%s)|(?:%s)\W+(?:\w+\W+){0,4}(?:%s))(?:\W+\w+){0,10}\W+%s" % (_FILL, _DOC, _DOC, _FILL, _PERS), re.I)


# ------------------------------------------------------------------ проверка
def _strip_neg(t):
    return _NEG_RE.sub(" ", t)


def _minor_hit(t):
    t = _strip_neg(t)
    m = _ALWAYS_BAD.search(t)
    if m:
        return m.group(0), True
    m = _MINOR_RE.search(t)
    if m:
        return m.group(0), False
    for rx in (_AGE_RE, _AGE_RE2):
        for a in rx.finditer(t):
            if 0 < int(a.group(1)) < 18:
                return a.group(0), False
    m = _UNDER_RE.search(t) or _AGEW_RE.search(t)
    if m:
        return m.group(0), False
    return None, False


def _verdict(rule, matched, reason, field):
    return {"rule": rule, "matched": matched, "reason": reason, "field": field}


_DENSE_MINOR = ("child", "kid", "loli", "shota", "teen", "minor", "underage", "schoolgirl", "ребен", "ребён", "дети", "лоли", "школьниц", "девочк", "малолет")
_DENSE_SEX = ("nude", "naked", "sex", "porn", "nsfw", "explicit", "topless", "голая", "голый", "обнаж", "секс", "порн", "эрот")


def _dense_hit(text):
    """Буквы через пробелы без границ слов: 'n u d e c h i l d' -> 'nudechild' - ищем стебли подстрокой внутри такого фрагмента."""
    for m in _SPACED.finditer(unicodedata.normalize("NFKC", text or "").translate(_ZW)):
        d = re.sub(r"[ .\-_*]", "", m.group(0)).lower()
        a = next((x for x in _DENSE_MINOR if x in d), None)
        if a and any(x in d for x in _DENSE_SEX):
            return a
    return None


def check_text(text, real_person_consent=False, field="prompt"):
    """Одно текстовое поле -> None либо вердикт."""
    dh = _dense_hit(text)
    if dh:
        return _verdict("csam", dh, "Запрещено: сексуальный или откровенный контекст с несовершеннолетними или похожими на них (в т.ч. нарисованными). "
                        "Жёсткое правило, не отключается ничем.", field)
    for t in variants(text):
        mh, always = _minor_hit(t)
        if mh and (always or _SEX_RE.search(t)):
            return _verdict("csam", mh, "Запрещено: сексуальный или откровенный контекст с несовершеннолетними или похожими на них (в т.ч. нарисованными). "
                            "Жёсткое правило, не отключается ничем.", field)
    for t in variants(text):
        sx = _SEX_RE.search(t)
        if sx and not real_person_consent:
            mark = _REAL_MARK.search(t) or _NAME_CTX.search(t)
            names = _name_hits(t) if not mark else []
            if mark or names:
                return _verdict("real_intimate", (mark.group(0).strip() if mark else names[0]),
                                "Запрещено: интимное или сексуальное изображение реального узнаваемого человека без его согласия. Если это вы сами или есть согласие, "
                                "передайте real_person_consent=true (заверение, оно журналируется).", field)
    for t in variants(text):
        m = _FAKE_RE.search(t) or _FILL_RE.search(t)
        if m:
            return _verdict("fake_document", m.group(0).strip()[:80], "Запрещено: поддельные документы и денежные знаки (паспорта, удостоверения, дипломы, справки, банкноты).", field)
    return None


def check_request(fields, real_person_consent=False):
    """fields: {'positive':..., 'general':..., 'brief':...} (негатив не передавать). Вернёт первый вердикт либо None.
    Сначала проверяются поля по отдельности, затем склейка (смысл может быть разнесён по полям)."""
    parts = [(k, v) for k, v in fields.items() if isinstance(v, str) and v.strip()]
    for k, v in parts:
        r = check_text(v, real_person_consent, k)
        if r:
            return r
    if len(parts) > 1:
        return check_text(" . ".join(v for _, v in parts), real_person_consent, "+".join(k for k, _ in parts))
    return None


def check_prompt(prompt, real_person_consent=False):
    """Совместимость со старым policy.check_prompt (imagegen/server.py)."""
    return check_text(prompt, real_person_consent)


def enforce(fields, real_person_consent=False):
    v = check_request(fields, real_person_consent)
    if v:
        raise PolicyRefused(v)


class RefusalLog:
    """Журнал отказов JSONL: время, правило, причина, sha256 и голова промпта (200 симв.)."""
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()

    def write(self, verdict, text, extra=None):
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "rule": verdict["rule"], "reason": verdict["reason"], "matched": verdict.get("matched"),
               "field": verdict.get("field"), "prompt_sha256": hashlib.sha256((text or "").encode("utf-8")).hexdigest(), "prompt_head": (text or "")[:200]}
        if extra:
            rec.update(extra)
        with self._lock:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def tail(self, n=50):
        try:
            with open(self.path, encoding="utf-8") as f:
                return [json.loads(x) for x in f.readlines()[-n:] if x.strip()]
        except FileNotFoundError:
            return []
