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



# V151: the 92 WEB routes and Windows/OneHost authority must not drift silently.
# This audits source manifests only; no native route, owner cookie or backup is called.
ROUTE_PLAN = ROOT / "coordination/NOX_WEB_V293_92_ROUTE_HOST_PLAN.json"
FROZEN_92 = ROOT / "coordination/NOX_V98_WEB_FULL_REAL_API_MATRIX.json"
PC_ONLY = frozenset((
    "/api/install/", "/api/install/apply", "/api/install/backup",
    "/api/install/capabilities", "/api/install/operation", "/api/install/report",
    "/api/install/scan", "/api/install/source", "/api/install/verify",
    "/api/install/voice", "/api/pc-metrics", "/api/unified/build",
    "/api/voice/speech", "/api/voice/status", "/api/voice/transcribe",
    "/api/voice/transcribe/stop",
))
WINDOWS_BOUNDARY = "WINDOWS_OWNER_PC_REQUIRED_NOT_VAST_METRICS"
ONEHOST_BOUNDARY = "EXISTING_ONEHOST"
# V152: pinned source host classifications from V151, not native proof.
# Any host reclassification requires a reviewed baseline and new acceptance.
FROZEN_EXISTING_ONEHOST = frozenset((
    "/api/health",
    "/api/nox/activity",
    "/api/nox/chat/stream",
    "/api/nox/experience",
    "/api/nox/history",
    "/api/nox/memory",
    "/api/nox/model",
    "/api/nox/premium/capabilities",
    "/api/nox/premium/status",
    "/api/nox/status",
    "/api/nox/stop",
    "/api/nox/system/processes",
    "/api/nox/training/status",
    "/api/status",
    "/api/training/status",
    "/api/ui/capabilities",
    "/api/ui/memory/dialogs",
    "/api/ui/memory/dialogs/create",
    "/api/ui/memory/dialogs/history",
    "/api/ui/memory/dialogs/status",
    "/api/ui/memory/dialogs/update",
    "/api/ui/memory/facts/history",
    "/api/ui/memory/status",
))
FROZEN_EXTERNAL_CONSENT = frozenset((
    "/api/push/ack",
    "/api/push/status",
    "/api/push/subscribe",
    "/api/push/test",
    "/api/push/unsubscribe",
    "/api/ui/push/",
    "/api/ui/push/ack",
    "/api/ui/push/status",
    "/api/ui/services/fx",
    "/api/ui/services/geocode",
    "/api/ui/services/news",
    "/api/ui/services/weather",
))
UNVERIFIED_BOUNDARY = "REQUIRES_ORIGINAL_CALLSITE_AND_OWNER_HOST_VERIFICATION"
EXTERNAL_BOUNDARY = "BROWSER_CONSENT_OR_EXTERNAL_PROVIDER_REVIEW"


def assert_original_92_owner_boundary(plan: dict, frozen: dict) -> None:
    """Reject a missing/duplicate route or an unreviewed Windows authority change."""
    rows = plan.get("functions")
    original = frozen.get("functions")
    if not isinstance(rows, list) or not isinstance(original, list):
        raise AssertionError("HOLD_92_ROUTE_MATRIX_MISSING")
    names = [item.get("route") for item in rows]
    frozen_names = [item.get("route") for item in original]
    if (len(names) != 92 or len(set(names)) != 92 or
            len(frozen_names) != 92 or len(set(frozen_names)) != 92 or
            set(names) != set(frozen_names)):
        raise AssertionError("HOLD_92_FROZEN_ROUTE_SET_DRIFT")
    by_path = {item["route"]: item for item in rows}
    pc_actual = {route for route, item in by_path.items()
                 if item.get("host_boundary") == WINDOWS_BOUNDARY}
    if pc_actual != PC_ONLY:
        raise AssertionError("HOLD_92_WINDOWS_OWNER_HOST_BOUNDARY_DRIFT")
    # V151 pinned 16 Windows routes and three OneHost routes only.
    # Any other reclassification, including equal-count swaps, used to pass.
    onehost_actual = {route for route, item in by_path.items()
                      if item.get("host_boundary") == ONEHOST_BOUNDARY}
    if onehost_actual != FROZEN_EXISTING_ONEHOST:
        raise AssertionError("HOLD_92_ONEHOST_ROUTE_BOUNDARY_DRIFT")
    external_actual = {route for route, item in by_path.items()
                       if item.get("host_boundary") == EXTERNAL_BOUNDARY}
    if external_actual != FROZEN_EXTERNAL_CONSENT:
        raise AssertionError("HOLD_92_EXTERNAL_CONSENT_BOUNDARY_DRIFT")
    unresolved_expected = set(names) - PC_ONLY - FROZEN_EXISTING_ONEHOST - FROZEN_EXTERNAL_CONSENT
    unresolved_actual = {route for route, item in by_path.items()
                         if item.get("host_boundary") == UNVERIFIED_BOUNDARY}
    if unresolved_actual != unresolved_expected:
        raise AssertionError("HOLD_92_UNVERIFIED_HOST_BOUNDARY_DRIFT")
    for path in ("/api/nox/status", "/api/nox/chat/stream", "/api/nox/memory"):
        if by_path[path].get("host_boundary") != ONEHOST_BOUNDARY:
            raise AssertionError("HOLD_92_ONEHOST_BOUNDARY_DRIFT_" + path)
    if by_path["/api/nox/memory/facts"].get("host_boundary") != (
            "REQUIRES_ORIGINAL_CALLSITE_AND_OWNER_HOST_VERIFICATION"):
        raise AssertionError("HOLD_92_S03_WRITER_OWNER_UNVERIFIED_BOUNDARY_DRIFT")
    for route, item in by_path.items():
        evidence = item.get("functional_e2e")
        if evidence not in (
                "NOT_CLAIMED", "SCOPED_PHYSICAL_OWNER_HTTP_S03_EVIDENCE",
                "SCOPED_REAL_READ_ONLY_HTTP_ACCEPTED"):
            raise AssertionError("HOLD_92_UNATTESTED_FUNCTIONAL_PASS_" + route)
        if evidence != "NOT_CLAIMED" and item.get("host_boundary") != ONEHOST_BOUNDARY:
            raise AssertionError("HOLD_92_SCOPED_HTTP_EVIDENCE_WRONG_HOST_" + route)
    if plan.get("gate_policy", "").find("independent live acceptance") < 0:
        raise AssertionError("HOLD_92_NO_LIVE_ACCEPTANCE_GATE")


class Original92WindowsOwnerBoundary(unittest.TestCase):
    @staticmethod
    def fixtures():
        import json
        return (json.loads(ROUTE_PLAN.read_text(encoding="utf8")),
                json.loads(FROZEN_92.read_text(encoding="utf8")))

    def test_frozen_92_routes_are_not_conflated_with_windows_or_onehost(self):
        assert_original_92_owner_boundary(*self.fixtures())

    def test_regression_rejects_wrong_host_missing_route_and_false_e2e(self):
        from copy import deepcopy
        plan, frozen = self.fixtures()
        wrong = deepcopy(plan)
        next(item for item in wrong["functions"]
             if item["route"] == "/api/install/backup")["host_boundary"] = ONEHOST_BOUNDARY
        with self.assertRaisesRegex(AssertionError, "HOLD_92_WINDOWS_OWNER_HOST_BOUNDARY_DRIFT"):
            assert_original_92_owner_boundary(wrong, frozen)
        incomplete = deepcopy(plan)
        incomplete["functions"] = [x for x in incomplete["functions"]
                                   if x["route"] != "/api/nox/memory/facts"]
        with self.assertRaisesRegex(AssertionError, "HOLD_92_FROZEN_ROUTE_SET_DRIFT"):
            assert_original_92_owner_boundary(incomplete, frozen)
        false_pass = deepcopy(plan)
        next(item for item in false_pass["functions"]
             if item["route"] == "/api/install/backup")["functional_e2e"] = "PASS"
        with self.assertRaisesRegex(AssertionError, "HOLD_92_UNATTESTED_FUNCTIONAL_PASS"):
            assert_original_92_owner_boundary(false_pass, frozen)

    def test_regression_rejects_equal_count_host_swap_and_external_consent_drift(self):
        # V152 reproduction: before patch, this equal-count swap passed V151.
        from copy import deepcopy
        plan, frozen = self.fixtures()
        swapped = deepcopy(plan)
        next(x for x in swapped["functions"] if x["route"] == "/api/health")[
            "host_boundary"] = UNVERIFIED_BOUNDARY
        next(x for x in swapped["functions"] if x["route"] == "/api/chat")[
            "host_boundary"] = ONEHOST_BOUNDARY
        with self.assertRaisesRegex(AssertionError, "HOLD_92_ONEHOST_ROUTE_BOUNDARY_DRIFT"):
            assert_original_92_owner_boundary(swapped, frozen)

        external = deepcopy(plan)
        next(x for x in external["functions"] if x["route"] == "/api/ui/services/news")[
            "host_boundary"] = UNVERIFIED_BOUNDARY
        with self.assertRaisesRegex(AssertionError, "HOLD_92_EXTERNAL_CONSENT_BOUNDARY_DRIFT"):
            assert_original_92_owner_boundary(external, frozen)

        unexpected = deepcopy(plan)
        next(x for x in unexpected["functions"] if x["route"] == "/api/chat")[
            "host_boundary"] = "INVENTED_NATIVE_OWNER_PASS"
        with self.assertRaisesRegex(AssertionError, "HOLD_92_UNVERIFIED_HOST_BOUNDARY_DRIFT"):
            assert_original_92_owner_boundary(unexpected, frozen)

if __name__ == "__main__":
    unittest.main()
