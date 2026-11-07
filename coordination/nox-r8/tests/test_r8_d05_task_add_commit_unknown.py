"""D05 R8 SOURCE_ONLY: ATLAS task ADD commit-unknown must not be a false denial.
This checks the original native source/owner HTML; not Windows IPC or SQLite runtime.
Run: python coordination/nox-r8/tests/test_r8_d05_task_add_commit_unknown.py
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "overrides/src"
cs = (root / "MainWindow.xaml.cs").read_text(encoding="utf-8")
html = (root / "index.html").read_text(encoding="utf-8")
add = cs.split("private long AddTask(string title)", 1)[1].split("private void HandleTaskToggle(", 1)[0]
handler = cs.split("private void HandleTaskAdd(", 1)[1].split("private void HandleNoteAdd(", 1)[0]
uncertain_ui = html.split("case 'tasks.add.uncertain':", 1)[1].split("case 'tasks.add.denied':", 1)[0]
assert "db.BeginTransaction()" in add
assert "cmd.Transaction = tx;" in add and "idQuery.Transaction = tx;" in add
assert add.index("commitAttempted = true;") < add.index("tx.Commit();")
assert "TaskAddPersistenceUnknownException" in add
assert "NOX_TASK_ADD_COMMIT_UNKNOWN_HOLD" in add
assert 'catch (TaskAddPersistenceUnknownException ex)' in handler
assert handler.index('Send("tasks.add.uncertain"') < handler.index('Send("tasks.add.receipt"')
assert handler.index("using var verifyDb = OpenDatabase();") < handler.index('Send("tasks.add.receipt"')
assert "NOX_TASK_ADD_READBACK_UNKNOWN_HOLD" in handler
assert handler.index('Send("tasks.add.receipt"') < handler.rindex("RefreshTasksBestEffort();")
assert "v?.requestId===pendingTask.requestId" in uncertain_ui
assert "pendingTask.uncertain=true" in uncertain_ui
assert "$('taskAdd').disabled=true" in uncertain_ui
assert "pendingTask=null" not in uncertain_ui
assert "post('tasks.add'" not in uncertain_ui
print("D05 ATLAS task ADD commit-before-ACK/uncertain owner interlock SOURCE_ONLY PASS")
