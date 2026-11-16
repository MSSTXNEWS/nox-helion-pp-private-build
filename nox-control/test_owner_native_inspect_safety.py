#!/usr/bin/env python3
"""Read-only OneHost safety probe regression; synthetic fixtures only."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "nox_owner_inspect_safety", Path(__file__).with_name("owner_native_inspect.py"))
INSPECT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECT)

SERVICES = ("nox-chat-8081", "nox-dispatcher-t855u",
            "nox-priority-scheduler", "nox-selfheal",
            "nox-gpu-watchdog-t865u")


class OwnerSafetyReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "nox"
        self.root.mkdir()
        self.proc = Path(self.tmp.name) / "proc"
        (self.proc / "net").mkdir(parents=True)
        for net in ("tcp", "tcp6"):
            (self.proc / "net" / net).write_text("sl local_address rem_address st tx rx tr tm retrnsmt uid timeout inode\n")
        self.patches = [
            patch.object(INSPECT, "ROOT", self.root),
            patch.object(INSPECT, "PROC", self.proc),
            patch.object(INSPECT, "run", side_effect=self.supervisor_stopped),
        ]
        for patched in self.patches:
            patched.start()
            self.addCleanup(patched.stop)

    @staticmethod
    def supervisor_stopped(args, timeout=12):
        assert args[:2] == ["supervisorctl", "status"]
        return 3, f"{args[2]} STOPPED Nov 16 01:35 PM\n"

    def test_all_stopped_does_not_authorize_restart(self):
        snapshot = INSPECT.owner_safety_snapshot()
        self.assertEqual(snapshot["admission"], "READ_ONLY_NO_RESTART_NO_DELETE_NO_TRAINER")
        self.assertEqual(snapshot["writer_lease"], "UNKNOWN_NO_OWNER_CAS_READBACK")
        self.assertEqual(snapshot["manual_stop"], "NOT_OBSERVED_NOT_AUTHORIZATION")
        self.assertEqual(set(snapshot["supervisor"]), set(SERVICES))
        for state in snapshot["supervisor"].values():
            self.assertEqual(state["state"], "STOPPED")
            self.assertEqual(state["supervisor_rc"], 3)
            self.assertIsNone(state["pid"])
        self.assertEqual(snapshot["listener_8081"]["socket_inodes_observed"], 0)
        self.assertEqual(snapshot["listener_8081"]["matched_pids"], [])

    def test_stop_and_symlink_are_distinct_fail_closed(self):
        (self.root / "STOP.flag").write_text("owner manually stopped\n")
        snapshot = INSPECT.owner_safety_snapshot()
        self.assertEqual(snapshot["manual_stop"], "PRESENT")
        (self.root / "STOP.flag").unlink()
        (self.root / "STOP.flag").symlink_to(self.root / "sensitive-target")
        snapshot = INSPECT.owner_safety_snapshot()
        self.assertEqual(snapshot["stop_flags"][str(self.root / "STOP.flag")],
                         "HOLD_SYMLINK")
        self.assertEqual(snapshot["manual_stop"], "HOLD_UNSAFE_FLAG")

    def test_live_supervisor_pid_and_socket_inode_are_bound_to_start_ticks(self):
        pid = 432
        process = self.proc / str(pid)
        (process / "fd").mkdir(parents=True)
        (process / "fd" / "3").symlink_to("socket:[42]")
        # /proc/PID/stat suffix: state index 0; starttime index 19.
        (process / "stat").write_text(
            f"{pid} (llama server) S " + " ".join(["0"] * 18 + ["987654"]) + "\n")
        # Listening TCP port 8081 = 0x1F91, inode at field 9.
        (self.proc / "net/tcp").write_text(
            "sl local_address rem_address st tx rx tr tm retrnsmt uid timeout inode\n"
            "0: 0100007F:1F91 00000000:0000 0A 0 0 0 0 0 42\n")
        def running_chat(args, timeout=12):
            name = args[2]
            if name == "nox-chat-8081":
                return 0, f"{name} RUNNING pid {pid}, uptime 0:00:30\n"
            return self.supervisor_stopped(args, timeout=timeout)
        with patch.object(INSPECT, "run", side_effect=running_chat):
            snapshot = INSPECT.owner_safety_snapshot()
        self.assertEqual(snapshot["supervisor"]["nox-chat-8081"]["pid"], pid)
        self.assertEqual(snapshot["supervisor"]["nox-chat-8081"]["start_ticks"], 987654)
        self.assertEqual(snapshot["listener_8081"]["socket_inodes_observed"], 1)
        self.assertEqual(snapshot["listener_8081"]["matched_pids"],
                         [{"pid": pid, "start_ticks": 987654}])
        self.assertEqual(snapshot["listener_8081"]["status"], "OBSERVED")

    def test_unowned_listening_socket_cannot_trigger_restart(self):
        (self.proc / "net/tcp").write_text(
            "sl local_address rem_address st tx rx tr tm retrnsmt uid timeout inode\n"
            "0: 0100007F:1F91 00000000:0000 0A 0 0 0 0 0 919\n")
        snapshot = INSPECT.owner_safety_snapshot()
        self.assertEqual(snapshot["listener_8081"]["status"], "UNRESOLVED_LISTENER_OWNER")
        self.assertFalse(snapshot["listener_8081"]["complete_pid_map"])
        self.assertEqual(snapshot["admission"], "READ_ONLY_NO_RESTART_NO_DELETE_NO_TRAINER")

    def test_unavailable_network_namespace_is_unknown_not_empty_verified(self):
        (self.proc / "net/tcp").unlink()
        snapshot = INSPECT.owner_safety_snapshot()
        self.assertEqual(snapshot["listener_8081"]["status"], "UNKNOWN_NETWORK_NAMESPACE")
        self.assertFalse(snapshot["listener_8081"]["complete_pid_map"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
