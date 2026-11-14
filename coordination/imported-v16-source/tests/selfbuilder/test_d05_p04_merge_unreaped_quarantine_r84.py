"""Native D05: never free the original GPU gate for an unreapable merge child.
No Windows GPU/models, second host, model activation, or independent E07.
"""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.nox_selfbuilder.background_forge import ExistingP04Background, ForgeHold


class FakeMergeProcess:
    def __init__(self, *, refuses_kill):
        self.refuses_kill = refuses_kill
        self.alive = True
        self.returncode = None

    def poll(self):
        return None if self.alive else self.returncode

    def terminate(self):
        if self.refuses_kill:
            raise PermissionError("Windows denied terminate")
        self.alive = False
        self.returncode = 1

    def kill(self):
        if self.refuses_kill:
            raise PermissionError("Windows denied kill")
        self.alive = False
        self.returncode = 1

    def wait(self, timeout=None):
        if self.alive:
            raise AssertionError("unbounded wait on live native GPU child")
        return self.returncode


class MergeStopQuarantineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        owner = object.__new__(ExistingP04Background)
        owner._gate = threading.Lock()
        owner._control_lock = threading.Lock()
        owner._unreaped_worker = None
        owner._active = None
        owner._requested = None
        owner._merge_active = False
        owner._merge_stop = False
        owner.p04 = root
        owner.python = root / "python.exe"
        owner._trusted_file = lambda p: str(p)
        owner._control = lambda job: root
        owner._output = lambda path: root / "merged"
        owner._owner_training_grant = lambda **kwargs: True
        owner.verified_receipt = lambda job: {"status": "COMPLETED"}
        owner.trainer = SimpleNamespace()
        self.owner = owner
        self.job = SimpleNamespace(base_model_dir=root, model_lock=root / "lock",
                                   output_dir=root / "adapter",
                                   dataset_manifest=root / "manifest",
                                   rights_verifier=root / "rights")

    @staticmethod
    def approve_first_then_revoke():
        calls = iter((True, False))
        return lambda job, output: next(calls)

    def test_unreapable_merge_quarantines_gate_and_never_acks_stop(self):
        process = FakeMergeProcess(refuses_kill=True)
        with patch("src.nox_selfbuilder.background_forge.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(ForgeHold, "TRAINER_CHILD_UNREAPED_QUARANTINE_HOLD"):
                self.owner.merge_candidate(self.job, output_dir="approved",
                                           owner_approve=self.approve_first_then_revoke())
        self.assertIs(self.owner._unreaped_worker, process)
        self.assertTrue(self.owner._gate.locked())
        self.assertTrue(self.owner._merge_active)
        self.assertEqual(self.owner.request_stop()["reason"],
                         "TRAINER_CHILD_UNREAPED_QUARANTINE_HOLD")
        self.assertEqual(self.owner.request_pause()["status"], "HOLD")
        self.assertTrue(process.alive)

    def test_reaped_merge_returns_hold_and_releases_gate(self):
        process = FakeMergeProcess(refuses_kill=False)
        with patch("src.nox_selfbuilder.background_forge.subprocess.Popen", return_value=process):
            result = self.owner.merge_candidate(self.job, output_dir="approved",
                                                owner_approve=self.approve_first_then_revoke())
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "MERGE_STOPPED_NO_ACTIVATION")
        self.assertIsNone(self.owner._unreaped_worker)
        self.assertFalse(self.owner._merge_active)
        self.assertFalse(self.owner._gate.locked())
        self.assertFalse(process.alive)


if __name__ == "__main__":
    unittest.main()
