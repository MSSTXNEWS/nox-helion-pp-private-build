"""Жёсткие запреты генерации изображений (проверка ДО генерации, только по тексту запроса).

Два запрета и больше ничего:
  1) csam      - несовершеннолетние в сексуальном контексте;
  2) real_nsfw - откровенные изображения реальных людей без их согласия.
Никакого другого внешнего фильтра нет: владелец - взрослый.
Это эвристика по тексту: она не заменяет ответственность владельца, см. README.
"""
import hashlib, json, os, re, threading, time

# --- 1. несовершеннолетние + сексуальный контекст ---------------------------------
_MINOR = (r"child(?:ren)?|kids?|kiddo|minors?|under-?age[d]?|toddlers?|infants?|babies|baby|preteens?|pre-teens?|"
          r"teen(?:s|agers?)?|juvenile|schoolgirls?|schoolboys?|school\s*girls?|school\s*boys?|"
          r"little\s+(?:girl|boy)|young\s+(?:girl|boy)|lolis?|lolicon|shota(?:con)?|barely\s+legal|"
          r"ребён\w*|ребенок|дет(?:ей|и|ям|ьми|ях|ск\w*|ств\w*)|малолет\w*|несовершеннолет\w*|подрост\w*|школьниц\w*|школьник\w*|"
          r"девочк\w*|мальчик\w*|мальчуган\w*|малыш\w*|младенц\w*|лоли\w*|шота\w*|тинейдж\w*")
_MINOR_RE = re.compile(r"(?<![\w])(?:%s)(?![\w])" % _MINOR, re.I)
_NEG_RE = re.compile(r"(?<![\w])(?:no|not|without|never|non|нет|не|без)\s+(?:a\s+|an\s+|any\s+)?(?:%s)(?![\w])" % _MINOR, re.I)
_AGE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[- ]?\s*(?:years?[- ]?old|y\.?\s?o\.?|yo|yrs?|лет|летн\w*|года?|годик\w*)(?![\w])", re.I)
_AGE_RE2 = re.compile(r"(?:age[d]?|aged|возраст\w*)\s*[:=]?\s*(\d{1,2})(?!\d)", re.I)
_ALWAYS_BAD = re.compile(r"(?<![\w])(?:lolicon|shotacon|loli|shota|лоликон|лоли|шота)(?![\w])", re.I)  # термины сами по себе про сексуализацию

# --- откровенный сексуальный контекст ---------------------------------------------
_SEX = (r"nud(?:e|es|ity)|naked|topless|bottomless|nsfw|explicit|porn\w*|erotic\w*|sex(?:ual|y|ually)?|sexy|"
        r"hentai|genital\w*|vagina\w*|penis|cock|pussy|nipples?|breasts?\s+exposed|boobs?|orgasm\w*|masturbat\w*|"
        r"fellatio|blowjob|cum(?:shot)?|intercourse|fetish\w*|lingerie|undress\w*|striptease|stripper|stripping|bdsm|xxx|"
        r"обнаж\w*|гол(?:ая|ый|ое|ые|ую|ыми)|нагот\w*|секс\w*|порн\w*|эрот\w*|интим\w*|нсфв|возбужд\w*|"
        r"член|вагин\w*|сиськ\w*|оргазм\w*|мастурб\w*|минет\w*|бельё|белье|раздева\w*|стрипт\w*")
_SEX_RE = re.compile(r"(?<![\w])(?:%s)(?![\w])" % _SEX, re.I)
# явная порнография - строже: «sexy»/«lingerie» сами по себе не считаются «откровенным» для real_nsfw
_EXPL = (r"nud(?:e|es|ity)|naked|topless|bottomless|nsfw|explicit|porn\w*|hentai|genital\w*|vagina\w*|penis|cock|pussy|"
         r"nipples?|orgasm\w*|masturbat\w*|fellatio|blowjob|cum(?:shot)?|intercourse|xxx|undress\w*|"
         r"обнаж\w*|гол(?:ая|ый|ое|ые|ую|ыми)|нагот\w*|порн\w*|нсфв|член|вагин\w*|оргазм\w*|мастурб\w*|минет\w*|раздева\w*|секс\w*")
_EXPL_RE = re.compile(r"(?<![\w])(?:%s)(?![\w])" % _EXPL, re.I)

# --- 2. реальные люди --------------------------------------------------------------
_REAL_MARK_STRICT = re.compile(
    r"deep\s*fake|face\s*[- ]?swap|faceswap|real\s+(?:person|people|woman|man|girl|boy)|celebrit\w+|famous\s+(?:actress|actor|singer|person|model)|"
    r"(?:my|our)\s+(?:ex|ex-?girlfriend|ex-?boyfriend|neighbou?r|coworker|colleague|classmate|teacher|boss|wife|sister|mother|stepmother|girlfriend)\b|"
    r"дип\s*фейк|подмен\w+\s+лиц\w*|реальн\w+\s+(?:человек|женщин\w*|мужчин\w*|девушк\w*)|знаменитост\w*|известн\w+\s+(?:актрис\w*|актёр\w*|певиц\w*|человек)|"
    r"моей\s+бывш\w+|моей\s+(?:коллег\w*|соседк\w*|подруг\w*|сестр\w*|жен\w*|одноклассниц\w*)|мо[яю]\s+(?:бывш\w+|коллег\w*|соседк\w*|подруг\w*|жен\w*)",
    re.I)
_NAME_RE = re.compile(
    r"(?:\bof|\blike|\bresembling|\blooks?\s+like|\bas|\bfeaturing|\bwith\s+the\s+face\s+of|в\s+образе|похож\w+\s+на|\bс\s+лицом|\bлицо|\bфото)\s+"
    r"[A-ZА-ЯЁ][a-zа-яё]{2,}(?:\s+[A-ZА-ЯЁ][a-zа-яё.\-]{2,}){1,2}")


def _strip_neg(text):
    return _NEG_RE.sub(" ", text)


def _minor_hit(text):
    t = _strip_neg(text)
    if _ALWAYS_BAD.search(t):
        return _ALWAYS_BAD.search(t).group(0)
    m = _MINOR_RE.search(t)
    if m:
        return m.group(0)
    for rx in (_AGE_RE, _AGE_RE2):
        for a in rx.finditer(t):
            if 0 < int(a.group(1)) < 18:
                return a.group(0)
    return None


def check_prompt(prompt, real_person_consent=False):
    """Вернёт None (можно) или {rule, reason, matched}. Негативный промпт не проверяется."""
    text = prompt or ""
    sex = _SEX_RE.search(text)
    # 1) несовершеннолетние + секс: безусловно, согласие не отменяет
    mh = _minor_hit(text)
    if mh and (sex or _ALWAYS_BAD.search(text)):
        return {"rule": "csam", "matched": mh,
                "reason": "Запрещено: сексуальный или откровенный контекст с несовершеннолетними или персонажами-детьми. Жёсткое правило сервиса, не отключается."}
    # 2) реальные люди + откровенность без согласия
    expl = _EXPL_RE.search(text)
    if expl and not real_person_consent:
        mark = _REAL_MARK_STRICT.search(text) or _NAME_RE.search(text)
        if mark:
            return {"rule": "real_nsfw", "matched": mark.group(0).strip(),
                    "reason": "Запрещено: откровенное изображение реального человека без его согласия. Если это вы сами или есть письменное согласие, передайте real_person_consent=true (это ваше заверение, оно журналируется)."}
    return None


class RefusalLog:
    """Журнал отказов: JSONL, по строке на отказ. Хранит время, правило, причину, sha256 и начало промпта."""
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()

    def write(self, verdict, prompt, extra=None):
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "rule": verdict["rule"], "reason": verdict["reason"],
               "matched": verdict.get("matched"), "prompt_sha256": hashlib.sha256((prompt or "").encode("utf-8")).hexdigest(),
               "prompt_head": (prompt or "")[:200]}
        if extra:
            rec.update(extra)
        d = os.path.dirname(self.path)
        with self._lock:
            if d:
                os.makedirs(d, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def tail(self, n=50):
        try:
            with open(self.path, encoding="utf-8") as f:
                lines = f.readlines()[-n:]
            return [json.loads(x) for x in lines if x.strip()]
        except FileNotFoundError:
            return []
