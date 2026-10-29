#!/usr/bin/env python3
"""NOX V16 P04/P05 component gate. No model pulls, training, merge or release."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

CHECKS = (
    ("P04-PYTHON", [sys.executable, "-m", "unittest", "discover", "-s", "tests/P04", "-p", "test_*.py", "-v"]),
    ("P04-DOTNET", ["dotnet", "build", "Packages/P04/NoxP04.csproj", "-c", "Release", "--nologo"]),
    ("P04-RAG", ["dotnet", "run", "--project", "tests/P04/RagComponentHarness.csproj", "-c", "Release"]),
    ("P04-GPU-ACK", ["dotnet", "run", "--project", "tests/P04/GpuWorkerReceiptHarness.csproj", "-c", "Release"]),
    ("P05-FEED", ["dotnet", "run", "--project", "Packages/P05/Space/tests/SpaceFeedClientR16Smoke.csproj", "-c", "Release"]),
    ("P05-FRESHNESS", ["dotnet", "run", "--project", "Packages/P05/Space/tests/SpaceFeedSourceFreshnessR20.csproj", "-c", "Release"]),
)
REQUIRED = (
    "Packages/P04/model_snapshot_probe.py",
    "Packages/P04/NoxP04.csproj",
    "Packages/P05/Space/SpaceFeedClient.cs",
    "Packages/P05/Space/tests/SpaceFeedClientR16Smoke.csproj",
    "Packages/P05/Space/tests/SpaceFeedSourceFreshnessR20.csproj",
    "tests/P04/test_model_snapshot_probe.py",
)

def probe(args: argparse.Namespace) -> tuple[int, dict]:
    root = Path(args.repo_root).resolve()
    report = {
        "schema": "NOX-V16-MANUAL3-P04P05-COMPONENT-GATE-v1",
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "expected_head": args.expected_head,
        "actual_head": None,
        "status": "HOLD",
        "steps": [],
        "reason": None,
        "acceptance_boundary": "COMPONENT_ONLY; no live GPU, Windows EXE or E07 acceptance",
    }
    try:
        git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        if git.returncode:
            report["reason"] = "GIT_CHECKOUT_UNAVAILABLE"
            return 3, report
        report["actual_head"] = git.stdout.strip()
        if report["actual_head"] != args.expected_head:
            report["reason"] = "EXACT_HEAD_MISMATCH"
            return 3, report
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                               cwd=root, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=15)
        if dirty.returncode or dirty.stdout.strip():
            report["reason"] = "TRACKED_WORKTREE_DIRTY"
            return 3, report
        missing = [p for p in REQUIRED if not (root / p).is_file() or (root / p).is_symlink()]
        if missing:
            report["reason"] = "REQUIRED_SOURCES_MISSING"
            report["missing"] = missing
            return 3, report
        env = os.environ.copy()
        p02 = root / "Packages/P02/worker-python"
        if p02.is_dir() and not p02.is_symlink():
            env["NOX_P02_SOURCE_DIR"] = str(p02)
        for label, cmd in CHECKS:
            if cmd[0] == "dotnet" and not shutil.which("dotnet"):
                report["reason"] = "DOTNET8_SDK_UNAVAILABLE"
                return 3, report
            try:
                run = subprocess.run(cmd, cwd=root, env=env, text=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     timeout=args.step_timeout)
                log = run.stdout or ""
                entry = {"name": label, "exit": run.returncode,
                         "output_sha256": hashlib.sha256(log.encode()).hexdigest(),
                         "output_tail": log[-4000:]}
                report["steps"].append(entry)
                if run.returncode:
                    report["reason"] = "COMPONENT_FAILURE_" + label
                    report["status"] = "FAILED"
                    return 1, report
            except subprocess.TimeoutExpired:
                report["reason"] = "COMPONENT_TIMEOUT_" + label
                report["status"] = "FAILED"
                return 1, report
        final_git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                                   text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=15)
        if final_git.returncode or final_git.stdout.strip() != args.expected_head:
            report["reason"] = "HEAD_DRIFT_DURING_TESTS"
            return 3, report
        report["status"] = "COMPONENT_PASS_ONLY"
        report["reason"] = "INDEPENDENT_WINDOWS_GPU_AND_HOST_QA_PENDING"
        return 0, report
    except (OSError, ValueError) as exc:
        report["reason"] = "EXECUTION_ENVIRONMENT_UNAVAILABLE"
        report["exception_type"] = type(exc).__name__
        return 3, report

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True,
                        help="Exact 40-character Git commit SHA being tested")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[3]) if len(Path(__file__).resolve().parents) > 3 else str(Path.cwd()))
    parser.add_argument("--evidence", default=None, help="Output JSON receipt path outside the checkout")
    parser.add_argument("--step-timeout", type=int, default=240)
    args = parser.parse_args()
    if (len(args.expected_head) != 40 or
            any(c not in "0123456789abcdef" for c in args.expected_head) or
            not 30 <= args.step_timeout <= 1800):
        parser.error("expected-head must be a lowercase SHA-1 and timeout 30..1800 seconds")
    code, receipt = probe(args)
    output = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if args.evidence:
        dest = Path(args.evidence).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=dest.parent,
                                         prefix=".nox-source-gate-", delete=False) as f:
            f.write(output)
            staged = f.name
        os.replace(staged, dest)
    print(output)
    return code

if __name__ == "__main__":
    sys.exit(main())
