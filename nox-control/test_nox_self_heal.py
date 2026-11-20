"""NOX self-heal safe behavior regression checks."""
import importlib.util
import json
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
                run.return_value.returncode=3
                result=healer.repair_cycle(p,state,dry_run=True)
                self.assertEqual(result[0]["action"],"would_restart")
                run.assert_not_called()
    def test_restart_verified_only_after_live_probe(self):
        with tempfile.TemporaryDirectory() as t:
            state=Path(t)/"s.json"
            p=self.policy(Path(t)/"STOP")
            with patch.object(healer,"alive",side_effect=[False,False,True]), patch.object(healer.subprocess,"run") as run, patch.object(healer.time,"sleep"):
                # A failed systemd unit is no longer active; only that state
                # may enter the legacy guarded restart branch.
                run.side_effect=lambda args,**kw: subprocess.CompletedProcess(
                    args, 3 if args[1]=="is-active" else 0)
                healer.repair_cycle(p,state)
                result=healer.repair_cycle(p,state)
                self.assertEqual(result[0]["action"],"restart_verified")
                self.assertEqual(len(json.loads(state.read_text())["services"]["nox-dispatcher.service"]["attempts"]),1)
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
                    ["systemctl","is-active","--quiet","nox-dispatcher.service"],
                    shell=False,timeout=8,check=False)

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
