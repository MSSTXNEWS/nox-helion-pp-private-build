"""E06 / W1.03 / R15 — read-only SOURCE-level Creative Worker stdio budget regression.

TestID: E06-W1-03-R15-CREATIVE-STDIO-PREALLOCATION-BUDGET
Owner: E06 independent security QA (not owner of product CreativeHostBridge).
Pinned source at discovery: PR #162 HEAD e86c2225ef449c8dbb9f676c9a39f3ed50c098d8
File: integrations/creative/bridge/CreativeHostBridge.cs
Git blob SHA-1: c63ac4c61cc27edbbada7e5267c209015ccc95b3

Run in an actual checkout: python -m unittest tests.e06.test_creative_stdio_bounded_reader_r15 -v
No native C#/Windows acceptance is claimed by these static source-contract tests.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

PROJECT = Path(__file__).resolve().parents[2]
BRIDGE = PROJECT / "integrations" / "creative" / "bridge" / "CreativeHostBridge.cs"
TEST_ID = "E06-W1-03-R15-CREATIVE-STDIO-PREALLOCATION-BUDGET"


def creative_reader_contract(source: str) -> str:
    begin = source.find("private async Task<Process> EnsureCreativeWorkerAsync()")
    end = source.find("private void ImportCreativeAsset(", begin)
    if begin < 0 or end <= begin:
        raise AssertionError("CREATIVE_WORKER_READER_MISSING_OR_MOVED: review owner source")
    return source[begin:end]


class CreativeWorkerBoundedStdioContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Missing current owner preimage is HOLD, not a synthetic green.
        if not BRIDGE.is_file() or BRIDGE.is_symlink():
            raise AssertionError(f"SOURCE_MISSING_OR_SYMLINK: {BRIDGE}")
        cls.source = BRIDGE.read_text(encoding="utf-8")
        cls.reader = creative_reader_contract(cls.source)

    def test_stdout_must_not_allocate_unbounded_line_before_budget_check(self):
        # StreamReader.ReadLineAsync materializes a complete attacker-influenced
        # stdout line before the next line.Length check. 8,000,000 after-the-fact
        # is not a memory/CPU budget. Use a bounded chunk/frame reader instead.
        self.assertNotRegex(
            self.reader,
            r"\bStandardOutput\s*\.\s*(?:ReadLineAsync|ReadToEndAsync)\s*\(",
            "STDOUT_PREALLOCATION_BUDGET_HOLD: unbounded stdout read; "
            "replace with fixed-size chunk reader and cap frame during accumulation",
        )

    def test_stderr_drain_must_not_allocate_unbounded_line(self):
        # Even discarded stderr lines are materialized in memory by ReadLineAsync.
        self.assertNotRegex(
            self.reader,
            r"\bStandardError\s*\.\s*(?:ReadLineAsync|ReadToEndAsync)\s*\(",
            "STDERR_PREALLOCATION_BUDGET_HOLD: drain via fixed-size chunks, "
            "do not materialize an unbounded stderr line",
        )

    def test_keep_existing_r14_frame_isolation(self):
        self.assertIn("CREATIVE_STDOUT_INVALID_JSON", self.reader)
        self.assertIn("CREATIVE_STDOUT_INVALID_SHAPE", self.reader)
        self.assertIn("CREATIVE_RESPONSE_TOO_LARGE", self.reader)

    def test_keep_existing_r13_launch_attestation(self):
        self.assertIn("HoldApprovedCreativeWorker(path)", self.reader)
        self.assertIn("CREATIVE_WORKER_SHA256_MISMATCH", self.source)
        self.assertIn("CREATIVE_WORKER_PARENT_REPARSE_HOLD", self.source)


if __name__ == "__main__":
    unittest.main()
