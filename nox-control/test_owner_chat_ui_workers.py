"""Regression tests for existing owner-only NOX executor status projection.
No OneHost, S03, serving model, process, or HTTP calls.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import owner_chat_ui as ui


class ExistingExecutorClaimsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "status").mkdir()
        (self.root / "state").mkdir()
        override = patch.object(ui, "ROOT", self.root)
        override.start()
        self.addCleanup(override.stop)

    def snapshot(self, workers):
        (self.root / "status/agents_t856u.json").write_text(
            json.dumps({"n": len(workers), "workers": workers}), encoding="utf-8"
        )
        return ui.workers()

    def test_two_idle_workers_without_claims_are_observed(self):
        rows = [
            {"id": "nox-agent-01", "status": "idle"},
            {"id": "nox-agent-02", "status": "idle"},
        ]
        result = self.snapshot(rows)
        self.assertEqual(result["state"], "OBSERVED")
        self.assertEqual([r["task_id"] for r in result["workers"]], [None, None])

    def test_one_busy_claim_two_idle_workers_are_observed(self):
        rows = [
            {"id": "nox-agent-01", "status": "idle"},
            {"id": "nox-agent-02", "status": "busy", "current_task": {"id": "S3-07"}},
            {"id": "nox-agent-03", "status": "idle"},
        ]
        result = self.snapshot(rows)
        self.assertEqual(result["state"], "OBSERVED")
        self.assertEqual([r["task_id"] for r in result["workers"]], [None, "S3-07", None])

    def test_busy_without_claim_id_is_unknown_not_success(self):
        result = self.snapshot([{"id": "nox-agent-01", "status": "busy", "current_task": {}}])
        self.assertEqual(result["state"], "UNAVAILABLE")

    def test_duplicate_busy_claims_fail_closed(self):
        result = self.snapshot([
            {"id": "nox-agent-01", "status": "busy", "current_task": {"id": "S2-07"}},
            {"id": "nox-agent-02", "status": "busy", "current_task": {"id": "S2-07"}},
        ])
        self.assertEqual(result["state"], "UNAVAILABLE")

    def test_idle_with_unexpected_claim_is_not_accepted(self):
        result = self.snapshot([
            {"id": "nox-agent-01", "status": "idle", "current_task": {"id": "S1-01"}}
        ])
        self.assertEqual(result["state"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
