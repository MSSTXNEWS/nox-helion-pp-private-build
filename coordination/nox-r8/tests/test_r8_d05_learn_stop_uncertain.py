"""D05 native LEARN STOP commit-unknown source contract; not Windows E2E.

Run: python coordination/nox-r8/tests/test_r8_d05_learn_stop_uncertain.py
Works in the source repository and original Windows-CI copied-r8 layout.
"""
from pathlib import Path
import re
import sqlite3

root = Path(__file__).resolve().parent
candidates = (root.parent / "overrides" / "src" / "MainWindow.xaml.cs", root / "src" / "MainWindow.xaml.cs")
sources = [p for p in candidates if p.is_file()]
assert len(sources) == 1, "D05_NATIVE_SOURCE_MISSING_OR_AMBIGUOUS_HOLD"
native = sources[0].read_text(encoding="utf-8")

def method(name):
    start = re.search(r"private void " + re.escape(name) + r"\([^)]*\)\s*\{", native)
    assert start, "D05_METHOD_MISSING_HOLD:" + name
    return native[start.end():].split("\n    private ", 1)[0]

stop, unknown = method("CancelLearnRequest"), method("SendLearnStopUnknown")
assert "bool commitAttempted = false;" in stop
assert stop.index("commitAttempted = true;") < stop.index("tx.Commit();")
assert "if (commitAttempted)" in stop
assert 'SendLearnStopUnknown(requestId, "NOX_LEARN_STOP_COMMIT_UNKNOWN_HOLD")' in stop
assert 'SendLearnStopUnknown(requestId, "NOX_LEARN_STOP_READBACK_UNKNOWN_HOLD")' in stop
assert 'Send("learn.denied", new { requestId, reason = "NOX_LEARN_STOP_PRECOMMIT_HOLD" })' in stop
assert stop.index("tx.Commit();") < stop.index("using var verifyDb = OpenDatabase();") < stop.index('Send("learn.receipt",')
assert "owner_sid=$sid" in stop and "state='AWAITING_VERIFIED_WORKER'" in stop
assert 'state = "PERSISTENCE_UNKNOWN_HOLD"' in unknown
assert 'Send("learn.denied"' not in unknown
assert "RefreshLearnQueueBestEffort();" in unknown and "RefreshLearnQueueBestEffort();" in stop
assert "catch (Exception)" in stop[stop.index('Send("learn.receipt",'):]

# Independent SQLite-only fixture exercises intent/owner isolation and replay,
# not the WPF handler, Ollama stream or the owner's real database.
db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE learn_requests(owner_sid TEXT, state TEXT)")
db.executemany("INSERT INTO learn_requests VALUES (?,?)", [
    ("owner-a", "AWAITING_VERIFIED_WORKER"), ("owner-a", "AWAITING_VERIFIED_WORKER"),
    ("owner-b", "AWAITING_VERIFIED_WORKER")])
sql = "UPDATE learn_requests SET state='CANCELLED_BY_OWNER' WHERE owner_sid=? AND state='AWAITING_VERIFIED_WORKER'"
assert db.execute(sql, ("owner-a",)).rowcount == 2
db.commit()
assert db.execute(sql, ("owner-a",)).rowcount == 0
db.commit()
assert db.execute("SELECT COUNT(*) FROM learn_requests WHERE owner_sid=? AND state='AWAITING_VERIFIED_WORKER'", ("owner-a",)).fetchone()[0] == 0
assert db.execute("SELECT COUNT(*) FROM learn_requests WHERE owner_sid=?", ("owner-b",)).fetchone()[0] == 1
print("D05 LEARN STOP SOURCE_ONLY: commit/readback unknown guards + owner-isolated replay fixture PASS; owner Windows NOT_TESTED")
