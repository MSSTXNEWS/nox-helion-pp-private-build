"""V149: prevent silent loss of original Windows PC/owner and FORGE STOP CI gates.

Only checks GitHub workflow scope. No remote host access, S03, GPU, backup POST,
credentials or production promotion. The source-only result stays HOLD live.
"""
from __future__ import annotations
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CANON = "feature/nox-v38-synaptic-brain-20261114"
WINDOWS = ROOT / ".github/workflows/nox-onepass-windows-safe-source.yml"
FORGE = ROOT / ".github/workflows/nox-v135-forge-stop-callback-source.yml"


def scoped_event(source: str, event: str) -> str:
    match = re.search(
        r"(?ms)^  " + re.escape(event) +
        r":\n(.*?)(?=^  (?:push|pull_request):|^permissions:|\Z)", source
    )
    if not match:
        raise AssertionError("HOLD_CI_EVENT_NOT_DEFINED_" + event)
    return match.group(1)


def assert_covered(source: str, required_paths: tuple[str, ...]) -> None:
    push = scoped_event(source, "push")
    branch = re.search(r"(?m)^    branches:\s*\[([^\n]+)\]", push)
    if not branch or CANON not in [x.strip() for x in branch.group(1).split(",")]:
        raise AssertionError("HOLD_CANONICAL_PUSH_NOT_COVERED")
    pr = scoped_event(source, "pull_request")
    for path in required_paths:
        token = "'" + path + "'"
        if token not in push or token not in pr:
            raise AssertionError("HOLD_CI_PATH_NOT_COVERED_" + path)


class ContinuousGateCoverage(unittest.TestCase):
    def test_real_windows_pc_source_gate_runs_after_feature_merge(self):
        source = WINDOWS.read_text(encoding="utf8")
        assert_covered(source, (
            "coordination/onepass/windows/**",
            "coordination/onepass/test_windows_pc_owner_probe.py",
            "coordination/onepass/test_windows_receipt_no_clobber.py",
            "coordination/onepass/test_ci_guard_coverage.py",
        ))
        for command in (
            "coordination.onepass.test_windows_pc_owner_probe",
            "coordination.onepass.test_windows_receipt_no_clobber",
            "coordination.onepass.test_ci_guard_coverage",
            "command -v pwsh",
            "NOX_WINDOWS_PC_OWNER_COOKIE_E2E=HOLD",
            "NOX_WINDOWS_BACKUP_NATIVE_HANDLER=HOLD",
        ):
            self.assertIn(command, source)

    def test_fullweight_original_forge_stop_gate_runs_after_feature_merge(self):
        source = FORGE.read_text(encoding="utf8")
        assert_covered(source, (
            "nox_runpod/teacher_mesh/v135/train_full_base_zero3.py",
            "nox_runpod/teacher_mesh/v135/tests/test_training_stop_lifecycle.py",
            "coordination/onepass/test_ci_guard_coverage.py",
        ))
        for command in (
            "nox_runpod.teacher_mesh.v135.tests.test_training_stop_lifecycle",
            "nox_runpod.teacher_mesh.v135.tests.test_fullbase_distillation",
            "coordination.onepass.test_ci_guard_coverage",
            "NOX_FORGE_NATIVE_OPTIMIZER_STEPS_VERIFIED=0",
        ):
            self.assertIn(command, source)

    def test_regression_kills_canonical_branch_and_missing_test_path(self):
        source = WINDOWS.read_text(encoding="utf8")
        with self.assertRaisesRegex(AssertionError, "HOLD_CANONICAL_PUSH_NOT_COVERED"):
            assert_covered(source.replace(CANON, "fix/irrelevant-old-branch"), (
                "coordination/onepass/test_windows_pc_owner_probe.py",
            ))
        with self.assertRaisesRegex(AssertionError, "HOLD_CI_PATH_NOT_COVERED"):
            assert_covered(source.replace(
                "      - 'coordination/onepass/test_windows_pc_owner_probe.py'\n", ""
            ), ("coordination/onepass/test_windows_pc_owner_probe.py",))


if __name__ == "__main__":
    unittest.main()
