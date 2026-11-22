"""netio: минимальный asyncio-HTTP (stdlib): клиент (закрытие сокета = отмена генерации в апстриме) и сервер."""
import asyncio
import json
from urllib.parse import urlparse


class UpstreamError(Exception):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


async def open_request(method, url, body=None, timeout=10.0, headers=None):
    """-> (status, headers(lower), reader, writer). Соединение закрывает вызывающий."""
    u = urlparse(url)
    reader, writer = await asyncio.wait_for(asyncio.open_connection(u.hostname, u.port or 80), timeout)
    data = b"" if body is None else json.dumps(body, ensure_ascii=False).encode()
    h = {"Host": "%s:%s" % (u.hostname, u.port or 80), "Connection": "close", "Accept": "*/*", "Content-Length": str(len(data))}
    if body is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    path = (u.path or "/") + ("?" + u.query if u.query else "")
    writer.write(("%s %s HTTP/1.1\r\n" % (method, path) + "".join("%s: %s\r\n" % kv for kv in h.items()) + "\r\n").encode() + data)
    try:
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout)
        status = int(line.decode("latin1").split(" ", 2)[1])
        hdrs = {}
        while True:
            l = await asyncio.wait_for(reader.readline(), timeout)
            if l in (b"\r\n", b"\n", b""):
                break
            k, _, v = l.decode("latin1").partition(":")
            hdrs[k.strip().lower()] = v.strip()
    except BaseException:
        writer.close()
        raise
    return status, hdrs, reader, writer


async def _chunks(reader, hdrs):
    if hdrs.get("transfer-encoding", "").lower() == "chunked":
        while True:
            szl = await reader.readline()
            if not szl:
                return
            try:
                n = int(szl.split(b";")[0].strip() or b"0", 16)
            except ValueError:
                return
            if n == 0:
                return
            data = await reader.readexactly(n)
            await reader.readexactly(2)
            yield data
    elif "content-length" in hdrs:
        left = int(hdrs["content-length"])
        while left > 0:
            data = await reader.read(min(65536, left))
            if not data:
                return
            left -= len(data)
            yield data
    else:
        while True:
            data = await reader.read(65536)
            if not data:
                return
            yield data


async def read_body(reader, hdrs, limit=4_000_000):
    out = b""
    async for c in _chunks(reader, hdrs):
        out += c
        if len(out) > limit:
            break
    return out


async def iter_sse_data(reader, hdrs):
    buf = b""
    async for c in _chunks(reader, hdrs):
        buf += c
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if line.startswith(b"data:"):
                yield line[5:].strip().decode("utf-8", "replace")


async def json_call(method, url, body=None, timeout=10.0, headers=None):
    """-> (status, obj|None). Сетевые исключения пробрасываются."""
    status, hdrs, reader, writer = await open_request(method, url, body, timeout, headers)
    try:
        raw = await asyncio.wait_for(read_body(reader, hdrs), timeout)
    finally:
        writer.close()
    try:
        return status, json.loads(raw or b"null")
    except ValueError:
        return status, None


# ---------------- сервер ----------------
async def read_request(reader):
    line = await reader.readline()
    if not line:
        return None
    method, target, _ = line.decode("latin1").split(" ", 2)
    hdrs = {}
    while True:
        h = await reader.readline()
        if h in (b"\r\n", b"\n", b""):
            break
        k, _, v = h.decode("latin1").partition(":")
        hdrs[k.strip().lower()] = v.strip()
    n = int(hdrs.get("content-length", "0") or 0)
    body = await reader.readexactly(n) if n else b""
    return method, target, hdrs, body


CORS = "Access-Control-Allow-Origin: *\r\nAccess-Control-Allow-Headers: *\r\nAccess-Control-Allow-Methods: GET, POST, OPTIONS\r\n"


async def send_json(writer, code, obj):
    b = json.dumps(obj, ensure_ascii=False).encode()
    writer.write(("HTTP/1.1 %d X\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: %d\r\n%sConnection: close\r\n\r\n" % (code, len(b), CORS)).encode() + b)
    await writer.drain()


async def send_sse_head(writer):
    writer.write(("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream; charset=utf-8\r\nCache-Control: no-cache\r\nX-Accel-Buffering: no\r\n%sConnection: close\r\n\r\n" % CORS).encode())
    await writer.drain()


def sse(event, obj):
    """Именованное SSE-событие (служебное: nox_phase / nox_meta)."""
    return ("event: %s\ndata: %s\n\n" % (event, json.dumps(obj, ensure_ascii=False))).encode()


def sse_data(obj):
    return ("data: %s\n\n" % (obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False))).encode()
