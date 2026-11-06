"""D05 R5 regression: original P04 event bus never signals COMPLETED before receipt/STOP admission.
Uses the original relay_events method with a disposable event log and fake sink.
This is Python source/runtime unit proof only; no Windows/GPU/E07 evidence.
"""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from src.nox_selfbuilder.background_forge import ExistingP04Background


class D05TerminalEventGate(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.owner = object.__new__(ExistingP04Background)
        self.owner._control = lambda job: root
        self.owner._relayed = set()
        self.events = []
        self.owner.event_sink = lambda event: self.events.append(event) or True
        self.owner.trainer = SimpleNamespace(EventWriter=lambda *a, **kw: None)
        self.job = SimpleNamespace(run_id="r1", task_id="t1")
        rows = []
        for index, kind, state in ((1, "training.step", "RUNNING"),
                                    (2, "task.completed", "COMPLETED"),
                                    (3, "checkpoint.saved", "COMPLETED"),
                                    (4, "checkpoint.saved", "RUNNING")):
            rows.append({
                "schema": "NOX-INSTALLER-EVENT-v3", "run_id": "r1",
                "task_id": "t1", "package_id": "P04",
                "evidence_verified": False, "source": "P04.QLoRA",
                "event_type": kind, "state": state,
                "message": "native provisional GPU event",
                "event_id": format(index, "032x")
            })
        (root / "events.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def test_terminal_event_deferred_without_losing_live_progress(self):
        self.assertEqual(self.owner.relay_events(self.job, live=True), 2)
        self.assertEqual([e["event_id"] for e in self.events], [
            format(1, "032x"), format(4, "032x")])
        self.assertFalse(any(e["state"] == "COMPLETED" for e in self.events))
        # Called only after verified_receipt and STOP linearization in _run.
        self.assertEqual(self.owner.relay_events(self.job), 2)
        self.assertEqual(len(self.events), 4)
        self.assertEqual(self.owner.relay_events(self.job), 0)


if __name__ == "__main__":
    unittest.main()
