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
    if any(not isinstance(x, str) or not x.strip() or len(x) > 200 or
           any(ord(char) < 32 or ord(char) == 127 for char in x)
           for x in (tenant, user, chat)):
        raise ValueError("Missing or invalid tenant, user or chat scope")


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
        original_root = pathlib.Path(attachment_root).absolute()
        # Native owner must give the actual app-owned directory, never a symlink.
        if original_root.is_symlink():
            raise P02Error('ATTACHMENT_ROOT_SYMLINK_DENIED')
        self.root = original_root.resolve()
        self.staging = self.root / "staging"
        self.blobs = self.root / "stored"
        # This is host-selected application data, NEVER a path from webpage JS.
        # Do not follow existing symlinks for the storage subdirectories: a
        # crafted profile could otherwise redirect private attachments outside
        # the approved app-owned tree even if individual *.blob is checked.
        if self.staging.is_symlink() or self.blobs.is_symlink():
            raise P02Error('ATTACHMENT_STORAGE_SYMLINK_DENIED')
        self.staging.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.blobs.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._assert_storage_roots()
        self._lock = threading.RLock()

    def _assert_storage_roots(self):
        if (self.staging.is_symlink() or self.blobs.is_symlink()
                or self.staging.resolve() != self.root / 'staging'
                or self.blobs.resolve() != self.root / 'stored'
                or not self.staging.is_dir() or not self.blobs.is_dir()):
            raise P02Error('ATTACHMENT_STORAGE_OUTSIDE_APPROVED_ROOT')

    def host_schema_inventory(self) -> tuple[str, ...]:
        """Read-only host table list for #6; never silently migrate a user's DB."""
        with self._lock:
            return tuple(sorted(row[0] for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
                if not str(row[0]).startswith('sqlite_')))

    @contextlib.contextmanager
    def _write_transaction(self, *, stop: threading.Event | None = None):
        """Never silently commit an unrelated host transaction on the SHARED DB.

        #6 must serialize use of the supplied connection across host modules.
        SQLite savepoints alone cannot tell a P02 write from the host's pending
        transaction, so reject a busy connection instead of adopting its commit.
        """
        if stop is not None and not isinstance(stop, threading.Event):
            raise TypeError('P02_STOP_EVENT_REQUIRED')
        with self._lock:
            if stop is not None and stop.is_set():
                raise Cancelled('STOP before P02 SQLite BEGIN')
            if self.db.in_transaction:
                raise P02Error('HOST_SQLITE_TRANSACTION_ACTIVE')
            # Host may reopen the shared SQLite connection with FK enforcement
            # disabled. Never perform deletes that would orphan chat history.
            self.db.execute('PRAGMA foreign_keys=ON')
            enabled = self.db.execute('PRAGMA foreign_keys').fetchone()
            if enabled != (1,):
                raise P02Error('HOST_SQLITE_FOREIGN_KEYS_REQUIRED')
            # Explicit BEGIN makes CREATE TABLE/INDEX and metadata insert one
            # rollbackable unit (sqlite3's implicit transactions skip DDL).
            self.db.execute('BEGIN IMMEDIATE')
            with self.db:
                yield
                # Abort this original shared SQLite transaction on observed STOP.
                # Native host must still serialize STOP-vs-COMMIT for full atomicity.
                if stop is not None and stop.is_set():
                    raise Cancelled('STOP before P02 SQLite commit')

    def initialize(self):
        """Fail-closed shared DB admission and atomic P02-only schema creation.

        Existing production chats must be mapped by #6 rather than overlaid.
        No PRAGMA user_version changes, no unrelated writes, no executescript,
        no implicit commit of host transactions, no schema deletion/downgrade.
        """
        reserved = {'p02_chats','p02_messages','p02_attachments',
                    'p02_gc','p02_meta','p02_messages_by_chat',
                    'p02_messages_stable_seq'}
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
                if version not in (('1',), ('2',)):
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
                    # C13: permit only the original owner-reviewed V2 field.
                    if table == 'p02_messages' and version == ('2',):
                        expected_columns = expected_columns | {'stable_seq'}
                    if cols != expected_columns:
                        raise P02Error('P02_SCHEMA_COLUMNS_MISMATCH; restore verified backup')
                    key_columns = {'p02_chats': 'id', 'p02_messages': 'id',
                                   'p02_attachments': 'id', 'p02_gc': 'storage',
                                   'p02_meta': 'key'}
                    info = list(self.db.execute(f'PRAGMA table_info({table})'))
                    if not any(row[1] == key_columns[table] and row[5] == 1 for row in info):
                        raise P02Error('P02_SCHEMA_PRIMARY_KEY_DRIFT; restore verified backup')
                # A forged attachment table with matching column names but no
                # storage uniqueness could bind one physical blob to several chats.
                indices = list(self.db.execute('PRAGMA index_list(p02_attachments)'))
                found_storage_unique = False
                for index_row in indices:
                    if index_row[2] != 1:  # unique = 1
                        continue
                    index_name = str(index_row[1]).replace('"', '""')
                    keys = [row[2] for row in self.db.execute(
                        f'PRAGMA index_info("{index_name}")')]
                    if keys == ['storage']:
                        found_storage_unique = True
                if not found_storage_unique:
                    raise P02Error('P02_STORAGE_UNIQUENESS_DRIFT; restore verified backup')
                # Stable same-second history order uses the internal rowid.
                # Existing WITHOUT ROWID variants must be mapped/migrated by #6;
                # accepting them here could break ordering or lose history.
                try:
                    self.db.execute('SELECT rowid FROM p02_messages LIMIT 0')
                except sqlite3.OperationalError as exc:
                    raise P02Error('P02_MESSAGE_ROWID_REQUIRED; restore verified backup') from exc
                for table in ('p02_messages', 'p02_attachments'):
                    rows = list(self.db.execute(f'PRAGMA foreign_key_list({table})'))
                    if not any(row[2] == 'p02_chats' and row[3] == 'chat_id'
                               and row[4] == 'id' and row[6] == 'CASCADE' for row in rows):
                        raise P02Error('P02_SCHEMA_FOREIGN_KEY_DRIFT; restore verified backup')
                if self.db.execute('PRAGMA foreign_key_check').fetchone() is not None:
                    raise P02Error('P02_SCHEMA_FOREIGN_KEY_VIOLATION; restore verified backup')
                if version == ('2',):
                    from p02_history_stable import verify_v2_contract
                    verify_v2_contract(self.db)
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
            if version not in (('1',), ('2',)):
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

    def add_turn(self, tenant: str, user: str, chat: str,
                 user_text: str, assistant_text: str,
                 *, stop: threading.Event | None = None) -> tuple[str, str]:
        """One completed turn, one transaction in the EXISTING host SQLite DB.

        Assistant-write failure, access denial or STOP before COMMIT rolls back
        both messages. No second database, schema change or provider.
        """
        if (type(user_text) is not str or type(assistant_text) is not str
                or not user_text or not assistant_text
                or len(user_text) > 1_000_000 or len(assistant_text) > 1_000_000):
            raise ValueError("Valid bounded completed chat turn required")
        with self._write_transaction(stop=stop):
            self._owned(tenant, user, chat)
            ids = (uuid.uuid4().hex, uuid.uuid4().hex)
            stamp = int(time.time())
            self.db.execute(
                "INSERT INTO p02_messages(id,chat_id,role,content,created_at) VALUES(?,?,?,?,?)",
                (ids[0], chat, "user", user_text, stamp))
            if stop is not None and stop.is_set():
                raise Cancelled("STOP before assistant message")
            self.db.execute(
                "INSERT INTO p02_messages(id,chat_id,role,content,created_at) VALUES(?,?,?,?,?)",
                (ids[1], chat, "assistant", assistant_text, stamp))
            return ids

    def add_message(self, tenant: str, user: str, chat: str, role: str, content: str,
                    *, stop: threading.Event | None = None) -> str:
        if role not in ("user", "assistant", "tool") or not isinstance(content, str) or len(content) > 1_000_000:
            raise ValueError("Invalid role/content")
        with self._write_transaction(stop=stop):
            self._owned(tenant, user, chat)
            message_id = uuid.uuid4().hex
            self.db.execute("INSERT INTO p02_messages(id,chat_id,role,content,created_at) VALUES(?,?,?,?,?)",
                            (message_id, chat, role, content, int(time.time())))
            return message_id

    def history(self, tenant: str, user: str, chat: str, limit: int = 250) -> list[dict]:
        # bool is an int subclass; accepting it as a page size hides UI/host mistakes.
        if type(limit) is not int or not (1 <= limit <= 1000):
            raise ValueError("Invalid limit")
        with self._lock:
            self._owned(tenant, user, chat)
            # UUID message IDs are random: sorting by ID after same-second
            # timestamps reorders user/assistant messages.  Existing P02
            # message tables use SQLite rowid, the insertion-order tie breaker.
            # Do not alter schema, timestamps, IDs or any persisted message.
            schema = self.db.execute("SELECT value FROM p02_meta WHERE key='schema'").fetchone()
            if schema == ('2',):
                # Same original SQLite/ACL. A validated existing V2, no auto-migration.
                from p02_history_stable import stable_history
                return stable_history(self.db, tenant, user, chat, limit)
            if schema != ('1',):
                raise P02Error('P02_HISTORY_SCHEMA_UNRECOGNIZED')
            rows = self.db.execute("""SELECT role,content FROM p02_messages WHERE chat_id=?
                       ORDER BY created_at DESC,rowid DESC LIMIT ?""", (chat, limit)).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def prune(self, tenant: str, user: str, chat: str, before_epoch: int) -> int:
        # Invalid retention inputs must not delete any user history. Values are
        # UTC seconds, not milliseconds; explicit delete_chat handles full removal.
        if type(before_epoch) is not int or not 0 <= before_epoch <= 253402300799:
            raise ValueError("Invalid UTC retention cutoff")
        with self._write_transaction():
            self._owned(tenant, user, chat)
            cursor = self.db.execute("DELETE FROM p02_messages WHERE chat_id=? AND created_at<?",
                                     (chat, before_epoch))
            return cursor.rowcount

    def store_file(self, tenant: str, user: str, chat: str, mime: str, source) -> dict:
        if mime not in ALLOWED_MIME:
            raise P02Error("Unsupported MIME")
        _check_scope(tenant, user, chat)
        # Deny unauthorized streams BEFORE allocating staging bytes. Ownership
        # is checked again in the committing SQLite transaction to prevent TOCTOU.
        with self._lock:
            self._owned(tenant, user, chat)
        self._assert_storage_roots()
        fd, tmp_name = tempfile.mkstemp(prefix="p02_", suffix=".stage", dir=self.staging)
        tmp = pathlib.Path(tmp_name)
        storage = uuid.uuid4().hex
        dest = _safe_blob_path(self.blobs, storage)
        moved = False
        size = 0
        first = bytearray()
        digest = hashlib.sha256()
        text_decoder = None
        if mime == 'text/plain':
            import codecs
            text_decoder = codecs.getincrementaldecoder('utf-8')('strict')
        try:
            with os.fdopen(fd, "wb") as out:
                while True:
                    chunk = source.read(65536)
                    if chunk == b'':
                        break
                    if not isinstance(chunk, bytes) or len(chunk) > 65536:
                        raise P02Error('ATTACHMENT_STREAM_INVALID_CHUNK')
                    size += len(chunk)
                    if size > MAX_FILE:
                        raise P02Error("Attachment exceeds 25 MiB limit")
                    if text_decoder is not None:
                        if b'\x00' in chunk:
                            raise P02Error('ATTACHMENT_PLAINTEXT_NUL_DENIED')
                        try:
                            text_decoder.decode(chunk, final=False)
                        except UnicodeError as exc:
                            raise P02Error('ATTACHMENT_PLAINTEXT_UTF8_REQUIRED') from exc
                    digest.update(chunk)
                    if len(first) < 12:
                        first.extend(chunk[:12 - len(first)])
                    out.write(chunk)
                if text_decoder is not None:
                    try:
                        text_decoder.decode(b'', final=True)
                    except UnicodeError as exc:
                        raise P02Error('ATTACHMENT_PLAINTEXT_UTF8_REQUIRED') from exc
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
            self._assert_storage_roots()
            with self._write_transaction():
                self._owned(tenant, user, chat)
                current = self.db.execute("SELECT COALESCE(SUM(bytes),0) FROM p02_attachments WHERE chat_id=?",
                                          (chat,)).fetchone()[0]
                if current + size > MAX_CHAT:
                    raise P02Error("Chat attachment quota exceeded")
                # Atomic, no-clobber publication on the same application data
                # volume; preserve any prior blob on collision (NO-LOSS).
                os.link(tmp, dest, follow_symlinks=False)
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
            self._assert_storage_roots()
            path = _safe_blob_path(self.blobs, storage)
            # O_NOFOLLOW is unavailable on some Windows Python builds.
            # Do not trust fstat alone: it follows reparse points/symlinks.
            try:
                before = path.lstat()
            except OSError as exc:
                raise P02Error('ATTACHMENT_STORAGE_UNAVAILABLE') from exc
            if not stat.S_ISREG(before.st_mode):
                raise P02Error('ATTACHMENT_STORAGE_UNSAFE_FILE_TYPE')
            if before.st_nlink != 1:
                raise P02Error('ATTACHMENT_HARDLINK_ALIAS_DENIED')
            if before.st_ino == 0 and not getattr(os, "O_NOFOLLOW", 0):
                raise P02Error('ATTACHMENT_NO_SAFE_FILE_ID')
            try:
                fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                             | getattr(os, "O_BINARY", 0))
            except OSError as exc:
                raise P02Error('ATTACHMENT_STORAGE_OPEN_DENIED') from exc
            with os.fdopen(fd, "rb") as f:
                file_stat = os.fstat(f.fileno())
                # A replaced regular file must also fail, even if it has the
                # same bytes: avoid a pre-stat -> open pathname substitution.
                if (not stat.S_ISREG(file_stat.st_mode) or
                        (file_stat.st_dev, file_stat.st_ino) !=
                        (before.st_dev, before.st_ino)):
                    raise P02Error('ATTACHMENT_STORAGE_CHANGED')
                if file_stat.st_nlink != 1:
                    raise P02Error('ATTACHMENT_HARDLINK_ALIAS_DENIED')
                try:
                    after = path.lstat()
                except OSError as exc:
                    raise P02Error('ATTACHMENT_STORAGE_CHANGED') from exc
                if (not stat.S_ISREG(after.st_mode) or
                        (after.st_dev, after.st_ino) !=
                        (file_stat.st_dev, file_stat.st_ino)):
                    raise P02Error('ATTACHMENT_STORAGE_CHANGED')
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
                self._assert_storage_roots()
                path = _safe_blob_path(self.blobs, storage)
                try:
                    st = path.lstat()
                except FileNotFoundError:
                    st = None
                if st is not None:
                    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                        raise P02Error('ATTACHMENT_GC_UNSAFE_FILE_TYPE')
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
