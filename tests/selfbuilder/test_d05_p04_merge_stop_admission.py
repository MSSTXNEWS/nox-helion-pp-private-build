"""D05: original P04 merge must not publish an acknowledged STOP or revoked approval.

Isolated mocked subprocess and receipt fixture: no GPU, no model download and
no installed-Windows/E07 evidence. Exercise original ExistingP04Background code.
"""
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.nox_selfbuilder.background_forge import ExistingP04Background


class D05MergeStopAdmissionTests(unittest.TestCase):
    def _case(self, interrupt=None):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            controls = root / "controls"
            controls.mkdir()
            script = root / "merge_qlora_adapter.py"
            script.write_text("# existing P04 script fixture\n", encoding="utf-8")
            owner = object.__new__(ExistingP04Background)
            owner._gate = threading.Lock()
            owner._control_lock = threading.Lock()
            owner._unreaped_worker = None  # match original P04 constructor quarantine state
            owner._active = None
            owner._merge_active = False
            owner._merge_stop = False
            owner._requested = None
            owner.p04 = root
            owner.python = Path(sys.executable)
            owner.stop = lambda: False
            owner.permit = lambda: True
            owner.busy = lambda: False
            owner._control = lambda job: controls
            owner._trusted_file = lambda path: str(path)
            owner._output = lambda path, *, resume=False: root / "merged"
            owner.verified_receipt = lambda job: {
                "status": "COMPLETED", "adapter_sha256": "c" * 64
            }
            job = SimpleNamespace(base_model_dir=root / "model", model_lock=root / "lock",
                                  output_dir=root / "trained", dataset_manifest=root / "manifest",
                                  rights_verifier=root / "rights", run_id="run1", task_id="task1")
            state = {"approved": True, "stop_ack": None}

            def approval(job_arg, output_dir_arg):
                return state["approved"]

            def read_receipt(path):
                if interrupt == "STOP" and state["stop_ack"] is None:
                    state["stop_ack"] = owner.request_stop()
                if interrupt == "REVOKE":
                    state["approved"] = False
                return {
                    "schema": "NOX-QLORA-MERGE-RECEIPT-v1",
                    "status": "CREATED",
                    "training_receipt_sha256": "b" * 64,
                    "adapter_sha256": "c" * 64,
                    "merged_payload_sha256": "a" * 64,
                }

            owner.trainer = SimpleNamespace(
                read_object=read_receipt,
                sha256_file=lambda path: "b" * 64,
            )

            class CompletedProcess:
                returncode = 0
                polls = 0
                def poll(self):
                    self.polls += 1
                    return None if self.polls == 1 else 0

            merger = SimpleNamespace(tree_sha256=lambda path, *, skip_merge_receipt: "a" * 64)
            spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda obj: None))
            with patch("src.nox_selfbuilder.background_forge.subprocess.Popen",
                       return_value=CompletedProcess()), patch(
                       "src.nox_selfbuilder.background_forge.time.sleep",
                       return_value=None), patch(
                       "src.nox_selfbuilder.background_forge.importlib.util.spec_from_file_location",
                       return_value=spec), patch(
                       "src.nox_selfbuilder.background_forge.importlib.util.module_from_spec",
                       return_value=merger):
                result = owner.merge_candidate(job, output_dir=root / "merged",
                                               owner_approve=approval, max_seconds=60)
            self.assertFalse(owner._merge_active)
            return result, state

    def test_stop_after_process_exit_before_receipt_admission(self):
        result, state = self._case("STOP")
        self.assertEqual(state["stop_ack"]["status"], "STOP_REQUESTED")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "MERGE_STOPPED_NO_ACTIVATION")
        self.assertIs(result["activation_allowed"], False)

    def test_owner_revokes_specific_merge_approval_after_exit(self):
        result, state = self._case("REVOKE")
        self.assertFalse(state["approved"])
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "MERGE_OWNER_REVOKED_BEFORE_RECEIPT")

    def test_authorized_uninterrupted_merge_still_candidate_only(self):
        result, state = self._case()
        self.assertTrue(state["approved"])
        self.assertEqual(result["status"], "MERGED_CANDIDATE_PENDING_IMPORT")
        self.assertIs(result["activation_allowed"], False)
        self.assertIs(result["weights_updated"], False)


if __name__ == "__main__":
    unittest.main()
