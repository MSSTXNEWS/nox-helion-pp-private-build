#!/usr/bin/env python3
"""B06 fail-closed SOURCE-ONLY acceptance guard for native R8 chat.

Run: python coordination/nox-r8/tests/test_b06_six_check_contract.py
This checks the checked-out R8 C# source; it does NOT run Qwen or prove E07.
The native six-check selftest must still run against the exact installed EXE.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "overrides" / "src" / "MainWindow.xaml.cs"
REQUIRED_CHECK = "real_chat_after_http_stop_sqlite"

class B06NativeSixCheckContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8-sig")

    def test_six_checks_not_five(self):
        s = self.source
        self.assertRegex(s, r"checks\.Count\s*==\s*6\b",
                         "HOLD: acceptance still allows the obsolete five-check contract")
        self.assertNotRegex(s, r"checks\.Count\s*==\s*5\b",
                            "HOLD: obsolete five-check acceptance remains")

    def test_post_stop_fresh_chat_requires_sqlite_readback(self):
        s = self.source
        self.assertIn('checks["' + REQUIRED_CHECK + '"] = "PASS"', s,
                      "HOLD: missing real fresh chat after HTTP STOP")
        for token in ("WaitForGenerationStartAsync", "WaitForGenerationFinishAsync",
                      "HasSavedPrompt(resumePrompt)", "WaitForSavedChatUiReleaseAsync",
                      "lastGenerationStopped"):
            self.assertIn(token, s, "HOLD: missing post-STOP witness " + token)

    def test_no_loss_unknown_sqlite_receipt_and_owner_stop(self):
        s = self.source
        for token in ("sqliteWriteAttempted", "sqliteVerified", "sqliteUnknown",
                      "NOX_CHAT_SQLITE_COMMIT_UNKNOWN_HOLD", "activeRequestId"):
            self.assertIn(token, s, "HOLD: lost canonical safety guard " + token)

if __name__ == "__main__":
    unittest.main()
