"""R20 W1·03 source-only regression: Creative Worker stdout EOF must fail
pending request IDs, prevent writes to a closed response channel, and preserve
previously repaired STOP/hash/stdio guards. Run on exact owner checkout:

python -m unittest discover -s tests/e06 -p test_creative_stdout_orphan_cleanup_r20.py -v

This is structural SOURCE QA, not an executed C# component or Windows test.
Product branch adoption requires manual owner review + full component tests.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

SOURCE_PATH = (
    Path(__file__).resolve().parents[2]
    / "integrations" / "creative" / "bridge" / "CreativeHostBridge.cs"
)
EXPECTED_POST_SHA256 = "e14f3777e210629fb00377cf5c507c8a6dae7407d5447127a0f20b617e0936a5"


class CreativeWorkerEofR20(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_bytes = SOURCE_PATH.read_bytes()
        cls.source = cls.source_bytes.decode("utf-8-sig")
        a = cls.source.index("private async Task DispatchCreativeAsync(")
        b = cls.source.index("// Runtime payload consistency check", a)
        cls.dispatch = cls.source[a:b]
        c = cls.source.index("private async Task<Process> EnsureCreativeWorkerAsync()")
        d = cls.source.index("private void ImportCreativeAsset", c)
        cls.worker = cls.source[c:d]

    def test_01_reader_eof_fails_orphaned_pending(self):
        self.assertIn('FailOrphanedCreativeRequests("CREATIVE_WORKER_RESPONSE_CHANNEL_CLOSED")', self.worker)
        self.assertIn("if (ReferenceEquals(_creativeWorker, process))", self.worker)
        self.assertIn("_creativeResponseReaderClosed=true", self.worker)

    def test_02_request_admitted_after_worker_selection(self):
        self.assertLess(
            self.dispatch.index("var worker=await EnsureCreativeWorkerAsync();"),
            self.dispatch.index("if (!_creativePending.TryAdd(requestId!,0))"),
        )

    def test_03_closed_reader_blocks_new_worker_writes(self):
        self.assertIn("if (_creativeResponseReaderClosed)", self.worker)
        self.assertIn("if (worker.HasExited || _creativeResponseReaderClosed)", self.dispatch)

    def test_04_exited_worker_drained_before_new_start(self):
        self.assertIn("if (_creativeWorker is {HasExited:true})", self.worker)
        self.assertIn('FailOrphanedCreativeRequests("CREATIVE_WORKER_EXITED")', self.worker)

    def test_05_existing_verified_stop_retained(self):
        self.assertIn("await worker.WaitForExitAsync(timeout.Token)", self.source)
        self.assertIn('error="CREATIVE_STOP_NOT_CONFIRMED"', self.source)

    def test_06_existing_binary_hash_guard_retained(self):
        self.assertIn("SHA256.HashData(handle)", self.source)
        self.assertIn("HoldApprovedCreativeWorker(path)", self.source)

    def test_07_existing_bounded_stdout_retained(self):
        self.assertIn("class BoundedCreativeLineReader", self.source)
        self.assertIn("var (line, oversized) = await reader.ReadAsync()", self.source)

    def test_08_exact_owner_source_sha256(self):
        self.assertEqual(hashlib.sha256(self.source_bytes).hexdigest(), EXPECTED_POST_SHA256)


if __name__ == "__main__":
    unittest.main(verbosity=2)
