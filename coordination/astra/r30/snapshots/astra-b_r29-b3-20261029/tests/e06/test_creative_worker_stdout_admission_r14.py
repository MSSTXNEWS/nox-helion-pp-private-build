"""E06 R14: exact-source, read-only Creative Worker stdout trust regression.

Owner: independent E06 QA only. Run against a checkout of PR #162:
  python -m unittest discover -s tests/e06 -p test_creative_worker_stdout_admission_r14.py -v

This is a SOURCE gate, not a Windows runtime or installed EXE acceptance. The
negative tests intentionally fail against the affected CreativeHostBridge.cs
until the owner isolates bad output per frame and validates response fields.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import unittest

ROOT = Path(os.environ.get("NOX_SOURCE_ROOT", Path(__file__).resolve().parents[2])).resolve()
BRIDGE = ROOT / "integrations/creative/bridge/CreativeHostBridge.cs"


def stdout_frame_block(source: str) -> str:
    """Extract the actual bounded stdout consumer, excluding its outer task."""
    anchor = "var reader = new BoundedCreativeLineReader(process.StandardOutput);"
    if source.count(anchor) != 1:
        raise AssertionError("CREATIVE_BOUNDED_STDOUT_READER_MISSING")
    start = source.index("while (true)", source.index(anchor))
    start = source.index("{", start)
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError("CREATIVE_STDOUT_UNBALANCED_LOOP")

class CreativeWorkerStdoutAdmissionR14(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not BRIDGE.is_file() or BRIDGE.is_symlink():
            raise AssertionError("EXACT_CREATIVE_OWNER_SOURCE_MISSING")
        cls.source = BRIDGE.read_text(encoding="utf-8")
        cls.frame = stdout_frame_block(cls.source)

    def test_original_worker_launch_trust_lock_remains(self):
        self.assertIn("HoldApprovedCreativeWorker(path)", self.source)
        self.assertIn("CREATIVE_WORKER_SHA256_MISMATCH", self.source)
        self.assertIn("CREATIVE_WORKER_PARENT_REPARSE_HOLD", self.source)

    def test_original_stdout_size_budget_remains(self):
        self.assertIn("line.Length >= 8_000_000", self.source)
        self.assertIn("if (oversized)", self.frame)
        self.assertNotIn("StandardOutput.ReadLineAsync(", self.source)

    def test_frame_json_parse_exception_cannot_end_reader(self):
        # Catch must be within the read-loop body, NOT the surrounding Task.Run.
        self.assertIn("JsonDocument.Parse(line)", self.frame)
        self.assertRegex(self.frame, r"\bcatch\s*(?:\(|\{)")

    def test_response_root_is_object_before_try_get_property(self):
        # JsonElement.TryGetProperty throws for arrays/null/scalars.
        parse = self.frame.index("JsonDocument.Parse(line)")
        request = self.frame.index('TryGetProperty("request_id"')
        shape_guard = re.search(
            r"RootElement\.ValueKind\s*(?:==\s*JsonValueKind\.Object|"
            r"!=\s*JsonValueKind\.Object)", self.frame[parse:request],
        )
        self.assertIsNotNone(shape_guard, "CREATIVE_STDOUT_ROOT_SHAPE_UNGUARDED")

    def test_ok_without_data_is_a_managed_error(self):
        # Missing data is expected to be rejected without terminating stdout.
        self.assertNotIn('doc.RootElement.GetProperty("data")', self.frame)
        self.assertIn('TryGetProperty("data"', self.frame)

    def test_bounded_reader_discards_overflow_before_allocating_full_line(self):
        self.assertIn("private sealed class BoundedCreativeLineReader", self.source)
        self.assertIn("new char[4096]", self.source)
        self.assertIn("line.Clear();", self.source)
        self.assertIn("ReadAsync(_chunk.AsMemory())", self.source)
        self.assertIn("if (ch == '\\n')", self.source)

    def test_stderr_drained_in_fixed_chunks(self):
        self.assertIn("process.StandardError.ReadAsync(discard.AsMemory())", self.source)
        self.assertNotIn("StandardError.ReadLineAsync(", self.source)

    def test_worker_stderr_not_forwarded_to_webview(self):
        self.assertIn("Do not surface arbitrary worker stderr", self.source)


if __name__ == "__main__":
    unittest.main()
