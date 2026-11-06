"""D05 R5 regression: original P04 event bus never signals COMPLETED before receipt/STOP admission.
Uses the original relay_events method with a disposable event log and fake sink.
This is Python source/runtime unit proof only; no Windows/GPU/E07 evidence.
"""
import hashlib
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from src.nox_selfbuilder.background_forge import ExistingP04Background, ForgeJob
from src.nox_selfbuilder.p04_forge_bridge import ExistingP04NativePorts, ForgeHold


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
        self.owner.trainer = SimpleNamespace(
            EventWriter=lambda *a, **kw: None,
            reject_reparse_ancestors=lambda path: None,
            sha256_file=lambda path: "a" * 64)
        self.job = ForgeJob("r1", "t1", root / "model", root / "model.lock",
                            "a" * 40, root / "manifest", root / "rights",
                            root / "train", root / "holdout", root / "output")
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
                "event_sequence": index,
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
        # Without original owner-scoped SQLite RESULT no completed bus event
        # may be emitted, even if a verified worker receipt was returned.
        self.assertEqual(self.owner.relay_events(self.job), 0)
        self.assertEqual(len(self.events), 2)
        self.assertEqual(self.owner.relay_events(self.job, durable_s03=True), 2)
        self.assertEqual(len(self.events), 4)
        self.assertEqual(self.owner.relay_events(self.job, durable_s03=True), 0)

    def test_terminal_bus_follows_exact_durable_s03_owner_record(self):
        self.assertEqual(self.owner.relay_events(self.job, live=True), 2)
        sealed = hashlib.sha256(json.dumps(
            asdict(self.job), sort_keys=True, default=str).encode()).hexdigest()
        good = {
            "kind": "FORGE", "task_id": 7,
            "state": "ADAPTER_CANDIDATE_PENDING_E07",
            "payload": {"run_id": "r1", "task_id": "t1", "job_sha256": sealed},
            "result": {"status": "ADAPTER_CANDIDATE_PENDING_E07",
                       "run_id": "r1", "receipt_sha256": "a" * 64,
                       "weights_updated": False, "activation_allowed": False},
        }
        current = {"row": None}
        ports = ExistingP04NativePorts(
            self.owner, job_resolver=lambda *_: self.job,
            last_run=lambda *_: None, native_submit=lambda *_: None,
            durable_result=lambda *_: current["row"])
        with self.assertRaises(ForgeHold):
            ports._attest_recorded_training("owner", self.job,
                                            {"status": "COMPLETED"})
        self.assertEqual(len(self.events), 2)
        current["row"] = {**good, "state": "HOLD"}
        with self.assertRaises(ForgeHold):
            ports._attest_recorded_training("owner", self.job,
                                            {"status": "COMPLETED"})
        self.assertEqual(len(self.events), 2)
        current["row"] = good
        self.assertIs(ports._attest_recorded_training(
            "owner", self.job, {"status": "COMPLETED"}), good)
        self.assertEqual(len(self.events), 4)
        self.assertEqual(self.owner.relay_events(self.job), 0)


if __name__ == "__main__":
    unittest.main()
