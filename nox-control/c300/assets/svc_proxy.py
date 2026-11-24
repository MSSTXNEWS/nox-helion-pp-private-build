"""NOX · общий обратный прокси /svc/<имя>/ для встроенных сервисов (HTTP + WebSocket). Реестр: svc_registry.json рядом.
mode=base: приложение само знает префикс /svc/<имя> (путь не меняется); mode=strip: префикс срезается."""
import socket, select, json, os, re, time, threading
_DIR = os.path.dirname(os.path.abspath(__file__))
_REG = os.path.join(_DIR, "svc_registry.json")
_cache = {"m": 0, "d": {}}
_DROP = (b"x-frame-options", b"content-security-policy", b"content-security-policy-report-only")
def registry():
    try:
        m = os.stat(_REG).st_mtime
        if m != _cache["m"]:
            _cache["d"] = json.load(open(_REG, encoding="utf-8")); _cache["m"] = m
    except Exception:
        pass
    return _cache["d"]
def _up(port):
    try:
        s = socket.create_connection(("127.0.0.1", int(port)), timeout=0.4); s.close(); return True
    except OSError:
        return False
def status():
    return {"ok": True, "ts": int(time.time()), "services": {k: dict(v, up=_up(v["port"])) for k, v in registry().items()}}
def _j(h, code, obj):
    b = json.dumps(obj, ensure_ascii=False).encode()
    h.send_response(code); h.send_header("Content-Type", "application/json; charset=utf-8"); h.send_header("Content-Length", str(len(b))); h.send_header("Cache-Control", "no-store"); h.end_headers()
    if h.command != "HEAD": h.wfile.write(b)
def handle(h, method):
    raw = h.path; p = raw.split("?")[0]
    reg = registry()
    if p == "/svc/_status": _j(h, 200, status()); return True
    name = None; upath = None
    m = re.match(r"^/svc/([a-z0-9_-]+)(/.*)?$", p)
    if m and m.group(1) in reg:
        name = m.group(1); rest = m.group(2)
        if rest is None:
            h.send_response(302); h.send_header("Location", "/svc/%s/" % name); h.send_header("Content-Length", "0"); h.end_headers(); return True
        qs = raw[len(p):]
        upath = (raw if reg[name].get("mode") == "base" else (rest or "/") + qs)
    else:
        for k, v in reg.items():  # абсолютные пути приложений без поддержки подпути
            for pre in v.get("alias", []):
                if p == pre or p.startswith(pre.rstrip("/") + "/"):
                    name = k; upath = raw; break
            if name: break
    if not name: return False
    _proxy(h, name, upath, reg[name])
    return True
def _proxy(h, name, upath, spec):
    try:
        up = socket.create_connection(("127.0.0.1", int(spec["port"])), timeout=5)
    except OSError as e:
        _j(h, 502, {"ok": False, "error": "%s недоступен: %s" % (spec.get("title", name), e)}); return
    up.settimeout(None)
    conn = h.headers.get("Connection", "").lower(); upg = "upgrade" in conn
    host = h.headers.get("Host", "127.0.0.1")
    lines = ["%s %s HTTP/1.1" % (h.command, upath), "Host: " + host]
    for k, v in h.headers.items():
        kl = k.lower()
        if kl in ("host", "connection", "proxy-connection", "keep-alive", "x-forwarded-for", "x-forwarded-prefix", "x-forwarded-host", "x-forwarded-proto"): continue
        lines.append("%s: %s" % (k, v))
    lines += ["Connection: " + ("Upgrade" if upg else "close"), "X-Forwarded-Host: " + host, "X-Forwarded-Proto: http", "X-Forwarded-Prefix: /svc/" + name]
    up.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1", "replace"))
    n = int(h.headers.get("Content-Length", "0") or 0)
    while n > 0:
        ch = h.rfile.read(min(65536, n))
        if not ch: break
        up.sendall(ch); n -= len(ch)
    h.close_connection = True
    try:
        if upg:
            cs = h.connection; cs.setblocking(True); socks = [cs, up]
            while True:
                r, _, _ = select.select(socks, [], [], 120)
                if not r: break
                dead = False
                for s in r:
                    d = s.recv(65536)
                    if not d: dead = True; break
                    (up if s is cs else cs).sendall(d)
                if dead: break
        else:
            buf = b""
            while b"\r\n\r\n" not in buf:
                d = up.recv(65536)
                if not d: break
                buf += d
            if b"\r\n\r\n" not in buf:
                _j(h, 502, {"ok": False, "error": "пустой ответ сервиса"}); return
            head, body = buf.split(b"\r\n\r\n", 1)
            hl = head.split(b"\r\n"); out = [hl[0]] + [l for l in hl[1:] if l.split(b":")[0].strip().lower() not in _DROP]
            h.wfile.write(b"\r\n".join(out) + b"\r\n\r\n" + body); h.wfile.flush()
            while True:
                d = up.recv(65536)
                if not d: break
                h.wfile.write(d); h.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        try: up.close()
        except Exception: pass
def install(cls):
    """Добавляет методы PUT/DELETE/PATCH/OPTIONS для /svc/*."""
    def mk(meth):
        def f(self):
            if handle(self, meth): return
            self.send_response(405); self.send_header("Content-Length", "0"); self.end_headers()
        return f
    for m in ("PUT", "DELETE", "PATCH", "OPTIONS"):
        if not hasattr(cls, "do_" + m): setattr(cls, "do_" + m, mk(m))
