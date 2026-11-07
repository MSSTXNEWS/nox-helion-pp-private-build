"""B03 R8 pre-migration SQLite checkpoint/export NO-LOSS contract + isolated WAL fixture.
SOURCE_ONLY: not native C# execution, Windows lifecycle or owner-PC acceptance.
"""
import hashlib
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

# Accept both the checked-in repository layout and the CI source-staging layout.
# Prefer the authentic R8 WPF override if both layouts happen to exist; never
# silently accept a missing or unrelated source file as a passing regression.
test_dir = Path(__file__).resolve().parent
candidates = (
    test_dir.parent / "overrides" / "src" / "MainWindow.xaml.cs",
    test_dir / "src" / "MainWindow.xaml.cs",
)
source_file = next((p for p in candidates if p.is_file()), None)
assert source_file is not None, "NOX_B03_SOURCE_PATH_HOLD"
src = source_file.read_text(encoding="utf-8")
checkpoint = src.split("private string CheckpointSqlite(", 1)[1].split("private static bool HasPersonaColumn(", 1)[0]
export = src.split("private void BackupLocalDatabase()", 1)[1].split("// An explicit native consent gate", 1)[0]
for phrase in (
    "ValidateBackupParent(Path.GetDirectoryName(dir)!)",
    "Directory.CreateDirectory(dir)",
    "ValidateBackupParent(dir)",
    "new FileStream(file, FileMode.CreateNew",
    "source.BackupDatabase(dest)",
    "Pooling = false",
    "PRAGMA quick_check",
    "string sha = Sha256File(file);",
    "new FileStream(stagedManifest, FileMode.CreateNew",
    "output.Flush(flushToDisk: true)",
    "File.Move(stagedManifest, manifest, overwrite: false)",
    "NOX_SQLITE_BACKUP_MANIFEST_READBACK_HOLD",
    "NOX_SQLITE_BACKUP_SHA_READBACK_HOLD",
):
    assert phrase in checkpoint, "NOX_B03_CHECKPOINT_GUARD_HOLD:" + phrase
assert checkpoint.index("FileMode.CreateNew") < checkpoint.index("source.BackupDatabase(dest)")
assert checkpoint.index("PRAGMA quick_check") < checkpoint.index("File.Move(stagedManifest, manifest, overwrite: false)")
assert checkpoint.index("ValidateBackupParent(dir);", checkpoint.index("string sha =")) < checkpoint.index("File.Move(stagedManifest, manifest, overwrite: false)")
assert "WriteAllText" not in checkpoint and "File.Delete(" not in checkpoint
assert "File.Copy(" not in checkpoint and "File.Move(" in checkpoint
for guard in ("private static void ValidateBackupParent(", "FileAttributes.ReparsePoint",
              "NOX_BACKUP_PARENT_MISSING_HOLD", "NOX_BACKUP_PARENT_REPARSE_HOLD"):
    assert guard in src, guard
for guard in ("OverwritePrompt = false", "NOX_BACKUP_DESTINATION_EXISTS_HOLD",
              "new[] { \"-wal\", \"-shm\", \"-journal\" }",
              "NOX_BACKUP_LIVE_SIDECAR_HOLD",
              "ValidateBackupParent(outputDirectory)", "FileMode.CreateNew",
              "NOX_BACKUP_EXPORT_CHECKSUM_HOLD", "File.Move(stage, target);",
              "NOX_BACKUP_EXPORT_READBACK_HOLD"):
    assert guard in export, guard
assert export.index("ValidateBackupParent(outputDirectory)") < export.index("FileMode.CreateNew")
assert export.rindex("ValidateBackupParent(outputDirectory)") < export.index("File.Move(stage, target);")

# The isolated *native Windows process* must exercise the real C# backup,
# not only the Python sqlite3 fixture or a diagnostic claim.
native = src.split("private void VerifyIsolatedSqliteBackup()", 1)[1].split(
    "// Fail closed if any existing parent", 1)[0]
for guard in (
    "UiSmokeRequested", 'StartsWith("selftest_r8_"',
    'CheckpointSqlite(live, "SMOKE_ISOLATED")',
    'File.ReadAllText(snapshot + ".sha256", Encoding.UTF8)',
    'Mode = SqliteOpenMode.ReadOnly, Pooling = false',
    'NOX_B03_SMOKE_SNAPSHOT_ROWS_HOLD',
    'NOX_B03_SMOKE_SOURCE_CHANGED_HOLD',
    'NOX_B03_SMOKE_SHA_READBACK_HOLD'
):
    assert guard in native, "NOX_B03_NATIVE_SNAPSHOT_CONTRACT_HOLD:" + guard
assert 'VerifyIsolatedSqliteBackup();' in src
assert 'checks["sqlite_native_backup_no_loss"] = "PASS";' in src
assert '"sqlite_native_backup_no_loss", "native_wpf_webview2_renderer"' in src

# The first bootstrap must protect a partially populated *existing* database
# before CREATE TABLE / CREATE INDEX / journal-mode changes, not merely before
# the later Persona migration. Avoid an unbounded backup on every healthy launch.
init = src.split("private void InitializeDatabase()", 1)[1].split("// Owner-only SQLite", 1)[0]
for guard in ("SELECT type,name FROM sqlite_master", "preexistingOwnerBytes",
              "PRAGMA journal_mode", 'CheckpointSqlite(db, "PRE_SCHEMA_BOOTSTRAP")',
              '"idx_learn_pending_owner", "idx_chat_history_time"'):
    assert guard in init, "NOX_B03_PRE_SCHEMA_SNAPSHOT_HOLD:" + guard
assert init.index('CheckpointSqlite(db, "PRE_SCHEMA_BOOTSTRAP")') < init.index('command.CommandText = """')
assert init.index('SELECT type,name FROM sqlite_master') < init.index('CheckpointSqlite(db, "PRE_SCHEMA_BOOTSTRAP")')
assert 'bool preexistingOwnerBytes = File.Exists(dbPath) && new FileInfo(dbPath).Length > 0;' in init
assert init.index("preexistingOwnerBytes = File.Exists(dbPath)") < init.index("using var db = OpenDatabase();")
assert 'if ((existingTables || preexistingOwnerBytes) && !selfTestRequested)' in init
assert 'needed.Any(name => !knownObjects.Contains(name))' in init


# First-ever startup should not create an empty PRE_PERSONA_MIGRATION copy,
# but an existing legacy database must still checkpoint before ALTER TABLE.
assert "MigratePersonaStorage(db, existingTables);" in init
migration = src.split(
    "private void MigratePersonaStorage(SqliteConnection db, bool hadExistingTablesBeforeBootstrap)", 1
)[1].split("private string ActivePersona()", 1)[0]
assert migration.index("if (chatReady && notesReady && !missingIndexes) return;") < migration.index(
    "if (hadExistingTablesBeforeBootstrap)"
)
assert "'idx_chat_persona','idx_notes_persona'" in migration
assert "using var indexRows = indexInventory.ExecuteReader();" in migration
assert "foundIndexes.Contains" in migration
assert '"idx_chat_persona", "idx_notes_persona"' in init
assert migration.index("if (hadExistingTablesBeforeBootstrap)") < migration.index(
    'CheckpointSqlite(db, "PRE_PERSONA_MIGRATION")'
) < migration.index("using var tx = db.BeginTransaction();")
assert "ALTER TABLE chat_history ADD COLUMN persona" in migration
assert "ALTER TABLE memory_notes ADD COLUMN persona" in migration

# Both B03 and D03 implement a verified preimport SQLite snapshot.
# The final source must keep exactly one snapshot before the write transaction.
legacy = src.split("private void ImportLegacyJsonlIfNeeded(", 1)[1].split("\n    private ", 1)[0]
snapshots = re.findall(
    r'CheckpointSqlite\(\s*db,\s*"(PRE_LEGACY_JSONL_IMPORT|PRE_LEGACY_IMPORT)"\s*\)', legacy
)
assert len(snapshots) == 1 and legacy.count("CheckpointSqlite(") == 1, (
    "NOX_B03_LEGACY_SNAPSHOT_MISSING_OR_DUPLICATED_HOLD"
)
for guard in (
    "if (!File.Exists(legacy)) return;",
    "SELECT COUNT(*) FROM imported_sources",
    "using var tx = db.BeginTransaction();",
    "INSERT INTO chat_history(timestamp,prompt,answer)",
    "INSERT INTO imported_sources(source,imported_at,rows)",
    "tx.Commit()",
):
    assert guard in legacy, "NOX_B03_LEGACY_IMPORT_CONTRACT_HOLD:" + guard
snapshot_pos = legacy.index("CheckpointSqlite(")
assert legacy.index("SELECT COUNT(*) FROM imported_sources") < snapshot_pos
assert snapshot_pos < legacy.index("using var tx = db.BeginTransaction();")
assert "File.Delete(" not in legacy and "File.Move(" not in legacy

if snapshots[0] == "PRE_LEGACY_JSONL_IMPORT":
    # Original B03 semantics: no redundant backup after import is complete.
    for guard in (
        "using (var prior = db.CreateCommand())",
        "if (Convert.ToInt64(prior.ExecuteScalar()) > 0) return;",
        "if (Convert.ToInt64(check.ExecuteScalar()) > 0) { tx.Commit(); return; }",
    ):
        assert guard in legacy, "NOX_B03_ORIGINAL_IMPORT_CONTRACT_HOLD:" + guard
    assert legacy.index("prior.ExecuteScalar()") < snapshot_pos
else:
    # D03's stronger SHA/rollback importer supersedes B03's import hunk.
    for guard in (
        "FileAttributes.ReparsePoint",
        "NOX_LEGACY_JSONL_REPARSE_HOLD",
        "NOX_LEGACY_JSONL_INCOMPLETE_HOLD",
        "NOX_LEGACY_JSONL_CHANGED_DURING_IMPORT_HOLD",
        "shaPrefix + sourceSha",
        "tx.Rollback()",
        "Sha256File(legacy)",
    ):
        assert guard in legacy, "NOX_D03_IMPORT_NOLOSS_CONTRACT_HOLD:" + guard
    assert legacy.count("Sha256File(legacy)") >= 2
    assert legacy.index("Sha256File(legacy)") < snapshot_pos

# Run actual WAL + backup + integrity + SHA + immutable foreign file fixtures
# on an isolated temporary SQLite database; no production files are touched.
with tempfile.TemporaryDirectory(prefix="nox_b03_") as folder:
    root = Path(folder)
    live = root / "chat.sqlite3"
    snapshot = root / "snapshot.sqlite3"
    foreign = root / "foreign.sqlite3"
    foreign.write_bytes(b"OWNER_BYTES_NEVER_OVERWRITE")
    foreign_before = hashlib.sha256(foreign.read_bytes()).hexdigest()
    with closing(sqlite3.connect(live)) as srcdb:
        srcdb.execute("PRAGMA journal_mode=WAL")
        srcdb.execute("CREATE TABLE notes(value TEXT NOT NULL)")
        srcdb.execute("INSERT INTO notes(value) VALUES('original')")
        srcdb.commit()
        with snapshot.open("xb"):
            pass
        with closing(sqlite3.connect(snapshot)) as dstdb:
            srcdb.backup(dstdb)
        with closing(sqlite3.connect(snapshot)) as verify:
            assert verify.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            assert verify.execute("SELECT value FROM notes").fetchone()[0] == "original"
        sha = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        record = (sha.upper() + "  " + snapshot.name + "\n").encode()
        manifest = root / "snapshot.sqlite3.sha256"
        with manifest.open("xb") as out:
            out.write(record)
            out.flush()
        assert manifest.read_bytes() == record
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == sha
        try:
            with foreign.open("xb") as out:
                out.write(b"ATTACK")
        except FileExistsError:
            pass
        else:
            raise AssertionError("NOX_B03_FOREIGN_CREATE_NEW_MUST_HOLD")
        assert hashlib.sha256(foreign.read_bytes()).hexdigest() == foreign_before
        assert srcdb.execute("SELECT value FROM notes").fetchone()[0] == "original"
# Existing schema-free SQLite still owns non-table metadata (e.g. user_version).
# Reproduces the old existingTables=False miss on a real isolated database.
with tempfile.TemporaryDirectory(prefix="nox_b03_metadata_") as folder:
    owner = Path(folder) / "metadata_only.sqlite3"
    copy = Path(folder) / "metadata_snapshot.sqlite3"
    with closing(sqlite3.connect(owner)) as db:
        db.execute("PRAGMA user_version=77")
        db.commit()
    assert owner.stat().st_size > 0, "NOX_B03_METADATA_FIXTURE_EMPTY_HOLD"
    with closing(sqlite3.connect(owner)) as db:
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        assert not tables, "NOX_B03_METADATA_FIXTURE_HAS_TABLES_HOLD"
        assert db.execute("PRAGMA user_version").fetchone()[0] == 77
        with closing(sqlite3.connect(copy)) as dest:
            db.backup(dest)
    with closing(sqlite3.connect(copy)) as verify:
        assert verify.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert verify.execute("PRAGMA user_version").fetchone()[0] == 77, "NOX_B03_METADATA_PREIMAGE_LOST_HOLD"
    assert owner.exists() and hashlib.sha256(owner.read_bytes()).hexdigest()

# A partially completed Persona migration may have both columns but no
# persona indexes. The old early return silently treated it as healthy. Exercise
# the real SQLite DDL/online-backup semantics on an isolated owner-data fixture;
# this is not evidence that original WPF C# has executed.
with tempfile.TemporaryDirectory(prefix="nox_b03_persona_index_") as folder:
    original = Path(folder) / "owner.sqlite3"
    preimage = Path(folder) / "before_index_repair.sqlite3"
    with closing(sqlite3.connect(original)) as db:
        db.execute("CREATE TABLE chat_history (id INTEGER PRIMARY KEY, timestamp TEXT, prompt TEXT, answer TEXT, persona TEXT NOT NULL DEFAULT 'KV')")
        db.execute("CREATE TABLE memory_notes (id INTEGER PRIMARY KEY, created_at TEXT, title TEXT, content TEXT, persona TEXT NOT NULL DEFAULT 'KV')")
        db.execute("INSERT INTO chat_history VALUES(1,'now','question','answer','KV')")
        db.execute("INSERT INTO memory_notes VALUES(1,'now','title','note','KV')")
        db.commit()
        initial = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert "idx_chat_persona" not in initial and "idx_notes_persona" not in initial
        with closing(sqlite3.connect(preimage)) as dest:
            db.backup(dest)
        db.execute("CREATE INDEX IF NOT EXISTS idx_chat_persona ON chat_history(persona,id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_notes_persona ON memory_notes(persona,id)")
        db.commit()
        repaired = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {"idx_chat_persona", "idx_notes_persona"} <= repaired
        assert db.execute("SELECT prompt,answer,persona FROM chat_history").fetchone() == ("question","answer","KV")
        assert db.execute("SELECT content,persona FROM memory_notes").fetchone() == ("note","KV")
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    with closing(sqlite3.connect(preimage)) as copy:
        assert copy.execute("SELECT content,persona FROM memory_notes").fetchone() == ("note","KV")
        assert "idx_notes_persona" not in {r[0] for r in copy.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert copy.execute("PRAGMA quick_check").fetchone()[0] == "ok"

print("B03_R8_SOURCE_ONLY_PASS: guards, WAL, metadata-only owner preimage, quick_check/SHA; native Windows pending")
