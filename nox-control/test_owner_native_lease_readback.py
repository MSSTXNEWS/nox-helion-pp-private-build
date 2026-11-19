"""Fail-closed offline tests for native subagent owner lease readback."""
import os
from pathlib import Path
import tempfile
import unittest

import owner_native_inspect as inspect


class NativeLeaseReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.lock = self.root / "state/dispatcher/native_subagents.lock"
        self.lock.parent.mkdir(parents=True)
        self.lock.touch()
        st = self.lock.stat()
        self.major, self.minor, self.inode = os.major(st.st_dev), os.minor(st.st_dev), st.st_ino
        self.pid = 4321
        self.owner = {"owner_authorized": True, "instance_id": 60509551}
        self.locks = (f"1: FLOCK ADVISORY WRITE {self.pid} "
                      f"{self.major:x}:{self.minor:x}:{self.inode} 0 EOF")
        self.supervisor = (0, f"nox-dispatcher-t855u RUNNING pid {self.pid}, uptime 0:05:00")
        self.reader = lambda pid: 123456 if pid == self.pid else 0

    def tearDown(self):
        self.temp.cleanup()

    def readback(self, **overrides):
        args = dict(root=self.root, proc_root=self.root/"proc",
                    proc_locks_text=self.locks, supervisor_result=self.supervisor,
                    owner_config=self.owner, starttime_reader=self.reader)
        args.update(overrides)
        return inspect.native_subagents_writer_lease_readback(**args)

    def test_exact_lock_holder_supervisor_and_owner_are_proven(self):
        result = self.readback()
        self.assertTrue(result["verified"])
        self.assertEqual(result["state"], "VERIFIED_OWNER_FLOCK_READONLY")
        self.assertEqual(result["lock_inode"], self.inode)
        self.assertEqual(result["holder_pid"], self.pid)
        self.assertEqual(result["holder_start_ticks"], 123456)
        self.assertEqual(result["supervisor_pid"], self.pid)
        self.assertTrue(result["owner_authorized"])
        self.assertEqual(result["owner_instance_id"], 60509551)
        self.assertNotIn("path", result)
        self.assertNotIn("content", result)

    def test_missing_or_ambiguous_lock_holder_fails_closed(self):
        self.assertFalse(self.readback(proc_locks_text="").get("verified"))
        ambiguous = self.locks + "\n" + self.locks.replace("1:", "2:", 1)
        self.assertEqual(self.readback(proc_locks_text=ambiguous)["state"],
                         "HOLD_LOCK_HOLDER_UNKNOWN")

    def test_unrelated_lock_type_and_device_are_not_accepted(self):
        wrong_type = self.locks.replace("FLOCK", "POSIX")
        wrong_device = self.locks.replace(f"{self.major:x}:{self.minor:x}",
                                           "ff:ff")
        self.assertFalse(self.readback(proc_locks_text=wrong_type)["verified"])
        self.assertFalse(self.readback(proc_locks_text=wrong_device)["verified"])

    def test_supervisor_mismatch_and_bad_rc_fail_closed(self):
        self.assertEqual(self.readback(supervisor_result=(
            0, "nox-dispatcher-t855u RUNNING pid 9999, uptime 0:01:00"
        ))["state"], "HOLD_LEASE_OWNER_MISMATCH")
        self.assertFalse(self.readback(supervisor_result=(1, self.supervisor[1]))["verified"])
        self.assertFalse(self.readback(supervisor_result=(
            0, "nox-dispatcher-t855u RUNNING"
        ))["verified"])

    def test_unauthorized_owner_and_changed_pid_fail_closed(self):
        self.assertEqual(self.readback(owner_config={
            "owner_authorized": False, "instance_id": 60509551
        })["state"], "HOLD_OWNER_AUTHORIZATION")
        sequence = iter((123456, 123457))
        self.assertEqual(self.readback(starttime_reader=lambda _pid: next(sequence))["state"],
                         "HOLD_IDENTITY_CHANGED")

    def test_lease_or_supervisor_change_between_reads_fails_closed(self):
        self.assertEqual(self.readback(proc_locks_text_after="")["state"],
                         "HOLD_LOCK_CHANGED")
        self.assertEqual(self.readback(supervisor_result_after=(
            0, "nox-dispatcher-t855u RUNNING pid 9999, uptime 0:01:00"
        ))["state"], "HOLD_SUPERVISOR_CHANGED")

    def test_lock_symlink_is_rejected(self):
        replacement = self.root / "other"
        replacement.touch()
        self.lock.unlink()
        self.lock.symlink_to(replacement)
        self.assertEqual(self.readback()["state"], "HOLD_UNSAFE_LOCK_OBJECT")


if __name__ == "__main__":
    unittest.main()
