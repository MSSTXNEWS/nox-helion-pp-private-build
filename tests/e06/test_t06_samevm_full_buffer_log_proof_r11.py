"""Fail-closed regression on ORIGINAL T06 SameVM WPF log proof, NOT E07."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_samevm_installed_smoke.py"
spec = importlib.util.spec_from_file_location("nox_t06_original_samevm", MODULE)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)

class FakeProcess:
    pid = 25813
    def __init__(self, already_exited=False):
        self.exited = already_exited
    def poll(self):
        return 10 if self.exited else None
    def terminate(self):
        self.exited = True
    def wait(self, timeout=None):
        return 0

class OriginalLiveWpfLogTests(unittest.TestCase):
    def probe(self, raw, *, already_exited=False):
        with tempfile.TemporaryDirectory() as temp:
            local = Path(temp)
            log = local / "NOX_HELION/P01/logs/shell.log"
            def create_wpf(*args, **kwargs):
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_bytes(raw)
                return FakeProcess(already_exited)
            with patch.object(smoke.subprocess, "Popen", side_effect=create_wpf), \
                 patch.object(smoke.time, "sleep", return_value=None):
                return smoke.live_original_wpf_probe(local / "NOX.P01.Shell.exe", local)

    def test_late_init_error_in_existing_buffer_must_not_pass(self):
        raw = b"NAV_OK\nP02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK\n" + b"x"*70000 + b"\nINIT_ERROR\n"
        evidence = self.probe(raw)
        self.assertTrue(evidence["init_error"])
        self.assertFalse(evidence["new_nav_ok"])
        self.assertFalse(evidence["new_python_ipc_handshake"])

    def test_late_native_hold_in_existing_buffer_must_not_pass(self):
        raw = b"NAV_OK\nP02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK\n" + b"y"*70000 + b"\nP02_ORIGINAL_NATIVE_HOLD\n"
        evidence = self.probe(raw)
        self.assertTrue(evidence["native_hold"])
        self.assertFalse(evidence["new_nav_ok"])

    def test_large_clean_buffer_drains_and_passes(self):
        raw = b"NAV_OK\nP02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK\n" + b"z"*140000
        evidence = self.probe(raw)
        self.assertTrue(evidence["new_nav_ok"])
        self.assertTrue(evidence["new_python_ipc_handshake"])
        self.assertEqual(evidence["new_log_bytes_scanned"], len(raw))
        self.assertTrue(evidence["live_process_at_receipt"])

    def test_exited_process_never_attests_gui(self):
        evidence = self.probe(b"NAV_OK\nP02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK", already_exited=True)
        self.assertFalse(evidence["new_nav_ok"])
        self.assertFalse(evidence["live_process_at_receipt"])

if __name__ == "__main__":
    unittest.main()
