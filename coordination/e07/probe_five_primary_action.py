"""Pinned installed NOX primary-action UIA gate; read-only Windows QA, never release approval.

Invoke only BETWEEN original E07's verified NSIS install and uninstall on the SAME
candidate. Reuse existing reviewed GUI/UIA witnesses; no second GUI or backend.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from independent_setup_e07 import (Hold, clean_dir, clean_file, gui_hwnd,
                                   installed_file_sha_locked, manifest_owner, require)

PRIMARY = ("CHAT", "INSTALL", "MODELS", "LEARN", "SETTINGS")


def snapshot_installed_owner(install: Path) -> tuple:
    """Verify owned bytes and owner metadata both sides of the real GUI UIA run.

    The existing independent installed-manifest verifier binds every file SHA
    to its physical descriptor. A UIA navigation witness is not admissible if
    any owned byte or owner metadata changes while the GUI is running.
    Unknown and unowned user files are never modified, scanned, or removed.
    This is an identity witness ONLY, not a visual/function/release PASS.
    """
    _, files = manifest_owner(install)
    root = install.resolve(strict=True)
    meta = []
    for name in ("nox-p01-owned.txt", "payload.sha256.json"):
        item = install / name
        require(clean_file(item) and item.stat().st_size <= 8388608,
                "E07_PRIMARY_OWNER_METADATA_HOLD")
        size = item.stat().st_size
        digest = hashlib.sha256(item.read_bytes()).hexdigest()
        locked = installed_file_sha_locked(item, root, size, digest)
        require(locked == digest, "E07_PRIMARY_OWNER_METADATA_SHA_HOLD")
        meta.append((name, size, locked))
    owned_names = tuple(str(p.relative_to(install)) for p in files)
    return owned_names, tuple(meta)


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



def bounded_primary_diagnostics(witness: object) -> dict:
    """Bounded UIA status/error evidence only, never a click or release verdict."""
    if type(witness) is not dict:
        return {"error": "E07_PRIMARY_WITNESS_SCHEMA_HOLD"}

    def status(value: object, choices: tuple[str, ...], default: str) -> str:
        return value if type(value) is str and value in choices else default

    def error_code(value: object) -> str:
        return (value if type(value) is str and
                re.fullmatch(r"E07_[A-Z0-9_]{1,80}", value) else "NOT_REPORTED")

    def count(value: object, limit: int) -> int:
        return value if type(value) is int and 0 <= value <= limit else 0

    buttons = witness.get("five_primary_buttons")
    chat = witness.get("ui_chat_action_probe")
    nav = witness.get("ui_safe_primary_navigation")
    buttons = buttons if type(buttons) is dict else {}
    chat = chat if type(chat) is dict else {}
    nav = nav if type(nav) is dict else {}
    present = buttons.get("buttons_present")
    present = present if type(present) is list and len(present) <= 64 else []
    items = nav.get("per_action")
    items = items if type(items) is dict else {}
    return {
        "five_presence": {
            "status": status(buttons.get("status"), ("PASS", "HOLD"), "HOLD"),
            "present": [name for name in PRIMARY if name in present],
            "error_code": error_code(buttons.get("error")),
        },
        "chat": {
            "actions_invoked": count(chat.get("actions_invoked"), 1),
            "navigation_verified": status(chat.get("navigation_verified"),
                                          ("PASS", "NOT_TESTED", "HOLD"), "NOT_TESTED"),
            "error_code": error_code(chat.get("error")),
        },
        "four_navigation": {
            "actions_invoked": count(nav.get("actions_invoked"), 4),
            "navigation_verified": status(nav.get("navigation_verified"),
                                          ("PASS", "NOT_TESTED", "HOLD"), "NOT_TESTED"),
            "error_code": error_code(nav.get("error")),
            "per_action": {
                name: {
                    "button_actuated": status(items[name].get("button_actuated"),
                                              ("OBSERVED", "HOLD"), "HOLD"),
                    "navigation_verified": status(items[name].get("navigation_verified"),
                                                  ("PASS", "NOT_TESTED"), "NOT_TESTED"),
                }
                for name in PRIMARY[1:] if type(items.get(name)) is dict
            },
        },
    }

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
        pre_gui_owner = snapshot_installed_owner(install)
        require("NOX.P01.Shell.exe" in pre_gui_owner[0],
                "E07_PRIMARY_INSTALLED_SHELL_UNOWNED_HOLD")
        witness = gui_hwnd(install / "NOX.P01.Shell.exe", local, safe_nav=True)
        post_gui_owner = snapshot_installed_owner(install)
        require(pre_gui_owner == post_gui_owner,
                "E07_PRIMARY_OWNED_PAYLOAD_CHANGED_DURING_UIA_HOLD")
        receipt["owner_pre_post_gui_sha_verified_not_e07"] = True
        # Record the actual lower-layer first failure before evaluate() fail-closes.
        # Whitelist fields: do not leak UI text, paths, logs or user data.
        receipt["first_failure_diagnostics"] = bounded_primary_diagnostics(witness)
        # Save bounded exact-action outcomes BEFORE strict evaluation raises HOLD.
        # A previous receipt lost all four-button diagnostics on the first
        # incomplete navigation, slowing repair without strengthening safety.
        nav = witness.get("ui_safe_primary_navigation")
        action_results = nav.get("per_action") if type(nav) is dict else None
        if type(action_results) is dict:
            receipt["four_clicks_observed"] = {
                name: {
                    "button_actuated": (item.get("button_actuated")
                                        if item.get("button_actuated") in ("OBSERVED", "HOLD") else "HOLD"),
                    "navigation_verified": (item.get("navigation_verified")
                                            if item.get("navigation_verified") in ("PASS", "NOT_TESTED") else "NOT_TESTED")
                }
                for name, item in action_results.items()
                if name in PRIMARY[1:] and type(item) is dict
            }
        receipt.update({"source_setup": identity,
                        "installed_files_sha_verified": len(post_gui_owner[0]),
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
