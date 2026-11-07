"""F01 R8 independent source contract: real Windows backup-lock native smoke wiring.
SOURCE_ONLY assertions. Windows acceptance is the original WPF UI smoke runner,
not this file. Owner-PC Qwen STREAM/STOP/SQLite is NOT exercised here.
"""
from pathlib import Path

root = Path(__file__).resolve().parent
paths = (root / "src" / "MainWindow.xaml.cs",
         root.parent / "overrides" / "src" / "MainWindow.xaml.cs")
source_path = next((p for p in paths if p.is_file()), None)
assert source_path is not None, "NOX_F01_ORIGINAL_SOURCE_MISSING_HOLD"
src = source_path.read_text(encoding="utf-8")
checkpoint = src.split("private string CheckpointSqlite(", 1)[1].split(
    "private void VerifyIsolatedSqliteBackup()", 1)[0]
native = src.split("private void VerifyIsolatedSqliteBackup()", 1)[1].split(
    "// Fail closed if any existing parent", 1)[0]
chat = src.split("private async Task Generate(", 1)[1].split(
    "private void PersistChat(", 1)[0]

# Both temporary native backup connections must use non-pooled handles.
assert checkpoint.count("Pooling = false") == 2, "NOX_F01_BACKUP_POOLING_HOLD"
assert checkpoint.index("source.BackupDatabase(dest)") < checkpoint.index("PRAGMA quick_check")
assert checkpoint.index("PRAGMA quick_check") < checkpoint.index("Sha256File(file)")
assert "FileMode.CreateNew" in checkpoint
assert "File.Delete(" not in checkpoint and "File.Move(stagedManifest, manifest, overwrite: false)" in checkpoint
assert "NOX_SQLITE_BACKUP_SHA_READBACK_HOLD" in checkpoint
assert 'CheckpointSqlite(live, "SMOKE_ISOLATED")' in native
assert "Mode = SqliteOpenMode.ReadOnly, Pooling = false" in native

# The original native WPF Windows process must prove the isolated snapshot
# accepts a non-sharing handle AFTER both check/read connections are disposed.
guard = native.split("NOX_B03_SMOKE_SHA_READBACK_HOLD", 1)[1]
for exact in (
    "using var exclusive = new FileStream(snapshot, FileMode.Open, FileAccess.Read, FileShare.None)",
    "NOX_F01_BACKUP_LOCKED_HANDLE_HOLD", "NOX_F01_SNAPSHOT_EMPTY_HOLD"
):
    assert exact in guard, "NOX_F01_NATIVE_LOCK_GUARD_HOLD:" + exact
assert "File.Delete(" not in guard and "File.WriteAllBytes(" not in guard
assert "new FileStream(dbPath" not in guard and "new FileStream(live" not in guard
assert 'checks["sqlite_native_backup_no_loss"] = "PASS";' in src
assert "VerifyIsolatedSqliteBackup();" in src

# Stream and native STOP must remain a real owner request, never a fixture.
for exact in ("ResponseHeadersRead", "/api/generate",
              "ReadLineAsync(readWindow.Token)", "Emit(\"token\"",
              "generationLock.WaitAsync(0)", "activeRequestId = requestId",
              "cancellation.Token.ThrowIfCancellationRequested()",
              "PersistChat(prompt, answer.ToString(), persona)",
              "sqliteWriteAttempted = true;", "sqliteVerified = true;",
              "sqliteUnknown = sqliteWriteAttempted && !sqliteVerified"):
    assert exact in chat, "NOX_F01_STREAM_STOP_SOURCE_GUARD_HOLD:" + exact
assert chat.index("cancellation.Token.ThrowIfCancellationRequested();\n            if (answer.Length") < chat.index(
    "PersistChat(prompt, answer.ToString(), persona)")
assert chat.index("PersistChat(prompt, answer.ToString(), persona)") < chat.index(
    "Emit(\"complete\", new { requestId, ok = answer.Length > 0")
print("NOX_F01_SOURCE_ONLY_PASS: native Windows backup lock guard, unpooled SQLite, STOP-before-commit source retained")

# The optional real-Qwen owner-PC selftest is stricter than the CI smoke:
# at least two genuine Ollama HTTP chunks must become visible before STOP,
# STOP cannot save partial data, and a subsequent turn must recover.
selftest = src.split("private async Task RunNativeSelfTestAsync()", 1)[1].split(
    "private bool HasSavedPrompt(", 1)[0]
assert "generationStreamingTokenCount) + 2" in selftest, "NOX_F01_TWO_REAL_CHUNKS_HOLD"
assert "NOX_F01_STREAM_NOT_VISIBLE_HOLD" in selftest
assert "NOX_F01_STOP_ACK_NOT_VISIBLE_HOLD" in selftest
assert "NOX_F01_LATE_TOKEN_OR_PARTIAL_SQLITE_HOLD" in selftest
assert "NOX_F01_STOP_RECOVERY_SQLITE_HOLD" in selftest
assert "NOX_F01_STOP_RECOVERY_NOT_VISIBLE_HOLD" in selftest
assert 'checks["real_chat_visible_webview_sqlite_ack"] = "PASS"' in selftest
assert 'checks["real_chat_after_stop_recovery_sqlite"] = "PASS"' in selftest
assert 'checks.Count == 7' in selftest
assert "DeleteSyntheticChats(recoveryMarker, null)" in selftest
print("NOX_F01_REAL_QWEN_E2E_ORACLE_SOURCE_ONLY_PASS: owner-PC model still NOT_RUN")
