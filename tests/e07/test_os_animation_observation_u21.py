"""Regression: OS animation diagnostic is not a WebView2 Reduced Motion PASS."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "coordination/e07/probe_final_same_setup.py"
sys.path.insert(0, str(TARGET.parent))
spec = importlib.util.spec_from_file_location("nox_e07_os_animation", TARGET)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WindowsAnimationsObservation(unittest.TestCase):
    def test_query_returns_read_only_os_evidence(self):
        observed = {"os_ui_animations_enabled": False,
                    "source": "WinRT.UISettings.AnimationsEnabled",
                    "webview2_media_query": "NOT_TESTED"}
        with patch.object(module, "_run_ps", return_value=observed) as runner:
            result = module.probe_windows_animation_setting()
        self.assertEqual(result, observed)
        script = runner.call_args.args[0]
        self.assertIn("AnimationsEnabled", script)
        self.assertNotIn("Set-ItemProperty", script)
        self.assertNotIn("SystemParametersInfo", script)
        self.assertEqual(runner.call_args.kwargs["phase"], "VISUAL")

    def test_query_failure_never_claims_pass(self):
        with patch.object(module, "_run_ps", side_effect=module.e07.Hold("E07_FINAL_UIA_VISUAL_PROCESS_HOLD")):
            result = module.probe_windows_animation_setting()
        self.assertIsNone(result["os_ui_animations_enabled"])
        self.assertEqual(result["webview2_media_query"], "NOT_TESTED")
        self.assertNotIn("PASS", str(result))

    def test_invalid_result_is_not_converted_to_success(self):
        with patch.object(module, "_run_ps", return_value={"os_ui_animations_enabled": "false"}):
            result = module.probe_windows_animation_setting()
        self.assertIsNone(result["os_ui_animations_enabled"])
        self.assertEqual(result["source"], "WINRT_INVALID_VALUE")

    def test_final_release_gate_still_requires_real_reduced_motion(self):
        source = (ROOT / "coordination/e07/independent_setup_e07.py").read_text(encoding="utf-8")
        self.assertIn('visual.get("reduced_motion") == "PASS"', source)
        probe = TARGET.read_text(encoding="utf-8")
        self.assertIn('"reduced_motion":"HOLD"', probe)
        self.assertIn('"os_animation_observation":os_animation', probe)


if __name__ == "__main__":
    unittest.main()
