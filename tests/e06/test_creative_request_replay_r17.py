"""E06 R17 SOURCE-only Creative Worker request replay regression.
Owner: W1.03 E06 QA. TestID: E06-W1-03-R17-CREATIVE-REQUEST-REPLAY.
Pinned owner blob: c9c8bf947ca941c25edf92d8995dc5bbccbba9a0.
Not Windows E2E. Read-only. Run from PR162 checkout.
"""
import os
import re
import unittest
from pathlib import Path

PATH = Path(os.getenv("NOX_CREATIVE_BRIDGE_PATH", "integrations/creative/bridge/CreativeHostBridge.cs"))

class CreativeRequestReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PATH.read_text(encoding="utf-8-sig")
        i = cls.source.index("private async Task DispatchCreativeAsync(")
        j = cls.source.index("// Runtime payload consistency check", i)
        cls.method = cls.source[i:j]

    def guard(self):
        return re.search(
            r"if\s*\(\s*!\s*_creativePending\.TryAdd\(requestId!,\s*0\)\s*\)"
            r"\s*\{(?:(?!\}).)*?\breturn\s*;\s*\}", self.method, flags=re.S)

    def test_01_guid_gate_retained(self):
        self.assertIn('Guid.TryParseExact(requestId, "D", out _)', self.method)

    def test_02_worker_sha_gate_retained(self):
        self.assertIn("HoldApprovedCreativeWorker(path)", self.source)
        self.assertIn("SHA256.HashData(handle)", self.source)

    def test_03_atomic_duplicate_admission(self):
        self.assertIsNotNone(self.guard(), "RED: unchecked TryAdd permits duplicate dispatch")

    def test_04_duplicate_cannot_reach_worker(self):
        g = self.guard()
        self.assertIsNotNone(g, "RED: duplicate guard missing")
        self.assertLess(g.end(), self.method.index("EnsureCreativeWorkerAsync()"))

    def test_05_duplicate_cannot_clear_first_request(self):
        g = self.guard()
        self.assertIsNotNone(g, "RED: failed duplicate can clear original pending request")
        self.assertLess(g.end(), self.method.rindex("_creativePending.TryRemove(requestId!,out _)"))

if __name__ == "__main__":
    unittest.main()
