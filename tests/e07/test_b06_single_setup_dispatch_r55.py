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


if __name__ == "__main__":
    unittest.main()
