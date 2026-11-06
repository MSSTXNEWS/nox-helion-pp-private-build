"""D05 source regression on original P04 polling. No real GPU/SQLite/E07."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from src.nox_selfbuilder.background_forge import ExistingP04Background, ForgeHold

class D05SnapshotOwnerResultGate(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.path = root / "events.jsonl"
        self.job = SimpleNamespace(run_id="native-run", task_id="native-task")
        owner = object.__new__(ExistingP04Background)
        owner._control = lambda _: root
        owner.trainer = SimpleNamespace(
            reject_reparse_ancestors=lambda _: None,
            EventWriter=lambda *a: None)
        self.owner = owner

    def row(self, n, state="RUNNING", kind="training.step"):
        return dict(schema="NOX-INSTALLER-EVENT-v3", run_id="native-run",
                    task_id="native-task", event_sequence=n,
                    event_id=format(n, "032x"), event_type=kind, state=state,
                    package_id="P04", source="P04.QLoRA",
                    evidence_verified=False, message="provisional GPU telemetry",
                    metric_value=0.5)

    def put(self, *rows):
        self.path.write_text("".join(r + "\n" for r in rows), encoding="utf-8")

    def test_no_terminal_event_in_unverified_checkpoints(self):
        self.put(json.dumps(self.row(1)),
                 json.dumps(self.row(2, "COMPLETED", "task.completed")),
                 json.dumps(self.row(3, "COMPLETED", "checkpoint.saved")),
                 json.dumps(self.row(4)))
        self.assertEqual([r["event_sequence"] for r in
                          self.owner.event_snapshot(self.job)], [1, 4])

    def test_task_completed_type_alone_is_hidden(self):
        self.put(json.dumps(self.row(1, kind="task.completed")))
        self.assertEqual(self.owner.event_snapshot(self.job), [])

    def test_duplicate_state_is_hold(self):
        self.put(json.dumps(self.row(1)).replace('"state": "RUNNING"',
                 '"state": "STOPPED", "state": "RUNNING"'))
        with self.assertRaisesRegex(ForgeHold, "P04_SNAPSHOT_AMBIGUOUS_JSON_HOLD"):
            self.owner.event_snapshot(self.job)

    def test_nonfinite_json_telemetry_is_hold(self):
        for token in ("NaN", "Infinity", "1e999"):
            with self.subTest(token=token):
                self.put(json.dumps(self.row(1)).replace(
                         '"metric_value": 0.5', '"metric_value": ' + token))
                with self.assertRaisesRegex(ForgeHold, "P04_SNAPSHOT_NONFINITE_HOLD"):
                    self.owner.event_snapshot(self.job)

    def test_foreign_run_is_hold(self):
        self.put(json.dumps({**self.row(1), "run_id":"other-run"}))
        with self.assertRaisesRegex(ForgeHold, "P04_SNAPSHOT_PROVENANCE_HOLD"):
            self.owner.event_snapshot(self.job)

if __name__ == "__main__":
    unittest.main()
