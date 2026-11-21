"""events_bus: локальная шина событий (JSONL) для анимаций веба + подписка long-poll.

Строка файла: {"seq": N, "ts": epoch, "type": "memory.found", "source": "...", "data": {...}}.
Запись: дописывание с блокировкой flock (несколько процессов-писателей безопасны на одной машине).
Подписка: poll(since_seq, types, timeout) ждёт новые события и возвращает их пачкой
{"events": [...], "last_seq": N, "timeout": bool}. HTTP: GET /events?since=N&timeout=25&types=a,b (serve()).
Ротация: при превышении max_bytes файл переименовывается в <file>.1 (прежний .1 затирается), номер seq продолжается.
Реальные события: memory.found (память найдена), mode.changed (режим сменён), reply.started (ответ начался),
reply.finished, memory.changed. Другие типы тоже допустимы.
"""
import json
import os
import threading
import time

try:
    import fcntl
except ImportError:   # не POSIX
    fcntl = None

KNOWN_TYPES = ("memory.found", "mode.changed", "reply.started", "reply.finished", "memory.changed", "bus.rotated")


class EventBus:
    def __init__(self, path, max_bytes=5 * 1024 * 1024, clock=time.time):
        self.path, self.max_bytes, self.clock = path, max_bytes, clock
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        self._mu = threading.Lock()

    # --- запись ---
    def _last_seq(self, f):
        f.seek(0, os.SEEK_END)
        size = f.tell()
        back = min(size, 65536)
        f.seek(size - back)
        for line in reversed(f.read().decode("utf-8", "replace").splitlines()):
            try:
                return int(json.loads(line)["seq"])
            except (ValueError, KeyError, TypeError):
                continue
        return 0

    def publish(self, type_, data=None, source=None):
        if not type_ or not isinstance(type_, str):
            raise ValueError("type обязателен")
        with self._mu, open(self.path, "ab+") as f:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_EX)
            try:
                seq = self._last_seq(f)
                if f.tell() > self.max_bytes:
                    f.seek(0)
                    old = f.read()
                    with open(self.path + ".1", "wb") as g:
                        g.write(old)
                    f.truncate(0)
                    seq += 1
                    f.write((json.dumps({"seq": seq, "ts": self.clock(), "type": "bus.rotated", "source": "bus", "data": {}},
                                        ensure_ascii=False) + "\n").encode())
                seq += 1
                ev = {"seq": seq, "ts": self.clock(), "type": type_, "source": source, "data": data or {}}
                f.write((json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8"))
                f.flush()
            finally:
                if fcntl:
                    fcntl.flock(f, fcntl.LOCK_UN)
        return ev

    # удобные обёртки
    def memory_found(self, refs, query="", turn_id=None, source="memory"):
        return self.publish("memory.found", {"refs": list(refs), "count": len(refs), "query": query, "turn_id": turn_id}, source)

    def mode_changed(self, old, new, reason=None, source="mode"):
        return self.publish("mode.changed", {"from": old, "to": new, "reason": reason}, source)

    def reply_started(self, turn_id, source="chat"):
        return self.publish("reply.started", {"turn_id": turn_id}, source)

    def reply_finished(self, turn_id, tokens=None, source="chat"):
        return self.publish("reply.finished", {"turn_id": turn_id, "tokens": tokens}, source)

    # --- чтение ---
    def read(self, since_seq=0, types=None, limit=200):
        """События с seq > since_seq (по порядку). Битые строки пропускаются."""
        out = []
        if not os.path.isfile(self.path):
            return out
        with open(self.path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                    if ev["seq"] <= since_seq:
                        continue
                except (ValueError, KeyError, TypeError):
                    continue
                if types and ev.get("type") not in types:
                    continue
                out.append(ev)
                if len(out) >= limit:
                    break
        return out

    def latest_seq(self):
        if not os.path.isfile(self.path):
            return 0
        with open(self.path, "rb") as f:
            return self._last_seq(f)

    def poll(self, since_seq=None, types=None, timeout=25.0, limit=200, interval=0.1):
        """Long-poll. since_seq=None -> только будущие события (с текущего конца)."""
        if since_seq is None:
            since_seq = self.latest_seq()
        deadline = self.clock() + timeout
        while True:
            evs = self.read(since_seq, types, limit)
            if evs:
                return {"events": evs, "last_seq": evs[-1]["seq"], "timeout": False}
            if self.clock() >= deadline:
                return {"events": [], "last_seq": max(since_seq, self.latest_seq()), "timeout": True}
            time.sleep(interval)


def serve(bus, host="127.0.0.1", port=8789, max_timeout=30.0):
    """GET /events?since=N&timeout=S&types=a,b -> JSON poll(). since не указан - только новые."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import parse_qs, urlparse

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            u = urlparse(self.path)
            if u.path != "/events":
                self.send_response(404); self.end_headers(); return
            q = parse_qs(u.query)
            try:
                since = int(q["since"][0]) if "since" in q else None
                timeout = min(float(q.get("timeout", ["25"])[0]), max_timeout)
            except ValueError:
                self.send_response(400); self.end_headers(); return
            types = [t for t in q.get("types", [""])[0].split(",") if t] or None
            b = json.dumps(bus.poll(since, types, timeout), ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def log_message(self, *a):
            pass

    return ThreadingHTTPServer((host, port), H)
