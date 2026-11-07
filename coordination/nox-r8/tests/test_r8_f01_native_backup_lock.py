"""F01/B06 R8 source-only guard for single-EXE backup-lock and visible HTTP STOP.
No model mock, no owner-PC access, no claim of completed Windows acceptance.
"""
from pathlib import Path
here = Path(__file__).resolve().parent
if here.name == "tests" and here.parent.name == "nox-r8":
    src = here.parent / "overrides" / "src" / "MainWindow.xaml.cs"
elif here.name == "r8":
    src = here / "src" / "MainWindow.xaml.cs"
else:
    raise AssertionError("F01_SOURCE_ORIGIN_HOLD")
assert src.is_file(), "F01_SOURCE_MISSING_HOLD"
code = src.read_text(encoding="utf-8")
checkpoint = code.split("private string CheckpointSqlite(",1)[1].split("private void VerifyIsolatedSqliteBackup()",1)[0]
backup = code.split("private void VerifyIsolatedSqliteBackup()",1)[1].split("// Fail closed if any existing parent",1)[0]
native = code.split("private async Task RunNativeSelfTestAsync()",1)[1].split("private bool HasSavedPrompt(",1)[0]
assert checkpoint.count("Pooling = false") == 2, "F01_BACKUP_POOLING_HOLD"
assert "FileShare.None" in backup and "NOX_F01_BACKUP_LOCKED_HANDLE_HOLD" in backup
assert "NOX_F01_SNAPSHOT_EMPTY_HOLD" in backup
for x in (
    'generationStreamingTokenCount) + 2',
    'NOX_WEBVIEW2_STREAM_TOKEN_NOT_VISIBLE_HOLD',
    'NOX_F01_FIRST_CHAT_NOT_VISIBLE_HOLD',
    'NOX_F01_LATE_TOKEN_OR_PARTIAL_SQLITE_HOLD',
    'NOX_F01_STOP_RECOVERY_NOT_VISIBLE_HOLD',
    'checks["real_chat_visible_webview_sqlite_ack"] = "PASS"',
    'checks["real_chat_after_http_stop_sqlite"] = "PASS"',
    'checks.Count == 7 && checks.Values.All(v => v == "PASS")',
    'WaitForSavedChatUiReleaseAsync(TimeSpan.FromSeconds(4))',
):
    assert x in native, "F01_REAL_NATIVE_E2E_SOURCE_HOLD: "+x
assert native.index('WaitForVisibleChatTokenAsync') < native.index("document.getElementById('stop').click()")
assert native.index('NOX_F01_LATE_TOKEN_OR_PARTIAL_SQLITE_HOLD') < native.index('real_chat_after_http_stop_sqlite')
print("F01_B06_NATIVE_BACKUP_AND_REAL_QWEN_STOP_ORACLE_SOURCE_ONLY_PASS_OWNER_NOT_TESTED")
