"""C13 original OneHost/S03: generated preview must never reach either audit write."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


class OriginalS03PreviewPersistenceTest(unittest.TestCase):
    def test_both_existing_s03_write_boundaries_strip_preview_not_proof(self):
        import nox_selfbuilder.onehost_builder as original

        class AuditQueue:
            def __init__(self):
                self.writes = []
                self.authority = []

            def record(self, session, task_id, state, result, *,
                       expected_epoch, permission):
                # Serialize as existing NativeWorkQueue.record does before S03.
                self.authority.append((session, task_id, expected_epoch, permission))
                self.writes.append((state, json.loads(json.dumps(result))))
                return True

            def submit_source(self, session, task_id, callback):
                # Existing NativeWorkQueue._start also records callback output.
                result = callback()
                self.record(session, task_id, result["status"], result,
                            expected_epoch=1, permission="selfbuilder.propose")
                return {"status": "QUEUED", "task_id": task_id}

        preview = {"files": [{"path": "src/sample.py",
                              "source": "C13_TRANSIENT_SOURCE_SENTINEL",
                              "diff": "C13_TRANSIENT_DIFF_SENTINEL",
                              "tests": ["C13_TRANSIENT_TEST_SENTINEL"]}]}
        receipt = {"source_head": "a" * 40, "patch_sha256": "b" * 64,
                   "status": "CANDIDATE_REVIEW_REQUIRED",
                   "review_required": True, "preview": preview}

        class FakeWorker:
            def __init__(self, host, *, workspace):
                self.host = host

            def tick(self):
                self.host.record_result("S03-7", "CANDIDATE_REVIEW_REQUIRED", receipt)
                return SimpleNamespace(status="CANDIDATE_REVIEW_REQUIRED",
                                       receipt=receipt)

        queue = AuditQueue()
        existing_service = SimpleNamespace(queue=queue, workspace=ROOT,
                                           stop_epoch=lambda: 1)
        with patch.object(original, "EvolutionWorker", FakeWorker):
            ack = original.OneHostSelfBuilder._submit_payload(
                existing_service, "owner-session", 7, {"source_head": "a" * 40})

        self.assertEqual(len(queue.writes), 2)
        self.assertEqual(queue.authority,
                         [("owner-session", 7, 1, "selfbuilder.propose")] * 2)
        for state, stored in queue.writes:
            self.assertEqual(state, "CANDIDATE_REVIEW_REQUIRED")
            durable = stored["receipt"]
            self.assertNotIn("preview", durable)
            self.assertEqual(durable["source_head"], "a" * 40)
            self.assertEqual(durable["patch_sha256"], "b" * 64)
            self.assertTrue(durable["review_required"])
            self.assertNotIn("C13_TRANSIENT_", json.dumps(stored))
        self.assertEqual(receipt["preview"], preview)  # memory untouched
        self.assertEqual(ack["task_id"], 7)
        self.assertIs(ack["ack"], True)


if __name__ == "__main__":
    unittest.main()
