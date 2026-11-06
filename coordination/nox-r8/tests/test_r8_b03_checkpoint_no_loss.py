"""B03 R8 pre-migration SQLite checkpoint/export NO-LOSS contract + isolated WAL fixture.
SOURCE_ONLY: not native C# execution, Windows lifecycle or owner-PC acceptance.
"""
import hashlib
import sqlite3
import tempfile
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

# Run actual WAL + backup + integrity + SHA + immutable foreign file fixtures
# on an isolated temporary SQLite database; no production files are touched.
with tempfile.TemporaryDirectory(prefix="nox_b03_") as folder:
    root = Path(folder)
    live = root / "chat.sqlite3"
    snapshot = root / "snapshot.sqlite3"
    foreign = root / "foreign.sqlite3"
    foreign.write_bytes(b"OWNER_BYTES_NEVER_OVERWRITE")
    foreign_before = hashlib.sha256(foreign.read_bytes()).hexdigest()
    with sqlite3.connect(live) as srcdb:
        srcdb.execute("PRAGMA journal_mode=WAL")
        srcdb.execute("CREATE TABLE notes(value TEXT NOT NULL)")
        srcdb.execute("INSERT INTO notes(value) VALUES('original')")
        srcdb.commit()
        with snapshot.open("xb"):
            pass
        with sqlite3.connect(snapshot) as dstdb:
            srcdb.backup(dstdb)
        with sqlite3.connect(snapshot) as verify:
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
