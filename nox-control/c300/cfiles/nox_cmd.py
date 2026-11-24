"""NOX командная шина: POST /api/cmd (белый список из qa/registry.json) и /api/cmd/confirm (одноразовый токен 60 с)."""
import json, os, secrets, time, urllib.request, urllib.error
REG_PATH = "/workspace/nox/web/site/qa/registry.json"
LOG = "/workspace/nox/state/cmd_log.jsonl"
BASE = "http://127.0.0.1:8091"
_tokens = {}  # token -> (name, expires)

def _reg():
    with open(REG_PATH, encoding="utf-8") as f:
        return json.load(f)

def _log(rec):
    rec["ts"] = time.strftime("%FT%T")
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass

def _send(h, code, obj):
    data = json.dumps(obj, ensure_ascii=False).encode()
    h.send_response(code)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(data)))
    h.send_header("Cache-Control", "no-cache")
    h.end_headers()
    h.wfile.write(data)

def _read_json(raw):
    try:
        return json.loads((raw or b"{}").decode("utf-8") or "{}")
    except Exception:
        return None

def _check_params(schema, params):
    if not isinstance(params, dict):
        return "params должен быть объектом"
    for k in (schema or {}).get("required", []):
        if k not in params:
            return "нет параметра: " + k
    return None

def _exec(cmd, params):
    if not cmd.get("endpoint"):
        return 501, {"ok": False, "error": "команда зарегистрирована, но бэкенд не подключён"}
    body = None
    url = BASE + cmd["endpoint"]
    if cmd["method"] == "GET":
        if params:
            import urllib.parse
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if isinstance(v, (str, int, float))})
    else:
        body = json.dumps(params or {}).encode()
    rq = urllib.request.Request(url, data=body, method=cmd["method"], headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(rq, timeout=120) as r:
            txt = r.read().decode("utf-8", "replace")
            return r.status, {"ok": True, "result": txt[:20000]}
    except urllib.error.HTTPError as e:
        return e.code, {"ok": False, "error": "HTTP %d" % e.code}
    except Exception as e:
        return 502, {"ok": False, "error": str(e)[:200]}

def handle(h, path, raw):
    reg = _reg()
    cmds = reg.get("commands", {})
    body = _read_json(raw)
    if body is None:
        return _send(h, 400, {"ok": False, "error": "нужен JSON"})
    if path == "/api/cmd/confirm":
        name = body.get("name")
        cmd = cmds.get(name)
        if not cmd or not cmd.get("confirm"):
            return _send(h, 400, {"ok": False, "error": "команда не требует подтверждения"})
        if body.get("clicked") is not True:
            return _send(h, 400, {"ok": False, "error": "подтверждение только после клика в диалоге"})
        tok = secrets.token_urlsafe(24)
        _tokens[tok] = (name, time.time() + 60)
        _log({"cmd": name, "event": "confirm_issued"})
        return _send(h, 200, {"ok": True, "confirm_token": tok, "ttl": 60})
    name = body.get("name")
    cmd = cmds.get(name)
    if not cmd:
        _log({"cmd": str(name)[:80], "event": "rejected_unknown"})
        return _send(h, 404, {"ok": False, "error": "нет в белом списке"})
    params = body.get("params") or {}
    err = _check_params(cmd.get("params"), params)
    if err:
        return _send(h, 400, {"ok": False, "error": err})
    if cmd.get("confirm"):
        tok = body.get("confirm_token")
        ent = _tokens.pop(tok, None) if tok else None
        if not ent or ent[0] != name or ent[1] < time.time():
            _log({"cmd": name, "event": "rejected_no_token"})
            return _send(h, 403, {"ok": False, "error": "нужен confirm_token (получить после подтверждения)", "need_confirm": True})
    code, res = _exec(cmd, params)
    _log({"cmd": name, "event": "run", "status": code, "ok": res.get("ok")})
    return _send(h, code, res)
