"""Regression of original P04 Windows worker STOP-failure safety (SOURCE_ONLY).

Uses only synthetic process objects and a temporary file. Never launches GPU,
installs models or treats a STOP request as a successful training receipt.
"""
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from src.nox_selfbuilder.background_forge import ExistingP04Background


class FakeProcess:
    def __init__(self, *, timeout=False, exited=False):
        self.code = 0 if exited else None
        self.timeout = timeout
        self.term = 0
        self.killed = 0

    def poll(self):
        return self.code

    def terminate(self):
        self.term += 1
        if not self.timeout:
            self.code = 1

    def wait(self, timeout=None):
        if self.code is None and self.timeout:
            raise subprocess.TimeoutExpired('fake-original-p04', timeout)
        return self.code

    def kill(self):
        self.killed += 1
        self.code = -9


class P04UnacknowledgedStopTests(unittest.TestCase):
    def test_normal_stop_uses_original_process_handle(self):
        p = FakeProcess()
        ExistingP04Background._terminate_unacknowledged_worker(p)
        self.assertEqual((p.term, p.killed, p.poll()), (1, 0, 1))

    def test_bounded_stop_escalates_to_kill(self):
        p = FakeProcess(timeout=True)
        ExistingP04Background._terminate_unacknowledged_worker(p)
        self.assertEqual((p.term, p.killed, p.poll()), (1, 1, -9))

    def test_completed_process_is_not_signalled(self):
        p = FakeProcess(exited=True)
        ExistingP04Background._terminate_unacknowledged_worker(p)
        self.assertEqual((p.term, p.killed), (0, 0))

    def test_denied_termination_never_creates_success(self):
        class Denied(FakeProcess):
            def terminate(self):
                raise PermissionError('OS_DENIED')
        with self.assertRaises(PermissionError):
            ExistingP04Background._terminate_unacknowledged_worker(Denied())

    def test_owner_stop_marker_failure_shuts_down_native_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = object.__new__(ExistingP04Background)
            runner.p04 = root
            runner.trainer = SimpleNamespace(reject_reparse_ancestors=lambda path: None)
            runner._control_lock = threading.Lock()
            runner._active = runner._requested = None
            runner._owner_training_grant = lambda **kwargs: True
            runner.preflight = lambda job: {'status': 'HARDWARE_READY_ONLY'}
            runner._output = lambda *args, **kwargs: root / 'candidate'
            runner._job_command = lambda *args, **kwargs: (
                ['original-worker-double'], root / 'stop.marker', root / 'pause.marker')
            runner._control = lambda job: root
            runner.stop = lambda: True
            runner.permit = lambda: True
            runner.busy = lambda: False

            def blocked_marker():
                raise PermissionError('NO_OWNER_MARKER_WRITE')
            runner.request_stop = blocked_marker
            p = FakeProcess()
            with patch('src.nox_selfbuilder.background_forge.subprocess.Popen', return_value=p):
                result = runner._run(SimpleNamespace(run_id='r', task_id='t'), .01, 10, False, True)
            self.assertEqual(result['status'], 'HOLD')
            self.assertEqual(result['reason'], 'TRAINER_MONITOR_FAILED')
            self.assertIs(result['activation_allowed'], False)
            self.assertIs(result['weights_updated'], False)
            self.assertEqual(p.term, 1)
            self.assertIsNotNone(p.poll())


if __name__ == '__main__':
    unittest.main()
