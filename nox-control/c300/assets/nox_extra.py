"""NOX · доп. маршруты веба: вход по паролю для внешнего доступа, /cal (календарь, JSON), /search (Meilisearch)."""
import os, json, time, base64, hmac, uuid, threading, urllib.request, urllib.parse
SECRETS = "/workspace/nox/secrets"; CAL = "/workspace/nox/state/cal_events.json"; OFF = "/workspace/nox/state/web_auth_off"
_lock = threading.Lock()
def _cred():
    try: return open(SECRETS + "/web_basic_auth.txt").read().strip()
    except Exception: return None
def _external(h):
    ip = h.client_address[0]
    if ip not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"): return True
    for k in ("CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP", "Forwarded"):
        v = h.headers.get(k)
        if v and v.split(",")[0].strip() not in ("127.0.0.1", "::1", ""): return True
    return False
def _send(h, code, obj, extra=None):
    b = json.dumps(obj, ensure_ascii=False).encode()
    h.send_response(code); h.send_header("Content-Type", "application/json; charset=utf-8"); h.send_header("Content-Length", str(len(b))); h.send_header("Cache-Control", "no-store")
    for k, v in (extra or {}).items(): h.send_header(k, v)
    h.end_headers()
    if h.command != "HEAD": h.wfile.write(b)
def guard(h):
    """True = запрос отклонён (ответ уже отправлен)."""
    p = h.path.split("?")[0]
    if os.path.exists(OFF) or not _external(h): return False
    if p.endswith("manifest.json") or "/icons/" in p: return False
    cred = _cred()
    if not cred: return False
    a = h.headers.get("Authorization", "")
    if a.startswith("Basic "):
        try:
            if hmac.compare_digest(base64.b64decode(a[6:]).decode("utf-8", "replace"), cred): return False
        except Exception: pass
    b = b"Auth required"
    h.send_response(401); h.send_header("WWW-Authenticate", 'Basic realm="NOX HELION", charset="UTF-8"'); h.send_header("Content-Length", str(len(b))); h.send_header("Content-Type", "text/plain"); h.end_headers()
    if h.command != "HEAD": h.wfile.write(b)
    return True
def _load():
    try: return json.load(open(CAL, encoding="utf-8"))
    except Exception: return []
def _save(d):
    os.makedirs(os.path.dirname(CAL), exist_ok=True); tmp = CAL + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, CAL)
def _body(h):
    n = int(h.headers.get("Content-Length", "0") or 0)
    try: return json.loads(h.rfile.read(n) or b"{}")
    except Exception: return {}
def _meili(path, body=None, method=None):
    key = open(SECRETS + "/meili_key.txt").read().strip()
    rq = urllib.request.Request("http://127.0.0.1:7700" + path, data=json.dumps(body).encode() if body is not None else None, method=method or ("POST" if body is not None else "GET"), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(rq, timeout=5))
def handle(h, method):
    if guard(h): return True
    raw = h.path; p = raw.split("?")[0]
    if p == "/search":
        q = urllib.parse.parse_qs(raw[len(p) + 1:]).get("q", [""])[0]
        try:
            r = _meili("/indexes/nox/search", {"q": q, "limit": 12, "attributesToCrop": ["text"], "cropLength": 12, "attributesToHighlight": []})
            _send(h, 200, {"ok": True, "hits": [{k: x.get(k) for k in ("kind", "title", "url", "text")} for x in r.get("hits", [])]})
        except Exception as e: _send(h, 502, {"ok": False, "error": "Meilisearch недоступен: %s" % e})
        return True
    if p == "/cal/events" or p.startswith("/cal/events/"):
        with _lock:
            d = _load()
            if p == "/cal/events" and method == "GET": _send(h, 200, d); return True
            if p == "/cal/events" and method == "POST":
                b = _body(h)
                if not b.get("title") or not b.get("start"): _send(h, 400, {"ok": False, "error": "нужны title и start"}); return True
                e = {"id": uuid.uuid4().hex[:10], "title": str(b["title"])[:200], "start": b["start"], "end": b.get("end"), "allDay": bool(b.get("allDay")), "notes": str(b.get("notes", ""))[:2000]}
                d.append(e); _save(d); _send(h, 200, {"ok": True, "event": e}); return True
            eid = p.rsplit("/", 1)[1]
            if method == "DELETE":
                n = [x for x in d if x.get("id") != eid]; _save(n); _send(h, 200, {"ok": True, "deleted": len(d) - len(n)}); return True
            if method in ("PUT", "PATCH"):
                b = _body(h)
                for x in d:
                    if x.get("id") == eid: x.update({k: b[k] for k in ("title", "start", "end", "allDay", "notes") if k in b}); _save(d); _send(h, 200, {"ok": True, "event": x}); return True
                _send(h, 404, {"ok": False}); return True
        _send(h, 405, {"ok": False}); return True
    return False
