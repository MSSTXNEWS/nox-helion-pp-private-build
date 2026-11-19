"""Reciprocal NOX supervision tests use synthetic /proc and fake supervisor."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("reciprocal", Path(__file__).with_name("owner_dispatcher_reciprocal_health.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def proc_fixture(root, pid, script, start="123456"):
    p = Path(root) / str(pid)
    p.mkdir(parents=True, exist_ok=True)
    fields = ["S"] + ["0"] * 19
    fields[19] = start
    (p / "stat").write_text(f"{pid} (python) " + " ".join(fields))
    (p / "cmdline").write_bytes(b"python3\0" + script.encode() + b"\0")

class ReciprocalTests(unittest.TestCase):
    def test_verified_pid_start_ticks(self):
        with tempfile.TemporaryDirectory() as root:
            proc_fixture(root, 123, module.SERVICES["nox-dispatcher-t855u"])
            def call(argv, **kwargs):
                return SimpleNamespace(returncode=0, stdout=f"{argv[-1]} RUNNING pid 123, uptime 0:10:00")
            health = module.inspect(("nox-dispatcher-t855u",), call=call, proc=Path(root))
            self.assertTrue(health["verified"])
            self.assertEqual(health["services"][0]["start_ticks"], 123456)
    def test_reject_wrong_script_or_missing_proc(self):
        with tempfile.TemporaryDirectory() as root:
            proc_fixture(root, 123, "/tmp/wrong.py")
            def call(argv, **kwargs):
                return SimpleNamespace(returncode=0, stdout=f"{argv[-1]} RUNNING pid 123, uptime 0:00")
            health = module.inspect(("nox-dispatcher-t855u",), call=call, proc=Path(root))
            self.assertFalse(health["verified"])
            self.assertEqual(health["services"][0]["state"], "HOLD_PID_OR_SCRIPT")
    def test_reject_supervisor_mismatch_and_bad_status(self):
        for raw in ("nox-selfheal RUNNING pid 123, uptime 0:01",
                    "nox-dispatcher-t855u RUNNING no-pid",
                    "nox-dispatcher-t855u RUNNING pid 123\nnox-selfheal RUNNING pid 123"):
            def call(argv, **kwargs):
                return SimpleNamespace(returncode=0, stdout=raw)
            out = module.inspect(("nox-dispatcher-t855u",), call=call)
            self.assertFalse(out["verified"])
    def test_native_rc3_stopped_is_reported_as_unhealthy_not_unknown(self):
        def call(argv, **kwargs):
            return SimpleNamespace(returncode=3,
                stdout=f"{argv[-1]} STOPPED Not started")
        result = module.inspect(("nox-dispatcher-t855u",), call=call)
        self.assertFalse(result["verified"])
        self.assertEqual(result["services"][0]["state"], "STOPPED")
        self.assertFalse(result["services"][0]["identity_verified"])
        for bad in ("RUNNING pid 123", "STOPPED pid 123", "FATAL"):
            with self.subTest(bad=bad):
                def invalid(argv, **kwargs):
                    return SimpleNamespace(returncode=3, stdout=f"{argv[-1]} {bad}")
                result = module.inspect(("nox-dispatcher-t855u",), call=invalid)
                self.assertEqual(result["services"][0]["state"], "UNKNOWN")

    def test_reject_unreviewed_services(self):
        with self.assertRaises(ValueError):
            module.inspect(("sshd",))
        with self.assertRaises(ValueError):
            module.inspect(("nox-selfheal", "nox-selfheal"))
    def test_stop_or_crash_not_claimed_healthy(self):
        def call(argv, **kwargs):
            return SimpleNamespace(returncode=3, stdout=f"{argv[-1]} STOPPED Not started")
        out = module.inspect(("nox-selfheal",), call=call)
        self.assertFalse(out["verified"])

if __name__ == "__main__":
    unittest.main()
