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
