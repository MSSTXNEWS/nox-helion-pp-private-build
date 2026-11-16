"""Prove NOX cannot report dispatcher success without native Supervisor evidence."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

path = Path(__file__).with_name("nox_agent.py")
spec = importlib.util.spec_from_file_location("nox_control_agent", path)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)

class StatusTests(unittest.TestCase):
    def test_running_requires_pid_and_native_output(self):
        def runner(args,**kw):
            self.assertEqual(args[:2],["supervisorctl","status"])
            self.assertIs(kw["shell"],False)
            return SimpleNamespace(stdout=args[2]+" RUNNING pid 4321, uptime 0:01:40\n",returncode=0)
        with patch.object(agent.platform,"system",return_value="Linux"), patch.object(agent.subprocess,"run",side_effect=runner):
            result=agent.run_action("nox_status")
        self.assertTrue(result["ok"])
        self.assertTrue(result["lifeline_healthy"])
        self.assertEqual(result["services"]["nox-dispatcher-t855u"]["pid"],4321)

    def test_down_dispatcher_not_reported_online(self):
        def runner(args,**kw):
            state = "STOPPED" if args[-1] == "nox-dispatcher-t855u" else "RUNNING pid 4321, uptime 0:01"
            return SimpleNamespace(stdout=args[-1]+" "+state+"\n",returncode=0)
        with patch.object(agent.platform,"system",return_value="Linux"), patch.object(agent.subprocess,"run",side_effect=runner):
            result=agent.run_action("nox_status")
        self.assertFalse(result["ok"])
        self.assertEqual(result["services"]["nox-dispatcher-t855u"]["state"],"STOPPED")

    def test_missing_report_does_not_become_online(self):
        with patch.object(agent.platform,"system",return_value="Linux"), patch.object(agent.subprocess,"run",side_effect=OSError("unavailable")):
            result=agent.run_action("nox_status")
        self.assertFalse(result["ok"])
        self.assertFalse(result["lifeline_healthy"])
        self.assertEqual(result["services"]["nox-priority-scheduler"]["state"],"UNKNOWN")

    def test_windows_never_claims_linux_supervisor(self):
        with patch.object(agent.platform,"system",return_value="Windows"), patch.object(agent.subprocess,"run") as runner:
            result=agent.run_action("nox_status")
        self.assertFalse(result["ok"])
        runner.assert_not_called()

if __name__=="__main__":
    unittest.main()
