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

    def test_supervisorctl_never_shell_and_not_train(self):
        with self.assertRaises(ValueError):
            lifeline.supervise("nox-train-volta-t866u","start")
        with patch.object(lifeline.subprocess,"run") as run:
            run.return_value.stdout = "nox-dispatcher-t855u RUNNING pid 123, uptime 0:42:12\n"
            run.return_value.returncode = 0
            result=lifeline.supervise("nox-dispatcher-t855u")
            self.assertEqual(result["pid"],123)
            self.assertEqual(result["state"],"RUNNING")
            self.assertEqual(run.call_args.args[0], ["supervisorctl","status","nox-dispatcher-t855u"])
            self.assertIs(run.call_args.kwargs["shell"],False)

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

if __name__=="__main__":
    unittest.main()
