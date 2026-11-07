"""B04: SQLite ambiguous-commit must not trigger duplicate retries (SOURCE_ONLY)."""
from pathlib import Path
root = Path(__file__).resolve().parent / "src"
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
print("NOX_B04_COMMIT_UNKNOWN_SOURCE_ONLY_PASS")
