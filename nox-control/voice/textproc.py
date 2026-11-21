"""Подготовка текста к озвучке: очистка (markdown, эмодзи, URL), числа и аббревиатуры RU/ES,
потоковый сегментатор по предложениям/фразам. Только stdlib."""
import re

# ---------------- числа ----------------
_RU_ONES_M = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_RU_ONES_F = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_RU_TEENS = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать",
             "семнадцать", "восемнадцать", "девятнадцать"]
_RU_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
_RU_HUND = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]
_RU_SCALES = [("", "", "", "m"), ("тысяча", "тысячи", "тысяч", "f"), ("миллион", "миллиона", "миллионов", "m"),
              ("миллиард", "миллиарда", "миллиардов", "m"), ("триллион", "триллиона", "триллионов", "m")]


def ru_plural(n, one, few, many):
    n = abs(n)
    if 11 <= n % 100 <= 14:
        return many
    r = n % 10
    return one if r == 1 else few if 2 <= r <= 4 else many


def _ru_triplet(n, fem):
    out = []
    out.append(_RU_HUND[n // 100])
    t = n % 100
    if 10 <= t <= 19:
        out.append(_RU_TEENS[t - 10])
    else:
        out.append(_RU_TENS[t // 10])
        out.append((_RU_ONES_F if fem else _RU_ONES_M)[t % 10])
    return [w for w in out if w]


def ru_int(n, fem=False):
    if n == 0:
        return "ноль"
    if n < 0:
        return "минус " + ru_int(-n, fem)
    if n >= 10 ** 15:
        return " ".join(ru_int(int(c)) if False else _digits_ru(c) for c in [str(n)])
    parts = []
    scale = 0
    while n > 0:
        n, t = divmod(n, 1000)
        if t:
            sc = _RU_SCALES[scale]
            words = _ru_triplet(t, fem if scale == 0 else sc[3] == "f")
            if scale:
                words.append(ru_plural(t, sc[0], sc[1], sc[2]))
            parts.insert(0, " ".join(words))
        scale += 1
    return " ".join(parts)


def _digits_ru(s):
    return " ".join(("ноль" if d == "0" else _RU_ONES_M[int(d)]) for d in s if d.isdigit())


_ES_ONES = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
            "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno",
            "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve"]
_ES_TENS = ["", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
_ES_HUND = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos", "setecientos",
            "ochocientos", "novecientos"]


def _es_below_1000(n):
    if n == 100:
        return "cien"
    out = []
    if n >= 100:
        out.append(_ES_HUND[n // 100])
        n %= 100
    if n:
        if n < 30:
            out.append(_ES_ONES[n])
        else:
            t, o = divmod(n, 10)
            out.append(_ES_TENS[t] + (" y " + _ES_ONES[o] if o else ""))
    return " ".join(out)


def es_int(n):
    if n == 0:
        return "cero"
    if n < 0:
        return "menos " + es_int(-n)
    if n >= 10 ** 12:
        return " ".join(_ES_ONES[int(d)] for d in str(n))
    parts = []
    if n >= 10 ** 9:
        b, n = divmod(n, 10 ** 9)
        parts.append("mil millones" if b == 1 else es_int(b) + " mil millones")
    if n >= 10 ** 6:
        m, n = divmod(n, 10 ** 6)
        parts.append("un millón" if m == 1 else es_int(m) + " millones")
    if n >= 1000:
        k, n = divmod(n, 1000)
        parts.append("mil" if k == 1 else _es_below_1000(k).replace("uno", "un") + " mil")
    if n:
        parts.append(_es_below_1000(n))
    return " ".join(parts)


def detect_lang(text, default="ru"):
    cyr = sum(1 for c in text if "Ѐ" <= c <= "ӿ")
    lat = sum(1 for c in text if c.isascii() and c.isalpha())
    if cyr > lat:
        return "ru"
    if re.search(r"[¿¡ñáéíóúü]", text, re.I) or re.search(r"\b(el|la|los|las|que|de|un|una|es|por|para|con|no|muy|hola)\b", text, re.I):
        return "es"
    return default if lat == 0 else ("es" if default == "es" else default)


# ---------------- аббревиатуры и единицы ----------------
_ABBR = {
    "ru": [
        (r"\bи т\. ?д\.", "и так далее"), (r"\bи т\. ?п\.", "и тому подобное"), (r"\bт\. ?е\.", "то есть"),
        (r"\bт\. ?к\.", "так как"), (r"\bт\. ?н\.", "так называемый"), (r"\bи др\.", "и другие"), (r"\bи пр\.", "и прочее"),
        (r"\bнапр\.", "например"), (r"\bсм\. ", "смотри "), (r"\bрис\. ", "рисунок "), (r"\bг\. ", "город "),
        (r"\bим\. ", "имени "),
    ],
    "es": [
        (r"\bp\. ?ej\.", "por ejemplo"), (r"\betc\.", "etcétera"), (r"\bEE\. ?UU\.", "Estados Unidos"),
        (r"\bSr\. ", "señor "), (r"\bSra\. ", "señora "), (r"\bDr\. ", "doctor "), (r"\bDra\. ", "doctora "),
        (r"\bUd\. ", "usted "), (r"\bUds\. ", "ustedes "), (r"\bpág\. ", "página "), (r"\bvs\. ", "contra "),
    ],
}
# единицы: (regex, ru (one, few, many), es (sing, plur))
_UNITS = [
    (r"ГБ|Гб|GB", ("гигабайт", "гигабайта", "гигабайт"), ("gigabyte", "gigabytes")),
    (r"МБ|Мб|MB", ("мегабайт", "мегабайта", "мегабайт"), ("megabyte", "megabytes")),
    (r"КБ|Кб|KB", ("килобайт", "килобайта", "килобайт"), ("kilobyte", "kilobytes")),
    (r"ТБ|Тб|TB", ("терабайт", "терабайта", "терабайт"), ("terabyte", "terabytes")),
    (r"кг|kg", ("килограмм", "килограмма", "килограммов"), ("kilogramo", "kilogramos")),
    (r"км|km", ("километр", "километра", "километров"), ("kilómetro", "kilómetros")),
    (r"мс|ms", ("миллисекунда", "миллисекунды", "миллисекунд"), ("milisegundo", "milisegundos")),
    (r"°C|°С", ("градус Цельсия", "градуса Цельсия", "градусов Цельсия"), ("grado Celsius", "grados Celsius")),
    (r"ГГц|GHz", ("гигагерц", "гигагерца", "гигагерц"), ("gigahercio", "gigahercios")),
    (r"ядер|vCPU", ("ядро", "ядра", "ядер"), ("núcleo", "núcleos")),
]
_WORDS_ABBR = {
    "ru": {"ИИ": "и и", "GPU": "джи пи ю", "CPU": "си пи ю", "VRAM": "ви рам", "API": "эй пи ай", "URL": "ю эр эл", "LLM": "эл эл эм",
           "STT": "эс ти ти", "TTS": "ти ти эс", "NOX": "нокс", "HELION": "хелион", "OK": "окей", "ОК": "окей"},
    "es": {"GPU": "ge pe u", "CPU": "ce pe u", "VRAM": "uve ram", "API": "a pe i", "URL": "u erre ele", "IA": "i a", "LLM": "ele ele eme",
           "STT": "ese te te", "TTS": "te te ese", "NOX": "nox", "OK": "vale"},
}

_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U0001F1E6-\U0001F1FF‍️⃣←-⇿⌀-⏿■-◿]+")


def _num_to_words(s, lang):
    try:
        n = int(s)
    except ValueError:
        return s
    return ru_int(n) if lang == "ru" else es_int(n)


def numbers_to_words(text, lang):
    """Числа -> слова (целые, десятичные, проценты, единицы, минус, время). Порядковые (1-й) не склоняются - честное ограничение."""
    # проценты
    def pct(m):
        raw = m.group(1)
        if re.search(r"[.,]", raw):
            return decimal_words(raw, lang) + (" процента" if lang == "ru" else " por ciento")
        n = int(raw)
        if lang == "ru":
            return "%s %s" % (ru_int(n), ru_plural(n, "процент", "процента", "процентов"))
        return "%s por ciento" % es_int(n)
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s?%", pct, text)

    # число + единица
    for pat, ru, es in _UNITS:
        def unit(m, ru=ru, es=es):
            raw = m.group(1)
            frac = re.search(r"[.,]", raw)
            if frac:
                w = decimal_words(raw, lang)
                u = ru[1] if lang == "ru" else es[1]
                return "%s %s" % (w, u)
            n = int(raw)
            if lang == "ru":
                fem = ru[0] in ("миллисекунда",)
                return "%s %s" % (ru_int(n, fem), ru_plural(n, *ru))
            return "%s %s" % (es_int(n), es[0] if n == 1 else es[1])
        text = re.sub(r"(\d+(?:[.,]\d+)?)\s?(?:%s)(?![\wА-Яа-я])" % pat, unit, text)

    text = re.sub(r"(?<=\d):(?=\d{2}\b)", " ", text)          # 12:30 -> 12 30
    text = re.sub(r"(?<=\d)\s?[-–—]\s?(?=\d)", " ", text)     # 5-10 -> 5 10
    text = re.sub(r"(?<![\w.,])-(?=\d)", "минус " if lang == "ru" else "menos ", text)
    text = re.sub(r"\d+[.,]\d+", lambda m: decimal_words(m.group(0), lang), text)
    text = re.sub(r"\d{1,3}(?:[  ]\d{3})+(?!\d)", lambda m: _num_to_words(re.sub(r"\D", "", m.group(0)), lang), text)
    text = re.sub(r"\d+", lambda m: _num_to_words(m.group(0), lang), text)
    return text


def decimal_words(raw, lang):
    ip, fp = re.split(r"[.,]", raw, maxsplit=1)
    comma = "запятая" if lang == "ru" else "coma"
    # дробную часть читаем как целое, если нет ведущих нулей, иначе по цифрам
    if fp.startswith("0") or len(fp) > 3:
        frac = " ".join(("ноль" if d == "0" else _RU_ONES_M[int(d)]) if lang == "ru" else _ES_ONES[int(d)] for d in fp)
    else:
        frac = _num_to_words(fp, lang)
    return "%s %s %s" % (_num_to_words(ip, lang), comma, frac)


def strip_markdown(text):
    t = text
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"```.*$", " ", t, flags=re.S)           # незакрытый блок
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"<[^>\n]{1,200}>", " ", t)
    t = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", t)
    t = re.sub(r"(?m)^\s*>\s?", "", t)
    t = re.sub(r"(?m)^\s*[-*+•]\s+", "", t)
    t = re.sub(r"(?m)^\s*\d+[.)]\s+", "", t)
    t = re.sub(r"(?m)^\s*[-=_*]{3,}\s*$", " ", t)
    t = re.sub(r"(?m)^\s*\|?[\s:|-]{3,}\|?\s*$", " ", t)
    t = t.replace("|", ", ")
    t = re.sub(r"(\*\*|__|~~)", "", t)
    t = re.sub(r"(?<![\w*])[*_]+(\S(?:.*?\S)?)[*_]+(?![\w*])", r"\1", t)
    t = t.replace("*", "")
    return t


def clean_for_tts(text, lang="auto"):
    """Полная очистка фразы: markdown, URL, эмодзи, аббревиатуры, числа, пробелы."""
    if lang in (None, "", "auto"):
        lang = detect_lang(text)
    t = strip_markdown(text or "")
    t = re.sub(r"https?://\S+|www\.\S+", "ссылка" if lang == "ru" else "enlace", t)
    t = re.sub(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b", "почта" if lang == "ru" else "correo", t)
    t = _EMOJI.sub(" ", t)
    for pat, rep in _ABBR.get(lang, []):
        t = re.sub(pat, rep, t, flags=re.I)
    t = numbers_to_words(t, lang)
    for k, v in _WORDS_ABBR.get(lang, {}).items():
        t = re.sub(r"(?<![\wА-Яа-я])%s(?![\wА-Яа-я])" % re.escape(k), v, t)
    t = t.replace("&", " и " if lang == "ru" else " y ").replace("+", " плюс " if lang == "ru" else " más ")
    t = t.replace("=", " равно " if lang == "ru" else " igual ").replace("→", ", ").replace("—", " - ").replace("–", " - ")
    t = re.sub(r"[#@^~<>{}\[\]\\/_]", " ", t)
    t = re.sub(r"\s*\n+\s*", ". ", t) if re.search(r"\w\s*\n", t) else t.replace("\n", " ")
    t = re.sub(r"\.\s*\.(?!\.)", ".", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([,.!?;:])", r"\1", t)
    return t


def has_speakable(text):
    return bool(re.search(r"\w", text or ""))


# ---------------- сегментатор ----------------
_NONTERM_TOKENS = {
    "т", "е", "д", "п", "н", "к", "др", "пр", "напр", "см", "рис", "г", "гг", "им", "ул", "стр", "тыс", "млн", "млрд", "руб", "коп",
    "sr", "sra", "dr", "dra", "ud", "uds", "pág", "ej", "vs", "núm", "aprox", "etc",
}
_TERM = ".!?…"
_CLOSERS = "\"'»”)]"


class SentenceSegmenter:
    """Потоковый сегментатор. feed(delta) -> список готовых фраз; flush() -> остаток.
    Правила: конец предложения (. ! ? …, перенос строки) вне аббревиатур/десятичных; слишком короткие куски
    (< min_chars) склеиваются со следующими; первая фраза режется по запятой/двоеточию уже после first_min_chars
    (быстрый старт речи); длинные куски (> max_chars) режутся по запятой/пробелу; блоки ``` пропускаются."""

    def __init__(self, min_chars=12, first_min_chars=30, max_chars=180, early_first=True):
        self.min_chars = min_chars
        self.first_min_chars = first_min_chars
        self.max_chars = max_chars
        self.early_first = early_first
        self.buf = ""
        self._raw = ""
        self._fence = False
        self._emitted = 0
        self._held = ""   # короткий кусок, ждущий склейки

    # --- фенсы ---
    def _absorb(self, s):
        self._raw += s
        out = []
        while self._raw:
            if not self._fence:
                i = self._raw.find("```")
                if i >= 0:
                    out.append(self._raw[:i])
                    out.append("\n")
                    self._raw = self._raw[i + 3:]
                    self._fence = True
                    continue
                keep = 0
                for k in (2, 1):
                    if self._raw.endswith("`" * k):
                        keep = k
                        break
                out.append(self._raw[: len(self._raw) - keep])
                self._raw = self._raw[len(self._raw) - keep:]
                break
            i = self._raw.find("```")
            if i >= 0:
                self._raw = self._raw[i + 3:]
                self._fence = False
                continue
            keep = 2 if self._raw.endswith("``") else 1 if self._raw.endswith("`") else 0
            self._raw = self._raw[len(self._raw) - keep:]
            break
        self.buf += "".join(out)

    def _is_terminator(self, s, i):
        """s[i] in '.!?…' - конец предложения? Нужен символ после (или точка в самом конце - решается позже)."""
        c = s[i]
        if c in "!?…":
            return True
        j = i + 1
        while j < len(s) and s[j] in _CLOSERS:
            j += 1
        if j < len(s) and not s[j].isspace():
            return False            # 3.5, example.com, т.е.
        k = i
        while k > 0 and (s[k - 1].isalnum() or s[k - 1] == "."):
            k -= 1
        token = s[k:i].lower().strip(".")
        last = token.split(".")[-1] if token else ""
        if last in _NONTERM_TOKENS and (len(last) <= 3 or token in _NONTERM_TOKENS):
            return token == "etc"
        if token.isdigit() and (k == 0 or s[k - 1] == "\n"):
            return False            # «1. пункт»
        return True

    def _split_ready(self, final=False):
        out = []
        while True:
            s = self.buf
            cut = -1
            i = 0
            while i < len(s):
                c = s[i]
                if c == "\n":
                    if s[:i].strip():
                        cut = i + 1
                        break
                    i += 1
                    continue
                if c in _TERM:
                    j = i + 1
                    while j < len(s) and s[j] in _TERM:
                        j += 1
                    while j < len(s) and s[j] in _CLOSERS:
                        j += 1
                    if j >= len(s) and not final:
                        break           # ждём следующий символ
                    if self._is_terminator(s, j - 1 if s[j - 1] in _TERM else i) or c in "!?…":
                        cut = j
                        break
                    i = j
                    continue
                i += 1
            if cut < 0:
                early = self._early_cut(s)
                if early > 0:
                    cut = early
                elif len(s) > self.max_chars:
                    cut = self._long_cut(s)
            if cut < 0:
                break
            piece, self.buf = s[:cut], s[cut:]
            out.extend(self._emit(piece))
        return out

    def _early_cut(self, s):
        limit = self.first_min_chars if self._emitted == 0 and not self._held and self.early_first else None
        if limit is None or len(s) < limit:
            return -1
        for i in range(limit - 1, len(s)):
            if s[i] in ",;:—" and (i + 1 >= len(s) or s[i + 1].isspace()) and i + 1 < len(s):
                return i + 1
        return -1

    def _long_cut(self, s):
        seg = s[: self.max_chars]
        for chars in (",;:", " "):
            idx = max(seg.rfind(c) for c in chars)
            if idx > self.min_chars:
                return idx + 1
        return self.max_chars

    def _emit(self, piece):
        text = ((self._held + " " if self._held else "") + piece.strip()).strip()
        self._held = ""
        if not text:
            return []
        if not has_speakable(text):
            return []
        if len(text) < self.min_chars and not self._force:
            self._held = text
            return []
        self._emitted += 1
        return [text]

    _force = False

    def feed(self, delta):
        self._absorb(delta or "")
        return self._split_ready()

    def flush(self):
        self._absorb("")
        self._force = True
        try:
            out = self._split_ready(final=True)
            rest = ((self._held + " " if self._held else "") + self.buf.strip()).strip()
            self._held = ""
            self.buf = ""
            if rest and has_speakable(rest):
                out.append(rest)
                self._emitted += 1
        finally:
            self._force = False
        self._raw = ""
        self._fence = False
        return out

    def reset(self):
        self.__init__(self.min_chars, self.first_min_chars, self.max_chars, self.early_first)


def split_text(text, **kw):
    """Удобство: разбить целый текст на фразы."""
    s = SentenceSegmenter(**kw)
    return s.feed(text) + s.flush()
