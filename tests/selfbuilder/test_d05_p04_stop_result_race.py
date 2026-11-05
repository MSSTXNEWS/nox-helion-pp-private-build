"""D05: original P04 must not accept a raced COMPLETED trainer receipt after STOP/PAUSE.

No external GPU, model or new backend; the existing P04 _run, native control,
receipt and queue semantics are exercised through in-memory subprocess fixtures.
Physical owner SID/ACL, GPU and same-Setup E07 remain separate gates.
"""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.nox_selfbuilder.background_forge import ExistingP04Background


class D05StopResultRaceTests(unittest.TestCase):
    def _run_case(self, *, request=None, when="poll", receipt_status="COMPLETED"):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "output"
            output.mkdir()
            control = root / "control"
            control.mkdir()
            owner = object.__new__(ExistingP04Background)
            owner._control_lock = threading.Lock()
            owner._unreaped_worker = None  # match original P04 constructor quarantine state
            owner._active = None
            owner._requested = None
            owner.stop = lambda: False
            owner.permit = lambda: True
            owner.busy = lambda: False
            owner.trainer = SimpleNamespace(
                reject_reparse_ancestors=lambda path: None,
                sha256_file=lambda path: "a" * 64,
            )
            owner.preflight = lambda job: {"status": "HARDWARE_READY_ONLY"}
            owner._output = lambda path, *, resume=False: output
            owner._control = lambda job: control
            owner._job_command = lambda job, out, *, resume=False: (
                ["existing-trainer"], control / "stop.marker", control / "pause.marker"
            )
            owner.relay_events = lambda job, *, live=False: 0
            job = SimpleNamespace(run_id="r1", task_id="t1", output_dir=output)
            def request_owner():
                if request == "STOP":
                    owner.request_stop()
                elif request == "PAUSE":
                    owner.request_pause(job)
            def receipt(job):
                if when == "receipt":
                    request_owner()
                return {"status": receipt_status, "checkpoint": {"status": "HASHED"}}
            owner.verified_receipt = receipt

            class FakeProcess:
                returncode = 0
                polls = 0
                def poll(self):
                    self.polls += 1
                    if self.polls == 1:
                        if when == "poll":
                            request_owner()
                        return None
                    return 0
                def wait(self, *args, **kwargs):
                    return 0

            with patch("src.nox_selfbuilder.background_forge.subprocess.Popen",
                       side_effect=lambda *args, **kwargs: FakeProcess()), patch(
                       "src.nox_selfbuilder.background_forge.time.sleep",
                       return_value=None):
                return owner._run(job, .01, 10, False, True)

    def test_stop_ack_cannot_be_success_receipt(self):
        result = self._run_case(request="STOP")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "TRAINER_STOP_RESULT_CONFLICT")
        self.assertIs(result["weights_updated"], False)

    def test_stop_during_receipt_verification_also_wins(self):
        result = self._run_case(request="STOP", when="receipt")
        self.assertEqual(result["reason"], "TRAINER_STOP_RESULT_CONFLICT")

    def test_pause_ack_cannot_be_success_receipt(self):
        result = self._run_case(request="PAUSE")
        self.assertEqual(result["reason"], "TRAINER_PAUSE_RESULT_CONFLICT")

    def test_legitimate_stopped_receipt_remains_recordable(self):
        self.assertEqual(self._run_case(request="STOP", receipt_status="STOPPED")["status"], "STOPPED")

    def test_no_stop_preserves_completed_candidate(self):
        self.assertEqual(self._run_case()["status"], "ADAPTER_CANDIDATE_PENDING_E07")


if __name__ == "__main__":
    unittest.main()
