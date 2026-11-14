"""Pure E06 contract regression, executable without fake Windows services."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "coordination" / "e06" / "adapters"))
from g2_event_state_gate import EventStateHold, require_event_state_coherence


class EventStateGateTests(unittest.TestCase):
    def test_valid_completed(self):
        self.assertIsNone(require_event_state_coherence("task.completed", "COMPLETED"))

    def test_valid_failure(self):
        self.assertIsNone(require_event_state_coherence("task.failed", "ERROR"))

    def test_valid_stop(self):
        self.assertIsNone(require_event_state_coherence("model.stopped", "STOPPED"))

    def test_valid_running(self):
        self.assertIsNone(require_event_state_coherence("task.progress", "RUNNING"))

    def test_valid_paused(self):
        self.assertIsNone(require_event_state_coherence("task.progress", "PAUSED"))

    def test_completed_failure_mismatch(self):
        with self.assertRaises(EventStateHold):
            require_event_state_coherence("task.completed", "ERROR")

    def test_failed_completion_mismatch(self):
        with self.assertRaises(EventStateHold):
            require_event_state_coherence("task.failed", "COMPLETED")

    def test_stopped_running_mismatch(self):
        with self.assertRaises(EventStateHold):
            require_event_state_coherence("model.stopped", "RUNNING")

    def test_progress_claims_ready(self):
        with self.assertRaises(EventStateHold):
            require_event_state_coherence("task.progress", "READY")

    def test_started_claims_completed(self):
        with self.assertRaises(EventStateHold):
            require_event_state_coherence("task.started", "COMPLETED")

    def test_gpu_sample_claims_stop(self):
        with self.assertRaises(EventStateHold):
            require_event_state_coherence("gpu.sample", "STOPPED")

    def test_unhashable_type_before_membership(self):
        for bad in (None, [], {}, 9, True):
            with self.subTest(bad=repr(bad)), self.assertRaises(EventStateHold):
                require_event_state_coherence(bad, "RUNNING")
            with self.subTest(state=repr(bad)), self.assertRaises(EventStateHold):
                require_event_state_coherence("task.progress", bad)


@unittest.skipUnless(
    (ROOT / "coordination" / "e06" / "adapters" / "g2_space_mobile.py").is_file(),
    "Full E06 owner adapter not present in isolated local fixture",
)
class ExistingBusIntegrationTests(unittest.TestCase):
    """Run against the existing publisher only when checkout is available."""

    def sample(self, event_type, state, verified):
        return {
            "schema": "NOX-INSTALLER-EVENT-v3", "run_id": "E06-W4-R11",
            "event_id": "event-r11", "event_type": event_type,
            "task_id": "E06-W4-R11-06", "package_id": "P05",
            "action_id": "space.news", "timestamp_utc": "2026-10-28T14:00:00Z",
            "state": state, "source": "E05", "message": "native payload",
            "evidence_verified": verified,
        }

    def relay(self, event):
        from g2_space_mobile import relay_existing_events_v3
        published = []
        def publish(payload):
            published.append(payload)
            return True
        def evidence(_payload):
            return True
        result = relay_existing_events_v3(
            event, run_id="E06-W4-R11", trusted_owner=lambda: True,
            existing_publish=publish, trusted_evidence=evidence)
        return result, published

    def test_native_completed_passes_through_existing_bus(self):
        event = self.sample("task.completed", "COMPLETED", True)
        result, published = self.relay(event)
        self.assertTrue(result)
        self.assertEqual(published, [event])

    def test_native_completed_error_denied(self):
        from g2_space_mobile import G2Denied
        with self.assertRaises(G2Denied):
            self.relay(self.sample("task.completed", "ERROR", True))

    def test_native_failure_complete_denied(self):
        from g2_space_mobile import G2Denied
        with self.assertRaises(G2Denied):
            self.relay(self.sample("task.failed", "COMPLETED", True))

    def test_unverified_progress_ready_denied(self):
        from g2_space_mobile import G2Denied
        with self.assertRaises(G2Denied):
            self.relay(self.sample("task.progress", "READY", False))


if __name__ == "__main__":
    unittest.main()
