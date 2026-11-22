"""Input encoding for the local NOX operation router, Python standard library.

Schema v1 has 119 positions in fixed order: 12 text-shape features, 24
bilingual lexical intent cues, 19 top-level payload shape cues, and two
separately normalized hashed banks of 32 positions each. The API does not
learn, identify a person, read the full conversation, or choose an operation;
the caller supplies exactly the current text and optional operation payload.

A position is an input to the router, not an independent mental faculty or
the weight of an operation. Lexical cues can co-occur. The 32 token and 32
within-word character-trigram buckets deliberately collide. Equal intent
cues across languages do not imply equal full vectors. Values are finite
floats in [0,1]. Empty text and payload give an all-zero vector.
"""
from collections import Counter
import hashlib
import math
import re
import unicodedata


ENCODER_ID = "nox.features.ru-es.v1.119"
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_CYR = re.compile(r"[\u0400-\u052f]")
_LAT = re.compile(r"[a-z\u00c0-\u024f]")
_TIME = re.compile(r"(?<!\d)\d{1,2}:\d{2}(?::\d{2})?(?!\d)")
_LEADING_LIST = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+")
SHAPE = ("log_characters", "log_tokens", "vocabulary_ratio", "digit_fraction",
         "cyrillic_fraction", "latin_fraction", "question", "quotation",
         "multiline", "graph_arrow", "timestamp", "list_markup")

# Match whole tokens, or prefixes explicitly marked with *. Lexical overlap
# is intentional, e.g. "почему изменил решение?" is both causal and revisional.
INTENTS = {
    "recall": "вспом* помни* помню памя* recuerd* recorda* memoria",
    "search": "найди ищи поис* искать encuentra busca* localiza*",
    "compare": "сравн* сопостав* разниц* compara* contrast* diferenci*",
    "revise": "пересмотр* исправ* передела* замен* revisa* corrige* cambi* reemplaz*",
    "reason": "причин* почему из-за обосну* razón razon* causa* explica* porqué porque",
    "predict": "прогноз* предскаж* ожида* вероятн* predic* pronosti* anticip* probab*",
    "evidence": "докаж* доказ* источник* подтверж* eviden* fuente* demuestra* verific*",
    "plan": "план* задач* заплан* расписан* plan planif* tarea* agenda* calendario*",
    "dependency": "завис* блокир* порядок упорядоч* depend* bloque* ordena* prerrequis*",
    "estimate": "оцени* оценк* оценить стоим* бюджет* estima* eval* coste* presupuest*",
    "choose": "выбер* выбра* выбор решени* elige elij* escoge* opcion* opción* decisi*",
    "promise": "обеща* обязател* договорил* comprom* promes* promet* acorda* acordó",
    "preference": "предпоч* нравит* вкус gusta* prefer* gusto*",
    "create": "созда* придум* сочин* смонтир* invent* crea* compón compone* monta*",
    "learn": "обуч* научи* учись урок* учител* aprend* enseñ* lecci*",
    "reflect": "передум* осмысл* переосмысл* вывод* reconsider* reflexi* conclusión*",
    "quote": "цитат* процитир* абзац* выдел* cita citas citar* párrafo* seleccion*",
    "voice": "голос* звук* слыш* услыш* озвуч* escucha* voz voces audio* sonido*",
    "interrupt": "переб* останов* прерв* продолж* возобнов* interrum* deten* continú* reanud*",
    "caption": "субтитр* таймкод* расшифро* subtítul* subtitul* transcri*",
    "translate": "перевед* перевод* испанск* русск* traduc* traducción español castellano ruso",
    "measure": "подсчи* посчит* измер* частот* числ* cuenta contar* calcul* frecuen* mide",
    "disagree": "возраж* спор* несоглас* оспор* discre* objeci* objeta* desacuerdo",
    "history": "вчера раньше прежде истори* верси* ayer antes historial* versión* versione*",
}

# A schema cue concerns which fields the caller supplied, even for a valid
# empty list or an explicit zero timestamp. Null does not assert a field.
PAYLOAD = {
    "document": ("text", "document_id", "document", "srt"),
    "revision": ("new_text", "replacement", "baseline", "before", "after"),
    "selection": ("start", "end", "other_start", "other_end", "anchor", "anchors"),
    "captions": ("cues", "captions", "srt"),
    "playhead": ("position_ms", "start_ms", "end_ms", "media_id"),
    "dialogue": ("turns", "turn_id", "other_turn_id", "reply_to"),
    "task_graph": ("tasks", "deps", "edges"),
    "schedule": ("due", "deadline", "days", "capacities", "calendar"),
    "choices": ("options", "variants", "criteria", "weights"),
    "events": ("events", "as_of", "as_known", "timeline"),
    "claims": ("claims", "evidence", "assumptions", "sources"),
    "learning": ("examples", "labels", "predictions", "model", "scores"),
    "taste": ("preferences", "taste", "chosen", "accepted"),
    "social": ("participants", "agreements", "commitments", "audience", "turns"),
    "creative": ("scene", "base", "overlay", "clips", "fragments"),
    "identity": ("actor", "owner", "speaker", "role", "author"),
    "reference": ("key", "source", "scope", "origin", "revision"),
    "query": ("query", "search", "limit", "fields"),
    "numeric_series": ("series", "values", "observations", "samples", "measurements"),
}

FEATURE_NAMES = tuple(["shape." + x for x in SHAPE] + ["cue." + x for x in INTENTS]
                      + ["payload." + x for x in PAYLOAD]
                      + [f"word_hash.{i:02}" for i in range(32)]
                      + [f"trigram_hash.{i:02}" for i in range(32)])


def _fold(token):
    # Keep ñ distinct; Latin accents are retained for both lexical and hash banks.
    return unicodedata.normalize("NFKC",token).casefold().replace("ё","е")


def _patterns(values):
    entries = [_fold(v) for v in values.split()]
    return ({v for v in entries if not v.endswith("*")},
            tuple(v[:-1] for v in entries if v.endswith("*")))


_MATCHERS = tuple(_patterns(v) for v in INTENTS.values())


def _bank(counts, person):
    buckets = [0.0] * 32
    for token, count in counts.items():
        h = hashlib.blake2s(token.encode("utf-8"), digest_size=2, person=person).digest()
        buckets[int.from_bytes(h,"little") % 32] += count
    buckets = [math.log1p(x) for x in buckets]
    norm = math.sqrt(sum(x*x for x in buckets))
    return [x/norm for x in buckets] if norm else buckets


def _bounded_log(n, reference):
    return min(1.0, math.log1p(n) / math.log1p(reference))


def encode(text: str, data: dict = None) -> list[float]:
    """Encode caller-supplied instruction and top-level JSON argument keys.

    Token and trigram frequencies cover the complete input string. Payload
    values never enter the lexical hash banks. No Python randomized hash,
    network call, random seed, model, task history or cache is required.
    """
    if not isinstance(text,str):
        raise TypeError("text must be a string")
    if data is None:
        data = {}
    if not isinstance(data,dict):
        raise TypeError("data must be a dictionary")
    normalized = _fold(text)
    tokens = _TOKEN.findall(normalized)
    counts = Counter(tokens)
    n_letters = max(1,sum(c.isalpha() for c in normalized))
    shape = [_bounded_log(len(normalized),16000),_bounded_log(len(tokens),2000),
             len(counts)/max(1,len(tokens)),sum(c.isdigit() for c in normalized)/max(1,len(normalized)),
             sum(bool(_CYR.fullmatch(c)) for c in normalized if c.isalpha())/n_letters,
             sum(bool(_LAT.fullmatch(c)) for c in normalized if c.isalpha())/n_letters,
             float("?" in normalized or "¿" in normalized),
             float(any(c in normalized for c in '«»“”"')),
             float("\n" in normalized or "\r" in normalized),
             float("->" in normalized or "→" in normalized),
             float(bool(_TIME.search(normalized))),float(bool(_LEADING_LIST.search(normalized)))]
    lexical = [float(any(w in exact or (prefixes and w.startswith(prefixes)) for w in counts))
               for exact,prefixes in _MATCHERS]
    # Spanish "por qué" is a two-word cue with a potentially meaningful accent.
    if "por" in counts and re.search(r"\bpor\s+qué\b",normalized):
        lexical[tuple(INTENTS).index("reason")] = 1.0
    structure = [float(any(k in data and data[k] is not None for k in keys))
                 for keys in PAYLOAD.values()]
    grams = Counter()
    for word,count in counts.items():
        wrapped = "^" + word + "$"
        for i in range(len(wrapped)-2):
            grams[wrapped[i:i+3]] += count
    return shape + lexical + structure + _bank(counts,b"noxword1") + _bank(grams,b"noxgram1")
