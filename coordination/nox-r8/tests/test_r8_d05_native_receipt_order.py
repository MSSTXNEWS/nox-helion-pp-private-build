"""SOURCE_ONLY safeguards for D05 WPF receipts after persisted SQLite mutations.

Run with: python coordination/nox-r8/tests/test_r8_d05_native_receipt_order.py
This cannot substitute for Windows native IPC/SQLite/owner acceptance.
"""
from pathlib import Path
import re

SOURCE = (Path(__file__).resolve().parents[1] / "overrides/src/MainWindow.xaml.cs").read_text(encoding="utf-8")

def method(name):
    match = re.search(r"\\bprivate void " + re.escape(name) + r"\\([^)]*\\)\\s*\\{", SOURCE)
    assert match is not None, "MISSING_METHOD:" + name
    body = SOURCE[match.end():].split("\\n    private ", 1)[0]
    return body

for method_name, receipt, refresh, inline in (
    ("HandleTaskToggle", "tasks.toggle.receipt", "RefreshTasksBestEffort();", 'Send("tasks", ReadTasks());'),
    ("HandleTaskAdd", "tasks.add.receipt", "RefreshTasksBestEffort();", 'Send("tasks", ReadTasks());'),
    ("HandleNoteAdd", "notes.add.receipt", "RefreshNotesBestEffort();", 'Send("notes", ReadNotes());'),
    ("HandleNoteDelete", "notes.delete.receipt", "RefreshNotesBestEffort();", 'Send("notes", ReadNotes());'),
):
    body = method(method_name)
    receipt_index = body.index('Send("' + receipt + '"')
    refresh_index = body.index(refresh)
    assert receipt_index < refresh_index, "FALSE_DENIAL_ON_POST_COMMIT_REFRESH:" + method_name
    assert inline not in body, "UNGUARDED_REFRESH:" + method_name
    assert "saved = true" in body[:refresh_index], "UNVERIFIED_SUCCESS:" + method_name

for refresh, inline in (
    ("RefreshTasksBestEffort", 'Send("tasks", ReadTasks());'),
    ("RefreshNotesBestEffort", 'Send("notes", ReadNotes());'),
):
    body = method(refresh)
    assert "try {" in body and inline in body and "catch (Exception)" in body, refresh

assert 'backupVerified = true' in method("HandleNoteDelete")
assert "NOX_NOTE_DELETE_READBACK_HOLD" in method("HandleNoteDelete")
assert "NOX_TASK_TOGGLE_SQLITE_READBACK_HOLD" in method("HandleTaskToggle")
assert "NOX_NOTE_SQLITE_READBACK_HOLD" in method("HandleNoteAdd")
assert "NOX_TASK_SQLITE_READBACK_HOLD" in method("HandleTaskAdd")
print("D05 R8 native task/note receipts: 4 routes + 2 optional refresh handlers SOURCE_ONLY PASS")
