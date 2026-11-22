"""RTE: минимальный asyncio-HTTP клиент (stdlib). Нужен, чтобы закрытие сокета = отмена генерации в апстриме."""
import asyncio, json
from urllib.parse import urlparse


async def open_request(method, url, body=None, timeout=10.0, headers=None):
    """-> (status, headers(dict lower), reader, writer). Соединение закрывает вызывающий (writer.close())."""
    u = urlparse(url)
    reader, writer = await asyncio.wait_for(asyncio.open_connection(u.hostname, u.port or 80), timeout)
    data = b"" if body is None else json.dumps(body, ensure_ascii=False).encode()
    h = {"Host": "%s:%s" % (u.hostname, u.port or 80), "Connection": "close", "Accept": "*/*", "Content-Length": str(len(data))}
    if body is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    path = (u.path or "/") + ("?" + u.query if u.query else "")
    writer.write(("%s %s HTTP/1.1\r\n" % (method, path) + "".join("%s: %s\r\n" % kv for kv in h.items()) + "\r\n").encode() + data)
    await writer.drain()
    try:
        status_line = await asyncio.wait_for(reader.readline(), timeout)
        parts = status_line.decode("latin1").split(" ", 2)
        status = int(parts[1])
        hdrs = {}
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout)
            if line in (b"\r\n", b"\n", b""):
                break
            k, _, v = line.decode("latin1").partition(":")
            hdrs[k.strip().lower()] = v.strip()
    except BaseException:
        writer.close()
        raise
    return status, hdrs, reader, writer


async def read_body(reader, hdrs, limit=4_000_000):
    out = b""
    async for chunk in _chunks(reader, hdrs):
        out += chunk
        if len(out) > limit:
            break
    return out


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


async def iter_sse_data(reader, hdrs):
    """Отдаёт строки data: из SSE (разбирает chunked)."""
    buf = b""
    async for chunk in _chunks(reader, hdrs):
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if line.startswith(b"data:"):
                yield line[5:].strip().decode("utf-8", "replace")


async def json_call(method, url, body=None, timeout=10.0):
    """-> (status, obj|None). Исключения сети пробрасываются."""
    status, hdrs, reader, writer = await open_request(method, url, body, timeout)
    try:
        raw = await asyncio.wait_for(read_body(reader, hdrs), timeout)
    finally:
        writer.close()
    try:
        return status, json.loads(raw or b"null")
    except ValueError:
        return status, None
