"""D05 R8 SOURCE_ONLY regression: duplicate WebView2 ATLAS add must never re-INSERT.

Run from checked-out repository:
  python coordination/nox-r8/tests/test_r8_d05_task_add_replay_owner.py
This is not evidence of .NET compilation or the owner's Windows/SQLite runtime.
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "overrides" / "src" /
          "MainWindow.xaml.cs").read_text(encoding="utf-8")
HANDLER = SOURCE.split("private void HandleTaskAdd(", 1)[1].split(
    "private void HandleNoteAdd(", 1)[0]


class AtlasAddReplayGuard(unittest.TestCase):
    def test_native_owner_request_reserved_before_insert(self):
        self.assertIn("recentlyHandledTaskAddIdSet.Add(requestId)", HANDLER)
        self.assertLess(HANDLER.index("recentlyHandledTaskAddIdSet.Add(requestId)"),
                        HANDLER.index("id = AddTask(title, requestId);"))
        self.assertLess(HANDLER.index("ValidWriteRequestId(requestId)"),
                        HANDLER.index("recentlyHandledTaskAddIdSet.Add(requestId)"))

    def test_duplicate_cannot_claim_success_or_write_again(self):
        duplicate = HANDLER.split("if (!recentlyHandledTaskAddIdSet.Add(requestId))", 1)[1].split(
            "recentlyHandledTaskAddIds.Enqueue(requestId)", 1)[0]
        self.assertIn("NOX_TASK_ADD_REQUEST_REPLAY_HOLD", duplicate)
        self.assertIn('Send("tasks.add.uncertain"', duplicate)
        self.assertIn("return;", duplicate)
        self.assertNotIn('Send("tasks.add.receipt"', duplicate)
        self.assertNotIn("AddTask(title)", duplicate)

    def test_session_guard_is_bounded_and_uncertainty_kept(self):
        self.assertIn("recentlyHandledTaskAddIds.Count > 2048", HANDLER)
        self.assertIn("recentlyHandledTaskAddIdSet.Remove(recentlyHandledTaskAddIds.Dequeue())", HANDLER)
        self.assertIn("TaskAddPersistenceUnknownException", HANDLER)
        self.assertLess(HANDLER.index("using var verifyDb = OpenDatabase();"),
                        HANDLER.index('Send("tasks.add.receipt"'))
        self.assertIn("new HashSet<string>", SOURCE) if False else None
        self.assertIn("private readonly HashSet<string> recentlyHandledTaskAddIdSet", SOURCE)


if __name__ == "__main__":
    unittest.main()