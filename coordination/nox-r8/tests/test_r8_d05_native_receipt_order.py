"""SOURCE_ONLY safeguards for D05 WPF receipts after persisted SQLite mutations.

Run with: python coordination/nox-r8/tests/test_r8_d05_native_receipt_order.py
This cannot substitute for Windows native IPC/SQLite/owner acceptance.
"""
from pathlib import Path
import re

SOURCE = (Path(__file__).resolve().parents[1] / "overrides/src/MainWindow.xaml.cs").read_text(encoding="utf-8")

def method(name):
    match = re.search(r"\bprivate void " + re.escape(name) + r"\([^)]*\)\s*\{", SOURCE)
    assert match is not None, "MISSING_METHOD:" + name
    body = SOURCE[match.end():].split("\n    private ", 1)[0]
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
assert "UPDATE tasks SET complete=$complete WHERE id=$id" in method("HandleTaskToggle")
assert "NOX_TASK_TOGGLE_COMMIT_UNKNOWN_HOLD" in method("HandleTaskToggle")
assert "tasks.toggle.uncertain" in method("HandleTaskToggle")
assert method("HandleTaskToggle").index("tx.Commit();") < method("HandleTaskToggle").index('Send("tasks.toggle.receipt"')
assert "NOX_NOTE_SQLITE_READBACK_HOLD" in method("HandleNoteAdd")
assert "NOX_TASK_SQLITE_READBACK_HOLD" in method("HandleTaskAdd")
print("D05 R8 native task/note receipts: 4 routes + 2 optional refresh handlers SOURCE_ONLY PASS")

# D05 source-only regression: a committed rating with failed SQLite readback
# cannot be a false denial that invites the owner to submit a duplicate.
feedback = method("HandleFeedback")
assert 'catch (FeedbackPersistenceUnknownException ex)' in feedback
assert 'Send("feedback.uncertain", new { requestId, reason = ex.Message })' in feedback
assert feedback.index('catch (FeedbackPersistenceUnknownException ex)') < feedback.index('catch (SqliteException)')
save_feedback = SOURCE.split("private long SaveFeedback(", 1)[1].split("\n    // D05: owner-correlated", 1)[0]
assert "using (var tx = db.BeginTransaction())" in save_feedback
assert "cmd.Transaction = tx;" in save_feedback and "rowId.Transaction = tx;" in save_feedback
assert save_feedback.index("commitAttempted = true;") < save_feedback.index("tx.Commit();")
assert save_feedback.index("tx.Commit();") < save_feedback.index("using var verifyDb = OpenDatabase();")
assert "NOX_FEEDBACK_COMMIT_UNKNOWN_HOLD" in save_feedback
assert "NOX_FEEDBACK_READBACK_UNKNOWN_HOLD" in save_feedback
assert 'throw new FeedbackPersistenceUnknownException(' in save_feedback
html_src = (Path(__file__).resolve().parents[1] / "overrides/src/index.html").read_text(encoding="utf-8")
uncertain = html_src.split("case 'feedback.uncertain':{", 1)[1].split("case 'feedback.denied':{", 1)[0]
assert "v?.requestId!==pendingFeedback.requestId" in uncertain
assert "pendingFeedback=null;feedbackReady=false;setFeedbackEnabled(false);" in uncertain
assert "setFeedbackEnabled(true)" not in uncertain and "post('feedback'" not in uncertain
print("D05 feedback commit-unknown source contract SOURCE_ONLY PASS")
