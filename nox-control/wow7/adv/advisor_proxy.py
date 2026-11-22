"""ADV-04: прокси шлюза /v1/advisors/* -> хаб советников (advisor_hub serve, 127.0.0.1:8095). Подключается из glm53/gateway.py (ADV/gateway_adv.diff).

handle(h, method, path, raw) -> True, если путь /v1/advisors/* обработан (ответ клиенту отдан), False - путь не наш, шлюз продолжает как обычно.
Разрешено: GET /v1/advisors/status; POST /v1/advisors/ask, /v1/advisors/command. Остальное -> 404. Тело до 32 КБ. Хаб лежит -> 503 {"ok": false, "error": "advisor_hub_down"}:
отката на «старый путь» нет (советники необязательны), чат не затрагивается. Токен хаба NOX_ADV_TOKEN передаётся как Bearer; клиентский Authorization не пробрасывается.
Флаг NOX_ADV=0 выключает прокси (404). env: NOX_ADV_URL (по умолчанию http://127.0.0.1:8095), NOX_ADV_PROXY_TIMEOUT_S (45; ask ждёт советников до дедлайна хаба)."""
import http.client
import json
import os
import socket
from urllib.parse import urlsplit

PREFIX = "/v1/advisors/"
ALLOWED = {("GET", "/v1/advisors/status"), ("POST", "/v1/advisors/ask"), ("POST", "/v1/advisors/command")}
MAX_BODY = 32768


def hub_url():
    return os.environ.get("NOX_ADV_URL") or "http://127.0.0.1:%s" % os.environ.get("NOX_ADV_PORT", "8095")


def _reply(h, code, obj):
    b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(b)))
    h.end_headers()
    h.wfile.write(b)


def handle(h, method, path, raw=b""):
    p = path.split("?")[0].rstrip("/")
    if not p.startswith(PREFIX.rstrip("/")):
        return False
    if os.environ.get("NOX_ADV") == "0":
        _reply(h, 404, {"ok": False, "error": "advisors_disabled"})
        return True
    if (method, p) not in ALLOWED:
        _reply(h, 404, {"ok": False, "error": "not_found"})
        return True
    if len(raw or b"") > MAX_BODY:
        _reply(h, 413, {"ok": False, "error": "too_large"})
        return True
    u = urlsplit(hub_url())
    timeout = float(os.environ.get("NOX_ADV_PROXY_TIMEOUT_S", "45"))
    try:
        c = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)
        hdrs = {"Content-Type": "application/json"}
        tok = os.environ.get("NOX_ADV_TOKEN")
        if tok:
            hdrs["Authorization"] = "Bearer " + tok
        if method == "POST":
            hdrs["Content-Length"] = str(len(raw or b""))
        c.request(method, p, body=(raw or b"{}") if method == "POST" else None, headers=hdrs)
        r = c.getresponse()
        data = r.read(1 << 20)
        code, ctype = r.status, r.getheader("Content-Type") or "application/json; charset=utf-8"
        c.close()
    except (OSError, socket.timeout, http.client.HTTPException):
        _reply(h, 503, {"ok": False, "error": "advisor_hub_down", "hint": "advisor_hub.py serve на %s не отвечает" % hub_url()})
        return True
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(data)))
    h.end_headers()
    h.wfile.write(data)
    return True
