"""Isolated fail-closed contract tests for the existing P04/P05 source gate.

Pure stdlib mocks; no real compiler, model, network or GitLab acceptance.
"""
from __future__ import annotations
import argparse
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

GATE_PATH = Path(__file__).resolve().parents[2] / "coordination/manual/no3/verify_p04_p05_components.py"
spec = importlib.util.spec_from_file_location("nox_component_gate", GATE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

_HEAD = "a" * 40
_REQUIRED = (
    "Packages/P04/model_snapshot_probe.py",
    "Packages/P04/NoxP04.csproj",
    "Packages/P05/Space/SpaceFeedClient.cs",
    "Packages/P05/Space/tests/SpaceFeedClientR16Smoke.csproj",
    "Packages/P05/Space/tests/SpaceFeedSourceFreshnessR20.csproj",
    "tests/P04/test_model_snapshot_probe.py",
)


def _fixture_result(cmd, *, mode="valid", **kwargs):
    label = " ".join(map(str, cmd))
    if cmd[:3] == ["git", "rev-parse", "HEAD"]:
        return subprocess.CompletedProcess(cmd, 0, stdout=_HEAD + "\n")
    if cmd[:2] == ["git", "status"]:
        return subprocess.CompletedProcess(cmd, 0, stdout="")
    if "unittest" in cmd:
        output = "Ran 40 tests in 0.01s\n\nOK\n"
    elif "RagComponentHarness" in label:
        output = "" if mode == "missing_rag" else "P04_RAG_SYNTHETIC_COMPONENT_PASS: 11 checks; NO_REAL_OLLAMA_OR_GPU\n"
    elif "GpuWorkerReceiptHarness" in label:
        output = "" if mode == "missing_gpu" else "PASS: receipt-gated worker STOP/PAUSE/RESUME, disposal and in-flight control race.\n"
    elif "SpaceFeedClientR16Smoke" in label:
        count = 23 if mode == "short_feed" else 24
        output = "PASS fixture\n" * count + "P05 R16 smoke: 24 semantic assertions PASS (only after this .NET 8 program actually runs)\n"
    elif "SpaceFeedSourceFreshnessR20" in label:
        count = 6 if mode == "short_freshness" else 7
        output = "PASS fixture\n" * count + "P05 SOURCE_FRESHNESS 7/7 semantic checks defined (runtime execution required)\n"
    else:
        output = "Build succeeded.\n"
    return subprocess.CompletedProcess(cmd, 0, stdout=output)


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for item in _REQUIRED:
            path = self.root / item
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("offline dummy fixture\n", encoding="utf-8")
        self.args = argparse.Namespace(repo_root=str(self.root), expected_head=_HEAD, step_timeout=30)

    def run_gate(self, mode="valid"):
        def fake_run(cmd, **kwargs):
            return _fixture_result(cmd, mode=mode, **kwargs)
        with patch.object(gate.subprocess, "run", side_effect=fake_run), patch.object(gate.shutil, "which", return_value="dotnet"):
            return gate.probe(self.args)

    def test_all_six_known_proofs_pass_as_component_only(self):
        code, report = self.run_gate()
        self.assertEqual((code, report["status"]), (0, "COMPONENT_PASS_ONLY"))
        self.assertEqual(len(report["steps"]), 6)
        self.assertNotIn("QA_ACCEPTED", report["status"])

    def test_missing_rag_marker_fails(self):
        code, report = self.run_gate("missing_rag")
        self.assertEqual((code, report["reason"]), (1, "P04_RAG_PROOF_MISSING"))

    def test_missing_gpu_marker_fails(self):
        code, report = self.run_gate("missing_gpu")
        self.assertEqual((code, report["reason"]), (1, "P04_GPU_ACK_PROOF_MISSING"))

    def test_short_feed_markers_fail(self):
        code, report = self.run_gate("short_feed")
        self.assertEqual((code, report["reason"]), (1, "P05_FEED_ASSERTION_COUNT_MISMATCH"))

    def test_short_freshness_markers_fail(self):
        code, report = self.run_gate("short_freshness")
        self.assertEqual((code, report["reason"]), (1, "P05_FRESHNESS_ASSERTION_COUNT_MISMATCH"))

    def test_head_drift_fails_before_component_execution(self):
        self.args.expected_head = "b" * 40
        code, report = self.run_gate()
        self.assertEqual((code, report["reason"]), (3, "EXACT_HEAD_MISMATCH"))
        self.assertEqual(len(report["steps"]), 0)


if __name__ == "__main__":
    unittest.main()
