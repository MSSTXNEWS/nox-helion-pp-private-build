#!/usr/bin/env python3
"""NOX HELION MB1/T06: fail-closed read-only Windows build diagnostics.

Reuses the original T06 builder and its receipts; never edits a donor,
runner, installer, HOME/MENU/WORK, bridge, SourceLock, or shared ledger.
Run after the existing one-shot CI job:
    python coordination/mb1/t06_onepass_diagnostics.py --root .
Only an original same-SHA Windows receipt may classify a candidate PASS.
This is NEVER independent E07 acceptance.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

REASON = re.compile(r"^T06_[A-Z0-9_]{4,160}(?::[A-Za-z0-9_.-]{1,80})?$")
STEPS = (
    "preflight_original", "preflight_final", "install",
    "verify", "native_ipc", "original_wpf_gui",
    "update", "rollback", "uninstall",
)
PASS_PHASE = "INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PASS_NOT_E07"
CANDIDATE_PHASE = "ONEHOST_NSIS_CANDIDATE_SOURCE_ONLY"
SOURCE_SHA = re.compile(r"^[a-f0-9]{40}$")
DIGEST = re.compile(r"^[a-f0-9]{64}$")


def safe_json(root: Path, relative: str) -> dict | None:
    """Read only fixed, regular receipt locations under an unlinked root."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("T06_UNTRUSTED_ROOT")
    obj = root
    for part in Path(relative).parts:
        if part in ("", ".", "..") or part.startswith("."):
            raise ValueError("T06_UNSAFE_RECEIPT_PATH")
        obj = obj / part
        if obj.is_symlink():
            raise ValueError("T06_RECEIPT_REPARSE_HOLD")
    if not obj.exists():
        return None
    if not obj.is_file() or obj.stat().st_size > 1024 * 1024:
        raise ValueError("T06_RECEIPT_SIZE_OR_TYPE_HOLD")
    value = json.loads(obj.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("T06_RECEIPT_OBJECT_REQUIRED")
    return value


def classify(bridge: dict | None, smoke: dict | None) -> dict:
    """No inference of product readiness from tests, logs or source reports."""
    result = {
        "schema": "NOX-MB1-T06-ONEPASS-DIAGNOSTIC-v1",
        "status": "NOT_RUN",
        "failure_gate": "T06_INSTALLED_RECEIPT_MISSING",
        "source_sha": None,
        "steps": [],
        "independent_e07": "NOT_RUN",
        "release_accepted": False,
    }
    if not isinstance(bridge, dict) and not isinstance(smoke, dict):
        return result
    result["status"] = "HOLD"
    sha = bridge.get("gitlab_sha") if isinstance(bridge, dict) else None
    if isinstance(sha, str) and SOURCE_SHA.fullmatch(sha):
        result["source_sha"] = sha
    reason = smoke.get("reason") if isinstance(smoke, dict) else None
    if isinstance(reason, str) and REASON.fullmatch(reason):
        result["failure_gate"] = reason.split(":", 1)[0]
    elif isinstance(smoke, dict):
        result["failure_gate"] = "T06_INSTALLED_SMOKE_UNCLASSIFIED_HOLD"

    lifecycle = smoke.get("installer_lifecycle") if isinstance(smoke, dict) else None
    lifecycle = lifecycle if isinstance(lifecycle, dict) else {}
    for name in STEPS:
        value = lifecycle.get(name)
        if not isinstance(value, dict):
            continue
        code = value.get("code", value.get("exit_code"))
        if type(code) is int and -32768 <= code <= 32768:
            outcome = "EXIT_" + str(code)
        elif value.get("status") == "PASS":
            outcome = "PASS"
        elif name == "original_wpf_gui":
            outcome = ("PASS" if
                       value.get("new_nav_ok") is True and
                       value.get("new_python_ipc_handshake") is True
                       else "HOLD")
        else:
            outcome = "UNKNOWN"
        result["steps"].append({"step": name, "result": outcome})

    # All conditions necessary, not sufficient for final Release 1.
    gui = lifecycle.get("original_wpf_gui")
    approved = isinstance(smoke, dict) and smoke.get(
        "original_home_and_core01_sha_verified") is True
    candidate = isinstance(bridge, dict) and bridge.get("phase") == CANDIDATE_PHASE
    source = bool(result["source_sha"])
    if (source and candidate and isinstance(smoke, dict) and
        smoke.get("phase") == PASS_PHASE and
        smoke.get("release_accepted") is False and
        smoke.get("e07_independent_acceptance") == "NOT_RUN" and
        isinstance(gui, dict) and gui.get("new_nav_ok") is True and
        gui.get("new_python_ipc_handshake") is True and approved):
        result["status"] = "SOURCE_CANDIDATE_PASS_NOT_E07"
        result["failure_gate"] = None
    elif reason is None and not isinstance(smoke, dict):
        result["failure_gate"] = "T06_INSTALLED_RECEIPT_MISSING"
    return result


def inspect(root: Path) -> dict:
    bridge = safe_json(root, "work/t06-local-bridge/ONEHOST_LOCAL_BRIDGE_RESULT.json")
    smoke = safe_json(root, "work/t06-local-bridge/T06_INSTALLED_SMOKE.json")
    return classify(bridge, smoke)


def self_test() -> None:
    import unittest
    class Checks(unittest.TestCase):
        def test_no_receipt_is_not_a_pass(self):
            self.assertEqual(classify(None, None)["status"], "NOT_RUN")
        def test_specific_failure_survives_generic_parent_hold(self):
            result = classify({"phase": "HOLD", "gitlab_sha": "a" * 40},
                              {"reason": "T06_INSTALLED_BACKEND_FRAME_ABSENT"})
            self.assertEqual(result["failure_gate"],
                             "T06_INSTALLED_BACKEND_FRAME_ABSENT")
        def test_bogus_phase_cannot_grant_release(self):
            obj = classify({"phase": CANDIDATE_PHASE, "gitlab_sha": "a" * 40},
                           {"phase": PASS_PHASE, "release_accepted": True,
                            "installer_lifecycle": {"original_wpf_gui": {
                                "new_nav_ok": True, "new_python_ipc_handshake": True}},
                            "original_home_and_core01_sha_verified": True,
                            "e07_independent_acceptance": "NOT_RUN"})
            self.assertEqual(obj["status"], "HOLD")
            self.assertFalse(obj["release_accepted"])
        def test_bad_untrusted_gate_is_filtered(self):
            obj = classify(None, {"reason": "T06_OK:secret=12345"})
            self.assertEqual(obj["failure_gate"],
                             "T06_INSTALLED_SMOKE_UNCLASSIFIED_HOLD")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    if not unittest.TextTestRunner(verbosity=0).run(suite).wasSuccessful():
        raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    try:
        result = inspect(args.root.resolve())
    except (ValueError, OSError, json.JSONDecodeError, UnicodeError):
        result = classify({"phase": "HOLD"}, {"reason": "T06_RECEIPT_READ_HOLD"})
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["status"] == "SOURCE_CANDIDATE_PASS_NOT_E07" else 1


if __name__ == "__main__":
    sys.exit(main())
