"""IMG: инструмент ДЕЙСТВИЯ для BRAIN (формат TaskRunnerPlanner: match/preview/irreversible/execute). «Нарисуй ...» -> превью -> подтверждение -> генерация -> квитанция.
Мастер-промпт и политика выполняются внутри img_service (здесь только вызов HTTP и честная строка результата). Генерация обратима (файл можно удалить)."""
import json, os, re, urllib.error, urllib.request

BASE = os.environ.get("NOX_IMG_URL", "http://127.0.0.1:8097")
_TRIG = re.compile(r"^\s*(?:нокс[,:]?\s*)?(?:нарисуй|сгенерируй|создай|сделай)\s+(?:мне\s+)?(?:(?:картинк\w*|изображени\w*|арт|рисунок|фото|постер|иллюстраци\w*)\s*[:,-]?\s*)?(.+)$", re.I | re.S)
_Q = re.compile(r"\b(качествен\w*|максимальн\w+\s+качеств\w*|лучш\w+\s+качеств\w*)\b", re.I)
_FAST = re.compile(r"\b(быстро|быстрый\s+вариант|набросок)\b", re.I)


class ImgActionPlanner:
    kind = "image_generation"

    def __init__(self, base=None, post=None):
        self.base = base or BASE
        self.post = post or self._post

    def match(self, text):
        m = _TRIG.match(text or "")
        if not m or not m.group(1).strip():
            return None
        slider = 100 if _Q.search(text) else 10 if _FAST.search(text) else 50
        return {"id": "img", "brief": m.group(1).strip(), "slider": slider, "steps": [{"op": "generate_image", "args": {"path": m.group(1).strip()[:80]}}]}

    def irreversible(self, card):
        return False

    def preview(self, card):
        mode = "качество" if card["slider"] >= 67 else "быстро" if card["slider"] <= 33 else "баланс"
        return "Сгенерирую изображение (режим: %s): «%s». Модель поднимется на видеокарту на время генерации и вернётся в оперативку." % (mode, card["brief"][:200])

    def _post(self, path, body, timeout=1900):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"}, "POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode())
            except ValueError:
                return e.code, {"error": "http"}
        except OSError as e:
            return 0, {"error": "unreachable", "message": str(e)}

    async def execute(self, card):
        import asyncio
        loop = asyncio.get_running_loop()
        code, r = await loop.run_in_executor(None, lambda: self.post("/generate", {"brief": card["brief"], "slider": card["slider"]}))
        return self.describe(code, r)

    @staticmethod
    def describe(code, r):
        if code == 200:
            b = r["images"][r["best"]]
            return "Мессир, готово: %s (SHA %s…), квитанция %s." % (b["url"], b["sha256"][:12], r["receipt_url"])
        if code == 403:
            return "Мессир, это я делать не буду: %s" % r.get("reason", "жёсткое правило")
        if code == 0:
            return "Мессир, сервис графики не отвечает (%s). Картинка не создана." % r.get("message", "")
        return "Мессир, не вышло (%s): %s." % (code, r.get("message") or r.get("error") or "ошибка")
