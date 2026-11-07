"""B03 R8 pre-migration SQLite checkpoint/export NO-LOSS contract + isolated WAL fixture.
SOURCE_ONLY: not native C# execution, Windows lifecycle or owner-PC acceptance.
"""
import hashlib
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

src = (Path(__file__).resolve().parent / "src" / "MainWindow.xaml.cs").read_text(encoding="utf-8")
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
for guard in ("SELECT type,name FROM sqlite_master", "existingTables && !selfTestRequested",
              "PRAGMA journal_mode", 'CheckpointSqlite(db, "PRE_SCHEMA_BOOTSTRAP")',
              '"idx_learn_pending_owner", "idx_chat_history_time"'):
    assert guard in init, "NOX_B03_PRE_SCHEMA_SNAPSHOT_HOLD:" + guard
assert init.index('CheckpointSqlite(db, "PRE_SCHEMA_BOOTSTRAP")') < init.index('command.CommandText = """')
assert init.index('SELECT type,name FROM sqlite_master') < init.index('CheckpointSqlite(db, "PRE_SCHEMA_BOOTSTRAP")')
assert 'if (existingTables && !selfTestRequested)' in init
assert 'needed.Any(name => !knownObjects.Contains(name))' in init


# Importing the first local JSONL history must create exactly one verified
# preimage before BEGIN; repeated startup must not create repeated backups.
legacy = src.split("private void ImportLegacyJsonlIfNeeded(", 1)[1].split("\n    private ", 1)[0]
for guard in (
    "if (!File.Exists(legacy)) return;",
    "using (var prior = db.CreateCommand())",
    "if (Convert.ToInt64(prior.ExecuteScalar()) > 0) return;",
    'CheckpointSqlite(db, "PRE_LEGACY_JSONL_IMPORT")',
    "using var tx = db.BeginTransaction();",
    "if (Convert.ToInt64(check.ExecuteScalar()) > 0) { tx.Commit(); return; }",
    "INSERT INTO chat_history(timestamp,prompt,answer)",
    "INSERT INTO imported_sources(source,imported_at,rows)",
):
    assert guard in legacy, "NOX_B03_LEGACY_IMPORT_CONTRACT_HOLD:" + guard
assert legacy.index('CheckpointSqlite(db, "PRE_LEGACY_JSONL_IMPORT")') > legacy.index(
    "if (Convert.ToInt64(prior.ExecuteScalar()) > 0) return;")
assert legacy.index('CheckpointSqlite(db, "PRE_LEGACY_JSONL_IMPORT")') < legacy.index(
    "using var tx = db.BeginTransaction();")
assert "File.Delete(" not in legacy and "File.Move(" not in legacy

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
print("B03_R8_SOURCE_ONLY_PASS: native guards checked, real isolated WAL/quick_check/SHA, foreign bytes unchanged")
