"""B06 SOURCE_ONLY: protect independent E07 from repeated SetupSHA launches.

This tests the exact Git workflow source, not a Windows installer.
"""
from pathlib import Path
import unittest

WORKFLOW = Path(__file__).resolve().parents[2] / (
    ".github/workflows/nox-express-independent-e07-current-d02.yml")


class B06SingleSetupDispatch(unittest.TestCase):
    def test_exact_inputs_dispatch_only_no_historical_fallback(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("on:\n  workflow_dispatch:\n", source)
        self.assertNotIn("\n  push:\n", source)
        for name in ("producer_run_id", "artifact_name", "source_sha",
                     "setup_sha256", "setup_bytes", "build_id", "owned_count"):
            self.assertIn("${{ inputs." + name + " }}", source)
            self.assertNotIn("inputs." + name + " ||", source)
        self.assertNotIn("41966861333", source)
        self.assertNotIn("8a552091502d8401ced76dc0063acb24f851bc3d99fbc40efe130f4535b4980d", source)

    def test_prior_attempt_holds_before_download_and_model(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("run-name: B06 E07 ${{ inputs.setup_sha256 }}", source)
        self.assertIn("group: nox-express-e07-immutable-${{ inputs.setup_sha256 }}", source)
        self.assertIn("cancel-in-progress: false", source)
        for token in ("E07_EXPLICIT_IMMUTABLE_DISPATCH_HOLD",
                      "E07_DUPLICATE_RUN_LOOKUP_HOLD",
                      "E07_SAME_SETUP_PREVIOUS_RUN_HOLD",
                      "E07_DUPLICATE_HISTORY_INCOMPLETE_HOLD",
                      "$_.id -ne $current", "$_.display_title -ceq $expectedTitle"):
            self.assertIn(token, source)
        pos = source.index("B06 exclusive immutable SetupSHA")
        self.assertLess(pos, source.index("Download immutable candidate"))
        self.assertLess(pos, source.index("Start verified local Ollama"))



    def test_dispatch_yaml_has_one_complete_gate_and_one_real_e07(self):
        """Guard against nested duplicated workflow fragments inside pwsh."""
        source = WORKFLOW.read_text(encoding="utf-8")
        unique_steps = (
            "B06 exclusive immutable SetupSHA and previous-run admission",
            "Fast source regression gate before heavy artifacts",
            "Download immutable candidate from DIFFERENT Windows CI run",
            "Download prior SHA-pinned Authenticode-verified official Ollama x64 bytes",
            "Start verified local Ollama and fetch exact approved Qwen for same-VM E07",
            "Independent installed E07 candidate lifecycle, final receipts required",
            "Preserve NOT-RELEASE when actual model or visual E07 incomplete",
        )
        for title in unique_steps:
            self.assertEqual(source.count("      - name: " + title + "\n"), 1, title)
        self.assertEqual(source.count("      - name: B06 exclusive immutable"), 1)
        gate = source.split(
            "      - name: B06 exclusive immutable SetupSHA and previous-run admission\n", 1
        )[1].split("      - name: Fast source regression gate before heavy artifacts\n", 1)[0]
        self.assertIn("$env:E07_SETUP_SHA -cnotmatch '^[0-9a-f]{64}$'", gate)
        self.assertIn("$env:E07_SOURCE_SHA -cnotmatch '^[0-9a-f]{40}$'", gate)
        self.assertIn("$env:E07_PRODUCER_RUN_ID -cnotmatch '^[1-9][0-9]{0,17}$'", gate)
        self.assertIn("E07_SAME_SETUP_PREVIOUS_RUN_HOLD", gate)
        self.assertIn("E07_DUPLICATE_HISTORY_INCOMPLETE_HOLD", gate)
        self.assertNotIn("\n        shell: pwsh\n", gate)
        self.assertNotIn("\n      - name: Download immutable candidate", gate)
        self.assertEqual(source.count("E07_EXPLICIT_IMMUTABLE_DISPATCH_HOLD"), 1)


if __name__ == "__main__":
    unittest.main()
