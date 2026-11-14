"""Exit guard: a working provider does not excuse missing fresh-process SQLite history."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "coordination/e07/probe_installed_qwen.py"
SPEC = importlib.util.spec_from_file_location("nox_qwen_installed_probe_u12", SOURCE)
assert SPEC and SPEC.loader
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class QwenHistoryExitGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.ok = {"installed_native": "LIVE_NONEMPTY_RESPONSE_VERIFIED",
                   "native_history_restart": "PASS",
                   "first_unmet_gate": "NATIVE_ACTIVE_STOP_AND_FIVE_GUI_CLICKS_E07",
                   "independent_e07": "HOLD", "release_accepted": False}

    def test_nonempty_history_after_relaunch_only_passes_probe_not_e07(self):
        self.assertEqual(PROBE.qwen_probe_exit_code(self.ok), 0)
        self.assertFalse(self.ok["release_accepted"])

    def test_live_provider_without_history_never_passes(self):
        report = {**self.ok, "native_history_restart": "NOT_TESTED",
                  "first_unmet_gate": "NOX_INSTALLED_SQLITE_HISTORY_NOT_RELOADED_HOLD"}
        self.assertEqual(PROBE.qwen_probe_exit_code(report), 2)

    def test_empty_or_wrong_history_never_passes(self):
        for bad in ("HOLD", "", None, "EMPTY_ONLY_PASS"):
            with self.subTest(bad=bad):
                self.assertEqual(PROBE.qwen_probe_exit_code(
                    {**self.ok, "native_history_restart": bad}), 2)

    def test_native_chat_offline_never_passes(self):
        self.assertEqual(PROBE.qwen_probe_exit_code(
            {**self.ok, "installed_native": "PROVIDER_OFFLINE_HOLD"}), 2)

    def test_late_exception_must_not_pass_even_with_nonempty_history(self):
        self.assertEqual(PROBE.qwen_probe_exit_code(
            {**self.ok, "first_unmet_gate": "NOX_QWEN_PROBE_BROKEN_RECEIPT_HOLD"}), 2)


if __name__ == "__main__":
    unittest.main()
