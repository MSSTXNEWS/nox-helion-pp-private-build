"""D05 source-only LEARN.request commit-unknown guard, not Windows or Qwen proof.

Run: python coordination/nox-r8/tests/test_r8_d05_learn_request_uncertain.py
"""
from pathlib import Path
import sqlite3

HERE = Path(__file__).resolve().parent
PATHS = (
    HERE.parent / "overrides" / "src" / "MainWindow.xaml.cs",
    HERE / "src" / "MainWindow.xaml.cs",
)
found = [path for path in PATHS if path.is_file()]
assert len(found) == 1, "D05_SOURCE_MISSING_OR_AMBIGUOUS_HOLD"
native = found[0].read_text(encoding="utf-8")
handler = native.split("    private void HandleLearnRequest(", 1)[1].split(
    "    private void HandleLearnCancel(", 1)[0]
request = native.split("    private void RequestLearn(", 1)[1].split(
    "    // D05 owner STOP:", 1)[0]
assert handler.index("catch (LearnRequestPersistenceUnknownException ex)") < handler.index("catch (Exception)")
assert 'state = "PERSISTENCE_UNKNOWN_HOLD"' in handler
assert '"NOX_LEARN_REQUEST_HOLD"' in handler
assert 'catch (InvalidOperationException ex) when (ex.Message == "NOX_LEARN_EXISTING_MODEL_MISMATCH_HOLD")' in handler
assert "bool commitAttempted = false;" in request
assert request.count("commitAttempted = true;") == 2
assert request.count("tx.Commit();") == 2
assert request.index("commitAttempted = true;") < request.index("tx.Commit();")
assert request.index('tx.Commit();\n        }\n        // A queued request') < request.index('Send("learn.receipt", new { requestId, id, model')
assert "throw new LearnRequestPersistenceUnknownException(" in request
assert 'ex.Message == "NOX_LEARN_EXISTING_MODEL_MISMATCH_HOLD"' in request

# Isolated SQLite fixture: a post-COMMIT failure does not mean the owner
# consent was lost. A replay finds the prior pending row rather than inserting
# another job. This is not an execution of native WPF consent code.
db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE learn_requests(id INTEGER PRIMARY KEY, owner_sid TEXT, model TEXT, state TEXT)")
db.execute("CREATE UNIQUE INDEX pending_owner ON learn_requests(owner_sid) WHERE state='AWAITING_VERIFIED_WORKER'")
db.execute("BEGIN")
db.execute("INSERT INTO learn_requests(owner_sid, model, state) VALUES(?,?,?)",
           ("owner-a", "nox-qwen-clean:latest", "AWAITING_VERIFIED_WORKER"))
db.commit()
readback_failed = True  # injected connection/readback exception after COMMIT
assert readback_failed
persisted = db.execute("SELECT id FROM learn_requests WHERE owner_sid=? AND state=?",
    ("owner-a", "AWAITING_VERIFIED_WORKER")).fetchone()
assert persisted
replay = db.execute("SELECT id FROM learn_requests WHERE owner_sid=? AND state=?",
    ("owner-a", "AWAITING_VERIFIED_WORKER")).fetchone()
assert replay == persisted
assert db.execute("SELECT COUNT(*) FROM learn_requests").fetchone()[0] == 1
assert db.execute("SELECT COUNT(*) FROM learn_requests WHERE owner_sid='owner-b'").fetchone()[0] == 0
print("D05 LEARN.request uncertain-outcome source + isolated SQLite replay PASS; Windows NOT_TESTED")
