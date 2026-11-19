import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


observer = load("observer_uds", "owner_native_lifeline_observer.py")
runtime = load("lifeline_runtime_uds", "nox_native_lifeline.py")


class UDSLifelineTests(unittest.TestCase):
    def test_runtime_start_is_hard_blocked(self):
        with self.assertRaisesRegex(ValueError, "HOLD_OBSERVER_ONLY_START_DISABLED"):
            runtime.supervise("nox-dispatcher-t855u", "start")

    def test_runtime_status_uses_readonly_rpc_row(self):
        row = {"name": "nox-dispatcher-t855u", "statename": "RUNNING", "pid": 321}
        with patch.object(runtime, "_supervisor_row", return_value=row):
            self.assertEqual(runtime.supervise("nox-dispatcher-t855u"),
                             {"state": "RUNNING", "pid": 321, "rc": 0})

    def test_runtime_status_never_treats_stopped_with_pid_as_repairable(self):
        row = {"name": "nox-dispatcher-t855u", "statename": "STOPPED", "pid": 321}
        with patch.object(runtime, "_supervisor_row", return_value=row):
            self.assertEqual(runtime.supervise("nox-dispatcher-t855u"),
                             {"state": "UNKNOWN", "pid": None, "rc": 1})

    def test_stopped_model_uses_guard_and_installer_cgroup_anchor(self):
        target = "/sys/fs/cgroup"
        self_info = {"pid": 10, "start_ticks": 1, "cgroup_path": target}
        legacy_info = {"pid": 20, "start_ticks": 2, "cgroup_path": target}
        legacy = {"process": {"pid": 20, "start_ticks": 2}}
        row = {"name": observer.MODEL_SERVICE, "group": observer.MODEL_SERVICE,
               "statename": "STOPPED", "pid": 0}
        with (patch.object(observer, "CGROUP_ROOT", SimpleNamespace(resolve=lambda strict: Path(target))),
              patch.object(observer, "process_cgroup_info", side_effect=[self_info, legacy_info]),
              patch.object(observer, "_proc_start_ticks", return_value=1),
              patch.object(observer, "_supervisor_process_info", return_value=row),
              patch.object(observer, "model_runtime_census",
                           return_value={"target": target, "count": 0, "matches": []})):
            result = observer.resolve_cgroup_target(legacy)
        self.assertEqual(result["target"], target)
        self.assertEqual(result["model"]["state"], "STOPPED")
        self.assertEqual(result["model"]["anchor"], "installer_and_legacy_guard")

    def test_stopped_model_with_target_runtime_holds(self):
        target = "/sys/fs/cgroup"
        self_info = {"pid": 10, "start_ticks": 1, "cgroup_path": target}
        legacy_info = {"pid": 20, "start_ticks": 2, "cgroup_path": target}
        legacy = {"process": {"pid": 20, "start_ticks": 2}}
        row = {"name": observer.MODEL_SERVICE, "group": observer.MODEL_SERVICE,
               "statename": "EXITED", "pid": 0}
        with (patch.object(observer, "CGROUP_ROOT", SimpleNamespace(resolve=lambda strict: Path(target))),
              patch.object(observer, "process_cgroup_info", side_effect=[self_info, legacy_info]),
              patch.object(observer, "_proc_start_ticks", return_value=1),
              patch.object(observer, "_supervisor_process_info", return_value=row),
              patch.object(observer, "model_runtime_census",
                           return_value={"target": target, "count": 1, "matches": [{"pid": 30}]})):
            with self.assertRaisesRegex(observer.Hold, "MODEL_RUNTIME_PRESENT_WHILE_STOPPED"):
                observer.resolve_cgroup_target(legacy)

    def test_installer_systemctl_is_absolute_pinned_and_environment_fixed(self):
        pin = {"sha256": "systemctl-pin"}
        with (patch.object(observer, "SYSTEMCTL_PIN", pin),
              patch.object(observer, "_supervisorctl_snapshot", return_value=pin),
              patch.object(observer.subprocess, "run", return_value="ok") as run):
            observer.run(["systemctl", "daemon-reload"], timeout=3)
        self.assertEqual(run.call_args.args[0], ["/usr/bin/systemctl", "daemon-reload"])
        self.assertIs(run.call_args.kwargs["shell"], False)
        self.assertEqual(run.call_args.kwargs["env"],
                         {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"})

    def test_installer_systemctl_rejects_unapproved_scope(self):
        with self.assertRaisesRegex(observer.Hold, "SYSTEMCTL_OPERATION_NOT_ALLOWLISTED"):
            observer.run(["systemctl", "restart", "supervisor.service"])

    def test_listener_proof_binds_exact_path_pid_fd_and_kernel_inode(self):
        endpoint = {"path": "/run/supervisor.sock",
                    "configured_path": "/var/run/supervisor.sock"}
        table = (b"Num RefCount Protocol Flags Type St Inode Path\n"
                 b"000: 00000002 00000000 00010000 0001 01 9876 /run/supervisor.sock\n")
        entry = SimpleNamespace(path="/proc/42/fd/3", name="3")
        with (patch.object(observer, "_proc_file", return_value=table),
              patch.object(observer.os, "scandir", return_value=[entry]),
              patch.object(observer.os, "readlink", return_value="socket:[9876]")):
            proof = observer._unix_listener_evidence(42, endpoint)
        self.assertEqual(proof, {"inode": 9876, "path": "/run/supervisor.sock",
                                 "flags": "00010000", "socket_type": "0001", "state": "01",
                                 "owner_pid": 42, "fd": "3"})

    def test_listener_proof_holds_on_ambiguous_rows(self):
        endpoint = {"path": "/run/supervisor.sock",
                    "configured_path": "/var/run/supervisor.sock"}
        row = b"000: 00000002 00000000 00010000 0001 01 9876 /run/supervisor.sock\n"
        duplicate_other_type = b"001: 00000002 00000000 00010000 0002 01 9877 /run/supervisor.sock\n"
        table = b"Num RefCount Protocol Flags Type St Inode Path\n" + row + duplicate_other_type
        with patch.object(observer, "_proc_file", return_value=table):
            with self.assertRaisesRegex(observer.Hold, "SUPERVISOR_LISTENER_ROW_NOT_UNIQUE"):
                observer._unix_listener_evidence(42, endpoint)

    def test_listener_proof_rejects_wrong_type_flags_or_state(self):
        endpoint = {"path": "/run/supervisor.sock",
                    "configured_path": "/var/run/supervisor.sock"}
        for fields in ("00010000 0002 01", "00000000 0001 01", "00010000 0001 02"):
            row = ("000: 00000002 00000000 " + fields +
                   " 9876 /run/supervisor.sock\n").encode()
            table = b"Num RefCount Protocol Flags Type St Inode Path\n" + row
            with self.subTest(fields=fields), patch.object(observer, "_proc_file", return_value=table):
                with self.assertRaisesRegex(observer.Hold, "SUPERVISOR_LISTENER_ROW_NOT_LISTENING"):
                    observer._unix_listener_evidence(42, endpoint)

    def test_runtime_listener_rejects_duplicate_exact_path_even_if_second_is_invalid(self):
        row = b"000: 00000002 00000000 00010000 0001 01 9876 /run/supervisor.sock\n"
        duplicate = b"001: 00000002 00000000 00000000 0001 00 9877 /run/supervisor.sock\n"
        table = b"Num RefCount Protocol Flags Type St Inode Path\n" + row + duplicate
        entry = SimpleNamespace(path="/proc/42/fd/3", name="3")
        with (patch.object(runtime, "SUPERVISOR_SOCKET_PATH", "/run/supervisor.sock"),
              patch.object(runtime, "SUPERVISOR_IDENTITY_PIN", {
                  "configured_socket_path": "/var/run/supervisor.sock"}),
              patch.object(runtime, "SUPERVISOR_PID", 42),
              patch.object(runtime, "_bounded_proc_read", return_value=table),
              patch.object(runtime.os, "scandir", return_value=[entry]),
              patch.object(runtime.os, "readlink", return_value="socket:[9876]")):
            with self.assertRaisesRegex(ValueError, "HOLD_SUPERVISOR_LISTENER_ROW"):
                runtime._runtime_unix_listener()


if __name__ == "__main__":
    unittest.main()
