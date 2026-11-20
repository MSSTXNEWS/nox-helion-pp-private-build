"""Owner #2 diagnostic-only adapter: reuse E06's existing compiler fixes on a pinned R08 copy.

No canonical R11, D02, P03/P05, SQLite or other owner file is changed.
The E06 original source preimage manifest and each foreign-owner source are immutable
in the checkouts. This prepares only an isolated Windows CI compilation stage.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

LEGACY_SCRIPT = Path("coordination/e06/patch_legacy_compiler.py").resolve()
R08_MAINWINDOW_SHA256 = "b4c20c71380c63cec07c7ea4017c4f44f55077a985d2bfec42ecfe5f1a2b8825"


def main() -> None:
    if not LEGACY_SCRIPT.is_file() or LEGACY_SCRIPT.is_symlink():
        raise SystemExit("E06_PINNED_COMPILER_SCRIPT_MISSING")
    spec = importlib.util.spec_from_file_location("e06_existing_compiler_fixes", LEGACY_SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit("E06_COMPILER_SCRIPT_UNREADABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = module.HOST / "MainWindow.xaml.cs"
    observed = hashlib.sha256(original.read_bytes()).hexdigest()
    if observed != R08_MAINWINDOW_SHA256:
        raise SystemExit("R08_MAINWINDOW_EXACT_PREIMAGE_HOLD:" + observed)
    # Only source SHA differs between old P01 donor and additive R08.
    # Delegate all existing syntax fixes, original source backups and receipts
    # to the previously proven owner-6 helper. Every other SHA stays pinned.
    module.EXPECT["MainWindow.xaml.cs"] = R08_MAINWINDOW_SHA256
    module.main()


if __name__ == "__main__":
    main()
