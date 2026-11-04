"""Pinned installed NOX primary-action UIA gate; read-only Windows QA, never release approval.

Invoke only BETWEEN original E07's verified NSIS install and uninstall on the SAME
candidate. Reuse existing reviewed GUI/UIA witnesses; no second GUI or backend.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from independent_setup_e07 import (Hold, clean_dir, clean_file, gui_hwnd,
                                   installed_file_sha_locked, manifest_owner, require)

PRIMARY = ("CHAT", "INSTALL", "MODELS", "LEARN", "SETTINGS")


def evaluate(witness: object) -> dict:
    """Do not upgrade button presence, attempted Invoke, or a stale heading to PASS."""
    if type(witness) is not dict:
        raise Hold("E07_PRIMARY_WITNESS_SCHEMA_HOLD")
    buttons = witness.get("five_primary_buttons")
    chat = witness.get("ui_chat_action_probe")
    nav = witness.get("ui_safe_primary_navigation")
    require(type(buttons) is dict and buttons.get("status") == "PASS" and
            buttons.get("buttons_present") == list(PRIMARY),
            "E07_PRIMARY_FIVE_BUTTON_PRESENCE_HOLD")
    require(type(chat) is dict and chat.get("action") == "CHAT" and
            chat.get("actions_invoked") == 1 and
            chat.get("method") == "NATIVE_UIA_INVOKEPATTERN" and
            chat.get("navigation_verified") == "PASS" and
            chat.get("navigation_proof") == "NEW_VISIBLE_UIA_CHAT_HEADING",
            "E07_PRIMARY_CHAT_CLICK_NAV_HOLD")
    require(type(nav) is dict and nav.get("actions_invoked") == 4 and
            nav.get("navigation_verified") == "PASS" and
            type(nav.get("per_action")) is dict and
            set(nav["per_action"]) == set(PRIMARY[1:]),
            "E07_PRIMARY_FOUR_CLICK_NAV_HOLD")
    for action in PRIMARY[1:]:
        item = nav["per_action"][action]
        require(type(item) is dict and
                item.get("button_actuated") == "OBSERVED" and
                item.get("navigation_verified") == "PASS" and
                item.get("function_verified") == "NOT_TESTED",
                "E07_PRIMARY_" + action + "_CLICK_NAV_HOLD")
    return {"status": "PASS", "actions_invoked": 5,
            "actions_with_new_visible_heading": list(PRIMARY),
            "scope": "FIVE_REAL_UIA_CLICKS_AND_NAVIGATION_ONLY",
            "install_or_model_function_verified": False,
            "live_inference_verified": False, "release_accepted": False}


def checked_source_setup(artifact_dir: Path, expected_source: str,
                         expected_setup: str) -> dict:
    """Bind the source and exact physical installer to producer receipts, not caller labels."""
    require(bool(re.fullmatch(r"[0-9a-f]{40}", expected_source)) and
            bool(re.fullmatch(r"[0-9a-f]{64}", expected_setup)),
            "E07_PRIMARY_BAD_SHA_ARGUMENT_HOLD")
    require(clean_dir(artifact_dir), "E07_PRIMARY_ARTIFACT_ROOT_HOLD")
    build = artifact_dir / "BUILD_RECEIPT.json"
    setup = artifact_dir / "NOX_HELION_EXPRESS_CANDIDATE_SETUP.exe"
    require(clean_file(build) and clean_file(setup) and
            build.stat().st_size <= 1048576,
            "E07_PRIMARY_ARTIFACT_INTEGRITY_HOLD")
    try:
        from independent_setup_e07 import _read_locked_e06_json
        receipt = _read_locked_e06_json(build)
    except (OSError, UnicodeError, ValueError):
        raise Hold("E07_PRIMARY_BUILD_RECEIPT_HOLD") from None
    require(receipt.get("source_commit") == expected_source and
            receipt.get("setup_sha256") == expected_setup and
            receipt.get("physical_setup_built") is True and
            receipt.get("release_accepted") is False and
            type(receipt.get("setup_bytes")) is int and
            receipt["setup_bytes"] == setup.stat().st_size and
            installed_file_sha_locked(setup, artifact_dir.resolve(strict=True),
                                     receipt["setup_bytes"], expected_setup) == expected_setup,
            "E07_PRIMARY_SOURCE_SETUP_BIND_HOLD")
    return {"source_sha": expected_source, "setup_sha256": expected_setup,
            "setup_bytes": setup.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--setup-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt: dict = {"schema": "NOX-E07-FIVE-UIA-CLICKS-v1", "status": "HOLD",
                     "release_accepted": False, "error": "NOT_RUN"}
    try:
        require(sys.platform == "win32" and
                os.environ.get("GITHUB_ACTIONS") == "true" and
                os.environ.get("RUNNER_OS") == "Windows" and
                os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted" and
                os.environ.get("GITHUB_REPOSITORY") == "MSSTXNEWS/nox-helion-pp-private-build",
                "E07_PRIMARY_UNAUTHORIZED_RUNNER_HOLD")
        identity = checked_source_setup(args.artifact_dir, args.source_sha, args.setup_sha)
        local = Path(os.environ["LOCALAPPDATA"])
        install = local / "Programs" / "NOX HELION"
        require(clean_dir(install) and not install.is_symlink() and
                not getattr(install, "is_junction", lambda: False)(),
                "E07_PRIMARY_INSTALLED_ROOT_HOLD")
        _, files = manifest_owner(install)  # SHA of EVERY owned installed byte
        require(install / "NOX.P01.Shell.exe" in files,
                "E07_PRIMARY_INSTALLED_SHELL_UNOWNED_HOLD")
        witness = gui_hwnd(install / "NOX.P01.Shell.exe", local, safe_nav=True)
        receipt.update({"source_setup": identity, "installed_files_sha_verified": len(files),
                        "five_primary": evaluate(witness), "status": "PASS", "error": None})
    except (Hold, OSError, KeyError, ValueError) as exc:
        receipt["error"] = str(exc) if isinstance(exc, Hold) else "E07_PRIMARY_RUNTIME_HOLD"
    finally:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2),
                            encoding="utf-8")
        print("NOX_E07_FIVE_UIA_CLICKS", receipt["status"], receipt["error"], flush=True)
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
