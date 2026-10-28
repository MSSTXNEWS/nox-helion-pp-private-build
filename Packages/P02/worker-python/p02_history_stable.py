"""P02 stable chronology migration for the EXISTING host SQLite connection.

No database, connection, chat host, engine or service is created by this module.
The native owner must explicitly authorize migration, and must quiesce all other
writers and back up the original user database before attempting a schema change.
Only staged P02 schema v1 is supported; unknown host/history schemas HOLD.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import sqlite3
from dataclasses import dataclass


class HistoryHold(RuntimeError):
    pass


@dataclass(frozen=True)
class HistoryReceipt:
    backup_path: str
    backup_sha256: str
    messages_migrated: int
    schema_version: int


def _version(db: sqlite3.Connection) -> str:
    try:
        row = db.execute("SELECT value FROM p02_meta WHERE key='schema'").fetchone()
        return row[0] if row and isinstance(row[0], str) else ""
    except sqlite3.DatabaseError as exc:
        raise HistoryHold("P02_META_SCHEMA_HOLD") from exc


def _verify_v1(db: sqlite3.Connection) -> int:
    if _version(db) != "1":
        raise HistoryHold("P02_V1_EXPLICIT_MIGRATION_ONLY")
    if db.execute("PRAGMA foreign_keys").fetchone() != (1,):
        raise HistoryHold("P02_FOREIGN_KEYS_DISABLED")
    if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
        raise HistoryHold("P02_CANONICAL_DB_INTEGRITY_HOLD")
    required = {
        "p02_chats": {"id", "tenant", "principal", "created_at"},
        "p02_messages": {"id", "chat_id", "role", "content", "created_at"},
        "p02_meta": {"key", "value"},
    }
    for table, columns in required.items():
        found = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
        if found != columns:
            raise HistoryHold("P02_V1_COLUMN_SCHEMA_HOLD")
    # A canonical host chat schema may not coexist with a second P02 history.
    # Require integrator #6 to map the original database explicitly first.
    host_chat_names = {"chat", "chats", "messages", "chat_messages", "conversations",
                       "conversation_messages", "chat_history", "chat_sessions",
                       "message_history"}
    found_tables = {r[0].lower() for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if found_tables & host_chat_names:
        raise HistoryHold("CANONICAL_HOST_HISTORY_MAPPING_REQUIRED")
    if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise HistoryHold("P02_FOREIGN_KEY_CORRUPTION_HOLD")
    try:
        db.execute("SELECT rowid FROM p02_messages LIMIT 0")
    except sqlite3.DatabaseError as exc:
        raise HistoryHold("P02_ROWID_SCHEMA_HOLD") from exc
    return db.execute("SELECT count(*) FROM p02_messages").fetchone()[0]


def _sha_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1 << 20), b""):
            h.update(data)
    return h.hexdigest()


def migrate_host_history(db: sqlite3.Connection, backup_path: str | os.PathLike,
                         *, native_owner_approved: bool, writers_quiesced: bool,
                         verified_writer_v2_compatible: bool = False) -> HistoryReceipt:
    """V1 -> V2 in the same DB, after an exact SQLite online backup.

    This requires a host-owned SQLite connection, the host's synchronization
    barrier, a new exclusive backup file and a recovery plan. No silent upgrade.
    """
    if native_owner_approved is not True or writers_quiesced is not True:
        raise HistoryHold("NATIVE_APPROVAL_AND_WRITER_BARRIER_REQUIRED")
    # Original P02Store.add_message used INSERT INTO p02_messages VALUES(?,?,?,?,?).
    # Adding stable_seq makes that SQL fail. Do not migrate until E06 has pinned,
    # compiled and exercised the compatible explicit-column native writer.
    if verified_writer_v2_compatible is not True:
        raise HistoryHold("ORIGINAL_P02_WRITER_V2_COMPATIBILITY_NOT_VERIFIED")
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise HistoryHold("EXISTING_IDLE_SQLITE_CONNECTION_REQUIRED")
    if not isinstance(backup_path, (str, os.PathLike)) or not os.fspath(backup_path):
        raise HistoryHold("BACKUP_PATH_REQUIRED")
    backup = pathlib.Path(backup_path).absolute()
    if backup.is_symlink() or backup.exists() or not backup.parent.is_dir():
        raise HistoryHold("NEW_PRIVATE_BACKUP_PATH_REQUIRED")
    if backup.parent.is_symlink():
        raise HistoryHold("BACKUP_PARENT_SYMLINK_DENIED")
    src = db.execute("PRAGMA database_list").fetchall()
    main = next((r[2] for r in src if r[1] == "main"), "")
    if not main or main == ":memory:" or pathlib.Path(main).absolute() == backup:
        raise HistoryHold("PERSISTENT_CANONICAL_HOST_DB_REQUIRED")
    if os.path.commonpath([str(backup), str(pathlib.Path(main).absolute())]) == str(backup):
        raise HistoryHold("BACKUP_MUST_NOT_OVERWRITE_DB")
    # Preflight BEFORE reserving a backup path; invalid schema must not leave
    # an empty file masquerading as a recovery artifact.
    count = _verify_v1(db)
    # Ensure no existing file gets replaced by sqlite3.connect; exclusive reserve.
    fd = os.open(str(backup), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(str(backup)) as target:
            db.backup(target)
            if target.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise HistoryHold("BACKUP_INTEGRITY_HOLD")
            if target.execute("SELECT count(*) FROM p02_messages").fetchone()[0] != count:
                raise HistoryHold("BACKUP_COUNT_HOLD")
        checksum = _sha_file(backup)
        db.execute("BEGIN IMMEDIATE")
        try:
            if _verify_v1(db) != count:
                raise HistoryHold("CONCURRENT_MESSAGE_CHANGE_HOLD")
            db.execute("ALTER TABLE p02_messages ADD COLUMN stable_seq INTEGER")
            db.execute("""WITH ranked AS (
                SELECT rowid AS rid, ROW_NUMBER() OVER(ORDER BY created_at, rowid) AS seq
                FROM p02_messages)
                UPDATE p02_messages SET stable_seq =
                (SELECT seq FROM ranked WHERE rid = p02_messages.rowid)""")
            if db.execute("SELECT count(*) FROM p02_messages WHERE stable_seq IS NULL").fetchone()[0]:
                raise HistoryHold("HISTORY_BACKFILL_FAILED")
            db.execute("CREATE UNIQUE INDEX p02_messages_stable_seq ON p02_messages(stable_seq)")
            db.execute("""CREATE TRIGGER p02_messages_stable_insert AFTER INSERT ON p02_messages
                WHEN NEW.stable_seq IS NULL BEGIN
                  UPDATE p02_messages SET stable_seq =
                  (SELECT COALESCE(MAX(stable_seq),0)+1 FROM p02_messages)
                  WHERE rowid = NEW.rowid;
                END""")
            db.execute("UPDATE p02_meta SET value='2' WHERE key='schema' AND value='1'")
            if db.execute("SELECT changes()").fetchone()[0] != 1:
                raise HistoryHold("P02_SCHEMA_VERSION_RACE_HOLD")
            if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise HistoryHold("POST_MIGRATION_INTEGRITY_HOLD")
            db.commit()
        except Exception:
            db.rollback()
            raise
        return HistoryReceipt(str(backup), checksum, count, 2)
    except Exception:
        # Keep the backup even on failed migration for independent restoration.
        raise



def verify_v2_contract(db: sqlite3.Connection) -> None:
    """Read-only, fail-closed V2 admission for the original P02Store.

    This does not create or migrate anything. The verified Git source defines
    the writer, while this function checks the *actual* attached SQLite state.
    """
    if not isinstance(db, sqlite3.Connection) or _version(db) != "2":
        raise HistoryHold("P02_V2_ADMISSION_REQUIRED")
    if db.execute("PRAGMA foreign_keys").fetchone() != (1,):
        raise HistoryHold("P02_V2_FOREIGN_KEYS_REQUIRED")
    if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
        raise HistoryHold("P02_V2_DATABASE_INTEGRITY_HOLD")
    cols = {r[1] for r in db.execute("PRAGMA table_info(p02_messages)")}
    if cols != {"id", "chat_id", "role", "content", "created_at", "stable_seq"}:
        raise HistoryHold("P02_V2_COLUMN_SCHEMA_HOLD")
    indexed = False
    for row in db.execute("PRAGMA index_list(p02_messages)"):
        if row[1] == "p02_messages_stable_seq":
            if row[2] != 1 or [r[2] for r in db.execute(
                    "PRAGMA index_info(p02_messages_stable_seq)")] != ["stable_seq"]:
                raise HistoryHold("P02_V2_INDEX_INVALID")
            indexed = True
    if not indexed:
        raise HistoryHold("P02_V2_INDEX_MISSING")
    row = db.execute("""SELECT sql FROM sqlite_master WHERE type='trigger'
                AND tbl_name='p02_messages' AND name='p02_messages_stable_insert'""").fetchone()
    sql = row[0].lower() if row and isinstance(row[0], str) else ""
    if not all(token in " ".join(sql.split()) for token in (
            "after insert", "when new.stable_seq is null", "update p02_messages set stable_seq",
            "max(stable_seq)", "where rowid = new.rowid")):
        raise HistoryHold("P02_V2_TRIGGER_MISSING_OR_INVALID")
    if db.execute("""SELECT 1 FROM p02_messages
                   WHERE stable_seq IS NULL OR stable_seq<1 LIMIT 1""").fetchone():
        raise HistoryHold("P02_V2_SEQUENCE_DATA_INVALID")
    if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise HistoryHold("P02_V2_FOREIGN_KEY_HOLD")


def stable_history(db: sqlite3.Connection, tenant: str, principal: str,
                   chat: str, limit: int = 250) -> list[dict]:
    """Read the original authorized P02 messages with V2 vacuum-stable order."""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("History limit 1..1000")
    verify_v2_contract(db)
    if any(not isinstance(x, str) or not x or len(x) > 256 or x.strip() != x
           or any(ord(ch) < 32 for ch in x) for x in (tenant, principal, chat)):
        raise ValueError("Invalid native scope")
    owned = db.execute("SELECT 1 FROM p02_chats WHERE id=? AND tenant=? AND principal=?",
                       (chat, tenant, principal)).fetchone()
    if not owned:
        raise PermissionError("Host-owned chat scope required")
    rows = db.execute("""SELECT role,content FROM p02_messages WHERE chat_id=?
                   ORDER BY stable_seq DESC LIMIT ?""", (chat, limit)).fetchall()
    return [{"role": r, "content": c} for r,c in reversed(rows)]