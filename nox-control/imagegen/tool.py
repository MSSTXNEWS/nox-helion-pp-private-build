"""Инструмент generate_image для агентного цикла NOX: OpenAI-tools JSON-схема + вызов сервиса (127.0.0.1:8096).

    from tool import TOOLS, run_tool_call
    # tools=TOOLS -> в chat/completions; на tool_call: result = run_tool_call(call)  (dict -> content сообщения role=tool)
"""
import base64, json, os, sys, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE = os.environ.get("NOX_IMG_URL", "http://127.0.0.1:8096")
OUT_DIR = os.environ.get("NOX_IMG_OUT_DIR", os.path.join(os.path.expanduser("~"), ".nox", "imagegen", "out"))

TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": ("Сгенерировать изображение по текстовому описанию на сервере (FLUX.1-schnell или SDXL). Задачи идут по очереди, "
                        "одна картинка занимает от десятков секунд до нескольких минут. Пиши prompt на английском, конкретно: "
                        "субъект, действие, окружение, стиль, свет, ракурс. Возвращает путь к PNG и метаданные. "
                        "Запрещено сервисом: сексуальные изображения несовершеннолетних и откровенные изображения реальных людей без согласия."),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Описание картинки (англ. работает лучше), до 4000 символов"},
                "negative": {"type": "string", "description": "Чего не должно быть (только SDXL; FLUX игнорирует)"},
                "width": {"type": "integer", "minimum": 256, "maximum": 2048, "description": "Ширина, кратна 16 (по умолчанию 1024)"},
                "height": {"type": "integer", "minimum": 256, "maximum": 2048, "description": "Высота, кратна 16 (по умолчанию 1024); ширина*высота <= 1536*1536"},
                "steps": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Шаги (FLUX schnell 4, SDXL 30 по умолчанию)"},
                "seed": {"type": "integer", "minimum": 0, "description": "Зерно для воспроизводимости"},
                "model": {"type": "string", "description": "Имя модели из /health (по умолчанию FLUX.1-schnell, если установлена)"},
                "check": {"type": "boolean", "description": "Проверить результат зрением судьи (нужен NOX_VISION_URL)"},
            },
            "required": ["prompt"],
        },
    },
}
TOOLS = [TOOL_SPEC]
_FIELDS = ("prompt", "negative", "width", "height", "steps", "seed", "model")


def _post(url, body, timeout):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", "Accept": "application/json"}, "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": "http", "message": raw[:300]}


def generate_image(args, base=None, out_dir=None, timeout=1900):
    """Вызов сервиса. Возвращает dict: ok, path, meta, либо ok=False + error/reason/refused. Исключений наружу не бросает."""
    base, out_dir = base or BASE, out_dir or OUT_DIR
    if not isinstance(args, dict) or not str(args.get("prompt", "")).strip():
        return {"ok": False, "error": "bad_request", "message": "prompt обязателен"}
    body = {k: args[k] for k in _FIELDS if args.get(k) not in (None, "")}
    try:
        code, data = _post(base.rstrip("/") + "/v1/images/generate?format=json", body, timeout)
    except (urllib.error.URLError, OSError) as e:
        return {"ok": False, "error": "service_unreachable", "message": "сервис генерации не отвечает (%s): %s" % (base, e)}
    if code != 200:
        res = {"ok": False, "error": data.get("error", "http_%d" % code), "message": data.get("message") or data.get("reason"), "http": code}
        if code == 403:
            res.update(refused=True, rule=data.get("rule"), reason=data.get("reason"))
        return res
    png = base64.b64decode(data["png_base64"])
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "img_%s_%s.png" % (time.strftime("%Y%m%d_%H%M%S"), data["id"]))
    with open(path, "wb") as f:
        f.write(png)
    res = {"ok": True, "path": path, "meta": data["meta"], "bytes": len(png)}
    if args.get("check") is True:
        import judge
        v = judge.judge_image(png, body["prompt"], negative=body.get("negative", ""))
        res["judge"] = {k: v[k] for k in ("configured", "ok", "reasons")}
    return res


def run_tool_call(call, **kw):
    """call: элемент tool_calls OpenAI ({"function": {"name", "arguments": "<json>"}}). -> dict результата."""
    fn = (call or {}).get("function", {})
    if fn.get("name") != "generate_image":
        return {"ok": False, "error": "unknown_tool", "message": str(fn.get("name"))}
    raw = fn.get("arguments") or "{}"
    try:
        args = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError as e:
        return {"ok": False, "error": "bad_arguments", "message": str(e)}
    return generate_image(args, **kw)


if __name__ == "__main__":
    import sys
    print(json.dumps(generate_image({"prompt": " ".join(sys.argv[1:])}), ensure_ascii=False, indent=1))
