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



    def test_rerun_reuses_run_id_and_must_hard_hold(self):
        """Re-running a GitHub job preserves RUN_ID; attempts > 1 must HOLD."""
        source = WORKFLOW.read_text(encoding="utf-8")
        preflight = source.split(
            "      - name: B06 exclusive immutable SetupSHA and previous-run admission\n", 1
        )[1].split("      - name: Fast source regression gate before heavy artifacts\n", 1)[0]
        self.assertIn("$env:GITHUB_RUN_ATTEMPT -cne '1'", preflight)
        self.assertIn("throw 'E07_SAME_RUN_RERUN_HOLD'", preflight)
        self.assertLess(preflight.index("E07_SAME_RUN_RERUN_HOLD"),
                        preflight.index("E07_DUPLICATE_RUN_LOOKUP_HOLD"))
        self.assertLess(preflight.index("E07_SAME_RUN_RERUN_HOLD"),
                        preflight.index("E07_EXPLICIT_SINGLE_SETUP_DISPATCH_ADMITTED_NOT_PHYSICAL_PASS"))

    def test_each_b06_preflight_suite_has_immediate_native_exit_guard(self):
        """A later successful unittest must never erase an earlier failure."""
        source = WORKFLOW.read_text(encoding="utf-8")
        gates = (
            ("test_b06_current_head_r5.py", "E07_VERIFIER_CURRENT_HEAD_REGRESSION_HOLD"),
            ("test_b06_single_setup_dispatch_r55.py", "E07_SINGLE_SETUP_DISPATCH_REGRESSION_HOLD"),
            ("test_b06_receipt_descriptor_r5.py", "E07_E06_RECEIPT_DESCRIPTOR_REGRESSION_HOLD"),
            ("test_b06_manifest_identity_r6.py", "E07_MANIFEST_IDENTITY_REGRESSION_HOLD"),
        )
        for suite, expected_hold in gates:
            with self.subTest(suite=suite):
                command = "python -B -m unittest discover -s tests/e07 -p " + suite + " -v"
                immediate_guard = (
                    "          " + command + "\n"
                    "          if ($LASTEXITCODE -ne 0) { throw '" + expected_hold + "' }"
                )
                self.assertIn(immediate_guard, source)
        first = source.index("Fast source regression gate before heavy artifacts")
        self.assertLess(first, source.index("Download immutable candidate from DIFFERENT Windows CI run"))

    def test_provider_offline_never_runs_installed_e07(self):
        """A failed verified model provider cannot consume an installed E07 run."""
        source = WORKFLOW.read_text(encoding="utf-8")
        provider = source.index("      - name: Start verified local Ollama")
        witness = source.index("      - name: B06 record verified provider prerequisite failure")
        physical = source.index("      - name: Independent installed E07 candidate lifecycle")
        upload = source.index("      - name: Save independent evidence even on HOLD")
        self.assertLess(provider, witness)
        self.assertLess(witness, physical)
        self.assertLess(physical, upload)
        self.assertIn("        if: steps.provider.outcome != 'success'\\n", source[witness:physical])
        self.assertIn("        if: steps.provider.outcome == 'success'\\n", source[physical:upload])
        self.assertIn("physical_e07='NOT_RUN'", source[witness:physical])
        self.assertIn("release_accepted=$false", source[witness:physical])
        self.assertIn("status='PROVIDER_OFFLINE_HOLD'", source[witness:physical])
        self.assertIn("E07_CANDIDATE_RECEIPT.json", source[witness:physical])
        self.assertIn("if: always()", source[upload:])
        self.assertIn("steps.provider.outcome", source[upload:])

    def test_b06_immutable_download_action_pin(self):
        """The sole E07 cannot use an auto-moving artifact downloader tag."""
        source = WORKFLOW.read_text(encoding="utf-8")
        action = "uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
        self.assertEqual(source.count(action), 2)
        self.assertNotIn("uses: actions/download-artifact@v4", source)
        self.assertIn("Download immutable candidate from DIFFERENT Windows CI run", source)
        self.assertIn("Download prior SHA-pinned Authenticode-verified official Ollama x64 bytes", source)
        self.assertLess(source.index("E07_EXPLICIT_SINGLE_SETUP_DISPATCH_ADMITTED_NOT_PHYSICAL_PASS"),
                        source.index("Download immutable candidate from DIFFERENT Windows CI run"))
        self.assertIn("E07_SAME_SETUP_PREVIOUS_RUN_HOLD", source)

if __name__ == "__main__":
    unittest.main()
