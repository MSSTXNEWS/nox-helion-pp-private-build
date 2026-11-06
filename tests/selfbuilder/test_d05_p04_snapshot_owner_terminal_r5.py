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


    def test_snapshot_rejects_unknown_event_kinds_and_states(self):
        # A GPU worker event can be native-run-shaped yet use an invented
        # terminal status/type. The read-only UI snapshot must HOLD, not relay.
        for changed in ({"event_type": "task.approved"},
                        {"state": "ACTIVATED"}):
            with self.subTest(changed=changed):
                self.put(json.dumps({**self.row(1), **changed}))
                with self.assertRaisesRegex(ForgeHold, "P04_SNAPSHOT_PROVENANCE_HOLD"):
                    self.owner.event_snapshot(self.job)

    def test_snapshot_keeps_valid_provisional_gpu_progress(self):
        self.put(json.dumps(self.row(1, state="RUNNING", kind="training.step")))
        self.assertEqual([row["event_sequence"] for row in
                          self.owner.event_snapshot(self.job)], [1])

    def test_relay_late_invalid_provenance_has_no_partial_ui_delivery(self):
        # Earlier valid GPU telemetry must not escape into WebView2 when a
        # later complete row fails native provenance checks.
        forwarded = []
        self.owner.event_sink = lambda event: (forwarded.append(event), True)[1]
        self.owner._relayed = set()
        self.put(json.dumps(self.row(1)),
                 json.dumps({**self.row(2), "source": "FOREIGN.QLoRA"}))
        with self.assertRaisesRegex(ForgeHold, "P04_EVENT_PROVENANCE_HOLD"):
            self.owner.relay_events(self.job, live=True)
        self.assertEqual(forwarded, [])
        self.assertEqual(self.owner._relayed, set())

    def test_relay_valid_progress_is_once_only_and_terminal_is_withheld(self):
        forwarded = []
        self.owner.event_sink = lambda event: (forwarded.append(event), True)[1]
        self.owner._relayed = set()
        self.put(json.dumps(self.row(1)),
                 json.dumps(self.row(2, state="COMPLETED", kind="task.completed")),
                 json.dumps(self.row(3, state="RUNNING", kind="gpu.sample")))
        self.assertEqual(self.owner.relay_events(self.job, live=True), 2)
        self.assertEqual(self.owner.relay_events(self.job, live=True), 0)
        self.assertEqual([event["event_sequence"] for event in forwarded], [1, 3])


if __name__ == "__main__":
    unittest.main()
