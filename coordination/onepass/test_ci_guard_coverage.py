"""V149/V150: prevent silent loss of Windows/STOP/Resonance source CI gates.

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
RESONANCE = ROOT / ".github/workflows/nox-v135-resonance-owner-source-ci.yml"


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


    def test_original_full_resonance_sse_s03_gate_covers_canonical_and_pr(self):
        source = RESONANCE.read_text(encoding="utf8")
        assert_covered(source, (
            "coordination/onepass/nox-v135-resonance-owner-bridge.js",
            "coordination/onepass/test_v135_resonance_owner_bridge.cjs",
            "coordination/onepass/test_v135_resonance_owner_stage.py",
            "coordination/onepass/test_ci_guard_coverage.py",
        ))
        for command in (
            "node --test coordination/onepass/test_v135_resonance_owner_bridge.cjs",
            "python3 -m unittest -v coordination.onepass.test_v135_resonance_owner_stage",
            "python3 -m unittest -v coordination.onepass.test_ci_guard_coverage",
            "NOX_V135_LIVE_SERVER_DEPLOYED=false",
            "NOX_V135_NATIVE_COOKIE_E2E_VERIFIED=false",
        ):
            self.assertIn(command, source)

    def test_resonance_gate_regression_rejects_missing_branch_or_sse_path(self):
        source = RESONANCE.read_text(encoding="utf8")
        with self.assertRaisesRegex(AssertionError, "HOLD_CANONICAL_PUSH_NOT_COVERED"):
            assert_covered(source.replace(CANON, "fix/obsolete-branch"), (
                "coordination/onepass/test_v135_resonance_owner_bridge.cjs",
            ))
        missing = "      - 'coordination/onepass/test_v135_resonance_owner_bridge.cjs'\n"
        with self.assertRaisesRegex(AssertionError, "HOLD_CI_PATH_NOT_COVERED"):
            assert_covered(source.replace(missing, ""), (
                "coordination/onepass/test_v135_resonance_owner_bridge.cjs",
            ))


if __name__ == "__main__":
    unittest.main()
