"""Focused T06 same-VM WPF live-process/log witness regression, NOT native E07."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "coordination/e06/t06_samevm_installed_smoke.py"
spec = importlib.util.spec_from_file_location("nox_t06_wpf_live_log_r30", SOURCE)
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)

class FakeProcess:
    def __init__(self, dead=False):
        self.pid = 8123
        self.dead = dead
    def poll(self):
        return 1 if self.dead else None
    def terminate(self):
        self.dead = True
    def wait(self, timeout=None):
        return 0

class LiveWpfLogBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.local = Path(self.tmp.name)
        self.log = self.local / "NOX_HELION/P01/logs/shell.log"
        self.log.parent.mkdir(parents=True)
        self.exe = self.local / "NOX.P01.Shell.exe"
        self.exe.write_bytes(b"MZ")

    def probe(self, payload=b"", dead=False):
        def fake_start(*args, **kwargs):
            with self.log.open("ab") as stream:
                stream.write(payload)
            return FakeProcess(dead=dead)
        with patch.object(owner.subprocess, "Popen", side_effect=fake_start), \
             patch.object(owner.time, "sleep"):
            return owner.live_original_wpf_probe(self.exe, self.local)

    def test_live_wpf_beyond_prior_262144_byte_limit(self):
        payload = b"x" * 350000 + b"NAV_OK\nP02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK\n"
        result = self.probe(payload=payload)
        self.assertTrue(result["new_nav_ok"])
        self.assertTrue(result["new_python_ipc_handshake"])
        self.assertTrue(result["live_process_at_receipt"])
        self.assertGreater(result["new_log_bytes_scanned"], 262144)

    def test_retired_wpf_with_positive_text_cannot_pass(self):
        result = self.probe(b"NAV_OK\nP02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK\n", dead=True)
        self.assertFalse(result["new_nav_ok"])
        self.assertFalse(result["new_python_ipc_handshake"])

    def test_stale_prior_wpf_log_cannot_pass(self):
        self.log.write_bytes(b"NAV_OK\nP02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK\n")
        result = self.probe(dead=True)
        self.assertFalse(result["new_nav_ok"])
        self.assertEqual(result["new_log_bytes_scanned"], 0)

    def test_replaced_log_truncation_cannot_pass(self):
        self.log.write_bytes(b"old" * 10000)
        def fake_start(*args, **kwargs):
            self.log.write_bytes(b"NAV_OK\nP02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK\n")
            return FakeProcess()
        with patch.object(owner.subprocess, "Popen", side_effect=fake_start), \
             patch.object(owner.time, "sleep"):
            result = owner.live_original_wpf_probe(self.exe, self.local)
        self.assertTrue(result["log_replaced"])
        self.assertFalse(result["new_nav_ok"])

    def test_native_hold_blocks_positive_strings(self):
        payload = b"NAV_OK\nP02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK\nP02_ORIGINAL_NATIVE_HOLD\n"
        result = self.probe(payload)
        self.assertTrue(result["native_hold"])
        self.assertFalse(result["new_nav_ok"])

if __name__ == "__main__":
    unittest.main()
