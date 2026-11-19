import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "lifeline_supervisor_fallback", ROOT / "owner_native_lifeline_observer.py")
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class SupervisorFallbackTests(unittest.TestCase):
    def setUp(self):
        observer.SUPERVISOR_PROGRAM_RELOADED = False
        observer.SUPERVISOR_PROGRAM_ADDED = False
        observer.SUPERVISOR_PROGRAM_STARTED = False
        observer.SUPERVISOR_PROGRAM_AFTER_INVENTORY = None
        observer.SUPERVISOR_PROGRAM_ACTIVATION = None
        observer.SUPERVISOR_PROGRAM_ROLLBACK_PRIOR_GROUPS_UNCHANGED = None

    def test_config_is_one_bounded_root_observer_group(self):
        raw = (ROOT / "supervisor/nox-lifeline-observer.conf").read_bytes()
        options = observer.validate_supervisor_program_config(raw)
        self.assertEqual(options["autostart"], "true")
        self.assertEqual(options["autorestart"], "unexpected")
        self.assertEqual(options["stopasgroup"], "false")
        self.assertEqual(options["killasgroup"], "false")
        self.assertEqual(options["stopwaitsecs"], "5")
        self.assertEqual(options["stdout_logfile"], "NONE")
        self.assertNotIn("shell", options["command"])

    def test_none_log_requires_a_verified_supported_supervisor_version(self):
        for version in ("3.0", "3.0.0", "4.2.5", "4.2.5+vendor.1"):
            with self.subTest(version=version):
                self.assertEqual(observer.validate_supervisor_none_log_version(version), version)
        for version, reason in (("2.4.0", "SUPERVISOR_NONE_LOG_UNSUPPORTED"),
                                ("unknown", "SUPERVISOR_VERSION_UNVERIFIED"),
                                (None, "SUPERVISOR_VERSION_UNVERIFIED")):
            with self.subTest(version=version), self.assertRaisesRegex(observer.Hold, reason):
                observer.validate_supervisor_none_log_version(version)

    def test_config_rejects_group_signals_or_extra_programs(self):
        raw = (ROOT / "supervisor/nox-lifeline-observer.conf").read_bytes()
        with self.assertRaisesRegex(observer.Hold, "SUPERVISOR_PROGRAM_CONFIG_POLICY"):
            observer.validate_supervisor_program_config(
                raw.replace(b"killasgroup=false", b"killasgroup=true"))
        with self.assertRaisesRegex(observer.Hold, "SUPERVISOR_PROGRAM_CONFIG_SECTIONS"):
            observer.validate_supervisor_program_config(
                raw + b"\n[program:unrelated]\ncommand=/bin/true\n")

    def test_reload_delta_accepts_only_one_added_group(self):
        self.assertEqual(observer.validate_reload_config_delta(
            [[[observer.SUPERVISOR_PROGRAM_NAME], [], []]]),
            {"added": [observer.SUPERVISOR_PROGRAM_NAME], "changed": [], "removed": []})
        for delta in (
                [[observer.SUPERVISOR_PROGRAM_NAME, "other"], [], []],
                [[observer.SUPERVISOR_PROGRAM_NAME], ["existing"], []],
                [[observer.SUPERVISOR_PROGRAM_NAME], [], ["existing"]],
                [[observer.SUPERVISOR_PROGRAM_NAME], [], [observer.SUPERVISOR_PROGRAM_NAME]]):
            with self.subTest(delta=delta), self.assertRaises(observer.Hold):
                observer.validate_reload_config_delta(delta)

    def test_rollback_reload_delta_acceptance_is_exactly_scoped(self):
        # Decode the documented nested API 3.0 response and reject additions.
        self.assertEqual(observer.normalize_reload_config_result(
            [[[], [], [observer.SUPERVISOR_PROGRAM_NAME]]]),
            ([], [], [observer.SUPERVISOR_PROGRAM_NAME]))
        self.assertEqual(observer.validate_reload_config_delta(
            [[[], [], [observer.SUPERVISOR_PROGRAM_NAME]]], removed=True)["removed"],
            [observer.SUPERVISOR_PROGRAM_NAME])

    def test_normalized_inventory_detects_changes_to_existing_groups(self):
        baseline = observer.normalize_supervisor_inventory([
            {"group": "worker", "name": "worker_00", "statename": "RUNNING", "pid": 123},
            {"group": observer.SUPERVISOR_PROGRAM_NAME,
             "name": observer.SUPERVISOR_PROGRAM_NAME, "statename": "STOPPED", "pid": 0},
        ])
        after = observer.normalize_supervisor_inventory([
            {"group": "worker", "name": "worker_00", "statename": "RUNNING", "pid": 123},
            {"group": observer.SUPERVISOR_PROGRAM_NAME,
             "name": observer.SUPERVISOR_PROGRAM_NAME, "statename": "RUNNING", "pid": 456},
        ])
        observer.assert_supervisor_old_rows_unchanged(baseline, after)
        changed = list(after)
        changed[1] = {"group": "worker", "name": "worker_00", "state": "STOPPED", "pid": 0}
        with self.assertRaisesRegex(observer.Hold, "SUPERVISOR_EXISTING_GROUP_CHANGED"):
            observer.assert_supervisor_old_rows_unchanged(baseline, changed)

    def test_inventory_rejects_duplicate_and_unbounded_or_invalid_rows(self):
        row = {"group": "worker", "name": "worker", "statename": "RUNNING", "pid": 123}
        with self.assertRaisesRegex(observer.Hold, "SUPERVISOR_INVENTORY_DUPLICATE"):
            observer.normalize_supervisor_inventory([row, row])
        with self.assertRaisesRegex(observer.Hold, "SUPERVISOR_INVENTORY_ROW_INVALID"):
            observer.normalize_supervisor_inventory([dict(row, pid=True)])

    def test_runtime_pin_allows_only_exact_new_config_input(self):
        path = str(observer.SUPERVISOR_PROGRAM)
        old = {"path": "/etc/supervisor/supervisord.conf", "sha256": "a" * 64,
               "ctime_ns": 10}
        added = {"path": path, "sha256": "b" * 64, "ctime_ns": 20}
        baseline = {"endpoint": {"config_inputs": [old], "path": "/run/sock"},
                    "daemon": {"pid": 5, "config_inputs": [old]},
                    "legacy_pid": 6, "model_pid": 7}
        current = {"endpoint": {"config_inputs": [old, added], "path": "/run/sock"},
                   "daemon": {"pid": 5, "config_inputs": [old, added]},
                   "legacy_pid": 6, "model_pid": 7}
        self.assertTrue(observer.supervisor_runtime_delta(current, baseline, added))
        changed = json.loads(json.dumps(current))
        changed["endpoint"]["config_inputs"][0]["sha256"] = "c" * 64
        self.assertFalse(observer.supervisor_runtime_delta(changed, baseline, added))
        unrelated = json.loads(json.dumps(current))
        unrelated["model_pid"] = 99
        self.assertFalse(observer.supervisor_runtime_delta(unrelated, baseline, added))

    def test_activation_orders_reload_add_preflight_then_start_and_preserves_inventory(self):
        baseline = observer.normalize_supervisor_inventory([
            {"group": "worker", "name": "worker", "statename": "RUNNING", "pid": 123},
        ])
        snapshots = [baseline,
                     baseline + [{"group": observer.SUPERVISOR_PROGRAM_NAME,
                                  "name": observer.SUPERVISOR_PROGRAM_NAME,
                                  "state": "STOPPED", "pid": 0}],
                     baseline + [{"group": observer.SUPERVISOR_PROGRAM_NAME,
                                  "name": observer.SUPERVISOR_PROGRAM_NAME,
                                  "state": "RUNNING", "pid": 456}]]
        calls = []

        def inventory():
            calls.append("inventory")
            return snapshots.pop(0)

        def rpc(method, *args):
            calls.append((method, *args))
            if method == "supervisor.reloadConfig":
                return [[[observer.SUPERVISOR_PROGRAM_NAME], [], []]]
            return True

        def pre_start():
            calls.append("pre_start")

        receipt = observer.run_supervisor_group_activation(
            inventory, rpc, baseline, pre_start_fn=pre_start)
        self.assertTrue(receipt["existing_process_inventory_unchanged"])
        self.assertEqual(calls.count(("supervisor.reloadConfig",)), 1)
        self.assertEqual(calls.count(("supervisor.addProcessGroup",
                                     observer.SUPERVISOR_PROGRAM_NAME)), 1)
        self.assertEqual(calls.count(("supervisor.startProcess",
                                     observer.SUPERVISOR_PROGRAM_NAME, True)), 1)
        self.assertLess(calls.index("pre_start"),
                        calls.index(("supervisor.startProcess",
                                     observer.SUPERVISOR_PROGRAM_NAME, True)))
        self.assertFalse(any("update" in call if isinstance(call, str) else False
                             for call in calls))

    def test_activation_polls_starting_until_same_observer_pid_is_running(self):
        baseline = observer.normalize_supervisor_inventory([
            {"group": "worker", "name": "worker", "statename": "RUNNING", "pid": 123},
        ])
        starting = baseline + [{"group": observer.SUPERVISOR_PROGRAM_NAME,
                                "name": observer.SUPERVISOR_PROGRAM_NAME,
                                "state": "STARTING", "pid": 456}]
        stopped = baseline + [{"group": observer.SUPERVISOR_PROGRAM_NAME,
                               "name": observer.SUPERVISOR_PROGRAM_NAME,
                               "state": "STOPPED", "pid": 0}]
        running = baseline + [{"group": observer.SUPERVISOR_PROGRAM_NAME,
                               "name": observer.SUPERVISOR_PROGRAM_NAME,
                               "state": "RUNNING", "pid": 456}]
        snapshots = [baseline, stopped, starting, running]
        sleeps = []

        def rpc(method, *args):
            if method == "supervisor.reloadConfig":
                return [[[observer.SUPERVISOR_PROGRAM_NAME], [], []]]
            return True

        receipt = observer.run_supervisor_group_activation(
            lambda: snapshots.pop(0), rpc, baseline, sleep_fn=sleeps.append)
        self.assertEqual(receipt["observer_process"]["state"], "RUNNING")
        self.assertEqual(receipt["observer_process"]["pid"], 456)
        self.assertEqual(sleeps, [observer.SUPERVISOR_STATE_POLL_INTERVAL_SECONDS])

    def test_activation_holds_if_any_existing_process_changes(self):
        baseline = observer.normalize_supervisor_inventory([
            {"group": "worker", "name": "worker", "statename": "RUNNING", "pid": 123},
        ])
        changed = [{"group": "worker", "name": "worker", "state": "STOPPED", "pid": 0}]
        inventories = [changed]
        with self.assertRaisesRegex(observer.Hold, "SUPERVISOR_EXISTING_GROUP_CHANGED"):
            observer.run_supervisor_group_activation(
                lambda: inventories.pop(0),
                lambda method, *args: [[[observer.SUPERVISOR_PROGRAM_NAME], [], []]],
                baseline)

    def test_rpc_allowlist_rejects_other_groups_and_mutations(self):
        with self.assertRaisesRegex(observer.Hold, "SUPERVISOR_RPC_OPERATION_NOT_ALLOWLISTED"):
            observer.supervisor_rpc("supervisor.stopProcess", "nox-ds41-8098", True)
        with self.assertRaisesRegex(observer.Hold, "SUPERVISOR_RPC_OPERATION_NOT_ALLOWLISTED"):
            observer.supervisor_rpc("supervisor.startAllProcesses", True)

    def test_rollback_stops_removes_and_restores_only_observer_config(self):
        baseline = observer.normalize_supervisor_inventory([
            {"group": "worker", "name": "worker", "statename": "RUNNING", "pid": 123},
        ])
        running = baseline + [{"group": observer.SUPERVISOR_PROGRAM_NAME,
                               "name": observer.SUPERVISOR_PROGRAM_NAME,
                               "state": "RUNNING", "pid": 456}]
        stopped = baseline + [{"group": observer.SUPERVISOR_PROGRAM_NAME,
                               "name": observer.SUPERVISOR_PROGRAM_NAME,
                               "state": "STOPPED", "pid": 0}]
        drifted_worker = {"group": "worker", "name": "worker",
                          "state": "STOPPED", "pid": 0}
        stopped_with_drift = [drifted_worker, stopped[-1]]
        drifted_after = [drifted_worker]
        restored = []
        installed = b"exact observer config"
        with (patch.object(observer, "SUPERVISORCTL_PIN", {"after": True}),
              patch.object(observer, "SUPERVISOR_BASELINE_PIN", {"base": True}),
              patch.object(observer, "SUPERVISOR_PROGRAM_BEFORE_INVENTORY", baseline),
              patch.object(observer, "SUPERVISOR_PROGRAM_INSTALLED", installed),
              patch.object(observer, "SUPERVISOR_PROGRAM_PREIMAGE", (None, None)),
              patch.object(observer, "SUPERVISOR_PROGRAM_RELOADED", True),
              patch.object(observer, "SUPERVISOR_PROGRAM_ADDED", True),
              patch.object(observer, "SUPERVISOR_PROGRAM_STARTED", True),
              patch.object(observer, "SUPERVISOR_ALLOWED_PROGRAM_CONFIG", {
                  "path": str(observer.SUPERVISOR_PROGRAM), "sha256": "b" * 64}),
              patch.object(observer, "INSTALLED", {str(observer.SUPERVISOR_PROGRAM): installed}),
              patch.object(observer, "supervisor_inventory",
                           side_effect=[running, stopped_with_drift, drifted_after]),
              patch.object(observer, "process_identity",
                           return_value={"pid": 456, "start_ticks": 12345}),
              patch.object(observer, "supervisor_rpc", side_effect=[True, True, [[], [], []]]) as rpc,
              patch.object(observer, "_supervisor_client_snapshot", return_value={"base": True}),
              patch.object(observer, "restore_supervisor_file",
                           side_effect=lambda *args: restored.append(args))):
            result = observer.rollback_supervisor_fallback()
        self.assertEqual(result, "OBSERVER_GROUP_STOPPED_REMOVED;EXACT_CONFIG_AND_FILE_PREIMAGES_RESTORED")
        self.assertFalse(observer.SUPERVISOR_PROGRAM_ROLLBACK_PRIOR_GROUPS_UNCHANGED)
        self.assertEqual([call.args for call in rpc.call_args_list], [
            ("supervisor.stopProcess", observer.SUPERVISOR_PROGRAM_NAME, True),
            ("supervisor.removeProcessGroup", observer.SUPERVISOR_PROGRAM_NAME),
            ("supervisor.reloadConfig",),
        ])
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0][0], observer.SUPERVISOR_PROGRAM)
        self.assertEqual(restored[0][1], installed)

    def test_rollback_removes_crashed_observer_groups_without_signaling_pid_zero(self):
        baseline = observer.normalize_supervisor_inventory([
            {"group": "worker", "name": "worker", "statename": "RUNNING", "pid": 123},
        ])
        installed = b"exact observer config"
        for state in ("BACKOFF", "EXITED", "FATAL"):
            with self.subTest(state=state):
                before = baseline + [{"group": observer.SUPERVISOR_PROGRAM_NAME,
                                      "name": observer.SUPERVISOR_PROGRAM_NAME,
                                      "state": state, "pid": 0}]
                restored = []
                with (patch.object(observer, "SUPERVISORCTL_PIN", {"after": True}),
                      patch.object(observer, "SUPERVISOR_BASELINE_PIN", {"base": True}),
                      patch.object(observer, "SUPERVISOR_PROGRAM_BEFORE_INVENTORY", baseline),
                      patch.object(observer, "SUPERVISOR_PROGRAM_INSTALLED", installed),
                      patch.object(observer, "SUPERVISOR_PROGRAM_PREIMAGE", (None, None)),
                      patch.object(observer, "SUPERVISOR_PROGRAM_RELOADED", True),
                      patch.object(observer, "SUPERVISOR_PROGRAM_ADDED", True),
                      patch.object(observer, "SUPERVISOR_ALLOWED_PROGRAM_CONFIG", {
                          "path": str(observer.SUPERVISOR_PROGRAM), "sha256": "b" * 64}),
                      patch.object(observer, "INSTALLED", {
                          str(observer.SUPERVISOR_PROGRAM): installed}),
                      patch.object(observer, "supervisor_inventory",
                                   side_effect=[before, baseline]),
                      patch.object(observer, "process_identity") as identity,
                      patch.object(observer, "supervisor_rpc",
                                   side_effect=[True, [[[], [], [observer.SUPERVISOR_PROGRAM_NAME]]]]) as rpc,
                      patch.object(observer, "_supervisor_client_snapshot",
                                   return_value={"base": True}),
                      patch.object(observer, "restore_supervisor_file",
                                   side_effect=lambda *args: restored.append(args))):
                    result = observer.rollback_supervisor_fallback()
                self.assertEqual(result,
                                 "OBSERVER_GROUP_STOPPED_REMOVED;EXACT_CONFIG_AND_FILE_PREIMAGES_RESTORED")
                identity.assert_not_called()
                self.assertEqual([call.args for call in rpc.call_args_list], [
                    ("supervisor.removeProcessGroup", observer.SUPERVISOR_PROGRAM_NAME),
                    ("supervisor.reloadConfig",),
                ])
                self.assertEqual(len(restored), 1)
                self.assertEqual(restored[0][0], observer.SUPERVISOR_PROGRAM)
                self.assertEqual(restored[0][1], installed)

    def test_rollback_holds_for_ambiguous_nonrunning_observer_state(self):
        baseline = observer.normalize_supervisor_inventory([
            {"group": "worker", "name": "worker", "statename": "RUNNING", "pid": 123},
        ])
        ambiguous = baseline + [{"group": observer.SUPERVISOR_PROGRAM_NAME,
                                 "name": observer.SUPERVISOR_PROGRAM_NAME,
                                 "state": "UNKNOWN", "pid": 0}]
        with (patch.object(observer, "SUPERVISORCTL_PIN", {"after": True}),
              patch.object(observer, "SUPERVISOR_BASELINE_PIN", {"base": True}),
              patch.object(observer, "SUPERVISOR_PROGRAM_BEFORE_INVENTORY", baseline),
              patch.object(observer, "SUPERVISOR_PROGRAM_INSTALLED", None),
              patch.object(observer, "INSTALLED", {}),
              patch.object(observer, "supervisor_inventory", return_value=ambiguous),
              patch.object(observer, "supervisor_rpc") as rpc):
            with self.assertRaisesRegex(observer.Hold,
                                        "SUPERVISOR_ROLLBACK_TARGET_STATE_AMBIGUOUS"):
                observer.rollback_supervisor_fallback()
        rpc.assert_not_called()

    def test_owner_entrypoint_rolls_back_after_fallback_file_write_failure(self):
        receipts = []
        with (patch.object(observer, "SUPERVISOR_BACKEND_ACTIVE", True),
              patch.object(observer, "INSTALLED", {"observer-runtime": b"installed"}),
              patch.object(observer, "STATE_DIR_PREIMAGE", None),
              patch.object(observer, "SUPERVISOR_PROGRAM_RELOADED", False),
              patch.object(observer, "SUPERVISOR_PROGRAM_ADDED", False),
              patch.object(observer, "SUPERVISOR_PROGRAM_STARTED", False),
              patch.object(observer, "OWNER_LOCK_FD", 71),
              patch.object(observer, "SOURCE_SHA_VALUE", "a" * 40),
              patch.object(observer, "REQUEST_ID", "17"),
              patch.object(observer, "CGROUP_TARGET_EVIDENCE", None),
              patch.object(observer.signal, "signal"),
              patch.object(observer.os, "close") as close_fd,
              patch.object(observer, "rollback_supervisor_fallback",
                           return_value="ROLLBACK_FILE_WRITE") as rollback,
              patch.object(observer, "restore_state_artifacts") as restore_state,
              patch.object(observer, "emit", side_effect=receipts.append)):
            def fail_after_write():
                raise observer.Hold("HOLD_LIFELINE_OBSERVER_INJECTED_AFTER_FILE_WRITE")

            result = observer.run_owner_entrypoint(fail_after_write)
        self.assertEqual(result, 2)
        rollback.assert_called_once_with()
        restore_state.assert_called_once_with()
        close_fd.assert_called_once_with(71)
        self.assertEqual(receipts[0]["state"], "HOLD")
        self.assertEqual(receipts[0]["reason"],
                         "HOLD_LIFELINE_OBSERVER_INJECTED_AFTER_FILE_WRITE")
        self.assertEqual(receipts[0]["rollback"], "ROLLBACK_FILE_WRITE")

    def test_owner_entrypoint_rolls_back_after_fallback_group_start_failure(self):
        receipts = []
        with (patch.object(observer, "SUPERVISOR_BACKEND_ACTIVE", True),
              patch.object(observer, "INSTALLED", {}),
              patch.object(observer, "STATE_DIR_PREIMAGE", None),
              patch.object(observer, "SUPERVISOR_PROGRAM_RELOADED", True),
              patch.object(observer, "SUPERVISOR_PROGRAM_ADDED", True),
              patch.object(observer, "SUPERVISOR_PROGRAM_STARTED", True),
              patch.object(observer, "OWNER_LOCK_FD", 72),
              patch.object(observer, "SOURCE_SHA_VALUE", "b" * 40),
              patch.object(observer, "REQUEST_ID", "18"),
              patch.object(observer, "CGROUP_TARGET_EVIDENCE", None),
              patch.object(observer.signal, "signal"),
              patch.object(observer.os, "close") as close_fd,
              patch.object(observer, "rollback_supervisor_fallback",
                           return_value="ROLLBACK_GROUP_START") as rollback,
              patch.object(observer, "restore_state_artifacts") as restore_state,
              patch.object(observer, "emit", side_effect=receipts.append)):
            def fail_after_start():
                raise observer.Hold("HOLD_LIFELINE_OBSERVER_INJECTED_AFTER_GROUP_START")

            result = observer.run_owner_entrypoint(fail_after_start)
        self.assertEqual(result, 2)
        rollback.assert_called_once_with()
        restore_state.assert_called_once_with()
        close_fd.assert_called_once_with(72)
        self.assertEqual(receipts[0]["state"], "HOLD")
        self.assertEqual(receipts[0]["reason"],
                         "HOLD_LIFELINE_OBSERVER_INJECTED_AFTER_GROUP_START")
        self.assertEqual(receipts[0]["rollback"], "ROLLBACK_GROUP_START")

    def test_rollback_stops_starting_and_stopping_observer_processes_by_exact_group(self):
        baseline = observer.normalize_supervisor_inventory([
            {"group": "worker", "name": "worker", "statename": "RUNNING", "pid": 123},
        ])
        installed = b"exact observer config"
        for initial_state in ("STARTING", "STOPPING"):
            with self.subTest(initial_state=initial_state):
                target = {"group": observer.SUPERVISOR_PROGRAM_NAME,
                          "name": observer.SUPERVISOR_PROGRAM_NAME,
                          "state": initial_state, "pid": 456}
                stopping = dict(target, state="STOPPING")
                stopped = dict(target, state="STOPPED", pid=0)
                before = baseline + [target]
                after_stop = baseline + [stopping,]
                terminal = baseline + [stopped]
                restored = []
                with (patch.object(observer, "SUPERVISORCTL_PIN", {"after": True}),
                      patch.object(observer, "SUPERVISOR_BASELINE_PIN", {"base": True}),
                      patch.object(observer, "SUPERVISOR_PROGRAM_BEFORE_INVENTORY", baseline),
                      patch.object(observer, "SUPERVISOR_PROGRAM_INSTALLED", installed),
                      patch.object(observer, "SUPERVISOR_PROGRAM_PREIMAGE", (None, None)),
                      patch.object(observer, "SUPERVISOR_PROGRAM_RELOADED", True),
                      patch.object(observer, "SUPERVISOR_PROGRAM_ADDED", True),
                      patch.object(observer, "SUPERVISOR_ALLOWED_PROGRAM_CONFIG", {
                          "path": str(observer.SUPERVISOR_PROGRAM), "sha256": "b" * 64}),
                      patch.object(observer, "INSTALLED", {
                          str(observer.SUPERVISOR_PROGRAM): installed}),
                      patch.object(observer, "supervisor_inventory",
                                   side_effect=[before, after_stop, terminal, baseline]),
                      patch.object(observer, "process_identity",
                                   return_value={"pid": 456, "start_ticks": 12345}) as identity,
                      patch.object(observer, "supervisor_rpc",
                                   side_effect=[True, True, [[[], [], [
                                       observer.SUPERVISOR_PROGRAM_NAME]]]]) as rpc,
                      patch.object(observer, "_supervisor_client_snapshot",
                                   return_value={"base": True}),
                      patch.object(observer, "restore_supervisor_file",
                                   side_effect=lambda *args: restored.append(args))):
                    result = observer.rollback_supervisor_fallback()
                self.assertEqual(result,
                                 "OBSERVER_GROUP_STOPPED_REMOVED;EXACT_CONFIG_AND_FILE_PREIMAGES_RESTORED")
                identity.assert_called_once_with(456)
                self.assertEqual([call.args for call in rpc.call_args_list], [
                    ("supervisor.stopProcess", observer.SUPERVISOR_PROGRAM_NAME, True),
                    ("supervisor.removeProcessGroup", observer.SUPERVISOR_PROGRAM_NAME),
                    ("supervisor.reloadConfig",),
                ])
                self.assertEqual(len(restored), 1)

    def test_memory_headroom_uses_distinct_pre_and_post_thresholds(self):
        good = {"status": "OK", "raw_headroom_bytes": 3 * 1024**3}
        observer.require_memory_headroom(good, 2 * 1024**3 + 512 * 1024**2, "PRE")
        observer.require_memory_headroom(good, 2 * 1024**3, "POST")
        with self.assertRaisesRegex(observer.Hold, "HOLD_LIFELINE_OBSERVER_PRE"):
            observer.require_memory_headroom(
                {"status": "OK", "raw_headroom_bytes": 2 * 1024**3 + 511 * 1024**2},
                2 * 1024**3 + 512 * 1024**2, "PRE")

    def test_main_routes_to_fallback_only_when_systemd_is_absent(self):
        with (patch.dict("os.environ", {"NOX_OWNER_SOURCE_SHA": "a" * 40,
                                         "NOX_OWNER_REQUEST_ID": "7"}),
              patch.object(observer.os, "geteuid", return_value=0),
              patch.object(Path, "is_dir", return_value=False),
              patch.object(observer, "supervisor_fallback_main", return_value=17) as fallback):
            self.assertEqual(observer.main(), 17)
        fallback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
