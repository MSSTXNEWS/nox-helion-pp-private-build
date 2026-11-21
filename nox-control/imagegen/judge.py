"""Судья зрения: «получилось ли то, что просили». PNG (base64) -> vision-эндпоинт (OpenAI chat, image_url).

env: NOX_VISION_URL  - полный URL .../chat/completions либо база до /v1 (дописываем /chat/completions)
     NOX_VISION_MODEL (по умолчанию "default"), NOX_VISION_KEY (Bearer, необязательно), NOX_VISION_TIMEOUT (с, 180)
Ответ: {configured, ok, reasons, ...}; ok=None, если судью не удалось опросить (не считаем это «хорошо»).
"""
import base64, json, os, re, urllib.request, urllib.error

NOT_CONFIGURED = "судья зрения не настроен"
SYSTEM = ("Ты строгий судья сгенерированных изображений. Тебе дают исходный запрос и картинку. "
          "Оцени, получилось ли то, что просили: все ли ключевые объекты, количество, цвета, композиция, стиль, читаемость текста на картинке, "
          "нет ли явных артефактов (лишние пальцы, искажённые лица, мусор). Ответь ТОЛЬКО JSON без пояснений вокруг: "
          '{"ok": true|false, "reasons": ["короткая причина", ...]}. ok=true только если запрос выполнен по существу; '
          "в reasons при ok=false перечисли, что не так и что исправить в промпте.")


def _endpoint(url):
    u = url.rstrip("/")
    return u if u.endswith("/chat/completions") else u + "/chat/completions"


def parse_verdict(text):
    """Достать {ok, reasons} из ответа модели (допускаем ```json и текст вокруг)."""
    if not isinstance(text, str):
        raise ValueError("ответ судьи не строка")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("в ответе судьи нет JSON")
    obj = json.loads(m.group(0))
    ok = obj.get("ok")
    if not isinstance(ok, bool):
        raise ValueError("поле ok должно быть true/false")
    reasons = obj.get("reasons", [])
    if isinstance(reasons, str):
        reasons = [reasons]
    if not isinstance(reasons, list):
        raise ValueError("reasons должен быть списком")
    return {"ok": ok, "reasons": [str(r) for r in reasons]}


def judge_image(png, prompt, url=None, model=None, key=None, timeout=None, negative=""):
    url = url if url is not None else os.environ.get("NOX_VISION_URL", "")
    if not url:
        return {"configured": False, "ok": None, "reasons": [NOT_CONFIGURED]}
    model = model or os.environ.get("NOX_VISION_MODEL", "default")
    key = key if key is not None else os.environ.get("NOX_VISION_KEY", "")
    timeout = timeout or float(os.environ.get("NOX_VISION_TIMEOUT", "180"))
    b64 = base64.b64encode(png).decode()
    user = "Запрос на картинку: %s" % prompt
    if negative:
        user += "\nНе должно быть: %s" % negative
    body = {"model": model, "temperature": 0, "max_tokens": 400,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": [{"type": "text", "text": user},
                                                      {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]}]}
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(_endpoint(url), json.dumps(body).encode(), headers, "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"]
        if isinstance(text, list):   # часть серверов отдаёт content списком частей
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        v = parse_verdict(text)
    except urllib.error.HTTPError as e:
        return {"configured": True, "ok": None, "reasons": ["vision HTTP %d: %s" % (e.code, e.read()[:200].decode("utf-8", "replace"))], "error": True}
    except (urllib.error.URLError, OSError) as e:
        return {"configured": True, "ok": None, "reasons": ["vision недоступен: %s" % e], "error": True}
    except (ValueError, KeyError, IndexError, TypeError) as e:
        return {"configured": True, "ok": None, "reasons": ["не разобрать ответ судьи: %s" % e], "error": True}
    v["configured"] = True
    return v
