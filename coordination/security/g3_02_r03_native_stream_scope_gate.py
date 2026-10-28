"""NOX G3-02 R03 independent source-only P02 stream scope + revocation gate.

Read one immutable owner source via git show <SHA>:<PATH>, then pass its path.
Never promotes source syntax checks to Windows acceptance.
"""
from __future__ import annotations
import ast
import json
import pathlib
import sys
import unittest

FIELDS = ("tenant", "principal", "chat_id")


def inspect(source):
    try:
        root = ast.parse(source)
    except (SyntaxError, TypeError, ValueError):
        return {"status": "HOLD", "findings": ["INVALID_SOURCE"]}
    owner = next((n for n in root.body if isinstance(n, ast.ClassDef)
                  and n.name == "ExistingP02Adapter"), None)
    chat = next((n for n in owner.body if isinstance(n, ast.FunctionDef)
                 and n.name == "chat"), None) if owner else None
    if chat is None:
        return {"status": "HOLD", "findings": ["PINNED_OWNER_CHAT_MISSING"]}
    calls = [n for n in ast.walk(chat) if isinstance(n, ast.Call)]
    emits = [n for n in calls if isinstance(n.func, ast.Attribute)
             and isinstance(n.func.value, ast.Name)
             and n.func.value.id == "self" and n.func.attr == "event_sink"]
    writes = [n for n in calls if isinstance(n.func, ast.Attribute)
              and n.func.attr == "add_message"]
    issues = []
    if not emits:
        issues.append("STREAM_PUBLISHER_MISSING")
    for emit in emits:
        arg = emit.args[0] if len(emit.args) == 1 else None
        values = {}
        if isinstance(arg, ast.Dict):
            values = {k.value: v for k, v in zip(arg.keys, arg.values)
                      if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        scoped = all(isinstance(values.get(field), ast.Attribute)
                     and isinstance(values[field].value, ast.Name)
                     and values[field].value.id == "session"
                     and values[field].attr == field for field in FIELDS)
        if not scoped:
            issues.append("STREAM_EVENT_SCOPE_NOT_ATTESTED")
            break
    loops = [n for n in ast.walk(chat) if isinstance(n, (ast.For, ast.AsyncFor))]
    stream_end = max((n.end_lineno or n.lineno for n in loops), default=0)
    first_write = min((n.lineno for n in writes), default=0)
    native_rechecks = [n for n in calls if stream_end < n.lineno < first_write
                       and isinstance(n.func, ast.Attribute)
                       and n.func.attr in ("reauthorize", "authorize_native_session",
                                           "revalidate_native_session")]
    if not writes:
        issues.append("EXISTING_SQLITE_WRITER_NOT_FOUND")
    elif not native_rechecks:
        issues.append("POST_STREAM_NATIVE_RECHECK_NOT_ATTESTED")
    return {"status": "HOLD" if issues else "SOURCE_PATTERN_ONLY_NOT_ACCEPTED",
            "findings": issues, "events": len(emits), "writes": len(writes)}


PREFIX = """class ExistingP02Adapter:
    def chat(self, session, args):
        for chunk in self.client.stream("model", []):
            delta = chunk["delta"]
"""
BAD = """            self.event_sink({"route":"helion.chat","delta":delta})
        self.store.add_message(session.tenant,session.principal,session.chat_id,"assistant","answer")
"""
GOOD = """            self.event_sink({"tenant":session.tenant,"principal":session.principal,
                             "chat_id":session.chat_id,"delta":delta})
        self.reauthorize(session)
        self.store.add_message(session.tenant,session.principal,session.chat_id,"assistant","answer")
"""


class SourceOnlyRegressions(unittest.TestCase):
    def test_unscoped_frame_and_late_sqlite_write(self):
        self.assertEqual(set(inspect(PREFIX + BAD)["findings"]),
                         {"STREAM_EVENT_SCOPE_NOT_ATTESTED",
                          "POST_STREAM_NATIVE_RECHECK_NOT_ATTESTED"})

    def test_page_supplied_identity_not_native_scope(self):
        fake = GOOD.replace("session.tenant", 'args["tenant"]').replace(
            "session.principal", 'args["principal"]').replace(
            "session.chat_id", 'args["chat_id"]')
        self.assertIn("STREAM_EVENT_SCOPE_NOT_ATTESTED",
                      inspect(PREFIX + fake)["findings"])

    def test_scoped_frame_without_recheck_still_holds(self):
        candidate = GOOD.replace("        self.reauthorize(session)\n", "")
        self.assertEqual(inspect(PREFIX + candidate)["findings"],
                         ["POST_STREAM_NATIVE_RECHECK_NOT_ATTESTED"])

    def test_guard_pattern_is_not_windows_accepted(self):
        self.assertEqual(inspect(PREFIX + GOOD)["status"],
                         "SOURCE_PATTERN_ONLY_NOT_ACCEPTED")

    def test_comments_cannot_be_reauthorization(self):
        candidate = BAD.replace("        self.store.add_message",
                                "        # reauthorize(session)\n        self.store.add_message")
        self.assertEqual(inspect(PREFIX + candidate)["status"], "HOLD")

    def test_missing_or_invalid_code_fails_closed(self):
        self.assertEqual(inspect("def f(): pass")["status"], "HOLD")
        self.assertEqual(inspect("def broken(\n")["status"], "HOLD")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        unittest.main(argv=[sys.argv[0]], verbosity=2)
    elif len(sys.argv) == 2:
        report = inspect(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
        print(json.dumps(report, sort_keys=True))
        raise SystemExit(2 if report["status"] == "HOLD" else 0)
    else:
        raise SystemExit("usage: gate.py --self-test | EXACT_OWNER_SOURCE.py")
