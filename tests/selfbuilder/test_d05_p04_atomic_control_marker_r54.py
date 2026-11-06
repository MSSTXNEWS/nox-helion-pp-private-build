"""D05 regression: original P04 STOP/PAUSE must never append via a preexisting marker.

Tests original ExistingP04Background method with an isolated disposable directory.
No GPU weights, actual Windows x64, or E07 are exercised here.
"""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.nox_selfbuilder.background_forge import ExistingP04Background, ForgeHold


class NativeP04AtomicMarkerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        owner = object.__new__(ExistingP04Background)
        owner._control_lock = threading.Lock()
        owner._unreaped_worker = None  # match original P04 constructor quarantine state
        owner._active = (self.root / "stop.marker", self.root / "pause.marker", "run1", "task1")
        owner._requested = None
        owner._merge_active = False
        owner._merge_stop = False
        owner.trainer = SimpleNamespace(reject_reparse_ancestors=lambda path: None)
        self.owner = owner

    def test_unreapable_child_does_not_ack_or_create_control_markers(self):
        # Exercise the real original request_stop/request_pause methods with an
        # OS-unreapable child. This is not a fake owner ACK or GPU PASS.
        self.owner._unreaped_worker = object()
        for action in (self.owner.request_stop, self.owner.request_pause):
            result = action()
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["reason"], "TRAINER_CHILD_UNREAPED_QUARANTINE_HOLD")
        self.assertIsNone(self.owner._requested)
        self.assertFalse(self.owner._active[0].exists())
        self.assertFalse(self.owner._active[1].exists())

    def test_foreign_regular_marker_never_gets_first_ack(self):
        marker = self.owner._active[0]
        marker.write_bytes(b"foreign-existing-marker")
        with self.assertRaisesRegex(ForgeHold, "TRAINER_CONTROL_MARKER_UNOWNED_HOLD"):
            self.owner.request_stop()
        self.assertIsNone(self.owner._requested)
        self.assertEqual(marker.read_bytes(), b"foreign-existing-marker")

    def test_pause_cannot_authorize_foreign_preexisting_stop_marker(self):
        self.assertEqual(self.owner.request_pause()["status"], "PAUSE_REQUESTED")
        marker = self.owner._active[0]
        marker.write_bytes(b"foreign-existing-marker")
        with self.assertRaisesRegex(ForgeHold, "TRAINER_CONTROL_MARKER_UNOWNED_HOLD"):
            self.owner.request_stop()
        self.assertEqual(self.owner._requested, "PAUSE")
        self.assertEqual(marker.read_bytes(), b"foreign-existing-marker")

    def test_pause_then_stop_creates_exact_markers(self):
        self.assertEqual(self.owner.request_pause()["status"], "PAUSE_REQUESTED")
        self.assertTrue(self.owner._active[1].is_file())
        self.assertEqual(self.owner.request_stop()["status"], "STOP_REQUESTED")
        self.assertTrue(self.owner._active[0].is_file())

    def test_repeated_stop_never_appends_or_rewrites_existing_bytes(self):
        self.owner.request_stop()
        marker = self.owner._active[0]
        marker.write_bytes(b"unchanged owner marker")
        with patch("src.nox_selfbuilder.background_forge.os.open",
                   side_effect=FileExistsError()):
            self.assertEqual(self.owner.request_stop()["status"], "STOP_REQUESTED")
        self.assertEqual(marker.read_bytes(), b"unchanged owner marker")

    def test_replaced_regular_stop_marker_cannot_inherit_owner_ack(self):
        # A previous STOP ACK does not authorize a replacement by another
        # process, even when the replacement remains a normal regular file.
        self.assertEqual(self.owner.request_stop()["status"], "STOP_REQUESTED")
        marker = self.owner._active[0]
        foreign = self.root / "replacement.marker"
        foreign.write_bytes(b"foreign-regular-marker")
        os.replace(foreign, marker)
        with self.assertRaisesRegex(ForgeHold, "TRAINER_CONTROL_MARKER_REPLACED_HOLD"):
            self.owner.request_stop()
        self.assertEqual(marker.read_bytes(), b"foreign-regular-marker")

    def test_existing_symlink_cannot_touch_foreign_file_or_ack(self):
        foreign = self.root / "foreign.txt"
        foreign.write_bytes(b"foreign-preserved")
        marker = self.owner._active[0]
        try:
            marker.symlink_to(foreign)
        except (OSError, NotImplementedError):
            self.skipTest("Creating symlinks is not permitted on this test host")
        with self.assertRaisesRegex(ForgeHold, "TRAINER_CONTROL_MARKER_NOT_REGULAR"):
            self.owner.request_stop()
        self.assertEqual(foreign.read_bytes(), b"foreign-preserved")
        self.assertIsNone(self.owner._requested)

    def test_directory_marker_is_not_acknowledged(self):
        self.owner._active[0].mkdir()
        with self.assertRaisesRegex(ForgeHold, "TRAINER_CONTROL_MARKER_NOT_REGULAR"):
            self.owner.request_stop()
        self.assertIsNone(self.owner._requested)

    def test_failed_marker_creation_cannot_publish_owner_ack(self):
        with patch("src.nox_selfbuilder.background_forge.os.open",
                   side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                self.owner.request_stop()
        self.assertIsNone(self.owner._requested)
        self.assertFalse(self.owner._active[0].exists())

    def test_incorrect_owner_job_never_creates_marker(self):
        wrong = SimpleNamespace(run_id="different", task_id="task1")
        with self.assertRaisesRegex(ForgeHold, "ACTIVE_TRAINER_JOB_SCOPE_MISMATCH"):
            self.owner.request_pause(job=wrong)
        self.assertFalse(self.owner._active[1].exists())

    def test_stop_priority_survives_later_pause(self):
        self.owner.request_stop()
        self.assertEqual(self.owner.request_pause()["status"], "STOP_REQUESTED")
        self.assertFalse(self.owner._active[1].exists())

    def test_original_inactive_and_merge_stop_contract(self):
        self.owner._active = None
        self.assertEqual(self.owner.request_stop()["status"], "HOLD")
        self.owner._merge_active = True
        self.assertEqual(self.owner.request_stop()["status"], "STOP_REQUESTED")
        self.assertIs(self.owner._merge_stop, True)

    def test_verified_paused_receipt_clears_only_native_marker(self):
        self.assertEqual(self.owner.request_pause()["status"], "PAUSE_REQUESTED")
        marker = self.owner._active[1]
        with self.owner._control_lock:
            self.owner._clear_owned_paused_marker_locked(marker)
        self.assertFalse(marker.exists())
        self.assertNotIn("PAUSE", self.owner._owned_marker_identity)

    def test_verified_paused_receipt_never_unlinks_replaced_regular_file(self):
        self.assertEqual(self.owner.request_pause()["status"], "PAUSE_REQUESTED")
        marker = self.owner._active[1]
        replacement = self.root / "foreign-paused.marker"
        replacement.write_bytes(b"FOREIGN PRESERVE")
        os.replace(replacement, marker)
        with self.assertRaisesRegex(ForgeHold, "TRAINER_PAUSE_MARKER_REPLACED_HOLD"):
            with self.owner._control_lock:
                self.owner._clear_owned_paused_marker_locked(marker)
        self.assertEqual(marker.read_bytes(), b"FOREIGN PRESERVE")

    def test_stop_does_not_remove_prior_pause_marker(self):
        self.assertEqual(self.owner.request_pause()["status"], "PAUSE_REQUESTED")
        marker = self.owner._active[1]
        self.assertEqual(self.owner.request_stop()["status"], "STOP_REQUESTED")
        with self.assertRaisesRegex(ForgeHold, "TRAINER_PAUSE_MARKER_UNOWNED_HOLD"):
            with self.owner._control_lock:
                self.owner._clear_owned_paused_marker_locked(marker)
        self.assertTrue(marker.is_file())

    def test_missing_pause_marker_is_not_accepted_as_owner_receipt(self):
        self.assertEqual(self.owner.request_pause()["status"], "PAUSE_REQUESTED")
        marker = self.owner._active[1]
        marker.unlink()
        with self.assertRaisesRegex(ForgeHold, "TRAINER_PAUSE_MARKER_NOT_REGULAR_HOLD"):
            with self.owner._control_lock:
                self.owner._clear_owned_paused_marker_locked(marker)



if __name__ == "__main__":
    unittest.main()
