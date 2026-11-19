"""Source-level bounded tests for the original NOX Supervisor lifeline."""
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

script = Path(__file__).with_name("nox_native_lifeline.py")
spec = importlib.util.spec_from_file_location("nox_native_lifeline", script)
lifeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lifeline)

def policy(*, enabled=True, restart=True):
    return lifeline.policy_check({
        "schema": lifeline.SCHEMA, "enabled": enabled,
        "poll_seconds": 60, "consecutive_failures": 3,
        "cooldown_seconds": 300, "daily_limit": 2,
        "services": [{"name": "nox-dispatcher-t855u", "restart": restart}],
    })

class LifelineTests(unittest.TestCase):
    def test_policy_json_duplicate_keys_and_nonfinite_are_rejected(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "owner-policy.json"
            original = json.dumps(policy(enabled=False, restart=False))
            path.write_text(original, encoding="utf-8")
            self.assertFalse(lifeline.policy_load(path)["enabled"])
            for bad in (
                original.replace('"enabled": false',
                                 '"enabled": false, "enabled": true', 1),
                original.replace('"restart": false',
                                 '"restart": false, "restart": true', 1),
                original.replace('"daily_limit": 2',
                                 '"daily_limit": 2, "daily_limit": 0', 1),
                original.replace('"poll_seconds": 60',
                                 '"poll_seconds": NaN', 1),
                original.replace('"poll_seconds": 60',
                                 '"poll_seconds": Infinity', 1),
                original.replace('"poll_seconds": 60',
                                 '"poll_seconds": 1e309', 1),
            ):
                with self.subTest(bad=bad):
                    self.assertNotEqual(bad, original)
                    path.write_text(bad, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "HOLD_POLICY_CORRUPT"):
                        lifeline.policy_load(path)
                    self.assertEqual(path.read_text(encoding="utf-8"), bad)

    def state(self, directory):
        return {"_path": Path(directory) / "state.json", "services": {}}

    def test_policy_allowlist_and_ranges(self):
        p = policy()
        p["services"][0]["name"] = "nox-train-volta-t866u"
        with self.assertRaises(ValueError):
            lifeline.policy_check(p)
        p = policy()
        p["daily_limit"] = 200
        with self.assertRaises(ValueError):
            lifeline.policy_check(p)
        p = policy()
        p["enabled"] = 1
        with self.assertRaises(ValueError):
            lifeline.policy_check(p)

    def test_policy_file_symlink_and_perms(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"p.json"
            path.write_text("{}")
            path.chmod(0o666)
            with self.assertRaises(ValueError):
                lifeline.policy_load(path)
            link = Path(d)/"link"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                lifeline.policy_load(link)
            path.chmod(0o600)
            hardlink = Path(d)/"hardlinked-policy"
            os.link(path, hardlink)
            with self.assertRaisesRegex(ValueError, "HOLD_POLICY_FILE"):
                lifeline.policy_load(path)

    def test_supervisorctl_never_shell_and_not_train(self):
        with self.assertRaises(ValueError):
            lifeline.supervise("nox-train-volta-t866u","start")
        with patch.object(lifeline, "_supervisor_row", return_value={
                "name": "nox-dispatcher-t855u", "statename": "RUNNING", "pid": 123}):
            result=lifeline.supervise("nox-dispatcher-t855u")
            self.assertEqual(result["pid"],123)
            self.assertEqual(result["state"],"RUNNING")

    def test_no_mutation_while_disabled(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.state(d)
            calls=[]
            def fn(name, command="status"):
                calls.append(command)
                return {"state":"STOPPED","pid":None}
            for n in range(4):
                outcome=lifeline.tick(policy(enabled=False),s,now=100+n,status_fn=fn,stop_fn=lambda:False)
            self.assertEqual(outcome["results"][0]["action"],"owner_authorization_required")
            self.assertEqual(calls.count("start"),0)

    def test_stop_prevents_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.state(d)
            def fn(name,command="status"):
                if command=="start": raise AssertionError("must not start")
                return {"state":"EXITED","pid":None}
            for n in range(4):
                outcome=lifeline.tick(policy(),s,now=100+n,status_fn=fn,stop_fn=lambda:True)
            self.assertEqual(outcome["results"][0]["action"],"stop_or_maintenance_lock")

    def test_only_after_three_failures_and_readback(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.state(d)
            calls=[]
            def fn(name,command="status"):
                calls.append(command)
                if command=="start": return {"rc":0}
                if calls.count("start"): return {"state":"RUNNING","pid":123,"rc":0}
                return {"state":"STOPPED","pid":None,"rc":0}
            for n in range(2):
                outcome=lifeline.tick(policy(),s,now=100+n,status_fn=fn,stop_fn=lambda:False)
                self.assertEqual(outcome["results"][0]["action"],"observation_only")
            outcome=lifeline.tick(policy(),s,now=103,status_fn=fn,stop_fn=lambda:False)
            self.assertEqual(outcome["results"][0]["action"],"started_verified")
            self.assertEqual(calls.count("start"),1)
            self.assertTrue(Path(d,"state.json").exists())

    def test_unknown_and_fatal_never_restart(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.state(d)
            commands=[]
            def fn(name,command="status"):
                commands.append(command)
                return {"state":"FATAL","pid":None}
            for n in range(5):
                result=lifeline.tick(policy(),s,now=100+n,status_fn=fn,stop_fn=lambda:False)
            self.assertEqual(result["results"][0]["action"],"owner_investigation_required")
            self.assertNotIn("start",commands)

    def test_daily_budget_blocks_storm(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.state(d)
            s["services"]={"nox-dispatcher-t855u":{"attempts":[90,91],"failures":4}}
            commands=[]
            def fn(name,command="status"):
                commands.append(command)
                return {"state":"STOPPED","pid":None}
            result=lifeline.tick(policy(),s,now=100,status_fn=fn,stop_fn=lambda:False)
            self.assertEqual(result["results"][0]["action"],"daily_repair_budget_exhausted")
            self.assertNotIn("start",commands)

    def test_ambiguous_start_consumes_attempt(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.state(d)
            s["services"]={"nox-dispatcher-t855u":{"attempts":[],"failures":2}}
            def fn(name,command="status"):
                if command=="start": return {"rc":1}
                return {"state":"STOPPED","pid":None,"rc":0}
            result=lifeline.tick(policy(),s,now=100,status_fn=fn,stop_fn=lambda:False)
            self.assertEqual(result["results"][0]["action"],"start_failed_hold")
            self.assertEqual(s["services"]["nox-dispatcher-t855u"]["attempts"],[100])

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.state(d)
            s["services"]={"nox-dispatcher-t855u":{"attempts":[],"failures":2}}
            def fn(name,command="status"):
                if command=="start": raise AssertionError("dry-run must not start")
                return {"state":"STOPPED","pid":None}
            result=lifeline.tick(policy(),s,now=100,status_fn=fn,stop_fn=lambda:False,dry_run=True)
            self.assertEqual(result["results"][0]["action"],"would_start")
            self.assertFalse(Path(d,"state.json").exists())


    def test_missing_state_bootstraps_but_corrupt_existing_state_holds(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "state.json"
            self.assertEqual(lifeline.read_state(f), {})
            f.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "HOLD_STATE_CORRUPT"):
                lifeline.read_state(f)
            f.write_text('{"services":[]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "HOLD_STATE_STRUCTURE"):
                lifeline.read_state(f)

    def test_lifeline_restart_state_must_not_be_world_writable_or_hardlinked(self):
        # If an untrusted actor could rewrite attempts, the restart rate limits
        # would be reset. The guarded read must HOLD before any service action.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            raw = '{"services":{"nox-dispatcher-t855u":{"attempts":[1,2],"failures":2}}}'
            path.write_text(raw, encoding="utf-8")
            path.chmod(0o666)
            with self.assertRaisesRegex(ValueError, "HOLD_STATE_PERMISSIONS"):
                lifeline.read_state(path)
            self.assertEqual(path.read_text(encoding="utf-8"), raw)
            path.chmod(0o600)
            copy = Path(d) / "state-hardlink.json"
            os.link(path, copy)
            with self.assertRaisesRegex(ValueError, "HOLD_STATE_FILE"):
                lifeline.read_state(path)
            copy.unlink()
            self.assertEqual(lifeline.read_state(path)["services"]
                             ["nox-dispatcher-t855u"]["attempts"], [1,2])

    def test_repair_history_corruption_never_resets_attempts(self):
        with tempfile.TemporaryDirectory() as d:
            s = self.state(d)
            s["services"] = {"nox-dispatcher-t855u": {"attempts": ["bad"], "failures": 2}}
            def fn(name, command="status"):
                if command == "start":
                    raise AssertionError("unexpected Supervisor start")
                return {"state": "STOPPED", "pid": None}
            with self.assertRaisesRegex(ValueError, "HOLD_REPAIR_HISTORY_CORRUPT"):
                lifeline.tick(policy(), s, now=100, status_fn=fn, stop_fn=lambda: False)

    def test_two_retries_in_rolling_hour_even_when_daily_policy_three(self):
        with tempfile.TemporaryDirectory() as d:
            s = self.state(d)
            p = policy()
            p["daily_limit"] = 3
            s["services"] = {"nox-dispatcher-t855u": {"attempts": [100, 200], "failures": 2}}
            commands = []
            def fn(name, command="status"):
                commands.append(command)
                return {"state": "STOPPED", "pid": None}
            result = lifeline.tick(p, s, now=300, status_fn=fn, stop_fn=lambda: False)
            self.assertEqual(result["results"][0]["action"], "hourly_repair_budget_exhausted")
            self.assertNotIn("start", commands)

    def test_service_recovers_during_admission_no_second_start(self):
        with tempfile.TemporaryDirectory() as d:
            s = self.state(d)
            s["services"] = {"nox-dispatcher-t855u": {"attempts": [], "failures": 2}}
            commands = []
            def fn(name, command="status"):
                commands.append(command)
                if command == "start":
                    raise AssertionError("double-start must not be attempted")
                if len(commands) == 1:
                    return {"state": "STOPPED", "pid": None}
                return {"state": "RUNNING", "pid": 456}
            result = lifeline.tick(policy(), s, now=300, status_fn=fn, stop_fn=lambda: False)
            self.assertEqual(result["results"][0]["action"], "service_changed_before_start_hold")
            self.assertEqual(commands, ["status", "status"])
            self.assertFalse(Path(d, "state.json").exists())


    def test_supervisor_rc3_exact_stop_is_observed_but_never_automatically_started_when_disabled(self):
        with patch.object(lifeline, "_supervisor_row", return_value={
                "name": "nox-dispatcher-t855u", "statename": "STOPPED", "pid": 0}):
            self.assertEqual(lifeline.supervise("nox-dispatcher-t855u"),
                             {"state":"STOPPED","pid":None,"rc":3})
        with tempfile.TemporaryDirectory() as d:
            state = self.state(d)
            calls = []
            def observe(name, command="status"):
                calls.append(command)
                return {"state":"STOPPED","pid":None,"rc":3}
            for i in range(3):
                lifeline.tick(policy(enabled=False, restart=False), state, now=100+i,
                              status_fn=observe, stop_fn=lambda:True)
            self.assertNotIn("start", calls)

    def test_supervisor_rpc_state_requires_consistent_pid(self):
        cases = (("RUNNING", 123, "RUNNING"), ("FATAL", 0, "FATAL"),
                 ("STOPPED", 987, "UNKNOWN"))
        for state, pid, expected in cases:
            with self.subTest(state=state, pid=pid), patch.object(
                    lifeline, "_supervisor_row", return_value={
                        "name": "nox-dispatcher-t855u", "statename": state, "pid": pid}):
                self.assertEqual(lifeline.supervise("nox-dispatcher-t855u")["state"], expected)

    def test_nonzero_supervisorctl_status_cannot_start_any_service(self):
        with tempfile.TemporaryDirectory() as d:
            s = self.state(d)
            observed = []
            def native(name):
                observed.append(name)
                raise OSError("RPC unavailable")
            with patch.object(lifeline, "_supervisor_row", side_effect=native):
                for n in range(4):
                    result = lifeline.tick(policy(), s, now=100+n,
                        status_fn=lifeline.supervise, stop_fn=lambda: False)
            self.assertEqual(result["results"][0]["action"], "owner_investigation_required")
            self.assertTrue(observed)
            self.assertTrue(all(name == "nox-dispatcher-t855u" for name in observed))

    def test_nonzero_status_running_output_is_not_health_proof(self):
        with patch.object(lifeline, "_supervisor_row", side_effect=OSError("RPC unavailable")):
            observed = lifeline.supervise("nox-dispatcher-t855u")
            self.assertEqual(observed, {"state": "UNKNOWN", "pid": None, "rc": 124})

    def test_exit_with_pid_does_not_authorize_duplicate_start(self):
        with tempfile.TemporaryDirectory() as d:
            s = self.state(d)
            seen = []
            def native(name):
                seen.append(name)
                return {"name": name, "statename": "EXITED", "pid": 7637}
            with patch.object(lifeline, "_supervisor_row", side_effect=native):
                for n in range(4):
                    result = lifeline.tick(policy(), s, now=100+n,
                        status_fn=lifeline.supervise, stop_fn=lambda: False)
            self.assertEqual(result["results"][0]["action"], "owner_investigation_required")
            self.assertTrue(all(name == "nox-dispatcher-t855u" for name in seen))

    def test_persisted_malformed_service_record_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            raw = '{"services":{"nox-dispatcher-t855u":null}}'
            path.write_text(raw, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "HOLD_STATE_SERVICE_ROW"):
                lifeline.read_state(path)
            self.assertEqual(path.read_text(encoding="utf-8"), raw)

    def test_ambiguous_persisted_attempts_never_erase_repair_budget(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            payloads = (
                '{"services":{},"services":{"nox-dispatcher-t855u":{"attempts":[1]}}}',
                '{"services":{"nox-dispatcher-t855u":{"attempts":[1],"attempts":[]}}}',
                '{"services":{"nox-dispatcher-t855u":{"attempts":[NaN]}}}',
                '{"services":{"nox-dispatcher-t855u":{"failures":Infinity}}}',
            )
            for raw in payloads:
                with self.subTest(raw=raw):
                    path.write_text(raw, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "HOLD_STATE_CORRUPT"):
                        lifeline.read_state(path)
                    self.assertEqual(path.read_text(encoding="utf-8"), raw)

    def test_all_histories_preflight_before_any_service_start(self):
        with tempfile.TemporaryDirectory() as d:
            p = policy()
            p["services"].append({"name": "nox-priority-scheduler", "restart": True})
            for bad in (-1, True, 3.2, "2", 1001):
                with self.subTest(failures=bad):
                    state = self.state(d)
                    state["services"] = {
                        "nox-dispatcher-t855u": {"attempts": [], "failures": 3},
                        "nox-priority-scheduler": {"attempts": [], "failures": bad},
                    }
                    commands = []
                    def observer(name, command="status"):
                        commands.append((name, command))
                        return {"state": "STOPPED", "pid": None, "rc": 0}
                    with self.assertRaisesRegex(ValueError, "HOLD_REPAIR_HISTORY_CORRUPT"):
                        lifeline.tick(p, state, now=1000, status_fn=observer,
                                      stop_fn=lambda: False)
                    self.assertEqual(commands, [])
                    self.assertEqual(state["services"]["nox-dispatcher-t855u"]["failures"], 3)

    def test_corrupt_in_memory_repair_ledger_is_not_reset_or_restarted(self):
        with tempfile.TemporaryDirectory() as d:
            for value in (None, ["damaged"]):
                state = {"_path": Path(d) / "state.json", "services": value}
                with self.assertRaisesRegex(ValueError, "HOLD_REPAIR_HISTORY_CORRUPT"):
                    lifeline.tick(policy(), state, now=1000,
                        status_fn=lambda *_: {"state": "STOPPED", "pid": None},
                        stop_fn=lambda: False)
                self.assertEqual(state["services"], value)
            state = {"_path": Path(d) / "state.json",
                     "services": {"nox-dispatcher-t855u": "damaged"}}
            with self.assertRaisesRegex(ValueError, "HOLD_REPAIR_HISTORY_CORRUPT"):
                lifeline.tick(policy(), state, now=1000,
                    status_fn=lambda *_: {"state": "STOPPED", "pid": None},
                    stop_fn=lambda: False)
            self.assertEqual(state["services"]["nox-dispatcher-t855u"], "damaged")

    def test_supervisor_nonzero_rc_never_reports_running_from_stdout(self):
        with patch.object(lifeline, "_supervisor_row", side_effect=OSError("RPC unavailable")):
            status = lifeline.supervise("nox-dispatcher-t855u")
            self.assertEqual(status, {"state": "UNKNOWN", "pid": None, "rc": 124})


    def test_owner_canonical_state_stop_fences_and_dangling_link(self):
        # The read-only owner inspector recognizes both state-level STOP aliases.
        self.assertIn("/root/nox/state/STOP", lifeline.STOP_FILES)
        self.assertIn("/root/nox/state/STOP.flag", lifeline.STOP_FILES)
        self.assertIn("/root/nox/state/OWNER_MAINTENANCE.flag", lifeline.STOP_FILES)
        with tempfile.TemporaryDirectory() as d:
            stop = Path(d) / "STOP.flag"
            with patch.object(lifeline, "STOP_FILES", (str(stop),)):
                stop.write_text("owner STOP", encoding="utf-8")
                self.assertTrue(lifeline.stopped())
                state = self.state(d)
                status_commands = []
                def status(name, command="status"):
                    status_commands.append(command)
                    if command == "start":
                        raise AssertionError("owner STOP must prevent restart")
                    return {"state": "STOPPED", "pid": None, "rc": 0}
                for tick in range(3):
                    observed = lifeline.tick(policy(), state, now=100+tick,
                        status_fn=status, stop_fn=lifeline.stopped)
                self.assertEqual(observed["results"][0]["action"], "stop_or_maintenance_lock")
                self.assertNotIn("start", status_commands)
                stop.unlink()
                stop.symlink_to(Path(d) / "missing")
                self.assertTrue(lifeline.stopped())

    def test_unreadable_owner_stop_path_fails_closed(self):
        with patch.object(lifeline, "STOP_FILES", ("/root/nox/state/STOP.flag",)):
            with patch.object(lifeline.os, "lstat", side_effect=PermissionError("denied")):
                self.assertTrue(lifeline.stopped())


    def test_malformed_supervisor_pid_cannot_authorize_automatic_restart(self):
        with tempfile.TemporaryDirectory() as d:
            state = self.state(d)
            seen = []
            def native(name):
                seen.append(name)
                return {"name": name, "statename": "STOPPED", "pid": 987}
            with patch.object(lifeline, "_supervisor_row", side_effect=native):
                for t in range(3):
                    report = lifeline.tick(policy(), state, now=100+t,
                        status_fn=lifeline.supervise, stop_fn=lambda: False)
            self.assertEqual(report["results"][0]["action"], "owner_investigation_required")
            self.assertEqual(state["services"]["nox-dispatcher-t855u"]["attempts"], [])
            self.assertTrue(all(name == "nox-dispatcher-t855u" for name in seen))
            self.assertFalse(Path(d, "state.json").exists())

    def test_normal_stopped_description_remains_repairable_observation(self):
        with patch.object(lifeline, "_supervisor_row", return_value={
                "name": "nox-dispatcher-t855u", "statename": "STOPPED", "pid": 0}):
            self.assertEqual(lifeline.supervise("nox-dispatcher-t855u")["state"], "STOPPED")

if __name__=="__main__":
    unittest.main()
