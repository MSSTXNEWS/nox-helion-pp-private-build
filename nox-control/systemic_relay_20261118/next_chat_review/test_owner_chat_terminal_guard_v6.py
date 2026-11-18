"""Source-only assertions for the dash-only chat terminal guard, no network/native calls."""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from owner_chat_terminal_guard_v6 import ANCHORS, EXPECTED_INPUT_SHA256, prepare

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "nox-v24-chat-nonempty-current.js"


class ChatTerminalGuardTests(unittest.TestCase):
    def test_exact_existing_candidate_and_all_unique_anchors(self):
        raw = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_INPUT_SHA256)
        for old, _ in ANCHORS:
            self.assertEqual(raw.decode("utf-8").count(old), 1)
        result = prepare(raw)
        self.assertNotEqual(result, raw)
        self.assertEqual(len(result), len(raw) + sum(len(new.encode()) - len(old.encode()) for old, new in ANCHORS))
        text = result.decode("utf-8")
        self.assertIn("HOLD_CHAT_EMPTY_RESPONSE", text)
        self.assertIn("done?.status === 'done' && noSubstantiveReply(result)", text)
        self.assertIn("if (noSubstantiveReply(result)) { out.body.textContent = notice;", text)
        self.assertIn("out.box.dataset.source = 'SYSTEM_NOTICE';", text)
        self.assertIn("else if (noSubstantiveReply(result)) out.body.textContent", text)
        self.assertIn("const noSubstantiveReply = value =>", text)
        self.assertIn("/^[\\u2014\\u2013-]+$/", text)

    def test_bad_pin_or_anchor_fails_closed(self):
        raw = SOURCE.read_bytes()
        with self.assertRaisesRegex(ValueError, "SOURCE_PIN"):
            prepare(raw, "0" * 64)
        with self.assertRaisesRegex(ValueError, "SOURCE_PIN"):
            prepare(raw + b"\n", EXPECTED_INPUT_SHA256)
        candidate = prepare(raw)
        with self.assertRaisesRegex(ValueError, "SOURCE_PIN"):
            prepare(candidate, EXPECTED_INPUT_SHA256)


if __name__ == "__main__":
    unittest.main()
