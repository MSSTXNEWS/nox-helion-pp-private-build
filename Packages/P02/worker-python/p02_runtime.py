"""NOX P02 Python stdlib candidate. Owner #2 only; #6 integrates with *existing* host/DB/events.v3.
No new web engine, daemon, system install, or autonomous user actions.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import pathlib
import queue
import re
import sqlite3
import stat
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable, Iterator

MAX_FILE = 25 * 1024 * 1024
MAX_CHAT = 100 * 1024 * 1024
ALLOWED_MIME = {"application/pdf", "image/png", "image/jpeg", "text/plain"}
class _DenyRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward local prompts to a redirected remote host."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise P02Error("OLLAMA_HTTP_REDIRECT_DENIED")


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _DenyRedirect())


class P02Error(Exception):
    pass


class Cancelled(P02Error):
    pass


class OllamaClient:
    """Loopback-only Ollama. One producer per request; STOP never waits on socket reads.

    A daemon transport worker is bounded by the configured socket timeout, while the
    UI-facing iterator polls a bounded queue and responds to STOP independently.
    Closing the generator signals cancellation and closes the underlying connection.
    """
    def __init__(self, base: str = "http://127.0.0.1:11434", timeout: float = 30):
        u = urllib.parse.urlsplit(base)
        if (u.scheme != "http" or u.hostname not in ("127.0.0.1", "localhost", "::1")
                or u.username or u.password or u.path not in ("", "/") or u.query or u.fragment):
            raise ValueError("Ollama endpoint must be loopback HTTP without path, credentials or query")
        if timeout <= 0 or timeout > 600:
            raise ValueError("Timeout out of range")
        self.base = base.rstrip("/")
        self.timeout = timeout
        self._active = None
        self._cancel = None
        self._busy = False
        self._guard = threading.RLock()

    def _open(self, path: str, data: bytes | None = None):
        r = urllib.request.Request(self.base + path, data=data,
            headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
            method="POST" if data is not None else "GET")
        try:
            return _OPENER.open(r, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            detail = e.read(1024).decode("utf-8", "replace")
            raise P02Error(f"Ollama HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise P02Error(f"Ollama unavailable: {type(e).__name__}: {e}") from e

    def models(self) -> list[str]:
        with self._open("/api/tags") as r:
            raw = r.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise P02Error("Ollama model list over size limit")
        try:
            doc = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise P02Error("Invalid Ollama model list") from exc
        if not isinstance(doc, dict):
            raise P02Error("Invalid Ollama model metadata")
        models = doc.get("models")
        if not isinstance(models, list):
            raise P02Error("/api/tags returned invalid models")
        return [m["name"] for m in models if isinstance(m, dict)
                and isinstance(m.get("name"), str) and 0 < len(m["name"]) <= 256]

    def stop(self):
        """Signal the active iterator; never synchronously wait for HTTP close."""
        with self._guard:
            cancel, response = self._cancel, self._active
        if cancel is not None:
            cancel.set()
        if response is not None:
            threading.Thread(target=self._close_safely, args=(response,), daemon=True).start()

    @staticmethod
    def _close_safely(response):
        with contextlib.suppress(Exception):
            response.close()

    def stream(self, model: str, messages: list[dict], stop: threading.Event | None = None
               ) -> Iterator[dict[str, Any]]:
        if (not isinstance(model, str) or not 0 < len(model) <= 256 or
                not isinstance(messages, list) or not messages or
                any(not isinstance(m, dict) or m.get("role") not in
                    ("system", "user", "assistant", "tool") or
                    not isinstance(m.get("content"), str) for m in messages)):
            raise ValueError("Invalid Ollama model/messages")
        stop = stop if stop is not None else threading.Event()
        if stop.is_set():
            raise Cancelled("STOP before request")
        body = json.dumps({"model": model, "messages": messages, "stream": True},
            ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        cancel = threading.Event()
        with self._guard:
            if self._busy:
                raise P02Error("Another chat stream is active")
            self._busy, self._cancel = True, cancel
        received: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=32)
        finished = threading.Event()
        consumer_done = threading.Event()

        def release_if_closed():
            # The lease belongs to BOTH the transport and the UI iterator;
            # draining a buffered response is still an active chat operation.
            if not finished.is_set() or not consumer_done.is_set():
                return
            with self._guard:
                if self._cancel is cancel:
                    self._cancel, self._busy = None, False

        def emit(kind: str, item: object):
            # Bound memory even when the iterator is stopped/closed.
            while not cancel.is_set() and not stop.is_set():
                try:
                    received.put((kind, item), timeout=.05)
                    return
                except queue.Full:
                    continue

        def worker():
            response = None
            try:
                if cancel.is_set() or stop.is_set():
                    return
                response = self._open("/api/chat", body)
                with self._guard:
                    if cancel.is_set() or stop.is_set():
                        return
                    self._active = response
                done_seen = False
                for raw in response:
                    if cancel.is_set() or stop.is_set():
                        return
                    if len(raw) > 1024 * 1024:
                        raise P02Error("Overlarge Ollama event")
                    if not raw.strip():
                        continue
                    try:
                        data = json.loads(raw)
                    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                        raise P02Error("Malformed Ollama NDJSON") from exc
                    if not isinstance(data, dict):
                        raise P02Error("Ollama stream event must be an object")
                    if "error" in data:
                        raise P02Error(f"Ollama stream error: {str(data['error'])[:512]}")
                    if not isinstance(data.get("done"), bool):
                        raise P02Error("Ollama stream missing done boolean")
                    message = data.get("message", {})
                    delta = message.get("content", "") if isinstance(message, dict) else ""
                    if not isinstance(delta, str):
                        raise P02Error("Ollama stream returned non-text content")
                    emit("chunk", {"delta": delta, "done": data["done"],
                                   "reason": data.get("done_reason")})
                    if data["done"]:
                        done_seen = True
                        break
                if not done_seen and not cancel.is_set() and not stop.is_set():
                    raise P02Error("Ollama stream truncated before done=true")
            except (TimeoutError, OSError, urllib.error.URLError) as exc:
                emit("error", P02Error("Ollama streaming timeout/connection error: " +
                                        type(exc).__name__))
            except Exception as exc:
                emit("error", exc if isinstance(exc, P02Error) else
                     P02Error("Ollama transport exception: " + type(exc).__name__))
            finally:
                if response is not None:
                    self._close_safely(response)
                with self._guard:
                    if self._active is response:
                        self._active = None
                finished.set()
                release_if_closed()
                emit("end", None)

        thread = threading.Thread(target=worker, daemon=True, name="nox-p02-ollama-stream")
        thread.start()
        saw_done = False
        try:
            while True:
                if stop.is_set() or cancel.is_set():
                    raise Cancelled("STOP requested")
                try:
                    kind, payload = received.get(timeout=.05)
                except queue.Empty:
                    if finished.is_set() and received.empty():
                        break
                    continue
                if kind == "chunk":
                    if stop.is_set() or cancel.is_set():
                        raise Cancelled("STOP requested")
                    assert isinstance(payload, dict)
                    yield payload
                    if payload["done"]:
                        saw_done = True
                        break
                elif kind == "error":
                    raise payload  # type: ignore[misc]
                elif kind == "end":
                    break
            if stop.is_set() or cancel.is_set():
                raise Cancelled("STOP requested")
            if not saw_done:
                raise P02Error("Ollama stream truncated before done=true")
        finally:
            cancel.set()
            consumer_done.set()
            with self._guard:
                response = self._active
            # Only the final party to finish (socket OR consumer) clears the
            # single-chat lease. STOP of a blocked socket never releases it early.
            release_if_closed()
            if response is not None and not finished.is_set():
                threading.Thread(target=self._close_safely, args=(response,), daemon=True).start()


def _check_scope(tenant: str, user: str, chat: str):
    if any(not isinstance(x, str) or not x or len(x) > 200 for x in (tenant, user, chat)):
        raise ValueError("Missing tenant, user or chat scope")


def _safe_blob_path(root: pathlib.Path, storage: str) -> pathlib.Path:
    if not re.fullmatch(r"[0-9a-f]{32}", storage):
        raise P02Error("Invalid storage ID")
    path = root / (storage + ".blob")
    if path.is_symlink():
        raise P02Error("Symlinked attachment blocked")
    return path


class P02Store:
    """Accepts host's existing SQLite connection. No second DB or SQLite user_version mutation."""
    def __init__(self, db: sqlite3.Connection, attachment_root: str | os.PathLike,
                 *, approved_host_tables: frozenset[str] = frozenset()):
        self.db = db
        # Optional #6-approved table names allow a shared existing SQLite connection,
        # never a second history. Unknown schemas are quarantined, not guessed.
        if not isinstance(approved_host_tables, frozenset) or not all(
                isinstance(t, str) and t and len(t) <= 128 for t in approved_host_tables):
            raise TypeError('Native host approved table names required')
        self.approved_host_tables = approved_host_tables
        self.root = pathlib.Path(attachment_root).resolve()
        self.staging = self.root / "staging"
        self.blobs = self.root / "stored"
        self.staging.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.blobs.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lock = threading.RLock()

    def host_schema_inventory(self) -> tuple[str, ...]:
        """Read-only host table list for #6; never silently migrate a user's DB."""
        with self._lock:
            return tuple(sorted(row[0] for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
                if not str(row[0]).startswith('sqlite_')))

    @contextlib.contextmanager
    def _write_transaction(self):
        """Never silently commit an unrelated host transaction on the SHARED DB.

        #6 must serialize use of the supplied connection across host modules.
        SQLite savepoints alone cannot tell a P02 write from the host's pending
        transaction, so reject a busy connection instead of adopting its commit.
        """
        with self._lock:
            if self.db.in_transaction:
                raise P02Error('HOST_SQLITE_TRANSACTION_ACTIVE')
            with self.db:
                yield

    def initialize(self):
        """Fail-closed shared DB admission and atomic P02-only schema creation.

        Existing production chats must be mapped by #6 rather than overlaid.
        No PRAGMA user_version changes, no unrelated writes, no executescript,
        no implicit commit of host transactions, no schema deletion/downgrade.
        """
        reserved = {'p02_chats','p02_messages','p02_attachments',
                    'p02_gc','p02_meta','p02_messages_by_chat'}
        native_chat_names = {'chat','chats','messages','chat_messages',
                             'conversations','conversation_messages','chat_history',
                             'chat_sessions','message_history'}
        with self._write_transaction():
            rows = self.db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','index')").fetchall()
            existing = {str(row[0]).lower() for row in rows
                        if not str(row[0]).lower().startswith('sqlite_')}
            if existing & native_chat_names:
                raise P02Error('HOST_CHAT_SCHEMA_MAPPING_REQUIRED; refusing parallel history')
            unknown = existing - reserved
            if unknown - {x.lower() for x in self.approved_host_tables}:
                raise P02Error('HOST_SCHEMA_REVIEW_REQUIRED; refusing unapproved shared tables')
            if existing & reserved:
                if 'p02_meta' not in existing:
                    raise P02Error('INCOMPLETE_P02_SCHEMA; refusing implicit repair')
                version = self.db.execute("SELECT value FROM p02_meta WHERE key='schema'").fetchone()
                if version != ('1',):
                    raise P02Error('Incompatible existing P02 schema; refusing downgrade')
                # Existing user data is immutable until every required table and
                # its primary-key/foreign-key fields are confirmed. A partial
                # schema must be restored by #6 from verified backup, not
                # silently populated with empty tables alongside old chats.
                required = {
                    'p02_chats': {'id', 'tenant', 'principal', 'created_at'},
                    'p02_messages': {'id', 'chat_id', 'role', 'content', 'created_at'},
                    'p02_attachments': {'id', 'chat_id', 'storage', 'sha256', 'mime', 'bytes', 'created_at'},
                    'p02_gc': {'storage', 'queued_at'},
                    'p02_meta': {'key', 'value'},
                }
                if not set(required).issubset(existing):
                    raise P02Error('INCOMPLETE_P02_SCHEMA; restore verified backup')
                for table, expected_columns in required.items():
                    # Static table names only; never interpolate web/user input.
                    cols = {r[1] for r in self.db.execute(f'PRAGMA table_info({table})')}
                    if cols != expected_columns:
                        raise P02Error('P02_SCHEMA_COLUMNS_MISMATCH; restore verified backup')
            self.db.execute('PRAGMA foreign_keys=ON')
            schema = """
                CREATE TABLE IF NOT EXISTS p02_chats(
                    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, principal TEXT NOT NULL,
                    created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS p02_messages(
                    id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES p02_chats(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant','tool')),
                    content TEXT NOT NULL, created_at INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS p02_messages_by_chat ON p02_messages(chat_id,created_at,id);
                CREATE TABLE IF NOT EXISTS p02_attachments(
                    id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES p02_chats(id) ON DELETE CASCADE,
                    storage TEXT UNIQUE NOT NULL, sha256 TEXT NOT NULL, mime TEXT NOT NULL,
                    bytes INTEGER NOT NULL CHECK(bytes > 0), created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS p02_gc(storage TEXT PRIMARY KEY, queued_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS p02_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT OR IGNORE INTO p02_meta(key,value) VALUES('schema','1');
            """
            # Python sqlite3.executescript() may commit host work; individual
            # static statements inside this transaction preserve atomicity.
            for statement in schema.split(';'):
                if statement.strip():
                    self.db.execute(statement)
            version = self.db.execute("SELECT value FROM p02_meta WHERE key='schema'").fetchone()
            if version != ('1',):
                raise P02Error('Incompatible existing P02 schema; refuse automatic downgrade')

    def _owned(self, tenant: str, user: str, chat: str):
        _check_scope(tenant, user, chat)
        found = self.db.execute("SELECT 1 FROM p02_chats WHERE id=? AND tenant=? AND principal=?",
                                (chat, tenant, user)).fetchone()
        if not found:
            raise PermissionError("Chat unavailable for principal")

    def create_chat(self, tenant: str, user: str, chat: str):
        _check_scope(tenant, user, chat)
        with self._write_transaction():
            self.db.execute("INSERT INTO p02_chats VALUES(?,?,?,?)", (chat, tenant, user, int(time.time())))

    def add_message(self, tenant: str, user: str, chat: str, role: str, content: str) -> str:
        if role not in ("user", "assistant", "tool") or not isinstance(content, str) or len(content) > 1_000_000:
            raise ValueError("Invalid role/content")
        with self._write_transaction():
            self._owned(tenant, user, chat)
            message_id = uuid.uuid4().hex
            self.db.execute("INSERT INTO p02_messages VALUES(?,?,?,?,?)",
                            (message_id, chat, role, content, int(time.time())))
            return message_id

    def history(self, tenant: str, user: str, chat: str, limit: int = 250) -> list[dict]:
        if not (1 <= limit <= 1000):
            raise ValueError("Invalid limit")
        with self._lock:
            self._owned(tenant, user, chat)
            rows = self.db.execute("""SELECT role,content FROM p02_messages WHERE chat_id=?
                       ORDER BY created_at DESC,id DESC LIMIT ?""", (chat, limit)).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def prune(self, tenant: str, user: str, chat: str, before_epoch: int) -> int:
        with self._write_transaction():
            self._owned(tenant, user, chat)
            cursor = self.db.execute("DELETE FROM p02_messages WHERE chat_id=? AND created_at<?",
                                     (chat, before_epoch))
            return cursor.rowcount

    def store_file(self, tenant: str, user: str, chat: str, mime: str, source) -> dict:
        if mime not in ALLOWED_MIME:
            raise P02Error("Unsupported MIME")
        _check_scope(tenant, user, chat)
        fd, tmp_name = tempfile.mkstemp(prefix="p02_", suffix=".stage", dir=self.staging)
        tmp = pathlib.Path(tmp_name)
        storage = uuid.uuid4().hex
        dest = _safe_blob_path(self.blobs, storage)
        moved = False
        size = 0
        first = bytearray()
        digest = hashlib.sha256()
        try:
            with os.fdopen(fd, "wb") as out:
                while True:
                    chunk = source.read(65536)
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise P02Error("Attachment source must supply bytes")
                    size += len(chunk)
                    if size > MAX_FILE:
                        raise P02Error("Attachment exceeds 25 MiB limit")
                    digest.update(chunk)
                    if len(first) < 12:
                        first.extend(chunk[:12 - len(first)])
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            if size == 0:
                raise P02Error("Empty attachments disallowed")
            if mime == "application/pdf" and not first.startswith(b"%PDF-"):
                raise P02Error("Invalid PDF signature")
            if mime == "image/png" and not first.startswith(b"\x89PNG\r\n\x1a\n"):
                raise P02Error("Invalid PNG signature")
            if mime == "image/jpeg" and not first.startswith(b"\xff\xd8\xff"):
                raise P02Error("Invalid JPEG signature")
            if mime == "text/plain" and (b"\x00" in first):
                raise P02Error("Invalid plain-text header")
            sha = digest.hexdigest()
            with self._write_transaction():
                self._owned(tenant, user, chat)
                current = self.db.execute("SELECT COALESCE(SUM(bytes),0) FROM p02_attachments WHERE chat_id=?",
                                          (chat,)).fetchone()[0]
                if current + size > MAX_CHAT:
                    raise P02Error("Chat attachment quota exceeded")
                os.replace(tmp, dest)
                moved = True
                record_id = uuid.uuid4().hex
                self.db.execute("INSERT INTO p02_attachments VALUES(?,?,?,?,?,?,?)",
                                (record_id, chat, storage, sha, mime, size, int(time.time())))
            return {"stored_id": record_id, "sha256": sha, "bytes": size, "mime": mime}
        except BaseException:
            if moved:
                with contextlib.suppress(FileNotFoundError):
                    dest.unlink()
            raise
        finally:
            with contextlib.suppress(FileNotFoundError):
                tmp.unlink()

    def read_file(self, tenant: str, user: str, chat: str, stored_id: str) -> bytes:
        with self._lock:
            self._owned(tenant, user, chat)
            found = self.db.execute("SELECT storage,sha256,bytes FROM p02_attachments WHERE id=? AND chat_id=?",
                                    (stored_id, chat)).fetchone()
            if found is None:
                raise PermissionError("Attachment unavailable")
            storage, sha, expected = found
            path = _safe_blob_path(self.blobs, storage)
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as f:
                if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                    raise P02Error("Not a regular stored file")
                content = f.read(MAX_FILE + 1)
            if len(content) != expected or hashlib.sha256(content).hexdigest() != sha:
                raise P02Error("Stored attachment checksum mismatch")
            return content

    def delete_attachment(self, tenant: str, user: str, chat: str, stored_id: str):
        """Delete metadata under ACL and queue app-owned physical bytes for durable GC."""
        with self._write_transaction():
            self._owned(tenant, user, chat)
            row = self.db.execute("SELECT storage FROM p02_attachments WHERE id=? AND chat_id=?",
                                  (stored_id, chat)).fetchone()
            if row is None:
                raise PermissionError("Attachment unavailable")
            self.db.execute("INSERT OR IGNORE INTO p02_gc VALUES(?,?)", (row[0], int(time.time())))
            self.db.execute("DELETE FROM p02_attachments WHERE id=? AND chat_id=?", (stored_id, chat))

    def delete_chat(self, tenant: str, user: str, chat: str):
        with self._write_transaction():
            self._owned(tenant, user, chat)
            for (storage,) in self.db.execute("SELECT storage FROM p02_attachments WHERE chat_id=?", (chat,)):
                self.db.execute("INSERT OR IGNORE INTO p02_gc VALUES(?,?)", (storage, int(time.time())))
            self.db.execute("DELETE FROM p02_chats WHERE id=? AND tenant=? AND principal=?",
                            (chat, tenant, user))

    def collect_garbage(self) -> int:
        """Remove only DB-confirmed unreferenced blobs; safe to retry after crash."""
        removed = 0
        with self._lock:
            if self.db.in_transaction:
                raise P02Error('HOST_SQLITE_TRANSACTION_ACTIVE')
            records = self.db.execute("SELECT storage FROM p02_gc").fetchall()
            for (storage,) in records:
                if self.db.execute("SELECT 1 FROM p02_attachments WHERE storage=?", (storage,)).fetchone():
                    continue
                path = _safe_blob_path(self.blobs, storage)
                with contextlib.suppress(FileNotFoundError):
                    path.unlink()
                with self.db:
                    self.db.execute("DELETE FROM p02_gc WHERE storage=?", (storage,))
                removed += 1
        return removed


def authorized_app_message(source_uri: str, operation: str, main_frame: bool, user_confirmed: bool) -> bool:
    """Policy only: #6 must use browser-reported source and enforce in native WebView2 events."""
    try:
        origin = urllib.parse.urlsplit(source_uri)
        if (origin.scheme != "https" or origin.hostname != "nox.invalid" or
                origin.port is not None or origin.username or origin.password or not main_frame):
            return False
    except ValueError:
        return False
    allowed = {"chat.send", "chat.stop", "model.select", "history.list", "history.delete",
               "attachment.pick", "attachment.read"}
    if operation not in allowed:
        return False
    return operation not in {"history.delete", "attachment.pick"} or user_confirmed
