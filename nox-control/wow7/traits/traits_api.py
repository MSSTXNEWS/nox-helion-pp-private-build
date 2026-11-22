"""traits_api: JSON-API ползунков для веба «Резонанс» (stdlib). handle() - чистая функция, serve() - http.server.

GET  /api/traits               -> список ползунков, карточки предложений, оси PER
GET  /api/traits/<id>/why      -> последние причины изменений
POST /api/traits/action        -> {"action": set_value|set_mode|approve_change|reject_change|proposal|open|archive|undo|rollback|autonomy, ...}
Только владелец: заголовок X-NOX-Token == env NOX_TRAITS_TOKEN (POST без заданного токена отклоняется).
"""
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


def _auth(token, headers, need):
    if not token:
        return not need
    return hmac.compare_digest(str(headers.get("X-NOX-Token", "")), token)


def handle(tr, method, path, body=None, headers=None, dev=None, per=None, token=None):
    """-> (http_status, dict)."""
    headers, body = headers or {}, body or {}
    token = token if token is not None else os.environ.get("NOX_TRAITS_TOKEN", "")
    path = path.split("?")[0].rstrip("/")
    try:
        if method == "GET" and path == "/api/traits":
            if not _auth(token, headers, False):
                return 401, {"error": "нужен токен владельца"}
            return 200, tr.api_list(dev, per)
        if method == "GET" and path.startswith("/api/traits/") and path.endswith("/why"):
            if not _auth(token, headers, False):
                return 401, {"error": "нужен токен владельца"}
            return 200, {"why": tr.why(path[len("/api/traits/"):-len("/why")])}
        if method == "POST" and path == "/api/traits/action":
            if not token:
                return 403, {"error": "NOX_TRAITS_TOKEN не задан: изменения запрещены"}
            if not _auth(token, headers, True):
                return 401, {"error": "нужен токен владельца"}
            a, tid = body.get("action"), body.get("id")
            if a == "set_value":
                tr.set_value(tid, body["value"], body.get("reason") or "владелец поставил значение", bool(body.get("lock")))
            elif a == "set_mode":
                tr.set_mode(tid, body["mode"])
            elif a == "approve_change":
                tr.approve_change(tid)
            elif a == "reject_change":
                tr.reject_change(tid)
            elif a == "proposal":
                tr.decide_proposal(body["id"], body["decision"])
            elif a == "open":
                tr.open_trait(tid)
            elif a == "archive":
                tr.archive(tid)
            elif a == "undo":
                tr.undo_last(tid)
            elif a == "rollback":
                tr.rollback(body.get("label"))
            elif a == "autonomy":
                tr.autonomy = bool(body.get("on"))
                tr.save()
            else:
                return 400, {"error": "неизвестное действие"}
            return 200, tr.api_list(dev, per)
        return 404, {"error": "нет такого маршрута"}
    except (KeyError, ValueError, TypeError) as e:
        return 400, {"error": "%s: %s" % (type(e).__name__, e)}


def serve(tr, dev=None, per=None, host="127.0.0.1", port=8091):
    class H(BaseHTTPRequestHandler):
        def _go(self, method):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            except ValueError:
                body = None
            code, out = (400, {"error": "тело не JSON"}) if body is None else handle(tr, method, self.path, body, dict(self.headers), dev, per)
            data = json.dumps(out, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._go("GET")

        def do_POST(self):
            self._go("POST")

        def log_message(self, *a):
            pass

    HTTPServer((host, port), H).serve_forever()
