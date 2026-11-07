"""B04: SQLite ambiguous-commit must not trigger duplicate retries (SOURCE_ONLY)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
# Run the repository test against the original override, and the Windows CI
# copy against the exact pinned-overlaid r8/src. Do not fall back to a stale tree.
here = Path(__file__).resolve().parent
if here.name == "tests" and here.parent.name == "nox-r8":
    src = here.parent / "overrides" / "src"
elif here.name == "r8":
    src = here / "src"
else:
    raise AssertionError("F02_IPC_SQLITE_TEST_ORIGIN_HOLD")
for name in ("MainWindow.xaml.cs", "index.html"):
    assert (src / name).is_file(), "F02_IPC_SQLITE_SOURCE_MISSING_HOLD: " + str(src / name)
cs = (src / "MainWindow.xaml.cs").read_text(encoding="utf-8")
html = (src / "index.html").read_text(encoding="utf-8")
gen = cs.split("private async Task Generate(", 1)[1].split("private void PersistChat(", 1)[0]
for fragment in ("bool sqliteWriteAttempted = false, sqliteVerified = false;",
                 "sqliteWriteAttempted = true;", "PersistChat(prompt, answer.ToString(), persona);",
                 "sqliteVerified = true;", "bool sqliteUnknown = sqliteWriteAttempted && !sqliteVerified;",
                 "NOX_CHAT_SQLITE_COMMIT_UNKNOWN_HOLD",
                 'state = sqliteUnknown ? "SQLITE_UNKNOWN" : "ERROR"',
                 "stopped = false, sqliteUnknown"):
    assert fragment in gen, "B04_COMMIT_UNKNOWN_MISSING: " + fragment
assert gen.index("sqliteWriteAttempted = true;") < gen.index("PersistChat(prompt, answer.ToString(), persona);") < gen.index("sqliteVerified = true;")
assert "else if(v?.sqliteUnknown===true)" in html
assert "Проверьте историю перед повторной отправкой." in html
assert "lastAnswer='';" in html
# Ambiguous COMMIT is not permission to automatically re-POST a chat.
# Native WebView2 must prefer the warning to a generic success banner.
complete = html.split("case 'complete':", 1)[1].split("case 'error':", 1)[0]
assert complete.index("v?.sqliteUnknown===true") < complete.index("else if(v?.ok)"), "F02_SQLITE_UNCERTAIN_PRIORITY_HOLD"
assert "post('chat'" not in complete, "F02_SQLITE_UNCERTAIN_DUPLICATE_RETRY_HOLD"
persist = cs.split("private void PersistChat(", 1)[1].split("private object ReadHistory(", 1)[0]
assert persist.index("cmd.ExecuteNonQuery() != 1") < persist.index("using var verifyDb = OpenDatabase()")
assert "NOX_CHAT_SQLITE_READBACK_HOLD" in persist, "F02_SQLITE_ACK_BEFORE_READBACK_HOLD"
# Real WAL COMMIT/readback/reopen on an isolated temp SQLite database;
# not the owner's data, not real Qwen or release acceptance.
with TemporaryDirectory(prefix="nox-r8-f02-isolated-") as tmp:
    dbpath = Path(tmp) / "chat.sqlite3"
    with sqlite3.connect(dbpath) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE chat_history(id INTEGER PRIMARY KEY, prompt TEXT, answer TEXT, persona TEXT)")
        db.execute("INSERT INTO chat_history(prompt,answer,persona) VALUES(?,?,?)", ("first","persisted","KV"))
        db.commit()
    with sqlite3.connect(dbpath) as reader:
        assert reader.execute(
            "SELECT prompt,answer FROM chat_history WHERE persona=?", ("KV",)
        ).fetchall() == [("first", "persisted")], "F02_SQLITE_WAL_READBACK_HOLD"
    with sqlite3.connect(dbpath) as reopened:
        assert reopened.execute(
            "SELECT COUNT(*) FROM chat_history WHERE persona=?", ("KV",)
        ).fetchone()[0] == 1, "F02_SQLITE_UNKNOWN_NO_DUPLICATE_HOLD"
print("NOX_B04_COMMIT_UNKNOWN_SOURCE_ONLY_PASS; F02 isolated WAL/restart PASS; owner-PC NOT_TESTED")
