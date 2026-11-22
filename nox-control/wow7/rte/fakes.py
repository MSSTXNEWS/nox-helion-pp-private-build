"""Фейковые upstream для тестов RTE: имитируют llama-server/шлюз (SSE, /slots, /v1/stop) на локальном порту. Не часть продакшена."""
import asyncio, json


class FakeLLM:
    def __init__(self, tokens=12, first_delay=0.2, tok_delay=0.02, honor_disconnect=True, linger_tokens=0, intro_text="Принял, мессир, секунду.",
                 intro_delay=0.0, prefix="т"):
        self.tokens, self.first_delay, self.tok_delay = tokens, first_delay, tok_delay
        self.honor, self.linger, self.intro_text, self.intro_delay, self.prefix = honor_disconnect, linger_tokens, intro_text, intro_delay, prefix
        self.n_decoded, self.busy, self.generations, self.requests = 0, False, 0, []
        self.server, self.port, self.rid = None, 0, 0

    async def start(self):
        self.server = await asyncio.start_server(self._h, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return "http://127.0.0.1:%d" % self.port

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()

    async def _h(self, reader, writer):
        try:
            line = await reader.readline()
            method, target, _ = line.decode().split(" ", 2)
            hdrs = {}
            while True:
                h = await reader.readline()
                if h in (b"\r\n", b""):
                    break
                k, _, v = h.decode().partition(":")
                hdrs[k.strip().lower()] = v.strip()
            body = json.loads(await reader.readexactly(int(hdrs.get("content-length", "0"))) or b"null") if int(hdrs.get("content-length", "0")) else None
            path = target.split("?")[0]
            if path == "/slots":
                return await self._json(writer, 200, [{"id": 0, "is_processing": self.busy, "next_token": [{"n_decoded": self.n_decoded}]}])
            if path == "/v1/nox/stats":
                return await self._json(writer, 200, {"speed": {"deep": {"tps": 1.5}}})
            if path == "/v1/stop":
                return await self._json(writer, 200, {"stopped": True})
            if path == "/v1/chat/completions":
                self.requests.append(body)
                if not body.get("stream"):
                    await asyncio.sleep(self.intro_delay)
                    return await self._json(writer, 200, {"choices": [{"message": {"role": "assistant", "content": self.intro_text}}]})
                return await self._stream(reader, writer)
            await self._json(writer, 404, {})
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def _json(self, w, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        w.write(("HTTP/1.1 %d X\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % (code, len(b))).encode() + b)
        await w.drain()

    async def _stream(self, reader, writer):
        self.generations += 1
        self.rid += 1
        rid = "fake%d" % self.rid
        gone = asyncio.ensure_future(reader.read(1))          # EOF от клиента = разрыв
        writer.write(("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nX-NOX-Request-Id: %s\r\nConnection: close\r\n\r\n" % rid).encode())
        self.busy, self.n_decoded = True, 0
        try:
            await asyncio.sleep(self.first_delay)
            writer.write(b"data: " + json.dumps({"choices": [{"delta": {"role": "assistant", "content": ""}}], "nox": {"request_id": rid}}).encode() + b"\n\n")
            lingered = 0
            for i in range(self.tokens + self.linger):
                if gone.done():
                    if self.honor:
                        return
                    lingered += 1
                    self.n_decoded += 1
                    await asyncio.sleep(self.tok_delay)
                    continue
                self.n_decoded += 1
                writer.write(b"data: " + json.dumps({"choices": [{"delta": {"content": "%s%d " % (self.prefix, i)}}]}, ensure_ascii=False).encode() + b"\n\n")
                await writer.drain()
                await asyncio.sleep(self.tok_delay)
                if i >= self.tokens - 1 and not gone.done():
                    break
            writer.write(b"data: [DONE]\n\n")
            await writer.drain()
        except ConnectionError:
            pass
        finally:
            self.busy = False
            gone.cancel()
