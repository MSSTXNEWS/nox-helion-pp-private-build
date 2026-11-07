"""B04: SQLite ambiguous-commit must not trigger duplicate retries (SOURCE_ONLY)."""
from pathlib import Path
here = Path(__file__).resolve().parent
if here.name == "tests" and here.parent.name == "nox-r8":
    root = here.parent / "overrides" / "src"
elif here.name == "r8":
    root = here / "src"
else:
    raise AssertionError("F02_SQLITE_TEST_ORIGIN_HOLD")
for name in ("MainWindow.xaml.cs", "index.html"):
    assert (root/name).is_file(), "F02_SQLITE_SOURCE_MISSING_HOLD: " + str(root/name)
cs = (root/"MainWindow.xaml.cs").read_text(encoding="utf-8")
html = (root/"index.html").read_text(encoding="utf-8")
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

# B04 integration adapter: uncertain chat COMMIT must preserve per-Persona draft and require explicit replay confirmation.
assert "const uncertainChatKeys=new Set()" in html, "B04_UNKNOWN_COMMIT_REPLAY_GUARD_HOLD"
assert "uncertainChatKeys.has(uncertainKey)&&!window.confirm(" in html, "B04_UNKNOWN_COMMIT_REPLAY_GUARD_HOLD"
assert "uncertainChatKeys.delete(uncertainKey);busy=true;" in html, "B04_UNKNOWN_COMMIT_REPLAY_GUARD_HOLD"
assert "uncertainChatKeys.add(uncertainChatKey(retry.persona,retry.raw))" in html, "B04_UNKNOWN_COMMIT_REPLAY_GUARD_HOLD"
assert "let restored=false;if(!v?.ok&&retry){" in html, "B04_UNKNOWN_COMMIT_REPLAY_GUARD_HOLD"
assert "route('reflection');return;" in html, "B04_UNKNOWN_COMMIT_REPLAY_GUARD_HOLD"
print("NOX_B04_COMMIT_UNKNOWN_SOURCE_ONLY_PASS")

# F02 isolated WAL test; no owner database, model, or user file is touched.
from tempfile import TemporaryDirectory
from contextlib import closing
import sqlite3

with TemporaryDirectory(prefix="nox-f02-r8-sqlite-") as scratch:
    dbpath = Path(scratch) / "disposable.sqlite3"
    with closing(sqlite3.connect(dbpath)) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal", "F02_SQLITE_WAL_HOLD"
        writer.execute("CREATE TABLE chat_history(id INTEGER PRIMARY KEY, persona TEXT NOT NULL, prompt TEXT NOT NULL, answer TEXT NOT NULL)")
        writer.execute("INSERT INTO chat_history(persona,prompt,answer) VALUES (?,?,?)", ("KV", "one", "committed"))
        writer.commit()
        # Verify with a separate handle while the WAL writer remains open.
        with closing(sqlite3.connect(dbpath)) as reader:
            assert reader.execute("SELECT persona,prompt,answer FROM chat_history").fetchall() == [("KV","one","committed")], "F02_SQLITE_INDEPENDENT_READBACK_HOLD"
            assert reader.execute("PRAGMA quick_check").fetchone()[0] == "ok", "F02_SQLITE_QUICK_CHECK_HOLD"
    with closing(sqlite3.connect(dbpath)) as restarted:
        assert restarted.execute("SELECT COUNT(*) FROM chat_history WHERE persona=?", ("KV",)).fetchone()[0] == 1, "F02_SQLITE_NO_DUPLICATE_AFTER_REOPEN_HOLD"
print("F02 disposable SQLite WAL commit/independent readback/reopen: PASS; owner-PC NOT_TESTED")
