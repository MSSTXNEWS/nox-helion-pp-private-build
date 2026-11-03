"""Independent E07 source-only guard for NOX V16 Azure visual staging.

No installation, product mutation or release acceptance. Run:
  python -m unittest qa.e07.test_visual_stage_provenance -v
or:
  python qa/e07/test_visual_stage_provenance.py
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

REPO = Path(__file__).resolve().parents[2]
PIPELINE = REPO / "azure-pipelines-nox-v16.yml"
BUILDER = REPO / "coordination/e06/build_onehost_installer.ps1"

_PRESTAGE = re.compile(
    r"(?im)^\s*(?:&\s*)?(?:python(?:\.exe)?|\$[\w.]+)\s+"
    r"integrations/(?:creative/stage_creative|wow200/stage_wow200)\.py\b"
)
_CALL = re.compile(
    r"(?im)^\s*&\s*(?:\./coordination/e06/build_onehost_installer\.ps1|"
    r"\$builderCopy)\s+-SourceRoot\b"
)

def verify_once(pipeline: str, owner_builder: str) -> None:
    """Fail closed unless there is exactly one trusted visual staging owner."""
    if _PRESTAGE.search(pipeline):
        raise AssertionError("DUPLICATE_VISUAL_PRESTAGE")
    calls = _CALL.findall(pipeline)
    if len(calls) != 1:
        raise AssertionError("ONEHOST_CALL_COUNT_INVALID")
    if pipeline.count("-CreativeSourceRoot 'integrations/creative'") != 1:
        raise AssertionError("CREATIVE_SOURCE_BINDING_COUNT")
    if pipeline.count("-WowSourceRoot 'integrations/wow200'") != 1:
        raise AssertionError("WOW_SOURCE_BINDING_COUNT")

    for expression in (
        "& $py.Source $creativeScript $source $creative",
        "& $py.Source $wowScript $source $wow",
        "D02_PINNED_STAGE_SCRIPT_SHA_HOLD",
        "D02_CREATIVE_STAGE_ALREADY_PRESENT",
        "D02_WOW_STAGE_RECEIPT_REJECTED",
    ):
        if owner_builder.count(expression) != 1:
            raise AssertionError("OWNER_STAGE_LOCK_MISSING_OR_DUPLICATED:" + expression)
    if owner_builder.index("D02_CREATIVE_STAGE_ALREADY_PRESENT") > owner_builder.index(
        "& $py.Source $creativeScript $source $creative"
    ):
        raise AssertionError("CREATIVE_EXISTING_GUARD_TOO_LATE")

    use_copy = bool(re.search(r"(?m)^\s*&\s*\$builderCopy\s+-SourceRoot\b", pipeline))
    if use_copy:
        required = (
            "Copy-Item -LiteralPath 'coordination/e06/build_onehost_installer.ps1'",
            "build_onehost_creative_disposable.ps1",
            "(Join-Path $creativeRoot 'patch_installer.py') $builderCopy $workerDist",
            "AZURE_CREATIVE_BUILDER_COPY_NOT_PATCHED_HOLD",
            "CREATIVE_PAYLOAD_MISSING_HOLD",
            "NOX_CreativeWorker.exe",
        )
        for expression in required:
            if pipeline.count(expression) < 1:
                raise AssertionError("DISPOSABLE_OWNER_PROVENANCE_MISSING:" + expression)
        if pipeline.count("& $builderCopy -SourceRoot") != 1:
            raise AssertionError("DISPOSABLE_BUILDER_DUPLICATED")

    if "test_azure_visual_single_stage.py" not in pipeline:
        raise AssertionError("OWNER_REGRESSION_NOT_CALLED")
    if pipeline.index("test_azure_visual_single_stage.py") > _CALL.search(pipeline).start():
        raise AssertionError("OWNER_REGRESSION_TOO_LATE")
    if "SOURCE_ARCHIVE" not in pipeline and "verify_original_729_source.py" not in pipeline:
        raise AssertionError("SOURCE_ARCHIVE_GATE_ABSENT")

OWNER = """
if (Test-Path $source) { throw 'D02_CREATIVE_STAGE_ALREADY_PRESENT' }
if ($hash -cne $pin) { throw 'D02_PINNED_STAGE_SCRIPT_SHA_HOLD' }
& $py.Source $creativeScript $source $creative
& $py.Source $wowScript $source $wow
if (!$receipt) { throw 'D02_WOW_STAGE_RECEIPT_REJECTED' }
"""
BASE = """
python coordination/e06/verify_original_729_source.py
python -m unittest discover -s tests/e06 -p 'test_azure_visual_single_stage.py'
$builderCopy=Join-Path $workerRoot 'build_onehost_creative_disposable.ps1'
Copy-Item -LiteralPath 'coordination/e06/build_onehost_installer.ps1' -Destination $builderCopy
& $workerPython (Join-Path $creativeRoot 'patch_installer.py') $builderCopy $workerDist
if ($patchedBuilder -notmatch 'CREATIVE_PAYLOAD_MISSING_HOLD' -or
    $patchedBuilder -notmatch 'NOX_CreativeWorker.exe') {
    throw 'AZURE_CREATIVE_BUILDER_COPY_NOT_PATCHED_HOLD'
}
& $builderCopy -SourceRoot 'work/e06/staged/R11' -CreativeSourceRoot 'integrations/creative' -WowSourceRoot 'integrations/wow200'
"""

class VisualStageProvenanceTest(unittest.TestCase):
    def test_valid_disposable_copy(self):
        verify_once(BASE, OWNER)

    def test_valid_direct_owner_builder(self):
        x = BASE.replace("& $builderCopy -SourceRoot", "& ./coordination/e06/build_onehost_installer.ps1 -SourceRoot")
        verify_once(x, OWNER)

    def test_creative_prestage_rejected(self):
        with self.assertRaisesRegex(AssertionError, "DUPLICATE_VISUAL"):
            verify_once(BASE + "\npython integrations/creative/stage_creative.py some/place\n", OWNER)

    def test_wow_prestage_rejected(self):
        with self.assertRaisesRegex(AssertionError, "DUPLICATE_VISUAL"):
            verify_once(BASE + "\n& python.exe integrations/wow200/stage_wow200.py some/place\n", OWNER)

    def test_two_onehost_calls_rejected(self):
        with self.assertRaisesRegex(AssertionError, "ONEHOST_CALL_COUNT"):
            verify_once(BASE + "\n& $builderCopy -SourceRoot extra\n", OWNER)

    def test_missing_builder_rejected(self):
        with self.assertRaisesRegex(AssertionError, "ONEHOST_CALL_COUNT"):
            verify_once(BASE.replace("& $builderCopy -SourceRoot", "# no builder -SourceRoot"), OWNER)

    def test_missing_owner_copy_rejected(self):
        with self.assertRaisesRegex(AssertionError, "PROVENANCE"):
            verify_once(BASE.replace("Copy-Item -LiteralPath 'coordination/e06/build_onehost_installer.ps1'", "Copy-Item -LiteralPath 'another.ps1'"), OWNER)

    def test_missing_patch_rejected(self):
        with self.assertRaisesRegex(AssertionError, "PROVENANCE"):
            verify_once(BASE.replace("patch_installer.py", "unknown_installer.py"), OWNER)

    def test_missing_owner_safety_guard_rejected(self):
        with self.assertRaisesRegex(AssertionError, "OWNER_STAGE_LOCK"):
            verify_once(BASE, OWNER.replace("D02_CREATIVE_STAGE_ALREADY_PRESENT", "NO_SAFE_GUARD"))

    def test_multiple_wow_stages_in_owner_rejected(self):
        with self.assertRaisesRegex(AssertionError, "OWNER_STAGE_LOCK"):
            verify_once(BASE, OWNER + "\n& $py.Source $wowScript $source $wow\n")

    def test_missing_regression_gate_rejected(self):
        with self.assertRaisesRegex(AssertionError, "OWNER_REGRESSION_NOT_CALLED"):
            verify_once(BASE.replace("test_azure_visual_single_stage.py", "other.py"), OWNER)

    def test_current_repo_when_checkout_available(self):
        if not (PIPELINE.is_file() and BUILDER.is_file()):
            self.skipTest("Repository checkout not mounted; synthetic regressions still apply")
        verify_once(PIPELINE.read_text(encoding="utf-8"), BUILDER.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
