"""core_proxy: проксирование чата шлюза в NOX CORE (флаг NOX_CORE=1), потоково и без правки тела (BRAIN/gateway_core.md).
Вызывается из glm53/gateway.py (do_POST): proxy(handler, path, raw_body) -> True если ответ отдан клиенту (в т.ч. оборван клиентом),
False если CORE недоступен ДО начала ответа (connect refused/таймаут подключения) - тогда шлюз идёт старым путём (авто-откат)."""
import http.client
import os
import socket
from urllib.parse import urlsplit

PASS_HDR = ("Content-Type", "Authorization", "X-NOX-Eval", "Last-Event-ID", "Accept")
RESP_HDR = ("Content-Type", "Cache-Control", "X-NOX-Request-Id", "X-Accel-Buffering")


def core_url():
    return os.environ.get("NOX_CORE_URL", "http://127.0.0.1:%s" % os.environ.get("NOX_CORE_PORT", "8090"))


def proxy(h, path, raw, connect_timeout=3.0, read_timeout=1800.0):
    u = urlsplit(core_url())
    try:
        c = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=connect_timeout)
        c.connect()
        c.sock.settimeout(read_timeout)
    except (OSError, socket.timeout):
        return False
    try:
        hdrs = {k: h.headers[k] for k in PASS_HDR if h.headers.get(k)}
        hdrs["Content-Length"] = str(len(raw))
        c.request("POST", path, body=raw, headers=hdrs)
        r = c.getresponse()
    except (OSError, http.client.HTTPException):
        c.close()
        return False                       # ничего клиенту ещё не отдано - можно откатиться на старый путь
    try:
        h.send_response(r.status)
        for k in RESP_HDR:
            v = r.getheader(k)
            if v:
                h.send_header(k, v)
        h.send_header("Connection", "close")
        h.end_headers()
        while True:
            chunk = r.read1(8192) if hasattr(r, "read1") else r.read(8192)
            if not chunk:
                break
            h.wfile.write(chunk)
            h.wfile.flush()
    except (BrokenPipeError, ConnectionError, OSError):
        pass                               # клиент ушёл: закрываем апстрим, CORE увидит разрыв
    finally:
        c.close()
    return True
