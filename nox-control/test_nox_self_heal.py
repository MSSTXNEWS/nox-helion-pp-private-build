"""NOX self-heal safe behavior regression checks."""
import importlib.util
import json
import fcntl
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parent / "nox_self_heal.py"
spec = importlib.util.spec_from_file_location("nox_self_heal", SOURCE)
healer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(healer)

class SafeRepairTests(unittest.TestCase):
    def policy(self, stop, *, enabled=True, restart=True):
        return healer.policy_validate({
            "schema_version": 1, "enabled": enabled,
            "stop_file": str(stop), "daily_restart_limit": 2,
            "cooldown_seconds": 60,
            "services": [{"unit": "nox-dispatcher.service",
                          "restart_enabled": restart, "failures_before_restart": 2}]
        })

    def test_reject_non_nox_service_and_remote_probe(self):
        with self.assertRaises(ValueError):
            healer.policy_validate({"schema_version":1,"services":[{"unit":"ssh.service"}]})
        with self.assertRaises(ValueError):
            healer.policy_validate({"schema_version":1,"services":[{"unit":"nox-main.service",
                                  "health_url":"http://example.com/ping"}]})
    def test_6b04_ambiguous_enable_flags_never_authorize_repair(self):
        # JSON strings and integers previously became truthy when read by
        # _repair_cycle_locked; both must HOLD at policy admission.
        bad = (
            ({"enabled": "false"}, {}),
            ({"enabled": 1}, {}),
            ({}, {"restart_enabled": "false"}),
            ({}, {"restart_enabled": 1}),
            ({}, {"restart_enabled": None}),
        )
        for global_flags, service_flags in bad:
            with self.subTest(global_flags=global_flags, service_flags=service_flags):
                policy = {"schema_version": 1, "enabled": True,
                          "services": [{"unit": "nox-dispatcher.service",
                                        "restart_enabled": True}]}
                policy.update(global_flags)
                policy["services"][0].update(service_flags)
                with patch.object(healer, "alive") as probe, patch.object(
                        healer.subprocess, "run") as systemd:
                    with self.assertRaises(ValueError):
                        healer.policy_validate(policy)
                    probe.assert_not_called()
                    systemd.assert_not_called()
        self.assertTrue(healer.policy_validate({"schema_version": 1,
                        "enabled": False, "services": [{"unit": "nox-dispatcher.service",
                        "restart_enabled": False}]})["services"])

    def test_healthy_loopback_does_not_follow_redirect(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/healthy")
                else:
                    self.send_response(200)
                self.end_headers()
            def log_message(self, *args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = "http://127.0.0.1:" + str(server.server_port)
                with patch.object(healer.subprocess, "run") as run:
                    run.return_value.returncode = 0
                    self.assertTrue(healer.alive("nox-dispatcher.service", base + "/healthy"))
                    self.assertFalse(healer.alive("nox-dispatcher.service", base + "/redirect"))
            finally:
                server.shutdown()
                thread.join(timeout=4)

    def test_atomic_state_write_does_not_follow_predictable_temp_symlink(self):
        # Pre-existing state.json.tmp used to be opened with truncation and
        # could overwrite a canary file. The private tmp filename prevents it.
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state.json"
            canary = Path(root) / "unrelated"
            canary.write_text("DO_NOT_CHANGE", encoding="utf8")
            fixed = Path(root) / "state.json.tmp"
            fixed.symlink_to(canary)
            healer.write(state, {"services": {"nox-dispatcher.service": {"failures": 1}}})
            self.assertEqual(canary.read_text(encoding="utf8"), "DO_NOT_CHANGE")
            self.assertTrue(fixed.is_symlink())
            self.assertEqual(healer.load(state)["services"]["nox-dispatcher.service"]["failures"], 1)
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)

    def test_failed_atomic_state_replacement_cleans_private_temp(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state.json"
            with patch.object(healer.os, "replace", side_effect=OSError("simulated")):
                with self.assertRaises(OSError):
                    healer.write(state, {"services": {}})
            self.assertFalse(state.exists())
            self.assertEqual(list(Path(root).glob(".state.json.*.tmp")), [])

    def test_concurrent_repair_cycles_fail_closed(self):
        # Two processes using the same state must not both consume the same
        # restart budget or overwrite each other's attempt receipts.
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "repair.json"
            lock = state.with_name(state.name + ".writer.lock")
            fd = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(healer, "alive") as alive, patch.object(
                        healer.subprocess, "run") as run:
                    with self.assertRaises(BlockingIOError):
                        healer.repair_cycle(self.policy(Path(root) / "STOP"), state)
                    alive.assert_not_called()
                    run.assert_not_called()
                self.assertFalse(state.exists())
            finally:
                os.close(fd)

            # A released kernel lock allows the original observer to proceed.
            with patch.object(healer, "alive", return_value=True):
                rows = healer.repair_cycle(self.policy(Path(root) / "STOP"), state)
            self.assertEqual(rows[0]["action"], "healthy")
            self.assertEqual(healer.load(state)["services"]["nox-dispatcher.service"]["failures"], 0)

    def test_unsafe_writer_lock_holds_before_service_probe(self):
        # A FIFO or world-writable sidecar cannot serialize a trusted restart.
        # Neither case may reach health probing, systemctl or state mutation.
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "repair.json"
            lock = state.with_name(state.name + ".writer.lock")
            stop = Path(root) / "STOP"
            policy = self.policy(stop)
            lock.write_text("untrusted", encoding="utf8")
            lock.chmod(0o666)
            with patch.object(healer, "alive") as alive, patch.object(
                    healer.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "unsafe repair writer lock"):
                    healer.repair_cycle(policy, state)
                alive.assert_not_called()
                run.assert_not_called()
            self.assertFalse(state.exists())
            lock.unlink()
            os.mkfifo(lock)
            with patch.object(healer, "alive") as alive, patch.object(
                    healer.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "unsafe repair writer lock"):
                    healer.repair_cycle(policy, state)
                alive.assert_not_called()
                run.assert_not_called()
            self.assertFalse(state.exists())

    def test_dry_run_has_no_lock_or_directory_side_effects(self):
        # Read-only inspection on an absent state path must not create
        # the directory, writer lock, state, or any extra local files.
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "not-created" / "repair.json"
            lock = state.with_name(state.name + ".writer.lock")
            with patch.object(healer, "alive", return_value=True) as alive, patch.object(
                    healer.subprocess, "run") as run:
                rows = healer.repair_cycle(self.policy(Path(root) / "STOP"),
                                           state, dry_run=True)
                self.assertEqual(rows[0]["action"], "healthy")
                alive.assert_called_once()
                run.assert_not_called()
            self.assertFalse(state.parent.exists())
            self.assertFalse(state.exists())
            self.assertFalse(lock.exists())
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_writer_lock_symlink_cannot_redirect_observer(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "repair.json"
            canary = Path(root) / "unrelated"
            canary.write_text("DO_NOT_CHANGE", encoding="utf8")
            state.with_name(state.name + ".writer.lock").symlink_to(canary)
            with patch.object(healer, "alive") as alive:
                with self.assertRaises(OSError):
                    healer.repair_cycle(self.policy(Path(root) / "STOP"), state)
                alive.assert_not_called()
            self.assertEqual(canary.read_text(encoding="utf8"), "DO_NOT_CHANGE")
            self.assertFalse(state.exists())

    def test_invalid_existing_state_holds_without_overwriting_or_restart(self):
        # Malformed state must not reset recorded attempts or trigger a restart.
        bad_states = (
            "{broken json",
            '{"services":{"nox-dispatcher.service":{"failures":2,"attempts":"bad"}}}',
            '{"services":{"nox-dispatcher.service":{"failures":true,"attempts":[]}}}',
            '{"services":{"nox-dispatcher.service":{"failures":2,"attempts":[],"attempts":[1]}}}',
            '{"services":{"nox-dispatcher.service":{"failures":2,"attempts":[NaN]}}}',
            # A clock rollback previously discarded future-dated attempts,
            # resetting the 24-hour restart cap and enabling an extra restart.
            json.dumps({"services":{"nox-dispatcher.service":{
                "failures":2,"attempts":[healer.time.time()+3600]}}}),
        )
        for raw in bad_states:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as root:
                state = Path(root) / "state.json"
                state.write_text(raw, encoding="utf8")
                with patch.object(healer, "alive") as alive, patch.object(
                        healer.subprocess, "run") as run:
                    result = healer.repair_cycle(
                        self.policy(Path(root) / "STOP"), state)
                    self.assertEqual(result[0]["action"], "state_invalid_hold")
                    self.assertIsNone(result[0]["healthy_before"])
                    alive.assert_not_called()
                    run.assert_not_called()
                self.assertEqual(state.read_text(encoding="utf8"), raw)

    def test_repair_state_open_is_bounded_and_never_follows_links(self):
        # A valid JSON target reached via symlink must not authorize a repair.
        # Huge files and FIFOs also HOLD before probing or invoking systemd.
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state.json"
            target = Path(root) / "external.json"
            raw = '{"services":{"nox-dispatcher.service":{"failures":2,"attempts":[]}}}'
            target.write_text(raw, encoding="utf8")
            state.symlink_to(target)
            with patch.object(healer, "alive") as alive, patch.object(
                    healer.subprocess, "run") as run:
                result = healer.repair_cycle(self.policy(Path(root) / "STOP"), state)
                self.assertEqual(result[0]["action"], "state_invalid_hold")
                alive.assert_not_called()
                run.assert_not_called()
            self.assertEqual(target.read_text(encoding="utf8"), raw)
            state.unlink()
            state.write_bytes(b" " * (healer.MAX_REPAIR_STATE_BYTES + 1))
            with patch.object(healer, "alive") as alive, patch.object(
                    healer.subprocess, "run") as run:
                result = healer.repair_cycle(self.policy(Path(root) / "STOP"), state)
                self.assertEqual(result[0]["action"], "state_invalid_hold")
                alive.assert_not_called()
                run.assert_not_called()
            self.assertEqual(state.stat().st_size, healer.MAX_REPAIR_STATE_BYTES + 1)
            state.unlink()
            os.mkfifo(state)
            with patch.object(healer, "alive") as alive, patch.object(
                    healer.subprocess, "run") as run:
                result = healer.repair_cycle(self.policy(Path(root) / "STOP"), state)
                self.assertEqual(result[0]["action"], "state_invalid_hold")
                alive.assert_not_called()
                run.assert_not_called()

    def test_stop_blocks_restart(self):
        with tempfile.TemporaryDirectory() as t:
            stop=Path(t)/"STOP"
            stop.touch()
            state=Path(t)/"state.json"
            with patch.object(healer,"alive",return_value=False), patch.object(healer.subprocess,"run") as run:
                p=self.policy(stop)
                healer.repair_cycle(p,state)
                result=healer.repair_cycle(p,state)
                self.assertEqual(result[0]["action"],"stop_lock")
                run.assert_not_called()
    def test_dangling_stop_link_and_unreadable_marker_fail_closed(self):
        # Path.exists() returns False for a dangling STOP symlink; never
        # interpret that as owner permission to restart a failed unit.
        with tempfile.TemporaryDirectory() as t:
            stop = Path(t) / "STOP"
            stop.symlink_to(Path(t) / "absent-target")
            state = Path(t) / "repair.json"
            with patch.object(healer, "alive", return_value=False), patch.object(
                    healer.subprocess, "run") as run:
                policy = self.policy(stop)
                healer.repair_cycle(policy, state)
                result = healer.repair_cycle(policy, state)
                self.assertEqual(result[0]["action"], "stop_lock")
                run.assert_not_called()
            # An uninspectable STOP is also never considered safely absent.
            with patch.object(healer.os, "stat", side_effect=PermissionError("denied")):
                self.assertTrue(healer._stop_marker_present_or_unknown(stop))

    def test_missing_or_linked_stop_parent_blocks_restart(self):
        # An absent STOP directory used to look like an absent STOP marker.
        # An attacker-controlled symlink as the final parent must also HOLD.
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            missing_stop = root / "missing-owner-dir" / "STOP"
            real_dir = root / "other-dir"
            real_dir.mkdir()
            linked_dir = root / "linked-owner-dir"
            linked_dir.symlink_to(real_dir, target_is_directory=True)
            self.assertTrue(healer._stop_marker_present_or_unknown(missing_stop))
            self.assertTrue(healer._stop_marker_present_or_unknown(linked_dir / "STOP"))
            self.assertFalse(healer._stop_marker_present_or_unknown(real_dir / "STOP"))

            state = root / "repair.json"
            with patch.object(healer, "alive", return_value=False), patch.object(
                    healer.subprocess, "run") as systemd:
                policy = self.policy(missing_stop)
                healer.repair_cycle(policy, state)
                result = healer.repair_cycle(policy, state)
                self.assertEqual(result[0]["action"], "stop_lock")
                systemd.assert_not_called()

    def test_nested_stop_ancestor_symlink_is_hold(self):
        # The immediate STOP parent is real, but a higher ancestor can be a
        # symlink. The old single-parent stat followed it and returned clear.
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            owner = root / "owner"
            owner.mkdir()
            actual = owner / "actual"
            actual.mkdir()
            stopdir = actual / "stopdir"
            stopdir.mkdir()
            alias = owner / "alias"
            alias.symlink_to(actual, target_is_directory=True)
            linked_stop = alias / "stopdir" / "STOP"
            self.assertTrue(healer._stop_marker_present_or_unknown(linked_stop))
            self.assertFalse(healer._stop_marker_present_or_unknown(stopdir / "STOP"))
            state = root / "repair.json"
            with patch.object(healer, "alive", return_value=False), patch.object(
                    healer.subprocess, "run") as systemd:
                policy = self.policy(linked_stop)
                healer.repair_cycle(policy, state)
                result = healer.repair_cycle(policy, state)
                self.assertEqual(result[0]["action"], "stop_lock")
                systemd.assert_not_called()

    def test_disabled_default_does_not_restart(self):
        with tempfile.TemporaryDirectory() as t:
            state=Path(t)/"s.json"
            p=self.policy(Path(t)/"STOP",enabled=False)
            with patch.object(healer,"alive",return_value=False), patch.object(healer.subprocess,"run") as run:
                healer.repair_cycle(p,state)
                result=healer.repair_cycle(p,state)
                self.assertEqual(result[0]["action"],"needs_owner_approval")
                run.assert_not_called()
    def test_dry_run_does_not_write_or_restart(self):
        with tempfile.TemporaryDirectory() as t:
            state=Path(t)/"s.json"
            p=self.policy(Path(t)/"STOP")
            with patch.object(healer,"alive",return_value=False), patch.object(healer.subprocess,"run") as run:
                healer.repair_cycle(p,state)
                run.side_effect=[
                    subprocess.CompletedProcess(["systemctl","is-failed"],0,stdout="failed\n"),
                    subprocess.CompletedProcess(["systemctl","show"],0,stdout="0\n"),
                ]
                result=healer.repair_cycle(p,state,dry_run=True)
                self.assertEqual(result[0]["action"],"would_restart")
                # Dry-run requires both failed-unit and zero-MainPID readbacks.
                self.assertEqual([c.args[0][1] for c in run.call_args_list],
                                 ["is-failed","show"])
    def test_restart_verified_only_after_live_probe(self):
        with tempfile.TemporaryDirectory() as t:
            state=Path(t)/"s.json"
            p=self.policy(Path(t)/"STOP")
            with patch.object(healer,"alive",side_effect=[False,False,True]), patch.object(healer.subprocess,"run") as run, patch.object(healer.time,"sleep"):
                # A failed systemd unit is no longer active; only that state
                # may enter the legacy guarded restart branch.
                def systemd(args, **kw):
                    if args[1] == "is-failed":
                        return subprocess.CompletedProcess(args, 0, stdout="failed\n")
                    if args[1] == "show":
                        return subprocess.CompletedProcess(args, 0, stdout="0\n")
                    return subprocess.CompletedProcess(args, 0)
                run.side_effect=systemd
                healer.repair_cycle(p,state)
                result=healer.repair_cycle(p,state)
                self.assertEqual(result[0]["action"],"restart_verified")
                self.assertEqual(len(json.loads(state.read_text())["services"]["nox-dispatcher.service"]["attempts"]),1)
    def test_stop_arriving_during_attempt_write_prevents_restart(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state.json"
            stop = Path(root) / "STOP"
            policy = self.policy(stop)
            healer.write(state, {"services": {"nox-dispatcher.service": {
                "failures": 1, "attempts": []}}})
            original_write = healer.write

            def write_and_stop(path, value):
                original_write(path, value)
                stop.touch()

            with patch.object(healer, "alive", return_value=False), patch.object(
                    healer, "_unit_confirmed_inactive", return_value=True), patch.object(
                    healer, "write", side_effect=write_and_stop), patch.object(
                    healer.subprocess, "run") as run:
                result = healer.repair_cycle(policy, state)
                self.assertEqual(result[0]["action"], "stop_lock")
                run.assert_not_called()
            self.assertTrue(stop.exists())
            self.assertEqual(len(json.loads(state.read_text())["services"]
                                 ["nox-dispatcher.service"]["attempts"]), 1)

    def test_unit_recovery_during_attempt_write_prevents_restart(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state.json"
            stop = Path(root) / "STOP"
            policy = self.policy(stop)
            healer.write(state, {"services": {"nox-dispatcher.service": {
                "failures": 1, "attempts": []}}})
            with patch.object(healer, "alive", return_value=False), patch.object(
                    healer, "_unit_confirmed_inactive", side_effect=[True, False]) as inactive, patch.object(
                    healer.subprocess, "run") as run:
                result = healer.repair_cycle(policy, state)
                self.assertEqual(result[0]["action"], "needs_owner_investigation")
                self.assertEqual(inactive.call_count, 2)
                run.assert_not_called()
            self.assertEqual(len(json.loads(state.read_text())["services"]
                                 ["nox-dispatcher.service"]["attempts"]), 1)

    def test_health_probe_failure_does_not_restart_active_unit(self):
        # A transient HTTP timeout can make alive() false while systemd still
        # owns a healthy running process. Never restart it on that evidence.
        with tempfile.TemporaryDirectory() as t:
            state=Path(t)/"s.json"
            p=self.policy(Path(t)/"STOP")
            p["services"][0]["health_url"]="http://127.0.0.1:18775/health"
            with patch.object(healer,"alive",return_value=False), patch.object(
                    healer.subprocess,"run") as run:
                run.return_value.returncode=0  # systemctl is-active
                healer.repair_cycle(p,state)
                result=healer.repair_cycle(p,state)
                self.assertEqual(result[0]["action"],"needs_owner_investigation")
                run.assert_called_once_with(
                    ["systemctl","is-failed","nox-dispatcher.service"],
                    shell=False,timeout=8,check=False,capture_output=True,text=True)

    def test_unknown_systemd_state_does_not_restart(self):
        with tempfile.TemporaryDirectory() as t:
            state=Path(t)/"s.json"
            p=self.policy(Path(t)/"STOP")
            with patch.object(healer,"alive",return_value=False), patch.object(
                    healer.subprocess,"run") as run:
                run.return_value.returncode=4  # unknown unit
                healer.repair_cycle(p,state)
                result=healer.repair_cycle(p,state)
                self.assertEqual(result[0]["action"],"needs_owner_investigation")
                self.assertEqual(run.call_count,1)

    def test_systemd_failed_with_live_main_pid_does_not_restart(self):
        with tempfile.TemporaryDirectory() as t:
            state=Path(t)/"s.json"
            p=self.policy(Path(t)/"STOP")
            with patch.object(healer,"alive",return_value=False), patch.object(healer.subprocess,"run") as run:
                run.side_effect=[
                    subprocess.CompletedProcess(["systemctl","is-failed"],0,stdout="failed\n"),
                    subprocess.CompletedProcess(["systemctl","show"],0,stdout="7142\n"),
                ]
                healer.repair_cycle(p,state)
                result=healer.repair_cycle(p,state)
                self.assertEqual(result[0]["action"],"needs_owner_investigation")
                self.assertEqual([c.args[0][1] for c in run.call_args_list],
                                 ["is-failed","show"])

    def test_rate_limit(self):
        with tempfile.TemporaryDirectory() as t:
            state=Path(t)/"s.json"
            p=self.policy(Path(t)/"STOP")
            healer.write(state,{"services":{"nox-dispatcher.service":{
                "failures":1,"attempts":[healer.time.time(),healer.time.time()]}}})
            with patch.object(healer,"alive",return_value=False), patch.object(healer.subprocess,"run") as run:
                result=healer.repair_cycle(p,state)
                self.assertEqual(result[0]["action"],"needs_owner_investigation")
                run.assert_not_called()

if __name__ == "__main__":
    unittest.main()
