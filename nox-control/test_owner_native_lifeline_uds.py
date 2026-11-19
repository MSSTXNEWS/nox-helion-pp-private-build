import importlib.util
import contextlib
import hashlib
import io
import json
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
    def _emitted_receipt(self, payload):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            observer.emit(payload)
        line = output.getvalue().strip()
        prefix = "NOX_MAINT_LIFELINE_OBSERVER_RECEIPT="
        self.assertTrue(line.startswith(prefix))
        return line, json.loads(line[len(prefix):])

    def _privacy_canary_receipt(self, state):
        socket_path = "/run/secret-supervisor-endpoint-7d91.sock"
        configured_path = "/var/run/secret-configured-socket-7d91.sock"
        config_path = "/etc/supervisor/private-canary-7d91.conf"
        include_path = "/etc/supervisor/conf.d/secret-worker-7d91.conf"
        daemon_path = "/usr/sbin/private-supervisord-7d91"
        script_path = "/root/nox/scripts/private-lifeline-7d91.py"
        cgroup_path = "/sys/fs/cgroup/private-memory-scope-7d91"
        backup_path = "/root/nox/backup/private-request-7d91/private.conf"
        endpoint = {
            "backend": "unix_xmlrpc_read_only",
            "endpoint": {
                "path": socket_path,
                "configured_path": configured_path,
                "serverurl": "unix://" + socket_path,
                "rpc_factory": "RPC_FACTORY_CANARY_7d91",
                "include_glob": "/etc/supervisor/conf.d/private-*.conf",
                "var_run_alias": {"path": "/var/run", "target": "secret-relative-link-7d91"},
                "config_inputs": [{"path": config_path, "sha256": "a" * 64},
                                  {"path": include_path, "sha256": "b" * 64}],
                "socket": {"device": 1, "inode": 2, "mode": 0o660,
                           "uid": 0, "gid": 0, "nlink": 1},
            },
            "daemon": {
                "pid": 123, "start_ticks": 456, "exe": daemon_path,
                "argv": [daemon_path, "-c", config_path],
                "argv_sha256": "c" * 64,
                "config": "private-supervisord-7d91.conf",
                "cgroup": {"cgroup_path": cgroup_path},
                "executable": {"path": daemon_path, "sha256": "d" * 64,
                               "device": 1, "inode": 2},
                "script": {"path": script_path, "sha256": "e" * 64,
                           "device": 1, "inode": 3},
            },
            "api_version": "3.0", "legacy_pid": 321, "legacy_state": "RUNNING",
            "model_pid": 654, "model_state": "STOPPED",
        }
        return {
            "state": state,
            "reason": "HOLD_LIFELINE_OBSERVER_CANARY" if state == "HOLD" else None,
            "supervisor_endpoint": endpoint,
            "supervisor_endpoint_pre_enable": endpoint,
            "supervisor_endpoint_post_enable": endpoint,
            "cgroup_target_before": {
                "target": cgroup_path,
                "self": {"pid": 700, "start_ticks": 800, "cgroup_path": cgroup_path},
                "model": {"state": "STOPPED", "census": {
                    "target": cgroup_path, "scope": "all_visible_proc_pids",
                    "count": 1, "matches": [{"pid": 654, "start_ticks": 900,
                        "cgroup_path": cgroup_path, "in_memory_target_cgroup": True,
                        "argv_sha256": "f" * 64}] }},
            },
            "memory_preflight": {"cgroup_path": cgroup_path,
                                 "memory.current": 10, "memory.max": 100,
                                 "raw_headroom_bytes": 90, "status": "OK"},
            "cgroup_memory": {"cgroup_path": cgroup_path,
                              "memory.current": 10, "memory.max": 100,
                              "raw_headroom_bytes": 90, "status": "OK"},
            "preimages": {config_path: {"sha256": "1" * 64,
                                         "backup": backup_path}},
            "state_artifact_preimages": {"private-state-7d91.json.receipt": {
                "sha256": "2" * 64, "backup": backup_path}},
            "installed_paths": [script_path],
            "canary_paths": (socket_path, configured_path, config_path, include_path,
                             daemon_path, script_path, cgroup_path, backup_path,
                             "RPC_FACTORY_CANARY_7d91", "private-state-7d91.json",
                             "private-supervisord-7d91.conf", "secret-relative-link-7d91"),
        }

    def test_success_receipt_redacts_supervisor_and_memory_paths(self):
        payload = self._privacy_canary_receipt("OBSERVER_ACTIVE")
        canaries = payload.pop("canary_paths")
        line, receipt = self._emitted_receipt(payload)
        for canary in canaries:
            with self.subTest(canary=canary):
                self.assertNotIn(canary, line)
        endpoint = receipt["supervisor_endpoint"]
        self.assertEqual(endpoint["endpoint"]["path_kind"], "unix_socket")
        self.assertEqual(endpoint["endpoint"]["path_sha256"],
                         hashlib.sha256(canaries[0].encode()).hexdigest())
        self.assertEqual(endpoint["daemon"]["pid"], 123)
        self.assertEqual(endpoint["daemon"]["start_ticks"], 456)
        self.assertNotIn("model_pid", line)
        self.assertNotIn("legacy_pid", line)
        self.assertIn("memory_scope_before", receipt)
        self.assertIn("path_sha256", receipt["memory_scope_before"])
        self.assertNotIn("cgroup_path", json.dumps(receipt))

    def test_hold_receipt_redacts_supervisor_and_pre_post_paths(self):
        payload = self._privacy_canary_receipt("HOLD")
        canaries = payload.pop("canary_paths")
        line, receipt = self._emitted_receipt(payload)
        for canary in canaries:
            with self.subTest(canary=canary):
                self.assertNotIn(canary, line)
        self.assertEqual(receipt["state"], "HOLD")
        self.assertIn("supervisor_endpoint_pre_enable", receipt)
        self.assertIn("supervisor_endpoint_post_enable", receipt)
        self.assertNotIn("serverurl", line)
        self.assertNotIn("rpc_factory", line)
        self.assertNotIn("cgroup_path", line)

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
