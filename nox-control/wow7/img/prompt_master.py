"""IMG: мастер-промпт «ведущий графический дизайнер» + раскладка поля позитив/негатив/общий + ползунок быстро<->качество.

Страница «Графика» передаёт: brief (идея словами), positive/negative/general (необязательные ручные поля), slider 0..100.
build_request() -> параметры для img_service. Если задан llm (callable(messages)->str, например быстрый тир :8083), дизайнер
переписывает идею в позитив/негатив; без LLM или при ошибке - детерминированная сборка (compose_offline), всегда работает.
Тематических и стилистических ограничений здесь нет. Жёсткие запреты - ТОЛЬКО policy_hard.py (сервис проверяет итоговый позитив).
"""
import json, re

MASTER_PROMPT = """Ты - ведущий графический дизайнер и арт-директор студии NOX. Ты превращаешь идею Создателя в точный промпт для диффузионной модели.
Правила ремесла:
1. Субъект первым: кто/что, действие, поза, выражение; затем окружение; затем стиль и носитель (фото, масляная живопись, 3D, аниме, постер).
2. Свет, ракурс, объектив/кадр, палитра, фактуры, настроение - конкретно, без воды и без повторов.
3. Пиши на английском естественными фразами (модели Chroma/Z-Image понимают язык, а не теги); названия и надписи в кавычках сохраняй как есть.
4. Не смягчай и не цензурируй замысел: взрослая и тёмная тематика допустима. Исключение - жёсткие правила сервиса (их проверяет код, не ты).
5. Негативный промпт - только технические дефекты и то, что явно просили убрать.
6. Учитывай «общий промпт» (стиль/правила для всей серии) как обязательный, а ручные позитив/негатив - как приоритетные уточнения.
Ответь ТОЛЬКО JSON: {"positive": "...", "negative": "...", "aspect": "1:1|3:2|2:3|16:9|9:16|4:3|3:4", "notes": "что решил и почему, 1-2 фразы по-русски"}"""

DEFAULT_NEGATIVE = ("low quality, blurry, out of focus, deformed hands, extra fingers, malformed limbs, duplicated face, "
                    "watermark, signature, text artifacts, jpeg artifacts, oversaturated, cropped")
QUALITY_TAIL = "highly detailed, sharp focus, professional composition"
ASPECTS = {"1:1": (1024, 1024), "3:2": (1216, 832), "2:3": (832, 1216), "16:9": (1344, 768), "9:16": (768, 1344), "4:3": (1152, 896), "3:4": (896, 1152)}


def mode_params(slider):
    """slider 0..100 -> {role: fast|main, steps, guidance(None=по модели), n, judge, label}. 0 = быстрее всего, 100 = лучшее качество."""
    s = max(0, min(100, int(slider)))
    if s <= 33:
        return {"role": "fast", "steps": 9, "n": 1, "judge": False, "scale": 0.75, "label": "быстро"}
    if s <= 66:
        return {"role": "fast", "steps": 9, "n": 2, "judge": True, "scale": 1.0, "label": "баланс"}
    steps = 20 + round((s - 67) / 33 * 20)          # 20..40 шагов Chroma
    return {"role": "main", "steps": steps, "n": 3 if s >= 90 else 2 if s >= 80 else 1, "judge": s >= 80, "scale": 1.0, "label": "качество"}


def size_for(aspect, scale=1.0, width=None, height=None):
    if width and height:
        return int(width) // 16 * 16, int(height) // 16 * 16
    w, h = ASPECTS.get(aspect or "1:1", ASPECTS["1:1"])
    return max(256, int(w * scale) // 16 * 16), max(256, int(h * scale) // 16 * 16)


def _clean(s):
    return re.sub(r"\s+", " ", (s or "").strip()).strip(" ,.;")


def compose_offline(brief="", positive="", negative="", general=""):
    """Детерминированная сборка без LLM: общий (стиль серии) + ручной позитив + идея + хвост качества. Негатив: дефекты + ручной."""
    pos = [x for x in (_clean(positive), _clean(brief), _clean(general), QUALITY_TAIL) if x]
    neg = [x for x in (_clean(negative), DEFAULT_NEGATIVE) if x]
    return {"positive": ", ".join(pos), "negative": ", ".join(neg), "aspect": None, "notes": "офлайн-сборка (LLM не использован)", "source": "offline"}


def build_messages(brief, positive="", negative="", general="", mode_label="баланс"):
    user = "Идея: %s\nОбщий промпт (обязателен): %s\nРучной позитив: %s\nРучной негатив: %s\nРежим: %s" % (
        _clean(brief) or "(нет, используй ручной позитив)", _clean(general) or "-", _clean(positive) or "-", _clean(negative) or "-", mode_label)
    return [{"role": "system", "content": MASTER_PROMPT}, {"role": "user", "content": user}]


def parse_reply(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("нет JSON в ответе дизайнера")
    o = json.loads(m.group(0))
    pos = _clean(o.get("positive"))
    if not pos:
        raise ValueError("пустой positive")
    asp = o.get("aspect") if o.get("aspect") in ASPECTS else None
    return {"positive": pos, "negative": _clean(o.get("negative")) or DEFAULT_NEGATIVE, "aspect": asp, "notes": _clean(o.get("notes")), "source": "llm"}


def build_request(brief="", positive="", negative="", general="", slider=50, aspect=None, width=None, height=None, seed=None, llm=None):
    """Главная функция для страницы «Графика» и инструмента BRAIN. Вернёт тело для POST /generate (positive/negative/model_role/steps/...)."""
    mp = mode_params(slider)
    res = None
    if llm is not None and (_clean(brief) or _clean(positive)):
        try:
            res = parse_reply(llm(build_messages(brief, positive, negative, general, mp["label"])))
            if _clean(general) and _clean(general).lower() not in res["positive"].lower():
                res["positive"] += ", " + _clean(general)          # общий промпт обязателен всегда
            if _clean(negative) and _clean(negative).lower() not in res["negative"].lower():
                res["negative"] = _clean(negative) + ", " + res["negative"]
        except Exception as e:
            res = None
            err = "%s: %s" % (type(e).__name__, e)
    if res is None:
        res = compose_offline(brief, positive, negative, general)
        if llm is not None:
            res["notes"] += "; LLM не ответил (%s)" % err
    w, h = size_for(aspect or res.get("aspect"), mp["scale"], width, height)
    body = {"positive": res["positive"], "negative": res["negative"], "model_role": mp["role"], "steps": mp["steps"], "n": mp["n"], "judge": mp["judge"],
            "width": w, "height": h, "slider": int(slider), "mode_label": mp["label"], "notes": res["notes"], "prompt_source": res["source"]}
    if seed is not None:
        body["seed"] = int(seed)
    return body
