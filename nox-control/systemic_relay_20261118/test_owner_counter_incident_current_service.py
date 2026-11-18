"""Read-only NOX incident-observer regression; no supervisor or native calls."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name("owner_counter_policy_incident_inspect.py")
spec = importlib.util.spec_from_file_location("nox_incident_module", SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class CurrentSupervisorIdentityTests(unittest.TestCase):
    def test_current_pid_discovered_from_supervisor_not_old_pin(self):
        values = [b"S", b"0", b"114", b"242298", b"0"]
        values += [b"0"] * (19 - len(values))
        values += [b"183262723"]
        raw = b"242298 (python3) " + b" ".join(values) + b"\n"
        completed = subprocess.CompletedProcess([], 0, stdout="nox-proxy RUNNING pid 242298, uptime 00:20:00\n", stderr="")
        with patch.object(m.subprocess, "run", return_value=completed), patch.object(
            Path, "read_bytes", return_value=raw
        ):
            result = m.current_service_identity("nox-proxy")
        self.assertEqual(result["state"], "RUNNING")
        self.assertEqual(result["pid"], 242298)
        self.assertEqual(result["pgrp"], 242298)
        self.assertEqual(result["start_ticks"], 183262723)

    def test_missing_pid_fails_closed(self):
        completed = subprocess.CompletedProcess([], 0, stdout="nox-proxy STOPPED Not started\n", stderr="")
        with patch.object(m.subprocess, "run", return_value=completed):
            self.assertEqual(m.current_service_identity("nox-proxy"), {"state": "NOT_RUNNING"})

    def test_startup_order_is_evidence_not_behavioral_acceptance(self):
        base = {"current_services":{"nox-proxy":{"state":"RUNNING","pid":21,"start_ticks":3000}},
                "files": {name:{"version":"candidate","mtime_ns":125_000_000_000}
                          for name in ("slim_chat_t885u.py","common.py","chat_proxy.py")}}
        # btime 100, tick frequency 100 => proxy starts at 130 seconds.
        with patch.object(Path, "read_bytes", return_value=b"cpu 1 2 3\nbtime 100\n"), patch.object(m.os, "sysconf", return_value=100):
            result = m.startup_order_evidence(base)
        self.assertEqual(result["state"], "SOURCE_BEFORE_PROXY_START")
        self.assertTrue(result["source_before_proxy"])
        base["files"]["chat_proxy.py"]["mtime_ns"] = 129_000_000_000
        with patch.object(Path, "read_bytes", return_value=b"btime 100\n"), patch.object(m.os, "sysconf", return_value=100):
            result = m.startup_order_evidence(base)
        self.assertEqual(result["state"], "TIMELINE_UNRESOLVED")
        self.assertFalse(result["source_before_proxy"])


if __name__ == "__main__":
    unittest.main()
