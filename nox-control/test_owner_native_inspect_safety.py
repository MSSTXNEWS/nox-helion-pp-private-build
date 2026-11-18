#!/usr/bin/env python3
"""Read-only OneHost safety probe regression; synthetic fixtures only."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "nox_owner_inspect_safety", Path(__file__).with_name("owner_native_legacy_inspect.py"))
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

    def test_failed_supervisorctl_running_line_is_not_proof(self):
        # supervisorctl may return a stale-looking RUNNING line on error.
        def bad_run(args, timeout=12):
            if args[2] == "nox-chat-8081":
                return 7, "nox-chat-8081 RUNNING pid 987, uptime 0:00:10\\n"
            return self.supervisor_stopped(args, timeout=timeout)
        with patch.object(INSPECT, "run", side_effect=bad_run):
            snap = INSPECT.owner_safety_snapshot()
        chat = snap["supervisor"]["nox-chat-8081"]
        self.assertEqual(chat["state"], "UNKNOWN_SUPERVISOR_RUNNING_IDENTITY")
        self.assertEqual(chat["supervisor_rc"], 7)
        self.assertIsNone(chat["pid"])
        self.assertIsNone(chat["start_ticks"])
        self.assertEqual(snap["admission"], "READ_ONLY_NO_RESTART_NO_DELETE_NO_TRAINER")

    def test_successful_supervisorctl_running_without_pid_is_unknown(self):
        def missing_pid(args, timeout=12):
            if args[2] == "nox-chat-8081":
                return 0, "nox-chat-8081 RUNNING, uptime 0:00:10\\n"
            return self.supervisor_stopped(args, timeout=timeout)
        with patch.object(INSPECT, "run", side_effect=missing_pid):
            snap = INSPECT.owner_safety_snapshot()
        chat = snap["supervisor"]["nox-chat-8081"]
        self.assertEqual(chat["state"], "UNKNOWN_SUPERVISOR_RUNNING_IDENTITY")
        self.assertIsNone(chat["pid"])

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

    def test_state_stop_flag_is_full_manual_stop_alias(self):
        # The original eight-path NOX STOP set includes state/STOP.flag.
        # It must be read as a manual owner fence, not as TRAIN_HOLD.
        flag = self.root / "state" / "STOP.flag"
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("OWNER STOP\\n")
        snap = INSPECT.owner_safety_snapshot()
        self.assertEqual(snap["stop_flags"][str(flag)], "PRESENT")
        self.assertEqual(snap["manual_stop"], "PRESENT")
        self.assertEqual(snap["writer_lease"], "UNKNOWN_NO_OWNER_CAS_READBACK")
        flag.unlink()
        flag.symlink_to(self.root / "owner-unknown-target")
        snap = INSPECT.owner_safety_snapshot()
        self.assertEqual(snap["stop_flags"][str(flag)], "HOLD_SYMLINK")
        self.assertEqual(snap["manual_stop"], "HOLD_UNSAFE_FLAG")
        self.assertEqual(snap["admission"], "READ_ONLY_NO_RESTART_NO_DELETE_NO_TRAINER")

    def test_owner_model_update_maintenance_flag_is_visible_not_a_lease(self):
        # Real 2026-11-16 owner stop used this distinct flag.
        flag = self.root / "state" / "OWNER_MAINTENANCE.flag"
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("OWNER_MODEL_UPDATE 6917926683\\n")
        snap = INSPECT.owner_safety_snapshot()
        self.assertEqual(snap["owner_maintenance_flag"], "PRESENT")
        self.assertEqual(snap["writer_lease"], "UNKNOWN_NO_OWNER_CAS_READBACK")
        self.assertEqual(snap["manual_stop"], "NOT_OBSERVED_NOT_AUTHORIZATION")
        self.assertEqual(snap["admission"], "READ_ONLY_NO_RESTART_NO_DELETE_NO_TRAINER")
        flag.unlink()
        flag.symlink_to(self.root / "not-authorized")
        snap = INSPECT.owner_safety_snapshot()
        self.assertEqual(snap["owner_maintenance_flag"], "HOLD_SYMLINK")

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


class MayaP0BinaryReadOnlyTests(unittest.TestCase):
    def test_pin_is_original_owner_build_receipt_full_sha256(self):
        # Independent pinned build receipt 6906295096, validated by native
        # owner read-only #43887208632; neither result proves inference.
        self.assertEqual(len(INSPECT.MAYA_P0_BINARY_SHA256),64)
        self.assertEqual(INSPECT.MAYA_P0_BINARY_SHA256,
                         '3783980bb65861de36fe4d93b8e6bbd6b6a631207677bcabf330bf7830c21b20')

    def setUp(self):
        import hashlib
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'nox'
        self.path = self.root/INSPECT.MAYA_P0_BINARY_REL
        self.path.parent.mkdir(parents=True)
        self.elf = b'\x7fELF'+bytes([2,1])+b'\x00'*12+(62).to_bytes(2,'little')+b'\x00'*44
        self.path.write_bytes(self.elf)
        self.path.chmod(0o700)
        self.good_sha = hashlib.sha256(self.elf).hexdigest()

    def test_pin_sha_and_elf_not_cuda_or_inference(self):
        result = INSPECT.maya_p0_binary_readback(self.root,self.good_sha)
        self.assertEqual(result['state'],'SHA_PIN_MATCH_ELF_ONLY')
        self.assertEqual(result['cuda124_runtime'],'NOT_TESTED')
        self.assertEqual(result['model_pack'],'NOT_TESTED')
        self.assertFalse(result['native_model_promotion'])

    def test_wrong_sha_is_hold(self):
        self.assertEqual(INSPECT.maya_p0_binary_readback(self.root)['state'],
                         'HOLD_BINARY_SHA_MISMATCH')

    def test_missing_binary_is_hold(self):
        self.path.unlink()
        self.assertEqual(INSPECT.maya_p0_binary_readback(self.root)['state'],
                         'HOLD_BINARY_NOT_PRESENT')

    def test_symlink_binary_is_hold(self):
        self.path.unlink()
        self.path.symlink_to('/etc/passwd')
        self.assertEqual(INSPECT.maya_p0_binary_readback(self.root)['state'],
                         'HOLD_SYMLINK_BINARY')

    def test_bad_elf_is_hold(self):
        self.path.write_bytes(b'x'*70)
        self.assertEqual(INSPECT.maya_p0_binary_readback(self.root)['state'],
                         'HOLD_NOT_LINUX_X86_64_ELF')

    def test_nonexecutable_is_hold(self):
        self.path.chmod(0o600)
        self.assertEqual(INSPECT.maya_p0_binary_readback(self.root)['state'],
                         'HOLD_NOT_EXECUTABLE_REGULAR')

    def test_sparse_oversize_is_hold_without_hashing(self):
        with self.path.open('r+b') as stream:
            stream.truncate(1024**3+1)
        self.assertEqual(INSPECT.maya_p0_binary_readback(self.root)['state'],
                         'HOLD_BINARY_SIZE')

    def test_symlink_parent_is_hold(self):
        parent=self.root/'engine_builds'
        real=self.root/'engine_builds.real'
        parent.rename(real)
        parent.symlink_to(real,target_is_directory=True)
        self.assertEqual(INSPECT.maya_p0_binary_readback(self.root)['state'],
                         'HOLD_UNSAFE_PARENT')

if __name__ == "__main__":
    unittest.main(verbosity=2)
