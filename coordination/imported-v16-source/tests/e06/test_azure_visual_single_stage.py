"""Ensure canonical Azure Windows CI never stages D02/Creative/WOW twice.

Source-only contract; the independent Windows installer and E07 acceptance remain required.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "azure-pipelines-nox-v16.yml"
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"

def conflicting_visual_prestages(source: str) -> list[str]:
    return re.findall(
        r"(?m)^\s*(?:&\s*)?python(?:\.exe)?\s+"
        r"integrations/(?:creative/stage_creative|wow200/stage_wow200)\.py\b.*$",
        source,
    )

class VisualSingleStageContract(unittest.TestCase):
    def test_azure_pipeline_does_not_pre_stage_visual_content(self):
        self.assertEqual(conflicting_visual_prestages(PIPELINE.read_text(encoding="utf-8")), [])

    def test_existing_onehost_builder_retains_exact_source_owned_stage(self):
        pipeline = PIPELINE.read_text(encoding="utf-8")
        builder = BUILDER.read_text(encoding="utf-8")
        direct = pipeline.count("& ./coordination/e06/build_onehost_installer.ps1")
        disposable = pipeline.count("& $builderCopy -SourceRoot")
        self.assertEqual(direct + disposable, 1, "exactly one effective ONEHOST invocation")
        if disposable:
            self.assertIn("Copy-Item -LiteralPath 'coordination/e06/build_onehost_installer.ps1'", pipeline)
            self.assertIn("CREATIVE_PAYLOAD_MISSING_HOLD", pipeline)
            self.assertIn("build_onehost_creative_disposable.ps1", pipeline)
        self.assertIn("-CreativeSourceRoot 'integrations/creative'", pipeline)
        self.assertIn("-WowSourceRoot 'integrations/wow200'", pipeline)
        self.assertEqual(builder.count("& $py.Source $creativeScript $source $creative"), 1)
        self.assertEqual(builder.count("& $py.Source $wowScript $source $wow"), 1)
        self.assertIn("D02_PINNED_STAGE_SCRIPT_SHA_HOLD", builder)
        self.assertIn("D02_CREATIVE_STAGE_ALREADY_PRESENT", builder)
        self.assertIn("D02_WOW_STAGE_RECEIPT_REJECTED", builder)

    def test_double_stage_negative_fixture_fails(self):
        bad = "      python integrations/creative/stage_creative.py work/e06/staged/R11 integrations/creative"
        self.assertEqual(len(conflicting_visual_prestages(bad)), 1)

if __name__ == "__main__":
    unittest.main()
